# CBM Events & Webinars — Implementation Plan

Companion to `CBM_Events_PRD.md`. This is the build order, the file-level
design, and the verification gates. Requirement ids (`EV-nn`) and decision ids
(`D-nn`) refer to the PRD.

**Status:** Phase 0 complete (all decisions settled, schema applied on BOTH
CRMs — prod caught up 2026-08-09).
**Phases 1, 2, 3, 5 and 6 are BUILT. Phase 4 (WordPress plugin + cutover) is the
only one left**, and it is the one that ends the lead leak.

Live on crm-test since 2026-08-09 (`EVENTS_ENABLED` + `EVENTS_PUBLIC_API`); off
on prod. Verified against the real CRM there: the staff app, the event graphic,
the publish gate (page, payload AND image), a real public registration creating
a Contact + CEventRegistration, its intake receipt, and the website preview.

**Phase 6, built 2026-08-10 to 2026-08-16:**

- **6a attendance** (v0.193.0) — `events/attendance.py` + worker timer.
  **Never run against real Zoom.**
- **6b follow-up email** (v0.201.0) — `events/notify.py` + reminder timer.
  **Needs five EspoCRM templates; no frontend yet.**
- **6c reporting** (v0.194.0, frontends v0.199.0/v0.199.1) — engagement rollup,
  contact history, programme + conversion reports. Complete.
- **6d YouTube backfill** (v0.200.0) — `scripts/import_youtube_events.py`.
  **Never run against the real playlist.**

What is *built* is wider than what is *verified* — 6a, 6b and 6d have all been
unit-tested but never driven against their external service.

---

## 0. Shape of the work

Everything follows patterns this repo already runs in production, so almost
nothing here is novel infrastructure:

| New thing | Existing pattern it copies |
|---|---|
| `core/zoom.py` | `core/gcalendar.py` / `core/fathom.py` — a thin typed REST client with token caching and backoff. |
| Public registration | The five intake forms: durable capture → worker → orchestrator, honeypot + rate limit + idempotency token. |
| `events/` staff app | `sessions/` + `ops/` — team-gated router, field-spec-driven editor, house grid. |
| Attendance retrieval | `sessions/transcripts.py` — worker timer, candidate query, give-up window, best-effort. |
| Follow-up email | `comms/` shared-identity send + EspoCRM templates + write-back. |
| CRM entities | `CInformationRequest` / `CContribution` — feature-detected, app deploys ahead of the CRM build. |
| WordPress plugin | New to this repo, but a thin, boring shortcode plugin. |

**Feature flags:** `EVENTS_ENABLED` (whole feature, default off),
`ZOOM_EVENTS` (Zoom calls, default off — the app functions without Zoom for
in-person events), `EVENTS_PUBLIC_API` (public endpoints, default off until
cutover). Every CRM write feature-detects its entity, so a deploy before the CRM
build is inert, not broken.

---

## Phase 0 — Prerequisites (Doug + CRM team; no app code)

Nothing else can be verified live until these exist. Each has a probe so we
confirm rather than assume.

1. **Zoom (D-04).** Host account is **`zweb@cbmentors.org`** — every webinar
   runs under it, and it is the `ZOOM_HOST_EMAIL` setting.
   - ☐ Confirm the plan on that account includes **Webinars** and **reporting**.
   - ☐ Create a **Server-to-Server OAuth** app in the Zoom Marketplace; capture
     Account ID, Client ID, Client Secret. *(Doug, 2026-07-25: "I will create
     the oAuth account later" — the build is not blocked; Phases 1, 3's CRM
     half, 4, and 5 proceed behind the `ZOOM_EVENTS` flag, and Phase 2 lands
     with unit tests against a stubbed Zoom until real credentials exist.)*
   - ☐ Grant scopes for: webinar read/write, registrant read/write, report read,
     user read. *(Zoom's granular scope names shift between API versions — the
     exact list gets pinned by the read-only probe below.)*
   - ☐ Note the **per-webinar attendee ceiling** on that licence (it caps what
     `CEvent.capacity` can usefully be set to).
   - **Probe** (`scripts/probe_zoom.py`, read-only): lists webinars for
     `zweb@cbmentors.org` and fetches one past participant report. Green =
     scopes correct and reporting is available on the plan.
2. **CRM entities.** ✅ **Both already exist on crm-test** (verified 2026-07-25) —
   this is now a **modification**, not a build. Apply the change list in
   `../../cevent-entities-crm-handoff.md` (§2 CEvent, §3 CEventRegistration,
   §4 the readOnly fixes, §6 permissions), crm-test first, then prod.
   Blocking sub-items:
   - ☑ **Handoff §1 DECIDED** — the public programme shares the existing
     `CEvent`, gated by `publishToWebsite` (D-24).
   - ☑ **Handoff §5 DECIDED** — keep the existing 10-value `topic` list; no
     schema change required.
   - ☑ `readOnly` flags cleared and the whole change list applied to crm-test
     (2026-07-25) — verified by a real API-user write of all 17 fields.
   - ☐ Verify prod parity (handoff §7) — prod was not probed.
3. **Teams.** Confirm `Marketing Admin Team` membership is who should administer
   events (it currently gates `/ops`).
4. **WordPress.** Confirm plugin-install rights on the site and take a backup /
   export of the current `/webinars/` page content before any change.
5. **Apps Script + Sheet (R-1).** Doug shares the current script source and the
   backing sheet so parity is measured against reality, not inference.
6. **Email templates.** Decide the five template names; they can be authored in
   EspoCRM at any point before Phase 6.
7. **Topic vocabulary.** ✅ **Settled 2026-07-25 — keep the existing curated
   10-value `CEvent.topic` list** (supersedes D-18's `areaOfExpertise` choice).
   **No CRM change needed.** Handoff §5.

**Gate:** ✅ the entity modifications are applied on crm-test (Phase 1 unblocked) · Zoom probe green (blocks *only* the Phase 2 live
verification, not the Phase 2 build).

*Re-run the schema probe after the CRM changes and diff it against the change
list — the same read-only probe used for this review
(`scripts/probe_events_schema.py`, to be committed alongside Phase 1).*

---

## Phase 1 — CRM layer and read-only public API  ✅ DONE (v0.164.0)

**Goal:** events exist as CRM records and our API can serve the page's data.
Nothing public changes yet.

**Build**
- `events/__init__.py`, `events/config.py` — the single field spec
  (`EVENT_FIELDS`) that drives both the editor layout and the server-side write
  whitelist; enum options and required flags read live from CRM metadata.
- `events/service.py` — CRUD over `CEvent` / `CEventRegistration` as the
  signed-in user (ACL is the gate), plus the derived numbers
  (`event_summary()`: registered / waitlisted / cancelled / attended / no-show /
  show-rate / seats remaining — computed, never stored, EV-35).
- `events/public.py` — the public read endpoints (EV-01…EV-06 data), reading
  through the **API-key client** (no session), shaped to the today's-keys
  contract in PRD §6, with short-TTL in-process caching.
- Slug generation + uniqueness on save.
- `core/youtube.py` — server-side YouTube metadata/thumbnail fetch, so the key
  leaves the browser (EV-05).

**Tests:** service CRUD, derived counts (incl. edge cases: no registrations,
all cancelled, capacity zero/unlimited), slug collisions, public payload shape
matches the documented contract exactly, timezone round-trip (EV-85).

**Verify live (crm-test): ✅ PASSED 2026-07-25.** Three real `CEvent` records
(published upcoming, past-with-recording, unpublished internal) read back through
the app: correct Cleveland-local time strings (`2:00 PM - 3:30 PM | WEBINAR`),
the internal meeting absent from the calendar and 404 on its own slug, recording
search + derived thumbnail, per-event detail. Test records deleted, no residue.

---

## Phase 2 — Zoom client and webinar provisioning  ✅ BUILT (v0.165.0)

**Build**
- `core/zoom.py` — `ZoomClient`:
  - S2S OAuth token fetch + cache + refresh;
  - `create_webinar` / `update_webinar` / `delete_webinar`;
  - `add_registrant` / `cancel_registrant`;
  - `list_participants` (past-webinar report);
  - 429/5xx backoff honoring `Retry-After`, one shared connection, typed
    `ZoomError` / `ZoomTransportError` so existing error nets catch it (EV-25);
  - module docstring = the verified integration contract (the `comms/templates.py`
    convention).
- `events/zoom_sync.py` — the decision layer: publish → create; edit → patch;
  cancel → cancel; link-existing (EV-23); **registration on, auto-approve,
  Zoom reminders off** (EV-24). Best-effort: never fails a save; result rides
  the response as `zoom:{ok,…}` and is retried by the worker.

**Tests:** the decision matrix, token refresh, backoff, and "Zoom is down" —
every path degrades to a warning.

**Verify live — ☐ BLOCKED on the OAuth app.** When it exists: run
`scripts/probe_zoom.py` (authenticates, checks the webinar licence, lists
webinars, reads a past participant report — the check most likely to fail).
Then: publish a test event → webinar appears in Zoom with registration enabled
and **reminders off**; edit the time → patched; cancel → cancelled; and confirm
a registrant receives exactly ONE confirmation and no Zoom reminder.

---

## Phase 3 — Public registration write path  ✅ DONE (v0.166.0)

**Build**
- `forms/event_registration/` — schemas + orchestrator, registered in the form
  registry so it inherits **durable capture, idempotency, retries, resumable
  delivery, and `/ops` visibility for free** (EV-11).
  Orchestrator steps (each a named resumable step, so a retry never duplicates):
  Contact find-or-create/null-fill → consent stamp → CEventRegistration →
  Zoom registrant push.
- Capacity/waitlist evaluation at delivery time (EV-15) with promotion on
  cancellation.
- Cancel token = HMAC of the registration id keyed by the app secret —
  stateless, unguessable, constant-time compared (EV-16, EV-83).
- Registration closed / event full / event cancelled → readable refusals
  (EV-14).
- Auto-close the durable submission on success (the "Process completed" rule),
  so registrations don't pile up in the Submission Admin open queue.

**Tests:** dedupe (EV-13), waitlist + promotion, closed-registration refusal,
consent never flipped false, existing-Contact type preserved (D-09), honeypot
and rate limit, resumability (half-delivered → converges to one clean set).

**Verify live (crm-test): ✅ PASSED 2026-07-25** for everything not needing Zoom
— register → Contact (Prospect, consent, zip, E.164 phone) + linked
registration; same email again → updated, same id; capacity 2 → third person
Waitlisted; cancel → seat freed and the waitlisted person auto-promoted; forged
token → 404; unknown/cancelled event → readable 409. Records cleaned up.
☐ **Still to verify when Zoom credentials exist:** registrant appears in Zoom,
the confirmation email arrives with a working join link, and a cancel removes
them from Zoom.

---

## Phase 4 — WordPress plugin and cutover

**Build** — `wp-plugin/cbm-events/` in this repo:
- Shortcodes `[cbm_events_calendar]`, `[cbm_events_recordings]`,
  `[cbm_event_signup]`, emitting **exactly** the DOM/class contract in EV-01 so
  the existing Elementor CSS applies unchanged.
- A **server-side proxy** (`/wp-json/cbm-events/v1/…`) that calls our API,
  caches in transients (~60s), and **serves stale on error** (EV-07) — this is
  also why no CORS is needed and why visitors' browsers never see our host.
- Per-event pages: a rewrite rule for `/webinars/<slug>` rendered by the plugin
  with title/meta/OG tags (EV-06).
- One settings screen: API base URL, cache TTL, on/off switch.

**Preview done ahead of the build (2026-07-25).** The renderer
(`wp-plugin/cbm-events/assets/cbm-events.js`) was driven **inside the real live
page**, client-side in a browser only — no plugin installed, nothing deployed,
production untouched — with real CRM data from a locally-run app against
crm-test. Both panels rendered correctly under the site's own Elementor CSS,
confirming the class contract in EV-01. Preview events were seeded on crm-test
and deleted afterwards (back to 92 events / 0 registrations).

**The plugin also ships the page's stylesheet** (`assets/cbm-events.css`, added
2026-08-16). The live page keeps its CSS **inline inside the two Elementor HTML
widgets**, and cutover replaces those widgets — so the plugin has to carry the
styling with the markup or the page unstyles at the swap. It is a verbatim copy
of both `<style>` blocks; keep it in sync with the live page rather than editing
it to taste. The app's preview loads this file, so the preview is now an exact
colour/type check rather than an approximation.

**Second finding, from doing that (2026-08-16):** the recorded-library half of
the renderer was **off the class contract** — `video-date` / `video-title` /
`video-summary` against a stylesheet that only knows `video-info__date` /
`__title` / `__meta`, plus a play overlay with no inline `<svg>`. It rendered as
unstyled text on the site. The July preview pass confirmed the contract down to
`.video-item` / `.video-info` and the inner text classes slipped through, then
stayed hidden because the preview's own CSS styled our wrong names. Fixed, and
`tests/test_events_graphic.py` now asserts every emitted contract class has a
rule in the stylesheet.

**Registration stays a modal on the calendar** (Doug, 2026-08-16). The
per-event page is for reading about an event; signing up from the list keeps its
one click, exactly as visitors know it today. `CBMEvents.mountSignupModal()`
emits the site's existing modal DOM and the host supplies the POST — the plugin
through its proxy, the preview straight to `/api/events/{slug}/register`. The
open question there is consent wording (`OPEN-ITEMS.md` 19d).

**Per-event links need a host-supplied base.** The public payload's `url` is
always the live site's `/webinars/<slug>`, so anywhere but the website it 404s.
The renderer takes `CBMEvents.config.eventUrlBase`; the plugin sets it to its
own page URL, the preview to its stand-in page.

**Finding that changed the design:** hotlinked `i.ytimg.com` thumbnails returned
**HTTP 503** on that page, while the site's own proxied thumbnails loaded — which
is why the current page already ships a `/wp-json/cbm-yt/v1/thumbnails`
endpoint. The renderer now takes a **same-origin thumbnail proxy**
(`CBMEvents.config.thumbnailProxy`) instead of hotlinking; the plugin must
provide that endpoint. This would have shipped as a wall of black boxes.

**Cutover procedure (reversible):**
1. Install the plugin on the site with rendering **off**; verify the proxy
   returns correct data.
2. Stand up a staging/preview page using the shortcodes; compare **side by side**
   with the live page — screenshots at desktop and mobile widths. *(The
   desktop comparison is already done — see the preview note above.)*
3. Freeze new events in the Apps Script; create the same events in the app.
4. Swap the page's widgets to the shortcodes. Watch for one event cycle.
5. Keep the Apps Script deployed but idle for a rollback window, then retire it
   and **rotate the exposed YouTube API key** (R-7).

**Verify:** a real registration through the live page end-to-end; the page
renders identically; API down → cached content still renders.

---

## Phase 5 — Staff app `/events`  ✅ DONE (v0.168.0)

**Build**
- `events/router.py` — team-gated (`EVENTS_ALLOWED_TEAMS`, default
  `Marketing Admin Team`), mounted when `assignments_active`; portal tile.
- `events/frontend/` — vanilla JS, no build step:
  - **grid** (EV-51) using the shared grid behaviors (sort, resize, search,
    sticky header, right-click menu);
  - **detail** with Overview / Registrants / Check-in / Follow-up tabs (EV-52);
  - **editor** from the field spec, diffed saves, live enum options (EV-53);
  - actions with confirm modals, never-disabled buttons (EV-54);
  - **check-in** view sized for a phone: search, tap to mark arrived, add
    walk-in (EV-33);
  - `frontend/shared/busy.js` loaded first, per the standing convention.
- Action logging on every mutation (EV-56).

**Verify: ✅ browser pass against crm-test 2026-07-26** — grid/filter/detail/
tabs, and a real walk-in GET-verified in the CRM as a Prospect Contact +
Attended registration; records cleaned up. Caught three defects tests could not
(grid N+1, `display:flex` beating `[hidden]`, check-in tab resetting).
☐ **Still to do:** a pass signed in as a REAL non-admin Marketing Admin user
(the harness stubbed the session), which is what exercises the team gate and
the CRM ACL for a non-admin.

---

## Phase 6 — Attendance, follow-up email, reporting

**6a. Attendance (EV-30…EV-35)**
- `events/attendance.py` + a worker timer (`EVENTS_ATTENDANCE_SECONDS`):
  candidates = online events ended > grace and < give-up window with attendance
  not yet resolved → pull report → match by email → write results; unmatched
  participants recorded and flagged (EV-32); manual corrections respected
  (EV-34); per-pass totals logged, repeated failure alerts (EV-86).

**6b. Follow-up email (EV-60…EV-64)**
- `events/notify.py`: reminder, recording-available, no-show re-engagement,
  mentor CTA, survey — rendered from EspoCRM templates, sent as the shared
  info@ identity through the existing send path with CRM write-back.
- A per-registrant **send ledger** so each kind sends once (EV-62); cancelled
  and opted-out excluded (EV-63); manual preview/trigger from the Follow-up tab
  (EV-64).
- Worker timer for time-based sends (reminders), event-driven for the rest.

**6c. Reporting (EV-70…EV-74)**
- Event stats on the Overview tab.
- **Contact history** panel on the directory contact page (EV-71).
- **Engagement rollup** (EV-72, Doug's explicit ask): an **Events tab** on the
  mentor-domain record detail, gated by a `DomainConfig` flag exactly like
  Referred Clients and Contributions — so the partner/funder routers never
  register it. It gathers the engagement's contacts (primary + related),
  queries their attended registrations, deduplicates by event, and shows
  date · event · which of the engagement's people attended.
- **Conversion report** (EV-73) and program totals (EV-74) as a report view in
  `/events`.

**6d. Migration (EV-42)**
- `scripts/import_youtube_events.py` — dry-run by default, `--write` applies
  (house convention), creating past events from the playlist and flagging them
  for staff date/topic review.

---

## Files at a glance

```
core/zoom.py                    Zoom S2S client
core/youtube.py                 server-side YouTube metadata/thumbnails
events/__init__.py
events/config.py                EVENT_FIELDS spec = layout + write whitelist
events/service.py               CRUD + derived stats
events/public.py                public read + register endpoints
events/zoom_sync.py             publish/patch/cancel decision layer
events/attendance.py            worker attendance retrieval
events/notify.py                templated follow-up sends
events/router.py                team-gated staff app
events/frontend/                grid, detail tabs, editor, check-in
forms/event_registration/       durable-capture registration form kind
wp-plugin/cbm-events/           WordPress shortcodes + proxy + event pages
scripts/import_youtube_events.py
scripts/probe_zoom.py           read-only Phase 0 probe
tests/test_events_*.py
```

New settings (all defaulted, so the app still boots with none of them):
`events_enabled`, `events_allowed_teams`, `events_public_api`,
`zoom_events`, `zoom_account_id`, `zoom_client_id`, `zoom_client_secret`
(SECRET), `zoom_host_email` (= `zweb@cbmentors.org`), `events_attendance_seconds`,
`events_reminder_hours`, `events_give_up_days`, `youtube_api_key` (SECRET),
`youtube_playlist_id`, `events_public_base_url`.

Deploy targets: web (public API + staff app), worker (attendance + reminders).

---

## Sequencing and dependencies

```
Phase 0  prerequisites ──┬─> Phase 1 CRM + read API ──┬─> Phase 4 WP plugin + cutover
                         │                            │
                         └─> Phase 2 Zoom client ─────┴─> Phase 3 registration ──> Phase 5 staff app ──> Phase 6 attendance/email/reporting
```

Phases 1 and 2 are independent and can be built in either order. Phase 4
(the visible cutover) needs only Phases 1 and 3. Phase 6 needs Phase 5's UI to
land the check-in screen and the follow-up tab.

---

## Verification gates

Each phase ships only when: house test suite green with new coverage ·
UI flows driven in the stub-browser harness · a **live pass on crm-test** ·
and the live-check list written into the changelog entry. Production follows
crm-test verification, as with every other feature.

The single most important live test is the **first real event end to end**:
create → publish → Zoom webinar exists → a real person registers from the
website → Contact and registration in the CRM → Zoom confirmation arrives →
our reminder arrives (and Zoom's does not) → event runs → attendance appears
without anyone touching it → recording link pasted → follow-ups go out →
the engagement rollup shows the attendance.

---

## What could make this smaller, if you want it sooner

If the calendar year argues for a faster first cut, the honest minimum that
still ends the lead leak is **Phases 0–4**: events in the CRM, the page running
off our API, and every registrant becoming a Contact. That is roughly half the
work and delivers the single largest business benefit. Phases 5–6 (staff app
polish, automatic attendance, follow-ups, reporting) are what make it a program
management tool rather than a data capture fix. Doug has asked for all of it in
release one (D-23); this is noted only as a de-scope lever, not a recommendation.
