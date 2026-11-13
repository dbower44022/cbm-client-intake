"""The Twilio integration test (prds/integrations-tab-plan.md § 3; the check
list Doug approved 11-13-26, phase 3 stopping point 1).

Twilio's switch is ``sms_provider = twilio``; the checks run whether it is
chosen or not, so Twilio can be tested before it is. **Nothing is ever sent.**
Checks, in order:

1. **Settings present** — account SID, auth token, sender number.
2. **The account** — ``GET /Accounts/{sid}.json``. ``status`` active is ok,
   suspended or closed failed. A 403 is what Twilio's test credentials get on
   any read (its test-credentials page), so it is failed and says so. Fact:
   ``type`` (Trial or Full).
3. **The sender number** — ``GET /Accounts/{sid}/IncomingPhoneNumbers.json``
   with ``PhoneNumber``: failed if the number is not on the account, or its
   ``capabilities.sms`` is false. Facts: its name and capabilities.
4. **Sending hours** — the hours and the time zone parse. Local, no call.

The carrier registration (A2P 10DLC) is not read: a fact says so.
Confirmed against Twilio's API reference 11-13-26: the account's ``status``
and ``type`` values, the ``PhoneNumber`` filter, ``incoming_phone_numbers``,
and lowercase ``capabilities`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from integrations.testing import FAILED, OK, UNKNOWN, Blocked, Check, Context, run_checks


def _default_client(settings: Any) -> Any:
    from core.sms import TwilioSmsClient

    return TwilioSmsClient(settings.sms_account_sid, settings.sms_auth_token,
                           settings.sms_from_number, timeout=10.0)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


def _answer(exc: Exception, what: str) -> tuple[str, str]:
    status = getattr(exc, "status_code", None)
    if status is None or status >= 500 or status == 429:
        return UNKNOWN, f"Could not read {what}: {exc}"
    if status == 401:
        return FAILED, f"Twilio refused the account SID and auth token: {exc}"
    if status == 403:
        return FAILED, (f"Twilio refused to show {what} (HTTP 403). Test credentials get this "
                        "on every read: enter the live account SID and auth token.")
    if status == 404:
        return FAILED, f"Twilio has no such account: check the account SID. ({exc})"
    return FAILED, f"Twilio refused to show {what}: {exc}"


async def _settings(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    missing = [label for label, value in (
        ("account SID", s.sms_account_sid), ("auth token", s.sms_auth_token),
        ("sender number", s.sms_from_number),
    ) if not (value or "").strip()]
    if missing:
        return FAILED, "Not set: " + ", ".join(missing) + "."
    ctx.state["client"] = ctx.deps.client(s)
    note = "" if s.sms_provider == "twilio" else " The texting service is set to the dry run, so nothing is sent."
    return OK, "The account SID, auth token and sender number are set." + note


async def _account(ctx: Context) -> tuple[str, str]:
    if "client" not in ctx.state:
        raise Blocked("Not checked: a setting is missing (check 1).")
    try:
        account = await ctx.state["client"].get_account()
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the account")
    status = (account or {}).get("status")
    if not status:
        return UNKNOWN, "Twilio answered without the account's status; its API may have changed."
    ctx.fact("Account type", account.get("type") or "not reported")
    if account.get("friendly_name"):
        ctx.fact("Account name", account["friendly_name"])
    ctx.fact("Account status", status)
    ctx.state["account_ok"] = True
    if status != "active":
        return FAILED, f"The Twilio account is {status}: no text can be sent."
    trial = " It is a trial account, which can only text verified numbers." if account.get("type") == "Trial" else ""
    return OK, "The Twilio account is active." + trial


async def _number(ctx: Context) -> tuple[str, str]:
    if not ctx.state.get("account_ok"):
        raise Blocked("Not checked: the account could not be read (check 2).")
    number = ctx.settings.sms_from_number.strip()
    try:
        data = await ctx.state["client"].find_number(number)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the account's phone numbers")
    numbers = (data or {}).get("incoming_phone_numbers")
    if not isinstance(numbers, list):
        return UNKNOWN, "Twilio answered without a list of phone numbers; its API may have changed."
    match = next((n for n in numbers if (n or {}).get("phone_number") == number), None)
    if match is None:
        return FAILED, (f"{number} is not a number on this Twilio account. Check the sender "
                        "number, written in E.164 form (+12165550123).")
    caps = match.get("capabilities") or {}
    able = [k.upper() if k in ("sms", "mms") else k for k in ("sms", "mms", "voice") if caps.get(k)]
    ctx.fact("Sender number", f"{number} ({match.get('friendly_name') or 'no name'})")
    ctx.fact("Sender can", ", ".join(able) if able else "nothing reported")
    ctx.fact("Carrier registration (A2P 10DLC)", "not read by this test; checked in Twilio's console")
    if "sms" not in caps:
        return UNKNOWN, f"Twilio did not report whether {number} can send texts."
    if not caps.get("sms"):
        return FAILED, f"{number} is on the account but cannot send texts (SMS)."
    return OK, f"{number} is on the account and can send texts."


async def _hours(ctx: Context) -> tuple[str, str]:
    from core.sms import parse_hours

    s = ctx.settings
    written = (s.sms_send_hours or "").replace(" ", "")
    start, end = parse_hours(s.sms_send_hours)
    if written and written != f"{start}-{end}":
        # parse_hours falls back to 9-20 on anything it cannot read.
        return FAILED, (f"The sending hours “{s.sms_send_hours}” cannot be read, so texts go out "
                        f"{start}:00 to {end}:00 instead. Write them as two hours, for example 9-20.")
    try:
        ZoneInfo(s.sms_timezone)
    except Exception:  # noqa: BLE001
        return FAILED, f"“{s.sms_timezone}” is not a time zone name (for example America/New_York)."
    return OK, f"Texts go out between {start}:00 and {end}:00, {s.sms_timezone}."


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("account", "The account", _account),
    Check("number", "The sender number", _number),
    Check("hours", "Sending hours", _hours),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("twilio", CHECKS, ctx)
