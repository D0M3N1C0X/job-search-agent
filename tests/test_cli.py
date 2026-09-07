"""Command-layer tests.

The two bugs a full run exposed both lived here rather than in the library:
an argument collision when `fetch` called into a source, and a sort that
compared dictionaries whenever two applications shared an age. Neither was
reachable from the unit tests, so the commands get exercised directly.
"""

import argparse
import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa import __main__ as cli
from jsa import config
from jsa.models import Job
from jsa.score import score_all
from jsa.store import Store

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example"


class CliCase(unittest.TestCase):
    """A throwaway workspace built from the bundled demo profile."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name) / "profile"
        shutil.copytree(EXAMPLE, self.home)
        self.cfg = config.load(self.home)
        self.store = Store(self.cfg.db_path)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def ns(self, **kw):
        return argparse.Namespace(home=str(self.home), **kw)

    def run_cmd(self, fn, **kw) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fn(self.ns(**kw))
        self.assertEqual(code, 0)
        return buf.getvalue()

    def seed(self, n=2, **kw):
        made = []
        for i in range(n):
            job = Job(source="test", company=f"Company {i}", title=f"HR Advisor {i}",
                      url=f"https://example.com/{i}", location="Amsterdam, Netherlands",
                      country="NL", description="Employee relations, HR policy, payroll, leave.")
            self.store.upsert_job(job)
            for score in score_all(job, self.cfg.profile, self.cfg.tracks):
                self.store.save_score(score)
            made.append(job)
        return made


class TestDue(CliCase):
    def test_two_applications_of_the_same_age_do_not_break_the_sort(self):
        for job in self.seed(2):
            self.store.set_status(job.id, "drafted", track="hr_advisory")
        out = self.run_cmd(cli.cmd_due)
        self.assertIn("Company 0", out)
        self.assertIn("Company 1", out)

    def test_open_applications_are_listed_even_when_nothing_is_overdue(self):
        job = self.seed(1)[0]
        self.store.set_status(job.id, "shortlisted")
        out = self.run_cmd(cli.cmd_due)
        self.assertIn("nothing overdue", out)

    def test_an_empty_tracker_says_so(self):
        self.assertIn("Nothing in the tracker", self.run_cmd(cli.cmd_due))


class TestListing(CliCase):
    def test_top_lists_scored_jobs(self):
        self.seed(2)
        out = self.run_cmd(cli.cmd_top, min_score=0, track=None, limit=10,
                           new_only=False, include_closed=False, include_rejected=False)
        self.assertIn("HR Advisor 0", out)

    def test_top_hides_rejected_unless_asked(self):
        job = Job(source="test", company="Faraway Ltd", title="Warehouse Driver",
                  url="https://example.com/x", location="Tokyo, Japan", country="JP",
                  description="Drive a van.")
        self.store.upsert_job(job)
        for score in score_all(job, self.cfg.profile, self.cfg.tracks):
            self.store.save_score(score)
        hidden = self.run_cmd(cli.cmd_top, min_score=0, track=None, limit=10,
                              new_only=False, include_closed=False, include_rejected=False)
        shown = self.run_cmd(cli.cmd_top, min_score=0, track=None, limit=10,
                             new_only=False, include_closed=False, include_rejected=True)
        self.assertNotIn("Faraway", hidden)
        self.assertIn("Faraway", shown)

    def test_stats_reports_the_pipeline(self):
        self.seed(1)
        self.assertIn("jobs", self.run_cmd(cli.cmd_stats))

    def test_show_prints_a_breakdown_for_every_track(self):
        job = self.seed(1)[0]
        out = self.run_cmd(cli.cmd_show, job_id=job.id[:8], description=0)
        for track in (t["id"] for t in self.cfg.tracks):
            self.assertIn(track, out)


class TestScoringCommand(CliCase):
    def test_score_only_touches_unscored_jobs(self):
        self.seed(1)
        self.assertIn("Scored 0", self.run_cmd(cli.cmd_score, rescore=False))

    def test_rescore_covers_everything(self):
        self.seed(2)
        self.assertIn("Scored 2", self.run_cmd(cli.cmd_score, rescore=True))


if __name__ == "__main__":
    unittest.main()


class TestShim(unittest.TestCase):
    """`python3 -m jsa` only works inside the repository, which is the whole
    reason `jsa install` writes a command onto PATH."""

    def test_shim_runs_the_module_with_the_repo_importable(self):
        from jsa.install import SHIM

        script = SHIM.format(repo="/somewhere/job-search-agent", python="/usr/bin/python3")
        self.assertIn('PYTHONPATH="/somewhere/job-search-agent', script)
        self.assertIn('exec "/usr/bin/python3" -m jsa "$@"', script)
        self.assertTrue(script.startswith("#!/bin/bash"))

    def test_it_prefers_the_first_writable_directory(self):
        from jsa import install as inst

        with TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a", Path(tmp) / "b"
            second.mkdir(parents=True)
            original = inst.SHIM_DIRS
            try:
                inst.SHIM_DIRS = [first, second]      # `first` does not exist
                self.assertEqual(inst.shim_path(), second / "jsa")
                first.mkdir()
                self.assertEqual(inst.shim_path(), first / "jsa")
            finally:
                inst.SHIM_DIRS = original

    def test_an_existing_command_is_reused_rather_than_duplicated(self):
        from jsa import install as inst

        with TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a", Path(tmp) / "b"
            first.mkdir(); second.mkdir()
            (second / "jsa").write_text("#!/bin/bash\n")
            original = inst.SHIM_DIRS
            try:
                inst.SHIM_DIRS = [first, second]
                self.assertEqual(inst.shim_path(), second / "jsa")
            finally:
                inst.SHIM_DIRS = original


class TestWindowsShim(unittest.TestCase):
    """The Windows path cannot be exercised on macOS, but its shape can."""

    def test_the_batch_shim_sets_pythonpath_and_forwards_arguments(self):
        from jsa.install import SHIM_WINDOWS

        script = SHIM_WINDOWS.format(repo=r"C:\Users\x\job-search-agent",
                                     python=r"C:\Python\python.exe")
        self.assertIn(r'set "PYTHONPATH=C:\Users\x\job-search-agent;%PYTHONPATH%"', script)
        self.assertIn(r'"C:\Python\python.exe" -m jsa %*', script)
        self.assertTrue(script.startswith("@echo off"))

    def test_the_windows_launcher_starts_the_server_only_if_it_is_down(self):
        from jsa.install import LAUNCHER_WINDOWS

        script = LAUNCHER_WINDOWS.format(repo="C:\\repo", python="C:\\py.exe", port=8765)
        self.assertIn("curl -s -o NUL", script)          # is it already up?
        self.assertIn("if errorlevel 1", script)         # only then start it
        self.assertIn("-m jsa serve --port 8765", script)
        self.assertIn('start "" "%URL%"', script)        # and always open the browser


class TestEveryCommandRuns(CliCase):
    """Run every read-only command for real.

    A refactor once removed the two setup lines from `cmd_export` without
    giving it the decorator that replaced them, and nothing noticed until the
    command was typed by hand. Reading the code cannot catch that; running it
    can.
    """

    READ_ONLY = [
        ("stats", {}),
        ("due", {}),
        ("top", dict(min_score=0, track=None, limit=5, new_only=False,
                     include_closed=False, include_rejected=False)),
        ("export", dict(out=None)),
        ("dashboard", dict(out=None)),
        ("score", dict(rescore=False)),
        ("reindex", {}),
        ("enrich", dict(min_score=99, limit=0)),
        ("where", dict(port=8765)),
    ]

    def test_each_one_completes_without_raising(self):
        self.seed(2)
        for name, extra in self.READ_ONLY:
            with self.subTest(command=name):
                self.run_cmd(getattr(cli, f"cmd_{name}"), **extra)

    def test_they_work_on_an_empty_workspace_too(self):
        for name, extra in self.READ_ONLY:
            with self.subTest(command=name):
                self.run_cmd(getattr(cli, f"cmd_{name}"), **extra)

    def test_every_subcommand_is_wired_to_a_callable(self):
        parser = cli.build_parser()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        names = [n for a in actions for n in a.choices]
        self.assertIn("run", names)
        self.assertGreaterEqual(len(names), 20)
        for name in names:
            with self.subTest(command=name):
                self.assertTrue(callable(actions[0].choices[name].get_default("func")),
                                f"`jsa {name}` has no function behind it")
