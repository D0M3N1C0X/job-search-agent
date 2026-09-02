---
description: Review scoring mistakes and fix the tracks that caused them
---

Scoring is configuration, not intuition — when it is wrong, fix the config.

1. `python3 -m jsa top --min-score 0 --limit 60` and look for **false
   negatives**: roles you would have applied to that scored low. Run
   `jsa show <id>` on each and find which dimension underscored them.
2. Look for **false positives**: high scores on roles that are obviously wrong.
   Usually a title keyword that is too generic, or a missing anti-keyword.
3. Propose specific edits to `profile/tracks.json` — a keyword added to
   `titles.good`, an `anti` term, a changed `must_have_target`. Show the diff.
4. Apply the edits, then `python3 -m jsa score --rescore` and show what moved.

Never adjust a single job's score by hand. If one job needs an exception, the
rule is wrong.
