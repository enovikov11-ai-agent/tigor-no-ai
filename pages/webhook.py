#!/usr/bin/env python3
import os, subprocess, hmac, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

SECRET = os.environ["WEBHOOK_SECRET"]
REPO   = os.environ["REPO_URL"]
PATH   = "/srv/repo"
LIMIT  = 120

_lock  = threading.Lock()
_syncing = False

def _bg_sync():
    global _syncing
    while True:
        try:
            if not os.path.isdir(os.path.join(PATH, ".git")):
                subprocess.run(["git", "clone", "--depth=1", REPO, PATH], timeout=LIMIT, check=True)
            else:
                subprocess.run(["git", "-C", PATH, "pull", "--ff-only"], timeout=LIMIT, check=True)
            break
        except subprocess.SubprocessError:
            pass  # retry
    with _lock:
        _syncing = False

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/pull":
            self.send_response(404); return
        self.rfile.read(self.content_length or 0)
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(token, SECRET):
            self.send_response(401); return
        self.send_response(200)
        self.wfile.write(b"ok")
        global _syncing
        with _lock:
            if not _syncing:
                _syncing = True
                threading.Thread(target=_bg_sync, daemon=True).start()
    def log_message(self, *a): pass

HTTPServer(("0.0.0.0", 8000), H).serve_forever()
