"""The texting service behind the text-message campaign kind (rulings 38, 39).

One interface, two clients, the mail vendor's arrangement (``core/postal.py``):

* :class:`DryRunSmsClient` — the default. Sends nothing, accepts every message
  with a ``dryrun-`` id, and records what it was asked to send.
* :class:`TwilioSmsClient` — the one real adapter, written from Twilio's
  published Messages API and **never yet run against it**: the account, the
  sender number and the United States carrier registration (A2P 10DLC) are
  Doug's prerequisites before the first real text (ruling 38).

Twilio has no idempotency key on a send, so the caller marks the touch
*sending* before the call and never resends a touch left in that state by
itself — a resend after a crash between Twilio's accept and our own write would
text the person twice (ruling 39's "flagged for review, never resent").

Inbound requests (a reply, a delivery status) are signed by Twilio with the
account's auth token: :func:`verify_twilio_signature` is the HMAC-SHA1 of the
full URL followed by every POST parameter, sorted by name, base64-encoded.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol
from zoneinfo import ZoneInfo

import httpx

from .config import Settings

log = logging.getLogger("cbm_intake.sms")

TWILIO_BASE_URL = "https://api.twilio.com/2010-04-01"
PROVIDER_DRYRUN = "dryrun"
PROVIDER_TWILIO = "twilio"

#: The replies that opt a person out, as carriers and Twilio recognise them.
STOP_WORDS = frozenset({"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "REVOKE", "OPTOUT"})

#: Twilio's error codes that mean "never send to this number again".
PERMANENT_ERRORS = frozenset({21610, 21614, 21211, 21612, 21408})

#: The GSM-7 basic character set and its extension table (each extension
#: character costs two septets).
_GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM7_EXT = set("^{}\\[~]|€")


class SmsError(Exception):
    """Any texting-service failure. ``permanent`` means: never retry this number."""

    def __init__(self, message: str, *, permanent: bool = False, ambiguous: bool = False):
        super().__init__(message)
        self.permanent = permanent
        #: The request may have reached the service (a timeout after sending):
        #: the message may or may not have gone out.
        self.ambiguous = ambiguous


class SmsSignatureError(SmsError):
    """An inbound request whose signature does not verify."""


@dataclass
class SentMessage:
    id: str
    status: str


class SmsClient(Protocol):
    async def send(self, *, key: str, to: str, body: str, status_callback: str = "") -> SentMessage: ...


@dataclass
class DryRunSmsClient:
    """Sends nothing; every message is accepted as ``dryrun-<key>``."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, *, key: str, to: str, body: str, status_callback: str = "") -> SentMessage:
        self.sent.append({"key": key, "to": to, "body": body, "status_callback": status_callback})
        return SentMessage(id=f"dryrun-{key}", status="accepted (dry run)")


class TwilioSmsClient:
    """POST /Accounts/{sid}/Messages.json, basic auth with the account SID and
    auth token. Written from the published API; never run (ruling 38)."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str, *, timeout: float = 20.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        if not account_sid or not auth_token or not from_number:
            raise SmsError("The texting service is not configured (account SID, auth token and sender number).",
                           permanent=False)
        self._sid = account_sid
        self._auth = (account_sid, auth_token)
        self._from = from_number
        self._timeout = timeout
        self._transport = transport

    async def send(self, *, key: str, to: str, body: str, status_callback: str = "") -> SentMessage:
        data = {"To": to, "From": self._from, "Body": body}
        if status_callback:
            data["StatusCallback"] = status_callback
        url = f"{TWILIO_BASE_URL}/Accounts/{self._sid}/Messages.json"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                resp = await http.post(url, data=data, auth=self._auth)
        except httpx.TimeoutException as exc:
            raise SmsError(f"the texting service did not answer ({exc})", ambiguous=True) from exc
        except httpx.HTTPError as exc:
            raise SmsError(f"the texting service could not be reached ({exc})") from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400:
            code = payload.get("code")
            message = payload.get("message") or resp.text[:200]
            raise SmsError(f"HTTP {resp.status_code} [{code}] {message}",
                           permanent=code in PERMANENT_ERRORS or resp.status_code in (400, 404))
        return SentMessage(id=str(payload.get("sid") or ""), status=str(payload.get("status") or "queued"))


def make_client(settings: Settings) -> SmsClient:
    if settings.sms_provider == PROVIDER_TWILIO:
        return TwilioSmsClient(settings.sms_account_sid, settings.sms_auth_token, settings.sms_from_number,
                               timeout=float(settings.request_timeout_seconds))
    return DryRunSmsClient()


# --- the message ---------------------------------------------------------------------

def is_gsm7(text: str) -> bool:
    return all(ch in _GSM7 or ch in _GSM7_EXT for ch in text)


def segments(text: str) -> dict[str, Any]:
    """How many message parts a text takes: GSM-7 is 160 characters alone and
    153 a part when split; anything else (an emoji, a curly quote) makes the
    whole message UCS-2, 70 alone and 67 a part."""
    text = text or ""
    if is_gsm7(text):
        units = sum(2 if ch in _GSM7_EXT else 1 for ch in text)
        single, multi, encoding = 160, 153, "GSM-7"
    else:
        units = len(text.encode("utf-16-le")) // 2
        single, multi, encoding = 70, 67, "UCS-2"
    parts = 0 if units == 0 else (1 if units <= single else -(-units // multi))
    return {"characters": len(text), "units": units, "parts": parts, "encoding": encoding}


_STOP_HINT = re.compile(r"\bstop\b", re.IGNORECASE)


def tells_how_to_opt_out(text: str) -> bool:
    """The first text to a person names how to stop them (carrier rules for
    United States business texting): the word STOP must be in the message."""
    return bool(_STOP_HINT.search(text or ""))


def is_stop_reply(body: str) -> bool:
    return (body or "").strip().upper().rstrip(".!") in STOP_WORDS


# --- when a text may go out --------------------------------------------------------------

def parse_hours(spec: str) -> tuple[int, int]:
    """'9-20' → (9, 20): from 9:00 up to (not including) 20:00."""
    try:
        a, b = (int(x) for x in (spec or "9-20").split("-", 1))
    except ValueError:
        return 9, 20
    if not (0 <= a < b <= 24):
        return 9, 20
    return a, b


def within_send_hours(settings: Settings, now: Optional[datetime] = None) -> bool:
    start, end = parse_hours(settings.sms_send_hours)
    try:
        tz = ZoneInfo(settings.sms_timezone or "America/New_York")
    except Exception:  # noqa: BLE001 — a bad zone name falls back to the chapter default
        tz = ZoneInfo("America/New_York")
    local = (now or datetime.now(tz)).astimezone(tz)
    return start <= local.hour < end


# --- inbound requests ----------------------------------------------------------------------

def twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def verify_twilio_signature(auth_token: str, url: str, params: dict[str, str], signature: str) -> None:
    if not auth_token:
        raise SmsSignatureError("no auth token configured")
    expected = twilio_signature(auth_token, url, params)
    if not hmac.compare_digest(expected, signature or ""):
        raise SmsSignatureError("signature does not verify")
