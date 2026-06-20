# CInformationRequest — dedicated record of each info-request submission

The **info-request** form already creates/updates a Contact (Prospect), stamps
the message into the Contact's `description`, and writes a generic
`CIntakeSubmission` audit record. **In addition**, it now creates a dedicated
**`CInformationRequest`** record — a self-contained business record of the
request, linked to the Contact (and Account when a company is involved) — so
staff have a real worklist/reporting entity rather than only a note buried in a
Contact's description.

This is additive: the Contact.description stamp and the `CIntakeSubmission` log
are unchanged.

**Status:** to be **built by the CRM team** in EspoCRM (entity + fields + links +
the API user's *create* grant). The app writes the record **best-effort** — until
the entity, its fields/links, and the create grant exist in crm-test, the write
fails and is logged at WARNING, and the submission still succeeds. So the app can
deploy ahead of the CRM build (same pattern as `CIntakeSubmission`, see
`cintake-submission-entity.md`).

## Entity

- **EspoCRM name:** `CInformationRequest` (EspoCRM adds the `C` prefix to custom
  entities); natural label **"Information Request"**. Custom object entity; show
  in the navbar so staff can find the queue.

## Fields

Custom fields on a custom entity are plain camelCase api-names (**no `c` prefix**,
unlike custom fields on native Account/Contact). The app writes exactly these
keys:

| Field (api-name) | Type | Notes |
|---|---|---|
| `name` | varchar | Record label. The app sets `"<first> <last> — <YYYY-MM-DD>"`. |
| `createdAt` | datetime | Native. Submission time (use for over-time analytics; no separate field needed). |
| `firstName` | varchar | Requester first name. |
| `lastName` | varchar | Requester last name. |
| `email` | varchar | Requester email (plain varchar — not the multi-value email field type). |
| `phone` | varchar | Requester phone, normalized to E.164. Omitted if not given. |
| `company` | varchar | Company name. Omitted if not given. |
| `message` | text | The request body — the heart of the submission. |
| `source` | text | How they heard about CBM (`how_did_you_hear`). Omitted if not given. |
| `requestStatus` | enum | Staff worklist state. Options: `New`, `In Progress`, `Responded`, `Closed`. Default `New`; the app sets `New`. |
| `form` | text | The originating form — the app sets `"info-request"`. |
| `submitterEmail` | varchar | The submitter's email (same value as `email`); mirrors CIntakeSubmission. |
| `description` | text | Human note + the raw submission JSON (honeypot cleared), mirroring the CIntakeSubmission record. |
| `response` | wysiwyg | Staff-entered response. NOT written by the app. |
| `contact` | link (belongsTo → Contact) | The Contact this request is for (FK `contactId`; foreign link `cInformationRequests`). Always set. |
| `infoRequestCompany` | link (belongsTo → Account) | The company Account, when one is involved (FK `infoRequestCompanyId`; foreign link `cInformationRequests`). Set only when a new contact + company produced/matched an Account. |

Standard `assignedUser` / `teams` links come for free on a `Base`-type entity.

## API-user permission

Grant the dedicated intake API user **create** on `CInformationRequest` (same
create-only pattern as Account / Contact / CClientProfile / CEngagement /
CIntakeSubmission). The app only ever *creates* these records; staff
edit/triage/close them in the UI. No `edit` grant is needed.

## App integration (already wired)

`forms/info_request/orchestrator.py` → `_create_information_request()` builds the
payload above and creates the record (best-effort) after the Contact is
created/matched, on every submission — including repeat-email submissions (each
request becomes its own `CInformationRequest`, alongside the description append).
The created id is returned as `informationRequestId`.

## Verification (once built in crm-test)

1. Grant create on `CInformationRequest` to the intake API user.
2. Submit the info-request form (or POST `/api/info-request/intake`).
3. Confirm a `CInformationRequest` record exists with the fields above and a
   `contact` link to the produced Contact; the run logs show
   `created CInformationRequest <id>` instead of the best-effort WARNING.
