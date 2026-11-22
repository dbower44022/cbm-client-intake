"""What the training courses keep in the application database
(prds/training-app-plan.md § 6, TR9). People are keyed by their CRM user id.

- ``training_progress``: one row per step ticked or checkpoint answered, by
  user, course and item; saved as the trainee goes (decision 6).
- ``training_completion``: one row per user, course and revision, with the
  checkpoint answers copied in, so a later edit of the course never changes
  what was recorded.
- ``training_dismissal``: a reminder dismissed until the next significant
  revision (phase 2): one row per user, course and N.
- ``training_onboarding_write``: the TR10 writes and their outcome (phase 4).

Real people's records, so the sandbox reset keeps them
(``core/sandbox_reset.KEEP_TABLES``). One store per process; it borrows the
shared pool. In tests the in-memory twin is ``tests/courses_fakes.MemoryCourseStore``.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (Column, DateTime, Index, Integer, String, Table, Text, UniqueConstraint,
                        and_, delete, select)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import metadata, shared_engine

training_progress = Table(
    "training_progress",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(32), nullable=False),
    Column("course_id", String(64), nullable=False),
    Column("revision", String(16), nullable=False),
    Column("item_key", String(32), nullable=False),
    Column("done_at", DateTime(timezone=True), nullable=False),
    Column("answer", Text),
    UniqueConstraint("user_id", "course_id", "item_key", name="uq_training_progress_item"),
)

training_completion = Table(
    "training_completion",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(32), nullable=False),
    Column("user_name", String(255), nullable=False, server_default=""),
    Column("course_id", String(64), nullable=False),
    Column("revision", String(16), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    Column("answers", Text, nullable=False, server_default="{}"),
    UniqueConstraint("user_id", "course_id", "revision", name="uq_training_completion"),
    Index("ix_training_completion_course", "course_id", "completed_at"),
)

training_dismissal = Table(
    "training_dismissal",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(32), nullable=False),
    Column("course_id", String(64), nullable=False),
    Column("major", Integer, nullable=False),
    Column("dismissed_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("user_id", "course_id", "major", name="uq_training_dismissal"),
)

training_onboarding_write = Table(
    "training_onboarding_write",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(32), nullable=False),
    Column("mentor_profile_id", String(32), nullable=False),
    Column("written_at", DateTime(timezone=True), nullable=False),
    Column("outcome", Text, nullable=False),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _completion(r: Any) -> dict[str, Any]:
    d = dict(r)
    try:
        d["answers"] = json.loads(d.get("answers") or "{}")
    except ValueError:
        d["answers"] = {}
    return d


class CourseStore:
    """Postgres store."""

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def progress(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(training_progress).where(and_(
                training_progress.c.user_id == user_id,
                training_progress.c.course_id == course_id)))).mappings().all()
        return [dict(r) for r in rows]

    async def progress_counts(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """Every course's progress rows for one person, by course."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(training_progress).where(
                training_progress.c.user_id == user_id))).mappings().all()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r["course_id"], []).append(dict(r))
        return out

    async def save_item(self, user_id: str, course_id: str, revision: str, item_key: str,
                        answer: Optional[str] = None, now: Optional[datetime] = None
                        ) -> dict[str, Any]:
        """Tick a step (``answer`` None) or save a checkpoint answer; a second
        save of the same item replaces the first."""
        now = now or _now()
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "course_id": course_id,
               "revision": revision, "item_key": item_key, "done_at": now, "answer": answer}
        async with self._engine.begin() as conn:
            got = (await conn.execute(
                pg_insert(training_progress).values(**row)
                .on_conflict_do_update(constraint="uq_training_progress_item",
                                       set_={"revision": revision, "done_at": now,
                                             "answer": answer})
                .returning(training_progress))).mappings().first()
        return dict(got)

    async def clear_item(self, user_id: str, course_id: str, item_key: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(delete(training_progress).where(and_(
                training_progress.c.user_id == user_id,
                training_progress.c.course_id == course_id,
                training_progress.c.item_key == item_key)))

    async def clear_items(self, user_id: str, course_id: str, item_keys: list[str]) -> None:
        if not item_keys:
            return
        async with self._engine.begin() as conn:
            await conn.execute(delete(training_progress).where(and_(
                training_progress.c.user_id == user_id,
                training_progress.c.course_id == course_id,
                training_progress.c.item_key.in_(item_keys))))

    async def complete(self, user_id: str, user_name: str, course_id: str, revision: str,
                       answers: dict[str, Any], now: Optional[datetime] = None
                       ) -> tuple[dict[str, Any], bool]:
        """Record the completion; ``(row, created)``. A second press at the same
        revision returns the first row and False."""
        now = now or _now()
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "user_name": user_name or "",
               "course_id": course_id, "revision": revision, "completed_at": now,
               "answers": json.dumps(answers)}
        async with self._engine.begin() as conn:
            got = (await conn.execute(
                pg_insert(training_completion).values(**row)
                .on_conflict_do_nothing(constraint="uq_training_completion")
                .returning(training_completion))).mappings().first()
            if got is not None:
                return _completion(got), True
            old = (await conn.execute(select(training_completion).where(and_(
                training_completion.c.user_id == user_id,
                training_completion.c.course_id == course_id,
                training_completion.c.revision == revision)))).mappings().first()
        return _completion(old), False

    async def completions(self, user_id: str) -> list[dict[str, Any]]:
        """Every completion of one person, newest first."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(training_completion).where(
                training_completion.c.user_id == user_id)
                .order_by(training_completion.c.completed_at.desc()))).mappings().all()
        return [_completion(r) for r in rows]

    async def dismissals(self, user_id: str) -> list[dict[str, Any]]:
        """Every reminder one person dismissed."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(training_dismissal).where(
                training_dismissal.c.user_id == user_id))).mappings().all()
        return [dict(r) for r in rows]

    async def dismiss(self, user_id: str, course_id: str, major: int,
                      now: Optional[datetime] = None) -> dict[str, Any]:
        """Dismiss the reminder at significant revision ``major``; a second
        dismissal at the same N keeps the first."""
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "course_id": course_id,
               "major": major, "dismissed_at": now or _now()}
        async with self._engine.begin() as conn:
            got = (await conn.execute(
                pg_insert(training_dismissal).values(**row)
                .on_conflict_do_nothing(constraint="uq_training_dismissal")
                .returning(training_dismissal))).mappings().first()
            if got is None:
                got = (await conn.execute(select(training_dismissal).where(and_(
                    training_dismissal.c.user_id == user_id,
                    training_dismissal.c.course_id == course_id,
                    training_dismissal.c.major == major)))).mappings().first()
        return dict(got)

    async def course_records(self, course_id: str) -> dict[str, list[dict[str, Any]]]:
        """Everyone's progress, completions and dismissals in one course: the
        training report's read (TR5, phase 3)."""
        async with self._engine.begin() as conn:
            progress = (await conn.execute(select(training_progress).where(
                training_progress.c.course_id == course_id))).mappings().all()
            done = (await conn.execute(select(training_completion).where(
                training_completion.c.course_id == course_id)
                .order_by(training_completion.c.completed_at.desc()))).mappings().all()
            dismissed = (await conn.execute(select(training_dismissal).where(
                training_dismissal.c.course_id == course_id))).mappings().all()
        return {"progress": [dict(r) for r in progress],
                "completions": [_completion(r) for r in done],
                "dismissals": [dict(r) for r in dismissed]}


_stores: dict[str, CourseStore] = {}
#: A test sets this to an in-memory store.
_override: Optional[Any] = None


def course_store(settings: Settings):
    """One store per process when a database is configured, else None."""
    if _override is not None:
        return _override
    if not settings.store_enabled:
        return None
    store = _stores.get(settings.database_url)
    if store is None:
        store = _stores[settings.database_url] = CourseStore(settings.database_url)
    return store


def use(store: Optional[Any]) -> None:
    """Tests: serve ``store`` in place of the Postgres one (None restores)."""
    global _override
    _override = store
