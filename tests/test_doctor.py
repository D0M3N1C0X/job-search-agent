"""`jsa doctor` has to work when everything else does not."""

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.doctor import FAIL, OK, WARN, render, run_checks

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example"


def states(report, name):
    return [c.state for c in report.checks if c.name == name]


class TestDoctor(unittest.TestCase):
    def test_it_still_runs_when_the_workspace_is_broken(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            home.mkdir()
            (home / "profile.json").write_text("{ not json", encoding="utf-8")
            report = run_checks(home=home, network=False)
        self.assertEqual(states(report, "Workspace"), [FAIL])
        self.assertTrue(report.failures)
        # The rest of the checks must still have run.
        self.assertTrue(states(report, "Python"))
        self.assertTrue(states(report, "Version"))

    def test_a_broken_workspace_comes_with_something_to_do(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            home.mkdir()
            report = run_checks(home=home, network=False)
        workspace = next(c for c in report.checks if c.name == "Workspace")
        self.assertTrue(workspace.fix)

    def test_a_healthy_workspace_has_no_failures(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            shutil.copytree(EXAMPLE, home)
            report = run_checks(home=home, network=False)
        self.assertEqual(report.failures, [], [c.detail for c in report.failures])
        self.assertEqual(states(report, "Tracks"), [OK])

    def test_the_network_check_can_be_skipped(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            shutil.copytree(EXAMPLE, home)
            report = run_checks(home=home, network=False)
        self.assertEqual(states(report, "Network"), [WARN])

    def test_render_marks_every_check_and_ends_with_a_verdict(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            shutil.copytree(EXAMPLE, home)
            text = render(run_checks(home=home, network=False), colour=False)
        self.assertIn("✓", text)
        self.assertTrue(text.strip().endswith("improving.") or
                        text.strip().endswith("checks out."))


if __name__ == "__main__":
    unittest.main()
