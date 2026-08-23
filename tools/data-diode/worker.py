#!/usr/bin/env python3
"""Sandboxed artifact relay. Limits enforced by the host VM, not this code."""
import http.server
import json
import os
import shutil
import subprocess
import sys
import time
import threading
from urllib.parse import urlparse, parse_qs

TEMP = "/data/temp"
OUT = "/data/out"
MAX = 100_000_000
WEEK = 604800

ALLOWED = [
    "https://github.com", "https://gitlab.com",
    "https://codeload.github.com", "https://raw.githubusercontent.com",
    "https://registry.npmjs.org", "https://files.pythonhosted.org",
    "https://pypi.org", "https://cache.nixos.org",
    "https://registry-1.docker.io", "https://ghcr.io", "https://quay.io",
]


def good_url(u):
    return any(u.startswith(a) for a in ALLOWED)


def validate(cmd):
    a = cmd.split()
    if not a:
        return False

    if a[0] == "git" and a[1] == "clone":
        i = 2
        while i < len(a) and a[i].startswith("-"):
            if a[i] == "--depth":
                i += 2
            elif a[i] == "--single-branch":
                i += 1
            else:
                i += 1
        if len(a) >= i + 2 and good_url(a[i]):
            return True

    if a[0] == "npm" and a[1] in ("install", "pack") and len(a) == 3:
        return True

    if a[0] == "pip" and a[1] == "download":
        i = 2
        if i < len(a) and a[i] == "--dest" and i + 1 < len(a):
            i += 2
        return len(a) == i + 1

    if a[0] == "podman" and a[1] == "save" and len(a) == 3:
        return True

    if a[0] == "nix" and a[1] == "copy" and a[2] == "--from" and len(a) == 5:
        return True

    if a[0] == "nix-prefetch-url":
        i = 1
        while i < len(a) and a[i].startswith("-"):
            if a[i] in ("--name", "--type", "--max-size"):
                i += 2
            else:
                i += 1
        if len(a) == i + 1 and good_url(a[i]):
            return True

    if a[0] == "curl" and "-o" in a and len(a) >= 5:
        oi = a.index("-o")
        if oi + 2 <= len(a) and good_url(a[oi + 2]):
            return True

    if a[0] == "wget" and "-O" in a and len(a) >= 4:
        oi = a.index("-O")
        if oi + 2 <= len(a) and good_url(a[oi + 2]):
            return True

    return False


tasks = {}
lock = threading.Lock()


def cleanup():
    while True:
        time.sleep(3600)
        now = time.time()
        for f in os.listdir(OUT):
            p = os.path.join(OUT, f)
            if os.path.isfile(p) and now - os.path.getmtime(p) > WEEK:
                os.unlink(p)
                sys.stderr.write(f"cleanup: {f}\n")


def run_task(tid, cmd):
    td = os.path.join(TEMP, tid)
    os.makedirs(td)
    with lock:
        tasks[tid] = {"dir": td, "done": False, "sha": None}

    try:
        p = subprocess.Popen(cmd, shell=True, cwd=td, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with lock:
            tasks[tid]["proc"] = p
        with open(f"{td}/download.log", "wb") as lf:
            lf.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] {cmd}\n".encode())
            lf.flush()
            for line in p.stdout:
                lf.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] ".encode() + line)
                lf.flush()
            p.wait(timeout=600)
            lf.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] exit {p.returncode}\n".encode())
        if p.returncode != 0:
            with lock:
                tasks[tid]["done"] = True
            sys.stderr.write(f"task {tid} exit {p.returncode}\n")
            return

        op = os.path.join(OUT, f"{tid}.tar.gz")
        subprocess.run(["tar", "czf", op, "-C", TEMP, tid], check=True, timeout=120)
        h = subprocess.run(["sha256sum", op], capture_output=True, check=True).stdout.split()[0].decode()[:12]
        os.rename(op, os.path.join(OUT, f"{tid}-{h}.tag.gz"))
        with lock:
            tasks[tid]["done"] = True
            tasks[tid]["sha"] = h
        sys.stderr.write(f"task {tid} -> {h}\n")

    except subprocess.TimeoutExpired:
        with lock:
            tasks[tid]["done"] = True
        sys.stderr.write(f"task {tid} timeout\n")
    except Exception as e:
        sys.stderr.write(f"task {tid} error: {e}\n")
        with lock:
            tasks[tid]["done"] = True


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, f, *a):
        sys.stderr.write(f"[api] {a[0] if a else ''}\n")

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        q = parse_qs(u.query)

        if p == "/add":
            cmd = q.get("command", [""])[0]
            if not validate(cmd):
                return self._json(403, {"error": "rejected"})
            tid = str(int(time.time() * 1000))
            threading.Thread(target=run_task, args=(tid, cmd), daemon=True).start()
            return self._json(202, {"id": tid, "status": "running", "log": f"/temp/{tid}/download.log"})

        if p == "/remove":
            tid = q.get("id", [""])[0]
            if not tid:
                return self._json(400, {"error": "id required"})
            with lock:
                t = tasks.pop(tid, None)
            if t and "proc" in t and t["proc"].poll() is None:
                t["proc"].kill()
            shutil.rmtree(os.path.join(TEMP, tid), ignore_errors=True)
            for f in os.listdir(OUT):
                if f.startswith(tid):
                    os.unlink(os.path.join(OUT, f))
            return self._json(200, {"removed": tid})

        if p == "/status":
            info = {}
            with lock:
                for tid, t in tasks.items():
                    info[tid] = {"status": "done" if t["done"] else "running", "sha": t.get("sha")}
            return self._json(200, info)

        if p == "/health":
            return self._json(200, {"ok": True})

        self.send_error(404)

    def _json(self, c, o):
        b = json.dumps(o).encode()
        self.send_response(c)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    os.makedirs(TEMP, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    threading.Thread(target=cleanup, daemon=True).start()
    srv = http.server.HTTPServer(("0.0.0.0", 9999), H)
    srv.serve_forever()
