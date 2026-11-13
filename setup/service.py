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

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core import boot_overrides
from core import config as config_module
from core import branding
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
from core.settings_registry import BY_KEY, INTEGRATION_TAGS
from core.settings_store import Override, SettingsStore, scoped_overrides
from integrations import checklist
from integrations import guard as integration_guard
from integrations import registry as integration_registry
from integrations.registry import IN_USE_KEYS, INTEGRATIONS

log = logging.getLogger("cbm_intake.setup.service")

#: Settings that only mean anything while the Integrations tab is on: the
#: nightly integration test's hour and time zone (phase 5). Hidden with the
#: switch off, like the "in use" settings, so the page is exactly as before.
TAB_ONLY_KEYS = frozenset({"integration_test_hour", "integration_test_tz",
                           "integration_agent_model", "integration_agent_monthly_budget"})

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
        "label": branding.render_text(spec.label, settings),
        "group": spec.group,
        "kind": spec.kind,
        "choices": list(spec.choices),
        "unit": spec.unit,
        "help": branding.render_text(spec.help, settings) if spec.help else spec.help,
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


async def page_payload(
    store: Optional[SettingsStore],
    test_runs: Optional[dict[str, dict[str, Any]]] = None,
    checklist_state: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Everything the page renders in one call. ``test_runs`` is the last
    integration test of each integration (integrations/store.py), read only
    while the Integrations tab is on."""
    settings = get_settings()
    env = config_module.env_values()
    overrides = await store.load() if store is not None else {}

    # The Integrations tab (prds/integrations-tab-plan.md). Off: every
    # setting renders exactly as before, and the "in use" settings — which
    # only mean anything on that tab — are left out. On: every setting tagged
    # with an integration leaves its group for its sub-tab, and a group left
    # empty disappears with it.
    tab_on = bool(settings.integrations_tab)
    groups: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
    tagged: dict[str, dict[str, Any]] = {}
    for spec in SETTINGS:
        if (spec.key in IN_USE_KEYS or spec.key in TAB_ONLY_KEYS) and not tab_on:
            continue
        row = _row(spec, settings, env, overrides.get(spec.key))
        if tab_on and spec.integration:
            tagged[spec.key] = row
            continue
        groups[spec.group].append(row)

    now = datetime.now(timezone.utc)
    overdue = [
        o.as_dict()
        for o in overrides.values()
        if o.temporary and o.review_at and o.review_at <= now
    ]
    restart_rows = groups.get(GROUP_RESTART, [])
    boot = boot_overrides.state()
    # A change that is live but will undo itself unless somebody says the system
    # still works. The page has to lead with this — the whole mechanism depends
    # on an admin seeing it before the deadline.
    awaiting = [
        {
            "key": o.key,
            "label": (spec_for(o.key).label if spec_for(o.key) else o.key),
            "revertAt": o.revert_at.isoformat() if o.revert_at else None,
        }
        for o in overrides.values() if o.awaiting_confirmation
    ]
    payload = {
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
        "awaitingConfirmation": awaiting,
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
    if tab_on:
        payload["integrationsTab"] = True
        payload["integrations"] = _integrations(settings, env, overrides, tagged,
                                                test_runs or {}, checklist_state or {})
    return payload


# What brings each placeholder on a sub-tab (the build phases, plan § 8).
DIAGNOSIS_PHASE = 6
CHECKLIST_PHASE = 4


def _integrations(
    settings: Settings,
    env: dict[str, Any],
    overrides: dict[str, Override],
    tagged: dict[str, dict[str, Any]],
    test_runs: dict[str, dict[str, Any]],
    checklist_state: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """One entry per integration, in registry order: its status line, its
    settings (rendered by the same ``_row`` as the Settings tab) and its
    "Used by" list."""
    order = {key: i for i, key in enumerate(INTEGRATION_TAGS)}
    scoped = scoped_overrides()
    cs = checklist_state or {}
    state = checklist.State(
        settings=settings, overrides=overrides, test_runs=test_runs,
        ticks=cs.get("ticks") or {}, mailing_connected=cs.get("mailingConnected"),
        stored_google=cs.get("storedGoogle") or {},
    )
    try:
        steps = checklist.load_steps()
    except Exception as exc:  # noqa: BLE001 — the rest of the page still renders
        log.warning("setup checklist steps could not be read: %s", exc)
        steps = None
    out: list[dict[str, Any]] = []
    for integ in INTEGRATIONS:
        rows = sorted(
            (r for k, r in tagged.items() if INTEGRATION_TAGS[k][0] == integ.key),
            key=lambda r: order[r["key"]],
        )
        top = [r for r in rows if not BY_KEY[r["key"]].section]
        sections = [
            {
                "key": sec.key,
                "title": sec.title,
                "settings": [r for r in rows if BY_KEY[r["key"]].section == sec.key],
            }
            for sec in integ.sections
        ]
        used_by = []
        for u in integ.used_by:
            spec = BY_KEY.get(u.key)
            if spec is None:
                continue
            row = _row(spec, settings, env, overrides.get(u.key))
            used_by.append({
                "key": u.key,
                "label": row["label"],
                "group": spec.group,
                "kind": row["kind"],
                "value": row["value"],
                "secret": row["secret"],
                "isSet": row["isSet"],
                "unit": row["unit"],
                "blocks": u.blocks,
            })
        on_keys = integration_guard.switches_on(integ, settings, scoped)
        missing = [
            branding.render_text(BY_KEY[k].label, settings) if k in BY_KEY else k
            for k in integ.credentials if not getattr(settings, k, None)
        ]
        status: dict[str, Any] = {
            "alwaysInUse": integ.always_in_use,
            "inUse": integration_registry.in_use(integ, settings),
            "hasSwitches": bool(integ.blocking_switches),
            "on": bool(on_keys),
            "onSwitches": [
                branding.render_text(BY_KEY[k].label, settings) if k in BY_KEY else k
                for k in on_keys
            ],
            "credentialsMissing": missing,
            # The last integration test, or None: "Not tested yet".
            "tested": test_runs.get(integ.key) if integ.testable else None,
        }
        if integ.key == "espocrm":
            # EspoCRM has no feature switch; what it can be is writing or not.
            status["hasSwitches"] = True
            status["on"] = not settings.espo_dry_run
            status["dryRun"] = bool(settings.espo_dry_run)
        out.append({
            "key": integ.key,
            "name": integ.name,
            "inUseKey": integ.in_use_setting,
            "testable": integ.testable,
            "status": status,
            "checklist": (checklist.build(integ, state, steps) if steps is not None
                          else {"rows": [], "done": 0, "total": 0,
                                "error": "The deployment guide's step files could not be read."}),
            "ticksStored": bool(cs.get("ticksStored")),
            # The diagnosis agent (phase 6): the last fix plan, and what
            # diagnoses have spent this month against the budget.
            "fixPlan": (cs.get("fixPlans") or {}).get(integ.key),
            # The setup assistant (phase 7): the last setup plan.
            "setupPlan": (cs.get("setupPlans") or {}).get(integ.key),
            "agent": {"spent": cs.get("agentSpent"),
                      "budget": float(settings.integration_agent_monthly_budget or 0),
                      "keySet": bool((settings.anthropic_api_key or "").strip()),
                      "stored": cs.get("agentSpent") is not None},
            "settings": top,
            "sections": sections,
            "usedBy": used_by,
            "features": list(integ.features),
            "runbooks": list(integ.runbooks),
            "phases": {
                "test": integ.test_phase,
                "diagnosis": DIAGNOSIS_PHASE,
                "checklist": CHECKLIST_PHASE,
            },
        })
    return out


def describe_change(key: str, new_value: str) -> str:
    """One line for the action log / history — no secret ever reaches it."""
    spec = spec_for(key)
    label = spec.label if spec else key
    shown = SECRET_MASK if is_secret(key) else new_value
    return f"{label} ({key}) set to {shown!r}"
