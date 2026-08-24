# CGrant + CGrantDeliverable + CGrantReport — CRM build handoff

Written in **Entity Manager vocabulary** — "LEFT" means the entity whose
Relationships tab you are on. Plan: `prds/grant-management-plan.md` (rulings of
2026-08-23). Nothing here exists yet; this is a **from-scratch build**.

**Build on crm-test first**, verify, then repeat on production. The app
feature-detects every field, so it stays inert until the CRM has these.

---

## 0. What is being built and why

A funder awards a **grant**. The grant is the hub: it is tied to the money
(existing `CContribution` rows, which become its *payments*), to the
**deliverables** CBM promised in return, and to the periodic **reports** sent to
the funder to keep the funding coming. Deliverables and contributions are
**siblings under the grant, never a chain** — a deliverable that runs the whole
grant year has no single payment to hang off, and a grant paid in four tranches
has no single deliverable to hang each payment off.

Three new entities, **six links**, one role change.

> **Two fields added 2026-08-23 while the app side was being built**:
> `CGrantDeliverable.currentValue` and `.currentNote`. Manual measurement needs
> somewhere to record progress *before* the reporting engine exists, and without
> them a deliverable can state a target but never show how it is doing. Both are
> in the table below. Also changed: `deliverableStatus` and `nextReportDue`
> should stay **editable** rather than read-only — see their rows.

---

## 1. `CGrant` — the award

Administration → Entity Manager → **Create Entity**.

- **Name:** `CGrant`  ·  **Label:** `Grant`  ·  **Plural:** `Grants`
- **Type:** `BasePlus` (gives `assignedUser`, `teams`, `description`)
- Disable **Stream** unless you want grant edits in the stream (the app writes
  its own history via `CActionLog`).

Fields:

| Name | Type | Notes |
|---|---|---|
| `name` | varchar | **Required.** The grant's title as the funder calls it |
| `awardNumber` | varchar | The funder's own reference, if they issue one |
| `grantStatus` | enum | **Required.** `Applied` · `Awarded` · `Active` · `Reporting` · `Closed` · `Declined` · `Cancelled`. Default `Applied` |
| `awardAmount` | currency | EspoCRM adds `awardAmountCurrency` automatically — **a save that sets an amount must also set the currency or the CRM 400s the whole write** (this bit the Contributions ledger once) |
| `periodStart` | date | Start of the period of performance |
| `periodEnd` | date | End of it |
| `programArea` | varchar | What the grant funds. Left as free text deliberately — make it an enum once CBM's own list settles |
| `reportingFrequency` | enum | `Monthly` · `Quarterly` · `Semi-annual` · `Annual` · `Final only` · `Ad hoc` |
| `firstReportDue` | date | Seeds the report schedule |
| `nextReportDue` | date | **Leave it editable for now.** The report engine takes it over later; until then the app seeds it from `firstReportDue` and staff may correct it. (Entity Manager's Read-only is a UI setting only and never blocks an API write, so it can be locked down later with no code change) |
| `renewalDeadline` | date | When the next application is due — "in order to continue receiving grants". Replaces the inert `CContribution.nextGrantDeadline` |
| `notes` | wysiwyg | |

`description` and `assignedUser` come with BasePlus — no need to add them.

## 2. `CGrantDeliverable` — one promise, with a type and a target

- **Name:** `CGrantDeliverable` · **Label:** `Grant Deliverable` · **Plural:** `Grant Deliverables`
- **Type:** `BasePlus` (`assignedUser` is the *responsible individual* every
  grant-management product has)

| Name | Type | Notes |
|---|---|---|
| `name` | varchar | **Required.** As the funder worded it — "10 seminars" |
| `deliverableType` | enum | **Required.** `Numeric` · `Rate` · `Percentage` · `Milestone` · `Narrative` |
| `targetValue` | float | 10 seminars; 25 hours; 4.0 average rating |
| `unit` | varchar | `seminars` · `hours` · `clients` — shown after the number |
| `ratingScaleMax` | float | `Rate` only. Default `5` |
| `measurementSource` | enum | `Automatic` · `Manual`. Default `Manual` |
| `measureKey` | varchar | Which measure computes it — `events.held`, `sessions.hours`, `rating.sessions.avg`, or `analytics:<metric key>`. Ignored when Manual |
| `measurementNotes` | text | How this deliverable is measured, as a standing description |
| `currentValue` | float | **Progress to date.** Typed in today; computed from `measureKey` once the measures are wired |
| `currentNote` | text | Where the current figure came from — what makes a typed-in number defensible a year later |
| `dueBy` | date | `Milestone` only |
| `deliverableStatus` | enum | `On track` · `At risk` · `Behind` · `Met` · `Not met`. **Leave it editable** — the app derives a status from the numbers but staff must be able to override it, which is the whole point of the manual phase |
| `sortOrder` | int | The order the funder listed them in |

## 3. `CGrantReport` — one reporting period, and what was sent

- **Name:** `CGrantReport` · **Label:** `Grant Report` · **Plural:** `Grant Reports`
- **Type:** `BasePlus`

| Name | Type | Notes |
|---|---|---|
| `name` | varchar | **Required.** e.g. "Q2 2026 report" |
| `periodStart` | date | |
| `periodEnd` | date | |
| `dueDate` | date | Overdue is derived from this, never stored |
| `reportStatus` | enum | `Due` · `Draft` · `Submitted` · `Accepted`. Default `Due` |
| `submittedDate` | date | |
| `narrative` | wysiwyg | The prose half of the report |
| `results` | text | **The frozen numbers, as JSON.** Doug's ruling 2026-08-23: a period's per-deliverable figures are a snapshot on the report, not their own entity. Written once at submission and never recomputed — it is what CBM told the funder. Do not hand-edit it |
| `gmailThreadId` | varchar | The thread the report was sent on |
| `documentUrl` | url | The filed copy in Drive |

---

## 4. The six links

The Create Link dialog has a **Name** box on the LEFT panel *and* another on the
RIGHT panel, and likewise two **Label** boxes. **The dialog inverts what you
type**: a panel's Name defines the link that *points at that panel's entity*, so
it is stored on the **other** side. The values below are already in the correct —
i.e. inverted-looking — boxes. Do not compress them into a table; putting the two
Names in the wrong boxes is how this CRM ended up with reversed links four times.

After each one: Administration → **Clear Cache** → **Rebuild**.

### 4.1 Grant → Funder

1. Entity Manager → **Grant** → **Relationships** → **+ Create Link**.
2. Confirm the fixed LEFT panel header reads **Grant**.
3. **Relationship Type:** `Many-to-One` (LEFT is the Many — many grants, one funder).
4. **RIGHT panel Entity:** `Sponsor Profile` (`CSponsorProfile`).
5. **LEFT panel Name:** `grants`   **LEFT panel Label:** `Grants`
6. **RIGHT panel Name:** `sponsorProfile`   **RIGHT panel Label:** `Funder`
7. Save.

**Verify by outcome:** a **Grant** record shows a **Funder** field; a **Sponsor
Profile** shows a **Grants** panel.

### 4.2 Grant Deliverable → Grant

1. Entity Manager → **Grant Deliverable** → Relationships → + Create Link.
2. LEFT panel header must read **Grant Deliverable**.
3. **Type:** `Many-to-One`.
4. **RIGHT panel Entity:** `Grant`.
5. **LEFT panel Name:** `deliverables`   **Label:** `Deliverables`
6. **RIGHT panel Name:** `grant`   **Label:** `Grant`

**Verify:** a Grant shows a **Deliverables** panel; a Grant Deliverable shows a
**Grant** field.

### 4.3 Grant Report → Grant

1. Entity Manager → **Grant Report** → Relationships → + Create Link.
2. LEFT panel header must read **Grant Report**.
3. **Type:** `Many-to-One`.
4. **RIGHT panel Entity:** `Grant`.
5. **LEFT panel Name:** `reports`   **Label:** `Reports`
6. **RIGHT panel Name:** `grant`   **Label:** `Grant`

### 4.4 Contribution → Grant  *(this is what makes payments part of the grant)*

1. Entity Manager → **Contribution** → Relationships → + Create Link.
2. LEFT panel header must read **Contribution**.
3. **Type:** `Many-to-One` (a grant may be paid in tranches).
4. **RIGHT panel Entity:** `Grant`.
5. **LEFT panel Name:** `payments`   **Label:** `Payments`
6. **RIGHT panel Name:** `grant`   **Label:** `Grant`

**Nothing about the existing ledger changes.** A grant payment stays an ordinary
`CContribution` row and keeps counting in the Contributions tab's tiles exactly
as it does today; the link only says which grant it belongs to.

### 4.5 Grant ↔ Engagement  *(the funded clients)*

Doug's ruling 2026-08-23: attribution lives on the **grant**, not the funder, so
a client belongs to *this year's* grant and a renewal starts clean.

1. Entity Manager → **Grant** → Relationships → + Create Link.
2. LEFT panel header must read **Grant**.
3. **Type:** `Many-to-Many` (a grant funds many clients; a client may be funded
   by more than one grant over time).
4. **RIGHT panel Entity:** `Engagement` (`CEngagement`).
5. **LEFT panel Name:** `fundingGrants`   **Label:** `Funding Grants`
6. **RIGHT panel Name:** `fundedEngagements`   **Label:** `Funded Clients`

**Verify:** a Grant shows a **Funded Clients** panel; an Engagement shows
**Funding Grants**. This link is what `sessions.hours`, `sessions.count` and
`clients.served` count over — get it backwards and those three measure nothing.

### 4.6 Grant → Mentor Profile  *(the grant manager)*

1. Entity Manager → **Grant** → Relationships → + Create Link.
2. **Type:** `Many-to-One`.
3. **RIGHT panel Entity:** `Mentor Profile` (`CMentorProfile`).
4. **LEFT panel Name:** `managedGrants`   **Label:** `Managed Grants`
5. **RIGHT panel Name:** `grantManager`   **Label:** `Grant Manager`

### 4.7 *(Phase 5, build only if convenient)* Grant → Grant, the renewal chain

Self-referencing, so both links land on Grant. LEFT and RIGHT are both **Grant**;
Type `Many-to-One`; **LEFT panel Name:** `renewals` / **Label:** `Renewals`;
**RIGHT panel Name:** `renewalOf` / **Label:** `Renewal Of`.

---

## 5. Verify the links before moving on

Reading the labels in the UI is the quick check; the authoritative one is the
metadata. `GET /Metadata` and confirm, under `entityDefs`:

- `CGrant.links` contains `sponsorProfile` (belongsTo), `deliverables` (hasMany),
  `reports` (hasMany), `payments` (hasMany), `fundedEngagements` (hasMany),
  `grantManager` (belongsTo)
- `CSponsorProfile.links.grants`, `CContribution.links.grant`,
  `CEngagement.links.fundingGrants`, `CMentorProfile.links.managedGrants`

If a link sits on the wrong side, remove the row (▾ at its far right → Remove,
which deletes **both** sides) and redo it. Removing a relationship is
metadata-only — the column and any data in it survive, and a recreate under the
**same name** re-adopts them. A **mis-named** recreate is the trap: it strands
the data in the old column and looks exactly like data loss.

## 6. Role grants — Sponsor Management Team (Doug's ruling 2026-08-23)

On the role attached to the **Sponsor Management Team**, for all three new
entities:

| | Create | Read | Edit | Delete | Stream |
|---|---|---|---|---|---|
| `CGrant` | ✅ | **All** | ✅ | ❌ | — |
| `CGrantDeliverable` | ✅ | **All** | ✅ | ❌ | — |
| `CGrantReport` | ✅ | **All** | ✅ | ❌ | — |

**No delete anywhere**, matching the Contributions decision — a grant that falls
through is `Declined`/`Cancelled`, not a deleted row. Remember that a role only
reaches a user through **team attachment**: check Users → Access on a real
non-admin member afterwards, because an admin account passes regardless and
proves nothing.

## 7. One thing that needs no CRM work at all

**`CEvent.sponsorProfiles` already exists** (many-to-many CEvent ↔
CSponsorProfile) and is exposed nowhere in the app. That link is how a seminar
gets attributed to a funder, which is what the `events.held` measure counts.
Exposing it is an app change, not a CRM one.
