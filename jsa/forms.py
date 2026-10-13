"""Read an application form's own questions, and answer the ones that have a known answer.

Three ATS publish the questions of a form next to the posting: Greenhouse (the
board API with `questions=true`), Ashby (the same GraphQL its job pages use)
and Lever (the apply page itself). Reading them is what turns "fill the form"
from forty minutes of re-typing into a review.

Every suggestion carries a status, because the point is to say which answers a
person must still read or write, never to pretend there are none:

- ``auto``   a fact from the profile (name, email, EU work authorisation)
- ``check``  a written answer from the answer bank or the standard answers
- ``write``  needs the person: motivation, a figure still marked TODO, anything unknown
- ``yours``  optional and personal (diversity, consent): theirs to decide, never filled
- ``file``   an attachment from the packet

Nothing here submits anything.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .models import Job, canonical
from .util import html_to_text, http_get, http_json, log

ASHBY_GRAPHQL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
ASHBY_QUERY = (
    "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
    " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
    " jobPostingId: $jobPostingId) { applicationForm { sections { fieldEntries {"
    " field isRequired } } } } }"
)

# EU and EEA citizens work there without a permit; Switzerland admits them under
# the free-movement agreement. Anywhere else the answer depends on a visa.
FREE_MOVEMENT = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO", "CH",
}


@dataclass
class Question:
    label: str
    kind: str                      # text | long | choice | multi | yesno | file | number | location
    required: bool = False
    options: list[str] = field(default_factory=list)


@dataclass
class Suggestion:
    label: str
    kind: str
    required: bool
    options: list[str]
    key: str
    status: str
    answer: str = ""
    note: str = ""


# --------------------------------------------------------------- reading

def _greenhouse_kind(types: list[str]) -> str:
    if "input_file" in types:
        return "file"
    if "multi_value_single_select" in types:
        return "choice"
    if "multi_value_multi_select" in types:
        return "multi"
    if "textarea" in types:
        return "long"
    return "text"


def parse_greenhouse(data: dict[str, Any]) -> list[Question]:
    out = []
    for q in data.get("questions") or []:
        fields = q.get("fields") or []
        types = [f.get("type", "") for f in fields]
        options = [v.get("label", "") for f in fields for v in (f.get("values") or [])]
        out.append(Question(q.get("label", "").strip(), _greenhouse_kind(types),
                            bool(q.get("required")), [o for o in options if o]))
    return out


ASHBY_KINDS = {"File": "file", "LongText": "long", "Boolean": "yesno", "ValueSelect": "choice",
               "MultiValueSelect": "multi", "Number": "number", "Location": "location"}


def parse_ashby(data: dict[str, Any]) -> list[Question]:
    posting = (data.get("data") or {}).get("jobPosting") or {}
    out = []
    for section in (posting.get("applicationForm") or {}).get("sections") or []:
        for entry in section.get("fieldEntries") or []:
            f = entry.get("field") or {}
            options = [v.get("label", "") for v in (f.get("selectableValues") or [])]
            out.append(Question((f.get("title") or "").strip(), ASHBY_KINDS.get(f.get("type", ""), "text"),
                                bool(entry.get("isRequired")), [o for o in options if o]))
    return out


_LEVER_ITEM = re.compile(r'<li class="application-question(?! custom-question)[^"]*">(.*?)</li>', re.S)
_LEVER_LABEL = re.compile(r'<div class="application-label[^"]*">(.*?)</div>', re.S)
_LEVER_CARD = re.compile(r'value="(\{[^"]*?)"\s+name="cards\[[^\]]+\]\[baseTemplate\]"')
LEVER_KINDS = {"multiple-choice": "choice", "dropdown": "choice", "multiple-select": "multi",
               "textarea": "long", "text": "text", "file-upload": "file"}


def parse_lever(page: str) -> list[Question]:
    """Standard fields from the form's markup; custom questions from the JSON copy
    Lever keeps of each card, which carries every option (the markup nests them)."""
    out = []
    for block in _LEVER_ITEM.findall(page):
        found = _LEVER_LABEL.search(block)
        if not found:
            continue
        label = html_to_text(found.group(1)).replace("✱", "").strip()
        kind = "file" if 'type="file"' in block else "long" if "<textarea" in block else "text"
        out.append(Question(label, kind, "✱" in found.group(1)))
    for raw in _LEVER_CARD.findall(page):
        try:
            card = json.loads(html.unescape(raw))
        except ValueError:
            continue
        for f in card.get("fields") or []:
            out.append(Question((f.get("text") or "").strip(), LEVER_KINDS.get(f.get("type", ""), "text"),
                                bool(f.get("required")),
                                [o.get("text", "") for o in f.get("options") or [] if o.get("text")]))
    return out


def form_source(job: Job) -> tuple[str, list[str]] | None:
    """(provider, ids) for the boards whose forms can be read, from the posting's URL."""
    path = [p for p in urllib.parse.urlparse(job.url or "").path.split("/") if p]
    host = urllib.parse.urlparse(job.url or "").netloc
    if "greenhouse.io" in host and "jobs" in path:
        i = path.index("jobs")
        if i >= 1 and i + 1 < len(path):
            return "greenhouse", [path[i - 1], path[i + 1]]
    if host == "jobs.ashbyhq.com" and len(path) >= 2:
        return "ashby", path[:2]
    if host in ("jobs.lever.co", "jobs.eu.lever.co") and len(path) >= 2:
        return "lever", [host, *path[:2]]
    return None


def fetch(job: Job, *, get: Callable[..., Any] = http_json, get_text: Callable[..., str] = http_get
          ) -> list[Question] | None:
    """The form's questions, or None when this board's forms cannot be read."""
    source = form_source(job)
    if source is None:
        return None
    provider, ids = source
    opts = {"retries": 2, "timeout": 20}
    if provider == "greenhouse":
        board, job_id = ids
        return parse_greenhouse(get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
                                    "?questions=true", **opts))
    if provider == "ashby":
        org, posting = ids
        body = {"operationName": "ApiJobPosting", "query": ASHBY_QUERY,
                "variables": {"organizationHostedJobsPageName": org, "jobPostingId": posting}}
        return parse_ashby(get(ASHBY_GRAPHQL, body=body, **opts))
    host, company, posting = ids
    return parse_lever(get_text(f"https://{host}/{company}/{posting}/apply", **opts))


# ----------------------------------------------------------- recognising

# Order matters: "eligible to work without sponsorship" is the authorisation
# question, not the sponsorship one, so authorisation is tried first.
RULES: list[tuple[str, str]] = [
    ("resume", r"\b(resume|cv|curriculum)\b"),
    ("cover_letter", r"cover letter|motivation letter|lettera"),
    ("preferred_name", r"preferred (first )?name"),
    ("first_name", r"\bfirst name\b|given name"),
    ("last_name", r"\blast name\b|surname|family name"),
    ("full_name", r"^(full )?name$|^your (full )?name"),
    ("email", r"\be-?mail\b"),
    ("phone", r"\bphone\b|mobile|telephone"),
    ("linkedin", r"linkedin"),
    ("github", r"github"),
    ("website", r"website|portfolio|personal site|other profile"),
    ("eeo", r"gender|pronoun|ethnic|\brace\b|disab|veteran|sexual orientation|demographic|diversity|date of birth|\bage\b"),
    ("consent", r"consent|privacy|gdpr|data protection|retain (my|your) (data|application)|talent (pool|community)|future (roles|opportunities)"),
    ("work_auth", r"(eligible|authori[sz]ed|legally able|right|permitted) to work|work authori[sz]ation|work permit|right to work"),
    ("sponsorship", r"(require|need)\w*[^?]{0,40}sponsor|sponsorship"),
    ("relocation", r"relocat"),
    ("notice", r"notice period"),
    ("start", r"start date|earliest (possible )?start|when (could|can|would) you (start|join)|available to start"),
    ("salary", r"salary|compensation expectation|pay expectation|expected (annual |gross )*(pay|compensation)|desired pay|remuneration"),
    ("english_level", r"english (level|proficiency)|level of english|english language"),
    ("italian_level", r"italian (level|proficiency)|level of italian|speak italian|italian language"),
    ("languages", r"which languages|languages (do )?you speak|language skills"),
    ("referred", r"referr|referral"),
    ("worked_before", r"worked (at|for|with) .{0,40}(before|past|previously)|former employee|previously (been )?employed|ever (been )?employed"),
    ("hear_about", r"how did you (hear|find|learn)|where did you (hear|find|see)"),
    ("current_company", r"current (company|employer)"),
    ("location", r"where are you (currently )?(based|located)|(what|which) (country|city) are you (currently )?(based|located|living)|current (location|city|country)|^location$|(city|country) of residence"),
    ("driving", r"driv(ing|er'?s) licen[cs]e"),
    ("criminal", r"criminal|conviction"),
    ("work_model", r"(on-?site|in the office|hybrid|commute|days a week in)"),
    ("motivation", r"why (do you want|are you interested|.{0,30}(join|apply|us|company|role))|motivat|what excites|interest(s|ed) you"),
]


FOLLOW_UP = r"describe it|tell us more|more (about|detail)|please elaborate|if (yes|so),? (please )?(describe|explain|tell)"


def classify(label: str, options: list[str] | None = None) -> str:
    text = label.lower()
    for key, pattern in RULES:
        if re.search(pattern, text):
            return key
    # "We're curious to know!" says nothing; its options (LinkedIn, Careers Page,
    # Career Fair) say it is the "how did you hear about us" question.
    joined = " ".join(options or []).lower()
    if "linkedin" in joined and re.search(r"career|website|referral|job board", joined):
        return "hear_about"
    return ""


def pick(options: list[str], *wanted: str, avoid: str = "") -> str:
    """The option that best matches one of `wanted`, in order of preference.

    An exact match wins over a partial one, and an option matching `avoid` is
    never chosen: "Yes, I'm based in Barcelona" starts with "yes", and choosing
    it for someone in Kraków would put a false statement in the application.
    """
    norm = [(o, canonical(o).replace("/", " ")) for o in options if not (avoid and re.search(avoid, o, re.I))]
    for want in wanted:
        w = canonical(want)
        for original, c in norm:
            if c == w:
                return original
        for original, c in norm:
            if c.startswith(w + " ") or f" {w} " in f" {c} ":
                return original
    return ""


# ------------------------------------------------------------- answering

def _pending(value: Any) -> bool:
    return not value or str(value).startswith(("TODO", "AUTO"))


def load_bank(home: Path) -> list[dict[str, Any]]:
    path = home / "answer_bank.json"
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("answers") or [])
    except (OSError, ValueError):
        return []


def suggest(questions: list[Question], job: Job, profile: dict[str, Any],
            answers: dict[str, Any], bank: list[dict[str, Any]],
            files: dict[str, str] | None = None) -> list[Suggestion]:
    identity = profile.get("identity", {})
    name = identity.get("name", "").strip()
    first, _, last = name.partition(" ")
    free = (job.country or "").upper() in FREE_MOVEMENT
    employers = {canonical(e.get("company", "")) for e in profile.get("experience", [])}
    current = next((e.get("company", "") for e in profile.get("experience", [])
                    if str(e.get("end", "")).lower() in ("present", "current", "")), "")
    levels = {lang.get("code"): lang.get("level", "") for lang in profile.get("languages", [])}
    files = files or {}

    def standard(key: str) -> tuple[str, str]:
        value = answers.get(key, "")
        return ("write", "") if _pending(value) else ("check", str(value))

    def story_for(label: str) -> dict[str, Any] | None:
        return next((b for b in bank if any(re.search(p, label, re.I) for p in b.get("match", []))), None)

    out: list[Suggestion] = []
    previous = ""
    for q in questions:
        key = classify(q.label, q.options)
        status, answer, note = "write", "", ""

        story = story_for(q.label)
        if story is None and previous and re.search(FOLLOW_UP, q.label, re.I):
            # "Please briefly describe it" only makes sense with the question before it.
            story = story_for(previous)
        previous = q.label
        if story and q.kind in ("long", "text"):
            key, status, answer = f"bank:{story.get('id', '')}", "check", story.get("text", "")
            if not story.get("confirmed", True):
                note = "Contains a part still to confirm — read it before sending."
        elif key in ("resume", "cover_letter"):
            status, answer = ("file", files.get(key, "")) if files.get(key) else ("write", "")
        elif key in ("first_name", "last_name", "full_name", "email", "phone", "linkedin", "github"):
            answer = {"first_name": first, "last_name": last, "full_name": name}.get(key) or identity.get(key, "")
            status = "auto" if answer else "write"
        elif key == "preferred_name":
            status = "yours"
        elif key == "website":
            answer = answers.get("website") or identity.get("website") or identity.get("github", "")
            status = "auto" if answer else "write"
        elif key in ("eeo", "consent"):
            status = "yours"
            note = answers.get("diversity_questions", "") if key == "eeo" else "Your choice."
        elif key == "work_auth":
            if free:
                status = "auto"
                answer = pick(q.options, "yes") if q.options or q.kind == "yesno" else answers.get("work_authorisation", "")
                answer = answer or "Yes"
            else:
                note = f"{job.country or 'This country'} is outside EU free movement: a visa may be needed."
        elif key == "sponsorship":
            if free:
                status, answer = "auto", (pick(q.options, "no") or "No")
            else:
                note = f"{job.country or 'This country'} is outside EU free movement."
        elif key == "relocation":
            if q.options:
                # Only an option that says "willing to relocate", never one claiming
                # the person already lives there.
                answer = pick(q.options, "willing to relocate", "relocate", "yes", avoid=r"\bbased in\b|\blive in\b")
                status = "check" if answer else "write"
            else:
                status, answer = "check", ("Yes" if q.kind == "yesno" else answers.get("relocation", "") or "Yes")
        elif key in ("notice", "start", "salary", "languages", "driving", "criminal"):
            field_name = {"notice": "notice_period", "start": "earliest_start", "salary": "salary_expectation",
                          "driving": "driving_licence", "criminal": "criminal_record"}.get(key, key)
            status, answer = standard(field_name)
        elif key == "english_level":
            level = levels.get("en", "")
            words = {"C2": ("c2", "proficiency", "native"), "C1": ("c1", "advanced", "professional", "fluent"),
                     "B2": ("b2", "upper intermediate", "intermediate")}.get(level, (level,))
            answer = pick(q.options, *words) if q.options else level
            status = "check" if answer else "write"
        elif key == "italian_level":
            answer = pick(q.options, "native", "mother tongue", "c2") if q.options else "Native"
            status = "auto" if answer else "check"
        elif key == "referred":
            status, answer = "check", (pick(q.options, "no") or "No")
        elif key == "worked_before":
            before = canonical(job.company) in employers
            status, answer = "auto", (pick(q.options, "yes" if before else "no") or ("Yes" if before else "No"))
        elif key == "hear_about":
            status = "check"
            answer = pick(q.options, "careers page", "career site", "company website", "website", "other") \
                if q.options else "Company careers page"
        elif key == "current_company":
            status, answer = ("auto", current) if current else ("write", "")
        elif key == "location":
            answer = identity.get("location", "") or answers.get("current_location", "")
            if "country" in q.label.lower() and "," in answer:
                answer = answer.rsplit(",", 1)[1].strip()
            status = "auto" if answer else "write"
        elif key == "work_model":
            status, answer = standard("remote_preference")
        elif key == "motivation":
            note = "Written for this employer, from something you verified about them."
        out.append(Suggestion(q.label, q.kind, q.required, q.options, key or "other", status, answer, note))
    return out


def prepare(job: Job, profile: dict[str, Any], answers: dict[str, Any], home: Path, folder: Path,
            files: dict[str, str]) -> list[Suggestion] | None:
    """Read the form, suggest answers, save them as form.json in the packet. None if unreadable."""
    if os.environ.get("JSA_FORMS") == "off":
        return None
    try:
        questions = fetch(job)
    except Exception as exc:  # noqa: BLE001 - a form we cannot read must not stop the packet
        log.info("form of %s at %s not read: %s", job.title, job.company, exc)
        return None
    if questions is None:
        return None
    suggestions = suggest(questions, job, profile, answers, load_bank(home), files)
    (folder / "form.json").write_text(json.dumps([asdict(s) for s in suggestions], ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    return suggestions


def still_to_write(suggestions: list[Suggestion] | None) -> int:
    return sum(1 for s in suggestions or [] if s.status == "write" and s.required)
