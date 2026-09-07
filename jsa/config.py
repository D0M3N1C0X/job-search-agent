"""Where the workspace lives and how it is loaded.

The engine is public; the profile is not. `JSA_HOME` points at a profile
directory (default `./profile`), and if that does not exist the bundled
synthetic `profile.example` is used instead — so a fresh clone runs, with
demo data, before anyone has typed a personal detail.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .util import read_json


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
    for field in ("name", "email"):
        if not profile["identity"].get(field):
            raise ConfigError(
                f"profile.json is missing identity.{field}: {path}",
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

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def resolve_home(explicit: str | os.PathLike[str] | None = None) -> tuple[Path, bool]:
    """Return (profile directory, is_demo)."""
    if explicit:
        return Path(explicit).expanduser().resolve(), False
    env = os.environ.get("JSA_HOME")
    if env:
        return Path(env).expanduser().resolve(), False
    local = REPO_ROOT / "profile"
    if (local / "profile.json").exists():
        return local, False
    return REPO_ROOT / "profile.example", True


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
