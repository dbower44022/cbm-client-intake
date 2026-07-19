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
    # P1-5 (reliability review 2026-07-17): per-message failure tracking.
    # failed_ids = {"<gmail id>": consecutive-pass failure count} — while any
    # id is failing the cursor is NOT advanced past it; after
    # GMAIL_DEAD_LETTER_PASSES consecutive failures the id moves to
    # dead_letter (a JSON list) and the cursor moves on. Dead-lettered ids
    # are visible in the logs and /ops metrics.
    Column("failed_ids", Text),
    Column("dead_letter", Text),
)

# Local (mailbox, Gmail thread id) -> conversation id map, written whenever the
# sync creates a CConversation. CConversation has no thread-id field (schema:
# cconversation-entity.md), so a conversation whose FIRST message create failed
# was an unfindable empty shell — the retry then minted a duplicate (the five
# hand-deleted crm-test shells). This map makes shells findable so a retry
# fills the same conversation; it also lets the send path resolve/create the
# conversation BEFORE the best-effort write-through ingest (P1-5 F6).
conversation_thread = Table(
    "conversation_thread",
    metadata,
    Column("mailbox", String(255), nullable=False),
    Column("thread_id", String(100), nullable=False),
    Column("conversation_id", String(36), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("mailbox", "thread_id"),
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

# Per-user read state: when this user last opened each conversation. Unread =
# lastMessageAt newer than this stamp (or no stamp at all — see the never-seen
# window in comms.service.enrich_conversation_rows). Alembic 0010.
conversation_seen = Table(
    "conversation_seen",
    metadata,
    Column("username", String(64), nullable=False),
    Column("conversation_id", String(36), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("username", "conversation_id"),
)

ACTION_INCLUDE = "include"
ACTION_EXCLUDE = "exclude"


@dataclass
class SyncState:
    mailbox: str
    history_id: Optional[str]
    initial_done: bool
    # Last FULLY-successful pass (every fetched message ingested). This is the
    # expired-cursor backfill window source, so it must never advance on a
    # failed/partial pass (P1-5): a two-week outage would otherwise compute
    # the re-query window as "yesterday" and silently skip the whole span.
    last_synced_at: Optional[datetime]
    known_addresses: set[str]
    # {gmail id: consecutive failing passes} / ids skipped after 5 (D6).
    failed_ids: dict[str, int] = None  # type: ignore[assignment]
    dead_letter: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failed_ids is None:
            self.failed_ids = {}
        if self.dead_letter is None:
            self.dead_letter = []


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

        def _load(raw, default):
            try:
                value = _json.loads(raw or "")
                return value if isinstance(value, type(default)) else default
            except (ValueError, TypeError):
                return default

        return SyncState(
            mailbox=row.mailbox,
            history_id=row.history_id,
            initial_done=bool(row.initial_done),
            last_synced_at=row.last_synced_at,
            known_addresses=set(_load(row.known_addresses, [])),
            failed_ids=_load(row.failed_ids, {}),
            dead_letter=_load(row.dead_letter, []),
        )

    async def save_sync_state(
        self,
        mailbox: str,
        *,
        history_id: Optional[str],
        initial_done: bool,
        error: Optional[str] = None,
        known_addresses: Optional[set[str]] = None,
        success: bool = True,
        failed_ids: Optional[dict[str, int]] = None,
        dead_letter: Optional[list[str]] = None,
    ) -> None:
        """``success=False`` (an errored or partial pass) keeps the stored
        ``last_synced_at`` — it must reflect the last FULLY-successful pass,
        because it is the expired-cursor backfill window source (P1-5)."""
        import json as _json

        values: dict[str, Any] = {
            "history_id": history_id,
            "initial_done": initial_done,
            "last_error": error,
            "known_addresses": _json.dumps(sorted(known_addresses or [])),
            "failed_ids": _json.dumps(failed_ids or {}),
            "dead_letter": _json.dumps(dead_letter or []),
        }
        if success:
            values["last_synced_at"] = _now()
        stmt = (
            pg_insert(email_sync_state)
            .values(mailbox=mailbox, **values)
            .on_conflict_do_update(index_elements=["mailbox"], set_=values)
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def all_sync_states(self) -> list[SyncState]:
        """Every mailbox's state — for /ops metrics (dead-letter visibility)."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(email_sync_state.c.mailbox))).all()
        out = []
        for r in rows:
            state = await self.get_sync_state(r.mailbox)
            if state:
                out.append(state)
        return out

    async def reset_all_sync_state(self) -> None:
        """One-shot re-drive (GMAIL_RESYNC): forget every cursor so the next
        pass re-runs the initial backfill. Dedup makes the re-ingest idempotent.
        Failure tracking resets too — a resync is a fresh start (a formerly
        dead-lettered message gets its five new chances)."""
        from sqlalchemy import update

        async with self._engine.begin() as conn:
            await conn.execute(
                update(email_sync_state).values(
                    history_id=None, initial_done=False, known_addresses="[]",
                    failed_ids="{}", dead_letter="[]",
                )
            )

    # --- conversation thread map (shell reuse, P1-5 F5) ----------------------

    async def set_thread_conversation(
        self, mailbox: str, thread_id: str, conversation_id: str
    ) -> None:
        values = {"conversation_id": conversation_id, "created_at": _now()}
        stmt = (
            pg_insert(conversation_thread)
            .values(mailbox=mailbox, thread_id=thread_id, **values)
            .on_conflict_do_update(
                index_elements=["mailbox", "thread_id"], set_=values
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def get_thread_conversation(
        self, mailbox: str, thread_id: str
    ) -> Optional[str]:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(conversation_thread.c.conversation_id).where(
                        conversation_thread.c.mailbox == mailbox,
                        conversation_thread.c.thread_id == thread_id,
                    )
                )
            ).first()
        return row.conversation_id if row else None

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

    # --- per-user read state (unread badges) ---------------------------------

    async def mark_seen(self, username: str, conversation_id: str) -> None:
        stmt = (
            pg_insert(conversation_seen)
            .values(
                username=username, conversation_id=conversation_id,
                last_seen_at=_now(),
            )
            .on_conflict_do_update(
                index_elements=["username", "conversation_id"],
                set_={"last_seen_at": _now()},
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def mark_many_seen(self, username: str, conversation_ids: list[str]) -> None:
        for cid in conversation_ids:
            await self.mark_seen(username, cid)

    async def seen_map(
        self, username: str, conversation_ids: list[str]
    ) -> dict[str, datetime]:
        """``{conversation_id: last_seen_at}`` for this user, limited to the
        listed conversations (one page's worth)."""
        if not conversation_ids:
            return {}
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        conversation_seen.c.conversation_id,
                        conversation_seen.c.last_seen_at,
                    ).where(
                        conversation_seen.c.username == username,
                        conversation_seen.c.conversation_id.in_(conversation_ids),
                    )
                )
            ).all()
        return {r.conversation_id: r.last_seen_at for r in rows}


def make_comms_store(settings: Settings) -> Optional[CommsStore]:
    if not settings.database_url:
        return None
    return CommsStore(settings.database_url)


class MemoryCommsStore:
    """In-memory stand-in for tests / DB-less dev (same surface as CommsStore)."""

    def __init__(self) -> None:
        self._state: dict[str, SyncState] = {}
        self._overrides: dict[tuple[str, str, str], str] = {}
        self._threads: dict[tuple[str, str], str] = {}
        self._seen: dict[tuple[str, str], datetime] = {}

    async def create_all(self) -> None: ...

    async def dispose(self) -> None: ...

    async def get_sync_state(self, mailbox: str) -> Optional[SyncState]:
        return self._state.get(mailbox)

    async def save_sync_state(
        self, mailbox: str, *, history_id, initial_done, error=None,
        known_addresses=None, success=True, failed_ids=None, dead_letter=None,
    ) -> None:
        prev = self._state.get(mailbox)
        self._state[mailbox] = SyncState(
            mailbox=mailbox,
            history_id=history_id,
            initial_done=initial_done,
            last_synced_at=_now() if success else (prev.last_synced_at if prev else None),
            known_addresses=set(known_addresses or []),
            failed_ids=dict(failed_ids or {}),
            dead_letter=list(dead_letter or []),
        )

    async def all_sync_states(self) -> list[SyncState]:
        return list(self._state.values())

    async def reset_all_sync_state(self) -> None:
        for mailbox, st in list(self._state.items()):
            self._state[mailbox] = SyncState(
                mailbox=mailbox, history_id=None, initial_done=False,
                last_synced_at=st.last_synced_at, known_addresses=set(),
            )

    async def set_thread_conversation(self, mailbox, thread_id, conversation_id) -> None:
        self._threads[(mailbox, thread_id)] = conversation_id

    async def get_thread_conversation(self, mailbox, thread_id) -> Optional[str]:
        return self._threads.get((mailbox, thread_id))

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

    async def mark_seen(self, username: str, conversation_id: str) -> None:
        self._seen[(username, conversation_id)] = _now()

    async def mark_many_seen(self, username: str, conversation_ids: list[str]) -> None:
        for cid in conversation_ids:
            await self.mark_seen(username, cid)

    async def seen_map(
        self, username: str, conversation_ids: list[str]
    ) -> dict[str, datetime]:
        return {
            cid: ts
            for (u, cid), ts in self._seen.items()
            if u == username and cid in set(conversation_ids)
        }
