# Changelog

What changed in each release, for the people running it. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/): a new major version means something
you set up by hand (profile, tracks, database) needs attention.

## [Unreleased]

## [1.0.0] — unreleased

The first public release.

### The pipeline

- `jsa run` fetches, enriches, scores, shortlists and rebuilds the dashboard in
  one command; `jsa daily` does the same and notifies only when something new
  clears the threshold or something is overdue.
- Sources: seven applicant tracking systems (Greenhouse, Lever, Ashby,
  SmartRecruiters, Recruitee, Workable, Personio) through their public board
  APIs, job-alert emails saved as `.eml`/`.mbox`, LinkedIn guest search on a
  best-effort basis, and `jsa add` by hand. `jsa probe` finds which board a
  company uses.
- Deterministic, explainable 0–100 scoring per positioning track, with hard
  gates for language level, country, seniority and unpaid or commission-only
  roles, and country detection across Europe.
- `jsa apply` builds the packet in one step: tailored CV, draft cover letter,
  standard answers, an ATS keyword check and a local page with a form-filling
  bookmarklet. Nothing is ever submitted.
- `jsa import` reads an existing CV (`.docx`, `.pdf`, text); `jsa setup` builds
  the profile from questions and a library of eight tracks.
- The dashboard: a triage deck, the full table, a pipeline board and funnel
  charts, in English and Italian. `jsa dashboard` exports it; `jsa serve` runs
  it locally with statuses and notes written to SQLite.
- `jsa install` puts `jsa` on PATH and, on macOS, adds a Dock app and optional
  login and daily schedules. `jsa doctor` diagnoses the setup.
- Installable as a package (`pipx install git+https://github.com/D0M3N1C0X/job-search-agent`,
  or the wheel attached to each release): the workspace then lives in `~/.jsa`
  and scratch files in `~/.cache/job-search-agent`. From a clone it stays in
  `./profile`.

### Hardened before release

- **Security:** a web page open in another tab could write to `jsa serve`
  (cross-site request forgery); writes now need a per-server token.
- **Security:** a posting title containing `</script>` could run script in the
  dashboard; embedded data is now escaped and the page has a
  Content-Security-Policy.
- **Security:** `javascript:` and `file:` links from feeds reached links and
  macOS `open`; only http(s) links are kept.
- **Security:** on Windows, job titles were interpolated into a PowerShell
  command; the notification call is removed.
- The dashboard's *Run pipeline* button ran against the default workspace
  instead of the one on screen (visible with `jsa demo` or `--home`).
- `jsa setup`, `init` and `import` ignored `JSA_HOME` and wrote to `./profile`
  while every other command read from `JSA_HOME`. Background jobs installed on
  macOS now carry `JSA_HOME` too, since launchd does not inherit the shell's.
- `jsa demo` no longer inherits a `jobs.db` left in the example profile by an
  earlier run.
- `jsa fetch` flags a board that suddenly returns nothing after listing open
  roles, instead of printing it as a normal empty board.
- Oversized HTTP responses, gzip bombs, and PDF or DOCX files that inflate past
  any plausible CV are refused; a `.docx` that is not one gets an explanation
  instead of a traceback.
- CI runs on Linux (Python 3.10–3.13) and macOS, with ruff and CodeQL.

[Unreleased]: https://github.com/D0M3N1C0X/job-search-agent/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/D0M3N1C0X/job-search-agent/releases/tag/v1.0.0
