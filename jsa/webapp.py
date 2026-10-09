"""The dashboard interface.

One page serves two modes. Exported with `jsa dashboard` it is a static file
you can archive or send to someone; served with `jsa serve` the same page can
write back — change a status, keep a note — straight into SQLite, so the
database stays the single source of truth instead of the browser holding a
second, divergent copy.
"""

from __future__ import annotations

import base64
import functools
import html
import json
import secrets
from pathlib import Path
from typing import Any

from .i18n import LANGUAGES, bundle
from .models import STATUSES

CSS = """
:root{
  --bg:#F2F4F7; --panel:#FFFFFF; --panel-2:#F6F7FA; --ink:#0B1220; --ink-2:#3A4558;
  --ink-3:#5B6474; --line:#E2E5EC; --line-2:#EDF0F4;
  --accent:#FF6B4A; --accent-ink:#C2401F; --accent-soft:#FFE9E3;
  --navy:#0B1220; --navy-2:#16203A; --navy-3:#1E2A47; --navy-ink:#C9D1E0; --navy-muted:#8A94A8;
  --pass:#0B1220; --pass-bg:#FFE0D7; --review:#7A4E0E; --review-bg:#FDF1DC;
  --reject:#5B6474; --reject-bg:#ECEEF2;
  --shadow:0 1px 2px rgba(11,18,32,.05),0 12px 32px -12px rgba(11,18,32,.12);
  --radius:24px; color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0B1220; --panel:#141E36; --panel-2:#1A2440; --ink:#FFFFFF; --ink-2:#C9D1E0;
    --ink-3:#8A94A8; --line:#1E2A47; --line-2:#1A2440;
    --accent:#FF6B4A; --accent-ink:#FF9A80; --accent-soft:rgba(255,107,74,.16);
    --navy:#141E36; --navy-2:#1A2440; --navy-3:#263252;
    --pass:#FF9A80; --pass-bg:rgba(255,107,74,.16); --review:#E8B862; --review-bg:rgba(232,184,98,.14);
    --reject:#8A94A8; --reject-bg:#1A2440;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 16px 40px -16px rgba(0,0,0,.6); color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#0B1220; --panel:#141E36; --panel-2:#1A2440; --ink:#FFFFFF; --ink-2:#C9D1E0;
  --ink-3:#8A94A8; --line:#1E2A47; --line-2:#1A2440;
  --accent:#FF6B4A; --accent-ink:#FF9A80; --accent-soft:rgba(255,107,74,.16);
  --navy:#141E36; --navy-2:#1A2440; --navy-3:#263252;
  --pass:#FF9A80; --pass-bg:rgba(255,107,74,.16); --review:#E8B862; --review-bg:rgba(232,184,98,.14);
  --reject:#8A94A8; --reject-bg:#1A2440;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 16px 40px -16px rgba(0,0,0,.6); color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 Inter,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01"}
a{color:var(--accent-ink);text-decoration:none} a:hover{text-decoration:underline}
button,select,input,textarea{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}

/* ------------------------------------------------------------ top bar */
.top{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--bg) 82%,transparent);
  backdrop-filter:saturate(180%) blur(18px);-webkit-backdrop-filter:saturate(180%) blur(18px)}
.top-in{max-width:1320px;margin:0 auto;padding:14px 28px;display:flex;gap:18px;align-items:center}
.brand{display:flex;align-items:center;gap:10px;min-width:0}
.brand i{flex:none;width:11px;height:11px;border-radius:50%;background:var(--accent)}
.brand b{display:block;font-size:16px;font-weight:800;letter-spacing:-.02em;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.brand>div{min-width:0}
.brand small{display:block;font-size:11.5px;color:var(--ink-3);white-space:nowrap;max-width:190px;
  overflow:hidden;text-overflow:ellipsis}
.livedot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#2BB673;margin-right:6px}
.livedot.off{background:var(--ink-3)}
.tabs{display:flex;gap:4px;background:var(--panel);border-radius:999px;padding:4px;box-shadow:var(--shadow);margin:0 auto}
.tab{display:inline-flex;align-items:center;gap:7px;border:0;background:transparent;color:var(--ink-2);
  height:38px;padding:0 16px;border-radius:999px;font-size:14px;font-weight:600;white-space:nowrap}
.tab svg{width:17px;height:17px;flex:none}
.tab:hover{color:var(--ink)}
.tab[aria-selected="true"]{background:var(--navy);color:#FFFFFF}
.tools{display:flex;gap:8px;align-items:center}
.run{display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 18px;border:0;border-radius:999px;
  background:var(--accent);color:#0B1220;font-size:14px;font-weight:700;white-space:nowrap}
.run:hover:not(:disabled){filter:brightness(1.05)}
.run:disabled{opacity:.55;cursor:not-allowed}
.round{width:40px;height:40px;border-radius:50%;border:0;background:var(--panel);color:var(--ink-2);
  display:inline-flex;align-items:center;justify-content:center;box-shadow:var(--shadow)}
.round svg{width:18px;height:18px}
.round:hover{color:var(--ink)}
.langsel{height:40px;border:0;border-radius:999px;background:var(--panel);color:var(--ink-2);
  padding:0 12px;font-size:13px;font-weight:600;box-shadow:var(--shadow);cursor:pointer}
.spin{width:13px;height:13px;border:2px solid rgba(11,18,32,.3);border-top-color:#0B1220;
  border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

.runlog{max-width:1320px;margin:0 auto;padding:0 28px}
.runlog .inner{background:var(--navy);color:var(--navy-ink);border-radius:var(--radius);padding:16px 20px;margin-top:8px}
.runlog pre{margin:0;max-height:230px;overflow:auto;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  white-space:pre-wrap}
.runlog h4{margin:0 0 8px;font-size:12px;font-weight:700;color:#FFFFFF;display:flex;justify-content:space-between}
.runlog a{color:#FF9A80}

/* --------------------------------------------------------------- page */
.wrap{max-width:1320px;margin:0 auto;padding:18px 28px 96px}
.hero{background:var(--navy);color:#FFFFFF;border-radius:32px;padding:30px 32px;display:grid;
  grid-template-columns:minmax(0,1.1fr) minmax(0,1.6fr);gap:28px;align-items:end;margin-bottom:22px;
  box-shadow:0 40px 80px -48px rgba(11,18,32,.6)}
.hero .now{display:flex;flex-direction:column;gap:6px}
.hero .now b{font-size:clamp(64px,8vw,104px);line-height:.85;font-weight:900;letter-spacing:-.06em;color:#FF6B4A;
  font-variant-numeric:tabular-nums}
.hero .now span{font-size:17px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.kpi{background:var(--navy-2);border-radius:18px;padding:12px 14px}
.kpi .n{font-size:22px;font-weight:800;letter-spacing:-.03em;line-height:1.15;font-variant-numeric:tabular-nums}
.kpi .k{color:var(--navy-muted);font-size:11.5px;margin-top:2px}

.steps{position:relative;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:22px}
.step{background:var(--panel);border-radius:20px;padding:16px 18px 16px 58px;position:relative;box-shadow:var(--shadow)}
.step b{display:block;font-size:14.5px;margin-bottom:2px}
.step span{color:var(--ink-2);font-size:13.5px;line-height:1.5}
.step i{position:absolute;top:16px;left:18px;font-style:normal;font-size:13px;font-weight:800;color:#0B1220;
  background:var(--accent);border-radius:12px;width:28px;height:28px;display:grid;place-items:center}
.dismiss{position:absolute;top:-10px;right:-6px;width:32px;height:32px;border-radius:50%;border:0;z-index:2;
  background:var(--panel);color:var(--ink-3);font-size:18px;line-height:1;box-shadow:var(--shadow)}
.dismiss:hover{color:var(--ink)}
.lead{display:flex;align-items:baseline;gap:12px;margin:6px 0 14px;flex-wrap:wrap}
.lead h2{margin:0;font-size:24px;font-weight:800;letter-spacing:-.03em}
.lead span{color:var(--ink-3);font-size:14px}

.deck{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr));gap:14px;margin-bottom:20px}
.pick{background:var(--panel);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px;display:grid;
  grid-template-columns:auto minmax(0,1fr);gap:18px;transition:opacity .2s ease,transform .2s ease}
.pick.gone{opacity:0;transform:translateX(24px)}
.score{width:68px;height:68px;border-radius:20px;display:grid;place-items:center;font-size:28px;font-weight:900;
  letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.score.c-pass{background:var(--navy);color:#FF6B4A}
.pick h3{margin:0;font-size:18px;font-weight:700;letter-spacing:-.02em;line-height:1.3}
.pick .where{color:var(--ink-3);font-size:14px;margin:4px 0 10px}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.badge{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 12px;border-radius:999px;font-size:12.5px;
  font-weight:600;background:var(--panel-2);color:var(--ink-2);border:0}
.badge.it{background:var(--accent-soft);color:var(--accent-ink)}
.badge.country b{font-weight:800;color:var(--ink)}
button.badge:hover{color:var(--ink)}
.pick .why{font-size:14.5px;line-height:1.6;margin:0 0 6px;color:var(--ink-2)}
.pick .gap{font-size:13.5px;color:var(--ink-3);margin:0 0 14px}
.pick .gap b{color:var(--review);font-weight:700}
.acts{display:flex;gap:8px;flex-wrap:wrap}
.done{background:var(--panel);border-radius:var(--radius);padding:44px 24px;text-align:center;color:var(--ink-2);
  box-shadow:var(--shadow)}
.done b{display:block;font-size:20px;font-weight:800;color:var(--ink);margin-bottom:6px;letter-spacing:-.02em}

.btn{display:inline-flex;align-items:center;justify-content:center;height:40px;padding:0 16px;border-radius:999px;
  border:0;background:var(--panel-2);color:var(--ink);font-size:13.5px;font-weight:600;text-decoration:none}
.btn:hover{background:var(--line);text-decoration:none}
.btn.pri{background:var(--accent);color:#0B1220}
.btn.pri:hover{filter:brightness(1.05);background:var(--accent)}
.btn:disabled{opacity:.5;cursor:not-allowed}

/* ------------------------------------------------------------ postings */
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.search{position:relative;flex:1 1 260px;max-width:420px}
.search input{width:100%;height:42px;padding:0 16px 0 40px;border:0;border-radius:999px;background:var(--panel);
  color:var(--ink);font-size:14px;box-shadow:var(--shadow)}
.search svg{position:absolute;left:15px;top:13px;width:16px;height:16px;stroke:var(--ink-3);fill:none;stroke-width:2}
.filters select{height:42px;border:0;border-radius:999px;background:var(--panel);color:var(--ink-2);padding:0 14px;
  font-size:13.5px;font-weight:600;box-shadow:var(--shadow);cursor:pointer;max-width:200px}
.toggle{display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 16px;border-radius:999px;background:var(--panel);
  color:var(--ink-2);font-size:13.5px;font-weight:600;box-shadow:var(--shadow);cursor:pointer;user-select:none}
.toggle input{accent-color:#FF6B4A;width:16px;height:16px;margin:0}
.toggle:has(input:checked){background:var(--accent);color:#0B1220}
.count{color:var(--ink-3);font-size:13px;margin-left:auto}
.card{background:var(--panel);border-radius:var(--radius);box-shadow:var(--shadow)}
.tablewrap{overflow:auto;max-height:calc(100vh - 250px);border-radius:var(--radius)}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:14px}
thead th{position:sticky;top:0;z-index:2;background:var(--panel);text-align:left;font-weight:600;font-size:12px;
  color:var(--ink-3);padding:14px 16px;border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
thead th:hover{color:var(--ink)}
tbody td{padding:13px 16px;border-bottom:1px solid var(--line-2);vertical-align:middle}
tbody tr{cursor:pointer}
tbody tr:hover td{background:var(--panel-2)}
tbody tr.sel td{background:var(--accent-soft)}
.role{font-weight:650;letter-spacing:-.01em}
.sub{color:var(--ink-3);font-size:12.5px;margin-top:1px}
.chip{display:inline-flex;align-items:center;justify-content:center;min-width:40px;height:30px;padding:0 9px;
  border-radius:10px;font-size:14px;font-weight:800;font-variant-numeric:tabular-nums}
.c-pass{background:var(--pass-bg);color:var(--pass)} .c-review{background:var(--review-bg);color:var(--review)}
.c-reject{background:var(--reject-bg);color:var(--reject)}
.tag{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:999px;font-size:12px;
  background:var(--panel-2);color:var(--ink-2);white-space:nowrap}
.tag.st{background:var(--navy);color:#FFFFFF}
.tag.it{background:var(--accent-soft);color:var(--accent-ink);font-weight:600}
.nowrap{white-space:nowrap;color:var(--ink-3);font-size:12.5px;font-variant-numeric:tabular-nums}
.notedot{color:var(--accent);font-size:11px}

/* --------------------------------------------------------- applications */
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;align-items:start}
.col{background:var(--panel);border-radius:22px;padding:14px;box-shadow:var(--shadow)}
.col h3{margin:2px 4px 12px;font-size:13px;font-weight:700;color:var(--ink-2);display:flex;justify-content:space-between;
  text-transform:capitalize}
.col h3 span{color:var(--ink-3);font-weight:600}
.jc{border-radius:16px;padding:12px;margin-bottom:8px;background:var(--panel-2);cursor:pointer}
.jc:hover{background:var(--line)}
.jc b{display:block;font-size:13.5px;font-weight:650;line-height:1.35}
.jc span{display:block;color:var(--ink-3);font-size:12px;margin-top:3px}

/* ------------------------------------------------------------ countries */
.lands{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,230px),1fr));gap:12px}
.land{background:var(--panel);border:0;border-radius:24px;padding:20px 22px;text-align:left;box-shadow:var(--shadow);
  display:flex;flex-direction:column;gap:4px;cursor:pointer;transition:transform .15s ease}
.land:hover{transform:translateY(-2px)}
.land .nm{font-size:15px;color:var(--ink-2);font-weight:600}
.land .vs{font-size:44px;font-weight:900;letter-spacing:-.05em;line-height:1.05;font-variant-numeric:tabular-nums}
.land .vs.neg{color:var(--ink-3)}
.land .facts{font-size:12.5px;color:var(--ink-3)}
.land .jobs{margin-top:8px;font-size:13px;font-weight:600;color:var(--ink)}
.land .jobs b{color:var(--accent-ink)}
.land .vs.ref{font-size:26px;letter-spacing:-.03em;line-height:1.7;color:var(--ink-3)}
.note{margin:16px 2px 0;font-size:12.5px;color:var(--ink-3);line-height:1.5}

/* ------------------------------------------------------------- insights */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:14px}
.panelhead{padding:20px 22px 4px}
.panelhead h2{margin:0;font-size:15px;font-weight:700;letter-spacing:-.01em}
.panelbody{padding:10px 22px 22px}
.chart{width:100%;height:auto;display:block}
.chart .lbl{font-size:11.5px;fill:var(--ink-2)} .chart .val{font-size:11.5px;fill:var(--ink-3);font-weight:700}
.empty{color:var(--ink-3);font-size:14px;margin:6px 0}

/* --------------------------------------------------------------- drawer */
.scrim{position:fixed;inset:0;background:rgba(6,10,20,.45);opacity:0;pointer-events:none;
  transition:opacity .2s ease;z-index:40}
.scrim.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:12px;right:12px;bottom:12px;width:min(580px,calc(100vw - 24px));background:var(--bg);
  border-radius:30px;transform:translateX(calc(100% + 24px));transition:transform .26s cubic-bezier(.3,.7,.2,1);
  z-index:50;display:flex;flex-direction:column;box-shadow:0 30px 80px rgba(6,10,20,.35);overflow:hidden}
.drawer.open{transform:none}
.dhead{background:var(--navy);color:#FFFFFF;padding:22px 24px 24px;display:flex;flex-direction:column;gap:14px}
.dtop{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}
.dhead h2{margin:0 0 4px;font-size:20px;line-height:1.25;letter-spacing:-.02em}
.dhead .co{color:var(--navy-ink);font-size:14px}
.dhead .co a{color:#FF9A80}
.dscore{display:flex;align-items:baseline;gap:8px}
.dscore b{font-size:54px;font-weight:900;letter-spacing:-.05em;line-height:.9;color:#FF6B4A;font-variant-numeric:tabular-nums}
.dscore span{color:var(--navy-muted);font-size:14px}
.dhead .round{background:var(--navy-2);color:#FFFFFF;box-shadow:none;flex:none}
.dbody{overflow-y:auto;padding:16px 16px 28px;flex:1;display:flex;flex-direction:column;gap:12px}
.dsec{background:var(--panel);border-radius:22px;padding:18px 18px 16px}
.dsec h3{margin:0 0 12px;font-size:14.5px;font-weight:700;letter-spacing:-.01em}
.meta{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:13px;margin:12px 0 0}
.meta dt{color:var(--ink-3)} .meta dd{margin:0}
.bar{display:grid;grid-template-columns:96px 1fr 50px;gap:10px;align-items:center;margin-bottom:8px;font-size:13px}
.bar .track{display:block;height:8px;border-radius:4px;background:var(--line-2);overflow:hidden}
.bar .fill{display:block;height:100%;border-radius:4px;background:var(--ink);min-width:2px}
.bar .fill.low{background:var(--accent)}
.bar .num{text-align:right;color:var(--ink-2);font-weight:700;font-variant-numeric:tabular-nums;font-size:12.5px}
.hits{font-size:12px;color:var(--ink-3);margin:-4px 0 10px 106px;line-height:1.45}
.gate{background:var(--reject-bg);padding:9px 12px;border-radius:12px;font-size:13px;color:var(--ink-2);margin-bottom:7px}
.living{display:flex;justify-content:space-between;align-items:center;gap:12px}
.living .vs{font-size:34px;font-weight:900;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.living .vs.neg{color:var(--ink-3)}
.living small{display:block;font-size:12.5px;color:var(--ink-3);margin-top:2px}
.desc{font-size:13px;color:var(--ink-2);white-space:pre-wrap;max-height:260px;overflow-y:auto;line-height:1.6}
textarea{width:100%;min-height:90px;font-size:14px;padding:12px 14px;border:0;border-radius:16px;
  background:var(--panel-2);color:var(--ink);resize:vertical}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.row select{height:40px;border:0;border-radius:999px;background:var(--panel-2);padding:0 12px;font-size:13.5px}
code{background:var(--panel-2);border-radius:8px;padding:2px 7px;font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace}
.cmd{display:block;padding:10px 12px;margin-top:6px;overflow-x:auto;white-space:nowrap}
.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(120px);background:var(--ink);
  color:var(--bg);padding:12px 20px;border-radius:999px;font-size:14px;font-weight:600;z-index:60;
  transition:transform .22s ease}
.toast.show{transform:translateX(-50%)}
.readonly{background:var(--review-bg);color:var(--review);border-radius:14px;padding:10px 13px;font-size:13px}
footer{color:var(--ink-3);font-size:12px;margin-top:32px;text-align:center}

/* --------------------------------------------------------------- phone */
@media (max-width:860px){
  /* A backdrop filter makes the header the containing block of fixed children:
     the bottom tab bar would stick to the header instead of the screen. */
  .top{backdrop-filter:none;-webkit-backdrop-filter:none;background:var(--bg)}
  .top-in{padding:10px 16px;gap:10px}
  .brand small{display:none}
  .tools{margin-left:auto}
  .run .lbl{display:none}
  .run{width:40px;padding:0;justify-content:center}
  #reload{display:none}
  .tabs{position:fixed;left:10px;right:10px;bottom:10px;margin:0;justify-content:space-around;border-radius:26px;
    padding:6px;z-index:35;background:color-mix(in srgb,var(--panel) 92%,transparent);
    backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 12px 40px rgba(6,10,20,.25)}
  .tab{flex:1;flex-direction:column;gap:2px;height:52px;padding:0 4px;font-size:10.5px;border-radius:20px}
  .tab svg{width:20px;height:20px}
  .wrap{padding:8px 14px 120px}
  .runlog{padding:0 14px}
  .hero{grid-template-columns:1fr;padding:24px 22px;border-radius:28px}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .kpi:last-child:nth-child(odd){grid-column:1/-1}
  .pick{padding:18px;gap:14px}
  .score{width:56px;height:56px;font-size:23px;border-radius:17px}
  .tablewrap{max-height:none}
  th.hide,td.hide{display:none}
  .search{max-width:none;flex-basis:100%}
  .count{margin-left:0}
  .drawer{top:auto;left:0;right:0;bottom:0;width:100%;height:94vh;border-radius:30px 30px 0 0;
    transform:translateY(100%)}
  .toast{bottom:96px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = r"""
const DATA = window.__JSA__;
const I18N = window.__I18N__ || {en: {}};

/* Language: an explicit ?lang= wins, then the stored choice, then the browser,
   then English. Both languages ship inside the page, so switching is instant
   and works on a file opened from disk with no server behind it. */
const urlLang = new URLSearchParams(location.search).get('lang');
const storedLang = (() => { try { return localStorage.getItem('jsa-lang'); } catch { return null; } })();
const browserLang = (navigator.language || 'en').slice(0, 2);
let LANG = [urlLang, storedLang, browserLang, 'en'].find(l => l && I18N[l]) || 'en';
let T = I18N[LANG];

const fmt = (key, vars = {}) =>
  String(T[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');

function applyLang(lang) {
  LANG = I18N[lang] ? lang : 'en';
  T = I18N[LANG];
  try { localStorage.setItem('jsa-lang', LANG); } catch {}
  document.documentElement.lang = LANG;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const v = T[el.dataset.i18n]; if (v !== undefined) el.textContent = v;
  });
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const v = T[el.dataset.i18nHtml]; if (v !== undefined) el.innerHTML = v;
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    const v = T[el.dataset.i18nPh]; if (v !== undefined) el.placeholder = v;
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const v = T[el.dataset.i18nTitle]; if (v !== undefined) el.title = v;
  });
  renderFooter();
  renderTable();
  renderToday();
  renderCountries();
  if (!$('[data-view="pipeline"]').hidden) renderBoard();
  if (selected) openJob(selected);
}

function renderFooter() {
  const c = DATA.counts, s = DATA.stats;
  $('#foot').textContent =
    `${T.f_generated} ${DATA.generated.slice(0, 16).replace('T', ' ')} · ` +
    `${c.jobs} ${T.f_from} ${Object.keys(s.by_source || {}).length} ${T.f_sources_w} · ` +
    `${T.f_scoring}${DATA.scorer_version} · ${T.f_offline}`;
}
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Posting URLs are written by strangers; a javascript: link would run here.
const safeUrl = u => /^https?:\/\//i.test(u || '') ? u : '';
// Writes carry the token the server put in this page. A page on another origin
// cannot read it, and cannot set the header without a preflight that fails.
const WRITE = {'Content-Type': 'application/json', 'X-JSA-Token': DATA.token || ''};
const DIMS = ['title','skills','domain','location','seniority'];
const LANDS = DATA.countries || {};
const landName = code => (LANDS[code] && (LANDS[code][LANG] || LANDS[code].en)) || code;
const signed = n => (n > 0 ? '+' : n < 0 ? '\u2212' : '\u00b1') + Math.abs(n) + '%';
const euros = n => new Intl.NumberFormat(LANG === 'it' ? 'it-IT' : 'en-GB',
  {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(n);
/* The country beside a posting: what the salary is worth there, against Italy. */
function landBadge(j) {
  const c = LANDS[j.country];
  if (!c || c.vs === null || c.vs === undefined) return '';
  return `<span class="badge country">${esc(landName(j.country))} <b>${signed(c.vs)}</b></span>`;
}
let sortKey = 'score', sortAsc = false, selected = null;

/* ---------------------------------------------------------------- theme */
/* ?theme=light|dark forces the palette for this load — handy for a shared
   link or a screenshot; otherwise the stored choice, otherwise the system. */
const urlTheme = new URLSearchParams(location.search).get('theme');
const savedTheme = (() => { try { return localStorage.getItem('jsa-theme'); } catch { return null; } })();
const startTheme = ['light', 'dark'].includes(urlTheme) ? urlTheme : savedTheme;
if (startTheme) document.documentElement.dataset.theme = startTheme;
$('#lang').value = LANG;
$('#lang').onchange = e => applyLang(e.target.value);

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
  if (tab.dataset.target === 'today') renderToday();
  if (tab.dataset.target === 'countries') renderCountries();
  window.scrollTo({top: 0});
});
function showTab(name) {
  document.querySelector(`.tab[data-target="${name}"]`).click();
}

/* ------------------------------------------------------------ start here */
const TOP_N = 6;

/* Turn a score breakdown into something a person can act on in three seconds.
   The bars are fine once you know the model; this is for the moment you open
   the page. Short sentences, concrete nouns, the honest catch last. */
function plainReason(j) {
  const b = j.breakdown || {}, t = b.title, sk = b.skills, dm = b.domain, lo = b.location, se = b.seniority;
  const city = (j.location || '').split(',')[0].trim();
  const parts = [], gaps = [];

  /* Lead with title and place — the two things that decide whether you read on. */
  const titleFit = !t ? '' : t.points >= t.max ? 'exact' : t.points >= t.max * 0.6 ? 'close' : '';
  const place = lo && lo.why === 'remote' ? T.p_remote : city ? fmt('p_in', {city}) : '';
  if (titleFit === 'exact') parts.push(fmt('r_title_exact', {place: place || T.p_written}));
  else if (titleFit === 'close') parts.push(fmt('r_title_close', {place: place || T.p_desc}));
  else parts.push(fmt('r_title_none', {place: place ? ' — ' + place : ''}));

  /* Then the concrete overlap, named. */
  const skills = [...((sk && sk.must_have) || []), ...((sk && sk.nice_to_have) || [])];
  if (skills.length >= 3) {
    const shown = skills.slice(0, 4).join(', ');
    parts.push(skills.length > 4
      ? fmt('r_asks_more', {list: shown, n: skills.length - 4})
      : fmt('r_asks', {list: shown}));
  } else if (skills.length) {
    parts.push(fmt('r_overlaps', {list: skills.join(', ')}));
  } else {
    parts.push(T.r_thin);
  }

  if (dm && dm.points >= dm.max && sk && sk.points >= sk.max * 0.7)
    parts.push(T.r_squarely);

  /* The catch, if there is one. */
  if (se && se.years_required > (se.years_profile || 0) + 1)
    gaps.push(fmt('g_years', {n: se.years_required, have: se.years_profile}));
  if (se && ['senior', 'head'].includes(se.detected)) gaps.push(fmt('g_senior', {level: se.detected}));
  if (b.penalties) gaps.push(fmt('g_mentions', {list: (b.penalties.matched || []).slice(0, 2).join(', ')}));
  if (j.verdict === 'review') gaps.push(T.g_borderline);

  return {why: parts.join(' '), gaps};
}

function renderToday() {
  const pool = DATA.jobs
    .filter(j => j.verdict !== 'reject' && !j.status && !j.closed)
    .sort((a, b) => b.score - a.score);
  const picks = pool.slice(0, TOP_N);

  $('#herocount').textContent = pool.length;
  $('#todayhead').textContent = !picks.length ? T.lead_none
    : picks.length === 1 ? T.lead_one : fmt('lead_many', {n: picks.length});
  $('#todaysub').textContent = picks.length ? fmt('lead_sub', {n: pool.length}) : T.lead_sub_none;

  if (!picks.length) {
    $('#deck').innerHTML = `<div class="done"><b>${T.inbox_zero}</b>
      ${DATA.interactive ? T.inbox_live : T.inbox_static}</div>`;
    return;
  }

  $('#deck').innerHTML = picks.map(j => {
    const r = plainReason(j);
    const badges = (j.italian ? `<span class="badge it">${T.badge_italian}</span>` : '') + landBadge(j);
    return `<article class="pick" data-id="${esc(j.id)}">
      <div class="score c-${j.verdict}">${j.score}</div>
      <div>
        <h3>${esc(j.title)}</h3>
        <div class="where">${esc(j.company)} · ${esc(j.location || 'location not stated')}${
          j.remote !== 'unknown' ? ' · ' + esc(j.remote) : ''}</div>
        ${badges ? `<div class="badges">${badges}</div>` : ''}
        <p class="why">${esc(r.why)}</p>
        ${r.gaps.length ? `<p class="gap"><b>${T.catch}</b> ${esc(r.gaps.join('; '))}.</p>` : ''}
        <div class="acts">
          ${safeUrl(j.url) ? `<a class="btn pri" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${T.btn_read}</a>` : ''}
          ${DATA.interactive ? `<button class="btn" data-act="shortlisted">${T.btn_keep}</button>
                                <button class="btn" data-act="withdrawn">${T.btn_skip}</button>` : ''}
          <button class="btn" data-act="detail">${T.btn_why}</button>
        </div>
      </div>
    </article>`;
  }).join('');

  $('#deck').querySelectorAll('.pick').forEach(card => {
    card.querySelectorAll('[data-act]').forEach(btn => btn.onclick = async () => {
      const id = card.dataset.id;
      if (btn.dataset.act === 'detail') return openJob(id);
      const job = DATA.jobs.find(x => x.id === id);
      card.classList.add('gone');
      try {
        const res = await fetch('api/job/' + id, {
          method: 'POST', headers: WRITE,
          body: JSON.stringify({status: btn.dataset.act}),
        });
        if (!res.ok) throw new Error(await res.text());
        Object.assign(job, await res.json());
        toast(btn.dataset.act === 'shortlisted'
          ? T.t_kept
          : T.t_dismissed);
      } catch (err) {
        card.classList.remove('gone');
        toast(T.t_not_saved + err.message);
        return;
      }
      setTimeout(() => { renderToday(); renderTable(); }, 200);
    });
  });
}

try {
  if (localStorage.getItem('jsa-steps') === 'hidden') $('#steps').hidden = true;
} catch {}
$('#hidesteps').onclick = () => {
  $('#steps').hidden = true;
  try { localStorage.setItem('jsa-steps', 'hidden'); } catch {}
};

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
    if ($('#fItalian').checked && !j.italian) return false;
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
  $('#count').textContent = `${rows.length} ${T.of} ${DATA.jobs.length}`;
  $('#tbody').innerHTML = rows.map(j => `
    <tr data-id="${esc(j.id)}" class="${selected === j.id ? 'sel' : ''}">
      <td><span class="chip c-${j.verdict}">${j.score}</span></td>
      <td><div class="role">${esc(j.title)}</div><div class="sub">${esc(j.company)}${
        j.italian ? ` <span class="tag it">${T.badge_italian}</span>` : ''}</div></td>
      <td class="hide">${esc(j.location || '–')}${j.remote !== 'unknown' ? ` <span class="sub">${esc(j.remote)}</span>` : ''}</td>
      <td class="hide"><span class="tag">${esc(j.track)}</span></td>
      <td class="hide"><span class="tag">${esc(j.source)}</span></td>
      <td>${j.status ? `<span class="tag st">${esc(j.status)}</span>` : ''}${j.notes ? ' <span class="notedot" title="has a note">&#9679;</span>' : ''}</td>
      <td class="nowrap hide">${esc((j.first_seen || '').slice(0, 10))}</td>
    </tr>`).join('') || `<tr><td colspan="7" class="empty">${T.no_match}</td></tr>`;
  $('#tbody').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => openJob(tr.dataset.id));
}

document.querySelectorAll('th[data-sort]').forEach(th => th.onclick = () => {
  const k = th.dataset.sort;
  if (k === sortKey) sortAsc = !sortAsc; else { sortKey = k; sortAsc = k !== 'score'; }
  renderTable();
});
['q','fTrack','fVerdict','fCountry','fSource','fStatus','fItalian'].forEach(id => {
  const el = $('#' + id);
  el.addEventListener(el.tagName === 'INPUT' && el.type !== 'checkbox' ? 'input' : 'change', renderTable);
});

/* --------------------------------------------------------------- board */
function renderBoard() {
  const cols = DATA.statuses.filter(s => !['withdrawn','ghosted'].includes(s));
  $('#board').innerHTML = cols.map(s => {
    const items = DATA.jobs.filter(j => j.status === s);
    return `<div class="col"><h3>${s}<span>${items.length}</span></h3>
      ${items.map(j => `<div class="jc" data-id="${esc(j.id)}"><b>${esc(j.title)}</b>
        <span>${esc(j.company)} · ${esc(j.location || '–')}</span></div>`).join('')
      || '<div class="empty">—</div>'}</div>`;
  }).join('');
  $('#board').querySelectorAll('.jc').forEach(c => c.onclick = () => openJob(c.dataset.id));
}

/* ----------------------------------------------------------- countries */
function renderCountries() {
  const codes = Object.keys(LANDS);
  if (!codes.length) { $('#lands').innerHTML = `<div class="done">${T.countries_empty}</div>`; return; }
  const open = DATA.jobs.filter(j => !j.closed);
  const tally = code => {
    const here = open.filter(j => j.country === code);
    return {n: here.length, strong: here.filter(j => j.verdict === 'pass').length,
            it: here.filter(j => j.italian).length};
  };
  const order = codes.sort((a, b) => (LANDS[b].vs ?? 0) - (LANDS[a].vs ?? 0));
  $('#lands').innerHTML = order.map(code => {
    const c = LANDS[code], t = tally(code), ref = c.vs === null || c.vs === undefined;
    return `<button type="button" class="land" data-code="${esc(code)}">
      <span class="nm">${esc(landName(code))}</span>
      <span class="vs${ref ? ' ref' : c.vs < 0 ? ' neg' : ''}">${ref ? T.land_ref : signed(c.vs)}</span>
      <span class="facts">${T.net_avg} ${euros(c.net)} · ${T.prices_vs} ${signed(c.prices)}</span>
      <span class="jobs">${t.n ? fmt('land_jobs', {n: t.n, p: `<b>${t.strong}</b>`}) : T.land_none}</span>
    </button>`;
  }).join('');
  const year = LANDS[order[0]].year;
  $('#landnote').textContent = fmt('eurostat', {year});
  $('#lands').querySelectorAll('.land').forEach(b => b.onclick = () => {
    const sel = $('#fCountry');
    if (![...sel.options].some(o => o.value === b.dataset.code)) {
      sel.add(new Option(b.dataset.code, b.dataset.code));
    }
    sel.value = b.dataset.code;
    showTab('shortlist');
    renderTable();
  });
}

/* -------------------------------------------------------------- drawer */
function openJob(id) {
  const j = DATA.jobs.find(x => x.id === id);
  if (!j) return;
  selected = id;
  const b = j.breakdown || {};
  // Named apart from the `dim` holding each breakdown object below.
  const dimLabel = d => T['dim_' + d] || d;
  const bars = DIMS.filter(d => b[d]).map(d => {
    const dim = b[d], pct = Math.round(100 * dim.points / dim.max);
    const hits = d === 'title' ? [...(dim.strong||[]), ...(dim.good||[]), ...(dim.weak||[])]
      : d === 'skills' ? [...(dim.must_have||[]), ...(dim.nice_to_have||[])]
      : d === 'domain' ? (dim.matched || [])
      : d === 'location' ? [dim.why] : [`${dim.detected}, ${dim.years_required}y asked`];
    return `<div class="bar"><span>${dimLabel(d)}</span><span class="track"><span class="fill${pct < 40 ? ' low' : ''}" style="width:${pct}%"></span></span>
      <span class="num">${dim.points}/${dim.max}</span></div>
      ${hits.length ? `<div class="hits">${esc(hits.slice(0, 8).join(' · '))}</div>` : ''}`;
  }).join('');
  const gates = (b.gates || []).map(g => `<div class="gate"><b>${esc(g.gate)}</b> — ${esc(g.reason)}</div>`).join('');
  const pen = b.penalties ? `<div class="gate">${T.d_penalty} ${b.penalties.points} — ${esc((b.penalties.matched||[]).join(', '))}</div>` : '';

  $('#dtitle').textContent = j.title;
  $('#dscore').innerHTML = `<b>${j.score}</b><span>/ 100 · ${esc(j.verdict)}</span>`;
  const land = LANDS[j.country];
  const living = land && land.vs !== null && land.vs !== undefined ? `
    <div class="dsec"><div class="living">
      <div><h3 style="margin:0">${fmt('living_in', {country: esc(landName(j.country))})}</h3>
        <small>${T.vs_italy}</small></div>
      <span class="vs${land.vs < 0 ? ' neg' : ''}">${signed(land.vs)}</span></div>
      <dl class="meta">
        <dt>${T.net_avg}</dt><dd>${euros(land.net)}</dd>
        <dt>${T.prices_vs}</dt><dd>${signed(land.prices)}</dd>
        ${land.unemployment !== null && land.unemployment !== undefined
          ? `<dt>${T.unemp}</dt><dd>${String(land.unemployment).replace('.', LANG === 'it' ? ',' : '.')}%</dd>` : ''}
      </dl>
      <p class="note" style="margin:10px 0 0">${fmt('eurostat', {year: land.year})}</p></div>` : '';
  $('#dco').innerHTML = `${esc(j.company)} · ${esc(j.location || '–')}${safeUrl(j.url)
    ? ` · <a href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${T.open_posting}</a>` : ''}`;
  $('#dbody').innerHTML = `
    <div class="dsec"><h3>${T.why_score}</h3>${bars}${gates}${pen}
      <dl class="meta">
        <dt>${T.d_track}</dt><dd>${esc(j.track)}</dd>
        <dt>${T.d_source}</dt><dd>${esc(j.source)}</dd>
        <dt>${T.d_first_seen}</dt><dd>${esc((j.first_seen||'').slice(0,10))}</dd>
        <dt>${T.d_language}</dt><dd>${esc(b.language || '–')}</dd>
      </dl></div>
    ${living}
    <div class="dsec"><h3>${T.your_notes}</h3>
      ${DATA.interactive
        ? `<textarea id="note" placeholder="${T.notes_ph}">${esc(j.notes || '')}</textarea>
           <div class="row" style="margin-top:8px">
             <select id="dstatus">${['', ...DATA.statuses].map(s =>
               `<option value="${s}"${s === (j.status||'') ? ' selected' : ''}>${s || T.no_status}</option>`).join('')}</select>
             <button class="btn pri" id="save">${T.save}</button>
             <span id="saved" style="color:var(--ink-3);font-size:12px"></span>
           </div>`
        : `<div class="readonly">${T.readonly}</div>
           ${j.notes ? `<div class="desc" style="margin-top:9px">${esc(j.notes)}</div>` : ''}`}
    </div>
    <div class="dsec"><h3>${T.next_step}</h3>
      <code class="cmd">${esc(DATA.command || 'jsa')} apply ${esc(j.id.slice(0,8))}</code>
      <p class="note" style="margin:8px 2px 10px">${T.apply_hint}</p>
      <button class="btn" id="copy">${T.copy_id}</button></div>
    ${j.description ? `<div class="dsec"><h3>${T.posting}</h3><div class="desc">${esc(j.description)}</div></div>` : ''}`;

  $('#copy').onclick = async () => {
    try { await navigator.clipboard.writeText(j.id); toast(T.t_copied); }
    catch { toast(T.t_copy_failed); }
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
      method: 'POST', headers: WRITE,
      body: JSON.stringify({status: status || null, notes}),
    });
    if (!res.ok) throw new Error(await res.text());
    const updated = await res.json();
    Object.assign(j, updated);
    toast(T.t_saved);
    renderTable();
  } catch (err) {
    toast(T.t_not_saved + err.message);
  } finally { $('#save').disabled = false; }
}

/* ------------------------------------------------------------------ run */
$('#reload').onclick = () => location.reload();
const runBtn = $('#run'), runLog = $('#runlog'), runOut = $('#runout'), runState = $('#runstate');
const RUN_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg>';

function paintRun(s) {
  runLog.hidden = false;
  runOut.textContent = s.lines.join('\n');
  runOut.scrollTop = runOut.scrollHeight;
  if (s.running) {
    runState.textContent = T.run_running;
    runBtn.disabled = true;
    runBtn.innerHTML = '<span class="spin"></span><span class="lbl">' + T.running + '</span>';
  } else {
    runBtn.disabled = false;
    runBtn.innerHTML = RUN_ICON + '<span class="lbl" data-i18n="run">' + T.run + '</span>';
    if (s.returncode === 0) {
      runState.innerHTML = T.run_done;
      $('#rl').onclick = e => { e.preventDefault(); location.reload(); };
    } else if (s.returncode !== null) {
      runState.textContent = fmt('run_failed', {code: s.returncode});
    }
  }
  return s.running;
}

let poll;
async function watchRun() {
  clearInterval(poll);
  poll = setInterval(async () => {
    try {
      const s = await (await fetch('api/run')).json();
      if (!paintRun(s)) clearInterval(poll);
    } catch { clearInterval(poll); }
  }, 1200);
}

if (DATA.interactive) {
  runBtn.onclick = async () => {
    runBtn.disabled = true;
    runBtn.innerHTML = '<span class="spin"></span><span class="lbl">' + T.starting + '</span>';
    try {
      const res = await fetch('api/run', {method: 'POST', headers: WRITE});
      if (res.status === 409) { toast(T.t_in_progress); }
      else if (!res.ok) throw new Error(await res.text());
      paintRun(await res.json());
      watchRun();
    } catch (err) {
      toast(T.t_cannot_start + err.message);
      runBtn.disabled = false; runBtn.innerHTML = RUN_ICON + '<span class="lbl" data-i18n="run">' + T.run + '</span>';
    }
  };
  // A run started before this page loaded (or in another tab) keeps streaming.
  fetch('api/run').then(r => r.json()).then(s => { if (s.running) { paintRun(s); watchRun(); } }).catch(() => {});
}

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* One entry point: translating also re-renders everything that carries text. */
applyLang(LANG);
"""


ASSETS = Path(__file__).resolve().parent / "assets"
_LATIN = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
          "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")
_LATIN_EXT = ("U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,"
              "U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C4,U+2113,U+2C60-2C7F,U+A720-A7FF")


@functools.lru_cache(maxsize=1)
def font_css() -> str:
    """Inter, inlined. The page is often a file opened from disk, and its policy
    allows no network: the typeface has to travel inside it (SIL OFL, assets/OFL.txt).
    Without the files the page falls back to the system font, unchanged otherwise."""
    faces = []
    for name, ranges in (("inter-latin.woff2", _LATIN), ("inter-latin-ext.woff2", _LATIN_EXT)):
        path = ASSETS / name
        if not path.exists():
            continue
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append("@font-face{font-family:Inter;font-style:normal;font-weight:400 900;font-display:swap;"
                     f"src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{ranges}}}")
    return "".join(faces)


def _options(values: list[str], label: str, key: str) -> str:
    opts = "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in values)
    return f'<option value="" data-i18n="{key}">{html.escape(label)}</option>{opts}'


def script_json(value: Any) -> str:
    """JSON that is safe to place inside a <script> element.

    `json.dumps` leaves "</script>" alone, and the HTML parser ends the element
    there whatever the JavaScript thinks: a posting titled
    `</script><script>...` would run in the dashboard. Escaping <, > and & as
    JSON unicode escapes keeps the value identical once parsed. U+2028/9 are
    line terminators to older JavaScript engines.
    """
    text = json.dumps(value, ensure_ascii=False)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(char, escaped)
    return text


def content_security_policy(nonce: str) -> str:
    """What the page may do: run its own two scripts, talk to its own server.

    With scripts pinned to a nonce, a `javascript:` link or an injected
    <script> is refused by the browser even if an escaping bug lets one through.
    """
    return ("default-src 'none'; "
            f"script-src 'nonce-{nonce}'; "
            "style-src 'unsafe-inline'; "
            "img-src data:; "
            "font-src data:; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'")


def render_page(data: dict[str, Any], charts: dict[str, str], *, nonce: str | None = None) -> str:
    """Full HTML document. `charts` holds pre-rendered inline SVG."""
    nonce = nonce or secrets.token_urlsafe(16)
    jobs = data["jobs"]
    counts, stats = data["counts"], data["stats"]
    kpis = [
        ("kpi_seen", "postings seen", counts["jobs"]),
        ("kpi_cleared", "cleared gates", len([j for j in jobs if j["verdict"] != "reject"])),
        ("kpi_tracked", "in tracker", counts["applications"]),
        ("kpi_submitted", "submitted", stats["submitted"]),
        ("kpi_replies", "replies", stats["responded"]),
        ("kpi_rate", "response rate",
         f"{stats['response_rate']:.0%}" if stats["response_rate"] is not None else "–"),
        ("kpi_median", "median reply",
         f"{stats['median_response_days']}d" if stats["median_response_days"] is not None else "–"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="n">{html.escape(str(v))}</div>'
        f'<div class="k" data-i18n="{key}">{html.escape(k)}</div></div>'
        for key, k, v in kpis
    )
    tracks = sorted({j["track"] for j in jobs})
    countries = sorted({j["country"] or "–" for j in jobs})
    sources = sorted({j["source"] for j in jobs})
    live = ('<span class="livedot"></span><span data-i18n="live">live</span>'
            if data["interactive"]
            else '<span class="livedot off"></span><span data-i18n="static">static export</span>')
    lang_options = "".join(
        f'<option value="{code}">{name}</option>' for code, name in LANGUAGES.items()
    )
    run_disabled = "" if data["interactive"] else " disabled"
    run_title = "" if data["interactive"] else ' data-i18n-title="run_title_static"'

    icon = {
        "today": '<path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>'
                 '<circle cx="12" cy="12" r="4"/>',
        "shortlist": '<rect x="3" y="7" width="18" height="13" rx="3"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/>',
        "pipeline": '<path d="M4 5h16M4 12h10M4 19h6"/>',
        "countries": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
        "insights": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    }

    def tab(target: str, key: str, label: str, selected: bool = False) -> str:
        return (f'<button class="tab" role="tab" aria-selected="{str(selected).lower()}" data-target="{target}">'
                f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                f'stroke-linejoin="round" aria-hidden="true">{icon[target]}</svg>'
                f'<span data-i18n="{key}">{label}</span></button>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{content_security_policy(nonce)}">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#F2F4F7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0B1220" media="(prefers-color-scheme: dark)">
<title>Job pipeline · job-search-agent</title>
<style>{font_css()}{CSS}</style></head><body>

<header class="top"><div class="top-in">
  <div class="brand"><i></i><div><b data-i18n="brand">Job pipeline</b><small>{live}</small></div></div>
  <nav class="tabs" role="tablist" aria-label="Views">
    {tab("today", "tab_today", "Start here", True)}
    {tab("shortlist", "tab_all", "All postings")}
    {tab("pipeline", "tab_pipeline", "Pipeline")}
    {tab("countries", "tab_countries", "Countries")}
    {tab("insights", "tab_insights", "Insights")}
  </nav>
  <div class="tools">
    <button class="run" id="run"{run_disabled}{run_title}><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg><span class="lbl" data-i18n="run">Run pipeline</span></button>
    <button class="round" id="reload" data-i18n-title="refresh" title="Refresh" aria-label="Refresh"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg></button>
    <select class="langsel" id="lang" aria-label="Language">{lang_options}</select>
    <button class="round" id="theme" data-i18n-title="theme" title="Theme" aria-label="Theme"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16z" fill="currentColor"/></svg></button>
  </div>
</div></header>

<div class="runlog" id="runlog" hidden><div class="inner">
  <h4><span data-i18n="run_head">Pipeline run</span><span id="runstate"></span></h4>
  <pre id="runout"></pre>
</div></div>

<main class="wrap">
  <section data-view="today">
    <div class="hero">
      <div class="now"><b id="herocount">0</b><span data-i18n="hero_label">postings still to triage</span></div>
      <div class="kpis">{kpi_html}</div>
    </div>
    <div class="steps" id="steps">
      <button class="dismiss" id="hidesteps" data-i18n-title="hide" aria-label="Hide">&times;</button>
      <div class="step"><i>1</i><b data-i18n="step1_t">Triage</b><span data-i18n-html="step1_b">Read the cards below. Keep the ones worth an
        hour, dismiss the rest. That is the whole job of this screen.</span></div>
      <div class="step"><i>2</i><b data-i18n="step2_t">Prepare</b><span data-i18n-html="step2_b">For anything you keep, run
        <code>jsa apply &lt;id&gt;</code>: CV, letter and packet in one go.</span></div>
      <div class="step"><i>3</i><b data-i18n="step3_t">Send, then log it</b><span data-i18n-html="step3_b">You press send. Then mark it
        submitted here, so the Pipeline tab can tell you what actually works.</span></div>
    </div>
    <div class="lead"><h2 id="todayhead"></h2><span id="todaysub"></span></div>
    <div class="deck" id="deck"></div>
  </section>

  <section data-view="shortlist" hidden>
    <div class="filters">
      <div class="search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input id="q" data-i18n-ph="search" autocomplete="off" aria-label="Search">
      </div>
      <label class="toggle"><input type="checkbox" id="fItalian"><span data-i18n="f_italian">Italian only</span></label>
      <select id="fCountry" aria-label="Country">{_options(countries, "Anywhere", "f_countries")}</select>
      <select id="fVerdict" aria-label="Verdict"><option value="" data-i18n="f_verdicts">All verdicts</option><option value="pass">pass</option>
        <option value="review">review</option><option value="reject">reject</option></select>
      <select id="fTrack" aria-label="Track">{_options(tracks, "All tracks", "f_tracks")}</select>
      <select id="fSource" aria-label="Source">{_options(sources, "All sources", "f_sources")}</select>
      <select id="fStatus" aria-label="Status">{_options(STATUSES, "Any status", "f_statuses")}<option value="__none" data-i18n="f_untracked">Not yet tracked</option></select>
      <span class="count" id="count"></span>
    </div>
    <div class="card"><div class="tablewrap"><table>
      <thead><tr>
        <th data-sort="score" data-i18n="th_fit">Fit</th><th data-sort="title" data-i18n="th_role">Role</th>
        <th data-sort="location" class="hide" data-i18n="th_location">Location</th><th data-sort="track" class="hide" data-i18n="th_track">Track</th>
        <th data-sort="source" class="hide" data-i18n="th_source">Source</th><th data-sort="status" data-i18n="th_status">Status</th>
        <th data-sort="first_seen" class="hide" data-i18n="th_seen">Seen</th>
      </tr></thead><tbody id="tbody"></tbody>
    </table></div></div>
  </section>

  <section data-view="pipeline" hidden><div class="board" id="board"></div></section>

  <section data-view="countries" hidden>
    <div class="lead"><h2 data-i18n="countries_head">Where your salary goes further</h2>
      <span data-i18n="countries_sub">Purchasing power against Italy, with your open postings in each country.</span></div>
    <div class="lands" id="lands"></div>
    <p class="note" id="landnote"></p>
  </section>

  <section data-view="insights" hidden>
    <div class="grid">
      <div class="card"><div class="panelhead"><h2 data-i18n="panel_funnel">Application funnel</h2></div>
        <div class="panelbody">{charts['funnel']}</div></div>
      <div class="card"><div class="panelhead"><h2 data-i18n="panel_tracks">Replies by positioning track</h2></div>
        <div class="panelbody">{charts['tracks']}</div></div>
      <div class="card"><div class="panelhead"><h2 data-i18n="panel_sources">Where postings come from</h2></div>
        <div class="panelbody">{charts['sources']}</div></div>
      <div class="card"><div class="panelhead"><h2 data-i18n="panel_scores">Fit score, cleared postings</h2></div>
        <div class="panelbody">{charts['scores']}</div></div>
    </div>
  </section>

  <footer id="foot"></footer>
</main>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-label="Job detail">
  <div class="dhead">
    <div class="dtop">
      <div class="dscore" id="dscore"></div>
      <button class="round" id="dclose" data-i18n-title="close" title="Close" aria-label="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>
    </div>
    <div><h2 id="dtitle"></h2><div class="co" id="dco"></div></div>
  </div>
  <div class="dbody" id="dbody"></div>
</aside>
<div class="toast" id="toast" role="status"></div>

<script nonce="{nonce}">window.__JSA__ = {script_json(data)};
window.__I18N__ = {script_json(bundle())};</script>
<script nonce="{nonce}">{JS}</script>
</body></html>"""
