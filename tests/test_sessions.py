"""Session Management engine: config, service (list/detail/create/update), and
router auth-gating — across the three domains."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions import details, service
from sessions.config import DOMAINS, MENTOR, PARTNER, SPONSOR

_USER = {"userId": "u1", "userName": "boss", "name": "The Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- fake CRM client -------------------------------------------------------

class Fake:
    def __init__(self, *, mentors=None, contacts=None, related=None, records=None, meta_fields=None, acl=None):
        self.mentors = mentors or []            # rows returned by list(CMentorProfile)
        self.contacts = contacts or []          # rows returned by list(Contact)
        self.related = related or {}            # link name -> [rows]
        self.records = dict(records or {})      # (entity, id) -> dict
        self.meta_fields = meta_fields or {}
        self.acl = acl or {}                    # {entity: {"edit": "no"|"all"|...}}
        self.created = []
        self.updates = []
        self.relates = []
        self.unrelates = []
        self.list_calls = []
        self._seq = 0

    async def list(self, entity, **kw):
        self.list_calls.append((entity, kw))
        if entity == "CMentorProfile":
            return {"list": self.mentors}
        if entity == "Contact":
            return {"list": self.contacts}
        return {"list": []}

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": self.related.get(link, [])}

    async def get(self, entity, record_id, select=None):
        return dict(self.records.get((entity, record_id), {}), id=record_id)

    async def create(self, entity, payload):
        self._seq += 1
        rid = f"{entity.lower()}-{self._seq}"
        self.created.append((entity, payload))
        self.records[(entity, rid)] = dict(payload, id=rid)
        return {"id": rid}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        rec = self.records.setdefault((entity, record_id), {"id": record_id})
        rec.update(payload)
        return {"id": record_id}

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))

    async def unrelate(self, entity, record_id, link, related_id):
        self.unrelates.append((entity, record_id, link, related_id))

    async def metadata(self, key):
        return self.meta_fields

    async def app_user(self):
        return {"acl": {"table": self.acl}}


# --- config ----------------------------------------------------------------

def test_domains_registered():
    assert set(DOMAINS) == {"mentorsessions", "partnersessions", "sponsorsessions"}


def test_domain_links_match_crm():
    """Lock the live-verified CSession parent links / reverse links per domain."""
    assert MENTOR.session_parent_link == "engagement" and MENTOR.session_parent_fk == "engagementId"
    assert MENTOR.manager_owned_link == "engagements1"
    assert MENTOR.manager_comentor_link == "engagements"  # reverse of additionalMentors
    assert MENTOR.parent_sessions_link == "engagementSessions"
    assert MENTOR.supports_comentor is True
    assert MENTOR.status_values == ()  # no status pre-filter — the grid loads all

    assert PARTNER.session_parent_link == "partnerSession" and PARTNER.session_parent_fk == "partnerSessionId"
    assert PARTNER.manager_owned_link == "managedPartners"
    assert PARTNER.manager_comentor_link is None
    assert PARTNER.parent_sessions_link == "sessions"
    assert PARTNER.supports_comentor is False

    assert SPONSOR.session_parent_link == "sponsorProfile" and SPONSOR.session_parent_fk == "sponsorProfileId"
    assert SPONSOR.manager_owned_link == "managedSponsors"  # reverse of cBMSponsorManager
    assert SPONSOR.parent_sessions_link == "sponsorSessions"


# --- resolve manager profile ----------------------------------------------

@pytest.mark.asyncio
async def test_resolve_manager_profile_single_field():
    fake = Fake(mentors=[{"id": "p9", "assignedUserId": "u1"}, {"id": "pX", "assignedUserId": "u2"}])
    assert await service.resolve_manager_profile(fake, "u1") == "p9"


@pytest.mark.asyncio
async def test_resolve_manager_profile_collaborators_field():
    # prod: CMentorProfile uses assignedUsers (collaborators), not assignedUser.
    fake = Fake(mentors=[{"id": "p9", "assignedUsersIds": ["u1"]}])
    assert await service.resolve_manager_profile(fake, "u1") == "p9"


@pytest.mark.asyncio
async def test_resolve_manager_profile_none_when_unlinked():
    fake = Fake(mentors=[{"id": "pX", "assignedUserId": "u2"}])
    assert await service.resolve_manager_profile(fake, "u1") is None


# --- list_records ----------------------------------------------------------

@pytest.mark.asyncio
async def test_list_records_no_profile():
    fake = Fake(mentors=[])
    res = await service.list_records(PARTNER, fake, _USER)
    assert res == {"records": [], "profileFound": False}


@pytest.mark.asyncio
async def test_list_records_maps_columns():
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"managedPartners": [
            {"id": "P1", "name": "Acme", "partnershipStatus": "Active",
             "partnerCompanyName": "Acme Co", "primaryPartnercontactName": "Pat",
             "primaryPartnercontactId": "c1", "partnershipStartDate": "2026-01-15",
             "createdAt": "2026-01-02 00:00:00"},
        ]},
    )
    res = await service.list_records(PARTNER, fake, _USER)
    assert res["profileFound"] is True
    row = res["records"][0]
    assert row["id"] == "P1" and row["name"] == "Acme"
    assert row["status"] == "Active" and row["company"] == "Acme Co"
    # trailing date column (Start Date) + primary-contact id for the pop-up link
    assert row["startDate"] == "2026-01-15"
    assert row["contact"] == "Pat" and row["contactId"] == "c1"


@pytest.mark.asyncio
async def test_mentor_list_maps_next_session_and_start_inline():
    # Mentor grid lays both date columns out inline (Next Session + Start Date),
    # so no trailing date column is added.
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"engagements1": [
            {"id": "E1", "name": "Acme Eng", "engagementStatus": "Active",
             "engagementClientName": "Acme LLC", "clientOrganizationName": "Acme Co",
             "primaryEngagementContactName": "Pat", "primaryEngagementContactId": "c1",
             "nextSessionDateTime": "2026-08-04 15:30:00",
             "engagementStartDate": "2026-01-15", "createdAt": "2026-01-02 00:00:00"},
        ]},
    )
    res = await service.list_records(MENTOR, fake, _USER)
    row = res["records"][0]
    assert row["nextSession"] == "2026-08-04 15:30:00"
    assert row["startDate"] == "2026-01-15"
    assert row["company"] == "Acme Co" and row["client"] == "Acme LLC"
    assert row["contact"] == "Pat" and row["contactId"] == "c1"
    assert "created" not in row  # no trailing Created date column for mentor
    assert MENTOR.list_date_column is None


@pytest.mark.asyncio
async def test_mentor_list_includes_comentored_engagements():
    # Engagements where the mentor is a CO-mentor (additionalMentors reverse
    # link "engagements") are merged into the list, deduped against the ones
    # they're the assigned mentor of.
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={
            "engagements1": [
                {"id": "E1", "name": "Mine", "engagementStatus": "Active",
                 "createdAt": "2026-01-03"},
            ],
            "engagements": [
                {"id": "E2", "name": "Co-mentored", "engagementStatus": "Active",
                 "createdAt": "2026-01-04"},
                {"id": "E1", "name": "Mine", "engagementStatus": "Active",
                 "createdAt": "2026-01-03"},  # also assigned — must not duplicate
            ],
        },
    )
    res = await service.list_records(MENTOR, fake, _USER)
    ids = [r["id"] for r in res["records"]]
    assert sorted(ids) == ["E1", "E2"]
    assert len(ids) == 2  # deduped


@pytest.mark.asyncio
async def test_partner_list_reads_only_owned_link():
    # No co-mentor concept outside the mentor domain: only managedPartners is read.
    class Recording(Fake):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.related_calls = []

        async def list_related(self, entity, record_id, link, **kw):
            self.related_calls.append(link)
            return await super().list_related(entity, record_id, link, **kw)

    fake = Recording(mentors=[{"id": "p9", "assignedUserId": "u1"}])
    await service.list_records(PARTNER, fake, _USER)
    assert fake.related_calls == ["managedPartners"]


@pytest.mark.asyncio
async def test_mentor_list_includes_all_statuses():
    # The grid loads every engagement (any status); the UI's status filter narrows.
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"engagements1": [
            {"id": "E1", "name": "Active one", "engagementStatus": "Active", "createdAt": "2026-01-03"},
            {"id": "E2", "name": "Done one", "engagementStatus": "Completed", "createdAt": "2026-01-04"},
            {"id": "E3", "name": "Pending one", "engagementStatus": "Pending Acceptance", "createdAt": "2026-01-05"},
        ]},
    )
    res = await service.list_records(MENTOR, fake, _USER)
    ids = {r["id"] for r in res["records"]}
    assert ids == {"E1", "E2", "E3"}  # nothing excluded


@pytest.mark.asyncio
async def test_mentor_list_company_falls_back_to_profile_linked_company():
    # Intake-created engagements carry the Account on CClientProfile.linkedCompany
    # only (CEngagement.clientOrganization is null — the prod Agape case), so the
    # company is resolved through the client profile.
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"engagements1": [
            {"id": "E1", "name": "Agape — Intake", "engagementStatus": "Active",
             "engagementClientId": "cp1", "engagementClientName": "Agape W8loss",
             "createdAt": "2026-01-03"},
        ]},
        records={("CClientProfile", "cp1"):
                 {"linkedCompanyId": "a1", "linkedCompanyName": "Agape W8loss"}},
    )
    res = await service.list_records(MENTOR, fake, _USER)
    row = res["records"][0]
    assert row["company"] == "Agape W8loss"
    # the company pop-up aggregate carries the resolved Account too
    peek = {p["entity"]: p["id"] for p in row["companyPeek"]}
    assert peek == {"Account": "a1", "CClientProfile": "cp1"}


@pytest.mark.asyncio
async def test_company_fallback_degrades_when_profile_unreadable():
    class Forbidden(Fake):
        async def get(self, entity, record_id, select=None):
            if entity == "CClientProfile":
                raise EspoError("HTTP 403: forbidden")
            return await super().get(entity, record_id, select)

    fake = Forbidden(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"engagements1": [
            {"id": "E1", "name": "Agape — Intake", "engagementStatus": "Active",
             "engagementClientId": "cp1", "createdAt": "2026-01-03"},
        ]},
    )
    res = await service.list_records(MENTOR, fake, _USER)  # must not raise
    assert res["records"][0]["company"] is None


# --- get_detail ------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_detail_assembles_partner():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {
            "name": "Acme", "partnershipStatus": "Active",
            "partnerCompanyName": "Acme Co", "partnerCompanyId": "acct1",
            "primaryPartnercontactId": "cprimary", "partnerNotes": "<p>key relationship</p>"}},
        related={
            "contacts": [{"id": "c1", "name": "Pat", "emailAddress": "pat@x.org"}],
            "sessions": [{"id": "s1", "name": "Kickoff", "status": "Held",
                          "dateStart": "2026-02-01 10:00:00", "sessionNotes": "<p>went well</p>"}],
            # attendees are read via the sessionAttendees relationship link
            "sessionAttendees": [{"id": "c1", "name": "Pat"}, {"id": "c9", "name": "Dana"}],
        },
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert d["name"] == "Acme"
    # curated Overview facts (in config order), grouped into sections, with the
    # company linkable to a peek
    status = next(i for i in d["overview"] if i["label"] == "Partnership status")
    assert status == {"label": "Partnership status", "value": "Active",
                      "type": "badge", "block": False, "section": "key"}
    # single "Company" link aggregates the Account + the partner profile (parent)
    company = next(i for i in d["overview"] if i["label"] == "Company")
    assert company["value"] == "Acme Co"
    assert company["link"]["aggregate"] == [
        {"entity": "Account", "id": "acct1"},
        {"entity": "CPartnerProfile", "id": "P1"},
    ]
    # aggregated note feed carries each session's notes + attendees, stamped with time
    assert d["noteFeed"][0]["notes"] == "<p>went well</p>"
    assert d["noteFeed"][0]["dateStart"] == "2026-02-01 10:00:00"
    assert d["noteFeed"][0]["attendees"] == ["Pat", "Dana"]
    assert d["contacts"][0]["email"] == "pat@x.org"
    assert d["primaryContactId"] == "cprimary"
    assert d["sessions"][0]["status"] == "Held"
    # the same attendee names feed the Sessions grid's Participants column
    assert d["sessions"][0]["participants"] == ["Pat", "Dana"]
    # overall (partner-level) notes surface above the per-session feed
    assert d["overallNotes"] == {"label": "Partner Notes", "value": "<p>key relationship</p>", "type": "html"}
    # the only session is in the past => nothing scheduled ahead
    assert d["nextSession"] is None
    assert "coMentors" not in d  # partner domain has no co-mentors


@pytest.mark.asyncio
async def test_get_detail_next_session_is_soonest_upcoming():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {"name": "Acme"}},
        related={"sessions": [
            {"id": "past", "dateStart": "2020-01-01 09:00:00"},
            {"id": "soon", "name": "Check-in", "sessionType": "Partner Session",
             "dateStart": "2099-03-01 09:00:00", "videoMeetingLink": "https://meet.example/x"},
            {"id": "later", "dateStart": "2099-09-01 09:00:00"},
        ]},
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert d["nextSession"]["id"] == "soon"  # earliest still in the future
    assert d["nextSession"]["name"] == "Check-in"
    assert d["nextSession"]["videoMeetingLink"] == "https://meet.example/x"


@pytest.mark.asyncio
async def test_get_detail_note_feed_sorted_desc():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {"name": "Acme"}},
        related={"sessions": [
            {"id": "old", "dateStart": "2026-01-01 09:00:00", "sessionNotes": "first"},
            {"id": "new", "dateStart": "2026-03-01 09:00:00", "sessionNotes": "latest"},
        ]},
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert [n["id"] for n in d["noteFeed"]] == ["new", "old"]  # most recent first


@pytest.mark.asyncio
async def test_get_detail_company_falls_back_to_profile_linked_company():
    # Same fallback on the detail read: the Overview's aggregated Company link
    # gains the Account resolved through the client profile.
    fake = Fake(
        records={
            ("CEngagement", "E1"): {"name": "Agape — Intake", "engagementStatus": "Active",
                                    "engagementClientId": "cp1",
                                    "engagementClientName": "Agape W8loss"},
            ("CClientProfile", "cp1"): {"linkedCompanyId": "a1",
                                        "linkedCompanyName": "Agape W8loss"},
        },
    )
    d = await service.get_detail(MENTOR, fake, "E1")
    company = next(i for i in d["overview"] if i["label"] == "Company")
    assert company["value"] == "Agape W8loss"
    pairs = {p["entity"]: p["id"] for p in company["link"]["aggregate"]}
    assert pairs == {"Account": "a1", "CClientProfile": "cp1"}


@pytest.mark.asyncio
async def test_get_detail_overview_shows_assigned_mentor_above_cadence():
    # The assigned mentor is a key fact on the Overview rail, right above the
    # meeting cadence, linked to a CMentorProfile pop-up (Doug's ruling).
    fake = Fake(records={("CEngagement", "E1"): {
        "name": "Agape — Intake", "engagementStatus": "Active",
        "mentorProfileId": "mp1", "mentorProfileName": "Douglas Bower",
        "meetingCadence": "Weekly",
    }})
    d = await service.get_detail(MENTOR, fake, "E1")
    labels = [i["label"] for i in d["overview"]]
    assert labels.index("Assigned mentor") < labels.index("Meeting cadence")
    mentor = next(i for i in d["overview"] if i["label"] == "Assigned mentor")
    assert mentor["value"] == "Douglas Bower" and mentor["section"] == "key"
    assert mentor["link"] == {"entity": "CMentorProfile", "id": "mp1"}
    # its pop-up entity is allowlisted for the peek endpoint
    assert "CMentorProfile" in service.PEEK_FIELDS


@pytest.mark.asyncio
async def test_peek_allowlists_entities_and_drops_empties():
    fake = Fake(records={("Contact", "c1"): {
        "name": "Pat Lee", "emailAddress": "pat@x.org", "title": "COO", "phoneNumber": ""}})
    res = await service.peek(fake, "Contact", "c1")
    assert res["name"] == "Pat Lee"
    labels = {f["label"]: f["value"] for f in res["fields"]}
    assert labels["Email"] == "pat@x.org" and labels["Title"] == "COO"
    assert "Phone" not in labels  # empty value dropped

    with pytest.raises(service.SessionError):
        await service.peek(fake, "User", "u1")  # not on the allowlist


@pytest.mark.asyncio
async def test_peek_forbidden_read_degrades_to_restricted():
    """A 403 from the CRM (the user lacks read ACL on, e.g., the client's
    CClientProfile) must not become a 502 — peek returns a ``restricted`` marker
    so the pop-up shows a friendly note and the aggregate still renders the rest."""
    from core.espo import EspoError

    class Forbidden(Fake):
        async def get(self, entity, record_id, select=None):
            raise EspoError(
                f"get {entity}/{record_id} failed: HTTP 403 Forbidden"
            )

    res = await service.peek(Forbidden(), "CClientProfile", "cp1")
    assert res["restricted"] is True
    assert res["fields"] == [] and res["name"] is None


@pytest.mark.asyncio
async def test_peek_non_forbidden_error_propagates():
    """A non-403 CRM failure is still surfaced (mapped to 502 by the router)."""
    from core.espo import EspoError

    class Broken(Fake):
        async def get(self, entity, record_id, select=None):
            raise EspoError("get failed: HTTP 500 boom")

    with pytest.raises(EspoError):
        await service.peek(Broken(), "CClientProfile", "cp1")


@pytest.mark.asyncio
async def test_peek_contact_builds_copy_card_and_address():
    fake = Fake(records={("Contact", "c1"): {
        "name": "Pat Lee", "emailAddress": "pat@x.org", "phoneNumber": "+12165550142",
        "addressStreet": "1 Main St", "addressCity": "Cleveland",
        "addressState": "OH", "addressPostalCode": "44113"}})
    res = await service.peek(fake, "Contact", "c1")
    # paste-ready card: name, full address, email, phone (US display format)
    assert res["copyText"] == "Pat Lee\n1 Main St\nCleveland, OH 44113\npat@x.org\n(216)-555-0142"
    # a combined Address field is shown in the pop-up
    assert {"label": "Address", "value": "1 Main St\nCleveland, OH 44113", "type": "longtext"} in res["fields"]


@pytest.mark.asyncio
async def test_get_detail_includes_comentors_for_mentor():
    fake = Fake(
        records={("CEngagement", "E1"): {"name": "Eng", "engagementStatus": "Active"}},
        related={"additionalMentors": [
            {"id": "m2", "name": "Co Mentor", "contactRecordId": "ct9"},
            {"id": "m3", "name": "No Contact"},  # no linked Contact => not linkable
        ]},
    )
    d = await service.get_detail(MENTOR, fake, "E1")
    assert d["supportsComentor"] is True
    # each CBM contact carries its linked Contact id so the Overview can link to
    # the contact-info pop-up (None when no Contact is linked).
    assert d["coMentors"] == [
        {"id": "m2", "name": "Co Mentor", "contactId": "ct9"},
        {"id": "m3", "name": "No Contact", "contactId": None},
    ]


# --- Details tab -----------------------------------------------------------

def test_details_label_humanizes_field_names():
    assert details._label("partnershipStartDate") == "Partnership Start Date"
    assert details._label("cIndustrySector") == "Industry Sector"
    assert details._label("cBMValueProvided") == "CBM Value Provided"


def test_details_field_spec_filters_and_flags():
    spec = {f["name"]: f for f in details._field_spec({
        "name": {"type": "personName"},              # composite name — excluded
        "title": {"type": "varchar"},                # editable
        "industrySector": {"type": "enum", "options": ["A", "B", ""]},  # blank dropped
        "assignedUser": {"type": "link"},            # link — excluded
        "createdAt": {"type": "datetime"},           # system — excluded
        "emailAddressIsInvalid": {"type": "bool"},   # noise suffix — excluded
        "totalContribution": {"type": "currency"},   # shown but read-only
    })}
    assert spec["title"]["editable"] is True
    assert spec["industrySector"]["options"] == ["A", "B"]
    assert spec["totalContribution"]["editable"] is False
    for gone in ("name", "assignedUser", "createdAt", "emailAddressIsInvalid"):
        assert gone not in spec


def test_details_field_spec_hides_engagement_description():
    """CEngagement.description carries Client Administration's internal process
    notes (the /assignments Notes column) — never rendered or editable here."""
    fields = {"description": {"type": "text"}, "meetingCadence": {"type": "varchar"}}
    eng = [f["name"] for f in details._field_spec(fields, "CEngagement")]
    assert eng == ["meetingCadence"]
    # Only CEngagement hides it; other entities keep their description field.
    acct = [f["name"] for f in details._field_spec(fields, "Account")]
    assert "description" in acct


@pytest.mark.asyncio
async def test_save_details_drops_engagement_description():
    """A smuggled description change on CEngagement is dropped by the whitelist."""
    fake = Fake(meta_fields={
        "description": {"type": "text"},
        "meetingCadence": {"type": "varchar"},
    })
    res = await details.save_details(
        fake, "CEngagement", "e1",
        {"meetingCadence": "Weekly", "description": "smuggled"},
    )
    assert fake.updates == [("CEngagement", "e1", {"meetingCadence": "Weekly"})]
    assert res["saved"] == ["meetingCadence"]


@pytest.mark.asyncio
async def test_save_details_whitelists_and_drops_drifted_enum():
    fake = Fake(meta_fields={
        "title": {"type": "varchar"},
        "industrySector": {"type": "enum", "options": ["A", "B"]},
    })
    res = await details.save_details(
        fake, "Account", "acct1",
        {"title": "COO", "industrySector": "Z", "bogus": "x", "id": "hack"},
    )
    # non-editable/unknown keys dropped, drifted enum "Z" dropped, title kept
    assert fake.updates == [("Account", "acct1", {"title": "COO"})]
    assert res["saved"] == ["title"]


@pytest.mark.asyncio
async def test_save_details_normalizes_phone_to_e164():
    """EspoCRM only accepts E.164 phones — a human-formatted entry on the
    Company/Contact edit forms must not 400 the whole save (Doug's live report:
    'Phone Number has a value the CRM does not accept' on a company update)."""
    fake = Fake(meta_fields={
        "phoneNumber": {"type": "phone"},
        "name": {"type": "varchar"},
    })
    res = await details.save_details(
        fake, "Account", "acct1",
        {"phoneNumber": "(216) 555-1234", "name": "Acme"},
    )
    assert fake.updates == [("Account", "acct1", {"phoneNumber": "+12165551234", "name": "Acme"})]
    assert sorted(res["saved"]) == ["name", "phoneNumber"]


@pytest.mark.asyncio
async def test_save_details_phone_blank_clears_and_e164_passes_through():
    fake = Fake(meta_fields={"phoneNumber": {"type": "phone"}})
    await details.save_details(fake, "Account", "a1", {"phoneNumber": ""})
    await details.save_details(fake, "Account", "a2", {"phoneNumber": "+12165551234"})
    assert fake.updates == [
        ("Account", "a1", {"phoneNumber": ""}),        # clearing stays a clear
        ("Account", "a2", {"phoneNumber": "+12165551234"}),  # already E.164 untouched
    ]


@pytest.mark.asyncio
async def test_build_details_splits_sections_and_contacts():
    fake = Fake(
        records={
            ("CPartnerProfile", "P1"): {"name": "Acme", "partnerCompanyId": "acct1"},
            ("Account", "acct1"): {"name": "Acme Co"},
        },
        related={"contacts": [{"id": "c1", "name": "Pat", "title": "COO"}]},
        meta_fields={"title": {"type": "varchar"}, "website": {"type": "url"}},
    )
    d = await details.build_details(PARTNER, fake, "P1")
    # org sections carry a kind: the parent record (summary strip) vs. org cards.
    kinds = [(s["title"], s["entity"], s["kind"]) for s in d["sections"]]
    assert kinds == [("Partnership", "CPartnerProfile", "parent"), ("Company", "Account", "org")]
    # related contacts are their own list (one table), not sections.
    assert [c["name"] for c in d["contacts"]] == ["Pat"]
    assert d["contacts"][0]["entity"] == "Contact"
    # the Contact field spec ships for the create-new-contact form.
    assert [f["name"] for f in d["contactSpec"]] == ["title", "website"]
    # no ACL restrictions => everything editable; partner domain has no CBM card.
    assert all(s["editable"] for s in d["sections"]) and d["contacts"][0]["editable"]
    assert "cbmContacts" not in d


@pytest.mark.asyncio
async def test_build_details_mentor_cbm_contacts():
    """Mentor domain: the CBM Contacts card = the assigned mentor
    (CEngagement.mentorProfile) + co-mentors (additionalMentors), deduped, each
    resolved through the profile's linked Contact (contactRecord)."""
    fake = Fake(
        records={
            ("CEngagement", "E1"): {
                "name": "Eng", "clientOrganizationId": "acct1", "engagementClientId": "cp1",
                "mentorProfileId": "m1", "mentorProfileName": "Mentor One",
            },
            ("Account", "acct1"): {"name": "Acme Co"},
            ("CClientProfile", "cp1"): {"name": "Acme profile"},
            ("CMentorProfile", "m1"): {"name": "Mentor One", "contactRecordId": "ct1"},
            ("Contact", "ct1"): {"name": "Mentor One", "title": "Mentor"},
        },
        related={
            "engagementContacts": [{"id": "c1", "name": "Pat"}],
            "additionalMentors": [
                {"id": "m2", "name": "Co M", "contactRecordId": "ct2"},
                {"id": "m1", "name": "Mentor One"},  # also the primary -> deduped
            ],
        },
        meta_fields={"title": {"type": "varchar"}},
    )
    d = await details.build_details(MENTOR, fake, "E1")
    assert [s["kind"] for s in d["sections"]] == ["parent", "org", "org"]
    rows = d["cbmContacts"]
    assert [(p["role"], p["profileId"], p["name"]) for p in rows] == [
        ("Mentor", "m1", "Mentor One"), ("Co-mentor", "m2", "Co M"),
    ]
    # the mentor's linked Contact came back as a full editable section
    assert rows[0]["contact"]["entity"] == "Contact"
    assert rows[0]["contact"]["values"]["title"] == "Mentor"


@pytest.mark.asyncio
async def test_search_contacts_shape_and_min_length():
    fake = Fake(contacts=[{"id": "c1", "name": "Pat K", "emailAddress": "p@x.com",
                           "phoneNumber": "+12165550100", "accountName": "Acme"}])
    assert await details.search_contacts(fake, " a ") == []  # under 2 chars: no CRM call
    assert fake.list_calls == []
    res = await details.search_contacts(fake, "Pat")
    assert res == [{"id": "c1", "name": "Pat K", "email": "p@x.com",
                    "phone": "+12165550100", "company": "Acme"}]
    _, kw = fake.list_calls[0]
    assert kw["where"] == [{"type": "contains", "attribute": "name", "value": "Pat"}]


@pytest.mark.asyncio
async def test_link_contact_relates_and_backfills_missing_company():
    fake = Fake(records={
        ("CEngagement", "E1"): {"clientOrganizationId": "acct1"},
        ("Contact", "c9"): {"accountId": None},
    })
    await details.link_contact(MENTOR, fake, "E1", "c9")
    assert fake.relates == [("CEngagement", "E1", "engagementContacts", "c9")]
    assert fake.updates == [("Contact", "c9", {"accountId": "acct1"})]


@pytest.mark.asyncio
async def test_link_contact_never_overwrites_existing_company():
    fake = Fake(records={
        ("CEngagement", "E1"): {"clientOrganizationId": "acct1"},
        ("Contact", "c9"): {"accountId": "other-co"},
    })
    await details.link_contact(MENTOR, fake, "E1", "c9")
    assert fake.relates == [("CEngagement", "E1", "engagementContacts", "c9")]
    assert fake.updates == []


@pytest.mark.asyncio
async def test_unlink_contact_unrelates_only():
    # remove = the relation only; the Contact record itself is never touched
    fake = Fake()
    await details.unlink_contact(MENTOR, fake, "E1", "c9")
    assert fake.unrelates == [("CEngagement", "E1", "engagementContacts", "c9")]
    assert fake.updates == []


@pytest.mark.asyncio
async def test_unlink_contact_uses_each_domains_link():
    fake = Fake()
    await details.unlink_contact(PARTNER, fake, "P1", "c9")
    assert fake.unrelates == [("CPartnerProfile", "P1", "contacts", "c9")]


@pytest.mark.asyncio
async def test_create_contact_whitelists_stamps_company_and_links():
    fake = Fake(
        records={("CEngagement", "E1"): {"clientOrganizationId": "acct1"}},
        meta_fields={
            "firstName": {"type": "varchar"}, "lastName": {"type": "varchar"},
            "cPreferredContactMethod": {"type": "enum", "options": ["Email"]},
        },
    )
    res = await details.create_contact(MENTOR, fake, "E1", {
        "firstName": "Pat", "lastName": "K",
        "cPreferredContactMethod": "Fax",  # drifted enum -> dropped, never 400s
        "bogus": "x",                      # not a Contact field -> dropped
    })
    entity, payload = fake.created[0]
    assert entity == "Contact"
    assert payload == {"firstName": "Pat", "lastName": "K", "accountId": "acct1"}
    # created AND linked in the same operation, via the real relation
    assert fake.relates == [("CEngagement", "E1", "engagementContacts", res["id"])]


@pytest.mark.asyncio
async def test_create_contact_requires_a_name():
    fake = Fake(meta_fields={"firstName": {"type": "varchar"}, "title": {"type": "varchar"}})
    with pytest.raises(service.SessionError):
        await details.create_contact(MENTOR, fake, "E1", {"title": "COO"})
    assert fake.created == []


@pytest.mark.asyncio
async def test_build_details_marks_readonly_when_user_cannot_edit():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {"name": "Acme", "partnerCompanyId": "acct1"},
                 ("Account", "acct1"): {"name": "Acme Co"}},
        related={},
        meta_fields={"title": {"type": "varchar"}},
        acl={"Account": {"read": "all", "edit": "no"},          # can't edit companies
             "CPartnerProfile": {"read": "all", "edit": "all"}},  # can edit the profile
    )
    d = await details.build_details(PARTNER, fake, "P1", user_id="u1")
    by_entity = {s["entity"]: s for s in d["sections"]}
    assert by_entity["Account"]["editable"] is False
    assert by_entity["CPartnerProfile"]["editable"] is True


@pytest.mark.asyncio
async def test_build_details_own_level_checks_record_ownership():
    # edit:"own" — editable only on the record the user is assigned to. The
    # unowned Account (like crm-test's admin-created accounts) reads as read-only.
    fake = Fake(
        records={
            ("CPartnerProfile", "P1"): {"name": "Acme", "partnerCompanyId": "acct1", "assignedUserId": "u1"},
            ("Account", "acct1"): {"name": "Acme Co", "assignedUserId": None},
        },
        related={},
        meta_fields={"title": {"type": "varchar"}, "assignedUser": {"type": "link"}},
        acl={"Account": {"edit": "own"}, "CPartnerProfile": {"edit": "own"}},
    )
    d = await details.build_details(PARTNER, fake, "P1", user_id="u1")
    by_entity = {s["entity"]: s for s in d["sections"]}
    assert by_entity["Account"]["editable"] is False        # unassigned -> not owned
    assert by_entity["CPartnerProfile"]["editable"] is True  # assigned to u1


# --- create / update session ----------------------------------------------

@pytest.mark.asyncio
async def test_create_session_sets_parent_and_defaults_and_whitelists():
    fake = Fake()
    await service.create_session(
        PARTNER, fake, "P1",
        {"name": "Check-in", "sessionNotes": "<p>notes</p>", "id": "hack", "bogus": 1},
        ["c1", "c2"],
    )
    entity, payload = fake.created[0]
    assert entity == "CSession"
    assert payload["partnerSessionId"] == "P1"
    assert payload["sessionType"] == "Partner Session"  # domain default
    assert payload["status"] == "Scheduled"             # default
    assert payload["name"] == "Check-in" and payload["sessionNotes"] == "<p>notes</p>"
    assert "id" not in payload and "bogus" not in payload
    # attendees are attached via the relationship endpoint, not the create payload
    assert "sessionAttendeesIds" not in payload
    related = {(r[2], r[3]) for r in fake.relates}
    assert ("sessionAttendees", "c1") in related and ("sessionAttendees", "c2") in related


@pytest.mark.asyncio
async def test_create_session_keeps_explicit_type_and_status():
    fake = Fake()
    await service.create_session(
        MENTOR, fake, "E1", {"sessionType": "Other Session", "status": "Held"}, None
    )
    _, payload = fake.created[0]
    assert payload["sessionType"] == "Other Session" and payload["status"] == "Held"
    assert payload["engagementId"] == "E1"
    assert "sessionAttendeesIds" not in payload  # attendees=None => untouched


@pytest.mark.asyncio
async def test_create_session_stamps_owner_for_read_own():
    # The creating user is set as assignedUser (both shapes) so a read-own role
    # can still see the session they just made.
    fake = Fake()
    await service.create_session(MENTOR, fake, "E1", {"name": "S"}, None, owner_user_id="u1")
    _, payload = fake.created[0]
    assert payload["assignedUserId"] == "u1" and payload["assignedUsersIds"] == ["u1"]


@pytest.mark.asyncio
async def test_create_session_stamps_whole_mentor_team():
    # Mentor domain: every mentor on the engagement (assigned + co-mentors) is
    # stamped into assignedUsers so they ALL see the session under read=own.
    fake = Fake(
        records={
            ("CEngagement", "E1"): {"mentorProfileId": "mA"},
            ("CMentorProfile", "mA"): {"assignedUserId": "uA"},
        },
        related={"additionalMentors": [
            {"id": "m2", "assignedUserId": "u9"},
            {"id": "m3", "assignedUsersIds": ["u1"]},  # the creator — deduped
        ]},
    )
    await service.create_session(MENTOR, fake, "E1", {"name": "S"}, None, owner_user_id="u1")
    _, payload = fake.created[0]
    assert payload["assignedUserId"] == "u1"
    assert payload["assignedUsersIds"] == ["u1", "uA", "u9"]


@pytest.mark.asyncio
async def test_create_session_partner_domain_stamps_creator_only():
    # No co-mentor concept outside the mentor domain.
    fake = Fake(related={"additionalMentors": [{"id": "m2", "assignedUserId": "u9"}]})
    await service.create_session(PARTNER, fake, "P1", {"name": "S"}, None, owner_user_id="u1")
    _, payload = fake.created[0]
    assert payload["assignedUsersIds"] == ["u1"]


# --- first completed session activates the engagement -----------------------

def _eng_updates(fake):
    return [(rid, p) for e, rid, p in fake.updates if e == "CEngagement"]


@pytest.mark.asyncio
async def test_create_completed_session_activates_assigned_engagement():
    fake = Fake(records={("CEngagement", "E1"): {"engagementStatus": "Assigned"}})
    res = await service.create_session(MENTOR, fake, "E1", {"status": "Completed"}, None)
    assert _eng_updates(fake) == [("E1", {"engagementStatus": "Active"})]
    assert res["engagement"] == {"activated": True, "from": "Assigned", "to": "Active"}


@pytest.mark.asyncio
async def test_create_completed_session_activates_dormant_assignment():
    fake = Fake(records={("CEngagement", "E1"): {"engagementStatus": "Assignment Dormant"}})
    res = await service.create_session(MENTOR, fake, "E1", {"status": "Completed"}, None)
    assert _eng_updates(fake) == [("E1", {"engagementStatus": "Active"})]
    assert res["engagement"]["from"] == "Assignment Dormant"


@pytest.mark.asyncio
async def test_create_completed_session_leaves_other_engagement_statuses():
    # Already Active, or a status a staffer set deliberately => untouched.
    for status in ("Active", "On-Hold", "Completed", "Dormant"):
        fake = Fake(records={("CEngagement", "E1"): {"engagementStatus": status}})
        res = await service.create_session(MENTOR, fake, "E1", {"status": "Completed"}, None)
        assert _eng_updates(fake) == []
        assert "engagement" not in res


@pytest.mark.asyncio
async def test_create_scheduled_session_never_touches_engagement_status():
    fake = Fake(records={("CEngagement", "E1"): {"engagementStatus": "Assigned"}})
    res = await service.create_session(MENTOR, fake, "E1", {"status": "Scheduled"}, None)
    assert _eng_updates(fake) == []
    assert "engagement" not in res


@pytest.mark.asyncio
async def test_create_completed_session_partner_domain_no_engagement_rule():
    # The rule is mentor-domain only — a partner parent has no engagement lifecycle.
    fake = Fake(records={("CPartnerProfile", "P1"): {}})
    res = await service.create_session(PARTNER, fake, "P1", {"status": "Completed"}, None)
    assert _eng_updates(fake) == []
    assert "engagement" not in res


@pytest.mark.asyncio
async def test_update_to_completed_activates_assigned_engagement():
    fake = Fake(records={
        ("CSession", "s1"): {"engagementId": "E1"},
        ("CEngagement", "E1"): {"engagementStatus": "Assigned"},
    })
    res = await service.update_session(MENTOR, fake, "s1", {"status": "Completed"}, None)
    assert _eng_updates(fake) == [("E1", {"engagementStatus": "Active"})]
    assert res["engagement"]["activated"] is True


@pytest.mark.asyncio
async def test_update_without_status_change_never_touches_engagement():
    # A notes-only edit to an already-Completed session (status not in the diffed
    # payload) must not re-activate a deliberately parked engagement.
    fake = Fake(records={
        ("CSession", "s1"): {"engagementId": "E1", "status": "Completed"},
        ("CEngagement", "E1"): {"engagementStatus": "Assignment Dormant"},
    })
    res = await service.update_session(MENTOR, fake, "s1", {"sessionNotes": "<p>x</p>"}, None)
    assert _eng_updates(fake) == []
    assert "engagement" not in res


@pytest.mark.asyncio
async def test_activation_failure_never_fails_the_session_save():
    class Failing(Fake):
        async def update(self, entity, record_id, payload):
            if entity == "CEngagement":
                raise EspoError("forbidden")
            return await super().update(entity, record_id, payload)

    fake = Failing(records={("CEngagement", "E1"): {"engagementStatus": "Assigned"}})
    res = await service.create_session(MENTOR, fake, "E1", {"status": "Completed"}, None)
    assert res["id"]  # the session itself saved
    assert res["engagement"]["activated"] is False
    assert "forbidden" in res["engagement"]["error"]


@pytest.mark.asyncio
async def test_update_session_whitelists_fields_and_syncs_attendees():
    # existing attendee c1; user submits {c1, c3} -> relate c3, unrelate nothing;
    # c2 (not present, not submitted) untouched.
    fake = Fake(records={("CSession", "s1"): {"name": "old"}},
                related={"sessionAttendees": [{"id": "c1"}]})
    await service.update_session(MENTOR, fake, "s1", {"name": "new", "hack": 1}, ["c1", "c3"])
    entity, rid, payload = fake.updates[0]
    assert (entity, rid) == ("CSession", "s1")
    assert payload["name"] == "new" and "hack" not in payload
    assert "sessionAttendeesIds" not in payload            # synced via relate, not payload
    assert ("CSession", "s1", "sessionAttendees", "c3") in fake.relates  # added
    assert not fake.unrelates                              # nothing removed


@pytest.mark.asyncio
async def test_update_session_unrelates_removed_attendees():
    fake = Fake(records={("CSession", "s1"): {"name": "s"}},
                related={"sessionAttendees": [{"id": "c1"}, {"id": "c2"}]})
    await service.update_session(MENTOR, fake, "s1", {}, ["c1"])   # drop c2
    assert ("CSession", "s1", "sessionAttendees", "c2") in fake.unrelates
    assert not fake.relates                                # c1 already present


@pytest.mark.asyncio
async def test_update_drops_drifted_enum_but_keeps_valid_fields():
    # A stored sessionType value that's no longer a live option must be omitted
    # (not sent) rather than 400 the whole update; other fields still save.
    meta = {"sessionType": {"options": ["Client Session", "Follow-up"]}}
    fake = Fake(records={("CSession", "s1"): {}}, meta_fields=meta)
    await service.update_session(
        MENTOR, fake, "s1", {"sessionType": "In-Person", "name": "Kickoff"}, None
    )
    _, _, payload = fake.updates[0]
    assert "sessionType" not in payload      # drifted value dropped, not sent
    assert payload["name"] == "Kickoff"      # valid field still updated


@pytest.mark.asyncio
async def test_multienum_keeps_only_valid_values():
    meta = {"meetingType": {"options": ["Virtual", "Phone"]}}
    fake = Fake(records={("CSession", "s1"): {}}, meta_fields=meta)
    await service.update_session(
        MENTOR, fake, "s1", {"meetingType": ["Virtual", "Carrier Pigeon"]}, None
    )
    _, _, payload = fake.updates[0]
    assert payload["meetingType"] == ["Virtual"]


@pytest.mark.asyncio
async def test_field_required_reads_crm_metadata():
    # Only fields the CRM marks required (and are editable) are returned.
    meta = {
        "dateStart": {"type": "datetime", "required": True},
        "name": {"type": "varchar", "required": True},
        "status": {"type": "enum"},          # not required
        "notAField": {"required": True},      # not in the editable set
    }
    fake = Fake(meta_fields=meta)
    required = await service.field_required(fake)
    assert set(required) == {"dateStart", "name"}


@pytest.mark.asyncio
async def test_sanitizer_fails_open_when_options_unavailable():
    # No metadata options => can't verify => keep the value (never drop unverified).
    fake = Fake(records={("CSession", "s1"): {}})  # meta_fields={} => no options
    await service.update_session(MENTOR, fake, "s1", {"sessionType": "Anything"}, None)
    _, _, payload = fake.updates[0]
    assert payload["sessionType"] == "Anything"


@pytest.mark.asyncio
async def test_get_session_exposes_attendees():
    fake = Fake(records={("CSession", "s1"): {"name": "x"}},
                related={"sessionAttendees": [{"id": "c1", "name": "Pat"}, {"id": "c2", "name": "Dana"}]})
    rec = await service.get_session(fake, "s1")
    assert rec["attendees"] == ["c1", "c2"]           # ids for the editor picker
    assert rec["attendeeNames"] == ["Pat", "Dana"]    # names for the read-only view


@pytest.mark.asyncio
async def test_add_comentor_relates_and_stamps_assigned_users():
    # The co-mentor's login User is added to CEngagement.assignedUsers — the
    # Mentor Role reads engagements at "own" (= membership in assignedUsers), so
    # without the stamp the engagement never shows in the co-mentor's list.
    fake = Fake(records={
        ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
        ("CEngagement", "E1"): {"assignedUsersIds": ["u1"]},
    })
    res = await service.add_comentor(fake, "E1", "m2")
    assert fake.relates == [("CEngagement", "E1", "additionalMentors", "m2")]
    assert ("CEngagement", "E1", {"assignedUsersIds": ["u1", "u9"]}) in fake.updates
    assert "warning" not in res


@pytest.mark.asyncio
async def test_add_comentor_skips_stamp_when_already_assigned():
    fake = Fake(records={
        ("CMentorProfile", "m2"): {"assignedUsersIds": ["u9"]},  # collaborators shape
        ("CEngagement", "E1"): {"assignedUsersIds": ["u1", "u9"]},
    })
    res = await service.add_comentor(fake, "E1", "m2")
    assert fake.updates == []
    assert "warning" not in res


@pytest.mark.asyncio
async def test_add_comentor_warns_when_profile_has_no_user():
    fake = Fake(records={("CMentorProfile", "m2"): {}})
    res = await service.add_comentor(fake, "E1", "m2")
    assert fake.relates == [("CEngagement", "E1", "additionalMentors", "m2")]
    assert fake.updates == []
    assert "no linked login user" in res["warning"]


@pytest.mark.asyncio
async def test_add_comentor_warns_when_stamp_rejected():
    # The relate stands; a 403 on the assignedUsers write (assignment permission)
    # comes back as a readable warning instead of failing the add.
    class NoAssign(Fake):
        async def update(self, entity, record_id, payload):
            raise EspoError("HTTP 403: Assignment failure")

    fake = NoAssign(records={
        ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
        ("CEngagement", "E1"): {"assignedUsersIds": ["u1"]},
    })
    res = await service.add_comentor(fake, "E1", "m2")
    assert fake.relates == [("CEngagement", "E1", "additionalMentors", "m2")]
    assert "could not be given access" in res["warning"]


@pytest.mark.asyncio
async def test_add_comentor_backfills_existing_sessions():
    # The co-mentor must see the engagement's session HISTORY, not just new
    # sessions — their User is stamped onto every existing session.
    fake = Fake(
        records={
            ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
            ("CEngagement", "E1"): {"assignedUsersIds": ["u1"]},
        },
        related={"engagementSessions": [
            {"id": "s1", "assignedUsersIds": ["u1"]},
            {"id": "s2", "assignedUsersIds": ["u1", "u9"]},  # already stamped
        ]},
    )
    res = await service.add_comentor(fake, "E1", "m2")
    assert ("CSession", "s1", {"assignedUsersIds": ["u1", "u9"]}) in fake.updates
    assert [u for u in fake.updates if u[0] == "CSession"] == [
        ("CSession", "s1", {"assignedUsersIds": ["u1", "u9"]})
    ]  # s2 untouched
    assert "warning" not in res


@pytest.mark.asyncio
async def test_add_comentor_session_stamp_failure_skips_and_continues():
    # Under edit=own the acting mentor may not be able to stamp a session
    # someone else owns — that session is skipped, the rest still get stamped.
    class Flaky(Fake):
        async def update(self, entity, record_id, payload):
            if (entity, record_id) == ("CSession", "s1"):
                raise EspoError("HTTP 403: forbidden")
            return await super().update(entity, record_id, payload)

    fake = Flaky(
        records={
            ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
            ("CEngagement", "E1"): {"assignedUsersIds": ["u1"]},
        },
        related={"engagementSessions": [
            {"id": "s1", "assignedUsersIds": []},
            {"id": "s2", "assignedUsersIds": []},
        ]},
    )
    res = await service.add_comentor(fake, "E1", "m2")
    assert ("CSession", "s2", {"assignedUsersIds": ["u9"]}) in fake.updates
    assert "warning" not in res


@pytest.mark.asyncio
async def test_remove_comentor_unstamps_sessions_except_their_own():
    fake = Fake(
        records={
            ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
            ("CMentorProfile", "mA"): {"assignedUserId": "uA"},
            ("CEngagement", "E1"): {"mentorProfileId": "mA",
                                    "assignedUsersIds": ["uA", "u9"]},
        },
        related={
            "additionalMentors": [],
            "engagementSessions": [
                {"id": "s1", "assignedUserId": "uA", "assignedUsersIds": ["uA", "u9"]},
                # s2 is the removed co-mentor's OWN session — stays theirs
                {"id": "s2", "assignedUserId": "u9", "assignedUsersIds": ["uA", "u9"]},
            ],
        },
    )
    await service.remove_comentor(fake, "E1", "m2")
    assert ("CSession", "s1", {"assignedUsersIds": ["uA"]}) in fake.updates
    assert not any(u[0] == "CSession" and u[1] == "s2" for u in fake.updates)


@pytest.mark.asyncio
async def test_remove_comentor_unrelates_and_unstamps_user():
    fake = Fake(
        records={
            ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
            ("CMentorProfile", "mA"): {"assignedUserId": "uA"},
            ("CEngagement", "E1"): {"mentorProfileId": "mA",
                                    "assignedUsersIds": ["uA", "u9"]},
        },
        related={"additionalMentors": []},  # no co-mentors remain after unrelate
    )
    await service.remove_comentor(fake, "E1", "m2")
    assert fake.unrelates == [("CEngagement", "E1", "additionalMentors", "m2")]
    assert ("CEngagement", "E1", {"assignedUsersIds": ["uA"]}) in fake.updates


@pytest.mark.asyncio
async def test_remove_comentor_keeps_assigned_mentors_user():
    # Removing a co-mentor whose User is ALSO the assigned mentor's must not
    # strip the assigned mentor's visibility.
    fake = Fake(records={
        ("CMentorProfile", "m2"): {"assignedUserId": "uA"},
        ("CMentorProfile", "mA"): {"assignedUserId": "uA"},
        ("CEngagement", "E1"): {"mentorProfileId": "mA", "assignedUsersIds": ["uA"]},
    })
    await service.remove_comentor(fake, "E1", "m2")
    assert fake.unrelates == [("CEngagement", "E1", "additionalMentors", "m2")]
    assert fake.updates == []


@pytest.mark.asyncio
async def test_remove_comentor_keeps_user_shared_with_remaining_comentor():
    fake = Fake(
        records={
            ("CMentorProfile", "m2"): {"assignedUserId": "u9"},
            ("CEngagement", "E1"): {"assignedUsersIds": ["u9"]},
        },
        related={"additionalMentors": [{"id": "m3", "assignedUserId": "u9"}]},
    )
    await service.remove_comentor(fake, "E1", "m2")
    assert fake.updates == []


@pytest.mark.asyncio
async def test_field_options_reads_live_enums_and_drops_blank():
    fake = Fake(meta_fields={
        "status": {"type": "enum", "options": ["Planned", "Held", "Not Held"]},
        "meetingType": {"type": "multiEnum", "options": ["", "In Person", "Virtual Video"]},
        "name": {"type": "varchar"},
    })
    opts = await service.field_options(fake)
    assert opts["status"] == ["Planned", "Held", "Not Held"]
    assert opts["meetingType"] == ["In Person", "Virtual Video"]  # blank dropped
    assert "name" not in opts


@pytest.mark.asyncio
async def test_field_options_includes_duration_presets():
    # The CRM's virtual duration field carries its preset choices (seconds ints)
    # in metadata options — served to the editor like the enum options.
    fake = Fake(meta_fields={
        "duration": {"type": "duration", "options": [300, 1800, 3600]},
    })
    opts = await service.field_options(fake)
    assert opts["duration"] == [300, 1800, 3600]


def test_duration_is_not_writable_but_date_end_is():
    # duration is notStorable in the CRM (dateEnd − dateStart): the editor sends
    # the recomputed dateEnd; a stray duration key must never reach the payload.
    payload = service._session_payload(
        {"duration": 3600, "dateEnd": "2026-07-10 15:00:00", "dateStart": "2026-07-10 14:00:00"}
    )
    assert "duration" not in payload
    assert payload["dateEnd"] == "2026-07-10 15:00:00"
    assert payload["dateStart"] == "2026-07-10 14:00:00"


# --- router ----------------------------------------------------------------

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorsessions/api/records").status_code == 401
        assert c.get("/partnersessions/api/session").status_code == 401


def test_wrong_team_403_names_team(monkeypatch):
    _as(monkeypatch, dict(_USER, isAdmin=False, teams=["Mentor Team"], roles=[]))
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/partnersessions/api/records")
    assert r.status_code == 403
    assert "Partner Management Team" in r.json()["detail"]


def test_team_member_passes(monkeypatch):
    _as(monkeypatch, dict(_USER, isAdmin=False, teams=["Partner Management Team"], roles=[]))

    async def fake_list(cfg, client, user):
        return {"records": [{"id": "P1", "name": "Acme"}], "profileFound": True}

    monkeypatch.setattr("sessions.service.list_records", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/partnersessions/api/records")
    assert r.status_code == 200 and r.json()["records"][0]["name"] == "Acme"


def test_record_page_serves_frontend_with_base_href(monkeypatch):
    # /{slug}/record/{id} is the dedicated record page: the shared frontend,
    # with a <base> so its relative assets resolve against /{slug}/.
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/record/abc123")
        assert r.status_code == 200
        assert '<base href="/mentorsessions/">' in r.text
        assert r.headers["cache-control"] == "no-store"
        r2 = c.get("/sponsorsessions/record/xyz")
        assert r2.status_code == 200
        assert '<base href="/sponsorsessions/">' in r2.text


def test_session_endpoint_reports_domain(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentorsessions/api/session").json()
    assert data["domain"] == "mentorsessions"
    assert data["supportsComentor"] is True
    assert data["defaultSessionType"] == "Client Session"
    # distinct empty-state text for profileFound=false (no linked CMentorProfile)
    assert "Assigned User" in data["noProfileMessage"]
    # phase-one common detail tabs (same for every domain)
    tabs = data["detailTabs"]
    assert [t["key"] for t in tabs] == [
        "overview", "details", "sessions", "communications", "documents",
    ]
    # All five tabs are built (Documents since DOC-MGMT Phase 1 — it gates on
    # docsEnabled client-side, not on a placeholder flag).
    assert not any("placeholder" in t for t in tabs)


def test_partner_has_no_comentor_endpoints(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_mentors(client):
        return []

    monkeypatch.setattr("sessions.service.mentor_options", fake_mentors)
    with TestClient(_app(monkeypatch)) as c:
        # /mentors is mentor-only: registered for mentor, absent for partner.
        assert c.get("/partnersessions/api/mentors").status_code == 404
        assert c.get("/mentorsessions/api/mentors").status_code == 200


def test_create_session_endpoint(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_create(cfg, client, parent_id, changes, attendees,
                          owner_user_id=None, settings=None, skip_calendar=False):
        return {"id": "s1", "parent": parent_id, "attendees": attendees,
                "owner": owner_user_id, "skipCal": skip_calendar, **changes}

    monkeypatch.setattr("sessions.service.create_session", fake_create)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/sponsorsessions/api/records/SP1/sessions",
                   json={"changes": {"name": "Visit"}, "attendees": ["c1"]})
        r2 = c.post("/sponsorsessions/api/records/SP1/sessions",
                    json={"changes": {"name": "Visit"}, "skipCalendar": True})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"] == "SP1" and body["attendees"] == ["c1"] and body["name"] == "Visit"
    assert body["skipCal"] is False  # default: the calendar hook runs as usual
    # skipCalendar=true (user declined the invite prompt) reaches the service
    assert r2.json()["skipCal"] is True


def test_contact_search_and_add_endpoints(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_search(client, q):
        return [{"id": "c1", "name": "Pat (" + q + ")"}]

    linked, created = [], []

    async def fake_link(cfg, client, parent_id, contact_id):
        linked.append((cfg.slug, parent_id, contact_id))

    async def fake_create(cfg, client, parent_id, changes):
        created.append((cfg.slug, parent_id, changes))
        return {"id": "new1"}

    monkeypatch.setattr("sessions.details.search_contacts", fake_search)
    monkeypatch.setattr("sessions.details.link_contact", fake_link)
    monkeypatch.setattr("sessions.details.create_contact", fake_create)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/contacts", params={"q": "Pat"})
        assert r.status_code == 200 and r.json()["contacts"][0]["name"] == "Pat (Pat)"
        r = c.post("/mentorsessions/api/records/E1/contacts", json={"contactId": "c9"})
        assert r.status_code == 200 and linked == [("mentorsessions", "E1", "c9")]
        r = c.post("/mentorsessions/api/records/E1/contacts", json={"changes": {"lastName": "K"}})
        assert r.status_code == 200 and r.json()["id"] == "new1"
        assert created == [("mentorsessions", "E1", {"lastName": "K"})]


def test_remove_contact_and_comentor_endpoints(monkeypatch):
    _as(monkeypatch, _USER)
    unlinked, removed = [], []

    async def fake_unlink(cfg, client, parent_id, contact_id):
        unlinked.append((cfg.slug, parent_id, contact_id))

    async def fake_remove(client, engagement_id, mentor_profile_id):
        removed.append((engagement_id, mentor_profile_id))
        return {"status": "ok"}

    monkeypatch.setattr("sessions.details.unlink_contact", fake_unlink)
    monkeypatch.setattr("sessions.service.remove_comentor", fake_remove)
    with TestClient(_app(monkeypatch)) as c:
        r = c.delete("/mentorsessions/api/records/E1/contacts/c9")
        assert r.status_code == 200 and unlinked == [("mentorsessions", "E1", "c9")]
        r = c.delete("/mentorsessions/api/records/E1/comentors/m2")
        assert r.status_code == 200 and removed == [("E1", "m2")]
        # co-mentor removal is mentor-only, like the add (no partner route; the
        # unmatched DELETE falls through to the static mount, hence 405 not 404)
        assert c.delete("/partnersessions/api/records/P1/comentors/m2").status_code in (404, 405)
        assert removed == [("E1", "m2")]  # nothing extra was removed


def test_contact_endpoints_require_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorsessions/api/contacts?q=x").status_code == 401
        assert c.post("/mentorsessions/api/records/E1/contacts", json={"contactId": "c1"}).status_code == 401
        assert c.delete("/mentorsessions/api/records/E1/contacts/c1").status_code == 401
        assert c.delete("/mentorsessions/api/records/E1/comentors/m1").status_code == 401


def test_expired_token_returns_401(monkeypatch):
    _as(monkeypatch, _USER)

    async def boom(cfg, client, user):
        raise EspoError("list CMentorProfile failed: HTTP 401 Unauthorized")

    monkeypatch.setattr("sessions.service.list_records", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/records")
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()


def test_other_crm_error_returns_502(monkeypatch):
    _as(monkeypatch, _USER)

    async def boom(cfg, client, user):
        raise EspoError("list failed: HTTP 500 Server Error")

    monkeypatch.setattr("sessions.service.list_records", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/records")
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_get_session_exposes_attendee_grid_details():
    # The session view's attendee grid (name/role/company/email/phone/status)
    # reads the richer related-contact rows; ids/names stay for the editor+feed.
    fake = Fake(
        records={("CSession", "s1"): {"name": "x"}},
        related={"sessionAttendees": [
            {"id": "c1", "name": "Pat", "emailAddress": "pat@acme.example",
             "phoneNumber": "(216) 555-0100", "accountName": "Acme", "accountId": "a1"},
            {"id": "c2", "name": "Dana"},
        ]},
    )
    rec = await service.get_session(fake, "s1")
    assert rec["attendeeDetails"][0] == {
        "id": "c1", "name": "Pat", "email": "pat@acme.example",
        "phone": "(216) 555-0100", "companyName": "Acme", "companyId": "a1",
    }
    assert rec["attendeeDetails"][1]["email"] is None
    assert rec["attendees"] == ["c1", "c2"]
    assert rec["attendeeNames"] == ["Pat", "Dana"]


@pytest.mark.asyncio
async def test_get_session_transcript_feature_detected():
    # §12.5: the transcript column is feature-gated on live CRM metadata —
    # absent field => flag False (the view renders no transcript zone at all).
    fake = Fake(records={("CSession", "s1"): {"name": "x"}})
    rec = await service.get_session(fake, "s1")
    assert rec["transcriptFieldExists"] is False

    fake = Fake(
        records={("CSession", "s1"): {"name": "x", "sessionTranscription": "<p>hi</p>"}},
        meta_fields={"sessionTranscription": {"type": "wysiwyg"}},
    )
    rec = await service.get_session(fake, "s1")
    assert rec["transcriptFieldExists"] is True
    assert rec["sessionTranscription"] == "<p>hi</p>"


@pytest.mark.asyncio
async def test_field_spec_live_gates_the_transcript_field():
    # Serving the transcript editor box while the CRM lacks the column would
    # make every save fail — the spec includes it only once the field exists.
    fake = Fake()
    names = [f["name"] for f in await service.field_spec_live(fake)]
    assert "sessionTranscription" not in names
    assert "sessionNotes" in names

    fake = Fake(meta_fields={"sessionTranscription": {"type": "wysiwyg"}})
    names = [f["name"] for f in await service.field_spec_live(fake)]
    assert "sessionTranscription" in names


@pytest.mark.asyncio
async def test_cbm_contacts_resolve_manager_and_comentors():
    # The default-invitee set: the engagement's assigned mentor leads
    # (resolved via contactRecordId), a co-mentor without a contact link
    # resolves through the cbmEmail fallback (the live-data shape that made
    # invitees come up empty), an unresolvable profile is skipped, and a
    # duplicate collapses to one row.
    fake = Fake(
        records={
            ("CEngagement", "E1"): {"name": "Eng", "mentorProfileId": "m1"},
            ("CMentorProfile", "m1"): {"name": "Doug Bower", "contactRecordId": "cDoug"},
        },
        related={
            "engagementContacts": [],
            "engagementSessions": [],
            "additionalMentors": [
                {"id": "m2", "name": "Jane Doe",
                 "cbmEmail": "jane@cbmentors.org", "contactRecordId": None},
                {"id": "m3", "name": "No Contact",
                 "cbmEmail": None, "contactRecordId": None},
                {"id": "m4", "name": "Doug Bower", "contactRecordId": "cDoug"},
            ],
        },
        contacts=[{"id": "cJane", "name": "Jane Doe"}],
    )
    d = await service.get_detail(MENTOR, fake, "E1")
    assert d["cbmContacts"] == [
        {"contactId": "cDoug", "name": "Doug Bower"},
        {"contactId": "cJane", "name": "Jane Doe"},
    ]


@pytest.mark.asyncio
async def test_cbm_contacts_empty_without_manager_or_comentors():
    # A domain with no manager link and no co-mentor support answers an empty
    # set — the frontend then simply pre-checks nobody.
    fake = Fake(records={("CPartnerProfile", "P1"): {"name": "Acme"}})
    d = await service.get_detail(PARTNER, fake, "P1")
    assert d["cbmContacts"] == []


@pytest.mark.asyncio
async def test_build_details_restricted_org_card_does_not_fail_the_tab():
    """A card entity the user's role can't read (live 2026-07-16: whole
    Details tab died with a permission error) renders as a restricted
    section; everything else still loads."""
    from core.espo import EspoError

    class Forbidding(Fake):
        async def get(self, entity, record_id, select=None):
            if entity == "Account":
                raise EspoError(f"get {entity}/{record_id} failed: HTTP 403 Forbidden")
            return await super().get(entity, record_id, select)

    fake = Forbidding(
        records={
            ("CPartnerProfile", "P1"): {"name": "Acme", "partnerCompanyId": "acct1"},
        },
        related={"contacts": [{"id": "c1", "name": "Pat"}]},
        meta_fields={"title": {"type": "varchar"}},
    )
    d = await details.build_details(PARTNER, fake, "P1")
    by_entity = {s["entity"]: s for s in d["sections"]}
    assert by_entity["CPartnerProfile"].get("restricted") is None  # parent loaded
    assert by_entity["Account"]["restricted"] is True
    assert by_entity["Account"]["editable"] is False
    assert [c["name"] for c in d["contacts"]] == ["Pat"]  # rest of the tab intact


@pytest.mark.asyncio
async def test_build_details_restricted_contacts_list_does_not_fail_the_tab():
    from core.espo import EspoError

    class Forbidding(Fake):
        async def list_related(self, entity, record_id, link, **kw):
            if link == "contacts":
                raise EspoError(
                    f"list_related {entity}/{record_id}/{link} failed: HTTP 403 "
                )
            return await super().list_related(entity, record_id, link, **kw)

    fake = Forbidding(
        records={
            ("CPartnerProfile", "P1"): {"name": "Acme"},
        },
        meta_fields={"title": {"type": "varchar"}},
    )
    d = await details.build_details(PARTNER, fake, "P1")
    assert d["contacts"] == []
    assert d["contactsRestricted"] is True


@pytest.mark.asyncio
async def test_build_details_non_403_errors_still_raise():
    from core.espo import EspoError

    class Broken(Fake):
        async def get(self, entity, record_id, select=None):
            if entity == "Account":
                raise EspoError(f"get {entity}/{record_id} failed: HTTP 500 boom")
            return await super().get(entity, record_id, select)

    fake = Broken(
        records={("CPartnerProfile", "P1"): {"name": "Acme", "partnerCompanyId": "acct1"}},
        meta_fields={"title": {"type": "varchar"}},
    )
    with pytest.raises(EspoError):
        await details.build_details(PARTNER, fake, "P1")
