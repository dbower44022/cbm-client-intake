"""The Overview status picker on every domain (Doug, 10-21-26: partners and
funders "in exactly the same manner as the client engagement page"). The
funder status (ruling 67) is read and shown only once the CRM has the field."""

from __future__ import annotations

import asyncio

from sessions import service
from sessions.config import DOMAINS


def test_every_domain_has_an_editable_status():
    assert DOMAINS["mentorsessions"].status_edit_attr == "engagementStatus"
    assert DOMAINS["partnersessions"].status_edit_attr == "partnershipStatus"
    assert DOMAINS["sponsorsessions"].status_edit_attr == "funderStatus"


def test_the_status_fact_is_the_picker():
    for slug, attr in (("partnersessions", "partnershipStatus"), ("sponsorsessions", "funderStatus")):
        cfg = DOMAINS[slug]
        items = service._overview_items(cfg, {"id": "r1", attr: "Active"})
        status = [i for i in items if i.get("statusEdit")]
        assert len(status) == 1 and status[0]["type"] == "badge" and status[0]["value"] == "Active"


def test_funder_status_is_left_out_until_the_crm_has_it():
    cfg = DOMAINS["sponsorsessions"]
    items = service._overview_items(cfg, {"id": "r1"}, absent={"funderStatus"})
    assert not any(i["label"] == "Funder status" for i in items)


class _Meta:
    def __init__(self, fields):
        self.fields = fields

    async def metadata(self, key):
        return self.fields


def test_optional_attributes_follow_live_metadata():
    cfg = DOMAINS["sponsorsessions"]
    run = asyncio.run
    assert run(service._optional_present(cfg, _Meta({"funderStatus": {}}), cfg.detail_optional_select)) == ["funderStatus"]
    assert run(service._optional_present(cfg, _Meta({}), cfg.detail_optional_select)) == []
