"""The Calls tab side panel and the caller's link (build plan § 7e.10, ruling
116; § 7d.2 and ruling 126; step M10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from campaigns import calls, leadcode, service
from campaigns import config as cfg
from core.config import Settings
from tests.test_campaigns import FakeCrm, FakeStore
from tests.test_campaigns_phase3 import MENTOR, _running_call_campaign, _seed_callable, run


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class CodeCrm(FakeCrm):
    """FakeCrm with the lead-code fields and an ``in`` on ids."""

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.PROSPECT}.fields":
            return {**(await super().metadata(key) or {}), leadcode.LEAD_FIELD: {"type": "varchar"}}
        if key == f"entityDefs.{cfg.CONTACT}.fields":
            return {leadcode.CONTACT_FIELD: {"type": "varchar"}}
        return await super().metadata(key)


def _panel(**kw) -> Settings:
    return Settings(campaigns_calls=True, calls_panel=True, **kw)


def test_switch_off_answers_exactly_as_before():
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    out = run(calls.call_list(crm, crm, MENTOR, Settings(campaigns_calls=True)))
    assert "panel" not in out and "counts" not in out and "attempts" not in out["rows"][0]


def test_the_panel_counts_attempts_and_done_today_and_sinks_later_rows():
    crm = CodeCrm()
    camp = _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    now = datetime.now(timezone.utc)
    # Two earlier attempts on p1, one of them today.
    crm.add(cfg.TOUCH, {"channel": "Call", "touchStatus": "Done", "outcome": "No answer", "prospectId": "p1",
                        "prospectName": "Phone Shop", "outreachCampaignId": camp["id"],
                        "doneAt": _stamp(now - timedelta(days=3))})
    crm.add(cfg.TOUCH, {"channel": "Call", "touchStatus": "Done", "outcome": "No answer", "prospectId": "p1",
                        "prospectName": "Phone Shop", "outreachCampaignId": camp["id"], "doneAt": _stamp(now)})
    # p2 is planned for tomorrow: a call-again row sinks with its time.
    crm.rows[cfg.TOUCH]["t2"]["plannedAt"] = _stamp(now + timedelta(days=1))
    out = run(calls.call_list(crm, crm, MENTOR, _panel()))
    assert out["panel"] is True
    rows = {r["touchId"]: r for r in out["rows"]}
    assert rows["t1"]["attempts"] == 2 and rows["t1"]["lastAttempt"]["outcome"] == "No answer"
    assert rows["t3"]["attempts"] == 0 and rows["t3"]["lastAttempt"] is None
    assert [r["touchId"] for r in out["rows"]][-1] == "t2" and rows["t2"]["later"] is True
    assert out["counts"] == {"left": 3, "calledToday": 1}
    assert [d["name"] for d in out["doneToday"]] == ["Phone Shop"]


def test_the_personal_link_is_the_campaigns_first_link_plus_the_persons_code():
    crm, store = CodeCrm(), FakeStore()
    camp = _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    crm.rows[cfg.PROSPECT]["p1"][leadcode.LEAD_FIELD] = "ABCDEFGHJKMN"
    link = run(store.create_link(campaign_id=camp["id"], name="Form", destination_kind=cfg.DEST_FORM,
                                 destination_target="client-intake", destination_slug=None, created_by="t"))
    out = run(calls.call_list(crm, crm, MENTOR, _panel(), store=store, base_url="https://apps.example.org/"))
    rows = {r["touchId"]: r for r in out["rows"]}
    assert rows["t1"]["link"] == f"https://apps.example.org/c/{link['token']}/ABCDEFGHJKMN"
    assert rows["t1"]["linkNote"] == ""
    assert rows["t2"]["link"] == f"https://apps.example.org/c/{link['token']}"
    assert "no code yet" in rows["t2"]["linkNote"]


def test_a_campaign_with_no_link_says_so_in_words():
    crm = CodeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    row = run(calls.call_list(crm, crm, MENTOR, _panel(), store=FakeStore()))["rows"][0]
    assert row["link"] == "" and "no link yet" in row["linkNote"]


def test_building_the_list_mints_each_persons_code_when_asked():
    crm = CodeCrm()
    _seed_callable(crm)
    camp = crm.add(cfg.CAMPAIGN, {"name": "Chamber calls", "campaignKind": "Call", "campaignStatus": "Draft"})
    rule = {"statuses": ["Qualified", "Unqualified"], "stages": ["Prospect"]}
    built = run(calls.build_list(crm, crm, camp, rule, mint_codes=True))
    assert built["codes"] == {"ready": built["pieces"], "failed": 0}
    leads = [t["prospectId"] for t in crm.rows[cfg.TOUCH].values()
             if t.get("prospectId") and t.get("outreachCampaignId") == camp["id"]]
    assert leads and all(leadcode.looks_like_code(crm.rows[cfg.PROSPECT][i][leadcode.LEAD_FIELD]) for i in leads)
    again = run(calls.build_list(crm, crm, crm.rows[cfg.CAMPAIGN][camp["id"]], rule))
    assert "codes" not in again                                 # without the switch nothing is minted


def test_call_again_plans_the_row_at_the_chosen_time():
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    when = _stamp(datetime.now(timezone.utc) + timedelta(days=2))
    run(calls.record_outcome(crm, crm, MENTOR, "t1", outcome="No answer", notes="", call_again=True,
                             settings=_panel(), call_again_at=when))
    fresh = [t for t in crm.rows[cfg.TOUCH].values() if t.get("prospectId") == "p1" and t["touchStatus"] == "Planned"]
    assert len(fresh) == 1 and fresh[0]["plannedAt"] == when


@pytest.mark.parametrize("when,words", [
    ("tomorrow", "Choose the day and time"),
    (_stamp(datetime.now(timezone.utc) - timedelta(hours=2)), "already passed"),
])
def test_call_again_refuses_a_bad_time_and_writes_nothing(when, words):
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    with pytest.raises(service.CampaignError, match=words):
        run(calls.record_outcome(crm, crm, MENTOR, "t1", outcome="No answer", notes="", call_again=True,
                                 settings=_panel(), call_again_at=when))
    assert crm.rows[cfg.TOUCH]["t1"]["touchStatus"] == "Planned"


def test_the_panel_reads_codes_in_one_batch_not_one_per_row():
    crm = CodeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    seen: list[str] = []
    original = crm.list

    async def counting(entity, **kw):
        seen.append(entity)
        return await original(entity, **kw)
    crm.list = counting
    run(calls.call_list(crm, crm, MENTOR, _panel()))
    assert seen.count(cfg.PROSPECT) == 1
