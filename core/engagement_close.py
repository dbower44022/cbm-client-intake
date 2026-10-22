"""An engagement's close date is stamped when it closes (ruling 70,
prds/prospect-marketing/rulings.md, 10-21-26).

When an engagement moves into a closed status, the date it closed is written
into ``CEngagement.closeDate`` — only if the field is empty, never over a date
staff entered. Called from every place a status is saved: the session tools'
Overview status picker and Details tab, and Client Administration's popup.

Best-effort: a failure is logged, never fails the user's save. Feature-detected:
while the CRM still holds the field Read-only (every API write would be
silently dropped — Acl/GlobalRestriction), nothing is attempted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .espo import EspoError

log = logging.getLogger("cbm_intake.engagement_close")

ENGAGEMENT = "CEngagement"
CLOSE_FIELD = "closeDate"
#: The statuses that end an engagement (ruling 70).
CLOSED_STATUSES = frozenset({"Completed", "Inactive", "Abandoned"})


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def close_date_writable(client: Any) -> bool:
    """The field exists and is not Read-only. Fails closed."""
    try:
        fields = await client.metadata(f"entityDefs.{ENGAGEMENT}.fields") or {}
    except Exception:  # noqa: BLE001
        return False
    d = fields.get(CLOSE_FIELD) if isinstance(fields, dict) else None
    return isinstance(d, dict) and not d.get("readOnly")


async def stamp_close_date(client: Any, engagement_id: str, new_status: Optional[str], *,
                           payload: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Write today's date as the close date when ``new_status`` closes the
    engagement and no close date is held. ``payload`` is the save that set the
    status: a close date in it (staff typed one) wins. Returns the date
    written, or None."""
    if new_status not in CLOSED_STATUSES:
        return None
    if payload and payload.get(CLOSE_FIELD):
        return None
    try:
        if not await close_date_writable(client):
            return None
        rec = await client.get(ENGAGEMENT, engagement_id, select=CLOSE_FIELD)
        if (rec or {}).get(CLOSE_FIELD):
            return None
        today = _today()
        await client.update(ENGAGEMENT, engagement_id, {CLOSE_FIELD: today})
        return today
    except EspoError as exc:
        log.warning("close date stamp on %s failed: %s", engagement_id, exc)
        return None
