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
