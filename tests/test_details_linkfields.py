"""Curated link-field pickers in the Details tab + the always-shown Overview
fact (Doug's 2026-07-22 report: the Referring partner rail item vanished on
unlinked engagements, and the app had no way to SET the link — the values on
record had been set in the EspoCRM UI)."""

from __future__ import annotations

import pytest

from core.espo import EspoError
from sessions import details, service
from sessions.config import MENTOR

# --- _field_spec: the curated link picker ----------------------------------

_ENG_META = {
    "name": {"type": "varchar"},
    "engagementStatus": {"type": "enum", "options": ["Active", "Submitted"]},
    "referringPartner": {"type": "link"},
}


def test_field_spec_appends_link_picker_when_crm_has_the_link():
    spec = details._field_spec(_ENG_META, "CEngagement")
    link = [f for f in spec if f["type"] == "linkselect"]
    assert link == [{
        "name": "referringPartnerId", "label": "Referring partner",
        "type": "linkselect", "editable": True,
        "linkEntity": "CPartnerProfile", "nameAttr": "referringPartnerName",
    }]


def test_field_spec_omits_link_picker_when_crm_lacks_the_link():
    meta = {k: v for k, v in _ENG_META.items() if k != "referringPartner"}
    spec = details._field_spec(meta, "CEngagement")
    assert not any(f["type"] == "linkselect" for f in spec)
    # and no other entity gets it at all
    assert not any(f["type"] == "linkselect" for f in details._field_spec(_ENG_META, "Account"))


def test_select_includes_link_id_and_name():
    spec = details._field_spec(_ENG_META, "CEngagement")
    sel = details._select_for(spec, _ENG_META)
    assert "referringPartnerId" in sel.split(",")
    assert "referringPartnerName" in sel.split(",")


def test_section_carries_value_name_for_link_fields():
    spec = details._field_spec(_ENG_META, "CEngagement")
    rec = {"id": "E1", "name": "Eng", "engagementStatus": "Active",
           "referringPartnerId": "P1", "referringPartnerName": "Glide"}
    sec = details._section("Engagement", "CEngagement", rec, spec, True)
    f = next(x for x in sec["fields"] if x["name"] == "referringPartnerId")
    assert f["value"] == "P1" and f["valueName"] == "Glide"
    assert sec["values"]["referringPartnerName"] == "Glide"


# --- _clean_changes: the write path -----------------------------------------

def test_clean_changes_passes_link_id_and_clears_on_empty():
    spec = {f["name"]: f for f in details._field_spec(_ENG_META, "CEngagement")}
    assert details._clean_changes(spec, {"referringPartnerId": "P9"}) == {"referringPartnerId": "P9"}
    # the select's blank option ("") clears the link as an explicit null
    assert details._clean_changes(spec, {"referringPartnerId": ""}) == {"referringPartnerId": None}
    # anything not in the spec still drops (whitelist unchanged)
    assert details._clean_changes(spec, {"mentorProfileId": "HIJACK"}) == {}


# --- build_details: the option list -----------------------------------------

class _Fake:
    def __init__(self, *, partners=None, forbid_partner_list=False):
        self._partners = partners or []
        self._forbid = forbid_partner_list
        self.meta = {"CEngagement": _ENG_META, "Contact": {"firstName": {"type": "varchar"}},
                     "Account": {"name": {"type": "varchar"}},
                     "CClientProfile": {"industrySector": {"type": "enum", "options": []}}}

    async def metadata(self, key):
        entity = key.split(".")[1]
        return self.meta.get(entity, {})

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "name": "Rec " + record_id}

    async def list(self, entity, **kw):
        if entity == "CPartnerProfile":
            if self._forbid:
                raise EspoError("list CPartnerProfile failed: HTTP 403 forbidden")
            return {"list": self._partners}
        return {"list": []}

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": []}

    async def app_user(self):
        return {"acl": {"table": {}}}


@pytest.mark.asyncio
async def test_build_details_attaches_link_options():
    fake = _Fake(partners=[{"id": "P1", "name": "Glide"}, {"id": "P2", "name": "COSE"}])
    res = await details.build_details(MENTOR, fake, "E1", user_id="u1")
    assert res["linkOptions"]["CPartnerProfile"] == [
        {"id": "P1", "name": "Glide"}, {"id": "P2", "name": "COSE"},
    ]


@pytest.mark.asyncio
async def test_build_details_link_options_best_effort_on_403():
    fake = _Fake(forbid_partner_list=True)
    res = await details.build_details(MENTOR, fake, "E1", user_id="u1")
    assert "linkOptions" not in res  # picker degrades read-only; tab still loads


# --- Overview: the always-shown fact ----------------------------------------

def test_overview_referring_partner_always_renders():
    # Linked: value + partner pop-up link.
    parent = {"engagementStatus": "Active", "referringPartnerName": "Glide",
              "referringPartnerId": "P1"}
    items = {i["label"]: i for i in service._overview_items(MENTOR, parent)}
    rp = items["Referring partner"]
    assert rp["value"] == "Glide"
    assert rp["link"] == {"entity": "CPartnerProfile", "id": "P1"}
    # Unlinked: the slot still renders (value None -> "—"), with no link.
    bare = {i["label"]: i for i in service._overview_items(MENTOR, {"engagementStatus": "Active"})}
    rp2 = bare["Referring partner"]
    assert rp2["value"] is None and "link" not in rp2
    # Other empty facts still drop (the always flag is per-item).
    assert "Meeting cadence" not in bare
