# Fix the grant entities on crm-test — do this next

A short, ordered runbook. Follow it top to bottom. The reference detail (every
field, every link) is `cgrant-entities-crm-handoff.md`; this file is the
sequence.

**Where things stand, read live from crm-test at 04:23 UTC on 2026-08-24:**

- Three entities exist and are **named wrong**: `CCGrant`,
  `CCGrantDeliverable`, `CCGrantReport` (double C — EspoCRM adds the `C`
  itself, and the old handoff told you to type `CGrant`).
- All three are **completely bare**: no custom fields, no custom links, and
  **zero records** — last night's reset truncated their tables at 04:00:01.
- Nothing else has been built: no fields, no links, no role grants.

So there is nothing to preserve. Delete and rebuild.

**One thing worth knowing before you start:** the nightly reset log shows it
truncates records but then *rebuilds the schema from the live custom metadata*.
**Entity, field and link definitions survive the nightly reset; records inside
them do not.** Build the schema whenever you like — but any test grant you
create tonight is gone by morning.

---

## Step 1 — Delete the three mis-named entities

Do this three times, once for `CCGrant`, `CCGrantDeliverable`, `CCGrantReport`.

1. Go to **Administration → Entity Manager**.
2. Find the row. **Look at the `Name` column, not the Label** — the Label reads
   "CGrant" while the real name is `CCGrant`, which is exactly what hid this.
   Type `grant` in the search box to narrow the list.
3. Click the entity's **Label** link (left-hand column) to open it.
4. On that page, next to the big **Edit** button there is a **dropdown
   (⋯ / caret)**. Open it and choose **Remove**. Confirm.
5. Repeat for the other two.

## Step 2 — Clear cache and rebuild

**Administration → Clear Cache**, then **Administration → Rebuild**.

## Step 3 — Checkpoint

Back in **Entity Manager**, search `grant`. **You should see nothing.** If any
`CCGrant*` row is still listed, repeat steps 1–2 before going further —
building on top of a half-deleted entity is how data gets stranded.

---

## Step 4 — Build the schema. Pick ONE path.

### Path A (recommended) — run the script

It creates all 3 entities, all 32 fields and all 6 links through the admin API.
**There is no dialog, so there are no inverted boxes** — which is the failure
this whole exercise keeps hitting.

1. Dry run first. From the repo root, with your EspoCRM admin login:

   ```bash
   PYTHONPATH=. \
   ADMIN_BASE=https://crm-test.clevelandbusinessmentors.org \
   ADMIN_USER='<your admin username>' \
   ADMIN_PASS='<your admin password>' \
   uv run python scripts/migrate_grant_schema.py
   ```

   It changes nothing and prints the plan. Expect **41 lines under CHANGES**
   (3 entities + 32 fields + 6 links) and **nothing under FAILED**.

2. If that looks right, run it again with `--apply` on the end.

3. It rebuilds and then **reads every link back** to confirm it landed on the
   side intended, printing `verified …` per link. Anything under **FAILED** at
   the end is real — send it to me rather than working around it.

Notes: the account must be **Type = Admin** (the script checks and refuses
otherwise); it is safe to re-run — anything already correct is skipped.

### Path B — build it by hand

Follow `cgrant-entities-crm-handoff.md` in order:

- **§3** creates the three entities. **Type `Grant`, not `CGrant`** — Espo adds
  the C. Type must be **BasePlus**.
- **§4** is every field, one numbered block each: 11 on CGrant, 12 on
  CGrantDeliverable, 9 on CGrantReport.
- **§5** is the six links. **Read §5.1 first** — it maps each box in the Create
  Link dialog, and the Name box on the left is the link that lands on the *other*
  entity. The tables are already filled in correctly, so they will look
  backwards. Type them as written.
- Watch two labels in the Foreign Entity dropdown: `CSponsorProfile` is listed
  as **"Sponsor"** and `CMentorProfile` as **"CBM Member"**.

Clear Cache → Rebuild when you are done.

---

## Step 5 — Role grants (both paths; not scriptable)

**Administration → Roles →** the role attached to the **Sponsor Management
Team**. For each of `CGrant`, `CGrantDeliverable`, `CGrantReport`:

- **Create:** yes · **Read:** **all** · **Edit:** yes · **Delete:** **no**

No delete on any of the three — a grant that falls through is `Declined` or
`Cancelled`. Save.

Then check it on a **real non-admin** member of that team (Users → the user →
Access). An admin passes regardless and proves nothing.

## Step 6 — Checkpoint

In **Entity Manager**, the `Name` column must read **`CGrant`**,
**`CGrantDeliverable`**, **`CGrantReport`** — one C each.

Open a **CGrant** record view: it should show a **Funder** field, a
**Deliverables** panel, a **Reports** panel, a **Payments** panel, a **Funded
Clients** panel and a **Grant Manager** field.

Open a **Sponsor** record: it should show a **Grants** panel.

If a panel is on the wrong side, remove that link (Relationships → the row's ▾
→ Remove, which deletes both halves) and redo it. Removing a relationship is
metadata-only, so no data is lost — but **recreate it under the same name**, or
the old column is stranded and it looks exactly like data loss.

## Step 7 — Turn the app on and look

1. Go to `/setup` on crm-test and switch **Grants on funder records**
   (`GRANTS_ENABLED`) **on**.
2. Open **Funder Management → any funder → the Grants tab.**
   - If the entities are right, you get the tiles and an empty grid.
   - If something is still missing, the tab says the entities aren't built yet
     rather than erroring — that is the app checking the CRM, and it is a useful
     signal, not a failure.
3. Create a grant and add one deliverable of each type. Remember tonight's reset
   will delete those records — that is fine, it is only a smoke test.

**Then tell me it's done and I'll verify the whole schema from the metadata
directly** — field names, link directions, both sides of every relationship —
which is a stronger check than reading labels in the UI, and it costs you
nothing.

## Step 8 — Production, afterwards

Same sequence on prod, minus step 1 (nothing is mis-named there — nothing exists
at all). Path A works against prod by changing `ADMIN_BASE`. Then diff the enum
options between the two CRMs: they have drifted before, and the app reads its
option lists live from whichever CRM it is pointed at.
