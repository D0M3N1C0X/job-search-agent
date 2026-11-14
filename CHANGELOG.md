# Changelog

What changed in each release, for the people running it. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/): a new major version means something
you set up by hand (profile, tracks, database) needs attention.

## [Unreleased]

### Changed

- **Scorer 1.2.0.** Language requirements written as a duty ("you must be able
  to work in French every day", "German and English, both at business level,
  are a must") or in Italian as "conoscenza fluente dell'italiano"; "eight or
  more years"; pay written as a story ("no fixed salary; your income is your
  commission"). Tracks gain `titles.avoid`: a title that names another job
  ("Payroll & HR Administrator", "Customer Success Manager, HR Tech") earns no
  title points. **Measured honestly, it does not generalise:** on a new
  held-out set written after these fixes, 1.2.0 scores 21 of 30 as labelled,
  exactly as 1.1.0 does. `docs/scoring.md` says what that means.

### Added

- **`jsa evaluate`: how often the scorer is right, measured.** 130 labelled
  postings in `evaluation/`, each with what a person reading it for the example
  candidate would do (apply, maybe, skip), the gate that should fire and the
  track it should go on. The report prints precision, recall, which gates fired
  where they should and where they should not, and every posting scored
  differently from its label. 30 of the postings are held out: written after the
  last change to the rules and scored once. On them the scorer goes from 15 to
  20 as labelled, precision from 54% to 73%, and no posting labelled apply is
  rejected. `docs/scoring.md` lists what it still gets wrong.
- `jsa evaluate --mine` compares the scorer with your own decisions: what you
  drafted or sent against what you skipped, and the pass mark that would have
  agreed with you most often.
- **Language requirements are recognised without setup**, for sixteen
  languages, asked for in English or in the language itself, with the level
  before or after the name ("fluent Dutch", "Dutch (fluent)", "French mother
  tongue"). A language named without being required — "Dutch is a plus", "free
  Dutch lessons", "our Dutch entities", "fluent German or English" for someone
  with English — no longer counts. The profile's own `language_gates` still add
  to them; `preferences.language_gates_builtin: false` turns the built-in ones
  off. Before, only the languages the setup wizard had written a rule for were
  checked: of 18 language requirements in the benchmark, 3 were caught.
- An `experience` gate: a posting asking five or more years beyond the profile
  is rejected; three or four years beyond can reach review, not pass.
- An internship is rejected for a profile with two years of experience or more.

- CI runs mypy on the package and measures test coverage (78%, with a floor);
  both are CI-only, so the tool still installs nothing.
- A shared employer catalogue, used with no setup: `catalogue/companies.json`
  lists 265 European employers whose job boards were verified to answer, with
  where they hire and how many roles mention Italian. `jsa fetch` adds every
  board that hires in a country your profile accepts; your own watchlist comes
  first. `preferences.catalogue: false` or `jsa fetch --no-catalogue` turns it
  off. Built by `tools/catalogue.py`, which keeps a board only when it has
  roles in Europe and its declared name matches the company.
- Boards are fetched eight at a time: about 270 boards take under a minute.
- Country facts for moving abroad (`relocation/`): net pay, price levels,
  purchasing power against Italy and unemployment for 21 countries, read from
  Eurostat by `tools/relocation.py`, with a register of every rejected value.
- `jsa apply` adds a typeset CV PDF when Chrome, Edge or Chromium is installed.

### Fixed

- **"Years of experience" read numbers that were not about experience**: a
  company "trading for 25 years" asked 25 years of the candidate, and "in the
  past 3 years our headcount tripled" asked three. A number now counts only
  with "experience", "at least", a "+" or similar next to it; a range counts from
  its lower end; numbers up to fifteen may be written out, and "a decade" is ten.
- **A role reporting to a director read as a director's role**: "you will report
  to the Director of People" in the body made an untitled People Operations role
  a `head` and rejected it. The body can still make a role senior or junior,
  never a head of function.
- Keywords now match their plain plural: "dashboard" finds "dashboards", "HR
  policy" finds "HR policies". Terms under four letters do not, so "hr" never
  finds "hrs".
- An anti-keyword in the title weighs three times as much as one in the body:
  "Software Engineer, HR Tech" is the job, not a mention.
- The example tracks list the advisory work they were missing (absence,
  performance management, works council, investigations) and the neighbouring
  jobs they should push away (software, data engineering, software sales).
- The shared employer catalogue was missing from the installed package: an
  installed copy fetched only its own watchlist. It now ships inside it, with
  the labelled postings.

- **Alert emails saved as .mbox gave no jobs.** mbox files were read as legacy
  messages without `get_content()`, the error was swallowed, and every body came
  out empty; .eml files were unaffected. Both now go through the same parser.
- **One posting removed mid-run could end `jsa daily`.** A job deleted between
  reading the ranking and loading it reached the preparation step as `None`,
  and the handler meant to absorb the failure then failed itself.
- US state abbreviations no longer read as European countries: "Wilmington, DE"
  was Germany and "Birmingham, AL" Britain.
- HTTPS to sites using recent root certificates (ec.europa.eu) on older macOS:
  the keychain's roots are read on the first verification failure.
- PDFs printed by browsers are read as words, not single letters.

- Your own CVs, attached unchanged: `jsa cv add <file> --track <id>` or
  `--company <name>`. A CV written for the company wins, then the one for the
  winning track; the generated CV is used only when neither exists
  (`jsa apply --generated-cv` asks for it anyway). The ATS check reads PDFs.
- Cover letters built on your own model: `letter.json` in the workspace holds
  your anchor sentence, your evidence tagged by topic, and your close. The
  draft uses the evidence the posting asks about, in your order, and leaves
  why-this-company and the honest gap as `[[WRITE: …]]` parts, with the
  track's skills the posting asks for and your CV does not show as hints. The
  packet and the helper page say how many are left. Dates are written out
  ("18 September 2026").
- `jsa autoprepare --min-score 80 --per-week 5`: the daily run prepares
  packets for the best untouched postings, up to a weekly cap that counts
  packets made by hand too, and the notification leads with what is ready.
  You still read each one and press send.


## [1.1.0] — 2026-09-26

Nothing you set up by hand needs to change: profiles, tracks and databases
from 1.0.0 work as they are.

### Added

- `jsa setup` builds the profile from questions and a library of eight
  positioning tracks, instead of 500 lines of hand-written JSON.
- `jsa import` reads the CV you already have (`.docx`, `.pdf`, text) and fills
  the profile in.
- `jsa apply` builds the packet in one step: tailored CV, draft cover letter,
  standard answers, an ATS keyword check and a local page with a form-filling
  bookmarklet. Nothing is ever submitted. `jsa next` names the single next
  thing to do.
- `jsa daily` runs the pipeline and notifies only when something new clears
  the threshold or something is overdue; `jsa install --daily 08:30`
  schedules it on macOS.
- `jsa doctor` checks the whole setup and explains anything wrong.
- The dashboard speaks Italian and English, switchable on the page.
- A public site in `docs/` with a live demo of the dashboard on synthetic data.
- Installable as a package: `pipx install git+https://github.com/D0M3N1C0X/job-search-agent`,
  or the wheel attached to each release from now on. An installed copy keeps
  the workspace in `~/.jsa` and scratch files in `~/.cache/job-search-agent`;
  a clone keeps `./profile`.
- `jsa fetch` flags a board that suddenly returns nothing after listing open
  roles, instead of printing it as a normal empty board.
- `SECURITY.md`, this changelog, and releases published from a tag.

### Security

- A web page open in another tab could write to `jsa serve` (cross-site
  request forgery): start a run, or change a status or a note. Writes now need
  a per-server token that only the served page has.
- A posting title containing `</script>` could run script in the dashboard.
  Embedded data is now escaped, and the page has a Content-Security-Policy.
- `javascript:` and `file:` links from feeds reached links and macOS `open`;
  only http(s) links are kept.
- On Windows, job titles were interpolated into a PowerShell command; the
  notification call is removed.

### Fixed

- The unpaid-work gate rejected well-paid jobs whose benefits mention
  volunteering days (671 of its 719 rejections in an audit were wrong).
- Job descriptions keep their accented letters: only a handful of HTML
  entities were decoded, so a Greenhouse posting read "M&uuml;nchen" and
  "Krak&oacute;w" on screen, and keyword matching saw "m and uuml nchen".
  Entities are also decoded once rather than twice. Postings stored by 1.0.0
  are cleaned in place by running `jsa reindex` once (then
  `jsa score --rescore`).
- A stored description lost any text between `<` and `>` every time it was
  read back from the database.
- `jsa export` wrote titles and companies from feeds into cells a spreadsheet
  would run as formulas.
- Location matching covers every European country and the cities postings
  actually use; "Limassol" no longer resolves to Peru, and "Łódź" is found.
- `jsa init` copies `answers.json`, so the packet carries your standard answers.
- The dashboard's *Run pipeline* button ran against the default workspace
  instead of the one on screen (visible with `jsa demo` or `--home`).
- `jsa setup`, `init` and `import` ignored `JSA_HOME` and wrote to `./profile`
  while every other command read from `JSA_HOME`. Background jobs installed on
  macOS now carry `JSA_HOME` too, since launchd does not inherit the shell's.
- A non-editable install (`pipx install .`) could not find its example profile
  and would have put the workspace inside site-packages.
- A failed source shows why it failed rather than a truncated URL, and LinkedIn
  counts as failed when every query fails instead of reporting "0 listed".
- The form-filling bookmarklet altered answers containing `%` (a browser
  percent-decodes the link before running it), and a `%22` broke it outright.
- `jsa demo` no longer inherits a `jobs.db` left in the example profile.
- Oversized HTTP responses, gzip bombs, and PDF or DOCX files that inflate past
  any plausible CV are refused; a `.docx` that is not one gets an explanation
  instead of a traceback.

### Platforms and CI

- macOS and Linux are supported and tested; Windows is best effort.
- CI runs on Linux (Python 3.10–3.13) and macOS, with ruff and CodeQL, and
  installs the built wheel to check it runs and writes nothing into its own
  package directory.

## [1.0.0] — 2026-09-04

The first public release.

- `jsa run` fetches, enriches, scores, shortlists and rebuilds the dashboard in
  one command.
- Sources: seven applicant tracking systems (Greenhouse, Lever, Ashby,
  SmartRecruiters, Recruitee, Workable, Personio) through their public board
  APIs, job-alert emails saved as `.eml`/`.mbox`, LinkedIn guest search on a
  best-effort basis, and `jsa add` by hand. `jsa probe` finds which board a
  company uses.
- Deterministic, explainable 0–100 scoring per positioning track, with hard
  gates for language level, country, seniority and unpaid or commission-only
  roles.
- Tailored `.docx` CVs and cover letters from the profile and an overlay
  (`jsa brief`, `jsa docs`), checked against the profile so nothing is
  invented, with a submission packet per application.
- An application tracker with follow-up horizons (`jsa status`, `jsa due`) and
  funnel numbers by track (`jsa stats`).
- The dashboard: `jsa dashboard` exports it; `jsa serve` runs it locally with
  statuses and notes written to SQLite. `jsa demo` shows it on synthetic data.
- `jsa install` puts `jsa` on PATH and, on macOS, adds a Dock app.

[Unreleased]: https://github.com/D0M3N1C0X/job-search-agent/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/D0M3N1C0X/job-search-agent/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/D0M3N1C0X/job-search-agent/releases/tag/v1.0.0
