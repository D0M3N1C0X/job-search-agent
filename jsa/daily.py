"""The daily round: run the pipeline, then say something only if it matters.

Nothing was reminding anyone that seven roles had been sitting shortlisted for
a fortnight. A notification that arrives every morning stops being a
notification, so this speaks only when there is something new worth an
application, or something overdue — and stays silent otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from datetime import datetime, timedelta, timezone

from .store import Store
from .util import _SSL, USER_AGENT, days_between, log, now, today

LAST_RUN = "daily:last_notified"
# The round runs several times a day; a reminder about the same unsent packet
# is worth one interruption a day, not three.
OVERDUE_DAY = "daily:overdue_notified_on"
# A posting not seen by any source for this long is probably gone: preparing a
# packet for it wastes the one thing the cap protects, the person's attention.
STALE_DAYS = 3
TELEGRAM = "https://api.telegram.org/bot{token}/{method}"


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
    focus = cfg.profile.get("preferences", {}).get("prepare") or {}
    rows = [r for r in store.best_scores(min_score=threshold, limit=400, include_applied=False)
            if in_focus(r, focus)]
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


def in_focus(row: dict[str, Any], settings: dict[str, Any]) -> bool:
    """Whether a ranked posting is the kind worth a packet: a chosen track, still listed.

    Without this the cap filled up with whatever scored highest on any track —
    a RevOps role crowding out the HR adviser roles the search is actually for.
    """
    tracks = settings.get("tracks") or []
    if tracks and row.get("track") not in tracks:
        return False
    seen = row.get("last_seen")
    age = days_between(seen) if seen else None
    return age is None or age <= STALE_DAYS


def prepare_best(cfg: Any, store: Store) -> list[dict[str, Any]]:
    """Build packets for the best untouched postings, up to a weekly cap.

    Off unless the profile says otherwise (`jsa autoprepare`). The cap counts
    every packet made in the last seven days, by hand or here, because the
    point is a pace someone can actually send at — five good applications
    read and sent beat twenty prepared and ignored.
    """
    settings = cfg.profile.get("preferences", {}).get("prepare") or {}
    per_week = int(settings.get("per_week") or 0)
    if per_week <= 0:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=7)).replace(microsecond=0).isoformat()
    this_week = store.db.execute(
        "SELECT COUNT(DISTINCT job_id) FROM events WHERE kind = 'status:ready' AND at >= ?",
        (since,),
    ).fetchone()[0]
    room = per_week - this_week
    if room <= 0:
        return []

    from .apply import prepare_packet

    prepared: list[dict[str, Any]] = []
    rows = [r for r in store.best_scores(min_score=int(settings.get("min_score", 80)),
                                         include_applied=False, limit=room * 10)
            if in_focus(r, settings)]
    for row in rows:
        if len(prepared) >= room:
            break
        job = store.get_job(row["id"])
        if job is None:  # removed since the ranking was read
            continue
        try:
            prepared.append(prepare_packet(cfg, store, job))
        except Exception as exc:  # noqa: BLE001 - one bad posting must not end the daily run
            log.warning("could not prepare %s at %s: %s", job.title, job.company, exc)
    return prepared


def message(summary: dict[str, Any], prepared: Sequence[dict[str, Any]] = ()) -> tuple[str, str] | None:
    """The one line worth interrupting someone for, or nothing."""
    fresh, overdue = summary["fresh"], summary["overdue"]
    if not fresh and not overdue and not prepared:
        return None
    parts = []
    if prepared:
        first = prepared[0]
        parts.append(f"{len(prepared)} ready to send — {first['job'].title[:42]} at "
                     f"{first['job'].company} ({first['score'].score}/100)")
    if fresh:
        best = fresh[0]
        parts.append(f"{len(fresh)} new worth applying to — best: "
                     f"{best['title'][:42]} at {best['company']} ({best['score']}/100)")
    if overdue:
        age, app, why = overdue[0]
        parts.append(f"{len(overdue)} overdue — {app['company']} {why} for {age} days")
    subtitle = f"{summary['waiting']} untouched above threshold"
    return (" · ".join(parts), subtitle)


def write_digest(summary: dict[str, Any], path: Path, prepared: Sequence[dict[str, Any]] = ()) -> Path:
    lines = [f"# Daily digest — {now()[:16].replace('T', ' ')}", ""]
    if prepared:
        lines.append(f"## {len(prepared)} ready to send")
        for done in prepared:
            todo = (f" — write the {done['letter_todo']} [[WRITE]] part(s) of the letter first"
                    if done["letter_todo"] else "")
            if done.get("form_todo"):
                todo += f" — {done['form_todo']} form question(s) to write"
            lines.append(f"- **{done['score'].score}** {done['job'].title} — {done['job'].company}"
                         f"{todo}  \n  `{done['page']}`")
        lines.append("")
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
    if not summary["fresh"] and not summary["overdue"] and not prepared:
        lines.append("Nothing new and nothing overdue.")
    lines.append(f"\n{summary['waiting']} postings above threshold are still untouched.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def quiet_repeats(summary: dict[str, Any], store: Store) -> dict[str, Any]:
    """The same summary, minus overdue reminders already given today."""
    if not summary["overdue"]:
        return summary
    if store.get_meta(OVERDUE_DAY) == today():
        return {**summary, "overdue": []}
    store.set_meta(OVERDUE_DAY, today())
    return summary


# ------------------------------------------------------------------- phone

def phone_settings(home: Path) -> dict[str, str] | None:
    """Telegram token and chat, from `notify.json` in the private workspace."""
    path = home / "notify.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")).get("telegram") or {}
    except (OSError, ValueError):
        return None
    token, chat = str(data.get("token", "")), str(data.get("chat_id", ""))
    return {"token": token, "chat_id": chat} if token and chat else None


def telegram(token: str, method: str, payload: dict[str, Any] | None = None, *,
             opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]:
    """One Bot API call. The token travels in the URL path, as Telegram requires,
    and is never logged."""
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(  # noqa: S310 - a fixed https://api.telegram.org address
        TELEGRAM.format(token=token, method=method), data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with opener(req, timeout=20, context=_SSL) as resp:
        return json.loads(resp.read() or b"{}")


def phone_text(summary: dict[str, Any], prepared: Sequence[dict[str, Any]] = ()) -> str | None:
    """A message for the phone: what is ready, what is new, with links to the postings."""
    if not summary["fresh"] and not summary["overdue"] and not prepared:
        return None
    lines: list[str] = []
    if prepared:
        lines.append(f"✅ {len(prepared)} ready to check and send")
        for done in prepared[:5]:
            job = done["job"]
            todo = f" · {done['form_todo']} to write" if done.get("form_todo") else ""
            lines.append(f"• {done['score'].score} — {job.title} · {job.company}{todo}\n  {job.url}")
    if summary["fresh"]:
        lines.append(f"🆕 {len(summary['fresh'])} new above threshold")
        for row in summary["fresh"][:5]:
            lines.append(f"• {row['score']} — {row['title']} · {row['company']} "
                         f"({row['location'] or 'n/a'})\n  {row['url']}")
    if summary["overdue"]:
        lines.append(f"⏰ {len(summary['overdue'])} overdue")
        for age, app, why in summary["overdue"][:3]:
            lines.append(f"• {app['company']} — {why} for {age} days")
    return "\n".join(lines)[:3900]  # Telegram's limit is 4,096 characters


def send_phone(home: Path, text: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> bool:
    settings = phone_settings(home)
    if not settings:
        return False
    try:
        telegram(settings["token"], "sendMessage",
                 {"chat_id": settings["chat_id"], "text": text, "disable_web_page_preview": True},
                 opener=opener)
        return True
    except (OSError, ValueError) as exc:
        log.warning("phone notification failed: %s", type(exc).__name__)
        return False
