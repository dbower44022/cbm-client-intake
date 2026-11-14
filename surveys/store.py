"""The survey engine's application tables (migrations 0044 and 0047).

``survey_link`` holds the links sent to the people who answer, one row per
link: a random token (never a CRM id, ruling BE12), the survey purpose, the
CRM record it points at (entity type and id), the purpose's own data as JSON,
a display snapshot (so opening a link never calls the CRM), when consent was
given, who made it, when it expires and when it was replaced.

``survey_answer`` holds the answers saved as the person goes (ruling BE13),
one row per survey per link, and on submit the time, the submission token
and the progress of the purpose's submit (done, or the last error and when
to retry). ``crm_record_id`` is the CRM record that survey's answers go to,
when the purpose has one; ``crm_started_at`` marks that the purpose's
first-save step has run.

Both tables are training data on the sandbox (``core/sandbox_reset.RESET_TABLES``).
One engine per process: the store borrows ``core.store.shared_engine``.
"""

from __future__ import annotations

import copy
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column, DateTime, Integer, String, Table, Text, UniqueConstraint, and_, select, update,
)
from sqlalchemy.dialects.postgresql import JSONB

from core.config import Settings
from core.store import metadata, shared_engine

survey_link = Table(
    "survey_link",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("token", String(64), nullable=False),
    Column("purpose", String(64), nullable=False),
    Column("entity_type", String(64), nullable=False),
    Column("record_id", String(32), nullable=False),
    Column("data", JSONB, nullable=False),
    Column("display_name", String(255)),
    Column("consent_at", DateTime(timezone=True)),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("replaced_at", DateTime(timezone=True)),
    UniqueConstraint("token", name="uq_survey_link_token"),
)

survey_answer = Table(
    "survey_answer",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("link_id", String(36), nullable=False),
    Column("survey_key", String(64), nullable=False),
    Column("survey_version", String(64), nullable=False),
    Column("answers", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True)),
    Column("submitted_at", DateTime(timezone=True)),
    Column("submission_token", String(64)),
    Column("crm_record_id", String(32)),
    Column("crm_started_at", DateTime(timezone=True)),
    Column("delivered_at", DateTime(timezone=True)),
    Column("delivery_error", Text),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("next_attempt_at", DateTime(timezone=True)),
    UniqueConstraint("link_id", "survey_key", name="uq_survey_answer_link_survey"),
)


#: How long the worker leaves a fresh submission to the request that made it.
WEB_GRACE = timedelta(minutes=2)


def new_token() -> str:
    """32 URL-safe characters, 192 bits: not guessable (ruling BE12)."""
    return secrets.token_urlsafe(24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_link(*, purpose: str, entity_type: str, record_id: str, data: dict[str, Any],
              display_name: Optional[str], consent_at: Optional[datetime], created_by: str,
              days: int, now: datetime) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()), "token": new_token(), "purpose": purpose,
        "entity_type": entity_type, "record_id": record_id, "data": copy.deepcopy(data),
        "display_name": display_name or None, "consent_at": consent_at,
        "created_by": created_by or None, "created_at": now,
        "expires_at": now + timedelta(days=days), "replaced_at": None,
    }


class SurveyStore:
    """Postgres store. ``tests/test_survey_store_pg.py`` runs it against a real
    database; every other test uses ``tests/survey_fakes.MemoryStore``, which
    keeps the same contract."""

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    # --- links ---------------------------------------------------------------

    async def create_link(self, *, purpose: str, entity_type: str, record_id: str,
                          data: dict[str, Any], display_name: str, created_by: str, days: int,
                          surveys: list[tuple[str, str, Optional[str]]],
                          now: Optional[datetime] = None) -> dict[str, Any]:
        """A new link and one empty answer row per survey it opens
        (``(survey_key, survey_version, crm_record_id)``), in one transaction."""
        now = now or _now()
        link = _new_link(purpose=purpose, entity_type=entity_type, record_id=record_id,
                         data=data, display_name=display_name, consent_at=None,
                         created_by=created_by, days=days, now=now)
        rows = [{
            "id": str(uuid.uuid4()), "link_id": link["id"], "survey_key": key,
            "survey_version": version, "answers": {}, "crm_record_id": crm_id, "attempts": 0,
        } for key, version, crm_id in surveys]
        async with self._engine.begin() as conn:
            await conn.execute(survey_link.insert().values(**link))
            if rows:
                await conn.execute(survey_answer.insert(), rows)
        return link

    async def link_by_token(self, token: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(survey_link).where(survey_link.c.token == token))).mappings().first()
        return dict(row) if row else None

    async def link_by_id(self, link_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(survey_link).where(survey_link.c.id == link_id))).mappings().first()
        return dict(row) if row else None

    async def links_for_record(self, purpose: str, entity_type: str,
                               record_id: str) -> list[dict[str, Any]]:
        """Every link one survey purpose made for one CRM record, oldest first."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(survey_link).where(and_(
                survey_link.c.purpose == purpose, survey_link.c.entity_type == entity_type,
                survey_link.c.record_id == record_id))
                .order_by(survey_link.c.created_at))).mappings().all()
        return [dict(r) for r in rows]

    async def end_link(self, link_id: str, at: datetime) -> bool:
        """End a link: it opens nothing from now on. True when it was still
        open-ended; an ended link stays ended."""
        async with self._engine.begin() as conn:
            result = await conn.execute(update(survey_link).where(and_(
                survey_link.c.id == link_id, survey_link.c.replaced_at.is_(None)))
                .values(replaced_at=at))
        return bool(result.rowcount)

    async def replace_link(self, old: dict[str, Any], *, created_by: str, days: int,
                           now: Optional[datetime] = None) -> dict[str, Any]:
        """A new link for the same purpose, record and data that ends the old
        one. The saved answers and the consent move to the new link, so the
        person picks up where they stopped. One transaction."""
        now = now or _now()
        link = _new_link(purpose=old["purpose"], entity_type=old["entity_type"],
                         record_id=old["record_id"], data=old.get("data") or {},
                         display_name=old.get("display_name"), consent_at=old.get("consent_at"),
                         created_by=created_by, days=days, now=now)
        async with self._engine.begin() as conn:
            await conn.execute(survey_link.insert().values(**link))
            await conn.execute(update(survey_answer).where(
                survey_answer.c.link_id == old["id"]).values(link_id=link["id"]))
            await conn.execute(update(survey_link).where(and_(
                survey_link.c.id == old["id"], survey_link.c.replaced_at.is_(None)))
                .values(replaced_at=now))
        return link

    async def set_consent(self, link_id: str, at: datetime) -> datetime:
        """Records the first consent only; returns the stored time."""
        async with self._engine.begin() as conn:
            await conn.execute(update(survey_link).where(and_(
                survey_link.c.id == link_id, survey_link.c.consent_at.is_(None)))
                .values(consent_at=at))
            stored = (await conn.execute(select(survey_link.c.consent_at).where(
                survey_link.c.id == link_id))).scalar_one()
        return stored

    # --- answers -------------------------------------------------------------

    async def answers_for(self, link_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(survey_answer).where(
                survey_answer.c.link_id == link_id))).mappings().all()
        return [dict(r) for r in rows]

    async def save_answers(self, link_id: str, survey_key: str, answers: dict[str, Any],
                           at: datetime) -> Optional[dict[str, Any]]:
        """Replace a survey's saved answers. None when the survey is not on this
        link or is already submitted: a submitted survey never changes."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(update(survey_answer).where(and_(
                survey_answer.c.link_id == link_id,
                survey_answer.c.survey_key == survey_key,
                survey_answer.c.submitted_at.is_(None)))
                .values(answers=answers, updated_at=at)
                .returning(*survey_answer.c))).mappings().first()
        return dict(row) if row else None

    async def submit(self, link_id: str, survey_key: str, answers: dict[str, Any],
                     submission_token: str, at: datetime) -> Optional[dict[str, Any]]:
        """Lock a survey's answers as submitted and make it due at once. A
        survey already submitted is returned unchanged — the idempotent answer
        to a repeated press. None when it is not on the link."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(update(survey_answer).where(and_(
                survey_answer.c.link_id == link_id,
                survey_answer.c.survey_key == survey_key,
                survey_answer.c.submitted_at.is_(None)))
                .values(answers=answers, updated_at=at, submitted_at=at,
                        submission_token=submission_token,
                        # The submitting request delivers at once; the worker
                        # takes it only if that request did not finish.
                        next_attempt_at=at + WEB_GRACE)
                .returning(*survey_answer.c))).mappings().first()
            if row is None:
                row = (await conn.execute(select(survey_answer).where(and_(
                    survey_answer.c.link_id == link_id,
                    survey_answer.c.survey_key == survey_key)))).mappings().first()
        return dict(row) if row else None

    async def mark_started(self, answer_id: str, at: datetime) -> bool:
        """True the first time only: the purpose's first-save step runs once."""
        async with self._engine.begin() as conn:
            result = await conn.execute(update(survey_answer).where(and_(
                survey_answer.c.id == answer_id,
                survey_answer.c.crm_started_at.is_(None))).values(crm_started_at=at))
        return bool(result.rowcount)

    async def mark_delivered(self, answer_id: str, at: datetime) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(survey_answer).where(
                survey_answer.c.id == answer_id).values(
                delivered_at=at, delivery_error=None, next_attempt_at=None,
                attempts=survey_answer.c.attempts + 1))

    async def mark_failed(self, answer_id: str, error: str, retry_at: datetime) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(survey_answer).where(
                survey_answer.c.id == answer_id).values(
                delivery_error=error[:2000], next_attempt_at=retry_at,
                attempts=survey_answer.c.attempts + 1))

    async def due(self, now: datetime, limit: int = 50) -> list[dict[str, Any]]:
        """Submitted, not yet delivered, and due."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(survey_answer).where(and_(
                survey_answer.c.submitted_at.is_not(None),
                survey_answer.c.delivered_at.is_(None),
                survey_answer.c.next_attempt_at <= now))
                .order_by(survey_answer.c.next_attempt_at).limit(limit))).mappings().all()
        return [dict(r) for r in rows]


def make_survey_store(settings: Settings) -> Optional[SurveyStore]:
    """A store when a database is configured, else None (no links at all)."""
    if not settings.store_enabled:
        return None
    return SurveyStore(settings.database_url)
