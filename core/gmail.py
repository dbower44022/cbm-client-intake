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
from email.utils import formataddr, getaddresses, parseaddr
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


class MessageGoneError(GmailError):
    """``messages.get`` 404 — the message no longer exists (deleted before the
    fetch, or a history artifact like Meet/Chat records that never fetch).
    There is nothing to ingest and nothing to lose, so the sync SKIPS it
    immediately instead of holding the cursor through retry passes and
    dead-lettering with alerts (seen live 2026-07-20: batches of these across
    two mailboxes churned the 5-pass machinery for mail that never existed)."""


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


# Bounded retries on 429/5xx (the DriveClient treatment, P1-5 F4): during a
# large backfill, quota bursts previously surfaced as runs of swallowed
# per-message failures. Retry-After is honored when Google sends it.
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = 0.5
# Sends carry bodies up to ~27 MB (attachments); the default 20s timeout could
# expire AFTER Gmail committed the send — "try again" then double-sent. A
# roomy send timeout shrinks that window (full send idempotency is out of
# scope — Gmail's API has no client-token dedup for messages.send).
SEND_TIMEOUT_SECONDS = 120


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    ra = resp.headers.get("retry-after", "")
    if ra.isdigit():
        return min(float(ra), 30.0)
    return _BACKOFF_SECONDS * (2 ** attempt)


class GmailClient:
    """Gmail REST for ONE mailbox, authenticated by delegated impersonation.

    Holds ONE ``httpx.AsyncClient`` for its lifetime (connection reuse across
    a sync pass's hundreds of calls — previously every call re-handshook TLS).
    Long-lived callers (the sync loop) should ``await client.aclose()`` when
    done; short-lived web-endpoint instances may skip it (the transport is
    closed by GC at worst).
    """

    def __init__(
        self, service_account_info: dict[str, Any], mailbox: str, timeout: int = 20
    ) -> None:
        self.mailbox = mailbox
        self._info = service_account_info
        self._timeout = timeout
        self._tokens: dict[str, tuple[str, float]] = {}  # scope -> (token, expiry)
        self._http: Optional[httpx.AsyncClient] = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

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
        timeout: Optional[float] = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        """One authorized request, with bounded backoff retries on 429/5xx
        (honoring Retry-After). ``retry=False`` for non-idempotent calls
        (send): a 5xx/timeout is ambiguous — Gmail may have committed — so
        retrying could double-send."""
        token = await self._token(scope)
        headers = {"Authorization": f"Bearer {token}"}
        attempts = _MAX_ATTEMPTS if retry else 1
        last: Optional[httpx.Response] = None
        for attempt in range(attempts):
            try:
                resp = await self._client().request(
                    method,
                    f"{_BASE}{path}",
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=timeout if timeout is not None else self._timeout,
                )
            except httpx.HTTPError as exc:
                raise GmailError(f"Gmail request failed ({path}): {exc}") from exc
            if resp.status_code == 404 and path.startswith("/history"):
                raise HistoryExpiredError(f"historyId expired for {self.mailbox}")
            if (
                resp.status_code == 404
                and method == "GET"
                and path.startswith("/messages/")
            ):
                raise MessageGoneError(
                    f"Gmail message {path.rsplit('/', 1)[-1]} no longer exists "
                    f"in {self.mailbox}"
                )
            if resp.status_code < 400:
                return resp.json() if resp.content else {}
            last = resp
            if resp.status_code not in (429,) and resp.status_code < 500:
                break
            if attempt == attempts - 1:
                break
            await asyncio.sleep(_retry_after(resp, attempt))
        assert last is not None
        raise GmailError(
            f"Gmail {method} {path} for {self.mailbox}: HTTP {last.status_code} "
            f"{last.text[:300]}"
        )

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

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """One attachment part's bytes (``users.messages.attachments.get``).
        Covered by ``gmail.readonly`` — no extra scope."""
        data = await self._request(
            "GET", f"/messages/{message_id}/attachments/{attachment_id}"
        )
        raw = data.get("data") or ""
        try:
            return base64.urlsafe_b64decode(raw + "===")
        except Exception as exc:  # malformed base64 from the API — treat as failure
            raise GmailError(
                f"Gmail attachment {attachment_id} of {message_id} did not decode: {exc}"
            ) from exc

    async def get_message_headers(self, message_id: str) -> dict[str, Any]:
        """Headers-only fetch (format=metadata) — the cheap read for questions
        like "who wrote the last message?" (the /ops awaiting-reply column)."""
        return await self._request(
            "GET", f"/messages/{message_id}", params={"format": "metadata"}
        )

    async def get_thread(
        self, thread_id: str, *, headers_only: bool = False
    ) -> dict[str, Any]:
        """One thread with its messages. ``headers_only`` (format=metadata) is
        the cheap read for questions like "who wrote the thread's last
        message?" (the /ops awaiting-reply column)."""
        return await self._request(
            "GET",
            f"/threads/{thread_id}",
            params={"format": "metadata" if headers_only else "full"},
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
        # No retries (non-idempotent) + a roomy timeout sized for ~27 MB
        # bodies — a timeout after Gmail committed used to invite a manual
        # "try again" double-send.
        result = await self._request(
            "POST", "/messages/send", scope=GMAIL_SEND_SCOPE, json_body=body,
            timeout=SEND_TIMEOUT_SECONDS, retry=False,
        )
        log.info("gmail send as %s -> message %s", self.mailbox, result.get("id"))
        return result


# --- message parsing --------------------------------------------------------


@dataclass
class GmailAttachment:
    """One non-body part of a message (``messages.get format=full``).

    ``part_index`` is the part's position in the depth-first walk of the MIME
    tree — stable for a given stored message, so it doubles as the durable
    per-attachment key (the ledger's ``(rfc_message_id, part_index)``).
    ``is_attachment`` is True only for REAL attachments (Content-Disposition:
    attachment) — inline images (cid-referenced, signature logos) stay
    viewable through View original but are never auto-filed (Doug's ruling
    2026-07-21).
    """

    part_index: int
    filename: str
    mime_type: str
    size: int
    attachment_id: str
    disposition: str = ""  # "attachment" | "inline" | "" (header absent)
    content_id: str = ""   # the Content-ID (without <>), for cid: resolution

    @property
    def is_attachment(self) -> bool:
        # The ruling's filter, applied by spirit: anything inline (explicit
        # disposition, or cid-referenced with no disposition header) never
        # qualifies; an explicit "attachment" always does; a named part with
        # NO disposition header at all (some MTAs omit it) still counts —
        # requiring the header verbatim would silently drop real documents.
        if self.disposition == "attachment":
            return True
        if self.disposition:  # "inline" or anything else explicit
            return False
        return bool(self.filename) and not self.content_id

    @property
    def is_inline_image(self) -> bool:
        return bool(self.content_id) and self.mime_type.startswith("image/")


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
    # (display name, address) pairs — names as the headers carried them, so the
    # conversation participants list can show people, not just addresses.
    to_named: list[tuple[str, str]] = field(default_factory=list)
    cc_named: list[tuple[str, str]] = field(default_factory=list)
    label_ids: list[str] = field(default_factory=list)  # e.g. SENT, DRAFT, INBOX
    sent_at: str = ""  # "YYYY-MM-DD HH:MM:SS" UTC (from internalDate)
    snippet: str = ""
    body_text: str = ""
    body_html: str = ""
    # Every non-body part with retrievable bytes (real attachments AND inline
    # parts). Filter with .real_attachments for the auto-filing pipeline.
    attachments: list[GmailAttachment] = field(default_factory=list)

    @property
    def real_attachments(self) -> list[GmailAttachment]:
        """Only Content-Disposition: attachment parts (the auto-file set)."""
        return [a for a in self.attachments if a.is_attachment]

    @property
    def all_addresses(self) -> set[str]:
        out = {self.from_address} | set(self.to_addresses) | set(self.cc_addresses)
        return {a for a in out if a}


_BOUNCE_SENDER_RE = re.compile(r"^(mailer-daemon|postmaster)@", re.IGNORECASE)
_BOUNCE_SUBJECT_RE = re.compile(
    r"delivery status notification|undeliverable|returned mail|"
    r"mail delivery (?:failed|failure|subsystem)|failure notice|"
    r"delivery (?:has )?failed|delivery incomplete|address not found",
    re.IGNORECASE,
)


def looks_like_bounce(from_address: str, subject: str) -> bool:
    """True when a message is a delivery-status bounce (mailer-daemon /
    postmaster sender, or a DSN-style subject).

    Bounces land IN the original Gmail thread, so thread-based views (the
    /ops conversation) receive them — but they read as an ordinary reply
    unless classified, and an admin believes their reply was delivered (the
    2026-07-21 allen.ingram incident). Sender match is the strong signal;
    the subject patterns catch non-Gmail MTAs with odd sender addresses —
    a rare cosmetic false positive beats a missed real bounce.
    """
    if _BOUNCE_SENDER_RE.match((from_address or "").strip()):
        return True
    return bool(_BOUNCE_SUBJECT_RE.search(subject or ""))


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


def _part_headers(part: dict[str, Any]) -> dict[str, str]:
    return {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in part.get("headers") or []
    }


def _collect_attachments(payload: dict[str, Any]) -> list[GmailAttachment]:
    """Every part with retrievable bytes (an ``attachmentId``), indexed by its
    depth-first position. Bodies (the first text/plain + text/html) carry
    their data inline and have no attachmentId, so they never appear here."""
    out: list[GmailAttachment] = []
    for idx, part in enumerate(_walk_parts(payload)):
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            continue
        headers = _part_headers(part)
        disposition = headers.get("content-disposition", "").split(";", 1)[0]
        disposition = disposition.strip().lower()
        out.append(
            GmailAttachment(
                part_index=idx,
                filename=(part.get("filename") or "").strip(),
                mime_type=(part.get("mimeType") or "application/octet-stream").lower(),
                size=int(body.get("size") or 0),
                attachment_id=attachment_id,
                disposition=disposition,
                content_id=_clean_msgid(headers.get("content-id", "")),
            )
        )
    return out


def parse_message(raw: dict[str, Any]) -> ParsedGmailMessage:
    """Flatten a Gmail message resource into :class:`ParsedGmailMessage`."""
    payload = raw.get("payload") or {}
    headers = {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in payload.get("headers") or []
    }
    from_name, from_addr = parseaddr(headers.get("from", ""))
    to_named = [(n, a.lower()) for n, a in getaddresses([headers.get("to", "")]) if a]
    cc_named = [(n, a.lower()) for n, a in getaddresses([headers.get("cc", "")]) if a]
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
        to_addresses=[a for _, a in to_named],
        cc_addresses=[a for _, a in cc_named],
        to_named=to_named,
        cc_named=cc_named,
        label_ids=list(raw.get("labelIds") or []),
        sent_at=sent_at,
        snippet=raw.get("snippet", ""),
        body_text=text,
        body_html=html,
        attachments=_collect_attachments(payload),
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
    bcc: Optional[list[str]] = None,
    in_reply_to: str = "",
    references: str = "",
    sender_name: str = "",
    attachments: Optional[list[tuple[str, str, bytes]]] = None,
) -> EmailMessage:
    """A sendable MIME message. Reply threading = In-Reply-To + References.

    ``sender_name`` puts a display name on the From header ("Doug Bower
    <doug.bower@…>") — without it the write-through ingest of a tab-sent
    message stores a bare address as the sender, and the conversation view
    can't say WHO on the mentor team wrote it.

    ``attachments`` = ``(filename, content_type, data)`` triples; adding any
    turns the message multipart/mixed around the text/html alternative."""
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        # Gmail delivers to Bcc recipients listed on the raw message and strips
        # the header from the copies it hands to To/Cc recipients.
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = f"<{_clean_msgid(in_reply_to)}>"
        refs = references.strip()
        ref_id = f"<{_clean_msgid(in_reply_to)}>"
        msg["References"] = f"{refs} {ref_id}".strip() if refs else ref_id
    msg.set_content(body_text or _html_to_text(body_html or ""))
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    for filename, content_type, data in attachments or []:
        maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
        msg.add_attachment(
            data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=filename or "attachment",
        )
    return msg


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
