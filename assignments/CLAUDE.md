# assignments/ — Client Administration

Last Updated: 10-20-26 17:30 · Revision 1.0

Detail for the Client Administration application (`/assignments`): the engagement grid, Assign and Reassign, the mentor roster and the editable engagement popup.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## Client Administration — `/assignments`

Staff-only. Page title is "Client Administration"; the package and route stay
`assignments`. Lists `CEngagement` records in a sortable, searchable,
full-height grid with a status multi-select, and assigns each to a mentor.

- **Mentor dropdown** = `CMentorProfile` where `acceptingNewClients=true` AND
  `mentorStatus="Active"` AND `assignedUser` set. An empty dropdown means no
  mentor passes all three.
- **Client counts are app-computed from `CEngagement`, never the CRM's own
  `currentActiveClients`/`availableCapacity`** (crm-test's formula is
  known-buggy). `ACTIVE_CLIENT_STATUSES` = Active, Assigned, Pending Acceptance
  **and On-Hold** (Doug's ruling 2026-09-29 — the same set Analytics uses, so
  every screen agrees). Available = Max Clients − Active Clients.
  **CoMentors** (v0.234.0) counts the active engagements where the mentor is a
  *non-primary* mentor, read per mentor through the `engagements` reverse link
  of `CEngagement.additionalMentors` (a relationship — `additionalMentorsIds`
  on a list read is always empty). It does **not** reduce Available, and only
  the Client Administration roster asks for it
  (`list_all_mentors(include_comentors=True)`) — Mentor Administration shares
  the function and makes no extra reads. A failed per-mentor read renders "—",
  never 0.
- **A mentor's name in the Available Mentors list opens a read-only detail
  popup** (v0.220.0): the CRM's own `CMentorProfile` detail layout rendered by
  the shared `/shared/detail-render.js`, plus a Contact panel and an "Other
  fields" sweep (`directory.service.detail(..., include_unplaced=True)` via
  `service.mentor_detail`), read as the signed-in user. Its footer
  Assign/Reassign button completes the assignment when the roster was opened
  from an engagement's Assign/Reassign card ("Browse the full mentor list…");
  unscoped it explains itself on click. View-only by ruling — editing stays in
  Mentor Administration.
- **Assign** (`service.assign_engagement`) sets `mentorProfile` +
  `engagementStatus="Pending Acceptance"`, stamps `engagementAssignedDate`, and
  re-homes assigned users across every related Contact, the CClientProfile and
  the Account. **Merge, never overwrite** (`_merged_assignment_payload`) — an
  overwrite silently revokes co-mentor access.
- **The mentor gets a stamp too** — `CMentorProfile.lastClientAssignedDate`, the
  last date that mentor was given a NEW client. Written by Assign and by
  Reassign (the **new** mentor only; the field records gaining a client, not
  losing one), never by a repair. Advance-only, feature-detected, and
  best-effort — a role without `CMentorProfile` edit logs a warning rather than
  losing an assignment already written. It is a sortable **Last Assigned**
  column in the Available Mentors picker (ascending = who is most overdue), and
  the roster query asks for the field only when the CRM has it. Spec:
  `cmentorprofile-last-client-assigned-field.md`.
- **Assign needs `User: read` on the acting role.** The assignedUsers stamp is
  a link write, and EspoCRM refuses it (403 `cannotRelateForbidden`, identical
  in 9.3.4 and 10.0.6) unless the user can read every User being linked. The
  Client Assignment Role carried no User grant until 2026-09-07; Cleveland's
  client admins only ever passed through a second team seat (Mentor Team).
  Ruling: `User: read all, edit own` on the role itself —
  `scripts/migrate_client_assignment_role.py`, Lakeside done, crm-test and
  prod owed (`OPEN-ITEMS.md` #28).
- **Stale-write guard**: the engagement is re-read before any write and the call
  is rejected (400, nothing written) if it already has a mentor or is no longer
  `Submitted`. The frontend reloads the grid on any Assign 400.
- **Assigning the SAME mentor again is a repair run**, not an error — it
  re-executes the idempotent re-homing. Reachable from the row's right-click
  menu ("Repair assignment…"), which is the only way to reach it since assigned rows
  have no Assign control.
- **Reassign Mentor** swaps `mentorProfile`, re-stamps the date, re-homes
  everything including every CSession (swap-merge: the old mentor is removed
  unless a co-mentor shares the user or they personally own the session),
  and deliberately **leaves `engagementStatus` untouched**.
- A successful Assign/Reassign opens the quick-compose with the mentor's
  `cbmEmail` and the EspoCRM `MentorAssignmentNotice` template pre-applied.
- Every row function is also on the **right-click context menu**. The Notes
  column edits `CEngagement.description` inline — staff-internal by design, and
  excluded from the session tools' Details tab for that reason. **Whether it
  is a rich editor or a plain textarea is feature-detected per load** from the
  field's live CRM type (`service.live_wysiwyg_fields`): wysiwyg ⇒ the shared
  editor with images, text ⇒ the textarea, because only a wysiwyg field binds
  its inline attachments (an unbound one is collected by EspoCRM's cleanup).
  crm-test and production are converted (production 10-11-26,
  `scripts/convert_notes_wysiwyg.sh`); Boston is owed
  (`cengagement-description-wysiwyg-crm-handoff.md`). The popup's
  Engagement-notes and Mentoring-needs fields are wysiwyg on both CRMs and take
  images now.
- **The View-details popup is editable** (v0.210.0). It opens at 90% of the
  window, resizable, with the title bar and the Save/Cancel bar pinned around a
  scrolling body. `service.ENGAGEMENT_EDIT_FIELDS` is **one spec serving as both
  the form layout and the update whitelist**; enum options come from live CRM
  metadata, link-picker options are **paged at 200** (an oversized page is a 403,
  not a truncation), a forbidden list degrades the field to read-only, a stored
  value outside the option list keeps its place, and Save sends only what
  changed. **The referring partner is named in the popup's HEAD** (v0.256.0,
  Doug's request 2026-10-12): a "Referred by <partner>" band under the
  title, visible in view and edit mode alike because the head is outside
  the swapped body; no partner, no band. **The assigned mentor is deliberately not an editable field** —
  swapping `mentorProfile` re-homes contacts, client profile, company and
  sessions, so the row hands off to Assign/Reassign instead.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
