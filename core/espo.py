"""Minimal EspoCRM REST client.

Self-contained (the repository stays independent of the crmbuilder codebase,
whose ``espo_impl/core/api_client.py`` proves the same pattern). Authenticates
with the dedicated intake API user's key in the ``X-Api-Key`` header
(Technical Design §3.2).

``DryRunEspoClient`` implements the same interface without touching EspoCRM:
it returns synthetic ids and logs the would-be payloads, so the form runs
end-to-end locally without a live instance.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

import httpx

log = logging.getLogger("cbm_intake.espo")


class EspoError(Exception):
    """A create/read against EspoCRM failed."""


class EspoApi(Protocol):
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def find_one(
        self, entity: str, attribute: str, value: str
    ) -> Optional[dict[str, Any]]: ...
    async def relate(
        self, entity: str, record_id: str, link: str, related_id: str
    ) -> None: ...
    async def upload_attachment(
        self,
        *,
        filename: str,
        content_type: str,
        data_base64: str,
        related_type: str,
        field: str,
    ) -> str: ...


class EspoClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 20) -> None:
        self._base = base_url.rstrip("/") + "/api/v1"
        self._headers = {"X-Api-Key": api_key}
        self._timeout = timeout

    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/{entity}", json=payload, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"create {entity} failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    async def find_one(
        self, entity: str, attribute: str, value: str
    ) -> Optional[dict[str, Any]]:
        params = [
            ("select", "id"),
            ("maxSize", "1"),
            ("where[0][type]", "equals"),
            ("where[0][attribute]", attribute),
            ("where[0][value]", value),
        ]
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/{entity}", params=params, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"find {entity} failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        rows = resp.json().get("list") or []
        return rows[0] if rows else None

    async def relate(
        self, entity: str, record_id: str, link: str, related_id: str
    ) -> None:
        """Add a record to a hasMany/manyMany link (EspoCRM relationship POST)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/{entity}/{record_id}/{link}",
                json={"id": related_id},
                headers=self._headers,
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"relate {entity}/{record_id}/{link} failed: "
                f"HTTP {resp.status_code} {resp.text[:300]}"
            )

    async def upload_attachment(
        self,
        *,
        filename: str,
        content_type: str,
        data_base64: str,
        related_type: str,
        field: str,
    ) -> str:
        # EspoCRM expects the file as a data URL; the attachment is bound to the
        # target entity/field so it links when the record is created.
        body = {
            "name": filename,
            "type": content_type,
            "role": "Attachment",
            "relatedType": related_type,
            "field": field,
            "file": f"data:{content_type};base64,{data_base64}",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/Attachment", json=body, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"upload attachment failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()["id"]


class DryRunEspoClient:
    """No-op client for local development; never contacts EspoCRM."""

    def __init__(self) -> None:
        self._counter = 0

    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        fake_id = f"dryrun-{entity.lower()}-{self._counter:04d}"
        log.info("DRY_RUN create %s -> %s  payload=%s", entity, fake_id, payload)
        return {"id": fake_id, **payload}

    async def find_one(
        self, entity: str, attribute: str, value: str
    ) -> Optional[dict[str, Any]]:
        log.info("DRY_RUN find_one %s %s=%s -> None", entity, attribute, value)
        return None

    async def relate(
        self, entity: str, record_id: str, link: str, related_id: str
    ) -> None:
        log.info("DRY_RUN relate %s/%s/%s -> %s", entity, record_id, link, related_id)

    async def upload_attachment(
        self,
        *,
        filename: str,
        content_type: str,
        data_base64: str,
        related_type: str,
        field: str,
    ) -> str:
        self._counter += 1
        fake_id = f"dryrun-attachment-{self._counter:04d}"
        log.info(
            "DRY_RUN upload_attachment %s (%s, %d b64 chars) -> %s for %s.%s",
            filename, content_type, len(data_base64), fake_id, related_type, field,
        )
        return fake_id
