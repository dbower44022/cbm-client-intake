"""Find-or-create with null-fill on repeat submissions.

Intake Contacts/Accounts are matched by a natural key (email / name). On a
*repeat* submission we must not clobber data the CRM already holds — a staffer
may have curated it — but we should backfill any field the earlier record left
empty. ``find_create_or_fill`` encodes that rule:

* no match           -> create with the full payload;
* match, some empties -> update only the fields that are currently null/empty;
* match, nothing empty -> leave it untouched.

Returns ``(record_id, action)`` with ``action`` in ``{"created", "updated",
"matched"}`` so callers can log what happened.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Iterable, Optional

from .espo import EspoApi, EspoError, validation_field

log = logging.getLogger("cbm_intake.crm_upsert")

# Fields a create may sacrifice to save the submission (see
# :func:`create_dropping_invalid`). Free-text values the public forms collect
# but which are NOT the record's identity: losing one costs a detail, keeping
# it costs the whole lead.
DROPPABLE_CONTACT_FIELDS = frozenset({"phoneNumber", "phone"})


def _is_empty(value: Any) -> bool:
    """True for the CRM's notion of an unset field: None / "" / [] / {}.

    Deliberately does NOT treat ``False`` or ``0`` as empty — a stored boolean
    ``False`` or integer ``0`` is a real value and must not be overwritten.
    """
    return value is None or value == "" or value == [] or value == {}


async def create_dropping_invalid(
    client: EspoApi,
    entity: str,
    payload: dict[str, Any],
    *,
    droppable: Iterable[str] = DROPPABLE_CONTACT_FIELDS,
) -> dict[str, Any]:
    """Create ``entity``; if the CRM rejects ONE droppable field's value, drop
    it and retry rather than losing the whole submission.

    EspoCRM validates some values more strictly than the app can predict — a
    junk phone like ``123123213332`` passes :func:`core.phone.e164_or_none`
    (10–15 digits) but is rejected with ``validationFailure``
    ``{"field": "phoneNumber", "type": "valid"}``, which used to 400 the
    Contact create and strand the entire intake in ``needs_attention``
    (prod, sponsor submission 2026-06-30 — a month of hourly alerts for one
    spam phone number). Email is the contact channel that matters and the raw
    value survives in the ``CIntakeSubmission`` audit log, so a bad value in a
    *droppable* field is worth sacrificing.

    Only a ``valid``/``pattern`` rejection of a field in ``droppable`` is
    retried — a ``required`` failure, an unlisted field (identity, links,
    discriminators), or any other error re-raises unchanged. At most two
    fields are dropped before giving up.
    """
    attempt = dict(payload)
    droppable = set(droppable)
    for _ in range(2):
        try:
            return await client.create(entity, attempt)
        except EspoError as exc:
            parsed = validation_field(exc)
            if parsed is None:
                raise
            field, rule = parsed
            if rule not in ("valid", "pattern") or field not in droppable:
                raise
            if field not in attempt:
                raise
            log.warning(
                "%s create: CRM rejected %s=%r (%s) — dropping it and retrying "
                "so the submission is not lost; the raw value is in the "
                "submission audit log",
                entity, field, attempt[field], rule,
            )
            attempt.pop(field)
    return await client.create(entity, attempt)


# The Company (Account) type discriminator — a multiEnum every management grid
# and report filters on. One company may hold several values.
COMPANY_TYPE_FIELD = "cCompanyType"
COMPANY_SELECT = "id,cCompanyType,website"   # what a company find must select
# The Contact type discriminator, the same shape.
CONTACT_TYPE_FIELD = "cContactType"

# The Prospect relabel (prds/prospect-marketing/build-plan.md § 1.9, ruling 21):
# ``Prospect`` is the type a promoted business or person carries BEFORE any
# relationship exists. Appending a RELATIONSHIP type replaces it — the one
# sanctioned type rewrite. ``Presenter``, ``Member``, ``Donor`` and
# ``Administrator`` are not relationship types for this rule and leave it.
PROSPECT_TYPE = "Prospect"
RELATIONSHIP_TYPES = frozenset({"Client", "Partner", "Sponsor", "Mentor"})


def merged_types(types: Any, new_type: str) -> Optional[list[str]]:
    """The stored type list after this door appends ``new_type``, or None when
    nothing changes.

    * a value already present is left alone — nothing ELSE is ever removed;
    * a missing value is appended;
    * a relationship type (:data:`RELATIONSHIP_TYPES`) removes ``Prospect``
      (§ 1.9 — the relabel at conversion), any other type leaves it.
    """
    current = [t for t in (types or []) if t]
    out = list(current)
    if new_type not in out:
        out.append(new_type)
    if new_type in RELATIONSHIP_TYPES and PROSPECT_TYPE in out and new_type != PROSPECT_TYPE:
        out = [t for t in out if t != PROSPECT_TYPE]
    return None if out == current else out


def website_key(value: Any) -> str:
    """One comparable form of a website address, or "" for none.

    ``acme.com``, ``https://www.acme.com/`` and ``HTTP://Acme.com`` are one
    site to a person, so they are one key here: scheme dropped, a leading
    ``www.`` dropped, lower-cased, trailing slash dropped. The path is kept —
    ``example.org/program-a`` and ``example.org/program-b`` are different
    addresses, and a programme inside an organisation is exactly what a second
    partner record often is. Query strings and fragments are dropped.
    """
    raw = (value or "").strip() if isinstance(value, str) else ""
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    host, _, path = raw.partition("/")
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    path = path.rstrip("/")
    return f"{host}/{path}" if path else host


class CompanyConflict(Exception):
    """A same-named company exists at a DIFFERENT web address.

    Raised by the public-form orchestrators before any record is written, so
    the submission can be HELD for staff (never refused — the submitter is an
    anonymous visitor — and never merged, which would attach one business to
    another's record). Carries what the reviewer needs to decide.
    """

    def __init__(self, name: str, existing_id: str, existing_website: str,
                 submitted_website: str) -> None:
        self.name = name
        self.existing_id = existing_id
        self.existing_website = existing_website
        self.submitted_website = submitted_website
        super().__init__(
            f"A company named {name} already exists (Account/{existing_id}) with "
            f"the website {existing_website}; this submission gave {submitted_website}."
        )


def conflicting_website(existing: dict[str, Any], website: Any) -> Optional[str]:
    """The matched company's stored website when it DISAGREES with ``website``.

    None when no website was given, none is stored, or the two are one site
    under :func:`website_key`. ``existing`` must have been read with
    :data:`COMPANY_SELECT`.
    """
    given = website_key(website)
    stored = existing.get("website") or ""
    if not given or not stored:
        return None
    return stored if website_key(stored) != given else None


async def fill_company_website(client: EspoApi, existing: dict[str, Any], website: Any) -> bool:
    """Null-fill a matched company's website, best-effort. True when written."""
    if not website or existing.get("website"):
        return False
    try:
        await client.update("Account", existing["id"], {"website": website})
    except EspoError as exc:
        log.warning("could not fill website on Account/%s: %s", existing.get("id"), exc)
        return False
    return True


async def merge_company_type(client: EspoApi, existing: dict[str, Any], company_type: str) -> bool:
    """Give a REUSED company this door's role, merge-only and best-effort.

    A company the CRM already knows in one role (a funder, say) that comes back
    through another door (the partner form, the partner quick-add) must gain the
    new ``cCompanyType`` value, or every screen keyed on that type misses it.
    The rule, shared by the public forms and the staff quick-add:

    * a value already present is left alone — nothing is ever removed, with
      ONE exception: a relationship type replaces ``Prospect``
      (:func:`merged_types`, § 1.9 of the prospect marketing build plan);
    * a missing value is appended with one update;
    * a refused update is logged and swallowed — the type is a classification,
      never a reason to lose the submission.

    ``existing`` is the matched company as ``find_one`` returned it; select
    :data:`COMPANY_SELECT` on that read or the stored list reads as empty and
    the merge would overwrite it. Returns True when a write was made.
    """
    types = merged_types(existing.get(COMPANY_TYPE_FIELD), company_type)
    if types is None:
        return False
    try:
        await client.update("Account", existing["id"], {COMPANY_TYPE_FIELD: types})
    except EspoError as exc:
        log.warning(
            "could not add %s to Account/%s %s: %s",
            company_type, existing.get("id"), COMPANY_TYPE_FIELD, exc,
        )
        return False
    return True


async def merge_contact_type(client: EspoApi, existing: dict[str, Any], contact_type: str) -> bool:
    """The Contact sibling of :func:`merge_company_type`, and the ONE reason a
    door ever touches a matched contact's type (§ 1.9, ruling 21).

    A person's ``cContactType`` is curated data: it is never null-filled and
    never merged for a door's convenience — an existing Client who asks a
    question is not a Prospect, a Mentor who registers for a webinar stays a
    Mentor. The exception is conversion: when a relationship door (client
    intake, partner, sponsor) matches a Contact typed ``Prospect``, the
    relationship type is appended and ``Prospect`` removed. Any other stored
    type is left in place and only the missing value is appended. Merge-only
    on everything but ``Prospect``, best-effort, returns True when written.

    ``existing`` must have been read with ``cContactType`` selected, or the
    stored list reads as empty and the merge would overwrite it.
    """
    types = merged_types(existing.get(CONTACT_TYPE_FIELD), contact_type)
    if types is None:
        return False
    try:
        await client.update("Contact", existing["id"], {CONTACT_TYPE_FIELD: types})
    except EspoError as exc:
        log.warning(
            "could not add %s to Contact/%s %s: %s",
            contact_type, existing.get("id"), CONTACT_TYPE_FIELD, exc,
        )
        return False
    return True


async def find_create_or_fill(
    client: EspoApi,
    entity: str,
    *,
    match_attr: str,
    match_value: str,
    create_payload: dict[str, Any],
    fill_keys: Optional[Iterable[str]] = None,
    droppable: Iterable[str] = DROPPABLE_CONTACT_FIELDS,
    select_extra: Iterable[str] = (),
    on_match: Optional[Callable[[dict[str, Any]], Awaitable[Any]]] = None,
    true_wins: Iterable[str] = (),
) -> tuple[str, str]:
    """Find ``entity`` by ``match_attr == match_value``; create or null-fill.

    ``true_wins`` names boolean keys where a desired ``True`` is written over a
    stored ``False`` as well as over an empty value — never the reverse. It is
    for consent and opt-in boxes (Doug's ruling 10-22-26): a person's own
    later tick is dated evidence and overrides their earlier opt-out, whereas
    an unticked box writes nothing at all (the caller omits the key).

    ``fill_keys`` limits which fields participate in the null-fill on a match
    (defaults to every key in ``create_payload``). Pass it to exclude the match
    key, link FKs, and discriminators that must never be back-written. A field
    is updated only when the desired value is non-empty AND the stored value is
    empty.

    ``on_match`` is called with the matched record (as read, with ``id``,
    the fill keys and ``select_extra``) before the null-fill — the hook the
    relationship doors use for the Prospect relabel (:func:`merge_contact_type`)
    without a second read. It never changes the fill.

    The create goes through :func:`create_dropping_invalid`, so one CRM-rejected
    value in a ``droppable`` field costs that field, not the submission.
    """
    keys = list(fill_keys) if fill_keys is not None else list(create_payload.keys())
    select = ",".join(dict.fromkeys(["id", *keys, *select_extra]))
    existing = await client.find_one(entity, match_attr, match_value, select=select)
    if existing is None:
        created = await create_dropping_invalid(
            client, entity, create_payload, droppable=droppable
        )
        return created["id"], "created"

    if on_match is not None:
        await on_match(existing)
    fill = {
        k: create_payload[k]
        for k in keys
        if k in create_payload
        and not _is_empty(create_payload[k])
        and _is_empty(existing.get(k))
    }
    for k in true_wins:
        if create_payload.get(k) is True and existing.get(k) is False:
            fill[k] = True
    if fill:
        await client.update(entity, existing["id"], fill)
        return existing["id"], "updated"
    return existing["id"], "matched"
