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

## Application

This is a multi-form app: a shared core hosts any number of intake forms.

- `core/` — shared machinery (Technical Design §2–4): the EspoCRM client (with a
  dry-run mode), config, the form registry (`FormSpec` + `BaseSubmission`), and
  the FastAPI app factory. The only component that holds EspoCRM credentials.
- `forms/<name>/` — one form per package. Each contributes a `SPEC` with its
  submission schema, its EspoCRM mapping (`orchestrator`), and an optional
  `frontend/` directory.
  - `forms/client_intake/` — SCORE form 111 reconciled to the CBM model; creates
    Account + Contact + Engagement; ships the four-step wizard UI.
  - `forms/volunteer/` — SCORE form 6 (MR-APPLY); creates a single Contact
    (Mentor) with an optional resume upload; ships its own four-step wizard UI.
- `frontend/shared/` — shared assets served at `/shared/`: the CBM design tokens
  (`tokens.css`), the wizard styles (`wizard.css`), and the shared wizard
  controller (`wizard.js`) that both forms' page scripts build on.
- `main.py` — composition root; registers the forms.

Each registered form is reachable at `POST /api/<slug>/intake`, and (if it ships
a UI) at `/<slug>/`. The root lists the available forms.

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

> **Before going live:** the EspoCRM entity/attribute names in each form's
> `orchestrator.py` are provisional guesses and must be reconciled against the
> deployed instance metadata (Technical Design §3.4, §7); the §7 open issues
> (Pre-Startup Account mapping, anti-spam provider, admin auth, host) must be
> resolved; and `forms/client_intake/frontend/app.js` is still bespoke — it can
> migrate onto the shared `wizard.js` controller (the volunteer form already
> uses it) for full frontend reuse.
