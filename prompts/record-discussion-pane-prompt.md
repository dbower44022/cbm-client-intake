# Kickoff prompt — bring the Submission-Admin **Discussion** pane to the Partner & Funder Overview

## What to build

Copy the **Discussion UI** from Submission Admin (`/ops`) onto the **Overview**
tab of the **Partner Management** (`/partnersessions`) and **Funder/Sponsor
Management** (`/sponsorsessions`) tools, rendered as a **pane to the LEFT of the
Partner Notes / Sponsor Notes + Session Notes** column. It's the same
attributed, timestamped, staff-only comment stream with an "Add a comment" box
— a place for the managers of a partner/funder to leave running notes to each
other about that record, separate from the record's own Notes field.

**Scope:** the Discussion **pane only** (the comment stream + add box). Do NOT
bring the presence line or the automatic Activity feed — Doug asked for the
Discussion UI specifically. **Partner + Sponsor domains only** (not the mentor
/ client domain) — but implement it as a per-domain flag so mentor could be
switched on later.

## Decisions (settled with Doug 2026-07-23 — build to these)

1. **Where the comments live — DECIDED: Postgres `record_comment` table.**
   The Submission-Admin Discussion is backed by a Postgres table
   (`submission_comment`); this feature uses a generalized Postgres
   `record_comment` table keyed by `(parent_type, parent_id)` (e.g.
   `CPartnerProfile` / `CSponsorProfile` + the record id), reusing the exact
   `submission_comment` pattern — the session tools already run in the same
   FastAPI app, which exposes the durable store at
   `request.app.state.submission_store`. **The discussion is app-only** — it is
   deliberately NOT mirrored into the CRM (a private staff back-channel,
   separate from the record's official Notes; it won't appear in the EspoCRM
   record view, which is intended). (Rejected: CRM Stream notes — not an
   editable, uniformly-attributed comment stream, and it'd surface in the CRM
   record's history, which this deliberately should not.)
2. **Gating / visibility — DECIDED: team-level gating.** Comments are
   **staff-internal**: gated by the domain's existing per-request team gate
   (Partner Management Team / Sponsor Management Team; admins pass), attributed
   to the signed-in user, and **never written to the CRM or shown to the
   partner/funder**. Visibility is **team-wide**, not per-record — any member of
   the domain's team can read and post on any record's discussion (matches how
   the partner/funder grids already list all records to the whole team). Mirrors
   Submission Admin.
3. **Placement / layout — DECIDED: `facts rail | notes | Discussion`, Discussion
   on the far right.** Today the Overview is **facts rail (left) | splitter |
   notes column** (`sx__ov-notes` = overall notes + session-notes feed). Add the
   Discussion pane as a third column to the **right of the notes column**, so the
   order left-to-right is: facts rail, then Session/Partner Notes in the middle,
   then Discussion on the far right. Keep the existing splitter between the rail
   and the content group. No page-width cap
   ([[no-page-width-caps-density-by-packing]]); give the Discussion pane a
   **min-width + wrap** so it drops below the notes column on a narrower window
   instead of crushing the layout. Default widths ~25% rail / ~40% notes / ~35%
   Discussion, tuned by eye in the harness.

## Source to copy (Submission Admin Discussion)

- **Store:** `core/store.py` — the `submission_comment` table (migration 0016)
  + `add_comment` / `list_comments`. Add a **new** generalized `record_comment`
  table `(id, parent_type, parent_id, author, author_name, body, created_at)`
  with an index on `(parent_type, parent_id, created_at)`, plus **new** methods
  (`add_record_comment` / `list_record_comments`). **Leave the existing
  `submission_comment` table + `add_comment`/`list_comments` and the `/ops` code
  paths untouched** — do NOT migrate 0016's data or refactor Submission Admin to
  ride the new table; blast radius on the live queue must be zero. New **Alembic
  migration 0020** (next free number; runs in the pre-deploy migrate job).
  **Attribution mapping:** store `author = user["userName"]` (login) and
  `author_name = user["name"]` (display name) — the ported `initials`/`avatar`
  helpers render from `author_name`, so the display name must land there.
- **Endpoint:** `ops/router.py` — `add_comment` (`POST …/comments`, `CommentIn`),
  and the detail GET returning `comments`. The 503-when-no-store pattern is in
  `ops/router.py:_store`.
- **Frontend render:** `ops/frontend/app.js` — `renderDiscussion`, plus the
  `initials` / `avatar` helpers. (Ignore `renderActivity` / presence.)
- **CSS:** `ops/frontend/styles.css` — `.comment`, `.comment__body`,
  `.comment__meta`, `.comment__add`, `.av` (avatars). Port into
  `sessions/frontend/styles.css` (prefix to the `sx__` namespace).

## Target (the session tools)

- **Config:** `sessions/config.py` — add a `DomainConfig.discussion_enabled: bool
  = False` flag, set `True` on the partner + sponsor entries in `DOMAINS`. Gate
  the endpoint registration on it exactly like `contributions_link` gates the
  contributions routes in `sessions/router.py` (so the mentor router never
  registers it).
- **Backend:** `get_detail(cfg, client, parent_id)` has **no store access** (it
  takes only cfg + client; the router calls it at `sessions/router.py:319`).
  **Read comments in the ROUTER, not the service** — after `get_detail` returns,
  fetch the store from `request.app.state.submission_store` and merge a
  `comments` list into the detail dict (best-effort, only when
  `discussion_enabled`). This keeps `get_detail` pure and avoids threading a
  store param through the service layer. `sessions/router.py` — register
  `GET/POST /{slug}/api/records/{parent_id}/comments` inside `make_router`, gated
  by the flag; parent read AS THE USER first (the ACL gate), comments read/written
  via the store keyed by `(cfg.parent_entity, parent_id)`; attribute to
  `user["userName"]` / `user["name"]` (see the mapping above); 503 if the store
  isn't configured. **Store-off UX:** `DATABASE_URL` is set on both prod and
  crm-test so the store is normally present — but if a `comments` GET 503s, the
  frontend **hides the Discussion pane entirely** (consistent with how the
  comms/docs tabs vanish when their integration is off), not a read-only stub.
- **Frontend:** `sessions/frontend/index.html` — the Overview panel is the
  `sx__ov` / `sx__ov-notes` block (facts rail + `#overallNotes` + Session-notes
  feed). Add a Discussion pane container to the **right** of `sx__ov-notes` (see
  the placement decision above: facts rail | notes | Discussion).
  `sessions/frontend/app.js` — `renderOverview` / `renderOverallNotes` (~L668–L760)
  is where to hook a `renderDiscussion(d)` that reads `d.comments` and posts to
  the new endpoint (mirror the ops add-comment flow: on success **append the new
  comment and clear the box** — no full refetch, matching `/ops`). The stream is
  **append-only, mirroring `/ops`: no edit or delete**. The Add button's press
  feedback is already handled by `frontend/shared/busy.js` (it wraps `fetch`) —
  do NOT add a manual spinner. The shared frontend derives its domain from the
  first URL segment, so one implementation serves both partner and sponsor.

## Conventions (from CLAUDE.md — follow them)

- Vanilla JS, no build step. Keep the sessions app's existing patterns.
- **Tests:** router tests (with a fake store like `tests/test_ops.py`'s
  `FakeOpsStore`) + a **live-Postgres round-trip** of the new store methods
  (`docker compose up -d db`; `TEST_DATABASE_URL=…`; verify migration 0020 up +
  down). Full suite must stay green.
- **Visual-verify in the sessions stub-harness** before claiming it works
  ([[sessions-frontend-stub-harness]]); verify with a **real click / computed
  styles**, not just `el.hidden` ([[harness-js-clicks-bypass-overlays]] — a
  `display:flex` panel can beat `[hidden]`).
- Bump `pyproject.toml` version + add a CHANGELOG entry + update the Session
  Management section of CLAUDE.md (and `communications-tab.md` if the pane is
  worth a line for staff).
- **Push convention:** commit locally; **Doug reviews and pushes** unless he says
  otherwise. A push deploys **crm-test AND prod** (deploy-on-push) and runs
  migration 0020 pre-deploy.

## Definition of done

Partner and Funder Overview pages show a Discussion pane (attributed,
append-only comments + add box — no edit/delete) to the left of the record's
Notes, backed by the new `record_comment` store keyed by
`(parent_type, parent_id)`, gated to the domain team, staff-internal; the pane
hides itself if the store is unavailable (503); the existing Submission-Admin
`submission_comment` path is untouched; the mentor domain is unchanged; tests +
pg round-trip green (migration 0020 up + down); stub-harness verified; docs +
version bumped; committed for Doug's review.
