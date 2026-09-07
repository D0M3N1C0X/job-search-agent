"""The setup wizard, driven by scripted answers.

The point of this test is not that the prompts appear in a particular order —
it is that whatever a person types comes out the other end as a profile the
rest of the pipeline can actually use, and that a job scores against it.
"""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa import config
from jsa.models import Job
from jsa.score import score_all
from jsa import wizard

ANSWERS = [
    # identity
    "alex@example.com", "Alex Rivera", "HR Operations", "Amsterdam, Netherlands",
    "EU Citizen", "Open to relocation (EU)", "+31 600000000", "linkedin.com/in/example", "",
    # languages: English C1, Spanish native, then stop
    "English", "5", "Spanish", "7", "",
    # experience: one role, two bullets, then stop
    "HR Operations Specialist", "Example Corp", "Amsterdam", "Jan 2024", "Present",
    "Resolved around 120 HR cases a week across three European entities.",
    "Turned recurring case patterns into process changes.", "",
    "",  # no earlier roles
    # education: one entry, then stop
    "MSc Human Resource Management", "Example University", "2023", "", "", "",
    # skills
    "Employee Relations, HR Policy, Case Management",
    "Attrition analysis, Workforce reporting",
    "Python, SQL, Excel",
    "Stakeholder management, Process improvement",
    # tracks: hr_advisory and people_analytics
    "1,2",
    # preferences: cities, "specific countries", the names, seniority=mid, gate=German
    "Amsterdam, Remote", "2", "Netherlands, Germany", "2", "1",
    "y", "y",                                                # relocate, remote
    # answers
    "EU Citizen", "Open to remote", "1 month", "60000 EUR", "October", "B",
    # summary, then years
    "HR operations specialist working across three European entities.", "4",
]


def scripted():
    """Feed the answers in order, and fail loudly when the flow asks for more.

    Returning "" forever means a required question re-asks forever and the test
    hangs instead of failing — which is exactly what happened when the wizard
    grew a question.
    """
    queue = list(ANSWERS)

    def answer(prompt=""):
        if not queue:
            raise AssertionError(f"the wizard asked more than the script covers: {prompt!r}")
        return queue.pop(0)

    return answer


class TestWizard(unittest.TestCase):
    def build(self, tmp) -> Path:
        """Run the wizard on scripted answers, with its prompts swallowed."""
        home = Path(tmp) / "profile"
        with mock.patch.object(wizard, "_input", side_effect=scripted()), \
             mock.patch.object(wizard.sys.stdin, "isatty", return_value=True), \
             redirect_stdout(io.StringIO()):
            return wizard.run(home)

    def test_writes_a_profile_the_config_loader_accepts(self):
        with TemporaryDirectory() as tmp:
            home = self.build(tmp)
            cfg = config.load(home)
        self.assertEqual(cfg.profile["identity"]["name"], "Alex Rivera")
        self.assertEqual(cfg.profile["identity"]["email"], "alex@example.com")
        self.assertEqual([t["id"] for t in cfg.tracks], ["hr_advisory", "people_analytics"])

    def test_every_file_the_pipeline_needs_is_written(self):
        with TemporaryDirectory() as tmp:
            home = self.build(tmp)
            for name in ("profile.json", "tracks.json", "answers.json", "watchlist.json"):
                self.assertTrue((home / name).exists(), name)
            for folder in ("inbox", "output"):
                self.assertTrue((home / folder).is_dir(), folder)

    def test_countries_are_turned_into_codes(self):
        with TemporaryDirectory() as tmp:
            prefs = config.load(self.build(tmp)).profile["preferences"]
        self.assertEqual(prefs["countries_allowed"], ["DE", "NL"])
        self.assertEqual(prefs["seniority_target"], ["mid"])

    def test_a_language_gate_is_generated_from_the_deal_breakers(self):
        with TemporaryDirectory() as tmp:
            gates = config.load(self.build(tmp)).profile["preferences"]["language_gates"]
        self.assertEqual([g["code"] for g in gates], ["de"])
        self.assertIn("german", gates[0]["pattern"])

    def test_the_resulting_profile_actually_scores_a_job(self):
        with TemporaryDirectory() as tmp:
            cfg = config.load(self.build(tmp))
        job = Job(source="test", company="Acme", title="HR Operations Specialist",
                  url="https://example.com/1", location="Amsterdam, Netherlands", country="NL",
                  description="Employee relations, HR policy, case management, payroll, "
                              "leave, onboarding and HRIS across our European entities.")
        best = score_all(job, cfg.profile, cfg.tracks)[0]
        self.assertEqual(best.verdict, "pass")
        self.assertEqual(best.track, "hr_advisory")

    def test_a_job_demanding_a_blocked_language_is_rejected(self):
        with TemporaryDirectory() as tmp:
            cfg = config.load(self.build(tmp))
        job = Job(source="test", company="Acme", title="HR Operations Specialist",
                  url="https://example.com/2", location="Berlin, Germany", country="DE",
                  description="Employee relations, HR policy, case management, payroll. "
                              "Fluent German is required.")
        self.assertEqual(score_all(job, cfg.profile, cfg.tracks)[0].verdict, "reject")

    def test_it_refuses_to_clobber_an_existing_profile_silently(self):
        with TemporaryDirectory() as tmp:
            home = self.build(tmp)
            with mock.patch.object(wizard, "_input", return_value="n"), \
                 mock.patch.object(wizard.sys.stdin, "isatty", return_value=True), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    wizard.run(home)


class TestTrackLibrary(unittest.TestCase):
    def test_every_track_has_what_the_scorer_reads(self):
        library = json.loads(wizard.LIBRARY.read_text())["tracks"]
        self.assertGreaterEqual(len(library), 8)
        for track in library:
            for key in ("id", "label", "titles", "must_have_any", "nice_to_have",
                        "domain", "anti", "sections", "skill_groups", "cover_angle"):
                self.assertIn(key, track, f"{track.get('id')} is missing {key}")
            for bucket in ("strong", "good", "weak"):
                self.assertTrue(track["titles"][bucket], f"{track['id']}.{bucket} is empty")

    def test_track_ids_are_unique(self):
        ids = [t["id"] for t in json.loads(wizard.LIBRARY.read_text())["tracks"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
