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

import base64
import logging
from typing import Any, Optional, Protocol

import httpx

log = logging.getLogger("cbm_intake.espo")


class EspoError(Exception):
    """A create/read against EspoCRM failed."""


class EspoApi(Protocol):
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def update(
        self, entity: str, record_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def find_one(
        self, entity: str, attribute: str, value: str, select: str = "id"
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

    async def metadata_enum_options(
        self, entity: str, field: str
    ) -> Optional[list[str]]: ...


class EspoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: int = 20,
        *,
        auth_headers: Optional[dict[str, str]] = None,
    ) -> None:
        self._base = base_url.rstrip("/") + "/api/v1"
        # Either the shared service API key (X-Api-Key) or, for the assignment
        # tool, a per-user ``Espo-Authorization`` token header so EspoCRM runs
        # the request as that logged-in user and enforces their ACL.
        self._headers = auth_headers if auth_headers is not None else {"X-Api-Key": api_key}
        self._timeout = timeout

    @classmethod
    def for_user_token(
        cls, base_url: str, user_name: str, token: str, timeout: int = 20
    ) -> "EspoClient":
        """Build a client that authenticates as ``user_name`` via their auth token.

        EspoCRM accepts the login auth token in place of the password in the
        ``Espo-Authorization`` header (base64 of ``userName:token``), flagged by
        ``Espo-Authorization-By-Token``. Requests then run as that user.
        """
        cred = base64.b64encode(f"{user_name}:{token}".encode()).decode()
        return cls(
            base_url,
            timeout=timeout,
            auth_headers={
                "Espo-Authorization": cred,
                "Espo-Authorization-By-Token": "true",
            },
        )

    async def get(
        self, entity: str, record_id: str, select: Optional[str] = None
    ) -> dict[str, Any]:
        params = {"select": select} if select else None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/{entity}/{record_id}", params=params, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"get {entity}/{record_id} failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    async def list(
        self,
        entity: str,
        *,
        where: Optional[list[dict[str, Any]]] = None,
        select: Optional[str] = None,
        max_size: int = 50,
        offset: int = 0,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> dict[str, Any]:
        """List records. Returns the raw EspoCRM ``{"total", "list"}`` envelope."""
        params: list[tuple[str, str]] = [("maxSize", str(max_size))]
        if offset:
            params.append(("offset", str(offset)))
        if select:
            params.append(("select", select))
        if order_by:
            params.append(("orderBy", order_by))
        if order:
            params.append(("order", order))
        for i, clause in enumerate(where or []):
            params.append((f"where[{i}][type]", clause["type"]))
            params.append((f"where[{i}][attribute]", clause["attribute"]))
            if "value" in clause:
                value = clause["value"]
                if isinstance(value, (list, tuple)):
                    # Array filters (e.g. type=in) need indexed value params.
                    for j, item in enumerate(value):
                        params.append((f"where[{i}][value][{j}]", str(item)))
                else:
                    params.append((f"where[{i}][value]", str(value)))
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/{entity}", params=params, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"list {entity} failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    async def list_related(
        self,
        entity: str,
        record_id: str,
        link: str,
        *,
        select: Optional[str] = None,
        max_size: int = 200,
    ) -> dict[str, Any]:
        """List the records on a hasMany/manyMany link of ``entity/record_id``."""
        params: list[tuple[str, str]] = [("maxSize", str(max_size))]
        if select:
            params.append(("select", select))
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/{entity}/{record_id}/{link}",
                params=params,
                headers=self._headers,
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"list_related {entity}/{record_id}/{link} failed: "
                f"HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

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

    async def update(
        self, entity: str, record_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.put(
                f"{self._base}/{entity}/{record_id}", json=payload, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"update {entity}/{record_id} failed: "
                f"HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    async def find_one(
        self, entity: str, attribute: str, value: str, select: str = "id"
    ) -> Optional[dict[str, Any]]:
        params = [
            ("select", select),
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

    async def metadata(self, key: str) -> Any:
        """Fetch an arbitrary EspoCRM metadata key (e.g. an entity's field defs)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/Metadata", params={"key": key}, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"metadata {key} failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()

    async def metadata_enum_options(
        self, entity: str, field: str
    ) -> Optional[list[str]]:
        """The live option set of an enum/multiEnum field, for schema-drift checks.

        Returns None if the field/options aren't found (so callers can skip it).
        """
        params = {"key": f"entityDefs.{entity}.fields.{field}.options"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/Metadata", params=params, headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"metadata {entity}.{field} failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        options = resp.json()
        return options if isinstance(options, list) else None

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

    async def update(
        self, entity: str, record_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        log.info("DRY_RUN update %s/%s  payload=%s", entity, record_id, payload)
        return {"id": record_id, **payload}

    async def find_one(
        self, entity: str, attribute: str, value: str, select: str = "id"
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

    async def metadata_enum_options(self, entity: str, field: str):
        # No live CRM to validate against; None => callers skip enum sanitization.
        log.info("DRY_RUN metadata_enum_options %s.%s -> None", entity, field)
        return None
