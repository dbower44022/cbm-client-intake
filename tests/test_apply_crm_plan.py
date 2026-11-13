"""The CRM-plan applier ships in the image (``scripts/apply_crm_plan.py``) so a
production change can run from inside the deployed web container. These tests
pin the two things a console step page relies on: the naming rules, and the
fingerprint a dry run prints for a plan on a CRM that does not have it yet —
the presenters plan (``5a78484e6b9c`` on crm-test, 10-08-26), the SMS opt-in
plan (``0bc7219ab932``) and the outreach entities plan (``6b29c8928dcf``), the
last two on crm-test 10-14-26."""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys

import pytest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


applier = _load("scripts/apply_crm_plan.py", "apply_crm_plan_under_test")


class _Resp:
    def __init__(self, status: int, body=None):
        self.status_code = status
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return json.loads(self.content)


class _FakeClient:
    """A CRM with CEvent (custom) and Contact (system) and nothing else."""

    _base = "https://crm.example/api/v1"

    def __init__(self):
        self.writes: list[tuple[str, str]] = []

    async def _request(self, method, url, op="", params=None, json_body=None):
        if method != "GET":
            self.writes.append((method, url))
            return _Resp(200, {})
        key = (params or {}).get("key", "")
        if key == "scopes.CEvent":
            return _Resp(200, {"isCustom": True, "entity": True})
        if key == "scopes.Contact":
            return _Resp(200, {"entity": True})
        if key.startswith("scopes."):
            return _Resp(200)          # an unknown key: 200 with an EMPTY body
        if url.endswith("/Admin/fieldManager/CEvent/showPresenterBios"):
            return _Resp(404)
        return _Resp(200)


def test_naming_rules():
    assert applier.stored_entity_name("EventPresenter") == "CEventPresenter"
    assert applier.custom_prefixed("presenterAppearances") == "cPresenterAppearances"


def test_presenters_plan_dry_run_fingerprint_on_a_crm_without_the_entity():
    plan = json.loads((ROOT / "scripts/plans/cevent-presenters.json").read_text())
    client = _FakeClient()
    app = applier.Applier(client, plan, apply=False)
    asyncio.run(app.run())
    assert not app.failed
    assert client.writes == []
    assert app.fingerprint() == "5a78484e6b9c"
    assert "create entity CEventPresenter (from name 'EventPresenter', type Base)" in app.actions
    assert ("create link CEventPresenter.contact -> Contact.cPresenterAppearances "
            "(manyToOne)") in app.actions
    assert len([a for a in app.actions if a.startswith("create")]) == 9


def test_apply_refuses_a_non_crm_test_target_without_the_flag(monkeypatch, capsys):
    monkeypatch.setattr(applier, "load_env", lambda: {
        "ESPO_ADMIN_BASE": "https://crm.clevelandbusinessmentors.org",
        "ESPO_ADMIN_USER": "u", "ESPO_ADMIN_PASS": "p"})
    monkeypatch.setattr(sys, "argv", ["apply_crm_plan.py",
                                      str(ROOT / "scripts/plans/cevent-presenters.json"), "--apply"])
    assert asyncio.run(applier.main()) == 2
    assert "pass --production" in capsys.readouterr().err


class _FakeCrmTest(_FakeClient):
    """crm-test as it stood on 10-14-26 for the prospect-marketing plans: the
    native Contact and Account, the custom entities the links hang on, no
    ``COutreach*`` entity, none of the new fields, and ``Account.cCompanyType``
    without the ``Prospect`` option."""

    CUSTOM = {"CEvent", "CEngagement", "CPartnerProfile", "CSponsorProfile",
              "CInformationRequest", "CEventRegistration"}
    SYSTEM = {"Contact", "Account"}

    async def _request(self, method, url, op="", params=None, json_body=None):
        if method != "GET":
            self.writes.append((method, url))
            return _Resp(200, {})
        key = (params or {}).get("key", "")
        if key.startswith("scopes."):
            entity = key[len("scopes."):]
            if entity in self.CUSTOM:
                return _Resp(200, {"isCustom": True, "entity": True})
            if entity in self.SYSTEM:
                return _Resp(200, {"entity": True})
            return _Resp(200)
        if url.endswith("/Admin/fieldManager/Account/cCompanyType"):
            return _Resp(200, {"type": "multiEnum",
                               "options": ["", "Client", "Sponsor", "Partner", "Other"]})
        if "/Admin/fieldManager/" in url:
            return _Resp(404)
        return _Resp(200)


def test_sms_opt_in_plan_dry_run_fingerprint_on_a_crm_without_the_field():
    plan = json.loads((ROOT / "scripts/plans/contact-sms-opt-in.json").read_text())
    client = _FakeCrmTest()
    app = applier.Applier(client, plan, apply=False)
    asyncio.run(app.run())
    assert not app.failed
    assert client.writes == []
    assert app.actions == ["create field Contact.cSmsOptIn (bool)  [typed 'smsOptIn']"]
    assert app.fingerprint() == "0bc7219ab932"


def test_outreach_entities_plan_dry_run_fingerprint_on_a_crm_without_them():
    plan = json.loads((ROOT / "scripts/plans/coutreach-entities.json").read_text())
    client = _FakeCrmTest()
    app = applier.Applier(client, plan, apply=False)
    asyncio.run(app.run())
    assert not app.failed
    assert client.writes == []
    assert app.fingerprint() == "6b29c8928dcf"
    assert len(app.actions) == 78
    assert "create entity CProspect (from name 'Prospect', type BasePlus)" in app.actions
    # Native-entity names gain the prefix; custom-entity names are stored as typed.
    assert "create field Contact.cFunnelStage (enum)  [typed 'funnelStage']" in app.actions
    assert ("create link Contact.cOutreachCampaign -> COutreachCampaign.contacts "
            "(manyToOne)") in app.actions
    assert ("create link CEngagement.referringPartners -> "
            "CPartnerProfile.referredEngagements (manyToMany)") in app.actions
    assert "add enum options to Account.cCompanyType: Prospect" in app.actions
    # The plan names seventeen links and never a one-to-one.
    links = plan["links"]
    assert len(links) == 17
    assert {l["linkType"] for l in links} == {"manyToOne", "manyToMany"}
    assert all(l.get("relationName") for l in links if l["linkType"] == "manyToMany")
    # Two links may not share a name on one entity (build plan section 1.5 did).
    seen: set[tuple[str, str]] = set()
    for l in links:
        for pair in ((l["entity"], l["link"]), (l["entityForeign"], l["linkForeign"])):
            assert pair not in seen, f"duplicate link name {pair}"
            seen.add(pair)


# --- the tracked-field change (fieldParams {"audited": true}), 11-05-26 ------

_TRACKED = {
    "CMentorProfile": {
        "cbmEmail": {"isCustom": True, "type": "varchar"},
        "mentorStatus": {"type": "enum", "default": None, "isCustom": True, "maxLength": 100,
                         "options": ["", "Prospect", "Active", "Resigned"],
                         "style": {"": None, "Prospect": None, "Active": None, "Resigned": None}},
        "mentorType": {"type": "enum", "isCustom": True, "options": ["", "Mentor", "Co-Mentor"]},
        "acceptingNewClients": {"isCustom": True, "type": "bool"},
        "maximumClientCapacity": {"isCustom": True, "required": False, "type": "int"},
        "mentorStatusNotes": {"cutHeight": 500, "isCustom": True, "rowsMin": 2, "type": "text"},
        "departureDate": {"isCustom": True, "type": "date"},
    },
    "CPartnerProfile": {
        "partnershipStatus": {"type": "enum", "isCustom": True, "maxLength": 100,
                              "options": ["", "Meetings Held", "Inactive", "Candidate"]},
    },
    "CSponsorProfile": {
        "funderStatus": {"type": "enum", "isCustom": True, "maxLength": 100,
                         "options": ["", "Prospective", "Active", "Lapsed", "Ended"]},
    },
}


class _TrackedCrm:
    """crm-test's three profile entities as read on 11-05-26: fieldManager GET
    answers the metadata definition plus ``label``, and HTTP 500 for a field
    that does not exist. ``on_put`` lets a test make the CRM misbehave."""

    _base = "https://crm-test.example/api/v1"

    def __init__(self, defs=None, on_put=None):
        self.defs = copy.deepcopy(defs or _TRACKED)
        self.puts: list[tuple[str, dict]] = []
        self.posts: list[str] = []
        self.on_put = on_put

    async def _request(self, method, url, op="", params=None, json_body=None):
        path = url[len(self._base) + 1:]
        if method == "PUT":
            entity, field = path.split("/")[-2:]
            self.puts.append((f"{entity}.{field}", copy.deepcopy(json_body)))
            stored = {k: v for k, v in json_body.items() if k != "label"}
            stored["isCustom"] = True
            if self.on_put:
                stored = self.on_put(entity, field, stored)
            self.defs[entity][field] = stored
            return _Resp(200, {})
        if method == "POST":
            self.posts.append(path)
            return _Resp(200, {})
        if path.startswith("Admin/fieldManager/"):
            entity, field = path.split("/")[-2:]
            have = self.defs.get(entity, {}).get(field)
            if have is None:
                return _Resp(500)
            return _Resp(200, {**have, "label": field.title()})
        key = (params or {}).get("key", "")
        if key.startswith("scopes."):
            if key[len("scopes."):] in self.defs:
                return _Resp(200, {"isCustom": True, "entity": True})
            return _Resp(200)
        if key.startswith("entityDefs.") and key.endswith(".fields"):
            entity = key.split(".")[1]
            return _Resp(200, self.defs[entity]) if entity in self.defs else _Resp(200)
        return _Resp(200)


def _tracked_plan():
    return json.loads((ROOT / "scripts/plans/mentor-tracked-fields.json").read_text())


def test_tracked_fields_plan_names_the_nine_handoff_fields():
    plan = _tracked_plan()
    assert set(plan) == {"name", "description", "fieldParams"}
    named = [(s["entity"], s["name"]) for s in plan["fieldParams"]]
    assert named == [(e, f) for e, fs in _TRACKED.items() for f in fs]
    assert all(s["params"] == {"audited": True} for s in plan["fieldParams"])


def test_tracked_fields_dry_run_writes_nothing():
    crm = _TrackedCrm()
    app = applier.Applier(crm, _tracked_plan(), apply=False)
    asyncio.run(app.run())
    assert not app.failed
    assert crm.puts == [] and crm.posts == []
    assert len(app.actions) == 9
    assert "change field CMentorProfile.cbmEmail (audited: None -> True)" in app.actions
    # A CRM where none of the nine is tracked yet (crm-test and production,
    # 11-05-26) prints this fingerprint on the dry run.
    assert app.fingerprint() == "e85b46a1a6e0"


def test_tracked_fields_apply_sends_the_whole_definition_with_only_audited_changed():
    crm = _TrackedCrm()
    app = applier.Applier(crm, _tracked_plan(), apply=True)
    asyncio.run(app.run())
    assert not app.failed, app.failed
    assert len(crm.puts) == 9
    for name, body in crm.puts:
        entity, field = name.split(".")
        expected = {k: v for k, v in _TRACKED[entity][field].items() if k != "isCustom"}
        expected.update(label=field.title(), audited=True)
        assert body == expected
    assert crm.posts == ["Admin/rebuild"]
    assert len([a for a in app.actions if a.startswith("verified field")]) == 9


def test_tracked_fields_already_audited_are_skipped():
    defs = copy.deepcopy(_TRACKED)
    defs["CMentorProfile"]["mentorStatus"]["audited"] = True
    crm = _TrackedCrm(defs)
    app = applier.Applier(crm, _tracked_plan(), apply=True)
    asyncio.run(app.run())
    assert not app.failed
    assert "CMentorProfile.mentorStatus" not in [n for n, _ in crm.puts]
    assert len(crm.puts) == 8
    assert any("CMentorProfile.mentorStatus already has" in s for s in app.skipped)


def test_tracked_fields_refuses_a_field_that_does_not_exist():
    defs = copy.deepcopy(_TRACKED)
    del defs["CMentorProfile"]["mentorStatusNotes"]
    crm = _TrackedCrm(defs)
    app = applier.Applier(crm, _tracked_plan(), apply=False)
    asyncio.run(app.run())
    assert app.failed == [
        "field CMentorProfile.mentorStatusNotes does not exist — cannot change it"]
    assert crm.puts == []


def test_tracked_fields_read_back_fails_when_the_definition_was_replaced():
    # The trap in the handoff: the CRM keeps audited but loses the rest of the
    # definition. The read-back must catch it even though audited is true.
    def clobber(entity, field, stored):
        return {k: v for k, v in stored.items() if k != "options"}

    crm = _TrackedCrm(on_put=clobber)
    app = applier.Applier(crm, _tracked_plan(), apply=True)
    asyncio.run(app.run())
    moved = [f for f in app.failed if "changed beyond the plan" in f]
    assert len(moved) == 4    # the four enums lost their options
    assert ("VERIFY field CMentorProfile.mentorStatus changed beyond the plan: "
            "options: ['', 'Prospect', 'Active', 'Resigned'] -> None") in moved


def test_tracked_fields_read_back_fails_when_audited_did_not_stick():
    def drop(entity, field, stored):
        if field == "cbmEmail":
            stored.pop("audited", None)
        return stored

    crm = _TrackedCrm(on_put=drop)
    app = applier.Applier(crm, _tracked_plan(), apply=True)
    asyncio.run(app.run())
    assert app.failed == ["VERIFY field CMentorProfile.cbmEmail still reads {'audited': None}"]


def test_moved_keys_reads_absent_and_null_alike():
    assert applier._moved_keys({"a": 1}, {"a": 1, "b": None}, set()) == set()
    assert applier._moved_keys({"a": 1, "d": None}, {"a": 1}, set()) == set()
    assert applier._moved_keys({"a": 1}, {"a": 2, "x": True}, {"x"}) == {"a"}


def test_tracked_fields_refuses_a_fieldmanager_read_that_disagrees_with_metadata():
    # Review finding 11-05-26: the body is built from the fieldManager read, so
    # a read missing part of the definition must never be written back.
    class _Partial(_TrackedCrm):
        async def _request(self, method, url, op="", params=None, json_body=None):
            resp = await super()._request(method, url, op, params, json_body)
            if method == "GET" and url.endswith("Admin/fieldManager/CMentorProfile/mentorStatus"):
                body = resp.json()
                body.pop("options")
                return _Resp(200, body)
            return resp
    crm = _Partial()
    app = applier.Applier(crm, _tracked_plan(), apply=True)
    asyncio.run(app.run())
    assert any("CMentorProfile.mentorStatus: the fieldManager read differs" in f
               and "options" in f for f in app.failed)
    assert "CMentorProfile.mentorStatus" not in [n for n, _ in crm.puts]


def test_a_forbidden_field_read_is_an_error_not_a_missing_field():
    class _Denied(_TrackedCrm):
        async def _request(self, method, url, op="", params=None, json_body=None):
            if "Admin/fieldManager/" in url and method == "GET":
                return _Resp(403)
            return await super()._request(method, url, op, params, json_body)
    app = applier.Applier(_Denied(), _tracked_plan(), apply=False)
    with pytest.raises(applier.EspoError):
        asyncio.run(app.run())


# --- Business Evaluation (crm-plans/business-evaluation.json), 11-13-26 -----

class _FakeEvalCrm(_FakeClient):
    """crm-test before the Business Evaluation change: the custom entities the
    links hang on and the native User; no CBusinessEvaluation unless
    ``scope`` is given, in which case it exists with those entity settings
    (a dict the fake updates when the applier switches one on, unless
    ``sticky`` is False)."""

    CUSTOM = {"CEngagement", "CClientProfile", "CSession"}

    def __init__(self, scope=None, sticky=True):
        super().__init__()
        self.scope = scope
        self.sticky = sticky
        self.bodies: list[tuple[str, dict]] = []

    async def _request(self, method, url, op="", params=None, json_body=None):
        if method != "GET":
            self.writes.append((method, url))
            self.bodies.append((url, json_body))
            if url.endswith("/EntityManager/action/updateEntity") and self.sticky and self.scope is not None:
                self.scope.update({k: v for k, v in json_body.items() if k != "name"})
            return _Resp(200, {})
        key = (params or {}).get("key", "")
        if key == "scopes.CBusinessEvaluation":
            return _Resp(200, None if self.scope is None else {"isCustom": True, "entity": True, **self.scope})
        if key.startswith("scopes."):
            entity = key[len("scopes."):]
            if entity in self.CUSTOM:
                return _Resp(200, {"isCustom": True, "entity": True})
            if entity == "User":
                return _Resp(200, {"entity": True})
            return _Resp(200)
        if key.startswith("entityDefs.CBusinessEvaluation.fields"):
            return _Resp(200, {"stub": {}})
        if "/Admin/fieldManager/" in url:
            return _Resp(404)
        return _Resp(200)


def _eval_plan():
    return json.loads((ROOT / "crm-plans/business-evaluation.json").read_text())


def test_business_evaluation_plan_dry_run_on_a_crm_without_it():
    client = _FakeEvalCrm()
    app = applier.Applier(client, _eval_plan(), apply=False)
    asyncio.run(app.run())
    assert not app.failed
    assert client.writes == []
    assert "create entity CBusinessEvaluation (from name 'BusinessEvaluation', type Base)" in app.actions
    assert "set entity CBusinessEvaluation assignedUsers=True, collaborators=True" in app.actions
    # User is a native entity: its side of the link gains the c prefix.
    assert ("create link CBusinessEvaluation.approvedBy -> User.cApprovedBusinessEvaluations "
            "(manyToOne)") in app.actions
    assert "create field CClientProfile.evaluationProfile (text)" in app.actions
    assert len([a for a in app.actions if a.startswith("create field")]) == 20
    assert len([a for a in app.actions if a.startswith("create link")]) == 4


def test_business_evaluation_plan_marks_no_field_read_only():
    # A Read-only field drops every API write (ruling 40); the application
    # writes every one of these, the draft report included.
    assert not [f["name"] for f in _eval_plan()["fields"] if f.get("readOnly")]


def test_entity_params_send_only_what_differs_and_read_it_back():
    plan = {"entityParams": [{"entity": "CBusinessEvaluation",
                              "params": {"assignedUsers": True, "collaborators": True}}]}
    client = _FakeEvalCrm(scope={"assignedUsers": True})
    app = applier.Applier(client, plan, apply=True)
    asyncio.run(app.run())
    assert not app.failed
    sent = [b for u, b in client.bodies if u.endswith("/EntityManager/action/updateEntity")]
    assert sent == [{"name": "CBusinessEvaluation", "collaborators": True}]
    assert "verified entity CBusinessEvaluation params" in app.actions


def test_entity_params_already_set_are_skipped():
    plan = {"entityParams": [{"entity": "CBusinessEvaluation", "params": {"collaborators": True}}]}
    client = _FakeEvalCrm(scope={"collaborators": True})
    app = applier.Applier(client, plan, apply=False)
    asyncio.run(app.run())
    assert app.actions == [] and client.writes == []
    assert app.skipped == ["entity CBusinessEvaluation already has collaborators=True"]


def test_entity_params_read_back_fails_when_the_setting_did_not_stick():
    plan = {"entityParams": [{"entity": "CBusinessEvaluation", "params": {"assignedUsers": True}}]}
    client = _FakeEvalCrm(scope={}, sticky=False)
    app = applier.Applier(client, plan, apply=True)
    asyncio.run(app.run())
    assert app.failed == ["VERIFY entity CBusinessEvaluation still reads {'assignedUsers': None}"]
