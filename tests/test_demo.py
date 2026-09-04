"""The demo is the first thing a visitor runs, so it is held to the same bar."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.demo import build, synthesise
from jsa.store import Store


class TestSynthesis(unittest.TestCase):
    def test_is_deterministic(self):
        first = [(j.title, j.company, j.location) for j in synthesise(40)]
        second = [(j.title, j.company, j.location) for j in synthesise(40)]
        self.assertEqual(first, second)

    def test_countries_are_resolved(self):
        jobs = {j.location: j.country for j in synthesise(90)}
        self.assertEqual(jobs.get("Tokyo, Japan"), "JP")
        self.assertEqual(jobs.get("Milan, Italy"), "IT")
        self.assertEqual(jobs.get("Remote - EU", ""), "")

    def test_no_posting_points_at_a_real_site(self):
        self.assertTrue(all(".invalid/" in j.url for j in synthesise(30)))

    def test_the_range_includes_roles_that_should_be_rejected(self):
        titles = {j.title for j in synthesise(90)}
        self.assertTrue(titles & {"Backend Engineer", "Warehouse Supervisor", "Registered Nurse"})
        self.assertTrue(titles & {"HR Operations Specialist", "People Analytics Analyst"})


class TestBuild(unittest.TestCase):
    def test_produces_a_workspace_with_a_visible_funnel(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "demo"
            cfg = build(home=home, count=60)
            store = Store(cfg.db_path)
            try:
                counts = store.counts()
                verdicts = {row["verdict"] for row in store.best_scores(min_score=0, limit=200,
                                                                       include_rejected=True)}
                statuses = {a["status"] for a in store.applications()}
            finally:
                store.close()
        self.assertEqual(counts["jobs"], 60)
        self.assertTrue({"pass", "reject"} <= verdicts, verdicts)
        self.assertTrue(counts["applications"] >= 3)
        self.assertTrue({"submitted", "interview"} & statuses, statuses)


if __name__ == "__main__":
    unittest.main()
