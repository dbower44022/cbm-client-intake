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

from .config import CONTACT, MENTOR_PROFILE, DomainConfig
from .service import SessionClient, SessionError, fill_company_fallback

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
# Field names that are plumbing, never shown.
_SYSTEM_FIELDS = {
    "id", "deleted", "createdAt", "modifiedAt", "streamUpdatedAt",
    "createdBy", "modifiedBy", "createdById", "modifiedById",
    "assignedUser", "assignedUsers", "assignedUserId", "assignedUsersIds",
    "teams", "teamsIds", "hasPortalUser", "portalUser", "originalLead",
    "emailAddressData", "phoneNumberData", "addressMap", "billingAddressMap",
    "shippingAddressMap", "name",  # personName/formatted name shown via first/last
}
_SKIP_SUFFIX = ("IsInvalid", "IsOptedOut", "IsInactive", "AnyId", "Map")
_PREFIX_C = re.compile(r"^c(?=[A-Z])")


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
    return (s[0].upper() + s[1:]) if s else name


def _field_spec(meta_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Editable/readonly field descriptors for an entity, from its metadata."""
    spec: list[dict[str, Any]] = []
    for name, fdef in meta_fields.items():
        if name in _SYSTEM_FIELDS or name.endswith(_SKIP_SUFFIX):
            continue
        if not isinstance(fdef, dict):
            continue
        ctype = fdef.get("type")
        if ctype in _TYPE_MAP:
            item = {"name": name, "label": _label(name), "type": _TYPE_MAP[ctype], "editable": True}
            opts = fdef.get("options")
            if isinstance(opts, list):
                item["options"] = [o for o in opts if o != ""]
            spec.append(item)
        elif ctype in _READONLY_TYPES:
            spec.append({"name": name, "label": _label(name), "type": "readonly", "editable": False})
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
        fields.append({**f, "value": value})
    # A flat value map (all spec fields + display extras) for the summary composer.
    values = {f["name"]: rec.get(f["name"]) for f in spec}
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
        return _field_spec(await self.raw(entity))


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
        rec = await client.get(entity, rec_id, select=_select_for(spec, await meta.raw(entity), extra))
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
    contacts_data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_contacts_link,
        select=_select_for(contact_spec, contact_raw), max_size=200,
    )
    contacts = [
        _section(c.get("name") or "Contact", CONTACT, c, contact_spec,
                 _editable_for(levels.get(CONTACT), c, user_id))
        for c in contacts_data.get("list", [])
    ]

    result: dict[str, Any] = {
        "id": parent_id, "sections": sections, "contacts": contacts,
        "contactSpec": contact_spec,
    }
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


async def link_contact(cfg: DomainConfig, client: SessionClient, parent_id: str, contact_id: str) -> None:
    """Attach an EXISTING contact to this record via the domain's contacts link
    (``CEngagement.engagementContacts`` / ``CPartnerProfile.contacts`` /
    ``CSponsorProfile.sponsorContacts`` — the relation the Details tab lists), then
    backfill its company affiliation (see :func:`_backfill_company`)."""
    await client.relate(cfg.parent_entity, parent_id, cfg.parent_contacts_link, contact_id)
    await _backfill_company(cfg, client, parent_id, contact_id)


async def create_contact(cfg: DomainConfig, client: SessionClient, parent_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Create a NEW contact and link it to this record in one operation.

    The payload is whitelisted against the live Contact field spec (drifted enum
    values dropped — same policy as saves) and the company affiliation
    (``accountId``) is stamped from this record's Account. Create → relate,
    halt-on-failure: a relate failure surfaces as an error (the created id is in
    the message so nothing is silently lost)."""
    meta_fields = await client.metadata(f"entityDefs.{CONTACT}.fields")
    spec = {f["name"]: f for f in _field_spec(meta_fields)}
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
    return {"id": created["id"]}


def _clean_changes(spec: dict[str, dict[str, Any]], changes: dict[str, Any]) -> dict[str, Any]:
    """Whitelist a change set against an entity's editable field spec, dropping
    enum/multiEnum values outside the live options so one drifted value can't 400
    the whole write (non-required-enum policy)."""
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
        payload[name] = value
    return payload


async def save_details(
    client: SessionClient, entity: str, record_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Save whitelisted changes to one entity (see :func:`_clean_changes`)."""
    meta_fields = await client.metadata(f"entityDefs.{entity}.fields")
    spec = {f["name"]: f for f in _field_spec(meta_fields)}
    payload = _clean_changes(spec, changes)
    if payload:
        await client.update(entity, record_id, payload)
    return {"entity": entity, "id": record_id, "saved": list(payload.keys())}
