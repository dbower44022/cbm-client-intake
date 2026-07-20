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

import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    func,
    or_,
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
# An inbound info@ email captured by the worker's mailbox poller, waiting for
# staff triage in /ops (v0.110.0). Approve = redrive (→ pending, the worker
# delivers it through the info-email orchestrator, creating the CRM records);
# Discard = spam, no CRM residue. Never claimed by the worker while held.
STATUS_HELD_REVIEW = "held_review"
# Terminal, staff-set: a stuck submission resolved manually in /ops (e.g. a bad
# payload that can't be re-driven). Kept in the table for audit; excluded from
# the backlog / needs-attention alerting and never claimed by the worker.
STATUS_DISCARDED = "discarded"

# Statuses the worker is allowed to claim and deliver.
CLAIMABLE = (STATUS_PENDING, STATUS_RETRY)

# How many of the most recent completions feed metrics()'s windowed latency.
RECENT_LATENCY_WINDOW = 50

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
    # Lease expiry for a claimed ("processing") row. NULL on a row that was never
    # leased (pre-lease rows, or rows in any other status). The worker reclaims a
    # processing row whose lease has expired, so a crash can't strand it forever.
    Column("locked_until", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("progress", JSONB),
    Column("result", JSONB),
    # Who last acted on this row from /ops (redrive/discard) — the audit answer
    # to "who discarded this submission?" (P1-11, reliability review 2026-07-17).
    Column("acted_by", String(128)),
    # Staff triage notes on this submission, edited in /ops (Submission Admin
    # rebuild, 2026-07-19). Free text, staff-only — never delivered to the CRM.
    Column("notes", Text),
    # Staff resolution marker (independent of delivery status): "is anyone
    # still waiting on us?" NULL = open. The /ops grid defaults to open rows.
    Column("resolved_at", DateTime(timezone=True)),
    Column("resolved_by", String(128)),
    # Gmail thread ids anchored to this submission (JSON list, v0.110.0): the
    # threads staff started from /ops (recorded after each send) and — for an
    # email-originated submission — the inbound thread itself (in the payload
    # as gmail_thread_id AND mirrored here at capture). The conversation view
    # shows exactly these threads, never an address search.
    Column("thread_ids", JSONB),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("processed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("form_slug", "submission_token", name="uq_submission_form_token"),
    # Supports the worker's claim query (status + due/lease scan, oldest first).
    Index("ix_submission_claim", "status", "next_attempt_at", "received_at"),
)

# Worker liveness (P1-6, reliability review 2026-07-17): the worker upserts the
# single row each loop iteration; /healthz reports the beat's age so an external
# uptime check can see a dead/wedged worker — the in-worker alerter can't alert
# on its own death. One row, fixed key.
WORKER_HEARTBEAT_ID = "worker"

worker_heartbeat = Table(
    "worker_heartbeat",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("beat_at", DateTime(timezone=True), nullable=False),
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
    async def claim_batch(self, limit: int, *, lease_seconds: int = 900) -> list[Claimed]: ...
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
    async def redrive(self, submission_id: str, *, acted_by: Optional[str] = None) -> bool: ...
    async def discard(self, submission_id: str, *, acted_by: Optional[str] = None) -> bool: ...
    async def set_notes(
        self, submission_id: str, notes: str, *, acted_by: Optional[str] = None
    ) -> bool: ...
    async def set_resolved(
        self, submission_id: str, resolved: bool, *, acted_by: Optional[str] = None
    ) -> bool: ...
    # Gmail thread anchoring (v0.110.0):
    async def add_thread_id(self, submission_id: str, thread_id: str) -> bool: ...
    async def existing_tokens(self, form_slug: str, tokens: list[str]) -> set[str]: ...
    async def known_gmail_threads(self, thread_ids: list[str]) -> set[str]: ...
    async def metrics(self) -> dict[str, Any]: ...
    async def ping(self) -> bool: ...
    # Worker liveness (P1-6):
    async def heartbeat(self) -> None: ...
    async def dispose(self) -> None: ...


def _normalize_url(database_url: str) -> str:
    """SQLAlchemy async (asyncpg) URL with libpq-only query params removed.

    asyncpg rejects ``sslmode``/``channel_binding`` (they are psycopg/libpq
    options, and DigitalOcean's managed URL includes ``?sslmode=require``); SSL is
    configured via ``connect_args`` in :func:`make_async_engine` instead.
    """
    url = database_url
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    parts = urlsplit(url)
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if k not in ("sslmode", "channel_binding")
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def _connect_args(database_url: str) -> dict:
    """Enable an encrypted connection (no CA verification — like sslmode=require)
    when the URL asked for SSL, as DigitalOcean managed Postgres does."""
    sslmode = dict(parse_qsl(urlsplit(database_url).query)).get("sslmode")
    if sslmode in (None, "disable", "allow"):
        return {}
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return {"ssl": context}


def make_async_engine(database_url: str, **kwargs):
    """Async engine for a libpq-style URL, handling driver + SSL coercion.
    Shared by the store and Alembic so both connect identically."""
    return create_async_engine(
        _normalize_url(database_url),
        pool_pre_ping=True,
        connect_args=_connect_args(database_url),
        **kwargs,
    )


class PostgresStore:
    """Postgres-backed :class:`SubmissionStore`."""

    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

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

    async def claim_batch(self, limit: int, *, lease_seconds: int = 900) -> list[Claimed]:
        """Atomically claim up to ``limit`` due submissions for delivery.

        ``FOR UPDATE SKIP LOCKED`` makes concurrent workers safe — each row is
        handed to exactly one worker. Claimed rows move to ``processing`` with a
        lease (``locked_until``).

        A claim picks up two kinds of rows: (a) pending/retry rows that are due,
        and (b) ``processing`` rows whose lease has expired (or is NULL) — these
        were stranded by a worker that died mid-delivery, and reclaiming them is
        safe because delivery is resumable.
        """
        now = _now()
        lease_until = now + timedelta(seconds=lease_seconds)
        due = (
            select(submission.c.id)
            .where(
                or_(
                    and_(
                        submission.c.status.in_(CLAIMABLE),
                        or_(
                            submission.c.next_attempt_at.is_(None),
                            submission.c.next_attempt_at <= now,
                        ),
                    ),
                    and_(
                        submission.c.status == STATUS_PROCESSING,
                        or_(
                            submission.c.locked_until.is_(None),
                            submission.c.locked_until <= now,
                        ),
                    ),
                )
            )
            .order_by(submission.c.received_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        stmt = (
            update(submission)
            .where(submission.c.id.in_(due.scalar_subquery()))
            .values(status=STATUS_PROCESSING, locked_until=lease_until, updated_at=now)
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
                submission.c.notes,
                submission.c.resolved_at,
                submission.c.resolved_by,
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

    async def redrive(self, submission_id: str, *, acted_by: Optional[str] = None) -> bool:
        """Re-queue a submission: back to pending, due now, fresh attempt budget.
        The worker re-runs it from saved ``progress`` (no duplication).

        Guarded (P1-11): only ``needs_attention`` / ``retry`` /
        ``held_honeypot`` / ``held_review`` / ``discarded`` rows may be
        re-driven (held_honeypot = the honeypot false-positive recovery;
        held_review = staff APPROVING an inbound info@ email — delivery
        creates the CRM records; discarded = undoing a mistaken discard,
        which the /ops UI has offered since v0.106.0 but this guard used to
        refuse). Redriving a ``completed`` row would re-deliver (duplicate
        Normal audit record + re-run side effects); redriving a
        ``processing`` row would race the live worker's ``save_progress``
        into duplicate creates.
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .where(
                    submission.c.status.in_(
                        (STATUS_NEEDS_ATTENTION, STATUS_RETRY, STATUS_HELD,
                         STATUS_HELD_REVIEW, STATUS_DISCARDED)
                    )
                )
                .values(
                    status=STATUS_PENDING,
                    next_attempt_at=None,
                    attempt_count=0,
                    acted_by=acted_by,
                    updated_at=_now(),
                )
            )
        return result.rowcount > 0

    async def set_notes(
        self, submission_id: str, notes: str, *, acted_by: Optional[str] = None
    ) -> bool:
        """Save the staff triage notes for a submission (Submission Admin)."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(notes=notes, acted_by=acted_by, updated_at=_now())
            )
        return result.rowcount > 0

    async def set_resolved(
        self, submission_id: str, resolved: bool, *, acted_by: Optional[str] = None
    ) -> bool:
        """Mark a submission resolved (or reopen it). A staff workflow marker,
        independent of the delivery status — the /ops grid defaults to open."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(
                    resolved_at=_now() if resolved else None,
                    resolved_by=acted_by if resolved else None,
                    updated_at=_now(),
                )
            )
        return result.rowcount > 0

    async def add_thread_id(self, submission_id: str, thread_id: str) -> bool:
        """Anchor a Gmail thread to a submission (recorded after each /ops send;
        also at inbound capture). Appends to the ``thread_ids`` JSON list,
        skipping duplicates."""
        if not thread_id:
            return False
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(submission.c.thread_ids).where(submission.c.id == submission_id)
                )
            ).first()
            if row is None:
                return False
            threads = list(row[0] or [])
            if thread_id in threads:
                return True
            threads.append(thread_id)
            await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .values(thread_ids=threads, updated_at=_now())
            )
        return True

    async def existing_tokens(self, form_slug: str, tokens: list[str]) -> set[str]:
        """Which of these submission tokens already exist for the form — the
        inbound poller's cheap pre-check before fetching thread content."""
        if not tokens:
            return set()
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(submission.c.submission_token).where(
                        submission.c.form_slug == form_slug,
                        submission.c.submission_token.in_(tokens),
                    )
                )
            ).all()
        return {r[0] for r in rows}

    async def known_gmail_threads(self, thread_ids: list[str]) -> set[str]:
        """Which of these Gmail thread ids are already anchored to ANY
        submission (``thread_ids`` membership). Keeps the inbound poller from
        capturing a submitter's REPLY to a conversation staff started from a
        form submission as if it were a brand-new request."""
        if not thread_ids:
            return set()
        conds = [submission.c.thread_ids.contains([t]) for t in thread_ids]
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(submission.c.thread_ids).where(
                        submission.c.thread_ids.isnot(None), or_(*conds)
                    )
                )
            ).all()
        known: set[str] = set()
        wanted = set(thread_ids)
        for (threads,) in rows:
            known.update(t for t in (threads or []) if t in wanted)
        return known

    async def discard(self, submission_id: str, *, acted_by: Optional[str] = None) -> bool:
        """Resolve a stuck submission manually: move it to the terminal
        ``discarded`` status so it leaves the worker queue and stops counting
        toward the needs-attention alert. Never touches a completed delivery.
        The row (payload, error, progress) is kept for audit."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(submission)
                .where(submission.c.id == submission_id)
                .where(submission.c.status != STATUS_COMPLETED)
                .values(
                    status=STATUS_DISCARDED,
                    next_attempt_at=None,
                    locked_until=None,
                    acted_by=acted_by,
                    updated_at=_now(),
                )
            )
        return result.rowcount > 0

    async def metrics(self) -> dict[str, Any]:
        """Delivery health: counts, backlog, oldest-pending age, avg latency,
        stranded (lease-expired ``processing``) rows, worker-heartbeat age."""
        now = _now()
        async with self._engine.begin() as conn:
            counts = {
                r[0]: r[1]
                for r in (
                    await conn.execute(
                        select(submission.c.status, func.count()).group_by(submission.c.status)
                    )
                ).all()
            }
            oldest = (
                await conn.execute(
                    select(func.min(submission.c.received_at)).where(
                        submission.c.status.in_(CLAIMABLE)
                    )
                )
            ).scalar()
            avg_latency = (
                await conn.execute(
                    select(
                        func.avg(
                            func.extract(
                                "epoch", submission.c.processed_at - submission.c.received_at
                            )
                        )
                    ).where(submission.c.processed_at.isnot(None))
                )
            ).scalar()
            # Windowed latency (Phase 6, reliability review 2026-07-17): the
            # lifetime average above can never show THIS week's regression —
            # this one averages only the most recent completions.
            recent = (
                select(
                    func.extract(
                        "epoch", submission.c.processed_at - submission.c.received_at
                    ).label("latency")
                )
                .where(submission.c.processed_at.isnot(None))
                .order_by(submission.c.processed_at.desc())
                .limit(RECENT_LATENCY_WINDOW)
                .subquery()
            )
            recent_latency = (
                await conn.execute(select(func.avg(recent.c.latency)))
            ).scalar()
            # A ``processing`` row whose lease has expired = a worker died (or
            # crash-looped) mid-delivery. It will be reclaimed by the next claim
            # pass — but with no live worker it lingers invisibly unless counted
            # here (P1-6; also the visibility gap behind the P0-1 crash loop).
            stranded = (
                await conn.execute(
                    select(func.count())
                    .select_from(submission)
                    .where(submission.c.status == STATUS_PROCESSING)
                    .where(submission.c.locked_until.isnot(None))
                    .where(submission.c.locked_until < now)
                )
            ).scalar()
            beat = (
                await conn.execute(
                    select(worker_heartbeat.c.beat_at).where(
                        worker_heartbeat.c.id == WORKER_HEARTBEAT_ID
                    )
                )
            ).scalar()
        oldest_age = (now - oldest).total_seconds() if oldest else None
        return {
            "counts": counts,
            "needsAttention": counts.get(STATUS_NEEDS_ATTENTION, 0),
            "backlog": counts.get(STATUS_PENDING, 0) + counts.get(STATUS_RETRY, 0),
            "oldestPendingAgeSeconds": oldest_age,
            "avgLatencySeconds": float(avg_latency) if avg_latency is not None else None,
            # Average over the last RECENT_LATENCY_WINDOW completions only.
            "recentAvgLatencySeconds": (
                float(recent_latency) if recent_latency is not None else None
            ),
            "stranded": int(stranded or 0),
            # None = the worker has never stamped (fresh env, or pre-0.78 schema).
            "workerHeartbeatAgeSeconds": (
                (now - beat).total_seconds() if beat is not None else None
            ),
        }

    async def heartbeat(self) -> None:
        """Stamp worker liveness (one fixed row, upserted each loop iteration)."""
        async with self._engine.begin() as conn:
            stmt = pg_insert(worker_heartbeat).values(
                id=WORKER_HEARTBEAT_ID, beat_at=_now()
            )
            await conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[worker_heartbeat.c.id],
                    set_={"beat_at": stmt.excluded.beat_at},
                )
            )

    async def ping(self) -> bool:
        """Liveness check for the database connection (``/healthz``)."""
        async with self._engine.connect() as conn:
            await conn.execute(select(1))
        return True

    async def dispose(self) -> None:
        await self._engine.dispose()


def make_store(settings: Settings) -> Optional[SubmissionStore]:
    """A store when a database is configured, else None (V1 in-memory behavior)."""
    if not settings.store_enabled:
        return None
    return PostgresStore(settings.database_url)
