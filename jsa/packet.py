"""Assemble everything needed to submit an application, in one folder.

The last mile of a job application is not writing the CV — it is the twenty
minutes of retyping the same answers into yet another form. A packet puts the
documents, the standard answers and a submission checklist in one place, so
what is left for a human is reading it and pressing send.

Submitting is deliberately left to the human: forms are consent, and a machine
should not be clicking 'apply' on someone's behalf.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Job
from .util import slugify, today


def _answers(cfg: Any) -> dict[str, Any]:
    path = cfg.home / "answers.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_packet(
    cfg: Any,
    job: Job,
    *,
    cv_path: Path | None,
    cover_path: Path | None,
    track: dict[str, Any],
    ats_report: Any = None,
    notes: str = "",
) -> Path:
    """Create `output/<company>_<role>/` with documents, answers and a checklist."""
    folder = cfg.output_dir / f"{slugify(job.company)}_{slugify(job.title, 32)}"
    folder.mkdir(parents=True, exist_ok=True)

    for source in (cv_path, cover_path):
        if source and Path(source).exists() and Path(source).parent != folder:
            target = folder / Path(source).name
            target.write_bytes(Path(source).read_bytes())

    answers = _answers(cfg)
    todos = [k for k, v in answers.items() if isinstance(v, str) and v.startswith("TODO")]

    lines = [
        f"# {job.title} — {job.company}",
        "",
        f"- **Posting**: {job.url or 'n/a'}",
        f"- **Location**: {job.location or 'n/a'} ({job.remote})",
        f"- **Source**: {job.source}",
        f"- **Track**: {track['id']} — {track['label']}",
        f"- **Packet built**: {today()}",
        "",
        "## Before you send",
        "",
        "- [ ] Read the CV end to end — every line is yours to defend",
        "- [ ] Read the cover letter aloud once",
        "- [ ] Check the company name and role title in both documents",
        "- [ ] Attach both files in the format the form asks for",
        "- [ ] Log it: `python3 -m jsa status " + job.id[:8] + " submitted`",
        "",
    ]
    if ats_report is not None:
        lines += ["## ATS check", "", "```", ats_report.render(), "```", ""]
    if answers:
        lines += ["## Standard form answers", ""]
        for key, value in answers.items():
            if key.startswith("_"):
                continue
            label = key.replace("_", " ").capitalize()
            lines.append(f"**{label}** — {value}")
            lines.append("")
    if todos:
        lines += [
            "> These answers are still marked TODO and will slow you down mid-form: "
            + ", ".join(todos) + ". Fill them in `profile/answers.json` once.",
            "",
        ]
    if notes:
        lines += ["## Notes", "", notes, ""]

    (folder / "SUBMIT.md").write_text("\n".join(lines), encoding="utf-8")
    (folder / "posting.txt").write_text(
        f"{job.title}\n{job.company}\n{job.location}\n{job.url}\n\n{job.description}",
        encoding="utf-8",
    )
    return folder
