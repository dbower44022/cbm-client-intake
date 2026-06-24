"""Mentor Admin — read the full mentor record and update editable fields.

The editable-field set is declared here (the single source for the form layout
and the update whitelist); enum/multi-enum *options* are pulled live from
EspoCRM metadata so the CRM stays the source of truth. Computed totals
(availableCapacity, currentActiveClients, totals) are read-only.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Optional, Protocol

from core.google_directory import MailboxStatus

MENTOR_PROFILE = "CMentorProfile"

# A callable that returns whether a CBM mailbox exists in Google Workspace.
MailboxChecker = Callable[[str], Awaitable[MailboxStatus]]

# When a mentor is set to this status, a login User is provisioned for them.
STATUS_APPROVED = "Approved"
STATUS_ACTIVE = "Active"

# Sign-off flags every complete mentor must have set (field -> label).
COMPLETENESS_FLAGS = [
    ("backgroundCheckCompleted", "background check"),
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


# "How did you hear about CBM" is a free-text CRM field, but the mentor intake
# (volunteer) form offers a fixed list — mirror it here so admins pick the same
# values. Kept in sync with forms/volunteer/frontend/options.js (howDidYouHear).
HOW_HEARD_OPTIONS = [
    "Friend or relative", "Newspaper", "Online search", "Radio", "SBA",
    "CBM client or volunteer", "Social media", "TV", "Workshop/Event", "Other",
]

# Editable fields, grouped for the form (one tab per group). ``type`` drives the
# input + how the value is sent; ``row`` (optional) sub-groups fields within a
# tab; ``options`` (optional) supplies a static dropdown list for a field whose
# CRM type is free-text. Order is the display order.
EDITABLE_FIELDS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "type": "varchar", "group": "Profile"},
    {"name": "mentorStatus", "label": "Status", "type": "enum", "group": "Status"},
    {"name": "mentorType", "label": "Type", "type": "enum", "group": "Status"},
    {"name": "acceptingNewClients", "label": "Accepting new clients", "type": "bool", "group": "Status"},
    {"name": "publicProfile", "label": "Public profile", "type": "bool", "group": "Status"},
    {"name": "mentorStartDate", "label": "Mentor start date", "type": "date", "group": "Status"},
    {"name": "mentorStatusNotes", "label": "Status notes", "type": "text", "group": "Status"},
    {"name": "maximumClientCapacity", "label": "Maximum client capacity", "type": "int", "group": "Capacity"},
    {"name": "yearsOfExperience", "label": "Years of experience", "type": "int", "group": "Capacity"},
    {"name": "industrySector", "label": "Industry sector", "type": "enum", "group": "Expertise"},
    {"name": "mentoringFocusAreas", "label": "Mentoring focus areas", "type": "multiEnum", "group": "Expertise"},
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
    {"name": "howDidYouHearAboutCBM", "label": "How they heard about CBM", "type": "enum", "group": "Profile", "options": HOW_HEARD_OPTIONS},
    {"name": "description", "label": "Description / notes", "type": "text", "group": "Profile"},
    {"name": "aboutMentor", "label": "About the mentor", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentorProfessionalBio", "label": "Professional bio", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringSkills", "label": "Mentoring skills", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringWhyInterested", "label": "Why interested in mentoring", "type": "wysiwyg", "group": "Bio"},
]

EDITABLE_NAMES = {f["name"] for f in EDITABLE_FIELDS}
_ENUM_FIELDS = [f["name"] for f in EDITABLE_FIELDS if f["type"] in ("enum", "multiEnum")]

# Read-only context shown above the form. Includes the contact-info "foreign"
# fields CMentorProfile mirrors from the linked Contact (personalEmail/
# contactPhone/contactStreet/contactCity/postalCode) — not editable here (they
# live on the Contact), shown read-only in the summary card.
READ_ONLY_FIELDS = [
    "availableCapacity", "currentActiveClients", "maximumClientCapacity",
    "totalLifetimeSessions", "totalSessionsLast30Days", "totalMentoringHours",
    "contactRecordName", "contactRecordId", "assignedUserName", "assignedUserId",
    "createdAt", "modifiedAt", "recordStatus",
    "personalEmail", "contactPhone", "contactStreet", "contactCity", "postalCode",
]

# recordStatus enum value set manually (in the CRM) — never auto-overwritten.
RECORD_STATUS_MANUAL = "Duplicate"

_DETAIL_SELECT = ",".join(["id"] + sorted(EDITABLE_NAMES) + READ_ONLY_FIELDS)


async def get_mentor(client: MentorClient, mentor_id: str) -> dict[str, Any]:
    """The full mentor record: every editable field + read-only context."""
    return await client.get(MENTOR_PROFILE, mentor_id, select=_DETAIL_SELECT)


def _has_text(html: Any) -> bool:
    """True if a wysiwyg/text value has real text (ignoring HTML tags + nbsp)."""
    if not html:
        return False
    return bool(re.sub(r"<[^>]+>", "", str(html)).replace("\xa0", " ").strip())


async def check_completeness(client: MentorClient, rec: dict[str, Any]) -> dict[str, Any]:
    """Verify the mentor's data structure is complete & correct.

    A ``CMentorProfile`` *is* the "CBM member" record (present by definition when
    viewing it). Always required: a linked **Contact** record + the four sign-off
    flags (``COMPLETENESS_FLAGS``). For an **Active** mentor, additionally: a CBM
    email address, plus a login **User** assigned to the member and that same User
    on the Contact. For a **public profile** (``publicProfile`` true): About-the-
    mentor text, ≥1 mentoring focus area, ≥1 area of expertise, and an industry
    sector. Returns ``{"status": "Complete"|"Incomplete", "issues": [...]}``.
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
        user_id = rec.get("assignedUserId")
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

    if rec.get("publicProfile"):
        if not _has_text(rec.get("aboutMentor")):
            issues.append("public profile: About the mentor is empty")
        if not rec.get("mentoringFocusAreas"):
            issues.append("public profile: no mentoring focus area selected")
        if not rec.get("areaOfExpertise"):
            issues.append("public profile: no area of expertise selected")
        if not rec.get("industrySector"):
            issues.append("public profile: no industry sector selected")

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


async def update_mentor(
    client: MentorClient,
    mentor_id: str,
    changes: dict[str, Any],
    *,
    team_name: Optional[str] = None,
    admin_client_factory: Optional[Callable[[], Awaitable[MentorClient]]] = None,
    mailbox_checker: Optional[MailboxChecker] = None,
) -> dict[str, Any]:
    """Update whitelisted editable fields; ignore anything else.

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
    payload = {k: v for k, v in changes.items() if k in EDITABLE_NAMES}

    # When provisioning is possible, read the pre-save status + user link so we
    # can decide on the *effective* status (the change, or the stored value if
    # this save didn't touch status).
    before = None
    if admin_client_factory is not None:
        before = await client.get(
            MENTOR_PROFILE, mentor_id, select="mentorStatus,assignedUserId"
        )

    if payload:
        await client.update(MENTOR_PROFILE, mentor_id, payload)

    provision: Optional[dict[str, Any]] = None
    effective_status = (
        payload.get("mentorStatus", before.get("mentorStatus")) if before else None
    )
    if (
        admin_client_factory is not None
        and before is not None
        and effective_status in (STATUS_APPROVED, STATUS_ACTIVE)
        and not before.get("assignedUserId")
    ):
        try:
            admin_client = await admin_client_factory()
            summary = await provision_mentor_user(
                admin_client, client, mentor_id,
                team_name=team_name or DEFAULT_MENTOR_TEAM,
                mailbox_checker=mailbox_checker,
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
    if provision is not None:
        result["provision"] = provision
    elif (
        admin_client_factory is None
        and result.get("mentorStatus") in (STATUS_APPROVED, STATUS_ACTIVE)
        and not result.get("assignedUserId")
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
        MENTOR_PROFILE, mentor_id, select="assignedUserId,contactRecordId"
    )
    member_user = prof.get("assignedUserId")
    contact_id = prof.get("contactRecordId")
    contact_user = None
    if contact_id:
        contact = await client.get("Contact", contact_id, select="assignedUserId")
        contact_user = contact.get("assignedUserId")

    user = member_user or contact_user
    if not user:
        return  # no User to assign anywhere
    if member_user != user:
        await client.update(MENTOR_PROFILE, mentor_id, {"assignedUserId": user})
    if contact_id and contact_user != user:
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


async def provision_mentor_user(
    admin_client: MentorClient,
    edit_client: MentorClient,
    mentor_id: str,
    *,
    team_name: str,
    mailbox_checker: Optional[MailboxChecker] = None,
) -> dict[str, Any]:
    """Create a login User for an approved mentor, link it, and team it.

    Privilege split: ``admin_client`` (a backend service credential) does the
    User read/create + Team lookup — the operations staff users aren't allowed to
    do. ``edit_client`` (the logged-in staff user) reads the profile/contact and
    writes the ``assignedUser`` link, which staff already can. So the elevated
    permission lives only in the backend credential.

    userName/email = ``firstname.lastname@cbmentors.org`` (the CBM email; reuses
    the profile's ``cbmEmail`` if already set). The User is active, in
    ``team_name``, and EspoCRM is asked to email access info (``sendAccessInfo``)
    so the mentor sets their own password. The new User becomes the profile's
    ``assignedUser`` (the same link the assignment tool reads), and the CBM email
    is written back to the profile when it was blank.
    """
    profile = await edit_client.get(
        MENTOR_PROFILE, mentor_id, select="name,cbmEmail,contactRecordId"
    )
    first, last = "", ""
    contact_id = profile.get("contactRecordId")
    if contact_id:
        contact = await edit_client.get(
            "Contact", contact_id, select="firstName,lastName"
        )
        first = (contact.get("firstName") or "").strip()
        last = (contact.get("lastName") or "").strip()
    if not (first or last):
        first, last = _split_name(profile.get("name"))

    existing_cbm = (profile.get("cbmEmail") or "").strip()
    cbm = existing_cbm or cbm_email_for(first, last)

    # Hard gate: don't create a login (and bounce its welcome email) for a CBM
    # address that has no Google Workspace mailbox. Only a *confirmed*-missing
    # mailbox blocks; an inconclusive check (UNKNOWN) falls through so a Google
    # outage can't freeze approvals.
    if mailbox_checker is not None:
        status = await mailbox_checker(cbm)
        if status is MailboxStatus.MISSING:
            raise MentorAdminError(
                f"the Google Workspace mailbox {cbm} does not exist — create it "
                "before approving this mentor (the login's welcome email would "
                "otherwise bounce and they could never sign in)."
            )

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

    link_payload: dict[str, Any] = {"assignedUserId": user_id}
    if not existing_cbm:
        link_payload["cbmEmail"] = cbm
    await edit_client.update(MENTOR_PROFILE, mentor_id, link_payload)

    return {"userId": user_id, "userName": user_name, "email": cbm, "team": team_name}


async def field_options(client: MentorClient) -> dict[str, list[str]]:
    """Live option lists for the editable enum/multi-enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    options: dict[str, list[str]] = {}
    for name in _ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = opts
    return options
