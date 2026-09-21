"""Read an existing CV and turn it into a profile draft.

Nobody wants to retype their career. This reads the CV someone already has —
.docx, .pdf or plain text — and fills in as much of the profile as it can
recognise, then says plainly what it could not work out so a human can finish
the job.

Everything here is heuristic and admits it. A CV has no schema: the same
section is called Experience, Professional Experience or Esperienza, dates sit
anywhere, and half the layout meaning is carried by a font size this module
cannot see. So the parser aims to be *useful and honest* rather than complete —
it reports its own gaps instead of quietly inventing structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .docx import extract_text as docx_text
from .pdftext import extract as pdf_text
from .pdftext import legibility
from .sources.ats import guess_country

# Section headings, English and Italian. Matched on a whole line.
SECTIONS: dict[str, list[str]] = {
    "summary": ["profile", "summary", "professional summary", "about", "profilo",
                "sommario", "chi sono"],
    "experience": ["experience", "professional experience", "work experience",
                   "employment", "esperienza", "esperienze", "esperienza professionale",
                   "esperienze lavorative"],
    "education": ["education", "academic background", "formazione", "istruzione",
                  "formazione accademica"],
    "skills": ["skills", "core skills", "technical skills", "key skills", "competenze",
               "competenze tecniche", "competenze chiave"],
    "languages": ["languages", "languages & certifications", "languages and certifications",
                  "lingue", "lingue e certificazioni"],
    "certifications": ["certifications", "certificates", "certificazioni", "attestati"],
    "projects": ["projects", "portfolio", "progetti", "people analytics projects"],
    "research": ["research", "publications", "research & publications", "pubblicazioni",
                 "ricerca e pubblicazioni"],
    "additional": ["additional experience", "other experience", "altre esperienze",
                   "esperienze aggiuntive", "volunteering"],
}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().\-/]{7,}\d")
LINKEDIN = re.compile(r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/[\w%-]+", re.I)
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w.-]+", re.I)

MONTH = (r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
         r"|Gen|Mag|Giu|Lug|Ago|Set|Ott|Dic)[a-z]*")
# "Apr 2026 – Present", "2021 – 2025", "Nov 2025 - Jan 2026", "May – Oct 2025"
DATE_RANGE = re.compile(
    rf"((?:{MONTH}\s*)?\d{{4}}|{MONTH})\s*[–—−-]\s*"
    rf"((?:{MONTH}\s*)?\d{{4}}|{MONTH}|Presente|Present|Attuale|Today|oggi)",
    re.I,
)
LEVEL = re.compile(r"\b(A1|A2|B1|B2|C1|C2|native|madrelingua|mother ?tongue|fluent)\b", re.I)
SPLIT = re.compile(r"\s*[·•|;]\s*|\s{3,}")
BULLET = re.compile(r"^\s*[•·▪◦\-–—*]\s*")


@dataclass
class Draft:
    """What the parser managed to recognise, and what it did not."""

    name: str = ""
    headline: str = ""
    location: str = ""
    country: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    languages: list[dict[str, str]] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, str]] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    source: str = ""
    characters: int = 0


class UnreadableCV(Exception):
    """The file was opened but no usable text came out."""


def read_text(path: str | Path) -> tuple[str, str]:
    """Return (text, how it was read). Raises UnreadableCV when it is hopeless."""
    file = Path(path).expanduser()
    if not file.exists():
        raise UnreadableCV(f"{file} does not exist.")
    suffix = file.suffix.lower()

    if suffix == ".docx":
        text, how = docx_text(file), "docx"
    elif suffix == ".pdf":
        text, how = pdf_text(file), "pdf"
        quality = legibility(text)
        if not text or quality < 0.85:
            raise UnreadableCV(
                f"{file.name} did not yield readable text ({quality:.0%} usable characters).\n"
                "  This happens with scanned PDFs and with some exporters that embed fonts\n"
                "  without a character map. Export the same CV as .docx and import that, or\n"
                "  paste the text into a .txt file and import that instead."
            )
    elif suffix in (".txt", ".md", ".text"):
        text, how = file.read_text(encoding="utf-8", errors="replace"), "text"
    else:
        raise UnreadableCV(
            f"I cannot read {suffix or 'that file'}. Supported: .docx, .pdf, .txt"
        )
    if len(text.strip()) < 200:
        raise UnreadableCV(f"{file.name} contains almost no text ({len(text.strip())} characters).")
    return text, how


def _heading(line: str) -> str | None:
    """Which section a line announces, if any.

    Spaces are stripped before comparing, because designers letter-space
    headings ("P R O F E S S I O N A L  S U M M A R Y") and a PDF preserves
    that faithfully.
    """
    cleaned = re.sub(r"[^a-zàèéìòù]", "", line.lower())
    if not cleaned or len(cleaned) > 42:
        return None
    for section, labels in SECTIONS.items():
        if any(cleaned == label.replace(" ", "").replace("&", "") for label in labels):
            return section
    return None


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"_header": []}
    current = "_header"
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        found = _heading(line)
        if found:
            current = found
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _identity(header: list[str], draft: Draft) -> None:
    blob = "\n".join(header)
    if m := EMAIL.search(blob):
        draft.email = m.group(0)
    if m := LINKEDIN.search(blob):
        draft.linkedin = m.group(0).replace("https://", "").replace("http://", "")
    if m := GITHUB.search(blob):
        draft.github = m.group(0).replace("https://", "").replace("http://", "")
    for line in header:
        if m := PHONE.search(line):
            candidate = m.group(0).strip()
            if 8 <= len(re.sub(r"\D", "", candidate)) <= 15:
                draft.phone = candidate
                break

    if header:
        draft.name = header[0].strip()
        # A CV headline is the line under the name, usually with separators.
        for line in header[1:4]:
            if SPLIT.search(line) and not EMAIL.search(line) and not PHONE.search(line):
                if guess_country(line):
                    draft.location, draft.country = line, guess_country(line)
                elif not draft.headline:
                    draft.headline = line
        if not draft.location:
            for line in header[1:5]:
                if code := guess_country(line):
                    draft.location, draft.country = line, code
                    break


def _languages(lines: list[str], draft: Draft) -> None:
    for line in lines:
        for piece in SPLIT.split(line):
            piece = piece.strip()
            if not piece or not LEVEL.search(piece):
                continue
            level = LEVEL.search(piece).group(1)
            name = re.sub(r"[(),]", " ", piece.replace(level, "")).strip(" -–—:")
            if 2 <= len(name) <= 24:
                normalised = {"madrelingua": "native", "mother tongue": "native",
                              "fluent": "C1"}.get(level.lower(), level.upper())
                draft.languages.append({"code": name[:2].lower(), "name": name.title(),
                                        "level": "native" if normalised == "NATIVE" else normalised})


def _skills(lines: list[str], draft: Draft) -> None:
    for line in lines:
        body = re.sub(r"^[A-Za-zÀ-ÿ &]{3,28}:\s*", "", BULLET.sub("", line))
        for piece in SPLIT.split(body):
            piece = piece.strip(" .,")
            if 2 <= len(piece) <= 60:
                draft.skills.append(piece)


def _experience(lines: list[str], draft: Draft) -> None:
    entry: dict[str, Any] | None = None
    for line in lines:
        match = DATE_RANGE.search(line)
        if match and len(line) < 160:
            if entry:
                draft.experience.append(entry)
            title = line[:match.start()].strip(" ,–—-·|")
            entry = {"title": title or line.strip(), "company": "", "location": "",
                     "start": match.group(1).strip(), "end": match.group(2).strip(),
                     "bullets": []}
            continue
        if entry is None:
            continue
        if not entry["company"] and not BULLET.match(line) and len(line) < 110:
            parts = [p.strip() for p in SPLIT.split(line) if p.strip()]
            entry["company"] = parts[0] if parts else line
            entry["location"] = " · ".join(parts[1:]) if len(parts) > 1 else ""
            continue
        entry["bullets"].append({"text": BULLET.sub("", line), "tracks": ["*"]})
    if entry:
        draft.experience.append(entry)


def _education(lines: list[str], draft: Draft) -> None:
    entry: dict[str, str] | None = None
    for line in lines:
        match = DATE_RANGE.search(line) or re.search(r"\b(19|20)\d{2}\b", line)
        looks_like_degree = re.search(
            r"\b(BSc|MSc|BA|MA|MBA|PhD|Laurea|Master|Diploma|Bachelor|Degree|LM-\d+|L-\d+)\b",
            line, re.I)
        if looks_like_degree or (match and entry is None):
            if entry:
                draft.education.append(entry)
            date = match.group(0) if match else ""
            grade = g.group(0) if (g := re.search(r"\b\d{2,3}\s*/\s*110\b", line)) else ""
            degree = line.replace(date, "").replace(grade, "").strip(" —–-·,|")
            entry = {"degree": degree, "institution": "", "date": date.strip(),
                     "grade": grade, "detail": "", "thesis": ""}
        elif entry is not None and not entry["institution"]:
            entry["institution"] = SPLIT.split(line)[0].strip()
            rest = SPLIT.split(line)[1:]
            entry["detail"] = " · ".join(r.strip() for r in rest)
    if entry:
        draft.education.append(entry)


def parse(text: str, source: str = "") -> Draft:
    draft = Draft(source=source, characters=len(text))
    sections = split_sections(text)

    _identity(sections.get("_header", []), draft)
    if summary := sections.get("summary"):
        draft.summary = " ".join(summary)
    if skills := sections.get("skills"):
        _skills(skills, draft)
    if langs := sections.get("languages"):
        _languages(langs, draft)
        draft.certifications += [l for l in langs if not LEVEL.search(l) and len(l) > 12]
    if certs := sections.get("certifications"):
        draft.certifications += certs
    if exp := sections.get("experience"):
        _experience(exp, draft)
    if edu := sections.get("education"):
        _education(edu, draft)

    for label, value in (("name", draft.name), ("email", draft.email), ("phone", draft.phone),
                         ("location", draft.location), ("summary", draft.summary),
                         ("skills", draft.skills), ("languages", draft.languages),
                         ("experience", draft.experience), ("education", draft.education)):
        if not value:
            draft.missing.append(label)
    return draft


def to_profile(draft: Draft, base: dict[str, Any]) -> dict[str, Any]:
    """Merge a draft into the example profile's shape, keeping its defaults."""
    import copy

    profile = copy.deepcopy(base)
    profile["_comment"] = ("Imported from a CV by `jsa import`, then edited by hand. "
                           "Factual only — the tailoring overlay may select and reorder "
                           "what is here, never invent.")
    identity = profile.setdefault("identity", {})
    for key, value in (("name", draft.name), ("headline", draft.headline),
                       ("location", draft.location), ("email", draft.email),
                       ("phone", draft.phone), ("linkedin", draft.linkedin),
                       ("github", draft.github)):
        if value:
            identity[key] = value

    if draft.summary:
        profile["summaries"] = {key: draft.summary for key in profile.get("summaries", {})} or \
                               {"hr_advisory": draft.summary}
    if draft.skills:
        groups = profile.setdefault("skill_groups", {})
        first = next(iter(groups), "hr_core")
        groups.setdefault(first, {"label": "Skills", "items": []})
        groups[first]["items"] = draft.skills
    if draft.languages:
        profile["languages"] = draft.languages
    if draft.experience:
        profile["experience"] = draft.experience
    if draft.education:
        profile["education"] = draft.education
    if draft.certifications:
        profile["certifications"] = draft.certifications
    if draft.country:
        allowed = profile.setdefault("preferences", {}).setdefault("countries_allowed", [])
        if draft.country not in allowed:
            allowed.append(draft.country)
    return profile
