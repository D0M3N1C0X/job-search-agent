"""Job-alert emails as a source.

Instead of fighting a portal's bot defences, let the portal do the searching
and mail you the results: LinkedIn, Indeed, Pracuj and EURES all send alert
emails. Export or save them into one folder and this reads them locally — no
credentials, no scraping, and it works for portals that block everything else.

Emails are parsed as *data*: nothing inside them is executed or followed as an
instruction, and only the job links are extracted.
"""

from __future__ import annotations

import email
import email.policy
import mailbox as _mailbox
import re
from pathlib import Path
from typing import Any, Iterator

from ..models import Job
from ..util import html_to_text, log
from . import register

# Recognised job-link shapes, most specific first.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("linkedin", re.compile(r"https?://[\w.]*linkedin\.com/(?:comm/)?jobs/view/(\d+)")),
    ("indeed", re.compile(r"https?://[\w.]*indeed\.com/[^\s\"'<>]*[?&]jk=([0-9a-f]+)")),
    ("pracuj", re.compile(r"https?://[\w.]*pracuj\.pl/praca/[^\s\"'<>]*?,oferta,(\d+)")),
    ("greenhouse", re.compile(r"https?://(?:boards|job-boards)\.greenhouse\.io/([\w-]+)/jobs/(\d+)")),
    ("lever", re.compile(r"https?://jobs\.lever\.co/([\w-]+)/([\w-]+)")),
    ("ashby", re.compile(r"https?://jobs\.ashbyhq\.com/([\w.-]+)/([\w-]+)")),
    ("workable", re.compile(r"https?://apply\.workable\.com/([\w-]+)/j/([\w]+)")),
    ("smartrecruiters", re.compile(r"https?://jobs\.smartrecruiters\.com/([\w-]+)/(\d+)")),
    ("recruitee", re.compile(r"https?://([\w-]+)\.recruitee\.com/o/([\w-]+)")),
    ("eures", re.compile(r"https?://[\w.]*europa\.eu/eures/[^\s\"'<>]*?/jv-se-detail/(\d+)")),
]

# LinkedIn alert bodies put the role on one line and "Company · Location" on the next.
_LI_PAIR = re.compile(r"^(?P<title>[^\n]{3,120})\n(?P<company>[^\n·]{2,80})·\s*(?P<location>[^\n]{2,80})$", re.M)


def _body(message: email.message.Message) -> str:
    """Best-effort plain text of an email, HTML flattened."""
    if message.is_multipart():
        parts = [_body(p) for p in message.iter_parts()] if hasattr(message, "iter_parts") \
            else [_body(p) for p in message.get_payload()]
        return "\n".join(p for p in parts if p)
    content_type = message.get_content_type()
    if content_type not in ("text/plain", "text/html"):
        return ""
    try:
        payload = message.get_content()
    except Exception:  # noqa: BLE001 - malformed mail is common; skip the part
        return ""
    return html_to_text(payload) if content_type == "text/html" else payload


def iter_messages(path: Path) -> Iterator[email.message.Message]:
    if path.is_dir():
        for file in sorted(path.iterdir()):
            if file.suffix.lower() in (".eml", ".txt"):
                yield email.message_from_bytes(file.read_bytes(), policy=email.policy.default)
            elif file.suffix.lower() == ".mbox":
                yield from _mailbox.mbox(str(file))
    elif path.suffix.lower() == ".mbox":
        yield from _mailbox.mbox(str(path))
    else:
        yield email.message_from_bytes(path.read_bytes(), policy=email.policy.default)


def extract(text: str, *, sender: str = "") -> list[Job]:
    """Pull job links out of one message body."""
    jobs: dict[str, Job] = {}
    titles = {m.group("title").strip(): m for m in _LI_PAIR.finditer(text)}

    for source, pattern in PATTERNS:
        for match in pattern.finditer(text):
            url = match.group(0).split("?")[0]
            if source in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"):
                company, ident = match.group(1), match.group(2)
            else:
                company, ident = "", match.group(1)
            company = company.replace("-", " ").title() if company else ""

            # Look backwards for the nearest heading-like line: alert emails put
            # the role title immediately above the link.
            window = text[max(0, match.start() - 400):match.start()]
            title = ""
            for line in reversed([l.strip() for l in window.split("\n") if l.strip()]):
                if 3 < len(line) < 120 and not line.lower().startswith(("http", "view job", "apply")):
                    title = line
                    break
            location = ""
            if title in titles:
                company = company or titles[title].group("company").strip()
                location = titles[title].group("location").strip()
            if not title:
                continue
            job = Job(
                source=f"email:{source}",
                source_id=ident,
                company=company or "(unknown)",
                title=title,
                url=url,
                location=location,
                raw={"sender": sender},
            )
            jobs.setdefault(job.id, job)
    return list(jobs.values())


@register("mailbox")
def scan(*, path: str | Path, **_: Any) -> list[Job]:
    """Read every message under `path` and return the jobs referenced in them."""
    root = Path(path).expanduser()
    if not root.exists():
        log.warning("mailbox: %s does not exist — skipping", root)
        return []
    found: dict[str, Job] = {}
    for message in iter_messages(root):
        sender = str(message.get("From", ""))[:120]
        for job in extract(_body(message), sender=sender):
            found.setdefault(job.id, job)
    return list(found.values())
