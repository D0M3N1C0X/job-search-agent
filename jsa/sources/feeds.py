"""Job feeds that cover many employers at once.

The ATS adapters read one employer's board each. These read aggregators:

- **Arbeitnow** (arbeitnow.com): a free public API of European postings, no key,
  newest first, 300 a page. It has no search, so postings are kept only when
  their title names a job one of your tracks is looking for and they are in a
  country your profile accepts; the rest never reach the database.
- **Adzuna** (adzuna.com): search across fifteen European markets. It needs a
  free key of your own (developer.adzuna.com), read from the environment
  (JSA_ADZUNA_APP_ID, JSA_ADZUNA_APP_KEY) or from `secrets.json` in your
  workspace. Without one it is skipped and says so.

Both split fetching from parsing, so the parsers are tested on captured
payloads with no network.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from ..models import Job, canonical
from ..util import http_json, log
from .ats import guess_country, guess_remote

ARBEITNOW = "https://www.arbeitnow.com/api/job-board-api"
ADZUNA = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
# Markets Adzuna serves in Europe, by the code its URLs use.
ADZUNA_COUNTRIES = {"at", "be", "ch", "de", "es", "fr", "gb", "it", "nl", "pl"}


class MissingKey(RuntimeError):
    """A feed that needs a key of yours, run without one."""


# ------------------------------------------------------------------ relevance

def title_terms(tracks: list[dict[str, Any]]) -> list[str]:
    """Every title keyword the tracks score, strong and good: what a feed posting must name."""
    terms: list[str] = []
    for track in tracks:
        titles = track.get("titles", {})
        for term in titles.get("strong", []) + titles.get("good", []):
            if term not in terms:
                terms.append(term)
    return terms


def relevant(job: Job, terms: list[str], countries: list[str]) -> bool:
    """A feed posting is kept when its title names a tracked job and its country is accepted.

    Remote postings with no country are kept: the scorer's location gate decides
    them, as it does for every other source.
    """
    from ..score import _matches   # the scorer's own matching: word boundaries, plurals

    if terms and not _matches(terms, canonical(job.title)):
        return False
    return not (countries and job.country and job.country not in countries)


# ------------------------------------------------------------------ Arbeitnow

def parse_arbeitnow(data: Any) -> list[Job]:
    jobs: list[Job] = []
    for item in (data or {}).get("data", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("title") or not item.get("company_name"):
            continue
        location = str(item.get("location") or "")
        stamp = item.get("created_at")
        posted = (datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d")
                  if isinstance(stamp, (int, float)) else "")
        description = str(item.get("description") or "")
        jobs.append(Job(
            source="arbeitnow", source_id=str(item.get("slug") or ""), company=str(item["company_name"]),
            title=str(item["title"]), url=str(item.get("url") or ""), location=location,
            country=guess_country(location),
            remote="remote" if item.get("remote") else guess_remote(location, item["title"], description),
            description=description, posted_at=posted,
        ))
    return jobs


def arbeitnow(*, pages: int = 3, terms: list[str] | None = None, countries: list[str] | None = None,
              **opts: Any) -> tuple[list[Job], int]:
    """The newest `pages` × 300 postings, filtered. Returns (kept, read)."""
    kept: list[Job] = []
    read = 0
    for page in range(1, pages + 1):
        data = http_json(f"{ARBEITNOW}?page={page}", **opts)
        batch = parse_arbeitnow(data)
        read += len(batch)
        kept += [j for j in batch if relevant(j, terms or [], countries or [])]
        links = data.get("links", {}) if isinstance(data, dict) else {}
        if not batch or not links.get("next"):
            break
    return kept, read


# --------------------------------------------------------------------- Adzuna

def adzuna_keys(home: Path | None = None) -> tuple[str, str]:
    """Your Adzuna key, from the environment or the workspace's secrets.json; never from profile.json."""
    app_id, app_key = os.environ.get("JSA_ADZUNA_APP_ID", ""), os.environ.get("JSA_ADZUNA_APP_KEY", "")
    if (not app_id or not app_key) and home is not None and (home / "secrets.json").is_file():
        try:
            secrets = json.loads((home / "secrets.json").read_text(encoding="utf-8")).get("adzuna", {})
        except (OSError, ValueError, AttributeError):
            secrets = {}
        app_id = app_id or str(secrets.get("app_id", ""))
        app_key = app_key or str(secrets.get("app_key", ""))
    if not app_id or not app_key:
        raise MissingKey("no Adzuna key: register at developer.adzuna.com, then set JSA_ADZUNA_APP_ID and "
                         "JSA_ADZUNA_APP_KEY, or put {\"adzuna\": {\"app_id\": …, \"app_key\": …}} in "
                         "secrets.json in your workspace")
    return app_id, app_key


def parse_adzuna(data: Any, country: str = "") -> list[Job]:
    jobs: list[Job] = []
    for item in (data or {}).get("results", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        firm = item.get("company")
        company = firm.get("display_name", "") if isinstance(firm, dict) else ""
        place = item.get("location")
        where: dict[str, Any] = place if isinstance(place, dict) else {}
        location = str(where.get("display_name") or "")
        if not company:
            continue
        title = str(item["title"])
        description = str(item.get("description") or "")
        jobs.append(Job(
            source="adzuna", source_id=str(item.get("id") or ""), company=str(company), title=title,
            url=str(item.get("redirect_url") or ""), location=location,
            # Adzuna's location names the town and region, rarely the country: the market is the country.
            country=guess_country(location) or ("GB" if country == "gb" else country.upper()),
            remote=guess_remote(location, title, description),
            description=description, posted_at=str(item.get("created") or "")[:10],
        ))
    return jobs


def adzuna(*, queries: list[dict[str, Any]], app_id: str, app_key: str, pages: int = 1,
           terms: list[str] | None = None, countries: list[str] | None = None, **opts: Any) -> tuple[list[Job], int]:
    """Each query is {"what": "...", "country": "nl", "where": "..."}; returns (kept, read)."""
    kept: list[Job] = []
    read = 0
    for query in queries:
        country = str(query.get("country", "")).lower()
        if country not in ADZUNA_COUNTRIES:
            log.warning("adzuna: market %r is not one Adzuna serves in Europe — skipping", country)
            continue
        for page in range(1, pages + 1):
            params = {"app_id": app_id, "app_key": app_key, "results_per_page": 50,
                      "what": query.get("what", ""), "content-type": "application/json"}
            if query.get("where"):
                params["where"] = query["where"]
            if query.get("max_days_old"):
                params["max_days_old"] = query["max_days_old"]
            data = http_json(ADZUNA.format(country=country, page=page) + "?" + urlencode(params), **opts)
            batch = parse_adzuna(data, country)
            read += len(batch)
            kept += [j for j in batch if relevant(j, terms or [], countries or [])]
            if len(batch) < 50:
                break
    return kept, read
