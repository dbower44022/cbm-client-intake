# Claude Code Prompt — Section Edit Screens

| Revision Control | |
|---|---|
| Version | 0.1 |
| Last Updated | 07-14-26 00:48 |
| Author | Doug Bower (via Claude) |
| Status | Approved layout (edit screens mockup v2) |

**Change Log**

| Version | Date | Change |
|---|---|---|
| 0.1 | 07-14-26 00:48 | Initial draft from approved mockup v2 (v1 minus Company Partnership & account group) |

---

## Prompt

Operating mode: DETAIL. Make minimal, surgical changes. This builds on the Engagement Details view redesign (prompt v0.2 / view mockup v4): the view layout, per-section Edit buttons, contact grids, and Add flow are already specified there. This prompt specifies **the edit forms those buttons open**. The accompanying file `section-edit-screens-mockup-v2.html` is the design target — open it in a browser before writing code; it is authoritative for grouping, field widths, and picker behavior.

### General form rules

- Presentation (modal vs. inline expansion) follows the codebase's existing form pattern — do not introduce a new one.
- Forms use a 12-column grid with field widths as mocked; labeled field groups with small uppercase group headings separated by hairline rules.
- Yes/No fields render as checkboxes, never Yes/No dropdowns.
- Multi-value fields (funding sources, sales channels, certifications) render as tap-to-toggle chip selectors, never multi-select list boxes. Option lists come from the CRM field definitions — do not hardcode.
- All select/enum options come from the CRM schema; mockup options are illustrative.
- Save writes through to the CRM synchronously per existing write semantics; on failure keep the form open with an inline error. Cancel discards with no side effects.

### Reusable address block (build once, use everywhere)

A single address component laid out in postal format:
- Row 1: Address line 1 (span 8) | Address line 2 (span 4)
- Row 2: City (span 6) | State (span 2, select) | ZIP (span 4)

Used by: Company billing address, Company shipping address, Contact address. The shipping instance adds a **"Same as billing address"** checkbox above it; when checked, the shipping fields are disabled/dimmed and the save writes billing values (or the schema's equivalent — investigate whether the CRM models "same as billing" as copied values or a flag, and follow the schema).

### Time picker standard (build once, use for every time field app-wide)

Clicking a time field opens a popover — **not** a 60-minute scroll or free text as primary input:
- A grid of half-hour slots (:00 and :30 only), grouped "Morning" (8:00–11:30 AM) and "Afternoon & evening" (12:00–7:30 PM), 4 columns, one click to select.
- Selected slot highlighted navy; selection closes the popover and fills the field.
- Footer escape hatch: "Other time:" free-entry input for non-standard times (Enter commits).
- This component is the standard for all time fields in the app, including the New Session form and any future scheduling UI.

### Form 1 — Edit Engagement

Single group, one row: Status (select) | Start date (date) | Mentor (select) | Session cadence (select). Field list comes from the engagement schema — include every editable engagement field, keeping the layout compact; the four mocked fields are the known minimum.

### Form 2 — Edit Company

Groups, in order:
1. **Identity** — Company name (6) | Website (3) | Phone (3); Organization type (3) | Business stage (3) | Industry (3) | Industry sector (3).
2. **Billing address** — address block.
3. **Shipping address** — "Same as billing" checkbox + address block.

**Removed by design:** there is no Partnership & account group. All accounts in this app are client accounts, so Account type, Client status, Partner contact cadence, Partner organization type, Partner status, Sponsorship level, and Public announcement allowed do **not** appear on this form. Correspondingly, remove the Account / Cadence / Announcements rows from the Company **view** card (they were in view mockup v4's right column) — the view must not display fields the edit form doesn't manage. The Company view card right column instead carries the Business and Shipping rows.

### Form 3 — Edit Client Business Profile

Groups, in order:
1. **Business structure** — Legal entity type (4) | Formation date (4, date); checkbox set: Home based, Federal EIN on file, Ohio vendors license on file, Registered on SAM.gov.
2. **Financials** — Annual revenue range (4) | Revenue trend (4) | Profitability status (4); Funding sources used to date (chip selector, full width).
3. **Sales & market** — Primary customer type (4) | Geographic market reach (4) | Sales channels (chip selector, 4); checkbox set: Conducts business online, Has Google Business Profile, Uses email marketing.
4. **Certifications & owner demographics** — Certifications held (chip selector, full width); Client ethnicity (4) | Client race (4) | Veteran status (4).
5. **Goals** — "What does the client want help with?" (textarea, full width).

### Form 4 — Edit Contact

Used by both Client Contacts and CBM Contacts row Edit actions, and by the Add → Create new contact flow. Groups, in order:
1. **Name** — Salutation (2, select) | First name (4) | Last name (4) | Preferred name (2).
2. **Contact information** — Email (6) | Phone (3) | Contact type (3, select).
3. **Address** — address block.
4. **Preferences & agreements** — Preferred contact method (4) | Notification preference (4) | Do not call (checkbox); checkbox set: Marketing opt-in, Privacy policy accepted, Terms of use accepted, Code of conduct accepted.

If the CBM-contact entity type differs from the client contact entity in the schema (per the investigation gate in prompt v0.2), adapt this form's field set to that entity rather than forcing client-contact fields onto staff records — report the difference.

### Form 5 — New Session

Date (3, date) | Start time (3, **time picker standard**) | Duration (3, select) | Session type (3, select); Notes (textarea, full width).

**Investigate first:** the session entity's real field set — the mocked Duration and Session type fields are illustrative. Build the form from the actual schema; the fixed requirements are the postal-style layout discipline, the date field, and the time picker standard for start time. Report the session schema fields before building.

### Acceptance criteria

1. Every section Edit button and contact-row Edit opens its corresponding grouped form; Add → Create new contact opens the contact form empty.
2. Address block renders identically (postal layout) in all three uses; "Same as billing" disables and dims shipping fields.
3. Time fields use the half-hour grid popover with free-entry escape; no 60-minute minute-pickers anywhere.
4. Multi-value fields are chip selectors; boolean fields are checkboxes; option lists come from CRM field definitions.
5. Company form has no partnership/sponsor/account-type fields, and the Company view card no longer shows Account / Cadence / Announcements rows.
6. Save round-trips to the CRM and returns to view mode reflecting the change; failed saves keep the form open with an inline error.

### Report back

Before coding: the session entity field set; whether "same as billing" is a flag or copied values in the schema; any divergence between client-contact and CBM-contact entities. After coding: files touched, deviations from the mockup and why.
