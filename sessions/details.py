"""The Details tab — a metadata-driven, editable view of the org records behind
a session parent (the company Account, the Client/Partner/Sponsor profile, and
each related contact).

Rather than hand-curate ~100 fields per entity, the field set is read live from
EspoCRM metadata (``entityDefs.{Entity}.fields``) and filtered to the editable
scalar fields, so it stays correct as the CRM schema evolves. Every read/write
runs as the logged-in user, so EspoCRM enforces their ACL.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from core.espo import EspoError
from core.phone import to_e164

from .config import CONTACT, MENTOR_PROFILE, DomainConfig
from .service import SessionClient, SessionError, _is_forbidden, fill_company_fallback

log = logging.getLogger("cbm_intake.sessions.details")

# Field types we render as editable inputs (mapped to the frontend field editor).
_TYPE_MAP = {
    "varchar": "varchar", "url": "varchar", "phone": "varchar", "email": "varchar",
    "text": "text",
    "enum": "enum", "multiEnum": "multiEnum",
    "bool": "bool", "int": "int", "float": "int",
    "date": "date", "datetime": "datetime", "datetimeOptional": "datetime",
    "wysiwyg": "wysiwyg",
}
# Types shown in the read view but NOT editable here (computed / composite).
_READONLY_TYPES = {"currency", "currencyConverted", "foreign"}
# Field names that are plumbing, never shown. (`name` IS in the spec for
# entities where it's a plain varchar — the Edit Company form edits it; Contact's
# personName-typed `name` falls out via _TYPE_MAP and is shown via first/last.)
_SYSTEM_FIELDS = {
    "id", "deleted", "createdAt", "modifiedAt", "streamUpdatedAt",
    "createdBy", "modifiedBy", "createdById", "modifiedById",
    "assignedUser", "assignedUsers", "assignedUserId", "assignedUsersIds",
    "teams", "teamsIds", "hasPortalUser", "portalUser", "originalLead",
    "emailAddressData", "phoneNumberData", "addressMap", "billingAddressMap",
    "shippingAddressMap",
}
_SKIP_SUFFIX = ("IsInvalid", "IsOptedOut", "IsInactive", "AnyId", "Map")
# Per-entity hidden fields, on top of the generic filters. CEngagement.description
# holds Client Administration's internal process notes (the /assignments grid's
# click-to-edit Notes column) — staff-only by design, so it must neither render
# nor be writable in the session tools' Details view. CPartnerProfile.description
# holds the partner intake form's enum-drift triage note (Doug's 2026-07-18
# ruling: not shown when editing a partner — `partnerNotes` is THE notes field).
_ENTITY_EXCLUDED: dict[str, frozenset[str]] = {
    "CEngagement": frozenset({"description"}),
    "CPartnerProfile": frozenset({"description"}),
}
_PREFIX_C = re.compile(r"^c(?=[A-Z])")

# Curated LINK fields exposed as pickers in the edit forms. The metadata-driven
# spec deliberately covers scalars only, so a belongsTo link renders nowhere
# unless listed here (Doug's 2026-07-22 report: no way to set an engagement's
# referring partner in the app — the values on record were set in the EspoCRM
# UI). Each entry: (link name, label, foreign entity). The editor is a select
# over the foreign records the user can read (``linkOptions`` on the payload,
# best-effort); the write goes through ``{name}Id`` ("" clears the link).
_ENTITY_LINK_FIELDS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "CEngagement": (("referringPartner", "Referring partner", "CPartnerProfile"),),
}


def _label(name: str) -> str:
    """A human label from a CRM field name (camelCase → Title Case, custom-field
    ``c``/``cBM`` prefixes handled): ``cBMValueProvided`` → "CBM Value Provided",
    ``cIndustrySector`` → "Industry Sector", ``partnershipStartDate`` →
    "Partnership Start Date"."""
    if name.startswith("cBM"):
        name = "CBM " + name[3:]
    else:
        name = _PREFIX_C.sub("", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s).strip()
    s = s.replace("Linked In", "LinkedIn")  # brand name, not two words
    return (s[0].upper() + s[1:]) if s else name


def _field_spec(meta_fields: dict[str, Any], entity: str = "") -> list[dict[str, Any]]:
    """Editable/readonly field descriptors for an entity, from its metadata."""
    excluded = _ENTITY_EXCLUDED.get(entity, frozenset())
    spec: list[dict[str, Any]] = []
    for name, fdef in meta_fields.items():
        if name in _SYSTEM_FIELDS or name in excluded or name.endswith(_SKIP_SUFFIX):
            continue
        if not isinstance(fdef, dict):
            continue
        ctype = fdef.get("type")
        if ctype in _TYPE_MAP:
            item = {"name": name, "label": _label(name), "type": _TYPE_MAP[ctype], "editable": True}
            if ctype == "phone":
                item["phone"] = True  # EspoCRM only accepts E.164 — normalized on save
            opts = fdef.get("options")
            if isinstance(opts, list):
                item["options"] = [o for o in opts if o != ""]
            spec.append(item)
        elif ctype in _READONLY_TYPES:
            spec.append({"name": name, "label": _label(name), "type": "readonly", "editable": False})
    # Curated link pickers (present only when the CRM really has the link).
    for link_name, label, foreign in _ENTITY_LINK_FIELDS.get(entity, ()):
        fdef = meta_fields.get(link_name)
        if isinstance(fdef, dict) and fdef.get("type") in ("link", "linkParent"):
            spec.append({
                "name": link_name + "Id", "label": label, "type": "linkselect",
                "editable": True, "linkEntity": foreign, "nameAttr": link_name + "Name",
            })
    return spec


# Extra display attributes (link names etc., not in the editable field spec) read
# so the frontend can compose the view-mode summaries — e.g. the engagement's
# mentor (the id feeds the CBM Contacts card). Scalar fields (addresses, website,
# salutation) are already in the spec.
_DISPLAY_EXTRA: dict[str, tuple[str, ...]] = {
    "CEngagement": ("mentorProfileName", "mentorProfileId", "assignedUsersNames", "programName"),
}


def _select_for(spec: list[dict[str, Any]], raw: dict[str, Any], extra: tuple[str, ...] = ()) -> str:
    """Field select for a record read — the shown fields plus the ownership fields
    (only those that exist on the entity, to avoid a bad-select 400) plus any
    display-only extras that exist on the entity."""
    fields = ["id", "name"]
    if "assignedUser" in raw:
        fields.append("assignedUserId")
    if "assignedUsers" in raw:
        fields.append("assignedUsersIds")
    fields += [f["name"] for f in spec]
    fields += [f["nameAttr"] for f in spec if f.get("nameAttr")]  # link display names
    # extras: keep only those whose base link/field exists on the entity.
    for attr in extra:
        base = attr
        for suffix in ("Names", "Name", "Ids", "Id"):
            if attr.endswith(suffix):
                base = attr[: -len(suffix)]
                break
        if attr in raw or base in raw:
            fields.append(attr)
    return ",".join(dict.fromkeys(fields))


def _section(
    title: str, entity: str, rec: dict[str, Any], spec: list[dict[str, Any]],
    editable: bool, extra: tuple[str, ...] = (),
) -> dict[str, Any]:
    fields = []
    for f in spec:
        value = rec.get(f["name"])
        if value in (None, "", []) and not f["editable"]:
            continue  # hide empty read-only fields; keep empty editable ones
        entry = {**f, "value": value}
        if f.get("nameAttr"):  # link picker: the display name rides along
            entry["valueName"] = rec.get(f["nameAttr"])
        fields.append(entry)
    # A flat value map (all spec fields + display extras) for the summary composer.
    values = {f["name"]: rec.get(f["name"]) for f in spec}
    for f in spec:
        if f.get("nameAttr"):
            values[f["nameAttr"]] = rec.get(f["nameAttr"])
    for attr in extra:
        values[attr] = rec.get(attr)
    return {
        "title": title, "entity": entity, "id": rec.get("id"),
        "name": rec.get("name"), "editable": editable, "fields": fields, "values": values,
    }


async def _acl_edit_levels(client: SessionClient, entities: set[str]) -> dict[str, Optional[str]]:
    """The current user's ``edit`` ACL level per entity (``"no"`` / ``"own"`` /
    ``"team"`` / ``"all"`` / ``"yes"``), from their ACL table. Fails open (empty =>
    treated as permissive) if the ACL can't be read."""
    try:
        table = (await client.app_user()).get("acl", {}).get("table", {})
    except Exception:  # noqa: BLE001 — fail open; save-time 403s are handled too
        return {}
    levels: dict[str, Optional[str]] = {}
    for e in entities:
        perm = table.get(e)
        levels[e] = perm.get("edit") if isinstance(perm, dict) else perm
    return levels


def _editable_for(level: Optional[str], rec: dict[str, Any], user_id: Optional[str]) -> bool:
    """Whether the user can edit THIS record given their ``edit`` ACL level.

    ``"no"`` never; ``"own"`` only when they're the record's assigned user (so an
    unassigned record, editable by nobody but admins, reads as read-only rather
    than offering a doomed edit); everything else (``all``/``yes``/``team``/unknown)
    is treated as editable — ``team`` is left to the save to confirm."""
    if level in ("no", False):
        return False
    if level == "own":
        if not user_id:
            return False
        if rec.get("assignedUserId") == user_id:
            return True
        return user_id in (rec.get("assignedUsersIds") or [])
    return True


class _MetaCache:
    """Caches ``entityDefs.{Entity}.fields`` for the life of one request."""

    def __init__(self, client: SessionClient) -> None:
        self._client = client
        self._cache: dict[str, dict[str, Any]] = {}

    async def raw(self, entity: str) -> dict[str, Any]:
        if entity not in self._cache:
            self._cache[entity] = await self._client.metadata(f"entityDefs.{entity}.fields")
        return self._cache[entity]

    async def spec(self, entity: str) -> list[dict[str, Any]]:
        return _field_spec(await self.raw(entity), entity)


async def build_details(
    cfg: DomainConfig, client: SessionClient, parent_id: str, user_id: Optional[str] = None
) -> dict[str, Any]:
    """The Details payload.

    ``sections`` = the org records: the parent itself (``kind="parent"`` — rendered
    as the summary strip) then the company/profile cards (``kind="org"``), each with
    its editable field spec, current values, and whether THIS user can edit THIS
    record (entity ACL + per-record ownership). ``contacts`` = the client-side
    related contacts as the same section shape (rendered as one table, each row
    expandable into its edit form). ``contactSpec`` = the Contact field spec (drives
    the create-new-contact form). Mentor domain adds ``cbmContacts`` — the assigned
    mentor + co-mentors resolved through their linked Contact records.
    """
    meta = _MetaCache(client)
    parent = await client.get(cfg.parent_entity, parent_id, select=cfg.detail_select)
    await fill_company_fallback(cfg, client, [parent])
    entities = {e for _, e, _ in cfg.details_entities} | {CONTACT}
    levels = await _acl_edit_levels(client, entities)

    sections: list[dict[str, Any]] = []
    parent_values: dict[str, Any] = {}
    for title, entity, id_attr in cfg.details_entities:
        rec_id = parent_id if id_attr == "id" else parent.get(id_attr)
        if not rec_id:
            continue
        spec = await meta.spec(entity)
        extra = _DISPLAY_EXTRA.get(entity, ())
        try:
            rec = await client.get(entity, rec_id, select=_select_for(spec, await meta.raw(entity), extra))
        except EspoError as exc:
            # A card the user's role can't read must not take down the whole
            # tab (the peek pop-ups already tolerate this) — render it as a
            # "restricted" card instead. Found live 2026-07-16: staff whose
            # role lacked a read grant got "Could not load details" for the
            # entire Details tab.
            if not _is_forbidden(exc):
                raise
            sections.append({
                "title": title, "entity": entity, "id": rec_id, "name": None,
                "editable": False, "fields": [], "values": {},
                "kind": "parent" if id_attr == "id" else "org",
                "restricted": True,
            })
            continue
        editable = _editable_for(levels.get(entity), rec, user_id)
        sec = _section(title, entity, rec, spec, editable, extra)
        sec["kind"] = "parent" if id_attr == "id" else "org"
        if sec["kind"] == "parent":
            parent_values = sec["values"]
        sections.append(sec)

    # The client-side related contacts, one section each (drives the table rows
    # AND each row's expandable edit form).
    contact_spec = await meta.spec(CONTACT)
    contact_raw = await meta.raw(CONTACT)
    contacts_restricted = False
    try:
        contacts_data = await client.list_related(
            cfg.parent_entity, parent_id, cfg.parent_contacts_link,
            select=_select_for(contact_spec, contact_raw), max_size=200,
        )
    except EspoError as exc:
        if not _is_forbidden(exc):
            raise
        contacts_data = {"list": []}
        contacts_restricted = True
    contacts = [
        _section(c.get("name") or "Contact", CONTACT, c, contact_spec,
                 _editable_for(levels.get(CONTACT), c, user_id))
        for c in contacts_data.get("list", [])
    ]

    result: dict[str, Any] = {
        "id": parent_id, "sections": sections, "contacts": contacts,
        "contactSpec": contact_spec,
    }
    # Option lists for the curated link pickers (id+name of every foreign
    # record the USER can read, alphabetical). Best-effort: a forbidden or
    # failed list just omits the options — the picker renders read-only.
    link_entities = {
        f["linkEntity"]
        for sec in sections for f in sec.get("fields", ())
        if f.get("linkEntity")
    }
    if link_entities:
        options: dict[str, list[dict[str, Any]]] = {}
        for entity in sorted(link_entities):
            try:
                data = await client.list(entity, select="name", order_by="name", max_size=200)
                options[entity] = [
                    {"id": r["id"], "name": r.get("name")} for r in data.get("list", [])
                ]
            except EspoError as exc:
                log.warning("link-picker options for %s unavailable: %s", entity, exc)
        if options:
            result["linkOptions"] = options
    if contacts_restricted:
        result["contactsRestricted"] = True
    if cfg.supports_comentor:
        result["cbmContacts"] = await _cbm_contacts(
            cfg, client, parent_id, parent_values, contact_spec, contact_raw, levels, user_id,
        )
    return result


async def _contact_section(
    client: SessionClient, contact_id: str,
    contact_spec: list[dict[str, Any]], contact_raw: dict[str, Any],
    levels: dict[str, Optional[str]], user_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """One contact as a details section; None when this user can't read it."""
    try:
        rec = await client.get(CONTACT, contact_id, select=_select_for(contact_spec, contact_raw))
    except EspoError:
        return None
    editable = _editable_for(levels.get(CONTACT), rec, user_id)
    return _section(rec.get("name") or "Contact", CONTACT, rec, contact_spec, editable)


async def _cbm_contacts(
    cfg: DomainConfig, client: SessionClient, parent_id: str, parent_values: dict[str, Any],
    contact_spec: list[dict[str, Any]], contact_raw: dict[str, Any],
    levels: dict[str, Optional[str]], user_id: Optional[str],
) -> list[dict[str, Any]]:
    """CBM-side people on the engagement, for the CBM Contacts card.

    The CRM relations (verified live 2026-07-10): the assigned mentor is
    ``CEngagement.mentorProfile`` (belongsTo CMentorProfile) and co-mentors are
    ``CEngagement.additionalMentors`` (hasMany CMentorProfile) — there is no other
    staff/person link on the engagement. Each person's phone/email lives on their
    profile's linked Contact (``CMentorProfile.contactRecord``), returned here as a
    full contact section so the row can expand into the contact edit form. Every
    read degrades gracefully (a person the user can't fully read still shows as a
    name-only row).
    """
    people: list[dict[str, Any]] = []
    seen: set[str] = set()
    mentor_id = parent_values.get("mentorProfileId")
    if mentor_id:
        seen.add(mentor_id)
        contact_id = None
        try:
            prof = await client.get(MENTOR_PROFILE, mentor_id, select="name,contactRecordId")
            contact_id = prof.get("contactRecordId")
        except EspoError:
            pass
        people.append({
            "profileId": mentor_id, "name": parent_values.get("mentorProfileName"),
            "role": "Mentor", "_contactId": contact_id,
        })
    try:
        co = await client.list_related(
            cfg.parent_entity, parent_id, "additionalMentors",
            select="name,contactRecordId", max_size=200,
        )
        rows = co.get("list", [])
    except EspoError:
        rows = []
    for m in rows:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        people.append({
            "profileId": m["id"], "name": m.get("name"),
            "role": "Co-mentor", "_contactId": m.get("contactRecordId"),
        })

    out: list[dict[str, Any]] = []
    for p in people:
        contact_id = p.pop("_contactId", None)
        contact = None
        if contact_id:
            contact = await _contact_section(client, contact_id, contact_spec, contact_raw, levels, user_id)
        if contact and contact.get("name"):
            p["name"] = p["name"] or contact["name"]
        p["contact"] = contact
        out.append(p)
    return out


def _company_id_attr(cfg: DomainConfig) -> Optional[str]:
    """The parent attribute holding the org's company Account id (from the
    domain's details entities), e.g. ``clientOrganizationId`` / ``partnerCompanyId``."""
    for _, entity, id_attr in cfg.details_entities:
        if entity == "Account" and id_attr != "id":
            return id_attr
    return None


async def search_contacts(client: SessionClient, query: str) -> list[dict[str, Any]]:
    """Contact picker search for the add-existing-contact flow (name contains),
    running as the user so EspoCRM scopes the results to their ACL."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    data = await client.list(
        CONTACT,
        select="name,emailAddress,phoneNumber,accountName",
        where=[{"type": "contains", "attribute": "name", "value": q}],
        max_size=15, order_by="name",
    )
    return [
        {"id": r["id"], "name": r.get("name"), "email": r.get("emailAddress"),
         "phone": r.get("phoneNumber"), "company": r.get("accountName")}
        for r in data.get("list", [])
    ]


async def _resolve_company_id(cfg: DomainConfig, client: SessionClient, parent_id: str) -> Optional[str]:
    """The record's company Account id: the parent's own link, or resolved
    through the client profile for legacy engagements (``fill_company_fallback``)."""
    attr = _company_id_attr(cfg)
    if not attr:
        return None
    select = attr
    if cfg.company_fallback:
        select += "," + cfg.company_fallback[2]  # + the via-record id (profile)
    parent = await client.get(cfg.parent_entity, parent_id, select=select)
    await fill_company_fallback(cfg, client, [parent])
    return parent.get(attr)


async def _backfill_company(cfg: DomainConfig, client: SessionClient, parent_id: str, contact_id: str) -> None:
    """Affiliate the contact with this record's company (``Contact.account``) when
    it has none — backfill only, never overwrite an existing affiliation.
    Best-effort: the contacts-link relate is the operation that matters."""
    try:
        company_id = await _resolve_company_id(cfg, client, parent_id)
        if not company_id:
            return
        contact = await client.get(CONTACT, contact_id, select="accountId")
        if not contact.get("accountId"):
            await client.update(CONTACT, contact_id, {"accountId": company_id})
    except EspoError as exc:
        log.warning("could not backfill company on contact %s: %s", contact_id, exc)


async def _stamp_mentor_team(
    cfg: DomainConfig, client: SessionClient, parent_id: str, contact_id: str
) -> None:
    """Merge the engagement's mentor team (assigned mentor + co-mentors) into a
    newly-attached contact's ``assignedUsers`` — stamp-drift layer 2
    (2026-07-20): a contact added AFTER assignment was otherwise born
    unstamped, so the mentors' own-scope roles couldn't touch it (the
    session-attendee 403 class). Mentor domain only; best-effort — a stamp
    failure never fails the link (the nightly reconciliation is the backstop).
    Merge-only: existing assigned users are always kept."""
    if not cfg.supports_comentor:  # mentor domain only — no manager stamping elsewhere
        return
    try:
        from .service import _engagement_mentor_user_ids

        team = await _engagement_mentor_user_ids(cfg, client, parent_id)
        if not team:
            return  # unassigned engagement — the Assign re-homing stamps later
        rec = await client.get(CONTACT, contact_id, select="assignedUsersIds")
        current = list(rec.get("assignedUsersIds") or [])
        add = [u for u in team if u not in current]
        if not add:
            return
        await client.update(CONTACT, contact_id, {"assignedUsersIds": current + add})
        log.info(
            "stamped mentor team onto Contact/%s (+%d user(s), engagement %s)",
            contact_id, len(add), parent_id,
        )
    except EspoError as exc:
        log.warning(
            "mentor-team stamp failed for Contact/%s (engagement %s) — the "
            "nightly reconciliation will correct it: %s",
            contact_id, parent_id, exc,
        )


async def link_contact(cfg: DomainConfig, client: SessionClient, parent_id: str, contact_id: str) -> None:
    """Attach an EXISTING contact to this record via the domain's contacts link
    (``CEngagement.engagementContacts`` / ``CPartnerProfile.contacts`` /
    ``CSponsorProfile.sponsorContacts`` — the relation the Details tab lists), then
    backfill its company affiliation (see :func:`_backfill_company`) and stamp
    the mentor team onto it (see :func:`_stamp_mentor_team`)."""
    await client.relate(cfg.parent_entity, parent_id, cfg.parent_contacts_link, contact_id)
    await _backfill_company(cfg, client, parent_id, contact_id)
    await _stamp_mentor_team(cfg, client, parent_id, contact_id)


async def unlink_contact(cfg: DomainConfig, client: SessionClient, parent_id: str, contact_id: str) -> None:
    """Detach a contact from this record — the reverse of :func:`link_contact`.
    Removes the relation only: the Contact record itself (and any company
    affiliation the link flow backfilled) is never touched."""
    await client.unrelate(cfg.parent_entity, parent_id, cfg.parent_contacts_link, contact_id)


async def create_contact(cfg: DomainConfig, client: SessionClient, parent_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Create a NEW contact and link it to this record in one operation.

    The payload is whitelisted against the live Contact field spec (drifted enum
    values dropped — same policy as saves) and the company affiliation
    (``accountId``) is stamped from this record's Account. Create → relate,
    halt-on-failure: a relate failure surfaces as an error (the created id is in
    the message so nothing is silently lost)."""
    meta_fields = await client.metadata(f"entityDefs.{CONTACT}.fields")
    spec = {f["name"]: f for f in _field_spec(meta_fields, CONTACT)}
    payload = _clean_changes(spec, changes)
    if not (payload.get("lastName") or payload.get("firstName")):
        raise SessionError("A first or last name is required to create a contact.")
    try:
        company_id = await _resolve_company_id(cfg, client, parent_id)
        if company_id:
            payload.setdefault("accountId", company_id)
    except EspoError as exc:
        log.warning("could not read company for new contact on %s: %s", parent_id, exc)
    created = await client.create(CONTACT, payload)
    try:
        await client.relate(cfg.parent_entity, parent_id, cfg.parent_contacts_link, created["id"])
    except EspoError as exc:
        raise EspoError(
            f"The contact was created (id {created['id']}) but could not be linked "
            f"to this record: {exc}"
        ) from exc
    await _stamp_mentor_team(cfg, client, parent_id, created["id"])
    return {"id": created["id"]}


def _clean_changes(spec: dict[str, dict[str, Any]], changes: dict[str, Any]) -> dict[str, Any]:
    """Whitelist a change set against an entity's editable field spec, dropping
    enum/multiEnum values outside the live options so one drifted value can't 400
    the whole write (non-required-enum policy). Phone-type fields are normalized
    to E.164 — the only format EspoCRM accepts."""
    payload: dict[str, Any] = {}
    for name, value in changes.items():
        f = spec.get(name)
        if not f or not f.get("editable"):
            continue  # not an editable field on this entity — drop
        opts = f.get("options")
        if opts is not None and f["type"] == "enum":
            if value not in (None, "") and value not in opts:
                continue  # drifted single enum — omit (keeps stored value)
        elif opts is not None and f["type"] == "multiEnum" and isinstance(value, list):
            value = [v for v in value if v in opts]
        if f.get("phone") and isinstance(value, str) and value.strip():
            value = to_e164(value)
        if f["type"] == "linkselect" and value == "":
            value = None  # "" from the select's blank option = clear the link
        payload[name] = value
    return payload


async def save_details(
    client: SessionClient, entity: str, record_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Save whitelisted changes to one entity (see :func:`_clean_changes`)."""
    meta_fields = await client.metadata(f"entityDefs.{entity}.fields")
    spec = {f["name"]: f for f in _field_spec(meta_fields, entity)}
    payload = _clean_changes(spec, changes)
    if payload:
        await client.update(entity, record_id, payload)
    return {"entity": entity, "id": record_id, "saved": list(payload.keys())}
