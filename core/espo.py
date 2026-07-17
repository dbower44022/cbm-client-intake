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
import json
import logging
import re
from typing import Any, Optional, Protocol

import httpx

log = logging.getLogger("cbm_intake.espo")


class EspoError(Exception):
    """A create/read against EspoCRM failed."""


_HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")


def _humanize_field(name: str) -> str:
    """``howDidYouHearAboutCBM`` → ``How Did You Hear About CBM``."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return spaced[:1].upper() + spaced[1:]


def validation_message(exc: Exception) -> Optional[str]:
    """A plain-language message when ``exc`` is an EspoCRM 400 validation
    rejection, else ``None``.

    :class:`EspoError` messages embed ``HTTP <status> <body>``; a
    ``validationFailure`` body names the field and the failed rule
    (``{"messageTranslation": {"label": "validationFailure", "data":
    {"field": ..., "type": ...}}}``). Routers use this to answer with a
    readable 400 ("the CRM did not accept field X") instead of surfacing the
    raw error as a 502/504 — a bad value is the caller's data, not a server
    fault. Returns ``None`` (→ keep the generic handling) for anything that
    isn't provably a validation failure.
    """
    text = str(exc)
    m = _HTTP_STATUS_RE.search(text)
    if not m or m.group(1) != "400":
        return None
    start = text.find("{", m.end())
    if start < 0:
        return None
    try:
        body = json.loads(text[start:])
    except ValueError:  # body truncated or not JSON — can't classify it
        return None
    info = body.get("messageTranslation") or {}
    if info.get("label") != "validationFailure":
        return None
    data = info.get("data") or {}
    field = data.get("field")
    rule = data.get("type")
    label = f"“{_humanize_field(field)}”" if field else "one of the fields"
    reasons = {
        "valid": "has a value the CRM does not accept",
        "required": "is required and is missing",
        "maxLength": "is too long",
    }
    reason = reasons.get(rule) or (
        f"failed the CRM's “{rule}” check" if rule else "failed the CRM's validation"
    )
    return f"The CRM did not accept the save: {label} {reason}. Correct that field and try again."


# The operation prefix every EspoError message starts with ("get Entity/id
# failed: …", "relate Entity/id/link failed: …") — parsed by forbidden_hint.
_FORBIDDEN_OP_RE = re.compile(
    r"^(get|list_related|list|find|create|update|relate|unrelate)\s+([A-Za-z0-9_]+)"
)

# The EspoCRM permission each operation needs: link changes (relate/unrelate)
# require EDIT on the records being linked, not a separate grant.
_OP_PERMISSION = {
    "get": "read", "list": "read", "list_related": "read", "find": "read",
    "create": "create", "update": "edit", "relate": "edit", "unrelate": "edit",
}


def is_forbidden(exc: Exception) -> bool:
    """True when a CRM call failed with 403 — a missing ACL grant, not a
    server fault. Matches the FIRST ``HTTP <code>`` in the message (the real
    status precedes the echoed body, so a 403 quoted inside a body can't
    fool it)."""
    m = _HTTP_STATUS_RE.search(str(exc))
    return bool(m) and m.group(1) == "403"


def forbidden_hint(exc: Exception) -> Optional[str]:
    """When a CRM call was denied, name the missing permission — e.g.
    ``"read access to CClientProfile records"`` — parsed from the
    :class:`EspoError` operation prefix. Routers append this to their
    permission-denied 403s so the user (and the CRM admin they ask) can see
    exactly which grant is missing instead of a generic "no permission".
    Returns ``None`` when the operation can't be determined.
    """
    m = _FORBIDDEN_OP_RE.match(str(exc))
    if not m:
        return None
    return f"{_OP_PERMISSION[m.group(1)]} access to {m.group(2)} records"


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

    async def unrelate(
        self, entity: str, record_id: str, link: str, related_id: str
    ) -> None:
        """Remove a record from a hasMany/manyMany link (relationship DELETE).

        The id goes in the request BODY — EspoCRM's documented form. The
        path-suffix variant (…/{link}/{related_id}) 404s on crm-test
        (found live 2026-07-12 unlinking an engagement contact).
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(
                "DELETE",
                f"{self._base}/{entity}/{record_id}/{link}",
                json={"id": related_id},
                headers=self._headers,
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"unrelate {entity}/{record_id}/{link} ({related_id}) failed: "
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

    async def app_user(self) -> dict[str, Any]:
        """The ``App/user`` payload for the current auth — includes the user's
        ACL table (per-entity create/read/edit/delete levels)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base}/App/user", headers=self._headers)
        if resp.status_code >= 400:
            raise EspoError(f"App/user failed: HTTP {resp.status_code} {resp.text[:200]}")
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

    async def download_attachment(self, attachment_id: str) -> tuple[bytes, str]:
        """The attachment's raw bytes + content type. Runs under this client's
        credentials, so EspoCRM ACL-checks access against the related record —
        the browser can't reach the CRM directly, callers proxy through this."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/Attachment/file/{attachment_id}", headers=self._headers
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"download attachment {attachment_id} failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        content_type = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, content_type

    async def email_template_prepare(
        self,
        template_id: str,
        *,
        parent_type: Optional[str] = None,
        parent_id: Optional[str] = None,
        email_address: Optional[str] = None,
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """EspoCRM's server-side template render (``POST EmailTemplate/{id}/prepare``).

        The CRM resolves every placeholder itself — this app never substitutes
        (Decision ET-D1). ``parent_type``/``parent_id`` feed ``{Parent.*}`` and
        ``{<ParentType>.*}``; ``email_address`` independently resolves
        ``{Person.*}`` from a Contact/Lead/Account/User carrying that address;
        ``related_type``/``related_id`` add ONE more record to the render
        context under its own type — how ``{CMentorProfile.*}`` resolves (the
        processor only substitutes entities present in its context hash). ACL
        is enforced server-side against this client's user (403 = no template
        read access; an unreadable parent/related is silently dropped from the
        context). Returns ``{subject, body, isHtml, attachmentsIds,
        attachmentsNames}``; the attachment ids are fresh CLONES owned by the
        acting user. (Verified against crm-test EspoCRM 9.3.6, 2026-07-16/17.)
        """
        payload: dict[str, Any] = {}
        if parent_type and parent_id:
            payload["parentType"] = parent_type
            payload["parentId"] = parent_id
        if email_address:
            payload["emailAddress"] = email_address
        if related_type and related_id:
            payload["relatedType"] = related_type
            payload["relatedId"] = related_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/EmailTemplate/{template_id}/prepare",
                json=payload,
                headers=self._headers,
            )
        if resp.status_code >= 400:
            raise EspoError(
                f"prepare EmailTemplate/{template_id} failed: "
                f"HTTP {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()


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

    async def download_attachment(self, attachment_id: str) -> tuple[bytes, str]:
        # A 1x1 transparent PNG, so a dry-run photo fetch renders something.
        log.info("DRY_RUN download_attachment %s -> 1x1 png", attachment_id)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
            "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
        return png, "image/png"

    async def metadata_enum_options(self, entity: str, field: str):
        # No live CRM to validate against; None => callers skip enum sanitization.
        log.info("DRY_RUN metadata_enum_options %s.%s -> None", entity, field)
        return None

    async def email_template_prepare(
        self,
        template_id: str,
        *,
        parent_type: Optional[str] = None,
        parent_id: Optional[str] = None,
        email_address: Optional[str] = None,
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
    ) -> dict[str, Any]:
        log.info(
            "DRY_RUN email_template_prepare %s parent=%s/%s email=%s related=%s/%s",
            template_id, parent_type, parent_id, email_address, related_type, related_id,
        )
        return {
            "subject": "Dry-run template subject",
            "body": "<p>Dry-run rendered template body.</p>",
            "isHtml": True,
            "attachmentsIds": [],
            "attachmentsNames": {},
        }
