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

from typing import Any, Iterable, Optional

from .espo import EspoApi


def _is_empty(value: Any) -> bool:
    """True for the CRM's notion of an unset field: None / "" / [] / {}.

    Deliberately does NOT treat ``False`` or ``0`` as empty — a stored boolean
    ``False`` or integer ``0`` is a real value and must not be overwritten.
    """
    return value is None or value == "" or value == [] or value == {}


async def find_create_or_fill(
    client: EspoApi,
    entity: str,
    *,
    match_attr: str,
    match_value: str,
    create_payload: dict[str, Any],
    fill_keys: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
    """Find ``entity`` by ``match_attr == match_value``; create or null-fill.

    ``fill_keys`` limits which fields participate in the null-fill on a match
    (defaults to every key in ``create_payload``). Pass it to exclude the match
    key, link FKs, and discriminators that must never be back-written. A field
    is updated only when the desired value is non-empty AND the stored value is
    empty.
    """
    keys = list(fill_keys) if fill_keys is not None else list(create_payload.keys())
    select = ",".join(dict.fromkeys(["id", *keys]))
    existing = await client.find_one(entity, match_attr, match_value, select=select)
    if existing is None:
        created = await client.create(entity, create_payload)
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
