"""Campaign audiences — the lists' own tables (build plan § 7c.5; ruling 64:
lists live in the application's database, like campaign links). Migration
``alembic/versions/0032_campaign_audience_lists.py``; reset nightly on the
sandbox.

``AudienceStoreMixin`` is mixed into ``CampaignStore`` so the router keeps one
store on ``app.state.campaign_store``. A key is ``<type>:<CRM id>`` — ``lead``,
``contact`` (L1), ``client``, ``partner``, ``funder`` (L2).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.store import metadata

KIND_STATIC = "static"
KIND_DYNAMIC = "dynamic"
KINDS = (KIND_STATIC, KIND_DYNAMIC)
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"
SOURCE_RECIPE = "recipe"
SOURCE_HAND = "hand"
STATE_IN = "in"
STATE_OUT = "out"
MODE_INCLUDE = "include"
MODE_EXCLUDE = "exclude"

audience_list = Table(
    "audience_list",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("notes", Text),
    Column("kind", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("version", Integer, nullable=False),
    Column("recipe", JSONB, nullable=False),
    Column("last_run_at", DateTime(timezone=True)),
    Column("last_run_by", String(128)),
    Column("last_run", JSONB),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(128)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("retired_by", String(128)),
    Column("retired_at", DateTime(timezone=True)),
    Index("ix_audience_list_name", "name"),
)

audience_list_version = Table(
    "audience_list_version",
    metadata,
    Column("list_id", String(36), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("recipe", JSONB, nullable=False),
    Column("saved_by", String(128)),
    Column("saved_at", DateTime(timezone=True), nullable=False),
)

audience_list_member = Table(
    "audience_list_member",
    metadata,
    Column("list_id", String(36), primary_key=True),
    Column("target_key", String(64), primary_key=True),
    Column("source", String(16), nullable=False),
    Column("state", String(8), nullable=False),
    Column("step", Integer),
    Column("added_by", String(128)),
    Column("added_at", DateTime(timezone=True), nullable=False),
    Index("ix_audience_list_member_list", "list_id", "state"),
)

audience_list_entry = Table(
    "audience_list_entry",
    metadata,
    Column("list_id", String(36), primary_key=True),
    Column("target_key", String(64), primary_key=True),
    Column("mode", String(8), nullable=False),
    Column("note", String(500)),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

campaign_audience = Table(
    "campaign_audience",
    metadata,
    Column("campaign_id", String(32), primary_key=True),
    Column("list_id", String(36), nullable=False),
    Column("include_every_contact", Boolean, nullable=False, default=False),
    Column("set_by", String(128)),
    Column("set_at", DateTime(timezone=True), nullable=False),
    Column("built_version", Integer),
    Column("built_at", DateTime(timezone=True)),
    Column("build", JSONB),
    Index("ix_campaign_audience_list", "list_id"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AudienceStoreMixin:
    """The list methods. Needs ``self._engine`` (CampaignStore provides it)."""

    _engine: Any

    # --- lists ---------------------------------------------------------------------

    async def create_list(self, *, name: str, notes: str, kind: str, recipe: dict[str, Any],
                          actor: str) -> dict[str, Any]:
        now = _now()
        row = {"id": str(uuid.uuid4()), "name": name, "notes": notes or None, "kind": kind,
               "status": STATUS_ACTIVE, "version": 1, "recipe": recipe,
               "last_run_at": None, "last_run_by": None, "last_run": None,
               "created_by": actor, "created_at": now, "updated_by": actor, "updated_at": now,
               "retired_by": None, "retired_at": None}
        async with self._engine.begin() as conn:
            await conn.execute(audience_list.insert().values(**row))
            await conn.execute(audience_list_version.insert().values(
                list_id=row["id"], version=1, kind=kind, recipe=recipe, saved_by=actor, saved_at=now))
        return row

    async def get_list(self, list_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(audience_list).where(audience_list.c.id == list_id))).mappings().first()
        return dict(row) if row else None

    async def all_lists(self) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(audience_list).order_by(audience_list.c.name))).mappings().all()
        return [dict(r) for r in rows]

    async def save_list(self, list_id: str, *, name: str, notes: str, kind: str,
                        recipe: dict[str, Any], actor: str) -> Optional[dict[str, Any]]:
        """Save the editable parts. A change of recipe or kind is a new version."""
        current = await self.get_list(list_id)
        if not current:
            return None
        now = _now()
        values: dict[str, Any] = {"name": name, "notes": notes or None, "updated_by": actor, "updated_at": now}
        new_version = current["version"]
        if recipe != current["recipe"] or kind != current["kind"]:
            new_version = current["version"] + 1
            values.update(kind=kind, recipe=recipe, version=new_version)
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(**values))
            if new_version != current["version"]:
                await conn.execute(audience_list_version.insert().values(
                    list_id=list_id, version=new_version, kind=kind, recipe=recipe,
                    saved_by=actor, saved_at=now))
        return await self.get_list(list_id)

    async def set_list_status(self, list_id: str, status: str, actor: str) -> Optional[dict[str, Any]]:
        values: dict[str, Any] = {"status": status, "updated_by": actor, "updated_at": _now()}
        if status == STATUS_RETIRED:
            values.update(retired_by=actor, retired_at=_now())
        else:
            values.update(retired_by=None, retired_at=None)
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(**values))
        return await self.get_list(list_id)

    async def delete_list(self, list_id: str) -> None:
        async with self._engine.begin() as conn:
            for t in (audience_list_member, audience_list_entry, audience_list_version):
                await conn.execute(delete(t).where(t.c.list_id == list_id))
            await conn.execute(delete(audience_list).where(audience_list.c.id == list_id))

    async def list_versions(self, list_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(audience_list_version).where(audience_list_version.c.list_id == list_id)
                .order_by(audience_list_version.c.version.desc())
            )).mappings().all()
        return [dict(r) for r in rows]

    # --- membership (a run's result, and hand ticks on a static list) ----------------

    async def replace_recipe_members(self, list_id: str, keyed_steps: dict[str, int], *,
                                     run: dict[str, Any], actor: str) -> None:
        """A run: every recipe-sourced row is replaced by this result; hand rows
        stay (a hand tick on a static list survives "Run again")."""
        now = _now()
        m = audience_list_member
        async with self._engine.begin() as conn:
            hand = {r[0] for r in (await conn.execute(
                select(m.c.target_key).where(and_(m.c.list_id == list_id, m.c.source == SOURCE_HAND))
            )).all()}
            await conn.execute(delete(m).where(and_(m.c.list_id == list_id, m.c.source == SOURCE_RECIPE)))
            values = [{"list_id": list_id, "target_key": k, "source": SOURCE_RECIPE, "state": STATE_IN,
                       "step": s, "added_by": actor, "added_at": now}
                      for k, s in keyed_steps.items() if k not in hand]
            for i in range(0, len(values), 1000):
                await conn.execute(m.insert(), values[i:i + 1000])
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(
                last_run_at=now, last_run_by=actor, last_run=run))

    async def hand_mark(self, list_id: str, target_key: str, state: str, actor: str) -> None:
        stmt = pg_insert(audience_list_member).values(
            list_id=list_id, target_key=target_key, source=SOURCE_HAND, state=state,
            step=None, added_by=actor, added_at=_now())
        stmt = stmt.on_conflict_do_update(
            index_elements=["list_id", "target_key"],
            set_={"source": SOURCE_HAND, "state": state, "added_by": actor, "added_at": _now()})
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def hand_clear(self, list_id: str, target_key: str) -> None:
        m = audience_list_member
        async with self._engine.begin() as conn:
            await conn.execute(delete(m).where(and_(m.c.list_id == list_id, m.c.target_key == target_key,
                                                    m.c.source == SOURCE_HAND)))

    async def member_rows(self, list_id: str) -> list[dict[str, Any]]:
        m = audience_list_member
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(m).where(m.c.list_id == list_id))).mappings().all()
        return [dict(r) for r in rows]

    # --- standing entries (dynamic lists, ruling 65) -------------------------------

    async def set_entry(self, list_id: str, target_key: str, mode: str, note: str, actor: str) -> None:
        stmt = pg_insert(audience_list_entry).values(
            list_id=list_id, target_key=target_key, mode=mode, note=(note or None),
            created_by=actor, created_at=_now())
        stmt = stmt.on_conflict_do_update(
            index_elements=["list_id", "target_key"],
            set_={"mode": mode, "note": note or None, "created_by": actor, "created_at": _now()})
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def remove_entry(self, list_id: str, target_key: str) -> None:
        e = audience_list_entry
        async with self._engine.begin() as conn:
            await conn.execute(delete(e).where(and_(e.c.list_id == list_id, e.c.target_key == target_key)))

    async def entries(self, list_id: str) -> list[dict[str, Any]]:
        e = audience_list_entry
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(e).where(e.c.list_id == list_id).order_by(e.c.created_at))).mappings().all()
        return [dict(r) for r in rows]

    # --- the campaign's list -----------------------------------------------------------

    async def get_campaign_audience(self, campaign_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(campaign_audience).where(campaign_audience.c.campaign_id == campaign_id)
            )).mappings().first()
        return dict(row) if row else None

    async def set_campaign_audience(self, campaign_id: str, list_id: Optional[str], *,
                                    include_every_contact: bool, actor: str) -> None:
        ca = campaign_audience
        async with self._engine.begin() as conn:
            if not list_id:
                await conn.execute(delete(ca).where(ca.c.campaign_id == campaign_id))
                return
            stmt = pg_insert(ca).values(campaign_id=campaign_id, list_id=list_id,
                                        include_every_contact=include_every_contact,
                                        set_by=actor, set_at=_now())
            stmt = stmt.on_conflict_do_update(
                index_elements=["campaign_id"],
                set_={"list_id": list_id, "include_every_contact": include_every_contact,
                      "set_by": actor, "set_at": _now()})
            await conn.execute(stmt)

    async def record_campaign_build(self, campaign_id: str, *, version: int, build: dict[str, Any]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(campaign_audience).where(campaign_audience.c.campaign_id == campaign_id)
                               .values(built_version=version, built_at=_now(), build=build))

    async def campaigns_using(self, list_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(campaign_audience).where(campaign_audience.c.list_id == list_id)
            )).mappings().all()
        return [dict(r) for r in rows]

    async def usage_counts(self) -> dict[str, int]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(campaign_audience.c.list_id, func.count()).group_by(campaign_audience.c.list_id)
            )).all()
        return {r[0]: int(r[1]) for r in rows}
