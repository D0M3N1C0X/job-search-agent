---
description: Evaluate a posting, tailor the documents, build the submission packet
argument-hint: <job-id or URL or pasted posting>
---

Target: $ARGUMENTS

If it is a job id, run `python3 -m jsa brief <id> --out /tmp/brief.json` and read
it. If it is a URL, fetch it, then `python3 -m jsa add` it so it enters the
pipeline. If it is pasted text, `jsa add --file`.

**1. Assess before drafting.** Read the full posting and the deterministic
breakdown. Present: the real work behind the title, the two or three
requirements that actually decide this hire, the honest gap, the right track,
and a recommendation. If the answer is "do not apply", say that and stop.

**2. Write the overlay.** Select bullets by exact text from `profile.json` —
copy, never paraphrase into the `select` field. Reorder skill groups toward the
posting. Rewrite the summary only if the track's default genuinely misses the
role. Anything you add to `extra_skills` must already be true.

**3. Write the cover letter** into the overlay's `cover_letter` block, in the
posting's language (English or Italian only — never Polish), following the
style rules in CLAUDE.md. Verify any claim you make about the company by
actually looking it up in this session.

**4. Generate and check.**
`python3 -m jsa docs <id> --overlay profile/output/overlay_<company>.json`
Read the ATS report back. If keywords are missing, decide honestly whether the
profile supports them; if it does not, leave the gap and say so.

**5. Hand over.** Tell the user where the packet is, what is in it, what still
needs their decision, and remind them the send is theirs. Then
`python3 -m jsa status <id> ready`.
