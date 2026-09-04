# Contributing

Thanks for looking. This is a personal tool that happens to be useful to other
people, so the bar is "does it stay simple enough that one person can maintain
it", not "does it have every feature".

## The one rule that shapes everything

**No runtime dependencies.** Not one. The `.docx` writer is `zipfile` and
string building; the server is `http.server`; the dashboard is hand-written CSS
and vanilla JavaScript. This is not asceticism — it means the project still runs
in three years, on a locked-down work laptop, without a virtual environment.

A pull request that adds a dependency needs an argument that survives the
question *"could this be forty lines of standard library instead?"*. Usually it
could.

## What is most useful

**New ATS providers.** The backbone of this project is boards that publish JSON
without a key. Seven are supported. If you know another (Teamtailor, JOIN,
Softgarden, Jobvite, iCIMS, Taleo…) and it serves an unauthenticated feed, that
is the highest-value contribution there is. See `jsa/sources/ats.py`: each
provider is a fetch function and a parse function, deliberately separate so the
parser can be tested against a captured payload with no network.

**Companies for the watchlist.** `jsa probe <slug>` tells you which board a
company uses. Verified entries are welcome, especially outside the EU tech
bubble the current list leans on.

**Scoring that is wrong.** If a posting scores in a way you can show is wrong,
open an issue with the posting text and `jsa show <id>` output. Scoring is
configuration and rules, so this is fixable rather than a matter of opinion.

**Bugs.** Especially in the sources: a board changes its shape and the adapter
quietly returns nothing. That failure mode is the reason this project exists.

## What is unlikely to be merged

- Anything that submits an application on the user's behalf. Applicant tracking
  systems do not expose public submission endpoints, and a form is a signature.
  The tool prepares the packet; a human presses send.
- Scraping a portal that defends itself. It works until it doesn't, silently,
  and that is the failure this project was built to avoid.
- A web framework, an ORM, a build step, or a package manager for the frontend.
- Making the language model do work the rules can do. If a step can be a rule,
  it belongs in the code, where it can be tested.

## Working on it

```bash
git clone https://github.com/D0M3N1C0X/job-search-agent && cd job-search-agent
python3 -m jsa demo                      # a synthetic workspace, nothing fetched
python3 -m unittest discover -s tests -t .
```

The test suite runs offline in about a second and must stay that way. CI runs
it on Python 3.10 through 3.13.

**Every source adapter separates fetching from parsing.** `greenhouse()` does
the request; `parse_greenhouse()` turns a payload into `Job` objects. Tests
exercise the parser against a small captured payload, so adding a provider means
adding a fixture, not a network call.

**Tests are named after the behaviour they protect**, not the function they
call. `test_remote_does_not_rescue_a_role_in_an_excluded_country` says what
breaks if it fails.

## Style

British spelling. Comments explain *why*, never *what* — if a line needs a
comment to say what it does, rewrite the line. Commit messages say what changed
and what it fixes, in prose.

## Privacy

`profile/` holds real personal data and is git-ignored. Never commit anything
from it, and keep `profile.example/` entirely synthetic. If you open an issue,
redact your own contact details out of any pasted output.
