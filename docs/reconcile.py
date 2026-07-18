"""Nightly Drive-grant reconciliation — DOC-09 (PRD v1.3 §3.4/§5).

Runs in the delivery worker on its own timer (``GDRIVE_RECONCILE_SECONDS``,
default daily — the monitoring-check pattern). For every record that owns a
Drive folder (from the ``app_document`` metadata), it re-derives the complete
entitled set from the CRM and corrects BOTH directions of drift: grants the
CRM justifies but Drive lacks (a failed business-action hook, a manager
change made directly in the CRM, mentor offboarding) are added, and grants
the CRM no longer justifies are removed. Corrections are logged; removals are
surfaced as alerts (they are by definition unexpected — every entitled person
should already hold exactly a Commenter grant). Mentor personnel (Contact)
folders derive an EMPTY entitled set, so any grant found on one is stripped.

It also re-checks the DOC-08 ``documentsFolderUrl`` write-back per folder
(self-healing best-effort — Doug's ruling 2026-07-17, no retry queue).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core import monitoring
from core.config import Settings

from . import grants
from . import service as docs_service

log = logging.getLogger("cbm_intake.docs.reconcile")

# Folders that errored on consecutive passes (folder id -> count). A single
# blip self-heals next pass; the SAME folder failing again means its grants
# are silently drifting from the CRM — that persists, so it alerts (review
# docs-F9: errors previously never alerted, only removals). In-memory is fine:
# the worker is one long-lived process, and a restart merely delays the alert
# by one pass.
_error_passes: dict[str, int] = {}
_PERSISTENT_ERROR_PASSES = 2


async def run_docs_reconciliation(
    settings: Settings,
    *,
    store: Any = None,
    espo: Any = None,
    drive: Any = None,
    send: Any = None,
) -> Optional[dict[str, Any]]:
    """One full pass. Returns a summary dict, or None when the access model
    isn't active (grants exist only under ``GDRIVE_IDENTITY=service``)."""
    if not grants.grants_enabled(settings):
        return None
    store = store or docs_service.get_store(settings)
    if store is None:
        return None
    drive = drive or await grants.service_drive(settings)
    if drive is None:
        log.warning("docs reconciliation: no Google service-account credentials")
        return None
    espo = espo or grants.system_espo(settings)
    if send is None:
        async def send(text: str) -> None:
            await monitoring.send_alert(settings, text)

    summary = {"folders": 0, "granted": 0, "revoked": 0, "errors": 0, "linksWritten": 0}
    removal_lines: list[str] = []
    persistent_error_lines: list[str] = []

    def _track_errors(folder: str, label: str, had_errors: bool) -> None:
        """Consecutive-pass error tracking: the SAME folder erroring again
        means its grants are silently drifting — that alerts."""
        if not had_errors:
            _error_passes.pop(folder, None)
            return
        _error_passes[folder] = _error_passes.get(folder, 0) + 1
        if _error_passes[folder] == _PERSISTENT_ERROR_PASSES:
            persistent_error_lines.append(f"{label} (folder {folder})")

    for rec in await store.list_folder_records():
        entity_type, record_id = rec["entityType"], rec["recordId"]
        folder_id = rec["driveFolderId"]
        label = f"{entity_type} {record_id}"
        summary["folders"] += 1
        try:
            desired = await grants.entitled_emails(espo, entity_type, record_id)
            result = await grants.apply_folder_grants(drive, folder_id, desired)
        except Exception as exc:  # noqa: BLE001 — one folder never stops the pass
            summary["errors"] += 1
            log.warning(
                "docs reconciliation: %s (folder %s) failed: %s",
                label, folder_id, exc,
            )
            _track_errors(folder_id, label, True)
            continue
        summary["granted"] += len(result["added"])
        summary["revoked"] += len(result["removed"])
        summary["errors"] += len(result["errors"])
        _track_errors(folder_id, label, bool(result["errors"]))
        for email in result["added"]:
            log.info(
                "docs reconciliation: granted %s Commenter on %s %s (folder %s)",
                email, entity_type, record_id, folder_id,
            )
        for gone in result["removed"]:
            log.info(
                "docs reconciliation: removed %s (%s) from %s %s (folder %s)",
                gone["email"], gone["role"], entity_type, record_id, folder_id,
            )
            removal_lines.append(
                f"{gone['email']} ({gone['role']}) on {entity_type} {record_id}"
            )
        for err in result["errors"]:
            log.warning(
                "docs reconciliation: grant correction failed on %s %s: %s",
                entity_type, record_id, err,
            )
        # DOC-08 re-check: the CRM folder link self-heals here too.
        try:
            link = await docs_service.write_back_folder_link(
                settings, drive, entity_type, record_id, folder_id, espo=espo
            )
            if link:
                summary["linksWritten"] += 1
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            log.warning(
                "docs reconciliation: documentsFolderUrl re-check failed "
                "(%s %s): %s", entity_type, record_id, exc,
            )
    if removal_lines:
        await send(
            "Drive grant reconciliation removed grant(s) the CRM no longer "
            "justifies:\n" + "\n".join(removal_lines)
        )
    if persistent_error_lines:
        await send(
            "Drive grant reconciliation keeps FAILING for these record folders "
            "(second consecutive pass) — their access grants may be drifting "
            "from the CRM:\n" + "\n".join(persistent_error_lines)
        )
    log.info(
        "docs reconciliation done: %s folder(s), +%s grant(s), -%s, "
        "%s CRM link(s) written, %s error(s)",
        summary["folders"], summary["granted"], summary["revoked"],
        summary["linksWritten"], summary["errors"],
    )
    return summary
