#!/usr/bin/env python3
"""Data diode: validate command → run in temp dir → compress → serve via nginx."""
import http.server
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import threading
import io
from urllib.parse import urlparse, parse_qs, quote

DATA = "/data"
TEMP = f"{DATA}/temp"
OUT = f"{DATA}/out"
MAX_BYTES = 100_000_000
WEEK = 7 * 86400

# ── origin whitelist ───────────────────────────────────────────────────
ALLOWED_URLS = (
    "https://github.com/", "https://gitlab.com/",
    "https://codeload.github.com/", "https://raw.githubusercontent.com/",
    "https://registry.npmjs.org/", "https://files.pythonhosted.org/",
    "https://pypi.org/", "https://cache.nixos.org/",
    "https://registry-1.docker.io/", "https://ghcr.io/",
    "https://quay.io/",
)

URL_RE = re.compile(r'https?://\S+')
SHELL_META = re.compile(r'[;|&$`(){}\[\]<>`\n\r]')

# ── known-good command patterns ────────────────────────────────────────
URL_PAT = '|'.join(re.escape(u) for u in ALLOWED_URLS)
DIR = r'[a-zA-Z0-9._/-]+'
PKG = r'[a-zA-Z0-9@_.-]+'

PATTERNS = [
    # git clone --depth=N [--quiet] <url> <dir>
    rf'^git\s+clone\s+(?:--depth\s+\d+\s+|--filter\s+\S+\s+|--quiet\s+)*--single-branch\s+{URL_PAT}+{DIR}$',
    # git archive --remote <url> HEAD:./ > out.tar
    rf'^git\s+archive\s+--remote\s+{URL_PAT}+HEAD:./$',
    # npm pack|install <pkg>
    rf'^npm\s+(?:pack|install)\s+{PKG}(@\S+)?$' if 'PKG' in dir() else rf'^npm\s+(?:pack|install)\s+[a-zA-Z0-9@_.-]+$',
    # pip download [--dest D] <pkg>
    rf'^pip\s+download\s+(?:--dest\s+{DIR}\s+)?{PKG}(@\S+)?$',
    # python3 -m pip download …
    rf'^python3?\s+-m\s+pip\s+download\s+(?:--dest\s+{DIR}\s+)?{PKG}(@\S+)?$',
    # podman save [--quiet] <image>
    rf'^podman\s+save\s+(?:--quiet\s+)?[a-zA-Z0-9._/:@-]+$',
    # nix copy --from <store> <path> | nix prefetch hash|url <arg>
    rf'^nix\s+copy\s+--from\s+\S+\s+\S+$',
    rf'^nix\s+prefetch\s+(?:hash|url)\s+\S+$',
    # curl -fSL -o <file> <url>
    rf'^curl\s+-fSL\s+-o\s+{DIR}\s+{URL_PAT}+$',
    # wget -O <file> <url> | wget <url>
    rf'^wget\s+(?:-O\s+{DIR}\s+)?{URL_PAT}+$',
    # tar --extract --file <archive>
    rf'^tar\s+(?:--extract\s+|[-x]\S*)\s+--file\s+\S+(-to-stdout\s*)?$',
    # cat <local-file>
    rf'^cat\s+{DIR}$',
]
COMPILED = [re.compile(p) for p in PATTERNS]


def has_good_url(cmd: str) -> bool:
    """Every URL in the command must match an allowed origin."""
    for m in URL_RE.finditer(cmd):
        url = m.group()
        if not any(url.startswith(u) for u in ALLOWED_URLS):
            return False
    return True


def validate(cmd: str) -> bool:
    """True only if command is a known-good data-export with no injection."""
    cmd = cmd.strip()
    if not cmd:
        return False
    if SHELL_META.search(cmd):
        return False
    if not has_good_url(cmd):
        # some commands (npm, cat, podman) don't have URLs — ok
        has_url = bool(URL_RE.search(cmd))
        if has_url:
            return False
    for pat in COMPILED:
        if pat.match(cmd):
            return True
    return False


# ── xml listings ───────────────────────────────────────────────────────
def dir_size(path: str) -> int:
    total = 0
    try:
        for e in os.scandir(path):
            if e.is_file():
                total += e.stat().st_size
            elif e.is_dir():
                total += dir_size(e.path)
    except OSError:
        pass
    return total


def gen_xml(path: str) -> bytes:
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n<listing path="{path}">\n']
    try:
        entries = os.listdir(path)
    except FileNotFoundError:
        entries = []
    for name in sorted(entries, key=lambda f: os.path.getmtime(os.path.join(path, f)), reverse=True):
        fp = os.path.join(path, name)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        mtime = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))
        if os.path.isdir(fp):
            sz = dir_size(fp)
            try:
                count = len(os.listdir(fp))
            except OSError:
                count = 0
            parts.append(f'  <dir name="{name}" entries="{count}" size="{sz}" modified="{mtime}"/>\n')
        else:
            parts.append(f'  <file name="{name}" size="{st.st_size}" modified="{mtime}"/>\n')
    parts.append('</listing>')
    return ''.join(parts).encode()


# ── task runner ────────────────────────────────────────────────────────
tasks = {}
lock = threading.Lock()


def startup_cleanup():
    print("[worker] startup cleanup", file=sys.stderr)
    shutil.rmtree(TEMP, ignore_errors=True)
    os.makedirs(TEMP, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    now = time.time()
    for f in os.listdir(OUT):
        p = os.path.join(OUT, f)
        if os.path.isfile(p) and now - os.path.getmtime(p) > WEEK:
            os.unlink(p)
            print(f"  removed stale {f}", file=sys.stderr)


def run_task(tid: str, cmd: str):
    tdir = os.path.join(TEMP, tid)
    os.makedirs(tdir, exist_ok=True)
    with lock:
        tasks[tid] = {"dir": tdir, "done": False, "failed": False, "sha": None}

    try:
        # run command, stream stdout/stderr to download.log
        proc = subprocess.Popen(
            cmd, shell=True, cwd=tdir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        with lock:
            tasks[tid]["proc"] = proc

        with open(f"{tdir}/download.log", "w") as lf:
            lf.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] CMD: {cmd}\n")
            lf.flush()
            for line in proc.stdout:
                lf.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] {line.decode('utf-8', errors='replace')}")
                lf.flush()
            proc.wait(timeout=600)
            lf.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] EXIT: {proc.returncode}\n")

        if proc.returncode != 0:
            with lock:
                tasks[tid]["done"] = tasks[tid]["failed"] = True
            print(f"[worker] {tid} failed (exit {proc.returncode})", file=sys.stderr)
            return

        # compress temp dir → out/{tid}.tar.gz
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for e in sorted(os.listdir(tdir)):
                tar.add(os.path.join(tdir, e), arcname=e)
        buf.seek(0)
        sha = hashlib.sha256(buf.read()).hexdigest()[:12]
        buf.seek(0)

        out_path = os.path.join(OUT, f"{tid}-{sha}.tag.gz")
        with open(out_path, "wb") as f:
            f.write(buf.read())

        with lock:
            tasks[tid]["done"] = tasks[tid].get("failed", False) or False
            tasks[tid]["sha"] = sha
            tasks[tid].pop("proc", None)
        print(f"[worker] {tid} done → {os.path.basename(out_path)}", file=sys.stderr)

    except subprocess.TimeoutExpired:
        with lock:
            tasks[tid]["done"] = tasks[tid]["failed"] = True
        print(f"[worker] {tid} timed out", file=sys.stderr)
    except Exception as e:
        print(f"[worker] {tid} error: {e}", file=sys.stderr)
        with lock:
            tasks[tid]["done"] = tasks[tid]["failed"] = True


# ── HTTP API ───────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write(f"[api] {a[0] if a else ''}\n")

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # ── API ──
        if route == "/add":
            cmd = qs.get("command", [""])[0]
            if not validate(cmd):
                return self._json(403, {"error": "command rejected"})
            tid = str(int(time.time() * 1000))
            threading.Thread(target=run_task, args=(tid, cmd), daemon=True).start()
            return self._json(202, {"id": tid, "status": "running", "log": f"/temp/{tid}/download.log"})

        if route == "/remove":
            tid = qs.get("id", [""])[0]
            if not tid:
                return self._json(400, {"error": "id required"})
            # kill process if running
            with lock:
                t = tasks.pop(tid, None)
            if t and "proc" in t and t["proc"].poll() is None:
                t["proc"].kill()
            # wipe temp dir
            shutil.rmtree(os.path.join(TEMP, tid), ignore_errors=True)
            # wipe out files
            for f in list(os.listdir(OUT)):
                if f.startswith(tid):
                    os.unlink(os.path.join(OUT, f))
            return self._json(200, {"id": tid, "removed": True})

        if route == "/status":
            info = {}
            with lock:
                for tid, t in tasks.items():
                    st = "failed" if t["failed"] else ("done" if t["done"] else "running")
                    info[tid] = {"status": st, "sha": t.get("sha"), "log": f"/temp/{tid}/download.log"}
            return self._json(200, info)

        if route == "/health":
            return self._json(200, {"ok": True})

        # ── listings ──
        if route == "/temp" or route.startswith("/temp/"):
            fp = os.path.join(TEMP, route.lstrip("/temp/") or "")
            if os.path.isdir(fp):
                return self._xml(fp)
            self.send_error(404)
            return

        if route == "/out" or route.startswith("/out/"):
            fp = os.path.join(OUT, route.lstrip("/out/") or "")
            if os.path.isdir(fp):
                return self._xml(fp)
            self.send_error(404)
            return

        self.send_error(404)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _xml(self, path: str):
        body = gen_xml(path)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", "attachment; filename=listing.xml")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    startup_cleanup()
    srv = http.server.HTTPServer(("0.0.0.0", 9999), Handler)
    print("[worker] :9999", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
