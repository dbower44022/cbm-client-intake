"""Give the sandbox's showcase records data for every feature, not just structure.

``seed_training_data.py`` builds the skeleton — mentors, companies, contacts,
engagements, sessions, partners, funders. That is enough for the grids, but it
leaves half the feature surface empty: a Communications tab with no threads, a
Contributions tab with no gifts, a partner with no sessions and no referred
clients. Doug's requirement (2026-08-22) is that **each user type has at least
one record rich enough to demonstrate every feature**, so this fills the gaps on
a nominated record per domain — the "showcase" records that
``demo-records.md`` documents.

Deliberately concentrated rather than spread: one obviously-rich record per
domain is what a demo needs, and the thinner records around it are what makes
the rich one look normal rather than staged.

What this does NOT cover, and why:

* **Documents** — Drive uploads run as the service account, and crm-test still
  points at the PRODUCTION shared drive. Seeding documents before a sandbox
  drive exists would write training files into CBM's real Drive.
* **The Submission Admin queue** — those rows live in the app's Postgres, not
  the CRM. The realistic way to create them is to POST the public intake forms,
  which runs the whole capture pipeline; that is its own script.
* **The partner/funder Discussion pane** — app-only ``record_comment`` rows,
  reachable through the app as a signed-in user, not over the CRM API.

Idempotent by name, like the seed. Read-only unless ``--apply``.

    uv run python scripts/sandbox/enrich_training_data.py
    uv run python scripts/sandbox/enrich_training_data.py --apply
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

#: The record each user type is demonstrated on. Keep in step with demo-records.md.
SHOWCASE = {
    "engagement": "Brightline Bakehouse — Mentoring",
    "partner": "Cuyahoga Small Business Alliance",
    "funder": "Harrowgate Family Trust",
    "mentor": "Joe Mentor",
}

#: An email thread reads as real when it alternates and refers to itself.
#: (days ago, direction, subject, body)
THREADS: dict[str, tuple[str, tuple[tuple[int, str, str], ...]]] = {
    "engagement": (
        "Cash-flow forecast for the new oven",
        (
            (34, "Outbound", "Dana — good to meet yesterday. Attaching the template we "
                             "talked about for the 90-day forecast. Take a run at the "
                             "first month and we can look at it together."),
            (33, "Inbound", "Thanks Joe. I filled in January and February. March is the "
                            "one I am unsure about — that is when the second oven would "
                            "land and I do not know how to phase the payment."),
            (30, "Outbound", "That is exactly the right thing to be unsure about. Two "
                             "options: finance it over 24 months and keep the cash, or "
                             "pay outright and take the discount. Let us model both."),
            (16, "Inbound", "Modelled both. Financing wins if we hold three months of "
                            "payroll in reserve, which we now do. Can we go through it "
                            "at the next session?"),
            (14, "Outbound", "Yes — I have put it at the top of the agenda. Nice work."),
        ),
    ),
    "partner": (
        "Spring referral cohort",
        (
            (26, "Inbound", "We have six businesses coming out of the spring programme "
                            "who would benefit from a mentor. Shall I send the list?"),
            (25, "Outbound", "Please do. If you can include the sector and roughly what "
                             "stage they are at, we can match them faster."),
            (24, "Inbound", "Sent. Two are pre-revenue, the rest are trading."),
            (11, "Outbound", "Four are matched and the other two are in the queue. "
                             "Thank you — this is the smoothest cohort yet."),
        ),
    ),
    "funder": (
        "Renewal of the 2027 grant",
        (
            (40, "Outbound", "Attaching the impact summary for the year — 62 businesses "
                             "supported, 41 still trading at 24 months."),
            (38, "Inbound", "The board reviewed this and were impressed. We would like "
                            "to discuss renewing at the same level, possibly higher."),
            (20, "Outbound", "That is wonderful news. I have some dates for a call."),
        ),
    ),
}

#: Gifts across the lifecycle, so the Contributions tab shows more than one state.
CONTRIBUTIONS = (
    ("2026 General Operating Grant", "Grant", "Received", 25000, 250, "Check"),
    ("2027 General Operating Grant", "Grant", "Committed", 30000, 40, "Check"),
    ("Annual Dinner Sponsorship", "Sponsorship", "Received", 5000, 180, "ACH"),
    ("Spring Appeal Gift", "Donation", "Pledged", 2500, 20, "Credit Card"),
    ("Mentor Training Materials", "Donation", "Received", 1200, 300, "In-Kind"),
)

#: Published workshops, so /events and the Events tabs have content.
EVENTS = (
    (-45, "Pricing for Profit", "Online Webinar", "Virtual", "Held", True),
    (-20, "Reading Your Own Financials", "Online Webinar", "Virtual", "Held", True),
    (14, "Marketing on a Shoestring", "Online Webinar", "Virtual", "Planned", True),
    (35, "Hiring Your First Employee", "In Person Event", "In-Person", "Planned", True),
    (56, "AI Tools for Small Business", "Online Webinar", "Virtual", "Planned", True),
)

#: Staff-internal notes, so Client Administration's Notes column is not blank.
ENGAGEMENT_NOTES = {
    "Brightline Bakehouse — Mentoring": "Owner is expanding to a second site. "
                                        "Mentor asked for a finance-side co-mentor.",
    "Copperkettle Brewing — Mentoring": "Seasonal cash-flow. Check in before Q4.",
    "Halstead Print Works — Mentoring": "Assigned but not yet started — chase.",
    "Nightjar Studios — Mentoring": "On hold at the client's request until the new year.",
    "Whitmore Automotive — Mentoring": "Unresponsive since spring. Consider closing.",
}

#: Engagements credited to a partner, which is what the Referred Clients tab reads.
REFERRALS = {
    "Ashgrove Cabinetry — Mentoring": "Cuyahoga Small Business Alliance",
    "Riverbend Cycles — Mentoring": "Cuyahoga Small Business Alliance",
    "Salt & Sable Catering — Mentoring": "Northgate Chamber of Commerce",
}


class Enricher:
    def __init__(self, client: EspoClient, *, apply: bool) -> None:
        self.client = client
        self.apply = apply
        self.did: list[str] = []

    async def by_name(self, entity: str, name: str) -> dict | None:
        data = await self.client.list(
            entity, select="id,name", max_size=1,
            where=[{"type": "equals", "attribute": "name", "value": name}],
        )
        rows = data.get("list", [])
        return rows[0] if rows else None

    async def note(self, message: str) -> None:
        self.did.append(message)
        print(f"  {'' if self.apply else 'would '}{message}")


async def add_threads(e: Enricher, now: datetime) -> None:
    """Conversations + messages, related to the parent record and its contact.

    The parent link is a RELATIONSHIP on CConversation (``engagements`` /
    ``partnerProfiles`` / ``sponsorProfiles``), not a field — it has to be
    related after the create, the same way ``comms/crm.py`` does it.
    """
    targets = {
        "engagement": ("CEngagement", "engagements"),
        "partner": ("CPartnerProfile", "partnerProfiles"),
        "funder": ("CSponsorProfile", "sponsorProfiles"),
    }
    for key, (entity, link) in targets.items():
        parent = await e.by_name(entity, SHOWCASE[key])
        if not parent:
            await e.note(f"! no {key} record {SHOWCASE[key]!r} — skipped")
            continue
        subject, messages = THREADS[key]
        # Idempotency has to count MESSAGES, not just the conversation: a run
        # that died partway (the CRM rejects a snippet over 100 chars) leaves a
        # conversation with no messages, and a conversation-level skip would
        # leave the showcase record with an empty thread forever.
        existing = await e.by_name("CConversation", subject)
        have = 0
        if existing:
            have = int((await e.client.list(
                "CCommunication", max_size=1, select="id",
                where=[{"type": "equals", "attribute": "conversationId",
                        "value": existing["id"]}],
            )).get("total") or 0)
        if have >= len(messages):
            await e.note(f"thread on {SHOWCASE[key]} already complete ({have} messages)")
            continue
        await e.note(
            f"add thread {subject!r} to {SHOWCASE[key]} "
            f"({len(messages) - have} of {len(messages)} messages missing)"
        )
        if not e.apply:
            continue
        first = now - timedelta(days=messages[0][0])
        last = now - timedelta(days=messages[-1][0])
        if existing:
            conv = existing
            await e.client.update("CConversation", conv["id"], {
                "messageCount": len(messages),
                "firstMessageAt": first.strftime(CRM_FMT),
                "lastMessageAt": last.strftime(CRM_FMT),
            })
        else:
            conv = await e.client.create("CConversation", {
                "name": subject[:250],
                "conversationStatus": "Open",
                "firstMessageAt": first.strftime(CRM_FMT),
                "lastMessageAt": last.strftime(CRM_FMT),
                "messageCount": len(messages),
            })
            await e.client.relate("CConversation", conv["id"], link, parent["id"])
        for days, direction, body in messages[have:]:
            sent = (now - timedelta(days=days)).replace(
                hour=14, minute=0, second=0, microsecond=0
            )
            outbound = direction == "Outbound"
            await e.client.create("CCommunication", {
                "name": subject[:250],
                "conversationId": conv["id"],
                "direction": direction,
                "sentAt": sent.strftime(CRM_FMT),
                "fromName": "Joe Mentor" if outbound else "Sandbox Contact",
                "fromAddress": ("joe.mentor@sandbox.cbmentors.org" if outbound
                                else "contact@sandbox.cbmentors.org"),
                "toAddresses": ("contact@sandbox.cbmentors.org" if outbound
                                else "joe.mentor@sandbox.cbmentors.org"),
                "bodyCleaned": f"<p>{body}</p>",
                "snippet": body[:100],
                "sourceMailbox": "joe.mentor@sandbox.cbmentors.org",
            })


async def add_domain_sessions(e: Enricher, now: datetime) -> None:
    """Partner and funder meetings — those two tools' Sessions tabs are empty
    because the seed only ever parented sessions to engagements."""
    for key, entity, link_field, session_type in (
        ("partner", "CPartnerProfile", "partnerSessionId", "Partner Session"),
        ("funder", "CSponsorProfile", "sponsorProfileId", "Sponsor Session"),
    ):
        parent = await e.by_name(entity, SHOWCASE[key])
        if not parent:
            await e.note(f"! no {key} record — sessions skipped")
            continue
        # Count, don't match by name: the name embeds a date derived from
        # "now", so a re-run on a later day would duplicate the whole set.
        already = int((await e.client.list(
            "CSession", max_size=1, select="id",
            where=[{"type": "equals", "attribute": link_field.removesuffix("Id") + "Id",
                    "value": parent["id"]}],
        )).get("total") or 0)
        if already >= 4:
            await e.note(f"{key} already has {already} sessions")
            continue
        for n in range(4 - already):
            start = (now - timedelta(days=45 * (n + 1 + already))).replace(
                hour=15, minute=0, second=0, microsecond=0
            )
            name = f"{start:%Y-%m-%d} - {SHOWCASE[key]}"
            if await e.by_name("CSession", name):
                continue
            await e.note(f"add {key} session {name}")
            if not e.apply:
                continue
            await e.client.create("CSession", {
                "name": name,
                "dateStart": start.strftime(CRM_FMT),
                "dateEnd": (start + timedelta(hours=1)).strftime(CRM_FMT),
                "status": "Completed",
                "sessionType": session_type,
                link_field: parent["id"],
                "sessionNotes": "Quarterly review of the relationship and the "
                                "coming period. Sandbox training content.",
                "nextSteps": "Confirm dates for the next cohort.",
            })


async def add_contributions(e: Enricher, now: datetime) -> None:
    funder = await e.by_name("CSponsorProfile", SHOWCASE["funder"])
    if not funder:
        await e.note("! no funder record — contributions skipped")
        return
    for name, kind, status, amount, days_ago, gift in CONTRIBUTIONS:
        if await e.by_name("CContribution", name):
            continue
        await e.note(f"add contribution {name} ({status}, ${amount:,})")
        if not e.apply:
            continue
        when = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        payload = {
            "name": name,
            "contributionType": kind,
            "status": status,
            "giftType": gift,
            "amount": amount,
            # A currency amount without its companion currency 400s the create.
            "amountCurrency": "USD",
            "sponsorProfileId": funder["id"],
            "description": "Sandbox training data.",
        }
        if status == "Received":
            payload["receivedDate"] = when
        elif status in ("Committed", "Pledged"):
            payload["commitmentDate"] = when
        await e.client.create("CContribution", payload)


async def add_events(e: Enricher, now: datetime) -> None:
    for offset, name, kind, fmt, status, published in EVENTS:
        if await e.by_name("CEvent", name):
            continue
        await e.note(f"add event {name} ({status})")
        if not e.apply:
            continue
        start = (now + timedelta(days=offset)).replace(
            hour=17, minute=0, second=0, microsecond=0
        )
        await e.client.create("CEvent", {
            "name": name,
            "dateStart": start.strftime(CRM_FMT),
            "dateEnd": (start + timedelta(hours=1)).strftime(CRM_FMT),
            "format": fmt,
            "eventType": kind,
            "status": status,
            "publishToWebsite": published,
            "eventOverview": f"<p>A practical session on {name.lower()}. "
                             f"Sandbox training content.</p>",
            "description": "Sandbox training data.",
        })


async def add_notes_and_referrals(e: Enricher) -> None:
    for engagement_name, note in ENGAGEMENT_NOTES.items():
        record = await e.by_name("CEngagement", engagement_name)
        if not record:
            continue
        await e.note(f"note on {engagement_name}")
        if e.apply:
            await e.client.update("CEngagement", record["id"], {"description": note})

    for engagement_name, partner_name in REFERRALS.items():
        engagement = await e.by_name("CEngagement", engagement_name)
        partner = await e.by_name("CPartnerProfile", partner_name)
        if not (engagement and partner):
            continue
        await e.note(f"credit {engagement_name} to {partner_name}")
        if e.apply:
            await e.client.update(
                "CEngagement", engagement["id"], {"referringPartnerId": partner["id"]}
            )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="actually write")
    args = parser.parse_args()

    settings = get_settings()
    base = settings.espo_base_url or ""
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_BASE_URL is {base!r}, not the crm-test sandbox.")
        return 2

    client = EspoClient(base, settings.espo_api_key, settings.request_timeout_seconds)
    e = Enricher(client, apply=args.apply)
    now = datetime.now(timezone.utc)

    print(f"\nEnriching {base}")
    print("APPLY\n" if args.apply else "DRY RUN — nothing will be written\n")
    try:
        await add_threads(e, now)
        await add_domain_sessions(e, now)
        await add_contributions(e, now)
        await add_events(e, now)
        await add_notes_and_referrals(e)
    except EspoError as exc:
        print(f"\nSTOPPED: {exc}")
        return 1

    print(f"\n{len(e.did)} change(s).")
    if not args.apply:
        print("Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
