"""Applicant Tracking System job boards.

These are the backbone of the pipeline. Greenhouse, Lever, Ashby,
SmartRecruiters, Recruitee, Workable and Personio all publish the *same* JSON
or XML their own careers pages consume: no key, no login, no scraping, and a
contract they have every reason to keep stable. That is the opposite of
screen-scraping a job portal that actively defends itself.

Each provider function takes the company's board handle and returns Jobs.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Callable

from ..models import Job
from ..util import FetchError, html_to_text, http_json, http_get, log

PROVIDERS: dict[str, Callable[..., list[Job]]] = {}


def provider(name: str) -> Callable[[Callable[..., list[Job]]], Callable[..., list[Job]]]:
    def wrap(fn: Callable[..., list[Job]]) -> Callable[..., list[Job]]:
        PROVIDERS[name] = fn
        return fn
    return wrap


# --------------------------------------------------------------- helpers

_COUNTRY_HINTS = {
    "poland": "PL", "polska": "PL", "krak": "PL", "warsaw": "PL", "warszawa": "PL",
    "wroc": "PL", "gdansk": "PL", "poznan": "PL", "katowice": "PL", "lodz": "PL",
    "italy": "IT", "italia": "IT", "milan": "IT", "milano": "IT", "rome": "IT",
    "roma": "IT", "turin": "IT", "torino": "IT", "bologna": "IT", "naples": "IT",
    "spain": "ES", "madrid": "ES", "barcelona": "ES",
    "germany": "DE", "berlin": "DE", "munich": "DE", "münchen": "DE", "hamburg": "DE",
    "frankfurt": "DE", "cologne": "DE",
    "netherlands": "NL", "amsterdam": "NL", "utrecht": "NL", "rotterdam": "NL",
    "belgium": "BE", "brussels": "BE", "bruxelles": "BE",
    "ireland": "IE", "dublin": "IE",
    "portugal": "PT", "lisbon": "PT", "lisboa": "PT", "porto": "PT",
    "france": "FR", "paris": "FR", "lyon": "FR",
    "luxembourg": "LU", "austria": "AT", "vienna": "AT", "wien": "AT",
    "czech": "CZ", "prague": "CZ", "praha": "CZ",
    "romania": "RO", "bucharest": "RO", "cluj": "RO",
    "hungary": "HU", "budapest": "HU",
    "bulgaria": "BG", "sofia": "BG",
    "greece": "GR", "athens": "GR",
    "sweden": "SE", "stockholm": "SE", "denmark": "DK", "copenhagen": "DK",
    "finland": "FI", "helsinki": "FI", "norway": "NO", "oslo": "NO",
    "switzerland": "CH", "zurich": "CH", "zürich": "CH", "geneva": "CH",
    "united kingdom": "GB", "london": "GB", "manchester": "GB", "england": "GB",
    "united states": "US", "usa": "US", "new york": "US", "remote": "",
    # Countries outside the usual EU targets still need a code: an unrecognised
    # location silently scores as "unknown" and slips past the location gate.
    "azerbaijan": "AZ", "georgia": "GE", "armenia": "AM", "turkey": "TR", "türkiye": "TR",
    "israel": "IL", "united arab emirates": "AE", "dubai": "AE", "saudi": "SA", "qatar": "QA",
    "egypt": "EG", "morocco": "MA", "kenya": "KE", "nigeria": "NG", "south africa": "ZA",
    "india": "IN", "bangalore": "IN", "singapore": "SG", "japan": "JP", "tokyo": "JP",
    "china": "CN", "hong kong": "HK", "australia": "AU", "sydney": "AU", "new zealand": "NZ",
    "brazil": "BR", "sao paulo": "BR", "mexico": "MX", "argentina": "AR", "chile": "CL",
    "colombia": "CO", "canada": "CA", "toronto": "CA", "ukraine": "UA", "serbia": "RS",
    "croatia": "HR", "slovenia": "SI", "slovakia": "SK", "bratislava": "SK", "estonia": "EE",
    "tallinn": "EE", "latvia": "LV", "riga": "LV", "lithuania": "LT", "vilnius": "LT",
    "cyprus": "CY", "malta": "MT", "iceland": "IS", "albania": "AL", "kosovo": "XK",
    "bosnia": "BA", "north macedonia": "MK", "montenegro": "ME", "moldova": "MD",
    "philippines": "PH", "indonesia": "ID", "vietnam": "VN", "thailand": "TH",
    "malaysia": "MY", "south korea": "KR", "taiwan": "TW", "pakistan": "PK",
}


def guess_country(location: str) -> str:
    low = (location or "").lower()
    for hint, code in _COUNTRY_HINTS.items():
        if hint and hint in low:
            return code
    return ""


def guess_remote(*fields: Any) -> str:
    blob = " ".join(str(f) for f in fields if f).lower()
    if re.search(r"\bhybrid\b|ibrido|hybryd", blob):
        return "hybrid"
    if re.search(r"\b(fully )?remote\b|work from home|smart working|telelavoro", blob):
        return "remote"
    if re.search(r"\bon[- ]?site\b|in[- ]office", blob):
        return "onsite"
    return "unknown"


def _mk(source: str, company: str, **kw: Any) -> Job:
    location = kw.pop("location", "") or ""
    return Job(
        source=source,
        company=company,
        location=location,
        country=kw.pop("country", "") or guess_country(location),
        remote=kw.pop("remote", "") or guess_remote(location, kw.get("title"), kw.get("description")),
        **kw,
    )


# ------------------------------------------------------------- providers

@provider("greenhouse")
def greenhouse(handle: str, company: str = "", **opts: Any) -> list[Job]:
    data = http_json(
        f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs?content=true", **opts
    )
    return parse_greenhouse(data, company or handle)


def parse_greenhouse(data: Any, company: str) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(_mk(
            "greenhouse", company,
            source_id=str(j.get("id", "")),
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            location=(j.get("location") or {}).get("name", ""),
            description=html_to_text(j.get("content", "")),
            posted_at=(j.get("updated_at") or j.get("first_published") or "")[:19],
            raw={"departments": [d.get("name") for d in j.get("departments", [])]},
        ))
    return jobs


@provider("lever")
def lever(handle: str, company: str = "", **opts: Any) -> list[Job]:
    data = http_json(f"https://api.lever.co/v0/postings/{handle}?mode=json", **opts)
    return parse_lever(data, company or handle)


def parse_lever(data: Any, company: str) -> list[Job]:
    jobs = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        body = j.get("descriptionPlain") or html_to_text(j.get("description", ""))
        extra = "\n".join(
            f"{s.get('text', '')}\n{html_to_text(s.get('content', ''))}" for s in j.get("lists", [])
        )
        jobs.append(_mk(
            "lever", company,
            source_id=str(j.get("id", "")),
            title=j.get("text", ""),
            url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
            location=cats.get("location", ""),
            description=(body + "\n" + extra).strip(),
            posted_at=str(j.get("createdAt", ""))[:10],
            raw={"team": cats.get("team"), "commitment": cats.get("commitment")},
        ))
    return jobs


@provider("ashby")
def ashby(handle: str, company: str = "", **opts: Any) -> list[Job]:
    data = http_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{handle}?includeCompensation=true", **opts
    )
    return parse_ashby(data, company or handle)


def parse_ashby(data: Any, company: str) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(_mk(
            "ashby", company,
            source_id=str(j.get("id", "")),
            title=j.get("title", ""),
            url=j.get("jobUrl", ""),
            location=j.get("location", ""),
            remote="remote" if j.get("isRemote") else "",
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
            posted_at=str(j.get("publishedAt", ""))[:10],
            raw={"team": j.get("team"), "employmentType": j.get("employmentType")},
        ))
    return jobs


@provider("smartrecruiters")
def smartrecruiters(handle: str, company: str = "", *, details: bool = False, **opts: Any) -> list[Job]:
    """SmartRecruiters lists postings without descriptions.

    Fetching every description here would mean one request per posting — for a
    large employer that is hundreds of calls to learn that most roles are in
    warehousing. The list is cheap, so it is fetched in full and the bodies are
    filled in later by `jsa enrich`, only for postings worth reading.
    """
    base = f"https://api.smartrecruiters.com/v1/companies/{handle}/postings"
    jobs: list[Job] = []
    offset = 0
    while True:
        data = http_json(f"{base}?limit=100&offset={offset}", **opts)
        page = data.get("content", [])
        for j in page:
            loc = j.get("location") or {}
            location = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
            description = smartrecruiters_detail(handle, str(j.get("id")), **opts) if details else ""
            jobs.append(_mk(
                "smartrecruiters", company or handle,
                source_id=str(j.get("id", "")),
                title=j.get("name", ""),
                url=f"https://jobs.smartrecruiters.com/{handle}/{j.get('id')}",
                location=location,
                country=(loc.get("countryCode") or "").upper(),
                description=description,
                posted_at=str(j.get("releasedDate", ""))[:10],
                raw={"department": (j.get("department") or {}).get("label"), "handle": handle},
            ))
        offset += len(page)
        if len(page) < 100 or offset >= data.get("totalFound", 0):
            break
    return jobs


def smartrecruiters_detail(handle: str, posting_id: str, **opts: Any) -> str:
    """Full posting body for one SmartRecruiters role."""
    detail = http_json(
        f"https://api.smartrecruiters.com/v1/companies/{handle}/postings/{posting_id}", **opts
    )
    sections = (detail.get("jobAd") or {}).get("sections") or {}
    return "\n\n".join(
        html_to_text((sections.get(key) or {}).get("text", ""))
        for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation")
    ).strip()


@provider("recruitee")
def recruitee(handle: str, company: str = "", **opts: Any) -> list[Job]:
    data = http_json(f"https://{handle}.recruitee.com/api/offers/", **opts)
    return parse_recruitee(data, company or handle)


def parse_recruitee(data: Any, company: str) -> list[Job]:
    jobs = []
    for j in data.get("offers", []):
        location = ", ".join(x for x in [j.get("city"), j.get("country")] if x)
        jobs.append(_mk(
            "recruitee", company,
            source_id=str(j.get("id", "")),
            title=j.get("title", ""),
            url=j.get("careers_url") or j.get("careers_apply_url", ""),
            location=location,
            country=(j.get("country_code") or "").upper(),
            description=html_to_text((j.get("description") or "") + (j.get("requirements") or "")),
            posted_at=str(j.get("published_at", ""))[:10],
            raw={"department": j.get("department")},
        ))
    return jobs


@provider("workable")
def workable(handle: str, company: str = "", **opts: Any) -> list[Job]:
    data = http_json(
        f"https://apply.workable.com/api/v1/widget/accounts/{handle}?details=true", **opts
    )
    return parse_workable(data, company or handle)


def parse_workable(data: Any, company: str) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        loc = j.get("location") or {}
        location = ", ".join(str(x) for x in [loc.get("city"), loc.get("country")] if x)
        jobs.append(_mk(
            "workable", data.get("name") or company,
            source_id=str(j.get("shortcode") or j.get("id") or ""),
            title=j.get("title", ""),
            url=j.get("url") or j.get("application_url") or j.get("shortlink", ""),
            location=location,
            remote="remote" if j.get("telecommuting") else "",
            description=html_to_text(
                (j.get("description") or "") + (j.get("requirements") or "")
            ),
            posted_at=str(j.get("published_on", ""))[:10],
            raw={"department": j.get("department")},
        ))
    return jobs


@provider("personio")
def personio(handle: str, company: str = "", *, domain: str = "jobs.personio.de", **opts: Any) -> list[Job]:
    body = http_get(f"https://{handle}.{domain}/xml", **opts)
    return parse_personio(body, company or handle, handle=handle, domain=domain)


def parse_personio(body: str, company: str, *, handle: str = "", domain: str = "jobs.personio.de") -> list[Job]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise FetchError(f"personio/{handle}: malformed XML ({exc})") from exc
    jobs = []
    for pos in root.iter("position"):
        get = lambda tag: (pos.findtext(tag) or "").strip()  # noqa: E731
        parts = []
        for desc in pos.iter("jobDescription"):
            parts.append(
                f"{(desc.findtext('name') or '').strip()}\n"
                f"{html_to_text(desc.findtext('value') or '')}"
            )
        office = get("office")
        jobs.append(_mk(
            "personio", company,
            source_id=get("id"),
            title=get("name"),
            url=f"https://{handle}.{domain}/job/{get('id')}",
            location=office,
            description="\n\n".join(parts).strip(),
            posted_at=get("createdAt")[:10],
            raw={"department": get("department"), "schedule": get("schedule")},
        ))
    return jobs


# ------------------------------------------------------------------ API

def fetch_company(entry: dict[str, Any], **opts: Any) -> list[Job]:
    """Fetch one watchlist entry: {"company", "provider", "handle"}."""
    fn = PROVIDERS.get(entry["provider"])
    if fn is None:
        raise FetchError(f"unknown ATS provider: {entry['provider']}")
    return fn(entry["handle"], entry.get("company", ""), **opts)


def probe(handle: str, providers: list[str] | None = None, **opts: Any) -> list[tuple[str, int]]:
    """Try a handle against every provider; return (provider, job_count) hits.

    This is how the watchlist gets built without guessing: give it a plausible
    slug and it reports which board actually answers. Providers are tried
    concurrently because most of them will simply 404.
    """
    from concurrent.futures import ThreadPoolExecutor

    names = providers or list(PROVIDERS)

    def attempt(name: str) -> tuple[str, int] | None:
        try:
            found = PROVIDERS[name](handle, retries=1, timeout=12, **opts)
        except Exception as exc:  # noqa: BLE001 - probing is best-effort by design
            log.debug("probe %s/%s: %s", name, handle, exc)
            return None
        return (name, len(found)) if found else None

    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        results = list(pool.map(attempt, names))
    return [r for r in results if r]
