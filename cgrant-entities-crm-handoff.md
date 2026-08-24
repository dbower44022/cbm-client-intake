# CGrant + CGrantDeliverable + CGrantReport — CRM build handoff

Step-by-step build instructions for EspoCRM's Entity Manager. Plan:
`prds/grant-management-plan.md` (Doug's rulings 2026-08-23).

**Everything in this document was verified against the running crm-test
instance on 2026-08-23** — the dialog layout from
`client/res/templates/admin/link-manager/modals/edit.tpl`, the naming rules from
`Tools/EntityManager/NameUtil.php` and `Tools/LinkManager/LinkManager.php`, the
valid link types from `Tools/LinkManager/Type.php`, and the field types from
`Resources/metadata/fields/`. Earlier versions of this file were written from
memory and were wrong. Where a statement here comes from source, it says so.

> **§9 is a script that does this whole build through the API in one command.**
> The API has no dialog and no inverted boxes, so if you would rather not hand-
> build 24 fields and 6 links, skip to it. The instructions below are the manual
> path, and both produce exactly the same schema.

---

## 0. READ THIS FIRST — the three entities on crm-test are named wrong

The entities created on crm-test are **`CCGrant`, `CCGrantDeliverable` and
`CCGrantReport`** — with a double C. Read live from
`custom/Espo/Custom/Resources/metadata/entityDefs/` on 2026-08-23.

That is my fault: the previous version of this file said *"Name: `CGrant`"*.
**EspoCRM adds the `C` itself.** From `NameUtil::addCustomPrefix()`:

```php
$prefix = $ucFirst ? 'C' : 'c';
return $prefix . ucfirst($name);
```

and `EntityManager::create()` calls it unconditionally on every new entity
(`customPrefixDisabled` is `false` on this instance — checked). So typing
`CGrant` gives `CCGrant`; **typing `Grant` gives `CGrant`**, which is what the
application expects and what every existing entity here already follows
(`CEngagement`, `CSession`, `CContribution` were all created by typing the name
without the C).

**The fix is clean.** All three are bare `BasePlus` shells — stock fields only
(`name`, `description`, `createdAt`, `modifiedAt`, `createdBy`, `modifiedBy`,
`assignedUser`, `teams`), no custom fields, no custom links, no records. Delete
them and start again at §2. Nothing is lost.

## 1. The naming rules, once, so they stop biting

Three different rules, all verified in source. They are not the same rule, which
is why this keeps going wrong.

| What you are naming | Rule | Consequence here |
|---|---|---|
| **An entity** | **Always** gets `C` prepended (`EntityManager::create`) | Type `Grant`, get `CGrant` |
| **A field** | Prefixed **only if the entity is not custom** (`FieldManager::create`) | `CGrant` is custom ⇒ type `awardNumber`, get `awardNumber` |
| **A link** | `link` prefixed only if **this** entity isn't custom; `linkForeign` prefixed only if the **foreign** entity isn't custom, **or if there is no foreign entity** (`LinkManager` lines 162–168) | Every link in this build joins two custom entities ⇒ **no prefixing anywhere in §5** |

That last row is why the CRating build has a `cRatings` in it (Contact is a
system entity) and this one has nothing of the kind. Do not add a `C` to
anything below.

## 2. Delete the three mis-named entities

For each of `CCGrant`, `CCGrantDeliverable`, `CCGrantReport`:

1. Administration → **Entity Manager**.
2. Click the entity (it displays as **CGrant** / **CGrant Deliverable** /
   **CGrant Report** — the *label*, which is why this was easy to miss; the real
   name is on the row and in the URL).
3. Click **Remove** (bottom of the entity's detail view), confirm.

Then Administration → **Clear Cache**, then **Rebuild**.

## 3. Create the three entities

Administration → Entity Manager → **Create Entity**, once per row:

| Type box | Name box (**no C**) | Label Singular | Label Plural |
|---|---|---|---|
| `BasePlus` | `Grant` | `Grant` | `Grants` |
| `BasePlus` | `GrantDeliverable` | `Grant Deliverable` | `Grant Deliverables` |
| `BasePlus` | `GrantReport` | `Grant Report` | `Grant Reports` |

- **Type must be `BasePlus`**, not `Base` — BasePlus is what supplies
  `assignedUser`, `teams` and `description`, all three of which this build uses.
- Leave **Stream** off. The application writes its own history through
  `CActionLog`; a stream here would duplicate it.
- Everything else on the dialog stays at its default.

Save each one, then **Clear Cache** → **Rebuild**.

Confirm before going on: the Entity Manager list must now show `CGrant`,
`CGrantDeliverable`, `CGrantReport` — **one C each**.

---

## 4. Fields

For every field: Administration → Entity Manager → click the entity → **Fields**
→ **Add Field** → pick the type → fill the boxes named below → **Save**.
Anything not named below stays at its default (no Required, no Read-only, no
Audited, no tooltip, no default value).

`name` and `description` already exist on all three entities — they come with
BasePlus. Do not re-create them.

### 4.1 `CGrant` — 11 fields

**1. `awardNumber`** — type **Varchar**
- Name: `awardNumber` · Label: `Award number` · Max Length: `50`
- The funder's own reference for the award, when they issue one.

**2. `grantStatus`** — type **Enum**
- Name: `grantStatus` · Label: `Status`
- Options, one per line, in this order:
  `Applied`, `Awarded`, `Active`, `Reporting`, `Closed`, `Declined`, `Cancelled`
- Default: `Applied` · **Required: ✔**
- `Declined` and `Cancelled` are the soft delete — a grant that falls through
  keeps its record and stops counting. There is no delete anywhere in this app.

**3. `awardAmount`** — type **Currency**
- Name: `awardAmount` · Label: `Award amount`
- EspoCRM creates `awardAmountCurrency` alongside it automatically. Do not
  create that yourself, and do not delete it: EspoCRM validates the amount
  against it, and a bare amount on a record whose currency is null is rejected
  outright. That defect cost the contributions ledger a live 400 in v0.123.2;
  the app now always sends both.

**4. `periodStart`** — type **Date** · Name: `periodStart` · Label: `Period start`

**5. `periodEnd`** — type **Date** · Name: `periodEnd` · Label: `Period end`

**6. `programArea`** — type **Varchar**
- Name: `programArea` · Label: `Programme area` · Max Length: `100`
- Free text on purpose — make it an enum later, once CBM's own list settles.

**7. `reportingFrequency`** — type **Enum**
- Name: `reportingFrequency` · Label: `Reporting frequency`
- Options: `Monthly`, `Quarterly`, `Semi-annual`, `Annual`, `Final only`, `Ad hoc`
- No default, not required.

**8. `firstReportDue`** — type **Date** · Name: `firstReportDue` · Label: `First report due`

**9. `nextReportDue`** — type **Date** · Name: `nextReportDue` · Label: `Next report due`
- **Leave it editable** (do NOT tick Read-only). The app seeds it from
  `firstReportDue` once and never overwrites a value someone typed; the
  reporting engine takes it over in a later phase, and it can be locked down
  then with no code change.

**10. `renewalDeadline`** — type **Date** · Name: `renewalDeadline` · Label: `Renewal deadline`
- When the next application is due. This is the field that keeps the funding
  continuous, and it replaces the inert `CContribution.nextGrantDeadline`.

**11. `notes`** — type **Wysiwyg** · Name: `notes` · Label: `Notes`

### 4.2 `CGrantDeliverable` — 12 fields

**1. `deliverableType`** — type **Enum**
- Name: `deliverableType` · Label: `Type`
- Options: `Numeric`, `Rate`, `Percentage`, `Milestone`, `Narrative`
- Default: `Numeric` · **Required: ✔**
- This drives the progress arithmetic: `Numeric`/`Percentage`/`Rate` divide
  current by target, `Milestone` is binary, and `Narrative` has **no**
  percentage at all — a written answer is not a quantity.

**2. `targetValue`** — type **Float** · Name: `targetValue` · Label: `Target`
- 10 seminars; 25 hours; a 4.0 average rating.

**3. `unit`** — type **Varchar** · Name: `unit` · Label: `Unit` · Max Length: `50`
- `seminars` · `hours` · `clients`. Rendered after the number.

**4. `ratingScaleMax`** — type **Float** · Name: `ratingScaleMax` · Label: `Rating scale max`
- Default: `5`. Only shown for a `Rate` deliverable.

**5. `currentValue`** — type **Float** · Name: `currentValue` · Label: `Progress to date`
- Typed in today; computed from `measureKey` once the measures are wired.

**6. `currentNote`** — type **Text** · Name: `currentNote` · Label: `Progress note`
- Where the current figure came from. This is what makes a typed-in number
  defensible to a funder a year later.

**7. `dueBy`** — type **Date** · Name: `dueBy` · Label: `Due by`
- Past this date and short of target, the app reads the deliverable as *Behind*.

**8. `deliverableStatus`** — type **Enum**
- Name: `deliverableStatus` · Label: `Status`
- Options: `On track`, `At risk`, `Behind`, `Met`, `Not met`
- No default. **Leave it editable** (do NOT tick Read-only): the app derives a
  status from the numbers, but a stored value always wins, and staff being able
  to override the arithmetic is the entire point of the manual phase.

**9. `measurementSource`** — type **Enum**
- Name: `measurementSource` · Label: `Measured` · Options: `Automatic`, `Manual`
- Default: `Manual`.

**10. `measureKey`** — type **Varchar** · Name: `measureKey` · Label: `Measure` · Max Length: `100`
- Which measure computes this: `events.held`, `sessions.hours`,
  `rating.sessions.avg`, or `analytics:<metric key>`. Collected now, computed in
  a later phase; ignored while the source is Manual.

**11. `measurementNotes`** — type **Text** · Name: `measurementNotes` · Label: `How it is measured`
- The standing description of the method, as opposed to `currentNote`, which is
  about one reading.

**12. `sortOrder`** — type **Int** · Name: `sortOrder` · Label: `Order`
- The order the funder listed the deliverables in. The app sorts on this, then
  on creation date.

### 4.3 `CGrantReport` — 9 fields

**1. `periodStart`** — type **Date** · Name: `periodStart` · Label: `Period start`

**2. `periodEnd`** — type **Date** · Name: `periodEnd` · Label: `Period end`

**3. `dueDate`** — type **Date** · Name: `dueDate` · Label: `Due date`
- Overdue is derived from this and never stored.

**4. `reportStatus`** — type **Enum**
- Name: `reportStatus` · Label: `Status`
- Options: `Due`, `Draft`, `Submitted`, `Accepted` · Default: `Due`

**5. `submittedDate`** — type **Date** · Name: `submittedDate` · Label: `Submitted`

**6. `narrative`** — type **Wysiwyg** · Name: `narrative` · Label: `Narrative`

**7. `results`** — type **Text** · Name: `results` · Label: `Results (JSON)`
- **The frozen numbers.** Doug's ruling 2026-08-23: a period's per-deliverable
  figures are a snapshot on the report rather than their own entity. Written
  once at submission and never recomputed — it is what CBM told the funder.
  **Do not hand-edit it.**

**8. `gmailThreadId`** — type **Varchar** · Name: `gmailThreadId` · Label: `Email thread` · Max Length: `100`

**9. `documentUrl`** — type **Url** · Name: `documentUrl` · Label: `Filed copy`

After all three entities: **Clear Cache** → **Rebuild**.

---

## 5. Links

### 5.1 What the dialog's boxes actually are

This is where I have been wrong repeatedly, so here it is from the dialog's own
template (`client/res/templates/admin/link-manager/modals/edit.tpl`), which lays
out three rows of three columns:

```
        LEFT COLUMN                MIDDLE              RIGHT COLUMN
row 1   entity  (fixed:          linkType            entityForeign
        the entity you                               (you pick)
        opened this from)
row 2   Name  → linkForeign      relationName        Name  → link
row 3   Label → labelForeign     (blank)             Label → label
```

So, in plain words — and this is the whole trap:

> **The Name box on the LEFT, under the entity you are working on, is
> `linkForeign` — the link that will be created on the OTHER entity.**
> **The Name box on the RIGHT, under the foreign entity you picked, is `link` —
> the link that will be created on the entity you are working on.**

Each panel's Name describes the link that *points at that panel's entity*, and a
link that points at something is stored on the other side. The tables below are
already filled in correctly, i.e. they will look inverted. Type them as written.

Every link below joins two custom entities, so **no name gets a `C` added**
(§1).

**The Foreign Entity dropdown lists LABELS, not entity names**, and several
here do not resemble their names (read from the CRM's own i18n, 2026-08-23):
`CSponsorProfile` is **"Sponsor"**, `CMentorProfile` is **"CBM Member"**,
`CEngagement` is "Engagement", `CContribution` is "Contribution". Each table
below names the label to pick and the entity it corresponds to.

### 5.2 Grant → Funder

Entity Manager → **CGrant** → **Relationships** → **Create Link**.
Confirm the left panel header reads **Grant** before typing anything.

| Box | Position | Value |
|---|---|---|
| Entity | left, row 1 | **Grant** (fixed — if it says anything else, close and start from CGrant) |
| Link Type | middle, row 1 | **Many-to-One** (many grants, one funder) |
| Foreign Entity | right, row 1 | **Sponsor** — that is how `CSponsorProfile` is labelled in this CRM (checked 2026-08-23). The app calls it "Funder"; the CRM dropdown says **Sponsor** |
| **Name** | **left**, row 2 | `grants` ← lands on CSponsorProfile |
| **Name** | **right**, row 2 | `sponsorProfile` ← lands on CGrant |
| Label | left, row 3 | `Grants` |
| Label | right, row 3 | `Funder` |

**Verify by outcome:** a **Grant** record shows a **Funder** field; a **Sponsor**
record shows a **Grants** panel. If they are the other way round, remove the
link and redo it with the two Names swapped.

### 5.3 Grant Deliverable → Grant

Entity Manager → **CGrantDeliverable** → Relationships → Create Link.

| Box | Position | Value |
|---|---|---|
| Entity | left | **Grant Deliverable** (fixed) |
| Link Type | middle | **Many-to-One** |
| Foreign Entity | right | **Grant** |
| **Name** | **left** | `deliverables` ← lands on CGrant |
| **Name** | **right** | `grant` ← lands on CGrantDeliverable |
| Label | left | `Deliverables` |
| Label | right | `Grant` |

**Verify:** a Grant shows a **Deliverables** panel; a Grant Deliverable shows a
**Grant** field.

### 5.4 Grant Report → Grant

Entity Manager → **CGrantReport** → Relationships → Create Link.

| Box | Position | Value |
|---|---|---|
| Entity | left | **Grant Report** (fixed) |
| Link Type | middle | **Many-to-One** |
| Foreign Entity | right | **Grant** |
| **Name** | **left** | `reports` ← lands on CGrant |
| **Name** | **right** | `grant` ← lands on CGrantReport |
| Label | left | `Reports` |
| Label | right | `Grant` |

**Verify:** a Grant shows a **Reports** panel; a Grant Report shows a **Grant** field.

### 5.5 Contribution → Grant  *(this is what makes payments part of the grant)*

Entity Manager → **CContribution** → Relationships → Create Link.

| Box | Position | Value |
|---|---|---|
| Entity | left | **Contribution** (fixed) |
| Link Type | middle | **Many-to-One** (a grant may be paid in tranches) |
| Foreign Entity | right | **Grant** |
| **Name** | **left** | `payments` ← lands on CGrant |
| **Name** | **right** | `grant` ← lands on CContribution |
| Label | left | `Payments` |
| Label | right | `Grant` |

**Nothing about the existing ledger changes.** A grant payment stays an ordinary
contribution row and keeps counting in the Contributions tab's tiles exactly as
today; this link only records which grant it belongs to.

**Verify:** a Grant shows a **Payments** panel; a Contribution shows a **Grant**
field.

### 5.6 Grant ↔ Engagement  *(the funded clients)*

Doug's ruling 2026-08-23: attribution lives on the **grant**, not the funder, so
a client belongs to *this year's* grant and a renewal starts clean.

Entity Manager → **CGrant** → Relationships → Create Link.

| Box | Position | Value |
|---|---|---|
| Entity | left | **Grant** (fixed) |
| Link Type | middle | **Many-to-Many** |
| Foreign Entity | right | **Engagement** (`CEngagement`) |
| **Name** | **left** | `fundingGrants` ← lands on CEngagement |
| Relationship Name | **middle**, row 2 | `grantEngagement` (appears only for Many-to-Many; it names the join table) |
| **Name** | **right** | `fundedEngagements` ← lands on CGrant |
| Label | left | `Funding Grants` |
| Label | right | `Funded Clients` |

**Verify:** a Grant shows a **Funded Clients** panel; an Engagement shows
**Funding Grants**. Get this one backwards and the `sessions.hours`,
`sessions.count` and `clients.served` measures count nothing at all.

### 5.7 Grant → Mentor Profile  *(the grant manager)*

Entity Manager → **CGrant** → Relationships → Create Link.

| Box | Position | Value |
|---|---|---|
| Entity | left | **Grant** (fixed) |
| Link Type | middle | **Many-to-One** |
| Foreign Entity | right | **CBM Member** — that is how `CMentorProfile` is labelled here (checked 2026-08-23), NOT "Mentor Profile" |
| **Name** | **left** | `managedGrants` ← lands on CMentorProfile |
| **Name** | **right** | `grantManager` ← lands on CGrant |
| Label | left | `Managed Grants` |
| Label | right | `Grant Manager` |

### 5.8 *(Optional, a later phase)* Grant → Grant, the renewal chain

Both sides are **Grant**, Type **Many-to-One**; left Name `renewals` / Label
`Renewals`; right Name `renewalOf` / Label `Renewal Of`. Skip it for now if you
would rather — nothing in the app reads it yet.

After the links: **Clear Cache** → **Rebuild**.

---

## 6. Verify the whole build

Reading labels in the UI catches a reversed link; the authoritative check is the
metadata. As an admin, `GET /api/v1/Metadata`, then confirm under `entityDefs`:

- `CGrant.links` has `sponsorProfile`, `deliverables`, `reports`, `payments`,
  `fundedEngagements`, `grantManager`
- `CGrant.fields` has all 11 from §4.1 **without a `c` prefix**
- `CSponsorProfile.links.grants`, `CContribution.links.grant`,
  `CEngagement.links.fundingGrants`, `CMentorProfile.links.managedGrants`
- `CGrantDeliverable.links.grant`, `CGrantReport.links.grant`

If a link is on the wrong side, remove the row (▾ at its far right → Remove,
which deletes **both** sides) and redo it. Removing a relationship is
metadata-only: the column and any data in it survive, and a recreate under the
**same name** re-adopts them. A **mis-named** recreate is the trap — it strands
the data in the old column and looks exactly like data loss.

The application also tells you where it stands: switch `GRANTS_ENABLED` on at
`/setup` and open a funder's **Grants** tab. It probes for `CGrant` and
`CGrantDeliverable` and either shows the grid or says the entities aren't built
yet — and every field is checked against live metadata before it is offered, so
a field that is missing or mis-named simply doesn't appear. Nothing breaks
while the build is half-done.

## 7. Role grants — Sponsor Management Team (Doug's ruling 2026-08-23)

On the role attached to the **Sponsor Management Team**:

| | Create | Read | Edit | Delete | Stream |
|---|---|---|---|---|---|
| `CGrant` | ✔ | **All** | ✔ | ✘ | — |
| `CGrantDeliverable` | ✔ | **All** | ✔ | ✘ | — |
| `CGrantReport` | ✔ | **All** | ✔ | ✘ | — |

**No delete anywhere**, matching the Contributions decision. A role only reaches
a user through **team attachment**, so check Users → Access on a real non-admin
member afterwards — an admin account passes regardless and proves nothing.

## 8. Then production

Repeat §3–§7 on prod, and diff the enum options between the two CRMs when you
are done. The two have drifted before, and the application reads its option
lists live from whichever CRM it is pointed at.

## 9. The script that does all of this

`scripts/migrate_grant_schema.py` performs §3, §4 and §5 through the admin API —
**no dialog, so no inverted boxes**. It is modelled on
`scripts/migrate_event_schema.py`, which built the event schema on crm-test in
July and is the reason the API contract here is known rather than guessed. In
the API the parameters are unambiguous: `link` is the link stored on `entity`
and `linkForeign` the one stored on `entityForeign`, with no inversion of any
kind.

It is **idempotent** (an entity, field or link that already exists is left
alone) and **dry-run by default**:

```bash
# show the plan, change nothing
PYTHONPATH=. ADMIN_BASE=https://crm-test.clevelandbusinessmentors.org \
  ADMIN_USER=... ADMIN_PASS=... uv run python scripts/migrate_grant_schema.py

# apply it
... uv run python scripts/migrate_grant_schema.py --apply
```

It will NOT delete the mis-named `CCGrant*` entities — deleting things is not
something a script should do on its own. Do §2 by hand first, then run this.

Role grants (§7) are not scriptable either; they stay a UI step.
