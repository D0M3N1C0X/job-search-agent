"""Postings are written by strangers. Nothing they contain may run.

Every test here is a hole that was open once: a posting title that broke out of
the dashboard's <script>, a `javascript:` link from an ATS feed, a web page in
another tab writing to the local server, a job title handed to PowerShell.
"""

import http.client
import json
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zlib
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from jsa import daily, serve, util
from jsa.dashboard import charts_for, collect, funnel_stats
from jsa.models import Job, Score
from jsa.store import Store
from jsa.webapp import render_page, script_json

BREAKOUT = "</script><script>alert(1)</script>"


def job(**kw):
    base = dict(source="greenhouse", company="Acme", title="HR Advisor",
                url="https://example.com/1", location="Kraków, Poland", country="PL",
                description="Employee relations.")
    base.update(kw)
    return Job(**base)


class TestThePageCannotBeBrokenOutOf(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "jobs.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def page(self, **kw):
        hostile = job(**kw)
        self.store.upsert_job(hostile)
        self.store.save_score(Score(hostile.id, "hr_advisory", 80, "pass", {}))
        return render_page(collect(self.store, interactive=False),
                           charts_for(funnel_stats(self.store)), nonce="n0nce")

    def test_a_title_cannot_close_the_data_script(self):
        page = self.page(title="Analyst " + BREAKOUT)
        self.assertNotIn(BREAKOUT, page)
        # One opening tag per script the page ships, and no more.
        self.assertEqual(page.count("<script"), 2)

    def test_the_escaped_payload_still_parses_to_the_same_title(self):
        self.assertEqual(json.loads(script_json({"t": BREAKOUT + " &  "})),
                         {"t": BREAKOUT + " &  "})

    def test_scripts_run_only_with_the_page_nonce(self):
        page = self.page()
        policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', page).group(1)
        script_src = next(d.strip() for d in policy.split(";") if d.strip().startswith("script-src"))
        self.assertEqual(script_src, "script-src 'nonce-n0nce'")   # so javascript: links are dead
        self.assertEqual(page.count('<script nonce="n0nce">'), 2)

    def test_a_javascript_link_in_the_database_never_reaches_the_page(self):
        stored = job()
        self.store.upsert_job(stored)
        # A row written before URLs were checked.
        self.store.db.execute("UPDATE jobs SET url = ? WHERE id = ?", ("javascript:alert(2)", stored.id))
        self.store.db.commit()
        self.store.save_score(Score(stored.id, "hr_advisory", 80, "pass", {}))
        self.assertEqual(collect(self.store, interactive=False)["jobs"][0]["url"], "")


class TestOnlyWebLinksSurvive(unittest.TestCase):
    def test_web_links_are_kept(self):
        for url in ("https://boards.greenhouse.io/acme/jobs/1", "HTTP://example.com/x"):
            self.assertEqual(util.safe_url(url), url)

    def test_links_that_run_or_open_something_are_dropped(self):
        for url in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,<b>",
                    "file:///etc/passwd", "/System/Applications/Calculator.app",
                    "vbscript:msgbox", "//evil.example/x", ""):
            self.assertEqual(util.safe_url(url), "", url)

    def test_a_pasted_link_without_a_scheme_becomes_https(self):
        self.assertEqual(util.safe_url("www.example.com/jobs/1"), "https://www.example.com/jobs/1")

    def test_a_job_cannot_carry_a_javascript_link(self):
        self.assertEqual(job(url="javascript:alert(1)").url, "")

    def test_the_fetcher_refuses_anything_but_http(self):
        with self.assertRaises(util.FetchError):
            util.http_get("file:///etc/passwd", retries=1)


class FakeResponse:
    def __init__(self, body, gzip=False):
        self.body, self.headers = body, {"Content-Encoding": "gzip"} if gzip else {}

    def read(self, n=-1):
        return self.body[:n] if n >= 0 else self.body


class TestResponsesAreBounded(unittest.TestCase):
    def test_an_oversized_body_is_refused(self):
        with mock.patch.object(util, "MAX_RESPONSE", 1000):
            with self.assertRaises(util.FetchError):
                util._read_capped(FakeResponse(b"x" * 2000), "https://x")

    def test_a_gzip_bomb_is_refused(self):
        packer = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        bomb = packer.compress(b"\0" * 100_000) + packer.flush()
        with mock.patch.object(util, "MAX_RESPONSE", 10_000):
            self.assertLess(len(bomb), 10_000)
            with self.assertRaises(util.FetchError):
                util._read_capped(FakeResponse(bomb, gzip=True), "https://x")

    def test_an_ordinary_gzip_body_is_read(self):
        packer = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        body = packer.compress(b'{"jobs": []}') + packer.flush()
        self.assertEqual(util._read_capped(FakeResponse(body, gzip=True), "https://x"), b'{"jobs": []}')


class TestTheLocalServerOnlyObeysItsOwnPage(unittest.TestCase):
    """A page in another tab can send a POST to 127.0.0.1 — browsers deliver
    it and the Host header says 127.0.0.1. Only the token keeps it out."""

    TOKEN = "t0ken"

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        home = Path(cls._tmp.name)
        cls.cfg = SimpleNamespace(home=home, db_path=home / "jobs.db")
        with Store(cls.cfg.db_path) as store:
            cls.job = job()
            store.upsert_job(cls.job)
            store.save_score(Score(cls.job.id, "hr_advisory", 80, "pass", {}))
        cls.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(serve.Handler, cfg=cls.cfg, token=cls.TOKEN))
        # A short poll interval: shutdown() otherwise waits half a second.
        threading.Thread(target=cls.httpd.serve_forever, kwargs={"poll_interval": 0.01},
                         daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._tmp.cleanup()

    def post(self, path, body, **headers):
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def note(self):
        with Store(self.cfg.db_path) as store:
            return (store.application(self.job.id) or {}).get("notes")

    def test_a_cross_site_write_without_the_token_is_refused(self):
        code, _ = self.post(f"/api/job/{self.job.id}", b'{"notes": "from evil.example"}',
                            **{"Content-Type": "text/plain", "Origin": "https://evil.example"})
        self.assertEqual(code, 403)
        self.assertNotEqual(self.note(), "from evil.example")

    def test_a_cross_site_page_cannot_start_a_run(self):
        with mock.patch.object(serve.RUN, "start") as start:
            code, _ = self.post("/api/run", b"", Origin="https://evil.example")
        self.assertEqual(code, 403)
        start.assert_not_called()

    def test_the_token_from_another_origin_is_still_refused(self):
        code, _ = self.post(f"/api/job/{self.job.id}", b'{"notes": "x"}',
                            **{"X-JSA-Token": self.TOKEN, "Origin": "https://evil.example"})
        self.assertEqual(code, 403)

    def test_the_dashboard_page_can_write(self):
        code, body = self.post(f"/api/job/{self.job.id}", b'{"notes": "Worth a call."}',
                               **{"X-JSA-Token": self.TOKEN, "Origin": self.base,
                                  "Content-Type": "application/json"})
        self.assertEqual((code, body["notes"]), (200, "Worth a call."))

    def test_the_served_page_carries_the_token(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as resp:
            self.assertIn(f'"token": "{self.TOKEN}"', resp.read().decode())

    def test_a_malformed_content_length_is_a_client_error(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        conn.putrequest("POST", f"/api/job/{self.job.id}")
        conn.putheader("X-JSA-Token", self.TOKEN)
        conn.putheader("Content-Length", "-5")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()

    def test_a_body_that_is_not_an_object_is_a_client_error(self):
        code, _ = self.post(f"/api/job/{self.job.id}", b"[1, 2]", **{"X-JSA-Token": self.TOKEN})
        self.assertEqual(code, 400)


class TestARunFromTheDashboardUsesTheDashboardsWorkspace(unittest.TestCase):
    def test_the_child_process_is_given_the_home_being_shown(self):
        fake = mock.Mock(stdout=[], poll=mock.Mock(return_value=0), wait=mock.Mock(return_value=0))
        run = serve.Run()
        with mock.patch.object(serve.subprocess, "Popen", return_value=fake) as popen:
            run.start(Path("/demo/home"), ["--source", "ats"])
        argv = popen.call_args.args[0]
        self.assertEqual(argv[argv.index("--home") + 1], "/demo/home")
        self.assertLess(argv.index("--home"), argv.index("run"))   # a global option


class TestNotificationsNeverReachAShell(unittest.TestCase):
    def test_windows_is_not_handed_a_job_title(self):
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.object(daily.subprocess, "run") as run:
            self.assertFalse(daily.notify("Job pipeline", "Analyst's $(Start-Process calc)"))
        run.assert_not_called()

    def test_linux_passes_the_message_as_an_argument(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.object(daily.subprocess, "run") as run:
            daily.notify("Job pipeline", "-u critical")
        self.assertEqual(run.call_args.args[0], ["notify-send", "--", "Job pipeline", "-u critical"])


if __name__ == "__main__":
    unittest.main()
