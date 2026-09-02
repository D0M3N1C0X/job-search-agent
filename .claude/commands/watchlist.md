---
description: Find each company's applicant tracking system and add it to the watchlist
argument-hint: <company names or slugs>
---

Companies: $ARGUMENTS

For each one, work out the plausible board slugs (the company name lowercased,
hyphenated, without legal suffixes; check their careers page URL if you are
unsure — the ATS is usually visible in it) and run:

`python3 -m jsa probe <slug> ... --add`

Report which companies were found, on which ATS, and how many roles each has
open. For any not found, say so plainly and suggest the alternative: a job
alert email from their careers page, or manual entry.

Do not add a company whose board you could not verify — an unverified entry is
a source that silently returns nothing, which is the failure mode this whole
design exists to avoid.
