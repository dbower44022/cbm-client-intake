"""Delegated Gmail access for the Communications integration.

One :class:`GmailClient` per mailbox: the shared Google service account (the
same one the Directory mailbox check/creation uses) mints a short-lived access
token with domain-wide delegation, impersonating exactly ONE ``@cbmentors.org``
user (``subject``). Which mailbox that is comes from the caller:

- the sync worker passes each enumerated manager's ``cbmEmail``;
- the web endpoints derive it ONLY from the signed-in session's CRM identity —
  never from request input.

That subject rule is the control that scopes a domain-wide grant down to
"your own mailbox only" — see prds/communications-gmail-integration.md §3.2.

Plain REST via httpx (like :mod:`core.google_directory`) — no
google-api-python-client dependency. Every impersonated access is logged.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.gmail")

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailError(Exception):
    """Any Gmail API / auth failure."""


class HistoryExpiredError(GmailError):
    """The stored historyId is too old (Gmail 404) — do a date-window backfill."""


def resolve_gmail_service_account(
    settings: Any, db_config: Optional[dict[str, Any]] = None
) -> Optional[dict[str, Any]]:
    """The service-account key dict for Gmail delegation, or ``None``.

    Same two sources as the Directory integration — the in-app Email-Setup
    config (DB) first, else the ``GOOGLE_SERVICE_ACCOUNT_JSON`` env var — but
    NOT gated on ``google_directory_check`` (Gmail has its own flags).
    """
    raw = None
    if db_config and db_config.get("service_account_json"):
        raw = db_config["service_account_json"]
    elif getattr(settings, "google_service_account_json", ""):
        raw = settings.google_service_account_json
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning("Google service-account JSON is not valid JSON — Gmail disabled")
        return None


class GmailClient:
    """Gmail REST for ONE mailbox, authenticated by delegated impersonation."""

    def __init__(
        self, service_account_info: dict[str, Any], mailbox: str, timeout: int = 20
    ) -> None:
        self.mailbox = mailbox
        self._info = service_account_info
        self._timeout = timeout
        self._tokens: dict[str, tuple[str, float]] = {}  # scope -> (token, expiry)

    # --- auth -----------------------------------------------------------

    async def _token(self, scope: str) -> str:
        cached = self._tokens.get(scope)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account

            def mint() -> tuple[str, float]:
                creds = service_account.Credentials.from_service_account_info(
                    self._info, scopes=[scope], subject=self.mailbox
                )
                creds.refresh(Request())
                expiry = creds.expiry.timestamp() if creds.expiry else time.time() + 1800
                return creds.token, expiry

            token, expiry = await asyncio.to_thread(mint)
        except Exception as exc:  # bad key, delegation not authorized, network, …
            raise GmailError(f"Gmail auth failed for {self.mailbox}: {exc}") from exc
        self._tokens[scope] = (token, expiry)
        log.info("gmail access as %s (scope=%s)", self.mailbox, scope.rsplit(".", 1)[-1])
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        scope: str = GMAIL_READONLY_SCOPE,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        token = await self._token(scope)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(
                    method,
                    f"{_BASE}{path}",
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise GmailError(f"Gmail request failed ({path}): {exc}") from exc
        if resp.status_code == 404 and path.startswith("/history"):
            raise HistoryExpiredError(f"historyId expired for {self.mailbox}")
        if resp.status_code >= 400:
            raise GmailError(
                f"Gmail {method} {path} for {self.mailbox}: HTTP {resp.status_code} "
                f"{resp.text[:300]}"
            )
        return resp.json() if resp.content else {}

    # --- reads ------------------------------------------------------------

    async def profile(self) -> dict[str, Any]:
        """``{"emailAddress", "historyId", ...}`` — the initial sync cursor."""
        return await self._request("GET", "/profile")

    async def list_history(
        self, start_history_id: str, page_token: Optional[str] = None
    ) -> dict[str, Any]:
        """One page of mailbox history (messageAdded only). Raises
        :class:`HistoryExpiredError` when the cursor is too old."""
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": 500,
        }
        if page_token:
            params["pageToken"] = page_token
        return await self._request("GET", "/history", params=params)

    async def list_messages(
        self, query: str, page_token: Optional[str] = None, max_results: int = 100
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        return await self._request("GET", "/messages", params=params)

    async def get_message(self, message_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/messages/{message_id}", params={"format": "full"}
        )

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/threads/{thread_id}", params={"format": "full"}
        )

    # --- send -------------------------------------------------------------

    async def send(
        self, mime_message: EmailMessage, thread_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Send as this mailbox. ``thread_id`` keeps a reply on its Gmail thread."""
        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
        body: dict[str, Any] = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id
        result = await self._request(
            "POST", "/messages/send", scope=GMAIL_SEND_SCOPE, json_body=body
        )
        log.info("gmail send as %s -> message %s", self.mailbox, result.get("id"))
        return result


# --- message parsing --------------------------------------------------------


@dataclass
class ParsedGmailMessage:
    """The fields the pipeline needs from a ``messages.get format=full`` payload."""

    gmail_id: str
    thread_id: str
    rfc_message_id: str  # RFC822 Message-ID (global dedup key); falls back to gmail id
    in_reply_to: str
    references: str
    subject: str
    from_address: str
    from_name: str
    to_addresses: list[str] = field(default_factory=list)
    cc_addresses: list[str] = field(default_factory=list)
    sent_at: str = ""  # "YYYY-MM-DD HH:MM:SS" UTC (from internalDate)
    snippet: str = ""
    body_text: str = ""
    body_html: str = ""

    @property
    def all_addresses(self) -> set[str]:
        out = {self.from_address} | set(self.to_addresses) | set(self.cc_addresses)
        return {a for a in out if a}


def _walk_parts(payload: dict[str, Any]):
    yield payload
    for part in payload.get("parts") or []:
        yield from _walk_parts(part)


def _decode_body(part: dict[str, Any]) -> str:
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — malformed part; skip it
        return ""


def _clean_msgid(value: str) -> str:
    return value.strip().strip("<>").strip()


def parse_message(raw: dict[str, Any]) -> ParsedGmailMessage:
    """Flatten a Gmail message resource into :class:`ParsedGmailMessage`."""
    payload = raw.get("payload") or {}
    headers = {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in payload.get("headers") or []
    }
    from_name, from_addr = parseaddr(headers.get("from", ""))
    text, html = "", ""
    for part in _walk_parts(payload):
        mime = (part.get("mimeType") or "").lower()
        if mime == "text/plain" and not text:
            text = _decode_body(part)
        elif mime == "text/html" and not html:
            html = _decode_body(part)
    # internalDate is epoch millis UTC — normalize to the CRM datetime format.
    sent_at = ""
    if raw.get("internalDate"):
        try:
            sent_at = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.gmtime(int(raw["internalDate"]) / 1000)
            )
        except (ValueError, TypeError):
            pass
    return ParsedGmailMessage(
        gmail_id=raw.get("id", ""),
        thread_id=raw.get("threadId", ""),
        rfc_message_id=_clean_msgid(headers.get("message-id", "")) or raw.get("id", ""),
        in_reply_to=_clean_msgid(headers.get("in-reply-to", "")),
        references=headers.get("references", "").strip(),
        subject=headers.get("subject", ""),
        from_address=from_addr.lower(),
        from_name=from_name,
        to_addresses=[a.lower() for _, a in getaddresses([headers.get("to", "")]) if a],
        cc_addresses=[a.lower() for _, a in getaddresses([headers.get("cc", "")]) if a],
        sent_at=sent_at,
        snippet=raw.get("snippet", ""),
        body_text=text,
        body_html=html,
    )


# --- query building ----------------------------------------------------------

_QUERY_CHUNK = 20  # addresses per Gmail query (keeps the q string well under limits)


def address_queries(addresses: list[str], extra: str = "") -> list[str]:
    """Gmail search queries matching mail to/from any of ``addresses``.

    ``{from:a to:a cc:a}`` braces are Gmail's OR group. Chunked so a large
    address book never overflows the ``q`` parameter; run each query and union
    the results.
    """
    clean = sorted({a.strip().lower() for a in addresses if a and "@" in a})
    queries = []
    for i in range(0, len(clean), _QUERY_CHUNK):
        chunk = clean[i : i + _QUERY_CHUNK]
        terms = " ".join(f"from:{a} to:{a} cc:{a}" for a in chunk)
        q = "{" + terms + "}"
        if extra:
            q = f"{q} {extra}"
        queries.append(q)
    return queries


def build_mime(
    *,
    sender: str,
    to: list[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc: Optional[list[str]] = None,
    in_reply_to: str = "",
    references: str = "",
) -> EmailMessage:
    """A sendable MIME message. Reply threading = In-Reply-To + References."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = f"<{_clean_msgid(in_reply_to)}>"
        refs = references.strip()
        ref_id = f"<{_clean_msgid(in_reply_to)}>"
        msg["References"] = f"{refs} {ref_id}".strip() if refs else ref_id
    msg.set_content(body_text or _html_to_text(body_html or ""))
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return msg


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
