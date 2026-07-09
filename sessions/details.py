"""The Details tab — a metadata-driven, editable view of the org records behind
a session parent (the company Account, the Client/Partner/Sponsor profile, and
each related contact).

Rather than hand-curate ~100 fields per entity, the field set is read live from
EspoCRM metadata (``entityDefs.{Entity}.fields``) and filtered to the editable
scalar fields, so it stays correct as the CRM schema evolves. Every read/write
runs as the logged-in user, so EspoCRM enforces their ACL.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .config import CONTACT, DomainConfig
from .service import SessionClient

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


def _select_for(spec: list[dict[str, Any]]) -> str:
    return ",".join(["id", "name", *(f["name"] for f in spec)])


def _section(title: str, entity: str, rec: dict[str, Any], spec: list[dict[str, Any]]) -> dict[str, Any]:
    fields = []
    for f in spec:
        value = rec.get(f["name"])
        if value in (None, "", []) and not f["editable"]:
            continue  # hide empty read-only fields; keep empty editable ones
        fields.append({**f, "value": value})
    return {"title": title, "entity": entity, "id": rec.get("id"), "name": rec.get("name"), "fields": fields}


class _MetaCache:
    """Caches ``entityDefs.{Entity}.fields`` for the life of one request."""

    def __init__(self, client: SessionClient) -> None:
        self._client = client
        self._cache: dict[str, dict[str, Any]] = {}

    async def spec(self, entity: str) -> list[dict[str, Any]]:
        if entity not in self._cache:
            self._cache[entity] = await self._client.metadata(f"entityDefs.{entity}.fields")
        return _field_spec(self._cache[entity])


async def build_details(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> dict[str, Any]:
    """The Details payload: one section per org entity (company + profile) plus
    one per related contact, each with its editable field spec and current values."""
    meta = _MetaCache(client)
    parent = await client.get(cfg.parent_entity, parent_id, select=cfg.detail_select)

    sections: list[dict[str, Any]] = []
    for title, entity, id_attr in cfg.details_entities:
        rec_id = parent_id if id_attr == "id" else parent.get(id_attr)
        if not rec_id:
            continue
        spec = await meta.spec(entity)
        rec = await client.get(entity, rec_id, select=_select_for(spec))
        sections.append(_section(title, entity, rec, spec))

    # A section per related contact.
    contact_spec = await meta.spec(CONTACT)
    contacts = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_contacts_link,
        select=_select_for(contact_spec), max_size=200,
    )
    for c in contacts.get("list", []):
        sections.append(_section(c.get("name") or "Contact", CONTACT, c, contact_spec))

    return {"id": parent_id, "sections": sections}


async def save_details(
    client: SessionClient, entity: str, record_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Save whitelisted changes to one entity. The whitelist is the entity's live
    editable field set; enum/multiEnum values outside the live options are dropped
    so one drifted value can't 400 the whole save (non-required-enum policy)."""
    meta_fields = await client.metadata(f"entityDefs.{entity}.fields")
    spec = {f["name"]: f for f in _field_spec(meta_fields)}
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
    if payload:
        await client.update(entity, record_id, payload)
    return {"entity": entity, "id": record_id, "saved": list(payload.keys())}
