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

- `frontend/` — the static four-step wizard (plain HTML/CSS/JS). Styling comes
  from `frontend/tokens.css`, the CBM design tokens extracted from the public
  CBM site.
- `app/` — the FastAPI proxy (Technical Design §2–4). It is the only component
  that holds EspoCRM credentials and orchestrates the Account → Contact →
  Engagement create-and-link sequence.

### Run locally

```bash
uv sync                          # install dependencies
cp .env.example .env             # ESPO_DRY_RUN=true by default — no live CRM needed
uv run uvicorn app.main:app --reload --port 8000
```

Then open <http://localhost:8000>. In dry-run mode the would-be records are
logged and synthetic ids returned, so the full form works without an EspoCRM
instance. Set `ESPO_DRY_RUN=false` and supply `ESPO_BASE_URL` / `ESPO_API_KEY`
to write to a real instance.

```bash
uv run pytest                    # run the test suite
```

> **Before going live:** the EspoCRM entity/attribute names in
> `app/orchestrator.py` are provisional guesses and must be reconciled against
> the deployed instance metadata (Technical Design §3.4, §7), and the open
> issues in Technical Design §7 (Pre-Startup Account mapping, anti-spam
> provider, admin auth, host) must be resolved.
