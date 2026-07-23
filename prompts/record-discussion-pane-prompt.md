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

## Confirm with Doug BEFORE building (this repo elicits first)

1. **Where the comments live — the one real decision.** The Submission-Admin
   Discussion is backed by a Postgres table (`submission_comment`). Partner /
   sponsor records are CRM entities, so their comments need a home. **Recommended:
   a generalized Postgres `record_comment` table keyed by `(parent_type,
   parent_id)`** (e.g. `CPartnerProfile` / `CSponsorProfile` + the record id),
   reusing the exact `submission_comment` pattern — the session tools already
   run in the same FastAPI app, which exposes the durable store at
   `request.app.state.submission_store`. (Alternative considered and NOT
   recommended: CRM Stream notes — not an editable, uniformly-attributed comment
   stream, and it'd surface in the CRM record's history, which these deliberately
   should not.) **Get Doug's yes on the Postgres table before coding.**
2. **Gating / visibility.** Comments are **staff-internal**: gated by the
   domain's existing team gate (Partner Management Team / Sponsor Management
   Team), attributed to the signed-in user, and **never written to the CRM or
   shown to the partner/funder**. Confirm that's the intent (it mirrors
   submissions).
3. **Placement / layout.** Doug's words: "a pane to the left of the Partner
   Notes and Session Notes." Today the Overview is **facts rail (left) |
   splitter | notes column** (`sx__ov-notes` = overall notes + session-notes
   feed). Propose the exact new arrangement (e.g. facts rail | Discussion pane |
   notes column, or Discussion as a left sub-column of the notes area) and get
   Doug's ok — no page-width cap ([[no-page-width-caps-density-by-packing]]).

## Source to copy (Submission Admin Discussion)

- **Store:** `core/store.py` — the `submission_comment` table (migration 0016)
  + `add_comment` / `list_comments`. Generalize to `record_comment`
  `(id, parent_type, parent_id, author, author_name, body, created_at)` with an
  index on `(parent_type, parent_id, created_at)`. New **Alembic migration 0020**
  (next free number; runs in the pre-deploy migrate job).
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
- **Backend:** `sessions/service.py` — `get_detail` already returns
  `overallNotes` (see `_overview_items` / the `overall_notes_*` block); add a
  `comments` list (read via the store, best-effort, only when
  `discussion_enabled`). `sessions/router.py` — register
  `GET/POST /{slug}/api/records/{parent_id}/comments` inside `make_router`, gated
  by the flag; parent read AS THE USER first (the ACL gate), comments read/written
  via the store keyed by `(cfg.parent_entity, parent_id)`; attribute to
  `user["userName"]` / `user["name"]`; 503 if the store isn't configured.
- **Frontend:** `sessions/frontend/index.html` — the Overview panel is the
  `sx__ov` / `sx__ov-notes` block (facts rail + `#overallNotes` + Session-notes
  feed). Add a Discussion pane container to the left of `sx__ov-notes`.
  `sessions/frontend/app.js` — `renderOverview` / `renderOverallNotes` (~L668–L760)
  is where to hook a `renderDiscussion(d)` that reads `d.comments` and posts to
  the new endpoint (mirror the ops add-comment flow: append on success, clear the
  box, refresh). The shared frontend derives its domain from the first URL
  segment, so one implementation serves both partner and sponsor.

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

Partner and Funder Overview pages show a Discussion pane (attributed comments +
add box) to the left of the record's Notes, backed by the store, gated to the
domain team, staff-internal; the mentor domain is unchanged; tests + pg
round-trip green; stub-harness verified; docs + version bumped; committed for
Doug's review.
