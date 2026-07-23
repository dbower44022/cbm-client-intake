# Google-side setup for the Documents tabs (DOC-MGMT Phases 1–3) — step by step

Everything Google-side needed to activate the Google Drive document
management (`GDRIVE_DOCS`), reusing the service account the Gmail + Calendar
integrations already run on — **no new service account, no new JSON key, no
change to any app secret**.

**Status (2026-07-18): Tasks 1–4 AND the Task 6 activation are DONE.**
2026-07-16: Drive API enabled, the `auth/drive` scope authorized, the "CBM
Documents" shared drive created, `GDRIVE_DOCS` live on both environments,
first live upload verified on prod. 2026-07-17/18: the membership swap
completed under **Doug's amended ruling (PRD v1.5)** — the drive's members
are the service account **plus the two designated system administrators
(doug.bower@, allen.ingram@; maintenance and review)**, `espo@cbmentors.org`
removed; `GDRIVE_IDENTITY=service` + the worker env applied to BOTH
environments; and the first production reconciliation pass issued 2
engagement-folder Commenter grants with zero errors (by 2026-07-22 the
nightly pass covers 6 record folders, still zero errors). **Remaining:**
the `documentsFolderUrl` CRM field build (Task 6 step 3 — the nightly
log's "0 CRM link(s) written" flips to nonzero once it exists) and the
rest of the Task 6 verification checklist (items 1–3, 5–6 still to be
driven by hand; item 4's grant-issuance half is proven by the production
logs). **Known benign quirk:** folders whose entitled mentor is ALSO a
drive member (i.e. a system admin who is the assigned mentor — test-data
reality) get re-granted on every pass, because Drive merges a member's
redundant Commenter grant rather than storing it as a direct permission.
Logged, no errors, no emails; non-member mentors' grants persist
normally.

The facts you'll need (from the activation records):

| Item | Value |
|---|---|
| GCP project | `espcrm-498315` |
| Service account | `espocrm@espcrm-498315.iam.gserviceaccount.com` |
| Its OAuth2 **Client ID** (the DWD row key) | `109317126943210877831` |
| Scopes on the DWD row (since 2026-07-16) | `gmail.readonly`, `gmail.send`, `calendar.events`, `drive` |
| The "CBM Documents" shared drive ID | `0AE50yNppMh_hUk9PVA` |
| Accounts to use | GCP console: the Google account that owns the project (created under `admin@cbmentors.org`). Admin console / Drive: a **super-admin** of `cbmentors.org` |

How the app uses this (the final access model, PRD v1.3 / Doug's ruling
2026-07-16): the app performs **all Drive operations as the service account
itself** (`GDRIVE_IDENTITY=service`), and the service account is the shared
drive's **only member** — no person ever holds drive membership. The app's
own records (`uploaded_by`, run logs) attribute every operation to the real
person; Drive-side human access exists only as per-folder Commenter grants
the app issues automatically (Task 6). (The original per-user impersonation
mode, `GDRIVE_IDENTITY=user`, remains in the code for compatibility only.)

---

## Task 1 — Enable the Google Drive API on the GCP project ✅ DONE 2026-07-16

Without this, every Drive call fails with HTTP 403 `accessNotConfigured` /
"Google Drive API has not been used in project espcrm-498315 before or it is
disabled".

1. Go to **https://console.cloud.google.com** and sign in with the account
   that owns the project.
2. In the **project picker** (top bar, left of the search box), select
   **`espcrm-498315`**. Verify the picker shows that project id before
   continuing — enabling the API on the wrong project does nothing.
3. Open the left-hand menu (☰) → **APIs & Services → Library**.
   (Direct URL: https://console.cloud.google.com/apis/library?project=espcrm-498315)
4. In the Library search box type **`Google Drive API`** and open the result
   named exactly **Google Drive API** (by Google Enterprise API).
5. Click **Enable**. If the button already reads **Manage**, it's enabled —
   nothing to do.
6. Sanity check: **APIs & Services → Enabled APIs & services** should now
   list **Google Drive API** alongside **Gmail API** and **Google Calendar
   API**.

That's all in GCP. Do **not** add IAM roles to the service account — its
power comes from the Workspace delegation (Task 2), not GCP IAM. Do **not**
create a new key.

---

## Task 2 — Add the Drive scope to the existing delegation row ✅ DONE 2026-07-16

This authorizes the service account to act on users' Drive access. It's an
**edit of the existing row**, not a new row: Google keys delegation rows by
Client ID, and **all scopes for one Client ID must live in that single row** —
adding a second row for the same ID replaces/conflicts rather than merging.

1. Go to **https://admin.google.com** and sign in as a `cbmentors.org`
   **super-admin**.
2. Left menu → **Security → Access and data control → API controls**.
3. In the "Domain wide delegation" panel at the bottom, click
   **MANAGE DOMAIN WIDE DELEGATION**.
4. Find the row whose **Client ID** is `109317126943210877831` (it currently
   lists the two Gmail scopes + the Calendar scope). Hover the row and click
   **Edit** (pencil).
5. In **OAuth scopes**, set the value to exactly these **four** scopes,
   comma-separated, no spaces, no line breaks (copy-paste this whole line):

   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/drive
   ```

   ⚠️ The field REPLACES the previous list — the three existing scopes must
   be in it or the Communications/Calendar integrations break. Paste the
   full four-scope line, don't type just the new one.

   (Why the full `auth/drive` scope and not the narrower `auth/drive.file`:
   the app must list and create folders on a **shared drive** it didn't
   create per file — `drive.file` only reaches files the app itself opened
   or created, which breaks the folder scheme. PRD §3.4 / open issue OI-04
   records this; it can be revisited once the flows stabilize.)
6. Click **AUTHORIZE**.
7. Verify: the row now shows four scopes. Common paste mistakes that make
   authorization silently fail for one scope: a trailing period, a space
   after a comma, `http://` instead of `https://`.

**Propagation:** usually takes effect within a few minutes; Google documents
up to 24 hours. If a test right after authorizing fails with
`unauthorized_client` / "delegation denied", wait and retry before changing
anything.

---

## Task 3 — Create the "CBM Documents" shared drive ✅ DONE 2026-07-16 (except the step-5 membership swap — see Task 6)

A **shared drive** (not a folder in anyone's My Drive) so the files belong
to the organization and survive staff turnover (PRD decision D-03).

1. Go to **https://drive.google.com** signed in as a `cbmentors.org` account
   that's allowed to create shared drives (a super-admin always can).
2. In the left rail click **Shared drives**, then **+ New** (top-left).
3. Name it exactly **`CBM Documents`** and click **Create**.
4. Open the new drive. **Copy its ID from the browser address bar** — the
   URL looks like:

   ```
   https://drive.google.com/drive/folders/0AL3xKqz9AbCdEfGhIjK
   ```

   The last path segment (starting `0A…`) is the **shared drive ID** — this
   is the `GDRIVE_SHARED_DRIVE_ID` value the app needs. Paste it somewhere
   safe (it's not a secret, just fiddly to re-find).
5. Click the drive name (top) → **Manage members**. Under the amended
   access model (PRD v1.5, Doug's ruling 2026-07-17 — supersedes both the
   earlier "add every staff member" guidance AND v1.3's "exactly one
   member"): the members are the **service account**
   (`espocrm@espcrm-498315.iam.gserviceaccount.com`, the operational
   identity) **plus the designated system administrators** (currently
   doug.bower@ and allen.ingram@, for maintenance and review) — no other
   person. Remove any other members.
6. Human Drive access exists only as per-folder **Commenter** grants the app
   issues automatically (Phase 3, DOC-09) — mirroring CRM assignments. A
   manager who can see the record in the app can always view/upload through
   the app regardless; the folder grant only affects Drive-side access
   (Open in Drive).

Nothing else to configure on the drive: the app creates the whole folder
tree itself on first upload (PRD v1.2 §3.2) —

```
CBM Documents
├── Mentors
│   └── Jane Smith (contactId)/           ← mentor documents (Contact anchor)
├── Clients
│   └── Acme Robotics (clientId)/
│       └── Jane Smith – 2026 (engId)/    ← client-work documents (CEngagement)
├── Partners
└── Sponsors
```

Humans may rename any folder's words freely — the app locates folders and
files by ID only; the `(recordId)` suffix is for the app, the words are for
you.

---

## Task 4 — App-side activation (Claude/deploy side) ✅ DONE 2026-07-16 (Phase 1 flags on both envs; the Phase 3 additions are Task 6 step 2)

Not Workspace work — this is the overlay + deploy step once Tasks 1–3 are
done. On the target app's gitignored overlay (`.do/app.prod.yaml` for
crm-test first, then `.do/app.prod-crm.yaml` for prod), **web component
only** (the worker isn't involved):

```yaml
- key: GDRIVE_DOCS
  value: "true"
- key: GDRIVE_SHARED_DRIVE_ID
  value: "<the ID from Task 3 step 4>"
```

Apply with `doctl apps update <app-id> --spec <overlay> --wait`. The
pre-deploy migrate job runs Alembic `0005_app_document` automatically.
Optional overrides: `GDRIVE_DOC_TYPES` (comma-separated upload type list,
default `Resume,Agreement,Intake Document,Pitch Deck,Other`) and
`GDRIVE_MAX_FILE_MB` (default 100).

---

## Task 5 — Verify (the Phase 1 live smoke test)

1. Sign in to the portal as a real manager (e.g. `doug.bower`) → open a
   record in `/mentorsessions` → **Documents** tab. The upload button should
   appear (not the "coming soon" placeholder).
2. Upload a small PDF, picking a document type. Expected: "Document
   uploaded." and the file listed with your CBM address as uploader.
3. In Drive, open **CBM Documents** → **Clients** → the client's folder →
   the engagement's folder → the file should be there. (Drive shows the
   uploader as the person under the original `user` identity mode, and as
   the service account under `GDRIVE_IDENTITY=service` — in service mode
   the app's own document list and run logs carry the person's name.)
4. Upload a second file to the same record — it must reuse the same folder
   (no duplicate folders).
5. Also check the mentor side: `/mentoradmin` → open a mentor → **Documents**
   tab → upload → the file lands in **Mentors** → `<Mentor Name> (…)`.
6. **Phase 2 (v0.70.0) — viewing:** View on a PDF row opens it inside the
   app; View on an image shows it inline; a Google Doc/Sheet/Slide opens as
   an exported PDF. Edit a file in Drive, reopen the tab → the row shows an
   **"Updated in Drive"** tag and View fetches the new version (the old one
   was browser-cached under the previous modifiedTime). No extra
   configuration — Phase 2 rides the same flags.
7. **v0.71.0 — service-account identity + Office viewing.** Users are NOT
   shared-drive members (Doug's ruling), so run with **`GDRIVE_IDENTITY=
   service`** on the web component: the service account performs all Drive
   operations as itself. **One-time step: add the service account's
   `client_email` (from the JSON key) as a member of the "CBM Documents"
   shared drive with Content Manager access** — with this set, managers
   need no Drive access at all and the app's CRM permission check is the
   only gate. Word/Excel/PowerPoint/CSV files now view in-app too (the
   server converts to PDF on view — a temp Google-format copy appears in
   the record folder for a few seconds during conversion; that's normal).
   Note: the "Open in Drive" button works for people holding a folder
   grant — issued automatically by the Phase 3 grants module (Task 6).
   Remove any human members from the shared drive when switching to
   `GDRIVE_IDENTITY=service` — the ruling is that no person is ever a
   drive member.
8. Troubleshooting quick map:
   - 403 `accessNotConfigured` → Task 1 not done / wrong project.
   - `unauthorized_client` / "delegation denied" → Task 2 scope line wrong
     or not yet propagated.
   - Drive 403 on upload for one person, others fine (only possible under
     the legacy `GDRIVE_IDENTITY=user` mode) → that manager isn't a drive
     member. Under `service` mode everyone goes through the service
     account — a 403 there means the SA isn't a Content Manager member
     (Task 6 step 1).
   - "Your profile has no CBM email address" (legacy `user` mode only) →
     the manager's `CMentorProfile.cbmEmail` is blank in the CRM (fix in
     `/mentoradmin`); `service` mode never blocks on this.
   - "The document integration needs the database" (503) → `DATABASE_URL`
     missing on that app (dev/lobster has no DB — expected there).

---

## Task 6 — Phase 3 activation: the access model, grants, archive, CRM links (v0.76.0)

Phase 3 (DOC-MGMT, PRD v1.3) ships three things — folder-level **Drive access
grants** mirroring CRM assignments (DOC-09), **Archive/Restore** on every
Documents tab (DOC-07), and the **`documentsFolderUrl` CRM write-back**
(DOC-08). Archive/Restore needs nothing beyond the Phase 1 flags. The other
two activate as follows — **order matters**:

1. **Drive-side membership swap** ✅ **DONE 2026-07-18** (under the PRD
   v1.5 amended ruling): the service account was added as **Manager** and
   `espo@cbmentors.org` removed; the final member list is the service
   account + the two designated system administrators (doug.bower@,
   allen.ingram@). For any future membership change: Drive → CBM Documents
   → drive name → **Manage members**; the member list must always be the
   SA + the designated admins, nothing else (the nightly reconciliation
   governs FOLDER grants, not drive membership — membership is manual).
2. **Set the env on BOTH components** ✅ **DONE 2026-07-18** (both
   environments applied + verified; the first prod reconciliation pass
   issued 2 grants, zero errors). For reference — each app's gitignored
   overlay (`.do/app.prod.yaml` crm-test, `.do/app.prod-crm.yaml` prod),
   applied via `doctl apps update <app-id> --spec <overlay> --wait`:

   ```yaml
   # web component — switches all Drive operations to the service account
   - key: GDRIVE_IDENTITY
     value: "service"
   # worker component — the nightly reconciliation needs the same three
   # (plus the SA JSON + DATABASE_URL it already carries):
   - key: GDRIVE_DOCS
     value: "true"
   - key: GDRIVE_SHARED_DRIVE_ID
     value: "<same id as the web component>"
   - key: GDRIVE_IDENTITY
     value: "service"
   ```

   Optional: `GDRIVE_RECONCILE_SECONDS` (worker; default `86400` = daily;
   `0` disables the reconciliation job). Alerts go to `ALERT_WEBHOOK_URL`
   when set (else WARNING logs), like the V2 monitoring.
3. **CRM field build (CRM team / crmbuilder):** `documentsFolderUrl` (Url,
   read-only in layouts) on **CEngagement** and **Contact** — full spec:
   `documentsfolderurl-crm-field.md`. The app feature-detects it; build
   before or after the deploy in any order.

### Verify (the Phase 3 live checklist)

1. **Grants:** in Client Administration, assign a mentor to an engagement
   that already has documents → within a few seconds the mentor finds the
   engagement folder in Drive's **Shared with me**, role Commenter (they can
   open/download/comment, cannot upload or edit). Add a co-mentor on the
   engagement's Details tab → same for them; remove the co-mentor → their
   access is gone.
2. **First upload grants:** upload the first document to an engagement that
   already has an assigned mentor → the folder is created AND shared with
   that mentor in the same action.
3. **Mentors/ folders:** upload a mentor document in `/mentoradmin` → the
   `Mentors/{Name}` folder has NO human grants (check Manage access in
   Drive) — application-only, by design.
4. **Reconciliation:** hand-grant someone on a record folder in Drive (as a
   super-admin), wait for the nightly pass (or restart the worker — the job
   runs at startup) → the grant is removed and an alert is logged/posted.
5. **Archive:** on a Documents tab, Archive a row (two clicks) → the file
   moves to the record folder's `_Archived` subfolder in Drive and the row
   leaves the list; "Include archived" reveals it; Restore puts both back.
6. **CRM link:** after the field build, upload the first document for a
   record → the CEngagement (or mentor's Contact) record shows the Drive
   folder link in `documentsFolderUrl`; a second upload does not change it.
