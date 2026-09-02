"""Where the workspace lives and how it is loaded.

The engine is public; the profile is not. `JSA_HOME` points at a profile
directory (default `./profile`), and if that does not exist the bundled
synthetic `profile.example` is used instead — so a fresh clone runs, with
demo data, before anyone has typed a personal detail.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .util import read_json

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class Config:
    home: Path
    profile: dict[str, Any]
    tracks: list[dict[str, Any]]
    watchlist: list[dict[str, Any]]
    demo: bool

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
    if not (home / "profile.json").exists():
        raise SystemExit(
            f"No profile found in {home}.\n"
            "Run `python3 -m jsa init` to create one from the bundled example."
        )
    watchlist_path = home / "watchlist.json"
    watchlist = read_json(watchlist_path).get("companies", []) if watchlist_path.exists() else []
    return Config(
        home=home,
        profile=read_json(home / "profile.json"),
        tracks=read_json(home / "tracks.json")["tracks"],
        watchlist=watchlist,
        demo=demo,
    )
