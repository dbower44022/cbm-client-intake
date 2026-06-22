"""Durable submission store — V2 Phase 0 (see prds/v2/CBM_Intake_V2_Technical_Design.md).

Captures every submission to Postgres *before* any CRM work and enforces
idempotency durably (a unique key on form + token), replacing the in-memory
idempotency dict. Phase 0 still processes synchronously; the background worker
arrives in Phase 1.

The whole module is inert unless ``DATABASE_URL`` is set: ``make_store`` returns
None and the app keeps its V1 behavior, so attaching the database is the only
thing that turns durable capture on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

from .config import Settings

# --- status values (the submission lifecycle, §4 of the technical design) ---
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_RETRY = "retry"
STATUS_COMPLETED = "completed"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_HELD = "held_honeypot"

# Statuses the worker is allowed to claim and deliver.
CLAIMABLE = (STATUS_PENDING, STATUS_RETRY)

metadata = MetaData()

# Phase 0 columns. attempt_count / next_attempt_at / progress are defined now so
# the Phase 1 worker can use them without a second migration; Phase 0 leaves them
# at their defaults.
submission = Table(
    "submission",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("form_slug", String(64), nullable=False),
    Column("submission_token", String(128), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("status", String(32), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("next_attempt_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("progress", JSONB),
    Column("result", JSONB),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("processed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("form_slug", "submission_token", name="uq_submission_form_token"),
)


@dataclass
class Captured:
    """Result of a capture: the durable id, whether it was newly inserted, and —
    for an idempotent replay — the prior status and final result (if completed)."""

    id: str
    is_new: bool
    status: str
    result: Optional[dict[str, Any]]


@dataclass
class Claimed:
    """A submission claimed by the worker for delivery (V2 Phase 1)."""

    id: str
    form_slug: str
    submission_token: str
    payload: dict[str, Any]
    progress: Optional[dict[str, Any]]
    attempt_count: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SubmissionStore(Protocol):
    async def create_all(self) -> None: ...
    async def capture(
        self, form_slug: str, submission_token: str, payload: dict[str, Any], *, status: str
    ) -> Captured: ...
    async def mark_completed(self, submission_id: str, result: dict[str, Any]) -> None: ...
    async def mark_failed(self, submission_id: str, *, status: str, error: str) -> None: ...
    # Phase 1 (worker) operations:
    async def claim_batch(self, limit: int) -> list[Claimed]: ...
    async def mark_retry(
        self, submission_id: str, *, attempt_count: int, next_attempt_at: datetime, error: str
    ) -> None: ...
    async def save_progress(self, submission_id: str, progress: dict[str, Any]) -> None: ...
    # Phase 2 (ops view) operations:
    async def list_submissions(
        self, *, status: Optional[str] = None, form: Optional[str] = None, limit: int = 200
    ) -> list[dict[str, Any]]: ...
    async def get_submission(self, submission_id: str) -> Optional[dict[str, Any]]: ...
    async def counts_by_status(self) -> dict[str, int]: ...
    async def redrive(self, submission_id: str) -> bool: ...
    async def dispose(self) -> None: ...


def _normalize_url(database_url: str) -> str:
    """Coerce a libpq-style URL to SQLAlchemy's async (asyncpg) driver form."""
    if database_url.startswith("postgres://"):
        return "postgresql+asyncpg://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        return "postgresql+asyncpg://" + database_url[len("postgresql://"):]
    return database_url


class PostgresStore:
    """Postgres-backed :class:`SubmissionStore`."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(_normalize_url(database_url), pool_pre_ping=True)

    async def create_all(self) -> None:
        """Create the table if absent. Phase-0 convenience; Phase 1 moves schema
        management to Alembic (the migration already mirrors this table)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def capture(
        self, form_slug: str, submission_token: str, payload: dict[str, Any], *, status: str
    ) -> Captured:
        now = _now()
        stmt = (
            pg_insert(submission)
            .values(
                id=str(uuid.uuid4()),
                form_slug=form_slug,
                submission_token=submission_token,
                payload=payload,
                status=status,
                received_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["form_slug", "submission_token"])
            .returning(submission.c.id)
        )
        async with self._engine.begin() as conn:
            inserted = (await conn.execute(stmt)).first()
            if inserted is not None:
                return Captured(id=inserted[0], is_new=True, status=status, result=None)
            # Conflict: a row already exists for this (form, token) — idempotent replay.
            existing = (
                await conn.execute(
                    select(submission.c.id, submission.c.status, submission.c.result).where(
                        submission.c.form_slug == form_slug,
                        submission.c.submission_token == submission_token,
                    )
                )
            ).first()
            return Captured(id=existing[0], is_new=False, status=existing[1], result=existing[2])

    async def mark_completed(self, submission_id: str, result: dict[str, Any]) -> None:
        now = _now()
        async with self._engine.begin() as conn:
            await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(status=STATUS_COMPLETED, result=result, processed_at=now, updated_at=now)
            )

    async def mark_failed(self, submission_id: str, *, status: str, error: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(status=status, last_error=(error or "")[:2000], updated_at=_now())
            )

    async def claim_batch(self, limit: int) -> list[Claimed]:
        """Atomically claim up to ``limit`` due submissions for delivery.

        ``FOR UPDATE SKIP LOCKED`` makes concurrent workers safe — each row is
        handed to exactly one worker. Claimed rows move to ``processing``.
        """
        now = _now()
        due = (
            select(submission.c.id)
            .where(submission.c.status.in_(CLAIMABLE))
            .where(
                (submission.c.next_attempt_at.is_(None))
                | (submission.c.next_attempt_at <= now)
            )
            .order_by(submission.c.received_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        stmt = (
            update(submission)
            .where(submission.c.id.in_(due.scalar_subquery()))
            .values(status=STATUS_PROCESSING, updated_at=now)
            .returning(
                submission.c.id,
                submission.c.form_slug,
                submission.c.submission_token,
                submission.c.payload,
                submission.c.progress,
                submission.c.attempt_count,
            )
        )
        async with self._engine.begin() as conn:
            rows = (await conn.execute(stmt)).all()
        return [
            Claimed(
                id=r[0], form_slug=r[1], submission_token=r[2],
                payload=r[3], progress=r[4], attempt_count=r[5],
            )
            for r in rows
        ]

    async def mark_retry(
        self, submission_id: str, *, attempt_count: int, next_attempt_at: datetime, error: str
    ) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(
                    status=STATUS_RETRY,
                    attempt_count=attempt_count,
                    next_attempt_at=next_attempt_at,
                    last_error=(error or "")[:2000],
                    updated_at=_now(),
                )
            )

    async def save_progress(self, submission_id: str, progress: dict[str, Any]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(progress=progress, updated_at=_now())
            )

    async def list_submissions(
        self, *, status: Optional[str] = None, form: Optional[str] = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        query = (
            select(
                submission.c.id,
                submission.c.form_slug,
                submission.c.submission_token,
                submission.c.status,
                submission.c.attempt_count,
                submission.c.last_error,
                submission.c.payload["email"].astext.label("email"),
                submission.c.received_at,
                submission.c.processed_at,
                submission.c.next_attempt_at,
            )
            .order_by(submission.c.received_at.desc())
            .limit(limit)
        )
        if status:
            query = query.where(submission.c.status == status)
        if form:
            query = query.where(submission.c.form_slug == form)
        async with self._engine.begin() as conn:
            rows = (await conn.execute(query)).mappings().all()
        return [dict(r) for r in rows]

    async def get_submission(self, submission_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(submission).where(submission.c.id == submission_id)
                )
            ).mappings().first()
        return dict(row) if row else None

    async def counts_by_status(self) -> dict[str, int]:
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(submission.c.status, func.count().label("n")).group_by(
                        submission.c.status
                    )
                )
            ).all()
        return {r[0]: r[1] for r in rows}

    async def redrive(self, submission_id: str) -> bool:
        """Re-queue a submission: back to pending, due now, fresh attempt budget.
        The worker re-runs it from saved ``progress`` (no duplication)."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(
                    status=STATUS_PENDING,
                    next_attempt_at=None,
                    attempt_count=0,
                    updated_at=_now(),
                )
            )
        return result.rowcount > 0

    async def dispose(self) -> None:
        await self._engine.dispose()


def make_store(settings: Settings) -> Optional[SubmissionStore]:
    """A store when a database is configured, else None (V1 in-memory behavior)."""
    if not settings.store_enabled:
        return None
    return PostgresStore(settings.database_url)
