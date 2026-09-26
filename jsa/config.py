"""Where the workspace lives and how it is loaded.

The engine is public; the profile is not. The workspace is `--home`, else
`JSA_HOME`, else the default: `./profile` in a clone of the repository, or
`~/.jsa` when the package was installed with pip or pipx. If there is no
profile there yet, the bundled synthetic example is used instead — so a fresh
install runs, with demo data, before anyone has typed a personal detail.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any



class ConfigError(Exception):
    """A problem with the workspace that the person can fix, stated plainly.

    Raised instead of letting a JSONDecodeError or FileNotFoundError reach the
    terminal: a stack trace tells you where the code was, not what to do.
    """

    def __init__(self, problem: str, fix: str = "") -> None:
        super().__init__(problem)
        self.problem = problem
        self.fix = fix

    def render(self) -> str:
        return self.problem + (f"\n\n{self.fix}" if self.fix else "")


def _load_json(path: Path, *, what: str) -> Any:
    if not path.exists():
        raise ConfigError(
            f"{what} is missing: {path}",
            "Run `jsa setup` to build a profile by answering questions, "
            "or `jsa init` to start from the example.",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"{what} is not valid JSON: {path}\n"
            f"  line {exc.lineno}, column {exc.colno}: {exc.msg}",
            "A stray comma or a missing quote is the usual cause. Fix that line, "
            "or run `jsa setup --force` to write the file again.",
        ) from exc
    except OSError as exc:
        raise ConfigError(f"{what} could not be read: {path}\n  {exc}") from exc


REQUIRED = [
    ("identity", "who you are — name, email, phone"),
    ("preferences", "where you will work and what would rule a posting out"),
]


def validate(profile: dict[str, Any], tracks: list[dict[str, Any]], path: Path) -> list[str]:
    """Problems worth mentioning. Missing structure raises; thin content warns."""
    for key, description in REQUIRED:
        if not isinstance(profile.get(key), dict) or not profile[key]:
            raise ConfigError(
                f"profile.json has no '{key}' section ({description}): {path}",
                "Run `jsa setup` to write a complete profile.",
            )
    for name in ("name", "email"):
        if not profile["identity"].get(name):
            raise ConfigError(
                f"profile.json is missing identity.{name}: {path}",
                "Every generated CV needs it. Run `jsa setup` or add it by hand.",
            )
    if not tracks:
        raise ConfigError(
            f"tracks.json defines no tracks: {path}",
            "Without a track there is nothing to score against. Run `jsa setup`.",
        )

    warnings = []
    if not profile.get("experience"):
        warnings.append("no experience entries — generated CVs will be nearly empty")
    if not profile.get("summaries"):
        warnings.append("no summary — the CV will start straight at the skills")
    if not any(g.get("items") for g in profile.get("skill_groups", {}).values()):
        warnings.append("no skills listed — the ATS keyword check has nothing to compare")
    if not profile.get("preferences", {}).get("countries_allowed"):
        warnings.append("no target countries — nothing will be rejected on location")
    return warnings

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

# A clone keeps the example profile beside the package. An installed package
# carries it inside as jsa/example/, and lives in a site-packages directory that
# must never receive anyone's profile, database or demo.
CHECKOUT = (REPO_ROOT / "profile.example" / "profile.json").is_file()
EXAMPLE_DIR = REPO_ROOT / "profile.example" if CHECKOUT else PACKAGE_DIR / "example"
DEFAULT_HOME = REPO_ROOT / "profile" if CHECKOUT else Path.home() / ".jsa"
SCRATCH_DIR = REPO_ROOT if CHECKOUT else (
    Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "job-search-agent")
DEMO_HOME = SCRATCH_DIR / ".demo" if CHECKOUT else SCRATCH_DIR / "demo"

# How to spell the command in advice printed to the person. `python3 -m jsa`
# works in a clone without installing anything; an installed package is `jsa`,
# and its interpreter is not necessarily the `python3` on PATH.
COMMAND = "python3 -m jsa" if CHECKOUT else "jsa"

# What a workspace is made of. Anything else in the example directory — a
# jobs.db left by a run on the example, its output — is not copied onwards.
PROFILE_FILES = ("profile.json", "tracks.json", "watchlist.json", "answers.json")


@dataclass(slots=True)
class Config:
    home: Path
    profile: dict[str, Any]
    tracks: list[dict[str, Any]]
    watchlist: list[dict[str, Any]]
    demo: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def db_path(self) -> Path:
        return self.home / "jobs.db"

    @property
    def output_dir(self) -> Path:
        return self.home / "output"

    @property
    def cache_dir(self) -> Path:
        return self.home / ".cache"

    @property
    def inbox_dir(self) -> Path:
        configured = self.profile.get("search", {}).get("mailbox_path")
        return Path(configured).expanduser() if configured else self.home / "inbox"

    def track(self, track_id: str) -> dict[str, Any]:
        for track in self.tracks:
            if track["id"] == track_id:
                return track
        raise KeyError(f"unknown track: {track_id} (have: {[t['id'] for t in self.tracks]})")


def workspace(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Where the profile lives, whether or not it exists yet.

    `jsa setup`, `init` and `import` write here, and every other command reads
    from here, so the two can never disagree about which directory is yours.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("JSA_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_HOME


def example_home() -> Path:
    """Where commands run before there is a profile.

    In a clone that is profile.example/ itself; the jobs.db a run leaves there
    is git-ignored. An installed package copies the example into a cache
    directory first, because site-packages may be read-only and is no place
    for a database either way.
    """
    if CHECKOUT:
        return EXAMPLE_DIR
    target = SCRATCH_DIR / "example"
    target.mkdir(parents=True, exist_ok=True)
    # Compared rather than copied once: after an upgrade the package's example
    # may have changed, and a stale copy would score with last version's tracks.
    for name in (*PROFILE_FILES, "tracks.library.json"):
        source, copy = EXAMPLE_DIR / name, target / name
        if source.exists() and (not copy.exists() or copy.read_bytes() != source.read_bytes()):
            shutil.copy(source, copy)
    return target


def resolve_home(explicit: str | os.PathLike[str] | None = None) -> tuple[Path, bool]:
    """Return (profile directory, is_demo)."""
    home = workspace(explicit)
    if explicit or os.environ.get("JSA_HOME") or (home / "profile.json").exists():
        return home, False
    return example_home(), True


def load(explicit: str | os.PathLike[str] | None = None) -> Config:
    home, demo = resolve_home(explicit)
    profile = _load_json(home / "profile.json", what="profile.json")
    tracks_data = _load_json(home / "tracks.json", what="tracks.json")
    tracks = tracks_data.get("tracks") if isinstance(tracks_data, dict) else None
    if not isinstance(tracks, list):
        raise ConfigError(
            f"tracks.json has no 'tracks' list: {home / 'tracks.json'}",
            "It should look like {\"tracks\": [ ... ]}. Run `jsa setup` to rewrite it.",
        )

    watchlist_path = home / "watchlist.json"
    watchlist = []
    if watchlist_path.exists():
        data = _load_json(watchlist_path, what="watchlist.json")
        watchlist = data.get("companies", []) if isinstance(data, dict) else []

    return Config(
        home=home, profile=profile, tracks=tracks, watchlist=watchlist, demo=demo,
        warnings=validate(profile, tracks, home / "profile.json"),
    )
