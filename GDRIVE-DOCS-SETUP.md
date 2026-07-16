# Google-side setup for the Documents tab (v0.65.0) — step by step

Everything Google-side needed to activate the session tools' Google Drive
document management (`GDRIVE_DOCS`, DOC-MGMT Phase 1). Three tasks, reusing
the service account the Gmail + Calendar integrations already run on — **no
new service account, no new JSON key, no change to any app secret**.

The facts you'll need (from the Gmail/Calendar activation records):

| Item | Value |
|---|---|
| GCP project | `espcrm-498315` |
| Service account | `espocrm@espcrm-498315.iam.gserviceaccount.com` |
| Its OAuth2 **Client ID** (the DWD row key) | `109317126943210877831` |
| Scopes currently on the DWD row | `gmail.readonly`, `gmail.send`, `calendar.events` |
| Accounts to use | GCP console: the Google account that owns the project (created under `admin@cbmentors.org`). Admin console / Drive: a **super-admin** of `cbmentors.org` |

How the app uses this: when a manager uploads a document, the app
impersonates **that manager's own `@cbmentors.org` account** (their profile's
`cbmEmail`) and writes to the shared drive as them — so Drive's audit log
names the real person, and each manager needs their own access to the drive
(Task 3). The service account itself never appears as the uploader and does
**not** need drive membership.

---

## Task 1 — Enable the Google Drive API on the GCP project

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

## Task 2 — Add the Drive scope to the existing delegation row

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

## Task 3 — Create the "CBM Documents" shared drive and grant access

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
5. Click the drive name (top) → **Manage members**. Add **every staff member
   who will use the Documents tab** — each manager's `@cbmentors.org`
   account — with the role **Content Manager** (they need to create folders
   and upload; "Contributor" also works but Content Manager matches the PRD
   and lets them tidy files in Drive). Tip: if a suitable Google Group
   exists (or you make one, e.g. `mentors@cbmentors.org`), add the group
   once instead of person-by-person — future mentors then get access by
   joining the group.
6. Uploads act **as the signed-in manager**, so a manager who isn't a member
   gets a clear Drive 403 on their first upload — membership here is the
   fix, nothing app-side.

Nothing else to configure on the drive: the app creates the
`/{Entity Type}/{Record Name} ({recordId})/` folder structure itself on
first upload.

---

## Task 4 — App-side activation (Claude/deploy side, listed for completeness)

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
3. In Drive, open **CBM Documents** → a `CEngagement` folder →
   `<Record Name> (<id>)` → the file should be there, uploaded by **you**
   (not the service account) — that's the audit trail working.
4. Upload a second file to the same record — it must reuse the same folder
   (no duplicate folders).
5. Troubleshooting quick map:
   - 403 `accessNotConfigured` → Task 1 not done / wrong project.
   - `unauthorized_client` / "delegation denied" → Task 2 scope line wrong
     or not yet propagated.
   - Drive 403 on upload for one person, others fine → that manager isn't a
     member of the shared drive (Task 3 step 5).
   - "Your profile has no CBM email address" → the manager's
     `CMentorProfile.cbmEmail` is blank in the CRM (fix in `/mentoradmin`).
   - "The document integration needs the database" (503) → `DATABASE_URL`
     missing on that app (dev/lobster has no DB — expected there).
