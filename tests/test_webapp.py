"""The dashboard payload, the page it renders, and the write-back API."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.dashboard import charts_for, collect, funnel_stats
from jsa.models import Job, Score
from jsa.serve import apply_update
from jsa.store import Store
from jsa.webapp import render_page


def job(**kw):
    base = dict(source="greenhouse", company="Acme", title="HR Advisor",
                url="https://example.com/1", location="Kraków, Poland", country="PL",
                description="Employee relations and HR policy work across EMEA.")
    base.update(kw)
    return Job(**base)


class WebCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "jobs.db")
        self.job = job()
        self.store.upsert_job(self.job)
        self.store.save_score(Score(self.job.id, "hr_advisory", 82, "pass",
                                    {"title": {"points": 30, "max": 30, "strong": ["hr advisor"],
                                               "good": [], "weak": []}}))

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()


class TestPayload(WebCase):
    def test_collect_includes_the_fields_the_page_renders(self):
        data = collect(self.store, interactive=True)
        self.assertEqual(len(data["jobs"]), 1)
        entry = data["jobs"][0]
        for key in ("id", "company", "title", "score", "verdict", "track",
                    "breakdown", "status", "notes", "description"):
            self.assertIn(key, entry)
        self.assertTrue(data["interactive"])

    def test_notes_reach_the_payload(self):
        self.store.set_notes(self.job.id, "Ask about the Italian desk.")
        self.assertEqual(collect(self.store, interactive=False)["jobs"][0]["notes"],
                         "Ask about the Italian desk.")

    def test_payload_is_json_serialisable(self):
        json.dumps(collect(self.store, interactive=False))  # must not raise

    def test_description_is_truncated(self):
        long_job = job(title="Long Role", description="x" * 5000)
        self.store.upsert_job(long_job)
        self.store.save_score(Score(long_job.id, "hr_advisory", 70, "pass", {}))
        lengths = [len(j["description"]) for j in collect(self.store, interactive=False)["jobs"]]
        self.assertTrue(all(n <= 1400 for n in lengths), lengths)


class TestPage(WebCase):
    def page(self, interactive):
        data = collect(self.store, interactive=interactive)
        return render_page(data, charts_for(funnel_stats(self.store)))

    def test_page_is_self_contained(self):
        html = self.page(False)
        self.assertNotIn("<script src=", html)
        self.assertNotIn('<link rel="stylesheet"', html)
        self.assertNotIn("cdn.", html)

    def test_page_embeds_its_data_and_the_job(self):
        html = self.page(False)
        self.assertIn("window.__JSA__", html)
        self.assertIn("HR Advisor", html)

    def test_static_export_declares_itself_read_only(self):
        self.assertIn("static export", self.page(False))
        self.assertIn('"interactive": false', self.page(False))

    def test_served_page_declares_itself_writable(self):
        self.assertIn('"interactive": true', self.page(True))

    def test_no_function_shadows_a_browser_global(self):
        # `open` and `close` are window methods; a handler bound to the wrong
        # one fails silently in the browser.
        html = self.page(False)
        self.assertNotIn("function open(", html)
        self.assertNotIn("function close(", html)

    def test_theme_is_defined_for_light_and_dark(self):
        html = self.page(False)
        self.assertIn("prefers-color-scheme:dark", html)
        self.assertIn('[data-theme="dark"]', html)


class TestWriteBack(WebCase):
    def test_status_and_note_are_saved(self):
        result = apply_update(self.store, self.job.id,
                              {"status": "shortlisted", "notes": "Worth a call."})
        self.assertEqual(result, {"status": "shortlisted", "notes": "Worth a call."})
        self.assertEqual(self.store.application(self.job.id)["notes"], "Worth a call.")

    def test_unknown_status_is_refused(self):
        with self.assertRaises(ValueError):
            apply_update(self.store, self.job.id, {"status": "promoted"})

    def test_a_note_alone_starts_tracking_the_job(self):
        apply_update(self.store, self.job.id, {"notes": "Interesting."})
        self.assertEqual(self.store.application(self.job.id)["status"], "shortlisted")

    def test_saving_a_note_does_not_reset_the_status(self):
        self.store.set_status(self.job.id, "submitted")
        apply_update(self.store, self.job.id, {"notes": "Followed up."})
        self.assertEqual(self.store.application(self.job.id)["status"], "submitted")

    def test_changes_are_recorded_in_the_event_log(self):
        apply_update(self.store, self.job.id, {"status": "ready", "notes": "Done."})
        kinds = [e["kind"] for e in self.store.events(self.job.id)]
        self.assertIn("status:ready", kinds)


if __name__ == "__main__":
    unittest.main()
