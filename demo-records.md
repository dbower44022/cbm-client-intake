# Demo records — what to open, for each kind of user

The training sandbox is **crm-test**: the app at
`https://cbm-client-intake-svxs3.ondigitalocean.app` over the CRM at
`https://crm-test.clevelandbusinessmentors.org`. Every record in it is
invented. It is restored to a fixed state overnight, so the screens below look
the same at the start of every session.

This page names, for each kind of user, **the one login to use and the one
record to open** — the record deliberately built to have something on every
tab. Everything around it is thinner on purpose: that is what makes the
showcase record look normal rather than staged.

Setup and mechanics live in `SANDBOX-RESET.md`. The data is produced by
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
| Details | The full editable field set, including the address block for the paste-parser |
| Sessions | **8 sessions** — 7 completed going back through the year, 1 scheduled ahead |
| Communications | A **5-message thread**, "Cash-flow forecast for the new oven", alternating inbound and outbound |
| Contacts | Dana Whitcomb, with role chips and the agreements badge |
| Analytics | The engagement dashboard, computed live from the above |

Staff notes are on five engagements (the Notes column in Client
Administration), so Brightline also shows the internal-note pattern —
`Owner is expanding to a second site. Mentor asked for a finance-side
co-mentor.`

Also worth showing on this login: **My Mentor Profile**, which is fully filled
in for Joe — 22 years' experience, industry sector, areas of expertise,
mentoring focus areas and a personal-interests line — so the live preview
renders as a complete public mentor page rather than a shell.

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
calendar and the recorded library to both render.

Note that `/events` is **live on crm-test but off in production**, so treat it
as a preview rather than something staff will use on Monday.

---

## What has no demo data yet

Be aware of these before you build a session around them — they are empty, and
they will look broken rather than "not covered".

| Feature | Why it is empty |
|---|---|
| **Documents** tab, on every record | Drive uploads run as the service account, and crm-test still points at the **production** shared drive. Seeding documents would write training files into CBM's real Drive. Needs a sandbox shared drive first. |
| **Submission Admin** (`/ops`) | The queue lives in the app's own database, which was cleared. Refilling it means posting the public intake forms so the whole capture pipeline runs — worth doing, not yet done. |
| **Discussion pane** on partner and funder Overview | App-only comment rows, reachable through the app as a signed-in user rather than over the CRM API. |
| **Co-mentors** | No engagement has an additional mentor, so co-mentor visibility and the swap-merge on reassignment have no example. |
| **Session transcripts** and **My Email** | Both depend on integrations that are deliberately inert in the sandbox. |

None of these is hard to add. If a training session needs one, say so and it
can be seeded before the next baseline is captured.
