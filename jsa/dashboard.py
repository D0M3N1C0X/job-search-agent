"""Funnel analytics and the dashboard payload.

The numbers live here; the interface lives in `webapp.py`. Charts are inline
SVG that reference the page's CSS variables, so they follow the light/dark
theme instead of being baked to one palette.
"""

from __future__ import annotations

import html
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .models import STATUSES
from .score import SCORER_VERSION
from .store import Store
from .util import days_between, now

RESPONSE_STATUSES = {"screening", "interview", "offer", "rejected"}
FUNNEL = ["shortlisted", "drafted", "ready", "submitted", "screening", "interview", "offer"]
DESCRIPTION_CHARS = 1400


def funnel_stats(store: Store) -> dict[str, Any]:
    applications = store.applications()
    by_status = Counter(a["status"] for a in applications)

    submitted = [a for a in applications if a.get("submitted_at")]
    responded, response_days = [], []
    for app in submitted:
        events = [e for e in store.events(app["job_id"])
                  if e["kind"].startswith("status:")
                  and e["kind"].split(":", 1)[1] in RESPONSE_STATUSES]
        if events:
            responded.append(app)
            delta = days_between(app["submitted_at"], events[0]["at"])
            if delta is not None:
                response_days.append(delta)

    by_track: dict[str, dict[str, int]] = defaultdict(lambda: {"submitted": 0, "responded": 0})
    for app in submitted:
        by_track[app.get("track") or "unassigned"]["submitted"] += 1
    for app in responded:
        by_track[app.get("track") or "unassigned"]["responded"] += 1

    sources = Counter(row["source"] for row in store.db.execute("SELECT source FROM jobs").fetchall())

    # Only postings that cleared the gates: including the rejects would put
    # 97% of the mass in the 0–9 band and flatten everything worth seeing.
    score_bands: Counter[int] = Counter()
    for row in store.db.execute(
        "SELECT MAX(s.score) AS s FROM scores s WHERE s.verdict != 'reject' GROUP BY s.job_id"
    ).fetchall():
        score_bands[min(90, max(0, (row["s"] // 10) * 10))] += 1

    return {
        "by_status": dict(by_status),
        "submitted": len(submitted),
        "responded": len(responded),
        "response_rate": (len(responded) / len(submitted)) if submitted else None,
        "median_response_days": round(statistics.median(response_days)) if response_days else None,
        "by_track": {k: dict(v) for k, v in by_track.items()},
        "by_source": dict(sources),
        "score_bands": dict(sorted(score_bands.items())),
        "counts": store.counts(),
    }


# ------------------------------------------------------------------- SVG

def _bar_chart(data: dict[str, int], *, width: int = 520, bar_h: int = 24,
               colour: str = "var(--accent)", label_w: int = 140) -> str:
    if not data:
        return '<p class="empty">No data yet.</p>'
    top = max(data.values()) or 1
    height = len(data) * (bar_h + 8) + 8
    plot_w = width - label_w - 48
    rows = []
    for i, (label, value) in enumerate(data.items()):
        y = 8 + i * (bar_h + 8)
        w = max(2, int(plot_w * value / top))
        rows.append(
            f'<text x="{label_w - 10}" y="{y + bar_h * 0.7}" text-anchor="end" class="lbl">'
            f'{html.escape(str(label))}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w}" height="{bar_h}" rx="4" fill="{colour}"/>'
            f'<text x="{label_w + w + 8}" y="{y + bar_h * 0.7}" class="val">{value}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">{"".join(rows)}</svg>'


def _funnel_chart(by_status: dict[str, int], width: int = 520) -> str:
    """Cumulative funnel: each stage counts everyone who reached it or beyond."""
    order = {s: i for i, s in enumerate(STATUSES)}
    reached = {
        stage: sum(n for status, n in by_status.items()
                   if status in order and order[status] >= order[stage] and status != "withdrawn")
        for stage in FUNNEL
    }
    return _bar_chart(reached)


def _track_chart(by_track: dict[str, dict[str, int]], width: int = 520) -> str:
    if not by_track:
        return '<p class="empty">Nothing submitted yet — this fills in once you start sending.</p>'
    bar_h, label_w = 24, 140
    height = len(by_track) * (bar_h + 10) + 10
    plot_w = width - label_w - 66
    top = max((v["submitted"] for v in by_track.values()), default=1) or 1
    rows = []
    for i, (track, values) in enumerate(sorted(by_track.items())):
        y = 10 + i * (bar_h + 10)
        w_all = max(2, int(plot_w * values["submitted"] / top))
        w_rep = max(0, int(plot_w * values["responded"] / top))
        rate = f'{values["responded"] / values["submitted"]:.0%}' if values["submitted"] else "–"
        rows.append(
            f'<text x="{label_w - 10}" y="{y + bar_h * 0.7}" text-anchor="end" class="lbl">'
            f'{html.escape(track)}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w_all}" height="{bar_h}" rx="4" fill="var(--line-2)"/>'
            f'<rect x="{label_w}" y="{y}" width="{w_rep}" height="{bar_h}" rx="4" fill="var(--accent)"/>'
            f'<text x="{label_w + w_all + 8}" y="{y + bar_h * 0.7}" class="val">'
            f'{values["responded"]}/{values["submitted"]} · {rate}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">{"".join(rows)}</svg>'


# ------------------------------------------------------------- page data

def collect(store: Store, *, interactive: bool, limit: int = 4000) -> dict[str, Any]:
    """Everything the page needs, as one JSON-serialisable payload."""
    stats = funnel_stats(store)
    rows = store.best_scores(min_score=0, limit=limit, include_closed=True)
    jobs = []
    for row in rows:
        jobs.append({
            "id": row["id"],
            "company": row["company"],
            "title": row["title"],
            "location": row["location"] or "",
            "country": row["country"] or "",
            "remote": row["remote"] or "unknown",
            "url": row["url"],
            "source": row["source"],
            "first_seen": row["first_seen"],
            "posted_at": row["posted_at"] or "",
            "closed": bool(row["closed_at"]),
            "score": row["score"],
            "verdict": row["verdict"],
            "track": row["track"],
            "breakdown": row["breakdown"],
            "status": row["app_status"] or "",
            "notes": row["app_notes"] or "",
            "description": (row["description"] or "")[:DESCRIPTION_CHARS],
        })
    return {
        "generated": now(),
        "interactive": interactive,
        "scorer_version": SCORER_VERSION,
        "statuses": STATUSES,
        "counts": stats["counts"],
        "stats": {k: v for k, v in stats.items() if k != "counts"},
        "jobs": jobs,
    }


def charts_for(stats: dict[str, Any]) -> dict[str, str]:
    return {
        "funnel": _funnel_chart(stats["by_status"]),
        "tracks": _track_chart(stats["by_track"]),
        "sources": _bar_chart(dict(sorted(stats["by_source"].items(), key=lambda kv: -kv[1]))),
        "scores": _bar_chart({f"{k}–{k + 9}": v for k, v in stats["score_bands"].items()}),
    }


def build_dashboard(store: Store, cfg: Any, out_path: str | Path) -> Path:
    """Write the static, read-only export."""
    from .webapp import render_page

    data = collect(store, interactive=False)
    page = render_page(data, charts_for(funnel_stats(store)))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
