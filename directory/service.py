"""The Workspace Directory engine — one implementation for all three kinds.

Grids are ACL-scoped (every read runs as the signed-in user), server-side
searched + filtered + paginated. Columns and the detail-view arrangement are
read LIVE from the CRM's own layouts so they match the CRM. Editing reuses the
metadata-driven whitelist/gate from :mod:`sessions.details` (only records the
user owns; only editable scalar fields; drifted enum values dropped).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

from core.espo import EspoError
from sessions.details import (
    _acl_edit_levels,
    _editable_for,
    _field_spec,
    _label,
)

from .config import DirectoryConfig

log = logging.getLogger("cbm_intake.directory")

_PAGE = 50


class DirectoryError(Exception):
    """A user-facing, non-CRM directory error."""


class DirClient(Protocol):
    """The slice of ``EspoClient`` this module needs (eases test mocking)."""

    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def metadata(self, key: str) -> Any: ...
    async def layout(self, entity: str, name: str = ...) -> Any: ...
    async def i18n(self, scope: str) -> dict[str, Any]: ...
    async def app_user(self) -> dict[str, Any]: ...


# EspoCRM field type -> how the frontend renders the cell / value.
_CELL_TYPE = {
    "varchar": "text", "text": "longtext", "url": "url",
    "email": "email", "phone": "phone",
    "enum": "text", "multiEnum": "array", "array": "array", "checklist": "array",
    "bool": "bool", "int": "int", "float": "int",
    "currency": "currency", "currencyConverted": "currency",
    "date": "date", "datetime": "datetime", "datetimeOptional": "datetime",
    "wysiwyg": "html",
}
# The assignment/ownership fields read so the edit gate can check ownership.
_OWNER_FIELDS = ("assignedUserId", "assignedUsersIds")


class _Meta:
    """Per-request cache of an entity's field metadata, i18n labels, and its
    list/detail layouts — each fetched at most once."""

    def __init__(self, client: DirClient, entity: str) -> None:
        self._client = client
        self._entity = entity
        self._fields: Optional[dict[str, Any]] = None
        self._labels: Optional[dict[str, str]] = None
        self._layouts: dict[str, Any] = {}

    async def fields(self) -> dict[str, Any]:
        if self._fields is None:
            self._fields = await self._client.metadata(
                f"entityDefs.{self._entity}.fields"
            )
        return self._fields

    async def labels(self) -> dict[str, str]:
        if self._labels is None:
            try:
                data = await self._client.i18n(self._entity)
            except EspoError:
                data = {}
            fields = (data.get(self._entity) or {}).get("fields") or {}
            self._labels = {k: v for k, v in fields.items() if isinstance(v, str) and v}
        return self._labels

    async def layout(self, name: str) -> Any:
        if name not in self._layouts:
            self._layouts[name] = await self._client.layout(self._entity, name)
        return self._layouts[name]

    async def label(self, name: str) -> str:
        return (await self.labels()).get(name) or _label(name)

    async def cell_type(self, name: str) -> str:
        fdef = (await self.fields()).get(name) or {}
        ctype = _CELL_TYPE.get(fdef.get("type", "varchar"), "text")
        # Product rule: an email/phone is always a compose/tel link, even when
        # the CRM stores it as a plain varchar (e.g. CMentorProfile.cbmEmail).
        if ctype == "text":
            low = name.lower()
            if "email" in low:
                return "email"
            if "phone" in low:
                return "phone"
        return ctype


def _read_cell(rec: dict[str, Any], name: str) -> Any:
    """A layout field's display value from a record. Link/relate fields come back
    under ``<name>Name`` (e.g. ``account`` -> ``accountName``); fall back through
    that then ``<name>Id``."""
    if name in rec and rec[name] is not None:
        return rec[name]
    for suffix in ("Name", "Id"):
        alt = name + suffix
        if rec.get(alt) is not None:
            return rec.get(alt)
    return rec.get(name)


async def _select(meta: _Meta, cfg: DirectoryConfig, extra: tuple[str, ...] = ()) -> str:
    """A select string covering the list-layout fields (+ id/name + ownership).
    Unknown select attrs are ignored by EspoCRM (verified — a bad select returns
    200), so link-field names and the ``Name`` variants are safe to include."""
    layout = await meta.layout("list")
    names = ["id", "name"]
    for item in layout:
        n = item.get("name")
        if n:
            names.append(n)
            names.append(n + "Name")  # link fields expose <name>Name
    names.extend(_OWNER_FIELDS)
    names.extend(extra)
    return ",".join(dict.fromkeys(names))


async def columns(client: DirClient, cfg: DirectoryConfig) -> list[dict[str, Any]]:
    """The grid columns, straight from the CRM's list layout."""
    meta = _Meta(client, cfg.entity)
    layout = await meta.layout("list")
    cols: list[dict[str, Any]] = []
    for item in layout:
        name = item.get("name")
        if not name:
            continue
        cols.append({
            "key": name,
            "label": await meta.label(name),
            "type": await meta.cell_type(name),
            "link": bool(item.get("link")),
            "sortable": not item.get("notSortable"),
        })
    return cols


async def filters(client: DirClient, cfg: DirectoryConfig) -> list[dict[str, Any]]:
    """The grid's filter definitions (top-left panel): each configured filter
    field resolved to enum options / bool from live metadata. A field that isn't
    a filterable type is dropped."""
    if not cfg.filters:
        return []
    meta = _Meta(client, cfg.entity)
    fields = await meta.fields()
    out: list[dict[str, Any]] = []
    for name in cfg.filters:
        fdef = fields.get(name)
        if not isinstance(fdef, dict):
            continue
        ftype = fdef.get("type")
        if ftype in ("enum", "multiEnum", "array"):
            opts = [o for o in (fdef.get("options") or []) if o != ""]
            if opts:
                out.append({
                    "key": name, "label": await meta.label(name),
                    "type": "multi" if ftype in ("multiEnum", "array") else "enum",
                    "options": opts,
                })
        elif ftype == "bool":
            out.append({"key": name, "label": await meta.label(name), "type": "bool"})
    return out


def _where(
    cfg: DirectoryConfig, q: str, applied: dict[str, Any],
    filter_types: dict[str, str],
) -> list[dict[str, Any]]:
    where: list[dict[str, Any]] = []
    q = (q or "").strip()
    if len(q) >= 2:
        where.append({"type": "contains", "attribute": cfg.search_attr, "value": q})
    for name, value in applied.items():
        ftype = filter_types.get(name)
        if ftype == "bool":
            where.append({"type": "isTrue" if value else "isFalse", "attribute": name})
        elif value:
            values = value if isinstance(value, list) else [value]
            values = [v for v in values if v]
            if not values:
                continue
            where.append({
                "type": "arrayAnyOf" if ftype == "multi" else "in",
                "attribute": name, "value": values,
            })
    return where


async def list_records(
    client: DirClient,
    cfg: DirectoryConfig,
    *,
    q: str = "",
    applied_filters: Optional[dict[str, Any]] = None,
    page: int = 1,
    page_size: int = _PAGE,
    order_by: Optional[str] = None,
    order: Optional[str] = None,
) -> dict[str, Any]:
    """One page of the directory grid: ACL-scoped, searched, filtered, sorted.
    Returns ``{columns, rows, total, page, pageSize, hasMore}``."""
    meta = _Meta(client, cfg.entity)
    cols = await columns(client, cfg)
    filter_defs = {f["key"]: f["type"] for f in await filters(client, cfg)}
    where = _where(cfg, q, applied_filters or {}, filter_defs)

    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    ob = order_by if order_by else cfg.default_order
    data = await client.list(
        cfg.entity,
        select=await _select(meta, cfg),
        where=where or None,
        max_size=page_size,
        offset=(page - 1) * page_size,
        order_by=ob,
        order=(order or "asc"),
    )
    raw = data.get("list", [])
    rows = []
    for r in raw:
        row = {"id": r["id"]}
        for c in cols:
            row[c["key"]] = _read_cell(r, c["key"])
        rows.append(row)
    total = data.get("total", len(raw))
    return {
        "columns": cols,
        "rows": rows,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": (page - 1) * page_size + len(raw) < total,
    }


async def _detail_panels(
    meta: _Meta, rec: dict[str, Any], spec_by_name: dict[str, dict[str, Any]],
    record_editable: bool,
) -> list[dict[str, Any]]:
    """The pop-up's field arrangement, straight from the CRM detail layout. Each
    field carries its view value + type + label AND, when it's an editable scalar
    the user may change, ``editable`` + ``options`` so the same panel switches to
    an edit form. Fields the detail layout doesn't place are not shown (that IS
    the CRM's own "all fields" view)."""
    layout = await meta.layout("detail")
    panels: list[dict[str, Any]] = []
    seen: set[str] = set()
    for panel in layout:
        if not isinstance(panel, dict):
            continue
        title = (
            panel.get("customLabel") or panel.get("tabLabel")
            or panel.get("label") or ""
        )
        fields: list[dict[str, Any]] = []
        for row in panel.get("rows", []):
            for cell in row or []:
                if not isinstance(cell, dict):
                    continue  # `false` = an empty layout slot
                name = cell.get("name")
                if not name or name in seen:
                    continue
                seen.add(name)
                spec = spec_by_name.get(name)
                fields.append({
                    "key": name,
                    "label": await meta.label(name),
                    "type": await meta.cell_type(name),
                    "value": _read_cell(rec, name),
                    "editable": bool(spec and record_editable),
                    "options": (spec or {}).get("options"),
                    "phone": bool((spec or {}).get("phone")),
                })
        if fields:
            panels.append({"title": title, "fields": fields})
    return panels


def _type_panel_type(title: str, type_words: list[str]) -> Optional[str]:
    """If ``title`` is a "<Type> Profile" panel, the matching type word, else
    None. So "Client Profile" -> "Client"; "Identification"/"Social Media" -> None
    (never filtered). Requires the "Profile" suffix so a coincidental prefix like
    "Partnership Details" isn't treated as a type panel."""
    t = (title or "").strip()
    if not t.lower().endswith("profile"):
        return None
    lead = t.split()[0].lower()
    for w in type_words:
        if w and w.lower() == lead:
            return w
    return None


def _filter_type_panels(
    panels: list[dict[str, Any]], type_words: list[str], record_types: Any
) -> list[dict[str, Any]]:
    """Drop "<Type> Profile" panels whose type isn't among the record's types."""
    if isinstance(record_types, (list, tuple, set)):
        have = {str(v) for v in record_types}
    elif record_types:
        have = {str(record_types)}
    else:
        have = set()
    out = []
    for p in panels:
        mt = _type_panel_type(p.get("title", ""), type_words)
        if mt is not None and mt not in have:
            continue
        out.append(p)
    return out


async def _company_contacts(
    client: DirClient, cfg: DirectoryConfig, record_id: str
) -> list[dict[str, Any]]:
    """The record's related contacts (name/email/phone) for the pop-up's contacts
    list. Best-effort: a forbidden/failed read just yields an empty list."""
    if not cfg.contacts_link:
        return []
    try:
        data = await client.list_related(
            cfg.entity, record_id, cfg.contacts_link,
            select="name,emailAddress,phoneNumber", max_size=200,
        )
    except EspoError as exc:
        log.warning("could not read %s contacts for %s: %s", cfg.entity, record_id, exc)
        return []
    return [
        {"id": c["id"], "name": c.get("name"),
         "email": c.get("emailAddress"), "phone": c.get("phoneNumber")}
        for c in data.get("list", [])
    ]


async def detail(
    client: DirClient, cfg: DirectoryConfig, record_id: str,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """The record detail payload for BOTH the preview pane and the pop-up: name,
    the CRM-arranged panels (view value + edit metadata per field), and whether
    this user may edit / owns this record.
    """
    meta = _Meta(client, cfg.entity)
    editable_spec = _field_spec(await meta.fields(), cfg.entity)
    spec_by_name = {f["name"]: f for f in editable_spec if f.get("editable")}

    # Read the detail-layout fields + editable-spec fields + ownership (+ the
    # type field, so profile panels can be filtered to the company's type).
    layout = await meta.layout("detail")
    names: set[str] = {"id", "name", *_OWNER_FIELDS}
    if cfg.type_field:
        names.add(cfg.type_field)
    for panel in layout:
        for row in (panel.get("rows", []) if isinstance(panel, dict) else []):
            for cell in row or []:
                if isinstance(cell, dict) and cell.get("name"):
                    n = cell["name"]
                    names.add(n)
                    names.add(n + "Name")
    names.update(spec_by_name)
    rec = await client.get(cfg.entity, record_id, select=",".join(names))

    levels = await _acl_edit_levels(client, {cfg.entity})
    is_own = _editable_for("own", rec, user_id)
    record_editable = cfg.editable and _editable_for(levels.get(cfg.entity), rec, user_id)

    panels = await _detail_panels(meta, rec, spec_by_name, record_editable)
    if cfg.type_field:
        type_words = [
            o for o in ((await meta.fields()).get(cfg.type_field, {}).get("options") or [])
            if o
        ]
        panels = _filter_type_panels(panels, type_words, rec.get(cfg.type_field))
    return {
        "id": record_id,
        "entity": cfg.entity,
        "name": rec.get("name"),
        "panels": panels,
        "contacts": await _company_contacts(client, cfg, record_id),
        "editable": record_editable,   # inline edit allowed (owned + ACL + kind)
        "isOwn": is_own,               # for the mentor edit-handoff decision
        "editHandoff": cfg.edit_handoff,
    }


async def save(
    client: DirClient, cfg: DirectoryConfig, record_id: str, changes: dict[str, Any],
) -> dict[str, Any]:
    """Save whitelisted changes to a directory record (Contacts/Companies only).

    Reuses the sessions Details whitelist: only editable scalar fields on this
    entity are written, drifted enum values are dropped, phone fields normalized
    — so one stale option can't 400 the whole save. Editing is refused for a kind
    whose records are handed off elsewhere (Mentors)."""
    if not cfg.editable:
        raise DirectoryError("Records in this directory are edited in their own tool.")
    from sessions.details import save_details

    return await save_details(client, cfg.entity, record_id, changes)
