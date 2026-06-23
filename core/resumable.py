"""Make any orchestrator safely re-runnable — V2 Phase 1, Requirement 4.

When the worker retries a submission that failed partway, we must finish the
missing CRM records without duplicating the ones already created. Rather than
change every orchestrator, this wraps the EspoCRM client and remembers each
``create``/``upload_attachment`` it performs, keyed by entity + position in the
deterministic create sequence. On a retry the recorded id is returned instead of
creating again, so a half-finished chain converges to exactly one complete set.

``find_one`` already makes Account/Contact idempotent (the retry finds the
existing record and never reaches a create); this covers the remaining plain
creates (profiles, engagements) and attachment uploads.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from .espo import EspoApi

SaveProgress = Callable[[dict[str, Any]], Awaitable[None]]


class ResumableClient:
    """Wraps an :class:`EspoApi` to skip work already recorded in ``progress``."""

    def __init__(
        self,
        inner: EspoApi,
        progress: Optional[dict[str, Any]] = None,
        save: Optional[SaveProgress] = None,
    ) -> None:
        self._inner = inner
        self._progress: dict[str, Any] = dict(progress or {})
        self._save = save
        self._counts: dict[str, int] = {}

    def _next_key(self, kind: str) -> str:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return f"{kind}#{self._counts[kind]}"

    async def _record(self, key: str, value: Any) -> None:
        self._progress[key] = value
        if self._save is not None:
            await self._save(self._progress)

    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        key = self._next_key(f"create:{entity}")
        if key in self._progress:
            return {"id": self._progress[key], **payload}
        created = await self._inner.create(entity, payload)
        await self._record(key, created["id"])
        return created

    async def upload_attachment(self, **kwargs: Any) -> str:
        key = self._next_key("upload")
        if key in self._progress:
            return self._progress[key]
        attachment_id = await self._inner.upload_attachment(**kwargs)
        await self._record(key, attachment_id)
        return attachment_id

    # Naturally idempotent / safe to repeat — pass straight through.
    async def find_one(self, *args: Any, **kwargs: Any):
        return await self._inner.find_one(*args, **kwargs)

    async def update(self, *args: Any, **kwargs: Any):
        return await self._inner.update(*args, **kwargs)

    async def relate(self, *args: Any, **kwargs: Any):
        return await self._inner.relate(*args, **kwargs)

    async def metadata_enum_options(self, *args: Any, **kwargs: Any):
        return await self._inner.metadata_enum_options(*args, **kwargs)
