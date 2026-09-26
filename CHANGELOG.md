# Changelog

What changed in each release, for the people running it. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/): a new major version means something
you set up by hand (profile, tracks, database) needs attention.

## [Unreleased]

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
