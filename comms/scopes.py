"""The mailbox-scope cache: rebuild the scopes only when the CRM has changed.

``crm.build_scopes`` reads every manager's engagements, partners and funders
and each record's contacts — about 400 CRM reads a pass on production, every
five minutes, most of the CRM load the worker generates (the 10-09-26
performance review). The scopes rarely change, so each pass now asks the CRM
five one-row questions instead — *anything created or modified since the last
build?* — one per entity the scopes are built from, and reuses the previous
scopes when the answer is no. A full rebuild still runs every
``COMMS_SCOPE_REBUILD_SECONDS`` (default one hour; 0 = every pass, the old
behaviour) whatever the answers.

Doug's ruling 10-09-26 (option A): the one path this does not see at once is
linking an ALREADY-KNOWN contact to an existing record, which (inferred, not
checked) leaves the record's modification time alone; a message from that
person inside the hour is skipped by the stale scope and, because a skipped
message's cursor moves on, is not captured for that record. The hourly rebuild
bounds it. Every other way a person joins a record creates or modifies one.

Fail open to freshness: a change check that cannot be answered rebuilds.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.espo import EspoError

from . import crm

log = logging.getLogger("cbm_intake.comms.scopes")

# The entities the scopes are built from. A manager's mailbox and login come
# from the profile; the records from the three reverse links; the addresses
# from the contacts. A new or edited row in any of them can change a scope.
WATCHED_ENTITIES = (
    crm.MENTOR_PROFILE, "CEngagement", "CPartnerProfile", "CSponsorProfile", "Contact",
)
# The watermark sits this far behind the build's start, so a record saved in
# the same second as the build (clock skew, a write racing the read) is not
# missed by the next pass's check.
_OVERLAP = timedelta(seconds=60)


@dataclass
class ScopeCache:
    scopes: list[Any] = field(default_factory=list)
    built_at: float = 0.0          # monotonic
    watermark: str = ""            # CRM datetime (UTC) the change check asks from
    rebuilds: int = 0
    reuses: int = 0


_cache = ScopeCache()


def reset() -> None:
    """Forget the cached scopes (tests; a process restart does the same)."""
    global _cache
    _cache = ScopeCache()


def _crm_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def changed_since(client: Any, watermark: str) -> Optional[str]:
    """The first watched entity with a row modified after ``watermark``, or
    None when nothing has. Raises nothing: an unanswerable check returns the
    entity's name with ``?`` so the caller rebuilds (fail open)."""
    for entity in WATCHED_ENTITIES:
        try:
            data = await client.list(
                entity,
                where=[{"type": "after", "attribute": "modifiedAt", "value": watermark}],
                select="id", max_size=1,
            )
        except EspoError as exc:
            log.warning("scope change check on %s failed (%s): rebuilding", entity, exc)
            return f"{entity}?"
        if int(data.get("total") or 0) > 0 or data.get("list"):
            return entity
    return None


async def scopes_for_pass(client: Any, settings: Any) -> list[Any]:
    """The scopes for this sync pass — cached, rebuilt when due or changed."""
    global _cache
    ttl = int(getattr(settings, "comms_scope_rebuild_seconds", 0) or 0)
    now = time.monotonic()
    reason: Optional[str] = None
    if ttl <= 0:
        reason = "caching off"
    elif not _cache.watermark:
        reason = "first pass"
    elif now - _cache.built_at >= ttl:
        reason = f"age {int(now - _cache.built_at)}s"
    else:
        changed = await changed_since(client, _cache.watermark)
        if changed:
            reason = f"{changed} changed"
    if reason is None:
        _cache.reuses += 1
        log.debug("scopes reused (%d mailboxes, built %ds ago)",
                  len(_cache.scopes), int(now - _cache.built_at))
        return _cache.scopes
    started = datetime.now(timezone.utc)
    scopes = await crm.build_scopes(client, settings)
    _cache = ScopeCache(
        scopes=scopes, built_at=now, watermark=_crm_stamp(started - _OVERLAP),
        rebuilds=_cache.rebuilds + 1, reuses=_cache.reuses,
    )
    log.info("scopes rebuilt (%s): %d mailboxes", reason, len(scopes))
    return scopes
