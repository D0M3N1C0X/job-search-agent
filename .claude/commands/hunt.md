---
description: Fetch, enrich, score and present the current shortlist
---

Run the pipeline and give a read on what came out.

1. `python3 -m jsa fetch` — report per-source counts honestly, including any
   source that failed or returned nothing.
2. `python3 -m jsa enrich` then `python3 -m jsa score`.
3. `python3 -m jsa top --new-only --min-score 60`.

Then, for the top handful, open each posting's breakdown (`jsa show <id>`) and
add what the score cannot see: whether the title matches the actual work,
whether the requirement list is real, the honest gap, and whether the engine
picked the right track. Rank them by "worth your next hour", not by score.

End with a single recommendation: which one to apply to first, and why.

If nothing scored above 60, say so and diagnose it — thin watchlist, a track
whose keywords are too narrow, or a genuinely quiet week — rather than padding
the list with weak matches.
