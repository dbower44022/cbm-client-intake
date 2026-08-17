# Open items to address

Running list of known issues and pending decisions that don't belong to any
single feature doc. Add new items at the top of their section with the date
found; move resolved items to the bottom with the resolution date.

## Needs a fix / decision

1. **This repository's `.git` lives inside the Dropbox-synced tree, and Dropbox
   destroyed it twice in one day** (2026-07-28).

   - **~10:38** — Dropbox replaced `.git` with a fresh clone of `origin/main`.
     The reflog was left with a single `clone` entry and the unpushed commits
     `e8f3a72` and `4230811` vanished. Working files survived, so the content
     was restored by hand in commit `0451b09`.
   - **~15:19** — worse: `.git` was reduced to a single empty `logs/HEAD`
     (12 KB total). The directory stopped being a git repository at all — every
     git command failed with `fatal: not a git repository` — while a parallel
     session was actively writing a 52 KB document into the working tree with
     no way to commit it. Rebuilt from `origin/main`; the in-flight work went in
     as `862f2dc`.

   The same afternoon Dropbox also left a `.venv (renamed)/` beside the real one
   — 55 MB, 2,583 files, no `bin/`. **The hazard is not confined to `.git`.**

   **Correction to the earlier record:** `e8f3a72` and `4230811` were *not*
   unrecoverable. Both were found intact in Dropbox's own **local** cache during
   the 15:19 salvage. The original entry was wrong on the single most important
   point, which is why the rule below is stated the way it is.

   **What survives and what does not** — established by salvaging the 15:19
   incident:

   - **Committed work is recoverable.** `~/Dropbox/.dropbox.cache/old_files`
     held 6 git packfiles and 1,364 loose objects for this repo, yielding **134
     commits**. 13 of them were absent from GitHub, and every one turned out to
     be a superseded pre-amend/reword duplicate or an abandoned stash whose
     final content was already pushed.
   - **Uncommitted work is recoverable by no means at all.** The 52 KB System
     Admin guide existed in **zero** git objects — no pack, no loose object, no
     blob. It had never been `git add`ed, so nothing anywhere had ever hashed
     it. Only the file on disk existed.

   That asymmetry is the whole lesson: **the danger is never the history — it is
   whatever has not been committed yet.** Commit early; the remote is a bonus.

   **Salvage procedure**, if it happens again — do this *before* rebuilding,
   since a `git init` in place is harmless but the cache is not forever:

   ```bash
   C=~/Dropbox/.dropbox.cache/old_files
   # packfiles: 4-byte "PACK" magic
   find $C -type f -size +1k | while read f; do \
     [ "$(head -c4 "$f")" = PACK ] && echo "$f"; done
   # index each into a scratch bare repo:
   #   git init --bare salvage.git
   #   cp <pack> salvage.git/objects/pack/p.pack && git -C salvage.git index-pack …
   # loose objects: zlib streams starting 0x78 that decompress to
   #   "commit|blob|tree|tag <len>\0" — write to salvage.git/objects/ab/cdef…
   ```

   Then `git cat-file --batch-all-objects` to enumerate, and compare against
   `git rev-list --all` from a fresh clone to find anything the remote lacks.

   **Do not use Dropbox's cloud Rewind for this.** It restores *folders*, so
   rewinding rolls the working tree back too — and the working tree is where the
   only copy of uncommitted work lives, so it can destroy the very thing you are
   trying to save. A `.git` reassembled from an unordered file-level snapshot is
   also a prime candidate for silent corruption (refs pointing at objects that
   did not come back). The local cache above is strictly better: read-only,
   instant, and verifiable.

   **Why it happens:** `.git` is thousands of small files that must change
   together. Dropbox syncs them individually and with no ordering guarantee, so
   another machine's (or an older) `.git` can overwrite this one. This also
   risks *corrupting* a repository, not just losing commits.

   **Options, cheapest first:**
   - **Push early and often** — a pushed commit survives any local `.git` loss.
     Weakest fix; it only narrows the window, and conflicts with the "Doug
     reviews and pushes" convention for work-in-progress.
   - **Add a Dropbox selective-sync / ignore rule for `.git`** (Dropbox supports
     marking a folder "ignored" via extended attribute:
     `attr -s com.dropbox.ignored -V 1 .git`). Keeps the working tree synced,
     stops the history being synced. Note this makes the repo's history
     machine-local, which is the correct model anyway — git already has a
     sync mechanism, and it is called a remote.
   - **Move the repo out of Dropbox entirely** (e.g. `~/Projects/`) and rely on
     GitHub for transport. The clean fix.

   **Recommendation: move the repo out of Dropbox.** Two destructions in one
   day settled this. The `com.dropbox.ignored` attribute is a real fix but has
   to be re-applied every time `.git` is recreated — including after each of
   these incidents — and it was absent both times precisely because nobody
   remembered. Relocation cannot be forgotten. Note the `.venv (renamed)`
   debris shows the working tree is exposed too, which the ignore attribute
   would not have helped with at all.

   Until it is done: **commit often, and never let a long editing session
   accumulate uncommitted work** — that is the only category the salvage
   procedure cannot rescue. Expect the same hazard in every other
   Dropbox-hosted repo (`crmbuilder`, `cbm-mentoring-app`, …); their `.git`
   directories are worth checking.

## Smaller follow-ups from the 2026-07-24 partner migration

**Not defects — Doug's ruling 2026-08-16.** The audit that came out of the
company-link work flagged three prod records as incomplete. They are
*accurately* incomplete, and are to be left alone:
- **The Villages- Sheffield** (partner) has no company because **CBM has no
  company for them yet** — not because the link was lost.
- **key Bank** (funder) has no company and no manager assigned because **the
  manager isn't known yet**.
- **Fatherhood Initiative - Cuyahoga County** has no partner manager (item 2
  below), which stays open for a different reason: its crm-test manager has no
  prod mentor profile to point at.

Do not re-raise the first two as data errors, and do not "repair" them — an
empty company on a partner/funder now renders as "—" and is fixable in the app
(v0.198.0) whenever the real information arrives.


2. **Fatherhood Initiative – Cuyahoga County has no partner manager on prod**
   — its crm-test manager (Tom Mendelsohn) has no prod CMentorProfile. Assign
   an owner in Partner Management / the CRM. **Since v0.197.0 this is doable in
   the app**: Partner Management → the record → Details → Partnership panel →
   Edit → *Partner manager*. It still needs a prod `CMentorProfile` to point at,
   so the choice is a different manager or building Tom's prod profile first.
3. **The 3 new prod partner records carry no Team** — the intake API user
   can't read Teams on prod, so the Partner Management Team stamp was skipped
   (Fatherhood Initiative, Global Cleveland, Sea Change + their Accounts). If
   partner-manager visibility relies on team-scope reads, set the team in the
   CRM UI.
4. **Prod "SBA - Cleveland" partner lists Korin Green (ECDI's director, with
   her @ecdi.org email) as its primary contact** — looks misfiled; verify and
   correct in the CRM.
5. **Fatherhood Initiative account's website field holds an email address**
   (`cuyahoga-fatherhood-initiative@jfs.ohio.gov`, copied as-is from
   crm-test) — fix in the CRM UI if wanted.

## Data cleanup

10. **Two prod CBM members have no linked Contact — and one has no mentor
    status** (found 2026-07-28, probing the birthday roster; both CRMs read
    read-only). On **production**:
    - **Sharon Rose** (Active, has a login; profile `6a47dc983b1894ec6`)
    - **Anita Khayat** (**mentorStatus empty**, has a login; profile
      `6a637b874fcd0e913`)

    The Contact is where a member's personal details live, so an unlinked
    profile means no email/phone/address on the member record, `/mentorprofile`
    refuses every Contact-side save (readable 400 before any write), and they
    can never be greeted on their birthday. Both should already read
    **Incomplete** on Mentor Administration's completeness badge. Fix in
    `/mentoradmin`: link their Contact (create one if none exists) — a staff
    save then runs `reconcile_user_links` and stamps the User on both sides.
    Anita's empty `mentorStatus` is a second gap: with no status she is greeted
    on her own birthday but never **announced** to CBM (the announcement is
    limited to current-member statuses) — set her to Active if that's what she
    is. Context: `birthday-greetings.md`.

9. **Intake-receipt redesign — CRM-side finish** (2026-07-27; app arc
   COMPLETE and converged — see the CLAUDE.md Current-status block). Three
   Doug-side items, both CRMs unless noted:
   - **Delete the old `reason` and `status` fields** on Intake Submission in
     Entity Manager (`cintake-submission-redesign.md` §6) — the migration is
     verified on both environments, nothing writes or reads them anymore.
   - The **§7 live pass** when convenient: a test form submission (watch it go
     Received → Completed in Submission Admin AND on the CRM receipt), an
     outside email to info@ (a Held-Email receipt exists in the CRM before
     anyone touches it), and a Discard-with-reason (who/when/why on the
     receipt).
   - Delete the live-probe receipt **ZZTEST `6a66f5b4bbe3805ee`** (crm-test).

7. **Partner Accounts carry a bogus industry sector** (found 2026-07-25).
   `Account.cIndustrySector` used to default to "Agriculture, Forestry, Fishing
   and Hunting", and it stuck on 7 of 8 crm-test partner Accounts — including
   Key Bank and Global Cleveland. The **default is now cleared on both CRMs**
   (verified `default=None` 2026-07-25), so new records are fine, but the
   already-stored values are wrong and now **visible**: v0.153.0 shows the
   company's industry on the partner/funder Overview rail. Doug is correcting
   these by hand in the CRM.

## Other follow-ups

6. **Re-save the session whose notes were lost to the pasted-image failure**
   (found 2026-07-24, fixed in v0.148.0). Prod CSession `6a604b7b26efd8e3f`:
   the 04:37 UTC save 500'd in the CRM ("Data too long for column
   'session_notes'" — a pasted image as base64), so those notes never stored.
   After the v0.150.0 deploy, re-enter/re-save the notes — pasting the image
   inline now works (v0.150.0 stores it as a CRM attachment). Live check while
   there: the pasted image dims briefly, then the save succeeds and the image
   renders on the Overview feed, the session view, and in the EspoCRM UI.

## CRM prerequisites outstanding

*(Moved here from CLAUDE.md 2026-07-28 during the CLAUDE.md slim-down. Each is a
CRM-side build/grant the app already feature-detects or degrades around — none
block a deploy.)*

11. **`Held-Duplicate` option on `CIntakeSubmission.intakeStatus`** (both CRMs) —
    handoff `cintake-submission-duplicate-status.md`. Until built, the receipt
    engine falls back to `Received` with the explanation in `intakeMessage`;
    activates with no deploy.
12. **prod Mentor Role: `CMentorProfile` edit = `all`** — crm-test has it, prod
    has `own`, which 403s "+ Add CBM contact" (co-mentor linking) for every
    non-admin mentor. v0.174.0 added an app-side admin escalation as the second
    layer, but Doug ruled fix both sides.
13. **prod sponsor-team role: `CContribution` create / read(All) / edit, NO
    delete** — done on crm-test 2026-07-21, still TO DO on prod before the
    Contributions tab is used there. Eyeball enum parity while in the CRM.
14. **`documentsFolderUrl`** (CEngagement + Contact) — handoff
    `documentsfolderurl-crm-field.md`. DOC-08 write-back is feature-detected and
    inert until it exists.
15. **prod field parity with crm-test** — confirm these exist on production
    (each is feature-detected, so the feature simply stays dark until then):
    `CSession.sessionAiSummary` (`csession-ai-summary-field.md`),
    `CMentorProfile.preferredMeetingProvider` + `zoomPersonalLink`
    (`cmentorprofile-meeting-fields.md`), `CEngagement.lastContactDate`
    (`clastcontactdate-field.md`).
16. **Partner / Funder domains on prod** — the `Partner Management Team` and
    `Sponsor Management Team` roles need the profile entity readable at **team**
    scope, existing records backfilled with the team, and the intake API role
    granted **Team read** (until then the intake team-stamp is skipped with a
    WARNING). Same list for the session-tool CRM prereqs generally: `CSession`
    create + read-own/edit-own, `assignedUsers` enabled on `CSession`, and the
    `CSession` name formula must be **keep-if-present**.
17. **`Analytics Admin Team`** — create in both CRMs to hand Analytics to
    non-admin staff (admins already pass the gate).
19. **Meet transcripts — three Google-side changes, none done** (re-probed
    2026-07-27: a delegated token minted fine for `calendar.events` but was
    rejected `unauthorized_client` for `meetings.space.created`, so the DWD scope
    is definitely still missing): (a) Admin console → Meet video settings →
    Transcription ON for the OU; (b) add `meetings.space.created` to the service
    account's DWD row (the field REPLACES — keep the existing scopes; client id
    109317126943210877831); (c) enable the **Meet REST API** in GCP project
    `espcrm-498315`. **Do NOT set `MEET_TRANSCRIPTS=true` before (b) exists** —
    every Scheduled-session save would show mentors a "transcription failed"
    notice. Re-probe recipe + the local SA key path are in
    `csession-transcript-fields.md`.

22. **One prod Gmail message can never be ingested** (gmail id
    `19f298a147e3ba38`). Its subject trips `CConversation.name`'s
    `$noBadCharacters` validation pattern, which exists on both CRMs. The
    field-length half of this class was fixed CRM-side (widened 255→500) and a
    resync recovered the other 7 messages; this one remains. The fix would be
    app-side subject sanitizing on conversation create — deliberately not built,
    since it is a single message. It now surfaces as a dead-letter alert rather
    than silent loss ([[prod-ccommunication-field-length-drift]]).

## Live verification owed

22. **Two-stage mentor provisioning has never run against real Google**
    (v0.204.0, 2026-08-17). The `Accepted-Provisional` → account + group →
    `Provisional` flow is covered by tests and fakes only. Three things gate the
    live pass, in this order:
    - **The All Members group address.** Doug does not have it yet. Until it is
      set (Email Setup, or `GOOGLE_MEMBERS_GROUP`) the group step is skipped
      silently and everything else works — that is deliberate, so the rest can be
      verified first.
    - **The `admin.directory.group` scope** must be added to the service account's
      domain-wide-delegation grant in the Workspace admin console, and the
      delegated admin needs group-admin privilege. Without it the add 403s
      `unauthorized_client` — the same failure shape as
      [[gmail-delegation-needs-licensed-mailbox]].
    - **"Create missing mailboxes"** must actually be on for the environment
      (check `/setup` or Email Setup — the overlays are gitignored). With it off,
      an `Accepted-Provisional` save correctly reports the mailbox missing and
      stops, which is not the intended outcome.

    Then, on crm-test **as a real non-admin Mentor Administration user**, with a
    throwaway mentor name (there is no test Workspace tenant — delete the mailbox
    and the group membership afterwards): save at `Accepted-Provisional` → the
    account is created, joins the group, the temp password is shown, **no** EspoCRM
    User exists, and the record now reads `Provisional`. Then save at `Approved` →
    the login is created against **that same address**, with no second mailbox, no
    suffixed duplicate, and no demotion back to `Provisional`. Also confirm prod's
    `mentorStatus` enum carries both `Accepted-Provisional` and `Provisional`
    (verified on crm-test 2026-08-17; the two CRMs drift). Plan and rulings:
    `prds/mentor-provisional-provisioning-plan.md`.

19f. **The Company record page and the client dashboard section have never been
    opened by a human** (2026-08-16). Both shipped 2026-07-28 and are covered by
    tests, and the Company route serves on crm-test — but no one has looked at
    either rendering real data. Worth ten minutes as a real non-admin in the
    Mentor Team:
    - `/directory/companies/` → click a company name → the page opens in its own
      tab, Overview shows the CRM-arranged detail, and the **Analytics** tab
      renders the `record-company` starter (people and activity for that
      company) rather than the "no analytics set up" message.
    - Client Management → any engagement → **Analytics**: two sections, the
      engagement dashboard and the client one beneath it. An engagement with an
      empty `engagementClientId` should show only the first, not an error.
    - Both need `ANALYTICS_ENABLED`; record-scoped metrics always run live as
      the user, so an empty panel means the metric found nothing, not a cache.

19f. **Event registration holds a person's SECOND webinar of the day for staff
    review** (found 2026-08-17). `_recent_duplicate_id` matches on form slug +
    email inside `duplicate_hold_seconds` (24h), and event registration rides
    the shared pipeline, so registering for two different events on one day
    captures the second as `held_duplicate` — never delivered, no Zoom
    registration, and the visitor sees a normal thank-you. The guard is right
    for client-intake (a re-filled form used to strip links off the first client
    profile) and wrong here. Fix and rationale:
    `prds/events/CBM_Events_Registration_Recognition_Plan.md`. Not urgent while
    `EVENTS_PUBLIC_API` is crm-test-only, but it must land **before** the
    website cutover.

19d. **The events sign-up modal's consent line under-covers what `consent: true`
    writes** (2026-08-16, v0.203.0). The line copied from the live page —
    *"By registering, you are agreeing to receive emails about our webinars"* —
    is a marketing-email statement, while `consent: true` also stamps
    terms-of-use, privacy-policy and code-of-conduct acceptance on the Contact
    (`forms/event_registration/orchestrator.py`). The preview therefore sends
    **false**, which claims nothing the visitor was not shown but records no
    opt-in at all. Before Phase 4 ships, decide which: a real consent checkbox
    in the modal (a visible change to a page visitors know), or consent text
    that names the three policies. Not urgent — no public traffic reaches this
    yet.

19e. **The events website preview has only been seen against stub data**
    (2026-08-16, v0.203.0). The site's own stylesheet, the sign-up modal, the
    title→event-page link and the corrected recorded-library markup were all
    verified in a local harness with fabricated events. `/events` is live on
    crm-test, so the real pass is available today: open
    `/events/preview.html` there, confirm both panels against
    `clevelandbusinessmentors.org/webinars/` side by side, click a title through
    to the event page, and register once with obvious test data (it creates a
    genuine Contact + CEventRegistration — delete them afterwards).

19c. **Events Phase 6 is built but three of its four parts have never met their
    external service** (2026-08-16). All are off everywhere; nothing is at risk
    until each is switched on, but none of it is proven:

    - **6a attendance** — `events/attendance.py` needs a real Zoom webinar with
      real participants. `ZOOM_EVENTS` has never been on in any environment, so
      **Phase 2 is unverified too** and the two have to be tested together: a
      real webinar, real registrants, then confirm the pull marks attended /
      no-show correctly and leaves hand-set attendance alone.
    - **6b follow-up email** — blocked on **five EspoCRM templates**
      (`EventReminder`, `EventRecordingAvailable`, `EventNoShow`,
      `EventMentorCTA`, `EventSurvey`); each send refuses by name until its
      template exists. Also **has no frontend** — the endpoints work but the
      Follow-up tab doesn't call them, so it is API-only today. Never sent a
      real message.
    - **6d YouTube backfill** — never run against the real playlist; needs a
      YouTube Data API v3 key and the playlist id. Run the dry-run on crm-test
      first: the intake API user cannot delete, so a bad import is cleaned up by
      hand.

    **6c reporting is the exception** — built and wired end to end, but every
    surface currently reads empty because no crm-test registration has been
    marked Attended. Setting one attended is the cheapest way to see the
    engagement rollup, the contact history and the programme reports carry real
    numbers.

19d. **Events is still off on production** (2026-08-16). crm-test has
    `EVENTS_ENABLED` + `EVENTS_PUBLIC_API`; prod has neither, though its CRM
    schema and the `Event Registration` receipt enum are both ready. Deliberate:
    **Phase 4 (the WordPress plugin and cutover) is not built**, so there is no
    public site pointing at prod and nothing to gain by switching it on. Phase 4
    remains the only thing standing between this work and the lead leak actually
    stopping.


19b. **The v0.198.0 Company picker's CREATE path has never run as a non-admin**
    (2026-08-16). "+ New company" creates the Account through the **intake API
    client** on purpose, because the partner/funder gate roles don't hold
    `Account` create — so an admin test proves nothing (admins bypass ACL). It
    was going to be discharged by repairing the two company-less records, but
    Doug ruled those stay as they are (see the partner-migration follow-ups
    below), so nothing is scheduled to exercise it. **It will be verified the
    first time a real manager adds a company from the Details tab** — if that
    403s, the fallback to the API client is not working and the button fails for
    exactly the users it was built for. Everything else about the picker is
    verified (server payload, save-diff, end-to-end in the preview harness).

20. **Everything through v0.187.0 is DEPLOYED to both environments** (verified
    2026-07-28; only docs commits are unpushed). What is owed is the *live
    eyeball*, not a deploy. Never driven against the live CRM/Gmail/Drive:
    - **The curated link pickers, now that they have options (v0.202.2)** —
      until this release the option list was fetched with `maxSize=500`, which
      EspoCRM 403s, so **every** picker offered only "(none)" for everyone
      including admins. That invalidates the earlier manager-picker sign-off,
      which could only have exercised the stored value. On a real partner and a
      real funder, as a **non-admin** team member: open Details → **Edit** on
      the first panel and confirm the **Company** picker lists the companies
      (~97 prod / 93 crm-test) and the **manager** picker lists mentor
      profiles; change each, Save, and confirm the CRM stored it and the grid
      column follows. If a picker is still empty for a non-admin it is now a
      genuine read-grant finding (Account / `CMentorProfile` on that team's
      role) rather than this bug — the sponsor team's role in particular may
      not read `CMentorProfile` at all.
    - **The events Add/Edit editor (v0.202.0)** — a resizable workspace modal
      with pinned Save/Cancel and the two Content fields on CBMRichText.
      Verified only in a stub harness, but **`/events` is live on crm-test**
      (`/events/api/session` 401s there and 404s on prod), so this can be done
      now. Fold it into the Events Phase 5 pass below: create and edit one
      event, confirm the rich text round-trips to `eventOverview` /
      `eventSyllabus` and renders on the website preview, the Duration select
      still translates into `dateEnd` (a wrong `dateEnd` is the four-hours-early
      class of bug), and the graphic uploads through the new "Choose image…"
      button. Also worth a glance: the page's buttons changed from a white
      outline to the standard navy secondary, since it no longer defines its
      own.
    - **Address paste-parsing (v0.196.0)** — **deployed** on the 2026-08-13
      push and live on both environments; there is no flag, so a revert is the
      only rollback. Verified against a faithful replica of each form shape in
      a browser, NOT against the real pages. What is owed is one live pass on the
      **session tools' Details tab** — the only surface where a State
      `<select>`, disabled shipping inputs and the "Same as billing" mirror are
      all in play at once. Paste a full address into Company **billing** line 1
      with *Same as billing* ticked and confirm shipping mirrors; paste a
      spelled-out state (`Ohio`) and confirm the `<select>` takes `OH`; click
      **Undo** and confirm every box returns, then Save and confirm the CRM
      stored what the boxes showed. Glance at the other five surfaces
      (`/mentoradmin`, `/mentorprofile`, `/directory` edit, volunteer,
      client intake) while you are there. Guide: `address-paste.md`;
      plan: `prds/address-paste-parsing-plan.md`.
    - **Quick add — "+ Add partner" / "+ Add funder" (v0.195.0)** — deployed to
      both environments; `RECORD_QUICK_ADD` gates it and `/setup` can now toggle
      it on either. **The UI is reviewed and signed off** (2026-08-12); what is
      owed is the CRM half. **As a real non-admin partner/funder-team member**
      (admins bypass every ACL this feature depends on), create one of each and
      confirm: the
      Account create lands (it runs through the intake API client), the profile
      is visible in the grid afterwards (team stamp), the contact appears on the
      Details tab, and the manager picker offered a usable list — the sponsor
      team's role may not read `CMentorProfile` at all, in which case the picker
      is legitimately empty and the manager is set later on Details. Then
      re-enter the SAME company and email to prove the reuse path (no duplicate
      Account/Contact, `cCompanyType` gains the type). Only then add the var to
      the prod overlay.
    - **Prod alert-email deep links** — `APP_BASE_URL` was applied to prod on
      2026-08-12 (it had sat unapplied in the overlay), so the next alert email
      and daily digest should carry absolute record links instead of bare
      names. Nobody has seen one yet; glance at the first that arrives.
    - **Analytics record dashboards (v0.187.0)** — open a real Mentor,
      Engagement, Partner, Funder and Contact on crm-test.
    - **Duplicate hold + preferred-mentor dropdown (v0.185.0)** — crm-test's
      roster has only 2 public mentors, neither Active+accepting, so the dropdown
      correctly stays hidden; flip `publicProfile` on a couple of
      Active+accepting crm-test mentors to exercise it.
    - **Co-mentor add as a real non-admin mentor** (`sharon.test`) — v0.174.0.
    - **Mentor permission-teams round-trip** to `User.teamsIds` — v0.155.0.
    - **Partner & Funder review pass** — the Overview rail manager + industry,
      the notes/Discussion splitter, Make primary, the Last Contacted column,
      contact name → peek (v0.153.0 / v0.154.0).
    - **Referred Clients tab** on a real partner (v0.156.0).
    - **Email round two** — forward with a real PDF attachment, grid unread
      chips, the daily digest (v0.157.0); **Other correspondence** reply
      (v0.159.0).
    - **Last Contact auto-advance** on a session save and an outbound email
      (v0.158.0).
    - **Zoom PMI preference** — the first real Scheduled save with the
      preference on (event carries the Zoom link, mints no Meet) (v0.151.0).
    - **Email templates + signatures (the whole ET arc)** — harness-verified
      only, never driven against the live CRM/Gmail.
    - **Google Calendar**: edit→patch, Cancel→cancel-event, and actual
      attendee-invitation delivery (only the create path is live-proven).
    - **Documents Phase 3** — the hand-driven checklist in
      `GDRIVE-DOCS-SETUP.md` Task 6 (assign/unassign grant flow as a mentor,
      `Mentors/` no-grant check, archive/restore against the real drive,
      hand-grant-removal alert).
    - **Reassign Mentor** (v0.81.0) — needs the staff role to carry CSession
      read+edit for the session re-stamp and Note create for the history stamp.
    - **Events Phase 5** signed in as a **real non-admin** Marketing Admin user
      (the browser pass stubbed the session, so the team gate and a non-admin's
      CRM ACL are untested).
    - **Birthday greetings** — nobody has yet watched it fire on a real member's
      birthday. Only 5 of 19 prod members have one recorded, so expect ~5 days a
      year; use `scripts/preview_birthday.py --date MM-DD` to see it on demand.

21. **Test-record sweep in the CRM UI** — the intake API user is create-only, so
    these have to be deleted by hand. Known outstanding on **crm-test**: 3
    `ZZTEST-COMPANYTYPE` Accounts (`6a682c8b3b6038e12`, `6a682c8b788683d2e`,
    `6a682c8bb25b0f76d`); the Fathom probe CSession `6a5f011bce8e19a19`; the
    receipt `6a66f5b4bbe3805ee` (also item 9). On **prod**: 4 `ZZTEST-GMAILPROD*`
    probe records. Older `ZZTEST … GrantCheck` / Stage A/B / provisioning test
    Users may already be gone — the reliable method is a `contains ZZTEST` sweep
    across the entities rather than chasing individual ids. Also on crm-test: the
    duplicate unlinked mentor profile "Doug Bower" (`6a4425f4c82d3f2ec`, alongside
    the real linked "Douglas Bower") and two "Acme Inc" CPartnerProfiles — records
    assigned to an unlinked profile are invisible in the session tools.

## Resolved

- **Analytics on the record views — the last two surfaces** (was item 0,
  decided 2026-07-28, `prds/analytics-app-plan.md` §17). **Both were built the
  same day the ruling was recorded and the item was simply never closed** —
  found 2026-08-16 while picking it up as new work.
  - **Company** — `44d7562` built the full record page at
    `/directory/companies/record/{id}`: the View Contact shell (Overview +
    Analytics, header/footer, single-tab lock) minus Communications, since
    companies talk through their people. `DirectoryConfig.company_page` gates
    the route mount and the `/session` flag; the grid's row-name click opens it
    in a stable named window while the View pop-up and preview strip stay for
    browsing, exactly as ruling 1 asked.
  - **Client** — no screen of its own, per ruling 2. `sessions/service.py` puts
    `clientProfileId` in the engagement detail payload and the Analytics tab
    fetches the `CClientProfile` dashboard as a second section beside the
    engagement one.
  - Starter dashboards `record-company` and `record-client` seeded in `cf23bf0`,
    so all seven record types now have one.
  - Verified 2026-08-16: 51 directory tests + 21 analytics record tests pass,
    and `GET /directory/companies/record/{id}` serves on the deployed crm-test
    app. What is owed is the eyeball, logged under *Live verification owed*.

- **`test_a_full_event_is_NOT_refused` failed on a date roll** (was item 7,
  found 2026-08-13). The shared `make_event()` fixture hard-codes
  `dateStart: 2026-07-28`, and registration closes at `dateStart`, so from that
  date on the event was refused as closed and the EV-15 "full means waitlisted"
  assertion never ran — the suite's only red line, and a permanent one.
  **Resolved 2026-08-16:** that test now builds its own event 30 days out
  rather than inheriting the fixed date, so it tests capacity again and cannot
  rot. The shared fixture keeps its fixed date, which the date-formatting tests
  depend on.

- **Company links were one-to-one, so a second record silently stole the
  company** (was item 00) — `Account.cCompanyPartnerProfile` and
  `Account.cSponsorProfile` were both `hasOne`, so linking a company to a second
  partner/funder profile *moved* it off the first, emptying that record with no
  error. Found 2026-08-13 from a live partner whose company had been taken by a
  duplicate entered nine hours later. **Resolved 2026-08-14 → 2026-08-16:** Doug
  ruled a company can hold **many** partner and funder records (a partnership is
  often with a programme inside an organisation), and recreated both
  relationships as Many-to-One in Entity Manager — partners on prod 2026-08-14
  and crm-test 2026-08-15, funders on both 2026-08-16. Verified via the API each
  time: no link lost anywhere (removing a relationship never drops the column),
  the link names match across environments (`partnerCompany` /
  `cCompanyPartnerProfiles`, `sponsorCompany` / `cSponsorProfiles`), and a
  functional test on crm-test confirmed two records now share one company with
  neither losing it. `CClientProfile.linkedCompany` stays `hasOne`
  **deliberately** — see the ruling in CLAUDE.md.

- **Events: prod schema migration not applied** (was item 18) — the Events
  change list had been applied to crm-test only, leaving prod short 16 fields,
  3 enum additions, 4 `readOnly` flags still set and the `partnerHost` link.
  **Resolved 2026-08-08:** Doug applied the whole list by hand in Entity
  Manager. Verified by running `scripts/probe_events_schema.py` inside the prod
  **web** container and diffing the output against a crm-test run: all 26 items
  present, and the probe reports "No blocking schema problems found" where it
  previously reported four fields whose values EspoCRM would silently strip.
  Only four differences remain and none are on the change list —
  `CEvent.duration` default 300 (prod) vs 3600, an extra `emails hasChildren →
  Email` link on prod, and empty-vs-unset defaults on `attendanceSource` /
  `followUpsSent`.

  **Two traps this exposed, both now recorded in
  `cevent-entities-crm-handoff.md` §2.4:**

  1. **The probe does not check link naming.** The `partnerHost` relationship
     was created **reversed** — prod had `CEvent.hostedEvents` → CPartnerProfile
     with the foreign link named `partnerHost` — and the probe still reported no
     problems, because it only verifies that the two entities exist and that the
     must-write fields aren't `readOnly`. Only a field-by-field diff against
     crm-test caught it. Diff the two instances; don't trust the clean exit.
  2. **The Create Link dialog inverts what you type.** A panel's Name/Label
     define the link that *points to* that panel's entity, so the link is stored
     on the **other** entity. Building from Event with Partner Profile on the
     right, the LEFT panel Name creates the link on **CPartnerProfile** and the
     RIGHT panel Name creates the one on **CEvent**. Specifying it the intuitive
     way round produced the reversed link twice before the labels
     (`GET /I18n?scope=<Entity>`) settled the mapping.

  **Also settled:** prod's `CEvent` legitimately holds **0 records** — the
  entity was never connected to Google, so CBM's org calendar exists only on
  crm-test (94 rows). This is not an ACL blind spot in the intake API key. It
  also means `publishToWebsite` has nothing to protect on prod yet, and the
  first published event there will be a real one rather than one hidden among
  internal meetings.

- **Account type stamp wrote a field that no longer exists** — found
  2026-07-24 on prod, where `Account.cAccountType` had been removed; all four
  intake orchestrators wrote it, and EspoCRM silently ignores unknown
  attributes, so the type stamp stored nothing. **Resolved 2026-07-28:** the
  Account entity is presented as **Company** and its type field is
  **`cCompanyType`** (Doug). A live probe found `cAccountType` gone from
  **both** CRMs and `cCompanyType` identical on both — multiEnum
  `['', 'Client', 'Sponsor', 'Partner', 'Other']` — so the fix is a straight
  retarget, no feature detection. All four orchestrators now write
  `cCompanyType`, and the sponsor form's value changed from `"Donor/Sponsor"`
  (rejected by the CRM — it is not an option) to **`"Sponsor"`**. The drift
  monitor (`core/schema_contract.py`) was retargeted with it. Verified live on
  crm-test: Client/Partner/Sponsor each stored, `"Donor/Sponsor"` refused.

- **Account-level partner fields duplicated (and contradicted) the partnership
  record** — found 2026-07-24 during Doug's partner review; `cPartnerStatus`,
  `cPartnerContactCadence`, `cPartnerType`, `cPartnershipStartDate` and
  `cPartnershipAgreementDate` were editable on the Company card while the grid
  and Overview read the `CPartnerProfile` twins, and live data had already
  drifted apart (Glide: Account "Monthly" vs partnership "As-Needed"; every
  Account "Prospect" regardless of real status). **Resolved 2026-07-25:** Doug
  deleted all five CRM-side, verified MISSING on crm-test AND prod, and
  v0.153.0 removed the app's references (the Company group is now organization
  type + announcements). The `cIndustrySector` stamped default was cleared in
  the same pass — see item 7 for the stored values it left behind.
