# Mentor Administration

A staff-only tool in the CBM Intake app for reviewing and maintaining **mentor
records**, ensuring each one is complete and correct, and managing mentor
logins. It is **not** a public form.

- **URL:** `/mentoradmin/` (page title **"Mentor Administration"**).
- **Who can use it:** staff who sign in with their own EspoCRM username/password
  and belong to the **Mentor Administration Team** (admins always allowed).
- **What it edits:** the `CMentorProfile` record (the "CBM member" record) and,
  where noted, its linked `Contact` and login `User`.
- All reads and writes run as the **logged-in staff user** (EspoCRM enforces
  their permissions) — except login creation, which runs as a dedicated admin
  service account (see [Logins](#logins-on-save) below).

---

## The mentor roster (grid)

The landing screen lists every mentor. You can:

- **Search** by name, email, expertise, or focus area.
- **Filter** by mentoring status, **Record** (completeness) status, or mentor type.
- **Sort** by any column.

Columns: **Mentor · Mentor Email · Record · Status · Type · Created · Active
Clients · Max Clients · Available · Assigned (30d) · Lifetime**.
(Mentor Email is the CBM `@cbmentors.org` login address, set once a mentor is provisioned.)

The five client-count columns are computed live from the mentor's engagements:

- **Active Clients** — engagements whose status is *Active*, *Assigned*, or
  *Pending Acceptance*.
- **Max Clients** — the mentor's stored maximum client capacity (blank if not set).
- **Available** — Max Clients minus Active Clients (blank when no max is set;
  "Unlimited" when the max is unlimited).
- **Assigned (30d)** — active-set engagements assigned within the last 30 days
  (from the engagement's *assigned date*, which the Client Administration
  Assign action stamps).
- **Lifetime** — every engagement ever linked to the mentor, in any status.

If your EspoCRM account can't read engagements, these columns show "—" and the
count line under the toolbar says so — ask an administrator to grant your role
read access to Engagements.

The **Record** column shows each mentor's stored completeness status
(**Complete / Incomplete / Duplicate**, or "—" if not yet calculated). Use the
**Record** filter set to *Incomplete* to quickly see **which mentors need work**.
The Record value is refreshed whenever a mentor is **saved** (see
[Record Status](#record-status)).

Click a mentor's name to open their detail screen.

### "Update Mentor Status" (bulk verification)

The **Update Mentor Status** button on the roster toolbar sweeps **every**
mentor and opens a results table showing, per mentor:

- **Login user** — whether the linked EspoCRM login **User actually exists**
  and is active. It distinguishes ✓ exists (with the username), ✗ *no login
  User linked*, ✗ *linked User no longer exists* (deleted), and *exists but
  deactivated*. The User lookups run as the provisioning admin service account
  when configured (regular staff can't read Users); without it the result is
  "could not verify" rather than an error.
- **Mailbox** — whether the mentor's `@cbmentors.org` mailbox exists in
  **Google Workspace** (via the same Directory integration as approval-time
  checks). Shows *"n/a — check not configured"* until Google is connected in
  **Email Setup**; a mentor with no CBM email is flagged.
- **Record** — while sweeping, each mentor's completeness is recomputed and the
  stored **Record status is re-synced** (same rules as a save: written only
  when it changed, never over a manual *Duplicate*). The roster reloads
  afterward, so the whole grid self-heals in one click.

A mentor whose record fails to load shows an error row; the rest of the sweep
still completes.

---

## The mentor detail screen

**Summary card (read-only, top of the page).** At-a-glance facts that aren't
edited here: the **Data completeness** badge (see below), mentoring status,
accepting-new-clients, the mentor's email / phone / address, the **same five
client counts as the roster grid** (Active clients · Max clients · Available ·
Assigned (30d) · Lifetime clients — always shown, "—" when unknown), and the
session metrics.

- The **Data completeness** badge reads **Complete** (green) or **Incomplete**
  (red). **Click it** for a popup listing exactly what is missing or incorrect.

**Tabbed editor (below the card).** The editable fields, grouped into tabs:
**Status · Capacity · Expertise · Compliance · Departure · Profile · Bio**.
Inputs match the field type (dropdowns, checkboxes, dates, multi-select checkbox
grids, and a rich-text editor for the biography fields).

**Saving.** Only fields you actually changed are sent. Before saving, the app
runs the completeness check and — if the record will still be incomplete —
shows a confirmation popup (see [Saving](#saving-a-record)).

---

## Complete-record requirements

A mentor record is **Complete** only when **all** of the applicable conditions
below are met; otherwise it is **Incomplete** and the badge popup lists the
specific reasons.

### Always required

| Requirement | Field |
|---|---|
| A linked **Contact** record | `contactRecord` |
| **Ethics agreement** accepted | `ethicsAgreementAccepted` = true |
| **Training** completed | `trainingCompleted` = true |
| **Terms** accepted | `termsAccepted` = true |

(**Background check** is optional — it is *not* required for completeness. **Public
profile** does not affect completeness either.)

### Additionally, if the mentor's status is **Active**

| Requirement | Field |
|---|---|
| A **CBM email address** is set | `cbmEmail` |
| A login **User** is assigned to the mentor (the CBM member record) | `assignedUser` |
| The **same User** is assigned to the mentor's **Contact** | `Contact.assignedUser` |

---

## Saving a record

When you press **Save**:

1. **Pre-save check.** If the record will still be incomplete, a popup lists what
   needs attention and asks **"Save anyway?"**
   - **Cancel** → nothing is saved; you stay in edit mode.
   - **Save anyway** → the save proceeds.
   - (The popup does *not* warn about missing logins/User assignments — the save
     creates and assigns those automatically; see below.)
2. **The edited fields are written** to the mentor record.
3. <a id="logins-on-save"></a>**Login provisioning (with a live status window).**
   If the mentor's status is **Approved or Active** and they have **no login
   yet**, saving opens a **status window** that narrates each step and provisions
   their access. The CBM email `firstname.lastname@cbmentors.org` is filled in
   automatically (reusing `cbmEmail` if already set). Then, depending on the
   Google Workspace configuration:
   - **Mailbox check (when enabled).** The app checks whether that mailbox exists.
   - **Mailbox creation (when enabled).** If the mailbox is **missing**, the app
     **creates** it in Google Workspace (a temporary password the mentor changes
     at first sign-in; their personal email is set as the Google **recovery
     email**), waits for it to become active, and shows the temp password in the
     status window to relay to the mentor. *If creation is off*, a missing mailbox
     instead **blocks** with *"the Google Workspace mailbox … does not exist —
     create it before approving"*. If the check can't run, provisioning proceeds.
   - **EspoCRM login.** Finally the app creates an EspoCRM **User**, places it in
     the **Mentor Team**, assigns it to the mentor record, and emails the welcome /
     set-password link to the new CBM mailbox.
   - The Google connection is configured in the admin-only **Email Setup** screen
     (top of the list view) — service-account key, delegated admin, and the
     check / create toggles, with a **Test connection** button.
4. **User reconciliation.** The mentor's User is assigned to **both** the member
   record and its **Contact** (filling any one-sided assignment).
5. <a id="record-status"></a>**Record Status persisted.** The freshly computed
   completeness result is written to the **`recordStatus`** field
   (`Complete` / `Incomplete`), so the roster grid shows it.

Steps 3–5 are best-effort: if one can't complete (e.g. a missing permission), the
save still succeeds and the reason is shown.

---

## Record Status

`CMentorProfile.recordStatus` is an enum with values **Incomplete**, **Complete**,
and **Duplicate**:

- **Complete / Incomplete** are written automatically on save from the
  completeness check.
- **Duplicate** is a **manual** designation (set in EspoCRM) and is **never
  overwritten** by the app.

The grid's **Record** column and filter read this stored value, so it is current
for any mentor that has been saved since the field was introduced.

---

## Access & configuration

- The tool (and the other staff tools) is mounted only when `SESSION_SECRET` is
  set. Access is gated by **`MENTOR_ADMIN_ALLOWED_TEAMS`** (default
  *Mentor Administration Team*).
- **Login provisioning** is off unless `MENTOR_PROVISION_USERS=true` and a
  dedicated **admin** EspoCRM service account is configured
  (`ESPO_PROVISION_USERNAME` / `ESPO_PROVISION_PASSWORD`); the team new logins
  join is `MENTOR_TEAM_NAME` (default *Mentor Team*). Creating EspoCRM Users is
  admin-only, which is why a dedicated admin account is required — staff stay
  non-admin. See `DEPLOYMENT.md` → *Staff tools + mentor-login provisioning*.
- **Google Workspace mailbox check / creation** is off unless configured — via
  the admin **Email Setup** screen (stored encrypted; needs `APP_ENCRYPTION_KEY` +
  `DATABASE_URL`) or the `GOOGLE_DIRECTORY_CHECK` / `GOOGLE_CREATE_MAILBOX` +
  `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_DELEGATED_ADMIN` env vars. When the
  check is on but creation is off, a confirmed-missing CBM mailbox blocks
  provisioning; with creation on, it's created instead; an inconclusive check
  fails open. Creating mailboxes needs the service account's read-write Directory
  scope. See `DEPLOYMENT.md` → *Google Workspace mailbox check + creation*.

Implementation lives in the `mentoradmin/` package (`service.py` is the
source-of-truth for the editable-field set + completeness rules); the grid reuses
`assignments.service.list_all_mentors`.
