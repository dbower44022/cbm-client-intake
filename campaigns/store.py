"""The campaign links and the prospect import ledger — the application's own
tables (ruling 31; build plan § 3.7 and § 2). Migration
``alembic/versions/0031_campaign_links.py``; reset nightly on the sandbox.

Why not the CRM: the resolve route runs on every public click and must answer
without a CRM call; visits are write-heavy rows the CRM should never carry; a
destination correction is an application write, not a CRM write under a public
identity. The CRM holds the campaign; the relationship records hold the campaign
id (ruling 27); the link is one level finer and stays here.
"""

from __future__ import annotations

import hashlib
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
    UniqueConstraint,
    and_,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB

from core.config import Settings
from core.store import make_async_engine, metadata, submission

from . import config as cfg
from .audience_store import AudienceStoreMixin
from .tokens import new_link_token

campaign_link = Table(
    "campaign_link",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("campaign_id", String(32), nullable=False),
    Column("token", String(16), nullable=False),
    Column("name", String(200), nullable=False),
    Column("destination_kind", String(32), nullable=False),
    Column("destination_target", String(200)),
    Column("destination_slug", String(200)),
    Column("state", String(16), nullable=False),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("retired_by", String(128)),
    Column("retired_at", DateTime(timezone=True)),
    Column("history", JSONB),
    UniqueConstraint("token", name="uq_campaign_link_token"),
    Index("ix_campaign_link_campaign", "campaign_id", "created_at"),
)

campaign_link_visit = Table(
    "campaign_link_visit",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("link_id", String(36), nullable=False),
    Column("visited_at", DateTime(timezone=True), nullable=False),
    Column("address_hash", String(64)),
    Column("late", Boolean, nullable=False, default=False),
    Column("agent_class", String(16)),
    Column("scan_token", String(16)),
    Index("ix_campaign_link_visit_link", "link_id", "visited_at"),
)

prospect_import_batch = Table(
    "prospect_import_batch",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("door", String(32), nullable=False),
    Column("file_sha256", String(64), nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("plan", JSONB),
    Column("result", JSONB),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True)),
    Index("ix_prospect_import_batch_file", "file_sha256"),
)

prospect_import_row = Table(
    "prospect_import_row",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("batch_id", String(36), nullable=False),
    Column("row_hash", String(64), nullable=False),
    Column("external_reference", String(100)),
    Column("business_name", String(255)),
    Column("postal_code", String(40)),
    Column("outcome", String(32), nullable=False),
    Column("prospect_id", String(32)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_prospect_import_row_batch", "batch_id"),
    Index("ix_prospect_import_row_hash", "row_hash"),
)

BATCH_PLANNED = "planned"
BATCH_APPLIED = "applied"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def address_hash(address: str, salt: str) -> str:
    """A salted hash of a visitor's address: enough to tell one visitor's
    repeats apart, never the address itself."""
    return hashlib.sha256(f"{salt}|{address}".encode()).hexdigest()


def agent_class(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "unknown"
    if any(w in ua for w in ("bot", "crawler", "spider", "preview", "facebookexternalhit", "slackbot")):
        return "bot"
    if any(w in ua for w in ("iphone", "android", "mobile", "ipad")):
        return "phone"
    return "desktop"


class CampaignStore(AudienceStoreMixin):
    """Links, visits and the import ledger. One engine per store, like the
    other ``_engine.begin()`` stores in this application."""

    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    # --- links ----------------------------------------------------------------

    async def create_link(
        self, *, campaign_id: str, name: str, destination_kind: str,
        destination_target: Optional[str], destination_slug: Optional[str],
        created_by: str, token: Optional[str] = None,
    ) -> dict[str, Any]:
        # ``token`` is for the sandbox's fixed demo links only
        # (campaigns/sandbox_demo.py); every real link gets a random one.
        row = {
            "id": str(uuid.uuid4()),
            "campaign_id": campaign_id,
            "token": token or new_link_token(),
            "name": name,
            "destination_kind": destination_kind,
            "destination_target": destination_target,
            "destination_slug": destination_slug,
            "state": cfg.LINK_ACTIVE,
            "created_by": created_by,
            "created_at": _now(),
            "history": [],
        }
        async with self._engine.begin() as conn:
            await conn.execute(campaign_link.insert().values(**row))
        return row

    async def get_link(self, link_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(campaign_link).where(campaign_link.c.id == link_id)
            )).mappings().first()
        return dict(row) if row else None

    async def get_link_by_token(self, token: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(campaign_link).where(campaign_link.c.token == token.lower())
            )).mappings().first()
        return dict(row) if row else None

    async def list_links(self, campaign_id: str) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(campaign_link)
                .where(campaign_link.c.campaign_id == campaign_id)
                .order_by(campaign_link.c.created_at)
            )).mappings().all()
        return [dict(r) for r in rows]

    async def landing_link(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """A postcard campaign's one link to the landing page, if made."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(campaign_link).where(and_(
                    campaign_link.c.campaign_id == campaign_id,
                    campaign_link.c.destination_kind == cfg.DEST_LANDING,
                )).order_by(campaign_link.c.created_at).limit(1)
            )).mappings().first()
        return dict(row) if row else None

    async def correct_destination(
        self, link_id: str, *, destination_kind: str, destination_target: Optional[str],
        destination_slug: Optional[str], actor: str,
    ) -> Optional[dict[str, Any]]:
        """The printed or posted address never changes; where it goes can."""
        current = await self.get_link(link_id)
        if current is None:
            return None
        history = list(current.get("history") or [])
        history.append({
            "at": _now().isoformat(), "by": actor, "change": "destination",
            "from": {"kind": current["destination_kind"], "target": current["destination_target"]},
            "to": {"kind": destination_kind, "target": destination_target},
        })
        async with self._engine.begin() as conn:
            await conn.execute(
                update(campaign_link).where(campaign_link.c.id == link_id).values(
                    destination_kind=destination_kind,
                    destination_target=destination_target,
                    destination_slug=destination_slug,
                    history=history,
                )
            )
        return await self.get_link(link_id)

    async def refresh_slug(self, link_id: str, slug: Optional[str]) -> None:
        """An event link's cached slug, refreshed from the CRM whenever staff
        look at the Links tab — so the public resolve never reads the CRM and a
        slug change still cannot strand the link."""
        async with self._engine.begin() as conn:
            await conn.execute(
                update(campaign_link).where(campaign_link.c.id == link_id)
                .values(destination_slug=slug)
            )

    async def set_state(self, link_id: str, state: str, actor: str) -> Optional[dict[str, Any]]:
        values: dict[str, Any] = {"state": state}
        if state == cfg.LINK_RETIRED:
            values.update(retired_by=actor, retired_at=_now())
        else:
            values.update(retired_by=None, retired_at=None)
        async with self._engine.begin() as conn:
            await conn.execute(
                update(campaign_link).where(campaign_link.c.id == link_id).values(**values)
            )
        return await self.get_link(link_id)

    # --- visits -----------------------------------------------------------------

    async def record_visit(
        self, link: dict[str, Any], *, address: str, user_agent: str, salt: str,
        scan_token: Optional[str] = None,
    ) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(campaign_link_visit.insert().values(
                id=str(uuid.uuid4()),
                link_id=link["id"],
                visited_at=_now(),
                address_hash=address_hash(address, salt),
                late=(link.get("state") == cfg.LINK_RETIRED),
                agent_class=agent_class(user_agent),
                scan_token=scan_token,
            ))

    async def visit_counts(self, link_ids: list[str]) -> dict[str, dict[str, int]]:
        """``{link id: {"visits": n, "late": n, "scans": n}}``."""
        out: dict[str, dict[str, int]] = {i: {"visits": 0, "late": 0, "scans": 0} for i in link_ids}
        if not link_ids:
            return out
        v = campaign_link_visit
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(
                    v.c.link_id,
                    func.count().label("visits"),
                    func.sum(func.cast(v.c.late, Integer)).label("late"),
                    func.count(v.c.scan_token).label("scans"),
                ).where(v.c.link_id.in_(link_ids)).group_by(v.c.link_id)
            )).mappings().all()
        for r in rows:
            out[r["link_id"]] = {
                "visits": int(r["visits"] or 0),
                "late": int(r["late"] or 0),
                "scans": int(r["scans"] or 0),
            }
        return out

    async def submissions_by_link(self, tokens: list[str]) -> dict[str, dict[str, int]]:
        """Submissions per link token, by form, from the durable store — the
        count comes from the application, never the CRM (§ 3.7)."""
        out: dict[str, dict[str, int]] = {t: {} for t in tokens}
        if not tokens:
            return out
        link_col = submission.c.payload[cfg.PAYLOAD_CAMPAIGN_LINK].astext
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(link_col.label("token"), submission.c.form_slug, func.count().label("n"))
                .where(link_col.in_(tokens))
                .where(submission.c.status.notin_(("held_honeypot", "discarded")))
                .group_by(link_col, submission.c.form_slug)
            )).mappings().all()
        for r in rows:
            out.setdefault(r["token"], {})[r["form_slug"]] = int(r["n"])
        return out

    async def recent_submissions(self, campaign_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """The latest submissions that carried this campaign, for the Responses tab."""
        col = submission.c.payload[cfg.PAYLOAD_CAMPAIGN_ID].astext
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(
                    submission.c.id, submission.c.form_slug, submission.c.status,
                    submission.c.received_at, submission.c.result,
                    submission.c.payload[cfg.PAYLOAD_CAMPAIGN_LINK].astext.label("link_token"),
                    submission.c.payload["email"].astext.label("email"),
                ).where(col == campaign_id)
                .order_by(submission.c.received_at.desc()).limit(limit)
            )).mappings().all()
        return [dict(r) for r in rows]

    # --- the import ledger ------------------------------------------------------

    async def find_batch_by_file(self, file_sha256: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(prospect_import_batch)
                .where(and_(prospect_import_batch.c.file_sha256 == file_sha256,
                            prospect_import_batch.c.status == BATCH_APPLIED))
                .order_by(prospect_import_batch.c.created_at.desc()).limit(1)
            )).mappings().first()
        return dict(row) if row else None

    async def get_batch(self, batch_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(prospect_import_batch).where(prospect_import_batch.c.id == batch_id)
            )).mappings().first()
        return dict(row) if row else None

    async def create_batch(
        self, *, name: str, door: str, file_sha256: str, row_count: int,
        plan: dict[str, Any], created_by: str,
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()), "name": name, "door": door,
            "file_sha256": file_sha256, "row_count": row_count,
            "status": BATCH_PLANNED, "plan": plan, "result": None,
            "created_by": created_by, "created_at": _now(), "applied_at": None,
        }
        async with self._engine.begin() as conn:
            await conn.execute(prospect_import_batch.insert().values(**row))
        return row

    async def mark_applied(self, batch_id: str, result: dict[str, Any]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(prospect_import_batch).where(prospect_import_batch.c.id == batch_id)
                .values(status=BATCH_APPLIED, result=result, applied_at=_now())
            )

    async def known_row_hashes(self, hashes: list[str]) -> set[str]:
        """Which of these rows an earlier apply already created — the across-batch
        duplicate check and what makes a re-upload a no-op. A recorded row is a
        lead that exists, whatever happened to the rest of its batch
        (a partial apply with two 403s left three real rows on 10-15-26)."""
        if not hashes:
            return set()
        r = prospect_import_row
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(r.c.row_hash).where(r.c.row_hash.in_(hashes))
            )).all()
        return {x[0] for x in rows}

    async def record_rows(self, batch_id: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        now = _now()
        values = [{
            "id": str(uuid.uuid4()), "batch_id": batch_id,
            "row_hash": r["row_hash"],
            "external_reference": r.get("external_reference"),
            "business_name": (r.get("business_name") or "")[:255] or None,
            "postal_code": r.get("postal_code"),
            "outcome": r["outcome"], "prospect_id": r.get("prospect_id"),
            "created_at": now,
        } for r in rows]
        async with self._engine.begin() as conn:
            await conn.execute(prospect_import_row.insert(), values)

    async def first_prospect_id(self, batch_id: str) -> Optional[str]:
        """The first lead an import made — the record its history row hangs on."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(prospect_import_row.c.prospect_id)
                .where(and_(prospect_import_row.c.batch_id == batch_id,
                            prospect_import_row.c.prospect_id.isnot(None)))
                .order_by(prospect_import_row.c.created_at).limit(1)
            )).first()
        return row[0] if row else None

    async def recent_batches(self, limit: int = 25) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(prospect_import_batch)
                .order_by(prospect_import_batch.c.created_at.desc()).limit(limit)
            )).mappings().all()
        return [dict(r) for r in rows]


def make_campaign_store(settings: Settings) -> Optional[CampaignStore]:
    """A store when a database is configured, else None — the links and the
    import then have nowhere to live and the screens say so."""
    if not settings.store_enabled:
        return None
    return CampaignStore(settings.database_url)
