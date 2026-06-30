# Field-mapping completion plan

**Goal:** make every intake form write each collected input to the CRM field the
business intends, per the canonical mapping provided 2026-06-30. Today a number of
fields are collected but dropped (they survive only in the `CIntakeSubmission`
raw-JSON audit log), and a few are written to a different field than intended.

**Status of CRM fields:** verified read-only against **crm-test**
(`https://crm-test.clevelandbusinessmentors.org`) on 2026-06-30. **Prod has NOT
been checked yet** — every target field + enum option set must be confirmed to
exist on `crm.clevelandbusinessmentors.org` before shipping, since one static
build serves both.

**Governance:** this repo owns the *app* (the orchestrator mapping + the forms).
Creating new CRM fields is owned by the **MN-INTAKE** process in the separate CRM
repo — items marked 🏗️ are hand-offs, not built here.

---

## Entity name key (business term → repo/CRM entity)

| Mapping says | CRM entity |
|---|---|
| Contact | `Contact` (native) |
| Company | `Account` |
| Client | `CClientProfile` |
| Engagement | `CEngagement` |
| CBM Member | `CMentorProfile` |
| Partner | `CPartnerProfile` |
| Sponsor | `CSponsorProfile` |

## Verified CRM fields used by this plan (crm-test, 2026-06-30)

- **Contact:** `cHowDidYouHear` (enum), `cPreferredContactMethod` (enum),
  `cEmploymentStatus` (enum), `cMarketingOptIn` (bool), `cTermsOfUseAccepted`
  (bool), `cPrivacyPolicyAccepted` (bool), `acceptanceStatusMeetings` (enum).
  **No** Contact field for: meeting-preference, notification-preference,
  code-of-conduct.
- **Account:** `cIndustrySector` (enum), `website` (url).
- **CClientProfile:** `formationDate` (date), `numberOfEmployees` (int),
  `industrySector` (enum).
- **CEngagement:** `mentoringFocusAreas` (multiEnum), `mentoringNeedsDescription`
  (wysiwyg), `meetingCadence` (enum).
- **CMentorProfile:** `mentoringWhyInterested` (wysiwyg), `mentorProfessionalBio`
  (wysiwyg), `areaOfExpertise` (multiEnum), `mentoringFocusAreas` (multiEnum),
  `fluentLanguages` (multiEnum), `industrySector` (enum),
  `howDidYouHearAboutCBM` (enum), `felonyConfiction` (bool — CRM misspelling),
  `mentorCodeAccepted` (bool), `termsAccepted` (bool), `ethicsAgreementAccepted`
  (bool). **No** `workExperience` or multi `industryExperience` field.
- **CPartnerProfile:** `partnershipType` (enum), `partnershipValue` (multiEnum),
  `cBMValueProvided` (multiEnum).
- **CSponsorProfile:** `description` (text).

---

## Per-form mapping (current → target)

Legend: ✅ ready (field exists, orchestrator edit only) · 🟢 already correct ·
🔁 retarget (currently writes a different field) · 🏗️ CRM field missing ·
📝 form change needed.

### Client Intake (`forms/client_intake/`)

| Form input (schema field) | Target | Today | Status |
|---|---|---|---|
| how_did_you_hear | `Contact.cHowDidYouHear` | only `CIntakeSubmission.source` | ✅ |
| mentoring_focus_areas | `CEngagement.mentoringFocusAreas` | same | 🟢 |
| mentoring_needs_description | `CEngagement.mentoringNeedsDescription` | same | 🟢 |
| industry_sector | `Account.cIndustrySector` | same | 🟢 |
| year_formed (int) | `CClientProfile.formationDate` (date) | dropped | ✅ + convert year→`YYYY-01-01` |
| number_of_employees | `CClientProfile.numberOfEmployees` | dropped | ✅ |
| marketing_consent | `Contact.cMarketingOptIn` | dropped | ✅ |
| terms_accepted | `Contact.cTermsOfUseAccepted` | dropped (gates submit only) | ✅ |
| (privacy policy) | `Contact.cPrivacyPolicyAccepted` | not collected separately | 📝 consent model |
| (code of conduct) | `Contact.` code-of-conduct | not collected; **no field** | 🏗️ + 📝 |
| meeting_preference | `Contact.` meeting-preference | dropped; **no field** | 🏗️ |
| notification_preference | `Contact.` notification-preference | dropped; **no field** | 🏗️ |
| industry_subsector | (not in mapping) | dropped | — leave dropped |

### Mentor / Volunteer (`forms/volunteer/`)

| Form input | Target | Today | Status |
|---|---|---|---|
| phone_type | NONE | dropped | 🟢 stays dropped (per mapping) |
| contact_preference | `Contact.cPreferredContactMethod` | dropped | ✅ |
| currently_employed | `Contact.cEmploymentStatus` | dropped | ✅ |
| why_volunteer | `CMentorProfile.mentoringWhyInterested` | same | 🟢 |
| fluent_languages | `CMentorProfile.fluentLanguages` | same | 🟢 (mapping said "Client" — typo; field is on CBM Member) |
| felony_conviction | `CMentorProfile.felonyConfiction` | same | 🟢 |
| how_did_you_hear | `CMentorProfile.howDidYouHearAboutCBM` | same | 🟢 (mapping said "Contact"; field is on profile — **confirm**) |
| areas_of_expertise | `CMentorProfile.areaOfExpertise` | `mentoringFocusAreas` | 🔁 **decision** |
| work_experience | `CMentorProfile` work-experience | `mentorProfessionalBio` | 🔁/🏗️ **decision** |
| industry_experience (multi) | `CMentorProfile` industry-experience | first value → `industrySector` | 🔁/🏗️ **decision** |
| terms_accepted | `CMentorProfile.mentorCodeAccepted` (code) + `Contact.cTermsOfUseAccepted` + `Contact.cPrivacyPolicyAccepted` | single → `CMentorProfile.termsAccepted` | ✅/📝 consent model |

### Partner (`forms/partner/`)

| Form input | Target | Today | Status |
|---|---|---|---|
| company | `Account.name` | same | 🟢 |
| business_website | `Account.website` | same | 🟢 |
| partnership_type | `CPartnerProfile.partnershipType` | same | 🟢 |
| partnership_value | `CPartnerProfile.cBMValueProvided` | `partnershipValue` | 🔁 **decision** |
| how_did_you_hear | `Contact.cHowDidYouHear` | `source` only | ✅ |
| (terms / privacy) | `Contact.cTermsOfUseAccepted` / `cPrivacyPolicyAccepted` | not collected | 📝 consent model |
| (code of conduct) | `Contact.` code-of-conduct | not collected; **no field** | 🏗️ + 📝 |

### Sponsor (`forms/sponsor/`)

| Form input | Target | Today | Status |
|---|---|---|---|
| message | `CSponsorProfile.description` | same | 🟢 |
| how_did_you_hear | `Contact.cHowDidYouHear` | `source` only | ✅ |
| (terms / privacy) | `Contact.cTermsOfUseAccepted` / `cPrivacyPolicyAccepted` | not collected | 📝 consent model |
| (code of conduct) | `Contact.` code-of-conduct | not collected; **no field** | 🏗️ + 📝 |

---

## Work, grouped into passes

### Pass A — Ready orchestrator edits (fields already exist) — ✅ DONE (v0.13.0, 2026-06-30)

**Shipped + live-verified on crm-test.** All targets below now write; the Contact
null-fill (`core/crm_upsert.find_create_or_fill`) reuses a matched Contact and
backfills only empty fields. The how-heard / contact-method / employment dropdowns
are CRM-backed via the options sync. Live check (ZZTEST-PASSA, **clean up in the
EspoCRM UI**): Contact `6a435376193680811` + Account `6a4353756c4bfcac3` +
CClientProfile `6a435376582ac897c`/`6a4353785b42f39f9` + CEngagement
`6a435376b4324c603`/`6a435378cf76f063f`; volunteer Contact `6a43537a24b1f051b` +
CMentorProfile `6a43537ad30d6e3ed`; partner Contact `6a43537c766baa2f5` + Account
`6a43537bd1134a980` + CPartnerProfile `6a43537d2c1259c36`.

**PROD PARITY — checked 2026-06-30 (read-only): the Pass A fields are NOT on prod
yet.** Prod (`crm.clevelandbusinessmentors.org`) is MISSING `Contact.cHowDidYouHear`,
`cMarketingOptIn`, `cTermsOfUseAccepted`, `cPreferredContactMethod`,
`cEmploymentStatus`, `cPrivacyPolicyAccepted`, and `CClientProfile.numberOfEmployees`;
only `CClientProfile.formationDate` exists. **v0.13.0 is SAFE on prod regardless** —
the writes are no-ops until the fields exist: `find_one` with an unknown-field
`select` returns 200 (verified on prod), the `EnumSanitizer` fails open on the
missing-field metadata lookup, and EspoCRM ignores unknown create/update attributes
(corroborated by the prod `submitterEmail`/`assignedUserId` precedents). So Pass A
stores these fields on crm-test today and will start storing them on prod the moment
the CRM team adds them — **no app change needed then.** **MN-INTAKE hand-off:** build
those 7 fields on the prod CRM (same names/types/enum options as crm-test), then
re-run `scripts/sync_form_options.py` against prod to confirm the dropdown values
match. The Contact edit grant (needed by the fill-null path) is present on prod via
`CustomAppAPIRole` per CLAUDE.md.

Original scope (all implemented):


No CRM build, no form change. All enum/multiEnum writes go through the existing
`EnumSanitizer` (`san.enum`/`san.multi`) so a drifted option is dropped, not fatal.

- **client-intake** (`orchestrator.py`):
  - `_find_or_create_contact`: add `cHowDidYouHear` (sanitized enum),
    `cMarketingOptIn` (bool), `cTermsOfUseAccepted` (bool from `terms_accepted`).
  - `_create_client_profile`: add `numberOfEmployees` (int) and `formationDate`
    (convert `year_formed` int → `"%04d-01-01"`).
- **volunteer** (`orchestrator.py`): add to the Contact payload
  `cPreferredContactMethod` (from `contact_preference`) + `cEmploymentStatus`
  (from `currently_employed`), both sanitized enums.
- **partner** + **sponsor** (`orchestrator.py`): add `cHowDidYouHear` (sanitized
  enum) to the Contact payload.

**Coupled work for Pass A:**
- **options.js sync.** `cPreferredContactMethod`, `cEmploymentStatus`, and
  `cHowDidYouHear` are enums — the form `<select>` values must match the live CRM
  options or the sanitizer drops them. Today the how-did-you-hear list is a
  *presentational* static list (not CRM-backed) and the contact-method/employment
  selects use local enums in `schemas.py`. Wrap each in the `>>> crm-enum …`
  sentinel markers and run `scripts/sync_form_options.py` so they track the CRM.
  (Confirm `ContactPreference`/`EmploymentStatus` schema enums still validate the
  synced values, or relax them.)
- **Tests:** extend each form's orchestrator test to assert the new payload keys.
- **Live verify** against crm-test (real `EspoClient`), GET-verify the written
  values, clean up `ZZTEST` records in the UI afterward.

### Pass B — Retarget decisions — ✅ RESOLVED (2026-06-30, Doug): KEEP current fields, no switch

Investigation found the "current" and "target" fields hold **different taxonomies**,
not the same list under two names:
- `CMentorProfile.mentoringFocusAreas` = 42 **industry** categories;
  `areaOfExpertise` = 29 **skill** categories (zero overlap).
- `CPartnerProfile.partnershipValue` = 7 partner-offering options;
  `cBMValueProvided` = 6 differently-worded options.

**Decision (Doug):** the current fields are canonical — do **not** switch.
- Volunteer `areas_of_expertise` stays on **`mentoringFocusAreas`** (the crm-test
  42-value list is the canonical one for both crm-test + prod + the form).
- Partner `partnership_value` stays on **`partnershipValue`** (its 7 options are the
  canonical enum for both crm-test + prod + the form).
The mapping's `areaOfExpertise` / `cBMValueProvided` targets are **not** used.

**No code change needed** — this is exactly what ships today. Verified 2026-06-30:
both fields' option sets are **identical on crm-test and prod**, and both form
dropdowns are already synced to them (`sync_form_options.py` reports no drift). The
`areaOfExpertise` / `cBMValueProvided` fields are simply left unused by the forms.

### Pass C — CRM fields to build first (hand-off to MN-INTAKE) 🏗️

> **Hand-off list drafted: `crm-field-handoff.md`** — exact field names/types/options
> for the CRM team, covering (1) the Pass A prod-parity gap and (2) the new fields
> below. Give that to whoever owns the MN-INTAKE CRM build.

Cannot be written until they exist in the CRM (name + type + enum options):
- **Contact** meeting-preference (or decide to use `CEngagement.meetingCadence` /
  `Contact.acceptanceStatusMeetings` instead — both already exist).
- **Contact** notification-preference.
- **Contact** code-of-conduct bool (note `CMentorProfile.mentorCodeAccepted`
  already exists for the mentor side).
- **CMentorProfile** `industryExperience` → **make it a multiEnum on BOTH CRMs with
  the 20 NAICS options** (decided 2026-06-30; it's currently multiEnum-empty on
  crm-test and a divergent single-enum on prod). Then repoint
  `industry_experience` → `industryExperience` + the form sync marker. Until built,
  stays first-value-only → `industrySector`. Specced in `crm-field-handoff.md`.

**Mentor decisions resolved (2026-06-30, Doug):**
- Work experience → **keep `mentorProfessionalBio`** (no build, already correct).
- Industry experience → **fix + map `industryExperience`** (the bullet above).

Each new enum also needs its options reflected into the relevant form via the
options.js sync.

### Pass D — Form changes (input not collected today) 📝

- **partner** + **sponsor** forms collect **no** consent at all → add the consent
  checkbox(es) to `index.html` + collect in `app.js` + accept in `schemas.py`
  (with the submit-gating validator) per the consent model chosen below.
- **client-intake** + **volunteer**: if the consent model is "three separate
  checkboxes," split the single `terms_accepted` into three.

### Pass E — Consent model 📝 (the key open decision)

Forms today: client-intake & volunteer collect ONE `terms_accepted`; partner &
sponsor collect none. Targets: `Contact.cTermsOfUseAccepted` ✅,
`Contact.cPrivacyPolicyAccepted` ✅, code-of-conduct (Contact 🏗️ / mentor
`mentorCodeAccepted` ✅). Two options:
- **One checkbox sets all** — single "I accept the Code of Conduct, Terms &
  Privacy Policy" per form; on submit set every applicable CRM bool true. Add that
  one checkbox to partner/sponsor.
- **Three separate checkboxes** — three required boxes per form, each → its own
  bool.
Either way, the Contact code-of-conduct bool (Pass C) must exist before that part
can be written; mentor uses `mentorCodeAccepted` which already exists.

---

## Cross-cutting concerns

1. **Find-or-create is create-only.** `_find_or_create_contact` (and the Account
   finder) **return early on an existing match and do not update**. So every new
   Contact/Account field above is written **only for first-time submitters**; a
   repeat email keeps its old record untouched. **Decision needed:** acceptable,
   or add an update-on-match path (more API calls, risk of clobbering staff edits)?
2. **`year_formed` → `formationDate`.** Form gives an int year; field is a date.
   Plan: store `YYYY-01-01`. Confirm that representation is acceptable.
3. **Enum option parity.** Any form value written to an enum must be a live CRM
   option or the sanitizer drops it. This is why Pass A is coupled to the
   options.js sync. `how_did_you_hear` especially changes from a free-text
   `source` (varchar, anything goes) to a validated enum.
4. **Keep `CIntakeSubmission.source`?** It still captures how-did-you-hear in the
   audit log; harmless to keep alongside the new structured Contact field.
5. **Prod parity.** Run the read-only field+option audit against prod before
   shipping; record any crm-test↔prod divergence.
6. **Mentor entity confirmations.** Mapping labels `howDidYouHearAboutCBM` and
   `fluentLanguages` as "Contact"/"Client"; both fields actually live on
   `CMentorProfile` (current behavior). Confirm we keep them on the profile.

## Open decisions (resolve before coding)

1. Consent model: one checkbox vs three (Pass E).
2. Repeat-submitter: update existing Contact/Account, or stay create-only (#1)?
3. Pass B retargets: Area of Expertise, Partner value — move or write both?
4. Mentor work-experience: build a field, or accept `mentorProfessionalBio`?
5. Mentor industry-experience: build multiEnum, or accept single-value
   `industrySector`?
6. Meeting / notification preference: build Contact fields, or reuse
   `CEngagement.meetingCadence` / `Contact.acceptanceStatusMeetings`?
7. `year_formed` stored as `YYYY-01-01` date — OK?

## Recommended sequence

1. Resolve the open decisions above.
2. **Pass A** + options.js sync + tests + crm-test live verify.
3. Verify **prod** field/option parity.
4. Hand off **Pass C** field builds to MN-INTAKE; sync options when they land.
5. **Pass D** form changes + **Pass E** consent once the fields exist.
6. **Pass B** retargets per decision.
7. Version bump + CHANGELOG per shipped pass; CLAUDE.md status update.

## Verification per pass

- `uv run pytest -q` (add coverage for new payload keys).
- `uv run python scripts/sync_form_options.py` (dry-run) — confirm no enum drift.
- Live: run the orchestrator against crm-test with a real client, GET-verify the
  written fields, then clean up `ZZTEST` records in the EspoCRM UI (the intake API
  user is create-only).
- Repeat the read-only metadata audit on prod before prod ships.
