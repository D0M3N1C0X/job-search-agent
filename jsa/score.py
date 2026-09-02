"""Deterministic fit scoring.

Why deterministic: an LLM asked "is this a good fit?" gives a different answer
on Tuesday than on Monday, and cannot be tested. Here the score is a pure
function of (job, profile, track) — same input, same number, every time, with
a breakdown that says exactly which words earned which points. The language
model is still used, but downstream: for judgement calls the rules cannot
make (nuance, tailoring, cover letters), on a shortlist this has already
narrowed and explained.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import Job, Score, canonical, normalize_title

SCORER_VERSION = "1.0.0"

# Points available per dimension. They sum to 100.
WEIGHTS = {
    "title": 30,
    "skills": 30,
    "domain": 15,
    "location": 15,
    "seniority": 10,
}

PASS_AT = 70
REVIEW_AT = 45

SENIORITY_PATTERNS = [
    ("intern", r"\b(intern|internship|stagiaire|stage|praktyk|traineeship|working student|werkstudent)\b"),
    ("junior", r"\b(junior|jr\.?|entry[- ]level|graduate|apprentice|associate i\b)\b"),
    ("mid", r"\b(mid[- ]level|specialist|analyst|advisor|consultant|associate|officer|coordinator|partner)\b"),
    ("senior", r"\b(senior|sr\.?|lead\b|principal|expert|manager)\b"),
    ("head", r"\b(head of|director|vp\b|vice president|chief|cxo|c-level|partner \(equity\))\b"),
]
SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "head"]

# Rough language identification, enough to pick the cover-letter language.
LANG_MARKERS = {
    "it": r"\b(e|di|il|la|per|con|del|della|dei|nostro|azienda|ricerca|candidat[oi]|requisiti|offriamo)\b",
    "pl": r"\b(i|w|na|do|oraz|firma|praca|wymagania|oferujemy|stanowisko|umowa|zespo)\b",
    "es": r"\b(y|de|la|el|para|con|empresa|puesto|requisitos|ofrecemos)\b",
    "fr": r"\b(et|de|le|la|pour|avec|entreprise|poste|exigences|nous offrons)\b",
    "en": r"\b(and|the|for|with|you|we|role|team|experience|requirements|responsibilities)\b",
}

_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|anni|lat[a]?|jahre)\b", re.I)


def detect_language(text: str) -> str:
    """Best-guess language of a posting, used to choose the cover-letter language."""
    sample = canonical((text or "")[:4000])
    if not sample:
        return "en"
    hits = {lang: len(re.findall(pat, sample)) for lang, pat in LANG_MARKERS.items()}
    best = max(hits, key=lambda k: hits[k])
    return best if hits[best] >= 3 else "en"


def detect_seniority(title: str, description: str = "") -> str:
    blob = f" {canonical(title)} "
    for level, pattern in reversed(SENIORITY_PATTERNS):  # most senior wins
        if re.search(pattern, blob):
            return level
    for level, pattern in reversed(SENIORITY_PATTERNS):
        if re.search(pattern, canonical(description)[:1500]):
            return level
    return "mid"


def required_years(text: str) -> int:
    """Highest 'N years of experience' figure stated in the posting."""
    numbers = [int(n) for n in _YEARS.findall(text or "") if int(n) <= 25]
    return max(numbers, default=0)


# Keyword lists are reused across thousands of postings, so each list is
# compiled once into a single alternation and matched in one pass. Searching
# term by term meant hundreds of scans of every description; this is one.
_MATCHERS: dict[tuple[str, ...], tuple[re.Pattern[str] | None, dict[str, str]]] = {}


def _matcher(terms: list[str]) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    key = tuple(terms)
    if key not in _MATCHERS:
        mapping: dict[str, str] = {}
        for term in terms:
            needle = canonical(term)
            if needle:
                mapping.setdefault(needle, term)
        parts = sorted(map(re.escape, mapping), key=len, reverse=True)
        pattern = (
            re.compile(r"(?<![a-z0-9])(" + "|".join(parts) + r")(?![a-z0-9])")
            if parts else None
        )
        _MATCHERS[key] = (pattern, mapping)
    return _MATCHERS[key]


def _matches(terms: list[str], haystack: str) -> list[str]:
    """Which of `terms` appear in `haystack` (already canonicalised)."""
    pattern, mapping = _matcher(terms)
    if pattern is None:
        return []
    hits = {mapping[found] for found in pattern.findall(haystack) if found in mapping}
    return [term for term in terms if term in hits]


@dataclass(slots=True)
class Gate:
    """A hard rule. Failing one rejects the job whatever the score."""

    name: str
    reason: str


def check_gates(job: Job, profile: dict[str, Any], text: str | None = None) -> list[Gate]:
    prefs = profile.get("preferences", {})
    text = canonical(job.text()) if text is None else text
    failures: list[Gate] = []

    # Language: a role that demands a language above the candidate's level is
    # not a fit, however good everything else looks.
    levels = {l["code"]: l.get("level", "") for l in profile.get("languages", [])}
    order = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]
    for rule in prefs.get("language_gates", []):
        code = rule["code"]
        if not re.search(rule["pattern"], text, re.I):
            continue
        have = levels.get(code, "")
        need = rule.get("min_level", "C1")
        have_i = order.index(have) if have in order else -1
        need_i = order.index(need) if need in order else len(order)
        if have_i < need_i:
            failures.append(Gate(
                "language",
                f"requires {code.upper()} at ~{need} (profile: {have or 'none'})",
            ))

    blocked = [canonical(c) for c in prefs.get("countries_blocked", [])]
    if job.country and canonical(job.country) in blocked:
        failures.append(Gate("location", f"country {job.country} is excluded"))

    allowed = prefs.get("countries_allowed") or []
    if allowed and job.country and job.country not in allowed and job.remote != "remote":
        failures.append(Gate("location", f"{job.country} outside target countries"))

    for term in prefs.get("hard_reject_keywords", []):
        if _matches([term], text):
            failures.append(Gate("keyword", f"posting mentions '{term}'"))

    seniority = detect_seniority(job.title, job.description)
    if seniority in prefs.get("seniority_reject", []):
        failures.append(Gate("seniority", f"role reads as '{seniority}'"))

    if re.search(r"\b(commission[- ]only|unpaid|no salary|volunteer)\b", text):
        failures.append(Gate("terms", "unpaid or commission-only"))

    return failures


def score_job(job: Job, profile: dict[str, Any], track: dict[str, Any],
              text: str | None = None) -> Score:
    """Score one job against one positioning track.

    `text` is the canonicalised posting; `score_all` computes it once and
    passes it in, since canonicalising a long description for every track is
    the difference between scoring five thousand postings in seconds or in
    minutes.
    """
    text = canonical(job.text()) if text is None else text
    title_c = normalize_title(job.title)
    prefs = profile.get("preferences", {})
    breakdown: dict[str, Any] = {}
    total = 0.0

    # --- title -----------------------------------------------------------
    titles = track.get("titles", {})
    strong = _matches(titles.get("strong", []), title_c)
    good = _matches(titles.get("good", []), title_c)
    weak = _matches(titles.get("weak", []), title_c)
    if strong:
        title_points = WEIGHTS["title"]
    elif good:
        title_points = WEIGHTS["title"] * 0.7
    elif weak:
        title_points = WEIGHTS["title"] * 0.4
    else:
        # Nothing in the title, but the body may still describe the job.
        body_hits = _matches(titles.get("strong", []) + titles.get("good", []), text)
        title_points = WEIGHTS["title"] * 0.2 if body_hits else 0.0
    breakdown["title"] = {
        "points": round(title_points, 1), "max": WEIGHTS["title"],
        "strong": strong, "good": good, "weak": weak,
    }
    total += title_points

    # --- skills ----------------------------------------------------------
    must = track.get("must_have_any", [])
    nice = track.get("nice_to_have", [])
    must_hits = _matches(must, text)
    nice_hits = _matches(nice, text)
    must_ratio = min(1.0, len(must_hits) / max(1, track.get("must_have_target", 3)))
    nice_ratio = min(1.0, len(nice_hits) / max(1, track.get("nice_to_have_target", 5)))
    skill_points = WEIGHTS["skills"] * (0.7 * must_ratio + 0.3 * nice_ratio)
    breakdown["skills"] = {
        "points": round(skill_points, 1), "max": WEIGHTS["skills"],
        "must_have": must_hits, "nice_to_have": nice_hits,
    }
    total += skill_points

    # --- domain ----------------------------------------------------------
    domain_hits = _matches(track.get("domain", []), text)
    domain_points = WEIGHTS["domain"] * min(1.0, len(domain_hits) / max(1, track.get("domain_target", 3)))
    breakdown["domain"] = {
        "points": round(domain_points, 1), "max": WEIGHTS["domain"], "matched": domain_hits,
    }
    total += domain_points

    # --- location --------------------------------------------------------
    preferred = [canonical(c) for c in prefs.get("locations_preferred", [])]
    loc_c = canonical(job.location)
    if job.remote == "remote" and prefs.get("remote_ok", True):
        location_points, location_why = WEIGHTS["location"], "remote"
    elif any(city and city in loc_c for city in preferred):
        location_points, location_why = WEIGHTS["location"], "preferred city"
    elif job.country in (prefs.get("countries_allowed") or []):
        base = WEIGHTS["location"] * (0.8 if prefs.get("relocation") else 0.5)
        location_points = base + (WEIGHTS["location"] * 0.1 if job.remote == "hybrid" else 0)
        location_why = f"target country ({job.country})"
    elif not job.country:
        location_points, location_why = WEIGHTS["location"] * 0.5, "location unknown"
    else:
        location_points, location_why = WEIGHTS["location"] * 0.2, f"outside targets ({job.country})"
    breakdown["location"] = {
        "points": round(location_points, 1), "max": WEIGHTS["location"],
        "why": location_why, "value": job.location or "-", "remote": job.remote,
    }
    total += location_points

    # --- seniority -------------------------------------------------------
    seniority = detect_seniority(job.title, job.description)
    targets = prefs.get("seniority_target", ["junior", "mid"])
    years_needed = required_years(job.description)
    years_have = int(profile.get("years_experience", 0))
    if seniority in targets:
        sen_points = WEIGHTS["seniority"]
    else:
        distance = abs(SENIORITY_ORDER.index(seniority) - SENIORITY_ORDER.index(targets[-1]))
        sen_points = max(0.0, WEIGHTS["seniority"] - 4.0 * distance)
    stretch = max(0, years_needed - years_have)
    sen_points = max(0.0, sen_points - min(6.0, 1.5 * stretch))
    breakdown["seniority"] = {
        "points": round(sen_points, 1), "max": WEIGHTS["seniority"],
        "detected": seniority, "years_required": years_needed, "years_profile": years_have,
    }
    total += sen_points

    # --- penalties -------------------------------------------------------
    anti_hits = _matches(track.get("anti", []) + prefs.get("soft_reject_keywords", []), text)
    penalty = min(25.0, 6.0 * len(anti_hits))
    if anti_hits:
        breakdown["penalties"] = {"points": -round(penalty, 1), "matched": anti_hits}
    total -= penalty

    # --- gates -----------------------------------------------------------
    gates = check_gates(job, profile, text)
    if gates:
        breakdown["gates"] = [{"gate": g.name, "reason": g.reason} for g in gates]

    final = max(0, min(100, round(total)))
    if gates:
        verdict = "reject"
    elif final >= PASS_AT:
        verdict = "pass"
    elif final >= REVIEW_AT:
        verdict = "review"
    else:
        verdict = "reject"

    breakdown["language"] = detect_language(job.description or job.title)
    breakdown["total"] = final
    return Score(
        job_id=job.id, track=track["id"], score=final, verdict=verdict,
        breakdown=breakdown, scorer_version=SCORER_VERSION,
    )


def score_all(job: Job, profile: dict[str, Any], tracks: list[dict[str, Any]]) -> list[Score]:
    """Score a job against every track. The best track is the one to apply on."""
    text = canonical(job.text())
    return sorted(
        (score_job(job, profile, t, text) for t in tracks),
        key=lambda s: s.score, reverse=True,
    )


def explain(score: Score) -> str:
    """Human-readable one-screen justification of a score."""
    b = score.breakdown
    lines = [f"{score.track}: {score.score}/100 → {score.verdict.upper()}"]
    for dim in ("title", "skills", "domain", "location", "seniority"):
        if dim not in b:
            continue
        d = b[dim]
        detail = ""
        if dim == "title":
            hits = d["strong"] + d["good"] + d["weak"]
            detail = ", ".join(hits[:4]) or "no title keyword"
        elif dim == "skills":
            detail = ", ".join((d["must_have"] + d["nice_to_have"])[:6]) or "no skill overlap"
        elif dim == "domain":
            detail = ", ".join(d["matched"][:5]) or "no domain signal"
        elif dim == "location":
            detail = f"{d['value']} — {d['why']}"
        elif dim == "seniority":
            detail = f"{d['detected']}, {d['years_required']}y required"
        lines.append(f"  {dim:<10} {d['points']:>5}/{d['max']:<3} {detail}")
    if "penalties" in b:
        lines.append(f"  {'penalty':<10} {b['penalties']['points']:>5}     {', '.join(b['penalties']['matched'])}")
    for gate in b.get("gates", []):
        lines.append(f"  GATE       {gate['gate']}: {gate['reason']}")
    return "\n".join(lines)
