# CBM Client Intake Application
## Requirements Specification

---

| Field | Value |
|---|---|
| Document | Requirements Specification |
| Project | CBM Client Intake Application |
| Status | Draft |
| Version | 0.1 |
| Last Updated | 05-28-26 01:32 |
| Owner | David Bower |

### Change Log

| Version | Date (MM-DD-YY HH:MM) | Author | Changes |
|---|---|---|---|
| 0.1 | 05-28-26 01:32 | Claude (scaffold) | Initial scaffold. Document control, change log, and the approved section structure established. Upstream sources cited at their current versions. Context overview and known open issues seeded. Design-dependent sections (form flow, field specification, branching logic, validation, integration requirements) left as placeholders pending the canonical data extraction and the branching design. |

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
| Mentoring Domain Client Intake process document (MN-INTAKE) | dbower44022/ClevelandBusinessMentoring | v2.4 | The intake process definition, data items collected, process-level system requirements, and the three-record outcome. |
| Contact Entity Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v1.7 | Canonical Contact field definitions, types, and constraints. |
| Account Entity Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v1.8 | Canonical Account field definitions, types, and constraints. |
| Engagement Entity Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v1.2 | Canonical Engagement field definitions, types, and constraints. |
| Master Product Requirements Document | dbower44022/ClevelandBusinessMentoring | v2.5 | The Universal Contact-Creation Rules and the Account creation precedence ladder. |
| Entity Inventory | dbower44022/ClevelandBusinessMentoring | v1.6 | Entity ownership and cross-domain field provenance. |

### 2.2 Carry-forward governance

Changes to any cited upstream document that affect Client Intake generate a carry-forward into this specification, following the carry-forward discipline used within the Cleveland Business Mentoring project. A carry-forward updates the relevant section here, bumps the cited upstream version, and records the change in the change log above.

A tracked follow-on already exists: the Mentoring Domain Client Intake process document is expected to receive a version 2.6 content update acknowledging that the intake form is implemented as a dynamic branching experience and stating the data-integrity expectation for the three-record creation. That update is sequenced after the in-flight four-session remediation workpacket on MN-INTAKE. When it lands, the version reference in Section 2.1 is bumped to 2.6 and the relevant sections here are reconciled.

---

## 3. Context Overview

A completed intake submission results in three linked records being created in the system of record:

1. An **Account** record representing the client organization.
2. A **Contact** record representing the individual applicant, linked to the Account.
3. An **Engagement** record representing the mentoring request, linked to the Account.

The application is a satellite of the system of record. It does not maintain a parallel store of business data; the canonical records live in the system of record. The exact sequencing, failure handling, and integration mechanism for the three-record creation are specified in Section 8 at the requirements level and in the Technical Design document at the implementation level.

---

## 4. User Experience and Form Flow

_Placeholder. To be authored. This section describes the dynamic branching intake experience in narrative form and includes a flow diagram. It is design work that has not yet been done and is the first content decision to resolve, since the field specification (Section 5) and the branching logic (Section 6) both depend on it._

---

## 5. Field Specification

_Placeholder. To be authored. Field-by-field specification — label, help text, type, required or optional status, conditional display rule, and target entity and field — extracted from the canonical sources cited in Section 2 (MN-INTAKE v2.4 and the Contact, Account, and Engagement Entity Product Requirements Documents) and reconciled with the agreed starting field set. The canonical extraction has not yet been performed._

---

## 6. Branching Logic

_Placeholder. To be authored. The conditional rules that determine which follow-up questions are presented based on prior answers, stated explicitly. Depends on Section 4._

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

*End of document.*
