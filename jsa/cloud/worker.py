"""The online beta's worker: the same engine, run for every member.

    python3 -m jsa.cloud.worker --once     one pass of everything, then exit
    python3 -m jsa.cloud.worker            stay up: queues every 30 s, the
                                           catalogue and scoring once a day

What it does, in order of urgency:

1. CV uploads. A member's file is read with the same parser as `jsa import`,
   turned into a profile and then deleted from storage, whatever happens.
2. Score requests. After onboarding or a change of countries or roles, that
   member's feed is recomputed straight away.
3. Once a day: every board in the shared catalogue is fetched once for
   everybody, postings that stop appearing are closed, and every member is
   rescored.

Only the worker writes to `jobs` and `scores`; it uses the service-role key,
which must never leave the server.
"""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ..config import EXAMPLE_DIR, load_catalogue
from ..cvimport import UnreadableCV, parse, read_text, to_profile
from ..italian import mentions_italian
from ..models import Job
from ..places import country_cards, guide_urls
from ..score import score_all
from ..sources import ats
from ..util import log
from .rest import Supabase

BUCKET = "cv-uploads"
DESCRIPTION_CHARS = 2000      # what the app shows; scoring reads the full text in memory
MAX_SCORES_PER_MEMBER = 600   # the feed, not an archive
MIN_SCORE_KEPT = 35
CLOSE_AFTER = timedelta(days=2)
DAILY_HOUR_UTC = 5
POLL_SECONDS = 30
FETCH_WORKERS = 8


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ profiles

def blank_profile() -> dict[str, Any]:
    """A member's starting profile: the engine's shape with nobody's data in it."""
    example = json.loads((EXAMPLE_DIR / "profile.json").read_text(encoding="utf-8"))
    return {
        "identity": {"name": "", "headline": "", "location": "", "email": "", "phone": ""},
        "years_experience": 0,
        "summaries": {},
        "skill_groups": {},
        "experience": [],
        "projects": {"items": []},
        "education": [],
        "research": [],
        "additional_experience": [],
        "languages": [{"code": "it", "name": "Italian", "level": "native"}],
        "certifications": [],
        "preferences": {
            **{k: copy.deepcopy(v) for k, v in example["preferences"].items()
               if k in ("relocation", "remote_ok", "follow_up_days", "ghost_after_days")},
            "locations_preferred": [],
            "countries_allowed": [],
            "countries_blocked": [],
            "seniority_target": ["junior", "mid", "senior"],
            "seniority_reject": [],
            "language_gates": [],
            "hard_reject_keywords": ["unpaid internship", "commission only"],
            "soft_reject_keywords": [],
        },
        "search": {},
    }


def track_library() -> dict[str, dict[str, Any]]:
    data = json.loads((EXAMPLE_DIR / "tracks.library.json").read_text(encoding="utf-8"))
    return {t["id"]: t for t in data["tracks"]}


def engine_profile(row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """What the scorer needs for one member: their profile and their chosen tracks."""
    profile = copy.deepcopy(row.get("profile") or {}) or blank_profile()
    prefs = profile.setdefault("preferences", {})
    prefs["countries_allowed"] = list(row.get("countries") or [])
    library = track_library()
    tracks = [library[t] for t in (row.get("tracks") or []) if t in library]
    return profile, tracks


# ---------------------------------------------------------------- CV imports

def read_cv(data: bytes, filename: str) -> dict[str, Any]:
    """CV bytes -> engine profile. Raises UnreadableCV with a reason a person can act on."""
    suffix = Path(filename).suffix.lower() or ".pdf"
    with tempfile.TemporaryDirectory(prefix="jsa-cv-") as tmp:
        path = Path(tmp) / f"cv{suffix}"
        path.write_bytes(data)
        text, _how = read_text(path)
    return to_profile(parse(text, filename), blank_profile())


def process_imports(db: Supabase) -> int:
    pending = db.select("cv_imports", {"status": "eq.pending", "order": "created_at.asc", "limit": "20"})
    for item in pending:
        status, error = "done", None
        try:
            profile = read_cv(db.download(BUCKET, item["path"]), item["path"])
            existing = db.select("profiles", {"user_id": f"eq.{item['user_id']}", "select": "user_id"})
            row = {"user_id": item["user_id"], "profile": profile, "updated_at": utcnow().isoformat()}
            if not existing:
                row["countries"] = list(profile.get("preferences", {}).get("countries_allowed", []))
            db.upsert("profiles", [row], on_conflict="user_id")
        except UnreadableCV as exc:
            status, error = "failed", str(exc).splitlines()[0][:300]
        except Exception as exc:  # noqa: BLE001 - one bad upload must not stop the queue
            status, error = "failed", f"{type(exc).__name__}: {exc}"[:300]
            log.warning("cv import %s failed: %s", item["id"], error)
        finally:
            # The file goes whatever happened: the profile is what we keep.
            try:
                db.remove(BUCKET, [item["path"]])
            except Exception as exc:  # noqa: BLE001
                log.warning("could not delete %s: %s", item["path"], exc)
        db.update("cv_imports", {"id": f"eq.{item['id']}"},
                  {"status": status, "error": error, "done_at": utcnow().isoformat()})
    return len(pending)


# ------------------------------------------------------------------ postings

def job_row(job: Job, seen: str) -> dict[str, Any]:
    return {
        "id": job.id, "source": job.source, "company": job.company, "title": job.title,
        "location": job.location, "country": job.country, "remote": job.remote, "url": job.url,
        "posted_at": job.posted_at, "italian": mentions_italian(job.title, job.description),
        "description": job.description[:DESCRIPTION_CHARS], "last_seen": seen, "closed_at": None,
    }


def fetch_catalogue(boards: list[dict[str, Any]] | None = None) -> list[Job]:
    """Every catalogue board, once, for everybody. A board that fails is skipped."""
    boards = boards if boards is not None else load_catalogue()

    def one(entry: dict[str, Any]) -> list[Job]:
        try:
            return ats.fetch_company(entry, retries=2, timeout=30)
        except Exception as exc:  # noqa: BLE001
            log.info("board %s/%s: %s", entry.get("provider"), entry.get("handle"), exc)
            return []

    jobs: dict[str, Job] = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        for batch in pool.map(one, boards):
            for job in batch:
                jobs.setdefault(job.id, job)
    return list(jobs.values())


def sync_jobs(db: Supabase, jobs: list[Job]) -> None:
    seen = utcnow().isoformat()
    db.upsert("jobs", [job_row(j, seen) for j in jobs], on_conflict="id")
    cutoff = (utcnow() - CLOSE_AFTER).isoformat()
    db.update("jobs", {"last_seen": f"lt.{cutoff}", "closed_at": "is.null"}, {"closed_at": seen})


def sync_countries(db: Supabase) -> None:
    guides = guide_urls()
    rows = [{"code": code, "facts": card, "guide_url": guides.get(code, "")}
            for code, card in country_cards().items()]
    db.upsert("countries", rows, on_conflict="code")


# -------------------------------------------------------------------- scores

def score_member(db: Supabase, member: dict[str, Any], jobs: list[Job]) -> int:
    profile, tracks = engine_profile(member)
    if not tracks:
        return 0
    allowed = set(profile["preferences"]["countries_allowed"])
    rows = []
    for job in jobs:
        if allowed and job.country and job.country not in allowed:
            continue
        best = score_all(job, profile, tracks)[0]
        if best.score >= MIN_SCORE_KEPT and best.verdict != "reject":
            rows.append({"user_id": member["user_id"], "job_id": job.id, "track": best.track,
                         "score": best.score, "verdict": best.verdict, "breakdown": best.breakdown,
                         "scored_at": utcnow().isoformat()})
    rows.sort(key=lambda r: -r["score"])
    rows = rows[:MAX_SCORES_PER_MEMBER]
    db.delete("scores", {"user_id": f"eq.{member['user_id']}"})
    db.upsert("scores", rows, on_conflict="user_id,job_id")
    return len(rows)


def open_jobs(db: Supabase) -> list[Job]:
    """Open postings as the scorer needs them (bodies are the shortened ones)."""
    out: list[Job] = []
    offset = 0
    while True:
        page = db.select("jobs", {"closed_at": "is.null", "select": "*", "order": "id",
                                  "limit": "1000", "offset": str(offset)})
        for row in page:
            out.append(Job(source=row["source"], company=row["company"], title=row["title"],
                           url=row["url"], location=row["location"], country=row["country"],
                           remote=row["remote"], description=row["description"],
                           posted_at=row["posted_at"], id=row["id"]))
        if len(page) < 1000:
            return out
        offset += 1000


def process_score_requests(db: Supabase, jobs_loader: Callable[[], list[Job]]) -> int:
    requests = db.select("score_requests", {"order": "requested_at.asc", "limit": "20"})
    if not requests:
        return 0
    jobs = jobs_loader()
    for req in requests:
        member = db.select("profiles", {"user_id": f"eq.{req['user_id']}"})
        if member:
            score_member(db, member[0], jobs)
        db.delete("score_requests", {"user_id": f"eq.{req['user_id']}"})
    return len(requests)


def daily(db: Supabase) -> None:
    sync_countries(db)
    jobs = fetch_catalogue()
    log.info("catalogue: %d postings", len(jobs))
    sync_jobs(db, jobs)
    members = db.select("profiles", {"onboarded": "eq.true"})
    for member in members:
        score_member(db, member, jobs)
    log.info("scored %d members", len(members))


# ---------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--once", action="store_true", help="one full pass, then exit")
    args = parser.parse_args()
    db = Supabase.from_env()
    cache: dict[str, Any] = {}

    def jobs_loader() -> list[Job]:
        if "jobs" not in cache or time.monotonic() - cache["at"] > 3600:
            cache["jobs"], cache["at"] = open_jobs(db), time.monotonic()
        return cache["jobs"]

    if args.once:
        process_imports(db)
        daily(db)
        process_score_requests(db, jobs_loader)
        return 0

    last_day = None
    while True:
        try:
            process_imports(db)
            process_score_requests(db, jobs_loader)
            now = utcnow()
            if now.hour >= DAILY_HOUR_UTC and last_day != now.date():
                daily(db)
                cache.clear()
                last_day = now.date()
        except Exception as exc:  # noqa: BLE001 - the loop outlives any one failure
            log.warning("worker pass failed: %s", exc)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
