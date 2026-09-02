import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.dashboard import build_dashboard, funnel_stats
from jsa.models import Job, Score
from jsa.store import Store


def job(**kw):
    base = dict(source="greenhouse", company="Acme", title="HR Advisor",
                url="https://example.com/1", location="Kraków, Poland", country="PL")
    base.update(kw)
    return Job(**base)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "jobs.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()


class TestJobs(StoreCase):
    def test_upsert_reports_new_then_seen(self):
        self.assertEqual(self.store.upsert_job(job()), "new")
        self.assertEqual(self.store.upsert_job(job()), "seen")
        self.assertEqual(self.store.counts()["jobs"], 1)

    def test_same_role_from_another_source_does_not_duplicate(self):
        self.store.upsert_job(job(source="greenhouse"))
        self.store.upsert_job(job(source="linkedin", title="HR Advisor (m/f/d)",
                                  url="https://linkedin.com/jobs/view/1"))
        self.assertEqual(self.store.counts()["jobs"], 1)

    def test_a_second_sighting_fills_in_a_missing_description(self):
        self.store.upsert_job(job(description=""))
        self.store.upsert_job(job(description="Now with detail."))
        self.assertEqual(self.store.get_job(job().id).description, "Now with detail.")

    def test_lookup_accepts_an_id_prefix(self):
        stored = job()
        self.store.upsert_job(stored)
        self.assertEqual(self.store.get_job(stored.id[:8]).id, stored.id)

    def test_jobs_no_longer_listed_are_marked_closed(self):
        gone, still = job(title="Old Role"), job(title="Current Role")
        self.store.upsert_job(gone)
        self.store.upsert_job(still)
        self.assertEqual(self.store.mark_closed([still], "greenhouse"), 1)
        self.assertTrue(self.store.get_job(gone.id).closed_at)
        self.assertFalse(self.store.get_job(still.id).closed_at)

    def test_closing_one_company_does_not_retire_another_on_the_same_ats(self):
        acme, globex = job(company="Acme"), job(company="Globex")
        self.store.upsert_job(acme)
        self.store.upsert_job(globex)
        self.assertEqual(self.store.mark_closed([acme], "greenhouse"), 0)
        self.assertFalse(self.store.get_job(globex.id).closed_at)

    def test_an_empty_batch_closes_nothing(self):
        stored = job()
        self.store.upsert_job(stored)
        self.assertEqual(self.store.mark_closed([], "greenhouse"), 0)
        self.assertFalse(self.store.get_job(stored.id).closed_at)

    def test_discovery_is_logged_once(self):
        stored = job()
        self.store.upsert_job(stored)
        self.store.upsert_job(stored)
        kinds = [e["kind"] for e in self.store.events(stored.id)]
        self.assertEqual(kinds.count("discovered"), 1)


class TestApplications(StoreCase):
    def setUp(self):
        super().setUp()
        self.job = job()
        self.store.upsert_job(self.job)

    def test_status_transitions_are_recorded_as_events(self):
        self.store.set_status(self.job.id, "shortlisted", track="hr_advisory")
        self.store.set_status(self.job.id, "submitted")
        self.store.set_status(self.job.id, "interview")
        kinds = [e["kind"] for e in self.store.events(self.job.id)]
        self.assertEqual(kinds, ["discovered", "status:shortlisted", "status:submitted", "status:interview"])

    def test_submitted_at_is_stamped_once(self):
        self.store.set_status(self.job.id, "submitted")
        first = self.store.application(self.job.id)["submitted_at"]
        self.store.set_status(self.job.id, "interview")
        self.assertEqual(self.store.application(self.job.id)["submitted_at"], first)

    def test_track_is_not_erased_by_a_later_update(self):
        self.store.set_status(self.job.id, "drafted", track="people_analytics")
        self.store.set_status(self.job.id, "submitted")
        self.assertEqual(self.store.application(self.job.id)["track"], "people_analytics")

    def test_open_only_excludes_closed_outcomes(self):
        other = job(title="Second Role")
        self.store.upsert_job(other)
        self.store.set_status(self.job.id, "submitted")
        self.store.set_status(other.id, "rejected")
        self.assertEqual(len(self.store.applications(open_only=True)), 1)


class TestScoresAndStats(StoreCase):
    def test_best_scores_returns_the_winning_track_only(self):
        stored = job()
        self.store.upsert_job(stored)
        self.store.save_score(Score(stored.id, "hr_advisory", 82, "pass", {}))
        self.store.save_score(Score(stored.id, "people_analytics", 51, "review", {}))
        rows = self.store.best_scores(min_score=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["track"], "hr_advisory")

    def test_rescoring_replaces_rather_than_duplicates(self):
        stored = job()
        self.store.upsert_job(stored)
        self.store.save_score(Score(stored.id, "hr_advisory", 60, "review", {}))
        self.store.save_score(Score(stored.id, "hr_advisory", 88, "pass", {}))
        self.assertEqual(self.store.best_scores(min_score=0)[0]["score"], 88)

    def test_funnel_counts_a_reply_and_a_silence(self):
        replied, silent = job(title="Replied Role"), job(title="Silent Role")
        for j in (replied, silent):
            self.store.upsert_job(j)
            self.store.set_status(j.id, "submitted", track="hr_advisory")
        self.store.set_status(replied.id, "interview")
        stats = funnel_stats(self.store)
        self.assertEqual(stats["submitted"], 2)
        self.assertEqual(stats["responded"], 1)
        self.assertAlmostEqual(stats["response_rate"], 0.5)
        self.assertEqual(stats["by_track"]["hr_advisory"], {"submitted": 2, "responded": 1})

    def test_dashboard_is_self_contained(self):
        stored = job()
        self.store.upsert_job(stored)
        self.store.save_score(Score(stored.id, "hr_advisory", 77, "pass", {}))
        self.store.set_status(stored.id, "submitted", track="hr_advisory")
        with TemporaryDirectory() as tmp:
            out = build_dashboard(self.store, None, Path(tmp) / "d.html")
            html = out.read_text()
        self.assertIn("<svg", html)
        self.assertIn("HR Advisor", html)
        for remote in ("http://", "src=\"//", "cdn."):
            self.assertNotIn(remote, html.replace("https://example.com/1", ""))


if __name__ == "__main__":
    unittest.main()
