# CBM Client Intake Application
## Requirements Specification

---

| Field | Value |
|---|---|
| Document | Requirements Specification |
| Project | CBM Client Intake Application |
| Status | Draft |
| Version | 0.4 |
| Last Updated | 05-28-26 10:30 |
| Owner | David Bower |

### Change Log

| Version | Date (MM-DD-YY HH:MM) | Author | Changes |
|---|---|---|---|
| 0.1 | 05-28-26 01:32 | Claude (scaffold) | Initial scaffold. Document control, change log, and the approved section structure established. Upstream sources cited at their current versions. Context overview and known open issues seeded. Design-dependent sections (form flow, field specification, branching logic, validation, integration requirements) left as placeholders pending the canonical data extraction and the branching design. |
| 0.2 | 05-28-26 10:02 | Claude (edit) | Corrected upstream version citations to the versions current on main (MN-INTAKE v2.7, Account Entity PRD v1.9, Engagement Entity PRD v1.3; Contact Entity PRD v1.7 unchanged). Reworded the carry-forward follow-on to be version-agnostic, since MN-INTAKE has advanced past the originally assumed v2.6. |
| 0.3 | 05-28-26 10:20 | Claude (edit) | Wrote finished content for Section 4 (form flow), Section 5 (field specification, reconciled to MN-INTAKE v2.7 and the Contact/Account/Engagement Entity PRDs), and Section 6 (branching logic). Added Section 11 carry-forward register and open-decisions list. Reflects the approved reconciliation: canonical multi-select mentoring areas, two-level NAICS, Business Stage as required field and branch trigger, how-did-you-hear mapped to the canonical 8-value list, kept SCORE-only fields (terms, marketing consent, meeting/notification preference, year formed, number of employees), dropped fields (referrer, workshop/event, schedule-now), and deferred Requested Mentor. |
| 0.4 | 05-28-26 10:30 | Claude (edit) | Resolved the presentation-model open decision (§11.2): the intake is a **multi-step wizard** with one logical group per step. Rewrote Section 4 to describe the four-step flow and the placement of the Business-Stage branch within the business step. Field set and branching rules unchanged. |

---

## 1. Purpose and Scope

This document specifies the requirements for a custom web application that collects information for the Client Intake process. It states what the application must do for the person filling out the form and what it must deliver to the system of record. It is product-agnostic at the requirements level; implementation choices belong in the companion Technical Design document.

This document is the implementation-level authority for *how* Client Intake is carried out as a web application. It is **not** the authority for *what* the Client Intake process is at the business level. That authority remains with the Mentoring Domain Client Intake process document in the Cleveland Business Mentoring repository (see Section 2).

**In scope:** the intake form experience, the questions asked and their ordering, dynamic branching, field-level validation, the data delivered to the system of record, applicant-facing confirmation, administrator notification, and the application's non-functional requirements.

**Out of scope:** the business definition of the intake process, the canonical field and entity definitions, the value lists owned by the upstream Entity Product Requirements Documents, and any concern owned by other processes (mentor matching, marketing attribution reporting, and so on).

---

## 2. Upstream Sources and Traceability

This is a derived specification. The authoritative source for the Client Intake process at the business level is the Mentoring Domain Client Intake process document. This specification translates that process into an implementable web application and is kept aligned with it through carry-forward.

### 2.1 Cited upstream sources

The following are cited at the versions current as of this scaffold. Each version reference is to be confirmed and, where necessary, bumped as the upstream documents advance.

| Upstream document | Repository | Version | What this specification draws from it |
|---|---|---|---|
| Mentoring Domain Client Intake process document (MN-INTAKE) | dbower44022/ClevelandBusinessMentoring | v2.7 | The intake process definition, data items collected, process-level system requirements, and the three-record outcome. |
| Contact Entity Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v1.7 | Canonical Contact field definitions, types, and constraints. |
| Account Entity Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v1.9 | Canonical Account field definitions, types, and constraints. |
| Engagement Entity Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v1.3 | Canonical Engagement field definitions, types, and constraints. |
| Master Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v2.5 | The Universal Contact-Creation Rules and the Account creation precedence ladder. |
| Entity Inventory | dbower44022/ClevelandBusinessMentoring | v1.6 | Entity ownership and cross-domain field provenance. |

### 2.2 Carry-forward governance

Changes to any cited upstream document that affect Client Intake generate a carry-forward into this specification, following the carry-forward discipline used within the Cleveland Business Mentoring project. A carry-forward updates the relevant section here, bumps the cited upstream version, and records the change in the change log above.

A tracked follow-on exists: the Mentoring Domain Client Intake process document does not yet acknowledge that the intake form is implemented as a dynamic branching experience, nor state the data-integrity expectation for the three-record creation. A future MN-INTAKE update (target version to be determined; the document is currently at v2.7) will add both. When it lands, the version reference in Section 2.1 is bumped and the relevant sections here are reconciled.

---

## 3. Context Overview

A completed intake submission results in three linked records being created in the system of record:

1. An **Account** record representing the client organization.
2. A **Contact** record representing the individual applicant, linked to the Account.
3. An **Engagement** record representing the mentoring request, linked to the Account.

The application is a satellite of the system of record. It does not maintain a parallel store of business data; the canonical records live in the system of record. The exact sequencing, failure handling, and integration mechanism for the three-record creation are specified in Section 8 at the requirements level and in the Technical Design document at the implementation level.

---

## 4. User Experience and Form Flow

The intake is presented as a **multi-step wizard** that adapts to the applicant's answers. Each step collects one logical group of questions; the applicant advances step by step, with the ability to move back, and submits from the final step. Most questions are always shown. One answer changes what follows: the applicant's Business Stage determines whether the business-profile questions are presented within the business step (see Section 6).

The wizard has four steps, in this order:

1. **About You** — applicant identity (first name, last name, email, confirm email, phone, zip code) and how the applicant heard about CBM.
2. **Your Mentoring Request** — communication preferences (meeting and notification) and the mentoring request itself (areas of mentoring and a free-text description of needs).
3. **Your Business** — Business Stage (always shown). When Business Stage is not Pre-Startup, the business-profile questions (business name, website, industry sector and subsector, year formed, number of employees) appear within this step; when it is Pre-Startup, the step contains only the Business Stage question.
4. **Review and Submit** — marketing consent and terms acceptance, with a read-back summary of the entered answers, and the submit action.

Step boundaries are an experience decision and may be re-grouped without affecting the field set or the branching rules in Section 6, both of which are independent of how the steps are divided. A progress indicator showing the current step out of four is expected; its exact form is a design-time detail.

---

## 5. Field Specification

The field set is reconciled against the canonical intake fields in MN-INTAKE v2.7, Section 8, and the Contact, Account, and Engagement Entity Product Requirements Documents. The "Required" column is the requirement applied at the form layer, which the application owns; it may be stricter than the underlying canonical field constraint. "Provenance" gives the MN-INTAKE data-item identifier for existing canonical fields, or marks a field as new and therefore subject to the carry-forward register in Section 11.

### 5.1 Contact (the applicant)

| Form label | Target field | Type | Required | Conditional display | Provenance |
|---|---|---|---|---|---|
| First Name | Contact.firstName | varchar | Yes | Always | DAT-010 |
| Last Name | Contact.lastName | varchar | Yes | Always | DAT-011 |
| Email Address | Contact.email | email | Yes | Always | DAT-014 |
| Confirm Email Address | (not stored) | — | Yes | Always | Client-side validation only |
| Phone Number | Contact.phone | phone | Yes | Always | DAT-015 |
| Zip Code | Contact.zipCode | varchar | Yes | Always | DAT-016 (canonical optional; required at form) |
| How did you hear about CBM | Contact.howDidYouHearAboutCbm | enum (8 canonical values) | No | Always | New to intake — field exists on Contact; pending carry-forward to add to the MN-INTAKE intake data set |
| Marketing Communication Consent | Contact.marketingConsent | bool | No | Always | New canonical field — pending carry-forward |

### 5.2 Account (the business)

| Form label | Target field | Type | Required | Conditional display | Provenance |
|---|---|---|---|---|---|
| Business Stage | Account.businessStage | enum (Pre-Startup, Startup, Early Stage, Growth Stage, Established) | Yes | Always | DAT-006 — also the branch trigger (Section 6) |
| Business Name | Account.name | varchar | No | When Business Stage is not Pre-Startup | DAT-002 |
| Business Website | Account.website | url | No | When Business Stage is not Pre-Startup | DAT-003 |
| Industry Sector | Account.industrySector | enum (20 NAICS sectors) | No | When Business Stage is not Pre-Startup | DAT-007 |
| Industry Subsector | Account.industrySubsector | enum (~100, filtered by Sector) | No | When Business Stage is not Pre-Startup and a Sector is selected | DAT-008 |
| Year Formed | Account.yearFormed | int | No | When Business Stage is not Pre-Startup | New canonical field — pending carry-forward |
| Number of Employees | Account.numberOfEmployees | int | No | When Business Stage is not Pre-Startup | New canonical field — pending carry-forward |

### 5.3 Engagement (the mentoring request)

| Form label | Target field | Type | Required | Conditional display | Provenance |
|---|---|---|---|---|---|
| Area(s) of Mentoring | Engagement.mentoringFocusAreas | multiEnum (~42 canonical values, pending ISS-001) | Yes | Always | DAT-022 (canonical optional; required at form) |
| Describe Your Mentoring Needs | Engagement.mentoringNeedsDescription | wysiwyg | Yes | Always | DAT-023 |
| Meeting Preference | Engagement.meetingPreference | enum (No Preference, Video, Phone, Email, In Person) | No | Always | New canonical field — pending carry-forward |
| Notification Preference | Engagement.notificationPreference | enum (Email, Text Message) | No | Always | New canonical field — pending carry-forward |
| Terms & Conditions Accepted | Engagement.termsAccepted | bool | Yes | Always | New canonical field — pending carry-forward |

### 5.4 System-set fields (no form input)

These are set by the integration at record creation and are not presented to the applicant: Account Type = Client (DAT-001); Contact Type = Client (DAT-009); Primary Contact = Yes (DAT-018); Engagement Status = Submitted (DAT-021); the auto-generated Engagement Name (DAT-020); the Contact-to-Account, Engagement-to-Account, and Primary-Engagement-Contact relationships (DAT-019, DAT-024, DAT-025); and applicantSinceTimestamp (DAT-027).

### 5.5 Not collected in this version

Collected by the source SCORE form but deliberately excluded here: Referrer Name, Workshop / Event, and Schedule Appointment Now (dropped per the approved reconciliation). The SCORE flat business-type list is replaced by the two-level NAICS Sector and Subsector. The SCORE single-select 40-value mentoring list is replaced by the canonical multi-select Mentoring Focus Areas. The SCORE 10-value "how did you hear" list is replaced by the canonical 8-value CBM list. Requested Mentor (DAT-026) is deferred to a later phase and left null.

Canonical Contact and Account fields not asked by this form, left unpopulated for now: Middle Name (DAT-012), Preferred Name (DAT-013), LinkedIn Profile (DAT-017), Organization Type (DAT-005), and full business Address (DAT-004).

---

## 6. Branching Logic

**BR-1 — Business-profile branch (primary).** The business-profile questions are shown only when the business exists. The trigger is Business Stage.

- When Business Stage is **Pre-Startup**, the following are hidden and not collected: Business Name, Business Website, Industry Sector, Industry Subsector, Year Formed, and Number of Employees.
- When Business Stage is **Startup, Early Stage, Growth Stage, or Established**, those fields are shown.

The Pre-Startup threshold is a draft and is recorded in Section 11 for confirmation; if a different cut-off is preferred (for example, revealing business detail only at Established), only this rule changes.

**BR-2 — Industry Subsector dependency.** Industry Subsector is a dependent dropdown. Its options are filtered by the selected Industry Sector, and it remains disabled until a Sector is chosen. This dependency applies only while the business-profile block is visible under BR-1.

No other fields branch in this version. Communication preferences, how-did-you-hear, mentoring request fields, marketing consent, and terms acceptance are presented unconditionally.

---

## 7. Validation Rules

_Placeholder. To be authored. Format-level and cross-field validation applied at the form layer. The Entity Product Requirements Documents define the underlying data type and field constraint; this section defines the validation actually applied at the form._

---

## 8. Integration Requirements

_Placeholder. To be authored. The data the application must deliver to the system of record, the three-record structure, the data-integrity expectation for the compound creation stated as what must be true, and source attribution handling._

---

## 9. Notifications and Confirmations

_Placeholder. To be authored. The applicant-facing confirmation experience and the administrator notification on submission._

---

## 10. Non-Functional Requirements

_Placeholder. To be authored. Accessibility, security and anti-spam, performance, browser and mobile support, and data protection._

---

## 11. Open Issues and Dependencies

The following value lists are owned upstream and remain unresolved. They are dependencies for go-live and are tracked here for visibility; they are not resolved by this specification.

| Item | Owner | Status |
|---|---|---|
| Mentoring Focus Areas value list | CBM Leadership | Unresolved upstream |
| NAICS subsector value list | Technical Administrator | Unresolved upstream |
| Northeast Ohio zip code master list (if intake consumes it) | To be confirmed | Deferred upstream to implementation |

Additional open issues will be recorded here as they surface during authoring.

---


### 11.1 Carry-forwards into the Cleveland Business Mentoring repository

Several decisions in this specification require fields or acknowledgments to be added to canonical upstream documents. Each is a separate carry-forward that follows CBM methodology; adding canonical fields may require stakeholder review. The entity placements below are provisional and are confirmed against the target document when each carry-forward is executed.

| Upstream target | Change | Status |
|---|---|---|
| MN-INTAKE intake data set | Add "How did you hear about CBM" as an intake data item mapping to Contact.howDidYouHearAboutCbm (8 canonical values) | Pending carry-forward |
| Contact Entity PRD (v1.7) | Add marketingConsent (bool) | Pending carry-forward |
| Account Entity PRD (v1.9) | Add yearFormed (int) and numberOfEmployees (int) | Pending carry-forward |
| Engagement Entity PRD (v1.3) | Add meetingPreference (enum), notificationPreference (enum), and termsAccepted (bool) | Pending carry-forward |
| MN-INTAKE | Acknowledge that intake is implemented as a dynamic branching form and state the three-record data-integrity expectation | Pending (version-agnostic follow-on, see Section 2.2) |

### 11.2 Open decisions

| Decision | Description | Status |
|---|---|---|
| Presentation model | Single scrolling page with progressive reveal, or a multi-step wizard (Section 4) | **Resolved 05-28-26 — multi-step wizard** (four steps; see Section 4) |
| BR-1 threshold | Confirm that Pre-Startup is the correct cut-off for hiding the business-profile block (Section 6) | Open — draft is Pre-Startup hides, all other stages show |

---

*End of document.*
