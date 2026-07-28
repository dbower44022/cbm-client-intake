# Kickoff — Events & Webinars, Phase 4 (WordPress plugin + cutover)

Paste this into a fresh session. Everything you need to orient is here; the
detail lives in the docs it names.

---

## Where the project is

The Events & Webinars feature replaces the data layer behind
`https://clevelandbusinessmentors.org/webinars/`. Today that page runs on a
**Google Apps Script** plus a **browser-side YouTube Data API call** (key
visible in page source), and EspoCRM is involved at no point — so every
registrant is an invisible lead.

**Built and committed** (read `CHANGELOG.md` 0.164.0 → 0.170.0):

| Phase | State |
|---|---|
| 0 — decisions + CRM schema | ✅ Applied and verified on **crm-test**. Prod NOT migrated. |
| 1 — CRM read layer + public API | ✅ Live-verified on crm-test |
| 2 — Zoom client + provisioning | ✅ Built; unit-tested against a stubbed Zoom. **Never run against real Zoom** (no OAuth app yet) |
| 3 — public registration into the CRM | ✅ Live-verified end to end on crm-test |
| 5 — `/events` staff app | ✅ Built; browser-verified on crm-test with a **stubbed session** |
| **4 — WordPress plugin + cutover** | ⬅ **this phase** |
| 6 — attendance, follow-up email, reporting | Not started |

Plan and requirements: `prds/events/CBM_Events_Implementation_Plan.md`,
`prds/events/CBM_Events_PRD.md`. Staff guide: `event-administration.md`.
Activation/testing: `EVENTS-SETUP.md`.

**Nothing is switched on.** `EVENTS_ENABLED`, `EVENTS_PUBLIC_API` and
`ZOOM_EVENTS` all default off.

---

## Check these before you plan anything

Facts change; verify rather than trust this file.

1. **Is the code pushed and deployed?**
   `curl -s https://cbm-client-intake-svxs3.ondigitalocean.app/healthz`
   — expect 0.170.0 or later.
2. **Has Doug tested Phase 5?** `EVENTS-SETUP.md` §4 is the script he was given.
   Ask what he found; fix fallout before building more.
3. **Do the three blockers still stand?** Each is Doug's to clear:
   - the **Zoom Server-to-Server OAuth app** (`scripts/probe_zoom.py` verifies it),
   - the **Apps Script source + its Google Sheet** — the parity baseline for
     this phase; behaviour so far is *inferred from network traffic*,
   - **WordPress plugin-install rights** and a backup of the current page.

**If WordPress access isn't available, do not stall.** Switch to **Phase 6c —
reporting**, which is fully unblocked and includes the engagement rollup Doug
explicitly asked for (PRD D-22 / EV-72: events attended, aggregated across all
of an engagement's contacts). Say you're switching and why.

---

## Phase 4 scope

Ship a small, versioned **WordPress plugin** (`wp-plugin/cbm-events/`) that
feeds the existing page from our API, plus per-event pages, then cut over.

**Already written:** `wp-plugin/cbm-events/assets/cbm-events.js` — the renderer.
It emits exactly the DOM the live page already styles, and was **driven inside
the real live page** in a browser (client-side only, nothing deployed) with real
CRM data. It works. Don't rewrite it; build the plugin around it.

**To build:**
- `cbm-events.php` — plugin header, asset enqueue, settings (API base URL,
  cache TTL, on/off).
- Shortcodes `[cbm_events_calendar]`, `[cbm_events_recordings]`,
  `[cbm_event_signup]` emitting the EV-01 class contract.
- A **server-side proxy** (`/wp-json/cbm-events/v1/…`) that calls our API,
  caches in transients (~60s), and **serves stale on error** (EV-07). This is
  also why no CORS is needed.
- A **thumbnail proxy** endpoint — see the trap below.
- The sign-up modal wired to `POST /api/events/{slug}/register`, including the
  409 refusals (closed / cancelled / unknown) rendered as readable messages.
- Per-event pages at `/webinars/{slug}` with title, meta description and Open
  Graph tags (EV-06).

---

## Traps that have already bitten this work

**1. Thumbnails must be proxied, not hotlinked.** During the preview, every
hotlinked `i.ytimg.com` URL returned **HTTP 503** on that page, while the site's
own thumbnails loaded — which is why the current page already ships
`/wp-json/cbm-yt/v1/thumbnails`. The renderer takes
`CBMEvents.config.thumbnailProxy`; the plugin must supply it. Shipped
hotlinked, the recorded library is a wall of black boxes.

**2. `topic` means the TITLE in the public payload.** The old Apps Script speaks
Zoom's vocabulary. The CRM's subject category rides as `category`. Aligning
those names would blank every title on the live site. Documented at the top of
`events/config.py`.

**3. The class contract is load-bearing.** Elementor's CSS keys on
`.cbm-wb`, `.event-item`, `.event-date__month`, `.cbm-modal`, `#cbm-signup-form`
and friends (full list in PRD EV-01). Renaming one silently unstyles a section.

**4. Live verification catches what tests cannot.** Two real bugs shipped past
green unit tests and were caught only by driving the thing: a CRM enum mismatch
(`registrationSource: "Website"` — the real value is `"Online"`) and an N+1 that
made the staff grid issue 98 sequential CRM queries. Drive it.

---

## Cutover — reversible, and not to be rushed

The procedure is in the plan; the shape is:

1. Install the plugin with rendering **off**; confirm the proxy returns correct
   data.
2. Build a staging/preview page with the shortcodes and compare side by side.
   *(The desktop comparison is already done — screenshots in the session that
   built the renderer. **Mobile widths are not.**)*
3. Freeze new events in the Apps Script; create the same events in `/events`.
4. Swap the page's widgets to the shortcodes. Watch one event cycle.
5. Keep the Apps Script deployed but idle as a rollback window, then retire it
   and **rotate the exposed YouTube API key**.

Production also needs, before any of this matters publicly: the **prod CRM
schema migration** (`scripts/migrate_event_schema.py`, then
`scripts/probe_events_schema.py` to diff against crm-test) and the flags on
`.do/app.prod-crm.yaml`.

---

## House rules that apply

- **Verify, don't assume.** Probe the CRM and the live page; this project has
  been bitten repeatedly by drift between crm-test and prod.
- **Commit, don't push** unless asked. Version races are common — check
  `pyproject.toml` and `CHANGELOG.md` before claiming a version; a parallel
  session has taken the next number three times in this arc.
- **Clean up test records** and say what you left behind.
- Buttons are never disabled or hidden; they validate on click.
- No page-width caps.
- Update `CLAUDE.md`'s Current status when the phase lands.

---

## Definition of done

The live `/webinars/` page renders from our API, looks the same as it does
today at desktop **and** mobile widths, a real registration from that page
creates a Contact and a registration record in EspoCRM, each event has a
shareable URL, and the page still renders if our app is unreachable.
