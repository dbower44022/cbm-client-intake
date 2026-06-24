# Release notes

Narrative summaries of notable release cycles. For the granular, per-version
change list see [`CHANGELOG.md`](CHANGELOG.md); for the running project state see
the "Current status" section of `CLAUDE.md`.

---

## 2026-06-24 — v0.9.0 → v0.10.5 (post-go-live hardening)

The first cycle after the production go-live (v0.9.0). Triggered by a report that
the prod Mentor Admin app "failed to properly update" a mentor: approving them was
meant to create an EspoCRM login + welcome email, but **mentor-login provisioning
was disabled in prod** (no admin service account) and the app gave no indication —
so it looked like a silent failure.

### Shipped

| Ver | Change | Status |
|---|---|---|
| **0.9.1** | Mentor Admin surfaces "no login was created" when provisioning is off (instead of a bare "Saved") | Live |
| **0.10.0** | Google Workspace mailbox hard-gate for provisioning | Built, OFF (pending GCP setup) |
| **0.10.1** | Form-index links open in a new tab (`target="_blank"`) | Live |
| **0.10.2** | Index served `Cache-Control: no-store` — no stale landing page after a deploy | Live |
| **0.10.3 → 0.10.4** | `CIntakeSubmission.submitterEmail` now stores | Live + verified |
| **0.10.5** | Styled confirm modal for mentor assignment (replaces native `confirm()`) | Live + verified |

### Configuration / infrastructure
- **Enabled mentor-login provisioning in prod** — `MENTOR_PROVISION_USERS=true`
  with a Type=Admin service account (`mentoradmin@cbmentors.org`), applied via
  `doctl`. Verified live by approving a mentor end-to-end (admin login → Team
  lookup → `POST /User` → `assignedUser` link); the welcome email delivered to the
  mentor's CBM address.
- Wired the Google mailbox-gate vars into the prod overlay (OFF until a GCP service
  account with domain-wide delegation exists; see `DEPLOYMENT.md`).

### Notable diagnoses
- **`submitterEmail` not stored.** The first attempt (0.10.3, send a
  `submitterEmailData` array) **failed live testing**. Real cause: the CRM field
  was type `email`, which binds to the entity's primary `emailAddress` field and
  stores nothing for a custom-named email field. Fixed CRM-side by changing the
  field to **varchar** (dev + prod); the app reverted to the plain-string write
  (0.10.4), verified PASS. The sister `CInformationRequest.submitterEmail` (varchar)
  was the tell.
- **"0.10 no work."** A redeploy briefly served a stale cached landing page — an
  edge/browser cache artifact, not a code bug — which motivated the `no-store`
  index header (0.10.2).

### Verified against the production CRM (all PASS)
- Mentor provisioning end-to-end.
- `submitterEmail` now stored on `CIntakeSubmission`.
- **Partner + Sponsor forms end-to-end** — Account → Contact →
  CPartnerProfile/CSponsorProfile → CIntakeSubmission, with correct
  `cAccountType`/`cContactType` and the email fix confirmed.
- Assignment confirm-modal behavior (12/12 checks against the real
  `showConfirmModal`).
- All `ZZTEST` verification records cleaned up.

### Docs updated
CHANGELOG, CLAUDE.md, `cintake-submission-entity.md` (submitterEmail must be
varchar), DEPLOYMENT.md (full GCP/Workspace setup runbook for the mailbox gate +
provisioning verified-live note), `mentor-administration.md`,
STAFF-DEPLOYMENT-GUIDE.md, README.md, `.env.example`.

### Tests
169 passing (added coverage for the provisioning-disabled signal, the Google
mailbox gate, and the `no-store` index header).

### Still open (not regressions — follow-ups)
- **Google mailbox gate** needs a GCP service account + domain-wide delegation to
  activate (runbook in `DEPLOYMENT.md`).
- **Staff-tool Teams** (`Client Administration Team`, `Mentor Administration Team`)
  in prod for full parity.
- Pre-fix `CIntakeSubmission` records aren't backfilled (the email is still
  preserved in each record's `name`/`description`).
