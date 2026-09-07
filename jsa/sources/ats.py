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
import unicodedata
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

_COUNTRY_HINTS: dict[str, str] = {}


def _add(code: str, *names: str) -> None:
    for name in names:
        _COUNTRY_HINTS[name] = code


# Europe, country by country: the country's own names plus the cities that
# actually appear in job postings. A posting that says only "Ljubljana" has to
# resolve, because the location gate cannot judge what it cannot place.
_add("AT", "austria", "österreich", "osterreich", "vienna", "wien", "graz", "linz", "salzburg", "innsbruck")
_add("BE", "belgium", "belgique", "belgië", "belgie", "brussels", "bruxelles", "brussel",
     "antwerp", "antwerpen", "anvers", "ghent", "gent", "leuven", "liege", "liège", "charleroi", "bruges")
_add("BG", "bulgaria", "sofia", "plovdiv", "varna", "burgas", "ruse")
_add("HR", "croatia", "hrvatska", "zagreb", "split", "rijeka", "osijek", "zadar")
_add("CY", "cyprus", "nicosia", "limassol", "larnaca", "paphos")
_add("CZ", "czech", "czechia", "cesko", "prague", "praha", "brno", "ostrava", "plzen", "olomouc")
_add("DK", "denmark", "danmark", "copenhagen", "kobenhavn", "københavn", "aarhus", "arhus",
     "odense", "aalborg", "billund")
_add("EE", "estonia", "eesti", "tallinn", "tartu", "parnu")
_add("FI", "finland", "suomi", "helsinki", "espoo", "tampere", "turku", "oulu", "vantaa")
_add("FR", "france", "paris", "lyon", "marseille", "toulouse", "bordeaux", "nantes", "lille",
     "nice", "strasbourg", "montpellier", "rennes", "grenoble", "sophia antipolis", "cergy",
     "boulogne billancourt", "neuilly", "massy", "montreuil", "creteil", "la defense")
_add("DE", "germany", "deutschland", "berlin", "munich", "münchen", "munchen", "hamburg",
     "frankfurt", "cologne", "köln", "koln", "stuttgart", "dusseldorf", "düsseldorf", "leipzig",
     "dresden", "hannover", "nuremberg", "nürnberg", "nurnberg", "essen", "dortmund", "bremen",
     "karlsruhe", "mannheim", "bonn", "münster", "munster", "heidelberg", "wolfsburg")
_add("GR", "greece", "hellas", "athens", "athina", "thessaloniki", "patras", "heraklion")
_add("HU", "hungary", "magyarorszag", "magyarország", "budapest", "debrecen", "szeged", "gyor")
_add("IE", "ireland", "eire", "éire", "dublin", "cork", "galway", "limerick", "shannon")
_add("IT", "italy", "italia", "rome", "roma", "milan", "milano", "turin", "torino", "naples",
     "napoli", "bologna", "florence", "firenze", "venice", "venezia", "verona", "genoa", "genova",
     "palermo", "bari", "catania", "padova", "padua", "trieste", "brescia", "modena", "parma",
     "perugia", "gorizia", "bergamo", "vicenza")
_add("LV", "latvia", "latvija", "riga", "rīga", "daugavpils")
_add("LT", "lithuania", "lietuva", "vilnius", "kaunas", "klaipeda")
_add("LU", "luxembourg", "luxemburg", "letzebuerg")
_add("MT", "malta", "valletta", "sliema", "birkirkara")
_add("NL", "netherlands", "nederland", "holland", "amsterdam", "rotterdam", "utrecht",
     "eindhoven", "the hague", "den haag", "hague", "groningen", "tilburg", "almere",
     "breda", "nijmegen", "haarlem", "arnhem", "amstelveen", "hoofddorp", "delft")
_add("PL", "poland", "polska", "warsaw", "warszawa", "krakow", "kraków", "cracow", "wroclaw",
     "wrocław", "gdansk", "gdańsk", "poznan", "poznań", "katowice", "lodz", "łódź", "lublin",
     "szczecin", "bydgoszcz", "gdynia", "rzeszow", "bialystok", "torun", "gliwice", "sopot")
_add("PT", "portugal", "lisbon", "lisboa", "porto", "oporto", "braga", "coimbra", "faro", "aveiro")
_add("RO", "romania", "bucharest", "bucuresti", "bucurești", "cluj", "timisoara", "timișoara",
     "iasi", "iași", "brasov", "brașov", "constanta", "sibiu")
_add("SK", "slovakia", "slovensko", "bratislava", "kosice", "košice", "zilina")
_add("SI", "slovenia", "slovenija", "ljubljana", "maribor", "celje")
_add("ES", "spain", "españa", "espana", "madrid", "barcelona", "valencia", "seville", "sevilla",
     "bilbao", "malaga", "málaga", "zaragoza", "murcia", "palma", "alicante", "granada",
     "valladolid", "vigo", "san sebastian", "pozuelo", "las rozas", "a coruna", "la coruna")
_add("SE", "sweden", "sverige", "stockholm", "gothenburg", "goteborg", "göteborg", "malmo",
     "malmö", "uppsala", "lund", "linkoping", "vasteras", "solna", "sundbyberg")

# EFTA and the rest of the continent.
_add("CH", "switzerland", "schweiz", "suisse", "svizzera", "zurich", "zürich", "geneva", "geneve",
     "genève", "basel", "bern", "berne", "lausanne", "lugano", "zug", "winterthur", "st gallen")
_add("NO", "norway", "norge", "oslo", "bergen", "trondheim", "stavanger", "tromso")
_add("IS", "iceland", "island", "reykjavik", "reykjavík")
_add("LI", "liechtenstein", "vaduz", "schaan")
_add("GB", "united kingdom", "great britain", "england", "scotland", "wales",
     "northern ireland", "london", "manchester", "birmingham", "edinburgh", "glasgow", "bristol",
     "leeds", "liverpool", "sheffield", "cambridge", "oxford", "reading", "belfast", "cardiff",
     "newcastle", "nottingham", "brighton", "milton keynes", "derby", "colchester", "st albans")
_add("RS", "serbia", "srbija", "belgrade", "beograd", "novi sad", "nis")
_add("AL", "albania", "shqiperia", "tirana", "tirane", "durres")
_add("BA", "bosnia", "herzegovina", "sarajevo", "banja luka", "mostar")
_add("ME", "montenegro", "crna gora", "podgorica", "budva")
_add("MK", "north macedonia", "macedonia", "skopje", "bitola")
_add("XK", "kosovo", "pristina", "prishtina")
_add("MD", "moldova", "chisinau", "chișinău")
_add("UA", "ukraine", "kyiv", "kiev", "lviv", "odesa", "odessa", "kharkiv")
_add("AD", "andorra")
_add("MC", "monaco")
_add("SM", "san marino")

# Outside Europe: enough to place a posting so the location gate can reject it.
_add("US", "united states", "usa", "u.s.", "new york", "chicago", "san francisco", "seattle",
     "boston", "austin", "denver", "atlanta", "los angeles", "miami", "washington", "dallas",
     "houston", "philadelphia", "phoenix", "san diego", "framingham", "mountain view")
_add("CA", "canada", "toronto", "vancouver", "montreal", "ottawa", "calgary")
_add("MX", "mexico", "mexico city", "guadalajara")
_add("BR", "brazil", "brasil", "sao paulo", "são paulo", "rio de janeiro", "belo horizonte")
_add("AR", "argentina", "buenos aires", "cordoba")
_add("CL", "chile", "santiago")
_add("CO", "colombia", "bogota", "bogotá", "medellin")
_add("PE", "peru", "lima")
_add("UY", "uruguay", "montevideo")
_add("IN", "india", "bangalore", "bengaluru", "hyderabad", "mumbai", "pune", "gurgaon",
     "gurugram", "chennai", "delhi", "noida")
_add("SG", "singapore")
_add("JP", "japan", "tokyo", "osaka", "kyoto")
_add("CN", "china", "shanghai", "beijing", "shenzhen", "guangzhou")
_add("HK", "hong kong")
_add("TW", "taiwan", "taipei")
_add("KR", "south korea", "seoul")
_add("AU", "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide")
_add("NZ", "new zealand", "auckland", "wellington")
_add("ZA", "south africa", "johannesburg", "cape town", "durban")
_add("NG", "nigeria", "lagos", "abuja")
_add("KE", "kenya", "nairobi")
_add("EG", "egypt", "cairo", "maadi", "giza")
_add("MA", "morocco", "casablanca", "rabat")
_add("AE", "united arab emirates", "dubai", "abu dhabi")
_add("SA", "saudi", "riyadh", "jeddah")
_add("QA", "qatar", "doha")
_add("IL", "israel", "tel aviv", "jerusalem")
_add("TR", "turkey", "türkiye", "turkiye", "istanbul", "ankara", "izmir")
_add("GE", "georgia", "tbilisi")
_add("AM", "armenia", "yerevan")
_add("AZ", "azerbaijan", "baku")
_add("KZ", "kazakhstan", "almaty", "astana", "nur sultan")
_add("UZ", "uzbekistan", "tashkent")
_add("PK", "pakistan", "karachi", "lahore", "islamabad")
_add("BD", "bangladesh", "dhaka")
_add("LK", "sri lanka", "colombo")
_add("PH", "philippines", "manila", "makati", "cebu")
_add("ID", "indonesia", "jakarta")
_add("VN", "vietnam", "hanoi", "ho chi minh")
_add("TH", "thailand", "bangkok")
_add("MY", "malaysia", "kuala lumpur", "bangsar", "penang")

# ATS location strings often end in an ISO country code ("Remote, US",
# "London, gb"). Only codes the table already knows are accepted, so an
# Italian province abbreviation is not mistaken for a country.
_ISO_CODES = set(_COUNTRY_HINTS.values())
_ISO_SUFFIX = re.compile(r",\s*([A-Za-z]{2})\s*$")


# Letters NFKD will not take apart, because they are letters in their own right
# rather than a base plus a mark. Without these, "Łódź" folds to "odz".
_LETTERS = str.maketrans({
    "ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d", "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th", "ß": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
    "ı": "i", "İ": "i",
})


def _fold(value: str) -> str:
    """Lowercase, accents removed, punctuation reduced to single spaces."""
    text = (value or "").translate(_LETTERS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# Hints are folded once and matched on word boundaries, longest first.
# Substring matching put "Limassol" in Peru, because "lima" is inside it.
_FOLDED_HINTS = {_fold(name): code for name, code in _COUNTRY_HINTS.items()}
_HINT_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(
        re.escape(h) for h in sorted(_FOLDED_HINTS, key=len, reverse=True) if h
    ) + r")(?![a-z0-9])"
)


def guess_country(location: str) -> str:
    """Best-effort ISO country code for a free-text location."""
    match = _HINT_RE.search(_fold(location))
    if match:
        return _FOLDED_HINTS[match.group(1)]
    suffix = _ISO_SUFFIX.search(location or "")
    if suffix and suffix.group(1).upper() in _ISO_CODES:
        return suffix.group(1).upper()
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
    # A hard stop, in case a board reports a total it never reaches: paging
    # forever against someone else's API is the rudest possible bug.
    for _ in range(60):
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
