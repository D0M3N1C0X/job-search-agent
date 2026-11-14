"""The scoring benchmark and the rules it measures: language requirements, years asked, plurals."""

import json
import unittest

from jsa import config, evaluate
from jsa.models import Job
from jsa.score import _matches, detect_seniority, language_requirements, required_years
from jsa.models import canonical

LEVELS = {"en": "C1", "nl": "B1", "es": "native"}


def asks(text: str, title: str = "HR Advisor") -> list[tuple[str, str]]:
    return language_requirements(
        Job(source="t", company="c", title=title, url="https://example.invalid/1", description=text), LEVELS)


class LanguageRequirements(unittest.TestCase):
    def test_a_requirement_is_a_sentence_not_a_word(self):
        self.assertEqual(asks("Fluent Dutch and good English are required"), [("nl", "C1")])
        for text in ("Dutch is a plus", "our Dutch and German entities", "free Dutch lessons for everyone",
                     "Excellent knowledge of English and Dutch employment law", "Polish is not required",
                     "help polish our handbook", "Fluent English is required; knowledge of Dutch is not needed",
                     "Fluent German and French is a plus"):
            self.assertEqual(asks(text), [], text)

    def test_the_level_may_come_after_the_language(self):
        self.assertEqual(asks("Languages: English (fluent) and Dutch (fluent)."), [("nl", "C1")])
        self.assertEqual(asks("Dutch: native or near-native. English: good."), [("nl", "C1")])
        self.assertEqual(asks("French mother tongue, with good English."), [("fr", "C1")])
        self.assertEqual(asks("you speak and write Dutch fluently"), [("nl", "C1")])

    def test_either_of_two_is_met_by_the_one_the_profile_has(self):
        self.assertEqual(asks("Fluent German or English"), [])
        self.assertEqual(asks("Fluent in English and German"), [("de", "C1")])

    def test_asked_in_its_own_language(self):
        self.assertEqual(asks("Je beheerst de Nederlandse taal vloeiend"), [("nl", "C1")])
        self.assertEqual(asks("fließende Deutschkenntnisse"), [("de", "C1")])
        self.assertEqual(asks("Wymagana biegła znajomość języka polskiego"), [("pl", "C1")])

    def test_a_language_in_the_title(self):
        self.assertEqual(asks("", "Swedish-speaking HR Advisor"), [("sv", "C1")])
        self.assertEqual(asks("", "Customer Support (Spanish)"), [])     # the profile is native

    def test_a_language_the_profile_has_is_never_asked(self):
        self.assertEqual(asks("Native Spanish is required"), [])


class YearsAndLevel(unittest.TestCase):
    def test_only_years_asked_of_the_candidate_count(self):
        self.assertEqual(required_years("Trading for 25 years. Two years of HR advisory experience."), 2)
        self.assertEqual(required_years("In the past 3 years our headcount tripled. One to three years of "
                                        "analyst experience."), 1)
        self.assertEqual(required_years("Minimum 10 years of experience in HR"), 10)
        self.assertEqual(required_years("Four to six years of HR experience"), 4)
        self.assertEqual(required_years("mindestens 5 Jahre Berufserfahrung"), 5)
        self.assertEqual(required_years("a decade of HR experience"), 10)
        self.assertEqual(required_years("27 days of leave"), 0)

    def test_the_level_of_the_manager_is_not_the_role_s(self):
        self.assertEqual(detect_seniority("People Operations", "You will report to the Director of People"), "mid")
        self.assertEqual(detect_seniority("Head of People"), "head")


class Plurals(unittest.TestCase):
    def test_long_terms_match_their_plural_short_ones_do_not(self):
        hits = _matches(["dashboard", "hr policy", "hr"], canonical("Dashboards, HR policies, 40 hrs a week"))
        self.assertEqual(hits, ["dashboard", "hr policy"])


class Benchmark(unittest.TestCase):
    def setUp(self):
        self.postings = evaluate.load_postings(config.BENCHMARK_PATH)
        example = config.load(config.example_home())
        self.profile, self.tracks = example.profile, example.tracks

    def test_every_posting_is_labelled_completely(self):
        ids = [p["id"] for p in self.postings]
        self.assertEqual(len(ids), len(set(ids)))
        for p in self.postings:
            self.assertIn(p["set"], ("development", "held-out"), p["id"])
            self.assertIn(p["expect"]["decision"], evaluate.DECISIONS, p["id"])
            self.assertTrue(p["expect"]["why"], p["id"])
        self.assertGreaterEqual(sum(p["set"] == "held-out" for p in self.postings), 30)

    def test_the_rules_still_score_the_development_postings_as_they_did(self):
        """A floor, not a target: a change that makes the scorer worse here fails the suite."""
        dev = [p for p in self.postings if p["set"] == "development"]
        s = evaluate.summarise(evaluate.benchmark(dev, self.profile, self.tracks))
        self.assertGreaterEqual(s["right"], 88)
        self.assertEqual(s["missed"], [])                 # nothing worth applying to is rejected
        self.assertLessEqual(len(s["wasted"]), 1)
        for gate, g in s["gates"].items():
            self.assertEqual(g["wrongly"], 0, gate)       # no gate on a posting worth reading

    def test_own_decisions(self):
        apps = [{"job_id": "a", "status": "submitted"}, {"job_id": "b", "status": "withdrawn"},
                {"job_id": "c", "status": "interview"}, {"job_id": "d", "status": "shortlisted"}]
        stats = evaluate.own_decisions(apps, {"a": (80, "pass"), "b": (75, "pass"), "c": (60, "review"),
                                              "d": (90, "pass")})
        self.assertEqual((stats["pursued"], stats["dismissed"]), (2, 1))
        self.assertEqual(stats["recall"], 0.5)
        self.assertEqual(stats["false_pass"], 1.0)
        self.assertIn("hint", evaluate.report_own(stats))
        json.dumps(stats)


if __name__ == "__main__":
    unittest.main()
