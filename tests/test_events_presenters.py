"""Track F, F4 — presenters on an event.

Design: prds/events/CBM_Events_Presenters_Design.md. The boundaries: feature
detection fails closed; the add copies a mentor once and never refreshes; a
guest email creates a Presenter-typed Contact and a known one is reused
unchanged; the spec is the whitelist; the biography is omitted when the
switch is off; a photo is reachable only through its own event.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from events import config as cfg
from events import service
from forms import ALL_SPECS

from tests.test_events_service import make_event

ROOT = Path(__file__).resolve().parents[1]
MARKETING = {"userName": "marcus", "name": "Marcus Admin", "userId": "u-1",
             "token": "t", "isAdmin": False, "teams": ["Marketing Admin Team"]}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class PresenterCrm:
    """A CRM with CEventPresenter, Contacts and mentor profiles, recording writes."""

    def __init__(self, *, events=None, contacts=None, mentors=None, presenters=None,
                 has_entity=True, meta_fails=False):
        self.events = list(events or [])
        self.contacts = list(contacts or [])
        self.mentors = list(mentors or [])
        self.presenters = list(presenters or [])
        self.has_entity = has_entity
        self.meta_fails = meta_fails
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, str, dict]] = []
        self.deleted: list[tuple[str, str]] = []
        self.uploads: list[dict] = []
        self.attachments = {"att-mentor": (b"PHOTO", "image/jpeg")}
        self._seq = 0

    def _pool(self, entity):
        return {cfg.EVENT: self.events, "Contact": self.contacts,
                "CMentorProfile": self.mentors, cfg.PRESENTER_ENTITY: self.presenters}.get(entity, [])

    async def metadata(self, key):
        if self.meta_fails:
            raise EspoError("metadata failed")
        if key == f"entityDefs.{cfg.PRESENTER_ENTITY}":
            return {"fields": {"biography": {}, "photo": {}}} if self.has_entity else None
        if key == f"entityDefs.{cfg.EVENT}.links":
            return ({cfg.PRESENTERS_LINK: {"entity": cfg.PRESENTER_ENTITY, "type": "hasMany"}}
                    if self.has_entity else {})
        if key == f"entityDefs.{cfg.EVENT}.fields":
            fields = {f: {} for f in cfg.AUDIENCE_FIELDS}
            if self.has_entity:
                fields[cfg.SHOW_BIOS_FIELD] = {}
            return fields
        return {}

    async def metadata_enum_options(self, entity, field):
        return None

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        rows = list(self._pool(entity))
        for clause in where or []:
            if clause.get("type") == "equals":
                rows = [r for r in rows if r.get(clause["attribute"]) == clause["value"]]
            elif clause.get("type") == "or":
                subs = clause["value"]
                rows = [r for r in rows if any(
                    (c["value"].lower() in str(r.get(c["attribute"]) or "").lower())
                    for c in subs)]
        return {"total": len(rows), "list": rows[offset: offset + max_size]}

    async def find_one(self, entity, attr, value, select=None):
        for row in self._pool(entity):
            if row.get(attr) == value:
                return row
        return None

    async def get(self, entity, record_id, select=None):
        for row in self._pool(entity):
            if row.get("id") == record_id:
                return dict(row)
        raise EspoError("GET failed: HTTP 404 Not Found")

    async def create(self, entity, payload):
        self._seq += 1
        record = {"id": f"{entity.lower()}-{self._seq}", **payload}
        if entity == "Contact" and "name" not in record:
            record["name"] = f"{payload.get('firstName', '')} {payload.get('lastName', '')}".strip()
        self.created.append((entity, payload))
        self._pool(entity).append(record)
        return record

    async def update(self, entity, record_id, payload):
        self.updated.append((entity, record_id, payload))
        for row in self._pool(entity):
            if row.get("id") == record_id:
                row.update(payload)
        return {"id": record_id}

    async def delete(self, entity, record_id):
        self.deleted.append((entity, record_id))
        pool = self._pool(entity)
        pool[:] = [r for r in pool if r.get("id") != record_id]

    async def upload_attachment(self, *, filename, content_type, data_base64, related_type, field, role="Attachment"):
        self._seq += 1
        att_id = f"att-{self._seq}"
        self.uploads.append({"id": att_id, "filename": filename, "contentType": content_type,
                             "relatedType": related_type, "field": field})
        self.attachments[att_id] = (base64.b64decode(data_base64), content_type)
        return att_id

    async def download_attachment(self, attachment_id):
        if attachment_id not in self.attachments:
            raise EspoError("GET 404")
        return self.attachments[attachment_id]


def mentor_contact():
    return {"id": "c-mentor", "name": "Jane Doe", "emailAddress": "jane@example.org",
            "title": "Consultant", "accountName": "", "cMentorProfileId": "m-1"}


def mentor_profile():
    return {"id": "m-1", "aboutMentor": "<p>Jane led finance for <b>30 years</b>.</p>"
                                        "<img src=\"?entryPoint=attachment&id=x\">",
            "mentorTitle": "Retired CFO", "profilePhotoId": "att-mentor"}


def guest_contact():
    return {"id": "c-guest", "name": "Sam Lee", "emailAddress": "sam@firstbank.example",
            "title": "Small-Business Lender", "accountName": "First Bank", "cMentorProfileId": None}


def crm(**kw):
    kw.setdefault("events", [make_event(id="ev1", slug="grant-writing-basics")])
    kw.setdefault("contacts", [mentor_contact(), guest_contact()])
    kw.setdefault("mentors", [mentor_profile()])
    return PresenterCrm(**kw)


# --- detection ---------------------------------------------------------------


async def test_detection_fails_closed_without_the_entity_or_on_a_failed_read():
    assert await service.presenters_available(crm()) is True
    assert await service.presenters_available(crm(has_entity=False)) is False
    assert await service.presenters_available(crm(meta_fails=True)) is False

    class Bare:  # the dry-run client has no metadata reader
        pass
    assert await service.presenters_available(Bare()) is False


def test_show_bios_is_a_feature_detected_publishing_field():
    spec = next(f for f in cfg.EVENT_FIELDS if f.name == cfg.SHOW_BIOS_FIELD)
    assert spec.group == "Publishing" and spec.type == "bool"
    assert cfg.SHOW_BIOS_FIELD in cfg.DETECTED_FIELDS
    assert cfg.SHOW_BIOS_FIELD in cfg.PUBLIC_SELECT
    # Absent from the editor on a CRM without it, present with it.
    assert cfg.SHOW_BIOS_FIELD not in [f.name for f in service.editor_fields(cfg.AUDIENCE_FIELDS)]
    assert cfg.SHOW_BIOS_FIELD in [f.name for f in service.editor_fields(cfg.DETECTED_FIELDS)]


# --- adding ------------------------------------------------------------------


async def test_adding_a_mentor_copies_biography_title_and_photo_once():
    c = crm()
    row = await service.add_presenter(c, "ev1", contact_id="c-mentor")
    entity, payload = c.created[-1]
    assert entity == cfg.PRESENTER_ENTITY
    assert payload["contactId"] == "c-mentor" and payload["eventId"] == "ev1"
    assert payload["name"] == "Jane Doe"
    assert payload["presenterTitle"] == "Retired CFO"          # the mentor title wins
    assert "30 years" in payload["biography"]
    assert "<img" not in payload["biography"]                  # inline images stripped
    assert payload["displayOrder"] == 1
    # The photo is a COPY bound to the entry's own field, not the mentor's attachment id.
    assert payload["photoId"] != "att-mentor"
    assert c.uploads[-1]["relatedType"] == cfg.PRESENTER_ENTITY
    assert c.uploads[-1]["field"] == cfg.PRESENTER_PHOTO_FIELD
    assert c.attachments[payload["photoId"]][0] == b"PHOTO"
    assert row["id"]
    # Nothing on the Contact or the profile was written.
    assert all(e not in ("Contact", "CMentorProfile") for e, _, _ in c.updated)


async def test_adding_a_guest_contact_takes_title_and_company_from_the_contact():
    c = crm()
    await service.add_presenter(c, "ev1", contact_id="c-guest")
    _, payload = c.created[-1]
    assert payload["presenterTitle"] == "Small-Business Lender"
    assert payload["presenterCompany"] == "First Bank"
    assert payload["biography"] == "" and "photoId" not in payload
    assert not c.uploads


async def test_a_new_email_creates_a_presenter_typed_contact():
    c = crm()
    await service.add_presenter(c, "ev1", new={
        "firstName": "Ada", "lastName": "Lovelace", "email": "Ada@Example.org ",
        "title": "Engineer", "company": "Analytical Engines",
    })
    contact_create = next(p for e, p in c.created if e == "Contact")
    assert contact_create["emailAddress"] == "ada@example.org"
    assert contact_create["cContactType"] == [cfg.PRESENTER_CONTACT_TYPE]
    assert contact_create["title"] == "Engineer"
    _, entry = c.created[-1]
    assert entry["name"] == "Ada Lovelace"
    assert entry["presenterCompany"] == "Analytical Engines"   # on the entry, not the Contact


async def test_a_known_email_reuses_the_contact_without_changing_it():
    c = crm()
    await service.add_presenter(c, "ev1", new={
        "firstName": "Samuel", "lastName": "Lee", "email": "sam@firstbank.example",
        "title": "VP", "company": "Second Bank",
    })
    assert not any(e == "Contact" for e, _ in c.created)
    assert not any(e == "Contact" for e, _, _ in c.updated)       # no null-fill, no edit
    _, entry = c.created[-1]
    assert entry["contactId"] == "c-guest"
    assert entry["presenterTitle"] == "Small-Business Lender"    # the stored Contact's, not the typed one


async def test_a_new_presenter_needs_names_and_an_email():
    c = crm()
    with pytest.raises(service.EventError, match="first and last name"):
        await service.add_presenter(c, "ev1", new={"firstName": "Ada", "email": "a@b.c"})
    with pytest.raises(service.EventError, match="email"):
        await service.add_presenter(c, "ev1", new={"firstName": "Ada", "lastName": "L", "email": "nope"})


async def test_the_same_person_twice_is_refused():
    c = crm()
    await service.add_presenter(c, "ev1", contact_id="c-guest")
    with pytest.raises(service.DuplicatePresenter, match="already a presenter"):
        await service.add_presenter(c, "ev1", contact_id="c-guest")


async def test_a_mentor_profile_the_user_cannot_read_still_adds_the_presenter():
    class Denied(PresenterCrm):
        async def get(self, entity, record_id, select=None):
            if entity == "CMentorProfile":
                raise EspoError("403 forbidden")
            return await super().get(entity, record_id, select)
    c = Denied(events=[make_event(id="ev1")], contacts=[mentor_contact()], mentors=[mentor_profile()])
    await service.add_presenter(c, "ev1", contact_id="c-mentor")
    _, payload = c.created[-1]
    assert payload["presenterTitle"] == "Consultant" and payload["biography"] == ""


# --- editing, ordering, removing ----------------------------------------------


async def test_update_is_whitelisted_and_cleans_the_biography():
    c = crm()
    row = await service.add_presenter(c, "ev1", contact_id="c-guest")
    await service.update_presenter(c, "ev1", row["id"], {
        "presenterTitle": " VP ", "biography": "<p>Hi</p><script>x()</script><img src=x>",
        "contactId": "c-mentor", "eventId": "other", "displayOrder": 9,
    })
    _, _, payload = c.updated[-1]
    assert payload == {"presenterTitle": "VP", "biography": "<p>Hi</p>"}


async def test_an_entry_on_another_event_is_not_found():
    c = crm(events=[make_event(id="ev1"), make_event(id="ev2", slug="other")])
    row = await service.add_presenter(c, "ev2", contact_id="c-guest")
    with pytest.raises(service.PresenterNotFound):
        await service.update_presenter(c, "ev1", row["id"], {"presenterTitle": "X"})
    with pytest.raises(service.PresenterNotFound):
        await service.get_presenter_photo(c, "ev1", row["id"])


async def test_reorder_sets_one_through_n_and_refuses_a_stale_set():
    c = crm()
    a = await service.add_presenter(c, "ev1", contact_id="c-mentor")
    b = await service.add_presenter(c, "ev1", contact_id="c-guest")
    rows = await service.reorder_presenters(c, "ev1", [b["id"], a["id"]])
    assert [r["id"] for r in rows] == [b["id"], a["id"]]
    assert [r["displayOrder"] for r in rows] == [1, 2]
    with pytest.raises(service.EventError, match="reload"):
        await service.reorder_presenters(c, "ev1", [a["id"]])


async def test_remove_deletes_the_entry_and_closes_the_gap():
    c = crm()
    a = await service.add_presenter(c, "ev1", contact_id="c-mentor")
    b = await service.add_presenter(c, "ev1", contact_id="c-guest")
    await service.remove_presenter(c, "ev1", a["id"])
    assert (cfg.PRESENTER_ENTITY, a["id"]) in c.deleted
    assert "Contact" not in [e for e, _ in c.deleted]
    remaining = await service.list_presenters(c, "ev1")
    assert [r["id"] for r in remaining] == [b["id"]] and remaining[0]["displayOrder"] == 1


async def test_photo_upload_binds_to_the_entry_and_a_bad_type_is_refused():
    c = crm()
    row = await service.add_presenter(c, "ev1", contact_id="c-guest")
    with pytest.raises(service.EventError, match="JPEG"):
        await service.set_presenter_photo(c, "ev1", row["id"], filename="x.svg",
                                          content_type="image/svg+xml", data_base64="AA==")
    updated = await service.set_presenter_photo(
        c, "ev1", row["id"], filename="sam.png", content_type="image/png",
        data_base64=base64.b64encode(b"PNG").decode(),
    )
    assert updated["photoId"] == c.uploads[-1]["id"]
    assert (await service.get_presenter_photo(c, "ev1", row["id"]))[0] == b"PNG"
    cleared = await service.clear_presenter_photo(c, "ev1", row["id"])
    assert cleared["photoId"] is None


# --- the page payload --------------------------------------------------------


def test_biography_is_omitted_when_the_switch_is_off():
    rows = [{"id": "p1", "name": "Jane", "presenterTitle": "CFO", "presenterCompany": "",
             "photoId": "att-1", "biography": "<p>Bio</p>", "displayOrder": 1}]
    off = service.public_presenters(rows, {cfg.SHOW_BIOS_FIELD: False},
                                    photo_url_for=lambda r: f"/x/{r['id']}")
    on = service.public_presenters(rows, {cfg.SHOW_BIOS_FIELD: True},
                                   photo_url_for=lambda r: f"/x/{r['id']}")
    assert off[0]["biography"] == "" and on[0]["biography"] == "<p>Bio</p>"
    assert off[0]["photoUrl"] == "/x/p1" and off[0]["title"] == "CFO"
    # No photo, no URL — the renderer draws initials.
    rows[0]["photoId"] = None
    assert service.public_presenters(rows, {}, photo_url_for=lambda r: "/x")[0]["photoUrl"] == ""


def test_photo_routes_are_keyed_on_the_event():
    row = {"id": "p1", "photoId": "abcdef123456789"}
    assert service.public_photo_url("grant-writing", row, base_url="https://apps.example/") == \
        "https://apps.example/api/events/grant-writing/presenters/p1/photo?v=abcdef123456"
    assert service.portal_photo_url("ev1", row) == "/api/portal/events/ev1/presenters/p1/photo?v=abcdef123456"
    assert service.staff_photo_url("ev1", row).startswith("/events/api/events/ev1/presenters/p1/photo")
    assert service.public_photo_url("", row) == ""


# --- the staff router ----------------------------------------------------------


def build(monkeypatch, crm_obj, *, on=True):
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_PRESENTERS", "true" if on else "false")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "true")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)
    import events.router as router_mod
    monkeypatch.setattr(router_mod, "current_user", lambda request: MARKETING)
    monkeypatch.setattr(router_mod, "client_for", lambda settings, u: crm_obj)

    async def _no_log(*a, **kw):
        return None
    monkeypatch.setattr(router_mod, "record_action", _no_log)
    return TestClient(app)


def test_fields_payload_reports_the_switch_and_the_detection(monkeypatch):
    client = build(monkeypatch, crm())
    data = client.get("/events/api/fields").json()
    assert data["presenters"] == {"enabled": True, "available": True}
    assert cfg.SHOW_BIOS_FIELD in {f["name"] for f in data["fields"]}
    client = build(monkeypatch, crm(has_entity=False))
    assert client.get("/events/api/fields").json()["presenters"] == {"enabled": True, "available": False}
    client = build(monkeypatch, crm(), on=False)
    assert client.get("/events/api/fields").json()["presenters"]["enabled"] is False


def test_staff_endpoints_add_list_update_reorder_remove(monkeypatch):
    c = crm()
    client = build(monkeypatch, c)
    r = client.post("/events/api/events/ev1/presenters", json={"contactId": "c-mentor"})
    assert r.status_code == 200, r.text
    first = r.json()["presenter"]
    assert first["title"] == "Retired CFO" and first["photoUrl"].startswith("/events/api/")
    r = client.post("/events/api/events/ev1/presenters", json={"contactId": "c-mentor"})
    assert r.status_code == 409
    r = client.post("/events/api/events/ev1/presenters", json={
        "firstName": "Ada", "lastName": "Lovelace", "email": "ada@example.org"})
    assert r.status_code == 200
    second = r.json()["presenter"]
    assert client.get("/events/api/events/ev1").json()["presenters"][0]["id"] == first["id"]
    r = client.put("/events/api/events/ev1/presenters/order", json={"ids": [second["id"], first["id"]]})
    assert r.status_code == 200 and r.json()["presenters"][0]["id"] == second["id"]
    r = client.put(f"/events/api/events/ev1/presenters/{first['id']}",
                   json={"changes": {"presenterTitle": "CFO (retired)", "contactId": "x"}})
    assert r.status_code == 200 and r.json()["presenter"]["title"] == "CFO (retired)"
    assert client.get("/events/api/presenters/search?q=jane").json()["contacts"][0]["isMentor"] is True
    r = client.delete(f"/events/api/events/ev1/presenters/{second['id']}")
    assert r.status_code == 200
    assert client.get("/events/api/events/ev1/presenters").json()["presenters"][0]["displayOrder"] == 1
    r = client.put("/events/api/events/ev1/presenters/nope", json={"changes": {}})
    assert r.status_code == 404


def test_staff_endpoints_answer_404_when_the_switch_is_off(monkeypatch):
    client = build(monkeypatch, crm(), on=False)
    assert client.post("/events/api/events/ev1/presenters", json={"contactId": "c-guest"}).status_code == 404
    assert client.get("/events/api/events/ev1").json()["presenters"] is None


# --- the pages and the editor source -------------------------------------------


def test_both_event_pages_carry_the_section_and_the_shared_stylesheet():
    for page in ("events/public_frontend/event.html", "portal/frontend/event.html"):
        html = (ROOT / page).read_text(encoding="utf-8")
        assert 'id="presenters"' in html, page
        assert "/shared/event-body.css" in html, page
        assert html.index('id="facts"') < html.index('id="presenters"') < html.index('id="overview"'), page
    js = (ROOT / "frontend" / "shared" / "event-body.js").read_text(encoding="utf-8")
    assert 'presenters($("presenters"), event.presenters)' in js
    css = (ROOT / "frontend" / "shared" / "event-body.css").read_text(encoding="utf-8")
    for cls in ("evb-presenter__photo", "evb-presenter__initials", "evb-presenter__bio"):
        assert f".{cls}" in css, cls


def test_the_editor_opens_the_biography_without_an_image_hook_and_carries_no_names():
    src = (ROOT / "events" / "frontend" / "app.js").read_text(encoding="utf-8")
    start = src.index("function presentersGroup(")
    end = src.index("/* ---------- actions ---------- */")
    block = src[start:end]
    assert "CBMRichText.create(" in block
    assert "uploadImage:" not in block           # public text: no Insert-image hook passed
    assert 'setAttribute("name"' not in block    # never collected as event fields
    assert ".name = " not in block
    assert "presenters/order" in block and "presenters/search" in block
