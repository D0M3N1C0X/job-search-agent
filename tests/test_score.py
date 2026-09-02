import json
import unittest
from pathlib import Path

from jsa.models import Job
from jsa.score import (
    detect_language, detect_seniority, required_years, score_all, score_job, check_gates,
)

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "profile.example" / "profile.json").read_text())
TRACKS = json.loads((ROOT / "profile.example" / "tracks.json").read_text())["tracks"]


def track(track_id):
    return next(t for t in TRACKS if t["id"] == track_id)


def job(**kw):
    base = dict(source="test", company="Acme", title="HR Advisor",
                url="https://example.com", location="Amsterdam, Netherlands")
    base.update(kw)
    return Job(**base)


class TestDetectors(unittest.TestCase):
    def test_language_detection(self):
        self.assertEqual(detect_language("We are looking for a candidate with experience in the team"), "en")
        self.assertEqual(detect_language("Siamo alla ricerca di un candidato con esperienza nel nostro team e nella nostra azienda"), "it")
        self.assertEqual(detect_language("Poszukujemy kandydata do pracy w naszej firmie oraz na stanowisko"), "pl")

    def test_seniority_detection(self):
        self.assertEqual(detect_seniority("Senior HR Advisor"), "senior")
        self.assertEqual(detect_seniority("Head of People"), "head")
        self.assertEqual(detect_seniority("HR Intern"), "intern")
        self.assertEqual(detect_seniority("HR Specialist"), "mid")

    def test_required_years(self):
        self.assertEqual(required_years("You have 5+ years of experience and 2 years in HR"), 5)
        self.assertEqual(required_years("no numbers here"), 0)
        self.assertEqual(required_years("founded 1999 years ago"), 0)


class TestGates(unittest.TestCase):
    def test_language_gate_rejects_when_below_level(self):
        posting = job(description="Fluent Dutch is required for this role.")
        gates = check_gates(posting, PROFILE)
        self.assertTrue(any(g.name == "language" for g in gates))

    def test_language_gate_passes_when_only_nice_to_have(self):
        posting = job(description="Dutch is a plus. English is our working language.")
        self.assertEqual([g.name for g in check_gates(posting, PROFILE)], [])

    def test_seniority_gate_rejects_head_of_roles(self):
        posting = job(title="Head of People Operations")
        self.assertTrue(any(g.name == "seniority" for g in check_gates(posting, PROFILE)))

    def test_country_outside_targets_is_gated(self):
        posting = job(location="Tokyo, Japan", country="JP")
        self.assertTrue(any(g.name == "location" for g in check_gates(posting, PROFILE)))


class TestScoring(unittest.TestCase):
    def test_strong_match_passes(self):
        posting = job(
            title="HR Operations Specialist",
            description=("You will handle employee relations, HR policy and case management "
                         "across our EMEA entities. Experience with payroll, leave, onboarding "
                         "and HRIS required. GDPR awareness. Stakeholder management. 2 years experience."),
        )
        score = score_job(posting, PROFILE, track("hr_advisory"))
        self.assertEqual(score.verdict, "pass")
        self.assertGreaterEqual(score.score, 70)

    def test_irrelevant_role_is_rejected(self):
        posting = job(
            title="Warehouse Driver",
            description="Deliver packages on a fixed route. Forklift licence required.",
        )
        score = score_job(posting, PROFILE, track("hr_advisory"))
        self.assertEqual(score.verdict, "reject")

    def test_gate_failure_overrides_a_high_score(self):
        posting = job(
            title="HR Operations Specialist",
            description=("Employee relations, HR policy, case management, payroll, leave, "
                         "onboarding, HRIS, GDPR. Fluent Dutch is required."),
        )
        score = score_job(posting, PROFILE, track("hr_advisory"))
        self.assertEqual(score.verdict, "reject")
        self.assertTrue(score.breakdown["gates"])

    def test_best_track_wins_for_an_analytics_role(self):
        posting = job(
            title="People Analytics Analyst",
            description=("Build dashboards in SQL and Python. Attrition and retention analysis, "
                         "engagement survey reporting, pay equity. Work with the HR team."),
        )
        best = score_all(posting, PROFILE, TRACKS)[0]
        self.assertEqual(best.track, "people_analytics")

    def test_scoring_is_deterministic(self):
        posting = job(title="HR Advisor", description="Employee relations and HR policy work.")
        first = score_job(posting, PROFILE, track("hr_advisory"))
        second = score_job(posting, PROFILE, track("hr_advisory"))
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.breakdown["title"], second.breakdown["title"])

    def test_breakdown_explains_every_dimension(self):
        posting = job(title="HR Advisor", description="Employee relations and HR policy.")
        score = score_job(posting, PROFILE, track("hr_advisory"))
        for dimension in ("title", "skills", "domain", "location", "seniority"):
            self.assertIn(dimension, score.breakdown)
            self.assertIn("points", score.breakdown[dimension])

    def test_remote_role_with_unknown_country_is_not_gated(self):
        posting = job(title="HR Advisor", location="Remote", country="", remote="remote",
                      description="Fully remote employee relations role.")
        self.assertEqual([g.name for g in check_gates(posting, PROFILE)], [])

    def test_remote_does_not_rescue_a_role_in_an_excluded_country(self):
        posting = job(title="HR Advisor", location="Remote, United States", country="US",
                      remote="remote", description="We are a remote-first company.")
        self.assertTrue(any(g.name == "location" for g in check_gates(posting, PROFILE)))


if __name__ == "__main__":
    unittest.main()
