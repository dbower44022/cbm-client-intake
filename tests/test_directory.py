"""Workspace Directory engine: live-layout columns, list/search/filter/paginate,
the view+edit detail payload, the owned-record edit gate, and the router gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from directory import service
from directory.config import COMPANIES, MENTORS
from forms import info_request, volunteer


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- a configurable fake EspoClient -----------------------------------------

class FakeClient:
    def __init__(self, *, layouts, i18n, fields, records, acl=None):
        self.layouts = layouts        # {(entity, name): data}
        self._i18n = i18n             # {entity: {"fields": {...}}}
        self.fields = fields          # {entity: {field: def}}
        self.records = records        # {entity: [record, ...]}
        self.acl = acl or {}
        self.updated = []

    async def layout(self, entity, name="list"):
        return self.layouts[(entity, name)]

    async def i18n(self, scope):
        return {scope: self._i18n.get(scope, {})}

    async def metadata(self, key):
        return self.fields[key.split(".")[1]]

    async def app_user(self):
        return {"acl": {"table": self.acl}}

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        rows = list(self.records.get(entity, []))
        for cl in where or []:
            t, attr = cl["type"], cl.get("attribute")
            if t == "contains":
                v = cl["value"].lower()
                rows = [r for r in rows if v in str(r.get(attr, "")).lower()]
            elif t == "in":
                rows = [r for r in rows if r.get(attr) in cl["value"]]
            elif t == "arrayAnyOf":
                rows = [r for r in rows if set(r.get(attr) or []) & set(cl["value"])]
            elif t == "isTrue":
                rows = [r for r in rows if r.get(attr)]
            elif t == "isFalse":
                rows = [r for r in rows if not r.get(attr)]
        total = len(rows)
        return {"total": total, "list": rows[offset:offset + max_size]}

    async def get(self, entity, record_id, select=None):
        for r in self.records.get(entity, []):
            if r["id"] == record_id:
                return dict(r)
        raise AssertionError("record not found")

    async def update(self, entity, record_id, payload):
        self.updated.append((entity, record_id, payload))
        return {"id": record_id, **payload}


def _accounts_client(acl_edit="own"):
    return FakeClient(
        layouts={
            ("Account", "list"): [
                {"name": "name", "link": True},
                {"name": "cCompanyType"},
                {"name": "website", "notSortable": True},
            ],
            ("Account", "detail"): [
                {"customLabel": "Identification", "rows": [
                    [{"name": "name"}],
                    [{"name": "cCompanyType"}, {"name": "website"}],
                    [{"name": "description"}, False],
                ]},
            ],
        },
        i18n={"Account": {"fields": {"cCompanyType": "Company Type", "website": "Website", "name": "Name"}}},
        fields={"Account": {
            "name": {"type": "varchar"},
            "cCompanyType": {"type": "multiEnum", "options": ["Client", "Partner", "Donor"]},
            "website": {"type": "url"},
            "description": {"type": "text"},
        }},
        records={"Account": [
            {"id": "a1", "name": "Acme", "cCompanyType": ["Client"], "website": "acme.com",
             "description": "note", "assignedUsersIds": ["u1"]},
            {"id": "a2", "name": "Beta", "cCompanyType": ["Partner"], "website": "",
             "assignedUsersIds": []},
            {"id": "a3", "name": "Gamma", "cCompanyType": ["Donor"], "assignedUsersIds": ["u9"]},
        ]},
        acl={"Account": {"edit": acl_edit}},
    )


# --- columns / filters (read from the live layout) ---------------------------

@pytest.mark.asyncio
async def test_columns_come_from_the_list_layout():
    cols = await service.columns(_accounts_client(), COMPANIES)
    assert [c["key"] for c in cols] == ["name", "cCompanyType", "website"]
    assert [c["label"] for c in cols] == ["Name", "Company Type", "Website"]
    assert [c["type"] for c in cols] == ["text", "array", "url"]
    assert cols[0]["link"] is True
    assert cols[2]["sortable"] is False  # website is notSortable in the layout


@pytest.mark.asyncio
async def test_filters_resolve_options_from_metadata():
    flt = await service.filters(_accounts_client(), COMPANIES)
    assert flt == [{"key": "cCompanyType", "label": "Company Type", "type": "multi",
                    "options": ["Client", "Partner", "Donor"]}]


# --- list / search / filter / paginate --------------------------------------

@pytest.mark.asyncio
async def test_list_paginates_and_flags_more():
    page = await service.list_records(_accounts_client(), COMPANIES, page=1, page_size=2)
    assert page["total"] == 3 and len(page["rows"]) == 2 and page["hasMore"] is True
    page2 = await service.list_records(_accounts_client(), COMPANIES, page=2, page_size=2)
    assert len(page2["rows"]) == 1 and page2["hasMore"] is False
    # rows carry exactly the column keys + id
    assert set(page["rows"][0]) == {"id", "name", "cCompanyType", "website"}


@pytest.mark.asyncio
async def test_search_and_filter():
    hit = await service.list_records(_accounts_client(), COMPANIES, q="acme")
    assert [r["name"] for r in hit["rows"]] == ["Acme"]
    partners = await service.list_records(
        _accounts_client(), COMPANIES, applied_filters={"cCompanyType": ["Partner"]}
    )
    assert [r["name"] for r in partners["rows"]] == ["Beta"]


# --- detail: CRM-arranged panels + owned-record edit gate --------------------

@pytest.mark.asyncio
async def test_detail_panels_and_edit_gate_owner():
    d = await service.detail(_accounts_client(), COMPANIES, "a1", user_id="u1")
    assert d["name"] == "Acme"
    assert d["editable"] is True and d["isOwn"] is True
    titles = [p["title"] for p in d["panels"]]
    assert "Identification" in titles
    ident = next(p for p in d["panels"] if p["title"] == "Identification")
    website = next(f for f in ident["fields"] if f["key"] == "website")
    assert website["value"] == "acme.com" and website["editable"] is True


@pytest.mark.asyncio
async def test_detail_edit_gate_non_owner_readonly():
    # edit=own and the user does not own a2 => not editable (view only).
    d = await service.detail(_accounts_client(), COMPANIES, "a2", user_id="u1")
    assert d["editable"] is False and d["isOwn"] is False
    assert all(not f["editable"] for p in d["panels"] for f in p["fields"])


@pytest.mark.asyncio
async def test_detail_edit_all_makes_owner_irrelevant():
    d = await service.detail(_accounts_client(acl_edit="all"), COMPANIES, "a3", user_id="u1")
    assert d["editable"] is True  # edit=all: not gated on ownership


# --- save: whitelist + enum-drift drop --------------------------------------

@pytest.mark.asyncio
async def test_save_whitelists_and_drops_drifted_enum():
    client = _accounts_client()
    await service.save(client, COMPANIES, "a1", {
        "website": "new.example.com",
        "cCompanyType": ["Client", "Bogus"],   # Bogus not a live option
        "notAField": "x",                        # not editable → dropped
    })
    assert len(client.updated) == 1
    _, rid, payload = client.updated[0]
    assert rid == "a1"
    assert payload["website"] == "new.example.com"
    assert payload["cCompanyType"] == ["Client"]   # Bogus dropped
    assert "notAField" not in payload


# --- mentors: no inline edit; handoff --------------------------------------

def _mentor_client():
    return FakeClient(
        layouts={
            ("CMentorProfile", "list"): [{"name": "name", "link": True}, {"name": "mentorStatus"}],
            ("CMentorProfile", "detail"): [
                {"tabLabel": "Status", "rows": [[{"name": "mentorStatus"}]]},
            ],
        },
        i18n={"CMentorProfile": {"fields": {"mentorStatus": "Mentor Status"}}},
        fields={"CMentorProfile": {"mentorStatus": {"type": "enum", "options": ["Active", "Approved"]}}},
        records={"CMentorProfile": [
            {"id": "m1", "name": "Pat Mentor", "mentorStatus": "Active", "assignedUsersIds": ["u1"]},
        ]},
        acl={"CMentorProfile": {"edit": "all"}},
    )


@pytest.mark.asyncio
async def test_mentors_are_inline_read_only_with_handoff():
    d = await service.detail(_mentor_client(), MENTORS, "m1", user_id="u1")
    # Even with CRM edit=all, the mentor directory hands editing off.
    assert d["editable"] is False
    assert d["editHandoff"] == "/mentorprofile/"
    assert d["isOwn"] is True


@pytest.mark.asyncio
async def test_saving_a_handoff_kind_is_refused():
    with pytest.raises(service.DirectoryError):
        await service.save(_mentor_client(), MENTORS, "m1", {"mentorStatus": "Approved"})


# --- router gate -------------------------------------------------------------

def _app(monkeypatch, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _login(monkeypatch, teams):
    user = {"userId": "u1", "userName": "jdoe", "name": "Jane Doe", "token": "tok",
            "isAdmin": False, "teams": teams, "roles": []}

    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return user

    async def fake_refresh(settings, session_user):
        return dict(session_user)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)


def test_partners_directory_is_registered():
    from directory.config import DIRECTORIES
    partners = DIRECTORIES.get("partners")
    assert partners is not None
    assert partners.entity == "CPartnerProfile"
    assert partners.editable is True and partners.edit_handoff is None


def test_all_directory_kinds_have_routes(monkeypatch):
    app = _app(monkeypatch)
    paths = {r.path for r in app.routes if isinstance(getattr(r, "path", None), str)}
    for kind in ("companies", "contacts", "mentors", "partners"):
        assert f"/directory/{kind}/api/session" in paths


def test_directory_requires_authentication(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/directory/companies/api/session").status_code == 401
        assert c.get("/directory/partners/api/session").status_code == 401


def test_directory_403_for_non_workspace_team(monkeypatch):
    _login(monkeypatch, teams=["Marketing Admin Team"])  # not the workspace team
    with TestClient(_app(monkeypatch)) as c:
        c.post("/api/portal/login", json={"username": "x", "password": "y"})
        r = c.get("/directory/companies/api/session")
        assert r.status_code == 403
        assert "not authorized" in r.json()["detail"].lower()
