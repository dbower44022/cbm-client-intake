# The per-chapter values — everything that differs between cities

> **Filling in a chapter's information?** This is not the place. Go to the
> deployment guide's stage 8, `deployment-guide/guide/08-fill-in-the-chapter-information-form.md`:
> it walks through the chapter information page question by question. This file
> is the engineers' inventory behind that form: where each value lands in the
> software and whether it is configurable yet.

**One document holding every value that is specific to a chapter**, so that
"configure this for Akron" means filling in one file rather than remembering
sixty places across an app spec, a CRM settings page and four source files.

Measured against the tree and against **live crm-test** on 2026-08-27, not
estimated. Where something is not yet parameterized it says so, rather than being
quietly listed as though it were.

**Why this exists.** Everything else in Phase 1 is about what all chapters share.
This is the opposite list, and it is the one that decides whether onboarding is a
morning or a fortnight. It is also the artifact
[Phase 3](phase-3-spec-secrets.md) automates — write it as a document first,
because a generator built before the list is known generates the wrong thing.

---

## The rule for deciding what belongs here

A value is **per-chapter** only if it names the chapter, its infrastructure or
its locale. Everything describing *how the product works* is standard, under
ruling 4 — core or nothing. When in doubt the answer is standard: every value
added here is one more thing that can be wrong on one instance and right on the
others, which is the drift this whole project exists to end.

The § G fence at the bottom lists what is deliberately **not** here. It matters
as much as the rest of the document.

---

## A. Identity — what the chapter is called

| Key | Cleveland's value | Lands in | State |
|---|---|---|---|
| `ORGANIZATION_NAME` | `Cleveland Business Mentors` | App env | **Built.** One setting names the chapter in every `<title>`, footer and piece of body prose across 18 pages, substituted server-side as the page is served |
| `CHAPTER_TOKENS_URL` | *(empty)* | App env | **Built.** A stylesheet loaded after `/shared/tokens.css` that may redefine `--cbm-*` on `:root` and nothing else |

`ops_mailbox_name` derives from `ORGANIZATION_NAME` automatically — a chapter
says who it is once. There is **no logo and no favicon** in the app by ruling
(2026-08-26); note § E, because the *CRM* carries one regardless.

---

## B. Web presence and legal

The policy URLs are the highest-stakes rows in this document: a chapter's
applicants tick a consent box, and it must link to **that chapter's** documents.
Shipping Cleveland's privacy policy to another city's applicants is a legal
exposure, not a branding blemish.

| Key | Cleveland's value | Lands in | State |
|---|---|---|---|
| `POLICY_CLIENT_CONDUCT_URL` | `…/client-code-of-conduct/` | App env | **Built** (v0.206.0) |
| `POLICY_MENTOR_ETHICS_URL` | `…/mentor-code-of-ethics/` | App env | **Built** |
| `POLICY_TERMS_URL` | `…/legal-notices/` | App env | **Built** |
| `POLICY_PRIVACY_URL` | `…/privacy-policy/` | App env | **Built** |
| `APP_BASE_URL` | the app's own root | App env | Built; already Cleveland-free in code |
| `DOCS_SITE_URL` | `https://docs.clevelandbusinessmentors.org` | App env | Setting exists, **defaults to Cleveland** |
| `EVENTS_PUBLIC_BASE_URL` | `https://clevelandbusinessmentors.org/webinars` | App env | Setting exists, **defaults to Cleveland**. Also the source of `CBMEvents.config.eventUrlBase` on the chapter's own website |
| `ALLOWED_ORIGINS` | — | App env | Per-chapter; only matters if a separate frontend origin is introduced |

The four "defaults to Cleveland" rows work today if a chapter sets them. The risk
is **forgetting**, which is exactly what this file removes.

---

## C. Locale — the silent one

| Key | Cleveland's value | Lands in | State |
|---|---|---|---|
| Application timezone | `America/New_York` | **Four source files** | **NOT parameterized** |
| `COMMS_DIGEST_TZ` | `America/New_York` | App env | Already a setting |
| `SANDBOX_RESET_TZ` | `America/New_York` | App env | Already a setting |

The four hardcodes, verified today:

- `portal/birthday.py:47` — `_LOCAL = ZoneInfo("America/New_York")`
- `assignments/service.py:1370` — the assignment date stamp
- `events/config.py:72` — `PUBLIC_TIMEZONE`
- `core/zoom.py:247` — a default argument

**Why this one is dangerous rather than merely missing.** Nothing errors. A
chapter in Denver or Phoenix simply gets wrong calendar days on birthday
greetings, assignment stamps and the public events programme, and the first
person to notice will be a mentor who was told the wrong date. Two of the four
are already settings, which shows the shape of the fix; the other four need doing
together, and a chapter outside Eastern time is the trigger.

---

## D. Google Workspace

Every chapter hosts its own email on its own Google Workspace (ruled 09-18-26,
replacing ruling 3's two branches). Every row below is the chapter's own.

| Key | Lands in | Supplied by | Notes |
|---|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | App env, **secret** | Services org | The delegation identity |
| `COMMS_INTERNAL_DOMAINS` | App env | Chapter | `cbmentors.org` today. Decides which mail is internal CBM↔CBM and so links to Contacts rather than records — wrong value silently pollutes the record Communications tabs. Since v0.217.0 it also governs the three "is this address one of ours" checks in `comms/service.py`, which were literals before |
| `OPS_MAILBOX` | App env | Chapter | The shared info@ identity. **Only ONE deployment may poll a given mailbox** — two double-capture |
| `ALERT_EMAIL_FROM` / `ALERT_EMAIL_TO` | App env | Chapter | The from-address must be a **real licensed mailbox**; a group or alias 403s `unauthorized_client` |
| `GDRIVE_SHARED_DRIVE_ID` | App env | Chapter | |
| `GOOGLE_MEMBERS_GROUP` | App env | Chapter | Empty disables the group step; the address is its own switch |
| `MENTOR_EMAIL_DOMAIN` | `cbmentors.org` | Chapter | The domain mentor logins and mailboxes are minted in. **Built** (v0.217.0) — it was a module constant, not "derived", until the Lakeside rehearsal reached the Google step |
| `ZOOM_HOST_EMAIL` | App env | Chapter | `zweb@cbmentors.org`; **defaults to Cleveland**. Public webinars only — mentor sessions never use a chapter Zoom account |

---

## E. Inside the CRM — inventoried 2026-08-27, not previously listed anywhere

These are **EspoCRM instance settings**, not app environment variables. Nothing
in this repo sets them; they are configured per instance and have never appeared
on any list until now. Measured live on crm-test.

| Setting | Cleveland's value | Notes |
|---|---|---|
| `applicationName` | `Cleveland Business Mentors` | The CRM's own name in its UI |
| `outboundEmailFromName` | `Cleveland Business Mentors` | **Production reads "Cleveland Business Mentoring"** (with -ing) and is a known outstanding fix. CRM-native sends carry whatever this says, regardless of what the app renders |
| `outboundEmailFromAddress` | `info@cbmentors.org` | |
| `siteUrl` | the instance's own URL | |
| `companyLogoName` | `CBM Logo DEV V2.png` | **The one per-city image asset that actually exists.** The app has no logo by ruling; the CRM does |
| `timeZone` | `America/New_York` | Independent of the app's timezone in § C — both must agree |
| `dateFormat` | `MM/DD/YYYY` | |
| `timeFormat` | `HH:mm` | |
| `defaultCurrency` | `USD` | Currency fields validate against their `*Currency` companion, so this is load-bearing, not cosmetic |
| `language` | `en_US` | |
| `weekStart` | `0` | |

Learned on the 2026-08-31 rehearsal, and not on the list above until then:

| | Cleveland's value | Notes |
|---|---|---|
| **The `tabList` url item** | *CBM Documentation* → `docs.clevelandbusinessmentors.org` | The one per-chapter item inside an otherwise-standard tab list; it is `DOCS_SITE_URL`'s twin inside the CRM |
| **EspoCRM version** | crm-test 9.3.4, prod (unverified) | The CRMBuilder deploy installs the current release (10.0.6 on 2026-08-31). Not a value a chapter picks. **Ruled 2026-09-23:** a new chapter takes the current release and Cleveland moves up to it (`TASKS.md` C1), so the difference is temporary |

Also per-chapter inside the CRM, and not configuration:

- **Users.** The chapter's own staff and mentors. 26 on crm-test.
- **The org-wide API key** and its role's key value.
- **The provisioning admin account** (`ESPO_PROVISION_*`).

---

## F. Infrastructure and secrets

| Key | Secret | Supplied by |
|---|---|---|
| `ESPO_BASE_URL` | no | Chapter's CRM |
| `ESPO_API_KEY` | **yes** | Chapter's CRM |
| `ESPO_PROVISION_USERNAME` / `_PASSWORD` | **yes** | Services org — admin accounts are theirs by ruling 6 |
| `DATABASE_URL` | **yes** | Chapter's DO account. Note DO appends `?sslmode=require`, which asyncpg rejects — `core/store.make_async_engine` strips it |
| `SESSION_SECRET` | **yes** | Generated per chapter |
| `APP_ENCRYPTION_KEY` | **yes** | Generated per chapter, **once** — it encrypts the secrets `/setup` stores, so rotating it makes every one of them permanently unreadable |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **yes** | The chapter's Google service account key (deployment guide stage 10) |
| `SESSION_COOKIE_SECURE` | no | `true` everywhere real |

Seven secrets across 42 environment variables today (six until 2026-09-18, which missed `APP_ENCRYPTION_KEY`; the Google key rides alongside them). **They live in gitignored
overlays on one laptop**, and regenerating an overlay from `doctl apps spec get`
encrypts the plaintext into unreadable `EV[…]` blobs. That is fragile for two
apps and not viable for N — it is the single largest reason
[Phase 3](phase-3-spec-secrets.md) exists, and the services org's bus factor
until it lands.

### Feature flags

Not identity, but per-deployment, and a chapter's spec must state each one
deliberately: `ANALYTICS_ENABLED`, `EVENTS_ENABLED`, `EVENTS_PUBLIC_API`,
`GMAIL_SYNC`, `GCAL_EVENTS`, `GDRIVE_DOCS`, `GDRIVE_IDENTITY`,
`MENTOR_PROVISION_USERS`, `RECORD_QUICK_ADD`, `SETUP_ENABLED`,
`ASYNC_DELIVERY`, `ESPO_DRY_RUN`.

**`deploy_on_push` is the chapter's choice, and the branch is always `release`.**
Since 09-24-26 the chapter answers Take each release automatically? on its form
(guide step 8.6): yes gives `deploy_on_push` on, the Latest Stable policy, and the
app updates itself when a release is cut; no gives `deploy_on_push` off, the On
Demand policy, and the app stays on its release until the chapter asks for the
upgrade or schedules it (CRMBuilder decision DEC-1156). Before 09-24-26 this said
ON for every chapter, and before 09-23-26 it said OFF, which was right while the
release tag travelled in each deployment's spec; since v0.228.0 the tag is stamped
into the software at cut time. The danger that remains is `deploy_on_push` from
`main`, which `render_spec.py` refuses.

---

## G. Deliberately NOT per-chapter — the ruling 4 fence

Every item below is **the same on every instance**. Anything here becoming
per-chapter ends the architecture, so it is listed explicitly rather than left to
inference.

| | Why it is standard |
|---|---|
| **The 7 team names** | Every team gate in the product resolves one of these strings. All 7 exist identically on both live instances (verified 2026-08-24) |
| **Roles** | 12 on crm-test. They define what teams *mean*; a chapter with different roles is a chapter running different software |
| **Email templates** | 6 required. **Verified 2026-08-27: template bodies carry no hardcoded brand at all**, so they are genuinely build-once-deploy-everywhere. This was not knowable without looking, and it removes a category people would otherwise assume was per-city |
| **Entity and field schema** | 16 custom entities, ~298 custom fields, ~96 custom links — **two file trees**: `custom/Espo/Custom/` and `client/custom/src/` (the CBM navbar view; without it the CRM UI is blank) |
| **Extensions the roles depend on** | Advanced Pack 3.12.1 and Google Integration 1.8.4 are installed on crm-test and the roles name their scopes. **Ruled IN the standard (R7, 2026-08-31)**: every chapter installs both before the roles are applied; an Advanced Pack licence per instance is accepted cost |
| **Enum options / form dropdowns** | 16 managed lists from 14 `Entity.field` sources |
| **Layouts** | `/directory` reads the CRM's own list and detail layouts live |
| **Everything in `frontend/`** | `CBM`, `cbm-`, `--cbm-*`, `data-cbm-*` are **identifiers, not content**, and two are live contracts with the website |

---

## H. What is not parameterized yet

The honest gap list, in the order I would fix it.

1. **The timezone** (§ C) — four source files, and the only item here that
   produces *wrong output* rather than a Cleveland-flavoured label. Trigger: the
   first chapter outside Eastern time.
2. **The values file itself** — this document describes the shape; nothing reads
   it. Phase 3.
3. **The secrets store** (§ F) — seven secrets on one laptop.
4. **The CRM settings in § E** — no script sets them, and they were not on any
   list before today. They are a handful of API calls and belong in whatever
   applies CRM configuration.
5. **Four settings defaulting to Cleveland** — `DOCS_SITE_URL`,
   `EVENTS_PUBLIC_BASE_URL`, `COMMS_INTERNAL_DOMAINS`, `ZOOM_HOST_EMAIL`. They
   work when set; the risk is forgetting, which this document addresses without
   any code change.

---

## The blank form

**Replaced on 09-23-26.** The form is now the chapter information page, built
from the `fields` lists in `deployment-guide/steps/stage-08.yaml` by
`scripts/chapter_form/build_page.py`, and the values file is written from the
page's answers by `scripts/chapter_form/to_values.py`. The questions, what each
means, where each answer comes from and how each is checked live in stage 8 and
nowhere else, so a list here would only fall behind it. A new per-chapter
setting is added as a question in stage 8; `tests/test_chapter_form.py` fails
until every setting the build reads is asked.

---

## Change log

| Date | Change |
|---|---|
| 09-24-26 00:39 | `deploy_on_push` becomes the chapter's own choice on the form (Doug, 09-24-26, CRMBuilder decision DEC-1156): yes is Latest Stable, no is On Demand; a chapter may decline a release or schedule its upgrade. |
| 09-23-26 13:23 | EspoCRM version row: a new chapter takes the current release and Cleveland moves up to it (Doug, 09-23-26). |
| 09-23-26 12:03 | The blank form is replaced by the chapter information page built from stage 8 of the deployment guide; this file becomes the engineers' inventory and says so at the top (Doug, 09-23-26: the file explained nothing about the process). |
| 09-23-26 00:55 | `deploy_on_push` corrected to ON (following `release`), matching guide step 11.9. The Google key is handed to the spec script by file path. Found reviewing the guide before the first real chapter. |
| 09-19-26 00:30 | `delegated_admin` added (GOOGLE_DELEGATED_ADMIN, which no step or form set); `events_public_base_url` now says to leave it empty; `shared_drive_id` notes it is filled in at step 10.5. Found by the precision sweep. |
| 09-19-26 00:10 | The Google branch field removed from the form, and § D rewritten: every chapter hosts its own Google Workspace (Doug, 09-18-26). |
| 09-18-26 17:45 | `mentor_email_domain` added to the form's Google section, and three switches added: `google_create_mailbox`, `gdrive_identity`, `zoom_events`. Found by the information check when the deployment guide was turned into data. |
| 09-18-26 02:05 | The Zoom app's account and client identifiers added to the form, and its client secret added to the secrets list, for a chapter that runs public webinars. `ZOOM_HOST_EMAIL` defaults to Cleveland's host, so a chapter must set it. Found while writing the deployment guide's methods for the hosting and video meeting accounts. |
| 09-18-26 00:58 | The blank form brought up to the trial chapter's filled-in copy. `APP_ENCRYPTION_KEY` added as the seventh secret (§ F and the form), and `GOOGLE_SERVICE_ACCOUNT_JSON` added to § F, where the form already had it. Five flags the trial chapter needed added to the form: `events_public_api`, `google_directory_check`, `record_quick_add`, `async_delivery`, `espo_dry_run`. Found while writing the deployment guide's methods for filling in the form. |
