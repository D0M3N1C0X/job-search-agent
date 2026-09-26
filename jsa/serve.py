"""A local, writable dashboard.

`jsa dashboard` exports a file you can archive or send. `jsa serve` runs the
same page against a tiny HTTP server so it can also write: change a status,
keep a note, and it lands in SQLite immediately. That keeps one source of
truth — the alternative, letting the browser remember things, produces a
second version of the truth that nobody reconciles.

Standard library only (`http.server`), bound to the loopback interface, and
requests from anywhere but this machine are refused. Writes also need the token
embedded in the page the server rendered, so a web page open in another tab
cannot reach through the browser and change anything. It is a personal tool,
not a service: do not expose it to a network.
"""

from __future__ import annotations

import hmac
import json
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from collections import deque
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .dashboard import charts_for, collect, funnel_stats
from .store import Store
from .webapp import render_page

MAX_BODY = 64 * 1024
ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}
REPO_ROOT = Path(__file__).resolve().parent.parent


class Run:
    """A pipeline run started from the dashboard.

    It is a subprocess of the same CLI rather than an in-process call: the run
    is long, it writes to the database the server is also reading, and a
    separate process keeps a crash in the pipeline from taking the dashboard
    down with it. Exactly one runs at a time.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[str] | None = None
        self.lines: deque[str] = deque(maxlen=500)
        self.returncode: int | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, home: Path, args: list[str]) -> bool:
        # --home is not optional: without it the child resolves its own
        # workspace, and a dashboard showing the demo would run against
        # ./profile and write into a database nobody is looking at.
        with self.lock:
            if self.running:
                return False
            self.lines.clear()
            self.returncode = None
            self.proc = subprocess.Popen(
                [sys.executable, "-u", "-m", "jsa", "--home", str(home), "run", *args],
                cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        threading.Thread(target=self._drain, daemon=True).start()
        return True

    def _drain(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self.lines.append(line.rstrip("\n"))
        self.returncode = proc.wait()

    def state(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "returncode": self.returncode,
            "lines": list(self.lines)[-40:],
        }


RUN = Run()


class Handler(BaseHTTPRequestHandler):
    server_version = "jsa"
    sys_version = ""

    def __init__(self, *args: Any, cfg: Any, token: str, **kwargs: Any) -> None:
        self.cfg = cfg
        self.token = token
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------ plumbing

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - base class name
        return  # the CLI prints what matters; access logs are noise here

    def _local_only(self) -> bool:
        """Peer must be this machine, and the Host header must say so too.

        Checking the peer alone leaves the door open to DNS rebinding: a page
        on the open web resolves its own hostname to 127.0.0.1 and then talks
        to this server from the victim's browser. Pinning Host closes that.
        """
        if self.client_address[0] not in ALLOWED_HOSTS:
            return False
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ALLOWED_HOSTS or host == ""

    def _may_write(self) -> bool:
        """Only the page this server rendered may change anything.

        The loopback and Host checks do not stop cross-site request forgery:
        any page in another tab can POST to 127.0.0.1, the browser sends
        `Host: 127.0.0.1`, and a text/plain body needs no preflight. The token
        exists only inside the served page, which another origin cannot read,
        and a custom header cannot be sent cross-origin without a preflight
        this server never approves. Origin, when the browser sends one, must
        be this machine as well.
        """
        sent = self.headers.get("X-JSA-Token") or ""
        if not hmac.compare_digest(sent.encode(), self.token.encode()):
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return (urllib.parse.urlsplit(origin).hostname or "") in ALLOWED_HOSTS

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # The page only ever talks to itself; forbid it being framed elsewhere.
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: Any) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _store(self) -> Store:
        return Store(self.cfg.db_path)

    # ----------------------------------------------------------------- GET

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._local_only():
            self._json(403, {"error": "local requests only"})
            return
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/":
            with self._store() as store:
                data = collect(store, interactive=True)
                data["token"] = self.token
                page = render_page(data, charts_for(funnel_stats(store)))
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/data":
            with self._store() as store:
                self._json(200, collect(store, interactive=True))
        elif path == "/api/run":
            self._json(200, RUN.state())
        else:
            self._json(404, {"error": "not found"})

    # ---------------------------------------------------------------- POST

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._local_only():
            self._json(403, {"error": "local requests only"})
            return
        if not self._may_write():
            self._json(403, {"error": "write refused: reload the dashboard and try again"})
            return
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/run":
            if RUN.start(self.cfg.home, ["--source", "ats"]):
                self._json(202, RUN.state())
            else:
                self._json(409, {"error": "a run is already in progress"})
            return
        if not path.startswith("/api/job/"):
            self._json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            self._json(400, {"error": "bad Content-Length"})
            return
        if length > MAX_BODY:
            self._json(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(400, {"error": f"invalid JSON: {exc}"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "expected a JSON object"})
            return

        job_id = path.rsplit("/", 1)[-1]
        with self._store() as store:
            job = store.get_job(job_id)
            if job is None:
                self._json(404, {"error": f"no job {job_id}"})
                return
            try:
                self._json(200, apply_update(store, job.id, payload))
            except ValueError as exc:
                # A rejected value is the caller's mistake, not a server fault:
                # answer it rather than tearing down the connection.
                self._json(400, {"error": str(exc)})


def apply_update(store: Store, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a status and/or note change; return the fields the page re-renders.

    Kept out of the handler so it can be tested without a socket.
    """
    from .models import STATUSES

    status = payload.get("status")
    notes = payload.get("notes")

    if isinstance(notes, str):
        store.set_notes(job_id, notes.strip())
    if status:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        store.set_status(job_id, status)

    application = store.application(job_id) or {}
    return {"status": application.get("status") or "", "notes": application.get("notes") or ""}


def serve(cfg: Any, *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    # A fresh token per server: a page left open from an earlier session has
    # to be reloaded before it can write, which is the behaviour you want.
    handler = partial(Handler, cfg=cfg, token=secrets.token_urlsafe(32))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        url = f"http://{host}:{port}/"
        print(f"Dashboard on {url}")
        print("Statuses and notes you change here are written to the database.")
        print("Ctrl-C to stop.")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
