"""Your own CVs, attached as they are.

A CV someone has written and laid out themselves — one per positioning, one
for a company they are courting — reads better than one assembled from JSON,
and it is the document they will be asked about. So the engine does not
rewrite it: it decides which of them fits a posting and attaches that file
unchanged. A CV written for the company wins; then the one for the winning
track; when neither exists, the generated .docx is used as before.

The files live in <workspace>/cv/, next to an index that says which is which.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .docx import extract_text as docx_text
from .models import Job, canonical
from .pdftext import extract as pdf_text
from .pdftext import legibility

INDEX = "cv.json"
SUPPORTED = (".pdf", ".docx")


def folder(home: Path) -> Path:
    return home / "cv"


def load(home: Path) -> dict[str, dict[str, str]]:
    """{"tracks": {track_id: file}, "companies": {canonical name: file}}."""
    path = folder(home) / INDEX
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"tracks": dict(data.get("tracks", {})), "companies": dict(data.get("companies", {}))}


def _save(home: Path, index: dict[str, dict[str, str]]) -> None:
    path = folder(home) / INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def text_of(path: Path) -> str:
    """What an applicant tracking system would read out of the file."""
    return pdf_text(path) if path.suffix.lower() == ".pdf" else docx_text(path)


def check(path: Path, profile: dict[str, Any]) -> list[str]:
    """What would make this file a poor thing to send, in plain words."""
    try:
        text = text_of(path)
    except Exception as exc:  # noqa: BLE001 - any failure to read is the finding
        return [f"it could not be read ({type(exc).__name__}: {exc})"]
    problems = []
    if legibility(text) < 0.85:
        problems.append("an ATS reads it as garbled text — export it again, or use the .docx")
    identity = profile.get("identity", {})
    email = identity.get("email", "")
    if email and email.lower() not in text.lower():
        problems.append(f"it does not contain your email ({email}) — is it an old version?")
    return problems


def add(home: Path, source: Path, *, track: str | None = None, company: str | None = None) -> Path:
    """Copy the file into the workspace and record what it is for."""
    if bool(track) == bool(company):
        raise ValueError("say what the CV is for: --track or --company, not both")
    if source.suffix.lower() not in SUPPORTED:
        raise ValueError(f"{source.name}: send a .pdf or a .docx")
    if not source.is_file():
        raise ValueError(f"{source} does not exist")
    target = folder(home) / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    index = load(home)
    if track:
        index["tracks"][track] = target.name
    else:
        index["companies"][canonical(company)] = target.name
    _save(home, index)
    return target


def remove(home: Path, *, track: str | None = None, company: str | None = None) -> bool:
    """Forget a CV. The file stays in cv/ until you delete it yourself."""
    index = load(home)
    removed = index["tracks"].pop(track, None) if track else index["companies"].pop(canonical(company), None)
    if removed:
        _save(home, index)
    return removed is not None


def pick(home: Path, job: Job, track_id: str) -> Path | None:
    """The file to send for this posting, or None to use the generated CV."""
    index = load(home)
    name = canonical(job.company)
    for key, file in index["companies"].items():
        # "revolut" matches "Revolut Ltd" and "Revolut Business", never "Evolut".
        if key == name or f" {key} " in f" {name} ":
            path = folder(home) / file
            if path.exists():
                return path
    file = index["tracks"].get(track_id)
    if file and (folder(home) / file).exists():
        return folder(home) / file
    return None
