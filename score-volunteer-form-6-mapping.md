# SCORE Form 6 (Volunteer / Become a Mentor) — Field Inventory & CBM Mapping

**Source:** https://score.tfaforms.net/6 (FormAssembly form 6, "Volunteer with SCORE")
**Captured:** 2026-05-28 from raw form HTML
**Purpose:** research input for the multi-form architecture decision, and a draft
mapping of this form to the CBM canonical model.

## 1. What this form is

This is a **mentor/volunteer application**, not a client intake. In the CBM model
it corresponds to the **Mentor Recruitment (MR) domain, MR-APPLY process**. A
submission creates **one record**: a **Contact with `contactType` = "Mentor"** and
`mentorStatus` = "Submitted". There is **no Account and no Engagement** — a
fundamentally different create-and-link shape from the client-intake form (111),
which creates three linked records.

The fields correspond almost one-to-one to the existing `MR-Contact.yaml`
custom fields (the Mentor application surface).

## 2. Field inventory

### Identity & contact
| Form label | Type | Notes |
|---|---|---|
| First Name | text | |
| Middle Initial | text (maxlength 1) | |
| Last Name | text | |
| Preferred Name | text | |
| Email | email | |
| Please re-enter Email | email | confirm-only, not stored |
| Street | text | address |
| Zip Code | text | |
| Phone | tel (`###-###-####`) | |
| Phone Type | select | Mobile · Home · Work |
| How would you like us to contact you? | select | Email · Phone · Text · No Preference |

### Motivation & professional background
| Form label | Type | Notes |
|---|---|---|
| Why would you like to volunteer for SCORE? | textarea | motivation |
| Describe your Work Experience | textarea | |
| Upload Resume (+ up to 4 additional files) | **file upload** | new capability — see §5 |
| Are you currently employed? | select | Yes, Full-time · Yes, Part-time · No |
| LinkedIn Profile | text/url | |

### Expertise & matching (all "choose up to 6" / multi-select)
| Form label | Type | Options |
|---|---|---|
| Industry Experience | multi-select (max 6) | 43 values (flat business-type list) |
| Areas of Expertise | multi-select (max 6) | 40 values (Accounting & Finance … Work/Life Balance) |
| Other Area of Expertise | text | free-text overflow |
| Fluent Languages | checkboxes (+ "Show More") | English/Spanish/Chinese/Tagalog/Vietnamese/French/Korean/Arabic + ~30 more |
| Other Language | text | free-text overflow |

### Referral & compliance
| Form label | Type | Options |
|---|---|---|
| How did you hear about SCORE? | select | 10 values (Friend or relative, Newspaper, Online search, Radio, SBA, SCORE client or volunteer, Social media, TV, Workshop/Event, Other) |
| Referrer Name | text | |
| Workshop / Event | text | |
| Have you ever been convicted of a felony? | select | No · Yes |
| Consent (Code of Conduct / Terms / Privacy) | checkbox | required |

## 3. Mapping to CBM `Contact` (contactType = Mentor)

| Form field | Target `Contact` field (per MR-Contact.yaml) | Type |
|---|---|---|
| First / Middle Initial / Last / Preferred Name | firstName / middleName / lastName / preferredName | native + `preferredName` |
| Email | personalEmail | email |
| Street / Zip | addressStreet / addressPostalCode | native |
| Phone / Phone Type | phoneNumber (+ phone type) | native (type via phoneNumberData) |
| How to contact you | *(new — preferred-contact-method; pending carry-forward)* | enum |
| Why volunteer | whyInterestedInMentoring | wysiwyg |
| Describe work experience | professionalBio | wysiwyg |
| Currently employed | currentlyEmployed (+ derive employment level) | bool |
| LinkedIn | linkedInProfile | url |
| Industry Experience | industrySectors | multiEnum — **value-list reconcile** (form uses 43 flat values; canonical is 20 NAICS) |
| Areas of Expertise | mentoringFocusAreas / skillsExpertiseTags | multiEnum — **value-list reconcile** |
| Fluent Languages | fluentLanguages | multiEnum |
| How did you hear | howDidYouHearAboutCbm | enum — reconcile to canonical 8-value CBM list |
| Felony conviction | felonyConvictionDisclosure | bool |
| Consent | termsAndConditionsAccepted (+ termsAndConditionsAcceptanceDateTime) | bool + datetime |

**System-set (no form input):** contactType = "Mentor"; mentorStatus = "Submitted";
applicant-since timestamp. (No Account, no Engagement, no primary-contact link.)

**Dropped / deferred (as the client-intake spec did):** Referrer Name, Workshop/Event,
resume *additional* files beyond the first (TBD), and the free-text "Other …" overflow
fields pending a value-list decision.

## 4. Value-list reconciliations (upstream-owned, per CBM methodology)
- Industry Experience: 43 flat values vs. canonical 20 NAICS sectors.
- Areas of Expertise: 40 values — confirm whether these land in `mentoringFocusAreas`
  (42-value canonical) or `skillsExpertiseTags` (33-value canonical).
- How-did-you-hear: 10 SCORE values → canonical 8-value CBM list.
- Fluent Languages: confirm against canonical `fluentLanguages` (36-value) list.

## 5. New capabilities this form needs (that form 111 did not)
1. **File upload** (resume) → ✅ **implemented**: `core.espo.upload_attachment`
   (EspoCRM Attachment API), wired in the volunteer orchestrator (uploads then
   links via `cResume`Ids). The frontend reads the file to base64 with a 5 MB cap
   and an allowed-type list. *Additional* files beyond the first remain deferred.
2. **"Choose up to N" multi-select** (max 6) → ✅ implemented: enforced client-side
   (boxes disable at the cap) and validated server-side (`max_length=6`).
3. **Progressive disclosure within a field** (Fluent Languages "Show More") — the
   UI shows the full language list directly; a "show more" affordance is optional.

## 6. Architecture implications (for the multi-form decision)
- **Same machinery, different mapping.** Form 6 reuses every shared piece — proxy,
  EspoCRM client, find-or-create, anti-spam, idempotency, design system — but its
  orchestration is *one* Contact create, versus form 111's three-record sequence.
  This is the clearest argument for **shared core + per-form mapping module**: the
  per-form code is a schema + an entity-mapping, nothing else.
- **The core grew a file-upload primitive** to serve this form — `upload_attachment`
  now lives in the shared EspoCRM client, written once and reusable by any future
  form that takes documents. (Architecture test: passed — the new shared capability
  slotted into the core without touching client-intake.)
- **Value-list reconciliation is per-form upstream work** regardless of code
  structure; both forms hit the same NAICS / focus-area / how-heard lists, so a
  shared options module (sourced from canonical lists) avoids duplicating them.
