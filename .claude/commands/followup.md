---
description: What is overdue, with drafted follow-up messages
---

Run `python3 -m jsa due`.

For each overdue item, decide what it actually needs:

- **Not sent yet** — ask why. If it has sat for a week, it is either not worth
  applying to (mark it `withdrawn` and move on) or it is avoidance. Say which
  you think it is.
- **Silent past the follow-up horizon** — draft a short follow-up message,
  four sentences at most, that adds something rather than just asking. Address
  it to a real person if the application had one.
- **Silent past the ghosting horizon** — recommend marking it `ghosted` and
  closing the loop mentally.

Show the drafts; do not send anything. Sending is the user's.

Finish with the funnel in one line (`python3 -m jsa stats`) and one observation
about what it suggests — for example, a track that gets replies and one that
does not.
