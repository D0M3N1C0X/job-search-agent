"""The daily round: run the pipeline, then say something only if it matters.

Nothing was reminding anyone that seven roles had been sitting shortlisted for
a fortnight. A notification that arrives every morning stops being a
notification, so this speaks only when there is something new worth an
application, or something overdue — and stays silent otherwise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .store import Store
from .util import days_between, now

LAST_RUN = "daily:last_notified"


def _applescript(value: str) -> str:
    """Quote a string for AppleScript.

    Python's repr() wraps in single quotes, which AppleScript rejects outright —
    every notification failed silently until this was spelled out.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def notify(title: str, message: str, subtitle: str = "") -> bool:
    """A desktop notification through whatever the platform already has.

    The message carries job titles and company names, which come from feeds
    other people write, so it only ever travels as an argument or a quoted
    literal — never through a shell.
    """
    if sys.platform == "win32":
        # Windows has no notification command that does not mean building a
        # PowerShell script out of that text. The digest file is the channel.
        return False
    try:
        if sys.platform == "darwin":
            script = (f"display notification {_applescript(message)} "
                      f"with title {_applescript(title)}"
                      + (f" subtitle {_applescript(subtitle)}" if subtitle else ""))
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)
            return True
        # "--" so a message that starts with a dash is not read as an option.
        subprocess.run(["notify-send", "--", title, message], check=True, capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def summarise(store: Store, cfg: Any, threshold: int) -> dict[str, Any]:
    """What has appeared since the last time we spoke, and what is overdue."""
    since = store.get_meta(LAST_RUN)
    rows = store.best_scores(min_score=threshold, limit=200, include_applied=False)
    fresh = [r for r in rows if not since or r["first_seen"] > since]

    prefs = cfg.profile.get("preferences", {})
    follow_up = prefs.get("follow_up_days", 10)
    overdue = []
    for app in store.applications(open_only=True):
        age = days_between(app.get("submitted_at") or app["last_update"])
        if age is None:
            continue
        if app["status"] in ("shortlisted", "drafted", "ready") and age >= 3:
            overdue.append((age, app, "not sent"))
        elif app["status"] in ("submitted", "screening", "interview") and age >= follow_up:
            overdue.append((age, app, "no reply"))

    return {
        "since": since,
        "fresh": fresh,
        "best": fresh[0] if fresh else (rows[0] if rows else None),
        "waiting": len(rows),
        "overdue": sorted(overdue, key=lambda item: -item[0]),
    }


def message(summary: dict[str, Any]) -> tuple[str, str] | None:
    """The one line worth interrupting someone for, or nothing."""
    fresh, overdue = summary["fresh"], summary["overdue"]
    if not fresh and not overdue:
        return None
    parts = []
    if fresh:
        best = fresh[0]
        parts.append(f"{len(fresh)} new worth applying to — best: "
                     f"{best['title'][:42]} at {best['company']} ({best['score']}/100)")
    if overdue:
        age, app, why = overdue[0]
        parts.append(f"{len(overdue)} overdue — {app['company']} {why} for {age} days")
    subtitle = f"{summary['waiting']} untouched above threshold"
    return (" · ".join(parts), subtitle)


def write_digest(summary: dict[str, Any], path: Path) -> Path:
    lines = [f"# Daily digest — {now()[:16].replace('T', ' ')}", ""]
    if summary["fresh"]:
        lines.append(f"## {len(summary['fresh'])} new above threshold")
        for row in summary["fresh"][:10]:
            lines.append(f"- **{row['score']}** {row['title']} — {row['company']} "
                         f"({row['location'] or 'n/a'})  \n  `jsa apply {row['id'][:8]}`")
        lines.append("")
    if summary["overdue"]:
        lines.append(f"## {len(summary['overdue'])} overdue")
        for age, app, why in summary["overdue"][:10]:
            lines.append(f"- {app['company']} — {app['title']} · {why} for {age} days")
        lines.append("")
    if not summary["fresh"] and not summary["overdue"]:
        lines.append("Nothing new and nothing overdue.")
    lines.append(f"\n{summary['waiting']} postings above threshold are still untouched.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
