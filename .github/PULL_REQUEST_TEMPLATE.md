## What this changes

<!-- One or two sentences. What was wrong, and what it does now. -->

## How it was checked

<!-- `python3 -m unittest discover -s tests -t .` at minimum. For a source
     adapter, say which real board you ran it against. -->

## Checklist

- [ ] No new runtime dependency (see CONTRIBUTING.md — this one is not negotiable)
- [ ] Tests pass offline and in under a second
- [ ] A new source adapter separates fetching from parsing, with a fixture test
- [ ] Nothing from `profile/` is included, and `profile.example/` stays synthetic
