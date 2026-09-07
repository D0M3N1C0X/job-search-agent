"""`jsa doctor` — say what is wrong before it is a mystery.

Everything here is read-only and safe to run at any time, including when the
workspace is broken. That is the point: the moment you most need a diagnosis is
the moment `jsa run` will not start.
"""

from __future__ import annotations

import shutil
import socket
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import MINIMUM_PYTHON, __version__
from .config import ConfigError, load, resolve_home
from .util import FetchError, http_json

# A board that has answered for years, used only to tell "no network" apart
# from "this company's board moved".
REACHABILITY_PROBE = "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs"

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    name: str
    state: str
    detail: str
    fix: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, state: str, detail: str, fix: str = "") -> None:
        self.checks.append(Check(name, state, detail, fix))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.state == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.state == WARN]


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) != 0


def run_checks(*, home: str | Path | None = None, port: int = 8765,
               network: bool = True) -> Report:
    report = Report()

    # ---- the interpreter ------------------------------------------------
    version = ".".join(str(n) for n in sys.version_info[:3])
    needed = ".".join(str(n) for n in MINIMUM_PYTHON)
    report.add(
        "Python", OK if sys.version_info >= MINIMUM_PYTHON else FAIL,
        f"{version} at {sys.executable}",
        "" if sys.version_info >= MINIMUM_PYTHON
        else f"Needs {needed} or newer. Install one with `brew install python`.",
    )

    # ---- the workspace --------------------------------------------------
    where, demo = resolve_home(home)
    try:
        cfg = load(home)
    except ConfigError as exc:
        report.add("Workspace", FAIL, exc.problem.splitlines()[0], exc.fix)
        cfg = None
    else:
        report.add(
            "Workspace", WARN if demo else OK,
            f"{where}" + (" (the bundled demo profile)" if demo else ""),
            "Run `jsa setup` to make it yours." if demo else "",
        )
        for warning in cfg.warnings:
            report.add("Profile", WARN, warning, "Run `jsa setup` to fill in the gaps.")
        report.add("Tracks", OK if cfg.tracks else FAIL,
                   ", ".join(t["id"] for t in cfg.tracks) or "none defined")

    # ---- where the jobs come from ---------------------------------------
    if cfg is not None:
        count = len(cfg.watchlist)
        report.add(
            "Watchlist", OK if count >= 5 else WARN,
            f"{count} verified compan{'y' if count == 1 else 'ies'}",
            "" if count >= 5 else
            "Add employers with `jsa probe <slug> --add` — a thin watchlist finds little.",
        )
        queries = cfg.profile.get("search", {}).get("linkedin_queries", [])
        report.add("LinkedIn queries", OK if queries else WARN,
                   f"{len(queries)} configured",
                   "" if queries else "Optional, but it is where roles the ATS boards miss come from.")

    # ---- the database ---------------------------------------------------
    if cfg is not None:
        if not cfg.db_path.exists():
            report.add("Database", WARN, "not created yet",
                       "It appears on your first `jsa run`.")
        else:
            try:
                db = sqlite3.connect(cfg.db_path)
                integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
                jobs = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                apps = db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
                db.close()
            except sqlite3.Error as exc:
                report.add("Database", FAIL, f"{cfg.db_path}: {exc}",
                           "Delete it and run `jsa run` to rebuild; applications would be lost.")
            else:
                size = cfg.db_path.stat().st_size / 1_048_576
                report.add("Database", OK if integrity == "ok" else FAIL,
                           f"{jobs} postings, {apps} applications, {size:.1f} MB "
                           f"(integrity: {integrity})")

    # ---- can we write the documents -------------------------------------
    if cfg is not None:
        try:
            cfg.output_dir.mkdir(parents=True, exist_ok=True)
            probe = cfg.output_dir / ".jsa-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            free = shutil.disk_usage(cfg.output_dir).free / 1_073_741_824
            report.add("Documents folder", OK if free > 0.2 else WARN,
                       f"{cfg.output_dir} · {free:.1f} GB free",
                       "" if free > 0.2 else "Very little disk left; document generation may fail.")
        except OSError as exc:
            report.add("Documents folder", FAIL, f"{cfg.output_dir}: {exc}",
                       "Check the folder permissions.")

    # ---- the outside world ----------------------------------------------
    if network:
        try:
            data = http_json(REACHABILITY_PROBE, retries=1, timeout=12)
            report.add("Network", OK, f"ATS boards reachable ({len(data.get('jobs', []))} "
                                      "postings on the reference board)")
        except FetchError as exc:
            report.add("Network", WARN, f"could not reach a reference board — {exc}",
                       "Offline is fine: `jsa top`, the dashboard and document generation "
                       "all work without a connection.")
    else:
        report.add("Network", WARN, "not checked (--offline)")

    # ---- how you reach it -----------------------------------------------
    from .install import APP_PATH, on_path, shim_path

    shim = shim_path()
    if shim.exists():
        report.add("jsa command", OK if on_path(shim.parent) else WARN, str(shim),
                   "" if on_path(shim.parent)
                   else f"Add {shim.parent} to your PATH, or run commands from the repository.")
    else:
        report.add("jsa command", WARN, "not installed",
                   "`python3 -m jsa install` makes `jsa` work from any directory.")

    if sys.platform == "darwin":
        report.add("Dashboard app", OK if APP_PATH.exists() else WARN,
                   str(APP_PATH) if APP_PATH.exists() else "not installed",
                   "" if APP_PATH.exists() else "`jsa install` puts it in your Dock.")

    running = not _port_free(port)
    report.add("Dashboard server", OK, f"running on port {port}" if running
               else f"not running (port {port} is free)",
               "" if running else "`jsa serve` starts it.")

    report.add("Version", OK, f"job-search-agent {__version__}")
    return report


MARKS = {OK: ("✓", "\033[32m"), WARN: ("!", "\033[33m"), FAIL: ("✗", "\033[31m")}


def render(report: Report, colour: bool = True) -> str:
    lines = []
    for check in report.checks:
        mark, code = MARKS[check.state]
        badge = f"{code}{mark}\033[0m" if colour else mark
        lines.append(f" {badge} {check.name:<18}{check.detail}")
        if check.fix:
            lines.append(f"   {'':<18}{check.fix}")
    lines.append("")
    if report.failures:
        lines.append(f"{len(report.failures)} problem(s) to fix before this will work.")
    elif report.warnings:
        lines.append(f"Working, with {len(report.warnings)} thing(s) worth improving.")
    else:
        lines.append("Everything checks out.")
    return "\n".join(lines)
