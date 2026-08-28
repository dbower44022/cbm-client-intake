"""System Settings — the page payload and the write path (plan §4).

Renders every setting as a row carrying BOTH values when they disagree
(ruling 2: the DB override wins, and the overlay's value is shown alongside so
the overlay never silently lies about what the app is doing), plus where the
effective value came from, whether it needs a redeploy, and which process reads
it.

Secrets never leave the server: :data:`SECRET_MASK` stands in for the value and
the row only reports whether one is set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from core import boot_overrides
from core import config as config_module
from core.config import Settings, get_settings
from core.settings_registry import (
    DENYLIST,
    GROUP_ORDER,
    GROUP_RESTART,
    SETTINGS,
    SettingSpec,
    is_secret,
    spec_for,
)
from core.settings_store import Override, SettingsStore

SECRET_MASK = "••••••••"

SOURCE_DEFAULT = "default"
SOURCE_ENV = "overlay"
SOURCE_OVERRIDE = "override"


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _source_of(key: str, env_value: Any, overridden: bool) -> str:
    if overridden:
        return SOURCE_OVERRIDE
    field = Settings.model_fields.get(key)
    if field is not None and env_value == field.default:
        return SOURCE_DEFAULT
    return SOURCE_ENV


def _row(
    spec: SettingSpec,
    settings: Settings,
    env: dict[str, Any],
    override: Optional[Override],
) -> dict[str, Any]:
    key = spec.key
    secret = is_secret(key)
    env_value = env.get(key)
    effective = getattr(settings, key, None)
    row: dict[str, Any] = {
        "key": key,
        "label": spec.label,
        "group": spec.group,
        "kind": spec.kind,
        "choices": list(spec.choices),
        "unit": spec.unit,
        "help": spec.help,
        "restart": spec.restart,
        "component": spec.component,
        "editable": not spec.readonly,
        "secret": secret,
        "value": SECRET_MASK if secret else _as_text(effective),
        "envValue": SECRET_MASK if secret else _as_text(env_value),
        "isSet": bool(effective) if secret else None,
        "overridden": override is not None,
        "source": _source_of(key, env_value, override is not None),
        # Only meaningful when overridden — shown as "overlay says X · override
        # says Y" so an overlay edit that appears to do nothing is explicable.
        "differs": override is not None and _as_text(env_value) != _as_text(effective),
        "override": override.as_dict() if override else None,
        # Scoping a worker-side setting cannot work: there is no user in the
        # worker. The UI must refuse rather than offer a control that does
        # nothing (plan §5).
        "scopable": spec.component == "web",
    }
    if spec.restart:
        _add_restart_state(row, key, secret, effective)
    return row


def _add_restart_state(
    row: dict[str, Any], key: str, secret: bool, effective: Any
) -> None:
    """Say what this process is ACTUALLY running, beside what is stored.

    For a restart-required setting the live ``Settings`` object is not the
    truth. The periodic refresh installs a newer value into it happily, while
    the routers, middleware and logging built at startup carry on using the one
    the process booted with. Reading it back would report that a change had
    taken effect when it had not — the failure this whole section exists to
    prevent.

    ``core.boot_overrides`` snapshots the real boot values, and that snapshot is
    what ``inForce`` reports.
    """
    boot = boot_overrides.state()
    booted = boot.snapshot.get(key, effective)
    row["inForce"] = SECRET_MASK if secret else _as_text(booted)
    # A pending change is one where what is stored now differs from what this
    # process started with. Nothing pending is the ordinary, quiet case.
    row["pendingRestart"] = not secret and _as_text(booted) != _as_text(effective)
    row["bootOutcome"] = boot.outcome


def _readonly_rows(settings: Settings, env: dict[str, Any]) -> list[dict[str, Any]]:
    """Every setting NOT curated for editing — visible behind "show all", never
    editable (ruling 3), with secrets masked."""
    curated = {s.key for s in SETTINGS}
    out: list[dict[str, Any]] = []
    for key in sorted(Settings.model_fields):
        if key in curated:
            continue
        secret = is_secret(key)
        value = getattr(settings, key, None)
        out.append({
            "key": key,
            "label": key.replace("_", " ").strip().capitalize(),
            "group": "Other",
            "kind": "text",
            "editable": False,
            "secret": secret,
            "denylisted": key in DENYLIST,
            "value": SECRET_MASK if secret else _as_text(value),
            "envValue": SECRET_MASK if secret else _as_text(env.get(key)),
            "isSet": bool(value) if secret else None,
            "overridden": False,
            "source": _source_of(key, env.get(key), False),
        })
    return out


async def page_payload(store: Optional[SettingsStore]) -> dict[str, Any]:
    """Everything the page renders in one call."""
    settings = get_settings()
    env = config_module.env_values()
    overrides = await store.load() if store is not None else {}

    groups: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
    for spec in SETTINGS:
        groups[spec.group].append(_row(spec, settings, env, overrides.get(spec.key)))

    now = datetime.now(timezone.utc)
    overdue = [
        o.as_dict()
        for o in overrides.values()
        if o.temporary and o.review_at and o.review_at <= now
    ]
    restart_rows = groups.get(GROUP_RESTART, [])
    boot = boot_overrides.state()
    return {
        "environment": settings.environment,
        "overridesActive": settings.overrides_active,
        # The restart-required group, summarised so the page can lead with it
        # when something is waiting rather than burying it at the bottom.
        "restart": {
            "pending": [
                {"key": r["key"], "label": r["label"],
                 "inForce": r.get("inForce"), "stored": r["value"]}
                for r in restart_rows if r.get("pendingRestart")
            ],
            "count": sum(1 for r in restart_rows if r.get("pendingRestart")),
            # How the boot-time load went. `failed` matters: the process is
            # running on its deployment configuration and every stored override
            # for a restart-required setting is NOT in force, whatever it says.
            "bootOutcome": boot.outcome,
            "bootDetail": boot.detail,
        },
        # The break-glass being off is the single most important thing to say
        # loudly: the page still renders, but nothing it saves takes effect.
        "breakGlass": not settings.settings_overrides,
        "writable": store is not None and settings.settings_overrides,
        "groups": [
            {"name": g, "settings": groups[g]} for g in GROUP_ORDER if groups[g]
        ],
        "other": _readonly_rows(settings, env),
        "overrideCount": len(overrides),
        "scopedCount": sum(1 for o in overrides.values() if o.scoped),
        "temporaryCount": sum(1 for o in overrides.values() if o.temporary),
        "overdue": overdue,
        "version": config_module.overrides_version(),
    }


def describe_change(key: str, new_value: str) -> str:
    """One line for the action log / history — no secret ever reaches it."""
    spec = spec_for(key)
    label = spec.label if spec else key
    shown = SECRET_MASK if is_secret(key) else new_value
    return f"{label} ({key}) set to {shown!r}"
