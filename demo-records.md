# Demo records — what to open, for each kind of user

Last Updated: 10-20-26 00:20 · Revision 1.1 — change log at the end.

The training sandbox is **crm-test**: the app at
`https://cbm-client-intake-svxs3.ondigitalocean.app` over the CRM at
`https://crm-test.clevelandbusinessmentors.org`. Every record in it is
invented. It is restored to a fixed state overnight, so the screens below look
the same at the start of every session.

This page names, for each kind of user, **the one login to use and the one
record to open** — the record deliberately built to have something on every
tab. Everything around it is thinner on purpose: that is what makes the
showcase record look normal rather than staged.

This is the **reference**. For running an actual session — who to sign in as,
what to click in what order, what to tell the room — use `training-guide.md`;
it links here rather than repeating any of it. Setup and mechanics live in
`SANDBOX-RESET.md`. The data is produced by
`scripts/sandbox/seed_training_data.py` and
`scripts/sandbox/enrich_training_data.py`; if you change what a demo shows,
change it there so it survives the nightly restore.

## Signing in

Sign in at the **app**, not the CRM — that is where the tools are. Passwords
are set in the CRM by an administrator; the sandbox addresses are not real
mailboxes, so "forgot password" and any emailed credentials will not arrive.

| User type | Login | Lands on |
|---|---|---|
| Mentor | `joe.mentor@cbmentors.org` | Client Management, My Mentor Profile, Directories, My Email |
| Client Administration | `kitty.cat@cbmentors.org` | Client Administration |
| Mentor Administration | `mentoradmin@cbmentors.org` | Mentor Administration |
| Partner Management | `partner.manager@cbmentors.org` | Partner Management |
| Funder Management | `sally.sponsor@cbmentors.org` | Funder Management |
| Submission Admin | `mark.marketing@cbmentors.org` | Submission Admin |

Every address in the sandbox ends `@sandbox.cbmentors.org`, which has no
mailboxes behind it. That is deliberate: nothing anyone clicks can send a real
email or put an invitation in a real calendar. It is also the quickest way to
tell at a glance that you are not in production.

---

## Mentor — **Joe Mentor**

**Open: `Brightline Bakehouse — Mentoring`** in Client Management.

Joe carries a book of seven clients across the lifecycle, so the grid itself
demonstrates status filtering before you open anything: three Active, one
Assigned, one On-Hold, two Completed. Brightline is the rich one.

| Tab | What is there |
|---|---|
| Overview | Facts rail, notes feed, the company peek, and a **Next-session callout** with a real upcoming meeting |
| Details | Every field populated — company, client profile and engagement all complete, including the address block for the paste-parser |
| Sessions | **8 sessions** — 7 completed going back through the year, 1 scheduled ahead, with attendees on the recent three |
| Communications | A **5-message thread**, "Cash-flow forecast for the new oven", alternating inbound and outbound |
| Contacts | Dana Whitcomb — phone, full address, job title, and all three agreements accepted so the badge reads complete |
| Co-mentor | **Matt Mentor** is an additional mentor, so co-mentor visibility has a live example |
| Referring partner | Credited to **Cuyahoga Small Business Alliance** |
| Analytics | The engagement dashboard, computed live from the above |

Staff notes are on five engagements (the Notes column in Client
Administration), so Brightline also shows the internal-note pattern —
`Owner is expanding to a second site. Mentor asked for a finance-side
co-mentor.`

Also worth showing on this login: **My Mentor Profile**, which is filled in
completely for Joe — bio, summary, skills, languages, industry experience,
dues, training and background-check dates, a Zoom link, a profile photo, and a
Contact carrying his phone, address and birthday. The live preview renders as a
finished public mentor page rather than a shell.

Behind that record: Joe also co-mentors `Ashgrove Cabinetry — Mentoring`,
manages one partner (Maple Ridge Enterprise Center) and one funder (Cedarcrest
Charitable Fund), and is registered for a past event — so the reverse links on
his profile are populated too.

## Client Administration — **Kitty Cat**

**Open: the four `Submitted` engagements** — Ember Lane Florists, Kestrel
Fabrication, Pinehurst Tutoring, Quarry Street Coffee.

These are the only unassigned engagements, so they are what the Assign flow is
demonstrated on. Nine mentors qualify for the dropdown (Active, accepting new
clients, and holding a login), which is enough to show filtering and to make
the choice look real.

For **Reassign** and **Repair assignment**, use an already-assigned row —
`Halstead Print Works — Mentoring` is Assigned with a single session, so the
before-and-after is easy to see. The Notes column is populated on five rows.

In **Review Mentors**, the eight mentors who hold clients carry a **Last
Assigned** date and the rest read "—". Sorting that column ascending is the
demo: the never-assigned mentors come to the top, then the longest-waiting.
**Tony Tiger** (9 days) and **Wally Walrus** (24 days) are the near end — they
are also the only two rows with **Assigned (30d)** above zero — and Tommy
Tranell at eight months is the far end. Assign one of the Submitted rows in the
room and watch today's date land on that mentor, which is the whole point of the
column.

Their two clients, **Larkspur Provisions** (Pending Acceptance) and
**Bellweather Signage** (Assigned), are the only ones with no session history.
That is not a gap: they are what a client looks like in the first weeks, before
the first meeting, and the sandbox has nothing else at that stage.

## Mentor Administration — **Mentor Admin**

**Open: `Joe Mentor`, then `Claudia Reinhart`.**

The roster is 26 profiles, and the completeness badge is the point of the
contrast:

- **Joe Mentor** and **Matt Mentor** read **Complete** — linked Contact, all
  three sign-offs, background check, a CBM email, and the same login User on
  both the profile and its Contact.
- **Claudia Reinhart** and **Owen Pryce** (Candidates) and **Yusuf Karim**
  (Provisional) read **Incomplete**, naming exactly what is missing: training
  and terms not confirmed.
- Nine more read Incomplete for a different reason — Active with no login
  User — which is the case the roster-wide **Update Mentor Status** sweep is
  there to surface.

Statuses across the roster span Active, Approved, Provisional, Candidate,
Paused and Inactive, so the status filter has something to do.

## Partner Management — **Partner Manager**

**Open: `Cuyahoga Small Business Alliance`.**

| Tab | What is there |
|---|---|
| Overview | Facts rail, notes, and the Discussion pane |
| Details | Partnership panel with the company and manager pickers |
| Sessions | **4 quarterly meetings** |
| Communications | A **4-message thread**, "Spring referral cohort" |
| Referred Clients | **2 engagements** credited to this partner — Ashgrove Cabinetry and Riverbend Cycles |
| Events | **2 events** this partner is linked to — `Hiring Your First Employee` (Terrence Boyd presents) and `Marketing on a Shoestring` — with registered / attended / became-a-client counts |
| Contacts | Terrence Boyd, with Make primary |

The grid lists all 8 partners, so the search and filter behaviour is visible
before you open anything. A second partner, Northgate Chamber of Commerce, also
has a referred client, which is useful for showing that referrals are not
unique to one record.

## Funder Management — **Sally Sponsor**

**Open: `Harrowgate Family Trust`.**

| Tab | What is there |
|---|---|
| Overview | Facts rail, notes, Discussion pane |
| Details | Funding panel with the company and manager pickers |
| Sessions | **4 quarterly meetings** |
| Communications | A **3-message thread**, "Renewal of the 2027 grant" |
| Contributions | **5 gifts, $63,700 total**, deliberately across the lifecycle |
| Events | **2 events** this funder is linked to — `Pricing for Profit` (held, with an attended registration) and `Hiring Your First Employee` (upcoming) |
| Contacts | Eleanor Harrowgate |

The contributions are the reason this is the funder showcase — Received,
Committed and Pledged are all represented, across Grant, Sponsorship and
Donation, including an In-Kind gift:

| Gift | Type | Status | Amount |
|---|---|---|---|
| 2027 General Operating Grant | Grant | Committed | $30,000 |
| 2026 General Operating Grant | Grant | Received | $25,000 |
| Annual Dinner Sponsorship | Sponsorship | Received | $5,000 |
| Spring Appeal Gift | Donation | Pledged | $2,500 |
| Mentor Training Materials | Donation (In-Kind) | Received | $1,200 |

## Workspace Directories — any Mentor Team login

**Open: Mentors → `Joe Mentor`.**

The read-only mentor profile page is the warmest screen in the product and Joe
is the only profile filled in enough to do it justice — hero, professional
lane, "Get to know them", availability. The Companies, Contacts and Partners
grids are all populated (30 companies, 56 contacts, 8 partners).

## Events — `/events`

Five published workshops: two held (`Pricing for Profit`,
`Reading Your Own Financials`) and three upcoming (`Marketing on a Shoestring`,
`Hiring Your First Employee`, `AI Tools for Small Business`). Enough for the
calendar and the recorded library to both render. Every event carries curated
topics.

**Open: `Hiring Your First Employee`** — the event showcase (since 10-11-26).
It has every relationship an event can hold:

| Where | What is there |
|---|---|
| Presenters group | **Joe Mentor** (a mentor — his biography, title and photo were copied from his profile when he was added) and **Terrence Boyd** (the partner's contact, a guest — title and company from his Contact), biographies switched on |
| Sponsorship group | Partner **Cuyahoga Small Business Alliance**, funder **Harrowgate Family Trust** — the same event appears on both showcase records' Events tab |
| Topics | Leadership & People, Operations |

Two more events show the variations: `Pricing for Profit` has one mentor
presenter (Matt Mentor), a second partner (Northgate Chamber of Commerce) and
the funder; `Marketing on a Shoestring` has a **guest presenter who exists
only as a `Presenter`-typed Contact** (Lena Okafor, created the way the
editor's "new person" path creates one), the showcase partner and a second
funder (Blue Heron Foundation). All of it is seeded by
`scripts/sandbox/enrich_training_data.py` (`EVENT_SHOWCASE`) and survives the
nightly reset only because the sandbox was re-baselined after it ran — the
presenter table and the partner-event link table are newer than the previous
baseline and were being truncated every night (`SANDBOX-RESET.md`).

Note that `/events` is **live on crm-test but off in production**, so treat it
as a preview rather than something staff will use on Monday.

---

## Campaign Management — **Mark Marketing**

Sign in as `mark.marketing@cbmentors.org`. Six campaigns, one of each kind,
and seventeen leads, seeded by `scripts/sandbox/seed_outreach_data.py`
(since 10-20-26). The campaigns' links are put back by the nightly reset
with fixed codes (`campaigns/sandbox_demo.py`), so every address below works
every morning.

**Open: `September 2026 filings — Postcard`** — a finished postcard run,
partner Cuyahoga Small Business Alliance. Its five cards show every state a
card reaches:

| Card | Lead | What happened | Card address |
|---|---|---|---|
| 1 | Lakeshore Tile & Stone | Delivered, scanned twice, then converted: Company **Lakeshore Tile & Stone** and Contact **Rosa Medina**, both at Engaged | `/c/sbxcard2/sbxscan23456` |
| 2 | Marigold Pet Grooming | Delivered, never scanned | `/c/sbxcard2/sbxscan23457` |
| 3 | Northcoast Drone Services | Returned — the lead's address is Dead | `/c/sbxcard2/sbxscan23458` |
| 4 | Tremont Coffee Roasters | Delivered, scanned once, still a lead | `/c/sbxcard2/sbxscan23459` |
| 5 | Ohio City Bike Works | Sent, no delivery report yet | `/c/sbxcard2/sbxscan2345a` |

A card address opens the landing page for that card, signed out. Scanning
adds to the card's count until the night.

The other five campaigns:

| Campaign | Kind and status | What to do with it |
|---|---|---|
| `November 2026 filings — Postcard` | Postcard, Draft | Press **Build the list**: it finds Gordon Square Florist, Detroit Shoreway Signs and Collinwood Records, and leaves out September's five (one card per business, ever), then sign off. The dry-run vendor prints nothing |
| `Fall follow-up calls` | Call, Running, called by the Marketing Admin Team and the Mentor Team | The Calls page lists Marigold Pet Grooming and Gordon Square Florist to call. Three calls are already recorded: no answer (Ohio City Bike Works), interested (Slavic Village Bakery, converted to a Company and Contact Pavel Novak) and declined (Kamm's Corners Hardware) |
| `Marketing on a Shoestring — Email` | Email, Complete | Event Marketing on a Shoestring; link `/c/sbxevnt7` opens the webinar |
| `Webinar reminder — Text` | Text, Draft | The wording carries STOP and the link `/c/sbxtext8`; sign-off works, and the dry-run text client sends nothing |
| `LinkedIn — Spring workshops` | Social media, Running, LinkedIn | Partner Northgate Chamber of Commerce, event Hiring Your First Employee, three links: `/c/sbxweb23` (programme), `/c/sbxmntr4` (request a mentor), `/c/sbxask56` (ask a question). Engagement Riverbend Cycles — Mentoring came through it; contact Dana Okoro (an information request, at Opportunity) too |

**The leads**, on the Leads grid and the Review tab: four Unqualified
(Detroit Shoreway Signs and Collinwood Records have no website; Hannah
Kowalski, from a list, has no email; Brightline Bakehouse is a Duplicate of
the company of that name), nine Qualified, one Disqualified (Quick Cash
Title Loans, with its reason), three Converted. Each way a lead stops is
there once: Duplicate, Do Not Contact (Euclid Avenue Pawn), Declined (Kamm's
Corners Hardware) and Stale (Clark-Fulton Auto Glass).

The same seeder adds two links the reset was also emptying: engagement
`Salt & Sable Catering — Mentoring` has **two referring partners**
(Northgate Chamber of Commerce and Cuyahoga Small Business Alliance), and
**Joe Mentor is an additional manager** on the partner and funder showcase
records.

---

## How complete the showcase records are

`scripts/sandbox/audit_showcase_records.py` measures this against the CRM's own
field definitions rather than a hand-kept list, so a field the CRM team adds
tomorrow shows up as a new gap. Current state across the eight showcase
records: **194 of 194 fields filled, 62 of 63 relationships populated.**

The audit knows which blanks are *correct* and excludes them — an Active mentor
has no `departureReason`, a client company carries no sponsorship fields, and
`nextSessionDateTime` is deliberately left empty because the app derives the
next session from real sessions and a stored value shows as a ghost. The one
genuine gap is a mentor CV attachment, which is not worth fabricating.

Run it after any re-seed:

```bash
uv run python scripts/sandbox/audit_showcase_records.py
```

## What has no demo data yet

Be aware of these before you build a session around them — they are empty, and
they will look broken rather than "not covered".

| Feature | Why it is empty |
|---|---|
| **Documents** tab, on every record | Drive uploads run as the service account, and crm-test still points at the **production** shared drive. Seeding documents would write training files into CBM's real Drive. Needs a sandbox shared drive first. |
| **Submission Admin** (`/ops`) | The queue lives in the app's own database, which was cleared. Refilling it means posting the public intake forms so the whole capture pipeline runs — worth doing, not yet done. |
| **Discussion pane** on partner and funder Overview | App-only comment rows, reachable through the app as a signed-in user rather than over the CRM API. |
| **Session transcripts** and **My Email** | Both depend on integrations that are deliberately inert in the sandbox. |

None of these is hard to add. If a training session needs one, say so and it
can be seeded before the next baseline is captured.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-20-26 00:20 | Claude (Claude Code) | Campaign Management section: the six demo campaigns, the five postcard card addresses, the leads, two referring partners and the additional managers. Revision control added. |
| 1.0 | — | — | The page before revision control. |
