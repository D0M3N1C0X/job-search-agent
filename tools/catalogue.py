"""Build the shared employer catalogue: European job boards that answer.

    python3 tools/catalogue.py probe catalogue/candidates/*.txt
    python3 tools/catalogue.py stats

A candidate is a company name, optionally with the board slugs to try:

    ## DE                          <- a heading names the region (informational)
    Delivery Hero
    Trade Republic | traderepublic traderepublicbank

Every slug is tried against every supported ATS. A hit enters the catalogue
only when the board is real and European: at least MIN_ROLES open roles, at
least one of them placed in a European country. That second rule is what
stops a US company that happens to share the slug from slipping in. Nothing is
added by hand and nothing is guessed: an entry is a board that answered, with
the date it answered.

For each entry the catalogue records where the roles are and how many mention
Italian — the two numbers the product is built on.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jsa.sources import ats  # noqa: E402
from jsa.util import http_get, http_json  # noqa: E402
from jsa.wizard import EUROPE  # noqa: E402

CATALOGUE = ROOT / "catalogue" / "companies.json"
MIN_ROLES = 3

# Mentions of the Italian language, in the languages postings are written in.
ITALIAN = re.compile(
    r"\b(italian|italiano|italiana|italienisch\w*|italien|italienne|italiaans\w*|"
    r"italiensk\w*|wło(?:ski|skiego|skim)|wlo(?:ski|skiego)|italsk\w*|italština|olasz\w*)\b",
    re.I,
)
LEGAL = re.compile(
    r"\b(gmbh|ag|se|sa|s\.a\.|spa|s\.p\.a\.|bv|b\.v\.|nv|n\.v\.|ltd|limited|plc|inc|group|"
    r"holding|holdings|kg|co|oy|ab|as|a/s|sp\. z o\.o\.|sp z oo|s\.r\.o\.|srl)\b\.?",
    re.I,
)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.lower()


def slugs_for(name: str) -> list[str]:
    """The slugs a board for this company is likely to live at."""
    base = LEGAL.sub(" ", fold(name).replace("&", " and "))
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    out = ["".join(words), "-".join(words)]
    if "and" in words:
        trimmed = [w for w in words if w != "and"]
        out += ["".join(trimmed), "-".join(trimmed)]
    return list(dict.fromkeys(s for s in out if len(s) >= 3))


def read_candidates(paths: list[Path]) -> list[tuple[str, list[str], str]]:
    found: list[tuple[str, list[str], str]] = []
    for path in paths:
        region = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") and not line.startswith("##"):
                continue
            if line.startswith("##"):
                region = line.lstrip("#").strip()
                continue
            name, _, explicit = line.partition("|")
            name = name.strip()
            slugs = explicit.split() + slugs_for(name)
            found.append((name, list(dict.fromkeys(slugs)), region))
    return found


TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
BOILERPLATE = re.compile(r"\b(jobs?|careers?|karriere|bei|at|en|chez|vacatures|ofertas|"
                         r"find|path|not|just|a|career|offene|stellen|current|openings)\b", re.I)


def board_name(provider: str, handle: str) -> str:
    """The employer name the board itself declares, or "" when it declares none."""
    opts = {"retries": 1, "timeout": 15}
    try:
        if provider == "greenhouse":
            return http_json(f"https://boards-api.greenhouse.io/v1/boards/{handle}", **opts).get("name", "")
        if provider == "smartrecruiters":
            page = http_json(f"https://api.smartrecruiters.com/v1/companies/{handle}/postings?limit=1", **opts)
            return ((page.get("content") or [{}])[0].get("company") or {}).get("name", "")
        if provider == "recruitee":
            offers = http_json(f"https://{handle}.recruitee.com/api/offers/", **opts).get("offers") or [{}]
            return offers[0].get("company_name") or ""
        if provider == "workable":
            return http_json(f"https://apply.workable.com/api/v1/widget/accounts/{handle}", **opts).get("name", "")
        page = {"personio": f"https://{handle}.jobs.personio.de/",
                "lever": f"https://jobs.lever.co/{handle}",
                "ashby": f"https://jobs.ashbyhq.com/{handle}"}.get(provider)
        if page:
            title = TITLE.search(http_get(page, **opts))
            return html.unescape(title.group(1)).strip() if title else ""
    except Exception:  # noqa: BLE001 - no name is an answer: "unknown"
        return ""
    return ""


def same_employer(candidate: str, declared: str) -> bool | None:
    """Does the board belong to the company we were looking for? None when it cannot tell.

    A slug is not an identity: "kbc" on Personio is a German consultancy, not
    the Belgian bank. The board's own name settles it whenever it gives one.
    """
    theirs = re.findall(r"[a-z0-9]+", BOILERPLATE.sub(" ", LEGAL.sub(" ", fold(declared))))
    if not theirs:
        return None
    ours = [w for w in re.findall(r"[a-z0-9]+", LEGAL.sub(" ", fold(candidate))) if w != "and"]
    joined_theirs, joined_ours = "".join(theirs), "".join(ours)
    return (joined_ours in joined_theirs or joined_theirs in joined_ours
            or any(len(w) >= 4 and w in theirs for w in ours))


def examine(provider: str, handle: str, company: str) -> dict | None:
    """Fetch a board and decide whether it belongs in the catalogue."""
    try:
        jobs = ats.PROVIDERS[provider](handle, company, retries=1, timeout=20)
    except Exception:  # noqa: BLE001 - a board that does not answer is simply absent
        return None
    if len(jobs) < MIN_ROLES:
        return None
    countries = Counter(j.country for j in jobs if j.country in EUROPE)
    if not countries:
        return None
    italian = sum(1 for j in jobs if j.country in EUROPE
                  and ITALIAN.search(f"{j.title}\n{j.description}"))
    declared = board_name(provider, handle)
    if same_employer(company, declared) is False:
        return None
    return {
        "company": company,
        "board_name": declared,
        "provider": provider,
        "handle": handle,
        "roles": len(jobs),
        "europe": sum(countries.values()),
        "countries": dict(countries.most_common(10)),
        "italian": italian,
        "verified": date.today().isoformat(),
    }


def probe_company(name: str, slugs: list[str], region: str) -> dict | None:
    """The company's best European board, or None."""
    best = None
    for handle in slugs:
        for provider, _count in ats.probe(handle):
            entry = examine(provider, handle, name)
            if entry and (best is None or entry["europe"] > best["europe"]):
                best = entry
        if best:
            break  # the first slug that answers is the company's own
    if best:
        best["region"] = region
    return best


def load() -> dict:
    if CATALOGUE.exists():
        return json.loads(CATALOGUE.read_text(encoding="utf-8"))
    return {"companies": []}


def save(data: dict) -> None:
    data["_comment"] = (
        "European employers whose job board answered on the date shown. Built by "
        "tools/catalogue.py from catalogue/candidates/; never edited by hand. 'europe' "
        "counts roles placed in Europe, 'italian' those that mention the Italian language."
    )
    data["updated"] = date.today().isoformat()
    data["companies"].sort(key=lambda e: e["company"].lower())
    CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cmd_probe(args: argparse.Namespace) -> int:
    data = load()
    known = {(e["provider"], e["handle"]) for e in data["companies"]}
    known_names = {fold(e["company"]) for e in data["companies"]}
    todo = [c for c in read_candidates([Path(p) for p in args.files])
            if fold(c[0]) not in known_names or args.again]
    print(f"{len(todo)} candidates to probe ({len(known_names)} already catalogued)")
    added = missed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe_company, *c): c[0] for c in todo}
        for n, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            entry = future.result()
            if entry and (entry["provider"], entry["handle"]) not in known:
                data["companies"].append(entry)
                known.add((entry["provider"], entry["handle"]))
                added += 1
                print(f"[{n}/{len(todo)}] + {name:<34} {entry['provider']:<15} "
                      f"{entry['europe']:>4} in Europe  {entry['italian']:>3} Italian")
            elif not entry:
                missed += 1
            if n % 50 == 0:
                save(data)  # a long run should survive an interruption
    save(data)
    print(f"\nadded {added}, no European board found for {missed}")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    """Re-examine every catalogued board; drop the ones that no longer qualify."""
    data = load()
    kept, dropped = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(examine, e["provider"], e["handle"], e["company"]): e
                   for e in data["companies"]}
        for future in as_completed(futures):
            old, new = futures[future], future.result()
            if new:
                new["region"] = old.get("region", "")
                kept.append(new)
            else:
                dropped.append(old["company"])
    data["companies"] = kept
    save(data)
    print(f"kept {len(kept)}, dropped {len(dropped)}: {', '.join(sorted(dropped)) or '-'}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    companies = load()["companies"]
    by_country: Counter = Counter()
    for e in companies:
        by_country.update(e["countries"])
    print(f"{len(companies)} employers · {sum(e['europe'] for e in companies)} roles in Europe · "
          f"{sum(e['italian'] for e in companies)} mention Italian")
    print("providers:", dict(Counter(e["provider"] for e in companies).most_common()))
    print("countries:", ", ".join(f"{c} {n}" for c, n in by_country.most_common(25)))
    top = sorted(companies, key=lambda e: -e["italian"])[:15]
    print("most Italian:", ", ".join(f"{e['company']} ({e['italian']})" for e in top))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("files", nargs="+")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--again", action="store_true", help="re-probe companies already catalogued")
    p.set_defaults(func=cmd_probe)
    r = sub.add_parser("refresh", help="re-verify every catalogued board")
    r.add_argument("--workers", type=int, default=8)
    r.set_defaults(func=cmd_refresh)
    s = sub.add_parser("stats")
    s.set_defaults(func=cmd_stats)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
