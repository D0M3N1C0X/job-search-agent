"""Turn the profile into a CV and a cover letter.

Two rules run through this module:

1. **Nothing is invented.** A tailoring overlay may reorder, drop, select and
   reword — but every bullet it selects must already exist in the profile. A
   bullet that is not in the pool is dropped and reported, not printed.
2. **Length is enforced, not hoped for.** Bullet budgets keep the CV to two
   pages instead of discovering the overflow after sending.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .docx import Document, extract_text
from .models import canonical
from .util import log, slugify

MAX_BULLETS_PER_ROLE = 4
MAX_TOTAL_BULLETS = 16


def _pick_bullets(pool: list[dict[str, Any]], track_id: str, limit: int) -> list[str]:
    """Bullets tagged for this track (or for all tracks), in profile order."""
    chosen = [b["text"] for b in pool if "*" in b.get("tracks", []) or track_id in b.get("tracks", [])]
    return chosen[:limit]


@dataclass
class Overlay:
    """Per-application tailoring. Selection and emphasis only."""

    track: str = ""
    summary: str = ""
    select: dict[str, list[str]] = field(default_factory=dict)
    skill_groups: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    extra_skills: list[str] = field(default_factory=list)
    max_bullets_per_role: int = MAX_BULLETS_PER_ROLE
    rejected: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Overlay":
        data = dict(data or {})
        known = {f for f in cls.__dataclass_fields__ if f != "rejected"}
        return cls(**{k: v for k, v in data.items() if k in known})

    def validate(self, profile: dict[str, Any]) -> list[str]:
        """Drop any selected bullet that is not literally in the profile."""
        pool = set()
        for role in profile.get("experience", []):
            pool.update(b["text"] for b in role.get("bullets", []))
        for project in profile.get("projects", {}).get("items", []):
            pool.update(b["text"] for b in project.get("bullets", []))
        for key, bullets in list(self.select.items()):
            kept = [b for b in bullets if b in pool]
            dropped = [b for b in bullets if b not in pool]
            if dropped:
                self.rejected.extend(dropped)
                log.warning("overlay: dropped %d fabricated bullet(s) for %s", len(dropped), key)
            self.select[key] = kept
        return self.rejected


def build_cv(
    profile: dict[str, Any],
    track: dict[str, Any],
    *,
    overlay: Overlay | None = None,
    path: str | Path,
) -> Path:
    overlay = overlay or Overlay()
    overlay.validate(profile)
    track_id = track["id"]
    identity = profile["identity"]

    doc = Document(
        title=f"CV — {identity['name']}",
        author=identity["name"],
    )
    doc.name(identity["name"].upper())
    doc.contact(track.get("label", identity.get("headline", "")))
    contact_bits = [
        identity.get("location", ""), identity.get("citizenship", ""), identity.get("relocation", ""),
    ]
    doc.contact(" · ".join(b for b in contact_bits if b))
    reach = [identity.get("phone", ""), identity.get("email", ""),
             identity.get("linkedin", ""), identity.get("github", "")]
    doc.contact(" · ".join(b for b in reach if b))

    sections = overlay.sections or track.get("sections", ["summary", "skills", "experience", "education", "languages"])
    budget = MAX_TOTAL_BULLETS

    for section in sections:
        if section == "summary":
            text = overlay.summary or profile["summaries"].get(track.get("summary_key", track_id), "")
            if text:
                doc.section("Profile")
                doc.paragraph(text)

        elif section == "skills":
            groups = overlay.skill_groups or track.get("skill_groups", [])
            if not groups:
                continue
            doc.section("Core skills")
            for key in groups:
                group = profile.get("skill_groups", {}).get(key)
                if not group:
                    continue
                items = list(group["items"])
                if key == groups[0]:
                    items += [s for s in overlay.extra_skills if s not in items]
                doc.paragraph(f"{group['label']}: " + " · ".join(items), style="Bullet")

        elif section == "experience":
            doc.section("Professional experience")
            for role in profile.get("experience", []):
                selected = overlay.select.get(role["company"])
                bullets = selected if selected else _pick_bullets(
                    role.get("bullets", []), track_id, overlay.max_bullets_per_role
                )
                bullets = bullets[:max(0, min(len(bullets), budget))]
                budget -= len(bullets)
                doc.role(f"{role['title']} — {role['company']}", f"{role['start']} – {role['end']}")
                doc.meta(role.get("location", ""))
                for bullet in bullets:
                    doc.bullet(bullet)

        elif section == "projects":
            projects = profile.get("projects", {})
            if not projects.get("items"):
                continue
            doc.section("People analytics projects")
            if projects.get("note"):
                doc.meta(projects["note"])
            for project in projects["items"]:
                selected = overlay.select.get(project["name"])
                bullets = selected if selected else _pick_bullets(
                    project.get("bullets", []), track_id, overlay.max_bullets_per_role
                )
                bullets = bullets[:max(0, min(len(bullets), budget))]
                budget -= len(bullets)
                doc.role(f"{project['name']} — {project['stack']}", project.get("url", ""))
                for bullet in bullets:
                    doc.bullet(bullet)

        elif section == "education":
            doc.section("Education")
            for entry in profile.get("education", []):
                grade = f" — {entry['grade']}" if entry.get("grade") else ""
                doc.role(f"{entry['degree']}{grade}", entry.get("date", ""))
                line = entry.get("institution", "")
                if entry.get("detail"):
                    line += f" · {entry['detail']}"
                doc.meta(line)
                if entry.get("thesis"):
                    doc.meta(f"Thesis: {entry['thesis']}")

        elif section == "research":
            items = profile.get("research", [])
            if items:
                doc.section("Research & publications")
                for item in items:
                    doc.bullet(item)

        elif section == "additional":
            items = profile.get("additional_experience", [])
            if items:
                doc.section("Additional experience")
                for entry in items:
                    doc.role(f"{entry['title']} — {entry['company']}", f"{entry['start']} – {entry['end']}")
                    doc.meta(entry.get("location", ""))

        elif section == "languages":
            doc.section("Languages & certifications")
            langs = " · ".join(f"{l['name']} ({l['level']})" for l in profile.get("languages", []))
            doc.paragraph(langs, style="Bullet")
            for cert in profile.get("certifications", []):
                doc.bullet(cert)

    return doc.save(path)


# ------------------------------------------------------------ cover letter

GREETINGS = {
    "en": ("Dear Hiring Team,", "Kind regards,"),
    "it": ("Gentile Team di selezione,", "Cordiali saluti,"),
}


def build_cover(
    profile: dict[str, Any],
    letter: dict[str, Any],
    *,
    path: str | Path,
) -> Path:
    """`letter` carries the drafted content: company, role, language, paragraphs."""
    identity = profile["identity"]
    language = letter.get("language", "en")
    if language not in GREETINGS:
        language = "en"
    greeting, closing = GREETINGS[language]

    doc = Document(title=f"Cover letter — {letter.get('company', '')}", author=identity["name"])
    doc.name(identity["name"])
    doc.contact(" · ".join(x for x in [
        identity.get("location", ""), identity.get("phone", ""), identity.get("email", ""),
        identity.get("linkedin", ""),
    ] if x))
    doc.spacer(10)
    header = [letter.get("company", ""), letter.get("company_location", ""), letter.get("date", "")]
    for line in [h for h in header if h]:
        doc.paragraph(line, style="Bullet")
    doc.spacer(8)
    subject = letter.get("subject") or (
        f"Application — {letter.get('role', '')}" if language == "en"
        else f"Candidatura — {letter.get('role', '')}"
    )
    doc.paragraph(subject, style="RoleLine")
    doc.spacer(4)
    doc.paragraph(letter.get("greeting") or greeting)
    for paragraph in letter.get("paragraphs", []):
        doc.paragraph(paragraph)
    doc.spacer(6)
    doc.paragraph(letter.get("closing") or closing)
    doc.paragraph(identity["name"])
    return doc.save(path)


# --------------------------------------------------------------- ATS check

_STOP = set("""a an the and or of to in for with on at by from as is are be am was were been being
we you our your their they it its this that these those there here he she them us my me
role roles team teams work working works experience experiences years year will would shall should
can could may might must have has had who what where which within across including include includes
job jobs position positions company companies candidate candidates able strong good great new
using use used also more most many much other others such very well both each any all one two
about into over under between during than then when while because so if but not no yes
help helps helping make makes making made take takes taking get gets look looking join joining
high low clear ideal plus etc via per level levels part full time day days week weeks month months
you'll we're we'll it's don't opportunity opportunities environment culture people-first
impact impactful decisions decision insights insight business ability skills skill knowledge
""".split())

_TOKEN = re.compile(r"[a-z][a-z+#./-]{2,}")


def keywords(text: str, limit: int = 30, exclude: set[str] | None = None) -> list[str]:
    """Frequent, meaningful terms of a posting — the ATS keyword surface.

    The employer's own name is excluded: a CV is not supposed to repeat it, so
    counting it as a missing keyword only produces noise in the report.
    """
    exclude = exclude or set()
    counts: dict[str, int] = {}
    for token in _TOKEN.findall(canonical(text)):
        if token in _STOP or token in exclude or len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, count in ranked if count >= 2][:limit]


@dataclass
class AtsReport:
    ok: bool
    words: int
    bullets: int
    est_pages: float
    contact_ok: bool
    name_first: bool
    covered: list[str]
    missing: list[str]
    problems: list[str]

    def render(self) -> str:
        lines = [
            f"ATS check: {'PASS' if self.ok else 'REVIEW'}",
            f"  length      {self.words} words, {self.bullets} bullets "
            f"(~{self.est_pages:.1f} pages estimated — confirm in Word before sending)",
            f"  contact     {'email + phone found' if self.contact_ok else 'MISSING email or phone'}",
            f"  reading     {'name in first lines' if self.name_first else 'name not at the top'}",
            f"  keywords    {len(self.covered)}/{len(self.covered) + len(self.missing)} "
            f"covered (informational — do not stuff)",
        ]
        if self.missing:
            lines.append("  not covered " + ", ".join(self.missing[:12]))
        for problem in self.problems:
            lines.append(f"  ! {problem}")
        return "\n".join(lines)


def ats_check(cv_path: str | Path, profile: dict[str, Any], job_text: str = "",
              company: str = "") -> AtsReport:
    """Read the generated .docx back and verify what an ATS would see.

    Missing keywords are reported, never auto-inserted: a gap in the profile
    is information, not something to paper over.
    """
    text = extract_text(cv_path)
    lower = canonical(text)
    identity = profile["identity"]
    words = len(text.split())
    problems: list[str] = []

    contact_ok = identity["email"].lower() in text.lower() and any(
        part in text for part in identity["phone"].split() if len(part) > 3
    )
    name_first = canonical(identity["name"]) in canonical("\n".join(text.split("\n")[:3]))
    bullets = sum(1 for line in text.split("\n") if line.startswith("•"))
    if words > 1050:
        problems.append(
            "likely over two pages — drop two or three bullets, or shorten the summary")
    if words < 250:
        problems.append("unusually short for a two-page CV")

    covered: list[str] = []
    missing: list[str] = []
    excluded = set(canonical(company).split())
    for word in keywords(job_text, exclude=excluded):
        (covered if re.search(rf"(?<![a-z0-9]){re.escape(word)}", lower) else missing).append(word)

    # Keyword coverage is reported, never scored: a posting's frequent words
    # include the hiring manager's name and half a paragraph of filler, and a
    # genuine gap should stay visible rather than fail a check that tempts you
    # to close it by stuffing. What can fail is mechanical: contact details,
    # reading order, length.
    ok = contact_ok and name_first and not problems
    return AtsReport(
        ok=ok, words=words, bullets=bullets, est_pages=round(words / 520, 1), contact_ok=contact_ok,
        name_first=name_first, covered=covered, missing=missing, problems=problems,
    )


def output_name(prefix: str, company: str, role: str = "") -> str:
    bits = [prefix, slugify(company)]
    if role:
        bits.append(slugify(role, 28))
    return "_".join(bits) + ".docx"
