"""Where things live, in a clone and in an installed package.

A clone keeps the workspace in ./profile. An installed package lives in
site-packages, which must never receive anyone's CV, database or demo, so it
keeps the workspace in ~/.jsa and copies the bundled example out before using
it. JSA_HOME and --home override both, for reading and for writing alike.
"""

import argparse
import io
import os
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa import __main__ as cli
from jsa import config, demo, install
from jsa.store import Store

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example"


class InstalledCase(unittest.TestCase):
    """The module constants an installed package would compute, pointed at a
    temporary home. The example itself is the real one, as the wheel ships it."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.user_home = root / "home" / ".jsa"
        self.scratch = root / "cache" / "job-search-agent"
        self.patches = [
            mock.patch.object(config, "CHECKOUT", False),
            mock.patch.object(config, "DEFAULT_HOME", self.user_home),
            mock.patch.object(config, "SCRATCH_DIR", self.scratch),
            mock.patch.object(config, "EXAMPLE_DIR", EXAMPLE),
            mock.patch.dict(os.environ, {}, clear=False),
        ]
        for patch in self.patches:
            patch.start()
        os.environ.pop("JSA_HOME", None)

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self._tmp.cleanup()


class TestAnInstalledPackage(InstalledCase):
    def test_with_no_profile_it_runs_on_a_copy_of_the_example_outside_the_package(self):
        home, is_demo = config.resolve_home()
        self.assertTrue(is_demo)
        self.assertEqual(home, self.scratch / "example")
        self.assertTrue((home / "profile.json").exists())
        config.load()   # and it loads

    def test_a_profile_in_the_user_home_is_used_once_it_exists(self):
        shutil.copytree(EXAMPLE, self.user_home)
        self.assertEqual(config.resolve_home(), (self.user_home, False))

    def test_jsa_home_wins_over_the_default(self):
        with mock.patch.dict(os.environ, {"JSA_HOME": str(self.scratch / "elsewhere")}):
            self.assertEqual(config.resolve_home(), ((self.scratch / "elsewhere").resolve(), False))

    def test_home_on_the_command_line_wins_over_jsa_home(self):
        with mock.patch.dict(os.environ, {"JSA_HOME": "/somewhere/else"}):
            self.assertEqual(config.workspace(self.scratch / "explicit"),
                             (self.scratch / "explicit").resolve())

    def test_the_command_is_not_given_a_second_shim(self):
        with mock.patch.object(install, "CHECKOUT", False), \
             mock.patch.object(install.shutil, "which", return_value="/venv/bin/jsa"), \
             mock.patch.object(install, "SHIM_DIRS", [self.scratch / "bin"]):
            self.assertEqual(install.build_shim(), (Path("/venv/bin/jsa"), True))
        self.assertFalse((self.scratch / "bin").exists())


class TestSetupWritesWhereEverythingElseReads(InstalledCase):
    def run_init(self, **kw):
        args = argparse.Namespace(home=None, path=None, force=False, **kw)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_init(args), 0)

    def test_init_writes_to_the_user_home(self):
        self.run_init()
        self.assertTrue((self.user_home / "profile.json").exists())
        self.assertEqual(config.resolve_home(), (self.user_home, False))

    def test_init_honours_jsa_home(self):
        # It used to write ./profile while every other command read JSA_HOME.
        target = self.scratch / "mine"
        with mock.patch.dict(os.environ, {"JSA_HOME": str(target)}):
            self.run_init()
            self.assertTrue((target.resolve() / "profile.json").exists())
            self.assertEqual(config.resolve_home()[0], target.resolve())


class TestTheDemoStartsClean(unittest.TestCase):
    def test_a_database_left_in_the_example_is_not_copied_into_the_demo(self):
        with TemporaryDirectory() as tmp:
            example = Path(tmp) / "example"
            shutil.copytree(EXAMPLE, example, ignore=shutil.ignore_patterns("*.db*", "output"))
            with Store(example / "jobs.db") as stale:
                stale.db.execute("INSERT INTO meta (key, value) VALUES ('left', 'behind')")
                stale.db.commit()
            with mock.patch.object(config, "EXAMPLE_DIR", example):
                cfg = demo.build(Path(tmp) / "demo", count=5)
            with Store(cfg.db_path) as store:
                self.assertEqual(store.get_meta("left"), "")


class TestAClone(unittest.TestCase):
    def test_a_clone_keeps_its_workspace_in_the_repository(self):
        self.assertTrue(config.CHECKOUT)
        self.assertEqual(config.DEFAULT_HOME, config.REPO_ROOT / "profile")
        self.assertEqual(config.EXAMPLE_DIR, EXAMPLE)
        self.assertEqual(config.COMMAND, "python3 -m jsa")


class TestBackgroundJobsFindTheSameWorkspace(unittest.TestCase):
    def test_launchd_is_given_jsa_home_when_the_shell_has_one(self):
        with mock.patch.dict(os.environ, {"JSA_HOME": "/data/jsa"}):
            env = install._agent_environment()
        self.assertEqual(env, {"EnvironmentVariables": {"JSA_HOME": str(Path("/data/jsa").resolve())}})

    def test_and_nothing_when_it_does_not(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JSA_HOME", None)
            self.assertEqual(install._agent_environment(), {})


if __name__ == "__main__":
    unittest.main()
