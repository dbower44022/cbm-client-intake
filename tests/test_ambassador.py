"""The Ambassador Program (prds/Ambassador Program/ambassador-program-prd.md)."""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from ambassador import config as cfg
from ambassador import delivery, lookup, referrals, runner, service
from ambassador import store as store_mod
from core.resumable import ResumableClient
from core.session_kinds import AMBASSADOR_SESSION_TYPE, is_ambassador, where_mentoring
from tests.ambassador_fakes import FakeCrm, MemoryReportStore, settings

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def sent(monkeypatch):
    out: list[tuple[list[str], str]] = []

    async def fake_send(s, to, subject, body):
        out.append((list(to), subject))

    monkeypatch.setattr("ambassador.notify.send_shared", fake_send)
    return out


def _report(payload: dict, **kw) -> dict:
    base = {"id": "r1", "reference": "AMB-TEST0001", "user_id": "u-amb", "user_name": "Pat Ambassador",
            "mentor_profile_id": "mp-amb", "payload": payload,
            "created_at": datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc), "progress": {}}
    base.update(kw)
    return base


def _payload(**kw) -> dict:
    p = {"activityDate": "2026-11-20", "activityType": cfg.INTRODUCTION, "contact": {},
         "personKind": "", "marketingAgreed": False, "followUp": False, "note": "", "corrections": []}
    p.update(kw)
    return p


async def _deliver(crm, s, report):
    return await delivery.deliver(ResumableClient(crm, report.get("progress") or {}), s, report)


def _activity(crm) -> dict:
    return crm.rows(cfg.ACTIVITY)[0]


# --- the session type every count ignores -------------------------------------------

def test_session_kind_helpers():
    assert is_ambassador({"sessionType": AMBASSADOR_SESSION_TYPE})
    assert not is_ambassador({"sessionType": "Client Session"}) and not is_ambassador({})
    w = where_mentoring()
    assert w["type"] == "or"
    assert {"type": "isNull", "attribute": "sessionType"} in w["value"]


#: Modules that read CSession but count nothing, with the reason. Every other
#: module naming CSession must use core/session_kinds (PRD § 4.3).
EXEMPT = {
    "analytics/router.py": "routes; the metrics are in analytics/records.py",
    "assignments/service.py": "re-homes sessions on a reassignment; counts none",
    "comms/crm.py": "links mail to records; counts no sessions",
    "core/action_log.py": "names record types",
    "core/config.py": "settings",
    "core/espo.py": "the CRM client",
    "core/fathom.py": "a transcript source",
    "core/gmeet.py": "a meeting link source",
    "evaluation/review.py": "links a review session the mentor chose",
    "integrations/checks/espocrm.py": "checks the record type exists",
    "sessions/config.py": "field layout",
    "sessions/__init__.py": "exports",
    "sessions/router.py": "routes; the counts are in sessions/service.py",
    "sessions/transcripts.py": "needs a video meeting link, which an ambassador contact never has",
    "setup/readiness.py": "checks the record type exists",
    "worker.py": "schedules jobs",
    "portal/router.py": "its Needs you sessions go through portal/needs.py, which leaves them out",
    "feedback/config.py": "names",
    "ambassador/config.py": "the program writes the sessions",
}


def test_every_session_reader_leaves_ambassador_contacts_out():
    missing = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith((".venv/", "tests/", "scripts/", "alembic/")) or "/__pycache__/" in rel:
            continue
        text = path.read_text(encoding="utf-8")
        if '"CSession"' not in text:
            continue
        if rel in EXEMPT or "session_kinds" in text:
            continue
        missing.append(rel)
    assert not missing, f"read CSession without core/session_kinds: {missing}"


def test_counting_modules_use_the_exclusion():
    for rel in ("analytics/records.py", "feedback/moments.py", "portal/needs.py",
                "sessions/service.py", "sessions/gcal.py"):
        assert "session_kinds" in (ROOT / rel).read_text(), rel


def test_needs_you_skips_an_ambassador_session():
    from portal import needs

    now = datetime(2026, 11, 21, tzinfo=timezone.utc)
    rows = [{"status": "Completed", "engagementId": "e1", "dateStart": "2026-11-15 12:00:00",
             "sessionType": AMBASSADOR_SESSION_TYPE, "sessionNotes": "", "nextSteps": ""}]
    assert needs.session_items(rows, {"e1": "Acme"}, now, summary_field=None) == []


# --- the lookups (AM3a) ---------------------------------------------------------

@pytest.mark.asyncio
async def test_lookup_person_shows_only_contact_and_company_fields():
    crm = FakeCrm()
    co = crm.add("Account", name="Acme", website="https://www.acme.com", cCompanyType=["Client"])
    crm.add("Contact", firstName="Ann", lastName="Lee", emailAddress="ann@acme.com",
            accountId=co["id"], accountName="Acme", cContactType=["Client"], phoneNumber="+12165550100")
    got = await lookup.by_email(settings(), crm, "ann@acme.com")
    assert got["kind"] == "person" and got["isPartner"] is False
    assert set(got["person"]) == {"contactId", "firstName", "lastName", "email", "phone", "title",
                                  "companyId", "organization"}
    assert "Client" not in str(got)


@pytest.mark.asyncio
async def test_lookup_partner_company_says_so():
    crm = FakeCrm()
    co = crm.add("Account", name="Hough Hub", website="houghhub.org", cCompanyType=["Partner"])
    crm.add("Contact", firstName="Bo", lastName="Ray", emailAddress="bo@houghhub.org", accountId=co["id"])
    got = await lookup.by_email(settings(), crm, "new.person@houghhub.org")
    assert got == {"kind": "company", "companies": [
        {"companyId": co["id"], "organization": "Hough Hub", "website": "houghhub.org", "isPartner": True}]}


@pytest.mark.asyncio
async def test_lookup_free_mail_and_member():
    crm = FakeCrm()
    crm.add("Account", name="Gmail Fans", website="gmail.com")
    assert await lookup.by_email(settings(), crm, "someone@gmail.com") == {"kind": "none"}
    assert await lookup.by_email(settings(), crm, "pat@mentors.test") == {"kind": "member"}
    crm.add("Contact", firstName="M", lastName="Ent", emailAddress="m@else.org", cContactType=["Mentor"])
    assert await lookup.by_email(settings(), crm, "m@else.org") == {"kind": "member"}


@pytest.mark.asyncio
async def test_people_search_needs_three_letters_and_skips_members():
    crm = FakeCrm()
    crm.add("Contact", firstName="Annabel", lastName="Lee", emailAddress="a@x.org")
    crm.add("Contact", firstName="Annie", lastName="Mentor", emailAddress="annie@mentors.test")
    assert await lookup.people(settings(), crm, "an") == []
    got = await lookup.people(settings(), crm, "ann")
    assert [p["firstName"] for p in got] == ["Annabel"]


# --- the delivery chain (PRD § 4.2) ----------------------------------------------

@pytest.mark.asyncio
async def test_liked_a_post_has_no_contact(sent):
    crm = FakeCrm()
    aid = await _deliver(crm, settings(), _report(_payload(activityType=cfg.LIKED)))
    act = crm.data[cfg.ACTIVITY][aid]
    assert act["matchStatus"] == cfg.M_NO_CONTACT
    assert act["assignedUsersIds"] == ["u-amb"] and act["mentorProfileId"] == "mp-amb"
    assert not crm.rows(cfg.SESSION) and not sent


@pytest.mark.asyncio
async def test_partner_contact_gets_a_session_and_the_manager_an_email(sent):
    crm = FakeCrm()
    crm.add(cfg.MENTOR, id="mp-mgr", name="Mia Manager", cbmEmail="mia@mentors.test")
    c = crm.add("Contact", name="Bo Ray", emailAddress="bo@houghhub.org", accountName="Hough Hub")
    p = crm.add(cfg.PARTNER, name="Hough Hub", partnerManagerId="mp-mgr", teamsIds=["t1"])
    crm.link(cfg.PARTNER, p["id"], cfg.PARTNER_CONTACTS, c["id"])
    await _deliver(crm, settings(), _report(_payload(
        contact={"email": "bo@houghhub.org", "firstName": "Bo", "lastName": "Ray"},
        personKind=cfg.EXISTING_ORG, note="Spring meetup")))
    sess = crm.rows(cfg.SESSION)
    assert len(sess) == 1
    assert sess[0]["sessionType"] == AMBASSADOR_SESSION_TYPE and sess[0]["status"] == "Completed"
    assert sess[0][cfg.PARTNER_SESSION_FK] == p["id"] and sess[0]["teamsIds"] == ["t1"]
    assert (cfg.SESSION, sess[0]["id"], cfg.ATTENDEE_LINK, c["id"]) in crm.related
    assert sent == [(["mia@mentors.test"], "Pat Ambassador met Bo Ray of Hough Hub")]
    assert _activity(crm)["matchStatus"] == cfg.M_MATCHED


@pytest.mark.asyncio
async def test_client_contact_session_on_current_engagement(sent):
    crm = FakeCrm()
    crm.add(cfg.MENTOR, id="mp-m", name="Mo", cbmEmail="mo@mentors.test")
    c = crm.add("Contact", name="Ann Lee", emailAddress="ann@acme.com")
    old = crm.add(cfg.ENGAGEMENT, name="old", engagementStatus="Completed", createdAt="2025-01-01",
                  primaryEngagementContactId=c["id"], mentorProfileId="mp-x")
    cur = crm.add(cfg.ENGAGEMENT, name="cur", engagementStatus="Active", createdAt="2026-05-01",
                  primaryEngagementContactId=c["id"], mentorProfileId="mp-m",
                  assignedUsersIds=["u-mo"])
    await _deliver(crm, settings(), _report(_payload(contact={"email": "ann@acme.com"},
                                                     personKind=cfg.SOMEONE_ELSE)))
    sess = crm.rows(cfg.SESSION)
    assert [s[cfg.ENGAGEMENT_SESSION_FK] for s in sess] == [cur["id"]]
    assert sess[0]["assignedUsersIds"] == ["u-mo"]
    assert sent[0][0] == ["mo@mentors.test"]
    # The engagement itself is untouched: no status change, no count.
    assert not [u for u in crm.updated if u[0] == cfg.ENGAGEMENT]
    assert old["id"] not in str(sess)


@pytest.mark.asyncio
async def test_unknown_potential_client_is_created_and_credited(sent, monkeypatch):
    leads = []

    async def fake_lead(client, attr, **kw):
        leads.append(kw)
    monkeypatch.setattr("campaigns.attribution.record_lead", fake_lead)
    crm = FakeCrm()
    await _deliver(crm, settings(), _report(_payload(
        activityType=cfg.REFERRED, personKind=cfg.POTENTIAL_CLIENT, marketingAgreed=True,
        contact={"email": "new@bakery.com", "firstName": "Sam", "lastName": "Baker",
                 "organization": "Sam's Bakery", "phone": "216 555 0101"})))
    contact = crm.rows("Contact")[0]
    assert contact["cContactType"] == ["Prospect"] and contact["cReferredById"] == "mp-amb"
    assert contact["cMarketingOptIn"] is True and contact["assignedUsersIds"] == ["u-amb"]
    assert crm.rows("Account")[0]["name"] == "Sam's Bakery"
    assert "cCompanyType" not in crm.rows("Account")[0]
    assert leads and leads[0]["source"] == cfg.LEAD_SOURCE
    act = _activity(crm)
    assert act["matchStatus"] == cfg.M_CREATED and act["referralOutcome"] == cfg.O_NOT_YET


@pytest.mark.asyncio
async def test_unknown_potential_funder_gets_a_prospective_profile(sent, monkeypatch):
    async def fake_lead(client, attr, **kw):
        return None
    monkeypatch.setattr("campaigns.attribution.record_lead", fake_lead)
    crm = FakeCrm()
    crm.add("Team", name="Sponsor Management Team", id="team-s")
    await _deliver(crm, settings(), _report(_payload(
        activityType=cfg.REFERRED, personKind=cfg.POTENTIAL_FUNDER,
        contact={"email": "cr@bank.com", "lastName": "Ng", "organization": "Bank"})))
    prof = crm.rows(cfg.SPONSOR)[0]
    assert prof["funderStatus"] == cfg.SPONSOR_CANDIDATE and prof["referredById"] == "mp-amb"
    assert prof["teamsIds"] == ["team-s"] and not prof.get(cfg.SPONSOR_MANAGER)


@pytest.mark.asyncio
async def test_known_person_referred_keeps_the_first_credit(sent):
    crm = FakeCrm()
    c = crm.add("Contact", name="Ann", emailAddress="ann@x.org", cReferredById="mp-first")
    await _deliver(crm, settings(), _report(_payload(
        activityType=cfg.REFERRED, personKind=cfg.POTENTIAL_CLIENT, contact={"email": "ann@x.org"})))
    assert crm.data["Contact"][c["id"]]["cReferredById"] == "mp-first"
    d = crm.add("Contact", name="Dee", emailAddress="dee@x.org")
    await _deliver(crm, settings(), _report(_payload(
        activityType=cfg.REFERRED, personKind=cfg.POTENTIAL_CLIENT, contact={"email": "dee@x.org"}),
        id="r2"))
    assert crm.data["Contact"][d["id"]]["cReferredById"] == "mp-amb"


@pytest.mark.asyncio
async def test_review_states(sent):
    crm = FakeCrm()
    await _deliver(crm, settings(), _report(_payload(contact={"email": "who@nowhere.org"},
                                                     personKind=cfg.EXISTING_ORG)))
    assert _activity(crm)["matchStatus"] == cfg.M_NOT_MATCHED
    crm2 = FakeCrm()
    crm2.add("Contact", emailAddress="two@x.org")
    crm2.add("Contact", emailAddress="two@x.org")
    await _deliver(crm2, settings(), _report(_payload(contact={"email": "two@x.org"},
                                                      personKind=cfg.SOMEONE_ELSE)))
    assert _activity(crm2)["matchStatus"] == cfg.M_MANY
    crm3 = FakeCrm()
    await _deliver(crm3, settings(), _report(_payload(contact={"firstName": "Lu"},
                                                      personKind=cfg.SOMEONE_ELSE)))
    assert _activity(crm3)["reviewOutcome"] == cfg.R_SEEN   # nothing to review


@pytest.mark.asyncio
async def test_follow_up_alerts_the_team(sent):
    crm = FakeCrm()
    await _deliver(crm, settings(), _report(_payload(followUp=True, note="Needs a speaker")))
    assert sent == [(["alerts@example.org"], "Ambassador follow-up requested by Pat Ambassador")]
    assert _activity(crm)["followUpRequested"] is True


@pytest.mark.asyncio
async def test_a_retry_duplicates_nothing(sent):
    crm = FakeCrm()
    crm.add(cfg.MENTOR, id="mp-mgr", cbmEmail="mia@mentors.test")
    c = crm.add("Contact", name="Bo", emailAddress="bo@h.org")
    p = crm.add(cfg.PARTNER, name="H", partnerManagerId="mp-mgr")
    crm.link(cfg.PARTNER, p["id"], cfg.PARTNER_CONTACTS, c["id"])
    store = MemoryReportStore()
    report, _ = await store.capture(token="t" * 16, user_id="u-amb", user_name="Pat",
                                    mentor_profile_id="mp-amb", lease_seconds=0, payload=_payload(
                                        contact={"email": "bo@h.org"}, personKind=cfg.EXISTING_ORG,
                                        followUp=True, note="x"))
    crm.fail_on = None
    original_update = crm.update

    calls = {"n": 0}

    async def flaky_update(entity, rid, payload):
        if entity == cfg.ACTIVITY and calls["n"] == 0:
            calls["n"] += 1
            from core.espo import EspoError
            raise EspoError("update failed: HTTP 503")
        return await original_update(entity, rid, payload)
    crm.update = flaky_update
    assert await runner.deliver_one(settings(), store, crm, report) is None
    again = await store.get(report["id"])
    assert again["status"] == "pending" and again["attempts"] == 1
    assert await runner.deliver_one(settings(), store, crm, again)
    assert len(crm.rows(cfg.ACTIVITY)) == 1 and len(crm.rows(cfg.SESSION)) == 1
    assert len(sent) == 2     # one manager email, one follow-up alert, never twice


def test_backoff_then_failed():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert store_mod.next_after(1, now) == now + timedelta(minutes=1)
    assert store_mod.next_after(5, now) == now + timedelta(hours=6)
    assert store_mod.next_after(6, now) is None


# --- the credit follows the person (§ 4.4, § 4.5) ------------------------------------

@pytest.mark.asyncio
async def test_intake_credits_the_engagement_and_marks_applied(sent):
    crm = FakeCrm()
    crm.add(cfg.MENTOR, id="mp-amb", cbmEmail="pat@mentors.test", firstName="Pat")
    c = crm.add("Contact", name="Sam Baker", cReferredById="mp-amb")
    e = crm.add(cfg.ENGAGEMENT, name="Sam's Bakery")
    a = crm.add(cfg.ACTIVITY, contactId=c["id"], activityType=cfg.REFERRED,
                referralOutcome=cfg.O_NOT_YET, mentorProfileId="mp-amb")
    assert await referrals.credit_engagement(crm, settings(), contact_id=c["id"], engagement_id=e["id"])
    assert crm.data[cfg.ENGAGEMENT][e["id"]]["referredById"] == "mp-amb"
    assert crm.data[cfg.ACTIVITY][a["id"]]["referralOutcome"] == cfg.O_APPLIED
    assert sent == [(["pat@mentors.test"], "Your referral applied: Sam Baker")]


@pytest.mark.asyncio
async def test_intake_without_a_referral_changes_nothing(sent):
    crm = FakeCrm()
    c = crm.add("Contact", name="Walk In")
    e = crm.add(cfg.ENGAGEMENT, name="X")
    assert not await referrals.credit_engagement(crm, settings(), contact_id=c["id"], engagement_id=e["id"])
    assert not crm.updated and not sent


@pytest.mark.asyncio
async def test_partner_form_reuses_the_referred_candidate(sent):
    crm = FakeCrm()
    acct = crm.add("Account", name="Hub")
    referred = crm.add("Contact", name="Ref")
    prof = crm.add(cfg.PARTNER, name="Hub", partnerCompanyId=acct["id"], partnershipStatus="Candidate",
                   referredById="mp-amb", primaryPartnercontactId=referred["id"])
    managed = crm.add("Account", name="Other")
    crm.add(cfg.PARTNER, name="Other", partnerCompanyId=managed["id"], partnershipStatus="Candidate",
            referredById="mp-amb", partnerManagerId="mp-mgr")
    got = await referrals.referred_candidate(crm, cfg.PARTNER, acct["id"])
    assert got["id"] == prof["id"]
    assert await referrals.referred_candidate(crm, cfg.PARTNER, managed["id"]) is None
    applicant = crm.add("Contact", name="Applicant")
    pid = await referrals.claim_candidate(crm, settings(), cfg.PARTNER, got, applicant["id"],
                                          {"partnershipType": "Referral"})
    assert pid == prof["id"]
    assert crm.data[cfg.PARTNER][pid]["partnershipType"] == "Referral"
    assert crm.data[cfg.PARTNER][pid]["primaryPartnercontactId"] == referred["id"]
    assert (cfg.PARTNER, pid, cfg.PARTNER_CONTACTS, applicant["id"]) in crm.related


@pytest.mark.asyncio
async def test_no_referred_by_link_means_no_reuse():
    crm = FakeCrm(built=False)
    assert await referrals.referred_candidate(crm, cfg.PARTNER, "a1") is None


# --- My activity and the review list ------------------------------------------------

def test_mine_view_hides_what_the_delivery_found():
    now = datetime(2026, 11, 21, tzinfo=timezone.utc)
    row = {"id": "a1", "activityDate": "2026-11-20", "activityType": cfg.REFERRED,
           "receivedAt": "2026-11-20 15:00:00", "referralOutcome": "Applied",
           "matchStatus": "Matched", "routedTo": "session on client X"}
    view = service.mine_view(row, 14, now)
    assert view["editable"] and view["outcome"] == "Applied"
    assert "routedTo" not in view and "matchStatus" not in view
    assert not service.mine_view(row, 14, now + timedelta(days=15))["editable"]
    assert "routedTo" not in service.MINE_SELECT and "matchStatus" not in service.MINE_SELECT


@pytest.mark.asyncio
async def test_correction_outside_the_window_is_refused():
    crm = FakeCrm()
    a = crm.add(cfg.ACTIVITY, activityDate="2026-01-01", activityType=cfg.LIKED,
                receivedAt="2026-01-01 10:00:00")
    with pytest.raises(service.CorrectionRefused):
        await service.correct(crm, a["id"], {"note": "x"}, 14)
    b = crm.add(cfg.ACTIVITY, activityDate="2026-11-20", activityType=cfg.LIKED,
                receivedAt=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    before, after = await service.correct(crm, b["id"], {"note": "fixed", "matchStatus": "x"}, 14)
    assert after == {"note": "fixed"}


def test_review_kinds():
    assert service.review_kind({"followUpRequested": True, "followUpDone": False}) == ["follow-up"]
    assert service.review_kind({"matchStatus": cfg.M_NOT_MATCHED}) == ["contact"]
    assert service.review_kind({"matchStatus": cfg.M_MATCHED, "corrections": "x"}) == ["correction"]
    assert service.review_kind({"matchStatus": cfg.M_NOT_MATCHED, "reviewOutcome": "Dismissed"}) == []


# --- the page and its routes ----------------------------------------------------------

def _client(monkeypatch, *, on=True, user=None):
    from fastapi.testclient import TestClient

    from core.app import create_app
    from core.config import get_settings
    from forms import info_request

    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("AMBASSADOR_PROGRAM", "true" if on else "false")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    if user is not None:
        monkeypatch.setattr("ambassador.router.current_user", lambda r: user)
    return TestClient(app)


MENTOR = {"userId": "u1", "userName": "pat", "name": "Pat", "token": "t", "teams": ["Mentor Team"]}


def test_switched_off_is_404(monkeypatch):
    c = _client(monkeypatch, on=False, user=MENTOR)
    assert c.get("/ambassador/api/session").status_code == 404


def test_signed_out_is_401(monkeypatch):
    c = _client(monkeypatch, on=True)
    assert c.get("/ambassador/api/session").status_code == 401


def test_session_lists_six_activities(monkeypatch):
    c = _client(monkeypatch, user=MENTOR)
    body = c.get("/ambassador/api/session").json()
    assert body["canLog"] is True and body["isReviewer"] is False
    assert [a["value"] for a in body["activities"]] == list(cfg.ACTIVITY_TYPES)
    assert all("{{" not in a["label"] for a in body["activities"])


def test_validation_names_what_is_missing(monkeypatch):
    from ambassador.router import ReportIn, _validate
    from fastapi import HTTPException

    s = settings()
    base = {"submissionToken": "x" * 16, "activityDate": "2026-11-20",
            "activityType": cfg.REFERRED, "followUp": False}
    with pytest.raises(HTTPException) as e:
        _validate(ReportIn(**base), s)
    assert "who you referred" in e.value.detail
    with pytest.raises(HTTPException) as e:
        _validate(ReportIn(**{**base, "contact": {"email": "a@b.org"}}), s)
    assert "This person is" in e.value.detail
    with pytest.raises(HTTPException) as e:
        _validate(ReportIn(**{**base, "activityType": cfg.LIKED, "followUp": True}), s)
    assert "what help you need" in e.value.detail
    got = _validate(ReportIn(**{**base, "activityType": cfg.LIKED,
                                "contact": {"email": "a@b.org"}, "personKind": cfg.SOMEONE_ELSE}), s)
    assert got["contact"] == {} and got["personKind"] == ""


def test_pages_load_busy_first_and_the_sign_in_box():
    for rel in ("ambassador/frontend/index.html", "ambassador/frontend/review/index.html"):
        html = (ROOT / rel).read_text()
        scripts = [l for l in html.splitlines() if "<script" in l]
        assert "busy.js" in scripts[0] and "textsize.js" in scripts[1], rel
        assert "/shared/signin.js" in html and 'name="cbm-org"' in html, rel


def test_reset_clears_the_report_table():
    from core.sandbox_reset import RESET_TABLES

    assert "ambassador_report" in RESET_TABLES


def test_crm_plan_has_no_read_only_field_and_the_links():
    import json

    plan = json.loads((ROOT / "crm-plans/ambassador.json").read_text())
    assert not [f for f in plan["fields"] if f.get("readOnly")]
    links = {(l["entity"], l["link"]) for l in plan["links"]}
    assert ("Contact", "referredBy") in links and ("CEngagement", "referredBy") in links
    stored = {f["name"] for f in plan["fields"]}
    assert set(service.ACTIVITY_SELECT.split(",")) - stored - {
        "id", "name", "mentorProfileId", "mentorProfileName", "contactId", "contactName",
        "companyId", "companyName", "createdAt"} == set()


def test_no_possessive_of_the_organization_name():
    for rel in ("ambassador/email.py", "ambassador/frontend/index.html",
                "ambassador/frontend/review/index.html"):
        text = (ROOT / rel).read_text()
        assert "{org}'s" not in text and "{{org}}'s" not in text and "(org)}'s" not in text, rel
