"""Broken workspaces must produce sentences, not stack traces."""

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.config import ConfigError, load

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example"


class ConfigCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name) / "profile"
        shutil.copytree(EXAMPLE, self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, data) -> None:
        path = self.home / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


class TestFailures(ConfigCase):
    def test_malformed_json_names_the_file_and_the_line(self):
        self.write("profile.json", '{\n  "identity": {,\n}')
        with self.assertRaises(ConfigError) as caught:
            load(self.home)
        message = caught.exception.render()
        self.assertIn("profile.json", message)
        self.assertIn("line 2", message)
        self.assertIn("jsa setup", message)

    def test_a_missing_file_says_which_one_and_what_to_run(self):
        (self.home / "tracks.json").unlink()
        with self.assertRaises(ConfigError) as caught:
            load(self.home)
        self.assertIn("tracks.json is missing", caught.exception.problem)
        self.assertIn("jsa setup", caught.exception.fix)

    def test_a_profile_without_an_identity_is_refused(self):
        self.write("profile.json", {"preferences": {"remote_ok": True}})
        with self.assertRaises(ConfigError) as caught:
            load(self.home)
        self.assertIn("identity", caught.exception.problem)

    def test_an_identity_without_an_email_is_refused(self):
        data = json.loads((self.home / "profile.json").read_text())
        data["identity"].pop("email")
        self.write("profile.json", data)
        with self.assertRaises(ConfigError) as caught:
            load(self.home)
        self.assertIn("identity.email", caught.exception.problem)

    def test_tracks_without_a_tracks_list_is_refused(self):
        self.write("tracks.json", {"whatever": []})
        with self.assertRaises(ConfigError):
            load(self.home)

    def test_an_unreadable_watchlist_is_reported_rather_than_ignored(self):
        self.write("watchlist.json", "{ nope")
        with self.assertRaises(ConfigError) as caught:
            load(self.home)
        self.assertIn("watchlist.json", caught.exception.problem)


class TestWarnings(ConfigCase):
    def test_the_bundled_example_loads_without_warnings(self):
        self.assertEqual(load(self.home).warnings, [])

    def test_a_thin_profile_warns_without_refusing(self):
        data = json.loads((self.home / "profile.json").read_text())
        data["experience"] = []
        data["skill_groups"] = {}
        self.write("profile.json", data)
        warnings = load(self.home).warnings
        self.assertTrue(any("experience" in w for w in warnings), warnings)
        self.assertTrue(any("skills" in w for w in warnings), warnings)

    def test_no_target_countries_is_worth_saying(self):
        data = json.loads((self.home / "profile.json").read_text())
        data["preferences"]["countries_allowed"] = []
        self.write("profile.json", data)
        self.assertTrue(any("countries" in w for w in load(self.home).warnings))


if __name__ == "__main__":
    unittest.main()
