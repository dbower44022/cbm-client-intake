"""Give the training sandbox leads and campaigns — the Campaign Management demo.

The nightly reset truncates every CRM table newer than the 09-07-26 baseline,
and the lead and campaign tables are all newer (``OPEN-ITEMS.md`` #45). Until a
re-baseline captures them, Campaign Management on crm-test is empty every
morning. This script makes a small, deliberate set of records so every screen
of the arc has something to show, then the re-baseline keeps them:

* **Leads** at every status (Unqualified, Qualified, Disqualified, Converted),
  from a state filing, a list and a public form, with each side exit
  (Duplicate of a known company, Do Not Contact, Declined, Stale) and one dead
  address.
* **Converted leads' Company and Contact**, typed Prospect, at each funnel stage
  (Prospect, Engaged, Opportunity) and carrying their campaign.
* **One campaign of each kind**: a finished postcard run with five cards (sent,
  delivered, scanned twice, scanned once, returned), a draft postcard ready to
  build its list, a running call list (two to call, three recorded), a sent
  email campaign on a webinar, a draft text campaign, and a running LinkedIn
  campaign with three links. Partners and events are related to them.
* Two links the earlier seeders missed and the reset also truncates: an
  engagement with **two referring partners**, and an **additional manager** on
  the partner and funder showcase records.

The campaigns' LINKS are not made here: they live in the application's
database, which this script cannot reach. ``campaigns/sandbox_demo.py`` puts
them back after every nightly reset, and ``/setup`` → Operations → *Sandbox demo
campaign links* does it on demand. The campaign names and the September
postcard's card codes come from that module, so the two cannot drift.

**Runs as the CRM administrator** (``ESPO_ADMIN_*`` in ``.env``, read with a
parser — never ``source .env``), unlike the other three seeders: the org-wide
API key may not create a campaign, and no role should gain that for a seeder.
Every field is checked against the live CRM's metadata first; an absent field
or a value outside its options is reported and dropped, never sent.

Idempotent by name. Never removes or overwrites a value a record already holds.
Read-only unless ``--apply``. Refuses any CRM but crm-test.

    uv run python scripts/sandbox/seed_outreach_data.py
    uv run python scripts/sandbox/seed_outreach_data.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from campaigns import config as cfg  # noqa: E402
from campaigns import sandbox_demo as demo  # noqa: E402
from core.espo import EspoError  # noqa: E402

CRM_FMT = "%Y-%m-%d %H:%M:%S"
NOTE = "Sandbox training data."
FILING = "Ohio filings — September 2026"
MARKETING_TEAM = "Marketing Admin Team"
MENTOR_TEAM = "Mentor Team"


def _addr(street: str, city: str = "Cleveland", zip_: str = "44113") -> dict[str, str]:
    return {"mailingAddressStreet": street, "mailingAddressCity": city,
            "mailingAddressState": "OH", "mailingAddressPostalCode": zip_,
            "mailingAddressCountry": "US"}


#: The leads. ``key`` is how the campaigns below refer to a lead; ``name`` is
#: the stored name the idempotency check matches on.
LEADS: tuple[dict[str, Any], ...] = (
    # --- carded by the September postcard (in DEMO_SCAN_TOKENS order) ---
    {"key": "lakeshore", "name": "Lakeshore Tile & Stone", "businessName": "Lakeshore Tile & Stone",
     **_addr("4120 Lorain Ave"), "website": "https://lakeshoretile.example.com",
     "leadStatus": cfg.LEAD_CONVERTED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5120331"},
    {"key": "marigold", "name": "Marigold Pet Grooming", "businessName": "Marigold Pet Grooming",
     **_addr("2210 Professor Ave"), "website": "https://marigoldpets.example.com", "phone": "+12165550141",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5120347"},
    {"key": "northcoast", "name": "Northcoast Drone Services", "businessName": "Northcoast Drone Services",
     **_addr("1890 E 40th St", zip_="44103"), "website": "https://northcoastdrones.example.com",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5120352",
     "addressStatus": cfg.ADDRESS_DEAD, "addressDeadDays": 9},
    # A named person and a phone: the ladder places this one Contactable.
    {"key": "tremont", "name": "Tremont Coffee Roasters", "businessName": "Tremont Coffee Roasters",
     **_addr("2368 W 11th St"), "website": "https://tremontroasters.example.com", "phone": "+12165550163",
     "firstName": "Lena", "lastName": "Varga",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5120368"},
    {"key": "ohiocity", "name": "Ohio City Bike Works", "businessName": "Ohio City Bike Works",
     **_addr("1814 W 25th St"), "website": "https://ohiocitybikes.example.com", "phone": "+12165550172",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5120374"},
    # --- never carded: the November postcard's Build the list finds these ---
    {"key": "gordon", "name": "Gordon Square Florist", "businessName": "Gordon Square Florist",
     **_addr("6515 Detroit Ave", zip_="44102"), "website": "https://gordonsquareflowers.example.com",
     "phone": "+12165550188",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5131020"},
    {"key": "shoreway", "name": "Detroit Shoreway Signs", "businessName": "Detroit Shoreway Signs",
     **_addr("5800 Detroit Ave", zip_="44102"),
     "leadStatus": cfg.LEAD_UNQUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5131044"},
    {"key": "collinwood", "name": "Collinwood Records", "businessName": "Collinwood Records",
     **_addr("15711 Waterloo Rd", zip_="44110"),
     "leadStatus": cfg.LEAD_UNQUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5131057"},
    # --- the call list ---
    {"key": "slavic", "name": "Slavic Village Bakery", "businessName": "Slavic Village Bakery",
     **_addr("6900 Fleet Ave", zip_="44105"), "website": "https://slavicvillagebakery.example.com",
     "phone": "+12165550195",
     "leadStatus": cfg.LEAD_CONVERTED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5108811"},
    {"key": "kamms", "name": "Kamm's Corners Hardware", "businessName": "Kamm's Corners Hardware",
     **_addr("16800 Lorain Ave", zip_="44111"), "website": "https://kammshardware.example.com",
     "phone": "+12165550117",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5108826",
     "sideExit": cfg.EXIT_DECLINED, "sideExitNote": "Said no on the call: already has an accountant who advises them."},
    # --- a list: person leads ---
    {"key": "kowalski", "name": "Hannah Kowalski", "firstName": "Hannah", "lastName": "Kowalski",
     "phone": "+12165550126", "leadStatus": cfg.LEAD_UNQUALIFIED, "leadSource": cfg.SOURCE_LIST,
     "importBatch": "Small-business fair sign-ups — Fall 2026"},
    # A referrer and an email: the ladder places this one Referred.
    {"key": "bell", "name": "Marcus Bell", "firstName": "Marcus", "lastName": "Bell",
     "email": "marcus.bell@sandbox.cbmentors.org", "phone": "+12165550139",
     "referredByName": "Pat Reilly, Tremont Chamber of Commerce",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_LIST,
     "importBatch": "Small-business fair sign-ups — Fall 2026"},
    # --- each way a lead stops being worked ---
    {"key": "titleloans", "name": "Quick Cash Title Loans", "businessName": "Quick Cash Title Loans",
     **_addr("3200 W 117th St", zip_="44111"), "website": "https://quickcashtitle.example.com",
     "leadStatus": cfg.LEAD_DISQUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5131063",
     "description": "Not a fit: consumer lending, outside the programme."},
    {"key": "brightline", "name": "Brightline Bakehouse", "businessName": "Brightline Bakehouse",
     **_addr("1400 W 6th St"), "leadStatus": cfg.LEAD_UNQUALIFIED, "leadSource": cfg.SOURCE_FILING,
     "externalReference": "OH-4977120", "sideExit": cfg.EXIT_DUPLICATE,
     "sideExitNote": "Duplicate of the company Brightline Bakehouse (matched by name and postal code at import).",
     "alreadyKnown": "Brightline Bakehouse"},
    {"key": "pawn", "name": "Euclid Avenue Pawn", "businessName": "Euclid Avenue Pawn",
     **_addr("8000 Euclid Ave", zip_="44103"), "website": "https://euclidpawn.example.com",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-5099302",
     "sideExit": cfg.EXIT_DO_NOT_CONTACT, "sideExitNote": "Owner asked not to be contacted again."},
    {"key": "glass", "name": "Clark-Fulton Auto Glass", "businessName": "Clark-Fulton Auto Glass",
     **_addr("3400 W 25th St", zip_="44109"), "website": "https://clarkfultonglass.example.com",
     "leadStatus": cfg.LEAD_QUALIFIED, "leadSource": cfg.SOURCE_FILING, "externalReference": "OH-4890015",
     "sideExit": cfg.EXIT_STALE, "sideExitNote": "No activity for 180 days."},
    # --- a lead behind a public form (ruling 48): Converted at once ---
    {"key": "okoro", "name": "Dana Okoro", "firstName": "Dana", "lastName": "Okoro",
     "email": "dana.okoro@sandbox.cbmentors.org",
     "leadStatus": cfg.LEAD_CONVERTED, "leadSource": cfg.SOURCE_INFO_REQUEST},
)

#: The Company and Contact a converted lead became (typed Prospect, ruling 43).
#: (lead key, company or None, contact or None, stage, campaign)
CONVERSIONS: tuple[tuple[str, Optional[dict], Optional[dict], str, str], ...] = (
    ("lakeshore",
     {"name": "Lakeshore Tile & Stone", "website": "https://lakeshoretile.example.com",
      "billingAddressStreet": "4120 Lorain Ave", "billingAddressCity": "Cleveland",
      "billingAddressState": "OH", "billingAddressPostalCode": "44113"},
     {"firstName": "Rosa", "lastName": "Medina", "emailAddress": "rosa.medina@sandbox.cbmentors.org",
      "phoneNumber": "+12165550144"},
     cfg.STAGE_ENGAGED, demo.POSTCARD_DONE),
    ("slavic",
     {"name": "Slavic Village Bakery", "website": "https://slavicvillagebakery.example.com",
      "billingAddressStreet": "6900 Fleet Ave", "billingAddressCity": "Cleveland",
      "billingAddressState": "OH", "billingAddressPostalCode": "44105"},
     {"firstName": "Pavel", "lastName": "Novak", "emailAddress": "pavel.novak@sandbox.cbmentors.org",
      "phoneNumber": "+12165550195"},
     cfg.STAGE_PROSPECT, demo.CALLS),
    ("okoro", None,
     {"firstName": "Dana", "lastName": "Okoro", "emailAddress": "dana.okoro@sandbox.cbmentors.org",
      "cSmsOptIn": True},
     cfg.STAGE_OPPORTUNITY, demo.SOCIAL),
)

#: The campaigns. Dates are days from today.
CAMPAIGNS: tuple[dict[str, Any], ...] = (
    {"name": demo.POSTCARD_DONE, "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": cfg.STATUS_COMPLETE,
     "postcardSize": "4x6", "pieceCount": 5, "estimatedCost": 4.25, "estimatedCostCurrency": "USD",
     "selectionSummary": "Leads at Qualified with a usable address, never sent a card.",
     "signedOffByName": "Mark Marketing", "signedOff": -30, "runStarted": -29, "runCompleted": -29,
     "startDate": -30, "endDate": 30, "teams": (MARKETING_TEAM,),
     "partners": ("Cuyahoga Small Business Alliance",), "events": (),
     "funders": ("Harrowgate Family Trust",),
     "description": "<p>First card to September's new filings. Offer: a free first meeting with a mentor.</p>"},
    {"name": demo.POSTCARD_DRAFT, "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": cfg.STATUS_DRAFT,
     "postcardSize": "6x9", "startDate": 10, "teams": (MARKETING_TEAM,), "partners": (), "events": (),
     "description": "<p>Ready to build its list: press <em>Build the list</em>.</p>"},
    {"name": demo.CALLS, "campaignKind": cfg.KIND_CALL, "campaignStatus": cfg.STATUS_RUNNING,
     "signedOffByName": "Mark Marketing", "signedOff": -6, "runStarted": -6, "startDate": -6, "endDate": 21,
     "selectionSummary": "Leads at Qualified with a phone number.",
     "teams": (MARKETING_TEAM, MENTOR_TEAM), "partners": (), "events": (),
     "description": "<p>Follow-up calls to the September filings. Mentors may call.</p>"},
    {"name": demo.EMAIL, "campaignKind": cfg.KIND_EMAIL, "campaignStatus": cfg.STATUS_COMPLETE,
     "pieceCount": 3, "signedOffByName": "Mark Marketing", "signedOff": -12, "runStarted": -12,
     "runCompleted": -11, "startDate": -12, "endDate": 14, "teams": (MARKETING_TEAM,),
     "selectionSummary": "Prospects and engaged contacts who opted in to email.",
     "partners": (), "events": (demo.EMAIL_EVENT,),
     "description": "<p>Invitation to the Marketing on a Shoestring webinar.</p>"},
    {"name": demo.TEXT, "campaignKind": cfg.KIND_SMS, "campaignStatus": cfg.STATUS_DRAFT,
     "startDate": 13, "teams": (MARKETING_TEAM,), "partners": (), "events": (demo.EMAIL_EVENT,),
     "smsMessage": "Cleveland Business Mentors: free webinar Marketing on a Shoestring is tomorrow. "
                   "Ask for a mentor: https://cbm-client-intake-svxs3.ondigitalocean.app/c/sbxtext8 "
                   "Reply STOP to stop texts.",
     "description": "<p>Reminder the day before the webinar, to contacts who ticked the text box.</p>"},
    {"name": demo.SOCIAL, "campaignKind": cfg.KIND_SOCIAL, "campaignStatus": cfg.STATUS_RUNNING,
     "platform": "LinkedIn", "startDate": -40, "endDate": 50, "teams": (MARKETING_TEAM,),
     "partners": ("Northgate Chamber of Commerce",), "events": ("Hiring Your First Employee",),
     "description": "<p>Posts on the chapter's page and Northgate Chamber's, linking to the "
                    "programme, the mentor request and the question form.</p>"},
)

#: Touches. (campaign, lead key, channel, status, outcome, days ago, extra)
#: The September postcard's five rows take DEMO_SCAN_TOKENS in order.
TOUCHES: tuple[tuple[str, str, str, str, str, int, dict], ...] = (
    (demo.POSTCARD_DONE, "lakeshore", cfg.KIND_POSTCARD, cfg.TOUCH_DELIVERED, cfg.OUTCOME_SCANNED, 29,
     {"scanCount": 2, "scannedDaysAgo": 24}),
    (demo.POSTCARD_DONE, "marigold", cfg.KIND_POSTCARD, cfg.TOUCH_DELIVERED, "", 29, {}),
    (demo.POSTCARD_DONE, "northcoast", cfg.KIND_POSTCARD, cfg.TOUCH_RETURNED, "", 29, {}),
    (demo.POSTCARD_DONE, "tremont", cfg.KIND_POSTCARD, cfg.TOUCH_DELIVERED, cfg.OUTCOME_SCANNED, 29,
     {"scanCount": 1, "scannedDaysAgo": 20}),
    (demo.POSTCARD_DONE, "ohiocity", cfg.KIND_POSTCARD, cfg.TOUCH_SENT, "", 29, {}),
    (demo.CALLS, "marigold", cfg.KIND_CALL, cfg.TOUCH_PLANNED, "", 6, {}),
    (demo.CALLS, "gordon", cfg.KIND_CALL, cfg.TOUCH_PLANNED, "", 6, {}),
    (demo.CALLS, "ohiocity", cfg.KIND_CALL, cfg.TOUCH_DONE, cfg.OUTCOME_NO_ANSWER, 4,
     {"callNotes": "Rang twice, no voicemail."}),
    (demo.CALLS, "slavic", cfg.KIND_CALL, cfg.TOUCH_DONE, cfg.OUTCOME_INTERESTED, 3,
     {"callNotes": "Owner wants help with wholesale pricing. Sent the mentor request link."}),
    (demo.CALLS, "kamms", cfg.KIND_CALL, cfg.TOUCH_DONE, cfg.OUTCOME_DECLINED, 2,
     {"callNotes": "Not interested; has an accountant."}),
)

#: Engagements: the campaign that brought them, and every referring partner.
ENGAGEMENT_CREDITS: tuple[tuple[str, Optional[str], tuple[str, ...]], ...] = (
    ("Riverbend Cycles — Mentoring", demo.SOCIAL, ("Northgate Chamber of Commerce",)),
    ("Salt & Sable Catering — Mentoring", None,
     ("Northgate Chamber of Commerce", "Cuyahoga Small Business Alliance")),
)

#: Additional managers on the partner and funder showcase records.
ADDITIONAL_MANAGERS: tuple[tuple[str, str, str], ...] = (
    ("CPartnerProfile", "Cuyahoga Small Business Alliance", "Joe Mentor"),
    ("CSponsorProfile", "Harrowgate Family Trust", "Joe Mentor"),
)


def _stamp(now: datetime, days: int) -> str:
    return (now + timedelta(days=days)).replace(hour=15, minute=0, second=0, microsecond=0).strftime(CRM_FMT)


def _date(now: datetime, days: int) -> str:
    return (now + timedelta(days=days)).strftime("%Y-%m-%d")


def _mailed(lead: dict[str, Any]) -> str:
    return "\n".join([lead["businessName"], lead["mailingAddressStreet"],
                      f"{lead['mailingAddressCity']}, {lead['mailingAddressState']} "
                      f"{lead['mailingAddressPostalCode']}"])


class OutreachSeeder:
    def __init__(self, client, *, apply: bool, now: datetime) -> None:
        self.client = client
        self.apply = apply
        self.now = now
        self.did: list[str] = []
        self._fields: dict[str, dict[str, Any]] = {}
        self.ids: dict[str, str] = {}      # "lead:<key>", "campaign:<name>", ...

    async def note(self, message: str) -> None:
        self.did.append(message)
        print(f"  {'' if self.apply else 'would '}{message}")

    async def fields(self, entity: str) -> dict[str, Any]:
        if entity not in self._fields:
            self._fields[entity] = await self.client.metadata(f"entityDefs.{entity}.fields") or {}
        return self._fields[entity]

    async def clean(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Drop a field the CRM lacks, and an enum value outside its options."""
        fields = await self.fields(entity)
        out: dict[str, Any] = {}
        for key, value in payload.items():
            known = (key in fields
                     or (key.endswith("Id") and key[:-2] in fields)
                     or (key.endswith("Ids") and key[:-3] in fields))
            if not known:
                await self.note(f"! {entity} has no field {key!r} — dropped")
                continue
            spec = fields.get(key) or {}
            if spec.get("type") == "enum" and value not in (spec.get("options") or [value]):
                await self.note(f"! {entity}.{key} has no option {value!r} — dropped")
                continue
            if spec.get("type") == "multiEnum":
                options = spec.get("options") or []
                value = [v for v in value if v in options]
            out[key] = value
        return out

    async def by_name(self, entity: str, name: str, select: str = "id,name") -> Optional[dict[str, Any]]:
        data = await self.client.list(entity, select=select, max_size=1,
                                      where=[{"type": "equals", "attribute": "name", "value": name}])
        rows = data.get("list", [])
        return rows[0] if rows else None

    async def ensure(self, entity: str, name: str, payload: dict[str, Any], *,
                     key: str, find: Optional[tuple[str, str]] = None) -> Optional[str]:
        """The record's id: an existing one by name (or by ``find``), else a
        new one. Never updates a record that is already there."""
        if find:
            row = await self.client.find_one(entity, find[0], find[1], select="id")
        else:
            row = await self.by_name(entity, name)
        if row:
            self.ids[key] = row["id"]
            return row["id"]
        await self.note(f"create {entity} {name}")
        # Cleaned in the dry run too, so a dropped field shows before --apply.
        payload = await self.clean(entity, payload)
        if not self.apply:
            self.ids[key] = f"<new {entity} {name}>"
            return self.ids[key]
        created = await self.client.create(entity, payload)
        self.ids[key] = created["id"]
        return created["id"]

    async def relate(self, entity: str, record_id: str, link: str, foreign_id: str, label: str) -> None:
        if record_id.startswith("<") or foreign_id.startswith("<"):
            await self.note(f"relate {label}")
            return
        current = await self.client.list_related(entity, record_id, link, select="id", max_size=200)
        if foreign_id in {r.get("id") for r in current.get("list", [])}:
            return
        await self.note(f"relate {label}")
        if self.apply:
            await self.client.relate(entity, record_id, link, foreign_id)

    async def fill(self, entity: str, record_id: str, values: dict[str, Any], label: str) -> None:
        """Null-fill: set each value only where the record holds none."""
        if record_id.startswith("<"):
            await self.note(f"set {', '.join(sorted(values))} on {label}")
            return
        values = await self.clean(entity, values)
        if not values:
            return
        row = await self.client.get(entity, record_id) or {}
        missing = {k: v for k, v in values.items() if row.get(k) in (None, "", [], False)}
        if not missing:
            return
        await self.note(f"set {', '.join(sorted(missing))} on {label}")
        if self.apply:
            await self.client.update(entity, record_id, missing)


async def team_ids(s: OutreachSeeder, names: tuple[str, ...]) -> list[str]:
    out = []
    for name in names:
        team = await s.by_name("Team", name)
        if team:
            out.append(team["id"])
        else:
            await s.note(f"! no team {name!r} — left off")
    return out


async def seed_campaigns(s: OutreachSeeder) -> None:
    for c in CAMPAIGNS:
        payload: dict[str, Any] = {k: v for k, v in c.items()
                                   if k not in ("teams", "partners", "events", "funders", "signedOff", "runStarted",
                                                "runCompleted", "startDate", "endDate")}
        for field, key in (("signedOffAt", "signedOff"), ("runStartedAt", "runStarted"),
                           ("runCompletedAt", "runCompleted")):
            if key in c:
                payload[field] = _stamp(s.now, c[key])
        for field in ("startDate", "endDate"):
            if field in c:
                payload[field] = _date(s.now, c[field])
        payload["teamsIds"] = await team_ids(s, c["teams"])
        cid = await s.ensure(cfg.CAMPAIGN, c["name"], payload, key=f"campaign:{c['name']}")
        for partner in c["partners"]:
            row = await s.by_name(cfg.PARTNER_PROFILE, partner)
            if row:
                await s.relate(cfg.CAMPAIGN, cid, cfg.LINK_PARTNERS, row["id"], f"{c['name']} -> {partner}")
            else:
                await s.note(f"! no partner {partner!r} — skipped")
        funders = c.get("funders") or ()
        if funders and cfg.LINK_FUNDERS not in (await s.client.metadata(f"entityDefs.{cfg.CAMPAIGN}.links") or {}):
            await s.note(f"! this CRM has no {cfg.CAMPAIGN}.{cfg.LINK_FUNDERS} (ruling 57) — funders skipped")
            funders = ()
        for funder in funders:
            row = await s.by_name(cfg.SPONSOR_PROFILE, funder)
            if row:
                await s.relate(cfg.CAMPAIGN, cid, cfg.LINK_FUNDERS, row["id"], f"{c['name']} -> {funder} (funder)")
            else:
                await s.note(f"! no funder {funder!r} — skipped")
        for event in c["events"]:
            row = await s.by_name(cfg.EVENT, event)
            if row:
                await s.relate(cfg.CAMPAIGN, cid, cfg.LINK_EVENTS, row["id"], f"{c['name']} -> {event}")
            else:
                await s.note(f"! no event {event!r} — skipped")


async def seed_leads(s: OutreachSeeder) -> None:
    for lead in LEADS:
        payload = {k: v for k, v in lead.items() if k not in ("key", "alreadyKnown", "addressDeadDays")}
        payload.setdefault("addressStatus", cfg.ADDRESS_USABLE if lead.get("mailingAddressStreet") else None)
        payload["leadStatusChangedAt"] = _stamp(s.now, -30)
        if lead["leadStatus"] in (cfg.LEAD_QUALIFIED, cfg.LEAD_CONVERTED):
            payload["qualifiedBy"] = "the filing filter" if lead["leadSource"] == cfg.SOURCE_FILING else "Mark Marketing"
            payload["qualifiedAt"] = _stamp(s.now, -31)
        if lead.get("sideExit"):
            payload["sideExitAt"] = _stamp(s.now, -2)
        if lead.get("addressDeadDays"):
            payload["addressDeadAt"] = _stamp(s.now, -lead["addressDeadDays"])
        if lead.get("alreadyKnown"):
            known = await s.by_name(cfg.ACCOUNT, lead["alreadyKnown"])
            if known:
                payload["alreadyKnownCompanyId"] = known["id"]
        payload.setdefault("description", NOTE)
        # The qualification ladder (build plan § 7e.3): a Qualified demo lead
        # carries the level its facts earn. ``clean`` drops the field on a CRM
        # without it; ``fill`` gives it to a lead seeded before the ladder.
        level = None
        if lead["leadStatus"] == cfg.LEAD_QUALIFIED:
            from campaigns.ladder import facts, placed
            level = placed(facts(payload))
            payload["qualificationLevel"] = level
        lead_id = await s.ensure(cfg.PROSPECT, lead["name"], {k: v for k, v in payload.items() if v is not None},
                                 key=f"lead:{lead['key']}")
        if level and lead_id:
            await s.fill(cfg.PROSPECT, lead_id, {"qualificationLevel": level}, lead["name"])


async def seed_conversions(s: OutreachSeeder) -> None:
    for key, company, contact, stage, campaign in CONVERSIONS:
        lead_id = s.ids.get(f"lead:{key}")
        campaign_id = s.ids.get(f"campaign:{campaign}")
        company_id = contact_id = None
        if company:
            company_id = await s.ensure(cfg.ACCOUNT, company["name"], {
                **company, "cCompanyType": [cfg.COMPANY_TYPE_PROSPECT], "cFunnelStage": stage,
                "cEntryStage": cfg.STAGE_PROSPECT, "cOutreachCampaignId": campaign_id, "description": NOTE,
            }, key=f"company:{key}")
        if contact:
            contact_id = await s.ensure(cfg.CONTACT, f"{contact['firstName']} {contact['lastName']}", {
                **contact, "cContactType": [cfg.CONTACT_TYPE_PROSPECT], "cFunnelStage": stage,
                "cEntryStage": cfg.STAGE_PROSPECT, "cOutreachCampaignId": campaign_id,
                **({"accountId": company_id} if company_id else {}), "description": NOTE,
            }, key=f"contact:{key}", find=("emailAddress", contact["emailAddress"]))
        if lead_id:
            links = {}
            if company_id:
                links["promotedCompanyId"] = company_id
            if contact_id:
                links["promotedContactId"] = contact_id
            await s.fill(cfg.PROSPECT, lead_id, links, f"lead {key}")


async def seed_touches(s: OutreachSeeder) -> None:
    leads = {l["key"]: l for l in LEADS}
    scans = iter(demo.DEMO_SCAN_TOKENS)
    call_teams = await team_ids(s, (MARKETING_TEAM, MENTOR_TEAM))
    for campaign, key, channel, status, outcome, days, extra in TOUCHES:
        lead = leads[key]
        name = f"{campaign} — {lead['name']}"
        sent = _stamp(s.now, -days)
        payload: dict[str, Any] = {
            "name": name, "channel": channel, "touchStatus": status,
            "plannedAt": _stamp(s.now, -days - 1),
            "outreachCampaignId": s.ids.get(f"campaign:{campaign}"),
            "prospectId": s.ids.get(f"lead:{key}"),
            "stageAtTouch": lead["leadStatus"] if lead["leadStatus"] in cfg.LEAD_OPEN_STATUSES else cfg.LEAD_QUALIFIED,
        }
        if outcome:
            payload["outcome"] = outcome
        if channel == cfg.KIND_POSTCARD:
            scan = next(scans)
            payload.update(scanToken=scan, sentAt=sent, mailedAddress=_mailed(lead),
                           vendorPieceId=f"dryrun-{scan}", vendorStatus="dry-run")
            if status in (cfg.TOUCH_DELIVERED,):
                payload["deliveredAt"] = _stamp(s.now, -days + 4)
            if status == cfg.TOUCH_RETURNED:
                payload["returnedAt"] = _stamp(s.now, -days + 20)
            if extra.get("scanCount"):
                payload["scanCount"] = extra["scanCount"]
                payload["firstScannedAt"] = _stamp(s.now, -extra["scannedDaysAgo"])
        else:
            payload["teamsIds"] = call_teams
            payload["calledPhone"] = lead.get("phone")
            if status == cfg.TOUCH_DONE:
                payload["doneAt"] = sent
                payload["callNotes"] = extra.get("callNotes")
        await s.ensure(cfg.TOUCH, name, {k: v for k, v in payload.items() if v is not None},
                       key=f"touch:{name}")


async def seed_engagement_links(s: OutreachSeeder) -> None:
    for engagement, campaign, partners in ENGAGEMENT_CREDITS:
        row = await s.by_name("CEngagement", engagement)
        if not row:
            await s.note(f"! no engagement {engagement!r} — skipped")
            continue
        if campaign:
            await s.fill("CEngagement", row["id"], {"outreachCampaignId": s.ids.get(f"campaign:{campaign}")},
                         engagement)
        if "referringPartners" not in (await s.client.metadata("entityDefs.CEngagement.links") or {}):
            await s.note("! this CRM has no CEngagement.referringPartners — skipped")
            continue
        for partner in partners:
            p = await s.by_name(cfg.PARTNER_PROFILE, partner)
            if p:
                await s.relate("CEngagement", row["id"], "referringPartners", p["id"],
                               f"{engagement} .referringPartners -> {partner}")


async def seed_additional_managers(s: OutreachSeeder) -> None:
    for entity, record, manager in ADDITIONAL_MANAGERS:
        if "additionalManagers" not in (await s.client.metadata(f"entityDefs.{entity}.links") or {}):
            await s.note(f"! this CRM has no {entity}.additionalManagers — skipped")
            continue
        row = await s.by_name(entity, record)
        profile = await s.by_name("CMentorProfile", manager)
        if row and profile:
            await s.relate(entity, row["id"], "additionalManagers", profile["id"],
                           f"{record} .additionalManagers -> {manager}")
        else:
            await s.note(f"! no {entity} {record!r} or mentor profile {manager!r} — skipped")


async def run(client, *, apply: bool, now: Optional[datetime] = None) -> OutreachSeeder:
    s = OutreachSeeder(client, apply=apply, now=now or datetime.now(timezone.utc))
    for entity in (cfg.PROSPECT, cfg.CAMPAIGN, cfg.TOUCH):
        if not await s.fields(entity):
            raise RuntimeError(f"This CRM has no {entity} — apply the outreach handoffs first.")
    if "leadStatus" not in await s.fields(cfg.PROSPECT):
        raise RuntimeError("This CRM has no CProspect.leadStatus — apply the lead-model handoff first.")
    await seed_campaigns(s)
    await seed_leads(s)
    await seed_conversions(s)
    await seed_touches(s)
    await seed_engagement_links(s)
    await seed_additional_managers(s)
    return s


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="actually write")
    args = parser.parse_args()

    from espo_admin import connect, credentials, load_env

    env = load_env()
    base = credentials(env)[0]
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_ADMIN_BASE is {base!r}, not the crm-test sandbox.")
        return 2
    client, _ = await connect(env)

    print(f"\nSeeding leads and campaigns on {base}")
    print("APPLY\n" if args.apply else "DRY RUN — nothing will be written\n")
    try:
        s = await run(client, apply=args.apply)
    except (EspoError, RuntimeError) as exc:
        print(f"\nSTOPPED: {exc}")
        return 1
    print(f"\n{len(s.did)} change(s).")
    if not args.apply:
        print("Re-run with --apply.")
    else:
        print("Next: /setup → Operations → Sandbox demo campaign links (dry run, then apply).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
