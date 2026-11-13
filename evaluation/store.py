"""The Business Evaluation's application tables (migration 0044).

``evaluation_link`` holds the links emailed to clients and ``evaluation_answer``
the answers saved as the client goes (ruling BE13). A link's token is random
and is never a CRM id (ruling BE12). Both tables are training data on the
sandbox (``core/sandbox_reset.RESET_TABLES``).

One engine per process: the store borrows ``core.store.shared_engine``.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Table, Text, UniqueConstraint, and_, select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB

from core.config import Settings
from core.store import metadata, shared_engine

evaluation_link = Table(
    "evaluation_link",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("token", String(64), nullable=False),
    Column("engagement_id", String(32), nullable=False),
    Column("client_profile_id", String(32), nullable=False),
    Column("round", Integer, nullable=False),
    Column("area_keys", JSONB, nullable=False),
    Column("profile_needed", Boolean, nullable=False, server_default="true"),
    Column("company_name", String(255)),
    Column("consent_at", DateTime(timezone=True)),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("replaced_at", DateTime(timezone=True)),
    UniqueConstraint("token", name="uq_evaluation_link_token"),
)

evaluation_answer = Table(
    "evaluation_answer",
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
    UniqueConstraint("link_id", "survey_key", name="uq_evaluation_answer_link_survey"),
)


#: How long the worker leaves a fresh submission to the request that made it.
WEB_GRACE = timedelta(minutes=2)


def new_token() -> str:
    """32 URL-safe characters, 192 bits: not guessable (ruling BE12)."""
    return secrets.token_urlsafe(24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationStore:
    """Postgres store. ``tests/test_evaluation_store_pg.py`` runs it against a
    real database; every other test uses ``tests/evaluation_fakes.MemoryStore``,
    which keeps the same contract."""

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    # --- links ---------------------------------------------------------------

    async def create_link(self, *, engagement_id: str, client_profile_id: str, round_no: int,
                          area_keys: list[str], profile_needed: bool, company_name: str,
                          created_by: str, days: int,
                          surveys: list[tuple[str, str, Optional[str]]],
                          now: Optional[datetime] = None) -> dict[str, Any]:
        """A new link and one empty answer row per survey it opens
        (``(survey_key, survey_version, crm_record_id)``), in one transaction."""
        now = now or _now()
        link = {
            "id": str(uuid.uuid4()), "token": new_token(), "engagement_id": engagement_id,
            "client_profile_id": client_profile_id, "round": round_no, "area_keys": list(area_keys),
            "profile_needed": profile_needed, "company_name": company_name or None,
            "consent_at": None, "created_by": created_by or None, "created_at": now,
            "expires_at": now + timedelta(days=days), "replaced_at": None,
        }
        rows = [{
            "id": str(uuid.uuid4()), "link_id": link["id"], "survey_key": key,
            "survey_version": version, "answers": {}, "crm_record_id": record_id, "attempts": 0,
        } for key, version, record_id in surveys]
        async with self._engine.begin() as conn:
            await conn.execute(evaluation_link.insert().values(**link))
            if rows:
                await conn.execute(evaluation_answer.insert(), rows)
        return link

    async def link_by_token(self, token: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(evaluation_link).where(evaluation_link.c.token == token))).mappings().first()
        return dict(row) if row else None

    async def link_by_id(self, link_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(evaluation_link).where(evaluation_link.c.id == link_id))).mappings().first()
        return dict(row) if row else None

    async def set_consent(self, link_id: str, at: datetime) -> datetime:
        """Records the first consent only; returns the stored time."""
        async with self._engine.begin() as conn:
            await conn.execute(update(evaluation_link).where(and_(
                evaluation_link.c.id == link_id, evaluation_link.c.consent_at.is_(None)))
                .values(consent_at=at))
            stored = (await conn.execute(select(evaluation_link.c.consent_at).where(
                evaluation_link.c.id == link_id))).scalar_one()
        return stored

    # --- answers -------------------------------------------------------------

    async def answers_for(self, link_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(evaluation_answer).where(
                evaluation_answer.c.link_id == link_id))).mappings().all()
        return [dict(r) for r in rows]

    async def save_answers(self, link_id: str, survey_key: str, answers: dict[str, Any],
                           at: datetime) -> Optional[dict[str, Any]]:
        """Replace a survey's saved answers. None when the survey is not on this
        link or is already submitted: a submitted survey never changes."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(update(evaluation_answer).where(and_(
                evaluation_answer.c.link_id == link_id,
                evaluation_answer.c.survey_key == survey_key,
                evaluation_answer.c.submitted_at.is_(None)))
                .values(answers=answers, updated_at=at)
                .returning(*evaluation_answer.c))).mappings().first()
        return dict(row) if row else None

    async def submit(self, link_id: str, survey_key: str, answers: dict[str, Any],
                     submission_token: str, at: datetime) -> Optional[dict[str, Any]]:
        """Lock a survey's answers as submitted and make it due for delivery at
        once. A survey already submitted is returned unchanged — the
        idempotent answer to a repeated press. None when it is not on the link."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(update(evaluation_answer).where(and_(
                evaluation_answer.c.link_id == link_id,
                evaluation_answer.c.survey_key == survey_key,
                evaluation_answer.c.submitted_at.is_(None)))
                .values(answers=answers, updated_at=at, submitted_at=at,
                        submission_token=submission_token,
                        # The submitting request delivers at once; the worker
                        # takes it only if that request did not finish.
                        next_attempt_at=at + WEB_GRACE)
                .returning(*evaluation_answer.c))).mappings().first()
            if row is None:
                row = (await conn.execute(select(evaluation_answer).where(and_(
                    evaluation_answer.c.link_id == link_id,
                    evaluation_answer.c.survey_key == survey_key)))).mappings().first()
        return dict(row) if row else None

    async def mark_started(self, answer_id: str, at: datetime) -> bool:
        """True the first time only: the CRM's In Progress write is owed once."""
        async with self._engine.begin() as conn:
            result = await conn.execute(update(evaluation_answer).where(and_(
                evaluation_answer.c.id == answer_id,
                evaluation_answer.c.crm_started_at.is_(None))).values(crm_started_at=at))
        return bool(result.rowcount)

    async def mark_delivered(self, answer_id: str, at: datetime) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(evaluation_answer).where(
                evaluation_answer.c.id == answer_id).values(
                delivered_at=at, delivery_error=None, next_attempt_at=None,
                attempts=evaluation_answer.c.attempts + 1))

    async def mark_failed(self, answer_id: str, error: str, retry_at: datetime) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(evaluation_answer).where(
                evaluation_answer.c.id == answer_id).values(
                delivery_error=error[:2000], next_attempt_at=retry_at,
                attempts=evaluation_answer.c.attempts + 1))

    async def due(self, now: datetime, limit: int = 50) -> list[dict[str, Any]]:
        """Submitted, not yet in the CRM, and due."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(evaluation_answer).where(and_(
                evaluation_answer.c.submitted_at.is_not(None),
                evaluation_answer.c.delivered_at.is_(None),
                evaluation_answer.c.next_attempt_at <= now))
                .order_by(evaluation_answer.c.next_attempt_at).limit(limit))).mappings().all()
        return [dict(r) for r in rows]


def make_evaluation_store(settings: Settings) -> Optional[EvaluationStore]:
    """A store when a database is configured, else None (no links at all)."""
    if not settings.store_enabled:
        return None
    return EvaluationStore(settings.database_url)
