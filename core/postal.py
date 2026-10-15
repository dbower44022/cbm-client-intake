"""The mail vendor behind the postcard kind (build plan § 3.2).

One interface, two clients:

* :class:`DryRunPostalClient` — the default. Mails nothing, costs nothing,
  accepts every piece with a ``dryrun-`` id, and lets the application render the
  piece preview itself (the QR and the merge variables are the artefact).
* :class:`LobPostalClient` — the one real adapter, written from Lob's published
  API (postcards, US verifications, webhooks) and **never yet run against it**:
  question 4 of the plan (which vendor) is Doug's, and the account does not
  exist. A real key with ``POSTAL_TEST_MODE`` on uses Lob's test environment,
  which runs the whole pipeline including the callback and prints nothing.

The idempotency key on every create is the touch's id, so a worker that dies
between the vendor's accept and our own write re-sends the same key and gets the
same piece back — that key is what stops a double mailing.

Prices are not in the code: ``POSTAL_UNIT_COST`` is the per-piece figure from the
vendor's price sheet, set at /setup when the vendor is chosen.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import httpx

from .config import Settings

log = logging.getLogger("cbm_intake.postal")

#: Test seam: monkeypatched so backoff tests don't sleep for real.
_sleep = asyncio.sleep

LOB_BASE_URL = "https://api.lob.com/v1"
PROVIDER_DRYRUN = "dryrun"
PROVIDER_LOB = "lob"

EVENT_DELIVERED = "delivered"
EVENT_RETURNED = "returned"
EVENT_OTHER = "other"


class PostalError(Exception):
    """Any vendor API or transport failure."""


class PostalAuthError(PostalError):
    """The key was rejected or is missing — a configuration problem."""


class PostalSignatureError(PostalError):
    """An inbound event whose signature does not verify."""


@dataclass(frozen=True)
class Address:
    """A postal address as the vendor wants it. ``name`` is the addressee line
    printed on the card — the business name for a prospect record."""
    name: str
    line1: str
    city: str
    state: str
    postal_code: str
    line2: str = ""
    country: str = "US"

    def is_complete(self) -> bool:
        return bool(self.name and self.line1 and self.city and self.state and self.postal_code)


@dataclass(frozen=True)
class Piece:
    """What the vendor accepted."""
    id: str
    status: str
    expected_delivery: Optional[str] = None
    preview_url: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PostalEvent:
    """One delivery event the vendor reported about one piece."""
    piece_id: str
    kind: str                  # EVENT_DELIVERED | EVENT_RETURNED | EVENT_OTHER
    vendor_status: str
    occurred_at: Optional[str] = None


class PostalClient(Protocol):
    provider: str

    async def create_postcard(
        self, *, idempotency_key: str, to: Address, template: str, size: str,
        merge_variables: dict[str, Any], metadata: dict[str, str],
    ) -> Piece: ...

    async def verify_address(self, address: Address) -> dict[str, Any]: ...

    def parse_events(self, *, headers: dict[str, str], body: bytes, secret: str) -> list[PostalEvent]: ...


class DryRunPostalClient:
    """Mails nothing. Every create is accepted; the piece id carries the key so a
    retry reads the same way a vendor's idempotent replay would."""

    provider = PROVIDER_DRYRUN

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create_postcard(
        self, *, idempotency_key: str, to: Address, template: str, size: str,
        merge_variables: dict[str, Any], metadata: dict[str, str],
    ) -> Piece:
        if not to.is_complete():
            raise PostalError("The address is incomplete; nothing to mail to.")
        record = {"key": idempotency_key, "to": to, "template": template, "size": size,
                  "merge_variables": merge_variables, "metadata": metadata}
        self.created.append(record)
        log.info("DRY_RUN postcard %s to %s (%s)", idempotency_key, to.name, size or "default")
        return Piece(id=f"dryrun-{idempotency_key}", status="accepted (dry run)", raw={})

    async def verify_address(self, address: Address) -> dict[str, Any]:
        return {"deliverability": "unknown", "note": "Address verification runs only with a real vendor."}

    def parse_events(self, *, headers: dict[str, str], body: bytes, secret: str) -> list[PostalEvent]:
        """The dry run signs its own events the same way the real adapter
        verifies them, so a signed test post exercises the callback end to end."""
        _verify_hmac(headers, body, secret)
        data = json.loads(body.decode("utf-8") or "{}")
        events = data if isinstance(data, list) else [data]
        out: list[PostalEvent] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            kind = str(ev.get("event") or "").lower()
            out.append(PostalEvent(
                piece_id=str(ev.get("piece_id") or ""),
                kind=kind if kind in (EVENT_DELIVERED, EVENT_RETURNED) else EVENT_OTHER,
                vendor_status=str(ev.get("status") or kind),
                occurred_at=ev.get("at"),
            ))
        return out


def sign_event(body: bytes, secret: str, timestamp: Optional[str] = None) -> dict[str, str]:
    """Headers for a signed event in the scheme both clients verify —
    ``{timestamp}.{body}`` under HMAC-SHA256, hex. Used by the dry run's
    simulated returns and by tests."""
    ts = timestamp or str(int(time.time()))
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"Lob-Signature": mac, "Lob-Signature-Timestamp": ts}


def _verify_hmac(headers: dict[str, str], body: bytes, secret: str) -> None:
    if not secret:
        raise PostalSignatureError("No webhook secret is configured; events are refused.")
    lower = {k.lower(): v for k, v in headers.items()}
    signature = lower.get("lob-signature", "")
    ts = lower.get("lob-signature-timestamp", "")
    if not signature or not ts:
        raise PostalSignatureError("The event carries no signature.")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PostalSignatureError("The event's signature does not verify.")


class LobPostalClient:
    """Lob's REST API, authenticated by HTTP Basic with the key as the username.
    Written from the published API; unrun against the real service."""

    provider = PROVIDER_LOB

    def __init__(self, api_key: str, *, base_url: str = LOB_BASE_URL, timeout: int = 30) -> None:
        if not api_key:
            raise PostalAuthError("A Lob API key is required.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _request(self, method: str, path: str, *, json_body: Optional[dict] = None,
                       headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        last: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, auth=(self._key, "")) as http:
                    resp = await http.request(method, url, json=json_body, headers=headers or {})
            except httpx.HTTPError as exc:
                last = exc
                await _sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code in (401, 403):
                raise PostalAuthError(f"Lob rejected the API key (HTTP {resp.status_code}).")
            if resp.status_code == 429 or resp.status_code >= 500:
                last = PostalError(f"Lob answered HTTP {resp.status_code}: {resp.text[:300]}")
                await _sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code >= 400:
                raise PostalError(f"Lob refused the request (HTTP {resp.status_code}): {resp.text[:300]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise PostalError("Lob answered with a body that is not JSON.") from exc
        raise PostalError(f"Lob could not be reached: {last}")

    async def create_postcard(
        self, *, idempotency_key: str, to: Address, template: str, size: str,
        merge_variables: dict[str, Any], metadata: dict[str, str],
    ) -> Piece:
        if not to.is_complete():
            raise PostalError("The address is incomplete; nothing to mail to.")
        if not template:
            raise PostalError("A postcard campaign needs the vendor's template id.")
        body: dict[str, Any] = {
            "to": {
                "name": to.name[:40], "address_line1": to.line1[:64],
                "address_line2": to.line2[:64] or None, "address_city": to.city[:200],
                "address_state": to.state[:2], "address_zip": to.postal_code[:11],
                "address_country": to.country or "US",
            },
            "front": template, "back": template,
            "size": size or "4x6",
            "merge_variables": merge_variables,
            "metadata": {k: str(v)[:500] for k, v in metadata.items()},
        }
        data = await self._request("POST", "/postcards", json_body=body,
                                   headers={"Idempotency-Key": idempotency_key})
        return Piece(
            id=str(data.get("id") or ""), status=str(data.get("status") or "created"),
            expected_delivery=data.get("expected_delivery_date"),
            preview_url=data.get("url"), raw=data,
        )

    async def verify_address(self, address: Address) -> dict[str, Any]:
        data = await self._request("POST", "/us_verifications", json_body={
            "primary_line": address.line1, "secondary_line": address.line2 or None,
            "city": address.city, "state": address.state, "zip_code": address.postal_code,
        })
        return {"deliverability": data.get("deliverability", "unknown"), "raw": data}

    def parse_events(self, *, headers: dict[str, str], body: bytes, secret: str) -> list[PostalEvent]:
        _verify_hmac(headers, body, secret)
        data = json.loads(body.decode("utf-8") or "{}")
        event_type = str(((data.get("event_type") or {}).get("id")) or "").lower()
        piece = data.get("body") or {}
        if event_type.endswith("delivered"):
            kind = EVENT_DELIVERED
        elif "returned" in event_type:
            kind = EVENT_RETURNED
        else:
            kind = EVENT_OTHER
        return [PostalEvent(piece_id=str(piece.get("id") or ""), kind=kind,
                            vendor_status=event_type, occurred_at=data.get("date_created"))]


def make_client(settings: Settings) -> PostalClient:
    """The vendor client the settings describe. The dry run needs nothing; a
    real provider without a key falls back to the dry run with a warning, so a
    half-configured deployment can never mail."""
    if settings.postal_provider == PROVIDER_LOB:
        if not settings.postal_api_key:
            log.warning("POSTAL_PROVIDER=lob but no POSTAL_API_KEY; using the dry run.")
            return DryRunPostalClient()
        return LobPostalClient(settings.postal_api_key)
    return DryRunPostalClient()


def estimated_cost(settings: Settings, pieces: int) -> float:
    """pieces × the price-sheet figure (ruling 13). The dry run is zero."""
    if settings.postal_provider == PROVIDER_DRYRUN:
        return 0.0
    return round(pieces * float(settings.postal_unit_cost or 0.0), 2)
