# Boston — HubSpot to EspoCRM migration

Last Updated: 10-07-26 03:55 · Revision 0.8 (draft) — change log at the end.

Boston Business Mentors kept its member and client records in a HubSpot portal
for eleven months (October 2025 to September 2026). This document records what
that portal holds, measured from a complete read-only snapshot, and the plan for
moving it into Boston's EspoCRM (`crm.bbmentors.org`). Rulings are recorded
here as they are made; until a ruling is recorded the section is a draft.

## 1. How the snapshot was taken

`scripts/hubspot/pull_snapshot.py` reads every CRM object type with every
property and its associations, plus owners, pipelines, lists, files and forms,
through HubSpot's v3 programming interface under a read-only private app
("EspoCRM migration read-only", created 2026-09-26). Output lands in
`~/.config/cbm-boston/hubspot-snapshot/<date>/` (outside the repository; it
holds personal data) with `inventory.json` beside it. No scope was refused. The
pull took under a minute and is repeatable, which is what makes the cut-over
delta (§ 6) cheap.

## 2. What HubSpot holds — measured 2026-09-26

| Object | Records | What they are |
|---|---|---|
| Contacts | 2,698 | 2,063 imported from eight per-mentor spreadsheets (SCORE-era client lists), 422 from the website's forms, 210 typed in |
| Companies | 1,098 | Almost all auto-created by HubSpot from email domains; 371 have no name; only 27 have more than one contact |
| Notes | 2,222 | Mentor session write-ups (median 1,272 characters) and intake triage notes; 84% written in 2026; 193 carry 241 file attachments |
| Meetings | 61 | Calendar-synced mentor appointments, 2026 |
| Tasks / Emails / Calls | 13 / 8 / 2 | Negligible |
| Deals / Tickets / custom objects | 0 | Unused; the sales pipeline was never touched |
| Owners | 45 active, 9 archived | The mentors. 43 have a `firstname.lastname@bbmentors.org` address, which is the standard's `cbmEmail` convention exactly |
| Lists | 2 | "Webinar Registrations" (empty), "Client" (one member) |
| Forms | 5 | Connect with a Mentor (397 submissions), Contact Us (66), Lead Magnet Request (16), a Roxbury Community College variant, Webinar Registration |
| Files | 5 | Two logos, two AI-tool guides (PDF), one image |

**The relationship model is "the owner is the mentor".** 2,693 of the 2,698
contacts have an owner; ownership is the whole of how a client is tied to a
mentor. The lifecycle stage is `lead` on all but two, the deal pipeline is
empty, and the only client markers are a custom `Contact Type = Client` on 36
contacts, a free-text `Classification` on 49, and a manual "Client" list with
one member. Co-mentoring is a custom multi-select `Co-owner(s)` on 138
contacts.

**Activity is concentrated.** 715 contacts have any note or meeting; 1,914 of
the imported spreadsheet rows have had no activity at all in eleven months.

**Custom fields worth carrying (20 defined, these are populated):**

| HubSpot field | Populated | Meaning |
|---|---|---|
| `contact_me_via` | 402 | Preferred contact method: Text / Email / No preference |
| `news_and_updates` | 372 | Newsletter opt-in |
| `referral` | 334 | How they heard of BBM (13 values) |
| `message` (standard) | 479 | The form's "how can we help" text |
| `button_source` | 217 | Which website page the form was on |
| `co_owner_s_` | 138 | Co-mentor(s), as owner ids |
| `mentor_name__if_known_` | 73 | Requested mentor, free text |
| `classification` | 49 | Free text: client / new volunteer / partner |
| `contact_type` | 36 | Client / Partner / Marketing Contact |
| `secondary_email` | 24 | |

Standard contact fields with real data: name, email (all but 2), phone (2,272),
city (468), zip (558), state (71), industry (370, free text), website (332),
company name (391), job title (65). Address lines: 2. Everything else populated
is HubSpot's own analytics and enrichment.

## 3. Boston's EspoCRM today — measured 2026-09-26

Three users (admin, the provisioning account, Doug), one mentor profile (Doug),
three contacts, one company, one engagement, one session, one event. The 45
HubSpot owners have no counterpart. **Creating the mentor roster is therefore
a prerequisite of the load, not part of it** (§ 5, step 1).

## 4. Mapping

### 4.1 What a HubSpot contact becomes — RULED: B (Doug, 2026-09-26)

The consequential question. Two viable readings were put to Doug:

- **A. Every owned contact becomes an engagement.** Contact + CClientProfile +
  CEngagement assigned to the owning mentor: 2,693 engagements, status `Active`
  where there is activity and `Assignment Dormant` where there is none. Each
  mentor's Client Management shows the list they had in HubSpot. Cost: 1,914
  engagements nobody is mentoring, in Client Administration's grid and every
  analytics count, from day one.
- **B. An engagement only where there is evidence of mentoring.** A mentor
  note, a meeting, `Contact Type = Client`, a client classification, or a
  "Connect with a Mentor" form submission: about 800 engagements. The other
  ~1,900 imported rows become Contacts of type Prospect with the mentor as
  assigned user: in the Workspace directory, searchable, promotable through
  intake, but in nobody's Client Management. Cost: a mentor's dormant
  SCORE-era list is no longer one click away.

Ruling: **B.** The standard's engagement means a mentoring relationship, and
eleven months without a note is a mailing list, not a caseload. Boston's
mentors are to be told before cut-over that dormant SCORE-era rows live in the
directory, not in Client Management.

Measured against the snapshot with the rule as coded (`classify()` in
`scripts/hubspot/load_boston.py`): **696 clients** — 546 `Active` (a mentor
note or a meeting exists), 119 `Assigned` (a client marker or a Connect form,
no activity yet), 31 `Submitted` (client evidence but the owner is a shared
inbox, `marketing@` or `connect@`, so Client Administration assigns them) —
and **2,002 prospects**. Of the 45 active owners, 44 become mentors (the
marketing inbox does not). The 9 archived owners create nothing: two are Rob
Stutzman's earlier addresses and are aliased to him; `connect@` is treated as
a shared inbox; the other six are typo'd or pre-onboarding duplicates owning
no records.

The Lakeside dry run (2026-09-26) plans: 44 Users, 44 mentor profiles, 2,698
contacts, 696 accounts, 696 client profiles, 696 engagements, 1,775 sessions
(1,718 from mentor notes, 57 from meetings), 685 stream posts (492 intake notes
and the attachment carriers), 241 attachments, 144 co-mentor links. **The
1,718 note-derived sessions are the draft's largest assumption**: a mentor
note is treated as a session write-up, and some are surely logged emails.

### 4.2 The rest of the mapping (drafts, decided unless overruled)

- **Owners → mentors.** One CMentorProfile + Contact per owner, `cbmEmail` =
  the owner's address, `mentorStatus = Active`; then the login through the
  standard provisioning path so `assignedUser` is set and the mentor sees their
  records. The two nameless owners and the one at `empireadvisors.org` are
  listed for Boston to rule on.
- **Contacts → Contact**, through the intake helper that reuses a contact by
  email and null-fills. Phone through the shared normaliser. `contact_me_via`,
  `news_and_updates`, `referral`, `message`, `secondary_email` to their standard
  fields where one exists; anything without a home to a dated
  "Imported from HubSpot" block at the top of the description. **No new CRM
  fields** (ruling 4 of the chapter network: core or nothing).
- **Companies → Account** only for a contact that becomes a client
  (CClientProfile.linkedCompany is one-to-one by ruling), **named from what
  the person typed as their company**, else after the person, exactly as
  intake names a Pre-Startup client. HubSpot's own associated company record
  is used only to enrich (website, address) and only when its name is that
  same company: most of them were auto-created from the email domain, and
  naming from them merged strangers at one university onto one client
  profile in the rehearsal (revised 2026-09-26 10:58). Placeholders such as
  "N/A" count as no company. A prospect's company name stays as text on the
  contact.
- **Mentor notes → CSession** (Completed, `dateStart` = the note's activity
  date, body into the session notes, mentor = the note's owner) on the
  contact's engagement. Intake-triage notes by "BBM Marketing" → a stream post
  on the Contact carrying the original date. Attachments (241) are pulled by id
  and attached to the session.
- **Meetings → CSession** (Completed, real start and end times, title kept).
- **Co-owner(s) → co-mentor** through the engagement's `additionalMentors`
  relationship and the `assignedUsers` stamp, the same as `add_comentor`.
- **Tasks, emails, calls** → lines in the imported block. **Lists, forms,
  marketing email, workflows** do not migrate; the snapshot is their record.

## 5. Load plan

1. **Mentor roster** on Boston (prerequisite): 45 profiles + logins.
2. **Load script** `scripts/hubspot/load_boston.py` (built 2026-09-26):
   dry-run by default, `--write` to apply, idempotent through a ledger beside
   the snapshot (`ledger-<host>.json`, hubspot id → EspoCRM id) so a re-run
   adds only what is missing. Same helpers as intake: `find_create_or_fill`,
   `EnumSanitizer`, `e164_or_none`. Runs as the provisioning admin (User
   creation is admin-only), falling back to the CRM admin when that password
   is stale (Lakeside's is). Order per contact: mentors first (`--mentors-only`
   stops there), then Account → Contact → CClientProfile → CEngagement →
   sessions and posts → attachments → co-mentor links. New mentor logins get a
   random password and **no welcome email** unless `--send-access-info` is
   passed; mentors use "Forgot your password" on first sign-in. The dry run
   reads the target for real and fakes every write, so its plan reflects what
   the target already holds.
3. **Rehearse on Lakeside** (the kept rehearsal chapter, same standard):
   full write pass, then check Client Administration, Client Management and the
   directory as a real non-admin mentor. **Write pass done 2026-09-26 02:04 to
   02:52** (Doug ran it; the classifier refuses the write from a session):
   44 mentors, 2,698 contacts, 624 engagements, 1,526 sessions, 648 stream
   posts, 237 attachments, 120 co-mentor links; one contact skipped on a
   session title holding an ``=`` (the CRM name pattern is ``[^<>=]+``), fixed
   and picked up by the re-run. Four defects the dry run could not see, all
   fixed in the loader: a duplicated assigned-user id makes EspoCRM 500 after
   inserting the row; a website without a scheme fails the URL validator; a
   session title with ``<`` or ``=`` fails the name pattern; and the ledger
   needed a rebuild path (``--rebuild-ledger``, from the markers every
   imported record carries) after two runs briefly overlapped. Ten HubSpot
   clients matched an existing Account by name and share its client profile,
   the same rule intake applies; the pairs are listed in the rehearsal notes
   for Boston to confirm.
4. **Reconcile**: per-object counts against `inventory.json` and against
   HubSpot's own export screen, run once as an independent count.

## 6. Cut-over

**Status 2026-10-07: waiting on Boston.** The overview for Boston's people
("Moving Boston's HubSpot records", a shared doc issued 2026-09-28, revision
1.0) puts the nine decisions to them with a blank answer line under each.
Nothing is written to Boston until those come back; the backups of
2026-09-27 must be retaken on freeze day.

**Rehearsal complete 2026-09-26** (Lakeside: load, re-run, session stamp
repair, and the browser checks as a mentor and as a client administrator all
passed). **Boston dry run 2026-09-26 21:31:** the same plan as Lakeside's
(44 mentors and logins, 2,698 contacts, 696 engagements, 1,775 sessions, 685
posts, 241 attachments); Boston's Mentor Role grants match Lakeside's on every
entity the load touches (verified read-only the same evening).

Before the write, in order:

1. **Boston confirms the roster.** All 44 active HubSpot owners become mentors
   with logins. Two may be staff rather than mentors (Sue Squires, Teresa
   Lang); one has an outside address that becomes the login name
   (`bob.fitterman@empireadvisors.org`); two contacts are Rob Stutzman's own
   test records ("Test Account"). Boston says which to keep.
2. **Boston's CRM cannot send mail yet** — `smtpServer` is unset (from
   address `connect@bbmentors.org`). The load does not need it, but no mentor
   can obtain a password until it is set: "Forgot your password" and the
   Send Access Info action both send mail. Set it (stage 10, or a plain SMTP
   relay) before mentors are told to sign in. The loader sends no welcome
   mail; an admin sends access info per user when Boston announces.
3. **Freeze HubSpot edits** at an agreed moment, then re-pull the snapshot
   (under a minute) so the load carries that day's data. After the load a
   re-pull and re-run adds new records and new notes; edits to already-loaded
   records do not carry.
4. **Droplet snapshot** of `crm.bbmentors.org` immediately before the write:
   the rollback. **Taken 2026-09-27 03:56 UTC** (Doug's request): DigitalOcean
   snapshot `crm-bbmentors-pre-hubspot-20260927` (action 3433308250, droplet
   603193973, context `boston-central`), plus a full MariaDB dump
   `espocrm-20260927-0356-pre-hubspot.sql.gz` (4.4 MB, 197 tables) at
   `/root/backups/` on the droplet and at `~/.config/cbm-boston/backups/` on
   the build computer. Both verified. If the write is delayed past the freeze,
   take them again.
5. **Write** in a quiet hour: `scripts/hubspot/run.sh boston write`, about
   55 minutes; then `… boston rebuild` once to prove the ledger is whole.
6. **Reconcile and check**: counts against `inventory.json`; the same browser
   checks as Lakeside, as one real mentor (password set by an admin until
   step 2 is done) and as a client administrator.
7. **Boston signs off**; HubSpot stays read-only for reference until the
   subscription ends.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 09-26-26 01:27 | Claude (Claude Code) | Ruling 4.1 recorded: option B. |
| 0.1 | 09-26-26 01:30 | Claude (Claude Code) | First draft: snapshot method, measured inventory of HubSpot and of Boston's EspoCRM, mapping draft with ruling 4.1 owed, load plan, cut-over. |
