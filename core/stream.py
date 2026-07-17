"""Best-effort stream notes — a durable "the app did this" line in Espo history.

The staff tools act as the signed-in user, so their record writes look identical
in the EspoCRM stream to hand edits made in the CRM UI by the same person (the
source of a real forensics headache 2026-07-16: a mentor swap that looked like,
but wasn't, an app-side assignment). Posting a Note (``type=Post``) parented to
the record stamps the action, the channel, and the outcome into the exact
History/Stream panel staff already read.

Always best-effort: the note must never fail (or roll back) the operation it
documents — a role without Note create, stream disabled on the entity, or any
other rejection is logged at WARNING and swallowed.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("cbm_intake.stream_note")


async def post_stream_note(client: Any, parent_type: str, parent_id: str, text: str) -> bool:
    """Post ``text`` onto ``parent_type/parent_id``'s stream as the acting user.

    Returns True when the note stored, False on any failure (logged, never
    raised — this is a side channel, not part of the operation's contract).
    """
    try:
        await client.create(
            "Note",
            {"type": "Post", "parentType": parent_type, "parentId": parent_id, "post": text},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — side channel: never break the operation
        log.warning("stream note on %s/%s failed: %s", parent_type, parent_id, exc)
        return False
