# Changelog

All notable changes to **cbm-client-intake**. Versions are the value reported by
`/healthz` and the page footer (sourced from `pyproject.toml`), and double as the
deploy marker on App Platform.

## [0.10.4] — 2026-06-24

> **Live in production** (`cbm-client-intake-prod`) — `/healthz` reports `0.10.4`.
> The CRM-side fix is applied: `CIntakeSubmission.submitterEmail` is now `varchar`
> in dev + prod, and a live test submission confirmed the email is stored.

### Changed
- **Reverted 0.10.3's `submitterEmailData` approach — the real fix is CRM-side.**
  Live testing showed `CIntakeSubmission.submitterEmail` stays null whether the app
  sends a plain string **or** the `submitterEmailData` array, because the field was
  built as EspoCRM type **`email`**, which is bound to the entity's single primary
  `emailAddress` field — a custom-named email-type field stores nothing. The fix is
  to change that field's type to **varchar** in the CRM (the sister
  `CInformationRequest.submitterEmail` is varchar and stores fine). The log reverts
  to the simple string write, which works once the field is varchar
  (`core/submission_log.py`). **CRM action required** — see
  `cintake-submission-entity.md`.

## [0.10.3] — 2026-06-24

### Fixed
- *(superseded by 0.10.4 — the `submitterEmailData` array did not work either; the
  field type itself is the problem.)* Attempted to store
  `CIntakeSubmission.submitterEmail` via the `submitterEmailData` array.

## [0.10.2] — 2026-06-24

### Changed
- **The form index is served with `Cache-Control: no-store`**, so a freshly
  deployed landing page is never shown stale from a browser/edge cache (a
  redeploy briefly served the previous index from cache otherwise)
  (`core/app.py` `index`).

## [0.10.1] — 2026-06-24

### Changed
- **The form index opens each form/staff-tool link in a new browser tab**
  (`target="_blank"` + `rel="noopener"`), so the landing page stays put when a
  user opens a form or staff tool (`core/app.py` `_index_html`).

## [0.10.0] — 2026-06-24

### Added
- **Mentor provisioning hard-gates on the Google Workspace mailbox.** Before
  creating an EspoCRM login (and firing its `sendAccessInfo` welcome email) for an
  approved mentor, the app can verify their `firstname.lastname@cbmentors.org`
  mailbox actually exists in Google Workspace — otherwise the credentials email
  bounces and the mentor is stranded with a login they can't receive. A
  *confirmed-missing* mailbox blocks provisioning with a clear error ("create it
  before approving"); an inconclusive check (not configured, API/auth error) fails
  **open** so a Google outage can't freeze approvals. New `core/google_directory.py`
  (`GoogleDirectory.mailbox_status` → `EXISTS`/`MISSING`/`UNKNOWN`, via the Admin
  SDK Directory API with a domain-wide-delegated service account, read-only scope).
  **Off by default** — a no-op until `GOOGLE_DIRECTORY_CHECK=true` +
  `GOOGLE_SERVICE_ACCOUNT_JSON` + `GOOGLE_DELEGATED_ADMIN` are set, so prod is
  unchanged until the Google credentials exist.

## [0.9.1] — 2026-06-24

### Fixed
- **Mentor Admin no longer silently hides "no login created" on approval.** When a
  mentor is saved at `Approved`/`Active` but login provisioning is disabled on the
  server (no admin service account configured — the production state), the save now
  returns `provision={ok:false, disabled:true}` and the UI shows *"Status saved, but
  no login was created — mentor login provisioning is turned off on this server."*
  Previously this case was indistinguishable from a successful approval, so an
  approval in prod silently created no EspoCRM User and no welcome email
  (`mentoradmin/service.py`, `mentoradmin/frontend/app.js`).

## [0.8.0] — 2026-06-23

### Fixed
- **Implausible phone numbers no longer fail the Contact create.** A submission
  with a bogus phone (e.g. `12345` → `+12345`) was 400'ing EspoCRM's `phoneNumber`
  "valid" check and losing the whole lead. `core/phone.e164_or_none` normalizes to
  E.164 but returns `None` when the result can't be a real number (<10 or >15
  digits); every orchestrator (volunteer, client-intake, partner, sponsor,
  info-request — both the Contact and the `CInformationRequest` phone fields) now
  **omits** `phoneNumber` when invalid. Email stays the contact channel and the
  raw value is preserved in the `CIntakeSubmission` audit log.
  *(This was the one stuck volunteer re-drive that still failed after enum
  resilience landed.)*

## [0.7.0] — 2026-06-23

### Added
- **Enum-drift resilience extended to client-intake and partner.** `EnumSanitizer`
  generalized to span a whole create chain (entity passed per call, options cached
  per `(entity, field)`, one aggregated note):
  - **client-intake** — sanitizes `cBusinessStage` + `cIndustrySector` (Account)
    and `mentoringFocusAreas` (CEngagement); drop-note on `CEngagement.description`.
  - **partner** — sanitizes `partnershipType` + `partnershipValue`; drop-note on
    `CPartnerProfile.description`.
  - **sponsor** — no change (writes no user-supplied enum, only system
    discriminators + a free-text message).
- System discriminators (`cAccountType`/`cContactType`/status) are deliberately
  **not** sanitized — they're required/monitored and must fail loudly if they drift.

## [0.6.0] — 2026-06-23

### Added
- **Enum-drift resilience (volunteer).** New `core/enum_filter.py` `EnumSanitizer`
  validates enum/multiEnum payload values against the live CRM options and **drops**
  unrecognized ones instead of letting a single drifted value 400 the whole create.
  The volunteer orchestrator sanitizes `industrySector` / `mentoringFocusAreas` /
  `fluentLanguages`; dropped values are noted on `CMentorProfile.description` for
  staff follow-up. Fails open (keeps the value if options can't be fetched, e.g.
  dry-run). `metadata_enum_options` added to the `EspoApi` protocol +
  `DryRunEspoClient` + `ResumableClient`. **Effect:** re-driving a drift-failed
  submission now creates the record (with the valid data + contact info) instead
  of failing — no discarding needed.

## [0.5.0] — 2026-06-23

### Added
- **`/ops` Discard action.** A stuck submission that can't be delivered (e.g. a bad
  payload that re-driving would just replay) can be moved to a terminal `discarded`
  status, so it leaves the worker queue and stops counting toward the
  needs-attention alert. The row is kept for audit; a completed delivery can never
  be discarded; Re-drive also covers `discarded` so a mistaken discard can be
  undone. (`store.discard()`, `POST /ops/api/submissions/{id}/discard`, Discard
  button on stuck rows.)

## [0.4.0] — 2026-06-23

First version bump of the session — the footer/`/healthz` had been stuck at 0.3.0,
so it gave no signal for whether a new build was live. `core/__init__.__version__`
now reads from `pyproject.toml` (single source) instead of a stale hardcoded value.
Bundles the following work, all shipped under this version:

### Added
- **Client Administration (`/assignments`) — Available Mentors grid:** a **Type**
  column + filter (sortable) and an **Accepting** (new clients) column. `mentorType`
  is normalized so a single enum or multi-enum both render/filter/search.
- **Client Administration — Requested Mentor (DAT-026).** The engagement detail
  popup now shows the `CEngagement.requestedMentor` link (belongsTo CMentorProfile)
  when set, resolving the name defensively (inline accessor → CMentorProfile read;
  a deleted target shows "(no longer in the system)"). Hidden when unset.
- **Worker crash-recovery (lease).** `claim_batch` now leases each claimed row
  (`locked_until = now + worker_lease_seconds`, default 900s) and reclaims
  `processing` rows whose lease expired — a worker killed mid-delivery
  (redeploy/OOM/SIGKILL) no longer strands a submission in `processing` forever
  (safe because delivery is resumable). Alembic migration `0002_processing_lease`
  adds `locked_until` + a claim index.
- **`/healthz` database check.** Pings the durable store and returns `503` +
  `database:"error"` when it's configured but unreachable. The CRM is deliberately
  not pinged (a CRM outage must not take the web tier down — durable capture +
  the async worker exist to ride it out).

### Changed
- **Public intake forms (all five) — UX.** The submission **reference number** is
  now shown on the confirmation screen; a **30s request timeout** (AbortController)
  with a retryable message replaces an indefinite "Submitting…"; validation errors
  are **announced + focused** (`role="alert"`); a double-submit guard; clearer phone
  placeholders + explicit "(optional)" labels. (Applied in both the shared
  `wizard.js` and client-intake's standalone `app.js`.)
- **Staff tools — UX.** All three (`/assignments`, `/ops`, `/mentoradmin`) now
  distinguish a 5xx/network boot failure ("server isn't responding") from "not
  signed in". `/mentoradmin`: cancelling the incomplete-record modal jumps to the
  first unresolved field; a field-spec load failure warns instead of a blank
  editor. `/assignments`: labeled load errors (mentors vs engagements). `/ops`:
  surfaces "metrics unavailable" instead of swallowing the error.

### Fixed
- **Schema drift — volunteer industry/language.** The form's `industryExperience`
  (20 NAICS sectors) had **zero overlap** with the live `CMentorProfile.industrySector`
  enum (28 CBM values), and `fluentLanguages` offered 36 vs the CRM's 2 — so every
  industry pick (and most language picks) 400'd. Aligned both lists to the live
  enums (verbatim, including the CRM's typos). Extended `core/schema_contract.py` to
  cover the volunteer form's enum fields so the Phase-3 drift monitor warns before
  the next such failure (they were previously unmonitored).
- **`session_expired`** now matches the *first* `HTTP <code>` in the EspoError
  message, so a 502 whose body merely contains "HTTP 401" is no longer misread as
  token expiry.
- **`assign_engagement` partial-failure reporting.** The downstream re-homing
  (contacts/client/account) is now best-effort and per-target — a CRM failure on
  one record is captured in `reassignmentErrors` and reported to the staffer,
  instead of raising after the engagement was already assigned. Steps 1–2 (the core
  assignment) stay fail-fast.

---

For per-feature design notes and live-verification records, see `CLAUDE.md`. The
V2 reliability platform (durable capture + async worker + ops + alerting) is
specified in `prds/v2/`.
