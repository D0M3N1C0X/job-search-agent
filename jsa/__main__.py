"""Command line interface: `python3 -m jsa <command>`."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from . import __version__, config
from .models import STATUSES, Job
from .packet import build_packet
from .render import Overlay, ats_check, build_cover, build_cv, output_name
from .score import explain, score_all
from .sources import ats as ats_sources
from .sources import linkedin, mailbox
from .store import Store
from .util import FetchError, days_between, log, read_json, setup_logging, today, write_json

GREEN, YELLOW, RED, DIM, BOLD, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def colour(text: str, code: str) -> str:
    return text if not sys.stdout.isatty() else f"{code}{text}{OFF}"


def verdict_colour(verdict: str) -> str:
    return {"pass": GREEN, "review": YELLOW}.get(verdict, RED)


# --------------------------------------------------------------- commands

def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path or (config.REPO_ROOT / "profile")).expanduser()
    if target.exists() and any(target.iterdir()) and not args.force:
        print(f"{target} already exists. Use --force to overwrite.")
        return 1
    target.mkdir(parents=True, exist_ok=True)
    for name in ("profile.json", "tracks.json", "watchlist.json"):
        source = config.REPO_ROOT / "profile.example" / name
        if source.exists():
            shutil.copy(source, target / name)
    (target / "inbox").mkdir(exist_ok=True)
    (target / "output").mkdir(exist_ok=True)
    print(f"Workspace ready in {target}")
    print("Next: edit profile.json with your details, then `python3 -m jsa fetch`.")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Find which ATS a company uses, without guessing."""
    for handle in args.handles:
        hits = ats_sources.probe(handle, args.provider)
        if not hits:
            print(f"{handle:<28} {colour('no board found', DIM)}")
            continue
        for provider, count in hits:
            print(f"{handle:<28} {colour(provider, GREEN):<22} {count} open roles")
            if args.add:
                _watchlist_add(args, handle, provider, count)
    return 0


def _watchlist_add(args: argparse.Namespace, handle: str, provider: str, count: int) -> None:
    cfg = config.load(args.home)
    path = cfg.home / "watchlist.json"
    data = read_json(path) if path.exists() else {"companies": []}
    company = args.company or handle.replace("-", " ").title()
    entry = {"company": company, "provider": provider, "handle": handle, "verified": today(), "open_roles": count}
    data["companies"] = [c for c in data["companies"]
                         if not (c["provider"] == provider and c["handle"] == handle)]
    data["companies"].append(entry)
    data["companies"].sort(key=lambda c: c["company"].lower())
    write_json(path, data)
    print(f"  added to watchlist: {company} ({provider}/{handle})")


def cmd_fetch(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    if cfg.demo:
        print(colour("Running on the bundled demo profile — `jsa init` to use your own.", YELLOW))
    store = Store(cfg.db_path)
    wanted = args.source
    totals = {"new": 0, "seen": 0, "failed": 0}

    if wanted in ("all", "ats"):
        entries = cfg.watchlist
        if args.company:
            needle = args.company.lower()
            entries = [e for e in entries if needle in e["company"].lower()]
        for entry in entries:
            try:
                jobs = ats_sources.fetch_company(entry, cache_dir=cfg.cache_dir, cache_ttl=args.cache_ttl)
            except Exception as exc:  # noqa: BLE001 - one bad board must not end the run
                totals["failed"] += 1
                print(f"{entry['company']:<32} "
                      f"{colour(f'{type(exc).__name__}: {exc}'[:70], RED)}")
                continue
            counts = {"new": 0, "seen": 0}
            for job in jobs:
                counts[store.upsert_job(job)] += 1
            store.mark_closed(jobs, entry["provider"])
            totals["new"] += counts["new"]
            totals["seen"] += counts["seen"]
            marker = colour(f"+{counts['new']}", GREEN) if counts["new"] else colour("+0", DIM)
            print(f"{entry['company']:<32} {entry['provider']:<16} {len(jobs):>3} listed  {marker}")

    if wanted in ("all", "linkedin"):
        queries = cfg.profile.get("search", {}).get("linkedin_queries", [])
        if queries:
            try:
                jobs = linkedin.search(queries=queries, pages=args.pages,
                                       with_descriptions=not args.fast, retries=1)
                counts = {"new": 0, "seen": 0}
                for job in jobs:
                    counts[store.upsert_job(job)] += 1
                totals["new"] += counts["new"]
                totals["seen"] += counts["seen"]
                print(f"{'LinkedIn (guest)':<32} {'linkedin':<16} {len(jobs):>3} listed  "
                      f"{colour('+' + str(counts['new']), GREEN)}")
            except Exception as exc:  # noqa: BLE001 - secondary source, best effort
                totals["failed"] += 1
                print(f"{'LinkedIn (guest)':<32} "
                      f"{colour(f'unavailable — {type(exc).__name__}: {exc}'[:80], YELLOW)}")

    if wanted in ("all", "mailbox"):
        try:
            jobs = mailbox.scan(path=cfg.inbox_dir)
            counts = {"new": 0, "seen": 0}
            for job in jobs:
                counts[store.upsert_job(job)] += 1
            totals["new"] += counts["new"]
            totals["seen"] += counts["seen"]
            print(f"{'Alert emails':<32} {'mailbox':<16} {len(jobs):>3} listed  "
                  f"{colour('+' + str(counts['new']), GREEN)}")
        except Exception as exc:  # noqa: BLE001 - a malformed mailbox is not fatal
            totals["failed"] += 1
            print(f"{'Alert emails':<32} "
                  f"{colour(f'unreadable — {type(exc).__name__}: {exc}'[:80], YELLOW)}")

    print()
    failed = (colour(f"{totals['failed']} sources failed", RED) if totals["failed"]
              else "0 sources failed")
    print(f"{colour(str(totals['new']), BOLD)} new · {totals['seen']} already known · {failed}")
    if totals["new"]:
        print("Next: `python3 -m jsa score` then `python3 -m jsa top`")
    store.close()
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    jobs = store.jobs() if args.rescore else [
        j for j in store.jobs() if not store.db.execute(
            "SELECT 1 FROM scores WHERE job_id = ?", (j.id,)).fetchone()
    ]
    verdicts = {"pass": 0, "review": 0, "reject": 0}
    for index, job in enumerate(jobs, 1):
        scores = score_all(job, cfg.profile, cfg.tracks)
        for score in scores:
            store.save_score(score, commit=False)
        verdicts[scores[0].verdict] += 1
        if index % 500 == 0:
            store.commit()
    store.commit()
    print(f"Scored {len(jobs)} job(s): "
          f"{colour(str(verdicts['pass']) + ' pass', GREEN)} · "
          f"{colour(str(verdicts['review']) + ' review', YELLOW)} · "
          f"{verdicts['reject']} reject")
    store.close()
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    """Recompute derived fields on stored jobs.

    Country and remote-ness are inferred from free-text locations. When that
    table improves, jobs already in the database should benefit too — otherwise
    a gate fixed today only applies to postings found tomorrow.
    """
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    changed = 0
    for job in store.jobs():
        country = ats_sources.guess_country(job.location)
        remote = ats_sources.guess_remote(job.location, job.title, job.description)
        if country != job.country or remote != job.remote:
            store.db.execute(
                "UPDATE jobs SET country = ?, remote = ? WHERE id = ?",
                (country, remote, job.id),
            )
            changed += 1
    store.commit()
    print(f"Updated location fields on {changed} job(s). Run `jsa score --rescore` next.")
    store.close()
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    """Fetch full descriptions for postings worth reading.

    Some boards list roles without bodies. Rather than pulling hundreds of
    descriptions blind, jobs are first scored on their title and location
    alone; only the plausible ones get a second request, and are then rescored
    on the full text.
    """
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    candidates = [j for j in store.jobs() if not j.description and not j.closed_at]
    ranked = sorted(
        ((score_all(j, cfg.profile, cfg.tracks)[0].score, j) for j in candidates),
        key=lambda pair: -pair[0],
    )
    picked = [job for score, job in ranked if score >= args.min_score][:args.limit]
    print(f"{len(candidates)} postings without a description · {len(picked)} worth fetching")

    filled = 0
    for job in picked:
        try:
            if job.source == "smartrecruiters":
                handle = job.raw.get("handle")
                if not handle:
                    continue
                job.description = ats_sources.smartrecruiters_detail(
                    handle, job.source_id, cache_dir=cfg.cache_dir)
            elif job.source in ("linkedin", "email:linkedin"):
                job.description = linkedin.fetch_description(job.source_id, retries=1)
            else:
                continue
        except FetchError as exc:
            log.debug("enrich %s: %s", job.id[:8], exc)
            continue
        if not job.description:
            continue
        store.upsert_job(job)
        for score in score_all(job, cfg.profile, cfg.tracks):
            store.save_score(score)
        filled += 1
    print(f"Filled {filled} description(s) and rescored them.")
    store.close()
    return 0


def cmd_top(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    rows = store.best_scores(
        min_score=args.min_score, track=args.track, limit=args.limit,
        include_closed=args.include_closed, include_applied=not args.new_only,
        include_rejected=args.include_rejected,
    )
    if not rows:
        print("Nothing above the threshold. Try --min-score 40 or fetch more sources.")
        return 0
    print(f"{'ID':<10}{'FIT':<5}{'VERDICT':<9}{'TRACK':<17}{'COMPANY':<24}"
          f"{'ROLE':<42}{'LOCATION':<22}STATUS")
    print("-" * 146)
    for row in rows:
        gates = row["breakdown"].get("gates") or []
        note = f"gated: {gates[0]['reason']}" if gates else (row["app_status"] or "")
        print(
            f"{row['id'][:8]:<10}{row['score']:<5}"
            f"{colour(row['verdict'], verdict_colour(row['verdict'])):<9}"
            f"{row['track']:<17}{row['company'][:22]:<24}{row['title'][:40]:<42}"
            f"{(row['location'] or '')[:20]:<22}{note}"
        )
    hidden = "" if args.include_rejected else " Rejected jobs hidden (--include-rejected to see them)."
    print(f"\n{len(rows)} shown.{hidden} `jsa show <ID>` for the full breakdown.")
    store.close()
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    job = store.get_job(args.job_id)
    if job is None:
        print(f"No job matching {args.job_id!r}")
        return 1
    print(f"{colour(job.title, BOLD)}  —  {job.company}")
    print(f"{job.location or 'location n/a'} · {job.remote} · {job.source} · first seen {job.first_seen[:10]}")
    print(job.url)
    if job.closed_at:
        print(colour(f"CLOSED (no longer listed as of {job.closed_at[:10]})", RED))
    print()
    for score in score_all(job, cfg.profile, cfg.tracks):
        print(explain(score))
    application = store.application(job.id)
    if application:
        print(f"\nApplication: {application['status']} (updated {application['last_update'][:10]})")
        if application.get("notes"):
            print(f"  {application['notes']}")
    if args.description:
        print("\n" + "-" * 70)
        print(job.description[:args.description])
    store.close()
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Manually add a posting — the always-works fallback."""
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    description = args.text or ""
    if args.file:
        description = Path(args.file).read_text(encoding="utf-8")
    job = Job(
        source="manual", company=args.company, title=args.title,
        url=args.url or "", location=args.location or "", description=description,
    )
    state = store.upsert_job(job)
    for score in score_all(job, cfg.profile, cfg.tracks):
        store.save_score(score)
    print(f"{state}: {job.id[:8]}  {job.title} @ {job.company}")
    print(explain(score_all(job, cfg.profile, cfg.tracks)[0]))
    store.close()
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    """Everything needed to tailor an application, as JSON on stdout.

    This is the hand-off point between the deterministic engine and the model:
    the engine decides *which* job and *why*, the model writes the words.
    """
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    job = store.get_job(args.job_id)
    if job is None:
        print(f"No job matching {args.job_id!r}", file=sys.stderr)
        return 1
    scores = score_all(job, cfg.profile, cfg.tracks)
    best = scores[0]
    track = cfg.track(args.track or best.track)
    brief = {
        "job": {
            "id": job.id, "company": job.company, "title": job.title, "url": job.url,
            "location": job.location, "remote": job.remote, "country": job.country,
            "posted_at": job.posted_at, "description": job.description,
        },
        "recommended_track": track["id"],
        "track": track,
        "scores": [{"track": s.track, "score": s.score, "verdict": s.verdict,
                    "breakdown": s.breakdown} for s in scores],
        "posting_language": best.breakdown.get("language", "en"),
        "profile": cfg.profile,
        "overlay_schema": {
            "track": "one of " + ", ".join(t["id"] for t in cfg.tracks),
            "summary": "optional replacement profile paragraph — factual only",
            "select": {"<company or project name>": ["exact bullet text from the profile"]},
            "skill_groups": "optional list of skill group keys to show, in order",
            "sections": "optional section order override",
            "extra_skills": "skills already true of the profile, surfaced for this posting",
        },
    }
    output = json.dumps(brief, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Brief written to {args.out}")
    else:
        print(output)
    store.close()
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    job = store.get_job(args.job_id)
    if job is None:
        print(f"No job matching {args.job_id!r}")
        return 1
    overlay_data = read_json(args.overlay) if args.overlay else {}
    overlay = Overlay.from_dict(overlay_data)
    track_id = args.track or overlay.track or score_all(job, cfg.profile, cfg.tracks)[0].track
    track = cfg.track(track_id)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cv_path = cfg.output_dir / output_name("CV", job.company, job.title)
    build_cv(cfg.profile, track, overlay=overlay, path=cv_path)
    print(f"CV        {cv_path}")

    cover_path = None
    letter = overlay_data.get("cover_letter")
    if letter:
        letter.setdefault("company", job.company)
        letter.setdefault("role", job.title)
        letter.setdefault("date", today())
        cover_path = cfg.output_dir / output_name("Cover", job.company, job.title)
        build_cover(cfg.profile, letter, path=cover_path)
        print(f"Cover     {cover_path}")

    report = ats_check(cv_path, cfg.profile, job.description, job.company)
    print()
    print(report.render())

    folder = build_packet(
        cfg, job, cv_path=cv_path, cover_path=cover_path, track=track,
        ats_report=report, notes=overlay_data.get("notes", ""),
    )
    print(f"\nPacket    {folder}/  (SUBMIT.md has the checklist and your standard answers)")
    if overlay.rejected:
        print(colour(f"\n{len(overlay.rejected)} overlay bullet(s) rejected — not in the profile:", RED))
        for bullet in overlay.rejected:
            print(f"  - {bullet[:100]}")
    store.set_status(
        job.id, "drafted", track=track_id,
        cv_path=str(cv_path), cover_path=str(cover_path) if cover_path else None,
    )
    store.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    job = store.get_job(args.job_id)
    if job is None:
        print(f"No job matching {args.job_id!r}")
        return 1
    if args.status not in STATUSES:
        print(f"Unknown status. Use one of: {', '.join(STATUSES)}")
        return 1
    follow_up = None
    if args.status == "submitted":
        days = cfg.profile.get("preferences", {}).get("follow_up_days", 10)
        follow_up = f"in {days} days"
    application = store.set_status(
        job.id, args.status, channel=args.channel, notes=args.note,
        next_action_at=args.next_action,
    )
    print(f"{job.company} — {job.title}: {colour(args.status, BOLD)}")
    if follow_up:
        print(f"Follow up {follow_up} (`jsa due` will remind you).")
    store.close()
    return 0


def cmd_due(args: argparse.Namespace) -> int:
    """What needs a nudge today — the discipline layer."""
    cfg = config.load(args.home)
    prefs = cfg.profile.get("preferences", {})
    follow_up_days = prefs.get("follow_up_days", 10)
    ghost_days = prefs.get("ghost_after_days", 28)
    store = Store(cfg.db_path)
    rows = store.applications(open_only=True)
    overdue, waiting = [], []
    for row in rows:
        age = days_between(row.get("submitted_at") or row["last_update"])
        if age is None:
            continue
        if row["status"] in ("shortlisted", "drafted", "ready"):
            if age >= 3:
                overdue.append((age, row, f"not sent yet — {age}d in {row['status']}"))
            else:
                waiting.append((age, row, f"{row['status']} {age}d ago"))
        elif row["status"] in ("submitted", "screening", "interview"):
            if age >= ghost_days:
                overdue.append((age, row, f"silent {age}d — mark ghosted?"))
            elif age >= follow_up_days:
                overdue.append((age, row, f"follow up ({age}d since update)"))
            else:
                waiting.append((age, row, f"{row['status']}, {age}d — follow up at {follow_up_days}d"))
    if not overdue and not waiting:
        print("Nothing in the tracker yet. `jsa top` to pick something, "
              "then `jsa status <id> shortlisted`.")
        store.close()
        return 0
    by_age = lambda item: item[0]  # noqa: E731
    for age, row, why in sorted(overdue, key=by_age, reverse=True):
        print(f"{colour('!', YELLOW)} {row['company'][:24]:<26}{row['title'][:38]:<40}{why}")
    for age, row, why in sorted(waiting, key=by_age, reverse=True):
        print(f"  {row['company'][:24]:<26}{row['title'][:38]:<40}{colour(why, DIM)}")
    if not overdue:
        print(f"\n{len(waiting)} open, nothing overdue.")
    store.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from .dashboard import funnel_stats

    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    counts = store.counts()
    stats = funnel_stats(store)
    print(f"{colour('Pipeline', BOLD)}")
    for key, value in counts.items():
        print(f"  {key:<16}{value}")
    print(f"\n{colour('Funnel', BOLD)}")
    for status in STATUSES:
        n = stats["by_status"].get(status, 0)
        if n:
            print(f"  {status:<16}{n}")
    if stats["response_rate"] is not None:
        print(f"\n  response rate   {stats['response_rate']:.0%} "
              f"({stats['responded']}/{stats['submitted']} submitted)")
    if stats["median_response_days"] is not None:
        print(f"  median reply    {stats['median_response_days']} days")
    for track, data in sorted(stats["by_track"].items()):
        print(f"  {track:<16}{data['submitted']} sent · {data['responded']} replies")
    store.close()
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import build_dashboard

    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    out = Path(args.out or (cfg.output_dir / "dashboard.html"))
    build_dashboard(store, cfg, out)
    print(f"Dashboard written to {out}")
    store.close()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """The whole loop in one command.

    Fetch, fill in the descriptions worth fetching, score, refresh the
    dashboard. This is what you run on a Monday morning; every other command
    exists for when you want a piece of it on its own.
    """
    ns = lambda **kw: argparse.Namespace(home=args.home, **kw)  # noqa: E731

    print(colour("1/4  Fetching", BOLD))
    cmd_fetch(ns(source=args.source, company=None, pages=args.pages,
                 fast=args.fast, cache_ttl=args.cache_ttl))

    print(colour("\n2/4  Filling in descriptions", BOLD))
    cmd_enrich(ns(min_score=args.enrich_min_score, limit=args.enrich_limit))

    print(colour("\n3/4  Scoring", BOLD))
    cmd_score(ns(rescore=args.rescore))

    print(colour("\n4/4  Shortlist", BOLD))
    cmd_top(ns(min_score=args.min_score, track=None, limit=args.limit,
               new_only=False, include_closed=False, include_rejected=False))

    cfg = config.load(args.home)
    out = cfg.output_dir / "dashboard.html"
    store = Store(cfg.db_path)
    from .dashboard import build_dashboard

    build_dashboard(store, cfg, out)
    store.close()
    print(f"\nDashboard  {out}")
    if args.serve:
        from .serve import serve

        serve(cfg, port=args.port)
    else:
        print("Open it, or run `python3 -m jsa serve` for the editable version.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .serve import serve

    cfg = config.load(args.home)
    if cfg.demo:
        print(colour("Running on the bundled demo profile — `jsa init` to use your own.", YELLOW))
    serve(cfg, host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Build a synthetic workspace and open the dashboard on it."""
    from .demo import DEMO_HOME, build
    from .serve import serve

    print("Building a demo workspace on invented data — nothing is fetched.")
    cfg = build(count=args.count)
    store = Store(cfg.db_path)
    counts = store.counts()
    cleared = len(store.best_scores(min_score=0, limit=999))
    store.close()
    print(f"{counts['jobs']} synthetic postings · {cleared} cleared the gates · "
          f"{counts['applications']} walked into the tracker")
    print(f"Workspace: {DEMO_HOME}  (delete it, or run `jsa demo` again to rebuild)\n")
    if args.no_serve:
        print(f"Open it with: JSA_HOME={DEMO_HOME} python3 -m jsa serve")
        return 0
    serve(cfg, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """Make the tool reachable: a `jsa` command anywhere, and an app in the Dock."""
    from .install import install

    result = install(port=args.port, at_login=args.login)

    print(f"{colour('Command', BOLD)}")
    print(f"  {result['shim']}")
    if result["shim_on_path"]:
        print(f"  {colour('jsa', GREEN)} now works from any directory — try `jsa where`.")
    else:
        print(colour(f"  {result['shim'].parent} is not on your PATH.", YELLOW))
        print(f"  Add this line to ~/.zshrc, then open a new terminal:")
        print(f"    export PATH=\"{result['shim'].parent}:$PATH\"")

    if result["app"]:
        print(f"\n{colour('App', BOLD)}")
        print(f"  {result['app']}")
        print("  Open it from Spotlight (⌘-Space, \"Job Pipeline\") or drag it to your Dock.")
        print("  It starts the server if it is down, then opens the dashboard.")
    if result["agent"]:
        print("\n  The server will also start automatically when you log in.")
    elif result["app"]:
        print("\n  Add `--login` to keep the server running in the background.")
    print("\nRemove all of it with: jsa uninstall")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    from .install import uninstall

    removed = uninstall()
    if not removed:
        print("Nothing was installed.")
        return 0
    for path in removed:
        print(f"Removed {path}")
    return 0


def cmd_where(args: argparse.Namespace) -> int:
    """Say plainly where things are and whether the dashboard is up."""
    from .install import APP_PATH, status

    cfg = config.load(args.home)
    state = status(args.port)
    url = f"http://127.0.0.1:{state['port']}/"
    print(f"{colour('Dashboard', BOLD)}")
    print(f"  address        {url}")
    print(f"  server         {colour('running', GREEN) if state['server_running'] else colour('not running', YELLOW)}")
    print(f"  app installed  {'yes — ' + str(APP_PATH) if state['app'] else 'no (run `jsa install`)'}")
    if state["command"]:
        note = "" if state["command_on_path"] else "  (its folder is not on your PATH)"
        print(f"  jsa command    {state['command']}{note}")
    else:
        print("  jsa command    not installed (run `python3 -m jsa install`)")
    print(f"  starts at login{'  yes' if state['login_agent'] else '  no'}")
    print(f"\n{colour('Files', BOLD)}")
    print(f"  profile        {cfg.home}")
    print(f"  database       {cfg.db_path}")
    print(f"  documents      {cfg.output_dir}")
    if not state["server_running"]:
        print(f"\nStart it with: python3 -m jsa serve")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    cfg = config.load(args.home)
    store = Store(cfg.db_path)
    rows = store.applications()
    out = Path(args.out or (cfg.output_dir / "applications.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["company", "title", "location", "track", "status", "channel",
              "created_at", "submitted_at", "last_update", "url", "notes"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} applications → {out}")
    store.close()
    return 0


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jsa", description="job-search-agent — find, score, apply, track.")
    parser.add_argument("--version", action="version", version=f"job-search-agent {__version__}")
    parser.add_argument("--home", help="profile directory (default: ./profile or $JSA_HOME)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="fetch, enrich, score and refresh the dashboard — the daily command")
    p.add_argument("--source", choices=["all", "ats", "linkedin", "mailbox"], default="all")
    p.add_argument("--min-score", type=int, default=65, help="threshold for the shortlist it prints")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--fast", action="store_true", help="skip LinkedIn description fetches")
    p.add_argument("--cache-ttl", type=int, default=900)
    p.add_argument("--enrich-min-score", type=int, default=30)
    p.add_argument("--enrich-limit", type=int, default=120)
    p.add_argument("--rescore", action="store_true")
    p.add_argument("--serve", action="store_true", help="open the editable dashboard when done")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("serve", help="editable dashboard on localhost (writes back to the database)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("demo", help="see it working on synthetic data, without fetching anything")
    p.add_argument("--count", type=int, default=90, help="how many synthetic postings to generate")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-serve", action="store_true", help="build the workspace and stop")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("install", help="put the dashboard in the Dock as a macOS app")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--login", action="store_true", help="also keep the server running from login")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="remove the app and the login agent")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("where", help="where everything lives and whether the dashboard is up")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_where)

    p = sub.add_parser("init", help="create a profile workspace from the example")
    p.add_argument("path", nargs="?")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("probe", help="discover which ATS a company uses")
    p.add_argument("handles", nargs="+", help="candidate board slugs, e.g. revolut monzo")
    p.add_argument("--provider", action="append", help="restrict to one provider")
    p.add_argument("--add", action="store_true", help="add hits to the watchlist")
    p.add_argument("--company", help="display name when adding")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("fetch", help="pull jobs from every configured source")
    p.add_argument("--source", choices=["all", "ats", "linkedin", "mailbox"], default="all")
    p.add_argument("--company", help="only this watchlist company")
    p.add_argument("--pages", type=int, default=2, help="LinkedIn pages per query")
    p.add_argument("--fast", action="store_true", help="skip LinkedIn description fetches")
    p.add_argument("--cache-ttl", type=int, default=900)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("score", help="score jobs against every track")
    p.add_argument("--rescore", action="store_true", help="re-score everything, not just new jobs")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("reindex", help="recompute country/remote on stored jobs")
    p.set_defaults(func=cmd_reindex)

    p = sub.add_parser("enrich", help="fetch descriptions for promising postings, then rescore")
    p.add_argument("--min-score", type=int, default=30, help="title-only score needed to spend a request")
    p.add_argument("--limit", type=int, default=120)
    p.set_defaults(func=cmd_enrich)

    p = sub.add_parser("top", help="ranked shortlist")
    p.add_argument("--min-score", type=int, default=60)
    p.add_argument("--track")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--new-only", action="store_true", help="hide jobs already in the tracker")
    p.add_argument("--include-closed", action="store_true")
    p.add_argument("--include-rejected", action="store_true",
                   help="also show jobs a hard gate rejected")
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("show", help="full score breakdown for one job")
    p.add_argument("job_id")
    p.add_argument("--description", type=int, nargs="?", const=2000, default=0,
                   help="also print the first N characters of the posting")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("add", help="add a posting by hand")
    p.add_argument("--company", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--url")
    p.add_argument("--location")
    p.add_argument("--text", help="posting text")
    p.add_argument("--file", help="file containing the posting text")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("brief", help="dump everything needed to tailor an application (JSON)")
    p.add_argument("job_id")
    p.add_argument("--track")
    p.add_argument("--out")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("docs", help="generate CV (+ cover letter) for a job")
    p.add_argument("job_id")
    p.add_argument("--overlay", help="tailoring overlay JSON")
    p.add_argument("--track")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("status", help="move an application along the funnel")
    p.add_argument("job_id")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--note")
    p.add_argument("--channel")
    p.add_argument("--next-action")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("due", help="what needs a follow-up")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("stats", help="pipeline and funnel numbers")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("dashboard", help="export the dashboard as a static HTML file")
    p.add_argument("--out")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("export", help="applications as CSV")
    p.add_argument("--out")
    p.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
