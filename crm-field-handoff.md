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

## Part 1 — Prod parity — ✅ DONE (2026-06-30)

**All 7 fields below were added to the prod CRM 2026-06-30 (verified), plus the
consent fields in Part 2/3. Pass A (v0.13.0) now stores on production.** The
original spec is kept for reference.

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
| ~~Contact `cMeetingPreference`~~ | ✅ DONE | enum | `Video`/`Phone`/`Email`/`In Person`/`No Preference` | Client-intake "Meeting preference" | mapped + live (v0.18.0) — options reconciled on both CRMs |
| ~~Contact `cNotificationPreference`~~ | ✅ DONE | enum | `Email`, `Text` | Client-intake "Notification preference" | mapped + live (v0.17.0) |
| ~~Contact `cCodeOfConductAccepted`~~ | ✅ DONE | bool | — | code-of-conduct acceptance | mapped + live (v0.16.0) |

**✅ Part 2 fully done.** All fields above are built on both CRMs and mapped. The
`cMeetingPreference` options were reconciled (the `No Preferrence` typo fixed on both,
and `In Person`/`In-Person` settled on `In Person` for both) and the field is live.

**Mentor "Industry Experience" — ✅ DONE (2026-06-30, v0.14.0).** `industryExperience`
is now a multiEnum with the canonical 28-value list on **both** CRMs (verified
identical), the app writes all selections to it, and the form is re-synced. The
original ask is kept below for history.

~~**Fix `industryExperience` so it can hold all picks
(decided 2026-06-30, Doug).**~~ The form's multi-select "Industry Experience (choose up
to 6)" currently stores **only the first value** into the single-enum
`CMentorProfile.industrySector` — selections 2–6 are dropped. The intended field
`industryExperience` exists but is **broken/divergent** and must be reconciled:

- **crm-test:** `industryExperience` is a `multiEnum` with **no options** (unusable).
- **prod:** `industryExperience` is a **single `enum`** with 20 options in a *different,
  typo-laden* taxonomy (`Group  homes`, `TRANSPORTATION & LOGISTICS`, etc.).

**Make `CMentorProfile.industryExperience` a `multiEnum` on BOTH CRMs with the same
20 NAICS sector options** that `industrySector` / the form already use:

> Agriculture, Forestry, Fishing and Hunting · Mining, Quarrying, and Oil and Gas
> Extraction · Utilities · Construction · Manufacturing · Wholesale Trade · Retail
> Trade · Transportation and Warehousing · Information · Finance and Insurance · Real
> Estate and Rental and Leasing · Professional, Scientific, and Technical Services ·
> Management of Companies and Enterprises · Administrative and Support and Waste
> Management · Educational Services · Health Care and Social Assistance · Arts,
> Entertainment, and Recreation · Accommodation and Food Services · Other Services
> (except Public Administration) · Public Administration

Once it's a multiEnum with those options on both CRMs, the app change is a one-line
orchestrator repoint (`industry_experience` → `industryExperience`, all values) plus
re-pointing the form's `industryExperience` sync marker — captures every selection,
no data loss. **Until then, the app keeps first-value-only (no change).**

> **Resolved, NO build needed:**
> - **Work experience** stays on `CMentorProfile.mentorProfessionalBio` (Doug, 2026-06-30).
> - **Areas of Expertise** stays on `mentoringFocusAreas`; **partner value** stays on
>   `partnershipValue` (Pass B) — `areaOfExpertise` / `cBMValueProvided` left unused.

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
