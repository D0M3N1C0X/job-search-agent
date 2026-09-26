"""The last mile: draft letter, form helper, and the daily nudge."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.apply import build_apply_page, draft_letter, _pretty
from jsa.daily import _applescript, message, summarise, write_digest
from jsa.models import Job, Score
from jsa.store import Store
from jsa.util import read_json

ROOT = Path(__file__).resolve().parent.parent
PROFILE = read_json(ROOT / "profile.example" / "profile.json")
TRACKS = read_json(ROOT / "profile.example" / "tracks.json")["tracks"]
ADVISORY = next(t for t in TRACKS if t["id"] == "hr_advisory")


def job(**kw):
    base = dict(source="test", company="Acme", title="HR Operations Specialist",
                url="https://example.com/1", location="Amsterdam, Netherlands", country="NL",
                description="Employee relations, HR policy, payroll, leave, onboarding.")
    base.update(kw)
    return Job(**base)


def score(**breakdown):
    base = {
        "skills": {"must_have": ["hr operations", "payroll"], "nice_to_have": ["gdpr"]},
        "seniority": {"detected": "mid", "years_required": 0, "years_profile": 3},
        "language": "en",
    }
    base.update(breakdown)
    return Score("x", "hr_advisory", 85, "pass", base)


class TestDraftLetter(unittest.TestCase):
    def test_it_names_the_role_and_the_matched_skills(self):
        letter = draft_letter(job(), PROFILE, ADVISORY, score())
        body = " ".join(letter["paragraphs"])
        self.assertIn("HR Operations Specialist", body)
        self.assertIn("Acme", body)
        self.assertIn("payroll", body)

    def test_acronyms_come_back_in_the_casing_a_person_uses(self):
        self.assertEqual(_pretty("hr operations"), "HR operations")
        self.assertEqual(_pretty("gdpr"), "GDPR")
        self.assertEqual(_pretty("employee lifecycle"), "employee lifecycle")
        body = " ".join(draft_letter(job(), PROFILE, ADVISORY, score())["paragraphs"])
        self.assertIn("HR operations", body)
        self.assertNotIn("hr operations", body)

    def test_a_years_gap_is_stated_rather_than_hidden(self):
        letter = draft_letter(job(), PROFILE, ADVISORY, score(
            seniority={"detected": "mid", "years_required": 8, "years_profile": 3}))
        self.assertTrue(any("8 years" in p and "3" in p for p in letter["paragraphs"]),
                        letter["paragraphs"])

    def test_a_senior_posting_says_it_is_a_step_up(self):
        letter = draft_letter(job(), PROFILE, ADVISORY, score(
            seniority={"detected": "senior", "years_required": 0, "years_profile": 3}))
        self.assertTrue(any("step up" in p for p in letter["paragraphs"]))

    def test_it_follows_the_language_of_the_posting(self):
        letter = draft_letter(job(), PROFILE, ADVISORY, score(language="it"))
        self.assertEqual(letter["language"], "it")
        self.assertTrue(letter["paragraphs"][0].startswith("Mi candido"))

    def test_relocation_keeps_its_capitals(self):
        # Lowercasing the whole clause turned "EU" into "eu".
        profile = json.loads(json.dumps(PROFILE))
        profile["identity"]["relocation"] = "Open to relocation (EU & international)"
        body = " ".join(draft_letter(job(), profile, ADVISORY, score())["paragraphs"])
        self.assertIn("(EU & international)", body)

    def test_it_marks_itself_as_a_draft(self):
        self.assertIn("DRAFT", draft_letter(job(), PROFILE, ADVISORY, score())["_draft_note"])


class TestApplyPage(unittest.TestCase):
    def page(self, answers):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            out = build_apply_page(job(), PROFILE, answers, folder, [folder / "CV.docx"])
            return out.read_text()

    def test_it_offers_a_bookmarklet_that_fills_but_never_submits(self):
        html = self.page({"notice_period": "1 month"})
        self.assertIn("javascript:", html)
        self.assertIn("Fill this form", html)
        self.assertNotIn(".submit()", html)
        self.assertNotIn("click()", html)

    def test_answers_still_marked_todo_are_kept_out_of_the_bookmarklet(self):
        import html as htmllib

        page = self.page({"notice_period": "TODO — check your contract",
                          "salary_expectation": "60000 EUR"})
        script = htmllib.unescape(page.split("javascript:")[1].split('"')[0])
        self.assertIn("60000 EUR", script)          # a real answer is carried
        self.assertNotIn("TODO", script)            # an undecided one is not

    def test_a_percent_sign_survives_the_browser_decoding_the_link(self):
        import html as htmllib
        from urllib.parse import unquote

        answer = 'PLN 12k + 10% bonus, "100%25" remote, %22'
        page = self.page({"salary_expectation": answer})
        href = htmllib.unescape(page.split('href="javascript:')[1].split('"')[0])
        script = unquote(href)                       # what the browser runs
        payload = json.loads(script.split("var d=", 1)[1].split(",n=0;", 1)[0])
        self.assertEqual(payload["salary"][1], answer)

    def test_every_answer_gets_a_copy_button(self):
        html = self.page({"a": "one", "b": "two", "c": "three"})
        self.assertEqual(html.count("data-copy="), 3)

    def test_it_says_plainly_that_nothing_is_submitted(self):
        self.assertIn("Nothing here submits anything", self.page({"a": "one"}))


class TestDaily(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "jobs.db")
        self.cfg = type("Cfg", (), {"profile": PROFILE})()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def seed(self, n=2, verdict="pass", score_value=85):
        made = []
        for i in range(n):
            j = job(title=f"HR Operations Specialist {i}", url=f"https://example.com/{i}")
            self.store.upsert_job(j)
            self.store.save_score(Score(j.id, "hr_advisory", score_value, verdict, {}))
            made.append(j)
        return made

    def test_applescript_quoting_uses_double_quotes(self):
        # repr() gives single quotes, which AppleScript rejects outright.
        self.assertEqual(_applescript("hi"), '"hi"')
        self.assertIn('\\"', _applescript('say "hi"'))

    def test_nothing_new_and_nothing_overdue_says_nothing(self):
        self.assertIsNone(message(summarise(self.store, self.cfg, 75)))

    def test_new_postings_are_announced_once(self):
        self.seed(2)
        first = summarise(self.store, self.cfg, 75)
        self.assertEqual(len(first["fresh"]), 2)
        self.assertIsNotNone(message(first))
        from jsa.daily import LAST_RUN
        from jsa.util import now
        self.store.set_meta(LAST_RUN, now())
        self.assertEqual(len(summarise(self.store, self.cfg, 75)["fresh"]), 0)

    def test_something_shortlisted_and_forgotten_becomes_overdue(self):
        j = self.seed(1)[0]
        self.store.set_status(j.id, "shortlisted")
        self.store.db.execute("UPDATE applications SET last_update = ? WHERE job_id = ?",
                              ("2020-01-01T00:00:00+00:00", j.id))
        self.store.commit()
        summary = summarise(self.store, self.cfg, 75)
        self.assertEqual(len(summary["overdue"]), 1)
        self.assertIn("overdue", message(summary)[0])

    def test_the_digest_carries_a_runnable_command_per_posting(self):
        self.seed(1)
        with TemporaryDirectory() as tmp:
            text = write_digest(summarise(self.store, self.cfg, 75),
                                Path(tmp) / "digest.md").read_text()
        self.assertIn("jsa apply", text)


if __name__ == "__main__":
    unittest.main()
