# CBM Client Intake Application
## Requirements Specification

---

| Field | Value |
|---|---|
| Document | Requirements Specification |
| Project | CBM Client Intake Application |
| Status | Draft |
| Version | 0.4 |
| Last Updated | 05-28-26 10:36 |
| Owner | David Bower |

### Change Log

| Version | Date (MM-DD-YY HH:MM) | Author | Changes |
|---|---|---|---|
| 0.1 | 05-28-26 01:32 | Claude (scaffold) | Initial scaffold. Document control, change log, and the approved section structure established. Upstream sources cited at their current versions. Context overview and known open issues seeded. Design-dependent sections (form flow, field specification, branching logic, validation, integration requirements) left as placeholders pending the canonical data extraction and the branching design. |
| 0.2 | 05-28-26 10:02 | Claude (edit) | Corrected upstream version citations to the versions current on main (MN-INTAKE v2.7, Account Entity PRD v1.9, Engagement Entity PRD v1.3; Contact Entity PRD v1.7 unchanged). Reworded the carry-forward follow-on to be version-agnostic, since MN-INTAKE has advanced past the originally assumed v2.6. |
| 0.3 | 05-28-26 10:20 | Claude (edit) | Wrote finished content for Section 4 (form flow), Section 5 (field specification, reconciled to MN-INTAKE v2.7 and the Contact/Account/Engagement Entity PRDs), and Section 6 (branching logic). Added Section 11 carry-forward register and open-decisions list. Reflects the approved reconciliation: canonical multi-select mentoring areas, two-level NAICS, Business Stage as required field and branch trigger, how-did-you-hear mapped to the canonical 8-value list, kept SCORE-only fields (terms, marketing consent, meeting/notification preference, year formed, number of employees), dropped fields (referrer, workshop/event, schedule-now), and deferred Requested Mentor. |
| 0.4 | 05-28-26 10:36 | Claude (edit) | Resolved the presentation-model decision in favor of a multi-step wizard and rewrote Section 4 to specify the four-step flow with the business-profile branch revealing in place within the Business step. Authored Section 7 (Validation Rules, VR-1 through VR-16), Section 8 (Integration Requirements, INT-1 through INT-9), Section 9 (Notifications and Confirmations, NC-1 through NC-6), and Section 10 (Non-Functional Requirements, NFR-1 through NFR-9). Closed the presentation-model row in Section 11.2; the BR-1 threshold row remains open per instruction. Sections 7 through 10 are product-agnostic per the PRD content rules. |

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

The intake is presented as a guided, multi-step form that adapts to the applicant's answers. Most questions are always shown. One answer changes what follows: the applicant's Business Stage determines whether the business-profile questions are presented (see Section 6).

The logical order of the form is: applicant identity (name, email, phone, zip code), how the applicant heard about CBM, communication preferences (meeting and notification), the mentoring request (areas of mentoring and a free-text description of needs), the Business Stage, the business-profile questions (shown only when applicable), and finally marketing consent and terms acceptance.

**Presentation model — resolved (05-28-26): multi-step wizard.** The applicant moves through a short sequence of steps, one logical group of questions per step, with Back and Next controls and a visible progress indicator. The steps are:

1. **About You** — First Name, Last Name, Email Address (with confirmation), Phone Number, Zip Code, and How did you hear about CBM.
2. **Your Mentoring Request** — Area(s) of Mentoring, Describe Your Mentoring Needs, Meeting Preference, and Notification Preference. The two communication preferences are grouped here, with the request they pertain to, rather than as a separate step.
3. **Your Business** — Business Stage, followed by the business-profile questions. The business-profile questions appear within this same step, in place, only when the Business Stage is not Pre-Startup (see Section 6, BR-1). The step count does not change with the branch: there is no separate business step that appears or disappears, which keeps the progress indicator stable for every applicant.
4. **Review and Submit** — a read-only summary of all answers, the Marketing Communication Consent, the Terms & Conditions acceptance, and the submit action.

Each step is validated when the applicant attempts to advance, and the complete field set is validated again at submission (Section 7). The field set (Section 5) and the branching rules (Section 6) are independent of this presentation choice; only the grouping of questions into steps is settled here. This decision is recorded as resolved in Section 11.2.

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

This section defines the validation actually applied at the form. The Entity Product Requirements Documents define the underlying data type and field constraint for each canonical field; the rules here are the form-layer checks, which the application owns and which may be stricter than the canonical constraint. Validation runs against the value lists named in Section 5; those lists are owned upstream and several are unresolved (Section 11), so a rule that constrains a field to "its canonical values" is enforced against whatever the resolved list turns out to be.

### 7.1 Field-level rules

| ID | Rule | Applies to |
|---|---|---|
| VR-1 | Required before submission is accepted. The field must be present and non-empty. | First Name, Last Name, Email Address, Confirm Email Address, Phone Number, Zip Code, Area(s) of Mentoring, Describe Your Mentoring Needs, Business Stage, Terms & Conditions Accepted |
| VR-2 | Must be a syntactically valid email address. | Email Address |
| VR-3 | Must exactly match the Email Address. This field is validation-only and is not delivered to the system of record (Section 5.1). | Confirm Email Address |
| VR-4 | Must be a valid North American phone number. The application accepts common input formats and normalizes the value to a single canonical form before delivery. | Phone Number |
| VR-5 | Must be a valid five-digit United States postal code. Geographic eligibility (for example, restriction to Northeast Ohio) is not enforced at the form; out-of-area inquiries are accepted and handled downstream. | Zip Code |
| VR-6 | When shown and provided, a four-digit year no earlier than 1900 and no later than the current year. | Year Formed |
| VR-7 | When shown and provided, a whole number of zero or greater. | Number of Employees |
| VR-8 | When shown and provided, a syntactically valid web address. The application accepts input without a scheme and normalizes it. | Business Website |
| VR-9 | At least one value must be selected, and every selected value must belong to the canonical Mentoring Focus Areas list. | Area(s) of Mentoring |
| VR-10 | The selected value must be one of the field's canonical values, or empty when the field is not required. | How did you hear about CBM, Business Stage, Industry Sector, Industry Subsector, Meeting Preference, Notification Preference |
| VR-11 | Required free text. Must contain non-whitespace content, must not exceed a defined maximum length, and is sanitized on receipt so that no markup is stored or rendered as active content. | Describe Your Mentoring Needs |
| VR-12 | Submission is blocked unless this is affirmatively accepted. | Terms & Conditions Accepted |

### 7.2 Cross-field and conditional rules

**VR-13 — Conditional fields validate only when visible.** The business-profile fields (Business Name, Business Website, Industry Sector, Industry Subsector, Year Formed, Number of Employees) are validated only while they are shown under BR-1. When the Business Stage is Pre-Startup and the block is hidden, those fields are neither required nor validated and carry no value into the system of record.

**VR-14 — Industry Subsector requires an Industry Sector.** Industry Subsector cannot hold a value unless an Industry Sector has been selected, and its permitted values are limited to those valid for the selected Sector. This enforces BR-2 at the validation layer.

**VR-15 — Normalization before validation and delivery.** Leading and trailing whitespace is trimmed from all text inputs before validation and before delivery to the system of record.

### 7.3 Validation timing and authority

Because the form is a multi-step wizard (Section 4), the fields on a step are validated when the applicant attempts to advance from that step, and the applicant cannot proceed past a step that has missing required fields or invalid values within it. The complete field set is validated once more at submission.

**VR-16 — Server-side validation is authoritative.** All validation in this section is performed both in the browser (for immediate applicant feedback) and on the server (for correctness and security). The server-side result is authoritative; a submission that fails server-side validation is rejected even if it passed in the browser. The security rationale for this is stated in Section 10.

---

## 8. Integration Requirements

This section states, at the requirements level, what the application must deliver to the system of record and what must be true of the result. The transactional mechanism, the failure-recovery and retry behavior, the idempotency mechanism, and the authentication to the system of record are implementation matters and belong to the Technical Design document (Sections 3 and 4 there). The requirements here are stated as outcomes, not mechanisms.

**INT-1 — Three-record creation.** A completed submission must result in three linked records in the system of record: an Account representing the client organization, a Contact representing the applicant and linked to the Account, and an Engagement representing the mentoring request and linked to the Account (Section 3).

**INT-2 — Field delivery.** The application must deliver each collected field to its target field exactly as mapped in Section 5. Confirm Email Address is not delivered, as it is a validation-only field (Section 5.1, VR-3).

**INT-3 — System-set fields.** At record creation the integration sets the following without applicant input, per Section 5.4: Account Type of Client, Contact Type of Client, Primary Contact of Yes, Engagement Status of Submitted, the auto-generated Engagement Name, the Contact-to-Account link, the Engagement-to-Account link, the Primary-Engagement-Contact link, and applicantSinceTimestamp. The form of the auto-generated Engagement Name is defined canonically by the Mentoring Domain Client Intake process document (DAT-020) and is not redefined here.

**INT-4 — Account precedence is honored, not re-implemented.** When the applicant provides a Business Website, record creation must honor the canonical Account creation precedence ladder defined in the Master Product Requirements Document, which matches on website domain first and otherwise creates a new Account. The application must not introduce any additional Account matching beyond what that ladder specifies; in particular, it must not match on company name, which was deliberately removed from the ladder as a confidentiality and data-integrity risk.

**INT-5 — Source attribution is delivered, not adjudicated.** The application delivers the applicant's How did you hear about CBM selection (one of the eight canonical values) to Contact.howDidYouHearAboutCbm. The precedence and audit-trail behavior for source attribution is owned by the Mentoring Domain Client Intake process document and the CR-MARKETING sub-domain (the intake-time layered write under MN-INTAKE REQ-013) and is applied at record creation; the application does not adjudicate attribution precedence.

**INT-6 — Integrity of the compound creation.** A submission must either produce the complete and correctly linked set of three records, or leave the system of record with no orphaned or partial records that are visible to operators as if they were a valid intake. The applicant must not be shown a success confirmation (Section 9) unless the complete record set has been created or has been durably accepted for guaranteed creation. The transactional semantics, partial-failure recovery, and retry behavior that achieve this are specified in the Technical Design document.

**INT-7 — No duplicate record sets and Contact de-duplication.** A single applicant submission, including a resubmission caused by a double-click, a page refresh, or an automatic retry, must not create more than one set of records. Where a Contact already exists for the submitted email address, the integration must follow the canonical de-duplication-by-email rule from the Mentoring Domain Client Intake process document (MN-INTAKE REQ-010) rather than create a duplicate Contact. The mechanism that guarantees this is an implementation matter for the Technical Design document.

**INT-8 — Confirmable outcome.** The application must be able to determine, for each submission, whether the complete record set was created. This determination is what drives the truthful applicant confirmation and administrator notification in Section 9; neither may be issued on an unconfirmed or failed creation.

**INT-9 — System of record authority.** The application does not maintain a parallel canonical store of business data; the canonical Account, Contact, and Engagement records live in the system of record (Section 3). The application may retain a minimal operational record of each submission for failure recovery and administration (see the Technical Design document, Section 5), but that operational record is not canonical and is not a second source of truth for client data.

---

## 9. Notifications and Confirmations

This section covers what the applicant sees and receives after submitting, and what the administrator is notified of. The exact wording of every applicant-facing message and administrator notification is content authored and owned by CBM and is not specified here; this section specifies the behavior the content sits inside.

**NC-1 — On-screen confirmation.** On a confirmed successful submission (INT-6, INT-8), the applicant is shown a clear confirmation that their request has been received, together with a plain statement of what happens next and the rough timeframe CBM sets for a response. The confirmation must not imply that a mentor has been assigned or matched, because the Engagement is created with a status of Submitted, not matched.

**NC-2 — Applicant confirmation message.** The applicant receives a confirmation of receipt sent to the Email Address they provided. The confirmation of receipt is always sent by email, because an email address is always collected and required. The applicant's Notification Preference (Email or Text Message) governs how CBM communicates with them about the request from that point forward, not the channel of this initial receipt. The confirmation is issued only after the record set is confirmed created; it is never sent on a partial or failed creation.

**NC-3 — Administrator notification.** On each new submission, the Client Administrator receives an automatic notification that a new submission has been received. The notification describes the behavior generically and does not name a specific message template, consistent with how the Mentoring Domain Client Intake process document and the Mentor Recruitment process documents describe submission notifications.

**NC-4 — Applicant-facing failure handling.** If a submission cannot be completed, the applicant is shown a clear, non-technical message explaining that the request could not be submitted and what to do next, such as trying again or contacting CBM directly. The applicant is never shown a success message for a submission that did not complete. The applicant's entered answers are preserved so they can retry without re-entering the form.

**NC-5 — Administrator visibility of failures.** A submission that fails record creation must not be silently dropped. It must be retained and surfaced to administrators so that it can be followed up or reprocessed. The administrative interface, reprocessing flow, and the authentication protecting them are specified in the Technical Design document, Section 5.

**NC-6 — Content ownership.** The wording of the on-screen confirmation, the applicant confirmation message, the administrator notification, and the failure messages is CBM-authored. The application must allow this content to be maintained without requiring a change to the form's field set or branching logic.

---

## 10. Non-Functional Requirements

These requirements are stated at the requirements level and name no specific technology. The choice of how each is satisfied belongs to the Technical Design document.

**NFR-1 — Accessibility.** The form must meet the Web Content Accessibility Guidelines version 2.1 at conformance Level AA. It must be fully operable by keyboard, compatible with screen readers, and present sufficient color contrast. Every field must have a programmatically associated label, and every validation error must be programmatically associated with the field it concerns. Because the form is a multi-step wizard, each step change must move keyboard focus appropriately and announce the new step to assistive technology, and the progress indicator must be perceivable to assistive technology.

**NFR-2 — Mobile and responsive use.** The form must be fully usable on phones and tablets as well as on desktop computers, with touch-friendly controls and a layout that adapts to small screens. The wizard's steps, navigation, and progress indicator must all work on a small screen. CBM's prospective-client audience includes a substantial share of mobile users, so mobile is a first-class target, not an afterthought.

**NFR-3 — Browser support.** The form must work correctly on the current and immediately prior major versions of the widely used web browsers, on both desktop and mobile.

**NFR-4 — Resistance to automated submission.** The form must defend against automated and bulk submissions. The chosen defense must not materially impede a legitimate applicant and must not conflict with the accessibility requirement in NFR-1, so approaches that present difficult visual or audio puzzles are disfavored.

**NFR-5 — Security.** All input must be validated and sanitized on the server, which is the authoritative validation layer (VR-16). The application must be protected against common web application vulnerabilities, including injection, cross-site scripting, and cross-site request forgery. All traffic between the applicant's browser and the application must be encrypted in transit. Any credentials or secrets used to authenticate to the system of record must never be exposed to the browser.

**NFR-6 — Data protection and privacy.** The form collects personal data, including the applicant's name, email address, phone number, zip code, and business information. This data must be handled in line with CBM's published privacy commitments and applicable data-protection expectations. The form collects only the data specified in Section 5, must not expose submitted data to unauthorized parties, and must protect personal data held in any operational store at rest. The applicant's affirmative Terms & Conditions acceptance is captured and delivered as the record of consent (Section 5.3, termsAccepted).

**NFR-7 — Performance and availability.** The form must load and become interactive quickly on a typical broadband or mobile connection, and a submission must complete, or be durably accepted for completion, without an unreasonable wait. Because the form is public-facing and intake can arrive at any time, the application is expected to be continuously available, with maintenance handled so as not to interrupt prospective applicants where practical.

**NFR-8 — Reliable capture of submissions.** A submission that the application has accepted from the applicant must not be lost. It must be durably retained until the complete record set is confirmed created in the system of record (INT-6, INT-8). The recovery behavior when creation is delayed or fails is specified in the Technical Design document, Section 4.

**NFR-9 — Maintainable value lists.** The canonical value lists used by the form — the Mentoring Focus Areas, the Industry Sector and Subsector lists, the How did you hear about CBM list, and the others named in Section 5 — are owned upstream, and several are unresolved (Section 11). The application must obtain these lists in a way that lets them be updated when the upstream lists are finalized or later change, without requiring a change to the application's code.

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
| Presentation model | Single scrolling page with progressive reveal, or a multi-step wizard (Section 4) | Resolved 05-28-26 — multi-step wizard. Four steps with the business-profile branch revealing in place; see Section 4. |
| BR-1 threshold | Confirm that Pre-Startup is the correct cut-off for hiding the business-profile block (Section 6) | Open — draft is Pre-Startup hides, all other stages show |

---

*End of document.*
