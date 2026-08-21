"""Seed the crm-test sandbox with fictional training data.

Run once against an empty sandbox (see ``purge_crm_records.py``), then capture
the golden baseline the nightly reset restores.  Everything here is invented:
no real client, mentor or company appears, because the audience for this
instance is every training group CBM runs.

**Shape of the training set** (Doug, 2026-08-21: one mentor at a time,
demo-led, no session creation during training — so the requirement is
read-rich, not write-heavy):

* One **primary training mentor** — ``TRAINING_MENTOR`` — with a full book of
  clients spread across the engagement lifecycle, each with session history,
  so every screen a mentor is shown has something on it.
* A **supporting roster** so the directory, the Client Administration mentor
  dropdown and the analytics panels are not bare.
* **Unassigned engagements** so Client Administration has something to assign.
* **Partners and funders** for those two management tools.

**Containment.**  Every seeded ``cbmEmail`` goes on ``--email-domain``
(default ``sandbox.cbmentors.org``), a domain with no Workspace mailboxes.
Outbound mail and calendar invites both impersonate that address by delegation,
so an accidental Save fails harmlessly instead of reaching a real person.  It
also makes the sandbox visually obvious on every screen that shows an address.
Do NOT change this to ``cbmentors.org``: the addresses would look real, and one
of them becoming real later would break containment silently.

**Logins are not created here.**  EspoCRM makes user creation admin-only, so
this attaches profiles to the fictional logins that already exist on crm-test
(``joe.mentor@``, ``matt.mentor@`` ...).  ``--check`` lists what it found.

Idempotent: every record is matched by name first, so a re-run tops up rather
than duplicating.  Read-only unless ``--apply``.

    uv run python scripts/sandbox/seed_training_data.py --check
    uv run python scripts/sandbox/seed_training_data.py
    uv run python scripts/sandbox/seed_training_data.py --apply
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

#: The mentor a trainee is shown the system as. Its login must already exist.
TRAINING_MENTOR = "Joe Mentor"

#: Profiles wired to a real login, so someone can actually sign in as them.
#: (display name, existing userName, mentorStatus, role note)
MENTORS_WITH_LOGINS: tuple[tuple[str, str, str], ...] = (
    ("Joe Mentor", "joe.mentor@cbmentors.org", "Active"),
    ("Matt Mentor", "matt.mentor@cbmentors.org", "Active"),
    ("Tony Tiger", "tony.tiger@cbmentors.org", "Active"),
    ("Wally Walrus", "wally.walrus@cbmentors.org", "Active"),
    ("Kitty Cat", "kitty.cat@cbmentors.org", "Active"),
    ("Tom Gold", "tom.gold@cbmentors.org", "Active"),
    ("Jim Beem", "jim.beem@cbmentors.org", "Approved"),
    ("Tommy Tranell", "tt@cbmentors.org", "Active"),
    ("Partner Manager", "partner.manager@cbmentors.org", "Active"),
    ("Sally Sponsor", "sally.sponsor@cbmentors.org", "Active"),
)

#: Roster volume — no login needed. These fill the directory, the assignment
#: dropdown and the analytics breakdowns.
SUPPORTING_MENTORS: tuple[tuple[str, str], ...] = (
    ("Marta Delgado", "Active"), ("Ray Okonkwo", "Active"),
    ("Priya Raman", "Active"), ("Gordon Whitfield", "Active"),
    ("Nina Barsotti", "Active"), ("Curtis Boyle", "Active"),
    ("Helena Vance", "Active"), ("Dmitri Sokolov", "Active"),
    ("Angela Fournier", "Active"), ("Marcus Ellery", "Approved"),
    ("Beatrice Nolan", "Approved"), ("Yusuf Karim", "Provisional"),
    ("Claudia Reinhart", "Candidate"), ("Owen Pryce", "Candidate"),
    ("Simone Achebe", "Paused"), ("Walter Kemp", "Inactive"),
)

#: (company, contact first, last, industry blurb, engagement status, sessions)
#: ``sessions`` is how many past sessions to write; the lifecycle spread is
#: deliberate so every grid filter and every status badge has an example.
CLIENTS: tuple[tuple[str, str, str, str, str, int], ...] = (
    # --- the training mentor's book -------------------------------------
    ("Brightline Bakehouse", "Dana", "Whitcomb", "Retail bakery, 6 staff", "Active", 7),
    ("Copperkettle Brewing", "Marcus", "Elwell", "Craft brewery and taproom", "Active", 5),
    ("Fernwood Landscaping", "Rosa", "Ibarra", "Commercial grounds maintenance", "Active", 4),
    ("Halstead Print Works", "Ted", "Grunwald", "Short-run commercial printing", "Assigned", 1),
    ("Marlow Pet Supply", "Alice", "Fenner", "Independent pet retailer", "Completed", 11),
    ("Nightjar Studios", "Devon", "Marsh", "Freelance design collective", "On-Hold", 3),
    # --- other mentors' books -------------------------------------------
    ("Ashgrove Cabinetry", "Peter", "Nyquist", "Custom millwork", "Active", 6),
    ("Riverbend Cycles", "Yolanda", "Trask", "Bicycle sales and repair", "Active", 5),
    ("Salt & Sable Catering", "Imani", "Boateng", "Event catering", "Active", 4),
    ("Tidewater Bookkeeping", "Frank", "Delacroix", "Small-business bookkeeping", "Active", 8),
    ("Verdigris Ceramics", "Nora", "Ashworth", "Studio pottery and classes", "Completed", 9),
    ("Whitmore Automotive", "Sam", "Kowalczyk", "Independent repair shop", "Dormant", 2),
    # --- waiting for Client Administration to assign ---------------------
    ("Ember Lane Florists", "Grace", "Odom", "Retail florist", "Submitted", 0),
    ("Kestrel Fabrication", "Luis", "Berganza", "Small-batch metal fabrication", "Submitted", 0),
    ("Pinehurst Tutoring", "Adaeze", "Nwosu", "In-home academic tutoring", "Submitted", 0),
    ("Quarry Street Coffee", "Miles", "Hartigan", "Coffee roaster and cafe", "Submitted", 0),
)

#: Clients belonging to the training mentor — the first six above.
TRAINING_BOOK = 6

PARTNERS: tuple[tuple[str, str, str], ...] = (
    ("Cuyahoga Small Business Alliance", "Terrence", "Boyd"),
    ("Lakeshore Community Foundation", "Meredith", "Vance"),
    ("Ironwood Credit Union", "Alan", "Petrosian"),
    ("Northgate Chamber of Commerce", "Bev", "Ahmadi"),
    ("Steelyard Workforce Partners", "Carl", "Mbeki"),
    ("Harborview Legal Clinic", "Denise", "Ferraro"),
    ("Maple Ridge Enterprise Center", "Ivan", "Petrov"),
    ("Sable Point Economic Council", "Trish", "Callahan"),
)

FUNDERS: tuple[tuple[str, str, str], ...] = (
    ("Harrowgate Family Trust", "Eleanor", "Harrowgate"),
    ("Blue Heron Foundation", "Nathan", "Kirkbride"),
    ("Sterling Mutual Bank", "Joyce", "Ambrose"),
    ("Rivermark Insurance Group", "Hal", "Sturgess"),
    ("Cedarcrest Charitable Fund", "Bianca", "Lorde"),
    ("Pilgrim Manufacturing Co.", "Roy", "Tanaka"),
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

class Seeder:
    def __init__(self, client: EspoClient, *, domain: str, apply: bool) -> None:
        self.client = client
        self.domain = domain
        self.apply = apply
        self.created: dict[str, int] = {}
        self.reused: dict[str, int] = {}

    def _tally(self, entity: str, *, new: bool) -> None:
        target = self.created if new else self.reused
        target[entity] = target.get(entity, 0) + 1

    async def find_by_name(self, entity: str, name: str) -> dict | None:
        data = await self.client.list(
            entity, select="id,name", max_size=1,
            where=[{"type": "equals", "attribute": "name", "value": name}],
        )
        rows = data.get("list", [])
        return rows[0] if rows else None

    async def upsert(self, entity: str, name: str, payload: dict) -> str | None:
        """Find by name or create. Returns the id, or None in a dry run."""
        existing = await self.find_by_name(entity, name)
        if existing:
            self._tally(entity, new=False)
            return existing["id"]
        self._tally(entity, new=True)
        if not self.apply:
            return None
        created = await self.client.create(entity, {"name": name, **payload})
        return created.get("id")

    def cbm_email(self, display_name: str) -> str:
        slug = display_name.strip().lower().replace(" ", ".")
        return f"{slug}@{self.domain}"

    def contact_email(self, first: str, last: str) -> str:
        return f"{first.strip().lower()}.{last.strip().lower()}@{self.domain}"

    async def user_ids(self) -> dict[str, str]:
        data = await self.client.list("User", select="userName", max_size=200)
        return {r.get("userName"): r["id"] for r in data.get("list", []) if r.get("userName")}


# --------------------------------------------------------------------------
# stages
# --------------------------------------------------------------------------

async def seed_mentors(s: Seeder, users: dict[str, str]) -> dict[str, str]:
    """Mentor profiles, each with a linked Contact. Returns name -> profile id."""
    profiles: dict[str, str] = {}
    missing: list[str] = []

    entries: list[tuple[str, str | None, str]] = [
        (name, username, status) for name, username, status in MENTORS_WITH_LOGINS
    ] + [(name, None, status) for name, status in SUPPORTING_MENTORS]

    for name, username, status in entries:
        first, _, last = name.partition(" ")
        contact_id = await s.upsert("Contact", name, {
            "firstName": first, "lastName": last or first,
            "emailAddress": s.contact_email(first, last or first),
            "cContactType": ["Mentor"],
        })
        payload: dict = {
            "mentorStatus": status,
            "acceptingNewClients": status in {"Active", "Approved"},
            "cbmEmail": s.cbm_email(name),
            "mentorCodeAccepted": True,
            "ethicsAgreementAccepted": True,
            "description": "Fictional sandbox mentor — training data only.",
        }
        if contact_id:
            payload["contactRecordId"] = contact_id
        if username:
            user_id = users.get(username)
            if not user_id:
                missing.append(username)
            else:
                # Dual-write: these entities use Multiple Assigned Users, and
                # resolve_manager_profile matches membership over BOTH fields.
                payload["assignedUserId"] = user_id
                payload["assignedUsersIds"] = [user_id]
        profile_id = await s.upsert("CMentorProfile", name, payload)
        if profile_id:
            profiles[name] = profile_id

    if missing:
        print(f"  ! no login found for: {', '.join(missing)} — profile left unassigned")
    return profiles


async def seed_clients(s: Seeder, profiles: dict[str, str], users: dict[str, str]) -> None:
    """Company -> Contact -> CClientProfile -> CEngagement, plus sessions."""
    mentor_names = [name for name, _, _ in MENTORS_WITH_LOGINS]
    now = datetime.now(timezone.utc)

    for index, (company, first, last, blurb, status, session_count) in enumerate(CLIENTS):
        account_id = await s.upsert("Account", company, {
            "cCompanyType": ["Client"],
            "description": blurb,
            "emailAddress": f"info@{company.split()[0].lower()}.{s.domain}",
        })
        contact_name = f"{first} {last}"
        contact_id = await s.upsert("Contact", contact_name, {
            "firstName": first, "lastName": last,
            "emailAddress": s.contact_email(first, last),
            "cContactType": ["Client"],
            **({"accountId": account_id} if account_id else {}),
        })
        profile_name = f"{company} — Client Profile"
        client_profile_id = await s.upsert("CClientProfile", profile_name, {
            **({"linkedCompanyId": account_id} if account_id else {}),
            **({"clientcontactId": contact_id} if contact_id else {}),
        })

        # Who owns it: the training mentor takes the first TRAINING_BOOK,
        # the rest spread across the other logins. Submitted ones stay free.
        mentor_name: str | None = None
        if status != "Submitted":
            mentor_name = (
                TRAINING_MENTOR if index < TRAINING_BOOK
                else mentor_names[index % len(mentor_names)]
            )
        mentor_profile_id = profiles.get(mentor_name) if mentor_name else None

        engagement_name = f"{company} — Mentoring"
        payload: dict = {
            "engagementStatus": status,
            "mentoringNeedsDescription": (
                f"{blurb}. Looking for help with growth planning, pricing and "
                "cash-flow forecasting."
            ),
            **({"clientOrganizationId": account_id} if account_id else {}),
            **({"engagementClientId": client_profile_id} if client_profile_id else {}),
            **({"primaryEngagementContactId": contact_id} if contact_id else {}),
        }
        if mentor_profile_id:
            assigned = now - timedelta(days=300 - index * 7)
            payload["mentorProfileId"] = mentor_profile_id
            # engagementAssignedDate is a DATETIME (not a date) — a bare
            # YYYY-MM-DD is rejected as a validation failure, not coerced.
            payload["engagementAssignedDate"] = assigned.strftime(CRM_FMT)
            payload["engagementStartDate"] = assigned.strftime("%Y-%m-%d")
            if session_count:
                payload["lastContactDate"] = (
                    now - timedelta(days=30)
                ).replace(minute=0, second=0, microsecond=0).strftime(CRM_FMT)
        # The mentor's login must hold the record, or their own-scope role
        # cannot read it — the assignedUsers stamp is what grants that.
        login = next((u for n, u, _ in MENTORS_WITH_LOGINS if n == mentor_name), None)
        if login and users.get(login):
            payload["assignedUserId"] = users[login]
            payload["assignedUsersIds"] = [users[login]]
        engagement_id = await s.upsert("CEngagement", engagement_name, payload)

        if session_count and engagement_id:
            await seed_sessions(s, engagement_id, company, session_count, now, users, login)


async def seed_sessions(
    s: Seeder, engagement_id: str, company: str, count: int,
    now: datetime, users: dict[str, str], login: str | None,
) -> None:
    """Session history walking backwards from a month ago, monthly-ish."""
    for n in range(count):
        # Business hours in Eastern, not whatever time the seed happened to run:
        # 13/15/17/19 UTC is 9am/11am/1pm/3pm EDT. A demo where every meeting
        # sits at 1am is a distraction on every screen that shows a time.
        start = (now - timedelta(days=30 * (n + 1))).replace(
            hour=13 + 2 * (n % 4), minute=0, second=0, microsecond=0
        )
        name = f"{start:%Y-%m-%d} - {company}"
        payload: dict = {
            "dateStart": start.strftime(CRM_FMT),
            "dateEnd": (start + timedelta(hours=1)).strftime(CRM_FMT),
            "status": "Completed",
            "sessionType": "Client Session",
            "engagementId": engagement_id,
            "sessionNotes": (
                "Reviewed the month's numbers and agreed next steps. "
                "Sandbox training content — not a real meeting."
            ),
            "nextSteps": "Draft a 90-day cash-flow forecast before the next session.",
        }
        if login and users.get(login):
            payload["assignedUserId"] = users[login]
            payload["assignedUsersIds"] = [users[login]]
        await s.upsert("CSession", name, payload)

    # One upcoming session so the Next-session callout on Overview is alive.
    upcoming = (now + timedelta(days=9)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    payload = {
        "dateStart": upcoming.strftime(CRM_FMT),
        "dateEnd": (upcoming + timedelta(hours=1)).strftime(CRM_FMT),
        "status": "Scheduled",
        "sessionType": "Client Session",
        "engagementId": engagement_id,
    }
    if login and users.get(login):
        payload["assignedUserId"] = users[login]
        payload["assignedUsersIds"] = [users[login]]
    await s.upsert("CSession", f"{upcoming:%Y-%m-%d} - {company}", payload)


async def seed_partners(s: Seeder, profiles: dict[str, str]) -> None:
    manager = profiles.get("Partner Manager")
    for company, first, last in PARTNERS:
        account_id = await s.upsert("Account", company, {
            "cCompanyType": ["Partner"],
            "description": "Fictional sandbox partner — training data only.",
        })
        contact_id = await s.upsert("Contact", f"{first} {last}", {
            "firstName": first, "lastName": last,
            "emailAddress": s.contact_email(first, last),
            **({"accountId": account_id} if account_id else {}),
        })
        await s.upsert("CPartnerProfile", company, {
            **({"partnerCompanyId": account_id} if account_id else {}),
            **({"primaryPartnercontactId": contact_id} if contact_id else {}),
            **({"partnerManagerId": manager} if manager else {}),
        })


async def seed_funders(s: Seeder, profiles: dict[str, str]) -> None:
    manager = profiles.get("Sally Sponsor")
    for company, first, last in FUNDERS:
        account_id = await s.upsert("Account", company, {
            "cCompanyType": ["Sponsor"],
            "description": "Fictional sandbox funder — training data only.",
        })
        contact_id = await s.upsert("Contact", f"{first} {last}", {
            "firstName": first, "lastName": last,
            "emailAddress": s.contact_email(first, last),
            **({"accountId": account_id} if account_id else {}),
        })
        await s.upsert("CSponsorProfile", company, {
            **({"sponsorCompanyId": account_id} if account_id else {}),
            **({"sponsorContactId": contact_id} if contact_id else {}),
            **({"sponsorManagerId": manager} if manager else {}),
        })


# --------------------------------------------------------------------------

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="actually create records")
    parser.add_argument("--check", action="store_true",
                        help="report the logins available and exit")
    parser.add_argument("--email-domain", default="sandbox.cbmentors.org",
                        help="domain for every seeded address (must have NO mailboxes)")
    args = parser.parse_args()

    settings = get_settings()
    base = settings.espo_base_url or ""
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_BASE_URL is {base!r}, not the crm-test sandbox.")
        return 2
    if args.email_domain.strip().lower() == "cbmentors.org":
        print("REFUSING: seeding real @cbmentors.org addresses would break containment.")
        return 2

    client = EspoClient(base, settings.espo_api_key, settings.request_timeout_seconds)
    seeder = Seeder(client, domain=args.email_domain, apply=args.apply)
    users = await seeder.user_ids()

    if args.check:
        print(f"\n{len(users)} logins on {base}\n")
        for name, username, _ in MENTORS_WITH_LOGINS:
            mark = "ok  " if username in users else "MISSING"
            print(f"  [{mark}] {name:20} {username}")
        return 0

    print(f"\nSeeding {base}")
    print(f"addresses on @{args.email_domain}")
    print("APPLY — records will be created\n" if args.apply
          else "DRY RUN — nothing will be created\n")

    try:
        profiles = await seed_mentors(seeder, users)
        await seed_clients(seeder, profiles, users)
        await seed_partners(seeder, profiles)
        await seed_funders(seeder, profiles)
    except EspoError as exc:
        print(f"\nSTOPPED: {exc}")
        return 1

    print("  created:", dict(sorted(seeder.created.items())) or "nothing")
    print("  reused: ", dict(sorted(seeder.reused.items())) or "nothing")
    if not args.apply:
        print("\nRe-run with --apply to create.")
    else:
        print(f"\nDone. Sign in as the training mentor's login to check "
              f"({TRAINING_MENTOR}), then capture the golden baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
