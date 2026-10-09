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
    "LT": "Lithuania", "IE": "Ireland",
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
        "guides_label": "Le guide per trasferirsi:",
        "cities_h": "Sei città, sei conti diversi.",
        "cities_p": "Potere d'acquisto rispetto all'Italia. Tocca una città per vedere i suoi conti.",
        "power": "potere d'acquisto",
        "photos": "Foto su Unsplash di",
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
        "guides_label": "Moving guides (in Italian):",
        "cities_h": "Six cities, six different sums.",
        "cities_p": "Purchasing power compared with Italy. Tap a city to see its sums.",
        "power": "purchasing power",
        "photos": "Photos on Unsplash by",
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
           "LT": "Vilnius", "IE": "Dublino"},
    "en": {"DE": "Berlin", "AT": "Vienna", "CH": "Zurich", "ES": "Madrid", "PT": "Lisbon",
           "FR": "Paris", "BE": "Brussels", "NL": "Amsterdam", "LU": "Luxembourg",
           "PL": "Warsaw", "CZ": "Prague", "SK": "Bratislava", "HU": "Budapest", "RO": "Bucharest",
           "BG": "Sofia", "HR": "Zagreb", "SI": "Ljubljana", "EE": "Tallinn", "LV": "Riga",
           "LT": "Vilnius", "IE": "Dublin"},
}

# Photos in docs/img/cities, chosen from Unsplash (licence and authors in credits.json).
CITIES = [
    ("amsterdam", "NL", {"it": "Amsterdam", "en": "Amsterdam"},
     {"it": ("Canale di Amsterdam al tramonto", "Case sul canale di notte"),
      "en": ("Amsterdam canal at sunset", "Canal houses at night")}),
    ("berlino", "DE", {"it": "Berlino", "en": "Berlin"},
     {"it": ("Berlino e la torre della televisione al tramonto", "La Sprea e l'Isola dei Musei"),
      "en": ("Berlin and the TV tower at sunset", "The Spree and Museum Island")}),
    ("parigi", "FR", {"it": "Parigi", "en": "Paris"},
     {"it": ("I tetti di Parigi con la Tour Eiffel", "La Tour Eiffel"),
      "en": ("Paris rooftops and the Eiffel Tower", "The Eiffel Tower")}),
    ("madrid", "ES", {"it": "Madrid", "en": "Madrid"},
     {"it": ("I tetti di Madrid al tramonto", "La Gran Vía"),
      "en": ("Madrid rooftops at sunset", "Gran Vía")}),
    ("varsavia", "PL", {"it": "Varsavia", "en": "Warsaw"},
     {"it": ("Il Palazzo della Cultura al tramonto", "La piazza della Città Vecchia"),
      "en": ("The Palace of Culture at sunset", "The Old Town square")}),
    ("lisbona", "PT", {"it": "Lisbona", "en": "Lisbon"},
     {"it": ("I tetti arancioni di Lisbona", "Il tram giallo"),
      "en": ("Lisbon's orange rooftops", "The yellow tram")}),
]

CSS = """
/* Inter, served from this site (SIL Open Font License, fonts/OFL.txt): no request to a third party. */
@font-face{font-family:Inter;font-style:normal;font-weight:400 900;font-display:swap;
 src:url(fonts/inter-latin.woff2) format("woff2");
 unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}
@font-face{font-family:Inter;font-style:normal;font-weight:400 900;font-display:swap;
 src:url(fonts/inter-latin-ext.woff2) format("woff2");
 unicode-range:U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C4,U+2113,U+2C60-2C7F,U+A720-A7FF}
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

.cities{padding-bottom:104px}
.cities .head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.cities .head p{margin:0;color:var(--muted);font-size:15px}
.strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:36px}
.city{position:relative;border:0;padding:0;border-radius:28px;overflow:hidden;aspect-ratio:4/5;cursor:pointer;
 background:#DCE1EA;font-family:inherit;text-align:left;transition:transform .2s ease}
.city:hover{transform:translateY(-3px)}
.city img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.city .label{position:absolute;left:0;right:0;bottom:0;padding:64px 22px 22px;display:flex;justify-content:space-between;align-items:flex-end;gap:10px;
 background:linear-gradient(to top,rgba(11,18,32,.82),rgba(11,18,32,0));color:#fff}
.city .label strong{font-size:clamp(20px,2.2vw,28px);letter-spacing:-.03em}
.city .label span{display:inline-flex;height:34px;align-items:center;padding:0 14px;border-radius:999px;
 background:var(--coral);color:var(--ink);font-size:16px;font-weight:800;font-variant-numeric:tabular-nums}
.city .label span.neg{background:rgba(255,255,255,.88)}
.city[aria-pressed="true"]{outline:3px solid var(--coral);outline-offset:3px}
@media (max-width:860px){.strip{grid-template-columns:repeat(2,minmax(0,1fr))}
 .city .label{padding:48px 14px 14px;flex-direction:column;align-items:flex-start;gap:6px}
 .city .label span{height:28px;font-size:14px;padding:0 10px}}
.collage{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;width:100%;margin-bottom:16px}
.collage img{width:100%;height:clamp(110px,16vw,220px);object-fit:cover;border-radius:20px;display:block}
.collage img:nth-child(even){margin-top:28px}
@media (max-width:700px){.collage{grid-template-columns:repeat(3,minmax(0,1fr))}.collage img:nth-child(n+4){display:none}}
.credits{font-size:12px;color:var(--muted);line-height:1.6}
.credits a{color:var(--muted)}
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
.guides-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:22px}
.guides-row span{font-size:15px;color:var(--muted);margin-right:4px}
.guides-row a{display:inline-flex;align-items:center;height:40px;padding:0 16px;border-radius:999px;background:var(--card);
 text-decoration:none;font-weight:600;font-size:14px}
.guides-row a:hover{background:var(--coral)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

SCRIPT = """
const DATA = %(data)s, L = %(labels)s;
const sel = document.getElementById('country');
const tiles = [...document.querySelectorAll('.tile, .city')];
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
    credits = {c_["file"]: c_ for c_ in json.loads(
        (DOCS / "img" / "cities" / "credits.json").read_text(encoding="utf-8"))}

    def picture(slug: str, alt: str, lazy: bool = True) -> str:
        loading = ' loading="lazy"' if lazy else ""
        return (f'<img src="img/cities/{slug}-900.webp" '
                f'srcset="img/cities/{slug}-480.webp 480w, img/cities/{slug}-900.webp 900w" '
                f'sizes="(max-width:860px) 50vw, 400px" '
                f'alt="{escape(alt)}" width="900" height="1200"{loading} decoding="async">')

    strip = "".join(
        f'<button type="button" class="city" data-code="{code}" '
        f'aria-pressed="{str(code == DEFAULT_COUNTRY).lower()}">'
        f'{picture(slug + "-1", alts[lang][0])}'
        f'<span class="label"><strong>{escape(names[lang])}</strong>'
        f'<span class="{"neg" if by_code[code]["neg"] else ""}">{by_code[code]["vs"]}</span>'
        f'</span></button>'
        for slug, code, names, alts in CITIES if code in by_code
    )
    collage = "".join(picture(slug + "-2", alts[lang][1]) for slug, _code, _names, alts in CITIES)
    authors = []
    for slug, _code, _names, _alts in CITIES:
        for n in (1, 2):
            entry = credits.get(f"{slug}-{n}")
            if entry and entry["author"] not in [a[0] for a in authors]:
                authors.append((entry["author"], entry["profile"]))
    photo_credits = ", ".join(
        f'<a href="{escape(url)}?utm_source=job-search-agent&amp;utm_medium=referral">{escape(name)}</a>'
        for name, url in authors)

    _common, guides = load_guides()
    guide_links = "".join(f'<a href="paesi/{g["slug"]}.html">{escape(by_code[g["country"]]["name"])}</a>'
                          for g in guides if g["country"] in by_code)
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
<link rel="preload" href="fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
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

<section class="wrap cities" aria-labelledby="cities-h">
  <div class="head"><h2 id="cities-h">{escape(c['cities_h'])}</h2><p>{escape(c['cities_p'])}</p></div>
  <div class="strip">{strip}</div>
  <div class="guides-row"><span>{escape(c['guides_label'])}</span>{guide_links}</div>
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
  <div class="collage">{collage}</div>
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
  <span class="credits">{c['photos']} {photo_credits}.</span>
</div></footer>

<script>{SCRIPT % {"data": json.dumps(data, ensure_ascii=False), "labels": json.dumps(labels, ensure_ascii=False)}}</script>
</body></html>
"""


# ------------------------------------------------------------------ guides

GUIDES = ROOT / "relocation" / "guides"
TOPICS = [
    ("registration", "Registrarsi", "Anagrafe e documenti per restare più di tre mesi."),
    ("tax", "Tasse", "Quando diventi residente fiscale e quale numero ti serve."),
    ("health", "Sanità", "Come sei coperto quando lavori lì."),
    ("home", "Casa e banca", "Cauzione dell'affitto e conto corrente."),
]
GUIDE_CSS = """
.g-hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:40px;align-items:center;
 padding-top:40px;padding-bottom:72px}
.g-hero .kicker{font-size:15px;font-weight:700;color:var(--coral-ink)}
.g-hero h1{margin:10px 0 0;font-size:clamp(44px,6vw,80px);line-height:1;letter-spacing:-.05em;font-weight:900}
.g-hero .lede{margin-top:18px}
.g-photo{position:relative;border-radius:32px;overflow:hidden;aspect-ratio:4/5;max-height:560px;background:#DCE1EA}
.g-photo img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.g-photo .label{position:absolute;left:20px;right:20px;bottom:20px;background:rgba(11,18,32,.82);color:#fff;
 border-radius:22px;padding:18px 20px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;
 backdrop-filter:blur(10px)}
.g-photo .label div{display:flex;flex-direction:column;gap:2px}
.g-photo .label span{font-size:11.5px;color:var(--night-muted)}
.g-photo .label b{font-size:17px;font-variant-numeric:tabular-nums}
.g-photo .label b.vs{color:var(--coral)}
.g-sec{padding-top:56px}
.g-sec h2{font-size:clamp(28px,3.4vw,44px)}
.g-sec .sub{margin:8px 0 0;color:var(--muted);font-size:16px}
.steps{list-style:none;margin:24px 0 0;padding:0;display:grid;gap:12px}
.steps li{background:var(--card);border-radius:24px;padding:22px 24px 20px 72px;position:relative}
.steps li::before{counter-increment:step;content:counter(step);position:absolute;left:22px;top:22px;width:32px;height:32px;
 border-radius:11px;background:var(--coral);color:var(--ink);font-weight:800;display:grid;place-items:center;font-size:15px}
.steps{counter-reset:step}
.steps p{margin:0;font-size:17px;line-height:1.6}
.steps a{display:inline-block;margin-top:8px;font-size:13px;color:var(--muted)}
.before{background:var(--night);color:#fff;border-radius:32px;padding:clamp(24px,4vw,40px);margin-top:8px}
.before h2{color:#fff;font-size:clamp(26px,3vw,38px)}
.before .steps li{background:var(--night2)}
.before .steps p{color:#fff}
.before .steps a{color:var(--night-muted)}
.gaps{margin-top:56px;background:#FFF4E5;border-radius:24px;padding:22px 26px}
.gaps h3{margin:0 0 8px;font-size:17px}
.gaps ul{margin:0;padding-left:20px;color:#5B4A2E;line-height:1.6}
.disclaimer{margin:40px 0 0;font-size:13.5px;color:var(--muted);max-width:760px;line-height:1.6}
.otherguides{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.otherguides a{display:inline-flex;align-items:center;height:40px;padding:0 16px;border-radius:999px;background:var(--card);
 text-decoration:none;font-weight:600;font-size:14px}
.otherguides a[aria-current]{background:var(--night);color:#fff}
.guides-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:22px}
.guides-row span{font-size:15px;color:var(--muted);margin-right:4px}
.guides-row a{display:inline-flex;align-items:center;height:40px;padding:0 16px;border-radius:999px;background:var(--card);
 text-decoration:none;font-weight:600;font-size:14px}
.guides-row a:hover{background:var(--coral)}
@media (max-width:640px){.steps li{padding:18px 18px 16px 58px}.steps li::before{left:16px;top:18px;width:28px;height:28px}
 .steps p{font-size:16px}.before{padding:20px 14px}.g-photo .label{left:12px;right:12px;bottom:12px;padding:14px}}
"""


def load_guides() -> tuple[dict, list[dict]]:
    common = json.loads((GUIDES / "common.json").read_text(encoding="utf-8"))
    guides = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GUIDES.glob("*.json"))
              if p.name != "common.json"]
    return common, guides


def steps_html(items: list[dict]) -> str:
    return "<ol class='steps'>" + "".join(
        f"<li><p>{escape(i['text'])}</p><a href='{escape(i['url'])}' rel='noopener'>Fonte: {escape(i['source'])} ↗</a></li>"
        for i in items) + "</ol>"


def guide_page(guide: dict, common: dict, guides: list[dict], catalogue: dict, countries: dict) -> str:
    code = guide["country"]
    row = {r["code"]: r for r in country_rows(countries, "it")}[code]
    name = row["name"]
    city_slug = guide["city"]
    hiring = [e for e in catalogue["companies"] if code in e.get("countries", {})]
    roles = sum(e["countries"][code] for e in hiring)
    alt = next((a["it"][0] for slug, _c, _n, a in CITIES if slug == city_slug), "")
    checked = long_date(guide["checked"], "it")
    sections = []
    for key, title, sub in TOPICS:
        shared = [] if key in guide.get("skip_common", []) else common.get(key, [])
        items = guide.get(key, []) + shared
        if items:
            sections.append(f"<section class='wrap g-sec'><h2>{title}</h2><p class='sub'>{sub}</p>{steps_html(items)}</section>")
    gaps = "".join(f"<li>{escape(g)}</li>" for g in guide.get("gaps", []))
    names = {r["code"]: r["name"] for r in country_rows(countries, "it")}
    current = ' aria-current="page"'
    others = "".join(
        f"<a href='{g['slug']}.html'{current if g is guide else ''}>{escape(names[g['country']])}</a>"
        for g in guides)
    css = CSS.replace("url(fonts/", "url(../fonts/") + GUIDE_CSS
    if city_slug:
        visual = f"""<div class="g-photo">
    <img src="../img/cities/{city_slug}-1-900.webp" srcset="../img/cities/{city_slug}-1-480.webp 480w, ../img/cities/{city_slug}-1-900.webp 900w" sizes="(max-width:860px) 100vw, 560px" alt="{escape(alt)}" width="900" height="1200">
    <div class="label">
      <div><span>Potere d'acquisto vs Italia</span><b class="vs">{row['vs']}</b></div>
      <div><span>Netto medio annuo</span><b>{row['net']}</b></div>
      <div><span>Prezzi vs Italia</span><b>{row['prices']}</b></div>
    </div>
  </div>"""
    else:
        visual = f"""<div class="calc">
    <span class="tag" style="align-self:flex-start">Da Italia a {escape(name)}</span>
    <span class="big{' neg' if row['neg'] else ''}">{row['vs']}</span>
    <p>di potere d'acquisto per lo stipendio netto medio, già tolti i prezzi.</p>
    <div class="figures">
      <div><span>Netto {escape(name)}</span><b>{row['net']}</b></div>
      <div><span>Prezzi</span><b>{row['prices']}</b></div>
      <div><span>Disoccupazione</span><b>{plain_pct(row['unemployment'], 'it') if row['unemployment'] is not None else '–'}</b></div>
    </div>
    <span class="source">Eurostat {row['year']} · dati nazionali</span>
  </div>"""
    title = f"Trasferirsi in {name} da italiano — {NAME}"
    desc = (f"Registrazione, tasse, sanità, casa e banca per un italiano che va a lavorare in {name}, "
            f"con le fonti ufficiali. Più i numeri: stipendio netto {row['net']}, potere d'acquisto {row['vs']} rispetto all'Italia.")
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:image" content="{'../img/cities/' + city_slug + '-1-900.webp' if city_slug else '../img/social-preview.png'}">
<meta name="theme-color" content="#F6F7FA">
<link rel="preload" href="../fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
<style>{css}</style></head><body>
<header class="wrap top">
  <a class="brand" href="../index.html"><i></i>{NAME}</a>
  <nav class="links" aria-label="Sezioni"><a class="pill" href="../index.html#paesi">Tutti i paesi</a></nav>
</header>
<main>
<section class="wrap g-hero">
  <div>
    <span class="kicker">Guida al trasferimento</span>
    <h1>Lavorare in {escape(name)} da italiano.</h1>
    <p class="lede">I passi per sistemarti: registrazione, tasse, sanità, casa e banca. Ogni frase rimanda alla fonte ufficiale da cui è presa.</p>
    <p class="lede" style="font-size:16px;margin-top:12px">{len(hiring)} aziende del nostro catalogo assumono in {escape(name)}, con {roles} offerte aperte.</p>
    <div class="ctas"><a class="btn btn-coral" href="../demo/">Apri la demo</a></div>
  </div>
  {visual}
</section>
<section class="wrap"><div class="before"><h2>Prima di partire, dall'Italia</h2>{steps_html(common['before'])}</div></section>
{''.join(sections)}
<section class="wrap">
  {f"<div class='gaps'><h3>Cosa non abbiamo ancora verificato</h3><ul>{gaps}</ul></div>" if gaps else ""}
  <p class="disclaimer">Informazioni generali, verificate sulle fonti ufficiali il {checked}. I numeri del paese sono di Eurostat, anno {row['year']}, per un lavoratore single con retribuzione media. Questa guida non sostituisce un consulente: prima di agire, apri il link della fonte e controlla che nulla sia cambiato.</p>
  <h2 style="font-size:24px;margin-top:48px">Altre guide</h2>
  <div class="otherguides">{others}</div>
</section>
</main>
<footer style="margin-top:72px"><div class="wrap">
  <span>Licenza MIT · <a href="{REPO}">{REPO.replace('https://', '')}</a></span>
  <span>Fonti ufficiali citate in ogni passo · registro in relocation/guides</span>
</div></footer>
</body></html>
"""


def register(common: dict, guides: list[dict]) -> str:
    lines = ["# Registro delle verifiche — guide paese", "",
             "Ogni passo pubblicato nelle guide, con la fonte da cui è scritto e la data del controllo. "
             "Generato da `tools/build_site.py`: non modificare a mano.", ""]
    for g in [dict(common, country="Comune a tutti i paesi")] + guides:
        lines += [f"## {g['country']}", "", f"Verificato il {g['checked']}.", "", "| Tema | Fonte |", "|---|---|"]
        for key in ("before", "registration", "tax", "health", "home"):
            for item in g.get(key, []):
                lines.append(f"| {key} | [{item['source']}]({item['url']}) |")
        if g.get("gaps"):
            lines += ["", "**Lacune**", ""] + [f"- {x}" for x in g["gaps"]]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    catalogue, countries = load_data()
    (DOCS / "index.html").write_text(page("it", catalogue, countries), encoding="utf-8")
    (DOCS / "index.en.html").write_text(page("en", catalogue, countries), encoding="utf-8")

    common, guides = load_guides()
    (DOCS / "paesi").mkdir(exist_ok=True)
    for guide in guides:
        (DOCS / "paesi" / f"{guide['slug']}.html").write_text(
            guide_page(guide, common, guides, catalogue, countries), encoding="utf-8")
    (GUIDES / "REGISTRO.md").write_text(register(common, guides), encoding="utf-8")

    demo = DOCS / "demo"
    demo.mkdir(exist_ok=True)
    cfg = build(count=90)
    with Store(cfg.db_path) as store:
        build_dashboard(store, cfg, demo / "index.html")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    print(f"  docs/paesi/  {len(guides)} guide")
    for path in (DOCS / "index.html", DOCS / "index.en.html", demo / "index.html"):
        print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")
    print("\nGitHub Pages: Settings → Pages → Source: main / docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
