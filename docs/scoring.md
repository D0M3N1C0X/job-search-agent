# How fit scoring works

Scoring is a pure function of `(job, profile, track)`. The same posting always
produces the same number, and the number always comes with a breakdown showing
which words earned which points. Nothing here calls a language model.

## Gates run first

A gate is a fact that ends the conversation, regardless of how well everything
else scores:

| Gate | Fires when |
|---|---|
| `language` | The posting demands a language above the profile's level. Sixteen languages are recognised without any setup, asked for in English (*"fluent Dutch"*, *"Dutch is a must"*, *"Dutch (fluent)"*, *"French mother tongue"*, *"German-speaking"*) or in the language itself (*"vloeiend Nederlands"*, *"biegła znajomość języka polskiego"*). A language merely named is not a requirement: *"Dutch is a plus"*, *"free Dutch lessons"* and *"our Dutch entities"* ask for nothing, and *"fluent German or English"* is met by English. `language_gates` in the profile adds patterns for anything else |
| `location` | The role is in a country outside the target list and is not remote |
| `seniority` | The title reads as a level the profile is not applying to (`head`, `director`, `VP`, `chief`), or the role is an internship and the profile has two years of experience or more. The body can make a role senior or junior, never a head of function: *"reporting to the Head of HR"* names the manager |
| `experience` | The posting asks five or more years beyond the profile's. Only years asked of the candidate count: *"trading for 25 years"* and *"in the past 3 years our headcount tripled"* do not; a range counts from its lower end |
| `keyword` | A hard-reject term appears (unpaid internship, commission-only, …) |
| `terms` | The posting describes unpaid or commission-only work |

A gated job scores whatever it scores and is still marked `reject`, with the
reason attached — so it can be reviewed, not silently discarded.

Asking three or four years beyond the profile is not a gate but a cap: the
posting can score anything up to `review`, never `pass`. It is worth reading,
not worth preparing on autopilot.

## Five weighted dimensions

| Dimension | Points | How it is earned |
|---|---:|---|
| Title | 30 | A `strong` title keyword takes all 30; `good` 70%; `weak` 40%; a keyword found only in the body, 20% |
| Skills | 30 | 70% from `must_have_any` coverage, 30% from `nice_to_have`, each capped at its target count |
| Domain | 15 | Domain vocabulary present in the posting, capped at its target |
| Location | 15 | Full for remote or a preferred city; 80% for a target country when relocation is on; 50% when unknown; 20% outside the targets |
| Seniority | 10 | Full when the detected level is in `seniority_target`, decaying by distance; a further penalty of 1.5 per year the posting asks for beyond the profile, capped at 6 |

Penalties subtract 6 points per anti-keyword, 18 when it is in the title (where
it names the job: *"Software Engineer, HR Tech"*), capped at 25.

Thresholds: **≥70 pass · 45–69 review · <45 reject.**

## Matching is word-boundary aware

Terms are compared against a canonicalised form of the posting — lowercased,
punctuation stripped, `&` expanded — with boundaries on both sides. `"hr"` does
not match *"through"*, and `"sql"` does not match *"nosql-adjacent"*. A term of
four letters or more also matches its plain plural (`dashboard` finds
*dashboards*, `hr policy` finds *HR policies*); shorter ones do not, so `hr`
never finds *hrs*. This is
why single-letter skills (`R`) are written as something longer (`Stata`,
`RStudio`) in the track configuration: a bare letter cannot be matched safely.

## Tracks, not one profile

Every job is scored against every track and the highest score wins. That is the
whole mechanism behind "the same person is several candidates": a posting for
*People Analytics Analyst* wins on the analytics track and gets a CV that leads
with projects and Python; a posting for *HR Advisor with Italian* wins on the
advisory track and gets one that leads with case work and jurisdictions.

If the engine keeps picking the wrong track, that is a bug in
`profile/tracks.json`, not a reason to override a job by hand. Use `/tune`.

## How often it is right

`jsa evaluate` scores 130 labelled postings ([evaluation/](../evaluation/README.md))
and compares each verdict with what a person reading the posting for the
example candidate decided. The figures to quote are the **held-out** ones: 30
postings written after the last change to the rules and scored once.

| Held-out, 30 postings | Scorer 1.0.0 | Scorer 1.1.0 |
|---|---:|---:|
| Scored as labelled | 15 | 20 |
| Of the postings scored pass, labelled apply (precision) | 54% | 73% |
| Of the postings labelled apply, scored pass (recall) | 70% | 80% |
| Skips scored as a pass | 5 | 2 |
| Applies rejected | 0 | 0 |
| Language requirements caught | 0 of 7 | 4 of 7 |

On the 100 development postings, which the rules were fixed against and so
flatter them, 1.1.0 scores 88 as labelled (1.0.0: 66).

What it still gets wrong on the held-out set, said plainly:

- **Language requirements worded as a duty, not a level**: *"you must be able
  to work in French every day"*, *"German and English, both at business level,
  are a must"*, or written in Italian in a phrasing the patterns do not know.
  Three of seven slipped through; one of them scored a pass.
- **A different profession that shares the vocabulary**: a payroll
  administrator role with an Irish payroll qualification required scored a
  pass on the advisory track. Payroll appears in advisory work too, and the
  rules cannot tell a profession from a task.
- **Terms of work written as a story**: *"no fixed salary; your income is your
  commission"* passed the terms gate, which looks for *commission only*.
- **"Eight or more years of experience"** is not read as a number of years: the
  words between the number and "years" hide it. The role (an *HR Lead*) scored
  review instead of being rejected.

None of these rejected a posting worth applying to. Every posting labelled
apply was at least kept for review, on both sets: the errors that remain cost
reading time, not missed applications.

## Against your own decisions

`jsa evaluate --mine` compares the scorer with what you did: the postings you
drafted or sent against those you pressed skip on. It says what share of your
applications the scorer passed, what share of your dismissals it passed, and
which pass mark would have agreed with you most often. Below twenty decisions it
says that the numbers are a hint, not a measurement.

## Tuning it

1. `jsa top --min-score 0` and look for roles you would have applied to that
   scored low — false negatives.
2. `jsa show <id>` shows which dimension underscored them.
3. Edit the track's keyword lists or targets.
4. `jsa score --rescore` and compare.

Scores carry `scorer_version`, so a rescore after a change is visible in the
database rather than silently rewriting history.
