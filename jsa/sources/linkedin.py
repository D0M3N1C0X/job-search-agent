"""LinkedIn guest search.

Kept deliberately as a *secondary* channel. The guest endpoints need no login
and no key, but LinkedIn rate-limits them hard and can change them without
notice — so a failure here is logged and the run continues. The ATS sources
are what the pipeline actually relies on.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlencode

from ..models import Job
from ..util import FetchError, html_to_text, http_get, log
from . import register

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# Time filters LinkedIn accepts on f_TPR (seconds).
PERIODS = {"day": "r86400", "week": "r604800", "month": "r2592000"}
# Workplace type: 1 on-site, 2 remote, 3 hybrid.
WORKPLACE = {"onsite": "1", "remote": "2", "hybrid": "3"}

_CARD = re.compile(r"<li\b.*?</li>", re.S)
_URN = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
_HREF = re.compile(r'href="(https://[a-z]{0,3}\.?linkedin\.com/jobs/view/[^"?]+)')
_TITLE = re.compile(r'base-search-card__title[^>]*>(.*?)</h3>', re.S)
_COMPANY = re.compile(r'base-search-card__subtitle[^>]*>.*?>(.*?)</a>', re.S)
_LOCATION = re.compile(r'job-search-card__location[^>]*>(.*?)</span>', re.S)
_POSTED = re.compile(r'datetime="([\d-]+)"')
_DESCRIPTION = re.compile(r'show-more-less-html__markup.*?>(.*?)</div>', re.S)


def _clean(match: re.Match[str] | None) -> str:
    return html_to_text(match.group(1)) if match else ""


def parse_cards(html: str) -> list[Job]:
    """Parse the HTML fragment the guest search endpoint returns."""
    jobs = []
    for card in _CARD.findall(html):
        urn = _URN.search(card)
        href = _HREF.search(card)
        title = _clean(_TITLE.search(card))
        company = _clean(_COMPANY.search(card))
        if not title or not company:
            continue
        job_id = urn.group(1) if urn else ""
        url = href.group(1) if href else (
            f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else ""
        )
        location = _clean(_LOCATION.search(card))
        posted = _POSTED.search(card)
        jobs.append(Job(
            source="linkedin",
            source_id=job_id,
            company=company,
            title=title,
            url=url,
            location=location,
            posted_at=posted.group(1) if posted else "",
        ))
    return jobs


def fetch_description(job_id: str, **opts: Any) -> str:
    html = http_get(DETAIL.format(job_id=job_id), **opts)
    return _clean(_DESCRIPTION.search(html))


@register("linkedin")
def search(
    *,
    queries: list[dict[str, Any]],
    pages: int = 2,
    with_descriptions: bool = True,
    pause: float = 1.5,
    **opts: Any,
) -> list[Job]:
    """Run every configured query. `queries` come from the profile's search block."""
    found: dict[str, Job] = {}
    for query in queries:
        for page in range(pages):
            params = {
                "keywords": query.get("keywords", ""),
                "location": query.get("location", ""),
                "start": page * 25,
            }
            if query.get("period"):
                params["f_TPR"] = PERIODS.get(query["period"], query["period"])
            if query.get("workplace"):
                params["f_WT"] = WORKPLACE.get(query["workplace"], query["workplace"])
            url = f"{SEARCH}?{urlencode(params)}"
            try:
                html = http_get(url, **opts)
            except FetchError as exc:
                log.warning("linkedin: %s (query %r) — skipping", exc, query.get("keywords"))
                break
            batch = parse_cards(html)
            if not batch:
                break
            for job in batch:
                found.setdefault(job.id, job)
            time.sleep(pause)

    if with_descriptions:
        # Detail pages are the most rate-limited call here, so they get a
        # single attempt — merged into the caller's options rather than passed
        # alongside them, which would collide when the caller sets `retries`.
        detail_opts = {**opts, "retries": 1}
        for job in found.values():
            if job.source_id and not job.description:
                try:
                    job.description = fetch_description(job.source_id, **detail_opts)
                except FetchError as exc:
                    log.debug("linkedin detail %s: %s", job.source_id, exc)
                time.sleep(pause)
    return list(found.values())
