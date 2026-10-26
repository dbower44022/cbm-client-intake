"""Campaign audiences — the lists' own tables (build plan § 7c.5; ruling 64:
lists live in the application's database, like campaign links). Migrations
``0032_campaign_audience_lists``, ``0037_lists_include_leave_out`` (the
Include / Leave out recipe, § 7e.8) and ``0038_list_constant_contact_copy``
(the copy in Constant Contact, § 7e.9); reset nightly on the sandbox.

A **dynamic** list's members are what its last run found (``source`` recipe,
``group_index`` the Include group that brought each one in). A **static**
list's members are the rows added by hand (``source`` hand, ``state`` in) and
nothing else (rulings 91, 94). A list's kind never changes (ruling 93).

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
    Column("needs_rebuild", Boolean, nullable=False, default=False),
    # The kept-current copy in Constant Contact (§ 7e.9, ruling 95; migration 0038).
    Column("cc_sync", Boolean, nullable=False, default=False),
    Column("cc_list_id", String(64)),
    Column("cc_last_sync_at", DateTime(timezone=True)),
    Column("cc_last_sync", JSONB),
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
    Column("group_index", Integer),
    Column("added_by", String(128)),
    Column("added_at", DateTime(timezone=True), nullable=False),
    Index("ix_audience_list_member_list", "list_id", "state"),
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
               "retired_by": None, "retired_at": None, "needs_rebuild": False,
               "cc_sync": False, "cc_list_id": None, "cc_last_sync_at": None, "cc_last_sync": None}
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
        """Save the editable parts. A change of recipe is a new version; a save
        clears ``needs_rebuild`` (someone has checked the list). The kind never
        changes (ruling 93): a different one raises ``ValueError``."""
        current = await self.get_list(list_id)
        if not current:
            return None
        if kind != current["kind"]:
            raise ValueError("A list's kind is fixed when it is created.")
        now = _now()
        values: dict[str, Any] = {"name": name, "notes": notes or None, "updated_by": actor, "updated_at": now,
                                  "needs_rebuild": False}
        new_version = current["version"]
        if recipe != current["recipe"]:
            new_version = current["version"] + 1
            values.update(recipe=recipe, version=new_version)
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(**values))
            if new_version != current["version"]:
                await conn.execute(audience_list_version.insert().values(
                    list_id=list_id, version=new_version, kind=kind, recipe=recipe,
                    saved_by=actor, saved_at=now))
        return await self.get_list(list_id)

    async def copy_list(self, *, name: str, notes: str, keys: list[str], actor: str) -> dict[str, Any]:
        """A new static list holding these members as hand rows (ruling 93:
        *Copy current members to a new static list*)."""
        row = await self.create_list(name=name, notes=notes, kind=KIND_STATIC,
                                     recipe={"include": [], "exclude": []}, actor=actor)
        await self.hand_add_many(row["id"], keys, actor)
        return row

    async def set_list_status(self, list_id: str, status: str, actor: str) -> Optional[dict[str, Any]]:
        values: dict[str, Any] = {"status": status, "updated_by": actor, "updated_at": _now()}
        if status == STATUS_RETIRED:
            values.update(retired_by=actor, retired_at=_now())
        else:
            values.update(retired_by=None, retired_at=None)
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(**values))
        return await self.get_list(list_id)

    # --- the Constant Contact copy (§ 7e.9) ---------------------------------------

    async def set_cc_sync(self, list_id: str, on: bool, actor: str) -> Optional[dict[str, Any]]:
        """The tick. Unticking keeps ``cc_list_id``: the copy stays at the vendor,
        and ticking again resumes it rather than making a second one."""
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(
                cc_sync=bool(on), updated_by=actor, updated_at=_now()))
        return await self.get_list(list_id)

    async def set_cc_list_id(self, list_id: str, cc_list_id: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(
                cc_list_id=cc_list_id or None))

    async def record_cc_sync(self, list_id: str, summary: dict[str, Any]) -> None:
        """The last sync's summary — the counts, or ``error`` in words."""
        async with self._engine.begin() as conn:
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(
                cc_last_sync_at=_now(), cc_last_sync=summary))

    async def cc_sync_lists(self) -> list[dict[str, Any]]:
        """Every active list with its copy on, by name — the worker's pass."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(audience_list).where(and_(
                audience_list.c.cc_sync.is_(True), audience_list.c.status == STATUS_ACTIVE,
            )).order_by(audience_list.c.name))).mappings().all()
        return [dict(r) for r in rows]

    async def delete_list(self, list_id: str) -> None:
        async with self._engine.begin() as conn:
            for t in (audience_list_member, audience_list_version):
                await conn.execute(delete(t).where(t.c.list_id == list_id))
            await conn.execute(delete(audience_list).where(audience_list.c.id == list_id))

    async def list_versions(self, list_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(audience_list_version).where(audience_list_version.c.list_id == list_id)
                .order_by(audience_list_version.c.version.desc())
            )).mappings().all()
        return [dict(r) for r in rows]

    # --- membership: a dynamic list's last run, a static list's hand rows -------------

    async def replace_recipe_members(self, list_id: str, keyed_groups: dict[str, int], *,
                                     run: dict[str, Any], actor: str) -> None:
        """A dynamic list's run: every row is replaced by this result, each
        with the Include group that brought it in."""
        now = _now()
        m = audience_list_member
        async with self._engine.begin() as conn:
            await conn.execute(delete(m).where(m.c.list_id == list_id))
            values = [{"list_id": list_id, "target_key": k, "source": SOURCE_RECIPE, "state": STATE_IN,
                       "group_index": g or None, "added_by": actor, "added_at": now}
                      for k, g in keyed_groups.items()]
            for i in range(0, len(values), 1000):
                await conn.execute(m.insert(), values[i:i + 1000])
            await conn.execute(update(audience_list).where(audience_list.c.id == list_id).values(
                last_run_at=now, last_run_by=actor, last_run=run))

    async def hand_mark(self, list_id: str, target_key: str, state: str, actor: str) -> None:
        """One person added to a static list by hand."""
        await self.hand_add_many(list_id, [target_key], actor)

    async def hand_add_many(self, list_id: str, keys: list[str], actor: str) -> int:
        """People added to a static list by hand, copied once (ruling 94).
        Returns how many were not on it already."""
        m = audience_list_member
        keys = list(dict.fromkeys(k for k in keys if k))
        if not keys:
            return 0
        now = _now()
        added = 0
        async with self._engine.begin() as conn:
            for i in range(0, len(keys), 1000):
                chunk = keys[i:i + 1000]
                stmt = pg_insert(m).values([
                    {"list_id": list_id, "target_key": k, "source": SOURCE_HAND, "state": STATE_IN,
                     "group_index": None, "added_by": actor, "added_at": now} for k in chunk
                ]).on_conflict_do_nothing(index_elements=["list_id", "target_key"])
                res = await conn.execute(stmt)
                added += res.rowcount or 0
        return added

    async def drop_member(self, list_id: str, target_key: str) -> None:
        """Take a row out of a dynamic list's last run (the Exclude button: the
        person is gone from the grid before the next run confirms it)."""
        m = audience_list_member
        async with self._engine.begin() as conn:
            await conn.execute(delete(m).where(and_(m.c.list_id == list_id, m.c.target_key == target_key)))

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

    async def member_counts(self) -> dict[str, int]:
        """Members per list, as the grid would show them (the index)."""
        m = audience_list_member
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(m.c.list_id, func.count()).where(m.c.state == STATE_IN).group_by(m.c.list_id)
            )).all()
        return {r[0]: int(r[1]) for r in rows}

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

    async def last_used(self) -> dict[str, datetime]:
        """Per list, when a campaign last built from it, else when one chose it
        (the index's *Last used*)."""
        ca = campaign_audience
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(ca.c.list_id, func.max(func.coalesce(ca.c.built_at, ca.c.set_at))).group_by(ca.c.list_id)
            )).all()
        return {r[0]: r[1] for r in rows if r[1]}
