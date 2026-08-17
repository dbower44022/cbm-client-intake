# Release notes

Narrative summaries of notable release cycles. For the granular, per-version
change list see [`CHANGELOG.md`](CHANGELOG.md); for the running project state see
the "Current status" section of `CLAUDE.md`.

---

## 2026-08-13 → 08-16 — v0.198.0 + a CRM change (the company-link arc)

Triggered by one question: a partner record on prod whose **Company read
"(details)"**, with no Company section on the Details tab and no way to put one
back.

**What it turned out to be.** The record was created by "+ Add partner" at
03:23 *with* its company. Nine and a half hours later a second staff member
added the same partner again; quick-add reused the same-named Account, and
because `Account.cCompanyPartnerProfile` was a **`hasOne`**, EspoCRM did not
refuse the second link — it **moved** the Account onto the new record, silently
emptying the first. Nothing failed, nobody saw an error, and the loser was the
record nobody was looking at. Confirmed from `CActionLog` and the EspoCRM id
timestamps, not inferred.

**The ruling.** Doug: a partnership is with a *programme inside* an
organisation as often as with the organisation itself — Case Western's
Think\[box\] was already the many case wearing the one case's clothes. So one
company, **many** partner records; likewise funders. **Clients are the
deliberate exception** — a client never has two business profiles, so
`CClientProfile.linkedCompany` stays `hasOne`, guarded in the app by the intake
orchestrator's find-or-create on `linkedCompanyId`.

**What changed.**

| | |
|---|---|
| CRM (prod 08-14, crm-test 08-15) | `partnerCompany` recreated as Many-to-One |
| CRM (both, 08-16) | `sponsorCompany` recreated as Many-to-One |
| App (v0.198.0) | Company picker + "+ New company" on the partner/funder Details tab; the Overview's empty company now reads "—" instead of "(details)" |
| App (v0.201.1) | Save on an unchanged Details panel closes it instead of ignoring the click |

**Worth carrying forward.**

- **Removing an EspoCRM relationship never drops the column or the data.**
  Entity Manager cannot change a relationship's *type*, so a type change is
  delete-then-recreate — and every link came back on its own each time, once the
  recreated link had the same name. A mis-named recreate is the only real
  hazard: it strands the data in the old column and looks exactly like data
  loss. ([[espo-removelink-is-metadata-only]])
- **The Create Link dialog inverts the two Name boxes** — the name typed under
  one entity becomes the link stored on the *other*. Got wrong four times across
  three builds before it was written into `CLAUDE.md` with a verify-by-metadata
  step that doesn't depend on remembering the rule.
- The audit that came out of this flagged three records as incomplete; two of
  them are *accurately* incomplete (CBM has no company for that partner yet, and
  the funder's manager isn't known). Recorded in `OPEN-ITEMS.md` so they stop
  being re-raised as defects.

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
