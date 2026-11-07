"""The key pages' content: mentors, events and recordings (plan piece B).

Finished page content, ``{title, description, html}``, in the shape the
prototype's stand-in served and the chapter connector already places into a
WordPress page (Association ruling 33). Rules kept here:

* **Every class name starts with ``cmw-``** (ruling 33, WT-44), guarded by
  ``tests/test_website_pages.py`` over every page and the stylesheet.
* **Links to website pages are website-relative** (``/mentors/…``,
  ``/request-a-mentor/``): the chapter connector owns those pages. Links to
  this application (photos, the search address, event registration) are
  absolute, built from the applications' public address.
* **Who appears** (``prds/public-mentor-pages-plan.md``): mentorStatus Active
  AND publicProfile. ``acceptingNewClients`` changes the request button's
  wording, never whether the mentor is shown.
* **Mentor text the mentor wrote is cleaned**: tags outside a short list are
  unwrapped, and every attribute but a safe ``href`` is dropped, so nothing
  the CRM holds can add a class, a style or a script to the website.
* **One CRM read per cache period.** The roster is cached, and the search
  filters the cached roster, so a visitor typing never reaches the CRM.
"""

from __future__ import annotations

import asyncio
import html as html_mod
import logging
import re
import time
from typing import Any, Optional

from bs4 import BeautifulSoup

from core.espo import EspoError

log = logging.getLogger("cbm_intake.website")

MENTOR_ENTITY = "CMentorProfile"
SUMMARY_FIELD = "mentorSummary"
_MENTOR_SELECT = [
    "id", "name", "mentorStatus", "publicProfile", "acceptingNewClients",
    "mentorTitle", "aboutMentor", "areaOfExpertise", "industryExperience",
    "fluentLanguages", "profilePhotoId", "contactRecordId",
]
_PAGE = 200  # the CRM refuses a list page above 200 (espo-list-maxsize-403)

_ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a"}
_SAFE_HREF = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)


def esc(value: Any) -> str:
    return html_mod.escape(str(value if value is not None else ""), quote=True)


def slugify(name: str) -> str:
    """Lower case, every run of other characters a hyphen — the rule every
    existing mentor address on Cleveland's site already follows."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def clean_rich_text(raw: str) -> str:
    """The mentor's own rich text, reduced to plain formatting."""
    soup = BeautifulSoup(raw or "", "html.parser")
    for bad in soup.find_all(["script", "style", "iframe", "object", "embed", "form", "img"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        href = tag.get("href") if tag.name == "a" else None
        tag.attrs = {}
        if tag.name == "a":
            if href and _SAFE_HREF.match(href.strip()):
                tag.attrs = {"href": href.strip(), "rel": "nofollow noopener"}
            else:
                tag.unwrap()
    return str(soup).strip()


def plain_text(raw: str) -> str:
    text = re.sub(r"\s+", " ", BeautifulSoup(raw or "", "html.parser").get_text(" ")).strip()
    # The separator also lands between a closing tag and punctuation.
    return re.sub(r" ([.,;:!?)])", r"\1", text)


def first_words(text: str, count: int = 40) -> str:
    words = text.split()
    return " ".join(words[:count]) + ("…" if len(words) > count else "")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if value not in (None, "") else []


# --- the mentor roster ----------------------------------------------------------


def _visible(rec: dict[str, Any]) -> bool:
    return bool(rec.get("publicProfile")) and rec.get("mentorStatus") == "Active"


async def _has_summary_field(client: Any) -> bool:
    """mentorSummary is feature-detected (cmentorprofile-summary-field.md)."""
    try:
        fields = await client.metadata(f"entityDefs.{MENTOR_ENTITY}.fields")
    except EspoError as exc:
        log.warning("could not read %s fields (%s) — summaries come from About", MENTOR_ENTITY, exc)
        return False
    return isinstance(fields, dict) and SUMMARY_FIELD in fields


async def _list_all(client: Any, entity: str, **kwargs: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        env = await client.list(entity, max_size=_PAGE, offset=offset, **kwargs)
        page = env.get("list", []) or []
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


async def load_mentors(client: Any) -> list[dict[str, Any]]:
    """Every mentor the website shows, in name order, each with a unique slug."""
    select = list(_MENTOR_SELECT)
    has_summary = await _has_summary_field(client)
    if has_summary:
        select.append(SUMMARY_FIELD)
    records = [r for r in await _list_all(client, MENTOR_ENTITY, select=",".join(select)) if _visible(r)]

    contact_ids = sorted({r["contactRecordId"] for r in records if r.get("contactRecordId")})
    contacts: dict[str, dict[str, Any]] = {}
    for i in range(0, len(contact_ids), 100):
        chunk = contact_ids[i:i + 100]
        try:
            rows = await _list_all(client, "Contact", select="id,firstName,lastName,cLinkedInProfile",
                                   where=[{"type": "in", "attribute": "id", "value": chunk}])
        except EspoError as exc:  # names fall back to the profile's own name
            log.warning("mentor contacts unreadable: %s", exc)
            rows = []
        contacts.update({c["id"]: c for c in rows if c.get("id")})

    mentors: list[dict[str, Any]] = []
    for rec in records:
        contact = contacts.get(rec.get("contactRecordId") or "", {})
        name = " ".join(x for x in (str(contact.get("firstName") or "").strip(),
                                    str(contact.get("lastName") or "").strip()) if x)
        name = name or str(rec.get("name") or "").strip()
        if not name:
            continue
        about_html = clean_rich_text(rec.get("aboutMentor") or "")
        summary = str(rec.get(SUMMARY_FIELD) or "").strip() if has_summary else ""
        mentors.append({
            "id": rec["id"],
            "name": name,
            "firstName": str(contact.get("firstName") or "").strip() or name.split()[0],
            "title": str(rec.get("mentorTitle") or "").strip(),
            "summary": summary or first_words(plain_text(about_html)),
            "about": about_html,
            "expertise": _as_list(rec.get("areaOfExpertise")),
            "industries": _as_list(rec.get("industryExperience")),
            "languages": _as_list(rec.get("fluentLanguages")),
            "accepting": bool(rec.get("acceptingNewClients")),
            "photoId": rec.get("profilePhotoId") or "",
            "linkedin": str(contact.get("cLinkedInProfile") or "").strip(),
        })
    mentors.sort(key=lambda m: m["name"].lower())
    taken: dict[str, int] = {}
    for m in mentors:
        base = slugify(m["name"]) or "mentor"
        taken[base] = taken.get(base, 0) + 1
        m["slug"] = base if taken[base] == 1 else f"{base}-{taken[base]}"
    return mentors


def search(mentors: list[dict[str, Any]], q: str) -> list[str]:
    """Slugs of the mentors matching every word of ``q``; all of them for an
    empty search."""
    words = (q or "").lower().split()
    out = []
    for m in mentors:
        hay = " ".join([m["name"], m["title"], m["summary"], *m["expertise"],
                        *m["industries"], *m["languages"]]).lower()
        if all(w in hay for w in words):
            out.append(m["slug"])
    return out


# --- the pages --------------------------------------------------------------------


def _photo(base: str, m: dict[str, Any], cls: str, size: int) -> str:
    if not m["photoId"]:
        return f'<div class="{cls} {cls}--none" role="img" aria-label="No photograph"></div>'
    return (f'<img class="{cls}" src="{esc(base)}/api/website/mentors/{esc(m["slug"])}/photo" '
            f'alt="Photograph of {esc(m["name"])}" width="{size}" height="{size}" loading="lazy">')


def mentor_card(base: str, m: dict[str, Any]) -> str:
    languages = f'<p class="cmw-card__meta">Speaks {esc(", ".join(m["languages"]))}</p>' if m["languages"] else ""
    return (
        '<li class="cmw-card">'
        f'<a class="cmw-card__link" href="/mentors/{esc(m["slug"])}/">'
        f'{_photo(base, m, "cmw-card__photo", 160)}'
        f'<span class="cmw-card__name">{esc(m["name"])}</span></a>'
        f'<span class="cmw-card__title">{esc(m["title"])}</span>'
        f'<p class="cmw-card__summary">{esc(m["summary"])}</p>'
        f"{languages}</li>"
    )


def page_mentors(base: str, mentors: list[dict[str, Any]]) -> dict[str, str]:
    cards = "".join(mentor_card(base, m) for m in mentors)
    grid = (f'<ul class="cmw-grid">{cards}</ul>' if mentors
            else '<p class="cmw-empty">Our mentor profiles are being updated. Please check back soon.</p>')
    body = (
        f'<div class="cmw-root cmw-directory" data-cmw-search="{esc(base)}/api/website/mentors.json">'
        '<p class="cmw-lead">Every mentor volunteers their time. Mentoring is free and confidential.</p>'
        '<label class="cmw-search"><span class="cmw-search__label">Search by name, skill, industry or language</span>'
        '<input class="cmw-search__input" type="search" autocomplete="off"></label>'
        f"{grid}"
        '<p class="cmw-cta"><a class="cmw-button" href="/request-a-mentor/">Request a mentor</a></p>'
        "</div>"
    )
    return {"title": "Find a Mentor",
            "description": "Browse our volunteer business mentors by skill, industry and language.",
            "html": body}


def _tags(items: list[str]) -> str:
    return '<ul class="cmw-tags">' + "".join(f'<li class="cmw-tag">{esc(x)}</li>' for x in items) + "</ul>"


def page_mentor(base: str, m: dict[str, Any]) -> dict[str, str]:
    parts = [f'<p class="cmw-profile__title">{esc(m["title"])}</p>' if m["title"] else ""]
    if m["about"]:
        parts.append(f'<div class="cmw-profile__about">{m["about"]}</div>')
    if m["expertise"]:
        parts.append(f'<h2 class="cmw-h">Areas of expertise</h2>{_tags(m["expertise"])}')
    if m["industries"]:
        parts.append(f'<h2 class="cmw-h">Industries</h2>{_tags(m["industries"])}')
    if m["languages"]:
        parts.append(f'<h2 class="cmw-h">Languages</h2><p class="cmw-p">{esc(", ".join(m["languages"]))}</p>')
    if m["linkedin"].startswith("https://"):
        parts.append(f'<p class="cmw-p"><a href="{esc(m["linkedin"])}" rel="nofollow noopener">'
                     f'{esc(m["firstName"])} on LinkedIn</a></p>')
    if m["accepting"]:
        parts.append(f'<p class="cmw-cta"><a class="cmw-button" href="/request-a-mentor/?mentor={esc(m["slug"])}">'
                     f'Request {esc(m["firstName"])} as your mentor</a></p>')
    else:
        # The button stays; it says why it leads to the general form.
        parts.append(f'<p class="cmw-note">{esc(m["firstName"])} is not taking new clients right now. '
                     "We will match you with another mentor.</p>"
                     '<p class="cmw-cta"><a class="cmw-button" href="/request-a-mentor/">Request a mentor</a></p>')
    parts.append('<p class="cmw-p"><a class="cmw-back" href="/mentors/">All mentors</a></p>')
    body = (
        '<article class="cmw-root cmw-profile">'
        f'{_photo(base, m, "cmw-profile__photo", 240)}'
        f'<div class="cmw-profile__body">{"".join(parts)}</div></article>'
    )
    description = " — ".join(x for x in (m["name"], m["title"]) if x)
    if m["summary"]:
        description += ". " + m["summary"]
    return {"title": m["name"], "description": description, "html": body}


def page_events(events: list[dict[str, Any]]) -> dict[str, str]:
    items = []
    for e in events:
        action = ("Register" if e.get("registrationOpen") else "Details")
        link = (f'<a class="cmw-button cmw-button--small" href="{esc(e["url"])}">{action}</a>'
                if e.get("url") else "")
        items.append(
            '<li class="cmw-event">'
            f'<div class="cmw-event__date"><span class="cmw-event__month">{esc(e.get("monthShort"))}</span>'
            f'<span class="cmw-event__day">{esc(e.get("day"))}</span></div>'
            f'<div class="cmw-event__info"><span class="cmw-event__time">{esc(e.get("time"))}</span>'
            f'<span class="cmw-event__title">{esc(e.get("topic"))}</span>'
            f'<p class="cmw-event__summary">{esc(e.get("summary"))}</p>{link}</div></li>'
        )
    listing = (f'<ul class="cmw-event-list">{"".join(items)}</ul>' if items
               else '<p class="cmw-empty">No workshops or webinars are scheduled right now. Please check back soon.</p>')
    body = (
        '<div class="cmw-root cmw-events"><p class="cmw-lead">Free webinars and workshops for business owners.</p>'
        f"{listing}"
        '<p class="cmw-p"><a href="/recordings/">Watch past webinars</a></p></div>'
    )
    return {"title": "Workshops and Events",
            "description": "Upcoming free webinars and workshops for small business owners.",
            "html": body}


def page_recordings(recordings: list[dict[str, Any]]) -> dict[str, str]:
    items = []
    for r in recordings:
        target = r.get("url") or r.get("recordingUrl") or ""
        title = (f'<a class="cmw-rec__link" href="{esc(target)}">{esc(r.get("title"))}</a>'
                 if target.startswith("https://") else esc(r.get("title")))
        topics = (f'<span class="cmw-rec__topics">{esc(", ".join(r.get("categories") or []))}</span>'
                  if r.get("categories") else "")
        items.append(
            f'<li class="cmw-rec"><span class="cmw-rec__date">{esc(r.get("dateLabel"))}</span>'
            f'<span class="cmw-rec__title">{title}</span>{topics}'
            f'<p class="cmw-rec__summary">{esc(r.get("summary"))}</p></li>'
        )
    listing = (f'<ul class="cmw-rec-list">{"".join(items)}</ul>' if items
               else '<p class="cmw-empty">No recordings are available yet.</p>')
    return {"title": "Recorded Webinars",
            "description": "Watch past webinars on running and growing a small business.",
            "html": f'<div class="cmw-root cmw-recordings">{listing}</div>'}


# --- the cache ---------------------------------------------------------------------


class TimedCache:
    """One value per key for ``ttl`` seconds, refreshed by one caller at a time,
    so a burst of website requests on an expired entry reads the CRM once."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, key: str, ttl: int, load) -> Any:
        hit = self._data.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self._data.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            value = await load()
            self._data[key] = (time.monotonic(), value)
            return value

    def peek(self, key: str) -> Optional[Any]:
        hit = self._data.get(key)
        return hit[1] if hit else None

    def clear(self) -> None:
        self._data.clear()


cache = TimedCache()
