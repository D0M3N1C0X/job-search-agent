"""Bring the code up to date without touching your data.

There are three ways to have this tool, and each updates differently:

- **git**: a clone. `git pull --ff-only`, and nothing else: if you changed the
  code yourself, git refuses and says so, and nothing is merged behind your back.
- **download**: what `install.sh` (or `Install.command`) put on disk, marked by
  a `.jsa-download` file. The current code is downloaded as a tarball and copied
  over the old: `jsa/` is replaced whole, so a module that was removed upstream
  does not linger; everything else is overwritten file by file; `profile/`,
  where your CV, tracks and database live, is never written to.
- **package**: pipx or pip. Those tools own the files, so they do the update;
  this says which command to run.

Only the code changes. The workspace is a separate directory and is left alone.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .config import CHECKOUT, REPO_ROOT
from .util import USER_AGENT, FetchError, _SSL, _read_capped

REPOSITORY = "D0M3N1C0X/job-search-agent"
TARBALL = f"https://codeload.github.com/{REPOSITORY}/tar.gz/refs/heads/main"
VERSION_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/jsa/__init__.py"
MARKER = ".jsa-download"
# Directories that belong to you, not to the code: never written by an update.
YOURS = {"profile", ".git"}
# Replaced whole rather than merged, so stale modules cannot shadow new ones.
REPLACED = {"jsa"}


def kind(root: Path = REPO_ROOT, checkout: bool = CHECKOUT) -> str:
    """git, download, package, or copy (a checkout this cannot safely update)."""
    if not checkout:
        return "package"
    if (root / ".git").exists():
        return "git"
    if (root / MARKER).is_file():
        return "download"
    return "copy"


def _fetch(url: str, timeout: int = 60) -> bytes:
    if not url.startswith("https://"):
        raise FetchError(f"{url} -> only https is used for updates")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - https only
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:  # noqa: S310 - https only
            return _read_capped(resp, url)
    except OSError as exc:
        raise FetchError(f"{url} -> {exc}") from exc


def parse_version(source: str) -> str:
    found = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', source, re.M)
    return found.group(1) if found else ""


def as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def latest_version(fetch: Any = _fetch) -> str:
    return parse_version(fetch(VERSION_URL).decode("utf-8", errors="replace"))


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Regular files and directories inside one top folder; anything else is refused.

    GitHub's tarballs are `<repo>-<branch>/…`. A link, a device, an absolute
    path or a `..` would let an archive write outside the folder it is unpacked
    into, so the whole update stops rather than skipping it.
    """
    members = []
    for member in archive.getmembers():
        if member.type == tarfile.XGLTYPE or member.type == tarfile.XHDTYPE:
            continue                                     # pax headers carry no file
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise FetchError(f"the downloaded archive contains {member.name!r}, which is refused")
        members.append(member)
    return members


def unpack(data: bytes, into: Path) -> Path:
    """Unpack a tarball into `into` and return the single top folder it holds."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = _safe_members(archive)
        tops = {PurePosixPath(m.name).parts[0] for m in members}
        if len(tops) != 1:
            raise FetchError("the downloaded archive is not a single folder")
        for member in members:
            target = into.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
            if member.mode & 0o111:
                target.chmod(0o755)
    top = into / tops.pop()
    if not (top / "jsa" / "__init__.py").is_file():
        raise FetchError("the downloaded archive does not contain job-search-agent")
    return top


def apply(new: Path, root: Path) -> list[str]:
    """Copy the code in `new` over `root`. Returns the top-level entries written."""
    written = []
    for entry in sorted(new.iterdir()):
        if entry.name in YOURS:
            continue
        target = root / entry.name
        if entry.is_dir():
            if entry.name in REPLACED and target.exists():
                shutil.rmtree(target)
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)
        written.append(entry.name)
    return written


def update_download(root: Path = REPO_ROOT, fetch: Any = _fetch) -> dict[str, Any]:
    data = fetch(TARBALL)
    with tempfile.TemporaryDirectory(prefix="jsa-update-") as tmp:
        new = unpack(data, Path(tmp))
        after = parse_version((new / "jsa" / "__init__.py").read_text(encoding="utf-8"))
        written = apply(new, root)
    (root / MARKER).write_text(f"{TARBALL}\n", encoding="utf-8")
    return {"before": __version__, "after": after, "written": written}


def update_git(root: Path = REPO_ROOT) -> tuple[int, str]:
    if shutil.which("git") is None:
        return 1, "git is not installed, so this clone cannot be updated from here."
    done = subprocess.run(["git", "-C", str(root), "pull", "--ff-only"],  # noqa: S603,S607
                          capture_output=True, text=True, check=False)
    return done.returncode, (done.stdout + done.stderr).strip()


def package_hint() -> str:
    return ("This copy was installed as a package, so the tool that installed it updates it:\n"
            "  pipx upgrade job-search-agent\n"
            "or, if you used pip:\n"
            f"  python3 -m pip install --upgrade git+https://github.com/{REPOSITORY}")
