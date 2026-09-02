"""Funnel analytics and a self-contained HTML dashboard.

The job search is itself a dataset: how many roles were seen, how many were
worth applying to, which positioning track converts, how long employers take
to reply. The dashboard is one HTML file with inline SVG — no CDN, no build
step, opens offline.
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
from .util import days_between, today

RESPONSE_STATUSES = {"screening", "interview", "offer", "rejected"}
FUNNEL = ["shortlisted", "drafted", "ready", "submitted", "screening", "interview", "offer"]

PALETTE = {
    "ink": "#1b1c1e", "muted": "#6b7280", "line": "#e3e5e8", "bg": "#ffffff",
    "panel": "#f7f8fa",
    "series": ["#2f6f9f", "#4f9d69", "#c9812f", "#9a5ba1", "#b4574a", "#5b8a8f"],
}


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

    sources = Counter(
        row["source"] for row in
        store.db.execute("SELECT source FROM jobs").fetchall()
    )
    # Only postings that cleared the gates: including the rejects would put
    # 97% of the mass in the 0–9 band and flatten everything worth seeing.
    score_bands = Counter()
    for row in store.db.execute(
        """SELECT MAX(s.score) AS s FROM scores s
           WHERE s.verdict != 'reject' GROUP BY s.job_id"""
    ).fetchall():
        band = min(90, max(0, (row["s"] // 10) * 10))
        score_bands[band] += 1

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

def _bar_chart(data: dict[str, int], *, width: int = 520, bar_h: int = 26,
               colour: str = PALETTE["series"][0], label_w: int = 150) -> str:
    if not data:
        return '<p class="empty">No data yet.</p>'
    top = max(data.values()) or 1
    height = len(data) * (bar_h + 8) + 8
    plot_w = width - label_w - 46
    rows = []
    for i, (label, value) in enumerate(data.items()):
        y = 8 + i * (bar_h + 8)
        w = max(2, int(plot_w * value / top))
        rows.append(
            f'<text x="{label_w - 10}" y="{y + bar_h * 0.68}" text-anchor="end" class="lbl">'
            f'{html.escape(str(label))}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w}" height="{bar_h}" rx="3" fill="{colour}"/>'
            f'<text x="{label_w + w + 8}" y="{y + bar_h * 0.68}" class="val">{value}</text>'
        )
    return (f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">'
            f'{"".join(rows)}</svg>')


def _funnel_chart(by_status: dict[str, int], width: int = 520) -> str:
    """Cumulative funnel: each stage counts everyone who reached it or beyond."""
    order = {s: i for i, s in enumerate(STATUSES)}
    reached: dict[str, int] = {}
    for stage in FUNNEL:
        idx = order[stage]
        reached[stage] = sum(
            n for status, n in by_status.items()
            if status in order and order[status] >= idx and status not in ("withdrawn",)
        )
    # rejected/ghosted sit after 'submitted' in the enum but represent people who
    # did reach submission, so they are already counted above.
    return _bar_chart(reached, width=width, colour=PALETTE["series"][0])


def _track_chart(by_track: dict[str, dict[str, int]], width: int = 520) -> str:
    if not by_track:
        return '<p class="empty">Nothing submitted yet.</p>'
    bar_h, label_w = 26, 150
    height = len(by_track) * (bar_h + 10) + 10
    plot_w = width - label_w - 60
    top = max((v["submitted"] for v in by_track.values()), default=1) or 1
    rows = []
    for i, (track, values) in enumerate(sorted(by_track.items())):
        y = 10 + i * (bar_h + 10)
        w_all = max(2, int(plot_w * values["submitted"] / top))
        w_rep = max(0, int(plot_w * values["responded"] / top))
        rate = f'{values["responded"] / values["submitted"]:.0%}' if values["submitted"] else "–"
        rows.append(
            f'<text x="{label_w - 10}" y="{y + bar_h * 0.68}" text-anchor="end" class="lbl">'
            f'{html.escape(track)}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w_all}" height="{bar_h}" rx="3" fill="{PALETTE["line"]}"/>'
            f'<rect x="{label_w}" y="{y}" width="{w_rep}" height="{bar_h}" rx="3" fill="{PALETTE["series"][1]}"/>'
            f'<text x="{label_w + w_all + 8}" y="{y + bar_h * 0.68}" class="val">'
            f'{values["responded"]}/{values["submitted"]} · {rate}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">{"".join(rows)}</svg>'


# ------------------------------------------------------------------ page

CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f2f3f5;color:#1b1c1e;
 font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:14px;margin:0 0 14px;letter-spacing:.04em;
 text-transform:uppercase;color:#6b7280}
.sub{color:#6b7280;margin:0 0 26px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:16px}
.card{background:#fff;border:1px solid #e3e5e8;border-radius:10px;padding:18px 20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}
.kpi{background:#fff;border:1px solid #e3e5e8;border-radius:10px;padding:14px 16px}
.kpi .n{font-size:26px;font-weight:600;letter-spacing:-.02em}
.kpi .k{color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.chart{width:100%;height:auto}
.chart .lbl{font-size:12px;fill:#4b5563}
.chart .val{font-size:12px;fill:#6b7280}
.empty{color:#9ca3af;font-style:italic;margin:4px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-weight:600;color:#6b7280;padding:8px 10px;border-bottom:1px solid #e3e5e8;
 position:sticky;top:0;background:#fff;cursor:pointer;user-select:none}
td{padding:8px 10px;border-bottom:1px solid #f0f1f3;vertical-align:top}
tr:hover td{background:#fafbfc}
a{color:#2f6f9f;text-decoration:none} a:hover{text-decoration:underline}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.p-pass{background:#e6f4ea;color:#276b3c} .p-review{background:#fdf3e0;color:#8a5a12}
.p-reject{background:#f1f2f4;color:#6b7280}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
input,select{font:inherit;padding:7px 10px;border:1px solid #d6d9dd;border-radius:7px;background:#fff}
input{flex:1;min-width:200px}
.scroll{overflow-x:auto;max-height:620px;overflow-y:auto}
footer{color:#9ca3af;font-size:12px;margin-top:24px}
"""

JS = """
const rows = Array.from(document.querySelectorAll('#jobs tbody tr'));
const q = document.getElementById('q');
const trackSel = document.getElementById('track');
const verdictSel = document.getElementById('verdict');
function apply(){
  const text = q.value.toLowerCase();
  const track = trackSel.value, verdict = verdictSel.value;
  let shown = 0;
  rows.forEach(r=>{
    const ok = (!text || r.dataset.search.includes(text))
      && (!track || r.dataset.track === track)
      && (!verdict || r.dataset.verdict === verdict);
    r.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  document.getElementById('count').textContent = shown + ' of ' + rows.length;
}
[q, trackSel, verdictSel].forEach(el => el.addEventListener('input', apply));
document.querySelectorAll('#jobs th[data-sort]').forEach((th, i) => {
  let asc = false;
  th.addEventListener('click', () => {
    asc = !asc;
    const key = th.dataset.sort;
    const body = th.closest('table').querySelector('tbody');
    rows.sort((a,b)=>{
      const x = a.dataset[key] || '', y = b.dataset[key] || '';
      const n = Number(x) - Number(y);
      const cmp = isNaN(n) ? x.localeCompare(y) : n;
      return asc ? cmp : -cmp;
    }).forEach(r => body.appendChild(r));
  });
});
apply();
"""


def build_dashboard(store: Store, cfg: Any, out_path: str | Path) -> Path:
    stats = funnel_stats(store)
    # Gated jobs are excluded: a table of five thousand rejects is not a
    # dashboard, it is a log. The rejection reasons stay available in `jsa top
    # --include-rejected` and in each job's breakdown.
    rows = store.best_scores(min_score=0, limit=4000, include_closed=True)
    counts = stats["counts"]

    kpis = [
        ("jobs seen", counts["jobs"]),
        ("open now", counts["open_jobs"]),
        ("in tracker", counts["applications"]),
        ("submitted", stats["submitted"]),
        ("replies", stats["responded"]),
        ("response rate", f"{stats['response_rate']:.0%}" if stats["response_rate"] is not None else "–"),
        ("median reply", f"{stats['median_response_days']}d" if stats["median_response_days"] is not None else "–"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="n">{html.escape(str(v))}</div>'
        f'<div class="k">{html.escape(k)}</div></div>' for k, v in kpis
    )

    body_rows = []
    for row in rows:
        verdict = row["verdict"]
        search = " ".join(str(row.get(k) or "") for k in
                          ("company", "title", "location", "track", "source")).lower()
        status = row["app_status"] or ""
        body_rows.append(
            f'<tr data-search="{html.escape(search, quote=True)}" data-track="{html.escape(row["track"])}"'
            f' data-verdict="{verdict}" data-score="{row["score"]}"'
            f' data-company="{html.escape(row["company"], quote=True)}"'
            f' data-seen="{html.escape(row["first_seen"][:10])}">'
            f'<td><span class="pill p-{verdict}">{row["score"]}</span></td>'
            f'<td>{html.escape(row["company"])}</td>'
            f'<td><a href="{html.escape(row["url"], quote=True)}" target="_blank" rel="noopener">'
            f'{html.escape(row["title"])}</a></td>'
            f'<td>{html.escape(row["location"] or "–")}</td>'
            f'<td>{html.escape(row["track"])}</td>'
            f'<td>{html.escape(row["source"])}</td>'
            f'<td>{html.escape(status or "–")}</td>'
            f'<td>{html.escape(row["first_seen"][:10])}</td></tr>'
        )

    tracks = sorted({r["track"] for r in rows})
    track_options = "".join(f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in tracks)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job search pipeline</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Job search pipeline</h1>
<p class="sub">Generated {today()} · {counts['jobs']} postings seen from {len(stats['by_source'])} sources ·
{len(body_rows)} cleared the hard gates · scoring v{SCORER_VERSION}</p>
<div class="kpis">{kpi_html}</div>
<div class="grid">
  <div class="card"><h2>Application funnel</h2>{_funnel_chart(stats['by_status'])}</div>
  <div class="card"><h2>Replies by positioning track</h2>{_track_chart(stats['by_track'])}</div>
  <div class="card"><h2>Where postings come from</h2>
    {_bar_chart(dict(sorted(stats['by_source'].items(), key=lambda kv: -kv[1])), colour=PALETTE['series'][2])}</div>
  <div class="card"><h2>Fit score, cleared postings</h2>
    {_bar_chart({f"{k}–{k+9}": v for k, v in stats['score_bands'].items()}, colour=PALETTE['series'][5])}</div>
</div>
<div class="card">
  <h2>Postings that cleared the gates</h2>
  <div class="controls">
    <input id="q" placeholder="Filter by company, role, location…">
    <select id="track"><option value="">All tracks</option>{track_options}</select>
    <select id="verdict"><option value="">All verdicts</option>
      <option value="pass">pass</option><option value="review">review</option>
      <option value="reject">reject</option></select>
    <span id="count" style="align-self:center;color:#6b7280"></span>
  </div>
  <div class="scroll"><table id="jobs"><thead><tr>
    <th data-sort="score">Fit</th><th data-sort="company">Company</th><th>Role</th>
    <th>Location</th><th data-sort="track">Track</th><th>Source</th><th>Status</th>
    <th data-sort="seen">Seen</th>
  </tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>
</div>
<footer>Self-contained: no network calls, no tracking. Built by job-search-agent.</footer>
</div><script>{JS}</script></body></html>"""

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
