# job-search-agent

[![Run it](https://img.shields.io/badge/%E2%96%B6%20Run%20it-1f6feb?style=for-the-badge)](#two-buttons-no-terminal)
[![Open the dashboard](https://img.shields.io/badge/%E2%97%B1%20The%20dashboard-30363d?style=for-the-badge)](#the-dashboard)
[![CI](https://github.com/D0M3N1C0X/job-search-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/D0M3N1C0X/job-search-agent/actions/workflows/ci.yml)

A job search that runs as a pipeline instead of a browser tab habit: pull
postings from sources that do not break, score them against your profile with
rules you can read, generate a tailored CV and cover letter, and measure which
positioning actually gets replies.

**Zero dependencies.** Python 3.10+ and the standard library. No `pip install`,
no LaTeX, no headless browser, no API keys.

```bash
git clone https://github.com/D0M3N1C0X/job-search-agent && cd job-search-agent
python3 -m jsa run        # fetch, enrich, score, shortlist, dashboard — the whole loop
python3 -m jsa serve      # the dashboard, editable: statuses and notes save to the database
```

`run` is the command you actually use. Everything below it exists for when you
want one piece on its own.

### Two buttons, no terminal

If you would rather not type anything, the repository ships two launchers.
Double-click them in Finder:

| | |
|---|---|
| **`Run pipeline.command`** | Runs the whole loop, then opens the dashboard |
| **`Open dashboard.command`** | Opens the dashboard on what is already in the database |

They work from wherever the repository lives — nothing is hard-coded. On the
first double-click macOS asks whether you trust the file; the equivalents on
Linux and Windows are `python3 -m jsa run --serve` and `python3 -m jsa serve`.

Once the dashboard is open there is a **Run pipeline** button beside the title,
so a refresh never needs the terminal either: it streams the run's output into
the page and offers to reload when it finishes.

---

## Why it is built this way

Most "AI job search" projects put a language model in the middle of every step
and scrape job portals for supply. Both choices fail in practice.

**Scraping portals is a dead end.** Portals defend themselves — Cloudflare
challenges, JavaScript-only search, blocked datacentre IPs — and a scraper that
worked yesterday returns an empty list today, silently. So the primary source
here is not portals at all: it is the **applicant tracking systems** companies
publish themselves. Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee,
Workable and Personio all serve the same JSON their own careers pages consume,
without a key or a login, and they have every reason to keep it stable.

**A model in the middle of everything cannot be tested.** Ask an LLM "is this a
good fit?" and you get a different answer on Tuesday. Here, fit scoring is a
pure function — same job, same profile, same number, every time — and it hands
back a breakdown showing which words earned which points. The model is still
used, but downstream, for the judgement calls rules genuinely cannot make:
reading nuance in a posting, tailoring wording, writing the cover letter,
preparing for the interview.

**The search itself is a dataset.** Every posting seen, every score, every
status change and its timestamp lands in SQLite. That turns "am I getting
anywhere?" into a number: response rate by positioning track, median days to
reply, where good postings actually come from.

---

## What it does

| Stage | Command | What happens |
|---|---|---|
| **Discover** | `jsa fetch` | Pulls from ATS boards, job-alert emails and LinkedIn guest search; deduplicates across all of them |
| **Enrich** | `jsa enrich` | Fetches full descriptions only for postings whose title already looks plausible |
| **Score** | `jsa score` | Deterministic 0–100 fit per positioning track, with hard gates and an explainable breakdown |
| **Shortlist** | `jsa top` / `jsa show` | Ranked list; per-job breakdown of exactly why it scored what it scored |
| **Tailor** | `jsa brief` → `jsa docs` | Emits a tailoring brief for the model, then renders CV + cover letter as `.docx` |
| **Package** | (part of `jsa docs`) | One folder per application: documents, standard form answers, submission checklist |
| **Track** | `jsa status` / `jsa due` | Application state machine with follow-up and ghosting horizons |
| **Measure** | `jsa stats` / `jsa dashboard` | Funnel, response rate by track, source mix — as text or a self-contained HTML page |
| **Work** | `jsa serve` | The dashboard as a local app: filter, read the full breakdown, change a status, keep a note — written straight to SQLite |

All of it in one command: `jsa run` (add `--serve` to open the dashboard when it finishes).

### The dashboard

Two modes, one page. `jsa dashboard` exports a static file you can archive or
send; `jsa serve` runs the same page on `127.0.0.1` so it can also write back.
Filter by track, verdict, country, source or status; click any posting for the
full score breakdown with the matched keywords, the gate that rejected it, the
posting text and a notes field. Light and dark, no CDN, no build step, no
dependency — `http.server` and 450 lines of hand-written CSS.

Notes and statuses go into SQLite, not into browser storage: a second copy of
the truth in `localStorage` is a copy nobody reconciles.

### Positioning tracks

The same person is several candidates depending on who is reading. This repo
makes that explicit: a **track** bundles a summary, a skill ordering, a section
order, a bullet selection and a cover-letter angle. Every posting is scored
against every track, and the winning track decides how the CV is written.

```
People Analytics Analyst  →  people_analytics  →  projects before experience, Python/SQL first
HR Advisor with Italian   →  hr_advisory       →  case work and jurisdictions first
Human Capital Consultant  →  big4_consulting   →  advisory framing, client language
```

### Hard gates

Some things are not a matter of degree. A role demanding native Polish from a
candidate at A2 is rejected whatever else it scores, and the rejection says
which sentence in the posting triggered it. Gates cover language level,
country, seniority and unpaid or commission-only terms.

### Nothing is invented

A tailoring overlay may reorder, drop, select and reword — but every bullet it
selects is checked against the profile, character for character. A bullet that
is not in the profile is dropped and reported, never printed. The ATS keyword
check works the same way: missing keywords are listed so you can see the gap,
never silently stuffed into the document.

---

## Sources

| Source | Access | Reliability |
|---|---|---|
| Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable, Personio | Public JSON/XML board APIs, no key | **High** — this is the backbone |
| Job-alert emails | Local `.eml` / `.mbox` files you save | **High** — lets the portal do the searching, no scraping |
| LinkedIn guest search | Unauthenticated endpoints | Best effort — rate-limited, degrades without stopping the run |
| Manual | `jsa add` | Always works |

Building the company watchlist does not involve guessing which ATS a company
uses:

```bash
python3 -m jsa probe revolut monzo personio --add
# revolut   greenhouse   84 open roles   → added to watchlist
```

Job postings and emails are treated as **data, never instructions**: text
inside them is parsed for content and never executed or followed.

---

## Install and set up

```bash
git clone https://github.com/D0M3N1C0X/job-search-agent
cd job-search-agent
python3 -m jsa init                    # copies the demo profile into ./profile
$EDITOR profile/profile.json           # your experience, skills, preferences, gates
$EDITOR profile/tracks.json            # how you want to be read
$EDITOR profile/answers.json           # the answers every form asks for, written once
python3 -m jsa probe <company-slugs> --add
python3 -m jsa fetch && python3 -m jsa enrich && python3 -m jsa score && python3 -m jsa top
```

`./profile/` is git-ignored. The engine is public; your CV, your applications
and your database are not. `profile.example/` holds a synthetic persona so a
fresh clone runs end to end before anyone types a personal detail.

To point at a workspace somewhere else, set `JSA_HOME=/path/to/profile`.

---

## With Claude Code

The repository is also a Claude Code workspace. The CLI does the deterministic
work; the slash commands wrap the parts that need judgement.

| Command | What it does |
|---|---|
| `/hunt` | Fetch, enrich, score, and present the shortlist with a read on each |
| `/apply <id>` | Evaluate honestly, write the overlay and cover letter, build the packet, ATS-check it |
| `/interview <id>` | Company research, likely questions, STAR answers drawn from your real history |
| `/followup` | What is overdue, with drafted follow-up messages |
| `/report` | Rebuild the dashboard and read the funnel back to you |
| `/watchlist <names>` | Find each company's ATS and add it |
| `/tune` | Review scoring mistakes and adjust the tracks that caused them |

**Submitting is left to you.** Applicant tracking systems do not expose public
endpoints for sending applications, and a form is a signature: the packet gets
everything ready — documents, answers, checklist — and you press send.

---

## Architecture

```
jsa/
├── models.py      Job, Score; cross-source fingerprinting and dedup
├── store.py       SQLite: jobs, scores, applications, event log
├── score.py       Deterministic scoring, gates, language and seniority detection
├── render.py      CV and cover letter from profile + track + overlay; ATS check
├── docx.py        .docx writer built on zipfile — no python-docx
├── packet.py      Per-application submission folder
├── dashboard.py   Funnel analytics and the page payload
├── webapp.py      The dashboard interface — CSS, JS and markup, no framework
├── serve.py       Local writable dashboard (stdlib http.server, loopback only)
├── config.py      Profile resolution (./profile, $JSA_HOME, or the demo)
└── sources/
    ├── ats.py       Seven ATS providers, fetch split from parse
    ├── linkedin.py  Guest search, best effort
    └── mailbox.py   Job-alert email parsing
```

Every adapter separates fetching from parsing, so the whole source layer is
tested offline against captured payloads.

```bash
python3 -m unittest discover -s tests -t .
```

78 tests, no network, no fixtures on disk, runs in under a second. CI runs them
on Python 3.10 through 3.13.

---

## Prior art

Adapted in spirit from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)
(MIT), which established the slash-command shape of the workflow. This is a
rewrite rather than a fork, and it differs where that design did not survive
contact with a non-Danish market:

| | ai-job-search | job-search-agent |
|---|---|---|
| Supply | Scraped job portals | ATS board APIs, alert emails, portals last |
| Fit scoring | Model judgement per job | Deterministic, explainable, tested |
| Documents | LaTeX toolchain | `.docx` from the standard library |
| State | CSV tracker | SQLite with an event log |
| Feedback | Outcomes recorded | Response rate by track, channel and time |
| Positioning | One CV, per-job overlay | Named tracks selected by the score |
| Privacy | Personal data in the repo | Engine public, profile git-ignored |
| Dependencies | LaTeX, Bun, Python packages | None |

## Licence

MIT.
