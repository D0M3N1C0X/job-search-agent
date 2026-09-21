#!/usr/bin/env python3
"""Build the public site in docs/ — a landing page and a live demo.

GitHub Pages serves docs/ on the main branch, so the whole site is two files
that regenerate from one command. The demo is the real dashboard on synthetic
data: not a screenshot, not a mock. Anyone can open it, filter it, read a score
breakdown and switch language, without installing anything.

    python3 tools/build_site.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jsa.dashboard import build_dashboard  # noqa: E402
from jsa.demo import build  # noqa: E402
from jsa.store import Store  # noqa: E402

DOCS = ROOT / "docs"
REPO = "https://github.com/D0M3N1C0X/job-search-agent"

# The landing page carries its own strings: it is one page with one message and
# does not need the dashboard's 116 keys.
COPY = {
    "en": {
        "lang_name": "English",
        "tagline": "A job search that runs as a pipeline",
        "lede": "Job boards block scrapers. So this reads the APIs companies publish "
                "themselves — then scores every posting against your profile with rules "
                "you can read, writes the CV and cover letter, and measures which "
                "positioning actually gets replies.",
        "cta": "Open the live demo",
        "cta_note": "Real dashboard, invented data. Nothing to install.",
        "repo": "Code on GitHub",
        "facts_h": "What it is",
        "facts": [
            ("Seven ATS boards, no key",
             "Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable and Personio "
             "serve the same JSON their own careers pages use. No login, no scraping, "
             "nothing that breaks silently next week."),
            ("Scoring you can argue with",
             "Fit is a pure function of job, profile and positioning track — the same "
             "posting always scores the same, and the breakdown names the words that "
             "earned each point. No model deciding your career in private."),
            ("Documents that cannot invent",
             "CVs and cover letters as .docx. A tailoring pass may reorder and select, "
             "but every line is checked against your profile character for character, "
             "so nothing can appear that you did not write."),
            ("Zero dependencies",
             "Python 3.10 and the standard library. No pip install, no LaTeX, no "
             "headless browser. It will still run in three years on a locked-down "
             "laptop."),
        ],
        "how_h": "How you use it",
        "how": [
            ("Import your CV", "jsa import ~/cv.pdf",
             "Reads .docx, .pdf or text and fills the profile in. Or answer questions "
             "instead with jsa setup."),
            ("Run the pipeline", "jsa run",
             "Fetches, deduplicates, scores and opens the shortlist. Roughly five "
             "minutes across a watchlist of employers."),
            ("Work the shortlist", "jsa serve",
             "The dashboard opens on the handful worth your next hour, each with the "
             "reason in plain language and the catch stated honestly."),
        ],
        "start_h": "Start",
        "start_note": "macOS, Linux and Windows. `jsa install` also puts it in your Dock.",
        "honest_h": "What it will not do",
        "honest": "It does not submit applications. Applicant tracking systems expose no "
                  "public endpoint for that, and a form is a signature: the tool prepares "
                  "the packet — documents, standard answers, a checklist — and you press "
                  "send.",
        "foot": "MIT licence · built by Domenico Perroni",
    },
    "it": {
        "lang_name": "Italiano",
        "tagline": "La ricerca di lavoro come una pipeline",
        "lede": "I portali bloccano chi li raschia. Questo legge invece le API che le "
                "aziende pubblicano da sole, assegna a ogni offerta un punteggio secondo "
                "regole leggibili, scrive CV e lettera di presentazione, e misura quale "
                "posizionamento ottiene davvero risposte.",
        "cta": "Apri la demo",
        "cta_note": "Dashboard vera, dati inventati. Niente da installare.",
        "repo": "Il codice su GitHub",
        "facts_h": "Cos'è",
        "facts": [
            ("Sette portali ATS, senza chiavi",
             "Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable e Personio "
             "servono lo stesso JSON che usano le loro pagine lavora-con-noi. Nessun "
             "login, nessuno scraping, niente che si rompa in silenzio la settimana dopo."),
            ("Un punteggio con cui puoi discutere",
             "Il fit è una funzione pura di offerta, profilo e binario di posizionamento: "
             "la stessa offerta dà sempre lo stesso numero, e la scomposizione dice quali "
             "parole hanno fatto punti. Nessun modello che decide in privato."),
            ("Documenti che non possono inventare",
             "CV e lettere in .docx. L'adattamento può riordinare e selezionare, ma ogni "
             "riga viene confrontata carattere per carattere con il tuo profilo: non può "
             "comparire nulla che tu non abbia scritto."),
            ("Zero dipendenze",
             "Python 3.10 e la libreria standard. Nessun pip install, niente LaTeX, "
             "nessun browser headless. Funzionerà ancora fra tre anni su un portatile "
             "aziendale bloccato."),
        ],
        "how_h": "Come si usa",
        "how": [
            ("Importa il tuo CV", "jsa import ~/cv.pdf",
             "Legge .docx, .pdf o testo e compila il profilo. Oppure rispondi a delle "
             "domande con jsa setup."),
            ("Avvia la pipeline", "jsa run",
             "Scarica, deduplica, assegna i punteggi e apre la lista. Circa cinque minuti "
             "su una watchlist di aziende."),
            ("Lavora la lista", "jsa serve",
             "La dashboard si apre sulle poche offerte che valgono la tua prossima ora, "
             "con il motivo in parole e il rovescio detto onestamente."),
        ],
        "start_h": "Per iniziare",
        "start_note": "macOS, Linux e Windows. `jsa install` la mette anche nel Dock.",
        "honest_h": "Cosa non fa",
        "honest": "Non invia le candidature. Gli ATS non espongono endpoint pubblici per "
                  "farlo, e un modulo è una firma: lo strumento prepara il pacchetto — "
                  "documenti, risposte standard, lista di controllo — e l'invio lo fai tu.",
        "foot": "Licenza MIT · costruito da Domenico Perroni",
    },
}

INSTALL = """git clone https://github.com/D0M3N1C0X/job-search-agent
cd job-search-agent
python3 -m jsa demo"""

CSS = """
:root{color-scheme:light dark;--bg:#0f1115;--panel:#171a21;--panel2:#1c2029;--ink:#e8eaee;
 --ink2:#a2a9b6;--ink3:#767d8b;--line:#262b35;--accent:#5b9cff;--accent2:#1f6feb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased;
 background-image:radial-gradient(900px 500px at 82% -12%,rgba(31,111,235,.22),transparent 62%),
  radial-gradient(640px 420px at 2% 104%,rgba(26,127,75,.14),transparent 60%)}
.wrap{max-width:900px;margin:0 auto;padding:0 22px 72px}
header{display:flex;align-items:center;gap:14px;padding:26px 0 8px;flex-wrap:wrap}
.mark{width:40px;height:40px;border-radius:11px;background:var(--accent2);display:flex;
 flex-direction:column;justify-content:center;gap:4px;padding:0 9px;flex:none}
.mark i{display:block;height:5px;border-radius:3px;background:#fff}
.mark i:nth-child(1){width:22px}.mark i:nth-child(2){width:15px}.mark i:nth-child(3){width:9px}
.name{font-weight:600;letter-spacing:-.01em}
.spacer{flex:1}
select,a.ghost{background:var(--panel2);border:1px solid var(--line);color:var(--ink2);
 border-radius:9px;padding:7px 12px;font:inherit;font-size:13.5px;text-decoration:none}
a.ghost:hover,select:hover{border-color:var(--accent);color:var(--accent)}
h1{font-size:clamp(30px,5vw,46px);line-height:1.1;letter-spacing:-.03em;margin:26px 0 14px}
.lede{font-size:clamp(16px,2.2vw,19px);color:var(--ink2);max-width:60ch;margin:0 0 26px}
.cta{display:inline-flex;align-items:center;gap:10px;background:var(--accent2);color:#fff;
 text-decoration:none;font-weight:600;padding:14px 24px;border-radius:12px;font-size:16px}
.cta:hover{filter:brightness(1.1)}
.ctanote{color:var(--ink3);font-size:13.5px;margin:10px 0 0}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink3);
 margin:46px 0 16px;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:18px 20px}
.card b{display:block;font-size:15.5px;margin-bottom:6px;letter-spacing:-.01em}
.card p{margin:0;color:var(--ink2);font-size:14.5px;line-height:1.6}
ol{list-style:none;counter-reset:s;padding:0;margin:0;display:grid;gap:12px}
ol li{counter-increment:s;background:var(--panel);border:1px solid var(--line);border-radius:13px;
 padding:16px 20px 16px 58px;position:relative}
ol li::before{content:counter(s);position:absolute;left:18px;top:17px;width:24px;height:24px;
 border-radius:50%;background:var(--panel2);border:1px solid var(--line);color:var(--ink3);
 display:grid;place-items:center;font-size:12px;font-weight:700}
ol b{display:block;font-size:15px;margin-bottom:3px}
ol code{display:inline-block;margin:2px 0 6px}
ol p{margin:0;color:var(--ink2);font-size:14.5px}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
code{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:2px 7px;
 font-size:13.5px;color:var(--accent)}
pre{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:18px 20px;
 overflow-x:auto;font-size:14px;color:var(--ink);margin:0}
.note{color:var(--ink3);font-size:13.5px;margin:10px 0 0}
.honest{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
 border-radius:0 13px 13px 0;padding:18px 22px;color:var(--ink2);font-size:14.5px}
footer{color:var(--ink3);font-size:13px;margin-top:52px;padding-top:20px;border-top:1px solid var(--line)}
a{color:var(--accent)}
@media(max-width:640px){header{padding-top:18px}.wrap{padding-bottom:48px}}
"""


def page(lang: str) -> str:
    c = COPY[lang]
    facts = "".join(f"<div class='card'><b>{t}</b><p>{p}</p></div>" for t, p in c["facts"])
    how = "".join(f"<li><b>{t}</b><code>{cmd}</code><p>{p}</p></li>" for t, cmd, p in c["how"])
    options = "".join(
        f"<option value='{code}'{' selected' if code == lang else ''}>{COPY[code]['lang_name']}</option>"
        for code in COPY
    )
    other = "index.en.html" if lang == "it" else "index.html"
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>job-search-agent — {c['tagline']}</title>
<meta name="description" content="{c['lede'][:155]}">
<meta property="og:title" content="job-search-agent — {c['tagline']}">
<meta property="og:description" content="{c['lede'][:155]}">
<meta property="og:image" content="{REPO.replace('github.com', 'raw.githubusercontent.com')}/main/docs/img/social-preview.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style></head><body><div class="wrap">

<header>
  <div class="mark"><i></i><i></i><i></i></div>
  <div class="name">job-search-agent</div>
  <div class="spacer"></div>
  <select id="lang" aria-label="Language" data-other="{other}">{options}</select>
  <a class="ghost" href="{REPO}">{c['repo']}</a>
</header>

<h1>{c['tagline']}</h1>
<p class="lede">{c['lede']}</p>
<a class="cta" href="demo/">{c['cta']} →</a>
<p class="ctanote">{c['cta_note']}</p>

<h2>{c['facts_h']}</h2>
<div class="grid">{facts}</div>

<h2>{c['how_h']}</h2>
<ol>{how}</ol>

<h2>{c['start_h']}</h2>
<pre>{INSTALL}</pre>
<p class="note">{c['start_note']}</p>

<h2>{c['honest_h']}</h2>
<div class="honest">{c['honest']}</div>

<footer>{c['foot']} · <a href="{REPO}">{REPO.replace('https://', '')}</a></footer>
</div>
<script>
  const sel = document.getElementById('lang');
  sel.onchange = e => {{ location.href = e.target.value === 'it' ? 'index.html' : 'index.en.html'; }};
</script>
</body></html>"""


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(page("it"), encoding="utf-8")
    (DOCS / "index.en.html").write_text(page("en"), encoding="utf-8")

    demo = DOCS / "demo"
    demo.mkdir(exist_ok=True)
    cfg = build(count=90)
    with Store(cfg.db_path) as store:
        build_dashboard(store, cfg, demo / "index.html")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    for path in (DOCS / "index.html", DOCS / "index.en.html", demo / "index.html"):
        print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")
    print("\nGitHub Pages: Settings → Pages → Source: main / docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
