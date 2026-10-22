# sessions/ — Client, Partner and Funder Management

Last Updated: 10-22-26 12:10 · Revision 1.2

Detail for the session engine behind Client Management (`/mentorsessions`), Partner Management (`/partnersessions`) and Funder Management (`/sponsorsessions`): the grids, every record tab, quick add, managers and co-mentors, and the traps of this package.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## Session Management — `/mentorsessions`, `/partnersessions`, `/sponsorsessions`

User-facing titles: **Client Management**, **Partner Management**, **Funder
Management**. Packages, routes, slugs and team gates are unchanged. "Funder" is
display wording only — the CRM entities stay `CSponsorProfile` etc.

**One configurable engine, three team-gated routes.** Managers review the
records they own and record meetings as **`CSession`** records — one entity with
the parent link swapped. The domains differ only by a per-domain
`sessions/config.py:DomainConfig`; the whole feature is one engine
(`sessions/service.py`), one router factory (`sessions/router.make_router`), and
one shared frontend that derives its domain from the first segment of its URL.

| slug | parent | owned-records link on the user's `CMentorProfile` | co-mentors |
|---|---|---|---|
| `mentorsessions` | `CEngagement` | `engagements1` (+ `engagements` for co-mentored) | yes |
| `partnersessions` | `CPartnerProfile` | `managedPartners` | no |
| `sponsorsessions` | `CSponsorProfile` | `managedSponsors` | no |

- **Managers are `CMentorProfile` records** — the one whose `assignedUser` is
  their login. `resolve_manager_profile` matches `assignedUser` **in Python,
  never a `where` on `assignedUserId`** (prod's field ACL forbids it). A record
  assigned to a *duplicate unlinked* profile is invisible here — a recurring
  data trap ([[crm-test-duplicate-mentor-profiles]],
  [[sessions-manager-profile-must-be-assigned]]).
- **Partner and Funder grids list ALL records** (`DomainConfig.list_all`), not
  just owned ones — the user's CRM ACL is the gate. This also means those
  domains never read `CMentorProfile` for the list, which is what fixed the
  sponsor-team 403.
- **Detail tabs**: Overview · Details · Sessions · Communications · Documents,
  plus Contributions (funder only), Referred Clients (partner only), and
  Analytics (when enabled). Each optional tab is gated by a `DomainConfig` field
  that controls **both the tab and the endpoint registration** — a router that
  doesn't own the feature never registers its routes.
- **The Overview notes editor follows the field's LIVE CRM type** (v0.252.0,
  `service.live_notes_type`): wysiwyg ⇒ the rich editor, text ⇒ the plain
  box. Funder Notes (`CSponsorProfile.description`) is wysiwyg on crm-test
  and production since 10-11-26 (one command per instance,
  `scripts/convert_notes_wysiwyg.sh`; Boston owed) —
  `csponsorprofile-description-wysiwyg-crm-handoff.md` (Doug 2026-10-11:
  "the funder notes should be wysiwyg").
- **Overview** is a facts rail + notes feed with drag splitters, an aggregated
  Company peek, a Next-session callout with a Start/Open button, and (partner +
  funder) a **Discussion pane** — an app-only, append-only, attributed comment
  stream in the `record_comment` Postgres table, **never written to the CRM or
  shown to the partner/funder**. Record notes edit in place from the Overview.
  Every scalar rail fact renders "—" when empty rather than vanishing (an empty
  slot that disappears reads as a missing feature).
- **Details** renders from live CRM metadata (editable scalars, humanized
  labels) in curated, packed, full-width group panels. Curated lists control
  what appears: `DETAILS_LAYOUTS`, `DETAILS_REMOVED_FIELDS`, and
  `_ENTITY_LINK_FIELDS` (belongsTo links render **only** if curated there — the
  metadata sweep covers scalars only). Permission-aware down to per-record
  ownership. The PUT is entity-allowlisted (`cfg.details_entities` + Contact,
  else 404).
- **Re-assigning a record's manager happens on the Details tab**, through those
  curated link pickers — `CPartnerProfile.partnerManager` on the Partnership
  panel and `CSponsorProfile.cBMSponsorManager` on the Funding panel (v0.197.x).
  Each is the belongsTo behind the `manager_owned_link` reverse
  (`managedPartners` / `managedSponsors`), so it decides **whose** record this
  is — which is why it went unnoticed for so long that the grid displayed it and
  nothing could change it. Options are the mentor profiles the signed-in user
  can read; a forbidden list degrades the picker to read-only rather than
  breaking the tab, and a stored manager outside the list stays selected so a
  save can never silently drop them. **Mentor has no equivalent** — an
  engagement's mentor is re-assigned in Client Administration, deliberately
  (`DETAILS_LAYOUTS` keeps `mentorProfileName` read-only there).
- **The record's COMPANY is set on the Details tab too** (v0.198.0), the same
  way: `partnerCompany` / `sponsorCompany` as curated link pickers leading the
  Partnership and Funding panels, gated per domain by
  `DomainConfig.company_link_editable` (mentor has none — an engagement's
  company resolves through the client profile via `company_fallback`). These
  pickers also **create** the company, because a partner/funder the CRM holds no
  Account for cannot be repaired by picking: "+ New company" find-or-creates it
  (`details.create_company` → `service._find_or_create_company`, so a same-named
  company is reused and `cCompanyType` merged in), and the panel's **Save**
  writes the link — creating and linking stay separate so there is exactly one
  write path to the link. `POST /records/{id}/company` is **not** gated by
  `RECORD_QUICK_ADD`: it repairs records that already exist.
- **A company can carry MANY partner profiles.**
  `Account.cCompanyPartnerProfile` was `hasOne` until 2026-08-14, so linking a
  company to a second partner profile silently *moved* it off the first — that
  is how a live partner record lost its company to a duplicate entered nine
  hours later. Doug's ruling: a partnership is with a programme inside an
  organisation as often as with the organisation itself, so one company, many
  partner records. Recreated as many-to-one on prod 2026-08-14 and crm-test
  2026-08-15, verified in both; no application code was involved.
  **Funders followed on 2026-08-16** — `sponsorCompany` ↔
  `Account.cSponsorProfiles`, both environments, all links intact, proven by a
  two-funders-one-company test on crm-test.
- **Clients are the exception, and it is deliberate.** Doug's ruling
  (2026-08-16): **a client never has two client business profiles**, so
  `CClientProfile.linkedCompany` staying `hasOne` is *correct* — do not "fix" it
  to match partners and funders. The guard that makes the model safe lives in
  the app: `forms/client_intake/orchestrator._find_or_create_client_profile`
  find-or-creates the profile **matched on `linkedCompanyId`**, because an
  unconditional create silently moved the Account and contact off the existing
  hub (twice in production, 2026-07-17 and 2026-07-27). Verified clean
  2026-08-16: all 73 prod client profiles have a company and none share one.
- **Events (partner and funder, `sponsored_events_link`)** — the Events tab
  just before Communications (v0.239.0): every event linked to the record,
  with registered / attended / became-a-client counts and totals, all from
  `events/reporting.sponsor_rollup` so every screen agrees. "Became a
  client" is the programme's conversion rule scoped to one event, and never
  a separate "requested a mentor" count (Doug's ruling 2026-10-07). The
  endpoint feature-detects the reverse link and answers `available: false`
  with a reason on a CRM without it; an unreadable count renders "—", never 0.
  **The counts compute under the org-wide API key** after the user's own read
  of the parent record gates the tab — the Partner Manager and Sponsor Manager
  roles hold no event, registration or engagement access, and the numbers are
  aggregates (the directory-availability precedent).
- **Grants (funder only, `grants_link`)** — the Grants tab: awards, their
  deliverables, and later their funder reports. The **grant is the hub**:
  `CContribution` rows become its payments and deliverables its obligations, and
  the two are **siblings under it, never a chain**. Client attribution lives on
  the grant (`fundedEngagements`), so a renewal starts clean. Deliverable
  progress math lives in ONE place (`service.deliverable_progress`) — a stored
  status always beats the arithmetic, and a Narrative deliverable has no
  percentage at all. Gated by `GRANTS_ENABLED` **and** CRM feature detection,
  which fails closed. Plan + rulings: `prds/grant-management-plan.md`.
- **Partner and Funder can be CREATED here** (`RECORD_QUICK_ADD`, off by
  default): the grid's "+ Add partner" / "+ Add funder" runs the same
  Account → Contact → profile sequence the public intake forms do, as the
  signed-in user. `DomainConfig.create_spec` gates both the button and the
  routes (mentor has none — engagements arrive through intake), and the spec is
  BOTH the form layout and the write whitelist. Same dedupe policy as intake:
  a same-named company / same-email contact is reused and null-filled, never
  duplicated; a reused company gains the type value merge-only. **A website,
  when entered, must agree with the match** (v0.237.0, Doug's ruling
  2026-10-07): a same-named company at a *different* web address is a
  different company, and the save is **refused with the existing company
  named** — never a second same-named Account, which would make every
  name-based match in the CRM ambiguous. Same rule on the Details tab's
  "+ New company" picker (shared function). **Since v0.254.0 the quick-add's
  Company is a picker** (every company under the org-wide key, website
  beside the name, "+ New company…" for the typed path): a chosen company's
  id rides as `companyId` and skips the match and the website rule — the
  way to make a company that is both a partner and a funder. **A picked
  company with an empty contact block inherits the primary contact of its
  record in the other application** (Partner Management ↔ Funder
  Management; v0.257.0, Doug 2026-10-14): the newest such record naming
  one wins, read under the org key, contact stamped merge-only. Compared through
  `core/crm_upsert.website_key` (scheme, `www.`, case, trailing slash
  ignored; the path counts). No stored website ⇒ match and null-fill it.
  **The new contact is owned by its creator and the domain team** (v0.249.0,
  Doug's ruling 2026-10-09): `_create_quick_contact` stamps a NEW contact with
  `assignedUserId` + `assignedUsersIds` and `teamsIds`, exactly as the
  profile is. Without it EspoCRM refuses the create for a role whose
  Assignment Permission is *not-set* ("Assignment failure: assigned user or
  team not allowed" — the Sponsor Manager Role on both CRMs), and a
  team-read role could never see the contact it just made. The Partner
  Manager Role only passed because it is *all*/*all*; Partner Management and
  Funder Management share the function and must stay identical. **The company too** (v0.249.1):
  the match, the null-fill, the type merge, the team lookup and the create
  all run under the intake API client (a team-read user matching as
  themself created a duplicate per attempt; the Sponsor Manager Role has no
  Team read), a NEW company carries the creator and the team, and a REUSED
  company or contact GAINS them when missing (`_merge_owner_stamps`,
  merge-only, best-effort) — the contact's company link needs the user to
  read the company. Null-fills and creates still run as the user.
- **A new contact on the Contacts tab reuses a known email** (v0.264.2, the
  staff screens are bound like the public forms): matched under the intake API client, linked,
  null-filled as the user; a CBM member is refused.
- **Contacts tables are per-domain**: mentor shows Role chips and an Agreements
  badge; partner/funder show neither (every contact has the same relationship to
  CBM, and the consent bools are a client-intake concept) but offer **Make
  primary**.
- **First completed session activates the engagement** — a session saved
  Completed on an `Assigned`/`Assignment Dormant` engagement moves it to
  `Active`. The status guard *is* the "first session" rule. Best-effort.
- **Closing a session with a future "Next session" date books the follow-up**
  automatically (Scheduled, 1h, contacts invited). The grid's Next Session
  column derives **only from real sessions** — the stored
  `CEngagement.nextSessionDateTime` is deliberately discarded because staff can
  hand-edit it in the CRM and a stale value showed as a ghost session.
- **`touch_last_contact`** advances `CEngagement.lastContactDate` /
  `lastContacted` (advance-only, never backward or future) on a recorded session
  and an outbound email from the record.
- **Editor**: `SESSION_FIELDS` is layout + whitelist. `duration` is EspoCRM's
  *virtual* type — the frontend translates the Duration select into a recomputed
  `dateEnd`. The time picker **shades slots that conflict** with the user's own
  Google calendar (advisory only — a shaded slot stays selectable).
- **The partner's Details tab carries its client intake link** (v0.255.0):
  a card under the summary strip with the `?partner=<id>` address and a
  Copy button, gated by `DomainConfig.intake_link_form` (partner only) and
  derived in the router from `APP_BASE_URL`, else the request's origin.
  What the link produces shows on the Referred Clients tab. Rule in the
  five-forms section above.
- **Additional managers on partner and funder records** (v0.251.0, Doug's
  requirement 2026-10-11, Partner Management and Funder Management alike): the co-mentor model —
  `CPartnerProfile.additionalManagers` / `CSponsorProfile.additionalManagers`
  (many-to-many to `CMentorProfile`, reverses `comanagedPartners` /
  `comanagedSponsors`), **feature-detected** per request
  (`service.comanager_link_available`) so a CRM without the build shows
  nothing. Same routes, same CBM-contacts card, same picker; off the
  engagement the add is the link plus a history note — no stamps, no
  session backfill. The email scope reads every domain's second reverse
  link (a 404 is skipped at debug); Drive grants entitle them; My Email
  already did. Plan `scripts/plans/additional-managers.json`; handoff
  `cpartner-csponsor-additional-managers-crm-handoff.md`. The links exist
  on crm-test and production (10-11/12-26, both passed as non-admins);
  Boston owed with its next release. **"Make primary" on a CBM row**
  (v0.253.0, Doug's ruling 2026-10-12): `service.promote_comanager` writes
  the manager link first as the user, moves the new manager out of
  `additionalManagers`, and **keeps the former manager as an additional
  manager** (non-destructive, one click undoes it); partner and funder
  only — the engagement's mentor is Client Administration's.
- **The Overview status picker is on every domain** (v0.272.0, Doug
  10-21-26: "in exactly the same manner as the client engagement page"):
  `status_edit_attr` is `engagementStatus` / `partnershipStatus` /
  `funderStatus`; the badge's ▾ menu lists the CRM's live options and the
  pick is written as the user with a stream note (`service.set_status`).
  The funder status (ruling 67) is a field a CRM may not have yet:
  `detail_optional_select` and `list_optional_select` ask for it only when
  live metadata has it, and its Overview fact is left out until then.
- **A closing engagement gains its close date** (ruling 70, v0.273.0):
  `core/engagement_close.stamp_close_date` writes today into an EMPTY
  `CEngagement.closeDate` when the status moves into Completed, Inactive or
  Abandoned — from `service.set_status`, `details.save_details` and
  Client Administration's `update_engagement`; a date typed in the same save
  wins. It reads the field's Read-only flag first: the field WAS Read-only on
  crm-test and production (every write dropped), cleared on crm-test 10-22-26,
  production and Boston owed (`cengagement-close-date-crm-handoff.md`).
- **Co-mentor visibility** requires two things, both in the app: reading the
  `engagements` reverse link *and* stamping the co-mentor's User into the
  engagement's `assignedUsers` (Mentor Role reads CEngagement at "own", which
  with `assignedUser` disabled means `assignedUsers` membership). `add_comentor`
  also stamps the client records and backfills existing sessions;
  `remove_comentor` un-stamps symmetrically unless the user is shared.
- **New sessions are owner-stamped** so a read-own role can see its own create —
  without this the create itself 403s, because EspoCRM ACL-checks the read-back.

Watch for these when touching this package:

- **`sessionAttendees` and `additionalMentors` are RELATIONSHIPS, not fields** —
  read via `list_related`, write via relate/unrelate. Reading `<field>Ids` always
  returns empty and setting it on an update is silently ignored
  ([[espo-custom-linkmultiple-is-a-relationship]]). `unrelate` sends the id in
  the DELETE **body**; the path-suffix form 404s.
- **Relate/unrelate checks BOTH sides** — adding a co-mentor needs edit on the
  *other* mentor's profile. `_link_or_escalate` runs as the user first and only
  escalates a `noAccessToForeignRecord` denial to the admin account
  ([[espo-link-checks-both-sides]]). **Attendee linking goes through the same
  helper** (v0.258.6): `_sync_attendees` and the create-path relate loop
  escalate a foreign-contact 403 exactly as co-mentor linking does — a mentor
  recording an attendee assigned to someone else used to hit the warning
  "N attendee change(s) could not be applied" (Greg Malkin, prod 2026-10-15).
  The warning now fires only when no admin is configured or the admin fallback
  also fails.
- **Enum drift is handled in two layers**: the frontend sends only changed
  fields, and `_sanitize_enum_payload` drops values outside the live options
  before the CRM call (fails open).
- Required fields come from CRM metadata, not hard-coding.
- The `CSession` **name formula must be keep-if-present**
  (`ifThen(name == null || name == '', …)`) or it clobbers the supplied title.
- **One record, one tab** — records open in a stable per-record window and a
  `BroadcastChannel` elects one owner tab ([[single-tab-record-guard]]).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 10-22-26 12:10 | Claude (Claude Code) | The close-date stamp (ruling 70). |
| 1.1 | 10-21-26 21:56 | Claude (Claude Code) | The status picker on every domain (v0.272.0). |
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
