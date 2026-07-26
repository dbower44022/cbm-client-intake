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
from typing import Any, Iterable, Optional

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


async def find_create_or_fill(
    client: EspoApi,
    entity: str,
    *,
    match_attr: str,
    match_value: str,
    create_payload: dict[str, Any],
    fill_keys: Optional[Iterable[str]] = None,
    droppable: Iterable[str] = DROPPABLE_CONTACT_FIELDS,
) -> tuple[str, str]:
    """Find ``entity`` by ``match_attr == match_value``; create or null-fill.

    ``fill_keys`` limits which fields participate in the null-fill on a match
    (defaults to every key in ``create_payload``). Pass it to exclude the match
    key, link FKs, and discriminators that must never be back-written. A field
    is updated only when the desired value is non-empty AND the stored value is
    empty.

    The create goes through :func:`create_dropping_invalid`, so one CRM-rejected
    value in a ``droppable`` field costs that field, not the submission.
    """
    keys = list(fill_keys) if fill_keys is not None else list(create_payload.keys())
    select = ",".join(dict.fromkeys(["id", *keys]))
    existing = await client.find_one(entity, match_attr, match_value, select=select)
    if existing is None:
        created = await create_dropping_invalid(
            client, entity, create_payload, droppable=droppable
        )
        return created["id"], "created"

    fill = {
        k: create_payload[k]
        for k in keys
        if k in create_payload
        and not _is_empty(create_payload[k])
        and _is_empty(existing.get(k))
    }
    if fill:
        await client.update(entity, existing["id"], fill)
        return existing["id"], "updated"
    return existing["id"], "matched"
