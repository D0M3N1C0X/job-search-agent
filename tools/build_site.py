#!/usr/bin/env python3
"""Build the public site in docs/ — a landing page and a live demo.

GitHub Pages serves docs/ on the main branch. The landing page is generated, not
written: every number on it comes from catalogue/companies.json and
relocation/countries.json at build time, so it can never drift from the data
it describes. The demo is the real dashboard on synthetic data.

    python3 tools/build_site.py
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jsa.dashboard import build_dashboard  # noqa: E402
from jsa.demo import build  # noqa: E402
from jsa.store import Store  # noqa: E402

DOCS = ROOT / "docs"
REPO = "https://github.com/D0M3N1C0X/job-search-agent"
NAME = "job-search-agent"  # until the product has its name
DEFAULT_COUNTRY = "DE"

INSTALL = """git clone https://github.com/D0M3N1C0X/job-search-agent
cd job-search-agent
python3 -m jsa demo"""

COUNTRY_EN = {
    "IT": "Italy", "DE": "Germany", "AT": "Austria", "CH": "Switzerland", "ES": "Spain",
    "PT": "Portugal", "FR": "France", "BE": "Belgium", "NL": "Netherlands", "LU": "Luxembourg",
    "PL": "Poland", "CZ": "Czechia", "SK": "Slovakia", "HU": "Hungary", "RO": "Romania",
    "BG": "Bulgaria", "HR": "Croatia", "SI": "Slovenia", "EE": "Estonia", "LV": "Latvia",
    "LT": "Lithuania",
}
MONTHS = {
    "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
    "en": "January February March April May June July August September October November December",
}

COPY = {
    "it": {
        "lang_name": "Italiano",
        "title": "Lavoro all'estero, con i conti fatti",
        "description": "Offerte di lavoro da {companies} aziende europee e, per ogni paese, quanto vale "
                       "davvero lo stipendio rispetto all'Italia. Open source.",
        "nav_countries": "Paesi", "nav_italian": "Con l'italiano", "nav_code": "Codice",
        "h1": "Quanto vale il tuo stipendio a {city}?",
        "lede": "Prima di candidarti, sappi dove stai andando. Offerte vere da {companies} aziende "
                "europee e, per ogni paese, i conti fatti con i dati ufficiali.",
        "cta": "Apri la demo", "cta2": "Confronta i paesi",
        "from": "Da Italia", "to": "a",
        "card_line": "di potere d'acquisto per lo stipendio netto medio, già tolti i prezzi.",
        "card_line_neg": "di potere d'acquisto per lo stipendio netto medio, già tolti i prezzi.",
        "net_it": "Netto Italia", "net_there": "Netto {cc}", "prices": "Prezzi",
        "card_source": "Eurostat {year} · dati nazionali · lavoratore single con retribuzione media",
        "choose": "Scegli il paese",
        "italian_lead": "offerte in Europa citano l'italiano.",
        "italian_body": "È la lingua che ti distingue. Le cerchiamo nelle bacheche di {companies} "
                        "aziende verificate, e te le mettiamo davanti per prime.",
        "italian_note": "Offerte che citano l'italiano per azienda, catalogo del {date}.",
        "countries_h": "Ogni paese, a parità di prezzi.",
        "countries_note": "Potere d'acquisto dello stipendio netto medio rispetto all'Italia, {year}. "
                          "Fonte: Eurostat. Lo stipendio non è tutto: {low} ha la disoccupazione "
                          "più bassa, il {low_rate}.",
        "how_h": "Dal CV alla candidatura. Senza moduli.",
        "how": [
            ("Importa il CV", "PDF o Word: il profilo si compila da solo e lo controlli tu."),
            ("Scegli paesi e ruoli", "Le offerte arrivano con un punteggio spiegato, voce per voce."),
            ("Prepara la candidatura", "CV in PDF su misura per ogni offerta, senza una riga inventata."),
        ],
        "phone_h": "Paesi", "phone_sub": "rispetto all'Italia",
        "trust": [
            ("Niente invenzioni nel CV",
             "Ogni riga del CV che prepariamo esiste già nel tuo profilo. Un controllo automatico "
             "scarta tutto il resto."),
            ("I tuoi dati restano tuoi",
             "Oggi lo strumento gira sul tuo computer: CV e candidature non lasciano la tua macchina."),
            ("Codice aperto",
             "Il motore è pubblico su GitHub: puoi leggere come calcoliamo ogni punteggio e da dove "
             "viene ogni numero."),
        ],
        "soon": "In arrivo: la versione online, senza installare nulla.",
        "final_h": "Prima i numeri. Poi la valigia.",
        "final_p": "Gratis e open source. Gira su macOS, Windows e Linux.",
        "start_h": "Per iniziare",
        "foot": "Licenza MIT · costruito da Domenico Perroni",
        "foot_sources": "Paesi: Eurostat · Offerte: bacheche pubbliche delle aziende",
    },
    "en": {
        "lang_name": "English",
        "title": "Work abroad, with the numbers done",
        "description": "Job postings from {companies} European employers and, for every country, what "
                       "a salary is really worth compared with Italy. Open source.",
        "nav_countries": "Countries", "nav_italian": "Italian-speaking", "nav_code": "Code",
        "h1": "What is your salary worth in {city}?",
        "lede": "Know where you are going before you apply. Real postings from {companies} European "
                "employers and, for every country, the sums done with official data.",
        "cta": "Open the demo", "cta2": "Compare countries",
        "from": "From Italy", "to": "to",
        "card_line": "purchasing power for the average net salary, prices already accounted for.",
        "card_line_neg": "purchasing power for the average net salary, prices already accounted for.",
        "net_it": "Net Italy", "net_there": "Net {cc}", "prices": "Prices",
        "card_source": "Eurostat {year} · national figures · single worker on the average wage",
        "choose": "Choose a country",
        "italian_lead": "postings across Europe mention Italian.",
        "italian_body": "The language that sets you apart. We look for it on the boards of {companies} "
                        "verified employers and put those roles first.",
        "italian_note": "Postings mentioning Italian, by employer, catalogue of {date}.",
        "countries_h": "Every country, at equal prices.",
        "countries_note": "Purchasing power of the average net salary compared with Italy, {year}. "
                          "Source: Eurostat. Pay is not everything: {low} has the lowest "
                          "unemployment, {low_rate}.",
        "how_h": "From CV to application. No forms.",
        "how": [
            ("Import your CV", "PDF or Word: the profile fills itself in, and you check it."),
            ("Choose countries and roles", "Postings arrive with a score explained line by line."),
            ("Prepare the application", "A tailored CV as PDF for each posting, with nothing invented."),
        ],
        "phone_h": "Countries", "phone_sub": "compared with Italy",
        "trust": [
            ("Nothing invented in your CV",
             "Every line of the CV we prepare already exists in your profile. An automatic check "
             "drops everything else."),
            ("Your data stays yours",
             "Today the tool runs on your computer: your CV and applications never leave it."),
            ("Open code",
             "The engine is public on GitHub: read how every score is computed and where every "
             "number comes from."),
        ],
        "soon": "Coming: the online version, nothing to install.",
        "final_h": "Numbers first. Then the suitcase.",
        "final_p": "Free and open source. Runs on macOS, Windows and Linux.",
        "start_h": "Get started",
        "foot": "MIT licence · built by Domenico Perroni",
        "foot_sources": "Countries: Eurostat · Postings: employers' public job boards",
    },
}

# The city the headline asks about. The figures under it are national.
CITY = {
    "it": {"DE": "Berlino", "AT": "Vienna", "CH": "Zurigo", "ES": "Madrid", "PT": "Lisbona",
           "FR": "Parigi", "BE": "Bruxelles", "NL": "Amsterdam", "LU": "Lussemburgo",
           "PL": "Varsavia", "CZ": "Praga", "SK": "Bratislava", "HU": "Budapest", "RO": "Bucarest",
           "BG": "Sofia", "HR": "Zagabria", "SI": "Lubiana", "EE": "Tallinn", "LV": "Riga",
           "LT": "Vilnius"},
    "en": {"DE": "Berlin", "AT": "Vienna", "CH": "Zurich", "ES": "Madrid", "PT": "Lisbon",
           "FR": "Paris", "BE": "Brussels", "NL": "Amsterdam", "LU": "Luxembourg",
           "PL": "Warsaw", "CZ": "Prague", "SK": "Bratislava", "HU": "Budapest", "RO": "Bucharest",
           "BG": "Sofia", "HR": "Zagreb", "SI": "Ljubljana", "EE": "Tallinn", "LV": "Riga",
           "LT": "Vilnius"},
}

CSS = """
:root{color-scheme:light;--ink:#0B1220;--body:#3A4558;--muted:#5B6474;--soft:#F6F7FA;--card:#FFFFFF;
 --line:#E2E5EC;--coral:#FF6B4A;--coral-ink:#C2401F;--night:#0B1220;--night2:#16203A;--night3:#1E2A47;
 --night-ink:#B8C1D3;--night-muted:#8A94A8}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--soft);color:var(--ink);
 font-family:Inter,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01";line-height:1.5}
a{color:inherit}
.wrap{max-width:1200px;margin:0 auto;padding:0 clamp(20px,5vw,48px)}
.pill{display:inline-flex;align-items:center;height:40px;padding:0 16px;border-radius:999px;font-size:14px;
 font-weight:600;text-decoration:none;color:var(--body);border:0;background:transparent;font-family:inherit}
.pill:hover{color:var(--ink);background:#EBEEF3}
.btn{display:inline-flex;align-items:center;justify-content:center;height:54px;padding:0 26px;border-radius:999px;
 font-size:16px;font-weight:700;text-decoration:none;transition:transform .15s ease,filter .15s ease}
.btn:hover{transform:translateY(-1px);filter:brightness(1.04)}
.btn-coral{background:var(--coral);color:var(--ink)}
.btn-light{background:var(--card);color:var(--ink);border:1px solid #DCE1EA}
.btn-night{background:var(--night);color:#fff}
:focus-visible{outline:3px solid var(--coral);outline-offset:3px}

header.top{display:flex;align-items:center;justify-content:space-between;height:76px;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:8px;white-space:nowrap;text-decoration:none;font-weight:800;font-size:17px;letter-spacing:-.02em}
.brand i{width:10px;height:10px;border-radius:50%;background:var(--coral)}
nav.links{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.lang{height:40px;border-radius:999px;border:1px solid #DCE1EA;background:var(--card);padding:0 12px;
 font-family:inherit;font-size:13px;font-weight:600;color:var(--body)}

.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:48px;align-items:center;
 padding-top:64px;padding-bottom:104px}
.hero h1{margin:0;font-size:clamp(42px,6.2vw,80px);line-height:1;letter-spacing:-.05em;font-weight:900}
.lede{margin:24px 0 0;font-size:clamp(17px,1.6vw,20px);line-height:1.55;color:var(--body);max-width:520px}
.ctas{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}

.calc{background:var(--night);color:#fff;border-radius:36px;padding:clamp(24px,3.4vw,36px);display:flex;flex-direction:column;
 gap:22px;box-shadow:0 40px 80px -40px rgba(11,18,32,.55)}
.calc .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.calc .tag{display:inline-flex;align-items:center;height:40px;padding:0 16px;border-radius:999px;background:var(--night3);
 color:#C9D1E0;font-size:14px;font-weight:600}
.calc select{appearance:none;-webkit-appearance:none;height:40px;border:0;border-radius:999px;background:var(--coral);
 color:var(--ink);font-family:inherit;font-size:14px;font-weight:700;padding:0 38px 0 16px;cursor:pointer;
 background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%230B1220' stroke-width='2'/%3E%3C/svg%3E");
 background-repeat:no-repeat;background-position:right 14px center}
.big{font-size:clamp(88px,12vw,156px);line-height:.88;font-weight:900;letter-spacing:-.065em;color:var(--coral);
 font-variant-numeric:tabular-nums}
.big.neg{color:#C9D1E0}
.calc p{margin:0;font-size:18px;line-height:1.5;color:#C9D1E0}
.figures{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;border-top:1px solid var(--night3);padding-top:20px}
.figures div{display:flex;flex-direction:column;gap:4px;min-width:0}
.figures span{font-size:12px;color:var(--night-muted)}
.figures b{font-size:clamp(15px,1.6vw,18px);font-variant-numeric:tabular-nums}
.source{font-size:12px;color:var(--night-muted)}

.band{background:var(--night);color:#fff}
.italian{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:48px;align-items:end;
 padding-top:104px;padding-bottom:104px}
.huge{font-size:clamp(116px,16vw,220px);line-height:.85;font-weight:900;letter-spacing:-.07em;color:var(--coral)}
.italian .lead{display:block;font-size:22px;font-weight:600;margin-top:10px}
.italian p{margin:0 0 16px;font-size:18px;line-height:1.6;color:var(--night-ink)}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;height:36px;padding:0 14px;border-radius:999px;background:var(--night2);
 font-size:14px;font-weight:600}
.chip b{color:var(--coral);margin-left:6px}
.night-note{display:block;margin-top:14px;font-size:13px;color:var(--night-muted)}

section.countries{padding-top:104px;padding-bottom:104px}
h2{margin:0;font-size:clamp(34px,4.6vw,60px);line-height:1.02;letter-spacing:-.045em;font-weight:900;max-width:760px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,210px),1fr));gap:14px;margin-top:40px}
.tile{background:var(--card);border-radius:26px;padding:22px 24px;display:flex;flex-direction:column;gap:4px;
 border:0;text-align:left;font-family:inherit;color:var(--ink);cursor:pointer;transition:transform .15s ease}
.tile:hover{transform:translateY(-2px)}
.tile span{font-size:15px;color:var(--body)}
.tile b{font-size:clamp(40px,4vw,52px);font-weight:900;letter-spacing:-.05em;font-variant-numeric:tabular-nums}
.tile.neg b{color:var(--muted)}
.tile[aria-pressed="true"]{background:var(--coral)}
.tile[aria-pressed="true"] span,.tile[aria-pressed="true"] b{color:var(--ink)}
.note{margin:20px 0 0;font-size:13px;line-height:1.5;color:var(--muted);max-width:820px}

.how{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:56px;align-items:center;
 padding-top:104px;padding-bottom:104px}
.how ol{list-style:none;margin:32px 0 0;padding:0;display:flex;flex-direction:column;gap:24px}
.how li{display:flex;gap:18px}
.how li>span{font-size:34px;font-weight:900;color:var(--coral);min-width:44px;line-height:1}
.how li strong{display:block;font-size:19px;margin-bottom:4px}
.how li p{margin:0;color:var(--night-ink);font-size:16px;line-height:1.5}
.phone{justify-self:center;width:min(100%,330px);border-radius:46px;background:#060A14;padding:12px;
 box-shadow:0 50px 90px -40px rgba(0,0,0,.7),inset 0 0 0 1px #1E2A47}
.screen{border-radius:36px;background:var(--night);padding:28px 18px 22px;display:flex;flex-direction:column;gap:14px}
.screen h3{margin:0;font-size:26px;letter-spacing:-.03em}
.screen .sub{font-size:13px;color:var(--night-muted);margin-top:-10px}
.hilite{background:var(--coral);color:var(--ink);border-radius:24px;padding:18px;display:flex;justify-content:space-between;
 align-items:center}
.hilite span{font-weight:600;font-size:15px}
.hilite b{font-size:34px;font-weight:900;letter-spacing:-.04em}
.list{background:var(--night2);border-radius:22px;display:flex;flex-direction:column}
.list div{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;font-size:15px}
.list div+div{border-top:1px solid var(--night3)}
.list b{font-variant-numeric:tabular-nums}
.list .neg{color:var(--night-muted)}

.trust{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:40px;padding-top:104px}
.trust h3{margin:0 0 10px;font-size:21px;letter-spacing:-.02em}
.trust p{margin:0;font-size:16px;line-height:1.6;color:var(--body)}
.soon{margin-top:56px;display:inline-flex;align-items:center;gap:10px;height:44px;padding:0 18px;border-radius:999px;
 background:var(--card);font-size:15px;font-weight:600}
.soon i{width:8px;height:8px;border-radius:50%;background:var(--coral)}

.final{padding-top:104px;padding-bottom:88px;display:flex;flex-direction:column;align-items:center;text-align:center;gap:22px}
.final h2{font-size:clamp(40px,6vw,84px);max-width:900px}
.final p{margin:0;font-size:18px;color:var(--body)}
.start{max-width:640px;width:100%;text-align:left;margin-top:24px}
.start h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 10px}
pre{margin:0;background:var(--night);color:#E8ECF4;border-radius:20px;padding:20px 22px;overflow-x:auto;
 font:14px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace}
footer{border-top:1px solid var(--line)}
footer .wrap{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding-top:28px;padding-bottom:44px;
 font-size:13px;color:var(--muted)}
@media (max-width:640px){nav.links .pill.section{display:none}header.top{height:64px;flex-wrap:nowrap}nav.links{flex-wrap:nowrap}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

SCRIPT = """
const DATA = %(data)s, L = %(labels)s;
const sel = document.getElementById('country');
const tiles = [...document.querySelectorAll('.tile')];
function show(code) {
  const c = DATA[code];
  if (!c) return;
  const big = document.getElementById('big');
  big.textContent = c.vs;
  big.classList.toggle('neg', c.neg);
  document.getElementById('net-there-label').textContent = L.net_there.replace('{cc}', code);
  document.getElementById('net-there').textContent = c.net;
  document.getElementById('prices').textContent = c.prices;
  if (c.city) document.getElementById('headline').textContent = L.h1.replace('{city}', c.city);
  sel.value = code;
  tiles.forEach(t => t.setAttribute('aria-pressed', String(t.dataset.code === code)));
}
sel.addEventListener('change', e => show(e.target.value));
tiles.forEach(t => t.addEventListener('click', () => {
  show(t.dataset.code);
  document.getElementById('calc').scrollIntoView({behavior: 'smooth', block: 'center'});
}));
document.getElementById('lang').addEventListener('change', e => {
  location.href = e.target.value === 'it' ? 'index.html' : 'index.en.html';
});
"""


def money(value: float, lang: str) -> str:
    whole = f"{round(value):,}"
    return f"{whole.replace(',', '.')} €" if lang == "it" else f"€{whole}"


def pct(value: float, lang: str, decimals: int = 0) -> str:
    text = f"{abs(value):.{decimals}f}"
    if lang == "it":
        text = text.replace(".", ",")
    sign = "+" if value > 0 else "−" if value < 0 else "±"
    return f"{sign}{text}%"


def plain_pct(value: float, lang: str) -> str:
    text = f"{value:.1f}"
    return f"{text.replace('.', ',')}%" if lang == "it" else f"{text}%"


def long_date(iso: str, lang: str) -> str:
    year, month, day = iso.split("-")
    name = MONTHS[lang].split()[int(month) - 1]
    return f"{int(day)} {name} {year}" if lang == "it" else f"{int(day)} {name} {year}"


def load_data() -> tuple[dict, dict]:
    catalogue = json.loads((ROOT / "catalogue" / "companies.json").read_text(encoding="utf-8"))
    countries = json.loads((ROOT / "relocation" / "countries.json").read_text(encoding="utf-8"))
    return catalogue, countries


def country_rows(countries: dict, lang: str) -> list[dict]:
    """Every country with a comparable purchasing-power figure, best first."""
    italy = countries["countries"]["IT"]["facts"]
    rows = []
    for code, entry in countries["countries"].items():
        facts = entry["facts"]
        if code == "IT" or "vs_italy" not in facts:
            continue
        vs = facts["vs_italy"]["value"]
        rows.append({
            "code": code,
            "name": entry["name"] if lang == "it" else COUNTRY_EN.get(code, entry["name"]),
            "vs_value": vs,
            "vs": pct(vs, lang),
            "neg": vs < 0,
            "net": money(facts["net_earnings"]["value"], lang),
            "prices": pct((facts["price_level"]["value"] / italy["price_level"]["value"] - 1) * 100, lang),
            "unemployment": facts.get("unemployment", {}).get("value"),
            "year": facts["vs_italy"]["year"],
        })
    rows.sort(key=lambda r: -r["vs_value"])
    return rows


def page(lang: str, catalogue: dict, countries: dict) -> str:
    c = COPY[lang]
    companies = catalogue["companies"]
    n_companies = len(companies)
    n_italian = sum(e.get("italian", 0) for e in companies)
    top_italian = sorted((e for e in companies if e.get("italian")), key=lambda e: -e["italian"])[:6]
    rows = country_rows(countries, lang)
    by_code = {r["code"]: r for r in rows}
    first = by_code[DEFAULT_COUNTRY]
    italy_net = money(countries["countries"]["IT"]["facts"]["net_earnings"]["value"], lang)
    year = first["year"]
    lowest = min((r for r in rows if r["unemployment"] is not None), key=lambda r: r["unemployment"])
    fmt = {"companies": n_companies}

    options = "".join(
        f'<option value="{r["code"]}"{" selected" if r["code"] == DEFAULT_COUNTRY else ""}>'
        f'{escape(r["name"])}</option>'
        for r in sorted(rows, key=lambda r: r["name"])
    )
    langs = "".join(
        f'<option value="{code}"{" selected" if code == lang else ""}>{COPY[code]["lang_name"]}</option>'
        for code in COPY
    )
    tiles = "".join(
        f'<button type="button" class="tile{" neg" if r["neg"] else ""}" data-code="{r["code"]}" '
        f'aria-pressed="{str(r["code"] == DEFAULT_COUNTRY).lower()}">'
        f'<span>{escape(r["name"])}</span><b>{r["vs"]}</b></button>'
        for r in rows
    )
    chips = "".join(f'<span class="chip">{escape(e["company"])}<b>{e["italian"]}</b></span>'
                    for e in top_italian)
    steps = "".join(f"<li><span>{i}</span><div><strong>{escape(t)}</strong><p>{escape(p)}</p></div></li>"
                    for i, (t, p) in enumerate(c["how"], 1))
    trust = "".join(f"<div><h3>{escape(t)}</h3><p>{escape(p)}</p></div>" for t, p in c["trust"])
    phone_rows = "".join(
        f'<div><span>{escape(r["name"])}</span><b class="{"neg" if r["neg"] else ""}">{r["vs"]}</b></div>'
        for r in rows[1:5]
    )
    data = {r["code"]: {"vs": r["vs"], "neg": r["neg"], "net": r["net"], "prices": r["prices"],
                        "city": CITY[lang].get(r["code"], "")} for r in rows}
    labels = {"net_there": c["net_there"], "h1": c["h1"]}
    other = "index.en.html" if lang == "it" else "index.html"
    city = CITY[lang][DEFAULT_COUNTRY]
    description = c["description"].format(**fmt)
    title = f"{NAME} — {c['title']}"

    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:image" content="{REPO.replace('github.com', 'raw.githubusercontent.com')}/main/docs/img/social-preview.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#F6F7FA">
<link rel="alternate" hreflang="{'en' if lang == 'it' else 'it'}" href="{other}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&amp;display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>

<header class="wrap top">
  <a class="brand" href="#top"><i></i>{NAME}</a>
  <nav class="links" aria-label="{escape(c['nav_countries'])}">
    <a class="pill section" href="#paesi">{c['nav_countries']}</a>
    <a class="pill section" href="#italiano">{c['nav_italian']}</a>
    <a class="pill" href="{REPO}">{c['nav_code']}</a>
    <select id="lang" class="lang" aria-label="Lingua / Language" data-other="{other}">{langs}</select>
  </nav>
</header>

<main id="top">
<section class="wrap hero">
  <div>
    <h1 id="headline">{escape(c['h1'].format(city=city))}</h1>
    <p class="lede">{escape(c['lede'].format(**fmt))}</p>
    <div class="ctas">
      <a class="btn btn-coral" href="demo/">{c['cta']}</a>
      <a class="btn btn-light" href="#paesi">{c['cta2']}</a>
    </div>
  </div>
  <div class="calc" id="calc" aria-live="polite">
    <div class="row">
      <span class="tag">{c['from']}</span>
      <label class="tag" for="country" style="background:none;padding:0 4px">{c['to']}</label>
      <select id="country" aria-label="{escape(c['choose'])}">{options}</select>
    </div>
    <span class="big{' neg' if first['neg'] else ''}" id="big">{first['vs']}</span>
    <p>{escape(c['card_line'])}</p>
    <div class="figures">
      <div><span>{c['net_it']}</span><b>{italy_net}</b></div>
      <div><span id="net-there-label">{c['net_there'].format(cc=DEFAULT_COUNTRY)}</span><b id="net-there">{first['net']}</b></div>
      <div><span>{c['prices']}</span><b id="prices">{first['prices']}</b></div>
    </div>
    <span class="source">{escape(c['card_source'].format(year=year))}</span>
  </div>
</section>

<section class="band" id="italiano">
  <div class="wrap italian">
    <div>
      <span class="huge">{n_italian}</span>
      <span class="lead">{escape(c['italian_lead'])}</span>
    </div>
    <div>
      <p>{escape(c['italian_body'].format(**fmt))}</p>
      <div class="chips">{chips}</div>
      <span class="night-note">{escape(c['italian_note'].format(date=long_date(catalogue['updated'], lang)))}</span>
    </div>
  </div>
</section>

<section class="wrap countries" id="paesi">
  <h2>{escape(c['countries_h'])}</h2>
  <div class="tiles">{tiles}</div>
  <p class="note">{escape(c['countries_note'].format(year=year, low=lowest['name'], low_rate=plain_pct(lowest['unemployment'], lang)))}</p>
</section>

<section class="band">
  <div class="wrap how">
    <div class="phone" aria-hidden="true">
      <div class="screen">
        <h3>{c['phone_h']}</h3>
        <span class="sub">{c['phone_sub']}</span>
        <div class="hilite"><span>{escape(rows[0]['name'])}</span><b>{rows[0]['vs']}</b></div>
        <div class="list">{phone_rows}</div>
      </div>
    </div>
    <div>
      <h2>{escape(c['how_h'])}</h2>
      <ol>{steps}</ol>
    </div>
  </div>
</section>

<section class="wrap">
  <div class="trust">{trust}</div>
  <span class="soon"><i></i>{escape(c['soon'])}</span>
</section>

<section class="wrap final">
  <h2>{escape(c['final_h'])}</h2>
  <p>{escape(c['final_p'])}</p>
  <div class="ctas" style="justify-content:center">
    <a class="btn btn-coral" href="demo/">{c['cta']}</a>
    <a class="btn btn-night" href="{REPO}">GitHub</a>
  </div>
  <div class="start"><h3>{c['start_h']}</h3><pre>{INSTALL}</pre></div>
</section>
</main>

<footer><div class="wrap">
  <span>{c['foot']} · <a href="{REPO}">{REPO.replace('https://', '')}</a></span>
  <span>{c['foot_sources']}</span>
</div></footer>

<script>{SCRIPT % {"data": json.dumps(data, ensure_ascii=False), "labels": json.dumps(labels, ensure_ascii=False)}}</script>
</body></html>
"""


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    catalogue, countries = load_data()
    (DOCS / "index.html").write_text(page("it", catalogue, countries), encoding="utf-8")
    (DOCS / "index.en.html").write_text(page("en", catalogue, countries), encoding="utf-8")

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
