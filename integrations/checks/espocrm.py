"""The EspoCRM integration test (prds/integrations-tab-plan.md § 3; the check
list Doug approved 11-13-26, phase 2 stopping point 1).

Checks, in order:

1. **Mode** — dry run means there is no CRM to test (unknown, and nothing else
   runs); a missing address or API key is failed.
2. **Sign in with the API key** — ``GET App/user``. Facts: the EspoCRM version
   (``settings.version``, found on crm-test 11-13-26: 9.3.10) and the API
   user's name and roles (``GET User/{id}``).
3. **Conformance** — the entities, fields, teams and named email templates this
   application needs, by ``scripts/preflight_crm.run`` (read-only; a scope the
   key may not read is unknown, never "missing").
4. **Read access** — one record of each entity the application reads, plus each
   switched-on feature's own entities.
5. **Enum options** — the values ``core/schema_contract.py`` expects.
6. **Provisioning account** — signs in through ``core/admin_client.py`` (its
   token cache, so repeated clicks do not trip the CRM's lockout) and confirms
   the account is an administrator.

Every call is a read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from integrations.testing import (
    FAILED,
    OK,
    UNKNOWN,
    Blocked,
    Check,
    Context,
    Skip,
    run_checks,
)

#: Entities read under every configuration (the conformance list, plus sessions).
CORE_ENTITIES: tuple[str, ...] = (
    "Account", "Contact", "CClientProfile", "CEngagement", "CMentorProfile",
    "CPartnerProfile", "CSponsorProfile", "CInformationRequest", "CIntakeSubmission",
    "CSession",
)
#: A feature switch, and the entities only it reads.
FEATURE_ENTITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("events_enabled", ("CEvent", "CEventRegistration")),
    ("campaigns_enabled", ("CProspect", "COutreachCampaign", "COutreachTouch")),
)


def _default_client(settings: Any) -> Any:
    from core.espo import EspoClient

    return EspoClient(settings.espo_base_url, settings.espo_api_key, 10)


async def _default_conformance(url: str, key: str) -> tuple[int, dict]:
    from scripts.preflight_crm import run as preflight

    return await preflight(url, key)


def _default_admin(settings: Any) -> Optional[Callable[[], Awaitable[Any]]]:
    from core.admin_client import admin_client_factory

    return admin_client_factory(settings)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client
    conformance: Callable[[str, str], Awaitable[tuple[int, dict]]] = _default_conformance
    admin: Callable[[Any], Optional[Callable[[], Awaitable[Any]]]] = _default_admin


def _transport(exc: Exception) -> bool:
    from core.espo import EspoTransportError

    return isinstance(exc, EspoTransportError)


def _rejected(exc: Exception) -> bool:
    text = str(exc)
    return "401" in text or "403" in text


# --- the checks ---------------------------------------------------------------

async def _sign_in(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    client = ctx.deps.client(s)
    ctx.state["client"] = client
    try:
        payload = await client.app_user()
    except Exception as exc:  # noqa: BLE001
        if _transport(exc):
            return UNKNOWN, f"Could not reach the CRM at {s.espo_base_url}: {exc}"
        if _rejected(exc):
            return FAILED, f"The CRM answered but rejected the API key: {exc}"
        return FAILED, (
            f"{s.espo_base_url} answered, but not as an EspoCRM this application "
            f"can use: {exc}"
        )
    user = (payload or {}).get("user") or {}
    version = ((payload or {}).get("settings") or {}).get("version")
    ctx.fact("EspoCRM version", version or "not reported")
    name = user.get("userName") or user.get("name") or ""
    ctx.fact("API user", name or "not reported")
    roles = "could not be read"
    if user.get("id"):
        try:
            record = await client.get("User", str(user["id"]), select="rolesNames")
            names = sorted(((record or {}).get("rolesNames") or {}).values())
            roles = ", ".join(names) if names else "none"
        except Exception:  # noqa: BLE001 — a fact, not a check
            pass
    ctx.fact("API user's roles", roles)
    ctx.state["signed_in"] = True
    return OK, f"Signed in to {s.espo_base_url} as {name or 'the API user'}."


def _needs_sign_in(ctx: Context) -> None:
    if not ctx.state.get("signed_in"):
        raise Blocked("Not checked: the API key could not sign in (check 2).")


def _names(checks: list[dict], limit: int = 6) -> str:
    parts = []
    for c in checks[:limit]:
        missing = c.get("missing") or []
        parts.append(c["target"] + (f" ({', '.join(missing[:5])}"
                                    + (", …" if len(missing) > 5 else "") + ")"
                                    if missing else ""))
    more = len(checks) - limit
    return "; ".join(parts) + (f"; and {more} more" if more > 0 else "")


async def _conformance(ctx: Context) -> tuple[str, str]:
    _needs_sign_in(ctx)
    s = ctx.settings
    _code, result = await ctx.deps.conformance(s.espo_base_url, s.espo_api_key)
    ctx.state["conformance"] = result
    rows = [c for c in result.get("checks", []) if c.get("category") != "enum"]
    entities = [c for c in rows if c.get("category") == "entity"]
    present = sum(1 for c in entities if c.get("outcome") == "conformant")
    ctx.fact("Entities found", f"{present} of {len(entities)} required")
    absent = [c for c in rows if c.get("outcome") == "absent"]
    unchecked = [c for c in rows if c.get("outcome") in ("forbidden", "unreachable", "error")]
    if absent:
        return FAILED, "Missing from the CRM: " + _names(absent) + "."
    if unchecked:
        return UNKNOWN, ("Could not be checked (the API key may not read them, or "
                         "the CRM did not answer): " + _names(unchecked) + ".")
    return OK, (f"All {len(rows)} checks pass: the entities and fields this "
                "application writes, the teams it gates on and the email "
                "templates it sends by name.")


def entities_to_read(settings: Any) -> list[str]:
    out = list(CORE_ENTITIES)
    for switch, entities in FEATURE_ENTITIES:
        if getattr(settings, switch, False):
            out.extend(entities)
    return out


async def _read_access(ctx: Context) -> tuple[str, str]:
    _needs_sign_in(ctx)
    client = ctx.state["client"]
    entities = entities_to_read(ctx.settings)
    refused, missing, unreachable = [], [], []
    for entity in entities:
        try:
            await client.list(entity, max_size=1, select="id")
        except Exception as exc:  # noqa: BLE001
            if _transport(exc):
                unreachable.append(entity)
            elif "403" in str(exc):
                refused.append(entity)
            else:
                missing.append(entity)
    if refused or missing:
        parts = []
        if refused:
            parts.append("the API key may not read " + ", ".join(refused))
        if missing:
            parts.append("the CRM has no " + ", ".join(missing))
        text = "; ".join(parts)
        return FAILED, text[0].upper() + text[1:] + "."
    if unreachable:
        return UNKNOWN, "The CRM did not answer for " + ", ".join(unreachable) + "."
    return OK, f"Read one record of each of {len(entities)} entities: {', '.join(entities)}."


async def _enums(ctx: Context) -> tuple[str, str]:
    _needs_sign_in(ctx)
    result = ctx.state.get("conformance")
    if result is None:
        raise Blocked("Not checked: the conformance check did not run (check 3).")
    rows = [c for c in result.get("checks", []) if c.get("category") == "enum"]
    bad = [c for c in rows if c.get("outcome") in ("absent", "advisory")]
    unchecked = [c for c in rows if c.get("outcome") in ("forbidden", "unreachable", "error")]
    if bad:
        return FAILED, ("Expected values are missing; forms that send them store "
                        "nothing: " + _names(bad) + ".")
    if unchecked:
        return UNKNOWN, "Could not be read: " + _names(unchecked) + "."
    return OK, f"All {len(rows)} watched fields offer every value this application sends."


async def _provisioning(ctx: Context) -> tuple[str, str]:
    s = ctx.settings
    configured = bool(s.espo_provision_username and s.espo_provision_password)
    if not configured:
        if getattr(s, "mentor_provision_users", False):
            return FAILED, ("Mentor provisioning is on, but the provisioning "
                            "account's username or password is not set.")
        raise Skip("Not checked — not set; only mentor provisioning needs it.")
    _needs_sign_in(ctx)
    factory = ctx.deps.admin(s)
    if factory is None:
        return UNKNOWN, "The provisioning account could not be used here (dry run)."
    try:
        client = await factory()
        payload = await client.app_user()
    except Exception as exc:  # noqa: BLE001
        if _transport(exc) or type(exc).__name__ in ("ConnectError", "TimeoutException",
                                                     "ReadTimeout", "ConnectTimeout"):
            return UNKNOWN, f"Could not reach the CRM to sign in: {exc}"
        return FAILED, f"The provisioning account could not sign in: {exc}"
    user = (payload or {}).get("user") or {}
    name = user.get("userName") or s.espo_provision_username
    if user.get("type") == "admin" or user.get("isAdmin"):
        return OK, f"Signed in as {name}, an administrator."
    return FAILED, (f"Signed in as {name}, but it is a {user.get('type') or 'regular'} "
                    "user. Creating logins needs an administrator.")


CHECKS: list[Check] = [
    Check("sign_in", "Sign in with the API key", _sign_in),
    Check("conformance", "Entities, fields, teams and email templates", _conformance,
          timeout=20.0),
    Check("read_access", "Read access to each entity", _read_access),
    Check("enums", "Enum options", _enums),
    Check("provisioning", "Provisioning account", _provisioning),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    if settings.espo_dry_run:
        async def dry(_ctx: Context) -> tuple[str, str]:
            return UNKNOWN, "Dry run is on: there is no CRM to test."
        return await run_checks("espocrm", [Check("mode", "Mode", dry)], ctx)
    missing = [label for label, value in (("address", settings.espo_base_url),
                                          ("API key", settings.espo_api_key)) if not value]
    if missing:
        async def unset(_ctx: Context) -> tuple[str, str]:
            return FAILED, f"The CRM {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set."
        return await run_checks("espocrm", [Check("mode", "Mode", unset)], ctx)
    return await run_checks("espocrm", CHECKS, ctx)
