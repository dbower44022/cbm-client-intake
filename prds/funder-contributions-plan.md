# Funder Contributions — plan v0.1 (2026-07-20)

Approved plan from the 2026-07-20 solution-architecture session with Doug.
Scope: Funder Management (`/sponsorsessions`) gains a **Contributions** tab on
the funder record — enter contributions, see all future and past ones, with a
dashboard on top.

Status: **BUILT v0.115.0 (same day) — VERIFIED LIVE on crm-test 2026-07-21**
(create, edit, soft delete, tiles/rollups on real data). Two live-found
issues, both closed: (1) the crm-test sponsor role's CContribution **Create
grant was set wrong** (empty-body 403 on POST; read passed — diagnosed from
run logs + the Users → Access merged-ACL view); (2) **v0.123.2**: EspoCRM's
`validCurrency` rejects a bare `amount` on a record whose stored
`amountCurrency` is null — amount-setting saves now backfill the currency
(existing value, else USD). Mechanics: CHANGELOG 0.115.0 + 0.123.2; durable
reference: the "Contributions tab" bullet in CLAUDE.md's Session Management
section.

**Open for PROD use:** add the same role grants there (CContribution
create / read=All / edit, NO delete — attached to the sponsor team), and
eyeball prod's CContribution enum options against crm-test.

**Open design nuance (Doug to rule, from the 2026-07-21 Key Bank review):**
an *Applied* row with a future date gets the grid's "upcoming" tag but does
NOT count in the Scheduled tile (Pledged+Committed only) — reads as
contradictory side by side. Recommended fix: restrict the "upcoming" tag to
Pledged/Committed too (keep the tile a strict cash-flow number); alternative:
widen the tile to include Applied. One-line change either way.

## Verified facts (read live from crm-test metadata 2026-07-20)

The CRM entity **already exists on both CRMs** (built CRM-side; prod option
parity still to be eyeballed — the local prod API key is EV-encrypted, so it
was not probed):

- **`CContribution`** — `contributionType` (enum, REQUIRED: Donation /
  Sponsorship / Grant), `status` (enum, REQUIRED: Applied / Pledged /
  Committed / Received / Unsuccessful / Cancelled), `amount` (currency, with
  `amountCurrency`/`amountConverted` companions), dates: `applicationDate`,
  `commitmentDate`, `expectedPaymentDate`, `receivedDate`,
  `acknowledgmentDate`, `nextGrantDeadline`; `giftType` (enum: Cash / Check /
  Credit Card / ACH / Online Payment / In-Kind / Other), `inKindDescription`,
  `inKindValuationBasis`, `designation`, `acknowledgmentSent` (bool),
  `notes` (wysiwyg), `description` (text), `name` (varchar, REQUIRED).
- Links: `sponsorProfile` belongsTo CSponsorProfile (reverse
  **`sponsorContributions`** hasMany), `donorAccount` belongsTo Account
  (reverse `cContributions`), `donorContact` belongsTo Contact (reverse
  `cContributions`), `assignedUser`, `teams`.

## Doug's rulings (2026-07-20)

1. Dashboard + grid = a **new tab on the Funder View (record) page** —
   per-funder, not global.
2. **Future = effective date after today** (funders use scheduled funding;
   tracked for cash flow).
3. Field set = the as-built entity above (no CRM build needed).
4. **Totals count status = Received ONLY.**
5. Calculations are **on the fly, never stored** (e.g. 6-month / yearly
   aggregates).
6. **Soft delete = status Cancelled**; cancelled rows are excluded from every
   total (but stay visible for audit — dimmed with a tag).
7. **Effective date** = `receivedDate` → `expectedPaymentDate` →
   `commitmentDate` → `applicationDate` (first set wins). Drives ordering,
   future/past classification, and the time windows.
8. Tile window = **rolling 12 months** back from today (not calendar YTD).
9. **Four tiles** (see Dashboard below) — the Scheduled tile included.
10. Aggregation buckets = **rolling 6-month windows anchored at the LAST
    contribution**, not calendar halves. Design principle: CBM promotes
    CONTINUOUS contributions, so the tab reads recency-first — everything
    relative to the funder's most recent contribution; gaps must show.

## Design

### Tab

- `DomainConfig` gains per-domain **extra detail tabs**; the sponsor domain
  declares `{"key": "contributions", "label": "Contributions"}` (mentor /
  partner domains unchanged). Flows to the frontend via the existing
  `/session` → `detailTabs` payload.

### Endpoints (sponsor router only; all run as the signed-in user)

- `GET /sponsorsessions/api/records/{id}/contributions` — all rows via the
  `sponsorContributions` reverse link (paginated read, newest effective date
  first), plus a server-computed **`summary`** block (tiles + recency +
  period rollups; one tested place computes the business rules).
- `POST /sponsorsessions/api/records/{id}/contributions` — create; stamps
  `sponsorProfileId`; defaults `donorAccountId` from the funder's
  `sponsorCompanyId` and `donorContactId` from `sponsorContactId` (both
  overridable in the editor later if ever needed; hidden in v1).
- `GET /sponsorsessions/api/contributions/{cid}` / `PUT …/contributions/{cid}`
  — read / whitelisted diffed update (`CONTRIBUTION_FIELDS` whitelist, enum
  sanitize, `_crm_failure` 401/403 mapping). The PUT verifies the
  contribution belongs to a funder record the user can read (record-scoped,
  the documents-endpoint precedent).
- **No DELETE endpoint** — cancellation is an edit to status Cancelled.

### Dashboard (top of the tab)

Four stat tiles, all computed server-side from the fetched rows:

| Tile | Rule |
|------|------|
| Contributions | count, status=Received only |
| Total received | sum of `amount`, Received only |
| Last 12 months | Received sum, effective date within rolling 365 days |
| Scheduled (upcoming) | sum of **Pledged + Committed** rows with a FUTURE effective date (cash-flow view; Applied deliberately excluded — an application isn't scheduled money; Doug can widen later) |

Under the tiles, a one-line **recency callout** (the "relative to last
contribution" principle): "Last received: $X on DATE — N months ago", amber
when the gap exceeds 6 months, plus "Next expected: $Y on DATE" when a
future Pledged/Committed row exists. No data ⇒ "No contributions recorded."

### Grid

Sortable + column-resizable (`makeColumnsResizable`, the Sessions-tab
treatment): Contribution (name) · Type · Status · Amount · Expected ·
Received · Gift type · Acknowledged. Future-dated rows get the upcoming
visual treatment (the v0.62.0 precedent); Cancelled/Unsuccessful rows dimmed
with a tag; default sort = effective date, newest first.

### Period rollup ("Totals by period" toggle)

A small aggregate table over the loaded rows (client-side, on the fly):
**6-month windows walking BACK from the anchor** — anchor = the most recent
Received row's effective date (today when none). Each window shows range
label, count, Received total; **empty windows still render** ("—") so giving
gaps are visible — that's the point. A Yearly toggle uses 12-month windows
from the same anchor. Received only; Cancelled/Unsuccessful never counted.

### Editor

`CONTRIBUTION_FIELDS` in `sessions/config.py` (the SESSION_FIELDS pattern —
one spec drives the form layout AND the server-side whitelist; enum options
+ required flags read live from CRM metadata). Grouped panels:

1. **Contribution** — contributionType · status · amount · the date row
   (application / commitment / expected / received; `nextGrantDeadline` with
   them).
2. **Payment** — giftType · designation; the in-kind pair shown only when
   giftType = In-Kind (client-side show/hide, both always whitelisted).
3. **Acknowledgment** — acknowledgmentSent · acknowledgmentDate.
4. **Notes** — `notes` (CBMRichText, per the wysiwyg convention) ·
   `description` (plain).

`name` is CRM-required → editable auto-default "{YYYY-MM-DD} — {funder} 
{contributionType}" (the session-name pattern; user value wins).
Editor buttons follow [[buttons-never-disabled-validate-on-click]]; save
diffs against render snapshots; drifted enums sanitized server-side.

## CRM prerequisites (Doug)

1. The sponsor team's role: **CContribution enabled, create + read + edit**
   (Read = All, matching the 2026-07-20 CSponsorProfile decision; NO delete
   grant — soft delete only). Remember role reach = team attachment
   ([[espo-403-diagnosis-merged-team-roles]]).
2. Eyeball prod's CContribution enum options match crm-test (couldn't be
   probed locally).

## Verification

Unit tests for the summary math (effective-date chain, received-only,
cancelled exclusion, rolling windows incl. the empty-window case and the
anchor rule); stub-harness UI loop (tiles, recency line, grid flags, period
toggle, editor groups + in-kind show/hide, cancel-as-soft-delete); then live
on crm-test as a sponsor-team member: create → tiles update, future Pledged
row shows in Scheduled + upcoming flag, Cancel → drops out of totals but
stays visible, PUT smuggle-drop check.

## Out of scope (future candidates)

- Global contributions dashboard across all funders (the list page).
- Deriving the Overview's stored `totalContribution` / `lastContribution`
  facts from the live rows (or retiring those scalar fields) — open ruling.
- `donorAccount`/`donorContact` pickers in the editor (auto-stamped in v1).
- Acknowledgment-owed nudges (acknowledgmentSent=false on Received rows).
