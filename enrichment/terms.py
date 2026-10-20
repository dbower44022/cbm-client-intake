"""The name-reading rules: which words read as a holding company, which as a
trade, which name or street is a registered-agent service, and which words are
only a legal suffix.

The defaults ship in ``data/name_terms.json``. A chapter overrides any list by
publishing its own file at ``ENRICHMENT_TERMS_URL`` (the
``CHAPTER_TOKENS_URL`` precedent); a list it leaves out keeps the default. The
segment list (design E2) is read the same way from ``CHAPTER_SEGMENTS_URL``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.enrichment.terms")

_DATA = Path(__file__).parent / "data" / "name_terms.json"
_LISTS = ("holding_words", "trade_words", "agent_names", "agent_streets", "legal_suffixes")


@dataclass(frozen=True)
class Terms:
    holding_words: tuple[str, ...]
    trade_words: tuple[str, ...]
    agent_names: tuple[str, ...]
    agent_streets: tuple[str, ...]
    legal_suffixes: tuple[str, ...]


@dataclass(frozen=True)
class Segments:
    """The chapter's segment list (design E2). Empty until the chapter writes
    one, and then the segment signal is a fixed 50 for every lead."""
    favoured: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.favoured and not self.excluded


def _clean(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({str(v).strip().lower() for v in values if str(v).strip()}))


@lru_cache(maxsize=1)
def _default_raw() -> dict[str, Any]:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def build_terms(override: Optional[dict[str, Any]] = None) -> Terms:
    raw = dict(_default_raw())
    for key in _LISTS:
        if isinstance(override, dict) and isinstance(override.get(key), list):
            raw[key] = override[key]
    return Terms(**{key: _clean(raw.get(key)) for key in _LISTS})


def build_segments(raw: Optional[dict[str, Any]]) -> Segments:
    if not isinstance(raw, dict):
        return Segments()
    return Segments(favoured=_clean(raw.get("favoured")), excluded=_clean(raw.get("excluded")))


def words(text: str) -> str:
    """Lower case, punctuation to spaces, single-spaced, padded for whole-word
    matching: ``" smith bakery llc "``."""
    return " " + re.sub(r"[^a-z0-9&]+", " ", (text or "").lower()).strip() + " "


def has_word(haystack_words: str, term: str) -> bool:
    return words(term) in haystack_words if term.strip() else False


def matches(text: str, terms: tuple[str, ...]) -> list[str]:
    """Every term found in ``text`` as whole words, in list order."""
    hay = words(text)
    return [t for t in terms if has_word(hay, t)]


def core_name(name: str, terms: Terms) -> list[str]:
    """The business name's words without its legal suffix: ``SMITH BAKERY
    LLC`` → ``["smith", "bakery"]``."""
    tokens = words(name).split()
    suffixes = {w for s in terms.legal_suffixes for w in words(s).split()}
    while tokens and tokens[-1] in suffixes:
        tokens.pop()
    return tokens


async def fetch_json(url: str, timeout: float = 10.0) -> Optional[dict[str, Any]]:
    """A chapter's published JSON file, or None (logged) when it cannot be read.
    Never raises: a missing override means the defaults, never a failed pass."""
    if not url:
        return None
    try:
        # Its own short-lived client: the shared pool is the CRM's, and an
        # outside address must never hold one of its connections.
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
            resp = await http.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001 — an override is optional
        log.warning("enrichment: could not read %s: %s", url, exc)
        return None
