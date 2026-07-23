# cbm-client-intake

Custom web application for the Cleveland Business Mentors **Client Intake** process.

A prospective client completes a dynamic, branching intake form. A completed
submission creates three linked records in the system of record: an Account
(the client organization), a Contact (the applicant, linked to the Account),
and an Engagement (the mentoring request, linked to the Account).

## Documentation

Product Requirements Documents live in [`prds/`](prds/):

- **Requirements Specification** — what the application must do. Derived from,
  and kept aligned by carry-forward with, the Mentoring Domain Client Intake
  process document in the `dbower44022/ClevelandBusinessMentoring` repository.
- **Technical Design** — how the application is built. Derives from the
  Requirements Specification.

The business-level definition of the Client Intake process is **not** owned
here. It lives in the Mentoring Domain Client Intake process document
(MN-INTAKE) in the Cleveland Business Mentoring repository.

Change history: [`CHANGELOG.md`](CHANGELOG.md) (per-version) and
[`RELEASE_NOTES.md`](RELEASE_NOTES.md) (narrative summaries of release cycles).

### Deployment

- [`DEPLOYMENT.md`](DEPLOYMENT.md) — the engineer-level runbook (DigitalOcean
  App Platform): deploy, go live, custom domain, rollback, troubleshooting.
- [`STAFF-DEPLOYMENT-GUIDE.md`](STAFF-DEPLOYMENT-GUIDE.md) — a plain-language,
  web-console-only companion for CBM staff.

## Application

This is a multi-form app: a shared core hosts any number of intake forms.

- `core/` — shared machinery (Technical Design §2–4): the EspoCRM client (with a
  dry-run mode), config, the form registry (`FormSpec` + `BaseSubmission`), and
  the FastAPI app factory. The only component that holds EspoCRM credentials.
- `forms/<name>/` — one form per package. Each contributes a `SPEC` with its
  submission schema, its EspoCRM mapping (`orchestrator`), and an optional
  `frontend/` directory.
  - `forms/client_intake/` — SCORE form 111 reconciled to the CBM model; creates
    Account → Contact → CClientProfile → CEngagement; ships the multi-step wizard.
  - `forms/volunteer/` — SCORE form 6 (MR-APPLY); creates a Contact (Mentor) +
    CMentorProfile; ships its own wizard UI.
  - `forms/info_request/` — generic request-for-information; creates a Contact
    (+ Account when a company is given) and a CInformationRequest record.
  - `forms/partner/` — Become-a-Partner; creates Account → Contact → CPartnerProfile.
  - `forms/sponsor/` — Become-a-Sponsor; creates Account → Contact → CSponsorProfile.
- **Staff tools** — not public forms; signed-in EspoCRM staff only, gated by team
  membership and mounted only when `SESSION_SECRET` is set. Sign-in is **single
  sign-on at the portal** (`portal/`, the root `/` page): log in once with your
  CRM account and see the links your teams allow; each app still enforces its
  own team per request:
  - `assignments/` — **Client Administration** (`/assignments/`): assign submitted
    engagements to mentors who are accepting new clients.
  - `ops/` — **Submission Admin** (`/ops/`): a console over the V2 durable
    store (list/inspect/redrive submissions, backlog metrics); gated by
    `OPS_ALLOWED_TEAMS` (default "Marketing Admin Team").
  - `mentoradmin/` — **Mentor Administration** (`/mentoradmin/`): browse the mentor
    roster and edit any mentor's profile; verifies each record is complete and
    can auto-provision a mentor's EspoCRM login (optionally gated on whether their
    Google Workspace mailbox exists). The roster's **Update Mentor Status** action
    bulk-verifies every mentor's login user + mailbox and refreshes Record
    statuses. See
    [`mentor-administration.md`](mentor-administration.md) for the functionality
    and the complete-record requirements.
  - `sessions/` — **Session Management** (`/mentorsessions/`, `/partnersessions/`,
    `/sponsorsessions/`): one configurable engine, three team-gated routes. Each
    manager reviews the records they own (engagements / managed partners / managed
    sponsors) and records `CSession` **meetings** against them (notes, next steps,
    attendees, status; mentors can add co-mentors). The session editor's time
    picker checks the manager's own Google calendar and shades conflicting
    slots light red (advisory — still selectable; gated by `GCAL_EVENTS`). The **Communications** tab
    shows the email conversations with each record's contacts — synced from the
    manager's `@cbmentors.org` Gmail, cleaned to just the new text per message,
    with reply/compose from the tool (gated by `GMAIL_SYNC`); see
    [`email-management.md`](email-management.md) for the whole email system
    (My Email, compose, identities, submissions) and
    [`communications-tab.md`](communications-tab.md) for this tab in depth. Opening a record shows a tabbed,
    information-dense detail — an **Overview** (aggregated company pop-up, a
    session-notes feed, a Next-session Start/Open button), an editable
    permission-aware **Details** tab (`sessions/details.py`), the Sessions list,
    the Communications tab above, and a **Documents** tab — Google Drive
    document management (upload/list/in-app viewing/archive on the "CBM
    Documents" shared drive, with Drive access grants mirroring CRM
    assignments; `docs/`, gated by `GDRIVE_DOCS`). Gated by
    `SESSION_{MENTOR,PARTNER,SPONSOR}_ALLOWED_TEAMS`. Phase 1 (CRUD + review UI); see
    CLAUDE.md for the CRM prerequisites (CSession `assignedUsers` + name formula) and
    the later Calendar/Meet phases.
- **V2 reliability platform** (`prds/v2/`): optional durable capture
  (`core/store.py`) + an async delivery `worker.py`, gated by `DATABASE_URL` /
  `ASYNC_DELIVERY` so behavior is unchanged until a Postgres DB is attached.
- `frontend/shared/` — shared assets served at `/shared/`: the CBM design tokens
  (`tokens.css`), the wizard styles (`wizard.css`), the shared wizard
  controller (`wizard.js`) that the forms' page scripts build on, and the
  standard rich-text editor (`richtext.js`, wrapping the vendored MIT
  [Jodit](https://xdsoft.net/jodit/) build in `vendor/jodit/`) used by every
  wysiwyg field and the compose-email dialog across the staff tools.
- `main.py` — composition root; registers the forms.

Each registered form is reachable at `POST /api/<slug>/intake`, and (if it ships
a UI) at `/<slug>/`. The root lists the available forms (and the staff tools).

### Run locally

```bash
uv sync                          # install dependencies
cp .env.example .env             # ESPO_DRY_RUN=true by default — no live CRM needed
uv run uvicorn main:app --reload --port 8000
```

Then open <http://localhost:8000> (the client-intake wizard is at
`/client-intake/`). In dry-run mode the would-be records are logged and synthetic
ids returned, so the forms work without an EspoCRM instance. Set
`ESPO_DRY_RUN=false` and supply `ESPO_BASE_URL` / `ESPO_API_KEY` to write to a
real instance.

```bash
uv run pytest                    # run the test suite
```

### Adding a form

Create `forms/<name>/` with a `schemas.py` (extend `core.forms.BaseSubmission`),
an `orchestrator.py` (`async def submit(sub, client) -> dict`), and an
`__init__.py` exposing a `SPEC`. Register it in `main.py`. For a UI, add a
`frontend/` directory (its `index.html` + `app.js` build on the shared
`/shared/wizard.js` controller) and point `SPEC.frontend_dir` at it.

> **Status:** the app is **deployed and live on DigitalOcean App Platform,
> writing to `crm-test`** — all five forms and the first three staff tools
> (Client Administration, Submission Admin, Mentor Administration) have been
> verified end-to-end against the deployed EspoCRM. The fourth, **Session
> Management** (v0.31.0), is built and driven live on crm-test but **not yet
> pushed/deployed** — see CLAUDE.md for the live verification record per feature. Each `orchestrator.py` was reconciled against
> the deployed instance metadata and is the source-of-truth mapping; the form
> dropdowns are aligned to the live CRM enums. Note `forms/client_intake/`
> ships a bespoke `frontend/app.js`; it can still migrate onto the shared
> `wizard.js` controller (the other forms use it) for fuller frontend reuse.
