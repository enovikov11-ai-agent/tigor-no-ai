#!/usr/bin/env python3
import os, subprocess, hmac, shutil, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

SECRET = os.environ["WEBHOOK_SECRET"]
REPO   = os.environ["REPO_URL"]
PATH   = "/srv/repo"
LIMIT  = 300

_lock = threading.Lock()

def _sync():
    try:
        if os.path.isdir(os.path.join(PATH, ".git")):
            subprocess.run(["git", "-C", PATH, "pull", "--ff-only"], timeout=LIMIT, check=True)
            return
    except subprocess.SubprocessError:
        shutil.rmtree(PATH, ignore_errors=True)
    subprocess.run(["git", "clone", "--depth=1", REPO, PATH], timeout=LIMIT, check=True)

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/pull":
            self.send_response(404); return
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(token, SECRET):
            self.send_response(401); return
        self.send_response(200)
        self.wfile.write(b"ok")
        if _lock.acquire(blocking=False):
            t = threading.Thread(target=lambda: (_sync(), _lock.release())[-1], daemon=True)
            t.start()

HTTPServer(("0.0.0.0", 8000), H).serve_forever()
