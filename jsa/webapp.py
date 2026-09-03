"""The dashboard interface.

One page serves two modes. Exported with `jsa dashboard` it is a static file
you can archive or send to someone; served with `jsa serve` the same page can
write back — change a status, keep a note — straight into SQLite, so the
database stays the single source of truth instead of the browser holding a
second, divergent copy.
"""

from __future__ import annotations

import html
import json
from typing import Any

from .models import STATUSES

CSS = """
:root{
  --bg:#f4f5f7; --panel:#ffffff; --panel-2:#fafbfc; --ink:#16181d; --ink-2:#5b6270;
  --ink-3:#878e9c; --line:#e4e6ea; --line-2:#eef0f3; --accent:#1f6feb; --accent-soft:#e8f0fe;
  --pass:#1a7f4b; --pass-bg:#e6f4ec; --review:#8a5a12; --review-bg:#fdf3e0;
  --reject:#6b7280; --reject-bg:#f0f1f3; --shadow:0 1px 2px rgba(16,20,30,.06),0 8px 24px rgba(16,20,30,.06);
  --radius:12px; color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0f1115; --panel:#171a21; --panel-2:#1c2029; --ink:#e8eaee; --ink-2:#a2a9b6;
    --ink-3:#767d8b; --line:#262b35; --line-2:#20242c; --accent:#5b9cff; --accent-soft:#16233a;
    --pass:#5fd39a; --pass-bg:#16301f; --review:#e0b060; --review-bg:#332612;
    --reject:#8b93a1; --reject-bg:#20242c;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3); color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#0f1115; --panel:#171a21; --panel-2:#1c2029; --ink:#e8eaee; --ink-2:#a2a9b6;
  --ink-3:#767d8b; --line:#262b35; --line-2:#20242c; --accent:#5b9cff; --accent-soft:#16233a;
  --pass:#5fd39a; --pass-bg:#16301f; --review:#e0b060; --review-bg:#332612;
  --reject:#8b93a1; --reject-bg:#20242c;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3); color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
button{font:inherit;cursor:pointer}

.topbar{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--panel) 88%,transparent);
  backdrop-filter:saturate(160%) blur(12px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1400px;margin:0 auto;padding:12px 24px;display:flex;gap:16px;align-items:center}
.brand{display:flex;flex-direction:column;line-height:1.25;margin-right:6px}
.brand b{font-size:15px;letter-spacing:-.01em}
.brand span{font-size:11.5px;color:var(--ink-3)}
.search{flex:1;max-width:460px;position:relative}
.search input{width:100%;padding:8px 12px 8px 32px;border:1px solid var(--line);border-radius:9px;
  background:var(--panel-2);color:var(--ink);font-size:13px}
.search input:focus{outline:2px solid var(--accent-soft);border-color:var(--accent)}
.search svg{position:absolute;left:10px;top:9px;width:14px;height:14px;stroke:var(--ink-3);fill:none;stroke-width:2}
.spacer{flex:1}
.iconbtn{background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:7px 11px;
  color:var(--ink-2);font-size:12.5px}
.iconbtn:hover{border-color:var(--accent);color:var(--accent)}
.livedot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--pass);margin-right:6px}
.livedot.off{background:var(--ink-3)}

.wrap{max-width:1400px;margin:0 auto;padding:22px 24px 80px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:13px 15px}
.kpi .n{font-size:23px;font-weight:600;letter-spacing:-.025em;line-height:1.15}
.kpi .k{color:var(--ink-3);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;margin-top:3px}

.tabs{display:flex;gap:3px;background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:3px;width:fit-content;margin-bottom:16px}
.tab{border:0;background:transparent;color:var(--ink-2);padding:7px 15px;border-radius:7px;font-size:13px;font-weight:500}
.tab[aria-selected="true"]{background:var(--accent-soft);color:var(--accent)}

.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
select{font:inherit;font-size:12.5px;padding:6px 9px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink)}
.count{color:var(--ink-3);font-size:12.5px;margin-left:auto}

.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.tablewrap{overflow:auto;max-height:calc(100vh - 330px);border-radius:var(--radius)}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}
thead th{position:sticky;top:0;z-index:2;background:var(--panel);text-align:left;font-weight:600;
  font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);
  padding:11px 14px;border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
thead th:hover{color:var(--ink)}
tbody td{padding:11px 14px;border-bottom:1px solid var(--line-2);vertical-align:middle}
tbody tr{cursor:pointer}
tbody tr:hover td{background:var(--panel-2)}
tbody tr.sel td{background:var(--accent-soft)}
.role{font-weight:550;letter-spacing:-.005em}
.sub{color:var(--ink-3);font-size:11.5px;margin-top:1px}
.chip{display:inline-flex;align-items:center;justify-content:center;min-width:34px;padding:3px 8px;
  border-radius:7px;font-size:12px;font-weight:650;font-variant-numeric:tabular-nums}
.c-pass{background:var(--pass-bg);color:var(--pass)} .c-review{background:var(--review-bg);color:var(--review)}
.c-reject{background:var(--reject-bg);color:var(--reject)}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;
  background:var(--panel-2);border:1px solid var(--line);color:var(--ink-2);white-space:nowrap}
.tag.st{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.nowrap{white-space:nowrap;color:var(--ink-3);font-size:12px;font-variant-numeric:tabular-nums}
.notedot{color:var(--accent);font-size:11px}

.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;align-items:start}
.col{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px}
.col h3{margin:0 0 10px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3);
  display:flex;justify-content:space-between}
.jc{border:1px solid var(--line);border-radius:9px;padding:10px;margin-bottom:8px;background:var(--panel-2);cursor:pointer}
.jc:hover{border-color:var(--accent)}
.jc b{display:block;font-size:12.5px;font-weight:600;line-height:1.35}
.jc span{display:block;color:var(--ink-3);font-size:11px;margin-top:3px}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.panelhead{padding:15px 18px 4px}
.panelhead h2{margin:0;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3)}
.panelbody{padding:10px 18px 18px}
.chart{width:100%;height:auto;display:block}
.chart .lbl{font-size:11px;fill:var(--ink-2)} .chart .val{font-size:11px;fill:var(--ink-3);font-weight:600}
.empty{color:var(--ink-3);font-style:italic;font-size:13px;margin:6px 0}

.scrim{position:fixed;inset:0;background:rgba(10,12,16,.38);opacity:0;pointer-events:none;
  transition:opacity .18s ease;z-index:40}
.scrim.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100vh;width:min(560px,94vw);background:var(--panel);
  border-left:1px solid var(--line);transform:translateX(100%);transition:transform .22s cubic-bezier(.4,0,.2,1);
  z-index:50;display:flex;flex-direction:column;box-shadow:-16px 0 48px rgba(10,12,16,.14)}
.drawer.open{transform:none}
.dhead{padding:20px 22px 14px;border-bottom:1px solid var(--line)}
.dhead h2{margin:0 0 4px;font-size:17px;line-height:1.3;letter-spacing:-.015em}
.dhead .co{color:var(--ink-2);font-size:13px}
.dbody{overflow-y:auto;padding:18px 22px 28px;flex:1}
.dsec{margin-bottom:22px}
.dsec h3{margin:0 0 10px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3)}
.meta{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:12.5px}
.meta dt{color:var(--ink-3)} .meta dd{margin:0}
.bar{display:grid;grid-template-columns:74px 1fr 54px;gap:9px;align-items:center;margin-bottom:7px;font-size:12px}
.bar .track{display:block;height:7px;border-radius:4px;background:var(--line-2);overflow:hidden}
.bar .fill{display:block;height:100%;border-radius:4px;background:var(--accent);min-width:2px}
.bar .num{text-align:right;color:var(--ink-3);font-variant-numeric:tabular-nums;font-size:11.5px}
.hits{font-size:11.5px;color:var(--ink-3);margin:-3px 0 9px 83px;line-height:1.45}
.gate{background:var(--reject-bg);border-left:2px solid var(--reject);padding:8px 11px;border-radius:0 7px 7px 0;
  font-size:12.5px;color:var(--ink-2);margin-bottom:7px}
.desc{font-size:12.5px;color:var(--ink-2);white-space:pre-wrap;max-height:230px;overflow-y:auto;
  background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:12px;line-height:1.55}
textarea{width:100%;min-height:82px;font:inherit;font-size:13px;padding:10px;border:1px solid var(--line);
  border-radius:9px;background:var(--panel-2);color:var(--ink);resize:vertical}
textarea:focus{outline:2px solid var(--accent-soft);border-color:var(--accent)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.btn{border:1px solid var(--line);background:var(--panel-2);color:var(--ink);border-radius:9px;padding:8px 13px;font-size:12.5px}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.pri{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.pri:hover{filter:brightness(1.08);color:#fff}
.btn:disabled{opacity:.5;cursor:not-allowed}
code{background:var(--panel-2);border:1px solid var(--line);border-radius:6px;padding:2px 6px;
  font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.cmd{display:block;padding:9px 11px;margin-top:6px;overflow-x:auto;white-space:nowrap}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(80px);background:var(--ink);
  color:var(--bg);padding:10px 18px;border-radius:10px;font-size:13px;z-index:60;transition:transform .2s ease}
.toast.show{transform:translateX(-50%)}
.readonly{background:var(--review-bg);color:var(--review);border-radius:9px;padding:9px 12px;font-size:12.5px}
footer{color:var(--ink-3);font-size:11.5px;margin-top:26px;text-align:center}
@media (max-width:720px){
  .topbar-in{flex-wrap:wrap;padding:10px 14px} .wrap{padding:16px 14px 60px}
  .search{max-width:none;order:3;flex-basis:100%} .tablewrap{max-height:none}
  th.hide,td.hide{display:none}
}
"""

JS = r"""
const DATA = window.__JSA__;
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const DIMS = ['title','skills','domain','location','seniority'];
let sortKey = 'score', sortAsc = false, selected = null;

/* ---------------------------------------------------------------- theme */
const savedTheme = (() => { try { return localStorage.getItem('jsa-theme'); } catch { return null; } })();
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$('#theme').onclick = () => {
  const dark = getComputedStyle(document.body).backgroundColor.match(/\d+/g)[0] < 60;
  const next = dark ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('jsa-theme', next); } catch {}
};

/* ----------------------------------------------------------------- tabs */
document.querySelectorAll('.tab').forEach(tab => tab.onclick = () => {
  document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-selected', t === tab));
  document.querySelectorAll('[data-view]').forEach(v => v.hidden = v.dataset.view !== tab.dataset.target);
  if (tab.dataset.target === 'pipeline') renderBoard();
});

/* -------------------------------------------------------------- filters */
function visible() {
  const q = $('#q').value.trim().toLowerCase();
  const f = id => $('#' + id).value;
  return DATA.jobs.filter(j => {
    if (q && !(j.company + ' ' + j.title + ' ' + (j.location||'') + ' ' + (j.notes||'')).toLowerCase().includes(q)) return false;
    if (f('fTrack') && j.track !== f('fTrack')) return false;
    if (f('fVerdict') && j.verdict !== f('fVerdict')) return false;
    if (f('fCountry') && (j.country || '–') !== f('fCountry')) return false;
    if (f('fSource') && j.source !== f('fSource')) return false;
    if (f('fStatus') === '__none' ? j.status : (f('fStatus') && j.status !== f('fStatus'))) return false;
    return true;
  }).sort((a, b) => {
    const x = a[sortKey] ?? '', y = b[sortKey] ?? '';
    const n = (typeof x === 'number' && typeof y === 'number') ? x - y : String(x).localeCompare(String(y));
    return sortAsc ? n : -n;
  });
}

function renderTable() {
  const rows = visible();
  $('#count').textContent = rows.length + ' of ' + DATA.jobs.length;
  $('#tbody').innerHTML = rows.map(j => `
    <tr data-id="${j.id}" class="${selected === j.id ? 'sel' : ''}">
      <td><span class="chip c-${j.verdict}">${j.score}</span></td>
      <td><div class="role">${esc(j.title)}</div><div class="sub">${esc(j.company)}</div></td>
      <td class="hide">${esc(j.location || '–')}${j.remote !== 'unknown' ? ` <span class="sub">${j.remote}</span>` : ''}</td>
      <td class="hide"><span class="tag">${esc(j.track)}</span></td>
      <td class="hide"><span class="tag">${esc(j.source)}</span></td>
      <td>${j.status ? `<span class="tag st">${esc(j.status)}</span>` : ''}${j.notes ? ' <span class="notedot" title="has a note">&#9679;</span>' : ''}</td>
      <td class="nowrap hide">${esc((j.first_seen || '').slice(0, 10))}</td>
    </tr>`).join('') || `<tr><td colspan="7" class="empty">Nothing matches these filters.</td></tr>`;
  $('#tbody').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => openJob(tr.dataset.id));
}

document.querySelectorAll('th[data-sort]').forEach(th => th.onclick = () => {
  const k = th.dataset.sort;
  if (k === sortKey) sortAsc = !sortAsc; else { sortKey = k; sortAsc = k !== 'score'; }
  renderTable();
});
['q','fTrack','fVerdict','fCountry','fSource','fStatus'].forEach(id => {
  const el = $('#' + id); el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', renderTable);
});

/* --------------------------------------------------------------- board */
function renderBoard() {
  const cols = DATA.statuses.filter(s => !['withdrawn','ghosted'].includes(s));
  $('#board').innerHTML = cols.map(s => {
    const items = DATA.jobs.filter(j => j.status === s);
    return `<div class="col"><h3>${s}<span>${items.length}</span></h3>
      ${items.map(j => `<div class="jc" data-id="${j.id}"><b>${esc(j.title)}</b>
        <span>${esc(j.company)} · ${esc(j.location || '–')}</span></div>`).join('')
      || '<div class="empty">—</div>'}</div>`;
  }).join('');
  $('#board').querySelectorAll('.jc').forEach(c => c.onclick = () => openJob(c.dataset.id));
}

/* -------------------------------------------------------------- drawer */
function openJob(id) {
  const j = DATA.jobs.find(x => x.id === id);
  if (!j) return;
  selected = id;
  const b = j.breakdown || {};
  const bars = DIMS.filter(d => b[d]).map(d => {
    const dim = b[d], pct = Math.round(100 * dim.points / dim.max);
    const hits = d === 'title' ? [...(dim.strong||[]), ...(dim.good||[]), ...(dim.weak||[])]
      : d === 'skills' ? [...(dim.must_have||[]), ...(dim.nice_to_have||[])]
      : d === 'domain' ? (dim.matched || [])
      : d === 'location' ? [dim.why] : [`${dim.detected}, ${dim.years_required}y asked`];
    return `<div class="bar"><span>${d}</span><span class="track"><span class="fill" style="width:${pct}%"></span></span>
      <span class="num">${dim.points}/${dim.max}</span></div>
      ${hits.length ? `<div class="hits">${esc(hits.slice(0, 8).join(' · '))}</div>` : ''}`;
  }).join('');
  const gates = (b.gates || []).map(g => `<div class="gate"><b>${esc(g.gate)}</b> — ${esc(g.reason)}</div>`).join('');
  const pen = b.penalties ? `<div class="gate">penalty ${b.penalties.points} — ${esc((b.penalties.matched||[]).join(', '))}</div>` : '';

  $('#dtitle').textContent = j.title;
  $('#dco').innerHTML = `${esc(j.company)} · ${esc(j.location || '–')} · <a href="${esc(j.url)}" target="_blank" rel="noopener">open posting &#8599;</a>`;
  $('#dbody').innerHTML = `
    <div class="dsec"><h3>Fit — ${j.score}/100, ${j.verdict}</h3>${bars}${gates}${pen}
      <dl class="meta">
        <dt>track</dt><dd>${esc(j.track)}</dd>
        <dt>source</dt><dd>${esc(j.source)}</dd>
        <dt>first seen</dt><dd>${esc((j.first_seen||'').slice(0,10))}</dd>
        <dt>posting language</dt><dd>${esc(b.language || '–')}</dd>
      </dl></div>
    <div class="dsec"><h3>Your notes</h3>
      ${DATA.interactive
        ? `<textarea id="note" placeholder="What matters about this one — who to mention, what to check, why you passed.">${esc(j.notes || '')}</textarea>
           <div class="row" style="margin-top:8px">
             <select id="dstatus">${['', ...DATA.statuses].map(s =>
               `<option value="${s}"${s === (j.status||'') ? ' selected' : ''}>${s || 'no status'}</option>`).join('')}</select>
             <button class="btn pri" id="save">Save</button>
             <span id="saved" style="color:var(--ink-3);font-size:12px"></span>
           </div>`
        : `<div class="readonly">Read-only export. Run <code>python3 -m jsa serve</code> to edit statuses and notes here.</div>
           ${j.notes ? `<div class="desc" style="margin-top:9px">${esc(j.notes)}</div>` : ''}`}
    </div>
    <div class="dsec"><h3>Next step</h3>
      <code class="cmd">python3 -m jsa brief ${j.id.slice(0,8)}</code>
      <code class="cmd">python3 -m jsa docs ${j.id.slice(0,8)} --overlay &lt;overlay.json&gt;</code>
      <button class="btn" id="copy" style="margin-top:9px">Copy job id</button></div>
    ${j.description ? `<div class="dsec"><h3>Posting</h3><div class="desc">${esc(j.description)}</div></div>` : ''}`;

  $('#copy').onclick = async () => {
    try { await navigator.clipboard.writeText(j.id); toast('Job id copied'); }
    catch { toast('Copy failed — select it by hand'); }
  };
  if (DATA.interactive) $('#save').onclick = () => save(j);
  $('#scrim').classList.add('open'); $('#drawer').classList.add('open');
  renderTable();
}

function closeDrawer() {
  $('#scrim').classList.remove('open'); $('#drawer').classList.remove('open');
  selected = null; renderTable();
}
$('#scrim').onclick = closeDrawer; $('#dclose').onclick = closeDrawer;
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

async function save(j) {
  const status = $('#dstatus').value, notes = $('#note').value;
  $('#save').disabled = true;
  try {
    const res = await fetch('api/job/' + j.id, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({status: status || null, notes}),
    });
    if (!res.ok) throw new Error(await res.text());
    const updated = await res.json();
    Object.assign(j, updated);
    toast('Saved to the database');
    renderTable();
  } catch (err) {
    toast('Not saved: ' + err.message);
  } finally { $('#save').disabled = false; }
}

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

renderTable();
"""


def _options(values: list[str], label: str) -> str:
    opts = "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in values)
    return f'<option value="">{html.escape(label)}</option>{opts}'


def render_page(data: dict[str, Any], charts: dict[str, str]) -> str:
    """Full HTML document. `charts` holds pre-rendered inline SVG."""
    jobs = data["jobs"]
    counts, stats = data["counts"], data["stats"]
    kpis = [
        ("postings seen", counts["jobs"]),
        ("cleared gates", len([j for j in jobs if j["verdict"] != "reject"])),
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
    tracks = sorted({j["track"] for j in jobs})
    countries = sorted({j["country"] or "–" for j in jobs})
    sources = sorted({j["source"] for j in jobs})
    live = ('<span class="livedot"></span>live — edits save to the database' if data["interactive"]
            else '<span class="livedot off"></span>static export')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job pipeline · job-search-agent</title>
<style>{CSS}</style></head><body>

<div class="topbar"><div class="topbar-in">
  <div class="brand"><b>Job pipeline</b><span>{live}</span></div>
  <div class="search">
    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="q" placeholder="Search role, company, location, notes…" autocomplete="off">
  </div>
  <div class="spacer"></div>
  <button class="iconbtn" id="theme">Theme</button>
</div></div>

<div class="wrap">
  <div class="kpis">{kpi_html}</div>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" aria-selected="true" data-target="shortlist">Shortlist</button>
    <button class="tab" role="tab" aria-selected="false" data-target="pipeline">Pipeline</button>
    <button class="tab" role="tab" aria-selected="false" data-target="insights">Insights</button>
  </div>

  <section data-view="shortlist">
    <div class="filters">
      <select id="fTrack">{_options(tracks, "All tracks")}</select>
      <select id="fVerdict"><option value="">All verdicts</option><option value="pass">pass</option>
        <option value="review">review</option><option value="reject">reject</option></select>
      <select id="fCountry">{_options(countries, "Anywhere")}</select>
      <select id="fSource">{_options(sources, "All sources")}</select>
      <select id="fStatus">{_options(STATUSES, "Any status")}<option value="__none">Not yet tracked</option></select>
      <span class="count" id="count"></span>
    </div>
    <div class="card"><div class="tablewrap"><table>
      <thead><tr>
        <th data-sort="score">Fit</th><th data-sort="title">Role</th>
        <th data-sort="location" class="hide">Location</th><th data-sort="track" class="hide">Track</th>
        <th data-sort="source" class="hide">Source</th><th data-sort="status">Status</th>
        <th data-sort="first_seen" class="hide">Seen</th>
      </tr></thead><tbody id="tbody"></tbody>
    </table></div></div>
  </section>

  <section data-view="pipeline" hidden><div class="board" id="board"></div></section>

  <section data-view="insights" hidden>
    <div class="grid">
      <div class="card"><div class="panelhead"><h2>Application funnel</h2></div>
        <div class="panelbody">{charts['funnel']}</div></div>
      <div class="card"><div class="panelhead"><h2>Replies by positioning track</h2></div>
        <div class="panelbody">{charts['tracks']}</div></div>
      <div class="card"><div class="panelhead"><h2>Where postings come from</h2></div>
        <div class="panelbody">{charts['sources']}</div></div>
      <div class="card"><div class="panelhead"><h2>Fit score, cleared postings</h2></div>
        <div class="panelbody">{charts['scores']}</div></div>
    </div>
  </section>

  <footer>Generated {html.escape(data['generated'][:16].replace('T', ' '))} ·
    {counts['jobs']} postings from {len(stats['by_source'])} sources · scoring v{html.escape(data['scorer_version'])} ·
    self-contained, no network calls</footer>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-label="Job detail">
  <div class="dhead">
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div><h2 id="dtitle"></h2><div class="co" id="dco"></div></div>
      <button class="iconbtn" id="dclose">Close</button>
    </div>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>
<div class="toast" id="toast"></div>

<script>window.__JSA__ = {json.dumps(data, ensure_ascii=False)};</script>
<script>{JS}</script>
</body></html>"""
