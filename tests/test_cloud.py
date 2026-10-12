"""The online worker, against an in-memory stand-in for Supabase."""

import unittest
from pathlib import Path
from unittest import mock

from jsa.cloud import worker
from jsa.models import Job

FIXTURES = Path(__file__).resolve().parent.parent / "profile.example"

CV_TEXT = """Giulia Rossi
Customer Operations Specialist
Milano, Italy · giulia.rossi@example.com · +39 333 000 0000

PROFILE
Customer operations specialist with five years in multilingual support teams, SLA reporting
and process improvement across European markets.

EXPERIENCE
Customer Operations Specialist — Acme Srl  2021 – Present
Milano, Italy
• Led a team of six agents answering Italian and English customers.
• Cut average handling time by 18% by rewriting the knowledge base.

EDUCATION
BA Languages — Università di Milano  2019

LANGUAGES
Italian (native) · English (C1) · Spanish (B2)
"""


class FakeDB:
    def __init__(self):
        self.tables = {"cv_imports": [], "profiles": [], "scores": [], "score_requests": [],
                       "jobs": [], "countries": []}
        self.files = {}
        self.removed = []

    @staticmethod
    def _match(row, filters):
        for key, cond in filters.items():
            if key in ("order", "limit", "offset", "select"):
                continue
            op, _, value = cond.partition(".")
            if op == "eq" and str(row.get(key)).lower() != value.lower():
                return False
            if op == "is" and value == "null" and row.get(key) is not None:
                return False
        return True

    def select(self, table, query=None):
        query = query or {}
        rows = [dict(r) for r in self.tables[table] if self._match(r, query)]
        return rows[: int(query.get("limit", 10_000))]

    def upsert(self, table, rows, *, on_conflict):
        keys = on_conflict.split(",")
        for row in rows:
            for existing in self.tables[table]:
                if all(existing.get(k) == row.get(k) for k in keys):
                    existing.update(row)
                    break
            else:
                self.tables[table].append(dict(row))
        return len(rows)

    def update(self, table, filters, values):
        for row in self.tables[table]:
            if self._match(row, filters):
                row.update(values)

    def delete(self, table, filters):
        self.tables[table] = [r for r in self.tables[table] if not self._match(r, filters)]

    def download(self, bucket, path):
        return self.files[path]

    def remove(self, bucket, paths):
        self.removed.extend(paths)


def job(**kw):
    base = dict(source="greenhouse", company="Acme", title="Customer Operations Specialist with Italian",
                url="https://example.com/1", location="Lisbon, Portugal", country="PT",
                description="Support Italian customers, SLA reporting, process improvement, knowledge base.")
    base.update(kw)
    return Job(**base)


class TestImports(unittest.TestCase):
    def test_a_cv_becomes_a_profile_and_the_file_is_deleted(self):
        db = FakeDB()
        db.files["u1/cv.txt"] = CV_TEXT.encode()
        db.tables["cv_imports"].append({"id": "i1", "user_id": "u1", "path": "u1/cv.txt", "status": "pending"})
        worker.process_imports(db)
        self.assertEqual(db.tables["cv_imports"][0]["status"], "done")
        self.assertEqual(db.removed, ["u1/cv.txt"])
        profile = db.tables["profiles"][0]["profile"]
        self.assertEqual(profile["identity"]["name"], "Giulia Rossi")
        self.assertNotIn("Amsterdam", str(profile))      # nothing from the example person

    def test_an_unreadable_upload_fails_with_a_reason_and_is_still_deleted(self):
        db = FakeDB()
        db.files["u1/cv.txt"] = b"too short"
        db.tables["cv_imports"].append({"id": "i1", "user_id": "u1", "path": "u1/cv.txt", "status": "pending"})
        worker.process_imports(db)
        item = db.tables["cv_imports"][0]
        self.assertEqual(item["status"], "failed")
        self.assertIn("almost no text", item["error"])
        self.assertEqual(db.removed, ["u1/cv.txt"])
        self.assertEqual(db.tables["profiles"], [])

    def test_a_reimport_keeps_the_countries_already_chosen(self):
        db = FakeDB()
        db.tables["profiles"].append({"user_id": "u1", "profile": {}, "countries": ["PT", "ES"]})
        db.files["u1/cv.txt"] = CV_TEXT.encode()
        db.tables["cv_imports"].append({"id": "i1", "user_id": "u1", "path": "u1/cv.txt", "status": "pending"})
        worker.process_imports(db)
        self.assertEqual(db.tables["profiles"][0]["countries"], ["PT", "ES"])


class TestScoring(unittest.TestCase):
    def member(self, **kw):
        row = {"user_id": "u1", "profile": worker.blank_profile(), "countries": ["PT"],
               "tracks": ["strategy_ops"], "onboarded": True}
        row.update(kw)
        return row

    def test_only_the_members_countries_are_scored_and_rows_are_replaced(self):
        db = FakeDB()
        db.tables["scores"].append({"user_id": "u1", "job_id": "stale", "score": 99})
        jobs = [job(), job(title="Operations Analyst", location="Berlin, Germany", country="DE")]
        with mock.patch.object(worker, "MIN_SCORE_KEPT", 0), \
                mock.patch.object(worker, "score_all", lambda j, p, t: [mock.Mock(
                    score=50, verdict="review", track="strategy_ops", breakdown={})]):
            worker.score_member(db, self.member(), jobs)
        ids = {r["job_id"] for r in db.tables["scores"]}
        self.assertEqual(ids, {jobs[0].id})               # Germany skipped, stale row gone

    def test_no_tracks_means_no_feed_rather_than_a_guess(self):
        db = FakeDB()
        self.assertEqual(worker.score_member(db, self.member(tracks=[]), [job()]), 0)

    def test_the_real_scorer_runs_on_a_blank_profile(self):
        profile, tracks = worker.engine_profile(self.member())
        result = worker.score_all(job(), profile, tracks)
        self.assertTrue(result and 0 <= result[0].score <= 100)


class TestRows(unittest.TestCase):
    def test_job_rows_flag_italian_and_shorten_the_body(self):
        row = worker.job_row(job(description="x" * 5000 + " Italian"), "2026-10-12T00:00:00+00:00")
        self.assertTrue(row["italian"])
        self.assertEqual(len(row["description"]), worker.DESCRIPTION_CHARS)
        self.assertIsNone(row["closed_at"])

    def test_the_blank_profile_carries_nobody(self):
        profile = worker.blank_profile()
        self.assertEqual(profile["experience"], [])
        self.assertEqual(profile["preferences"]["language_gates"], [])
        self.assertEqual(profile["identity"]["name"], "")


if __name__ == "__main__":
    unittest.main()
