"""Feature readiness — is this feature actually able to work? (plan §5, phase 2)

A flag being on is not the same as a feature running. Two failure classes have
cost real time here and both are invisible from the settings row alone:

* the flag is set on **web** when the **worker** is what does the work — the
  classic "the feature is on but nothing happens"; and
* the feature is on but its **CRM field does not exist yet**, so it stays dark
  by design (the standard feature-detected pattern) with nothing saying so.

So each feature declares what it needs, and this module reports it: the flag,
the settings that must be non-empty, the CRM fields that must exist, which
process reads it, and — for worker features — how long ago the worker last beat.

Read-only and best-effort throughout: a CRM probe that fails reports "unknown",
never an error page.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoClient

log = logging.getLogger("cbm_intake.setup.readiness")


@dataclass(frozen=True)
class Feature:
    key: str
    name: str
    flag: str
    component: str  # web | worker | both
    requires: tuple[str, ...] = ()          # settings that must be non-empty
    crm_fields: tuple[tuple[str, str], ...] = ()   # (entity, field)
    crm_entities: tuple[str, ...] = ()
    needs_database: bool = False
    note: str = ""
    blockers: tuple[str, ...] = field(default=())


FEATURES: tuple[Feature, ...] = (
    Feature(
        key="analytics", name="Analytics", flag="analytics_enabled", component="both",
        note="Mount-time — a change needs a redeploy. Cached results need a database.",
    ),
    Feature(
        key="events", name="Events & Webinars", flag="events_enabled", component="both",
        crm_entities=("CEvent", "CEventRegistration"),
        crm_fields=(("CEvent", "publishToWebsite"), ("CEvent", "slug")),
        note="publishToWebsite is the entire boundary to the public website.",
    ),
    Feature(
        key="events_public", name="Events public API", flag="events_public_api",
        component="web",
        note="Unauthenticated. Also requires a live CRM — there is nothing to serve "
             "in dry-run.",
    ),
    Feature(
        key="zoom", name="Zoom webinars", flag="zoom_events", component="both",
        requires=("zoom_account_id", "zoom_client_id", "zoom_client_secret",
                  "zoom_host_email"),
        note="Public webinars only — never mentor 1:1 sessions.",
    ),
    Feature(
        key="gmail", name="Gmail sync", flag="gmail_sync", component="both",
        requires=("google_service_account_json", "google_delegated_admin"),
        crm_entities=("CConversation", "CCommunication"),
        note="The delegated subject must be a real licensed mailbox — a group 403s.",
    ),
    Feature(
        key="digest", name="Daily email digest", flag="comms_digest", component="worker",
        requires=("ops_mailbox",), needs_database=True,
    ),
    Feature(
        key="inbound", name="Inbound info@ capture", flag="ops_mailbox",
        component="worker", requires=("ops_mailbox",), needs_database=True,
        note="Only ONE environment may poll the shared mailbox — setting it on both "
             "double-captures every thread.",
    ),
    Feature(
        key="gcal", name="Google Calendar events", flag="gcal_events", component="web",
        requires=("google_service_account_json",),
        crm_fields=(("CSession", "googleCalendarEventId"),),
    ),
    Feature(
        key="meet", name="Meet transcripts", flag="meet_transcripts", component="both",
        requires=("google_service_account_json",),
        crm_fields=(("CSession", "sessionTranscription"), ("CSession", "transcriptDocUrl")),
        note="Needs the meetings.space.created DWD scope. Switching this on without "
             "it shows mentors a transcription failure on every Scheduled save.",
    ),
    Feature(
        key="fathom", name="Fathom transcripts", flag="fathom_transcripts",
        component="worker", requires=("fathom_api_key",),
        crm_fields=(("CSession", "sessionTranscription"),),
    ),
    Feature(
        key="gdrive", name="Google Drive documents", flag="gdrive_docs", component="both",
        requires=("google_service_account_json", "gdrive_shared_drive_id"),
        needs_database=True,
    ),
    Feature(
        key="provisioning", name="Mentor provisioning", flag="mentor_provision_users",
        component="web", requires=("espo_provision_username", "espo_provision_password"),
        note="Two events: the Google account at Accepted-Provisional (which then moves "
             "the mentor to Provisional), the CRM login at Approved/Active. EspoCRM "
             "makes User creation admin-only, so this runs as the dedicated admin "
             "service account. Creating the account also needs the Google Workspace "
             "connection; the members group is skipped unless an address is set.",
    ),
    Feature(
        key="async", name="Asynchronous delivery", flag="async_delivery",
        component="both", needs_database=True,
    ),
    Feature(
        key="actionlog", name="Action history", flag="", component="both",
        crm_entities=("CActionLog",),
        note="Feature-detected: the stream note always posts; the reporting row waits "
             "for the CRM entity.",
    ),
)


async def _crm_snapshot(settings: Settings) -> Optional[dict[str, Any]]:
    """Entity + field existence in one pass. None when we cannot ask the CRM."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    client = EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )
    wanted_entities: set[str] = set()
    for feature in FEATURES:
        wanted_entities.update(feature.crm_entities)
        wanted_entities.update(entity for entity, _ in feature.crm_fields)
    try:
        scopes = await client.metadata("scopes")
    except Exception as exc:  # noqa: BLE001 — probe: unknown, never an error page
        log.debug("readiness: scopes probe failed: %s", exc)
        return None
    present = {e for e in wanted_entities if isinstance(scopes, dict) and e in scopes}

    async def _fields(entity: str) -> tuple[str, set[str]]:
        try:
            defs = await client.metadata(f"entityDefs.{entity}")
            return entity, set((defs or {}).get("fields", {}))
        except Exception as exc:  # noqa: BLE001
            log.debug("readiness: %s fields probe failed: %s", entity, exc)
            return entity, set()

    results = await asyncio.gather(*(_fields(e) for e in sorted(present)))
    return {"entities": present, "fields": dict(results)}


def _requirement_rows(feature: Feature, settings: Settings) -> list[dict[str, Any]]:
    rows = []
    for key in feature.requires:
        value = getattr(settings, key, None)
        rows.append({
            "kind": "setting",
            "label": key,
            # Never the value — several of these are secrets.
            "ok": bool(value),
            "detail": "set" if value else "not set",
        })
    if feature.needs_database:
        rows.append({
            "kind": "database",
            "label": "DATABASE_URL",
            "ok": bool(settings.database_url),
            "detail": "attached" if settings.database_url else "not attached",
        })
    return rows


def _crm_rows(feature: Feature, crm: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity in feature.crm_entities:
        if crm is None:
            rows.append({"kind": "entity", "label": entity, "ok": None, "detail": "unknown"})
        else:
            ok = entity in crm["entities"]
            rows.append({
                "kind": "entity", "label": entity, "ok": ok,
                "detail": "present" if ok else "missing",
            })
    for entity, fname in feature.crm_fields:
        if crm is None:
            rows.append({
                "kind": "field", "label": f"{entity}.{fname}", "ok": None,
                "detail": "unknown",
            })
            continue
        fields = crm["fields"].get(entity)
        if fields is None:
            rows.append({
                "kind": "field", "label": f"{entity}.{fname}", "ok": False,
                "detail": f"{entity} missing",
            })
        else:
            ok = fname in fields
            rows.append({
                "kind": "field", "label": f"{entity}.{fname}", "ok": ok,
                "detail": "present" if ok else "missing — feature stays dark",
            })
    return rows


async def readiness_payload(settings: Settings, store: Any = None) -> dict[str, Any]:
    """One row per feature: flag, requirements, CRM prerequisites, component."""
    crm = await _crm_snapshot(settings)

    heartbeat_age: Optional[float] = None
    if store is not None:
        try:
            metrics = await store.metrics()
            heartbeat_age = metrics.get("workerHeartbeatAgeSeconds")
        except Exception as exc:  # noqa: BLE001 — best effort
            log.debug("readiness: worker heartbeat unavailable: %s", exc)

    worker_stale = (
        heartbeat_age is None or heartbeat_age > settings.worker_heartbeat_alert_seconds
    )

    features = []
    for feature in FEATURES:
        on = bool(getattr(settings, feature.flag, False)) if feature.flag else True
        checks = _requirement_rows(feature, settings) + _crm_rows(feature, crm)
        unmet = [c for c in checks if c["ok"] is False]
        unknown = [c for c in checks if c["ok"] is None]
        # A worker feature that is ON with no live worker is the exact shape of
        # "the flag is set but nothing happens" — call it out explicitly.
        worker_warning = (
            on and feature.component in ("worker", "both") and worker_stale
        )
        features.append({
            "key": feature.key,
            "name": feature.name,
            "flag": feature.flag,
            "on": on,
            "component": feature.component,
            "note": feature.note,
            "checks": checks,
            "unmet": len(unmet),
            "unknown": len(unknown),
            "status": (
                "off" if not on
                else "blocked" if unmet
                else "unknown" if unknown
                else "ready"
            ),
            "workerWarning": worker_warning,
        })

    return {
        "features": features,
        "crmReachable": crm is not None,
        "crm": settings.espo_base_url,
        "dryRun": settings.espo_dry_run,
        "workerHeartbeatAgeSeconds": heartbeat_age,
        "workerStale": worker_stale,
        "workerThresholdSeconds": settings.worker_heartbeat_alert_seconds,
    }
