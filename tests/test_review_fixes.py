"""What a full review of the package turned up, one test per defect.

Each test fails on the code as it was before the fix, which is the only way to
know a test is protecting anything.
"""

import argparse
import csv
import io
import os
import shutil
import unittest
import zipfile
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa import __main__ as cli
from jsa import config, install, serve, util
from jsa.apply import build_apply_page
from jsa.cvimport import UnreadableCV, read_text
from jsa.docx import extract_text
from jsa.models import Job, canonical
from jsa.store import Store

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example"


class Response:
    """What urlopen hands back: a context manager with headers and read(n)."""

    def __init__(self, body: bytes, headers: dict):
        self.body, self.headers = body, _Headers(headers)

    def read(self, n=-1):
        return self.body[:n] if n >= 0 else self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Headers(dict):
    def get_content_charset(self):
        return None


def gzipped(data: bytes) -> bytes:
    packer = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    return packer.compress(data) + packer.flush()


class TestATruncatedResponseIsRetriedAndNeverCached(unittest.TestCase):
    """read(n) returns a short body where read() raised IncompleteRead, so a
    dropped connection used to come back as half a JSON document — and be
    cached, failing every run for the next fifteen minutes."""

    def test_a_body_shorter_than_its_content_length_is_refused(self):
        with self.assertRaises(util.TruncatedResponse):
            util._read_capped(Response(b'{"jo', {"Content-Length": "100"}), "https://x")

    def test_a_gzip_stream_that_stops_early_is_refused(self):
        whole = gzipped(b'{"jobs": []}' * 50)
        with self.assertRaises(util.TruncatedResponse):
            util._read_capped(Response(whole[: len(whole) // 2], {"Content-Encoding": "gzip"}), "https://x")

    def test_every_gzip_member_is_read(self):
        body = gzipped(b"first ") + gzipped(b"second")
        self.assertEqual(util._read_capped(Response(body, {"Content-Encoding": "gzip"}), "https://x"),
                         b"first second")

    def test_http_get_retries_it_and_caches_only_the_whole_body(self):
        replies = iter([Response(b'{"jo', {"Content-Length": "12"}),
                        Response(b'{"jobs": []}', {"Content-Length": "12"})])
        with TemporaryDirectory() as tmp, \
             mock.patch.object(util.urllib.request, "urlopen", lambda *a, **k: next(replies)), \
             mock.patch.object(util.time, "sleep", lambda *_: None):
            body = util.http_get("https://boards.example/jobs", cache_dir=Path(tmp), retries=2)
            cached = [p.read_text() for p in Path(tmp).iterdir()]
        self.assertEqual(body, '{"jobs": []}')
        self.assertEqual(cached, ['{"jobs": []}'])


class TestEntitiesAreDecodedOnceAndCompletely(unittest.TestCase):
    def test_accented_names_in_a_posting_are_readable(self):
        text = util.html_to_text("<p>Office in M&uuml;nchen, caf&eacute; &ndash; &#x27;hybrid&#x27;</p>")
        self.assertEqual(text, "Office in München, café – 'hybrid'")

    def test_greenhouse_escaped_html_becomes_text_keywords_can_match(self):
        content = ("&lt;p&gt;Team in M&amp;uuml;nchen &amp;amp; Krak&amp;oacute;w&lt;/p&gt;"
                   "&lt;ul&gt;&lt;li&gt;HR policy&lt;/li&gt;&lt;/ul&gt;")
        text = util.html_to_text(content)
        self.assertEqual(text, "Team in München & Kraków\n• HR policy")
        # What the scorer matches against: it used to read "m and uuml nchen".
        self.assertIn("munchen and krakow", canonical(text))

    def test_a_literal_entity_in_the_text_is_not_decoded_twice(self):
        self.assertEqual(util.html_to_text("<p>use &amp;lt;tag&amp;gt;</p>"), "use &lt;tag&gt;")

    def test_a_docx_is_not_decoded_twice(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.docx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("word/document.xml", "<w:p><w:t>write &amp;lt;tag&amp;gt; &amp; more</w:t></w:p>")
            self.assertEqual(extract_text(path), "write &lt;tag&gt; & more")


class TestADamagedDocxIsExplained(unittest.TestCase):
    def test_a_corrupt_deflate_stream_is_an_unreadable_cv_not_a_traceback(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cv.docx"
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("word/document.xml", "<w:p>" + "hello " * 400 + "</w:p>")
            with mock.patch.object(zipfile.ZipFile, "read", side_effect=zlib.error("invalid block type")):
                with self.assertRaises(UnreadableCV):
                    read_text(path)


class TestTheApplyPage(unittest.TestCase):
    PROFILE = {"identity": {"name": "Alex Rivera", "email": "a@example.com"}}

    def page(self, url):
        job = Job(source="greenhouse", company="Acme", title="HR Advisor", url=url)
        with TemporaryDirectory() as tmp:
            return build_apply_page(job, self.PROFILE, {}, Path(tmp), []).read_text()

    def test_a_posting_without_a_safe_link_gets_no_empty_button(self):
        page = self.page("javascript:alert(1)")
        self.assertNotIn('href=""', page)
        self.assertIn("No link to the posting was kept", page)

    def test_it_names_the_command_that_works_here(self):
        self.assertIn(f"{config.COMMAND} status", self.page("https://example.com/1"))


class TestTheCsvExportIsDataNotFormulas(unittest.TestCase):
    def test_formulas_and_stale_links_are_neutralised(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            shutil.copytree(EXAMPLE, home, ignore=shutil.ignore_patterns("*.db*", "output"))
            with Store(home / "jobs.db") as store:
                job = Job(source="greenhouse", company='=HYPERLINK("http://x","a")',
                          title="+HR Advisor", url="https://example.com/1")
                store.upsert_job(job)
                store.db.execute("UPDATE jobs SET url = 'javascript:alert(1)' WHERE id = ?", (job.id,))
                store.db.commit()
                store.set_status(job.id, "shortlisted")
            out = Path(tmp) / "apps.csv"
            with redirect_stdout(io.StringIO()):
                cli.cmd_export(argparse.Namespace(home=str(home), out=str(out)))
            with out.open(encoding="utf-8") as fh:
                row = next(csv.DictReader(fh))
        self.assertEqual(row["company"], '\'=HYPERLINK("http://x","a")')
        self.assertEqual(row["title"], "'+HR Advisor")
        self.assertEqual(row["url"], "")


class TestUninstallRemovesOnlyWhatInstallWrote(unittest.TestCase):
    def test_pipx_entry_point_is_left_alone(self):
        with TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            pipx_script = bin_dir / "jsa"
            pipx_script.write_text("#!/home/u/.local/pipx/venvs/job-search-agent/bin/python\n"
                                   "from jsa.__main__ import main\n")
            none = Path(tmp) / "absent"
            with mock.patch.object(install, "SHIM_DIRS", [bin_dir]), \
                 mock.patch.object(install, "AGENT_PATH", none), \
                 mock.patch.object(install, "DAILY_PATH", none), \
                 mock.patch.object(install, "APP_PATH", none):
                self.assertEqual(install.uninstall(), [])
            self.assertTrue(pipx_script.exists())

    def test_its_own_shim_is_removed(self):
        with TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            shim = bin_dir / install.SHIM_NAME
            shim.write_text(install.SHIM.format(repo="/r", python="/p"))
            none = Path(tmp) / "absent"
            with mock.patch.object(install, "SHIM_DIRS", [bin_dir]), \
                 mock.patch.object(install, "AGENT_PATH", none), \
                 mock.patch.object(install, "DAILY_PATH", none), \
                 mock.patch.object(install, "APP_PATH", none):
                install.uninstall()
            self.assertFalse(shim.exists())


class TestInitIsNotBlockedByALogFile(unittest.TestCase):
    def test_a_workspace_holding_only_serve_log_can_still_be_initialised(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "ws"
            target.mkdir()
            (target / "serve.log").write_text("started\n")
            with redirect_stdout(io.StringIO()):
                code = cli.cmd_init(argparse.Namespace(home=None, path=str(target), force=False))
            self.assertEqual(code, 0)
            self.assertTrue((target / "profile.json").exists())

    def test_an_existing_profile_still_is_protected(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "ws"
            shutil.copytree(EXAMPLE, target)
            with redirect_stdout(io.StringIO()):
                code = cli.cmd_init(argparse.Namespace(home=None, path=str(target), force=False))
            self.assertEqual(code, 1)


class TestInstallPinsTheWorkspaceItWasRunFor(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(os.environ, {}, clear=False)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("JSA_HOME", None)

    def test_home_on_the_command_line_reaches_launchd(self):
        env = install._agent_environment("/work/jsa")
        self.assertEqual(env, {"EnvironmentVariables": {"JSA_HOME": str(Path("/work/jsa").resolve())}})

    def test_and_the_windows_launcher(self):
        with TemporaryDirectory() as tmp, mock.patch.object(install.Path, "home", return_value=Path(tmp)):
            written = install.build_windows_launcher(8765, "/work/jsa")
            self.assertIn(f'set "JSA_HOME={Path("/work/jsa").resolve()}"', written.read_text())

    def test_the_default_workspace_is_not_pinned(self):
        self.assertEqual(install._agent_environment(None), {})

    def test_cmd_install_passes_home_through(self):
        with mock.patch("jsa.install.install", return_value={
                "shim": Path("/x/jsa"), "shim_on_path": True, "app": None, "platform": "linux"}) as inst:
            with redirect_stdout(io.StringIO()):
                cli.cmd_install(argparse.Namespace(home="/work/jsa", port=8765, login=False, daily=None))
        self.assertEqual(inst.call_args.kwargs["home"], "/work/jsa")


class TestTheInstalledCommandIsFoundByItsRealName(unittest.TestCase):
    def test_it_asks_path_for_jsa_so_windows_finds_jsa_exe(self):
        # On Windows a clone's shim is jsa.bat, but pip installs jsa.exe.
        with mock.patch.object(install, "WINDOWS", True), \
             mock.patch.object(install, "SHIM_NAME", "jsa.bat"), \
             mock.patch.object(install.shutil, "which", side_effect=lambda n: "/venv/Scripts/jsa.exe"
                               if n == "jsa" else None):
            self.assertEqual(install.installed_command(), (Path("/venv/Scripts/jsa.exe"), True))


class TestTheCachedExampleFollowsThePackage(unittest.TestCase):
    def test_a_changed_example_replaces_the_cached_copy(self):
        with TemporaryDirectory() as tmp:
            package_example = Path(tmp) / "package"
            shutil.copytree(EXAMPLE, package_example, ignore=shutil.ignore_patterns("*.db*", "output"))
            scratch = Path(tmp) / "cache"
            with mock.patch.object(config, "CHECKOUT", False), \
                 mock.patch.object(config, "EXAMPLE_DIR", package_example), \
                 mock.patch.object(config, "SCRATCH_DIR", scratch):
                config.example_home()
                (package_example / "tracks.json").write_text('{"tracks": []}')   # an upgrade
                cached = config.example_home() / "tracks.json"
            self.assertEqual(cached.read_text(), '{"tracks": []}')


class TestARunFromAnInstalledDashboardStaysOutOfSitePackages(unittest.TestCase):
    def test_the_child_runs_in_the_workspace(self):
        fake = mock.Mock(stdout=[], poll=mock.Mock(return_value=0), wait=mock.Mock(return_value=0))
        with mock.patch.object(serve, "CHECKOUT", False), \
             mock.patch.object(serve.subprocess, "Popen", return_value=fake) as popen:
            serve.Run().start(Path("/home/u/.jsa"), [])
        self.assertEqual(popen.call_args.kwargs["cwd"], Path("/home/u/.jsa"))


if __name__ == "__main__":
    unittest.main()
