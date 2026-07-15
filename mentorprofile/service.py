"""My Mentor Profile — a mentor reads and edits their OWN record.

The editable-field set is declared here (the single source for the form layout
and the update whitelist). Everything is scoped to the signed-in user: the
profile is resolved from their login (``sessions.service.resolve_manager_profile``
— a Python-side ``assignedUser`` match, never a ``where`` on ``assignedUserId``,
which prod's field ACL forbids), so no record id is ever taken from the client.
Enum/multi-enum *options* are pulled live from EspoCRM metadata so the CRM stays
the source of truth.

The field set is deliberately **non-administrative**: status, compliance, dues,
capacity, departure etc. are absent from ``PROFILE_FIELDS``, so the whitelist
drops them even if a request smuggles them in. Staff edit those in
``/mentoradmin``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

from core.phone import to_e164
from sessions.service import resolve_manager_profile

log = logging.getLogger("cbm_intake.mentorprofile.service")

MENTOR_PROFILE = "CMentorProfile"
CONTACT_ENTITY = "Contact"

# The photo is an EspoCRM ``image`` field: the value is an Attachment id in
# ``profilePhotoId``. It is uploaded/cleared through the dedicated photo
# endpoints (never part of a field save), so it is excluded from the PUT
# whitelist below.
PHOTO_FIELD = "profilePhoto"

# The website's short summary paragraph. NOT built in the CRM yet — the app
# feature-detects it from metadata (editor field + reads/writes activate on
# their own once the CRM team builds it; spec: cmentorprofile-summary-field.md).
SUMMARY_FIELD = "mentorSummary"
FEATURE_GATED_FIELDS = {SUMMARY_FIELD}

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
# ~5 MB of raw image, as base64 (volunteer-resume cap style).
MAX_PHOTO_B64_CHARS = 7_000_000


class MentorProfileError(Exception):
    """A profile operation could not be completed — a 400-level, user-facing
    condition (e.g. no linked Contact, or an unusable photo)."""


class ProfileClient(Protocol):
    """The slice of ``EspoClient`` this module needs (eases test mocking)."""

    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def metadata(self, key: str) -> Any: ...
    async def upload_attachment(
        self, *, filename: str, content_type: str, data_base64: str,
        related_type: str, field: str,
    ) -> str: ...
    async def download_attachment(self, attachment_id: str) -> tuple[bytes, str]: ...


# Editable fields, grouped for the form (stacked sections, not tabs). ``type``
# drives the input + how the value is sent; ``row`` (optional) packs fields on
# one line; ``entity: "Contact"`` marks a field living on the mentor's linked
# Contact record (merged into the read, routed to the Contact on save).
# ``preview: True`` marks the fields the public-website preview renders from —
# the CRM feed to the website uses exactly these, so the pane is faithful.
PROFILE_FIELDS: list[dict[str, Any]] = [
    # --- Top bar: the photo with the two PROMINENT status toggles opposite it
    #     (``toggle: True`` fields render in the top-right status panel).
    {"name": PHOTO_FIELD, "label": "Profile photo", "type": "image", "group": "Public profile", "preview": True},
    {"name": "publicProfile", "label": "Show my profile on the website", "type": "bool", "group": "Public profile", "preview": True, "toggle": True},
    {"name": "acceptingNewClients", "label": "Accepting new clients", "type": "bool", "group": "Public profile", "toggle": True},
    # --- Public profile (what the website shows) ---
    {"name": "mentorTitle", "label": "Headline (shown under your name)", "type": "varchar", "group": "Public profile", "preview": True},
    # Feature-gated: the website's short summary paragraph (left column, under
    # the gold ABOUT label). Served/read/saved only once the CRM field exists
    # (the sessionTranscription precedent) — see cmentorprofile-summary-field.md.
    {"name": SUMMARY_FIELD, "label": "Short summary (shown on the website)", "type": "text", "group": "Public profile", "preview": True},
    {"name": "areaOfExpertise", "label": "Areas of expertise", "type": "multiEnum", "group": "Public profile", "preview": True},
    {"name": "industryExperience", "label": "Industries served", "type": "multiEnum", "group": "Public profile", "preview": True},
    {"name": "aboutMentor", "label": "About you (shown on the website)", "type": "wysiwyg", "group": "Public profile", "preview": True},
    {"name": "cLinkedInProfile", "label": "LinkedIn profile URL", "type": "url", "group": "Public profile", "preview": True, "entity": CONTACT_ENTITY},
    # --- Contact information (lives on the linked Contact record; renders
    #     side by side with the Personal details panel) ---
    {"name": "firstName", "label": "First name", "type": "varchar", "group": "Contact information", "row": "personname", "entity": CONTACT_ENTITY, "preview": True},
    {"name": "lastName", "label": "Last name", "type": "varchar", "group": "Contact information", "row": "personname", "entity": CONTACT_ENTITY, "preview": True},
    {"name": "emailAddress", "label": "Email", "type": "varchar", "group": "Contact information", "row": "reach", "entity": CONTACT_ENTITY},
    {"name": "phoneNumber", "label": "Phone", "type": "varchar", "group": "Contact information", "row": "reach", "entity": CONTACT_ENTITY},
    {"name": "addressStreet", "label": "Street address", "type": "text", "group": "Contact information", "entity": CONTACT_ENTITY},
    {"name": "addressCity", "label": "City", "type": "varchar", "group": "Contact information", "row": "citystate", "entity": CONTACT_ENTITY},
    {"name": "addressState", "label": "State", "type": "varchar", "group": "Contact information", "row": "citystate", "entity": CONTACT_ENTITY},
    {"name": "addressPostalCode", "label": "ZIP code", "type": "varchar", "group": "Contact information", "row": "citystate", "entity": CONTACT_ENTITY},
    # --- Personal details (the panel to the right of Contact information) ---
    {"name": "cBirthday", "label": "Birthday", "type": "date", "group": "Personal details", "entity": CONTACT_ENTITY},
    {"name": "cSpouseName", "label": "Spouse name", "type": "varchar", "group": "Personal details", "entity": CONTACT_ENTITY},
    {"name": "yearsOfExperience", "label": "Years of experience", "type": "int", "group": "Personal details"},
    # --- Mentoring preferences ---
    {"name": "maximumClientCapacity", "label": "Max client capacity", "type": "int", "group": "Mentoring preferences", "row": "pause"},
    {"name": "mentorPauseStartDate", "label": "Pause start", "type": "date", "group": "Mentoring preferences", "row": "pause"},
    {"name": "mentorPauseEndDate", "label": "Pause end", "type": "date", "group": "Mentoring preferences", "row": "pause"},
    {"name": "mentorBusinessStagePref", "label": "Preferred business stages", "type": "multiEnum", "group": "Mentoring preferences"},
    {"name": "fluentLanguages", "label": "Fluent languages", "type": "multiEnum", "group": "Mentoring preferences"},
    # --- More about you (internal, not on the website) ---
    {"name": "mentorProfessionalBio", "label": "Professional bio", "type": "wysiwyg", "group": "More about you"},
    {"name": "mentoringWhyInterested", "label": "Why you mentor", "type": "wysiwyg", "group": "More about you"},
    # --- Internal CRM description (the very bottom; plain text in the CRM,
    #     so it renders as a large text box — rich-text markup saved into a
    #     text field would show as raw HTML tags in the CRM UI) ---
    {"name": "description", "label": "Internal CRM description", "type": "text", "group": "Internal CRM description", "rows": 6},
]

# Read-only context served with the record (never in the update whitelist):
# the "Mentoring since" date shown in the page header.
READ_ONLY_FIELDS = ["mentorStartDate"]

# The update whitelist, split by target entity. The image field is read-only in
# a PUT — its writes go through set_own_photo/clear_own_photo.
PROFILE_EDIT_NAMES = {
    f["name"] for f in PROFILE_FIELDS if not f.get("entity") and f["type"] != "image"
}
CONTACT_NAMES = {f["name"] for f in PROFILE_FIELDS if f.get("entity") == CONTACT_ENTITY}
EDIT_NAMES = PROFILE_EDIT_NAMES | CONTACT_NAMES
_ENUM_FIELDS = [f["name"] for f in PROFILE_FIELDS
                if f["type"] in ("enum", "multiEnum") and not f.get("entity")]
_FIELD_LABELS = {f["name"]: f["label"] for f in PROFILE_FIELDS}

_DETAIL_SELECT = ",".join(
    ["id", "name", "contactRecordId", "contactRecordName", f"{PHOTO_FIELD}Id", f"{PHOTO_FIELD}Name"]
    + READ_ONLY_FIELDS
    + sorted(PROFILE_EDIT_NAMES - FEATURE_GATED_FIELDS)
)
_CONTACT_SELECT = ",".join(sorted(CONTACT_NAMES))


async def gated_fields_present(client: ProfileClient) -> set[str]:
    """Which feature-gated fields the live CRM actually has (from metadata).
    Absent-until-proven-present: an unreachable metadata read gates them OFF, so
    the app never selects/saves a column the CRM may not have."""
    if not FEATURE_GATED_FIELDS:
        return set()
    try:
        fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
        return {n for n in FEATURE_GATED_FIELDS if isinstance(fields.get(n), dict)}
    except Exception as exc:  # noqa: BLE001
        log.warning("could not feature-detect gated fields: %s", exc)
        return set()


async def field_spec_live(client: ProfileClient) -> list[dict[str, Any]]:
    """The editor field spec as the live CRM can honor it: feature-gated fields
    (the website-summary field) appear only once they really exist — serving an
    editor box the CRM must reject would strand the user's text."""
    present = await gated_fields_present(client)
    return [
        f for f in PROFILE_FIELDS
        if f["name"] not in FEATURE_GATED_FIELDS or f["name"] in present
    ]


async def get_own_profile(client: ProfileClient, user_id: str) -> dict[str, Any]:
    """The signed-in user's own mentor record: every editable field + the linked
    Contact's fields merged in (best-effort — a profile with no Contact still
    opens; those fields just render blank). ``{"profileFound": False}`` when the
    login has no linked ``CMentorProfile``."""
    profile_id = await resolve_manager_profile(client, user_id)
    if not profile_id:
        return {"profileFound": False}
    select = _DETAIL_SELECT
    gated = await gated_fields_present(client)
    if gated:
        select = ",".join([select] + sorted(gated))
    rec = await client.get(MENTOR_PROFILE, profile_id, select=select)
    contact_id = rec.get("contactRecordId")
    if contact_id:
        try:
            contact = await client.get(CONTACT_ENTITY, contact_id, select=_CONTACT_SELECT)
            for name in CONTACT_NAMES:
                rec[name] = contact.get(name)
        except Exception as exc:  # noqa: BLE001 — best-effort merge
            log.warning("contact info unavailable for profile %s: %s", profile_id, exc)
    return {"profileFound": True, "record": rec}


async def _sanitize_enum_changes(
    client: ProfileClient, payload: dict[str, Any]
) -> list[str]:
    """Drop enum/multi-enum values the live CRM no longer accepts, in place.

    One drifted option must never 400 the whole save (Doug's policy): a single
    enum is omitted (preserving the stored value), a multi-enum keeps its valid
    members, and a plain-language warning per drop is returned for the UI.
    **Fails open** — if the live options can't be fetched, nothing is dropped.
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


async def update_own_profile(
    client: ProfileClient, user_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Update whitelisted editable fields on the caller's OWN profile; ignore
    anything else. Profile fields write to CMentorProfile; Contact fields to the
    linked Contact (raising :class:`MentorProfileError` before any write when no
    Contact is linked). Phone is normalized to E.164 at the CRM boundary."""
    profile_id = await resolve_manager_profile(client, user_id)
    if not profile_id:
        raise MentorProfileError(
            "No mentor profile is linked to your login. Please contact CBM staff."
        )
    payload = {k: v for k, v in changes.items() if k in PROFILE_EDIT_NAMES}
    contact_payload = {k: v for k, v in changes.items() if k in CONTACT_NAMES}
    # A feature-gated field the CRM doesn't have yet is dropped, not written
    # (EspoCRM would silently ignore it — dropping keeps the response honest).
    if any(k in FEATURE_GATED_FIELDS for k in payload):
        present = await gated_fields_present(client)
        payload = {k: v for k, v in payload.items()
                   if k not in FEATURE_GATED_FIELDS or k in present}
    warnings = await _sanitize_enum_changes(client, payload)

    contact_id = None
    if contact_payload:
        prof = await client.get(MENTOR_PROFILE, profile_id, select="contactRecordId")
        contact_id = prof.get("contactRecordId")
        if not contact_id:
            raise MentorProfileError(
                "Your mentor profile has no linked Contact record, so contact "
                "information can't be saved. Please contact CBM staff."
            )
        phone = contact_payload.get("phoneNumber")
        if isinstance(phone, str) and phone.strip():
            contact_payload["phoneNumber"] = to_e164(phone)

    if payload:
        await client.update(MENTOR_PROFILE, profile_id, payload)
    if contact_payload:
        await client.update(CONTACT_ENTITY, contact_id, contact_payload)

    result = await get_own_profile(client, user_id)
    if warnings:
        result["warnings"] = warnings
    return result


async def field_options(client: ProfileClient) -> dict[str, list[str]]:
    """Live option lists for the editable enum/multi-enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    options: dict[str, list[str]] = {}
    for name in _ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = [o for o in opts if o != ""]
    return options


async def field_required(client: ProfileClient) -> list[str]:
    """Names of editable fields the CRM marks **required**, read live from
    metadata over BOTH entities so the form requires exactly what the CRM does
    (e.g. Contact.lastName) instead of hard-coding it and drifting."""
    required: list[str] = []
    profile_md = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    for name in sorted(PROFILE_EDIT_NAMES):
        if isinstance(profile_md.get(name), dict) and profile_md[name].get("required"):
            required.append(name)
    contact_md = await client.metadata(f"entityDefs.{CONTACT_ENTITY}.fields")
    for name in sorted(CONTACT_NAMES):
        if isinstance(contact_md.get(name), dict) and contact_md[name].get("required"):
            required.append(name)
    return required


async def set_own_photo(
    client: ProfileClient,
    user_id: str,
    *,
    filename: str,
    content_type: str,
    data_base64: str,
) -> dict[str, Any]:
    """Upload a new profile photo (an Attachment bound to
    ``CMentorProfile.profilePhoto``) and point the caller's own profile at it."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise MentorProfileError(
            "Please choose a JPEG, PNG, WebP, or GIF image for your photo."
        )
    if len(data_base64) > MAX_PHOTO_B64_CHARS:
        raise MentorProfileError("That image is too large — please use one under 5 MB.")
    profile_id = await resolve_manager_profile(client, user_id)
    if not profile_id:
        raise MentorProfileError(
            "No mentor profile is linked to your login. Please contact CBM staff."
        )
    attachment_id = await client.upload_attachment(
        filename=filename or "profile-photo",
        content_type=content_type,
        data_base64=data_base64,
        related_type=MENTOR_PROFILE,
        field=PHOTO_FIELD,
    )
    await client.update(MENTOR_PROFILE, profile_id, {f"{PHOTO_FIELD}Id": attachment_id})
    return {f"{PHOTO_FIELD}Id": attachment_id}


async def clear_own_photo(client: ProfileClient, user_id: str) -> None:
    """Remove the caller's profile photo (clears the link; the Attachment stays
    in the CRM, like any detached upload)."""
    profile_id = await resolve_manager_profile(client, user_id)
    if not profile_id:
        raise MentorProfileError(
            "No mentor profile is linked to your login. Please contact CBM staff."
        )
    await client.update(MENTOR_PROFILE, profile_id, {f"{PHOTO_FIELD}Id": None})


async def get_own_photo(client: ProfileClient, user_id: str) -> Optional[tuple[bytes, str]]:
    """The caller's photo bytes + content type, or None when no profile/photo."""
    profile_id = await resolve_manager_profile(client, user_id)
    if not profile_id:
        return None
    rec = await client.get(MENTOR_PROFILE, profile_id, select=f"{PHOTO_FIELD}Id")
    attachment_id = rec.get(f"{PHOTO_FIELD}Id")
    if not attachment_id:
        return None
    return await client.download_attachment(attachment_id)
