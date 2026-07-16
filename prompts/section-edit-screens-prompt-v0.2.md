# Claude Code Prompt — Section Edit Screens

| Revision Control | |
|---|---|
| Version | 0.3 |
| Last Updated | 07-16-26 |
| Author | Doug Bower (via Claude) |
| Status | Approved (Company form mockup v3; rule 1 amended) |

**Change Log**

| Version | Date | Change |
|---|---|---|
| 0.1 | 07-14-26 00:48 | Initial draft from edit screens mockup v2 |
| 0.2 | 07-16-26 00:57 | Remediation of delivered Company form: width constraint, Country in address block, schema field triage, form design rules added |
| 0.3 | 07-16-26 | Rule 1 REVERSED per Doug: no width cap — edit forms are full-width with content-sized packed fields; mockup spans are relative widths, not a fixed grid |

---

## Prompt

Operating mode: DETAIL. Make minimal, surgical changes to the existing Company edit form implementation. Do not touch the other section forms except where the shared address block component changes. The accompanying file `company-edit-form-mockup-v3.html` is the design target — open it in a browser before writing code; it is authoritative for layout, grouping, and widths.

### What went wrong in the current implementation (context, not blame)

The delivered Company edit form rendered every Account-entity field at full page width with no grouping judgment: a nine-field row across the viewport, Country orphaned below the address blocks, an "Additional details" dumping ground, partner/sponsor fields that were explicitly removed in the prior revision, a system timestamp exposed as an editable field with a raw minute-level time input. This prompt corrects it and adds standing rules to prevent recurrence.

### Standing form design rules (apply to ALL edit forms, now and future)

1. **No width cap** *(v0.3 — reverses the v0.2 960px rule, per Doug 07-16-26: "the app is supposed to utilize as much of the screen as possible"; CBM users are on 4K monitors)*. Edit forms are full-width like every other screen. Density comes from CONTENT-SIZED fields that PACK (flex wrap — each width class is a sensible width for its data; a row holds as many fields as fit), never from proportional 12-column spans stretched across the viewport. The mockups' span numbers indicate relative field widths and grouping, not a fixed grid.
2. **Schema fields are candidates, not requirements.** When the entity schema exposes fields not present in the approved mockup, do NOT add them to the form. List them in your report as "unplaced schema fields" and stop for a placement/exclusion decision. Every field on a form must be either assigned to a mockup group or explicitly excluded in the spec.
3. **No system-managed fields on forms.** Timestamps, computed fields, and workflow metadata (e.g., Applicant Since Timestamp) are never hand-editable.
4. **Time fields use the half-hour picker standard** (prompt v0.1). Never a raw time/minute input.
5. **A maximum of ~4 input fields per row.** Never stretch a single row of many fields across the container.

### Company form — corrected structure

Groups in order, per mockup v3:

**1. Identity**
- Row: Company name (span 6) | Phone number (3) | Email address (3)
- Row: Organization type (3) | Business stage (3) | Industry (3) | SIC code (3)
- Row: Industry sector (6) | Industry subsector (6)

**2. Web presence**
- Row: Website (6) | LinkedIn page (6)

**3. Addresses** — billing and shipping side by side (two equal columns, ~36px gutter; stack below ~720px). Each uses the shared address block, which is **updated to include Country**:
- Row: Address line 1 (span 8) | Line 2 (4)
- Row: City (6) | State (2, select) | ZIP (4)
- Row: Country (6)

Shipping column header carries the "Same as billing" checkbox inline; when checked, shipping fields disable and dim. (Write behavior per the v0.1 investigation: flag vs. copied values — follow the schema.) Update the shared address block component once; the Contact form inherits Country automatically.

**4. Notes**
- Description (textarea, full width)
- Client notes (rich text with the existing B / I / bullet / numbered / Clear toolbar, full width)

### Field triage — explicit dispositions

**Kept and placed** (from the schema fields the previous build surfaced): Email address → Identity; SIC code → Identity; LinkedIn page → Web presence; Description → Notes; Client notes → Notes; Country → inside both address blocks.

**Excluded — remove from the form entirely:**
- Annual Pledge Amount Currency (sponsor field — removed per prompt v0.1 decision)
- Target Population (partner-organization field — same decision)
- Applicant Since Timestamp (system-managed; never hand-editable)
- Contact Role (contact-level attribute; does not belong on the company entity form)

Excluded means excluded from the mentor app's form only — the CRM fields remain untouched and other CRM workflows can still manage them.

If the schema contains additional Account fields beyond everything named above, apply standing rule 2: report them, don't place them.

### Acceptance criteria

1. Company edit form renders full-width with the four groups in mockup order; fields are content-sized and pack (v0.3 — the 960px criterion is reversed).
2. Field widths are sensible for their content (per the shared width classes); no field balloons across the viewport.
3. Country appears inside both billing and shipping address blocks; nothing address-related renders outside the blocks.
4. "Same as billing" disables and dims the shipping fields.
5. None of the four excluded fields appear anywhere on the form.
6. No raw time inputs anywhere; no system timestamps editable.
7. The shared address block change carries into the Contact form (Country row appears there too) with no other Contact form changes.
8. Save/Cancel behavior unchanged from prompt v0.1 (synchronous CRM write-through, inline error on failure).

### Report back

Before coding: confirm which component implements the shared address block and where the Company form width is currently set. After coding: files touched; any Account schema fields not named in this prompt (as unplaced candidates, not additions); any deviation from mockup v3 and why.
