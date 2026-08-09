"""Environment diff — "what is on in test that is off in prod?" (plan §5, phase 3)

Each deployment can expose a **read-only, non-secret** snapshot of its settings
to its peer, authorised by a shared token. The diff view fetches the peer's
snapshot and lists the keys whose effective values differ, turning promotion
into a checklist instead of memory.

Ruling 8: nothing is stored. The diff is computed live, and a key can be
expanded to pull that key's history from both sides on demand.

**Secrets never cross the wire** — a secret contributes only a boolean "set",
so the diff can tell you "prod has no Fathom key" without ever moving one.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any, Optional

import httpx

from core import config as config_module
from core.config import Settings
from core.settings_registry import SECRET_KEYS, SETTINGS, is_secret, spec_for
from core.settings_store import Override, SettingsStore

log = logging.getLogger("cbm_intake.setup.snapshot")

TOKEN_HEADER = "X-CBM-Setup-Token"
SNAPSHOT_PATH = "/api/setup/snapshot"


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def compared_keys() -> list[str]:
    """Everything the diff covers: the curated settings, plus every secret as a
    presence-only entry.

    Including the secrets is what lets the diff say "prod has no Fathom key"
    — the single most useful thing to know before a promotion — while the value
    itself never leaves the process.
    """
    curated = [s.key for s in SETTINGS]
    return curated + [k for k in sorted(SECRET_KEYS) if k not in set(curated)]


def _label(key: str) -> str:
    spec = spec_for(key)
    return spec.label if spec else key.replace("_", " ").strip().capitalize()


def _group(key: str) -> str:
    spec = spec_for(key)
    return spec.group if spec else "Credentials"


def build_snapshot(
    settings: Settings, overrides: Optional[dict[str, Override]] = None
) -> dict[str, Any]:
    """This deployment's non-secret settings, as the peer will see them."""
    overrides = overrides or {}
    env = config_module._env_settings()
    entries: dict[str, Any] = {}
    for key in compared_keys():
        override = overrides.get(key)
        if is_secret(key):
            entries[key] = {"secret": True, "set": bool(getattr(settings, key, None))}
            continue
        entries[key] = {
            "secret": False,
            "value": _as_text(getattr(settings, key, None)),
            "envValue": _as_text(getattr(env, key, None)),
            "overridden": override is not None,
            "temporary": bool(override.temporary) if override else False,
            "scoped": bool(override.scoped) if override else False,
        }
    return {
        "environment": settings.environment,
        "crm": settings.espo_base_url,
        "version": config_module.overrides_version(),
        "settings": entries,
    }


def token_matches(settings: Settings, presented: str) -> bool:
    """Constant-time check. An unset token means the endpoint is closed, not open."""
    expected = settings.setup_peer_token
    if not expected:
        return False
    return hmac.compare_digest(expected, presented or "")


async def fetch_peer(settings: Settings) -> dict[str, Any]:
    """Fetch the peer deployment's snapshot. Returns ``{"ok": False, "error": …}``
    rather than raising — an unreachable peer degrades the diff, not the page."""
    if not settings.setup_peer_url or not settings.setup_peer_token:
        return {
            "ok": False,
            "error": "No peer configured (set SETUP_PEER_URL and SETUP_PEER_TOKEN "
                     "on both deployments).",
        }
    url = settings.setup_peer_url.rstrip("/") + SNAPSHOT_PATH
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.get(
                url, headers={TOKEN_HEADER: settings.setup_peer_token}
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Could not reach {url}: {exc}"}
    if resp.status_code == 401:
        return {"ok": False, "error": "The peer rejected our token (401) — the two "
                                      "deployments must share the same SETUP_PEER_TOKEN."}
    if resp.status_code >= 400:
        return {"ok": False, "error": f"Peer returned HTTP {resp.status_code}."}
    try:
        return {"ok": True, "snapshot": resp.json()}
    except ValueError:
        return {"ok": False, "error": "The peer's response was not JSON."}


def diff_snapshots(local: dict[str, Any], peer: dict[str, Any]) -> dict[str, Any]:
    """Keys whose effective value differs between the two deployments."""
    local_entries = local.get("settings", {}) or {}
    peer_entries = peer.get("settings", {}) or {}
    keys = compared_keys()
    rows = []
    for key in keys:
        mine = local_entries.get(key)
        theirs = peer_entries.get(key)
        if mine is None or theirs is None:
            # A key one side doesn't know about — the two deployments are on
            # different app versions, which is worth seeing rather than hiding.
            rows.append({
                "key": key, "label": _label(key), "group": _group(key),
                "local": None if mine is None else mine.get("value"),
                "peer": None if theirs is None else theirs.get("value"),
                "secret": is_secret(key),
                "kind": "unknown-key",
            })
            continue
        if mine.get("secret") or theirs.get("secret"):
            if bool(mine.get("set")) != bool(theirs.get("set")):
                rows.append({
                    "key": key, "label": _label(key), "group": _group(key),
                    "local": "set" if mine.get("set") else "not set",
                    "peer": "set" if theirs.get("set") else "not set",
                    "secret": True, "kind": "secret-presence",
                })
            continue
        if mine.get("value") != theirs.get("value"):
            rows.append({
                "key": key, "label": _label(key), "group": _group(key),
                "local": mine.get("value"),
                "peer": theirs.get("value"),
                "localOverridden": bool(mine.get("overridden")),
                "peerOverridden": bool(theirs.get("overridden")),
                "secret": False,
                "kind": "value",
            })
    return {
        "localEnvironment": local.get("environment"),
        "peerEnvironment": peer.get("environment"),
        "differences": rows,
        "sameCount": len(keys) - len(rows),
    }


async def diff_payload(settings: Settings, store: Optional[SettingsStore]) -> dict[str, Any]:
    overrides = await store.load() if store is not None else {}
    local = build_snapshot(settings, overrides)
    peer = await fetch_peer(settings)
    if not peer.get("ok"):
        return {"ok": False, "error": peer.get("error"), "local": local}
    result = diff_snapshots(local, peer["snapshot"])
    result["ok"] = True
    return result
