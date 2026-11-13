"""The Lob integration test (prds/integrations-tab-plan.md § 3; the check list
Doug approved 11-13-26, phase 3 stopping point 1).

Lob's switch is ``postal_provider = lob``; the checks run whether it is chosen
or not, so Lob can be tested before it is. **Nothing is ever mailed, and the
address check is never called** (it is a create, and Lob bills it in live
mode). Checks, in order:

1. **Settings present** — the API key. While the vendor is the dry run, the
   detail says nothing can be mailed.
2. **Test or live** — Lob decides by the key itself: ``test_…`` or ``live_…``
   (Lob's Getting Started, read 11-13-26). Only that prefix is read. The test
   mode setting changes nothing Lob does, so a live key with test mode on is
   failed (postcards would really be printed), and a test key with test mode
   off is failed too. Fact: test or live.
3. **Read postcards** — ``GET /postcards?limit=1``: proves the key. Fact: the
   number on the account when Lob reports ``total_count``.
4. **Webhook secret** — set; failed only while the vendor is Lob.

Plan § 3's "account" fact is dropped: Lob's API has no call that reads the
account (its reference, read 11-13-26).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from integrations.testing import FAILED, OK, UNKNOWN, Blocked, Check, Context, run_checks


def _default_client(settings: Any) -> Any:
    from core.postal import LobPostalClient

    return LobPostalClient(settings.postal_api_key, timeout=8)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


def _chosen(settings: Any) -> bool:
    return (settings.postal_provider or "").strip().lower() == "lob"


def _key(settings: Any) -> str:
    return (settings.postal_api_key or "").strip()


async def _settings(ctx: Context) -> tuple[str, str]:
    if not _key(ctx.settings):
        return FAILED, "Not set: the Lob API key."
    ctx.state["settings_ok"] = True
    if not _chosen(ctx.settings):
        return OK, "The Lob API key is set. The mail vendor is the dry run, so nothing can be mailed."
    return OK, "The Lob API key is set, and Lob is the mail vendor."


async def _mode(ctx: Context) -> tuple[str, str]:
    if not ctx.state.get("settings_ok"):
        raise Blocked("Not checked: the API key is not set (check 1).")
    key = _key(ctx.settings)
    test_mode = bool(ctx.settings.postal_test_mode)
    if key.startswith("test_"):
        ctx.fact("Lob environment", "test (nothing is printed)")
        if not test_mode:
            return FAILED, ("The key is a Lob test key, but test mode is off: campaigns treat "
                            "postcards as real, and Lob prints none. Enter the live key, or "
                            "switch test mode on.")
        return OK, "The key is a test key, and test mode is on: nothing is printed."
    if key.startswith("live_"):
        ctx.fact("Lob environment", "live (postcards are printed and mailed)")
        if test_mode:
            return FAILED, ("The key is a Lob LIVE key, but test mode is on: postcards would "
                            "really be printed and mailed. Enter the test key, or switch test mode off.")
        return OK, "The key is a live key, and test mode is off: postcards are printed and mailed."
    ctx.fact("Lob environment", "not known")
    return UNKNOWN, "The key starts with neither test_ nor live_, so its environment is not known."


async def _postcards(ctx: Context) -> tuple[str, str]:
    from core.postal import PostalAuthError, PostalError, PostalUnavailable

    if not ctx.state.get("settings_ok"):
        raise Blocked("Not checked: the API key is not set (check 1).")
    try:
        data = await ctx.deps.client(ctx.settings).list_postcards(limit=1)
    except PostalAuthError as exc:
        return FAILED, f"{exc} Check the key in Lob's dashboard."
    except PostalUnavailable as exc:
        return UNKNOWN, str(exc)
    except PostalError as exc:
        return FAILED, str(exc)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return UNKNOWN, "Lob answered without a list of postcards; its API may have changed."
    total = data.get("total_count")
    ctx.fact("Postcards on the account", total if total is not None else "not reported")
    return OK, "Lob accepted the key and listed postcards."


async def _webhook(ctx: Context) -> tuple[str, str]:
    if (ctx.settings.postal_webhook_secret or "").strip():
        return OK, "The webhook secret is set: Lob's delivery events can be verified."
    if _chosen(ctx.settings):
        return FAILED, ("The webhook secret is not set: every delivery event Lob sends is "
                        "refused. Copy it from the webhook in Lob's dashboard.")
    return OK, "The webhook secret is not set. It must be before Lob is chosen as the mail vendor."


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("mode", "Test or live", _mode),
    Check("postcards", "Read postcards", _postcards),
    Check("webhook", "Webhook secret", _webhook),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("lob", CHECKS, ctx)
