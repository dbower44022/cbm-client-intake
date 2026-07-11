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
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Protocol

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

# When a mentor is set to this status, a login User is provisioned for them.
STATUS_APPROVED = "Approved"
STATUS_ACTIVE = "Active"

# Sign-off flags every complete mentor must have set (field -> label).
# (Background check is optional — deliberately not required for completeness.)
COMPLETENESS_FLAGS = [
    ("ethicsAgreementAccepted", "ethics agreement"),
    ("trainingCompleted", "training completed"),
    ("termsAccepted", "terms accepted"),
]
# CBM-issued email/login domain: userName = firstname.lastname@cbmentors.org.
CBM_EMAIL_DOMAIN = "cbmentors.org"
DEFAULT_MENTOR_TEAM = "Mentor Team"
USER_TYPE = "regular"


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
    {"name": "mentorStartDate", "label": "Mentor start date", "type": "date", "group": "Status"},
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
_CONTACT_SELECT = ",".join(sorted(CONTACT_NAMES))


async def get_mentor(client: MentorClient, mentor_id: str) -> dict[str, Any]:
    """The full mentor record: every editable field + read-only context, plus
    ``clientCounts`` — the same app-computed counts the roster grid shows
    (Active/Max/Available/Assigned-30d/Lifetime), so the detail card and the
    grid always agree. Counts are best-effort (None when engagements can't be
    read); ``update_mentor`` returns through here, so a save refreshes them."""
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
        contact_user = None
        if contact_id:
            try:
                contact = await client.get("Contact", contact_id, select="assignedUserId")
                contact_user = contact.get("assignedUserId")
            except Exception:
                issues.append("could not read the Contact record")
        if contact_id and not contact_user:
            issues.append("no User assigned to the Contact")
        elif user_id and contact_user and contact_user != user_id:
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
        except Exception:
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
    keys = [k for k in payload if k in _ENUM_FIELDS]
    if not keys:
        return []
    try:
        options = await field_options(client)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the save
        log.warning("could not fetch enum options (%s); keeping values as-is", exc)
        return []
    warnings: list[str] = []

    def note(name: str, values: list[Any]) -> None:
        log.warning(
            "%s.%s: dropping unrecognized %s (not in the live enum)",
            MENTOR_PROFILE, name, values,
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
    """
    payload = {k: v for k, v in changes.items() if k in PROFILE_EDIT_NAMES}
    contact_payload = {k: v for k, v in changes.items() if k in CONTACT_NAMES}
    warnings = await _sanitize_enum_changes(client, payload)

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
        and effective_status in (STATUS_APPROVED, STATUS_ACTIVE)
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
    except Exception:
        pass

    result = await get_mentor(client, mentor_id)
    if warnings:
        result["warnings"] = warnings
    if provision is not None:
        result["provision"] = provision
    elif (
        admin_client_factory is None
        and result.get("mentorStatus") in (STATUS_APPROVED, STATUS_ACTIVE)
        and not assigned_user_id(result)
    ):
        # The mentor is Approved/Active but has no login User, and provisioning is
        # disabled on this server (no admin service account configured). Surface
        # it so the UI doesn't silently imply a login was created — without this,
        # an approval looks identical to a successful one. See the overlay's
        # MENTOR_PROVISION_USERS / ESPO_PROVISION_* to enable it.
        result["provision"] = {
            "ok": False,
            "disabled": True,
            "error": "mentor login provisioning is disabled on this server",
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
    if contact_id:
        contact = await client.get("Contact", contact_id, select="assignedUserId")
        contact_user = contact.get("assignedUserId")

    user = member_user or contact_user
    if not user:
        return  # no User to assign anywhere
    if member_user != user:
        # CMentorProfile uses assignedUsers (collaborators) on prod — write both.
        await client.update(MENTOR_PROFILE, mentor_id, assigned_user_payload(MENTOR_PROFILE, user))
    if contact_id and contact_user != user:
        # Contact uses the single assignedUser on both instances.
        await client.update("Contact", contact_id, {"assignedUserId": user})


def cbm_email_for(first: str, last: str) -> str:
    """Build firstname.lastname@cbmentors.org from a contact's name."""
    f = re.sub(r"[^a-z0-9]", "", (first or "").lower())
    last_clean = re.sub(r"[^a-z0-9]", "", (last or "").lower())
    local = ".".join(p for p in (f, last_clean) if p) or "mentor"
    return f"{local}@{CBM_EMAIL_DOMAIN}"


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


async def provision_mentor_user_steps(
    admin_client: MentorClient,
    edit_client: MentorClient,
    mentor_id: str,
    *,
    team_name: str,
    directory: Optional[MailboxDirectory] = None,
    create_mailbox: bool = False,
    poll_seconds: int = MAILBOX_POLL_SECONDS,
    poll_timeout: int = MAILBOX_POLL_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[dict[str, Any]]:
    """Provision an approved mentor's CBM mailbox + EspoCRM login, yielding a
    human-readable status event for each step (for the live status window).

    Steps, in order: (1) resolve the ``firstname.lastname@cbmentors.org`` address;
    (2) if a ``directory`` is given, check whether that Workspace mailbox exists —
    if MISSING and ``create_mailbox`` is on, create it (temp password +
    change-at-first-login + the mentor's personal email as recovery) and poll
    until it's live, else block; an inconclusive (UNKNOWN) check proceeds (fail
    open); (3) create the EspoCRM **User** (welcome email via ``sendAccessInfo``),
    link it as ``assignedUser``, and back-fill ``cbmEmail`` when blank.

    Privilege split (unchanged): ``admin_client`` (a backend admin credential)
    does the User read/create + Team lookup; ``edit_client`` (the staff user)
    reads the profile/contact and writes the link. A terminal event has
    ``status`` ``error`` (and stops) or is the final ``{"step":"done", ...,
    "result": {...}}`` carrying the created login (and, if a mailbox was created,
    the temp password + recovery email to relay to the mentor).
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
    cbm = existing_cbm or cbm_email_for(first, last)

    created_mailbox = False
    temp_password: Optional[str] = None

    if directory is not None:
        yield _step("mailbox", "running", f"Checking for the mentor email account — {cbm}")
        status = await directory.mailbox_status(cbm)
        if status is MailboxStatus.EXISTS:
            yield _step("mailbox", "done", f"Email account found for {cbm}")
        elif status is MailboxStatus.MISSING:
            if not create_mailbox:
                yield _step(
                    "mailbox", "error",
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
            try:
                await directory.create_user(
                    cbm, first, last,
                    recovery_email=recovery_email, temp_password=temp_password,
                )
            except GoogleDirectoryError as exc:
                yield _step("mailbox", "error", f"Could not create the email account: {exc}")
                return
            created_mailbox = True
            yield _step("mailbox", "running", f"Created {cbm} — waiting for it to become active…")
            active = await _mailbox_becomes_active(
                directory, cbm, poll_seconds=poll_seconds, timeout=poll_timeout, sleep=sleep
            )
            if not active:
                yield _step(
                    "mailbox", "error",
                    f"The mailbox {cbm} was created but is not active yet. Save this "
                    "mentor again in a few minutes to finish creating their login.",
                    mailboxCreated=True, tempPassword=temp_password, recoveryEmail=recovery_email,
                )
                return
            yield _step("mailbox", "done", f"The mailbox {cbm} is active")
        else:  # UNKNOWN — fail open so a Google outage can't freeze approvals
            yield _step("mailbox", "done", "Could not verify the mailbox — continuing anyway")

    # Reuse the mentor's existing CBM login rather than creating a duplicate,
    # suffixed account on every save. Only reuse when the profile ALREADY had a
    # cbmEmail (existing_cbm): that means this mentor was assigned `cbm` before, so
    # a User with that userName IS their login (it just wasn't linked — the link
    # write was silently failing on prod; see below). When cbmEmail is blank we're
    # assigning a fresh address, so a userName clash is a DIFFERENT person and the
    # create path suffixes it (jane.doe2@…). This fixes the doug.bower2/doug.bower3
    # duplicate-User pileup without merging two same-named mentors onto one login.
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
    except MentorAdminError as exc:
        yield _step("login", "error", str(exc))
        return
    except Exception as exc:  # EspoError etc. — surface, don't crash the stream
        yield _step("login", "error", f"Could not provision the EspoCRM login: {exc}")
        return

    result = {
        "userId": user_id, "userName": user_name, "email": cbm,
        "team": team_name, "reused": reused,
    }
    if created_mailbox:
        result["mailboxCreated"] = True
        result["tempPassword"] = temp_password
        result["recoveryEmail"] = recovery_email
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
) -> dict[str, Any]:
    """Non-streaming wrapper over :func:`provision_mentor_user_steps`: drains the
    generator and returns the final result, raising :class:`MentorAdminError` on
    the first error event (so the inline ``update_mentor`` path reports it as a
    provisioning failure). Used by the redrive / JS-off fallback."""
    result: dict[str, Any] = {}
    async for event in provision_mentor_user_steps(
        admin_client, edit_client, mentor_id,
        team_name=team_name, directory=directory, create_mailbox=create_mailbox,
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
) -> dict[str, Any]:
    """One mentor's row for the Update-Mentor-Status sweep.

    Verifies (1) the linked login **User** actually exists in EspoCRM and is
    active — not just that the profile carries a link (a deleted User leaves a
    dangling FK), and (2) the mentor's ``@cbmentors.org`` **mailbox** exists in
    Google Workspace (when the Directory integration is configured — else
    reported ``unavailable``, never a failure). Also recomputes completeness
    and self-heals the stored ``recordStatus`` (same write rules as a detail
    view: only on change, never over a manual Duplicate).

    ``user_client``: privileged client for the User read — regular staff can't
    read Users, so the router passes the provisioning admin's client when that
    account is configured. Falls back to ``client``; an ACL rejection reports
    the check as unverifiable rather than failing the sweep.
    """
    rec = await get_mentor(client, mentor_id)
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

    return {
        "id": mentor_id,
        "name": rec.get("name"),
        "mentorStatus": rec.get("mentorStatus"),
        "cbmEmail": email or None,
        "recordStatus": record_status,
        "issues": completeness["issues"],
        "user": user_check,
        "mailbox": mailbox,
    }


async def verify_all_mentor_statuses(
    client: MentorClient,
    *,
    user_client: Optional[MentorClient] = None,
    directory: Optional[MailboxDirectory] = None,
) -> list[dict[str, Any]]:
    """Run :func:`verify_mentor_status` over the whole roster (bounded
    concurrency). A per-mentor CRM failure becomes an ``error`` row so one bad
    record can't sink the sweep."""
    data = await client.list(
        MENTOR_PROFILE, select="id,name", max_size=200, order_by="name"
    )
    roster = data.get("list", [])
    sem = asyncio.Semaphore(5)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            try:
                return await verify_mentor_status(
                    client, row["id"], user_client=user_client, directory=directory
                )
            except EspoError as exc:
                return {"id": row["id"], "name": row.get("name"), "error": str(exc)}

    return list(await asyncio.gather(*(one(r) for r in roster)))


async def field_options(client: MentorClient) -> dict[str, list[str]]:
    """Live option lists for the editable enum/multi-enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    options: dict[str, list[str]] = {}
    for name in _ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = opts
    return options
