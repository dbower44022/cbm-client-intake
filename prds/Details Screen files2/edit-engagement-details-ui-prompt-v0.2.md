# Claude Code Prompt — Engagement Details UI Redesign

| Revision Control | |
|---|---|
| Version | 0.2 |
| Last Updated | 07-10-26 05:34 |
| Author | Doug Bower (via Claude) |
| Status | Approved layout (mockup v4) |

**Change Log**

| Version | Date | Change |
|---|---|---|
| 0.1 | 07-10-26 04:27 | Initial draft — per-panel edit, directory-style summaries |
| 0.2 | 07-10-26 05:34 | Full layout revision after v0.32.12 review: single-column cards with two-column internal rows, engagement summary strip, merged contact grids (Client + CBM), Add contact flow |

---

## Prompt

Operating mode: DETAIL. Make minimal, surgical changes. Preserve all existing routing, data fetching, and the Overview / Sessions / Communications / Documents tabs. Ask before removing any existing functionality.

### Context

The current implementation (v0.32.12) of the Engagement Details tab renders each section as a full-width panel containing prose sentences and loose two-column text. It is hard to scan and wastes space. This prompt replaces that layout. The accompanying file `engagement-details-mockup-v4.html` is the **design target** — open it in a browser before writing any code; it is authoritative for layout, density, and component behavior. Where this prompt and the mockup conflict, the mockup wins.

### Target layout (top to bottom, single column)

1. **Engagement summary strip** (replaces the Engagement panel)
2. **Company** card
3. **Client Business Profile** card
4. **Client Contacts** card — all client contacts in one table
5. **CBM Contacts** card — mentor/staff contacts in one table

### 1. Engagement summary strip

Not a card. A slim horizontal bar directly under the tab row: light gray background, cells separated by hairline dividers. Each cell: small uppercase muted label above a bold value. Cells: Status (navy pill) | Started | Mentor | Cadence | Sessions to date, then an Edit button right-aligned. Pull the actual field list from the engagement schema — the mockup's cells are illustrative; include every engagement-entity field that carries information, but keep the strip to one row (wrap on narrow widths).

### 2 & 3. Company and Client Business Profile cards

Full-width cards. Card header: title left, Edit button right, light gray header band. Card body: a **two-column row grid** — rows flow into left and right halves with a wide gutter (~44px), collapsing to one column below ~900px viewport width.

Each row: fixed-width (~122px) small uppercase muted label on the left, value on the right, hairline top border between rows. Values compose related fields with bold emphasis and light separators, exactly as in the mockup:

- Company left column: directory block first (company name in navy bold, billing address lines, phone · website link), then Business row (org type | stage | industry sector) and Shipping row (only when shipping differs from billing). Right column: Account (type + status), Cadence, Announcements (red "Not allowed" badge when disallowed).
- Client Business Profile left column: Entity (legal entity + formation date), Revenue (range | trend | profitability), Sells (customer type | channels | market reach), On file (EIN, Google Business Profile — list only what is true). Right column: Certifications (chip row), Funding to date (chip row), Client goal (the client's description, italic, quoted).

Empty / "No" / false fields are **omitted** from view mode, except operationally meaningful negatives (Public Announcement not allowed; agreement flags — see contacts).

### 4. Client Contacts card (true grid)

One card containing **all** client contacts as a table:

- Header: "Client Contacts (N)" with count, and a **+ Add** button (see Add flow below).
- Table columns: Name | Role | Phone | Email | City | Contact via | Agreements | Edit.
- Name: salutation in muted regular weight, name in navy bold.
- Role: chip badge (Client, Co-owner, etc.) — use the contact-type/role field from the schema.
- Contact via: the preferred contact method.
- Agreements: single status badge summarizing privacy policy + terms of use + code of conduct — green "Complete" when all accepted, red "N pending" otherwise. Do not render three separate sentences.
- Edit: per-row Edit action opening the contact edit form (see Editing below).
- Empty cells render empty — no "—", no "No".
- Row hover highlight. Table header row: small uppercase muted labels on a near-white band.

### 5. CBM Contacts card

Same table pattern for CBM-side people on the engagement (mentor, program manager, etc.). Columns: Name | Role | Phone | Email | Contact via | Edit — no City, no Agreements column (staff do not carry client acceptance flags; if the schema says otherwise, include the column and tell me).

**Investigate first:** determine how CBM staff/mentor contacts relate to an engagement in the CRM schema. The assigned mentor is presumably a direct relation on the engagement; other staff may come from a different relation or entity type. Report what you find in the schema before building this card, and build from the real relation — do not invent a parallel data model (replacement-workflow rule: modules write directly to CRM entities).

### Editing model

- No page-global Edit / Save changes / Cancel bar anywhere on the tab.
- Engagement strip, Company card, and Client Business Profile card each have one Edit button opening an edit form scoped to that section (inline expansion or modal — follow the codebase's existing form pattern).
- Contacts edit per-row: the row's Edit opens the full contact form.
- Save writes through to the CRM synchronously per existing write semantics; on failure, keep the form open and show the error inline. Cancel discards with no side effects.
- Edit forms remain full field-level forms — the composed-summary treatment applies to view mode only.

### Add contact flow

The + Add button on both contacts cards opens a two-option menu:

1. **Select existing contact…** — search/picker over existing CRM contacts; selecting one links it to this engagement's company (client side) or engagement (CBM side) via the appropriate CRM relation.
2. **Create new contact…** — opens the contact create form; on save, creates the contact in the CRM and links it in the same operation (compound write: idempotent, halt-on-failure, same-key retry per existing write semantics).

Use the CRM's real relation for the link in each case — investigate which relation attaches a contact to the account vs. to the engagement, and report before implementing.

### Visual system (from mockup v4)

- Base font ~13.5px; card titles 14px bold; row labels 11px uppercase letter-spaced muted gray.
- Existing navy/gold palette; hairline borders `#dfe3e8`; row separators `#f0f2f4`; light gray header bands `#f4f6f8`.
- Badges: warn (red on light red) for pending/not-allowed; ok (green on light green) for complete; neutral chips for roles, certifications, funding.
- Tight vertical rhythm — row padding ~4px, table cell padding ~8px 14px.

### Acceptance criteria

1. Details tab renders: engagement strip, Company card, Client Business Profile card, Client Contacts card, CBM Contacts card — in that order, single column.
2. No page-global Edit/Save/Cancel bar remains; each section edits independently and per-contact editing works from table rows.
3. Company and Profile cards use the two-column labeled row grid; no prose sentences, no one-cell-per-field grids.
4. All client contacts appear in one table matching the column spec; agreements collapse to one status badge per contact.
5. CBM Contacts card populates from the real CRM relation (documented in your report).
6. + Add on both contact cards supports select-existing and create-new, with the CRM link written correctly.
7. Empty/false fields hidden in view mode except meaningful negatives (announcements, pending agreements).
8. Layout collapses gracefully below ~900px (rows to one column; tables scroll or stack per existing responsive pattern).

### Report back

Before coding: the CBM-contact and contact-linking relations found in the schema. After coding: files touched, any deviations from the mockup and why.
