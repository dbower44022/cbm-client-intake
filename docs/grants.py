"""Drive access grants — DOC-09 (PRD v1.3 §3.4, decisions D-08/D-09).

The access model (Doug's rulings 2026-07-16, final): the service account is
the shared drive's ONLY member and performs all Drive operations
(``GDRIVE_IDENTITY=service``); no person ever holds drive membership. Human
Drive access exists solely as per-person, folder-level **Commenter** grants
that mirror CRM entitlements:

  * ``CEngagement`` folders   -> the assigned mentor + co-mentors
  * ``CPartnerProfile``       -> the assigned partner manager
  * ``CSponsorProfile``       -> the assigned sponsor manager
  * ``Contact`` (mentor personnel folders) -> **NO ONE** — application-only

The person's Workspace address is their ``CMentorProfile.cbmEmail``.
Commenter permits open/download/comment only — grant-holders cannot create,
modify, move, delete, or re-share, so every document still enters through the
application (DOC-01's index cannot be bypassed).

Grants are issued/revoked by the same app actions that change the entitlement
(engagement assignment, co-mentor add/remove, folder creation at first
upload) via :func:`sync_record_grants_safe` — always best-effort: a grant
failure never fails the business action (it is logged; the nightly
reconciliation in :mod:`docs.reconcile` is the backstop and also covers
changes made directly in the CRM, e.g. partner/sponsor manager changes and
mentor offboarding, which have no in-app action).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoClient
from core.gdrive import DriveClient

log = logging.getLogger("cbm_intake.docs.grants")

COMMENTER = "commenter"

# Entities whose record folders carry grants, and how the entitled people are
# derived. Contact (mentor personnel) folders are deliberately ABSENT: they are
# granted to no one, and the reconciliation strips any grant found on them.
_ENGAGEMENT = "CEngagement"
_PARTNER = "CPartnerProfile"
_SPONSOR = "CSponsorProfile"
_MENTOR_PROFILE = "CMentorProfile"

# The parent-manager FK per profile entity (single manager).
_MANAGER_FK = {_PARTNER: "partnerManagerId", _SPONSOR: "cBMSponsorManagerId"}


def grants_enabled(settings: Settings) -> bool:
    """Grant management runs only under the ruled access model: documents on,
    the service account operating as ITSELF (drive membership), and a real CRM
    to derive entitlements from. In ``user`` identity mode humans are drive
    members, so folder grants would be meaningless."""
    return bool(
        settings.gdrive_docs
        and settings.gdrive_identity == "service"
        and settings.gdrive_shared_drive_id
        and not settings.espo_dry_run
        and settings.espo_api_key
    )


def system_espo(settings: Settings) -> EspoClient:
    """The app's own API-key CRM client — entitlement derivation must not vary
    with the acting user's ACL (the API role reads all the entities involved)."""
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


async def service_drive(settings: Settings) -> Optional[DriveClient]:
    """A Drive client acting as the service account itself (the drive's sole
    member). None when the service-account credentials aren't configured."""
    from comms.service import get_service_account

    sa_info = await get_service_account(settings)
    if sa_info is None:
        return None
    return DriveClient(
        sa_info,
        "the application",  # attribution only — never an auth subject
        settings.gdrive_shared_drive_id,
        timeout=max(settings.request_timeout_seconds, 60),
        impersonate=False,
    )


async def _profile_email(espo: Any, profile_id: str) -> Optional[str]:
    """The mentor profile's Workspace address (``cbmEmail``), or None."""
    profile = await espo.get(_MENTOR_PROFILE, profile_id, select="cbmEmail")
    email = (profile.get("cbmEmail") or "").strip()
    return email or None


async def entitled_emails(espo: Any, entity_type: str, record_id: str) -> set[str]:
    """The Workspace addresses the CRM currently entitles to ``record_id``'s
    folder (lower-cased). Contact — and any unknown anchor — returns the empty
    set: those folders are application-only."""
    emails: set[str] = set()
    if entity_type == _ENGAGEMENT:
        eng = await espo.get(entity_type, record_id, select="mentorProfileId")
        if eng.get("mentorProfileId"):
            email = await _profile_email(espo, eng["mentorProfileId"])
            if email:
                emails.add(email)
        related = await espo.list_related(
            entity_type, record_id, "additionalMentors", select="cbmEmail", max_size=50
        )
        for row in related.get("list", []):
            email = (row.get("cbmEmail") or "").strip()
            if email:
                emails.add(email)
    elif entity_type in _MANAGER_FK:
        fk = _MANAGER_FK[entity_type]
        record = await espo.get(entity_type, record_id, select=fk)
        if record.get(fk):
            email = await _profile_email(espo, record[fk])
            if email:
                emails.add(email)
    return {e.lower() for e in emails}


async def apply_folder_grants(
    drive: DriveClient, folder_id: str, desired: set[str]
) -> dict[str, Any]:
    """Make the folder's DIRECT user grants exactly ``desired`` at Commenter.

    Inherited permissions (the service account's drive membership) are never
    touched. An entitled person holding the wrong role is corrected to
    Commenter (Editor would let them bypass the app's index — D-09); anyone
    the CRM doesn't justify is removed. Non-inherited ``group``/``domain``/
    ``anyone`` permissions are NEVER justified by the access model (the CRM
    entitles individual people only) — a console-added org-wide share would
    otherwise silently outlive every reconciliation (review docs-F9), so they
    are revoked like any stray grant. Per-grant best-effort: one failure is
    recorded and the rest still apply."""
    desired = {e.lower() for e in desired if e}
    added: list[str] = []
    removed: list[dict[str, str]] = []
    errors: list[str] = []
    current: dict[str, dict[str, Any]] = {}
    for perm in await drive.list_permissions(folder_id):
        if perm.get("inherited"):
            continue
        if perm.get("type") != "user":
            # group/domain/anyone: the model never grants these — revoke.
            label = (
                perm.get("emailAddress")
                or perm.get("domain")
                or perm.get("type")
                or "?"
            )
            try:
                await drive.delete_permission(folder_id, perm["id"])
                removed.append({
                    "email": f"{perm.get('type')}:{label}",
                    "role": perm.get("role") or "?",
                })
            except Exception as exc:  # noqa: BLE001 — per-grant best-effort
                errors.append(f"remove {perm.get('type')}:{label}: {exc}")
            continue
        email = (perm.get("emailAddress") or "").lower()
        if email:
            current[email] = perm
    for email, perm in current.items():
        role_ok = perm.get("role") == COMMENTER
        if email in desired and role_ok:
            continue
        try:
            await drive.delete_permission(folder_id, perm["id"])
            removed.append({"email": email, "role": perm.get("role") or "?"})
        except Exception as exc:  # noqa: BLE001 — per-grant best-effort
            errors.append(f"remove {email}: {exc}")
            if email in desired:
                desired.discard(email)  # don't double-grant a failed downgrade
    for email in sorted(desired):
        perm = current.get(email)
        if perm is not None and perm.get("role") == COMMENTER:
            continue
        try:
            await drive.create_permission(folder_id, email, COMMENTER)
            added.append(email)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"grant {email}: {exc}")
    return {"added": added, "removed": removed, "errors": errors}


async def sync_record_grants(
    settings: Settings,
    entity_type: str,
    record_id: str,
    *,
    folder_id: Optional[str] = None,
    espo: Any = None,
    drive: Optional[DriveClient] = None,
) -> Optional[dict[str, Any]]:
    """Re-derive one record's entitled set from the CRM and make its folder's
    grants match. Returns the applied diff, or None when grants are disabled /
    the record has no folder yet (nothing to grant on — folder creation at
    first upload calls this again)."""
    if not grants_enabled(settings):
        return None
    if folder_id is None:
        from .service import get_store

        store = get_store(settings)
        if store is None:
            return None
        folder_id = await store.cached_folder_id(entity_type, record_id)
    if not folder_id:
        return None
    if drive is None:
        drive = await service_drive(settings)
    if drive is None:
        return None
    desired = await entitled_emails(espo or system_espo(settings), entity_type, record_id)
    result = await apply_folder_grants(drive, folder_id, desired)
    if result["added"] or result["removed"] or result["errors"]:
        log.info(
            "drive grants synced (%s %s, folder %s): +%s -%s errors=%s",
            entity_type, record_id, folder_id,
            result["added"], result["removed"], result["errors"],
        )
    return result


async def sync_record_grants_safe(
    settings: Settings, entity_type: str, record_id: str, **kwargs: Any
) -> Optional[dict[str, Any]]:
    """Best-effort wrapper for the business-action hooks (assignment,
    co-mentor add/remove, first upload): a grant failure NEVER fails the
    action — it is logged and the nightly reconciliation corrects it."""
    try:
        return await sync_record_grants(settings, entity_type, record_id, **kwargs)
    except Exception as exc:  # noqa: BLE001 — hook must not raise
        log.warning(
            "drive grant sync failed (%s %s): %s — the nightly reconciliation "
            "will correct it", entity_type, record_id, exc,
        )
        return None
