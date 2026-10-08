"""Country facts for moving abroad, from Eurostat, with a register of every check.

    python3 tools/relocation.py

Writes relocation/countries.json and relocation/SOURCES.md. Each figure carries
its dataset, year and the date it was read; nothing is typed in by hand.

A value is published only after it passes two checks, and every rejection is
written to the register rather than dropped quietly:

* plausibility: a year that differs from both of its neighbours by more than
  MAX_JUMP is treated as a publication error (Eurostat's 2024 net-earnings
  release, read in October 2026, carries monthly figures in an annual series);
* recency: a figure older than MAX_AGE years is reported as a gap, not shown.

Italy is always included: the reader is Italian, and every figure is shown
next to the Italian one.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jsa.util import http_json  # noqa: E402

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
OUT = ROOT / "relocation"
MAX_JUMP = 0.4
MAX_AGE = 4

# The five regions the catalogue covers, plus Italy as the reference.
COUNTRIES = {
    "IT": "Italia",
    "DE": "Germania", "AT": "Austria", "CH": "Svizzera",
    "ES": "Spagna", "PT": "Portogallo",
    "FR": "Francia", "BE": "Belgio", "NL": "Paesi Bassi", "LU": "Lussemburgo",
    "PL": "Polonia", "CZ": "Cechia", "SK": "Slovacchia", "HU": "Ungheria", "RO": "Romania",
    "BG": "Bulgaria", "HR": "Croazia", "SI": "Slovenia", "EE": "Estonia", "LV": "Lettonia",
    "LT": "Lituania",
}

INDICATORS = {
    "net_earnings": {
        "label": "Stipendio netto annuo, persona single con retribuzione media (EUR)",
        "dataset": "earn_nt_net",
        "filters": {"currency": "EUR", "estruct": "NET", "ecase": "P1_NCH_AW100"},
        "decimals": 0,
    },
    "gross_earnings": {
        "label": "Retribuzione lorda annua corrispondente (EUR)",
        "dataset": "earn_nt_net",
        "filters": {"currency": "EUR", "estruct": "GRS", "ecase": "P1_NCH_AW100"},
        "decimals": 0,
    },
    "price_level": {
        "label": "Livello dei prezzi al consumo (UE-27 = 100)",
        "dataset": "prc_ppp_ind",
        "filters": {"na_item": "PLI_EU27_2020", "ppp_cat": "A01"},
        "decimals": 1,
    },
    "housing_price_level": {
        "label": "Livello dei prezzi di casa, acqua, luce e gas (UE-27 = 100)",
        "dataset": "prc_ppp_ind",
        "filters": {"na_item": "PLI_EU27_2020", "ppp_cat": "A0104"},
        "decimals": 1,
    },
    "unemployment": {
        "label": "Tasso di disoccupazione, 15-74 anni (%)",
        "dataset": "une_rt_a",
        "filters": {"age": "Y15-74", "sex": "T", "unit": "PC_ACT"},
        "decimals": 1,
    },
}


def series(dataset: str, filters: dict[str, str]) -> tuple[dict[str, dict[str, float]], str, str]:
    """{country: {year: value}}, the query URL, and Eurostat's update stamp."""
    params = [("format", "JSON"), ("lang", "EN"), ("sinceTimePeriod", str(date.today().year - 8))]
    params += list(filters.items()) + [("geo", g) for g in COUNTRIES]
    url = API + dataset + "?" + urlencode(params)
    data = http_json(url, retries=2, timeout=60)
    ids, sizes = data["id"], data["size"]
    index = {dim: data["dimension"][dim]["category"]["index"] for dim in ids}
    for dim, size in zip(ids, sizes):
        if dim not in ("geo", "time") and size != 1:
            raise ValueError(f"{dataset}: dimension {dim} has {size} values; the filter is incomplete")
    stride = {}
    step = 1
    for dim, size in reversed(list(zip(ids, sizes))):
        stride[dim] = step
        step *= size
    out: dict[str, dict[str, float]] = {}
    for geo, gi in index["geo"].items():
        for year, ti in index["time"].items():
            value = data["value"].get(str(gi * stride["geo"] + ti * stride["time"]))
            if value is not None:
                out.setdefault(geo, {})[year] = float(value)
    return out, url, data.get("updated", "")


def implausible(years: dict[str, float]) -> set[str]:
    """Years that jump away from their neighbours: a publication error, not an economy.

    Interior years are judged first, against both neighbours. An end year has
    only one neighbour, so it is judged against the nearest year that passed:
    otherwise one bad 2024 would also condemn a sound 2025.
    """
    keys = sorted(years)
    jump = lambda a, b: abs(years[a] - years[b]) / max(abs(years[b]), 1e-9) > MAX_JUMP  # noqa: E731
    bad = {k for i, k in enumerate(keys[1:-1], 1) if jump(k, keys[i - 1]) and jump(k, keys[i + 1])}
    for end, others in ((keys[0], keys[1:]), (keys[-1], keys[-2::-1])) if len(keys) > 1 else ():
        nearest = next((k for k in others if k not in bad), None)
        if nearest and jump(end, nearest):
            bad.add(end)
    return bad


def main() -> int:
    today = date.today()
    countries = {code: {"name": name, "facts": {}} for code, name in COUNTRIES.items()}
    register: list[str] = []
    sources: list[str] = []
    for key, spec in INDICATORS.items():
        try:
            data, url, updated = series(spec["dataset"], spec["filters"])
        except Exception as exc:  # noqa: BLE001 - one dataset down must not lose the others
            register.append(f"| {key} | tutti | non letto: {type(exc).__name__}: {exc} |")
            continue
        sources.append(f"| {key} | `{spec['dataset']}` | {updated[:10]} | [query]({url}) |")
        accepted: dict[str, dict[str, float]] = {}
        for code in COUNTRIES:
            years = data.get(code, {})
            bad = implausible(years)
            for year in sorted(bad):
                register.append(f"| {key} | {code} {year} | scartato: {years[year]:,.2f} si discosta "
                                f"di oltre il {MAX_JUMP:.0%} dagli anni vicini |")
            good = {y: v for y, v in years.items() if y not in bad}
            if good:
                accepted[code] = good
            else:
                register.append(f"| {key} | {code} | lacuna: Eurostat non pubblica il dato |")
        # One year for every country, so that comparisons compare like with
        # like: the latest year that every country with data has passed.
        shared = set.intersection(*(set(v) for v in accepted.values())) if accepted else set()
        common = max(shared) if shared else None
        if common and today.year - int(common) > MAX_AGE:
            register.append(f"| {key} | tutti | lacuna: ultimo anno comune {common}, troppo vecchio |")
            continue
        for code, good in accepted.items():
            year = common if common in good else max(good)
            if year != common:
                register.append(f"| {key} | {code} | anno {year} invece di {common}: "
                                f"non confrontabile direttamente |")
            countries[code]["facts"][key] = {
                "value": round(good[year], spec["decimals"]),
                "year": int(year),
                "label": spec["label"],
                "source": f"Eurostat {spec['dataset']}",
            }

    # Derived: what the net salary buys, relative to Italy. Prices and pay are
    # not always published for the same year; both years are kept on the figure.
    italy = countries["IT"]["facts"]
    for entry in countries.values():
        facts = entry["facts"]
        net, pli = facts.get("net_earnings"), facts.get("price_level")
        if net and pli:
            real = net["value"] / (pli["value"] / 100)
            facts["real_net_earnings"] = {
                "value": round(real), "year": net["year"], "price_year": pli["year"],
                "label": "Stipendio netto a parità di potere d'acquisto (EUR, prezzi UE-27)",
                "source": "derivato: net_earnings / price_level × 100",
            }
        gross = facts.get("gross_earnings")
        if net and gross and net["year"] == gross["year"] and gross["value"]:
            facts["net_share"] = {
                "value": round(net["value"] / gross["value"] * 100, 1), "year": net["year"],
                "label": "Quota del lordo che resta in tasca (%)",
                "source": "derivato: net_earnings / gross_earnings",
            }
    for code, entry in countries.items():
        mine, ref = entry["facts"].get("real_net_earnings"), italy.get("real_net_earnings")
        if mine and ref and code != "IT":
            entry["facts"]["vs_italy"] = {
                "value": round((mine["value"] / ref["value"] - 1) * 100),
                "year": mine["year"],
                "label": "Potere d'acquisto dello stipendio netto rispetto all'Italia (%)",
                "source": "derivato: real_net_earnings / real_net_earnings(IT) − 1",
            }

    OUT.mkdir(exist_ok=True)
    (OUT / "countries.json").write_text(json.dumps({
        "_comment": "Generated by tools/relocation.py from Eurostat. See SOURCES.md for every "
                    "query and every value that was rejected or missing.",
        "retrieved": today.isoformat(),
        "countries": countries,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "SOURCES.md").write_text("\n".join([
        "# Fonti e verifiche — dati per trasferirsi",
        "",
        f"Letti da Eurostat il {today.isoformat()} con `python3 tools/relocation.py`. "
        "Ogni numero in `countries.json` porta con sé dataset e anno.",
        "",
        "## Fonti",
        "",
        "| Indicatore | Dataset | Aggiornato da Eurostat | Query |",
        "|---|---|---|---|",
        *sources,
        "",
        "## Registro delle verifiche",
        "",
        "Valori scartati e lacune. Un dato che manca qui sotto resta vuoto nel prodotto: "
        "non viene stimato né sostituito.",
        "",
        "| Indicatore | Paese / anno | Esito |",
        "|---|---|---|",
        *(register or ["| — | — | nessuna anomalia |"]),
        "",
        "## Cosa non c'è ancora",
        "",
        "- Affitti in euro al mese per città: Eurostat pubblica indici, non livelli. "
        "Il livello dei prezzi di casa e utenze è un confronto tra paesi, non un affitto.",
        "- Burocrazia per i cittadini UE (registrazione, codice fiscale, sanità): da scrivere "
        "paese per paese dalle pagine ufficiali Your Europe e delle amministrazioni nazionali.",
        "",
    ]), encoding="utf-8")
    shown = sum(len(c["facts"]) for c in countries.values())
    print(f"{shown} figures for {len(countries)} countries · {len(register)} register entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
