# System Admin Troubleshooting & Verification Guide

**For:** a CBM System Administrator with **EspoCRM Admin rights** and a
**DigitalOcean console login**, who needs to confirm the CRM and the custom apps
are working — or work out why they aren't — **when the engineer is unavailable**.

You do **not** need the command line, a code editor, or the source repository to
use this guide. Everything here is done in a web browser: the DigitalOcean
console, EspoCRM's admin screens, and the apps' own buttons.

> **The one rule that matters most:** *diagnose freely, remediate only from
> §5, never touch §6.* Everything in §5 is safe, reversible, and designed to be
> pressed by a human. Everything in §6 can take the live forms offline or cause
> duplicate CRM records, and none of it is ever urgent enough to do without the
> engineer.

**Contents**

1. [What you're looking after — and how to get in](#1-what-youre-looking-after--and-how-to-get-in)
   · [Credentials (Proton Pass)](#14-credentials--everything-is-in-proton-pass)
   · [Signing in to DigitalOcean](#15-signing-in-to-digitalocean)
   · [The console map](#16-the-digitalocean-console--where-everything-is)
   · [Which setting lives where](#17-which-setting-lives-where)
2. [The five-minute health check](#2-the-five-minute-health-check)
3. [The weekly verification sweep](#3-the-weekly-verification-sweep)
4. [Symptom index — someone reports a problem](#4-symptom-index--someone-reports-a-problem)
5. [The remediation toolkit — what you may safely do](#5-the-remediation-toolkit--what-you-may-safely-do)
6. [Off-limits — never do these without the engineer](#6-off-limits--never-do-these-without-the-engineer)
7. [Alerts — what each one means](#7-alerts--what-each-one-means)
8. [Escalating: what to capture](#8-escalating-what-to-capture)
9. [Reference tables](#9-reference-tables)
10. [Glossary](#10-glossary)

---

## 1. What you're looking after — and how to get in

### 1.1 Two systems, not one

There are **two live systems** and they are separate things:

| | What it is | Where you administer it |
|---|---|---|
| **EspoCRM** | CBM's database and system of record. All the real data lives here. | The CRM's own web interface, signed in as an Admin user |
| **The custom apps** | The public intake forms + the staff/mentor tools, running on DigitalOcean. They **read and write the CRM over its API** — they store almost nothing themselves. | The DigitalOcean console + each app's own screens |

Because the apps are a *front end onto the CRM*, **most app problems are
actually CRM problems** — a missing permission, a renamed dropdown value, a
record that isn't linked to the right person. That's why §4 sends you to the CRM
so often.

### 1.2 The three deployments

| Environment | App address | Which CRM it writes to | Name in the DO console |
|---|---|---|---|
| **Production** | https://apps.clevelandbusinessmentors.org/ | https://crm.clevelandbusinessmentors.org | **`cbm-client-intake-prod`** |
| **Test** | https://cbm-client-intake-svxs3.ondigitalocean.app/ | https://crm-test.clevelandbusinessmentors.org | **`cbm-client-intake`** |
| **Dev** | https://lobster-app-w6h5m.ondigitalocean.app/ | none — writes nothing anywhere | **`lobster-app`** |

> ### ⚠️ Read that last column twice
>
> The app called plain **`cbm-client-intake`** is the **TEST** one. Production is
> the one with **`-prod`** on the end. The naming is the opposite of most
> people's instinct, and it is the single easiest way to do something to the
> wrong environment. **Before you change anything, confirm the app name at the
> top of the page.**

**Production is the one that matters.** Test is a safe copy used to try things
out; Dev writes to no CRM at all. If someone reports a problem, *first establish
which address they were using* — a surprising number of "it didn't save" reports
are someone working in Test or Dev.

### 1.3 The parts inside one app

Each of Production and Test runs **two processes** you can see in the
DigitalOcean console:

- **`web`** — everything a person touches: the five public forms, the portal
  sign-in, and all the staff/mentor tools.
- **`delivery-worker`** — the background engine. It delivers submissions into
  the CRM, sends the alert emails, syncs Gmail, polls the info@ inbox, tidies
  Google Drive permissions, fetches meeting transcripts, and runs the nightly
  repair jobs.

If **web** is down, people see errors. If **delivery-worker** is down, *people
usually see nothing wrong* — forms still accept submissions, which pile up
safely and deliver in a rush once it recovers. That silence is exactly why §2's
worker check exists.

---

### 1.4 Credentials — everything is in Proton Pass

**Every login and key this guide refers to is stored in Proton Pass**, in the
vault shared with the people who cover this role. You should already have
access; if you don't, that's the first thing to sort out — *before* there's an
incident, not during one.

What you should expect to find in the vault:

| Credential | Used for |
|---|---|
| **DigitalOcean — `admin@cbmentors.org`** | The shared console login (§1.5) |
| **EspoCRM admin account** | Administration screens on the production CRM |
| **EspoCRM intake API key** | How the apps write to the CRM. You will never need to type this — only to confirm it hasn't been changed |
| **EspoCRM provisioning service account** | Creates mentor logins and sets permission teams. Runs behind the scenes |
| **Google service account key** | Gmail sync, Calendar, Drive, the alert emails |
| **info@cbmentors.org / the alert mailbox** | Where inbound requests and alerts land |

**Three rules about credentials, and they are not negotiable:**

1. **Never copy a credential out of Proton Pass** into a document, an email, a
   support ticket, a chat message, or an escalation (§8). If an engineer needs a
   key, they get it from Proton Pass themselves.
2. **Never paste a secret into anything you send.** When capturing logs for §8,
   scan them first — if a key or token appears, redact it.
3. **If a credential doesn't work, don't regenerate or reset it.** A rotated key
   silently breaks the live apps until every place that uses it is updated.
   Escalate instead (§6).

### 1.5 Signing in to DigitalOcean

1. Go to **https://cloud.digitalocean.com**.
2. Sign in as **`admin@cbmentors.org`** using the password from Proton Pass.
3. If a **two-factor code** is requested, it is on the same Proton Pass item
   (Proton Pass stores the authenticator code alongside the password — look for
   the rotating 6-digit code on the item). **If you're asked for a code you
   can't produce, stop.** Do not start account recovery, and do not request a
   password reset — escalate (§8). Account recovery on a shared login can lock
   everyone out, including the engineer.
4. In the left sidebar, click **Apps**.
5. Click the app you want — check the name against §1.2 before you do anything.

You are now on that app's dashboard. Everything in §1.6 and §1.7 happens here.

> **A quick sanity check that you're in the right place:** the production app's
> dashboard shows the domain **apps.clevelandbusinessmentors.org**. It also has
> its own DigitalOcean address, **cbm-client-intake-prod-a9li7.ondigitalocean.app**,
> which is worth knowing: if the custom domain ever has a certificate or DNS
> problem (§4-A2), that address reaches the same live app and lets you prove the
> app itself is fine.

### 1.6 The DigitalOcean console — where everything is

The app dashboard has a row of tabs. Here is what each one is for, and whether
you should be *reading* or *doing* on it.

| Tab | What's there | Your use |
|---|---|---|
| **Overview** | Whether each component is running, plus basic resource graphs | **Read.** First glance at "is anything obviously down" |
| **Activity** *(sometimes shown as Deployments)* | Every deployment, in order, with its outcome, and the build + deploy logs for each | **Read**, and **act**: this is where you Retry a failed deploy or Roll back a bad one (§5.6) |
| **Runtime Logs** | The live output of a running component. **Pick the component first** — `web` or `delivery-worker` | **Read.** This is where the actual error text lives (§5.10) |
| **Insights** | CPU, memory, restart counts over time | **Read.** A sawtooth restart pattern on `delivery-worker` means crash-looping (§4-A4) |
| **Console** | A command prompt *inside* the running container | **Don't.** Reading is harmless; running commands here is engineer territory (§6) |
| **Settings** | Components, environment variables, domains, alerts, resource sizes | **Read.** Changes here are almost all §6 |

Inside **Settings** you'll see the app's parts listed. Production has four:

| Part | Type | What it is |
|---|---|---|
| **`web`** | Service (`basic-xxs`, port 8080, **1 instance**) | The forms, the portal, all the staff tools |
| **`delivery-worker`** | Worker (`basic-xxs`, **1 instance**) | The background engine. Runs `python -m worker` |
| **`migrate`** | Pre-deploy job | Runs the database upgrade before each new version goes live. Runs once per deploy and exits — **a "stopped" migrate job is normal**, not a fault |
| **`cbm-db-prod`** | Managed Postgres database | Where submissions are safely stored before delivery. Test's is `cbm-db` |

> **The `migrate` job is the one that confuses people.** It is *supposed* to run
> and finish. If a deployment fails, though, check this job's log first — a
> failed database upgrade blocks the whole deploy, and its log says why.

### 1.7 Which setting lives where

Use this to *find* a setting so you can confirm its value. **Reading is always
fine. Changing almost anything here is §6** — the "Change it?" column tells you
which is which.

| What you're looking for | Where in the console | Change it? |
|---|---|---|
| Which CRM this app writes to | Settings → **`web`** → Environment Variables → `ESPO_BASE_URL`, `ESPO_DRY_RUN` | ❌ §6 |
| The CRM API key | Settings → `web` → Environment Variables → `ESPO_API_KEY` (encrypted — you'll see `EV[…]`, not the value) | ❌ §6 |
| The database connection | Settings → `web` / `delivery-worker` / `migrate` → `DATABASE_URL` | ❌ §6 |
| Whether a feature is switched on | Settings → the component → Environment Variables (see the component table just below) | ❌ §6 |
| The custom web address | Settings → **Domains** | ❌ §6 |
| Which GitHub branch deploys | Settings → the component → **Source** | ❌ §6 |
| How many instances run | Settings → the component → resource size / instance count | ❌ §6 — **never scale `delivery-worker` above 1** |
| DigitalOcean's own alerting | Settings → **Alerts** (separate from the app's alert emails in §7) | Ask first |
| The database's status and backups | Left sidebar → **Databases** → `cbm-db-prod` | ❌ §6 |
| Deployment history / rollback | **Activity** tab | ✅ §5.6 |
| Error messages | **Runtime Logs**, right component | ✅ read freely |

#### Which component gets which setting — and why it matters

A setting on the wrong component is a real and recurring cause of "the feature
is switched on but nothing happens". The rule: **`web` runs everything a person
touches; `delivery-worker` runs everything that happens on its own.** Features
that do both are set on *both*.

This is the **actual production configuration** — useful when you need to
confirm nothing has been quietly changed:

| Setting | On `web` | On `delivery-worker` | Controls |
|---|:---:|:---:|---|
| `ESPO_DRY_RUN`, `ESPO_BASE_URL`, `ESPO_API_KEY` | ✅ | ✅ | The CRM connection |
| `DATABASE_URL` | ✅ | ✅ | Where submissions are stored *(also on `migrate`)* |
| `ASYNC_DELIVERY` | ✅ | ✅ | Background delivery |
| `GMAIL_SYNC`, `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅ | ✅ | Email sync and sending |
| `GDRIVE_DOCS`, `GDRIVE_SHARED_DRIVE_ID`, `GDRIVE_IDENTITY` | ✅ | ✅ | Documents |
| `ANALYTICS_ENABLED` | ✅ | ✅ | Analytics |
| `ALERT_EMAIL_TO`, `ALERT_EMAIL_FROM` | ✅ | ✅ | **Who gets the alert emails in §7** |
| `OPS_MAILBOX` | ✅ | ✅ | The shared info@ identity and inbound capture |
| `APP_BASE_URL` | ✅ | ✅ | The clickable links inside alert emails |
| `SESSION_SECRET`, `SESSION_COOKIE_SECURE` | ✅ | — | Portal sign-in |
| `ALLOWED_ORIGINS` | ✅ | — | Browser security |
| `GCAL_EVENTS` | ✅ | — | Calendar events (created when a person saves a session) |
| `MENTOR_PROVISION_USERS`, `ESPO_PROVISION_USERNAME`, `ESPO_PROVISION_PASSWORD` | ✅ | — | Mentor login creation |
| `ASSIGN_ALLOWED_TEAMS`, `MENTOR_ADMIN_ALLOWED_TEAMS`, `MENTOR_TEAM_NAME` | ✅ | — | Three of the team gates |

Two things about this table that will otherwise waste your time:

- **`OPS_MAILBOX` is set on Production and deliberately NOT on Test.** Only one
  environment may poll the info@ inbox; setting it on both captures every
  incoming message twice (§4-E5). If you find it on Test, that's the fault —
  don't "fix" Production to match.
- **Most team gates are not environment variables at all.** Only the three above
  are set explicitly; the rest (Submission Admin, the session tools,
  Directories, Analytics, Events) run on the built-in defaults listed in §9.2.
  If you go looking for `OPS_ALLOWED_TEAMS` in the console you won't find it —
  that is correct, and it means the team name is exactly what §9.2 says.

---

## 2. The five-minute health check

Do this whenever you're asked "is everything OK?", and any time before you start
digging into a specific complaint. It rules out the whole bottom half of the
stack in a few minutes.

### Step 1 — the health page (the single most useful thing in this guide)

In a browser, open:

> **https://apps.clevelandbusinessmentors.org/healthz**

You get a block of text like this. **This is what healthy looks like** —
captured from Production on 2026-07-28:

```json
{"status":"ok","version":"0.187.0","environment":"production","dryRun":false,
 "forms":["client-intake","volunteer","info-request","partner","sponsor"],
 "assignments":true,"durableStore":true,"database":"ok",
 "worker":{"lastHeartbeatAgeSeconds":112.09,"backlog":0,
           "oldestPendingAgeSeconds":null,"stranded":0}}
```

Read it against this table:

| Field | Healthy value | What a wrong value means | What to do |
|---|---|---|---|
| `status` | `"ok"` | `"degraded"` = the app cannot reach its own database. Submissions **cannot be accepted**. | Check `database` below. Escalate. |
| `version` | matches Test's version | A version older than Test's means a deploy didn't finish. | DigitalOcean → the app → **Activity**. See §5.6. |
| `environment` | `"production"` | `"test"` or `"dev"` on the production address means the CRM target was changed. | **Escalate immediately** — do not fix this yourself (§6). |
| `dryRun` | `false` | `true` means the app is accepting forms and **writing nothing to the CRM**. Every submission is being stored but not delivered. | **Escalate immediately.** The data is not lost — it's queued — but nothing is reaching the CRM. |
| `forms` | all five listed | A missing form means that form is not being served. | Escalate. |
| `assignments` | `true` | `false` means every staff/mentor tool is switched off — the portal won't work. | Escalate. |
| `durableStore` | `true` | `false` means submissions are no longer being safely stored before delivery. | Escalate. |
| `database` | `"ok"` | `"error"` = the Postgres database is unreachable. | See §4-A3. |
| `worker.lastHeartbeatAgeSeconds` | **under 180** | The worker stamps this every few seconds. Over 180 it is considered dead and an alert fires. | §4-A4. |
| `worker.backlog` | `0`, or a small number that shrinks | Submissions waiting to be delivered. A handful mid-delivery is normal. | If it isn't shrinking, §4-B2. |
| `worker.oldestPendingAgeSeconds` | `null` or under ~300 | How long the oldest undelivered submission has waited. Over **1800** (30 min) an alert fires. | §4-B2. |
| `worker.stranded` | `0` | Submissions whose worker died mid-delivery. A healthy worker reclaims them automatically. | If it stays above 0 for more than ~20 minutes, §4-A4. |

Then do the same for **Test**:
https://cbm-client-intake-svxs3.ondigitalocean.app/healthz

Comparing the two is diagnostic in itself. If Production looks wrong and Test
looks right, the problem is Production-specific. If **both** are wrong in the
same way, suspect the change was made to both — or that the CRM (which they
share nothing but a code base with) isn't the cause at all.

> **Note on `version`:** both apps deploy from the same source, so they should
> normally show the **same** version number. A mismatch just means one finished
> deploying and the other hasn't yet (or failed). It is not itself an emergency.

### Step 2 — can people sign in?

Open **https://apps.clevelandbusinessmentors.org/** and sign in with your own
EspoCRM username and password.

- **You see the portal with app tiles** → the sign-in path and the CRM
  connection are both fine.
- **"Invalid credentials"** with a password you know is right → the app couldn't
  reach the CRM, or your CRM account is disabled. Sign in to the CRM directly to
  tell the two apart.
- **The page doesn't load at all** → §4-A1.

The portal is the honest test, because signing in **is** a live CRM call — the
app hands your username and password to EspoCRM and uses the token it gets back.
A successful portal login proves the app can talk to the CRM.

### Step 3 — is the CRM itself healthy?

Sign in to **https://crm.clevelandbusinessmentors.org** as an Admin and check:

1. **The CRM loads and you can open a Contact.** Obvious, but it's the check.
2. **Administration → Scheduled Jobs** — EspoCRM's own background jobs. Look for
   jobs whose *Last Run* is hours or days stale. (These drive EspoCRM's own
   notifications and workflows. **The intake apps do not depend on them** — a
   stalled EspoCRM cron will not stop submissions arriving — but it will stop
   the CRM's own email notifications.)
3. **Administration → Action History** — recent changes. This is where you find
   out that "someone changed something yesterday", which explains a great many
   sudden failures. Especially look for changes to **Entity Manager**, **Roles**,
   or **Teams**.

### Step 4 — did anything alert?

Check the alert mailbox (whoever `ALERT_EMAIL_TO` is set to; ask if you don't
know). Alert emails have subjects like:

> `[CBM Intake — production] 2 intake submissions were NOT delivered to the CRM…`

Every alert is decoded in §7. **A repeating alert every hour is normal
behaviour for an unresolved problem** — the same condition re-alerts once an
hour until it's actually cleared. It is not a new problem each time.

---

## 3. The weekly verification sweep

The five-minute check proves the machinery is running. This sweep proves the
*features* work. Run it weekly, and always after the CRM team has made changes.

You can do the whole thing signed in as yourself, in a browser. Nothing here
changes data except where noted.

### 3.1 The five public intake forms

Open each form and confirm it **loads and reaches its final step**:

| Form | Address (add to the app root) |
|---|---|
| Client intake | `/client-intake/` |
| Become a mentor | `/volunteer/` |
| Information request | `/info-request/` |
| Partner | `/partner/` |
| Sponsor | `/sponsor/` |

**Do this on Test, not Production,** if you want to actually submit one — a
Production submission creates real CRM records that someone then has to clean
up. On Production, walking the wizard *without* submitting is enough to prove
the form renders and its dropdowns are populated.

**What to look at:** every dropdown should have options in it. An **empty or
suspiciously short dropdown** is the classic sign that the CRM's list of values
was renamed and the form's copy is now out of date. That doesn't stop a
submission — the app quietly drops the unrecognised value rather than failing —
but **the field silently stores nothing**, which is worse. Report it (§8).

If you do submit a test one on Test: it should end on a confirmation with a
**reference number**, and within a minute or two appear in Submission Admin
(§3.3) and as a record in crm-test.

### 3.2 The delivery pipeline

The `/healthz` worker block (§2 Step 1) is the main check. Add one thing:

Open **Submission Admin** → https://apps.clevelandbusinessmentors.org/ops/
(you need the **Marketing Admin Team**).

- The count chips across the top are your queue. **Error** and **Held-** chips
  are the ones that need a person.
- A healthy week: a small number of open information requests being replied to,
  and **zero** in Error.
- Anything sitting in **Error** for more than a day should either be re-driven
  or closed with a reason (§5.1). Leaving it open is what generates the hourly
  alert email.

### 3.3 The portal and the staff/mentor tools

Sign in to the portal and confirm each tile you're entitled to **opens and shows
data**. The tiles you see depend on your CRM **Teams** — an admin sees all of
them.

| App | Address | Healthy looks like |
|---|---|---|
| Client Administration | `/assignments/` | A grid of engagements; the mentor dropdown on a row has names in it |
| Mentor Administration | `/mentoradmin/` | The mentor roster with completeness badges |
| My Mentor Profile | `/mentorprofile/` | *(mentors only — admins may see an error here; that's expected)* |
| Client Management | `/mentorsessions/` | The signed-in person's own engagements |
| Partner Management | `/partnersessions/` | All partner records |
| Funder Management | `/sponsorsessions/` | All funder records |
| Submission Admin | `/ops/` | The submission queue |
| Directories | `/directory/` | Browsable grids of Companies, Contacts, Mentors, Partners |
| My Email | `/myemail/` | Threads across the records you handle |
| Analytics | `/analytics/` | Dashboards that render (not "unavailable" panels) |

Two known-and-expected things, so you don't chase them:

- **An empty grid is not necessarily a fault.** Client Management shows only
  *your own* engagements. If you're an admin who mentors nobody, empty is
  correct.
- **The mentor dropdown in Client Administration** only lists mentors who are
  *simultaneously* Active, accepting new clients, **and** linked to a login user.
  An empty dropdown means no mentor passes all three — a data condition, not a
  bug.

### 3.4 Email

Check these three, in this order:

1. **Reading** — open any record with correspondence (a Client Management
   engagement, then its **Communications** tab). Recent messages should be
   there. If the newest message is more than a few hours old across *several*
   records, Gmail sync has stalled → §4-E1.
2. **Sending** — in Submission Admin, open any information request and start a
   reply. The compose window should open with the shared **info@** identity and
   your signature. *You do not have to send it* — that it opens and populates is
   the check.
3. **Inbound capture** — send a message from an outside address to
   **info@cbmentors.org**, then wait ~5 minutes and refresh Submission Admin.
   It should appear as a new held **info-email** item. This is the only check
   here that touches live data; discard your test item afterwards with the
   reason "test".

### 3.5 Documents (Google Drive)

Open a record in Client Management → **Documents** tab.

- Existing documents listed, and clicking one opens it → healthy.
- **"Coming soon" placeholder** → the Drive feature is switched off on this
  deployment. That's a configuration state, not a fault.
- Listed but won't open, or an upload fails → §4-F1.

### 3.6 Calendar, meetings and transcripts

- Open a **Scheduled** session in Client Management. It should show a meeting
  link. Cross-check that the event exists on the mentor's Google Calendar.
- Transcripts appear on completed sessions **after** the meeting, on a timer —
  not instantly. An empty transcript on a session from an hour ago is normal.
- **Sessions in the past never create a new calendar event.** Recording a
  meeting that already happened and seeing no calendar entry is correct
  behaviour, not a failure.

### 3.7 Analytics and Events

- **Analytics** — dashboards render. A single panel reading **"unavailable"** is
  a degraded metric, not a broken app; note which one and report it (§8).
- **Events** — the staff app at `/events/`. Note that the **public website
  webinars page still runs on the old Google Apps Script**; the Events app has
  not been cut over. Do not expect changes there to show on the public site.

### 3.8 CRM configuration integrity

The single highest-value CRM check, because it's the failure that hurts most:

**Administration → Users → (the app's API user) → Access**, and the same for
each **Role** attached to the staff Teams.

What you're confirming:

- Every Team that gates an app (§9.2) **still exists** and **still has its Role
  attached**. A team losing its role attachment has happened twice, and the
  symptom is "everyone in that team suddenly gets a permission error".
- The API user still has **create** rights on: Account, Contact,
  CClientProfile, CEngagement, CMentorProfile, CPartnerProfile,
  CSponsorProfile, CInformationRequest, CIntakeSubmission.

And in **Entity Manager**, confirm nobody has renamed or deleted a field the
apps write to. The schema-drift alert (§7) catches renamed *dropdown values*
automatically and emails you; it does **not** catch a deleted field.

---

## 4. Symptom index — someone reports a problem

Find the row that matches what was actually reported. Always run §2 first —
half of these are answered by the health page in thirty seconds.

### A. "It's down" / nothing works

| # | What's reported | Most likely cause | What to do |
|---|---|---|---|
| **A1** | A form or the portal won't load at all | A deploy is in progress, or the web process is crash-looping | Wait 3 minutes and retry. Then DigitalOcean → app → **Runtime Logs** on the **web** component. If it's restarting repeatedly, roll back (§5.6). |
| **A2** | Browser security/certificate warning | Domain or certificate issue | Open **https://cbm-client-intake-prod-a9li7.ondigitalocean.app/healthz** — the app's own address (§1.5). If that works, the app is healthy and the problem is only the domain/certificate. Usually self-resolves; if it persists past an hour, escalate — **do not change DNS or domain settings**. |
| **A3** | `/healthz` shows `"database":"error"` and `status: degraded` | The Postgres database is unreachable | Check DigitalOcean → **Databases** for the cluster's status and any maintenance event. **Submissions cannot be accepted while this is true** — this is a genuine outage. Escalate. |
| **A4** | Worker heartbeat over 180s, or `stranded` above 0 and not clearing | The delivery worker is dead or crash-looping | Runtime Logs on **delivery-worker**. Then restart it (§5.5). Nothing is lost meanwhile — submissions queue safely. |
| **A5** | Everything is fine but the version is behind Test | A deploy failed | DigitalOcean → **Activity** → open the failed deployment → read the build/deploy log. See §5.6. |

### B. "The form submitted but nothing appeared in the CRM"

By far the most common report. Work down in order:

| # | Check | If it's this |
|---|---|---|
| **B1** | Was it the **Dev** app (`lobster-app`)? | Dev writes to no CRM at all. Nothing is wrong. |
| **B2** | `/healthz` → `dryRun`, `backlog`, `oldestPendingAgeSeconds` | `dryRun:true` = nothing is being written anywhere → escalate. A growing backlog = the worker or the CRM is struggling; submissions are safe and will deliver when it recovers. |
| **B3** | Submission Admin (`/ops/`) — find it by the submitter's email | This tells you **exactly** what happened. The row's Intake status is the answer: **Completed** = it did reach the CRM (look again — often it's there under a slightly different name). **Error** = delivery failed; the row shows why. **Held-Duplicate** = the same person submitted the same form twice within 24 hours and the second was held for review on purpose. **Held-Spam** = the honeypot caught it. |
| **B4** | The row says **Error** — read "Why it failed" | A **validation/enum** message names the exact field: a dropdown value the CRM no longer has → §4-H1. A **403** names an entity and operation: the API user lost a permission → fix the Role in the CRM, then Re-drive (§5.1). A **timeout/5xx** → the CRM was down; just Re-drive. |
| **B5** | Nothing in Submission Admin at all | The submission never reached the app. Ask the submitter for their reference number. No reference number = they never got past the final step; ask them to try again in a private browser window (a stale cached page is the usual cause). |

### C. "I can't sign in" / "I can't see an app"

| # | Symptom | Cause | What to do |
|---|---|---|---|
| **C1** | Sign-in rejects a correct password | The CRM account is disabled, or the CRM is unreachable | Try signing in to the CRM directly. If that works and the portal doesn't, escalate. |
| **C2** | Signs in, but a tile is missing or opens to "you need the … team" | They're not in the Team that gates that app | CRM → Administration → Teams → add them (§5.4). Access is re-checked automatically within ~15 minutes — **no re-login needed**. |
| **C3** | They were just added to a team and still can't get in | The 15-minute membership refresh hasn't elapsed | Wait, or have them sign out and back in for an immediate refresh. |
| **C4** | Was working, now suddenly 401/redirected to sign-in | Their CRM token was revoked, or their password changed | Sign out and back in. |
| **C5** | A whole team lost access at once | The Team's Role attachment went missing in the CRM | CRM → Administration → **Users → Access** for one affected person to confirm, then re-attach the Role to the Team (§5.4). Check **Action History** to see who detached it. |

### D. "A mentor can't see their clients" / "permission denied when saving"

| # | Symptom | Cause | What to do |
|---|---|---|---|
| **D1** | A mentor's session tool grid is **empty** | Their `CMentorProfile` isn't linked to their login user — or, very commonly, there are **two profiles for them** and the records hang off the wrong (unlinked) one | CRM → find their CMentorProfile → confirm **Assigned User** is their login. Search for duplicate profiles under name variants ("Doug Bower" vs "Douglas Bower"). |
| **D2** | A mentor gets "permission denied" saving a contact or session | The record is missing their assignment stamp | Client Administration → right-click the engagement row → **Repair assignment…** (§5.3). This is exactly what that button is for. |
| **D3** | A **co-mentor** can't see an engagement | Co-mentor visibility needs the stamp too | Same fix: **Repair assignment…** on that engagement. |
| **D4** | Widespread, several mentors at once | Stamp drift across many records | The nightly repair job fixes this automatically. If it's urgent, Repair assignment on the specific engagements people are blocked on, and report the pattern (§8). |
| **D5** | A field shows but won't save | Either it's a **read-only mirror** of a linked record's field (edit it on the source record instead), or the Role has a field-level restriction | Check the Role's field permissions in the CRM as Admin. |

### E. Email

| # | Symptom | Cause | What to do |
|---|---|---|---|
| **E1** | Communications tabs stopped updating across many records | Gmail sync stalled | Runtime Logs on **delivery-worker**, filter for `gmail`. A repeatedly failing message holds the queue deliberately and is skipped automatically after 5 passes. Restart the worker (§5.5) if it's wedged; escalate if it recurs. |
| **E2** | One mentor's mail is missing, everyone else's is fine | Their mailbox is misconfigured, or their `cbmEmail` is wrong/missing | Mentor Administration → their record → check **CBM email**. |
| **E3** | Sending fails | The shared mailbox delegation has broken | Mentor Administration → **Email Setup** → **Test** (§5.7). This one button verifies the whole Google connection. |
| **E4** | Nothing arriving from info@ into Submission Admin | The inbound poller is off or stalled | Confirm on the worker's Runtime Logs (look for `inbound mailbox poll`). Restart the worker (§5.5). |
| **E5** | The same inbound message captured **twice** | The info@ poller is running on **both** Production and Test | This is a configuration fault. **Escalate** — do not change the setting yourself (§6). |
| **E6** | Alert emails stopped arriving | The sending mailbox is a group/alias rather than a real mailbox, or delegation broke | §5.7's test. Note that alerts must send from a **real licensed mailbox** — a group address will not work. |

### F. Documents (Google Drive)

| # | Symptom | Cause | What to do |
|---|---|---|---|
| **F1** | Documents listed but won't open / uploads fail | The service account lost its access to the shared drive | Check the **CBM Documents** shared drive membership in Google Admin — the service account must be a member. Escalate if it looks right. |
| **F2** | A mentor says they can't find a document in Drive directly | **Expected.** People aren't members of the shared drive by design; per-folder Commenter access is granted by the app | Not a fault. They access documents through the app. |
| **F3** | A document is in the app but archived/missing in Drive | An archive action moved it to `_Archived` | Look in the `_Archived` folder before treating it as lost. |

### G. Calendar, meetings, transcripts

| # | Symptom | Cause | What to do |
|---|---|---|---|
| **G1** | No calendar event for a scheduled session | The session start is in the past (>5 min) — new events are deliberately never created for past times | Not a fault. |
| **G2** | No calendar event for a **future** session | The Google delegation, or that mentor's `cbmEmail` | §5.7's test; check the mentor's CBM email. |
| **G3** | Duplicate calendar invitations | Someone is being invited at a personal address as well as their CBM one | Check the Contact's email vs the mentor's `cbmEmail`. Report it (§8). |
| **G4** | No transcript on a completed session | Normal for a while; also normal if transcription wasn't on, or the meeting was never held | The system stops looking after 14 days. Not a fault before then. |

### H. Data looks wrong

| # | Symptom | Cause | What to do |
|---|---|---|---|
| **H1** | A form field is saving as blank in the CRM | The CRM's list of allowed values was changed and the form's copy is stale. The app **drops** the unknown value rather than failing the whole submission — so it stores nothing, silently | This needs a code change to fix properly. Capture the exact field and value and escalate (§8). Meanwhile, staff can set the field by hand in the CRM. |
| **H2** | Duplicate client records from one submitter | Someone submitted twice | Second submissions within 24 hours are now held for review, so this should be rare going forward. Merge in the CRM as normal. |
| **H3** | An engagement stuck at "Assigned" despite a completed session | Known and investigated — **not a systemic fault** | It self-corrects on the next completed session save. Don't chase it. |
| **H4** | A "next session" shows that doesn't exist | Stale hand-entered value in the CRM | The grids derive next-session from real sessions only; correct the CRM field if it bothers anyone. |
| **H5** | The footer shows the new version but behaviour is old | The browser cached the old page | Hard-refresh (Ctrl+Shift+R) or use a private window. Always try this before diagnosing anything else. |

---

## 5. The remediation toolkit — what you may safely do

Every action here is designed for a human to press, is reversible or idempotent
(safe to repeat), and cannot lose data. **You do not need permission to use
these.** Record what you did and why, so the engineer can pick up the thread.

Anything below that starts with **DigitalOcean** assumes you're signed in per
§1.5 — and that you've checked the app name against §1.2, because
`cbm-client-intake` is the *test* one.

### 5.1 Re-drive a failed submission — Submission Admin

**Where:** `/ops/` → open the submission → **Re-drive** (labelled **Approve** on
a held item).

**What it does:** puts the submission back in the queue to be delivered to the
CRM again.

**When:** any row in **Error** whose cause you've fixed (a restored permission, a
CRM that's back up), or a held item you've reviewed and want delivered.

**Why it's safe:** delivery is *resumable* — it skips records it already
created. Re-driving a half-finished submission completes it rather than
duplicating it. It refuses to re-drive anything already Completed.

### 5.2 Close or discard a submission — Submission Admin

**Where:** `/ops/` → open the submission → **Close** (needs a reason) or
**Discard ▾** (pick a reason).

**When:** **Close** an item that's been dealt with, or an Error you've decided
not to re-drive. **Discard** spam or a test.

**Important:** closing an Error item is what **stops the hourly alert email**.
An alert that keeps arriving is telling you a row is still open. Discard is
reversible — a discarded row can be re-driven.

### 5.3 Repair an assignment — Client Administration

**Where:** `/assignments/` → **right-click** the engagement row → **Repair
assignment…**

**What it does:** re-applies the mentor's access stamps across the engagement,
its contacts, the client profile and the company.

**When:** a mentor or co-mentor gets permission errors on a specific client
(§4-D2, D3).

**Why it's safe:** it only ever *adds* access, never removes it, and re-running
it changes nothing that's already correct.

### 5.4 Fix team membership — EspoCRM

**Where:** CRM → Administration → **Teams** (add a person) or **Roles** (confirm
the role is attached to the team).

**When:** §4-C2 and C5.

**Remember:** gate by **Team**, not by Role — the apps check team membership.
Access refreshes within about 15 minutes without a re-login.

### 5.5 Restart a component — DigitalOcean

**Where:** DigitalOcean → the app → the component (**web** or
**delivery-worker**) → **Actions** → restart/redeploy that component.

**When:** the worker is wedged (§4-A4, E1, E4).

**Why it's safe:** the worker shuts down cleanly, finishing whatever it's
mid-way through. Anything not finished is picked up again automatically.

**The one caution:** there must only ever be **one** delivery-worker instance.
Restarting is fine; **scaling it to 2 is not** (§6).

### 5.6 Re-run or roll back a deploy — DigitalOcean

**Where:** DigitalOcean → the app → **Activity**.

- A **failed** deployment: open it, read the log, and use **Retry**. Transient
  build failures do happen.
- A deployment that **succeeded but broke something**: find the last known-good
  deployment and use **Rollback**.

**When:** §4-A1, A5.

**Note:** both Production and Test deploy from the same source, so a bad change
usually affects both. Roll back Production first.

### 5.7 Test the Google connection — Mentor Administration

**Where:** `/mentoradmin/` → **Email Setup** → **Test** *(you must be signed in
as a CRM **Admin** user)*.

**What it does:** proves in one click that the Google service account
authenticates and that domain-wide delegation is working.

**When:** anything email-, calendar-, or Drive-related is failing (§4-E3, E6,
G2). It's the fastest way to separate "Google connection broken" from
"something wrong with this one record".

### 5.8 Re-sync the CRM receipts — Submission Admin

**Where:** `/ops/` → **Sync receipts**.

**What it does:** re-checks every submission's receipt record in the CRM and
creates or corrects any that are missing or stale. It's the hourly background
job, on demand.

**When:** the CRM's intake receipts look out of step with Submission Admin.

**Why it's safe:** idempotent — press it twice, nothing bad happens.

### 5.9 Re-sync mentor statuses — Mentor Administration

**Where:** `/mentoradmin/` → **Update Mentor Status**.

**What it does:** sweeps the whole roster — verifies each mentor's login user
exists, checks their CBM mailbox, repairs one-sided user links, and refreshes
the completeness badges.

**When:** completeness badges look wrong, or after bulk mentor changes. This is
the standing repair button for the mentor roster.

### 5.10 Read the logs — DigitalOcean

**Where:** DigitalOcean → the app → the component → **Runtime Logs**.

You are looking for lines containing `ERROR` or `WARNING`. You don't need to
understand them — **copy them** (§8). Pick the right component: user-facing
problems are on **web**, everything background is on **delivery-worker**.

### 5.11 Clear the CRM cache — EspoCRM

**Where:** CRM → Administration → **Clear Cache**, and **Rebuild**.

**When:** after CRM configuration changes that don't seem to have taken effect.
Standard, safe EspoCRM administration.

---

## 6. Off-limits — never do these without the engineer

None of these are ever so urgent they can't wait for a phone call. Each one can
take the live forms offline, or write wrong data into the CRM that then has to
be untangled by hand.

**In the DigitalOcean console**

- ❌ **Don't delete an app.** That takes the public forms offline immediately.
- ❌ **Don't change any environment variable.** In particular:
  - `ESPO_BASE_URL` — points the app at a different CRM. Changing this on
    Production would write live submissions into the test CRM.
  - `ESPO_API_KEY` — breaks all CRM writes.
  - `ESPO_DRY_RUN` — silently stops all CRM writes.
  - `DATABASE_URL` — the app stops accepting submissions.
  - `ASYNC_DELIVERY` — turning this off while the worker is running risks
    **delivering every submission twice**.
  - `OPS_MAILBOX` — setting it on both environments double-captures every
    inbound email.
  - `GMAIL_RESYNC` — re-reads every mailbox on every deploy if left set.
- ❌ **Don't scale `delivery-worker` above 1 instance.** Exactly one must run.
- ❌ **Don't change the deploy branch or source repository.**

**In EspoCRM**

- ❌ **Don't delete or rename entities or fields** the apps write to (§3.8's
  list). A rename silently breaks writes with no error anywhere.
- ❌ **Don't edit or remove dropdown options** on fields the forms write to.
  Adding is safe; renaming and removing are not.
- ❌ **Don't delete `CIntakeSubmission` receipt records.** They're the CRM-side
  audit trail for every arrival.
- ❌ **Don't share the API key**, and don't regenerate it.
- ❌ **Don't disable or delete the provisioning admin service account** — mentor
  login creation and permission-team changes run as it.

**Credentials**

- ❌ **Don't rotate, regenerate or reset any key or password** — the EspoCRM API
  key, the provisioning account, the Google service account key. Every one of
  them is configured in more than one place; rotating one silently breaks the
  live apps until all of them are updated.
- ❌ **Don't reset the shared DigitalOcean password or run account recovery.**
  On a shared login that can lock out everyone, including the engineer.
- ❌ **Don't copy a credential out of Proton Pass** into a document, email,
  ticket, chat message or escalation (§1.4).
- ❌ **Don't add new people to the DigitalOcean account** or change who can sign
  in.

**Generally**

- ❌ **Don't "fix" data in bulk in the CRM** to work around an app problem.
  Fixing symptoms one by one is fine; a bulk edit can conflict with the repair
  jobs and make the original cause impossible to find.

---

## 7. Alerts — what each one means

Alerts arrive by email with the subject `[CBM Intake — production] …`. Each
condition re-sends at most **once an hour** while it remains unresolved.

| Alert says | What it means | Urgency | Your move |
|---|---|---|---|
| "*N* intake submissions were NOT delivered… need a decision" | Delivery failed permanently for these. The email names each one, why it failed, and links straight to it | **High** — real leads are stuck | Open each link. Fix the cause if it names one, then **Re-drive** (§5.1). If it can't be delivered, **Close with a reason** (§5.2) — that's what stops the alert |
| "Delivery backlog: the oldest undelivered submission is *N* minutes old" | Submissions are queuing. Usually the CRM is slow or down | **Medium** — nothing is lost | Check the CRM is up. It clears itself when the CRM recovers |
| "*N* submission(s) are stranded mid-delivery" | A worker died partway through. A running worker reclaims them automatically | **Medium** | If it doesn't clear within ~20 min, restart the worker (§5.5) |
| "The delivery worker's heartbeat is stale" | The worker is down or crash-looping. Submissions queue safely meanwhile | **High** | Runtime Logs on **delivery-worker**, then restart (§5.5) |
| "The delivery worker's heartbeat has recovered" | All clear | None | Nothing |
| "CRM schema drift: *Entity.field* no longer offers expected value(s)…" | Someone changed a dropdown in the CRM that a form or tool relies on | **Medium** — data will silently stop storing in that field | **Escalate** (§8) — fixing it properly needs a code change. Include the exact entity, field and values from the email |

---

## 8. Escalating: what to capture

Good escalations are answered in minutes; vague ones take days. Before you send,
collect:

1. **Which environment** — Production, Test, or Dev (the exact address).
2. **The `/healthz` output**, copied whole, from that environment.
3. **What was reported** — who, doing what, at roughly what time, and the exact
   error text or a screenshot of the whole screen (not a crop).
4. **The Runtime Log lines** around that time, from the right component
   (§5.10) — copy the `ERROR`/`WARNING` lines and a few lines either side.
5. **For a submission problem:** the reference number, or the submitter's email
   address, plus the row's Intake status and "Why it failed" text from
   Submission Admin.
6. **For a permission problem:** the person's CRM username and their Teams.
7. **Any recent change** — CRM → Administration → **Action History**, and
   DigitalOcean → **Activity**. "Nothing changed" is almost never true, and this
   is where you find out what did.
8. **What you already tried** from §5, and what happened.

> **Before you send it: check for secrets.** Logs and screenshots occasionally
> contain a key, token or connection string. Redact anything that looks like
> one. Never include a credential in an escalation — whoever picks it up has
> Proton Pass access already (§1.4).

---

## 9. Reference tables

### 9.1 Background jobs and their timings

Useful for answering "how long should I wait before this is a problem?"

| Job | Runs | Where |
|---|---|---|
| Deliver queued submissions | every 5 seconds | worker |
| Delivery retries after a transient failure | 1 min → 5 min → 30 min → 2 h → 6 h, then gives up and flags it | worker |
| Worker heartbeat | every cycle; **stale after 180 s** | worker |
| Alert threshold evaluation | every 5 min | worker |
| CRM schema-drift check | hourly | worker |
| Intake-receipt reconciliation | hourly | worker |
| Gmail sync | every 5 min | worker |
| Inbound info@ poll | every 5 min (sweeps a 2-day window) | worker |
| Meeting transcript retrieval | every 30 min, gives up after 14 days | worker |
| Assignment-stamp repair | nightly | worker |
| Google Drive permission reconciliation | nightly | worker |
| Analytics cache refresh | hourly | worker |
| Worker-liveness watch | every 2 min | web |
| Staff permission re-check | every 15 min per user | web |
| Duplicate-submission hold window | 24 hours | web |

**Rule of thumb:** anything on this list that hasn't happened in **three times**
its stated interval is worth investigating.

### 9.2 Which Team gates which app

Someone who can't open an app almost always needs one of these teams.

| App | Address | Team required |
|---|---|---|
| Client Administration | `/assignments/` | Client Administration Team |
| Mentor Administration | `/mentoradmin/` | Mentor Administration Team |
| My Mentor Profile | `/mentorprofile/` | Mentor Team |
| Client Management | `/mentorsessions/` | Mentor Team |
| Partner Management | `/partnersessions/` | Partner Management Team |
| Funder Management | `/sponsorsessions/` | Sponsor Management Team |
| Submission Admin | `/ops/` | Marketing Admin Team |
| Directories | `/directory/` | Mentor Team |
| Events | `/events/` | Marketing Admin Team |
| Analytics | `/analytics/` | Analytics Admin Team |

**CRM Admins always pass every gate.** That's worth remembering when you test
something as yourself and it works, but the person reporting it still can't do
it — you bypassed the very check that's blocking them. **Test permission
problems with a non-admin account, or by reading their Teams, not by trying it
yourself.**

### 9.3 What each intake form creates in the CRM

Useful when checking whether a submission really landed.

| Form | Records created |
|---|---|
| Client intake | Company → Contact → Client Profile → Engagement |
| Become a mentor | Contact (type Mentor) → Mentor Profile |
| Information request | Contact (Prospect), a Company if one was given, and an Information Request |
| Partner | Company (type Partner) → Contact → Partner Profile |
| Sponsor | Company (type Sponsor) → Contact → Sponsor Profile |

Every arrival also creates a **CIntakeSubmission** receipt record in the CRM,
whatever else happens. If you can't find the records above, look for the
receipt — it will tell you the status.

---

## 10. Glossary

- **App Platform** — DigitalOcean's managed hosting. Runs the apps; there's no
  server to maintain.
- **Backlog** — submissions accepted and safely stored but not yet written to
  the CRM.
- **Component** — one process inside an app: `web` or `delivery-worker`.
- **Dry-run** — a mode where forms work normally but write nothing to the CRM.
  Correct on Dev; a fault anywhere else.
- **Engagement** — a CBM mentoring relationship record (`CEngagement`).
- **Environment variable** — a named setting configured in the DigitalOcean
  console. See §6 before touching any.
- **Held** — a submission deliberately not delivered pending a person's review
  (duplicate, spam, or inbound email).
- **`/healthz`** — the status page every deployment serves (§2).
- **Idempotent** — safe to repeat; running it twice has the same effect as once.
- **Intake status** — what happened to an arrival: Received / Completed /
  Held- / Error / Discarded.
- **Needs attention** — the internal status behind an **Error** row.
- **Pre-deploy job** — a one-off task (here, `migrate`) that runs before a new
  version goes live. Finishing and stopping is success, not failure.
- **Proton Pass** — the password manager holding every credential in this guide
  (§1.4).
- **Re-drive** — put a submission back in the delivery queue.
- **Response status** — where the reply conversation stands, separate from
  intake status: New → In progress → Reply owed / Waiting on them → Responded →
  Closed.
- **Stamp** — the assignment record on a CRM row that gives a mentor access to
  it. Missing stamps cause permission errors (§4-D2).
- **Stranded** — a submission whose worker died partway through delivering it.
- **Receipt** — the `CIntakeSubmission` record created in the CRM for every
  arrival.

---

## Related documents

| Document | What it covers |
|---|---|
| `STAFF-DEPLOYMENT-GUIDE.md` | Plain-language console guide: deploying, going live, first-time setup |
| `DEPLOYMENT.md` | The engineer's runbook — command line, rollback, backups, reliability operations |
| `submission-admin.md` | Full functional reference for the `/ops` work queue |
| `email-management.md` | How CBM's email works end to end |
| `mentor-administration.md` | `/mentoradmin` functionality and the completeness rules |
| `intake-processing-overview.md` | The capture → worker → CRM pipeline in plain language |
| `OPEN-ITEMS.md` | Everything currently unresolved or owed |
| `CHANGELOG.md` | What changed in each version |
