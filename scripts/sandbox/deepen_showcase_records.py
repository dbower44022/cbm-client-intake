"""Fill every field and every relationship on the showcase records.

Doug's standard (2026-08-22): *"a full function record should have data in
every field and every relationship should include at least one record."* The
seed and the enrichment build structure and feature coverage; this makes the
handful of records a demo actually opens look like real, complete records —
phone numbers, addresses, agreements, a co-mentor, a referring partner.

Run ``audit_showcase_records.py`` before and after; it reads the CRM's own
``entityDefs``, so it measures this rather than trusting it.

**Not everything should be filled.** An Active mentor with a ``departureReason``
is worse data than one with a blank. Fields that are correctly empty for a
record's role are listed in the audit's ``EXPECTED_EMPTY``, with the reason.

Enum values go through :func:`pick`, which validates against the live options
and falls back rather than guessing — the CRM team changes these lists, and a
value outside them fails the whole update
([[non-required-enums-never-block]] is about user input; here a hard failure
would just stop the script).

Idempotent: every write is an update to a named record. Read-only unless
``--apply``.

    uv run python scripts/sandbox/deepen_showcase_records.py
    uv run python scripts/sandbox/deepen_showcase_records.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.espo import EspoClient, EspoError  # noqa: E402
from core.config import get_settings  # noqa: E402

CRM_FMT = "%Y-%m-%d %H:%M:%S"
DOMAIN = "sandbox.cbmentors.org"

ENGAGEMENT = "Brightline Bakehouse — Mentoring"
COMPANY = "Brightline Bakehouse"
CLIENT_PROFILE = "Brightline Bakehouse — Client Profile"
CLIENT_CONTACT = "Dana Whitcomb"
MENTOR = "Joe Mentor"
CO_MENTOR = "Matt Mentor"
PARTNER = "Cuyahoga Small Business Alliance"
FUNDER = "Harrowgate Family Trust"
#: Given to the mentor so his managedPartners / managedSponsors are not empty,
#: without disturbing the partner and funder showcases.
MENTOR_PARTNER = "Maple Ridge Enterprise Center"
MENTOR_FUNDER = "Cedarcrest Charitable Fund"


def _rejected_field(message: str) -> str | None:
    """The field named in an EspoCRM validation 400, if any."""
    marker = "field: "
    if marker not in message:
        return None
    tail = message.split(marker, 1)[1]
    return tail.split(",", 1)[0].strip() or None


class Deepener:
    def __init__(self, client: EspoClient, *, apply: bool) -> None:
        self.client = client
        self.apply = apply
        self.defs: dict = {}
        self.changes = 0

    async def load(self) -> None:
        self.defs = await self.client.metadata("entityDefs")

    def pick(self, entity: str, field: str, *preferred: str):
        """The first preferred option the CRM actually offers, else the first
        real option. Returns None when the field has no options at all."""
        spec = ((self.defs.get(entity) or {}).get("fields") or {}).get(field) or {}
        options = [o for o in (spec.get("options") or []) if o]
        if not options:
            return None
        for want in preferred:
            if want in options:
                return want
        return options[0]

    def pick_many(self, entity: str, field: str, *preferred: str) -> list[str]:
        spec = ((self.defs.get(entity) or {}).get("fields") or {}).get(field) or {}
        options = [o for o in (spec.get("options") or []) if o]
        chosen = [w for w in preferred if w in options]
        return chosen or options[:2]

    async def find(self, entity: str, name: str) -> dict | None:
        data = await self.client.list(
            entity, select="id,name", max_size=1,
            where=[{"type": "equals", "attribute": "name", "value": name}],
        )
        rows = data.get("list", [])
        return rows[0] if rows else None

    async def update(self, entity: str, name: str, payload: dict) -> str | None:
        record = await self.find(entity, name)
        if not record:
            print(f"  ! {entity} {name!r} not found — skipped")
            return None
        payload = {k: v for k, v in payload.items() if v is not None}
        self.changes += 1
        print(f"  {'' if self.apply else 'would '}fill {entity}/{name} "
              f"({len(payload)} fields)")
        if not self.apply:
            return record["id"]

        # Drop-and-retry on a field the CRM rejects, the way
        # core.espo.create_dropping_invalid does: one bad value should cost that
        # field, not the whole record. The CRM names the offending field in the
        # 400, and these lists drift under us.
        dropped: list[str] = []
        for _ in range(len(payload) + 1):
            try:
                await self.client.update(entity, record["id"], payload)
                break
            except EspoError as exc:
                field = _rejected_field(str(exc))
                if not field or field not in payload:
                    raise
                payload.pop(field)
                dropped.append(field)
        if dropped:
            print(f"    dropped {len(dropped)} rejected field(s): {', '.join(dropped)}")
        return record["id"]

    async def relate(self, entity: str, name: str, link: str,
                     target_entity: str, target_name: str) -> None:
        record = await self.find(entity, name)
        target = await self.find(target_entity, target_name)
        if not (record and target):
            print(f"  ! cannot relate {name} -> {target_name} (missing record)")
            return
        self.changes += 1
        print(f"  {'' if self.apply else 'would '}relate {entity}/{name} "
              f".{link} -> {target_name}")
        if self.apply:
            try:
                await self.client.relate(entity, record["id"], link, target["id"])
            except EspoError as exc:
                print(f"    ! relate failed: {str(exc)[-80:]}")


async def fill_contacts(d: Deepener, now: datetime) -> None:
    """Phones, addresses and the three consent bools.

    The agreements are what the session tools' Contacts table renders as its
    Agreements badge, and they were false on every seeded contact.
    """
    consent = {
        "cTermsOfUseAccepted": True,
        "cPrivacyPolicyAccepted": True,
        "cCodeOfConductAccepted": True,
    }
    await d.update("Contact", MENTOR, {
        "phoneNumber": "+12165550142",
        "emailAddress": f"j.mentor@{DOMAIN}",
        "title": "Retired Operations Director",
        "middleName": "A.",
        "salutationName": d.pick("Contact", "salutationName", "Mr."),
        "cPreferredName": "Joe",
        "addressStreet": "1200 Superior Avenue East, Suite 400",
        "addressCity": "Cleveland",
        "addressState": "OH",
        "addressPostalCode": "44114",
        "addressCountry": "USA",
        "cBirthday": "1962-04-17",
        "cSpouseName": "Marian Mentor",
        "cLinkedInProfile": "https://www.linkedin.com/in/joe-mentor-sandbox",
        "cMeetingPreference": d.pick("Contact", "cMeetingPreference", "Video"),
        "cEmploymentStatus": d.pick("Contact", "cEmploymentStatus", "No"),
        "cHowDidYouHear": d.pick("Contact", "cHowDidYouHear", "CBM Client or Volunteer"),
        "cPersonalProfile": "Thirty years in manufacturing operations, latterly as "
                            "plant director. Mentors on operations, pricing and "
                            "cash discipline.",
        "description": "Sails on Lake Erie, subscribes to the Cleveland Orchestra, "
                       "makes an indifferent sourdough.",
        **consent,
    })
    await d.update("Contact", CLIENT_CONTACT, {
        "phoneNumber": "+12165550188",
        "title": "Owner and Head Baker",
        "salutationName": d.pick("Contact", "salutationName", "Ms."),
        "cPreferredName": "Dana",
        "addressStreet": "4418 Lorain Avenue",
        "addressCity": "Cleveland",
        "addressState": "OH",
        "addressPostalCode": "44113",
        "addressCountry": "USA",
        "cBirthday": "1985-09-02",
        "cLinkedInProfile": "https://www.linkedin.com/in/dana-whitcomb-sandbox",
        "cMeetingPreference": d.pick("Contact", "cMeetingPreference", "In Person"),
        "cEmploymentStatus": d.pick("Contact", "cEmploymentStatus", "Yes, Full-time"),
        "cHowDidYouHear": d.pick("Contact", "cHowDidYouHear", "Partner Referral"),
        "cPersonalProfile": "Opened Brightline in 2019 after eight years in "
                            "restaurant kitchens. Six staff, one site, second "
                            "site under consideration.",
        "description": "Wants to understand her numbers well enough to stop "
                       "guessing at pricing.",
        **consent,
    })


async def fill_company(d: Deepener) -> None:
    address = {
        "billingAddressStreet": "4418 Lorain Avenue",
        "billingAddressCity": "Cleveland",
        "billingAddressState": "OH",
        "billingAddressPostalCode": "44113",
        "billingAddressCountry": "USA",
    }
    await d.update("Account", COMPANY, {
        **address,
        **{k.replace("billing", "shipping"): v for k, v in address.items()},
        "phoneNumber": "+12165550177",
        "website": f"https://brightline.{DOMAIN}",
        "type": d.pick("Account", "type", "Customer"),
        "industry": d.pick("Account", "industry", "Food & Beverage", "Retail"),
        "cIndustrySector": d.pick("Account", "cIndustrySector",
                                  "Accommodation and Food Services", "Retail Trade"),
        "cIndustrySubsector": d.pick("Account", "cIndustrySubsector"),
        "cBusinessStage": d.pick("Account", "cBusinessStage", "Growth Stage"),
        "cOrganizationType": d.pick("Account", "cOrganizationType", "For-Profit"),
        "cTargetPopulation": "Neighbourhood retail customers and local cafes.",
        "cClientNotes": "Second site under consideration for 2027. Landlord "
                        "conversation is the gating item.",
        "cLinkedInPage": "https://www.linkedin.com/company/brightline-sandbox",
        "cFacebookLink": "https://facebook.com/brightline.sandbox",
        "cInstagramLink": "https://instagram.com/brightline.sandbox",
        "cTwitterLink": "https://x.com/brightline_sbx",
        "cYoutubeLink": "https://youtube.com/@brightline-sandbox",
        "cTikTokLink": "https://tiktok.com/@brightline.sandbox",
        "sicCode": "5461",
        "description": "Retail bakery and cafe on Lorain Avenue, six staff, "
                       "trading since 2019.",
    })


async def fill_client_profile(d: Deepener) -> None:
    await d.update("CClientProfile", CLIENT_PROFILE, {
        "legalEntityType": d.pick("CClientProfile", "legalEntityType",
                                  "Limited Liability Company (LLC)"),
        "stateOfFormation": "OH",  # varchar(2)
        "formationDate": "2019-03-11",
        "fiscalYearEndMonth": d.pick("CClientProfile", "fiscalYearEndMonth", "December"),
        "numberOfEmployees": 6,
        "annualRevenueRange": d.pick("CClientProfile", "annualRevenueRange",
                                     "$500,000 to $1 Million"),
        "mostRecentFullYearRevenue": 640000,
        "mostRecentFullYearRevenueCurrency": "USD",
        "profitabilityStatus": d.pick("CClientProfile", "profitabilityStatus", "Profitable"),
        "revenueTrend": d.pick("CClientProfile", "revenueTrend", "Growing Modestly"),
        "geographicMarketReach": d.pick("CClientProfile", "geographicMarketReach",
                                        "Local (within Cuyahoga County)"),
        "primaryCustomerType": d.pick_many("CClientProfile", "primaryCustomerType",
                                           "Business-to-Consumer (B2C)",
                                           "Business-to-Business (B2B)"),
        "salesChannels": d.pick_many("CClientProfile", "salesChannels",
                                     "Retail Storefront", "Wholesale to Other Businesses",
                                     "Referrals and Word of Mouth"),
        # These three are multiEnums, not free text — a prose value is simply
        # dropped, which is why they read empty after the first pass.
        "certificationsHeld": d.pick_many("CClientProfile", "certificationsHeld",
                                          "Ohio Women Business Enterprise (WBE)"),
        "localLicensesAndPermits": "City of Cleveland retail food establishment permit",
        "fundingSourcesUsedToDate": d.pick_many("CClientProfile", "fundingSourcesUsedToDate",
                                                "Personal Savings", "Bank Loan (Conventional)"),
        "socialMediaPresence": d.pick_many("CClientProfile", "socialMediaPresence",
                                           "Instagram", "Facebook"),
        "clientRace": d.pick("CClientProfile", "clientRace", "White"),
        "clientEthnicity": d.pick("CClientProfile", "clientEthnicity",
                                  "Not Hispanic or Latino"),
        "clientVeteranStatus": d.pick("CClientProfile", "clientVeteranStatus",
                                      "No military, Reserver, or National Guard service"),
        "description": "Retail bakery with a wholesale side line. Wants pricing "
                       "discipline and a financing decision on a second oven.",
    })


async def fill_engagement(d: Deepener, now: datetime) -> None:
    await d.update("CEngagement", ENGAGEMENT, {
        "meetingCadence": d.pick("CEngagement", "meetingCadence", "Monthly"),
        "mentoringFocusAreas": d.pick_many(
            "CEngagement", "mentoringFocusAreas",
            "Finance & Cash Flow Management", "Business Strategy & Planning"),
        "engagementNotes": "Meets monthly, usually in person at the bakery. "
                           "Second-oven financing decision is the current focus.",
        "revenueIncreasePercentage": 18,
        "employmentIncreasePercentage": 33,
        "holdEndDate": None,
    })
    # Co-mentor: two writes, both required. The relationship makes him visible
    # on the record; the assignedUsers stamp is what lets his own-scope role
    # actually read it.
    await d.relate("CEngagement", ENGAGEMENT, "additionalMentors",
                   "CMentorProfile", CO_MENTOR)
    partner = await d.find("CPartnerProfile", PARTNER)
    mentor = await d.find("CMentorProfile", MENTOR)
    await d.update("CEngagement", ENGAGEMENT, {
        "referringPartnerId": (partner or {}).get("id"),
        "requestedMentorId": (mentor or {}).get("id"),
    })


async def fill_mentor(d: Deepener, now: datetime) -> None:
    await d.update("CMentorProfile", MENTOR, {
        "mentorTitle": "Retired Operations Director",
        "mentorSummary": "Operations and cash discipline for small manufacturers "
                         "and food businesses.",
        "mentorProfessionalBio":
            "<p>Joe spent thirty years in manufacturing operations, latterly as "
            "plant director for a mid-sized components maker, before joining CBM "
            "as a mentor. He works with owners on pricing, throughput and the "
            "cash consequences of growth.</p>",
        "aboutMentor": "<p>Straight-talking, numbers-first, allergic to jargon.</p>",
        "mentoringSkills": "<p>Pricing and margin analysis, cash-flow forecasting, "
                           "operations throughput, hiring the first manager.</p>",
        "mentoringWhyInterested": "<p>Someone did this for me in 1994 and I have "
                                  "been meaning to pay it back ever since.</p>",
        "fluentLanguages": d.pick_many("CMentorProfile", "fluentLanguages",
                                       "English", "Spanish"),
        "industryExperience": d.pick_many("CMentorProfile", "industryExperience",
                                          "Manufacturing", "Food and Beverage",
                                          "Business Consulting and Coaching"),
        "duesStatus": d.pick("CMentorProfile", "duesStatus", "Paid"),
        "duesPaymentDate": (now - timedelta(days=120)).strftime("%Y-%m-%d"),
        "duesRenewalDate": (now + timedelta(days=245)).strftime("%Y-%m-%d"),
        "trainingCompletionDate": (now - timedelta(days=700)).strftime("%Y-%m-%d"),
        "backgroundCheckDate": (now - timedelta(days=690)).strftime("%Y-%m-%d"),
        "ethicsAgreementAcceptanceDateTime": (now - timedelta(days=700)).strftime(CRM_FMT),
        "boardPosition": "Programme Committee",
        "onboardingNotes": "Completed the 2024 cohort onboarding. Shadowed two "
                           "sessions before taking his own client.",
        "mentorStatusNotes": "Available for one more client from the new year.",
        "zoomPersonalLink": "https://zoom.us/j/5551234567",
    })
    # managedPartners / managedSponsors are reverses of the manager link on the
    # other record — set them there, on records outside the partner and funder
    # showcases so those keep their own managers.
    await d.update("CPartnerProfile", MENTOR_PARTNER,
                   {"partnerManagerId": (await d.find("CMentorProfile", MENTOR) or {}).get("id")})
    joe_id = (await d.find("CMentorProfile", MENTOR) or {}).get("id")
    # CSponsorProfile carries TWO manager links: sponsorManager (reverse
    # sponsorsManaged) and cBMSponsorManager (reverse managedSponsors). Setting
    # only one leaves the other reverse empty on the mentor.
    await d.update("CSponsorProfile", MENTOR_FUNDER,
                   {"sponsorManagerId": joe_id, "cBMSponsorManagerId": joe_id})
    # Co-mentored engagement, so the `engagements` reverse link is not empty.
    await d.relate("CEngagement", "Ashgrove Cabinetry — Mentoring",
                   "additionalMentors", "CMentorProfile", MENTOR)


async def fill_partner_and_funder(d: Deepener, now: datetime) -> None:
    await d.update("CPartnerProfile", PARTNER, {
        "partnershipStatus": d.pick("CPartnerProfile", "partnershipStatus",
                                    "MOU/Contract Signed"),
        "partnershipType": d.pick("CPartnerProfile", "partnershipType", "Referral Partner"),
        "partnershipStartDate": (now - timedelta(days=880)).strftime("%Y-%m-%d"),
        "partnershipAgreementDate": (now - timedelta(days=875)).strftime("%Y-%m-%d"),
        "partnerContactCadence": d.pick("CPartnerProfile", "partnerContactCadence",
                                        "Quarterly"),
        "partnershipValue": d.pick_many("CPartnerProfile", "partnershipValue",
                                        "Connection to stakeholders / expanding influence",
                                        "Co-Hosted Events"),
        "cBMValueProvided": d.pick_many("CPartnerProfile", "cBMValueProvided",
                                        "Free mentoring support",
                                        "Co-hosted events or webinars"),
        "partnerNotes": "Strongest referral source. Cohorts finish in March and "
                        "September — plan capacity around those.",
        "relationGoalsEst": d.pick("CPartnerProfile", "relationGoalsEst", "Yes"),
        "lastContacted": (now - timedelta(days=11)).strftime("%Y-%m-%d"),
        "description": "County-wide small business alliance; refers programme "
                       "graduates into mentoring.",
    })
    await d.relate("CPartnerProfile", PARTNER, "hostedEvents",
                   "CEvent", "Hiring Your First Employee")

    await d.update("CSponsorProfile", FUNDER, {
        "description": "Family trust funding general operations since 2024. "
                       "Board reviews annually in the autumn.",
        "lastContacted": (now - timedelta(days=20)).strftime("%Y-%m-%d"),
        "lastContribution": (now - timedelta(days=40)).strftime("%Y-%m-%d"),
        "totalContribution": 63700,
        "totalContributionCurrency": "USD",
    })
    await d.relate("CSponsorProfile", FUNDER, "sponsoredEvents",
                   "CEvent", "Pricing for Profit")
    sally = await d.find("CMentorProfile", "Sally Sponsor")
    await d.update("CSponsorProfile", FUNDER,
                   {"cBMSponsorManagerId": (sally or {}).get("id")})
    # CPartnerProfile also has two company links; partnerCompany is the curated
    # one the app edits, `account` is the older one and reads empty without this.
    company = await d.find("Account", PARTNER)
    await d.update("CPartnerProfile", PARTNER, {"accountId": (company or {}).get("id")})


async def fill_contact_relationships(d: Deepener) -> None:
    """Attach the client contact to the things a demo opens from her record."""
    company = await d.find("Account", COMPANY)
    await d.update("Contact", CLIENT_CONTACT,
                   {"cPrimaryCompanyId": (company or {}).get("id")})
    await d.relate("CEvent", "Marketing on a Shoestring", "contacts",
                   "Contact", CLIENT_CONTACT)
    await d.relate("CEvent", "Reading Your Own Financials", "contacts",
                   "Contact", MENTOR)
    sessions = await d.client.list(
        "CSession", select="id,name", max_size=3, order_by="dateStart", order="desc",
        where=[{"type": "equals", "attribute": "engagementId",
                "value": (await d.find("CEngagement", ENGAGEMENT) or {}).get("id")}],
    )
    for row in sessions.get("list", []):
        await d.relate("CSession", row["name"], "sessionAttendees",
                       "Contact", CLIENT_CONTACT)
        await d.relate("CSession", row["name"], "sessionAttendees", "Contact", MENTOR)
    # Conversations are related to their contacts as well as their parent record;
    # this is what the contact record page's Communications tab reads.
    for subject, who in (("Cash-flow forecast for the new oven", CLIENT_CONTACT),
                         ("Cash-flow forecast for the new oven", MENTOR),
                         ("Spring referral cohort", "Terrence Boyd"),
                         ("Renewal of the 2027 grant", "Eleanor Harrowgate")):
        await d.relate("CConversation", subject, "contacts", "Contact", who)


async def fill_photo_and_registrations(d: Deepener, now: datetime) -> None:
    """A profile photo, and event registrations for both showcase contacts.

    The photo matters more than it sounds: the mentor directory's profile page
    is built around it, and without one that screen is the weakest thing a
    trainee sees.
    """
    profile = await d.find("CMentorProfile", MENTOR)
    if profile:
        record = await d.client.get("CMentorProfile", profile["id"], select="profilePhotoId")
        if record.get("profilePhotoId"):
            print("  profile photo already set")
        else:
            d.changes += 1
            print(f"  {'' if d.apply else 'would '}upload a profile photo for {MENTOR}")
            if d.apply:
                try:
                    attachment_id = await d.client.upload_attachment(
                        filename="joe-mentor.png",
                        content_type="image/png",
                        data_base64=_PORTRAIT_PNG,
                        related_type="CMentorProfile",
                        field="profilePhoto",
                    )
                    await d.client.update("CMentorProfile", profile["id"],
                                          {"profilePhotoId": attachment_id})
                except EspoError as exc:
                    print(f"    ! photo upload failed: {str(exc)[-90:]}")

    for contact_name, event_name, status in (
        (CLIENT_CONTACT, "Pricing for Profit", "Attended"),
        (CLIENT_CONTACT, "Marketing on a Shoestring", "Registered"),
        (MENTOR, "Reading Your Own Financials", "Attended"),
    ):
        reg_name = f"{event_name} — {contact_name}"
        if await d.find("CEventRegistration", reg_name):
            continue
        event = await d.find("CEvent", event_name)
        contact = await d.find("Contact", contact_name)
        if not (event and contact):
            continue
        d.changes += 1
        print(f"  {'' if d.apply else 'would '}register {contact_name} for {event_name}")
        if d.apply:
            await d.client.create("CEventRegistration", {
                "name": reg_name,
                # registrationDate is a DATETIME; a bare date is rejected.
                "registrationDate": (now - timedelta(days=50)).strftime(CRM_FMT),
                "registrationSource": d.pick("CEventRegistration",
                                             "registrationSource", "Online"),
                "attendanceStatus": d.pick("CEventRegistration",
                                           "attendanceStatus", status),
                "eventId": event["id"],
                "contactId": contact["id"],
            })


#: A 96x96 flat-grey PNG. Deliberately not a face — a stock portrait of a real
#: person on a fictional mentor is exactly the kind of thing that ends up
#: somewhere it should not be.
_PORTRAIT_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAIAAABt+uBvAAAAWklEQVR4nO3QMQEAAAjDMMC/"
    "52ECvlQgJ+lMbwHPWJgYCxNjYWIsTIyFibEwMRYmxsLEWJgYCxNjYWIsTIyFibEwMRYmxsLE"
    "WJgYCxNjYWIsTIyFibG4A0ZVAV3P4l7WAAAAAElFTkSuQmCC"
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    base = settings.espo_base_url or ""
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_BASE_URL is {base!r}, not the crm-test sandbox.")
        return 2

    client = EspoClient(base, settings.espo_api_key, settings.request_timeout_seconds)
    d = Deepener(client, apply=args.apply)
    await d.load()
    now = datetime.now(timezone.utc)

    print(f"\nDeepening showcase records on {base}")
    print("APPLY\n" if args.apply else "DRY RUN — nothing will be written\n")
    try:
        await fill_contacts(d, now)
        await fill_company(d)
        await fill_client_profile(d)
        await fill_engagement(d, now)
        await fill_mentor(d, now)
        await fill_partner_and_funder(d, now)
        await fill_contact_relationships(d)
        await fill_photo_and_registrations(d, now)
    except EspoError as exc:
        print(f"\nSTOPPED: {exc}")
        return 1

    print(f"\n{d.changes} change(s).")
    if not args.apply:
        print("Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
