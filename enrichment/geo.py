"""Postal code to county, and the chapter's service area (design E13, E17).

The table is built from the United States Census Bureau's 2020 ZIP Code
Tabulation Area to county relationship file and shipped in the image
(``data/zcta_county.csv``: zip, state, county), so the gate never calls
anything. A postal code that spans several counties lists each of them; the
gate passes it if any one is a chapter county (build plan § 2).
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "zcta_county.csv"
_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


@lru_cache(maxsize=1)
def _table() -> dict[str, tuple[tuple[str, str], ...]]:
    out: dict[str, list[tuple[str, str]]] = {}
    with _DATA.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["zip"], []).append((row["state"], row["county"]))
    return {k: tuple(v) for k, v in out.items()}


def zip5(postal_code: str) -> str:
    """The five-digit postal code inside a value, or '' when there is none."""
    m = _ZIP.search(postal_code or "")
    return m.group(1) if m else ""


def counties_for(postal_code: str) -> tuple[tuple[str, str], ...]:
    """Every (state, county) the postal code reaches; empty when unknown."""
    z = zip5(postal_code)
    return _table().get(z, ()) if z else ()


def parse_service_area(setting: str) -> frozenset[tuple[str, str]]:
    """``OH:Cuyahoga|OH:Lake`` as normalised (state, county) pairs.

    Separators ``|``, ``;`` and new lines are accepted; a trailing " County"
    is ignored, so ``OH:Lake County`` and ``OH:Lake`` are the same entry.
    """
    out = set()
    for part in re.split(r"[|;\n]+", setting or ""):
        if ":" not in part:
            continue
        state, county = part.split(":", 1)
        county = re.sub(r"\s+county$", "", county.strip(), flags=re.I)
        if state.strip() and county:
            out.add((state.strip().upper(), _norm(county)))
    return frozenset(out)


def in_area(counties: tuple[tuple[str, str], ...],
            area: frozenset[tuple[str, str]]) -> str:
    """The first chapter county among ``counties``, or '' when none is."""
    for state, county in counties:
        if (state.upper(), _norm(county)) in area:
            return county
    return ""
