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

- **Search** by name, industry, expertise, or focus area.
- **Filter** by mentoring status, **Record** (completeness) status, or industry.
- **Sort** by any column.

Columns: **Mentor · Record · Status · Created · Assigned · Capacity · Industry**.

The **Record** column shows each mentor's stored completeness status
(**Complete / Incomplete / Duplicate**, or "—" if not yet calculated). Use the
**Record** filter set to *Incomplete* to quickly see **which mentors need work**.
The Record value is refreshed whenever a mentor is **saved** (see
[Record Status](#record-status)).

Click a mentor's name to open their detail screen.

---

## The mentor detail screen

**Summary card (read-only, top of the page).** At-a-glance facts that aren't
edited here: the **Data completeness** badge (see below), mentoring status,
accepting-new-clients, the mentor's email / phone / address, and capacity /
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
| **Background check** completed | `backgroundCheckCompleted` = true |
| **Ethics agreement** accepted | `ethicsAgreementAccepted` = true |
| **Training** completed | `trainingCompleted` = true |
| **Terms** accepted | `termsAccepted` = true |

### Additionally, if the mentor's status is **Active**

| Requirement | Field |
|---|---|
| A **CBM email address** is set | `cbmEmail` |
| A login **User** is assigned to the mentor (the CBM member record) | `assignedUser` |
| The **same User** is assigned to the mentor's **Contact** | `Contact.assignedUser` |

### Additionally, if **Public profile** is turned on

(`publicProfile` = true — a checkbox on the **Status** tab.)

| Requirement | Field |
|---|---|
| **About the mentor** contains text | `aboutMentor` |
| At least one **Mentoring focus area** | `mentoringFocusAreas` |
| At least one **Area of expertise** | `areaOfExpertise` |
| An **Industry sector** is selected | `industrySector` |

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
3. <a id="logins-on-save"></a>**Login provisioning.** If the mentor's status is
   **Approved or Active** and they have **no login yet**, the app automatically
   creates an EspoCRM **User** for them:
   `firstname.lastname@cbmentors.org` (the CBM email — reusing `cbmEmail` if
   already set), places it in the **Mentor Team**, assigns it to the mentor
   record, and emails the mentor a welcome / set-password link.
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

Implementation lives in the `mentoradmin/` package (`service.py` is the
source-of-truth for the editable-field set + completeness rules); the grid reuses
`assignments.service.list_all_mentors`.
