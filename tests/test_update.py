"""`jsa update` and install.sh, offline: archives are built in memory, nothing is downloaded."""

import io
import re
import shutil
import subprocess
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa import update
from jsa.config import REPO_ROOT
from jsa.util import FetchError


def tarball(files: dict[str, str], *, links: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            archive.addfile(info)
    return buffer.getvalue()


RELEASE = {
    "job-search-agent-main/jsa/__init__.py": '__version__ = "9.9.0"\n',
    "job-search-agent-main/jsa/score.py": "# new scorer\n",
    "job-search-agent-main/README.md": "new readme\n",
    "job-search-agent-main/profile.example/profile.json": "{}\n",
}


class Kind(unittest.TestCase):
    def test_each_way_of_having_the_tool(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(update.kind(root, checkout=False), "package")
            self.assertEqual(update.kind(root, checkout=True), "copy")      # unknown origin: left alone
            (root / update.MARKER).write_text("x")
            self.assertEqual(update.kind(root, checkout=True), "download")
            (root / ".git").mkdir()
            self.assertEqual(update.kind(root, checkout=True), "git")       # git wins over the marker


class Download(unittest.TestCase):
    def test_replaces_the_code_and_never_touches_the_profile(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jsa").mkdir()
            (root / "jsa" / "__init__.py").write_text('__version__ = "1.0.0"\n')
            (root / "jsa" / "removed_upstream.py").write_text("old\n")
            (root / "profile").mkdir()
            (root / "profile" / "profile.json").write_text('{"mine": true}')
            (root / "notes.txt").write_text("a file of yours next to the code\n")

            done = update.update_download(root, fetch=lambda url: tarball(RELEASE))

            self.assertEqual(done["after"], "9.9.0")
            self.assertEqual((root / "jsa" / "score.py").read_text(), "# new scorer\n")
            self.assertFalse((root / "jsa" / "removed_upstream.py").exists())
            self.assertEqual((root / "profile" / "profile.json").read_text(), '{"mine": true}')
            self.assertTrue((root / "notes.txt").exists())
            self.assertEqual((root / "README.md").read_text(), "new readme\n")
            self.assertTrue((root / update.MARKER).is_file())

    def test_an_archive_that_would_write_outside_its_folder_is_refused_whole(self):
        hostile = [
            tarball({"top/jsa/__init__.py": "", "top/../../escape.py": "x"}),
            tarball({"/etc/evil": "x"}),
            tarball({"top/jsa/__init__.py": ""}, links={"top/profile": "/home"}),
        ]
        for data in hostile:
            with TemporaryDirectory() as tmp, self.assertRaises(FetchError):
                update.unpack(data, Path(tmp))

    def test_an_archive_that_is_not_this_tool_is_refused(self):
        with TemporaryDirectory() as tmp, self.assertRaises(FetchError):
            update.unpack(tarball({"something-else/README.md": "hello"}), Path(tmp))

    def test_an_archive_cannot_bring_a_profile(self):
        with TemporaryDirectory() as tmp:
            root, new = Path(tmp) / "root", Path(tmp) / "new"
            (root / "profile").mkdir(parents=True)
            (root / "profile" / "profile.json").write_text("mine")
            (new / "profile").mkdir(parents=True)
            (new / "profile" / "profile.json").write_text("theirs")
            update.apply(new, root)
            self.assertEqual((root / "profile" / "profile.json").read_text(), "mine")


class Versions(unittest.TestCase):
    def test_reads_and_compares_versions(self):
        self.assertEqual(update.parse_version('"""doc"""\n__version__ = "1.12.0"\n'), "1.12.0")
        self.assertEqual(update.parse_version("nothing here"), "")
        self.assertGreater(update.as_tuple("1.12.0"), update.as_tuple("1.9.3"))
        self.assertEqual(update.latest_version(lambda url: b'__version__ = "2.0.0"'), "2.0.0")


@unittest.skipIf(shutil.which("bash") is None, "needs bash")
class InstallScript(unittest.TestCase):
    script = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")

    def function(self, name: str) -> str:
        found = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", self.script, re.M | re.S)
        assert found, name
        return found.group(0)

    def test_the_python_finder_is_the_one_the_launchers_use(self):
        shared = (REPO_ROOT / "tools" / "python.sh").read_text(encoding="utf-8")
        start = self.script.index("# --- find_python")
        block = self.script[self.script.index("\n", start) + 1:self.script.index("# --- end find_python ---")]
        self.assertEqual(block, shared)

    def test_a_dragged_path_is_cleaned(self):
        program = self.function("clean_path") + 'clean_path "$1"'
        for typed, expected in [("/Users/d/My\\ CV.pdf ", "/Users/d/My CV.pdf"),
                                ("'/Users/d/My CV.pdf'", "/Users/d/My CV.pdf"),
                                ('"/tmp/cv.docx"', "/tmp/cv.docx"),
                                ("~/cv.pdf", "/home/x/cv.pdf")]:
            out = subprocess.run(["bash", "-c", program, "clean_path", typed], capture_output=True,
                                 text=True, check=True, env={"HOME": "/home/x", "PATH": "/usr/bin:/bin"})
            self.assertEqual(out.stdout.strip(), expected, typed)

    def test_everything_runs_from_main_on_the_last_line(self):
        """A download cut off halfway defines functions and runs nothing."""
        self.assertEqual(self.script.rstrip().splitlines()[-1], 'main "$@"')
        self.assertIn("set -euo pipefail", self.script)


if __name__ == "__main__":
    unittest.main()
