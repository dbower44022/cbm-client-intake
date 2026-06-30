# CRM field hand-off (for the MN-INTAKE / CRM team)

This lists the EspoCRM fields the intake app needs in order to finish writing every
collected form input to its intended field (see `field-mapping-completion-plan.md`).
**The app already sends these values** — a missing field is silently ignored, so
the moment a field below exists with the right name/type/options the app starts
storing it with **no app change required**.

Field creation is owned by the CRM/MN-INTAKE process, not this repo. After any enum
field is built/changed, run `uv run python scripts/sync_form_options.py` (point it at
the relevant CRM) to confirm the form dropdowns match — a value not in the live enum
is dropped by the app's sanitizer, so they must match exactly.

Status verified **2026-06-30** against crm-test + prod.

---

## Part 1 — Prod parity: build on PROD to match crm-test (unblocks v0.13.0 / Pass A)

These already exist on **crm-test** and are live there; **production is missing
them**. Build on the prod CRM (`crm.clevelandbusinessmentors.org`) with the **exact
same names, types, and enum options** as crm-test. Until then, Pass A stores nothing
on prod (no error — just no-ops).

| Entity | Field (API name) | Type | Enum options (verbatim) | Captures |
|--------|------------------|------|-------------------------|----------|
| Contact | `cHowDidYouHear` | enum | `CBM Client or Volunteer`, `CBM Email`, `News or Media`, `Online Search`, `Partner Referral`, `Personal Referral`, `Social Media`, `Workshop or Event`, `Other` (+ blank) | "How did you hear about CBM" (all forms) |
| Contact | `cPreferredContactMethod` | enum | `Email`, `Phone`, `Text` | Volunteer "How should we contact you" |
| Contact | `cEmploymentStatus` | enum | `Yes, Full-time`, `Yes, Part-time`, `No` (+ blank) | Volunteer "Are you employed" |
| Contact | `cMarketingOptIn` | bool | — | Client-intake marketing consent |
| Contact | `cTermsOfUseAccepted` | bool | — | Terms-of-Use acceptance (all forms) |
| Contact | `cPrivacyPolicyAccepted` | bool | — | Privacy-Policy acceptance (all forms) |
| CClientProfile | `numberOfEmployees` | int | — | Client-intake "Number of employees" |

`CClientProfile.formationDate` (date) **already exists on prod** — no action.

The intake API user (`customappsproduction`, role `CustomAppAPIRole`) already has
create/read/**edit** on these entities, so the app's null-fill update path works on
prod once the fields exist.

---

## Part 2 — New fields needed on BOTH crm-test and prod (Pass C)

These don't exist on **either** CRM. Each unblocks a form input that is currently
dropped. Two are **decisions** (reuse an existing field, or build a new one).

| Entity | Proposed field | Type | Options | Captures | Note |
|--------|----------------|------|---------|----------|------|
| Contact | meeting-preference (e.g. `cMeetingPreference`) | enum | `No Preference`, `Video`, `Phone`, `Email`, `In Person` | Client-intake "Meeting preference" | OR reuse existing `CEngagement.meetingCadence` / `Contact.acceptanceStatusMeetings` — **decide** |
| Contact | notification-preference (e.g. `cNotificationPreference`) | enum | `Email`, `Text Message` | Client-intake "Notification preference" | new field |
| Contact | code-of-conduct (e.g. `cCodeOfConductAccepted`) | bool | — | "Code of Conduct" acceptance (client-intake, partner, sponsor) | mentor side already has `CMentorProfile.mentorCodeAccepted` |

**Two mentor decisions (build vs. accept the existing field):**
- **Work experience** — the form's "Describe your work experience" currently writes
  to `CMentorProfile.mentorProfessionalBio`. Either accept that as the home, or
  build a dedicated `workExperience` field. **Decide.**
- **Industry experience** — the form's multi-select "Industry Experience" currently
  stores **only the first value** into the single-enum `CMentorProfile.industrySector`.
  To keep all selections, build a **multiEnum** `industryExperience` (options = the
  20 NAICS sectors already in `industrySector`). Otherwise it stays first-value-only.
  **Decide.**

> Resolved already (Pass B, no build needed): volunteer "Areas of Expertise" stays on
> `mentoringFocusAreas` and partner "What could you offer" stays on `partnershipValue`
> — the alternate `areaOfExpertise` / `cBMValueProvided` fields are intentionally
> unused.

---

## Part 3 — Consent model (Pass D/E, gated on a product decision)

The forms today collect **one** terms checkbox (client-intake, volunteer) or **none**
(partner, sponsor). The target wants three separate Contact acceptances: Terms of Use
(`cTermsOfUseAccepted` — Part 1), Privacy Policy (`cPrivacyPolicyAccepted` — Part 1),
and **Code of Conduct** (`cCodeOfConductAccepted` — Part 2, still to build). Before
the consent piece can ship we need the product decision **one checkbox vs. three**
(then partner/sponsor need a consent checkbox added to the form). The CRM dependency
is just the code-of-conduct bool in Part 2; the other two consent fields are covered
by Part 1.

---

## After the builds

1. Re-run `scripts/sync_form_options.py` against the affected CRM(s) and commit any
   dropdown changes (so form values match the new enums on **both** crm-test + prod).
2. No orchestrator change is needed for Part 1 or the already-mapped Part 2 fields —
   the app writes them already. New mappings (meeting/notification pref,
   code-of-conduct, the mentor decisions) get a one-line orchestrator add once the
   fields exist.
3. Re-verify live (the Pass A pattern: submit → GET-verify the fields → clean up
   ZZTEST records).
