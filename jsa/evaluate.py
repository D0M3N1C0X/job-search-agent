"""How often the scorer is right, measured two ways.

`benchmark()` scores the hand-labelled postings in evaluation/postings.json
against the example profile and compares each verdict with what a person
reading the posting for that candidate decided: apply, maybe, or skip, with
the rule that ends the conversation where there is one.

`own_decisions()` does the same against what you actually did: the postings
you prepared or sent against the ones you dismissed. The benchmark says whether
the rules are right; your own decisions say whether your tracks are.

Both are plain counting. Nothing here changes a score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Job, Score
from .score import PASS_AT, REVIEW_AT, score_all
from .sources.ats import guess_country, guess_remote

# What a person decides, and the verdict that means the same thing.
DECISIONS = {"apply": "pass", "maybe": "review", "skip": "reject"}
VERDICTS = ("pass", "review", "reject")


@dataclass(slots=True)
class Row:
    """One labelled posting, with what the scorer made of it."""

    id: str
    title: str
    company: str
    expected: str                     # pass | review | reject
    got: str
    score: int
    track: str
    expected_track: str | None
    expected_gate: str | None
    gates: list[str] = field(default_factory=list)
    why: str = ""

    @property
    def right(self) -> bool:
        return self.expected == self.got

    @property
    def serious(self) -> bool:
        """A skip scored as a pass, or an apply rejected: the two errors that cost something."""
        return {self.expected, self.got} == {"pass", "reject"}


def load_postings(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a list of postings")
    return data


def to_job(posting: dict[str, Any]) -> Job:
    """Built the way an adapter builds it: country and remote are read from the text."""
    location = posting.get("location", "")
    return Job(
        source="benchmark", source_id=posting["id"], company=posting["company"], title=posting["title"],
        url=f"https://example.invalid/benchmark/{posting['id']}", location=location,
        country=guess_country(location),
        remote=guess_remote(location, posting["title"], posting.get("description", "")),
        description=posting.get("description", ""),
    )


def judge(posting: dict[str, Any], best: Score) -> Row:
    expect = posting["expect"]
    return Row(
        id=posting["id"], title=posting["title"], company=posting["company"],
        expected=DECISIONS[expect["decision"]], got=best.verdict, score=best.score, track=best.track,
        expected_track=expect.get("track"), expected_gate=expect.get("gate"),
        gates=[g["gate"] for g in best.breakdown.get("gates", [])], why=expect.get("why", ""),
    )


def benchmark(postings: list[dict[str, Any]], profile: dict[str, Any],
              tracks: list[dict[str, Any]]) -> list[Row]:
    return [judge(p, score_all(to_job(p), profile, tracks)[0]) for p in postings]


def _ratio(hits: int, total: int) -> float | None:
    return hits / total if total else None


def summarise(rows: list[Row]) -> dict[str, Any]:
    """Every figure the report prints, as numbers."""
    matrix = {e: {g: 0 for g in VERDICTS} for e in VERDICTS}
    for r in rows:
        matrix[r.expected][r.got] += 1
    passed = [r for r in rows if r.got == "pass"]
    to_apply = [r for r in rows if r.expected == "pass"]

    gates: dict[str, dict[str, int]] = {}
    for r in rows:
        if r.expected_gate:
            g = gates.setdefault(r.expected_gate, {"expected": 0, "fired": 0, "wrongly": 0})
            g["expected"] += 1
            g["fired"] += r.expected_gate in r.gates
    for r in rows:
        if r.expected != "reject":           # a gate on a posting worth reading is always wrong
            for name in set(r.gates):
                gates.setdefault(name, {"expected": 0, "fired": 0, "wrongly": 0})["wrongly"] += 1

    # The track only matters where there is something to send.
    tracked = [r for r in rows if r.expected_track and r.expected != "reject"]
    return {
        "postings": len(rows),
        "right": sum(r.right for r in rows),
        "accuracy": _ratio(sum(r.right for r in rows), len(rows)),
        "matrix": matrix,
        "passed": len(passed),
        "precision": _ratio(sum(r.expected == "pass" for r in passed), len(passed)),
        "to_apply": len(to_apply),
        "recall": _ratio(sum(r.got == "pass" for r in to_apply), len(to_apply)),
        "kept": _ratio(sum(r.got != "reject" for r in to_apply), len(to_apply)),
        "wasted": [r.id for r in rows if r.expected == "reject" and r.got == "pass"],
        "missed": [r.id for r in rows if r.expected == "pass" and r.got == "reject"],
        "gates": gates,
        "tracked": len(tracked),
        "track_right": sum(r.track == r.expected_track for r in tracked),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def report(rows: list[Row], *, misses: bool = True) -> str:
    s = summarise(rows)
    name = {"pass": "apply", "review": "maybe", "reject": "skip"}
    out = [
        f"{s['postings']} labelled postings · {s['right']} scored as labelled ({_pct(s['accuracy'])})",
        "",
        f"{'labelled':<10}{'pass':>8}{'review':>8}{'reject':>8}",
    ]
    for expected in VERDICTS:
        row = s["matrix"][expected]
        out.append(f"{name[expected]:<10}{row['pass']:>8}{row['review']:>8}{row['reject']:>8}")
    out += [
        "",
        f"Of {s['passed']} postings scored pass, {_pct(s['precision'])} were labelled apply (precision).",
        f"Of {s['to_apply']} postings labelled apply, {_pct(s['recall'])} scored pass (recall); "
        f"{_pct(s['kept'])} were at least kept for review.",
        f"Skips scored as a pass: {len(s['wasted'])}. Applies rejected: {len(s['missed'])}.",
        "",
        "Gates",
    ]
    for gate, g in sorted(s["gates"].items()):
        out.append(f"  {gate:<10} fired on {g['fired']} of {g['expected']} postings that needed it, "
                   f"and on {g['wrongly']} worth reading")
    out.append(f"\nTrack: right on {s['track_right']} of {s['tracked']} postings worth sending.")
    wrong = [r for r in rows if not r.right]
    if misses and wrong:
        out += ["", "Scored differently from the label"]
        for r in sorted(wrong, key=lambda r: (not r.serious, r.id)):
            gate = f" [{', '.join(r.gates)}]" if r.gates else ""
            out.append(f"  {'!!' if r.serious else '  '} {r.id:<9} {name[r.expected]:<5} -> {r.got:<6} "
                       f"{r.score:>3}{gate}  {r.title} — {r.why}")
    return "\n".join(out)


# ------------------------------------------------------------ own decisions

# Statuses that mean "I decided this one was worth an application". A recruiter's
# rejection is still that decision; so is being ghosted.
PURSUED = {"drafted", "ready", "submitted", "screening", "interview", "offer", "rejected", "ghosted"}


def own_decisions(applications: list[dict[str, Any]], best_scores: dict[str, tuple[int, str]]) -> dict[str, Any]:
    """Your decisions against the scorer's.

    `applications` are rows of the applications table; `best_scores` maps a job
    id to its best (score, verdict). Pursued: anything you drafted or sent.
    Dismissed: withdrawn without ever being sent, which is what the dashboard's
    skip button records. A posting only shortlisted is undecided and left out.
    """
    pursued, dismissed = [], []
    for app in applications:
        scored = best_scores.get(app["job_id"])
        if scored is None:
            continue
        if app["status"] in PURSUED or (app["status"] == "withdrawn" and app.get("submitted_at")):
            pursued.append(scored)
        elif app["status"] == "withdrawn":
            dismissed.append(scored)

    def split(items: list[tuple[int, str]]) -> dict[str, int]:
        return {v: sum(verdict == v for _, verdict in items) for v in VERDICTS}

    # The threshold that would have separated the two groups best, had it been the pass mark.
    best_at, best_right = PASS_AT, -1
    for mark in range(REVIEW_AT, 96):
        right = sum(s >= mark for s, _ in pursued) + sum(s < mark for s, _ in dismissed)
        if right > best_right:
            best_at, best_right = mark, right
    total = len(pursued) + len(dismissed)
    return {
        "pursued": len(pursued), "dismissed": len(dismissed),
        "pursued_by_verdict": split(pursued), "dismissed_by_verdict": split(dismissed),
        "recall": _ratio(sum(v == "pass" for _, v in pursued), len(pursued)),
        "false_pass": _ratio(sum(v == "pass" for _, v in dismissed), len(dismissed)),
        "best_threshold": best_at if total else None,
        "best_threshold_right": _ratio(best_right, total),
        "current_right": _ratio(sum(s >= PASS_AT for s, _ in pursued) + sum(s < PASS_AT for s, _ in dismissed), total),
    }


# Below this many decisions the percentages say more about chance than about the tracks.
ENOUGH_DECISIONS = 20


def report_own(stats: dict[str, Any]) -> str:
    n = stats["pursued"] + stats["dismissed"]
    if not n:
        return ("No decisions to compare yet. Prepare or send an application for the postings you want, and "
                "press skip in the dashboard on the ones you do not: both are recorded.")
    out = [f"{stats['pursued']} postings you pursued · {stats['dismissed']} you dismissed", ""]
    p, d = stats["pursued_by_verdict"], stats["dismissed_by_verdict"]
    out.append(f"{'':<12}{'pass':>8}{'review':>8}{'reject':>8}")
    out.append(f"{'pursued':<12}{p['pass']:>8}{p['review']:>8}{p['reject']:>8}")
    out.append(f"{'dismissed':<12}{d['pass']:>8}{d['review']:>8}{d['reject']:>8}")
    out.append("")
    if stats["pursued"]:
        out.append(f"The scorer passed {_pct(stats['recall'])} of what you pursued.")
        if p["reject"]:
            out.append(f"It rejected {p['reject']} of them: look at those first (`jsa show <id>`), "
                       "they say which track is too narrow.")
    if stats["dismissed"]:
        out.append(f"It passed {_pct(stats['false_pass'])} of what you dismissed.")
    if stats["pursued"] and stats["dismissed"]:
        out.append(f"With the pass mark at {PASS_AT} it agrees with you on {_pct(stats['current_right'])} of "
                   f"decisions; at {stats['best_threshold']} it would agree on {_pct(stats['best_threshold_right'])}.")
    if n < ENOUGH_DECISIONS:
        out.append(f"\nOnly {n} decisions so far: read these as a hint, not a measurement.")
    return "\n".join(out)
