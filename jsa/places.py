"""Country facts for moving abroad, as the dashboard shows them.

The figures come from relocation/countries.json (tools/relocation.py, read from
Eurostat with a register of every check). Here they are reduced to what a card
needs, with every comparison made against Italy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

RELOCATION_PATH = REPO_ROOT / "relocation" / "countries.json"
GUIDES_DIR = REPO_ROOT / "relocation" / "guides"
SITE = "https://d0m3n1c0x.github.io/job-search-agent"


def guide_urls(directory: Path | None = None) -> dict[str, str]:
    """{country code: public URL of its moving guide}, for the guides that exist."""
    found: dict[str, str] = {}
    for path in sorted((directory or GUIDES_DIR).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("country") and data.get("slug"):
            found[data["country"]] = f"{SITE}/paesi/{data['slug']}.html"
    return found

NAMES = {
    "IT": ("Italia", "Italy"), "DE": ("Germania", "Germany"), "AT": ("Austria", "Austria"),
    "CH": ("Svizzera", "Switzerland"), "ES": ("Spagna", "Spain"), "PT": ("Portogallo", "Portugal"),
    "FR": ("Francia", "France"), "BE": ("Belgio", "Belgium"), "NL": ("Paesi Bassi", "Netherlands"),
    "LU": ("Lussemburgo", "Luxembourg"), "PL": ("Polonia", "Poland"), "CZ": ("Cechia", "Czechia"),
    "SK": ("Slovacchia", "Slovakia"), "HU": ("Ungheria", "Hungary"), "RO": ("Romania", "Romania"),
    "BG": ("Bulgaria", "Bulgaria"), "HR": ("Croazia", "Croatia"), "SI": ("Slovenia", "Slovenia"),
    "EE": ("Estonia", "Estonia"), "LV": ("Lettonia", "Latvia"), "LT": ("Lituania", "Lithuania"),
    "IE": ("Irlanda", "Ireland"),
}


def country_cards(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """{code: {it, en, vs, net, prices, unemployment, year}}; empty when the data is absent."""
    try:
        data = json.loads((path or RELOCATION_PATH).read_text(encoding="utf-8"))
        countries = data["countries"]
        italy = countries["IT"]["facts"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    cards: dict[str, dict[str, Any]] = {}
    guides = guide_urls()
    for code, entry in countries.items():
        facts = entry.get("facts", {})
        net, pli = facts.get("net_earnings"), facts.get("price_level")
        if not net or not pli:
            continue
        it, en = NAMES.get(code, (entry.get("name", code), entry.get("name", code)))
        cards[code] = {
            "it": it, "en": en,
            "vs": facts.get("vs_italy", {}).get("value"),          # None for Italy itself
            "net": net["value"],
            "prices": round((pli["value"] / italy["price_level"]["value"] - 1) * 100),
            "unemployment": facts.get("unemployment", {}).get("value"),
            "year": net["year"],
            "guide": guides.get(code, ""),
        }
    return cards
