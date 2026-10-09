"""Mailing service client — Constant Contact V3 (Phase C of the mailing-list arc).

The CRM is the system of record for who may be emailed; the mailing service is
a mirror of it (plan ruling 1, ``prds/mailing-list-and-event-sponsorship-plan.md``
§ 11). This module is the whole vendor boundary: the OAuth2 helpers, the one-row
connection store with its locked rotating refresh, and the API client. Nothing
above it knows a token exists.

Integration contract (the ``core/zoom.py`` convention — keep this accurate, it is
what the next person will trust). *Read* means read from the vendor's own
developer guide; *inferred* means the vendor's reference page could not be read
by the tools used (it is script-rendered) and the shape follows the vendor's
conventions — each inferred item is owed a check against the trial account on
the first dry-run (plan § 11.10).

* **Authorise** — ``GET https://authz.constantcontact.com/oauth2/default/v1/authorize``
  with ``client_id``, ``redirect_uri`` (absolute, must match one registered on
  the application character for character), ``response_type=code``, ``scope``
  (space-delimited) and ``state`` (*read*; both addresses also read back from
  the application's own details screen 2026-10-08).
* **Token** — ``POST …/oauth2/default/v1/token`` with HTTP Basic
  ``client_id:client_secret`` and form parameters ``grant_type=authorization_code``
  + ``code`` + ``redirect_uri``, or ``grant_type=refresh_token`` +
  ``refresh_token`` (*read*; the guide's example passes them as a query string,
  which this client also does — Okta-style token endpoints accept either).
  Response: ``access_token``, ``refresh_token`` (a NEW one on every refresh —
  Rotating Refresh Tokens, the application's chosen method), ``expires_in``
  seconds, ``token_type`` ``Bearer``, ``scope``. A code lives 300 seconds, so
  the exchange happens in the callback (*read*). The access token is quoted
  as 86,400 s in prose and 28,800 s in the example (*read*, inconsistent) —
  ``expires_in`` is what is trusted.
* **A 400/401 from the token endpoint is terminal** — the grant is gone until a
  human reconnects. The store marks ``needs_reauthorisation`` and nothing
  retries it.
* **Rate limits** — 4 requests a second and 10,000 a day per API key; over
  either answers 429 with body key ``throttled`` or ``quota_exceeded``; no
  ``Retry-After`` is promised (*read*). The client paces itself at the per-second
  limit and treats a 429 as retry-once-then-report.
* **Contacts** — ``GET /contacts`` with ``lists={id}`` for a list's members and
  ``status=unsubscribed&updated_after={iso}`` for the pull (*read*);
  ``limit`` (max 500) and the next page under ``_links.next.href`` as a path to
  append to the base (*inferred*).
* **Lists** — ``GET /contact_lists`` and ``POST /contact_lists`` with ``name``
  (*inferred*).
* **Bulk import** — ``POST /activities/contacts_json_import`` with
  ``import_data`` (each item ``email`` plus the properties to set) and
  ``list_ids``; at most 40,000 contacts per call; existing contacts are updated
  only in the properties sent (*read*). Asynchronous: the response is an
  activity whose ``GET /activities/{id}`` carries ``state`` (*read*; the state
  vocabulary is *inferred*: ``initialized``/``processing``/``completed``/
  ``cancelled``/``failed``/``timed_out``).
* **Remove from a list** — ``POST /activities/remove_list_memberships`` with
  ``source.contact_ids`` and ``list_ids`` (*inferred*). Removes membership, never
  the contact (ruling: removed from the list, never deleted).
* **Account** — ``GET /account/summary``; ``organization_name`` (*inferred*).

Every failure raises :class:`MailingError`; callers treat the service as
best-effort and never fail a CRM write because of it.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Optional
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import Column, DateTime, String, Table, Text, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .store import make_async_engine, metadata

log = logging.getLogger("cbm_intake.mailing")

DEFAULT_BASE_URL = "https://api.cc.email/v3"
AUTHORIZE_URL = "https://authz.constantcontact.com/oauth2/default/v1/authorize"
TOKEN_URL = "https://authz.constantcontact.com/oauth2/default/v1/token"

#: The four scopes § 11.3 asks for. ``campaign_data`` is unused by Phase C and
#: requested now so Phase D does not force a second authorisation.
SCOPES: tuple[str, ...] = ("contact_data", "campaign_data", "account_read", "offline_access")

#: A ``state`` older than this is refused — the authorisation code it protects
#: lives 300 s, so ten minutes is generous.
STATE_MAX_AGE_SECONDS = 600
#: Refresh when the access token is inside this many seconds of expiry.
REFRESH_WINDOW_SECONDS = 300
#: ``GET /contacts`` page size (inferred; the fake enforces it so a wrong guess
#: fails a test rather than a night).
CONTACTS_PAGE = 500
LISTS_PAGE = 1000
#: Contacts per bulk-import call (read).
IMPORT_MAX = 40_000
#: 4 requests a second (read) → never start two requests closer than this.
MIN_REQUEST_INTERVAL = 0.25

#: The one connection row's key. One account per deployment (§ 11.1).
ROW_ID = "default"
STATUS_CONNECTED = "connected"
STATUS_NEEDS_REAUTH = "needs_reauthorisation"

#: Activity states that mean "finished" (inferred vocabulary).
ACTIVITY_DONE = frozenset({"completed", "cancelled", "failed", "timed_out"})

# Test seam: monkeypatched so pacing/backoff tests don't sleep for real.
_sleep = asyncio.sleep


class MailingError(Exception):
    """Any mailing-service API or transport failure."""


class MailingAuthError(MailingError):
    """The token endpoint refused the grant — a human must reconnect."""


class MailingNotConnected(MailingError):
    """No usable connection row: never connected, disconnected, or awaiting re-authorisation."""


class MailingRateLimited(MailingError):
    """429 after the one retry — the caller reports the pass as partial."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- state ------------------------------------------------------------------


def _serializer(secret: str) -> URLSafeTimedSerializer:
    if not secret:
        raise MailingError("A session secret is required to sign the authorisation state.")
    return URLSafeTimedSerializer(secret, salt="mailing-oauth-state")


def sign_state(secret: str, user_id: str) -> str:
    """The ``state`` value for one administrator's authorisation attempt."""
    return _serializer(secret).dumps({"u": user_id})


def verify_state(secret: str, state: str, user_id: str) -> None:
    """Raise :class:`MailingError` unless ``state`` is ours, fresh, and this user's."""
    try:
        data = _serializer(secret).loads(state or "", max_age=STATE_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise MailingError("The authorisation took too long; start Connect again.") from exc
    except BadSignature as exc:
        raise MailingError("The authorisation response did not come from this application.") from exc
    if not isinstance(data, dict) or data.get("u") != user_id:
        raise MailingError("The authorisation was started by a different administrator.")


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """The address the administrator's browser is sent to."""
    if not client_id:
        raise MailingError("The mailing service client ID is not set.")
    query = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
    })
    return f"{AUTHORIZE_URL}?{query}"


# --- token endpoint -----------------------------------------------------------


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str = ""


def _basic(client_id: str, client_secret: str) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


async def _token_call(
    client_id: str, client_secret: str, params: dict[str, str], *, timeout: int = 30
) -> TokenSet:
    if not (client_id and client_secret):
        raise MailingAuthError("The mailing service client ID and secret are both required.")
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            resp = await http.post(
                TOKEN_URL,
                params=params,
                headers={
                    "Authorization": _basic(client_id, client_secret),
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
    except httpx.HTTPError as exc:
        raise MailingError(
            f"Mailing service token request failed: could not reach the service "
            f"({type(exc).__name__})"
        ) from exc
    if resp.status_code in (400, 401):
        # Never echo the body — it can carry the client id.
        raise MailingAuthError(
            f"The mailing service refused the credentials (HTTP {resp.status_code}). "
            "Check the client ID and secret, or reconnect."
        )
    if resp.status_code >= 400:
        raise MailingError(f"Mailing service token request failed: HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise MailingError("Mailing service token response was not JSON.") from exc
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not access or not refresh:
        raise MailingAuthError(
            "The mailing service returned no refresh token — the offline_access "
            "scope was not granted."
        )
    ttl = int(data.get("expires_in") or 0)
    return TokenSet(
        access_token=str(access),
        refresh_token=str(refresh),
        expires_at=_now() + timedelta(seconds=max(60, ttl) if ttl else 3600),
        scope=str(data.get("scope") or ""),
    )


async def exchange_code(
    client_id: str, client_secret: str, code: str, redirect_uri: str, *, timeout: int = 30
) -> TokenSet:
    """Turn the callback's authorisation code into the first token pair."""
    return await _token_call(
        client_id, client_secret,
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        timeout=timeout,
    )


async def refresh_tokens(
    client_id: str, client_secret: str, refresh_token: str, *, timeout: int = 30
) -> TokenSet:
    """Rotate: a new access token AND a new refresh token. The old refresh token is dead."""
    return await _token_call(
        client_id, client_secret,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=timeout,
    )


def needs_refresh(expires_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """True when the access token is missing or inside the refresh window."""
    if expires_at is None:
        return True
    now = now or _now()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (expires_at - now).total_seconds() <= REFRESH_WINDOW_SECONDS


# --- the connection row -------------------------------------------------------

# One row. Tokens are Fernet ciphertext (``core/crypto``), never plain text.
# Kept by the sandbox reset (``core/sandbox_reset.KEEP_TABLES``): a connection
# crm-test lost every night would be no connection. (Migration 0030.)
mailing_connection = Table(
    "mailing_connection",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("status", String(32), nullable=False),
    Column("access_token", Text, nullable=False),
    Column("refresh_token", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("scopes", Text),
    Column("account_label", String(255)),
    Column("connected_by", String(128)),
    Column("connected_at", DateTime(timezone=True), nullable=False),
    Column("last_refresh_at", DateTime(timezone=True)),
    Column("last_error", Text),
    # Cached by the push (§ 11.5 step 2) and the pull (§ 11.6).
    Column("list_id", String(64)),
    Column("pull_cursor", DateTime(timezone=True)),
    Column("last_push_at", DateTime(timezone=True)),
    Column("last_push_summary", JSONB),
)

_PUBLIC_COLUMNS = (
    "status", "scopes", "account_label", "connected_by", "connected_at",
    "expires_at", "last_refresh_at", "last_error", "list_id", "pull_cursor",
    "last_push_at", "last_push_summary",
)


@dataclass(frozen=True)
class Connection:
    """What the Settings panel and the worker may know — never a token."""

    status: str
    account_label: Optional[str]
    connected_by: Optional[str]
    connected_at: Optional[datetime]
    expires_at: Optional[datetime]
    last_refresh_at: Optional[datetime]
    last_error: Optional[str]
    scopes: tuple[str, ...]
    list_id: Optional[str]
    pull_cursor: Optional[datetime]
    last_push_at: Optional[datetime]
    last_push_summary: Optional[dict[str, Any]]

    @property
    def usable(self) -> bool:
        return self.status == STATUS_CONNECTED

    def as_dict(self) -> dict[str, Any]:
        def _iso(v: Optional[datetime]) -> Optional[str]:
            return v.isoformat() if v else None
        return {
            "status": self.status,
            "accountLabel": self.account_label,
            "connectedBy": self.connected_by,
            "connectedAt": _iso(self.connected_at),
            "expiresAt": _iso(self.expires_at),
            "lastRefreshAt": _iso(self.last_refresh_at),
            "lastError": self.last_error,
            "scopes": list(self.scopes),
            "listId": self.list_id,
            "pullCursor": _iso(self.pull_cursor),
            "lastPushAt": _iso(self.last_push_at),
            "lastPushSummary": self.last_push_summary,
        }


def _connection_from_row(row: Any) -> Connection:
    m = row._mapping if hasattr(row, "_mapping") else row
    return Connection(
        status=m["status"],
        account_label=m.get("account_label"),
        connected_by=m.get("connected_by"),
        connected_at=m.get("connected_at"),
        expires_at=m.get("expires_at"),
        last_refresh_at=m.get("last_refresh_at"),
        last_error=m.get("last_error"),
        scopes=tuple((m.get("scopes") or "").split()),
        list_id=m.get("list_id"),
        pull_cursor=m.get("pull_cursor"),
        last_push_at=m.get("last_push_at"),
        last_push_summary=m.get("last_push_summary"),
    )


Refresher = Callable[[str, str, str], Awaitable[TokenSet]]


class ConnectionStore:
    """The single connection row, with the one-refresher-at-a-time rule.

    ``cipher`` is a ``core.crypto.SecretCipher``. Without one every token write
    is refused — the same rule the settings store applies to secrets — because a
    token stored in plain text would make a database dump a mailing-account
    takeover.
    """

    def __init__(self, database_url: str, cipher: Any = None) -> None:
        self._engine = make_async_engine(database_url)
        self._cipher = cipher

    # --- plumbing -----------------------------------------------------------

    def _encrypt(self, value: str) -> str:
        if self._cipher is None:
            raise MailingError(
                "The mailing connection cannot be stored without an encryption key "
                "(APP_ENCRYPTION_KEY)."
            )
        return self._cipher.encrypt(value)

    def _decrypt(self, value: str) -> str:
        if self._cipher is None:
            raise MailingError(
                "The mailing connection cannot be read without an encryption key "
                "(APP_ENCRYPTION_KEY)."
            )
        try:
            return self._cipher.decrypt(value)
        except Exception as exc:  # CryptoError — the key changed since the write
            raise MailingAuthError(f"The stored mailing connection is unreadable: {exc}") from exc

    async def create_all(self) -> None:
        """Tests only — deployments migrate (Alembic is the schema authority)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(lambda sync: mailing_connection.create(sync, checkfirst=True))

    async def dispose(self) -> None:
        await self._engine.dispose()

    # --- reads --------------------------------------------------------------

    async def get(self) -> Optional[Connection]:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(*[mailing_connection.c[c] for c in _PUBLIC_COLUMNS])
                    .where(mailing_connection.c.id == ROW_ID)
                )
            ).first()
        return _connection_from_row(row) if row else None

    # --- writes -------------------------------------------------------------

    async def save(
        self, tokens: TokenSet, *, account_label: str, connected_by: str, scopes: str = ""
    ) -> None:
        """Connect (or reconnect): the row becomes usable and every cache is kept."""
        now = _now()
        values = {
            "id": ROW_ID,
            "status": STATUS_CONNECTED,
            "access_token": self._encrypt(tokens.access_token),
            "refresh_token": self._encrypt(tokens.refresh_token),
            "expires_at": tokens.expires_at,
            "scopes": scopes or tokens.scope or " ".join(SCOPES),
            "account_label": (account_label or "")[:255] or None,
            "connected_by": (connected_by or "")[:128] or None,
            "connected_at": now,
            "last_refresh_at": None,
            "last_error": None,
        }
        stmt = pg_insert(mailing_connection).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[mailing_connection.c.id],
            set_={k: v for k, v in values.items() if k != "id"},
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def delete(self) -> bool:
        """Disconnect. The caches go with it — a reconnect finds the list by name again."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                mailing_connection.delete().where(mailing_connection.c.id == ROW_ID)
            )
        return bool(result.rowcount)

    async def _set(self, **values: Any) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                update(mailing_connection).where(mailing_connection.c.id == ROW_ID).values(**values)
            )

    async def set_list_id(self, list_id: str) -> None:
        await self._set(list_id=(list_id or "")[:64] or None)

    async def set_pull_cursor(self, cursor: datetime) -> None:
        await self._set(pull_cursor=cursor)

    async def record_push(self, summary: dict[str, Any]) -> None:
        await self._set(last_push_at=_now(), last_push_summary=summary)

    async def mark_needs_reauthorisation(self, error: str) -> None:
        await self._set(status=STATUS_NEEDS_REAUTH, last_error=(error or "")[:2000])

    # --- the token, with the lock -------------------------------------------

    async def access_token(
        self,
        client_id: str,
        client_secret: str,
        *,
        force: bool = False,
        refresher: Refresher = refresh_tokens,
        now: Optional[datetime] = None,
    ) -> str:
        """A usable access token, refreshing under a row lock when needed.

        Two processes (web and worker) may both want a token. ``SELECT … FOR
        UPDATE`` makes the second wait; it then re-reads the expiry the first
        one just wrote and finds nothing to do. The new pair is written before
        the lock is released, so a rotating refresh token is never used twice.
        A refusal from the token endpoint marks the row and raises
        :class:`MailingAuthError`; nothing retries it.
        """
        refused: Optional[MailingAuthError] = None
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    select(mailing_connection).where(mailing_connection.c.id == ROW_ID)
                    .with_for_update()
                )
            ).first()
            if row is None:
                raise MailingNotConnected("The mailing service is not connected.")
            m = row._mapping
            if m["status"] != STATUS_CONNECTED:
                raise MailingNotConnected(
                    "The mailing service needs re-authorisation: " + (m.get("last_error") or "")
                )
            if not force and not needs_refresh(m["expires_at"], now):
                return self._decrypt(m["access_token"])
            try:
                fresh = await refresher(client_id, client_secret, self._decrypt(m["refresh_token"]))
            except MailingAuthError as exc:
                # Raising inside the transaction would roll the mark back with
                # it, so the mark is written on its own once the lock is released.
                refused = exc
            else:
                await conn.execute(
                    update(mailing_connection).where(mailing_connection.c.id == ROW_ID)
                    .values(
                        access_token=self._encrypt(fresh.access_token),
                        refresh_token=self._encrypt(fresh.refresh_token),
                        expires_at=fresh.expires_at,
                        scopes=fresh.scope or m.get("scopes"),
                        last_refresh_at=_now(),
                        last_error=None,
                    )
                )
                return fresh.access_token
        await self.mark_needs_reauthorisation(str(refused))
        log.warning("mailing: refresh refused — connection marked for re-authorisation")
        raise refused


# --- the API client -----------------------------------------------------------

TokenSource = Callable[[bool], Awaitable[str]]


def _retry_after(resp: httpx.Response) -> Optional[float]:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


class MailingClient:
    """Constant Contact V3, authenticated by a token the caller's store supplies.

    ``token_source(force)`` returns a bearer token; ``force=True`` demands a
    refresh (after a 401). In production it is
    ``ConnectionStore.access_token`` bound to the credentials; in tests a
    coroutine returning a string.
    """

    def __init__(
        self,
        token_source: TokenSource,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
    ) -> None:
        self._token_source = token_source
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._pace_lock = asyncio.Lock()
        self._last_start = 0.0
        self.request_count = 0

    # --- transport ----------------------------------------------------------

    async def _pace(self) -> None:
        """Never start two requests inside the vendor's per-second limit."""
        async with self._pace_lock:
            wait = self._last_start + MIN_REQUEST_INTERVAL - time.monotonic()
            if wait > 0:
                await _sleep(wait)
            self._last_start = time.monotonic()

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if path.startswith("/v3/"):  # a `_links.next.href` carries the version prefix
            path = path[3:]
        return f"{self._base}{path if path.startswith('/') else '/' + path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> dict[str, Any]:
        url = self._url(path)
        reauthed = False
        throttled = False
        resp: Optional[httpx.Response] = None
        token: Optional[str] = None
        for attempt in range(4):
            if token is None:
                token = await self._token_source(False)
            await self._pace()
            self.request_count += 1
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    resp = await http.request(
                        method, url, params=params, json=json_body,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    )
            except httpx.HTTPError as exc:
                raise MailingError(
                    f"Mailing service {method} {path} failed: could not reach the service "
                    f"({type(exc).__name__})"
                ) from exc

            if resp.status_code == 401 and not reauthed:
                reauthed = True
                token = await self._token_source(True)  # the refreshed token, used as given
                continue
            if resp.status_code == 429:
                if throttled:
                    raise MailingRateLimited(
                        f"Mailing service {method} {path}: rate limited twice; pass is partial."
                    )
                throttled = True
                await _sleep(_retry_after(resp) or 1.0)
                continue
            if resp.status_code in (500, 502, 503, 504) and attempt < 3:
                await _sleep(_retry_after(resp) or (2 ** attempt))
                continue
            break

        assert resp is not None
        if resp.status_code >= 400:
            raise MailingError(
                f"Mailing service {method} {path} failed: HTTP {resp.status_code} "
                f"{resp.text[:300]}"
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {"_list": data}

    # --- account --------------------------------------------------------------

    async def account_summary(self) -> dict[str, Any]:
        return await self._request("GET", "/account/summary")

    async def account_label(self) -> str:
        """The organisation name, or the account email, or empty — never raises for a missing field."""
        data = await self.account_summary()
        return str(
            data.get("organization_name") or data.get("contact_email") or ""
        )[:255]

    # --- paging ---------------------------------------------------------------

    async def _iter_pages(
        self, path: str, params: dict[str, Any], *, key: str
    ) -> AsyncIterator[dict[str, Any]]:
        next_path: Optional[str] = path
        next_params: Optional[dict[str, Any]] = params
        while next_path:
            page = await self._request("GET", next_path, params=next_params)
            for item in page.get(key) or []:
                yield item
            nxt = ((page.get("_links") or {}).get("next") or {}).get("href")
            next_path, next_params = (nxt, None) if nxt else (None, None)

    # --- lists ----------------------------------------------------------------

    async def lists(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for item in self._iter_pages("/contact_lists", {"limit": LISTS_PAGE}, key="lists"):
            out.append(item)
        return out

    async def find_list(self, name: str) -> Optional[dict[str, Any]]:
        want = (name or "").strip().casefold()
        for item in await self.lists():
            if str(item.get("name") or "").strip().casefold() == want:
                return item
        return None

    async def create_list(self, name: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/contact_lists", json_body={"name": name[:255], "favorite": False}
        )

    # --- contacts -------------------------------------------------------------

    def contacts(
        self,
        *,
        list_id: Optional[str] = None,
        status: Optional[str] = None,
        updated_after: Optional[datetime] = None,
        include: Iterable[str] = (),
    ) -> AsyncIterator[dict[str, Any]]:
        """Contacts matching the filters, paged transparently."""
        params: dict[str, Any] = {"limit": CONTACTS_PAGE}
        if list_id:
            params["lists"] = list_id
        if status:
            params["status"] = status
        if updated_after:
            params["updated_after"] = updated_after.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        inc = ",".join(include)
        if inc:
            params["include"] = inc
        return self._iter_pages("/contacts", params, key="contacts")

    async def import_contacts(
        self, rows: list[dict[str, Any]], *, list_id: str
    ) -> list[str]:
        """Add or update contacts and place them on the list; one activity id per chunk."""
        ids: list[str] = []
        for start in range(0, len(rows), IMPORT_MAX):
            chunk = rows[start:start + IMPORT_MAX]
            data = await self._request(
                "POST", "/activities/contacts_json_import",
                json_body={"import_data": chunk, "list_ids": [list_id]},
            )
            ids.append(str(data.get("activity_id") or ""))
        return ids

    async def remove_from_list(self, contact_ids: list[str], *, list_id: str) -> Optional[str]:
        """Take contacts off the list. They stay in the account."""
        if not contact_ids:
            return None
        data = await self._request(
            "POST", "/activities/remove_list_memberships",
            json_body={"source": {"contact_ids": list(contact_ids)}, "list_ids": [list_id]},
        )
        return str(data.get("activity_id") or "")

    async def activity(self, activity_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/activities/{activity_id}")

    async def wait_for_activity(
        self, activity_id: str, *, attempts: int = 30, interval: float = 2.0
    ) -> dict[str, Any]:
        """Poll until the activity is finished or the attempts run out (returns the last state)."""
        last: dict[str, Any] = {}
        for _ in range(max(1, attempts)):
            last = await self.activity(activity_id)
            if str(last.get("state") or "").lower() in ACTIVITY_DONE:
                return last
            await _sleep(interval)
        return last


def make_connection_store(settings: Any) -> Optional[ConnectionStore]:
    """The connection store for this deployment, or None without a database.

    Carries the Fernet cipher when ``APP_ENCRYPTION_KEY`` is configured. Without
    one the store still answers reads (there is nothing to read) and refuses
    every token write — a connection is never stored in plain text.
    """
    if not getattr(settings, "database_url", ""):
        return None
    cipher = None
    if getattr(settings, "app_encryption_key", ""):
        try:
            from core.crypto import SecretCipher

            cipher = SecretCipher(settings.app_encryption_key)
        except Exception as exc:  # noqa: BLE001 — no cipher is a working (read-only) state
            log.warning("mailing: encryption key unusable, connection cannot be stored: %s", exc)
    return ConnectionStore(settings.database_url, cipher)


def make_client(store: ConnectionStore, client_id: str, client_secret: str, *, base_url: str = DEFAULT_BASE_URL) -> MailingClient:
    """A client whose tokens come from the connection store, refreshed under its lock."""

    async def _source(force: bool) -> str:
        return await store.access_token(client_id, client_secret, force=force)

    return MailingClient(_source, base_url=base_url)
