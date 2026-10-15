"""The CRM-plan applier ships in the image (``scripts/apply_crm_plan.py``) so a
production change can run from inside the deployed web container. These tests
pin the two things a console step page relies on: the naming rules, and the
fingerprint a dry run prints for a plan on a CRM that does not have it yet —
the presenters plan (``5a78484e6b9c`` on crm-test, 10-08-26), the SMS opt-in
plan (``0bc7219ab932``) and the outreach entities plan (``6b29c8928dcf``), the
last two on crm-test 10-14-26."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
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
