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
import unicodedata
from dataclasses import dataclass
from typing import Any

from .models import Job, Score, canonical, normalize_title

SCORER_VERSION = "1.1.0"

# Points available per dimension. They sum to 100.
WEIGHTS: dict[str, float] = {
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

# Years of experience asked for. A number of years is a requirement only when
# the sentence says so: "25 years in business" and "in the past 3 years our
# headcount tripled" are the employer talking about itself. A range counts
# from its lower end, and the numbers one to fifteen may be written out.
_NUMBER_WORDS = {w: i for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split(), start=1)}
_NUM = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_UNIT = r"(?:years?|yrs?|anni|lata?|jahren?|ans|anos|jaar)"
_YEARS = re.compile(
    _NUM + r"\s*(\+)?\s*(?:(?:-|–|to|bis|a|do)\s*(?:\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s*)?(\+)?\s*"
    + _UNIT + r"\b([^.;\n]{0,70})", re.I)
_YEARS_LEAD = re.compile(
    r"(at least|minimum( of)?|min\.?|more than|over|mindestens|almeno|au moins|al menos|minimaal|co najmniej)\s*$", re.I)
_YEARS_CONTEXT = re.compile(
    r"\b(experience|experienced|erfahrung|berufserfahrung|esperienza|experiencia|expérience|experience|ervaring|"
    r"doświadczeni\w*|doswiadczeni\w*|in an?\b|in hr\b|in the field|as an?\b|of hr\b|of which|working|"
    r"background|track record|in a similar|in similar)", re.I)

# More years asked than the profile has: beyond the first figure the posting is
# read but cannot pass; beyond the second it is not a serious application.
YEARS_REVIEW_AT = 3
YEARS_REJECT_AT = 5
# From this much experience on, an internship is not a role to apply to.
INTERN_UNTIL_YEARS = 2


def detect_language(text: str) -> str:
    """Best-guess language of a posting, used to choose the cover-letter language."""
    sample = canonical((text or "")[:4000])
    if not sample:
        return "en"
    hits = {lang: len(re.findall(pat, sample)) for lang, pat in LANG_MARKERS.items()}
    best = max(hits, key=lambda k: hits[k])
    return best if hits[best] >= 3 else "en"


# "Reporting to the Head of HR", "you will report to the Director of People":
# the level named is the manager's, not the role's.
_REPORTING_LINE = re.compile(
    r"\b(report(s|ing)?( directly)?( in)? ?to|reporting line|supported by|working (closely )?with|"
    r"coaching from|partner(s|ing)? with|on behalf of)\b[^.;\n]*", re.I)


def detect_seniority(title: str, description: str = "") -> str:
    """The level of the role: from the title, or failing that from the posting's opening.

    The body can say the role is senior or junior, never that it is a head of
    function: such a job says so in its title, and a body that names a director
    is usually naming the person the role reports to.
    """
    blob = f" {canonical(title)} "
    for level, pattern in reversed(SENIORITY_PATTERNS):  # most senior wins
        if re.search(pattern, blob):
            return level
    body = canonical(_REPORTING_LINE.sub(" ", (description or "")[:1500]))
    for level, pattern in reversed(SENIORITY_PATTERNS[:-1]):
        if re.search(pattern, body):
            return level
    return "mid"


_DECADE = re.compile(r"\b(?:a|one) decade\b([^.;\n]{0,70})", re.I)


def required_years(text: str) -> int:
    """Highest 'N years of experience' figure the posting asks for; a range counts from its lower end."""
    text = text or ""
    asked = 10 if any(_YEARS_CONTEXT.search(m.group(1)) for m in _DECADE.finditer(text)) else 0
    for match in _YEARS.finditer(text):
        raw = match.group(1).lower()
        number = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
        if number > 25:
            continue
        plus = bool(match.group(2) or match.group(3))
        lead = _YEARS_LEAD.search(text[max(0, match.start() - 24):match.start()])
        if plus or lead or _YEARS_CONTEXT.search(match.group(4)):
            asked = max(asked, number)
    return asked


# Keyword lists are reused across thousands of postings, so each list is
# compiled once into a single alternation and matched in one pass. Searching
# term by term meant hundreds of scans of every description; this is one.
_MATCHERS: dict[tuple[str, ...], tuple[re.Pattern[str] | None, dict[str, str]]] = {}


# A keyword of four letters or more also matches its plain plural: "dashboard"
# finds "dashboards" and "hr policy" finds "hr policies". Shorter ones do not,
# because "hr" must not find "hrs".
_PLURAL_FROM = 4


def _matcher(terms: list[str]) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    key = tuple(terms)
    if key not in _MATCHERS:
        mapping: dict[str, str] = {}
        for term in terms:
            needle = canonical(term)
            if needle:
                mapping.setdefault(needle, term)
                last = needle.rsplit(" ", 1)[-1]
                if len(last) >= _PLURAL_FROM and last.endswith("y") and last[-2] not in "aeiou":
                    mapping.setdefault(needle[:-1] + "ies", term)
        plural = sorted((re.escape(n) for n in mapping
                         if len(n.rsplit(" ", 1)[-1]) >= _PLURAL_FROM and not n.endswith("s")),
                        key=len, reverse=True)
        fixed = sorted((re.escape(n) for n in mapping
                        if len(n.rsplit(" ", 1)[-1]) < _PLURAL_FROM or n.endswith("s")),
                       key=len, reverse=True)
        parts = []
        if plural:
            parts.append("(" + "|".join(plural) + ")(?:s|es)?")
        if fixed:
            parts.append("(" + "|".join(fixed) + ")")
        pattern = (
            re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")
            if parts else None
        )
        _MATCHERS[key] = (pattern, mapping)
    return _MATCHERS[key]


def _matches(terms: list[str], haystack: str) -> list[str]:
    """Which of `terms` appear in `haystack` (already canonicalised)."""
    pattern, mapping = _matcher(terms)
    if pattern is None:
        return []
    hits = set()
    for match in pattern.finditer(haystack):
        found = next(g for g in match.groups() if g)
        hits.add(mapping[found])
    return [term for term in terms if term in hits]


# ---------------------------------------------------- languages asked for
# A posting that asks for a language is read the same way whatever the profile
# says about gates: the sixteen languages below are recognised when they are
# required, in English and in the language itself, and compared with the level
# the profile declares. A language the profile does not list is one it lacks.
CEFR = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]
LANGUAGES: dict[str, tuple[str, str]] = {
    # code: (the name as English writes it, how the language asks for itself; accents folded, lower case)
    "en": ("English", ""),
    "de": ("German",
           r"(fliessend|fließend|verhandlungssicher|sehr gut|ausgezeichnet|muttersprach)\w*\s+(es\s+)?deutsch"
           r"|deutsch\w*\s+(in wort und schrift|fliessend|fließend|verhandlungssicher)"
           r"|deutschkenntnisse\s+(sind\s+)?(erforderlich|voraussetzung|zwingend)"),
    "fr": ("French",
           r"francais\s+(courant|indispensable|exige|obligatoire|natif)"
           r"|(maitrise|pratique)\s+(parfaite\s+|courante\s+)?(du|de la langue)\s+francais"
           r"|langue\s+maternelle\s+francais"),
    "nl": ("Dutch",
           r"vloeiend\w*\s+(in\s+)?(het\s+)?nederlands|nederlandse?\s+taal\s+vloeiend"
           r"|beheers\w*\s+(van\s+)?(de\s+|het\s+)?nederlands|uitstekend\w*\s+nederlands"
           r"|nederlands\s+is\s+(een\s+)?(must|vereist|verplicht)"),
    "pl": ("Polish",
           r"(bieg[łl]|bardzo dobr)\w*\s+znajomo\w+\s+(jezyka\s+)?polskiego"
           r"|jezyk\s+polski\s+(biegle|na poziomie (c1|c2|ojczystym))|polski\s+ojczysty"),
    "es": ("Spanish",
           r"(espanol|castellano)\s+(nativo|fluido|bilingue|alto)"
           r"|(nivel\s+alto|dominio)\s+(de|del)\s+(espanol|castellano)|lengua\s+materna\s+(espanol|castellan)"),
    "it": ("Italian",
           r"(ottima|eccellente|perfetta)\s+(conoscenza|padronanza)\s+(della lingua\s+italiana|dell\W?italiano)"
           r"|italiano\s+(fluente|madrelingua|ottimo)|madrelingua\s+italian|lingua\s+italiana\s+fluente"),
    "pt": ("Portuguese", r"portugues\s+(fluente|nativo)|fluencia\s+em\s+portugues"),
    "sv": ("Swedish", ""), "da": ("Danish", ""), "cs": ("Czech", ""), "hu": ("Hungarian", ""),
    "ro": ("Romanian", ""), "fi": ("Finnish", ""), "el": ("Greek", ""), "no": ("Norwegian", ""),
}
# How a requirement is worded, in English. The language name keeps its
# capital, which is what tells "Polish" from "polish our handbook"; everything
# around it is matched in any case.
_STRONG = r"fluent|fluency|native|near[- ]native|mother[- ]tongue|bilingual|c1|c2"
_SOLID = r"proficient|proficiency|advanced|excellent|very good|strong"
_NAMES = {name: code for code, (name, _own) in LANGUAGES.items()}
# "Dutch employment law", "the German market": the country, not the language.
_NOT_A_LANGUAGE = (
    r"(?!\s+(?:employment|labour|labor|law|legislation|market|entit|payroll|tax|social|compan|team|office|"
    r"business|client|customer|colleague|subsidiar|branch|operation|store|site|plant|workforce|population|"
    r"employee|staff|works council|regulat|provider|lawyer|adviser|advisor|collective))"
)
_NAME = r"\b(?:" + "|".join(f"{n}|{n.upper()}" for n in _NAMES) + r")\b" + _NOT_A_LANGUAGE
# "German", "German and French", "Dutch or German", "English, Dutch and French"
_CHAIN = rf"({_NAME}(?:\s*(?:,|/|&|\+|(?i:and|or|und|oder))\s*{_NAME})*)"
_BETWEEN = (r"(?:\s+level)?(?:\s+(?:in|of))?\s+(?:both\s+)?"
            r"(?:(?:written|spoken|verbal|business)(?:\s+and\s+(?:written|spoken))?\s+)?")
_MUST = (r"(?:\s+(?:language|skills|language skills))?\s+(?:(?:is|are)\s+)?(?:both\s+)?(?:an?\s+)?(?:absolute\s+)?"
         r"(?:must|required|mandatory|essential|necessary|needed|prerequisite|requirement)\b")
_REQUIREMENT = re.compile(
    rf"\b(?i:(?P<strong>{_STRONG})|(?P<solid>{_SOLID}))(?i:{_BETWEEN}){_CHAIN}"         # fluent Dutch and French
    rf"|{_CHAIN}(?i:{_MUST})"                                                          # Dutch is a must
    rf"|{_CHAIN}\s*[:(–-]\s*(?i:(?P<after>{_STRONG})|(?P<after_solid>{_SOLID}))\b"     # Dutch (fluent), Dutch: native
    rf"|{_CHAIN}\s+(?i:(?P<trail>mother[- ]tongue|native speakers?|native level|fluently|"
    rf"at (?:an? )?(?:native|fluent|c1|c2) level))\b"                                 # French mother tongue
    rf"|{_CHAIN}(?i:(?P<speaking>[- ]speak(?:ing|er)s?))\b"                            # German-speaking
)
_TITLE_LANGUAGE = re.compile(rf"\b(?i:with|mit|con|avec)\s+({_NAME})|\(({_NAME})\)|({_NAME})(?i:[- ]speak)")
_EITHER = re.compile(r"/|\b(?:or|oder)\b", re.I)
# What turns a requirement into a wish, when it follows the language in the same clause.
_SOFT = re.compile(
    r"\b(plus|bonus|advantage|advantageous|asset|nice to have|desirable|desired|beneficial|preferred|preferably|"
    r"ideally|helpful|welcome|optional|appreciated|would be|not (required|needed|necessary|essential|mandatory)|"
    r"lessons|classes|course|von vorteil|wunschenswert|un plus|un atout|souhaite|gradit[oa]|preferibile|"
    r"valorable|mile widzian\w+|een pre)\b", re.I)
_SOFT_BEFORE = re.compile(r"\b(preferably|ideally|nice to have|bonus|plus|optional\w*|desirable)\W*$", re.I)
_CLAUSE_END = re.compile(r"[.;!?\n]")
_OWN: dict[str, re.Pattern[str]] = {code: re.compile(own) for code, (_n, own) in LANGUAGES.items() if own}


def _folded(value: str) -> str:
    """Accents folded, case kept: language names are told from ordinary words by their capital."""
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c))


def language_requirements(job: Job, levels: dict[str, str]) -> list[tuple[str, str]]:
    """Languages the posting requires above the level in `levels`: [(code, level asked)].

    A requirement is a sentence, not a word: "Dutch is a plus", "free Dutch
    lessons" and "our Dutch and German entities" ask for nothing; "fluent
    German or English" is met by either; "fluent English and Dutch" asks for
    both.
    """
    text = _folded(job.text())
    lowered = text.lower()
    need: dict[str, str] = {}

    def has(code: str, level: str) -> bool:
        have = levels.get(code, "")
        return have in CEFR and CEFR.index(have) >= CEFR.index(level)

    def ask(code: str, level: str) -> None:
        if code not in need or CEFR.index(level) > CEFR.index(need[code]):
            need[code] = level

    if any(name.lower() in lowered for name in _NAMES):
        for match in _REQUIREMENT.finditer(text):
            start = max((m.end() for m in _CLAUSE_END.finditer(text, 0, match.start())), default=0)
            stop = _CLAUSE_END.search(text, match.end())
            after = text[match.end():stop.start() if stop else len(text)]
            if _SOFT.search(re.split(r"\b(?:and|but)\b", after)[0]) or _SOFT_BEFORE.search(text[start:match.start()]):
                continue
            chain = next(g for g in match.groups()[2:] if g and g[0].isupper())
            codes = [_NAMES[n.capitalize()] for n in re.findall("|".join(_NAMES), chain, re.I)]
            strong = match.group("strong") or match.group("after") or match.group("trail") or match.group("speaking")
            level = "C1" if strong else "B2"
            if _EITHER.search(chain) and any(has(c, level) for c in codes):
                continue                                   # either of them, and the profile has one
            for code in codes:
                ask(code, level)
    for code, own in _OWN.items():
        if code not in need and own.search(lowered):
            ask(code, "C1")
    for match in _TITLE_LANGUAGE.finditer(_folded(job.title)):
        name = next(g for g in match.groups() if g)
        if _NAMES[name.capitalize()] not in need:
            ask(_NAMES[name.capitalize()], "B2")
    return [(code, level) for code, level in need.items() if not has(code, level)]


@dataclass(slots=True)
class Gate:
    """A hard rule. Failing one rejects the job whatever the score."""

    name: str
    reason: str


_PATTERNS: dict[str, re.Pattern[str]] = {}


def _plain(value: str) -> str:
    """Lowercase, accents folded, punctuation kept."""
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c)).lower()


def _compiled(pattern: str) -> re.Pattern[str]:
    if pattern not in _PATTERNS:
        _PATTERNS[pattern] = re.compile(pattern, re.I)
    return _PATTERNS[pattern]


def check_gates(job: Job, profile: dict[str, Any], text: str | None = None) -> list[Gate]:
    prefs = profile.get("preferences", {})
    text = canonical(job.text()) if text is None else text
    failures: list[Gate] = []

    # Language: a role that demands a language above the candidate's level is
    # not a fit, however good everything else looks.
    levels = {l["code"]: l.get("level", "") for l in profile.get("languages", [])}
    order = CEFR
    gated: set[str] = set()
    if prefs.get("language_gates_builtin", True):
        for code, need in language_requirements(job, levels):
            gated.add(code)
            failures.append(Gate(
                "language",
                f"requires {LANGUAGES[code][0]} at ~{need} (profile: {levels.get(code) or 'none'})",
            ))
    # The profile's own rules: patterns written for a language or a phrasing
    # the built-in reading does not cover.
    rules = [r for r in prefs.get("language_gates", []) if r["code"] not in gated]
    # Language rules read the posting with its punctuation kept: the canonical
    # text has no full stops, so "excellent communication. ...our Polish
    # entities" read as one phrase and rejected roles that never asked for Polish.
    plain = _plain(job.text()) if rules else ""
    for rule in rules:
        code = rule["code"]
        # `word` is an optional cheap test (the language's name): most postings
        # never mention Swedish, and the full pattern is not worth running on them.
        if rule.get("word") and not _compiled(rule["word"]).search(plain):
            continue
        if not _compiled(rule["pattern"]).search(plain):
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
    if allowed and job.country and job.country not in allowed:
        # "Remote" almost never means "remote from anywhere": a role listed as
        # remote in Bangalore or New York is still hiring in that country. Only
        # a posting whose country cannot be determined gets the benefit of the
        # doubt.
        failures.append(Gate("location", f"{job.country} outside target countries"))

    for term in prefs.get("hard_reject_keywords", []):
        if _matches([term], text):
            failures.append(Gate("keyword", f"posting mentions '{term}'"))

    seniority = detect_seniority(job.title, job.description)
    years_have = int(profile.get("years_experience", 0))
    if seniority in prefs.get("seniority_reject", []):
        failures.append(Gate("seniority", f"role reads as '{seniority}'"))
    elif (seniority == "intern" and "intern" not in prefs.get("seniority_target", ["junior", "mid"])
          and years_have >= INTERN_UNTIL_YEARS):
        # An internship is for students; nobody with years of work behind them is its audience.
        failures.append(Gate("seniority", f"an internship (profile: {years_have} years of experience)"))

    stretch = required_years(job.description) - years_have
    if stretch >= YEARS_REJECT_AT:
        failures.append(Gate(
            "experience",
            f"asks {required_years(job.description)} years (profile: {years_have})",
        ))

    # Match the terms of employment, not any mention of the words. "Volunteer"
    # on its own appears in the benefits section of well-paid jobs — offering
    # volunteering days is a perk, and treating it as a red flag rejected 671
    # perfectly good postings before anyone noticed.
    if re.search(
        r"\b(commission[- ]only|100% commission|no basic salary|no salary"
        r"|unpaid (internship|position|role|placement|work)"
        r"|volunteer (position|role|opportunity|basis|placement)"
        r"|on a voluntary basis|without remuneration)\b", text
    ):
        failures.append(Gate("terms", "unpaid or commission-only"))

    return failures


def score_job(job: Job, profile: dict[str, Any], track: dict[str, Any],
              text: str | None = None, gates: list[Gate] | None = None) -> Score:
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
    # Asking clearly more years than the profile has keeps a posting out of the
    # passes whatever else it scores: it is read, not prepared.
    capped = stretch >= YEARS_REVIEW_AT
    total += sen_points

    # --- penalties -------------------------------------------------------
    anti = track.get("anti", []) + prefs.get("soft_reject_keywords", [])
    anti_hits = _matches(anti, text)
    # In the title the term names the job itself ("Software Engineer, HR Tech"),
    # not something the posting mentions in passing: it weighs three times as much.
    in_title = _matches(anti, title_c)
    penalty = min(25.0, 6.0 * len(anti_hits) + 12.0 * len(in_title))
    if anti_hits:
        breakdown["penalties"] = {"points": -round(penalty, 1), "matched": anti_hits}
        if in_title:
            breakdown["penalties"]["in_title"] = in_title
    total -= penalty

    # --- gates -----------------------------------------------------------
    if gates is None:
        gates = check_gates(job, profile, text)
    if gates:
        breakdown["gates"] = [{"gate": g.name, "reason": g.reason} for g in gates]

    final = max(0, min(100, round(total)))
    if gates:
        verdict = "reject"
    elif final >= PASS_AT:
        verdict = "review" if capped else "pass"
        if capped:
            breakdown["seniority"]["capped"] = True
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
    # Gates depend on the posting and the profile, never on the track: checked once.
    gates = check_gates(job, profile, text)
    return sorted(
        (score_job(job, profile, t, text, gates) for t in tracks),
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
            if d.get("capped"):
                detail += f" against {d['years_profile']}: read it, at most"
        lines.append(f"  {dim:<10} {d['points']:>5}/{d['max']:<3} {detail}")
    if "penalties" in b:
        lines.append(f"  {'penalty':<10} {b['penalties']['points']:>5}     {', '.join(b['penalties']['matched'])}")
    for gate in b.get("gates", []):
        lines.append(f"  GATE       {gate['gate']}: {gate['reason']}")
    return "\n".join(lines)
