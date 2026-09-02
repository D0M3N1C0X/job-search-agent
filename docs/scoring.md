# How fit scoring works

Scoring is a pure function of `(job, profile, track)`. The same posting always
produces the same number, and the number always comes with a breakdown showing
which words earned which points. Nothing here calls a language model.

## Gates run first

A gate is a fact that ends the conversation, regardless of how well everything
else scores:

| Gate | Fires when |
|---|---|
| `language` | The posting demands a language above the profile's level — matched by explicit patterns like *"fluent Polish"* or *"biegła znajomość języka polskiego"*, not by the language merely appearing |
| `location` | The role is in a country outside the target list and is not remote |
| `seniority` | The title reads as a level the profile is not applying to (`head`, `director`, `VP`, `chief`) |
| `keyword` | A hard-reject term appears (unpaid internship, commission-only, …) |
| `terms` | The posting describes unpaid or commission-only work |

A gated job scores whatever it scores and is still marked `reject`, with the
reason attached — so it can be reviewed, not silently discarded.

## Five weighted dimensions

| Dimension | Points | How it is earned |
|---|---:|---|
| Title | 30 | A `strong` title keyword takes all 30; `good` 70%; `weak` 40%; a keyword found only in the body, 20% |
| Skills | 30 | 70% from `must_have_any` coverage, 30% from `nice_to_have`, each capped at its target count |
| Domain | 15 | Domain vocabulary present in the posting, capped at its target |
| Location | 15 | Full for remote or a preferred city; 80% for a target country when relocation is on; 50% when unknown; 20% outside the targets |
| Seniority | 10 | Full when the detected level is in `seniority_target`, decaying by distance; a further penalty of 1.5 per year the posting asks for beyond the profile, capped at 6 |

Penalties subtract 6 points per anti-keyword, capped at 25.

Thresholds: **≥70 pass · 45–69 review · <45 reject.**

## Matching is word-boundary aware

Terms are compared against a canonicalised form of the posting — lowercased,
punctuation stripped, `&` expanded — with boundaries on both sides. `"hr"` does
not match *"through"*, and `"sql"` does not match *"nosql-adjacent"*. This is
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

## Tuning it

1. `jsa top --min-score 0` and look for roles you would have applied to that
   scored low — false negatives.
2. `jsa show <id>` shows which dimension underscored them.
3. Edit the track's keyword lists or targets.
4. `jsa score --rescore` and compare.

Scores carry `scorer_version`, so a rescore after a change is visible in the
database rather than silently rewriting history.
