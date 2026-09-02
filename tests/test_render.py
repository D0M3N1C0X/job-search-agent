import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.docx import extract_text
from jsa.render import Overlay, ats_check, build_cover, build_cv, keywords

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "profile.example" / "profile.json").read_text())
TRACKS = json.loads((ROOT / "profile.example" / "tracks.json").read_text())["tracks"]
ADVISORY = next(t for t in TRACKS if t["id"] == "hr_advisory")
ANALYTICS = next(t for t in TRACKS if t["id"] == "people_analytics")


class TestOverlaySafety(unittest.TestCase):
    def test_fabricated_bullets_are_rejected(self):
        overlay = Overlay(select={"Example Corp": [
            "Led a team of 40 people across five countries.",           # not in the profile
            "Resolve around 120 HR cases per week across three European entities, "
            "covering leave, payroll and policy questions.",            # genuine
        ]})
        rejected = overlay.validate(PROFILE)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(len(overlay.select["Example Corp"]), 1)

    def test_rejected_bullets_never_reach_the_document(self):
        overlay = Overlay(select={"Example Corp": ["Invented achievement."]})
        with TemporaryDirectory() as tmp:
            path = build_cv(PROFILE, ADVISORY, overlay=overlay, path=Path(tmp) / "cv.docx")
            self.assertNotIn("Invented achievement", extract_text(path))


class TestCvRendering(unittest.TestCase):
    def render(self, track, tmp, overlay=None):
        return extract_text(build_cv(PROFILE, track, overlay=overlay, path=Path(tmp) / "cv.docx"))

    def test_track_selects_the_matching_summary(self):
        with TemporaryDirectory() as tmp:
            self.assertIn("HR advisor in a multi-country", self.render(ADVISORY, tmp))
            self.assertIn("People analytics practitioner", self.render(ANALYTICS, tmp))

    def test_track_tagged_bullets_are_filtered(self):
        with TemporaryDirectory() as tmp:
            advisory = self.render(ADVISORY, tmp)
            analytics = self.render(ANALYTICS, tmp)
        marker = "Maintain quarterly workforce reporting in SQL"
        self.assertIn(marker, analytics)
        self.assertNotIn(marker, advisory)

    def test_contact_details_are_present_as_literal_text(self):
        with TemporaryDirectory() as tmp:
            text = self.render(ADVISORY, tmp)
        self.assertIn(PROFILE["identity"]["email"], text)
        self.assertIn("+31 6 0000 0000", text)

    def test_sections_follow_the_track_order(self):
        with TemporaryDirectory() as tmp:
            text = self.render(ANALYTICS, tmp)
        self.assertLess(text.index("People analytics projects"), text.index("Professional experience"))


class TestAtsCheck(unittest.TestCase):
    def test_reports_missing_keywords_without_inserting_them(self):
        posting = ("We need SQL and Python skills. SQL dashboards, Python scripts. "
                   "Kubernetes experience required, Kubernetes at scale.")
        with TemporaryDirectory() as tmp:
            path = build_cv(PROFILE, ANALYTICS, path=Path(tmp) / "cv.docx")
            report = ats_check(path, PROFILE, posting)
            self.assertIn("kubernetes", report.missing)
            self.assertIn("sql", report.covered)
            self.assertNotIn("Kubernetes", extract_text(path))

    def test_flags_a_cv_that_is_too_long(self):
        bloated = json.loads(json.dumps(PROFILE))
        bloated["summaries"]["hr_advisory"] = "word " * 1200
        with TemporaryDirectory() as tmp:
            path = build_cv(bloated, ADVISORY, path=Path(tmp) / "cv.docx")
            report = ats_check(path, bloated, "")
        self.assertFalse(report.ok)
        self.assertTrue(any("over two pages" in p for p in report.problems))

    def test_keywords_ignores_stopwords_and_singletons(self):
        found = keywords("the team the team will build dashboards dashboards with you")
        self.assertIn("dashboards", found)
        self.assertNotIn("the", found)
        self.assertNotIn("build", found)


class TestCoverLetter(unittest.TestCase):
    def test_italian_letter_uses_italian_conventions(self):
        with TemporaryDirectory() as tmp:
            path = build_cover(PROFILE, {
                "company": "Acme SpA", "role": "HR Advisor", "language": "it",
                "date": "2026-09-02", "paragraphs": ["Primo paragrafo."],
            }, path=Path(tmp) / "cover.docx")
            text = extract_text(path)
        self.assertIn("Gentile Team di selezione", text)
        self.assertIn("Candidatura — HR Advisor", text)
        self.assertIn("Cordiali saluti", text)

    def test_unknown_language_falls_back_to_english(self):
        with TemporaryDirectory() as tmp:
            path = build_cover(PROFILE, {"company": "Acme", "role": "X", "language": "pl",
                                         "paragraphs": ["Body."]}, path=Path(tmp) / "c.docx")
            self.assertIn("Dear Hiring Team", extract_text(path))


if __name__ == "__main__":
    unittest.main()
