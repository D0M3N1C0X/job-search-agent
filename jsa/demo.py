"""A working pipeline in ten seconds, on invented data.

`python3 -m jsa demo` builds a throwaway workspace, fills it with synthetic
postings and opens the dashboard. Nothing is fetched, nobody's servers are
touched, and no personal data is involved — it exists so someone evaluating
this repository can see the thing run before deciding whether to point it at
their own job search.

The generator is seeded, so the demo is identical on every machine and in CI.
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any

from .config import REPO_ROOT, load
from .sources.ats import guess_country
from .models import Job
from .score import score_all
from .store import Store

DEMO_HOME = REPO_ROOT / ".demo"
SEED = 20260904

COMPANIES = [
    ("Northwind Labs", "greenhouse"), ("Vessel Bank", "lever"), ("Kestrel Health", "ashby"),
    ("Blue Harbour", "smartrecruiters"), ("Meridian Retail", "workable"),
    ("Auralis", "recruitee"), ("Tramonto Group", "personio"), ("Fenner & Vale", "greenhouse"),
    ("Sparrow Logistics", "lever"), ("Calder Energy", "ashby"),
]

PLACES = [
    ("Amsterdam, Netherlands", "hybrid"), ("Rotterdam, Netherlands", "onsite"),
    ("Berlin, Germany", "hybrid"), ("Lisbon, Portugal", "remote"),
    ("Barcelona, Spain", "hybrid"), ("Dublin, Ireland", "onsite"),
    ("Remote - EU", "remote"), ("Milan, Italy", "onsite"),
    ("Tokyo, Japan", "onsite"), ("Austin, US", "hybrid"),
]

# Titles the demo profile should match, titles it should half-match, and
# titles a good scorer must reject. A demo that only shows wins teaches
# nothing about the scoring.
TITLES = {
    "strong": ["HR Operations Specialist", "People Operations Partner", "Employee Relations Advisor",
               "People Analytics Analyst", "HR Advisor", "People Operations Coordinator",
               "HR Services Specialist", "Workforce Reporting Analyst"],
    "middling": ["HR Systems Analyst", "Reward Analyst", "Talent Acquisition Partner",
                 "People Operations Manager", "Senior HR Business Partner", "HRIS Administrator"],
    "wrong": ["Backend Engineer", "Warehouse Supervisor", "Field Sales Representative",
              "Growth Product Analyst", "Head of People", "Registered Nurse",
              "Financial Controller", "Customer Support Associate"],
}

BLOCKS = {
    "strong": [
        "You will own employee relations cases end to end, applying HR policy across our European entities.",
        "Day to day this means leave, payroll queries, onboarding and the employee lifecycle, worked through our ticketing system against documented SOPs.",
        "You will work with employee data under GDPR, and turn recurring case patterns into process improvements.",
        "We use an HRIS and expect comfort in Excel; SQL is welcome but not required.",
    ],
    "analytics": [
        "You will build the reporting layer for our people team: attrition, retention and headcount.",
        "Expect to work in SQL and Python, publish dashboards, and present findings to the HR leadership team.",
        "Experience with engagement survey analysis, pay equity or pay transparency reporting is a strong plus.",
        "You will handle employee data under GDPR and design the confidentiality thresholds yourself.",
    ],
    "middling": [
        "You will support the people team with systems administration and reporting.",
        "Some exposure to HR processes is expected; most of the role is configuration and stakeholder management.",
        "The team is distributed across three countries and works in English.",
    ],
    "wrong": [
        "You will design, build and maintain services in a distributed architecture.",
        "Experience with containers, cloud infrastructure and on-call rotations is required.",
        "This role reports into the engineering organisation.",
    ],
}

EXTRAS = [
    "We work in English across all our markets.",
    "Fluent Dutch is required for this role.",
    "This is a fixed-term contract for twelve months.",
    "You will need around 8 years of experience in a comparable role.",
    "We offer a hybrid arrangement of two days in the office.",
    "This position is commission only.",
]


def synthesise(count: int = 90) -> list[Job]:
    """Deterministic postings across the whole quality range."""
    rng = random.Random(SEED)
    jobs: list[Job] = []
    for index in range(count):
        bucket = rng.choices(["strong", "middling", "wrong"], weights=[4, 3, 3])[0]
        title = rng.choice(TITLES[bucket])
        company, provider = rng.choice(COMPANIES)
        location, remote = rng.choice(PLACES)
        body = "strong" if bucket == "strong" else bucket
        if bucket == "strong" and "Analytics" in title or "Reporting" in title:
            body = "analytics"
        lines = list(BLOCKS[body if body in BLOCKS else "middling"])
        if rng.random() < 0.45:
            lines.append(rng.choice(EXTRAS))
        rng.shuffle(lines)
        jobs.append(Job(
            source=provider,
            source_id=f"demo-{index}",
            company=company,
            title=title,
            url=f"https://example.invalid/jobs/{index}",
            location=location,
            # Real adapters derive this on the way in; the demo has to do the
            # same or the country gate has nothing to test against.
            country=guess_country(location),
            remote=remote,
            description=f"About {company}\n\n" + "\n".join(lines),
            posted_at="2026-09-01",
        ))
    return jobs


def build(home: Path = DEMO_HOME, count: int = 90) -> Any:
    """Create the workspace, seed it, score it. Returns the loaded config."""
    if home.exists():
        shutil.rmtree(home)
    shutil.copytree(REPO_ROOT / "profile.example", home)
    cfg = load(home)
    store = Store(cfg.db_path)
    for job in synthesise(count):
        store.upsert_job(job)
        for score in score_all(job, cfg.profile, cfg.tracks):
            store.save_score(score, commit=False)
    store.commit()

    # A funnel with nothing in it teaches nothing, so walk a few applications
    # far enough along that the Pipeline and Insights tabs have something real
    # to draw. Deterministic, like everything else here.
    ranked = store.best_scores(min_score=70, limit=8)
    journey = ["submitted", "submitted", "interview", "rejected", "shortlisted", "drafted"]
    for row, status in zip(ranked, journey):
        store.set_status(row["id"], "shortlisted", track=row["track"])
        if status != "shortlisted":
            store.set_status(row["id"], "submitted" if status != "drafted" else "drafted")
        if status in ("interview", "rejected"):
            store.set_status(row["id"], status)
    store.close()
    return cfg
