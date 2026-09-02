"""Dataclasses shared across the pipeline."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Any

from .util import html_to_text, now

# Application lifecycle. Order matters: it drives the funnel chart.
STATUSES = [
    "shortlisted",   # worth a look, nothing drafted yet
    "drafted",       # CV + cover letter generated
    "ready",         # reviewed by a human, waiting to be sent
    "submitted",     # sent
    "screening",     # recruiter call / assessment
    "interview",     # interview stage(s)
    "offer",
    "rejected",
    "withdrawn",
    "ghosted",       # no reply past the follow-up horizon
]
OPEN_STATUSES = {"shortlisted", "drafted", "ready", "submitted", "screening", "interview"}
CLOSED_STATUSES = {"offer", "rejected", "withdrawn", "ghosted"}

_WS = re.compile(r"\s+")
_NOISE = re.compile(
    r"\b(m/f/d|f/m/d|w/m/d|m/w/d|all genders|remote|hybrid|onsite|full[- ]time|part[- ]time|"
    r"contract|permanent|temporary|fixed[- ]term|internship|maternity cover|\d{4})\b",
    re.I,
)


def canonical(value: str | None) -> str:
    """Lowercase, punctuation-light form used for matching and dedup."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9+#/ ]+", " ", value)
    return _WS.sub(" ", value).strip()


def normalize_title(title: str | None) -> str:
    """Strip the boilerplate that makes the same role look like two roles."""
    t = canonical(title)
    t = _NOISE.sub(" ", t)
    t = re.sub(r"\(.*?\)", " ", t)
    return _WS.sub(" ", t).strip()


@dataclass(slots=True)
class Job:
    source: str
    company: str
    title: str
    url: str
    source_id: str = ""
    location: str = ""
    country: str = ""
    remote: str = "unknown"          # onsite | hybrid | remote | unknown
    description: str = ""
    posted_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    first_seen: str = ""
    last_seen: str = ""
    closed_at: str = ""

    def __post_init__(self) -> None:
        if "<" in self.description and ">" in self.description:
            self.description = html_to_text(self.description)
        self.title = (self.title or "").strip()
        self.company = (self.company or "").strip()
        if not self.id:
            self.id = self.fingerprint()
        stamp = now()
        self.first_seen = self.first_seen or stamp
        self.last_seen = self.last_seen or stamp

    def fingerprint(self) -> str:
        """Stable identity across sources.

        Company + normalised title + city is deliberately URL-independent: the
        same role posted on Greenhouse, LinkedIn and an email alert collapses
        into one row instead of three.
        """
        city = canonical(self.location).split(",")[0].strip()
        key = "|".join([canonical(self.company), normalize_title(self.title), city])
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def text(self) -> str:
        """Everything a scorer should read."""
        return "\n".join([self.title, self.company, self.location, self.description])

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["raw"] = json.dumps(self.raw, ensure_ascii=False)
        # SQL treats "" and NULL differently; `closed_at` is queried with
        # IS NULL, so an empty string would silently hide every open job.
        row["closed_at"] = self.closed_at or None
        return row

    @classmethod
    def from_row(cls, row: Any) -> "Job":
        data = dict(row)
        raw = data.get("raw") or "{}"
        try:
            data["raw"] = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data["raw"] = {}
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: (v if v is not None else "") for k, v in data.items() if k in allowed})


@dataclass(slots=True)
class Score:
    job_id: str
    track: str
    score: int
    verdict: str                      # pass | review | reject
    breakdown: dict[str, Any] = field(default_factory=dict)
    scored_at: str = ""
    scorer_version: str = ""

    def __post_init__(self) -> None:
        self.scored_at = self.scored_at or now()
