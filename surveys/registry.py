"""The survey purposes (ruling BE23): every kind of survey the engine serves.

A survey purpose registers itself once, at import, with ``register``. The
engine then reads everything specific to it from here: its feature switch,
its link expiry and retry settings, its survey definitions, the surveys a
link opens, the first screen's words, and what happens on the first save and
on submit. ``surveys/CLAUDE.md`` says how to add one.

The definitions are read and checked once, at start-up (``load_definitions``).
An invalid file is logged as an ERROR and that purpose's links answer "no
longer valid", rather than the application failing to start; each purpose's
own definitions test is what stops one shipping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .definitions import LoaderRules, Survey, SurveyError, load_all

log = logging.getLogger("cbm_intake.surveys")


@dataclass(frozen=True)
class PageText:
    """The words on the survey page that depend on the purpose. Each value is
    trusted HTML written in the purpose's own code, and may use the branding
    tokens ``{{org}}`` and ``{{abbr}}``.

    ``title``: the page's heading and the end of its ``<title>``.
    ``consent_intro``: the paragraphs above the consent box.
    ``consent_label``: the consent box's own words.
    ``list_intro``: the text above the list of surveys.
    ``all_done``: shown once every survey on the link is submitted."""

    title: str
    consent_intro: str
    consent_label: str
    list_intro: str
    all_done: str


@dataclass
class SubmitContext:
    """What the first-save and submit steps receive: the link, the survey's
    answer row, its definition, and the purpose's CRM client."""

    link: dict[str, Any]
    row: dict[str, Any]
    survey: Survey
    client: Any


@dataclass(frozen=True)
class SurveyPurpose:
    """One kind of survey built on the engine.

    ``key``: stored on every link (``survey_link.purpose``).
    ``switch``, ``link_days``, ``retry_seconds``: names of ``Settings``
    attributes, read per request — the feature switch (off: its links open
    nothing), how many days a new link stays open, and the seconds between the
    worker's retry passes (0 stops them).
    ``definitions_dir`` and ``loader``: where its survey definitions live and
    what it adds to the format.
    ``surveys_for(link)``: the survey keys a link opens, in answer order.
    ``page``: the page's words.
    ``submit(ctx)``: hands one submitted survey on; raises to be retried
    (``retryable`` names the exception types that count as a refusal).
    ``first_save(ctx)``: optional, best-effort, once per survey per link, on
    the first save that holds an answer; it must never raise.
    ``client(app)``: the client ``submit`` and ``first_save`` write through."""

    key: str
    switch: str
    link_days: str
    retry_seconds: str
    definitions_dir: Path
    surveys_for: Callable[[dict[str, Any]], list[str]]
    page: PageText
    submit: Callable[[SubmitContext], Awaitable[None]]
    client: Callable[[Any], Any]
    loader: LoaderRules = field(default_factory=LoaderRules)
    first_save: Optional[Callable[[SubmitContext], Awaitable[None]]] = None
    retryable: tuple[type[BaseException], ...] = (Exception,)


_PURPOSES: dict[str, SurveyPurpose] = {}
_DEFINITIONS: dict[str, Optional[dict[str, Survey]]] = {}


def register(purpose: SurveyPurpose) -> SurveyPurpose:
    """Register a survey purpose. Registering the same key again replaces it
    (a module reloaded in a test)."""
    _PURPOSES[purpose.key] = purpose
    _DEFINITIONS.pop(purpose.key, None)
    return purpose


def unregister(key: str) -> None:
    """For tests that register a purpose of their own."""
    _PURPOSES.pop(key, None)
    _DEFINITIONS.pop(key, None)


def get(key: str) -> Optional[SurveyPurpose]:
    return _PURPOSES.get(key)


def all_purposes() -> list[SurveyPurpose]:
    return list(_PURPOSES.values())


def is_on(purpose: SurveyPurpose, settings: Any) -> bool:
    return bool(getattr(settings, purpose.switch, False))


def any_on(settings: Any) -> bool:
    """True when at least one purpose's switch is on: until then every survey
    address answers 404, before any database read."""
    return any(is_on(p, settings) for p in _PURPOSES.values())


def load_definitions(key: str) -> Optional[dict[str, Survey]]:
    """Read and check one purpose's definitions now. None, logged as an
    ERROR, when one is invalid."""
    purpose = _PURPOSES[key]
    try:
        loaded: Optional[dict[str, Survey]] = load_all(purpose.definitions_dir, purpose.loader)
    except SurveyError as exc:
        log.error("%s survey definitions are invalid: %s", key, exc)
        loaded = None
    _DEFINITIONS[key] = loaded
    return loaded


def definitions(key: str) -> Optional[dict[str, Survey]]:
    """One purpose's definitions, read on first use and kept."""
    if key not in _PURPOSES:
        return None
    if _DEFINITIONS.get(key) is None:
        return load_definitions(key)
    return _DEFINITIONS[key]


def load_every_purpose() -> None:
    """Start-up: read every registered purpose's definitions once."""
    for key in list(_PURPOSES):
        load_definitions(key)
