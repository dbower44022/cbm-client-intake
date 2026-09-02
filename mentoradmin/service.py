"""Mentor Admin — read the full mentor record and update editable fields.

The editable-field set is declared here (the single source for the form layout
and the update whitelist); enum/multi-enum *options* are pulled live from
EspoCRM metadata so the CRM stays the source of truth. Computed totals
(availableCapacity, currentActiveClients, totals) are read-only.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Protocol

from core.config import get_settings
from core.espo import EspoError
from core.phone import to_e164
from core.google_directory import (
    GoogleDirectoryError,
    MailboxStatus,
    gen_temp_password,
)
# The mentor's User link uses the single `assignedUser` on crm-test but the
# multi-user `assignedUsers` (collaborators) on prod. These helpers read/write
# both shapes so the link sticks on either (see assignments.service).
from assignments.service import (
    assigned_user_id,
    assigned_user_payload,
    client_counts_for,
    mentor_engagement_metrics,
)

log = logging.getLogger("cbm_intake.mentoradmin.service")

MENTOR_PROFILE = "CMentorProfile"

# How long the status window waits for a just-created mailbox to become live
# before handing off to the EspoCRM login (poll every N seconds, up to a cap).
MAILBOX_POLL_SECONDS = 5
MAILBOX_POLL_TIMEOUT = 60


class MailboxDirectory(Protocol):
    """The slice of ``core.google_directory.GoogleDirectory`` provisioning uses."""

    async def mailbox_status(self, email: str) -> MailboxStatus: ...
    async def create_user(
        self, primary_email: str, first_name: str, last_name: str,
        *, recovery_email: Optional[str], temp_password: str,
    ) -> None: ...
    async def add_group_member(self, group_email: str, member_email: str) -> None: ...
    async def is_group_member(self, group_email: str, member_email: str) -> Optional[bool]: ...


# --- The two provisioning events, and the statuses that trigger them ---------
# A mentor is provisioned in TWO stages (Doug's ruling 2026-08-17):
#
#   Accepted-Provisional  → create the Google Workspace account, add it to the
#                           All Members group, then ADVANCE the record to
#                           Provisional. No EspoCRM login.
#   Provisional           → the resting state: they have their account and are
#                           serving their provisional period. Nothing happens.
#   Approved / Active     → the EspoCRM login User (unchanged), on top of the
#                           mailbox check/create. NEVER writes Provisional back —
#                           a mentor may jump straight here from
#                           Accepted-Provisional, and that must not demote them.
#
# So `Accepted-Provisional` is a SIGNAL status, not a resting one: it means
# "accepted, and still needs a Google account".
STATUS_APPROVED = "Approved"
STATUS_ACTIVE = "Active"
STATUS_ACCEPTED_PROVISIONAL = "Accepted-Provisional"
STATUS_PROVISIONAL = "Provisional"
# Statuses at which a login User is provisioned.
LOGIN_STATUSES = (STATUS_APPROVED, STATUS_ACTIVE)
# Statuses at which the email-account-only flow runs.
EMAIL_STATUSES = (STATUS_ACCEPTED_PROVISIONAL, STATUS_PROVISIONAL)

# Sign-off flags every complete mentor must have set (field -> label).
# (Background check is optional — deliberately not required for completeness.)
COMPLETENESS_FLAGS = [
    ("ethicsAgreementAccepted", "ethics agreement"),
    ("trainingCompleted", "training completed"),
    ("termsAccepted", "terms accepted"),
]
# CBM-issued email/login domain: userName = firstname.lastname@<domain>. The
# domain is a setting (``MENTOR_EMAIL_DOMAIN``, default Cleveland's) since the
# Lakeside rehearsal showed a chapter with its own Workspace needs its own.
CBM_EMAIL_DOMAIN = "cbmentors.org"  # the default; read the setting, not this


def cbm_email_domain() -> str:
    return (get_settings().mentor_email_domain or CBM_EMAIL_DOMAIN).strip().lower()
DEFAULT_MENTOR_TEAM = "Mentor Team"
USER_TYPE = "regular"

# Shown when someone tries to assign teams to a mentor with no login User yet
# (Permission Teams live on the login User; a mentor without one has nothing to
# assign them to). Doug's exact wording.
NO_LOGIN_TEAM_MESSAGE = (
    "The Mentor is not Active yet, and so cannot be assigned teams."
)


class MentorAdminError(Exception):
    """A mentor-admin operation could not be completed (e.g. team not found)."""


class MentorClient(Protocol):
    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def find_one(self, entity: str, attribute: str, value: str, select: str = ...) -> Optional[dict[str, Any]]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def metadata(self, key: str) -> Any: ...


CONTACT_ENTITY = "Contact"

# Editable fields, grouped for the form (one tab per group). ``type`` drives the
# input + how the value is sent; ``row`` (optional) sub-groups fields within a
# tab; ``options`` (optional) supplies a static dropdown list for a field whose
# CRM type is free-text. Order is the display order. ``entity: "Contact"`` marks
# a field that lives on the mentor's linked Contact record (the Contact tab):
# its value is merged into the detail response and a change is saved to the
# Contact, not the profile.
EDITABLE_FIELDS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "type": "varchar", "group": "Profile"},
    {"name": "firstName", "label": "First name", "type": "varchar", "group": "Contact", "row": "personname", "entity": CONTACT_ENTITY},
    {"name": "lastName", "label": "Last name", "type": "varchar", "group": "Contact", "row": "personname", "entity": CONTACT_ENTITY},
    {"name": "emailAddress", "label": "Email", "type": "varchar", "group": "Contact", "row": "reach", "entity": CONTACT_ENTITY},
    {"name": "phoneNumber", "label": "Phone", "type": "varchar", "group": "Contact", "row": "reach", "entity": CONTACT_ENTITY},
    {"name": "addressStreet", "label": "Street address", "type": "text", "group": "Contact", "entity": CONTACT_ENTITY},
    {"name": "addressCity", "label": "City", "type": "varchar", "group": "Contact", "row": "citystate", "entity": CONTACT_ENTITY},
    {"name": "addressState", "label": "State", "type": "varchar", "group": "Contact", "row": "citystate", "entity": CONTACT_ENTITY},
    {"name": "addressPostalCode", "label": "ZIP code", "type": "varchar", "group": "Contact", "row": "citystate", "entity": CONTACT_ENTITY},
    {"name": "mentorStatus", "label": "Status", "type": "enum", "group": "Status", "row": "statustype"},
    {"name": "mentorType", "label": "Type", "type": "enum", "group": "Status", "row": "statustype"},
    # Pause window on its own line, directly under the status/type selectors.
    {"name": "mentorPauseStartDate", "label": "Mentor pause start date", "type": "date", "group": "Status", "row": "pause"},
    {"name": "mentorPauseEndDate", "label": "Mentor pause end date", "type": "date", "group": "Status", "row": "pause"},
    {"name": "acceptingNewClients", "label": "Accepting new clients", "type": "bool", "group": "Status"},
    {"name": "publicProfile", "label": "Public profile", "type": "bool", "group": "Status"},
    # Start date + the volunteer form's "are you employed" answer share a line
    # (Doug, 2026-09-01). Employment status lives on the linked Contact
    # (cEmploymentStatus — the same field the volunteer intake writes), so it
    # routes through CONTACT_NAMES like the Contact tab's fields.
    {"name": "mentorStartDate", "label": "Mentor start date", "type": "date", "group": "Status", "row": "startrow"},
    {"name": "cEmploymentStatus", "label": "Employment status", "type": "enum", "group": "Status", "row": "startrow", "entity": CONTACT_ENTITY},
    {"name": "mentorStatusNotes", "label": "Status notes", "type": "text", "group": "Status"},
    {"name": "maximumClientCapacity", "label": "Maximum client capacity", "type": "int", "group": "Capacity"},
    {"name": "yearsOfExperience", "label": "Years of experience", "type": "int", "group": "Capacity"},
    {"name": "industryExperience", "label": "Industry experience", "type": "multiEnum", "group": "Expertise"},
    {"name": "areaOfExpertise", "label": "Areas of expertise", "type": "multiEnum", "group": "Expertise"},
    {"name": "fluentLanguages", "label": "Fluent languages", "type": "multiEnum", "group": "Expertise"},
    # Compliance: checkboxes on the top row, dates (and dues status) below.
    {"name": "backgroundCheckCompleted", "label": "Background check completed", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "ethicsAgreementAccepted", "label": "Ethics agreement accepted", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "trainingCompleted", "label": "Training completed", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "termsAccepted", "label": "Terms accepted", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "felonyConfiction", "label": "Felony conviction", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "duesStatus", "label": "Dues status", "type": "enum", "group": "Compliance", "row": "dates"},
    {"name": "backgroundCheckDate", "label": "Background check date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "trainingCompletionDate", "label": "Training completion date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "duesPaymentDate", "label": "Dues payment date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "duesRenewalDate", "label": "Dues renewal date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "departureDate", "label": "Departure date", "type": "date", "group": "Departure"},
    {"name": "departureReason", "label": "Departure reason", "type": "enum", "group": "Departure"},
    {"name": "cbmEmail", "label": "CBM email", "type": "varchar", "group": "Profile"},
    {"name": "boardPosition", "label": "Board position", "type": "varchar", "group": "Profile"},
    # LinkedIn lives on the linked Contact (same field the My Mentor Profile
    # tool + the website preview use), but is shown on the Profile tab.
    {"name": "cLinkedInProfile", "label": "LinkedIn profile", "type": "varchar", "group": "Profile", "entity": CONTACT_ENTITY},
    # No static options: howDidYouHearAboutCBM is a real CRM enum (converted
    # from free-text 2026-07-11), so its options are pulled live like every
    # other enum — a hard-coded list here drifted and 400'd a prod save.
    {"name": "howDidYouHearAboutCBM", "label": "How they heard about CBM", "type": "enum", "group": "Profile"},
    {"name": "description", "label": "Description / notes", "type": "text", "group": "Profile"},
    {"name": "aboutMentor", "label": "About the mentor", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentorProfessionalBio", "label": "Professional bio", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringWhyInterested", "label": "Why interested in mentoring", "type": "wysiwyg", "group": "Bio"},
]

# The update whitelist, split by target entity: profile fields go to
# CMentorProfile, contact fields to the linked Contact.
PROFILE_EDIT_NAMES = {f["name"] for f in EDITABLE_FIELDS if not f.get("entity")}
CONTACT_NAMES = {f["name"] for f in EDITABLE_FIELDS if f.get("entity") == CONTACT_ENTITY}
EDITABLE_NAMES = PROFILE_EDIT_NAMES | CONTACT_NAMES
_ENUM_FIELDS = [f["name"] for f in EDITABLE_FIELDS
                if f["type"] in ("enum", "multiEnum") and not f.get("entity")]
# Enum fields living on the linked Contact (e.g. cEmploymentStatus): their live
# options come from Contact metadata, and they are drift-sanitized like the
# profile enums.
_CONTACT_ENUM_FIELDS = [f["name"] for f in EDITABLE_FIELDS
                        if f["type"] in ("enum", "multiEnum")
                        and f.get("entity") == CONTACT_ENTITY]
_FIELD_LABELS = {f["name"]: f["label"] for f in EDITABLE_FIELDS}

# Read-only context shown above the form. Includes the contact-info "foreign"
# fields CMentorProfile mirrors from the linked Contact (personalEmail/
# contactPhone/contactStreet/contactCity/postalCode) — not editable here (they
# live on the Contact), shown read-only in the summary card.
READ_ONLY_FIELDS = [
    # (The CRM-computed availableCapacity/currentActiveClients are deliberately
    # NOT read — the detail card shows the same app-computed clientCounts as the
    # roster grid; see get_mentor.)
    "maximumClientCapacity",
    "totalLifetimeSessions", "totalSessionsLast30Days", "totalMentoringHours",
    "contactRecordName", "contactRecordId",
    "assignedUserName", "assignedUserId", "assignedUsersNames", "assignedUsersIds",
    "createdAt", "modifiedAt", "recordStatus",
    "personalEmail", "contactPhone", "contactStreet", "contactCity", "postalCode",
]

# recordStatus enum value set manually (in the CRM) — never auto-overwritten.
RECORD_STATUS_MANUAL = "Duplicate"

_DETAIL_SELECT = ",".join(["id"] + sorted(PROFILE_EDIT_NAMES) + READ_ONLY_FIELDS)

# Sentinel: "no precomputed metrics were passed" (None is a real value meaning
# "metrics unavailable"), so get_mentor knows when to compute its own.
_METRICS_UNSET = object()
_CONTACT_SELECT = ",".join(sorted(CONTACT_NAMES))


async def get_mentor(
    client: MentorClient, mentor_id: str, *, metrics: Any = _METRICS_UNSET
) -> dict[str, Any]:
    """The full mentor record: every editable field + read-only context, plus
    ``clientCounts`` — the same app-computed counts the roster grid shows
    (Active/Max/Available/Assigned-30d/Lifetime), so the detail card and the
    grid always agree. Counts are best-effort (None when engagements can't be
    read); ``update_mentor`` returns through here, so a save refreshes them.

    ``metrics``: pass a precomputed :func:`mentor_engagement_metrics` result
    (or None for unavailable) to skip the full-CEngagement sweep — the
    status-check sweep computes it ONCE for the whole roster instead of once
    per mentor (P2, reliability review 2026-07-17)."""
    rec = await client.get(MENTOR_PROFILE, mentor_id, select=_DETAIL_SELECT)
    # Merge the linked Contact's editable fields (name/email/phone/address) into
    # the record for the Contact tab. Best-effort: a mentor with no Contact (or
    # an unreadable one) still opens — the fields just render blank.
    contact_id = rec.get("contactRecordId")
    if contact_id:
        try:
            contact = await client.get(CONTACT_ENTITY, contact_id, select=_CONTACT_SELECT)
            for name in CONTACT_NAMES:
                rec[name] = contact.get(name)
        except Exception as exc:
            log.warning("contact info unavailable for mentor %s: %s", mentor_id, exc)
    if metrics is _METRICS_UNSET:
        try:
            metrics = await mentor_engagement_metrics(client)
        except Exception as exc:  # no CEngagement grant, or a test fake without list()
            log.warning("mentor clientCounts unavailable for %s: %s", mentor_id, exc)
            metrics = None
    rec["clientCounts"] = client_counts_for(
        metrics, mentor_id, rec.get("maximumClientCapacity")
    )
    return rec


async def check_completeness(client: MentorClient, rec: dict[str, Any]) -> dict[str, Any]:
    """Verify the mentor's data structure is complete & correct.

    A ``CMentorProfile`` *is* the "CBM member" record (present by definition when
    viewing it). Always required: a linked **Contact** record + the sign-off flags
    (``COMPLETENESS_FLAGS`` — ethics, training, terms; background check is optional).
    For an **Active** mentor, additionally: a CBM email address, plus a login
    **User** assigned to the member and that same User on the Contact. (``publicProfile``
    is not part of completeness.) Returns
    ``{"status": "Complete"|"Incomplete", "issues": [...]}``.
    """
    issues: list[str] = []
    contact_id = rec.get("contactRecordId")
    if not contact_id:
        issues.append("no linked Contact record")
    for field, label in COMPLETENESS_FLAGS:
        if not rec.get(field):
            issues.append(f"{label} not confirmed")

    if rec.get("mentorStatus") == STATUS_ACTIVE:
        if not rec.get("cbmEmail"):
            issues.append("no CBM email address")
        user_id = assigned_user_id(rec)
        if not user_id:
            issues.append("no User assigned to the mentor")
        # Contact was switched to Multiple Assigned Users on both CRMs
        # (2026-07-16/17, so co-mentors can be assigned too) — the single
        # `assignedUser` is disabled and always reads null. Check membership in
        # either shape, never just `assignedUserId`.
        contact_users: set[str] = set()
        contact_read_ok = False
        if contact_id:
            try:
                contact = await client.get(
                    "Contact", contact_id, select="assignedUserId,assignedUsersIds"
                )
                contact_read_ok = True
                if contact.get("assignedUserId"):
                    contact_users.add(contact["assignedUserId"])
                contact_users.update(contact.get("assignedUsersIds") or [])
            except Exception:
                issues.append("could not read the Contact record")
        if contact_id and contact_read_ok and not contact_users:
            issues.append("no User assigned to the Contact")
        elif user_id and contact_users and user_id not in contact_users:
            issues.append("Contact is assigned to a different User than the mentor")

    return {"status": "Complete" if not issues else "Incomplete", "issues": issues}


async def sync_record_status(
    client: MentorClient, mentor_id: str, rec: dict[str, Any], status: str
) -> str:
    """Persist the computed completeness ``status`` to the ``recordStatus`` enum
    so the roster grid can show it without recomputing per row. Skips a manual
    ``Duplicate`` marking, and only writes when the value actually changes.
    Best-effort. Returns the effective recordStatus.
    """
    current = rec.get("recordStatus")
    if current == RECORD_STATUS_MANUAL:
        return current
    if status and status != current:
        try:
            await client.update(MENTOR_PROFILE, mentor_id, {"recordStatus": status})
            return status
        except Exception as exc:  # noqa: BLE001 — best-effort, but visibly so
            log.warning(
                "recordStatus persist failed for CMentorProfile/%s (wanted %s) "
                "— the grid keeps showing %s: %s", mentor_id, status, current, exc,
            )
            return current
    return current or status


async def _sanitize_enum_changes(
    client: MentorClient, payload: dict[str, Any]
) -> list[str]:
    """Drop enum/multi-enum values the live CRM no longer accepts, in place.

    One drifted option must never 400 the whole save (Doug's policy — see the
    sessions engine's ``_sanitize_enum_payload`` and the orchestrators'
    ``EnumSanitizer``): the rest of the save proceeds, the drop is logged, and a
    plain-language warning per dropped value is returned for the UI to show.
    A single enum is omitted (preserving the stored value); a multi-enum keeps
    its valid members. **Fails open**: if the live options can't be fetched,
    the payload is left untouched — never drop what can't be verified.
    """
    keys = [k for k in payload if k in _ENUM_FIELDS or k in _CONTACT_ENUM_FIELDS]
    if not keys:
        return []
    try:
        options = await field_options(client)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the save
        log.warning("could not fetch enum options (%s); keeping values as-is", exc)
        return []
    warnings: list[str] = []

    def note(name: str, values: list[Any]) -> None:
        entity = CONTACT_ENTITY if name in _CONTACT_ENUM_FIELDS else MENTOR_PROFILE
        log.warning(
            "%s.%s: dropping unrecognized %s (not in the live enum)",
            entity, name, values,
        )
        vals = ", ".join(f"“{v}”" for v in values)
        warnings.append(
            f"{_FIELD_LABELS.get(name, name)}: {vals} is no longer a valid "
            "option in the CRM, so that value was not saved."
        )

    for key in keys:
        opts = options.get(key)
        if opts is None:  # field not in the live options map — unverifiable, keep
            continue
        value = payload[key]
        if isinstance(value, list):  # multiEnum
            dropped = [v for v in value if v not in opts]
            if dropped:
                payload[key] = [v for v in value if v in opts]
                note(key, dropped)
        elif value not in (None, "") and value not in opts:
            del payload[key]
            note(key, [value])
    return warnings


async def update_mentor(
    client: MentorClient,
    mentor_id: str,
    changes: dict[str, Any],
    *,
    team_name: Optional[str] = None,
    admin_client_factory: Optional[Callable[[], Awaitable[MentorClient]]] = None,
    directory: Optional[MailboxDirectory] = None,
) -> dict[str, Any]:
    """Update whitelisted editable fields; ignore anything else. Profile fields
    write to CMentorProfile; Contact-tab fields (``CONTACT_NAMES``) write to the
    mentor's linked Contact record (raising :class:`MentorAdminError` before any
    write when no Contact is linked).

    Side effect: when a save leaves the mentor at status ``Approved`` **or
    ``Active``** with **no linked login user yet** AND ``admin_client_factory`` is
    supplied, provision an EspoCRM User for them, link it to the profile, and
    place it in the mentor team. This is recovery-friendly: it fires whether this
    save flips the status OR the mentor was already Approved/Active but never got
    a user (e.g. set straight to Active, skipping Approved, or a prior attempt
    failed) — so the next save self-heals, rather than requiring the admin to
    toggle the status to re-trigger it. **User
    creation/team lookup run under the privileged client the factory returns** (a
    dedicated admin service account), never the staff ``client`` — so Mentor
    Admin staff need no user-create permission. The factory is awaited lazily
    (and its login errors captured) only when provisioning actually applies.
    Without it (the default), no provisioning is attempted. Runs *after* the
    status write and is best-effort: any failure is captured in the returned
    ``provision`` summary rather than failing the save.

    The **Accepted-Provisional** event (create the Google account, add it to the
    All Members group, advance to Provisional) is deliberately NOT run here: it
    creates a mailbox, and a mailbox create produces a temporary password that a
    human has to relay, so it belongs to the browser's streaming status window
    (:func:`provision_mentor_email_steps`). A save straight over the API therefore
    does nothing Google-side — it cannot create the account whose existence
    ``Provisional`` would be asserting.
    """
    payload = {k: v for k, v in changes.items() if k in PROFILE_EDIT_NAMES}
    contact_payload = {k: v for k, v in changes.items() if k in CONTACT_NAMES}
    warnings = await _sanitize_enum_changes(client, payload)
    warnings += await _sanitize_enum_changes(client, contact_payload)

    # Contact-tab fields save to the linked Contact record. Resolve the link
    # BEFORE any write, so a mentor with no Contact fails fast with a clear
    # error instead of half-saving. Phone is normalized to E.164 at the CRM
    # boundary (EspoCRM rejects other formats with a phone "valid" 400).
    contact_id = None
    if contact_payload:
        prof = await client.get(MENTOR_PROFILE, mentor_id, select="contactRecordId")
        contact_id = prof.get("contactRecordId")
        if not contact_id:
            raise MentorAdminError(
                "This mentor has no linked Contact record, so contact "
                "information can't be saved. Link a Contact in the CRM first."
            )
        phone = contact_payload.get("phoneNumber")
        if isinstance(phone, str) and phone.strip():
            contact_payload["phoneNumber"] = to_e164(phone)

    # When provisioning is possible, read the pre-save status + user link so we
    # can decide on the *effective* status (the change, or the stored value if
    # this save didn't touch status).
    before = None
    if admin_client_factory is not None:
        before = await client.get(
            MENTOR_PROFILE, mentor_id,
            select="mentorStatus,assignedUserId,assignedUsersIds,assignedUsersNames",
        )

    if payload:
        await client.update(MENTOR_PROFILE, mentor_id, payload)
    if contact_payload:
        await client.update(CONTACT_ENTITY, contact_id, contact_payload)

    provision: Optional[dict[str, Any]] = None
    effective_status = (
        payload.get("mentorStatus", before.get("mentorStatus")) if before else None
    )
    if (
        admin_client_factory is not None
        and before is not None
        and effective_status in LOGIN_STATUSES
        and not assigned_user_id(before)
    ):
        try:
            admin_client = await admin_client_factory()
            # Inline (non-streaming) provisioning is a fallback for the redrive /
            # JS-off path; it never *creates* a mailbox (that long-running flow is
            # the SSE status window's job) — a missing mailbox still blocks here.
            summary = await provision_mentor_user(
                admin_client, client, mentor_id,
                team_name=team_name or DEFAULT_MENTOR_TEAM,
                directory=directory, create_mailbox=False,
            )
            provision = {"ok": True, **summary}
        except MentorAdminError as exc:
            provision = {"ok": False, "error": str(exc)}
        except Exception as exc:  # login/EspoError etc. — never break the saved status
            provision = {"ok": False, "error": str(exc)}

    # On every save, make sure the mentor's User is assigned to BOTH the CBM
    # member record and its Contact (provisioning sets it only on the member, and
    # this self-heals records assigned on only one side). Best-effort.
    try:
        await reconcile_user_links(client, mentor_id)
    except Exception as exc:  # noqa: BLE001 — best-effort, but visibly so
        log.warning(
            "reconcile_user_links failed for CMentorProfile/%s — a one-sided "
            "User assignment stays unhealed: %s", mentor_id, exc,
        )

    result = await get_mentor(client, mentor_id)
    if warnings:
        result["warnings"] = warnings
    if provision is not None:
        result["provision"] = provision
    elif admin_client_factory is None and (
        (
            result.get("mentorStatus") in LOGIN_STATUSES
            and not assigned_user_id(result)
        )
        or result.get("mentorStatus") == STATUS_ACCEPTED_PROVISIONAL
    ):
        # Provisioning is disabled on this server (no admin service account
        # configured) and this mentor needs it — either an Approved/Active mentor
        # with no login User, or one sitting at Accepted-Provisional waiting for a
        # Google account. Surface it so the UI doesn't silently imply the work
        # happened: without this, an approval looks identical to a successful one,
        # and a provisional save leaves the mentor at a signal status nobody is
        # acting on. See the overlay's MENTOR_PROVISION_USERS / ESPO_PROVISION_*.
        result["provision"] = {
            "ok": False,
            "disabled": True,
            "error": "mentor provisioning is disabled on this server",
        }
    return result


async def reconcile_user_links(client: MentorClient, mentor_id: str) -> None:
    """Assign the mentor's User to both the CBM member record (CMentorProfile)
    and its Contact. The mentor's User is the member's ``assignedUser`` (or the
    Contact's, if only that side has one). Idempotent — a no-op when there is no
    User or both sides already match. Run on every save.
    """
    prof = await client.get(
        MENTOR_PROFILE, mentor_id,
        select="assignedUserId,assignedUsersIds,assignedUsersNames,contactRecordId",
    )
    member_user = assigned_user_id(prof)
    contact_id = prof.get("contactRecordId")
    contact_user = None
    contact_users: list[str] = []
    if contact_id:
        contact = await client.get(
            "Contact", contact_id, select="assignedUserId,assignedUsersIds"
        )
        contact_users = list(contact.get("assignedUsersIds") or [])
        contact_user = contact.get("assignedUserId") or next(iter(contact_users), None)

    user = member_user or contact_user
    if not user:
        return  # no User to assign anywhere
    if member_user != user:
        # CMentorProfile uses assignedUsers (collaborators) on prod — write both.
        await client.update(MENTOR_PROFILE, mentor_id, assigned_user_payload(MENTOR_PROFILE, user))
    if contact_id and user != contact_user and user not in contact_users:
        # Contact uses assignedUsers (collaborators) since 2026-07-16 — write both
        # shapes, MERGING into the multi list (co-mentors stamped by the session
        # tools must keep their access; the disabled single field is ignored).
        await client.update(
            "Contact", contact_id,
            {"assignedUserId": user, "assignedUsersIds": contact_users + [user]},
        )


def cbm_email_for(first: str, last: str) -> str:
    """Build firstname.lastname@cbmentors.org from a contact's name."""
    f = re.sub(r"[^a-z0-9]", "", (first or "").lower())
    last_clean = re.sub(r"[^a-z0-9]", "", (last or "").lower())
    local = ".".join(p for p in (f, last_clean) if p) or "mentor"
    return f"{local}@{cbm_email_domain()}"


def _split_name(name: Optional[str]) -> tuple[str, str]:
    parts = (name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


async def _unique_user_name(client: MentorClient, email: str) -> str:
    """The CBM email, or firstname.lastname2@… etc. if that login already exists."""
    local, _, domain = email.partition("@")
    for i in range(0, 100):
        candidate = email if i == 0 else f"{local}{i + 1}@{domain}"
        if not await client.find_one("User", "userName", candidate, select="id"):
            return candidate
    return email  # give up after 100; let the CRM enforce uniqueness


def _suffixed(email: str, i: int) -> str:
    """``jane.doe@d`` → itself for i=0, ``jane.doe2@d`` for i=1, and so on."""
    if i == 0:
        return email
    local, _, domain = email.partition("@")
    return f"{local}{i + 1}@{domain}"


async def _reserve_cbm_email(
    edit_client: MentorClient,
    admin_client: Optional[MentorClient],
    mentor_id: str,
    first: str,
    last: str,
) -> str:
    """Pick this mentor's ``firstname.lastname@cbmentors.org`` address, skipping
    one that is demonstrably **someone else's**.

    Why this matters: the duplicate-login guard in the login flow reads "the
    profile already carries a cbmEmail" as "a User with that userName IS this
    mentor's login — reuse it rather than minting ``jane.doe2@``" (the fix for the
    doug.bower2/doug.bower3 pile-up). Since a mentor's account is now created at
    **Accepted-Provisional**, every mentor reaches approval with a cbmEmail, so
    that signal had to get stronger: the address is checked to be free *before*
    it is stored, against the two records that prove ownership —

    * an EspoCRM **User** with that userName (checked with ``admin_client``, the
      only credential that can read Users), and
    * **another CMentorProfile** already carrying it as its ``cbmEmail``.

    A Workspace mailbox that merely *exists* is deliberately NOT treated as taken:
    an admin pre-creating the mailbox before approval is the long-standing normal
    case, and the caller reads EXISTS as "found — it's theirs".

    Best-effort by design: a lookup failure (no grant, CRM hiccup) falls back to
    the plain computed address rather than blocking provisioning.
    """
    base = cbm_email_for(first, last)
    for i in range(0, 100):
        candidate = _suffixed(base, i)
        try:
            if admin_client is not None and await admin_client.find_one(
                "User", "userName", candidate, select="id"
            ):
                continue
            owner = await edit_client.find_one(
                MENTOR_PROFILE, "cbmEmail", candidate, select="id"
            )
            if owner and owner.get("id") != mentor_id:
                continue
        except Exception as exc:  # noqa: BLE001 — never block on a lookup
            log.warning(
                "could not verify that %s is free for CMentorProfile/%s: %s",
                candidate, mentor_id, exc,
            )
            return candidate
        return candidate
    return base  # give up after 100 — the CRM/Workspace enforce uniqueness


async def _find_team_id(client: MentorClient, team_name: str) -> str:
    team = await client.find_one("Team", "name", team_name, select="id,name")
    if team:
        return team["id"]
    available = await client.list("Team", select="name", max_size=200)
    names = sorted(t.get("name") for t in available.get("list", []) if t.get("name"))
    raise MentorAdminError(
        f"Team '{team_name}' not found in EspoCRM. Available teams: {names}"
    )


def _step(step: str, status: str, message: str, **extra: Any) -> dict[str, Any]:
    """A status event for the live provisioning window. ``status`` is one of
    ``running`` / ``done`` / ``error``; ``step`` groups events into one UI line."""
    return {"step": step, "status": status, "message": message, **extra}


async def _mailbox_becomes_active(
    directory: MailboxDirectory, email: str, *, poll_seconds: int, timeout: int,
    sleep: Callable[[float], Awaitable[None]],
) -> bool:
    """Poll until the just-created mailbox resolves, up to ``timeout`` seconds."""
    waited = 0
    while waited < timeout:
        await sleep(poll_seconds)
        waited += poll_seconds
        if await directory.mailbox_status(email) is MailboxStatus.EXISTS:
            return True
    return False


@dataclass
class MailboxOutcome:
    """What the mailbox stage established, for the stages that follow it.

    ``confirmed`` is the load-bearing one: the Google account is *known* to
    exist, because we either created it and watched it go live or found it
    already there. An UNKNOWN check (Google unreachable — the fail-open path)
    leaves it False, which is what stops the status advance from asserting an
    account exists on a guess. ``blocked`` means a terminal error event was
    already yielded and the caller must stop.
    """

    first: str = ""
    last: str = ""
    contact_id: Optional[str] = None
    recovery_email: Optional[str] = None
    address: str = ""
    # The address as STORED on the profile ("" until it is). The login stage reads
    # this exactly as it used to read a pre-existing cbmEmail.
    existing_cbm: str = ""
    confirmed: bool = False
    created: bool = False
    temp_password: Optional[str] = None
    group_added: Optional[bool] = None   # None = not attempted (no group configured)
    group_error: Optional[str] = None
    blocked: bool = False

    def result(self) -> dict[str, Any]:
        """The parts of the outcome the browser needs (temp password included —
        it is the one credential a human must relay to the mentor)."""
        out: dict[str, Any] = {"email": self.address}
        if self.created:
            out["mailboxCreated"] = True
            out["tempPassword"] = self.temp_password
            out["recoveryEmail"] = self.recovery_email
        if self.group_added is not None:
            out["groupAdded"] = self.group_added
        if self.group_error:
            out["groupError"] = self.group_error
        return out


async def provision_mentor_mailbox_steps(
    edit_client: MentorClient,
    mentor_id: str,
    outcome: MailboxOutcome,
    *,
    admin_client: Optional[MentorClient] = None,
    directory: Optional[MailboxDirectory] = None,
    create_mailbox: bool = False,
    members_group: str = "",
    for_login: bool = False,
    poll_seconds: int = MAILBOX_POLL_SECONDS,
    poll_timeout: int = MAILBOX_POLL_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[dict[str, Any]]:
    """Stage one of provisioning: the mentor's **Google Workspace account** and
    its **All Members group** membership. Yields a status event per step and
    records what happened in ``outcome`` (the caller's, so it survives the
    generator).

    Steps: (1) resolve the ``firstname.lastname@cbmentors.org`` address —
    reserving a free one when the profile has none (:func:`_reserve_cbm_email`);
    (2) with a ``directory`` configured, check whether that mailbox exists — if
    MISSING and ``create_mailbox`` is on, create it (temp password +
    change-at-first-login + the mentor's personal email as recovery) and poll
    until it is live, else stop; an inconclusive (UNKNOWN) check proceeds, failing
    open, so a Google outage can't freeze approvals; (3) store the address on the
    profile once the account is confirmed; (4) add it to ``members_group`` when one
    is configured — **non-fatal**, because a distribution list is not the
    account's existence.

    ``for_login`` only shapes the "mailbox is missing" message: the same stage
    serves the email-only flow (Accepted-Provisional) and the login flow
    (Approved/Active), and telling a provisional save that a login's welcome email
    would bounce would be nonsense.
    """
    profile = await edit_client.get(
        MENTOR_PROFILE, mentor_id, select="name,cbmEmail,contactRecordId"
    )
    first, last, recovery_email = "", "", None
    contact_id = profile.get("contactRecordId")
    if contact_id:
        contact = await edit_client.get(
            "Contact", contact_id, select="firstName,lastName,emailAddress"
        )
        first = (contact.get("firstName") or "").strip()
        last = (contact.get("lastName") or "").strip()
        recovery_email = (contact.get("emailAddress") or "").strip() or None
    if not (first or last):
        first, last = _split_name(profile.get("name"))

    existing_cbm = (profile.get("cbmEmail") or "").strip()
    cbm = existing_cbm or await _reserve_cbm_email(
        edit_client, admin_client, mentor_id, first, last
    )
    outcome.first, outcome.last = first, last
    outcome.contact_id, outcome.recovery_email = contact_id, recovery_email
    outcome.address, outcome.existing_cbm = cbm, existing_cbm

    if directory is None:
        # No Workspace connection: the login flow carries on (it always has —
        # the check is a gate, not a requirement), and the email-only flow's
        # caller reports that there is nothing it can create.
        return

    yield _step("mailbox", "running", f"Checking for the mentor email account — {cbm}")
    status = await directory.mailbox_status(cbm)
    if status is MailboxStatus.EXISTS:
        outcome.confirmed = True
        yield _step("mailbox", "done", f"Email account found for {cbm}")
    elif status is MailboxStatus.MISSING:
        if not create_mailbox:
            outcome.blocked = True
            yield _step(
                "mailbox", "error",
                f"the Google Workspace mailbox {cbm} does not exist and creating "
                "mailboxes is switched off — create it in Google Workspace first, "
                "or turn on 'Create missing mailboxes' in Email Setup."
                if not for_login else
                f"the Google Workspace mailbox {cbm} does not exist — create it "
                "before approving this mentor (the login's welcome email would "
                "otherwise bounce and they could never sign in).",
            )
            return
        recovery_note = f" (recovery to {recovery_email})" if recovery_email else ""
        yield _step(
            "mailbox", "running",
            f"No email account found — creating a new account for {cbm}{recovery_note}",
        )
        temp_password = gen_temp_password()
        outcome.temp_password = temp_password
        try:
            await directory.create_user(
                cbm, first, last,
                recovery_email=recovery_email, temp_password=temp_password,
            )
        except GoogleDirectoryError as exc:
            outcome.blocked = True
            outcome.temp_password = None
            yield _step("mailbox", "error", f"Could not create the email account: {exc}")
            return
        outcome.created = True
        yield _step("mailbox", "running", f"Created {cbm} — waiting for it to become active…")
        active = await _mailbox_becomes_active(
            directory, cbm, poll_seconds=poll_seconds, timeout=poll_timeout, sleep=sleep
        )
        if not active:
            # The account exists but isn't usable yet, so nothing downstream may
            # run — not the login, and not the status advance. A re-run finds it
            # EXISTS and finishes the job.
            outcome.blocked = True
            yield _step(
                "mailbox", "error",
                f"The mailbox {cbm} was created but is not active yet. Save this "
                "mentor again in a few minutes to finish setting them up.",
                mailboxCreated=True, tempPassword=temp_password, recoveryEmail=recovery_email,
            )
            return
        outcome.confirmed = True
        yield _step("mailbox", "done", f"The mailbox {cbm} is active")
    else:  # UNKNOWN — fail open so a Google outage can't freeze approvals
        yield _step("mailbox", "done", "Could not verify the mailbox — continuing anyway")

    # Store the address now that the account is real. The login stage relies on
    # cbmEmail being persisted BEFORE any User is created (P2, reliability review
    # 2026-07-17): if its link write fails, the profile still carries the address,
    # so the next run reuses that login instead of minting jane.doe2@ and sending
    # a second welcome email.
    if outcome.confirmed and not existing_cbm:
        try:
            await edit_client.update(MENTOR_PROFILE, mentor_id, {"cbmEmail": cbm})
            outcome.existing_cbm = cbm
        except EspoError as exc:
            outcome.blocked = True
            yield _step(
                "mailbox", "error",
                f"The account {cbm} exists, but the address could not be saved to "
                f"the mentor's record ({exc}). Nothing else was changed — try again.",
                mailboxCreated=outcome.created, tempPassword=outcome.temp_password,
                recoveryEmail=recovery_email,
            )
            return

    # All Members group. Only once the account is confirmed (adding an address
    # Google doesn't have would just fail), and never fatally.
    if members_group and outcome.confirmed:
        yield _step("group", "running", f"Adding {cbm} to {members_group}…")
        try:
            await directory.add_group_member(members_group, cbm)
            outcome.group_added = True
            yield _step("group", "done", f"{cbm} is a member of {members_group}")
        except GoogleDirectoryError as exc:
            outcome.group_added = False
            outcome.group_error = str(exc)
            yield _step(
                "group", "error",
                f"The email account is ready, but it could not be added to "
                f"{members_group} ({exc}). Add it by hand in Google Workspace, or "
                f"run this again.",
            )
    elif members_group:
        yield _step(
            "group", "done",
            f"Skipped adding {cbm} to {members_group} — the account is not confirmed yet.",
        )


async def _advance_to_provisional_steps(
    edit_client: MentorClient, mentor_id: str
) -> AsyncIterator[dict[str, Any]]:
    """Move a mentor from ``Accepted-Provisional`` to ``Provisional`` — the record
    of "their Google account now exists".

    Written as the staff user (they just saved that same field, so no escalation
    is involved). Guarded on the live enum: the two CRMs drift, and a status
    option that isn't there must produce a note, not a 400 that reads as a failed
    provisioning.
    """
    try:
        fields = await edit_client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
        options = ((fields or {}).get("mentorStatus") or {}).get("options")
    except Exception as exc:  # noqa: BLE001 — metadata read is advisory
        log.warning("could not read mentorStatus options: %s", exc)
        options = None
    if isinstance(options, list) and STATUS_PROVISIONAL not in options:
        yield _step(
            "status", "done",
            f"Left the status alone — this CRM has no '{STATUS_PROVISIONAL}' "
            "status to move them to.",
        )
        return
    yield _step("status", "running", f"Setting the status to {STATUS_PROVISIONAL}…")
    try:
        await edit_client.update(
            MENTOR_PROFILE, mentor_id, {"mentorStatus": STATUS_PROVISIONAL}
        )
    except EspoError as exc:
        yield _step(
            "status", "error",
            f"The email account is ready, but the status could not be changed to "
            f"{STATUS_PROVISIONAL} ({exc}). Set it by hand, or save again.",
        )
        return
    yield _step("status", "done", f"Status set to {STATUS_PROVISIONAL}")


async def provision_mentor_email_steps(
    edit_client: MentorClient,
    mentor_id: str,
    *,
    admin_client: Optional[MentorClient] = None,
    directory: Optional[MailboxDirectory] = None,
    create_mailbox: bool = False,
    members_group: str = "",
    advance_status: bool = True,
    poll_seconds: int = MAILBOX_POLL_SECONDS,
    poll_timeout: int = MAILBOX_POLL_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[dict[str, Any]]:
    """The **Accepted-Provisional** event: create the mentor's Google Workspace
    account, add it to the All Members group, and advance the record to
    ``Provisional``. **No EspoCRM login** — that stays with approval.

    ``advance_status`` is False for a mentor already at ``Provisional`` (the
    recovery path — their account went missing or was never made), where there is
    no status left to write. The status advance runs only on a *confirmed*
    account: see :class:`MailboxOutcome`.
    """
    if directory is None:
        yield _step(
            "mailbox", "error",
            "The Google Workspace connection isn't configured, so an email account "
            "can't be created. An administrator can set it up in Email Setup.",
        )
        return
    outcome = MailboxOutcome()
    async for event in provision_mentor_mailbox_steps(
        edit_client, mentor_id, outcome,
        admin_client=admin_client, directory=directory,
        create_mailbox=create_mailbox, members_group=members_group, for_login=False,
        poll_seconds=poll_seconds, poll_timeout=poll_timeout, sleep=sleep,
    ):
        yield event
    if outcome.blocked:
        return

    advanced = False
    if advance_status and outcome.confirmed:
        async for event in _advance_to_provisional_steps(edit_client, mentor_id):
            if event.get("status") == "done" and event.get("step") == "status":
                advanced = f"Status set to {STATUS_PROVISIONAL}" in (event.get("message") or "")
            yield event
    elif advance_status:
        # UNKNOWN mailbox check: we don't know the account exists, so we must not
        # record that it does. They stay at Accepted-Provisional and the next run
        # advances them.
        yield _step(
            "status", "done",
            "Left the status at Accepted-Provisional — the email account could not "
            "be verified. Try again once Google is reachable.",
        )

    result = outcome.result()
    result["statusAdvanced"] = advanced
    if advanced:
        result["mentorStatus"] = STATUS_PROVISIONAL
    yield {
        "step": "done", "status": "done",
        "message": "The mentor's email account is ready", "result": result,
    }


async def provision_mentor_user_steps(
    admin_client: MentorClient,
    edit_client: MentorClient,
    mentor_id: str,
    *,
    team_name: str,
    directory: Optional[MailboxDirectory] = None,
    create_mailbox: bool = False,
    members_group: str = "",
    poll_seconds: int = MAILBOX_POLL_SECONDS,
    poll_timeout: int = MAILBOX_POLL_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[dict[str, Any]]:
    """The **Approved/Active** event: ensure the mentor's CBM mailbox (stage one,
    :func:`provision_mentor_mailbox_steps`) and then create their EspoCRM
    **login User**, yielding a human-readable status event for each step.

    Stage two: create the User (welcome email via ``sendAccessInfo``), link it as
    ``assignedUser``, stamp it on the linked Contact, and back-fill ``cbmEmail``
    if stage one didn't. **The status is never touched** — a mentor arriving here
    straight from Accepted-Provisional must not be demoted to Provisional.

    Privilege split (unchanged): ``admin_client`` (a backend admin credential)
    does the User read/create + Team lookup; ``edit_client`` (the staff user)
    reads the profile/contact and writes the link. A terminal event has
    ``status`` ``error`` (and stops) or is the final ``{"step":"done", ...,
    "result": {...}}`` carrying the created login (and, if a mailbox was created,
    the temp password + recovery email to relay to the mentor).
    """
    outcome = MailboxOutcome()
    async for event in provision_mentor_mailbox_steps(
        edit_client, mentor_id, outcome,
        admin_client=admin_client, directory=directory,
        create_mailbox=create_mailbox, members_group=members_group, for_login=True,
        poll_seconds=poll_seconds, poll_timeout=poll_timeout, sleep=sleep,
    ):
        yield event
    if outcome.blocked:
        return

    first, last, contact_id = outcome.first, outcome.last, outcome.contact_id
    cbm, existing_cbm = outcome.address, outcome.existing_cbm

    # Reuse the mentor's existing CBM login rather than creating a duplicate,
    # suffixed account on every save. Only reuse when the address is already
    # STORED on the profile (existing_cbm): that means `cbm` was assigned to this
    # mentor, so a User with that userName IS their login (it just wasn't linked —
    # the link write was silently failing on prod; see below). When it is blank
    # we're assigning a fresh address, so a userName clash is a DIFFERENT person
    # and the create path suffixes it (jane.doe2@…). This fixes the
    # doug.bower2/doug.bower3 duplicate-User pileup without merging two same-named
    # mentors onto one login.
    #
    # Since a mentor's account is now created at Accepted-Provisional, stage one
    # usually stored the address already — which is safe precisely because
    # `_reserve_cbm_email` only stores an address that no User and no OTHER mentor
    # profile holds. Without that check, "has a cbmEmail" would no longer mean
    # "this login is theirs" and two same-named mentors would share one login.
    existing_user = None
    if existing_cbm:
        try:
            existing_user = await admin_client.find_one("User", "userName", cbm, select="id")
        except Exception:
            existing_user = None  # fall through to create on a lookup failure

    reused = bool(existing_user)
    try:
        if existing_user:
            user_id = existing_user["id"]
            user_name = cbm
            yield _step("login", "running", f"Linking the existing login {cbm} to the mentor…")
        else:
            yield _step("login", "running", "Creating the EspoCRM login…")
            # Persist cbmEmail BEFORE creating the User (P2, reliability review
            # 2026-07-17): if the link write below fails, the profile still
            # carries the address — so the next save's reuse guard (existing
            # cbmEmail → find the User by userName) fires instead of minting
            # jane.doe2@… and emailing a second welcome. A failure HERE aborts
            # before any User exists.
            if not existing_cbm:
                await edit_client.update(MENTOR_PROFILE, mentor_id, {"cbmEmail": cbm})
                existing_cbm = cbm
            user_name = await _unique_user_name(admin_client, cbm)
            team_id = await _find_team_id(admin_client, team_name)
            user_payload: dict[str, Any] = {
                "userName": user_name,
                "lastName": last or "Mentor",
                "emailAddress": cbm,
                "type": USER_TYPE,
                "isActive": True,
                "teamsIds": [team_id],
                "defaultTeamId": team_id,
                "sendAccessInfo": True,  # welcome email; ignored by CRM if unsupported
            }
            if first:
                user_payload["firstName"] = first
            user = await admin_client.create("User", user_payload)
            user_id = user.get("id")

        # Link the User to the member. CMentorProfile.assignedUser is DISABLED on
        # prod (it uses the multi-user assignedUsers collaborators field), where a
        # plain {"assignedUserId": …} PUT returns 200 but stores nothing — which is
        # why provisioned mentors stayed userless. Write BOTH attributes so the
        # link persists on crm-test (single) and prod (collaborators) alike.
        link_payload: dict[str, Any] = dict(assigned_user_payload(MENTOR_PROFILE, user_id))
        if not existing_cbm:
            link_payload["cbmEmail"] = cbm
        await edit_client.update(MENTOR_PROFILE, mentor_id, link_payload)

        # ROOT-CAUSE FIX (2026-07-20, Doug's finding): stamp the mentor's own
        # CONTACT with the new login too. Provisioning previously linked the
        # User to the profile only, so every newly provisioned mentor was BORN
        # with an unstamped Contact — their /mentorprofile contact-field saves
        # 403'd (Mentor Role edits Contacts at own scope) until a later staff
        # re-save or the status sweep happened to reconcile it. Written by the
        # admin credential (always permitted); merge-only; non-fatal — the
        # login exists either way, and the reconciliation is the backstop.
        if contact_id:
            try:
                rec = await admin_client.get(
                    "Contact", contact_id, select="assignedUserId,assignedUsersIds"
                )
                ids = list(rec.get("assignedUsersIds") or [])
                if user_id not in ids and rec.get("assignedUserId") != user_id:
                    contact_link: dict[str, Any] = {"assignedUsersIds": ids + [user_id]}
                    if not rec.get("assignedUserId"):
                        contact_link["assignedUserId"] = user_id
                    await admin_client.update("Contact", contact_id, contact_link)
                yield _step(
                    "login", "running",
                    "Linked the login to the mentor's contact record",
                )
            except Exception as exc:  # noqa: BLE001 — never fails the provisioning
                yield _step(
                    "login", "running",
                    f"Note: the login could not be linked to the mentor's "
                    f"contact record ({exc}) — run Update Mentor Status to "
                    f"finish, or it self-heals overnight.",
                )
    except MentorAdminError as exc:
        yield _step("login", "error", str(exc))
        return
    except Exception as exc:  # EspoError etc. — surface, don't crash the stream
        yield _step("login", "error", f"Could not provision the EspoCRM login: {exc}")
        return

    result = {
        **outcome.result(),  # email, mailbox creation + temp password, group
        "userId": user_id, "userName": user_name,
        "team": team_name, "reused": reused,
    }
    done_msg = (
        f"Linked the existing login {user_name} to the mentor."
        if reused
        else f"Created login {user_name} in {team_name} and sent a welcome email."
    )
    yield _step("login", "done", done_msg)
    yield {"step": "done", "status": "done", "message": "Provisioning complete", "result": result}


async def provision_mentor_user(
    admin_client: MentorClient,
    edit_client: MentorClient,
    mentor_id: str,
    *,
    team_name: str,
    directory: Optional[MailboxDirectory] = None,
    create_mailbox: bool = False,
    members_group: str = "",
) -> dict[str, Any]:
    """Non-streaming wrapper over :func:`provision_mentor_user_steps`: drains the
    generator and returns the final result, raising :class:`MentorAdminError` on
    the first error event (so the inline ``update_mentor`` path reports it as a
    provisioning failure). Used by the redrive / JS-off fallback."""
    result: dict[str, Any] = {}
    async for event in provision_mentor_user_steps(
        admin_client, edit_client, mentor_id,
        team_name=team_name, directory=directory, create_mailbox=create_mailbox,
        members_group=members_group,
    ):
        if event.get("status") == "error":
            raise MentorAdminError(event.get("message") or "provisioning failed")
        if event.get("step") == "done":
            result = event.get("result") or {}
    return result


# --- "Update Mentor Status" — bulk verification sweep -----------------------

async def verify_mentor_status(
    client: MentorClient,
    mentor_id: str,
    *,
    user_client: Optional[MentorClient] = None,
    directory: Optional[MailboxDirectory] = None,
    members_group: str = "",
    metrics: Any = _METRICS_UNSET,
) -> dict[str, Any]:
    """One mentor's row for the Update-Mentor-Status sweep.

    Verifies (1) the linked login **User** actually exists in EspoCRM and is
    active — not just that the profile carries a link (a deleted User leaves a
    dangling FK), (2) the mentor's ``@cbmentors.org`` **mailbox** exists in
    Google Workspace (when the Directory integration is configured — else
    reported ``unavailable``, never a failure), and (3) that mailbox's membership
    of the **All Members group** when one is configured. Also recomputes
    completeness and self-heals the stored ``recordStatus`` (same write rules as
    a detail view: only on change, never over a manual Duplicate).

    The sweep **reports, it never creates** (Doug's ruling): creating an account
    produces a temporary password that a human has to relay, so it stays in the
    per-mentor status window. ``needsEmailAccount`` flags a mentor stranded at
    ``Accepted-Provisional`` without an account — exactly the row this sweep
    exists to surface.

    ``user_client``: privileged client for the User read — regular staff can't
    read Users, so the router passes the provisioning admin's client when that
    account is configured. Falls back to ``client``; an ACL rejection reports
    the check as unverifiable rather than failing the sweep.
    """
    # Self-heal the member<->Contact User links first (same reconcile a save
    # runs) so the sweep FIXES a roster whose Contacts lost their effective
    # assignment — e.g. the 2026-07-16 CRM switch of Contact to Multiple
    # Assigned Users, which hid every previously-stored single assignedUser.
    # Best-effort: a rejected write still leaves the status computed honestly.
    try:
        await reconcile_user_links(client, mentor_id)
    except Exception as exc:
        log.warning("status sweep: reconcile_user_links failed for %s: %s", mentor_id, exc)

    rec = await get_mentor(client, mentor_id, metrics=metrics)
    completeness = await check_completeness(client, rec)
    record_status = await sync_record_status(
        client, mentor_id, rec, completeness["status"]
    )

    user_id = assigned_user_id(rec)
    if not user_id:
        user_check: dict[str, Any] = {
            "linked": False, "exists": False, "detail": "no login User linked",
        }
    else:
        reader = user_client or client
        try:
            u = await reader.get("User", user_id, select="userName,isActive")
            active = bool(u.get("isActive"))
            user_check = {
                "linked": True, "exists": True,
                "userName": u.get("userName"), "active": active,
                "detail": None if active else "User exists but is deactivated",
            }
        except EspoError as exc:
            if "404" in str(exc):
                user_check = {
                    "linked": True, "exists": False,
                    "detail": "linked User no longer exists (deleted?)",
                }
            else:
                user_check = {
                    "linked": True, "exists": None,
                    "detail": f"could not verify the User: {exc}",
                }

    email = (rec.get("cbmEmail") or "").strip()
    if not email:
        mailbox: dict[str, Any] = {
            "status": "no-email", "detail": "no CBM email on the profile",
        }
    elif directory is None:
        mailbox = {
            "status": "unavailable",
            "detail": "mailbox check not configured (see Email Setup)",
        }
    else:
        try:
            status = await directory.mailbox_status(email)
            mailbox = {"status": status.value, "email": email}
        except Exception as exc:  # mailbox_status fails open; belt-and-braces
            mailbox = {"status": MailboxStatus.UNKNOWN.value, "email": email,
                       "detail": str(exc)}

    # All Members group membership — same non-failure contract as the mailbox
    # check: unconfigured or unverifiable reports itself, never sinks the sweep.
    if not email:
        group: dict[str, Any] = {"status": "no-email"}
    elif directory is None or not members_group:
        group = {
            "status": "unavailable",
            "detail": "group check not configured (see Email Setup)",
        }
    else:
        try:
            member = await directory.is_group_member(members_group, email)
        except Exception as exc:  # noqa: BLE001 — advisory check
            member, detail = None, str(exc)
        else:
            detail = None
        group = {
            "status": "member" if member else ("missing" if member is False else "unknown"),
            "group": members_group,
        }
        if detail:
            group["detail"] = detail

    mentor_status = rec.get("mentorStatus")
    return {
        "id": mentor_id,
        "name": rec.get("name"),
        "mentorStatus": mentor_status,
        "cbmEmail": email or None,
        "recordStatus": record_status,
        "issues": completeness["issues"],
        "user": user_check,
        "mailbox": mailbox,
        "group": group,
        # Stranded at the signal status: accepted, but their Google account was
        # never made (or can't be seen), so nobody can reach them.
        "needsEmailAccount": (
            mentor_status == STATUS_ACCEPTED_PROVISIONAL
            and mailbox.get("status") != MailboxStatus.EXISTS.value
        ),
    }


async def verify_all_mentor_statuses(
    client: MentorClient,
    *,
    user_client: Optional[MentorClient] = None,
    directory: Optional[MailboxDirectory] = None,
    members_group: str = "",
) -> list[dict[str, Any]]:
    """Run :func:`verify_mentor_status` over the whole roster (bounded
    concurrency). A per-mentor CRM failure becomes an ``error`` row so one bad
    record can't sink the sweep."""
    data = await client.list(
        MENTOR_PROFILE, select="id,name", max_size=200, order_by="name"
    )
    roster = data.get("list", [])
    # ONE engagement sweep for the whole roster (P2, reliability review
    # 2026-07-17) — the per-mentor get_mentor path re-ran the full CEngagement
    # scan for every row, making the sweep O(mentors × engagements).
    try:
        metrics = await mentor_engagement_metrics(client)
    except Exception as exc:  # no CEngagement grant — counts render blank
        log.warning("status sweep: clientCounts unavailable: %s", exc)
        metrics = None
    sem = asyncio.Semaphore(5)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            try:
                return await verify_mentor_status(
                    client, row["id"], user_client=user_client,
                    directory=directory, members_group=members_group,
                    metrics=metrics,
                )
            except EspoError as exc:
                return {"id": row["id"], "name": row.get("name"), "error": str(exc)}

    return list(await asyncio.gather(*(one(r) for r in roster)))


async def field_options(client: MentorClient) -> dict[str, list[str]]:
    """Live option lists for the editable enum/multi-enum fields (CRM = truth).
    Profile enums read CMentorProfile metadata; Contact-entity enums
    (``_CONTACT_ENUM_FIELDS``) read Contact metadata."""
    fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    options: dict[str, list[str]] = {}
    for name in _ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = opts
    if _CONTACT_ENUM_FIELDS:
        cfields = await client.metadata(f"entityDefs.{CONTACT_ENTITY}.fields")
        for name in _CONTACT_ENUM_FIELDS:
            opts = (cfields.get(name) or {}).get("options")
            if isinstance(opts, list):
                options[name] = opts
    return options


# --- Permission-team assignment ---------------------------------------------
# EspoCRM Permission Teams live on the login **User** record (they are the
# access-control unit). Assigning a mentor to teams means editing their linked
# login User's team membership. Listing all Teams and reading/writing a User's
# teams require an ADMIN client — regular staff tokens can't — so these run
# under the provisioning admin service account, exactly like User provisioning.


async def list_permission_teams(admin_client: MentorClient) -> list[dict[str, str]]:
    """Every EspoCRM Permission Team as ``{"id", "name"}`` (for the multi-select).

    Requires an admin client (staff tokens can't list ``Team``)."""
    data = await admin_client.list("Team", select="name", max_size=200, order_by="name")
    return [
        {"id": t["id"], "name": t.get("name") or t["id"]}
        for t in data.get("list", [])
        if t.get("id")
    ]


async def _mentor_login_user_id(client: MentorClient, mentor_id: str) -> Optional[str]:
    """The mentor's linked login User id (``assignedUser`` on crm-test, the
    ``assignedUsers`` collaborators list on prod — resolved via
    :func:`assigned_user_id`), or None when no login has been provisioned yet."""
    prof = await client.get(
        MENTOR_PROFILE, mentor_id,
        select="assignedUserId,assignedUsersIds,assignedUsersNames",
    )
    return assigned_user_id(prof)


async def get_mentor_teams(
    client: MentorClient, admin_client: MentorClient, mentor_id: str
) -> dict[str, Any]:
    """Team-assignment state for a mentor's Status tab: every Permission Team,
    whether the mentor has a login User yet, and which teams that User currently
    belongs to.

    The login-User link is read as the staff ``client``; the Team list and the
    User's own teams are read with ``admin_client`` (staff tokens can read
    neither). A mentor with no login returns ``provisioned=False`` and no
    assigned teams — the control still renders (Doug's ruling: always active),
    it just can't be saved until a login exists.
    """
    user_id = await _mentor_login_user_id(client, mentor_id)
    teams = await list_permission_teams(admin_client)
    assigned: list[str] = []
    if user_id:
        try:
            u = await admin_client.get("User", user_id, select="teamsIds,teamsNames")
            assigned = list(u.get("teamsIds") or [])
        except Exception as exc:  # noqa: BLE001 — best-effort; empty on a hiccup
            log.warning("could not read teams for User %s: %s", user_id, exc)
    return {
        "teams": teams,
        "assignedTeamIds": assigned,
        "provisioned": bool(user_id),
    }


async def set_mentor_teams(
    client: MentorClient,
    admin_client: MentorClient,
    mentor_id: str,
    team_ids: list[str],
) -> dict[str, Any]:
    """Set the mentor's login User's Permission-Team membership to ``team_ids``.

    Raises :class:`MentorAdminError` (Doug's message) when the mentor has no
    login User yet — there is nothing to assign teams to. Unknown ids (not in
    the live Team list) are dropped. Writes ``User.teamsIds`` with the admin
    client, keeping the User's ``defaultTeam`` consistent (re-pointed to the
    first selected team when the old default is no longer a member; cleared
    when no teams remain) so an edit can't leave a dangling default-team FK.
    """
    user_id = await _mentor_login_user_id(client, mentor_id)
    if not user_id:
        raise MentorAdminError(NO_LOGIN_TEAM_MESSAGE)
    valid = {t["id"] for t in await list_permission_teams(admin_client)}
    chosen = [tid for tid in team_ids if tid in valid]

    current = await admin_client.get("User", user_id, select="teamsIds,defaultTeamId")
    payload: dict[str, Any] = {"teamsIds": chosen}
    default_team = current.get("defaultTeamId")
    if chosen and default_team not in chosen:
        payload["defaultTeamId"] = chosen[0]
    elif not chosen:
        payload["defaultTeamId"] = None
    await admin_client.update("User", user_id, payload)
    return {"assignedTeamIds": chosen}
