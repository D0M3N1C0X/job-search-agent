# Security

This is a personal tool that runs on your own machine, reads other people's
job postings, and holds your CV and your application history. Those three
facts decide what "secure" means here.

## Reporting a problem

Please report it privately, not as a public issue:
**[Report a vulnerability](https://github.com/D0M3N1C0X/job-search-agent/security/advisories/new)**
(the *Security* tab of the repository).

Say what you ran, what happened, and — if you can — a posting, email or file
that triggers it. Leave your own contact details and CV out of it.

This is maintained by one person. Expect an acknowledgement within a week and a
fix, or a plain explanation of why it is not one, as soon as it can be done
properly. Fixes land on `main` and in the next release; only the latest release
is supported.

## What it is built to withstand

**Postings, emails and company pages are data, never instructions.** Everything
the tool fetches is written by strangers, and it is treated that way wherever
it is shown or used:

- The dashboard escapes every field it renders, embeds its data so that a
  posting cannot close the `<script>` element carrying it, and ships a
  Content-Security-Policy that lets only its own scripts run.
- Only `http(s)` links survive: a `javascript:` or `file:` URL in a feed is
  dropped before it reaches a link, a browser or macOS `open`.
- Text from postings reaches desktop notifications only as a quoted literal or
  a process argument, never through a shell.
- Responses larger than 32 MB, gzip bodies that inflate past that, and CV files
  that are not plausibly CVs are refused rather than read into memory.

**The local dashboard (`jsa serve`) answers this machine only.** It binds to
127.0.0.1, refuses peers and `Host` headers that are not local (which stops DNS
rebinding), and accepts a write only with a token that exists inside the page
it served — so a web page open in another tab cannot change a status, a note,
or start a run.

**Nothing is sent on your behalf.** The tool never submits an application,
sends an email, creates an account or types into a form you did not open. The
form-filling bookmarklet runs only when you click it, on a page you opened, and
never touches a submit button.

**Your data stays in `profile/`**, which is git-ignored. There are no accounts,
no API keys and no telemetry; the only outbound requests are to the job boards
you list and, if you enable it, LinkedIn's guest search.

## What it does not try to defend against

- Anyone who can already run code as your user account. The database and the
  profile are ordinary files in your home directory.
- Exposing `jsa serve` to a network (`--host 0.0.0.0` and the like). It is not
  a service; do not do this.
- The job boards themselves. A board can list a fake role; the tool scores what
  it is given.

## Platforms

macOS and Linux are supported and tested in CI. Windows works on a best-effort
basis and is not tested; desktop notifications are deliberately disabled there.
