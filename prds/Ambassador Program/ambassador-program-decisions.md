# Ambassador Program — decision record

Last Updated: 11-21-26 23:02 · Revision 0.12

The planning record for building the Ambassador Activity Log into the
applications, in place of the Google Form proposed in
`CBM_Ambassador_Pilot_Form_and_CRM_Handoff (1).docx` (this folder). Doug
ruled out the Google Form on 11-21-26. Each decision below is Doug's, taken
one at a time in DETAIL mode. The PRD is written after the last decision.

## Decisions

### AM1 — Where a mentor reports an activity (approved 11-21-26)

Option A, revised: a page in the signed-in applications.

1. The mentor opens the activity page: a phone bookmark, a portal tile, or a
   "Log an activity" button on the home page.
2. The page checks for a valid sign-in cookie (signed by the server, carrying
   a working CRM sign-in).
3. With a valid cookie, the form shows at once. No email question.
4. Without one, the page shows its own sign-in box in the same place (CRM
   username and password, "Forgot your password?"), then the form. No trip
   to the portal and back.
5. The cookie is shared, so signing in here signs the mentor in everywhere,
   and the reverse.
6. Every save is made as the mentor, under their own CRM permissions.

Built: the activity page, and one shared sign-in box used by both the portal
and this page.

Settled later: how long a sign-in lasts (14 days today), the page name,
whether the date defaults to today, the six activities as large buttons.

### AM2 — Where an activity is stored (approved 11-21-26)

Option A: a new CRM record type, Ambassador Activity (stored by EspoCRM as
`CAmbassadorActivity`). One record per submission, linked to the mentor's
`CMentorProfile`: activity date, activity (six fixed choices), follow-up
flag, note, time received, follow-up done. Visible in the CRM, countable in
the Analytics metric builder, shown on the mentor in Mentor Administration.

Cost accepted: a CRM build with roles (mentors create and read their own;
the program owner reads all), applied CRM by CRM — the Association first,
then crm-test, production and the chapters — and a seeder step for
crm-test's nightly reset.

Settled later: the exact roles; capturing each submission in the
application's database before the CRM write, as the public forms do.

### AM3 — Who the contact was, and where it is recorded (approved 11-21-26)

Raised by Doug: ask whether the contact was a partner; notify the partner
manager and record a partner session; record a client session when the email
belongs to a client; hold unknown contacts for the program owner's review.
Doug's catch-all "Ambassador Partners" partner record was replaced by the
review list below (Claude's alternative, approved).

1. The form asks for the contact's name, email (optional), organization, and
   "Is this person from one of our partner organizations?" (yes / no / not
   sure).
2. The system looks the email up under the organization-wide key.
   - A partner's contact: a session on that partner; the partner's assigned
     manager is emailed.
   - A client's contact: a session on the client's current engagement; the
     engagement's assigned mentor is emailed.
   - Unknown, no email, more than one match, or "partner" said but no
     partner matched: held on the activity, marked "Not matched", for review.
3. The mentor sees the same "Thanks, recorded" every time. The routing
   result is never shown, so the form cannot reveal who is a client.
4. A separate session type, "Ambassador contact", ignored by every session
   count. Known counts it must not trigger: engagement activation (Assigned
   to Active on a Completed session) and the feedback survey's session
   milestone. The build audits every other count.
5. The program owner's review list: per contact, link to an existing partner
   or client (the session is recorded then), create as a new lead with Lead
   Source "Ambassador", or dismiss.

Cost accepted: a larger build (lookup, organization-wide session writes, the
session type and the count audit, two notifications, the review list); the
CRM gains the session type and the lead source; a longer form.

### AM3a — How smart the contact lookup is (approved 11-21-26)

Doug's requirement: never make the mentor type what the CRM already holds;
an email fills in the contact and company, a matching domain fills in the
company, and the mentor can override every lookup.

The lookup reads as the mentor. The production Mentor Role reads every
Contact and Company (from the 08-31-26 roles capture, not re-read live), so
it shows nothing the mentor cannot already browse in Workspace Directories.
A contact's type is never shown. Every filled field is marked "From our
records" and editable; "Not this person" clears the match.

In the first build (items 1 to 6):

1. Free-mail domains never match a company. The list is a setting in System
   Settings.
2. A domain matches on the company's website address (the public forms'
   comparison) and on the email domains of its existing contacts; more than
   one company means the mentor picks.
3. A correction never changes the CRM record. It is saved on the activity,
   and the review list shows what the mentor corrected.
4. The partner question is answered automatically when the matched company
   is a partner; the mentor can change it. Client status is never shown.
5. A CBM member's address stops with "That's a CBM member" (open item #77's
   rule).
6. Name search as the mentor types, from three letters.

Later phase, named so they are not lost: 7, paste a whole email signature or
business card's text and split it into fields; 8, the mentor's five recent
contacts as one-tap choices.

### AM4 — What happens when a mentor asks for follow-up (approved 11-21-26)

Option B: the follow-up lives on the activity record, as the feedback
surveys do. Fields: follow-up requested, follow-up done, date done, note.
An email to the responsible staff team, and an "Ambassador follow-up" row
in the home page's Needs you list. Marking done needs a note and is
recorded in the action history. Open requests share the review list with
unmatched contacts. This is separate from the routing notices in AM3, and a
mentor may ask for help whether or not the contact matched.

Cost accepted: a team to receive the alerts (settled with AM6); a second
kind of row in the review list.

Settled later: whether the mentor is emailed when a request is marked done
(Claude's lean: yes, with the note).

### AM5 — How a client referral is recorded (approved 11-21-26)

Doug's design, replacing Claude's referral link as the core.

1. The mentor logs "I referred an entrepreneur", with the AM3a lookups.
2. A person not in the CRM is created at once: a Contact typed Prospect with
   Referred by set to the mentor; their Company if given; a lead with Lead
   Source "Ambassador". The rules of every place that creates records apply
   (same-named company reused, known email never duplicated, creator and
   team stamped).
3. A person already in the CRM is not duplicated; Referred by is filled only
   when empty, so the first mentor keeps the credit.
4. When they later apply as a client by any route, the intake finds the
   Contact by email (as today) and delivery copies Referred by onto the new
   engagement. The mentor is emailed "Your referral applied".
5. Marketing: Prospect puts them in Marketing Management's audience, but the
   existing marketing opt-in is set only when the mentor answers yes to "Did
   they agree to hear from CBM?" — a yes sets it, nothing clears it.

Changes AM3: an unmatched potential client is created at once rather than
held for review. The review list keeps unmatched partners, multiple
matches and contacts with no email.

Cost accepted: CRM changes (Referred by on Contact and on the engagement,
pointing at the mentor's profile; "Ambassador" in the lead sources); a
change to the client intake delivery; mentors now create CRM records.

Later phase: the personal referral link and QR code, which also credits a
person who applies from a different email or whom the mentor never logged.

### AM5a — How a referred partner or funder is recorded (approved 11-21-26)

Doug's requirement: the same referral process for a potential partner or
funder. Option A.

1. The system creates the Contact, the Company, a lead with Lead Source
   "Ambassador", and a partner or funder profile with status "Candidate"
   and Referred by set to the mentor.
2. The profile carries the domain team, so it shows at once in Partner
   Management or Funder Management — the agreed review path (Doug's ruling
   07-22-26: no separate approval queue). The managing team is emailed.
3. When the organization later applies through the public partner or
   funder form, the form reuses that open Candidate profile instead of
   creating a second, and keeps Referred by. The reuse is narrow: only a
   Candidate profile that came from an ambassador and has no assigned
   manager. Every other case still creates a new profile.
4. Partner and funder are built together on one code path (Doug,
   10-11-26).

Cost accepted: changes to two public forms, with the public-form check; a
"Candidate" status may need adding to the funder profile (not yet found).

Settled later: the Contact's type for a referred partner or funder (lean:
Prospect, changing to Partner or Sponsor on application); the company's
type before they apply; the form's one question — "This person is a
potential client / a potential partner / a potential funder / from an
organization we already work with / someone else".

### AM6 — Who uses it, and how it is switched on (approved 11-21-26)

Option C (Doug: "we have good control over our users, so let's keep it
simple"). No pilot team: every Mentor Team member gets the activity page
once the switch is on. The Mentor Role gains the grant to create and read
its own Ambassador Activity records.

The program is built dark behind one switch; switched on and checked first
on the Business Mentors Association's system, then on Cleveland's
production. Switching off is the rollback.

Decided and announced by Claude (routine, changeable without code): alerts
and the review list go to the team named in `AMBASSADOR_REVIEW_TEAMS`,
editable at System Settings, default the Marketing Admin Team, which
already answers event feedback and submissions. The program owner joins
that team.

### AM7 — What each person sees afterwards (approved 11-21-26)

Option A. A "My activity" list on the activity page: date, activity,
contact name, and a referral's outcome (Applied / Not yet). The mentor may
correct the date, activity and note of their own recent entries, not undo a
created Contact or Company. No one else's activity, no chapter figures.

Built regardless (announced by Claude): an Ambassador Program page in
Analytics for the Analytics Admin Team and the review team — active
ambassadors, activities by type, open follow-ups, contacts awaiting review,
referrals made and applied by client, partner and funder.

Settled later: the edit window (lean: 14 days); a read-only view on
Mentor Administration's mentor record (lean: yes).

## Next

All decisions are taken. The PRD is
`prds/Ambassador Program/ambassador-program-prd.md`; its § 14 lists the
additions awaiting Doug's confirmation.

### AM8 — Where the demo script lives (approved 11-21-26)

Doug asked (11-21-26) for a functional overview, a user guide, and a demo
script test users can run, as a web page that is easy to reach. Option A: the
demo script is a **course in the training application** (`/courses/<id>`,
v0.362.0, `training/CLAUDE.md`): ticks and checkpoint answers recorded,
sign-ins and the system's address filled in from System Settings, never
written into the page. Shown where `TRAINING_COURSES` is on (the
Association today).

Cost accepted: the course follows the training application's format, which
another session is still building (phase 2 next).



### AM9 — The overview and the guide (approved 11-21-26)

Option A: two documents in the repository, both published to the public
docs site and registered in `scripts/publish_docs.py` (drift checked):

- **The functional overview**, for program leaders and the board: purpose,
  who does what, what happens to a report, what is credited, what is
  measured.
- **The user guide**, in two parts: members (logging, correcting, My
  activity) and the program team (the review list, follow-ups, the
  figures). The course names it under `guides:`, so its help agent (TR11)
  reads it.

Cost accepted: two documents to keep current; the docs site is public, so
neither names a sign-in or an `@cbmentors.org` address, and each publish
needs Doug's OK.

Settled later: the titles, the docs-site book, and whether the short
`ambassador-program.md` becomes the user guide.

### AM10 — What the demo walks through (approved 11-21-26)

Option A: one course, both sides, about 25 minutes, on the training system
with the training sign-ins (the training application's TR7): as Joe Mentor,
a shared post, a known contact, a referral with follow-up, and a
correction; as the program team, the follow-up marked done and the
Analytics page; then the member reads the answer. Every invented name
carries the tester's initials.

Cost accepted: a second training sign-in, for the role *Ambassador program
team* (Mark Marketing on the Association), added at System Settings;
testers share Joe Mentor; the review list holds every tester's rows.

Built 11-21-26 (v0.364.1): `training/ambassador-course/` (course id
`ambassador-demo`), `ambassador-program-overview.md` and the user guide
`ambassador-program.md` (the short note became the guide). The referral's
applied half is described in the overview, not walked through.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.12 | 11-21-26 23:02 | Claude (Claude Code) | AM10 recorded as approved, and the three deliverables built. |
| 0.11 | 11-21-26 22:57 | Claude (Claude Code) | AM9 (overview and guide, published) recorded as approved. |
| 0.10 | 11-21-26 22:39 | Claude (Claude Code) | AM8 (the demo script is a training course) recorded as approved. |
| 0.9 | 11-21-26 02:26 | Claude (Claude Code) | AM7 recorded as approved, option A; PRD revision 0.1 written. |
| 0.8 | 11-21-26 02:22 | Claude (Claude Code) | AM6 recorded as approved, option C; review team default announced. |
| 0.7 | 11-21-26 02:20 | Claude (Claude Code) | AM5a (partner and funder referral) recorded as approved, option A. |
| 0.6 | 11-21-26 02:19 | Claude (Claude Code) | AM5 (client referral) recorded as approved; referral link moved to a later phase; AM5a opened. |
| 0.5 | 11-21-26 02:09 | Claude (Claude Code) | AM4 (follow-up) recorded as approved, option B. |
| 0.4 | 11-21-26 02:00 | Claude (Claude Code) | AM3a (contact lookup) recorded as approved: items 1 to 6 now, 7 and 8 later. |
| 0.3 | 11-21-26 01:59 | Claude (Claude Code) | AM3 (contact routing) recorded as approved; later decisions renumbered AM4 to AM7; AM3a opened. |
| 0.2 | 11-21-26 01:41 | Claude (Claude Code) | AM2 recorded as approved. |
| 0.1 | 11-21-26 01:40 | Claude (Claude Code) | Created. AM1 recorded as approved. |
