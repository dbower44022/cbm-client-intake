"""What the feedback surveys remember in the application database (decision 5,
A, 11-20-26; rulings BE30, BE32, BE33).

``feedback_send`` holds one row per moment per person, keyed by ``send_key``
(for example ``closed:<engagement id>`` or ``event:<event id>:<registration
id>``). The unique key is what makes "never twice" a database guarantee, even
when two worker passes overlap. The row's ``email`` serves the quiet period,
and a skip is a row too, so every skip is recorded (BE33). Outcomes:

* ``pending``: claimed, being sent now;
* ``sent``: the link was made and sent (or handed to the mentor's composer);
* ``skipped``: not sent, ``reason`` says why (the quiet period, an opted-out
  address, no address, the closing survey sent instead);
* ``failed``: the send failed; the next sweep tries again, up to
  ``MAX_ATTEMPTS`` in all, then the row stays failed and is logged.

``feedback_alert`` holds one row per Survey Response whose follow-up alert was
sent, so a retried submit never alerts twice (decision 4).

Training data on the sandbox (``core/sandbox_reset.RESET_TABLES``). One store
per process; it borrows the shared pool. In tests the in-memory twin is
``tests/feedback_fakes.MemoryFeedbackStore``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import (Column, DateTime, Integer, String, Table, Text, UniqueConstraint, and_,
                        or_, select, update)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import metadata, shared_engine

PENDING, SENT, SKIPPED, FAILED = "pending", "sent", "skipped", "failed"
#: Sends tried in all before a failed row is left failed.
MAX_ATTEMPTS = 3
#: A row left pending this long (a worker that died mid-send) may be claimed again.
STALE_PENDING = timedelta(minutes=30)

feedback_send = Table(
    "feedback_send",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("send_key", String(160), nullable=False),
    Column("moment", String(32), nullable=False),
    Column("survey_key", String(64), nullable=False),
    Column("entity_type", String(64), nullable=False),
    Column("record_id", String(32), nullable=False),
    Column("email", String(255), nullable=False, server_default=""),
    Column("contact_id", String(32)),
    Column("link_id", String(36)),
    Column("outcome", String(32), nullable=False),
    Column("reason", Text),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("send_key", name="uq_feedback_send_key"),
)

feedback_alert = Table(
    "feedback_alert",
    metadata,
    Column("response_id", String(32), primary_key=True),
    Column("outcome", String(32), nullable=False),
    Column("reason", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def norm_email(email: str) -> str:
    """The quiet period counts per address: compared lower-case and trimmed."""
    return (email or "").strip().lower()


class FeedbackStore:
    """Postgres store. ``tests/test_feedback_store_pg.py`` runs it against a
    real database when one is available."""

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def claim(self, send_key: str, *, moment: str, survey_key: str, entity_type: str,
                    record_id: str, email: str, contact_id: Optional[str] = None,
                    created_by: str = "", now: Optional[datetime] = None) -> bool:
        """Claim one moment for one person. True when this caller should send:
        a new key, a failed one with tries left, or one left pending by a
        worker that died. False when it was already sent, skipped, failed for
        good or is being sent now."""
        now = now or _now()
        row = {"id": str(uuid.uuid4()), "send_key": send_key, "moment": moment,
               "survey_key": survey_key, "entity_type": entity_type, "record_id": record_id,
               "email": norm_email(email), "contact_id": contact_id or None,
               "outcome": PENDING, "attempts": 1, "created_by": created_by or None,
               "created_at": now, "updated_at": now}
        async with self._engine.begin() as conn:
            got = (await conn.execute(
                pg_insert(feedback_send).values(**row)
                .on_conflict_do_nothing(constraint="uq_feedback_send_key")
                .returning(feedback_send.c.id))).first()
            if got is not None:
                return True
            again = (await conn.execute(
                update(feedback_send)
                .where(and_(feedback_send.c.send_key == send_key, or_(
                    and_(feedback_send.c.outcome == FAILED,
                         feedback_send.c.attempts < MAX_ATTEMPTS),
                    and_(feedback_send.c.outcome == PENDING,
                         feedback_send.c.updated_at < now - STALE_PENDING))))
                .values(outcome=PENDING, attempts=feedback_send.c.attempts + 1,
                        email=norm_email(email), updated_at=now)
                .returning(feedback_send.c.id))).first()
        return again is not None

    async def finish(self, send_key: str, outcome: str, *, link_id: Optional[str] = None,
                     reason: Optional[str] = None, now: Optional[datetime] = None) -> None:
        values: dict[str, Any] = {"outcome": outcome, "reason": reason, "updated_at": now or _now()}
        if link_id:
            values["link_id"] = link_id
        async with self._engine.begin() as conn:
            await conn.execute(update(feedback_send)
                               .where(feedback_send.c.send_key == send_key).values(**values))

    async def recently_sent(self, email: str, since: datetime) -> bool:
        """True when any feedback survey was sent to this address since then."""
        address = norm_email(email)
        if not address:
            return False
        async with self._engine.begin() as conn:
            got = (await conn.execute(select(feedback_send.c.id).where(and_(
                feedback_send.c.email == address, feedback_send.c.outcome == SENT,
                feedback_send.c.updated_at >= since)).limit(1))).first()
        return got is not None

    async def get(self, send_key: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            got = (await conn.execute(select(feedback_send)
                                      .where(feedback_send.c.send_key == send_key))).mappings().first()
        return dict(got) if got else None

    async def claim_alert(self, response_id: str, now: Optional[datetime] = None) -> bool:
        """True when this caller should send the follow-up alert for a
        response: never sent before, or a failed one."""
        now = now or _now()
        async with self._engine.begin() as conn:
            got = (await conn.execute(
                pg_insert(feedback_alert).values(response_id=response_id, outcome=PENDING,
                                                 created_at=now, updated_at=now)
                .on_conflict_do_nothing(index_elements=["response_id"])
                .returning(feedback_alert.c.response_id))).first()
            if got is not None:
                return True
            again = (await conn.execute(
                update(feedback_alert)
                .where(and_(feedback_alert.c.response_id == response_id,
                            feedback_alert.c.outcome == FAILED))
                .values(outcome=PENDING, updated_at=now)
                .returning(feedback_alert.c.response_id))).first()
        return again is not None

    async def finish_alert(self, response_id: str, outcome: str, reason: Optional[str] = None,
                           now: Optional[datetime] = None) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(feedback_alert)
                               .where(feedback_alert.c.response_id == response_id)
                               .values(outcome=outcome, reason=reason, updated_at=now or _now()))

    async def failed_alerts(self) -> list[str]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(feedback_alert.c.response_id)
                                       .where(feedback_alert.c.outcome == FAILED))).all()
        return [r[0] for r in rows]


def make_feedback_store(settings: Settings) -> Optional[FeedbackStore]:
    """A store when a database is configured, else None (nothing is sent)."""
    if not settings.store_enabled:
        return None
    return FeedbackStore(settings.database_url)
