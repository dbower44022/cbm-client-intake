"""The Website images, stored in the application database (plan decision 4.3).

One row per image in ``website_image``. Configuration, not training data, so
the sandbox's nightly reset keeps it (``core/sandbox_reset.KEEP_TABLES``).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, Table, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import make_async_engine, metadata

website_image = Table(
    "website_image",
    metadata,
    Column("name", String(16), primary_key=True),
    Column("content_type", String(64), nullable=False),
    Column("data", LargeBinary, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("size", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(128)),
)

_META = (website_image.c.name, website_image.c.content_type, website_image.c.sha256,
         website_image.c.size, website_image.c.updated_at, website_image.c.updated_by)


def _meta(row: Any) -> dict[str, Any]:
    return {
        "name": row["name"],
        "contentType": row["content_type"],
        "sha256": row["sha256"],
        "size": row["size"],
        "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
        "updatedBy": row["updated_by"] or "",
    }


class WebsiteStore:
    """One engine per process, built once in ``create_app``."""

    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def image_meta(self) -> dict[str, dict[str, Any]]:
        """Every stored image's description, without its bytes."""
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(*_META))).mappings().all()
        return {r["name"]: _meta(r) for r in rows}

    async def get_image(self, name: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(website_image).where(website_image.c.name == name)
            )).mappings().first()
        if row is None:
            return None
        return {**_meta(row), "data": bytes(row["data"])}

    async def put_image(self, name: str, data: bytes, content_type: str, *,
                        actor: str = "") -> dict[str, Any]:
        row = {
            "name": name,
            "content_type": content_type,
            "data": data,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "updated_at": datetime.now(timezone.utc),
            "updated_by": actor or None,
        }
        stmt = pg_insert(website_image).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=[website_image.c.name],
            set_={k: stmt.excluded[k] for k in row if k != "name"},
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)
        return _meta(row)

    async def delete_image(self, name: str) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(delete(website_image).where(website_image.c.name == name))
        return bool(result.rowcount)


def make_website_store(settings: Settings) -> Optional[WebsiteStore]:
    """A store when a database is configured, else None (no images)."""
    if not settings.store_enabled:
        return None
    return WebsiteStore(settings.database_url)
