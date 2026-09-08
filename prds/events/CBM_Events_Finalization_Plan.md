# CBM Events & Webinars — Finalization Plan

Last Updated: 09-08-26 19:05 · Revision 1.0 — see change log at the end.

Companion to `CBM_Events_PRD.md`, `CBM_Events_Implementation_Plan.md` and
`CBM_Events_Registration_Recognition_Plan.md`. Those three say what the feature
is and how it was built. This document says what is left between today's state
and a finished, live, production feature, in the order it should be done, and
who owns each piece.

**Status:** DRAFT for Doug's approval.

---

## 1. Where it stands (verified 09-08-26)

The feature is a staff application for setting up events and tracking
enrollment, a public application programming interface (API) that feeds the
website, and a public registration path that creates a Contact and an Event
Registration in the customer relationship management system (CRM).

Verified today against the live deployments, not read from the documents:

- Both applications run **v0.221.0** (release tag v0.217.0). Six local commits
  are unpushed; none touch events.
- **crm-test** has Events switched on. The staff application answers (401 for an
  anonymous caller, as expected) and the public API serves the sandbox's
  published events at `/api/events/upcoming`.
- **Production** has Events switched off: the staff routes and the public API
  both 404. Production's CRM schema was migrated on 2026-08-09 and its `CEvent`
  entity holds no records, so the first published event there will be a real
  one.
- **The website still runs on the Google Apps Script.** `clevelandbusinessmentors.org/webinars/`
  answers 200 and is fed by the script plus a browser-side YouTube call whose key
  is visible in the page source. Every registrant there is still an invisible
  lead. That is the problem the whole feature exists to fix, and it is unchanged.

Built and verified: Phases 0, 1, 3, 5 and 6c (reporting).
Built and **never run against their external service**: Phase 2 (Zoom
provisioning), 6a (attendance from the Zoom report), 6b (follow-up email), 6d
(YouTube backfill).
**Not built:** Phase 4, the WordPress plugin and the cutover. The repository
holds only the renderer (`wp-plugin/cbm-events/assets/cbm-events.js`) and the
site's stylesheet. There is no plugin file, no server-side proxy, no thumbnail
proxy, no per-event page and no settings screen.
**Designed, not built:** registration recognition (the five-step plan), and its
prerequisite fix to the near-duplicate hold.

---

## 2. What "finalized" means

The feature is finished when all of the following are true on **production**:

1. The live `/webinars/` page renders from the application's API and looks the
   same as today at desktop and phone widths.
2. A registration from that page creates a Contact and an Event Registration in
   the production CRM, and the visitor receives a confirmation.
3. Each event has a shareable page of its own.
4. The page still renders when the application is unreachable.
5. A person registering for two events on one day gets both registrations.
6. Staff create, publish, run and report on an event entirely in `/events`,
   signed in as a non-admin member of the Marketing Admin Team.
7. The Google Apps Script is retired and its exposed YouTube key is rotated.

Items 1–5 and 7 are the **lead-leak fix**. Item 6 is the programme-management
tool. The Zoom automation, the follow-up emails and registration recognition
make the tool better but are not required for any of the seven.

---

## 3. The work, in five tracks

Tracks A and B are the finish line. C, D and E improve the tool and can run in
parallel or after. Each item names its owner: **Doug** (access, credentials,
site changes, rulings), **build** (code in this repository), or **verify** (a
live pass, always as a real non-admin where a gate is involved).

### Track A — The cutover (Phase 4). Ends the lead leak.

| # | Item | Owner | Depends on |
|---|---|---|---|
| A1 | Share the **Apps Script source and its Google Sheet**. The script's real behaviour is the parity baseline (PRD R-1); so far it is inferred from network traffic. | Doug | — |
| A2 | Confirm **WordPress plugin-install rights** and export the current `/webinars/` page content as the rollback copy. | Doug | — |
| A3 | **Scope the near-duplicate hold per event** (`OPEN-ITEMS.md` 19f). Give the form specification an optional payload key that joins the match, so event registration matches on form + email + event. Test: two events, one email, both deliver; the same event twice still holds. | build | — |
| A4 | **Decide the consent wording** in the sign-up modal (19d). The line copied from the live page covers marketing email only; `consent: true` also records terms-of-use, privacy-policy and code-of-conduct acceptance. Options in § 4. | Doug rules, build | — |
| A5 | **Build the WordPress plugin** (`wp-plugin/cbm-events/`): the plugin file with header, asset enqueue and a settings screen (API base URL, cache lifetime, on/off); the three shortcodes emitting the EV-01 class contract; a server-side proxy under `/wp-json/cbm-events/v1/` that caches in transients (about 60 s) and **serves stale on error**; a same-origin **thumbnail proxy** and **image proxy** (hotlinked YouTube thumbnails 503 on that page); the sign-up modal posting through the proxy, with the 409 refusals rendered as readable messages; per-event pages at `/webinars/<slug>` with title, meta description and Open Graph tags. Do not rewrite the renderer; build around it. | build | A1 |
| A6 | **Local WordPress harness.** A throwaway WordPress in Docker pointed at the crm-test API, so the plugin is driven end to end before it touches the real site. Screenshots at desktop and phone widths against the live page. | build + verify | A5 |
| A7 | **Switch production on.** Run `scripts/probe_events_schema.py` inside the production web container and diff against crm-test; set `EVENTS_ENABLED`, `EVENTS_PUBLIC_API` and `EVENTS_PUBLIC_BASE_URL` (at `/setup`, or the production overlay); confirm Marketing Admin Team membership is the intended event-administration group. | Doug + build | A3, A4 |
| A8 | **Staging page on the real site.** Install the plugin with rendering off; confirm the proxy returns production data; build a preview page from the shortcodes; compare side by side with the live page at both widths. | Doug + verify | A5, A6, A7 |
| A9 | **Cutover.** Freeze new events in the Apps Script; create the same upcoming events in production `/events`; swap the page's two HTML widgets for the shortcodes; set the Elementor container's Content Width (Full Width or 1600 px, Doug's choice — a page setting, never a plugin stylesheet rule); register once with obvious test data through the live page and delete the records; watch one event cycle. | Doug + verify | A8 |
| A10 | **Retire.** After the rollback window, remove the Apps Script, **rotate the exposed YouTube key** (R-7), and fix the mismatched contact address on the page (R-8, `info@clbmentors.org` in the footer). | Doug | A9 |

### Track B — Live verification already owed on crm-test. Can start today.

| # | Item | Owner |
|---|---|---|
| B1 | **Phase 5 as a real non-admin** Marketing Admin Team user: the team gate, the grid, the detail tabs, check-in. Every earlier pass stubbed the session, so the non-admin CRM access has never been exercised. | verify |
| B2 | **The Add / Edit editor** (v0.202.0): create and edit one event; rich text round-trips to `eventOverview` / `eventSyllabus` and renders on the preview; the Duration select still produces the right `dateEnd`; the graphic uploads. | verify |
| B3 | **The preview against the live page** (19e): `/events/preview.html` on crm-test beside `clevelandbusinessmentors.org/webinars/`; click a title through to its page; register once with test data and delete the records. | verify |
| B4 | **Reporting with real numbers** (6c): mark one crm-test registration Attended and confirm the engagement Events tab, the contact history and the programme reports show it. | verify |

crm-test resets nightly at 04:00 UTC, so each pass is a single-day job or it
starts again.

### Track C — Zoom. Makes online events automatic.

| # | Item | Owner | Depends on |
|---|---|---|---|
| C1 | Create the **Server-to-Server OAuth application** in the Zoom Marketplace under the `zweb@cbmentors.org` account; capture Account ID, Client ID and Client Secret; grant webinar, registrant, report and user scopes; note the per-webinar attendee ceiling on the licence. | Doug | — |
| C2 | Run `scripts/probe_zoom.py` (read-only). Green means the scopes and the reporting licence are right. | verify | C1 |
| C3 | **Phase 2 live on crm-test:** publish a test event → webinar exists with registration on and Zoom reminders off; edit the time → patched; cancel → cancelled; a registrant gets exactly one Zoom confirmation. | verify | C2 |
| C4 | **6a live:** a real webinar with real participants, then confirm the worker marks attended and no-show correctly and leaves hand-set attendance alone. Needs the worker flag on. | verify | C3 |
| C5 | Switch `ZOOM_EVENTS` on in production. | Doug | C4 |

Until C5, staff paste an existing webinar link into the event (the
link-existing path, EV-23). The cutover does not wait for Zoom.

### Track D — Email. Confirmation and follow-ups.

| # | Item | Owner | Depends on |
|---|---|---|---|
| D1 | Author the **five EspoCRM templates** on both CRMs, named exactly: `EventReminder`, `EventRecordingAvailable`, `EventNoShow`, `EventMentorCTA`, `EventSurvey`. Templates survive the crm-test reset. | Doug (wording), build (names, placeholders) | — |
| D2 | **Build the Follow-up tab frontend.** The endpoints exist; the tab does not call them. Preview by default, send on confirmation, ledger shown per registrant. | build | — |
| D3 | **Build the CBM confirmation email** (recognition plan step 2): a single-recipient send from a sixth template, `EventConfirmation`, ledgered on `followUpsSent`. This is what makes "check your email" true for in-person events, and it is where the re-arm and correction links will live. | build | D1 |
| D4 | Switch `EVENTS_REMINDERS` on for the **worker** in production; confirm one reminder goes out 24 hours ahead and Zoom's does not. | Doug + verify | D1, C3 |

### Track E — After the cutover. Not part of finalization.

- Registration recognition steps 3–5 (email-first lookup, device token, member
  redirect handoff). The three undecided points in that plan stay undecided
  until D3 exists.
- 6d YouTube backfill against the real playlist: dry-run on crm-test first;
  needs a YouTube Data API key and the playlist id.
- A member-facing event list inside the portal, if members should not register
  from the public page.

---

## 4. Decisions Doug owns

Two decisions shape the build. The rest are rulings recorded already.

**Decision 1 — Sequencing: cut over before Zoom, or wait for Zoom?**
Cutting over first (Track A, then C) stops the lead leak as soon as the plugin
is verified; online events carry a hand-pasted Zoom link until Track C lands.
Waiting for Zoom ships one coordinated change but leaves every registrant
invisible for as long as the OAuth application takes. **Recommendation: cut
over first.** Cost: a few weeks of staff pasting webinar links by hand.

**Decision 2 — Consent wording in the sign-up modal (19d).**
(a) A **consent checkbox** naming the three policies, like the intake forms. It
is unambiguous evidence of acceptance; the cost is a visible change to a page
visitors know and one more click. (b) **Consent text** under the button naming
the three policies with links, no checkbox. It keeps one-click sign-up; the
cost is weaker evidence than an affirmative tick. **Recommendation: (a), the
checkbox** — it matches what every other public form on the site does, and
`consent: true` should never be written on the strength of a sentence nobody
had to read.

Smaller choices, decided at the step: the Elementor container width (Full
Width or 1600 px, A9); template wording (D1); whether the Apps Script rollback
window is one event cycle or two (A10).

---

## 5. Sequence

```
A1 A2 (Doug)  ─┐
A3 A4 (build) ─┼─> A5 plugin ─> A6 local harness ─> A8 staging ─> A9 cutover ─> A10 retire
A7 prod on    ─┘                                          ▲
B1–B4 (crm-test, any day)                                 │
C1 (Doug) ─> C2 ─> C3 ─> C4 ─> C5 ─────────────────────────┘ (optional before A9)
D1 (Doug) ─> D2 D3 ─> D4
```

The critical path is A1 → A5 → A6 → A8 → A9. Everything Doug owns on that path
(A1, A2, A7's flags, A8's install, A9's page edit) is short; the long item is
A5, the plugin build.

---

## 6. Verification gates

Nothing on Track A reaches the live page without: the house test suite green
with new coverage · the plugin driven in the local WordPress harness · the
staging page compared side by side at desktop and phone widths · a real
registration through the staging page landing in the production CRM.

The single most important test remains the first real event end to end on
production: create → publish → a real person registers from the website →
Contact and registration in the CRM → confirmation arrives → event runs →
attendance recorded → recording link pasted → the engagement rollup shows it.

---

## 7. What this plan deliberately leaves out

- A dedicated approval queue for registrations. The Registrants tab and the CRM
  are the review path.
- Any change to the staff session cookie for member recognition. The redirect
  handoff is the agreed design.
- Restyling the site's stylesheet. It ships verbatim and stays in sync with the
  live page.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-08-26 19:05 | Claude (Claude Code) | First draft. State verified against both live deployments and the website; seven-point definition of done; five tracks with owners and dependencies; two decisions for Doug. |
