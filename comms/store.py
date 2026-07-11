"""Postgres state for the Gmail sync: per-mailbox cursors + curation overrides.

Tables are created by Alembic migration ``0004_comms_sync`` (``create_all``
mirrors them for local dev, like :mod:`core.store`). The overrides are
record-level and shared across co-mentors — one exclusion hides the
conversation from that record for everyone (plan §5.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import make_async_engine

metadata = MetaData()

email_sync_state = Table(
    "email_sync_state",
    metadata,
    Column("mailbox", String(255), primary_key=True),
    Column("history_id", String(32)),
    Column("initial_done", Boolean, nullable=False, server_default="false"),
    Column("last_synced_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("known_addresses", Text),
)

conversation_override = Table(
    "conversation_override",
    metadata,
    Column("parent_entity", String(64), nullable=False),
    Column("parent_id", String(36), nullable=False),
    Column("conversation_id", String(36), nullable=False),
    Column("action", String(16), nullable=False),  # include | exclude
    Column("created_by", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("parent_entity", "parent_id", "conversation_id"),
    Index("ix_conversation_override_conv", "conversation_id"),
)

ACTION_INCLUDE = "include"
ACTION_EXCLUDE = "exclude"


@dataclass
class SyncState:
    mailbox: str
    history_id: Optional[str]
    initial_done: bool
    last_synced_at: Optional[datetime]
    known_addresses: set[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CommsStore:
    """Sync-cursor + override persistence (one engine, like PostgresStore)."""

    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    # --- sync cursors ------------------------------------------------------

    async def get_sync_state(self, mailbox: str) -> Optional[SyncState]:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(email_sync_state).where(email_sync_state.c.mailbox == mailbox)
                )
            ).first()
        if row is None:
            return None
        import json as _json

        try:
            known = set(_json.loads(row.known_addresses or "[]"))
        except (ValueError, TypeError):
            known = set()
        return SyncState(
            mailbox=row.mailbox,
            history_id=row.history_id,
            initial_done=bool(row.initial_done),
            last_synced_at=row.last_synced_at,
            known_addresses=known,
        )

    async def save_sync_state(
        self,
        mailbox: str,
        *,
        history_id: Optional[str],
        initial_done: bool,
        error: Optional[str] = None,
        known_addresses: Optional[set[str]] = None,
    ) -> None:
        import json as _json

        values = {
            "history_id": history_id,
            "initial_done": initial_done,
            "last_synced_at": _now(),
            "last_error": error,
            "known_addresses": _json.dumps(sorted(known_addresses or [])),
        }
        stmt = (
            pg_insert(email_sync_state)
            .values(mailbox=mailbox, **values)
            .on_conflict_do_update(index_elements=["mailbox"], set_=values)
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def reset_all_sync_state(self) -> None:
        """One-shot re-drive (GMAIL_RESYNC): forget every cursor so the next
        pass re-runs the initial backfill. Dedup makes the re-ingest idempotent."""
        from sqlalchemy import update

        async with self._engine.begin() as conn:
            await conn.execute(
                update(email_sync_state).values(
                    history_id=None, initial_done=False, known_addresses="[]"
                )
            )

    # --- curation overrides --------------------------------------------------

    async def set_override(
        self,
        parent_entity: str,
        parent_id: str,
        conversation_id: str,
        action: str,
        created_by: str = "",
    ) -> None:
        values = {"action": action, "created_by": created_by, "created_at": _now()}
        stmt = (
            pg_insert(conversation_override)
            .values(
                parent_entity=parent_entity,
                parent_id=parent_id,
                conversation_id=conversation_id,
                **values,
            )
            .on_conflict_do_update(
                index_elements=["parent_entity", "parent_id", "conversation_id"],
                set_=values,
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def overrides_for_parent(
        self, parent_entity: str, parent_id: str
    ) -> dict[str, str]:
        """``{conversation_id: action}`` for one record."""
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        conversation_override.c.conversation_id,
                        conversation_override.c.action,
                    ).where(
                        conversation_override.c.parent_entity == parent_entity,
                        conversation_override.c.parent_id == parent_id,
                    )
                )
            ).all()
        return {r.conversation_id: r.action for r in rows}

    async def all_excludes(self) -> set[tuple[str, str, str]]:
        """Every (parent_entity, parent_id, conversation_id) exclusion — consulted
        by the sync before (re)linking. The table stays small (manual actions)."""
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        conversation_override.c.parent_entity,
                        conversation_override.c.parent_id,
                        conversation_override.c.conversation_id,
                    ).where(conversation_override.c.action == ACTION_EXCLUDE)
                )
            ).all()
        return {(r.parent_entity, r.parent_id, r.conversation_id) for r in rows}


def make_comms_store(settings: Settings) -> Optional[CommsStore]:
    if not settings.database_url:
        return None
    return CommsStore(settings.database_url)


class MemoryCommsStore:
    """In-memory stand-in for tests / DB-less dev (same surface as CommsStore)."""

    def __init__(self) -> None:
        self._state: dict[str, SyncState] = {}
        self._overrides: dict[tuple[str, str, str], str] = {}

    async def create_all(self) -> None: ...

    async def dispose(self) -> None: ...

    async def get_sync_state(self, mailbox: str) -> Optional[SyncState]:
        return self._state.get(mailbox)

    async def save_sync_state(
        self, mailbox: str, *, history_id, initial_done, error=None, known_addresses=None
    ) -> None:
        self._state[mailbox] = SyncState(
            mailbox=mailbox,
            history_id=history_id,
            initial_done=initial_done,
            last_synced_at=_now(),
            known_addresses=set(known_addresses or []),
        )

    async def reset_all_sync_state(self) -> None:
        for mailbox, st in list(self._state.items()):
            self._state[mailbox] = SyncState(
                mailbox=mailbox, history_id=None, initial_done=False,
                last_synced_at=st.last_synced_at, known_addresses=set(),
            )

    async def set_override(
        self, parent_entity, parent_id, conversation_id, action, created_by=""
    ) -> None:
        self._overrides[(parent_entity, parent_id, conversation_id)] = action

    async def overrides_for_parent(self, parent_entity, parent_id) -> dict[str, str]:
        return {
            conv: action
            for (pe, pid, conv), action in self._overrides.items()
            if pe == parent_entity and pid == parent_id
        }

    async def all_excludes(self) -> set[tuple[str, str, str]]:
        return {
            key for key, action in self._overrides.items() if action == ACTION_EXCLUDE
        }
