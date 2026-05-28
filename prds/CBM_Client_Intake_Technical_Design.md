# CBM Client Intake Application
## Technical Design

---

| Field | Value |
|---|---|
| Document | Technical Design |
| Project | CBM Client Intake Application |
| Status | Draft |
| Version | 0.3 |
| Last Updated | 05-28-26 16:08 |
| Owner | David Bower |

### Change Log

| Version | Date (MM-DD-YY HH:MM) | Author | Changes |
|---|---|---|---|
| 0.1 | 05-28-26 01:32 | Claude (scaffold) | Initial scaffold. Document control, change log, and the approved section structure established. All sections are placeholders pending the Requirements Specification reaching enough maturity to design against. |
| 0.2 | 05-28-26 10:30 | Claude (edit) | Authored Section 2 (architecture: static multi-step wizard frontend + FastAPI proxy backend, EspoCRM as system of record), Section 3 (integration: the `/api/intake` endpoint, payload, EspoCRM authentication via a dedicated scoped API user, and the Account→Contact→Engagement create-and-link sequence), and Section 4 (data integrity and partial-creation handling). Seeded Section 5 (administration), Section 6 (deployment), and Section 7 (open technical issues) with initial content. Designed against Requirements Specification v0.4 (multi-step wizard). |
| 0.3 | 05-28-26 16:08 | Claude (edit) | Reconciled the integration against the deployed crm-test instance. Section 3.3 rewritten as a four-record sequence (Account → Contact → CClientProfile → CEngagement); the Engagement links to the CClientProfile hub, not the Account. Confirmed entity/attribute names, multiEnum discriminators, link FKs, and `engagementStatus`; documented the not-deployed (§11.1 pending) fields the orchestrator omits. `forms/client_intake/orchestrator.py` is the executable source of truth for the mapping. |

---

## 1. Purpose and Scope

This document specifies how the Client Intake Application is built. It derives from the companion Requirements Specification (currently v0.1) and changes freely as technical decisions evolve, without disturbing the requirements. Product names and specific technologies are permitted throughout this document, because it is implementation documentation.

Where the Requirements Specification states what must be true, this document states how that is achieved.

---

## 2. Architecture Overview

### 2.1 Components

The application has two deployed components and one external dependency.

- **Intake frontend** — a static, multi-step wizard (Requirements Specification §4) served as plain HTML, CSS, and JavaScript. It collects and validates input, drives the Business-Stage branch (BR-1) and the dependent Industry Subsector dropdown (BR-2) client-side, and submits the completed answer set to the backend as a single payload. It holds no EspoCRM credentials and never calls EspoCRM directly. Styling derives from the CBM design tokens extracted from the public CBM site (Astra/Elementor palette and typography), so the form matches the CBM brand without reproducing the WordPress markup.
- **Intake backend** — a small server-side application (the "proxy") that is the only component holding EspoCRM credentials. It receives the submission, re-validates it server-side, applies anti-spam controls, and orchestrates the creation of the three records in EspoCRM. It returns a success or error result to the frontend.
- **EspoCRM** — the system of record, reached over its REST API. The application is a satellite of EspoCRM and keeps no parallel store of business data; it persists only operational data (submission audit and failed-submission state, Section 4 and Section 5).

### 2.2 Technology stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | Plain HTML / CSS / vanilla JS, no build step | Self-contained and trivially hostable or embeddable; the form is the whole UI, so a component framework would add weight without payoff. The design tokens drop in as CSS custom properties. |
| Backend | Python 3.12 + FastAPI, served by Uvicorn | Matches the team's Python expertise and the wider toolchain. The EspoCRM REST integration pattern (API-key auth, record create, record linking) is already proven in the `crmbuilder` codebase (`espo_impl/core/api_client.py`) and is re-implemented here as a small self-contained client to keep this repository independent. |
| EspoCRM client | `httpx` against the EspoCRM REST API | Async-friendly, fits FastAPI. |
| Configuration | Environment variables via `pydantic-settings` | Twelve-factor; secrets injected at deploy time, never committed. |

A heavier all-JavaScript stack (for example Next.js with API routes) and a serverless-function proxy were both considered. The Python proxy was chosen to reuse the proven EspoCRM integration pattern and the team's primary language; the decision is revisited only if hosting constraints (Section 6) rule out a long-running Python process.

### 2.3 Request lifecycle

1. The applicant works through the wizard steps; the browser validates each step and the branch logic locally.
2. On submit, the frontend POSTs the full answer set as JSON to the backend's intake endpoint (Section 3.1), including the anti-spam token.
3. The backend re-validates the payload, verifies the anti-spam token, and applies rate limiting. Invalid or suspected-bot submissions are rejected without touching EspoCRM.
4. The backend orchestrates the Account → Contact → Engagement creation sequence against EspoCRM (Section 3.3), recording progress for integrity (Section 4).
5. The backend returns a result. On success the frontend shows the confirmation experience (Requirements Specification §9); on failure it shows a recoverable error and the submission is retained for reprocessing (Section 4, Section 5).

---

## 3. Integration Implementation

### 3.1 Endpoint

The backend exposes a single public write endpoint plus operational endpoints.

- `POST /api/intake` — accepts the completed submission as JSON, returns `201` with the created record identifiers on success, or a `4xx`/`5xx` with a structured error on failure (Section 4.3). This is the only endpoint the frontend calls.
- `GET /healthz` — liveness/readiness probe for the host.
- Administration endpoints (submission review and reprocessing) are described in Section 5 and are authenticated separately from the public intake endpoint.

CORS is locked to the origin(s) that serve the frontend; the intake endpoint accepts cross-origin requests only from those origins.

### 3.2 Authentication to EspoCRM

EspoCRM is accessed with a **dedicated API User** created for this application, authenticating by API key in the `X-Api-Key` header. The user is assigned a role scoped to the minimum needed: create (and the read required to support find-or-create deduplication) on Account, Contact, and Engagement only, and no access to any other entity, no delete, and no administrative scope. The key is supplied to the backend as an injected secret (Section 6) and exists only server-side. If a submission must be attributed to a source, that attribution is set as field data on the records, not by impersonating a user.

### 3.3 The four-record create-and-link sequence

> **Reconciled against the deployed instance (crm-test, 2026-05-28).** Reading
> the deployed metadata showed a **Client Profile** (`CClientProfile`) hub: the
> Engagement (`CEngagement`) links to the Client Profile via `engagementClient`
> (belongsTo), not to the Account. The sequence below is therefore four records,
> superseding the earlier three-record description. The authoritative, executable
> mapping — entity names, the `c`-prefixed attribute names, the multiEnum
> discriminators (`cCompanyType`/`cContactType` = `["Client"]`), the link FKs
> (`accountId`, `clientcontactId`, `linkedCompanyId`, `engagementClientId`,
> `primaryEngagementContactId`), and the `engagementStatus` value — lives in
> `forms/client_intake/orchestrator.py`, which documents every field that is
> omitted because it is not yet deployed (the §11.1 pending-carry-forward set).

A completed submission yields one Account, one Contact, one Client Profile, and
one Engagement, created in dependency order so that each link target exists
before it is referenced:

1. **Account** — the client organization (`cCompanyType` includes "Client").
2. **Contact** — the applicant (find-or-create by email), linked to the Account.
3. **Client Profile** — linked to the Account (`linkedCompany`) and Contact
   (`clientcontact`).
4. **Engagement** — `engagementStatus` = "Submitted", linked to the Client
   Profile (`engagementClient`) with the Contact as `primaryEngagementContact`.

Historical detail (the original three-record write, retained for context):

1. **Account** — resolved first. New-business submissions create an Account (`name`, `website`, `industrySector`, `industrySubsector`, `yearFormed`, `numberOfEmployees`) with Account Type = Client (DAT-001). How a **Pre-Startup** submission — which collects no business profile — maps to the required Account record is governed by the Account creation precedence ladder in the Master PRD (v2.5) and is an open integration issue (Section 7); the sequence below assumes an Account identifier is available by the end of this step.
2. **Contact** — created (or matched; see Section 4.2) with Contact Type = Client (DAT-009) and Primary Contact = Yes (DAT-018), and linked to the Account from step 1. The Contact carries `firstName`, `lastName`, `email`, `phone`, `zipCode`, `howDidYouHearAboutCbm`, and `marketingConsent`, plus the applicant-since timestamp (DAT-027).
3. **Engagement** — created with Engagement Status = Submitted (DAT-021) and the auto-generated Engagement Name (DAT-020), linked to the Account (DAT-024) and to the Contact as the primary engagement contact (DAT-025). The Engagement carries `mentoringFocusAreas`, `mentoringNeedsDescription`, `meetingPreference`, and `notificationPreference`. `termsAccepted` is recorded per Requirements Specification §5.3. Requested Mentor (DAT-026) is left null in this version.

Records are related using EspoCRM's standard mechanisms: a many-to-one link is set by supplying the foreign-key attribute (for example, the Contact's account link) in the create payload, and any link that cannot be set at create time is set with a follow-up relate call. The Contact-to-Account, Engagement-to-Account, and primary-engagement-contact relationships correspond to DAT-019, DAT-024, and DAT-025.

### 3.4 Attribute-name resolution

The field names above are the canonical names from the Entity Product Requirements Documents. The actual EspoCRM stored attribute names are resolved against the deployed EspoCRM metadata for the target instance. In particular, custom fields added to the native Account and Contact entities are stored under a `c`-prefixed attribute name in EspoCRM, while fields on a custom entity are stored under their natural names; the exact deployed names follow from the CBM YAML deployment and are confirmed against the instance rather than assumed here. New fields flagged "pending carry-forward" in Requirements Specification §11.1 must exist on the instance before the integration can populate them; until each carry-forward is deployed, the corresponding field is omitted from the payload.

---

## 4. Data Integrity and Failure Handling

### 4.1 No distributed transaction

EspoCRM's REST API has no multi-record transaction spanning three separate create calls, so the sequence in Section 3.3 cannot be made atomic at the protocol level. The integrity expectation is therefore enforced by the backend as an orchestration, not by a database transaction. **What must be true after a successful submission:** exactly one Account (new or matched), one Contact (new or matched) linked to that Account, and one Engagement linked to both — and no Engagement is ever left without its Account and primary-contact links.

### 4.2 Idempotency and deduplication

- **Contact** is created find-or-create by email, honoring the Universal Contact-Creation Rules in the Master PRD (v2.5): a submission whose email matches an existing Contact reuses that Contact (and links it) rather than creating a duplicate. The form-layer rule on Contact must not silently overwrite populated canonical fields on a matched Contact; the merge policy for matched contacts is recorded as an open issue (Section 7).
- **Account** resolution follows the Account creation precedence ladder (Master PRD v2.5); see Section 7.
- **Submission idempotency** — the frontend includes a generated submission token with the payload. The backend treats a repeated token (double-click, retry, refresh) as the same submission and does not create a second set of records.

### 4.3 Partial-creation recovery

Each created identifier is captured as its step succeeds. If a later step fails (for example, the Engagement create fails after the Account and Contact exist), the backend does not delete the already-created records — they are valid canonical data — but records the submission, the step reached, and the identifiers created so far to a durable failed-submission store. The applicant receives a result indicating the request was received and is being completed, rather than a hard failure that would invite a resubmission and a duplicate. An administrator can then reprocess the submission to complete the remaining step(s) (Section 5). Reprocessing is safe because of the find-or-create and submission-token semantics in Section 4.2.

### 4.4 Retry behavior

Transient EspoCRM errors (network, timeout, `5xx`) on an individual create are retried a bounded number of times with backoff before the step is treated as failed and routed to Section 4.3. Validation-class errors (`4xx`) are not retried; they indicate a payload or instance-state problem and are surfaced to operations.

---

## 5. Administration and Operations

### 5.1 Submission audit

Every submission is logged with a timestamp, the generated submission token, the outcome (succeeded / failed-partial / rejected), and the identifiers of any records created. Personal data in logs is minimized; the durable record of intent is the canonical data in EspoCRM, not the application log.

### 5.2 Failed-submission review and reprocessing

The failed-submission store (Section 4.3) backs a small administrator view that lists submissions that did not complete, shows the step reached and the records already created, and offers a reprocess action that re-runs the remaining steps using the find-or-create and submission-token semantics. This view is authenticated and is **not** exposed on the public intake origin; it is operated by CBM administrators only. The authentication mechanism (shared admin credential, SSO, or restriction to an internal network) is an open issue (Section 7).

### 5.3 Logging and monitoring

The backend emits structured logs and exposes `GET /healthz` for the host's health checks. Alerting on a rising failed-submission rate or on EspoCRM-unreachable conditions is expected; the specific monitoring integration follows from the chosen host (Section 6).

---

## 6. Deployment Architecture

The application is intended to run on infrastructure already planned for other CBM applications; the specific host is confirmed against that plan (Section 7). The shape is host-independent:

- **Frontend** — static assets served over HTTPS, either from the backend host or a static/CDN origin. The serving origin is the one allow-listed in CORS (Section 3.1).
- **Backend** — a long-running Python/Uvicorn process (or container) reachable over HTTPS. It needs outbound network access to the EspoCRM REST API and a small amount of durable storage for the submission audit and failed-submission store (Section 4, Section 5).
- **Environments** — at least a staging environment pointed at a non-production EspoCRM instance, and production pointed at the live instance. The EspoCRM base URL is per-environment configuration.
- **Configuration and secrets** — the EspoCRM base URL, the dedicated API user's key, the allowed CORS origin(s), and the anti-spam provider keys are injected as environment variables at deploy time and are never committed. An example environment file documents the required variables without real values.
- **Build and deploy** — the frontend has no build step; the backend is deployed from this repository. The concrete pipeline follows from the chosen host.

---

## 7. Open Technical Issues

| Item | Description | Status |
|---|---|---|
| Pre-Startup Account mapping | How a Pre-Startup submission (no business profile collected) satisfies the required Account record — placeholder Account, personal Account, or deferred Account creation — per the Account creation precedence ladder in the Master PRD (v2.5). Blocks the Section 3.3 sequence for that branch. | Open |
| Matched-Contact merge policy | When a submission's email matches an existing Contact (Section 4.2), the rule for which submitted values may update the existing record and which must never overwrite populated canonical fields. | Open |
| Anti-spam provider | Choice of CAPTCHA/bot-defense provider (for example Cloudflare Turnstile or reCAPTCHA) and the rate-limit thresholds, enforced server-side at the intake endpoint. | Open |
| Administrator authentication | The mechanism protecting the failed-submission review interface (Section 5.2): shared credential, SSO, or internal-network restriction. | Open |
| Host confirmation | The specific shared CBM infrastructure the application deploys onto (Section 6), which determines the deploy pipeline, secrets mechanism, and monitoring integration. | Open |
| EspoCRM attribute names | Confirmation of the deployed attribute names (including `c`-prefixed custom fields) against the target instance, and confirmation that the §11.1 pending-carry-forward fields are deployed before the integration populates them (Section 3.4). | Open |

Open technical issues will continue to be recorded here as they surface.

---

*End of document.*
