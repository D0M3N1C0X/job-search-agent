"""`jsa setup` — build a profile by answering questions.

Editing five hundred lines of JSON is a reasonable ask of the person who wrote
the JSON and of nobody else. This asks in plain language and writes the files,
including the part nobody should have to write from scratch: the keyword lists
a scorer needs. Those come from a library of ready-made positioning tracks.

Everything it writes stays editable afterwards — this is a starting point, not
a wall.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .config import REPO_ROOT
from .sources.ats import guess_country
from .util import write_json

LIBRARY = REPO_ROOT / "profile.example" / "tracks.library.json"
CEFR = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]

# One pattern shape covers every language: postings are overwhelmingly in
# English even when the job is not, and they phrase the requirement the same way.
GATE_PATTERN = (
    r"(fluent|native|proficient|advanced|very good|c1|c2)\s+{lang}"
    r"|{lang}\s+(language\s+)?(is\s+)?(a\s+)?(must|required|mandatory|essential|fluency)"
)

COMMON_LANGUAGES = [
    ("en", "English"), ("de", "German"), ("fr", "French"), ("nl", "Dutch"),
    ("pl", "Polish"), ("es", "Spanish"), ("it", "Italian"), ("pt", "Portuguese"),
    ("sv", "Swedish"), ("da", "Danish"), ("cs", "Czech"), ("hu", "Hungarian"),
    ("ro", "Romanian"), ("fi", "Finnish"), ("el", "Greek"), ("no", "Norwegian"),
]

BOLD, DIM, GREEN, YELLOW, OFF = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[0m"


class Cancelled(Exception):
    """The person pressed Ctrl-C or Ctrl-D. Not an error."""


# ------------------------------------------------------------------ prompts

def _style(text: str, code: str) -> str:
    return f"{code}{text}{OFF}" if sys.stdout.isatty() else text


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError) as exc:
        raise Cancelled from exc


def heading(title: str, note: str = "") -> None:
    print(f"\n{_style(title, BOLD)}")
    if note:
        print(_style(note, DIM))


def ask(question: str, *, default: str = "", required: bool = False,
        validate: Callable[[str], str | None] | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = _input(f"  {question}{suffix}: ") or default
        if not answer and required:
            print(_style("    This one is needed.", YELLOW))
            continue
        if answer and validate:
            problem = validate(answer)
            if problem:
                print(_style(f"    {problem}", YELLOW))
                continue
        return answer


def ask_yes(question: str, *, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = _input(f"  {question} [{hint}]: ").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def ask_list(question: str, *, default: list[str] | None = None) -> list[str]:
    """Comma-separated, because that is how people already write lists."""
    shown = ", ".join(default or [])
    answer = ask(question, default=shown)
    return [item.strip() for item in answer.split(",") if item.strip()]


def ask_bullets(question: str) -> list[str]:
    print(f"  {question}")
    print(_style("    One per line. Empty line when you are done.", DIM))
    bullets = []
    while True:
        line = _input("    · ")
        if not line:
            return bullets
        bullets.append(line)


def ask_choice(question: str, options: list[tuple[str, str]], *,
               multiple: bool = False, default: list[str] | None = None) -> list[str]:
    print(f"\n  {question}")
    for index, (_, label) in enumerate(options, 1):
        print(f"    {index:>2}. {label}")
    hint = "numbers separated by commas" if multiple else "one number"
    marks = ", ".join(str(i) for i, (key, _) in enumerate(options, 1) if key in (default or []))
    while True:
        raw = ask(f"Pick {hint}", default=marks)
        try:
            picked = [int(n) for n in raw.replace(" ", "").split(",") if n]
        except ValueError:
            print(_style("    Numbers, please.", YELLOW))
            continue
        if not picked or any(n < 1 or n > len(options) for n in picked):
            print(_style(f"    Between 1 and {len(options)}.", YELLOW))
            continue
        if not multiple and len(picked) > 1:
            print(_style("    Just one.", YELLOW))
            continue
        return [options[n - 1][0] for n in picked]


# ------------------------------------------------------------------ sections

def collect_identity() -> dict[str, Any]:
    heading("Who you are", "This goes at the top of every CV the tool generates.")
    email = ask("Email", required=True,
                validate=lambda v: None if "@" in v and "." in v.split("@")[-1]
                else "That does not look like an email address.")
    return {
        "name": ask("Full name", required=True),
        "headline": ask("One-line headline", default="HR Professional"),
        "location": ask("Where you live (city, country)", required=True),
        "citizenship": ask("Citizenship or work authorisation", default="EU Citizen"),
        "relocation": ask("Relocation", default="Open to relocation (EU)"),
        "phone": ask("Phone", required=True),
        "email": email,
        "linkedin": ask("LinkedIn (without https://)", default=""),
        "github": ask("GitHub or portfolio (optional)", default=""),
    }


def collect_languages() -> list[dict[str, str]]:
    heading("Languages", "Level matters: it decides which postings are rejected outright.")
    languages = []
    while True:
        name = ask("Language (empty to finish)" if languages else "Language", required=not languages)
        if not name:
            return languages
        code = next((c for c, n in COMMON_LANGUAGES if n.lower() == name.lower()),
                    name[:2].lower())
        level = ask_choice(f"Your level in {name}", [(l, l) for l in CEFR], default=["B2"])[0]
        languages.append({"code": code, "name": name.title(), "level": level})


def collect_experience() -> list[dict[str, Any]]:
    heading("Experience", "Start with your current or most recent role. Two to four "
                          "bullets each is plenty; numbers where you have them.")
    roles = []
    while True:
        label = "Job title" if not roles else "Job title for the previous role (empty to finish)"
        title = ask(label, required=not roles)
        if not title:
            return roles
        roles.append({
            "title": title,
            "company": ask("Company", required=True),
            "location": ask("Location", default=""),
            "start": ask("Start (e.g. Mar 2024)", required=True),
            "end": ask("End, or 'Present'", default="Present" if not roles else ""),
            "bullets": [{"text": text, "tracks": ["*"]}
                        for text in ask_bullets("What you did there")],
        })


def collect_education() -> list[dict[str, str]]:
    heading("Education")
    entries = []
    while True:
        degree = ask("Degree (empty to finish)" if entries else "Degree", required=not entries)
        if not degree:
            return entries
        entries.append({
            "degree": degree,
            "institution": ask("Institution", required=True),
            "date": ask("Finished (e.g. 2024)", default=""),
            "grade": ask("Grade (optional)", default=""),
            "detail": ask("Relevant coursework (optional)", default=""),
            "thesis": "",
        })


def collect_skills() -> dict[str, Any]:
    heading("Skills", "Comma separated. These appear on the CV and feed the keyword check.")
    return {
        "hr_core": {"label": "HR", "items": ask_list("HR skills")},
        "analytics": {"label": "People analytics", "items": ask_list("Analytics and reporting")},
        "technical": {"label": "Tools & methods", "items": ask_list("Tools you actually use")},
        "ways_of_working": {"label": "Ways of working",
                            "items": ask_list("Ways of working",
                                              default=["Stakeholder management",
                                                       "Process improvement"])},
    }


def collect_tracks(library: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    heading("What you are looking for",
            "A track is a way of being read. Every posting is scored against each one you\n"
            "pick, and the winner decides how the CV is written. Two or three is usual.")
    chosen = ask_choice(
        "Which of these describe the roles you want?",
        [(t["id"], f'{t["label"]}  {_style("— " + t["cover_angle"], DIM)}') for t in library],
        multiple=True, default=["hr_advisory"],
    )
    return [t for t in library if t["id"] in chosen], chosen


def collect_preferences(languages: list[dict[str, str]]) -> dict[str, Any]:
    heading("Where and what level")
    cities = ask_list("Cities you would take a job in", default=["Remote"])
    countries_named = ask_list("Countries to include (names are fine)")
    codes = sorted({guess_country(name) for name in countries_named} - {""})
    if countries_named and not codes:
        print(_style("    None of those matched a country I know — leaving it open.", YELLOW))

    seniority = ask_choice("What level are you targeting?",
                           [("junior", "Junior / entry"), ("mid", "Mid / specialist"),
                            ("senior", "Senior / lead")],
                           multiple=True, default=["mid"])

    spoken = {lang["code"] for lang in languages
              if CEFR.index(lang["level"]) >= CEFR.index("C1")}
    candidates = [(code, name) for code, name in COMMON_LANGUAGES if code not in spoken]
    heading("Deal-breakers",
            "A posting demanding a language you do not have is a waste of your evening.\n"
            "Pick the ones that should reject a posting outright.")
    blocked = ask_choice("Which languages would rule you out?",
                         candidates + [("__none", "None of them")], multiple=True,
                         default=["__none"])
    gates = [
        {"code": code, "min_level": "C1",
         "pattern": GATE_PATTERN.format(lang=dict(COMMON_LANGUAGES)[code].lower())}
        for code in blocked if code != "__none"
    ]

    return {
        "locations_preferred": cities,
        "countries_allowed": codes,
        "countries_blocked": [],
        "relocation": ask_yes("Would you relocate?", default=True),
        "remote_ok": ask_yes("Is remote fine?", default=True),
        "seniority_target": seniority,
        "seniority_reject": ["head"],
        "language_gates": gates,
        "hard_reject_keywords": ["unpaid internship", "commission only", "door to door"],
        "soft_reject_keywords": ["outbound sales", "telemarketing"],
        "follow_up_days": 10,
        "ghost_after_days": 28,
    }


def collect_answers(identity: dict[str, Any], languages: list[dict[str, str]]) -> dict[str, Any]:
    heading("The questions every application form asks",
            "Answer once and they are in every packet the tool builds.")
    return {
        "_comment": "Written by `jsa setup`. Edit freely.",
        "work_authorisation": ask("Work authorisation", default=identity["citizenship"]),
        "current_location": identity["location"],
        "relocation": identity["relocation"],
        "remote_preference": ask("Remote preference", default="Open to remote, hybrid or on-site."),
        "notice_period": ask("Notice period", default="TODO — check your contract."),
        "salary_expectation": ask("Salary expectation", default="TODO — decide before you need it."),
        "earliest_start": ask("Earliest start date", default="TODO"),
        "languages": " · ".join(f'{l["name"]} ({l["level"]})' for l in languages),
        "driving_licence": ask("Driving licence", default=""),
        "linkedin": identity.get("linkedin", ""),
        "references": "Available on request.",
    }


def collect_search(preferences: dict[str, Any], tracks: list[dict[str, Any]]) -> dict[str, Any]:
    """Seed LinkedIn queries from the tracks and cities already chosen."""
    location = preferences["locations_preferred"][0] if preferences["locations_preferred"] else ""
    queries = [
        {"keywords": track["titles"]["strong"][0].title(), "location": location, "period": "week"}
        for track in tracks[:4]
    ]
    return {"linkedin_queries": queries, "mailbox_path": ""}


# --------------------------------------------------------------------- run

def run(home: Path, *, force: bool = False) -> Path:
    if not sys.stdin.isatty():
        raise SystemExit(
            "`jsa setup` asks questions, so it needs a terminal.\n"
            "If you are scripting this, copy profile.example/ and edit the JSON directly."
        )
    profile_path = home / "profile.json"
    if profile_path.exists() and not force:
        print(f"{profile_path} already exists.")
        if not ask_yes("Replace it?", default=False):
            raise SystemExit("Left alone.")

    library = json.loads(LIBRARY.read_text(encoding="utf-8"))["tracks"]

    print(_style("\nSetting up your profile", BOLD))
    print(_style("Press Ctrl-C at any point to stop; nothing is written until the end.\n", DIM))

    identity = collect_identity()
    languages = collect_languages()
    experience = collect_experience()
    education = collect_education()
    skills = collect_skills()
    tracks, track_ids = collect_tracks(library)
    preferences = collect_preferences(languages)
    answers = collect_answers(identity, languages)

    heading("One last thing",
            "A short paragraph about you, in your words. The tool reuses it for every\n"
            "track; Claude Code can tailor it per application later.")
    summary = ask("Summary", required=True)

    home.mkdir(parents=True, exist_ok=True)
    write_json(home / "profile.json", {
        "_comment": "Written by `jsa setup`. Factual only — the tailoring overlay may select "
                    "and reorder what is here, never invent.",
        "identity": identity,
        "years_experience": int(ask("Roughly how many years of relevant experience?",
                                    default="3", validate=lambda v: None if v.isdigit()
                                    else "A number.") or 3),
        "summaries": {track_id: summary for track_id in track_ids},
        "skill_groups": skills,
        "experience": experience,
        "projects": {"note": "", "items": []},
        "education": education,
        "research": [],
        "additional_experience": [],
        "languages": languages,
        "certifications": [],
        "preferences": preferences,
        "search": collect_search(preferences, tracks),
    })
    write_json(home / "tracks.json", {
        "_comment": "Copied from the track library by `jsa setup`. Edit the keyword lists as "
                    "you learn what the scorer gets wrong — that is the intended workflow.",
        "tracks": tracks,
    })
    write_json(home / "answers.json", answers)
    for folder in ("inbox", "output"):
        (home / folder).mkdir(exist_ok=True)

    watchlist = home / "watchlist.json"
    if not watchlist.exists():
        write_json(watchlist, {"_comment": "Add companies with `jsa probe <slug> --add`.",
                               "companies": []})
    return home
