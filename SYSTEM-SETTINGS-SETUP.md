# System Settings (`/setup`) — activation and use

Last Updated: 11-20-26 04:20 · Revision 1.6 — see change log at the end.

The admin-only page that changes this deployment's runtime settings from the
browser instead of editing a deployment overlay and running `doctl`. Plan and
the rulings behind it: `prds/system-settings-plan.md`.

**Audience:** an EspoCRM administrator. No CLI needed once it is switched on.

---

## 1. What it is for

There is no branch-level gate between a merge and production. Four App
Platform apps track `main` with `deploy_on_push: true`: the Business Mentors
Association's (the test system since 11-14-26), dev, crm-test and production.
The gate is the feature flag (`DEPLOYMENT.md` § *Reviewing a change before it
reaches production*), and this page is where you operate it:

1. merge the feature **dark** (its flag defaults off, so the production deploy
   changes nothing);
2. switch it on **here, on the Business Mentors Association's system** (the
   test system since 11-14-26), and review it live. crm-test is no longer
   where a change is reviewed;
3. switch it on **here, on production**.

Rollback is the same toggle. No overlay edit, no redeploy, and no chance of
tripping the `EV[…]` trap that encrypts an overlay's plaintext secrets.

## 2. Turning it on

**Status: on at the Business Mentors Association's system, crm-test and
production** (the Association's `/healthz` read `"page": true` 11-15-26).
crm-test since v0.190; **production since
2026-08-12**. Until then `SETUP_ENABLED` had only ever been added to the
crm-test overlay, so `/setup/` 404'd on prod and every prod flag change still
needed an overlay edit plus `doctl`. Step 3 above is now done, so the promotion
gate can be operated entirely from the browser.

Three env vars, all on the **web** component (the page is user-facing; the
worker only reads the overrides).

| Variable | Value | What it does |
|---|---|---|
| `SETUP_ENABLED` | `true` | The `/setup` page and the portal tile |
| `DATABASE_URL` | *(already set)* | Overrides live in `app_setting` — no database, no page |
| `SETTINGS_OVERRIDES` | *(leave unset)* | Defaults to `true`. This is the break-glass — see §6 |

Apply the overlay as usual:

```bash
doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml   # crm-test
doctl apps update aa1ddf69-f359-4b53-91ba-035cbed7bd53 --spec .do/app.prod-crm.yaml  # prod
```

⚠️ Edit the overlays **by hand**. Regenerating one with `doctl apps spec get`
encrypts every plaintext secret into an `EV[…]` blob.

The migration (`0025_app_setting`, `0026_app_job`) runs in the PRE_DEPLOY job
like every other. Confirm afterwards on `/healthz`:

```json
"settings": { "page": true, "overridesActive": true, "overrideCount": 0, "settingsVersion": 0 }
```

## 3. Who can use it

**EspoCRM administrators only.** Not a team gate — this page can reconfigure the
platform, so the audience is deliberately the smallest one available. The check
is the CRM user's own admin flag, re-read from the CRM on every session restore.
Non-admins get a 403 that says so, and the portal tile does not appear for them.

## 4. Using the page

### Settings tab

Curated groups — Features, Integrations, Email, Reliability, Team gates,
Presentation, Website — with everything else visible read-only behind **Show all**.

**Sub-tabs** (switch: *Settings page sub-tabs*, `SETTINGS_AREAS`, off by
default, no restart). With it on, the groups give way to ten sub-tabs, one per
application: Marketing Management, Events, Business Evaluation, Staff and
mentor tools, Email, Documents, calendar and meetings, Website and branding,
Team gates, Connected services and Platform. A setting sits where the screen it
changes is. An outside service's own account details (its *in use* switch,
keys, account numbers) are under Connected services; how a feature behaves is
with the feature. Inside a sub-tab, settings fall under short headings; each
heading shows its feature's main on/off switch first and the rest A to Z.

- **Search** matches each word you type on its own, in any order, against the
  setting's name, key, help, sub-tab and heading. While the box holds text, or
  *Only overridden* is ticked, the page lists the matches from every sub-tab,
  and each sub-tab's label shows its count; clicking one goes to its matches.
- **Settings that need a restart** sit in their own sub-tab with their badge.
  Any change waiting for a restart is named above the sub-tabs, and each name
  opens its setting.
- **With the Integrations tab on**, Connected services is left out (that tab
  holds the same settings). A feature setting that uses a service stays in its
  sub-tab and also shows on the service's own sub-tab; both show the same
  stored value.
- The page remembers the last sub-tab you opened, in this browser.

Switching it off puts the page back exactly as before. Plan and rulings:
`prds/settings-page-areas-plan.md`.

Each row shows where its value came from:

- **Default** — nobody has set it anywhere.
- **Deployment** — it comes from the overlay.
- **Override** — it was changed here. The row then also shows the overlay's
  value, so the overlay never silently lies about what the app is doing.

The **worker / both** badge tells you which process reads the setting. A
worker-side change takes up to `SETUP_REFRESH_SECONDS` (default 45s) to reach the
worker, because it is a separate container on its own timer.

### Presentation — whose name the app carries

The **Presentation** group holds the deployment's identity, added in
v0.205.0–v0.206.0: `Organisation name`, the four policy-document URLs the
consent checkbox links to on the public forms, and `Chapter design-token
override` (a stylesheet loaded after the base tokens that may redefine the
`--cbm-*` custom properties).

These behave differently from most settings here in one useful way: **they take
effect on the next page load, with no redeploy and no restart**, because the
name and the URLs are substituted into the page as it is served. Change one,
reload the page, and it is there. Changing it back works the same way.

Treat the policy URLs with more care than the rest — they are the documents a
member of the public is told they are agreeing to, so a typo points consent at
nothing.

Since v0.314.0 the organisation name, the acronym, the postal address, the
logo address, the website address and menu, and the design-token override sit
in the **Website** group instead. Their setting keys did not change.

### Website — what the chapter website shows

Step by step, for a chapter connecting its website: `CHAPTER-WEBSITE-SETUP.md`.

The **Website** group (v0.314.0, `prds/chapter-website-plan.md`) holds every
value the Association's chapter connector reads from
`GET /api/website/settings`, each set once: the chapter-wide values above, the
website's eight colours and two fonts, the contact email, telephone, employer
identification number, donation payment page and social media addresses, and
one switch per key page. Below the group's table, **Website images** uploads
the logo and the header graphic (PNG, JPEG or WebP, up to 2 MB; SVG is refused
because it can carry a script).

- **Nothing is served until `Chapter website connection` (`WEBSITE_API`, in
  Features) is on.** Off, every `/api/website/…` address answers 404. It is
  read per request, so no restart.
- **`Chapter website addresses` (`WEBSITE_ORIGINS`) names the website** that
  may read these addresses from a visitor's browser. It is separate from
  Allowed origins, which covers every address of the application.
- **A key page this release cannot serve is refused** with the reason (WT-10).
  Mentors, events and recordings can be switched on (v0.315.0); partners,
  sponsors and client stories are committee feature requests.
- **`Key page refresh` (`WEBSITE_CACHE_SECONDS`, 300)** is how long the key
  pages keep what they read from the CRM.
- Each value is checked on save: colours as `#RRGGBB`, the employer
  identification number as `12-3456789`, the payment page and social media
  addresses as https.

### Chapter News — news members see at sign-in

Two settings, both read per request (no restart). Publishers' guide:
`chapter-news.md`; plan `prds/home-page-plan.md` § 6.

- **Features → Chapter News** (`CHAPTER_NEWS`, off): the News section on the
  new home page, past news, and the Chapter News page for publishers. Needs
  **New home page** on for the home page's part, and the CRM's two Chapter
  News record types (`cchapternews-entities-crm-handoff.md`); until the CRM
  has them the section stays away and the page says so.
- **Team gates → Chapter News — publishers** (`NEWS_PUBLISH_ALLOWED_TEAMS`,
  default System Management Team): who sees the Chapter News tile and may
  write, publish and withdraw. Administrators always pass. Copy the team's
  name exactly.

### Settings that need a restart

Some settings are read once, when the application starts: the master
switches that mount an application (`EVENTS_ENABLED`, `ANALYTICS_ENABLED`,
`EVENTS_PUBLIC_API`, `ASSIGNMENTS_ENABLED`), the intake rate limits and body
cap, and `LOG_LEVEL`. They are in the **Restart required** group, and they
are editable (Doug's ruling, 08-28-26: a setting that cannot be seen or
changed here is unacceptable).

Each row shows the value **in force** beside the stored one. When the two
differ, the row is badged **Waiting for restart**. The stored value takes
effect at the next restart or deploy, because the application reads these
overrides at the very start of its startup, before it mounts anything.

**Reset to deployment value** deletes the override rather than writing the
default back, so the setting returns to whatever the overlay says.

### Temporary changes

Tick **Temporary** and give a review date. Nothing ever reverts on its own — an
unattended auto-revert is its own outage — but overdue ones are banner-flagged
on the page and logged by the worker every hour. This is the right mode for
`GMAIL_RESYNC`, which must be turned off again after one pass.

### Scoped rollout

Roll a feature out to named teams or people before everyone: that is how you
review a change in production as a real non-admin without exposing it to all
users. **Only web-side settings can be scoped** — the worker has no signed-in
user to evaluate a scope against, and the page refuses rather than offering a
control that would do nothing.

A scoped override deliberately does **not** change the process-wide
configuration; it applies only to matching users.

### Feature readiness tab

Per feature: the flag, the settings that must be non-empty, the CRM fields that
must exist, which process runs it, and how long ago the worker last checked in.
It exists for two specific failure modes — a flag set on the wrong component,
and a feature staying dark because its CRM field hasn't been built yet. A
worker feature that is on while the worker is silent is called out explicitly.

### Environment diff tab

"What is on in test that is off in prod?" Needs both deployments configured with
each other's URL and a shared token:

| Variable | crm-test | prod |
|---|---|---|
| `SETUP_PEER_URL` | prod's root URL | crm-test's root URL |
| `SETUP_PEER_TOKEN` | the same random string on both | the same random string on both |

Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
The snapshot endpoint is closed unless a token is set, carries **no secret
values** — a secret contributes only "set / not set" — and is authorised by
constant-time token comparison, not by the staff session.

### Operations tab

Maintenance jobs that used to need a container console. A job that changes
anything runs in two steps: **produce a plan → review it → apply that plan.** If
the plan has changed by the time you apply, nothing runs and you review the new
one. Applying requires a reason, which is recorded with the run.

Some mutating routines are listed but **not runnable**: they write as they go
and have no plan-producing pass, so they cannot honour dry-run-then-apply yet.
They say so instead of offering a button that would skip the review.

**The plan is the point — read it before applying.** A dry run prints exactly
what it would do: for the attachment cleanup, every document it would archive,
by record, with its filename, type, date and id, and a count line at the end.
Applying re-derives that plan and compares it to the one you read, so the two
are bound together. Every run keeps its report: **Recent runs** has a **Report**
column, and expanding a row shows what that run printed — which is how an apply
stays auditable against the plan it came from. (Before v0.208.1 the report was
rendered and then immediately destroyed by the page's own refresh, so a run
showed "done" and nothing else.)

**Clean up excluded email attachments** archives the documents that inbound mail
auto-filed but whose file type is now on the never-file list — calendar invites
above all (see *Email → Never file these attachments* on the Settings tab).
"Archive" is the same move as the Archive button on a record's Documents tab:
the file goes to that record folder's `_Archived` subfolder and leaves the
default list. Nothing is deleted, anything can be restored, and a file a person
uploaded by hand is never touched — the sweep only considers documents whose
type is *Email attachment*.

### History tab

Every change: old value → new value, who, when, and why. Also written to
`CActionLog` through the standard action-log path.

## 5. What can never be changed here

**Every setting is editable unless a change is genuinely impossible** (Doug's
ruling, 08-28-26). Three settings are on the page, read-only, each with its
reason. The server enforces this, not only the page:

- **`DATABASE_URL`.** The override table lives inside the database it names,
  so an override moving the application to another database would be left
  behind in the old one.
- **`APP_ENCRYPTION_KEY`.** Changing it makes every stored secret permanently
  unreadable. Rotating it is an engineer's job (`DEPLOYMENT.md`).
- **`RELEASE_TAG`.** The release stamp travels inside the image. A stored
  override would make the deployment misreport which release it runs.

Everything else, including the settings that used to be locked, is editable
through the **checked save**:

- **Secrets are editable but never readable.** You can set a new value. You
  can never read the old one back. Each secret is stored encrypted, and
  without an encryption key it is refused, never stored in plain text.
  History records *(secret set)*, never the value.
- **The CRM address, the CRM key, dry run, the provisioning account and the
  integration credentials are tried before they are stored.** A value the
  outside service rejects is refused with the service's own error. A check
  that cannot reach the service reads unknown, and unknown does not block
  the save, so a fix made during an outage is not stopped by it. A change
  that leaves the system not working is undone automatically.
- **`SETUP_ENABLED`, `SETTINGS_OVERRIDES`, `SESSION_SECRET`, the secure-cookie
  setting and the allowed origins apply with a 10-minute countdown.** Each
  one undoes itself unless an administrator confirms it within 10 minutes.
  No check can detect being locked out, because the application is working
  and simply will not let anyone back in. The countdown is the protection.

## 6. Break-glass

`SETTINGS_OVERRIDES=false` in the overlay disables the override layer entirely
and the app runs on pure environment configuration, whatever is in the table.
The page still renders and says so in a banner, so nobody wonders why a toggle
did nothing.

Related safety property: if the override lookup fails — database unreachable,
query error — the app falls back to **the overlay's values**, not to code
defaults, and logs a warning. A database incident must not silently reconfigure
the application.

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/setup/` 404s | `SETUP_ENABLED` unset, or no `DATABASE_URL` | Both are required (§2) |
| Tile missing on the portal | You are not an EspoCRM admin | §3 |
| Saved a flag, nothing changed | The row is badged **Waiting for restart** | Restart or redeploy (§4, *Settings that need a restart*) |
| Saved a worker flag, nothing happened yet | The worker refreshes on its own timer | Wait `SETUP_REFRESH_SECONDS`; compare `settingsVersion` on each component's `/healthz` |
| Saves succeed but have no effect | Break-glass is off | §6 |
| Diff says "No peer configured" | `SETUP_PEER_URL` / `SETUP_PEER_TOKEN` missing | §4 |
| Diff says the peer rejected our token | The two tokens differ | Set the same value on both |
| A job says it cannot be run | It has no dry-run mode | §4, Operations |

## 8. The Integrations tab

An integration is an outside service this application calls with its own
credentials: EspoCRM, Google Workspace, Zoom Meetings, Zoom Webinars,
Fathom, Constant Contact, Lob, Twilio, Anthropic and YouTube. The
Integrations tab gives each one a sub-tab of its own. On that sub-tab an
administrator sets the integration up in the setup dialog, tests it, and changes
its settings. Built v0.321.0 to v0.335.0. Design and rulings:
`prds/integrations-tab-plan.md`.

### 8.1 The switch

**`INTEGRATIONS_TAB`** (*Integrations tab*, in the Features group) turns it on.
It is off by default and read on every request, so no restart is needed.

While the switch is **off**, the page is exactly as it was before the tab
existed. The integration settings stay in the Settings tab's Integrations
and CRM connection groups, and nothing runs at night.

When the switch is **on**, four things change:

- An **Integrations** tab appears beside Settings, with one sub-tab per
  integration.
- Every integration setting **moves** to its sub-tab. The Settings tab's
  Integrations and CRM connection groups disappear. A setting appears in
  one place only.
- **Feature readiness** links each row to its sub-tab, and leaves out the
  warnings of an integration marked not in use.
- The worker runs the **nightly integration test** (§ 8.7).

A deep link opens one sub-tab: `/setup/#integrations/zoom_meetings`.

### 8.2 What a sub-tab shows: the status screen

Each sub-tab is a **status screen** (v0.337.0, Doug's rulings 11-15-26). It
shows where the integration stands and offers one thing to do next. Every
process runs in a dialog over it (§ 8.5).

1. **The heading and its state.** The state is one of *Set up*, *Needs
   attention* (with how many checks fail), *Not set up*, *Not tested yet*,
   *Setup not finished*, *Setup in progress* (with the step), or *Not used by
   this chapter*. The same state shows as a coloured dot on the sub-tab:
   red needs attention, green is set up, amber is a setup in progress, grey
   is not set up or not tested, and an empty ring is not used.
2. **The status line**, for example *"in use · on (zoom_meetings_events) ·
   credentials set · last test passed 11-15-26 14:02, run by admin"*.
   EspoCRM shows *always in use* and whether dry run is on. Missing
   credentials are named one by one.
3. **One button, chosen by the state**, checked in this order:
   - not used by this chapter: **Setup**;
   - a setup left partway through: **Continue setup**;
   - the last test failed or could not be completed: **Fix**;
   - no test yet: **Setup** when credentials are missing, otherwise **Test
     Integration**;
   - the last test passed: **Setup** when a setup step still fails,
     otherwise **Test Integration**.
4. **Other Actions ▾** lists the rest, each with a line saying what it
   does: **Test Integration**, **Review the setup** (opens the setup at its
   first step, to see or change any answer) and **Start the setup again**
   (opens it at the first step that does not pass). The button's own action
   is never repeated there.
5. **Checks from the last test**, failed checks first, then **Integration
   facts** (§ 8.4).
6. **Settings and what uses <integration>**, folded. It holds the
   integration's settings, edited exactly as on the Settings tab through the
   same checked save; Google Workspace's sections (Credentials, Drive,
   Calendar, Meet, Gmail and the shared mailbox, Workspace accounts); the
   **Used by** list, linking each setting to its place on the Settings tab
   (a row marked *needs <integration>* cannot work without it); and the
   runbooks. This browser remembers whether you left it open.

Opening the page never calls an outside service. The state, the checks and
the setup's place are worked out from the stored settings and the last
stored test.

### 8.3 "In use" and its two refusals

Every integration except EspoCRM has an *in use* setting, for example
*Zoom Meetings in use* (`zoom_meetings_in_use`). Its default is Yes. EspoCRM
is always in use, and its warnings are never hidden.

An integration marked **not in use** keeps its sub-tab, labelled *Not used
by this chapter*. Its settings can still be changed. Its warnings leave
Feature readiness, and the nightly test skips it.

The save refuses two changes, with HTTP 409 and a message that names the
setting:

- **Marking an integration not in use while any of its features is
  switched on.** The message names each switch that is on, and says to
  switch them off first.
- **Switching a feature on while its integration is marked not in use.** The
  message says where to mark it in use first: *Integrations, <integration>,
  <integration> in use*.

"Its features" means the integration's own switches and the features
elsewhere that cannot work without it. Two examples: text campaigns need
Twilio, and event confirmations need Google Workspace. A feature switched on
for only some teams or people counts as on. A reset to the deployment value
is checked the same way as a save.

### 8.4 Test Integration

**Test Integration** runs every check needed to prove the integration works
end to end, not only that a key is set. Every check only reads. Nothing is
changed in the outside service.

Each check shows one line with one of four results:

- **✓ passed.** The check proved what it checks.
- **✗ failed.** The service answered and the answer is wrong, for example a
  rejected key or a missing permission. The line says what is wrong, often
  in the vendor's own words.
- **? unknown.** The check could not get an answer, for example a timeout or
  a network fault. **Unknown never counts as passed.** Run the test again
  later. A check that cannot read its answer never reports passed.
- **– not checked.** The feature it serves is switched off, or there is
  nothing to read yet (no past meeting, for example). It does not count
  against the test.

The summary line reads *passed*, *failed* or *could not be completed*. It
names who ran the test, whether it was the nightly run, and how long it
took. Below the checks, **Integration facts** report what the test learned
about the service: the EspoCRM version, the Zoom account, the Google
permissions granted, and the like.

Each check has 12 seconds and the whole test 30. One test per integration
runs at a time. Every detail line is cleaned of every secret's value before
it is shown or stored. A run is recorded in the action log.

**Google Workspace's *Delegation: the whole grant* line** asks for a token
for every scope of guide step 10.3, whatever is switched on. It can fail
the button on a deployment whose grant lacks a scope that no switched-on
feature needs. The guide grants them all. The nightly run skips this line.

**Test Integration** runs in place, from the button or from Other Actions,
and the status screen updates. When a test does not pass, the button
becomes **Fix**.

### 8.5 The setup dialog

**Setup**, **Fix**, **Continue setup**, **Review the setup** and **Start the
setup again** all open the **setup dialog** over the status screen. It sets
an integration up, or repairs it, one step at a time. Each step is one
action, with **What** it is, **Why** it matters and **How** to do it. A
value to paste has its own **Copy** button. A step is checked before the
next one appears. The heading names the process and the step, for example
*"Fix EspoCRM · Step 3 of 9"*, with a progress bar.

The steps are written in the chapter deployment guide's step files
(`prds/chapter-network/deployment-guide/steps/`), so the guide and the
setup cannot disagree. Work done before this application exists, such as
building the Google Workspace account or the CRM server, stays in the guide
alone.

A step asks for one of five things. The strong button sits on the right of
the dialog's foot; **← Back** sits on the left.

- **An answer** to a question, such as *Does this chapter use Zoom
  Meetings?* An answer can save settings and choose which steps follow.
  Answering No to the first question ends the setup. The integration is
  then marked not used by this chapter.
- **A value** in a box, then **Save and check**. A secret's box never shows
  the stored value. It shows only *Set — paste a new value to replace it*.
- **A button** that the application carries out. Google Workspace's shared
  drive and Twilio's sender number are the two. The value it finds is saved
  for you.
- **Connect**, for Constant Contact. It leaves for Constant Contact's
  sign-in. On the way back the page reopens the dialog on that step, and
  you click **Done**.
- **Done**, for an action carried out in the vendor's own screens.

**Where it opens.** **Fix** and **Start the setup again** open at the first
step whose check fails; the steps before it are taken as done. **Review the
setup** opens at step 1. **Continue setup** opens where the setup was left.
When the last step passes, the dialog says *"<integration> is set up.
Every check passes."*

**← Back** returns to the step before, including the steps the setup opened
past (v0.336.1). Settings already saved stay saved, and an earlier answer
still chooses its branch.

**Close**, **Escape** or a click outside the dialog closes it and keeps
its place. Closing never undoes a step. **The place is kept for the whole
deployment**: a second administrator sees *Setup in progress* and
**Continue setup**. Every setting a step saves goes through the checked
save, as the administrator who clicked, with the reason *set in the setup
wizard*. It shows on the History tab like any other change.

**A failed step** stays open. It shows **Not done yet:** with the check's
own words, and **If not:** with the guide's advice for that case. **Fix**
opens with the stored test's failure already shown, before anything is
clicked. On a step that has failed, **Done** reads **Check again**. A value
that was saved and then undone automatically says so. A refusal from the
checked save is shown in its own words.

### 8.6 Ask Claude about this

A failed step offers **Ask Claude about this**, a button in the dialog's foot. Claude is called only when
someone clicks it. It reads that failure, the integration's settings, its
readiness rows, its last test, its recent errors, its guide steps and its
runbook, and the vendor's own documentation sites. It answers on that
screen, normally within a minute. The page updates by itself.

- **Claude only reads.** It cannot change a setting or call the vendor.
- **Claude never sees a secret's value**, only whether each secret is set
  and when it last changed.
- **It costs money**, so a failed step says what Ask Claude has spent this
  month against the monthly budget. Each answer shows its own cost. One
  answer stops itself at $5.
- **Once the month's spending reaches the budget, Ask Claude is refused.**
  The message says to raise the budget.

Two settings on the Anthropic sub-tab control it. *Integration agent model*
(`INTEGRATION_AGENT_MODEL`) has the default `claude-opus-5-5`. *Integration
agent monthly budget* (`INTEGRATION_AGENT_MONTHLY_BUDGET`) has the default
$25. Ask Claude also needs the Anthropic API key.

### 8.7 The nightly integration test

While the switch is on, the **worker** runs the integration test once a day.
The hour is set by `INTEGRATION_TEST_HOUR`, default 6. The time zone is set
by `INTEGRATION_TEST_TZ`, default America/New_York. Both are in the
Reliability group. The run covers EspoCRM always, plus each integration
that is in use and has at least one feature switched on. YouTube has no
switch, so it never runs at night. Claude is never called at night.

A few values are given to the web process only: the EspoCRM provisioning
account, Lob's webhook secret, and Google's All Members group. Their checks
are skipped at night unless the value was saved here. The Test Integration
button checks them.

**The alert** goes to the usual alert address:

- **A failure** alerts when its failed checks differ from the last night's.
  An unchanged failure is not repeated.
- **"Could not be completed"** alerts once, on the third night in a row.
- **A recovery** is reported once.

A failure's alert names each failed check, and ends with a link of the form
`<application address>/setup/#integrations/<integration>/wizard`. The link
opens that integration's status screen, whose button reads **Fix**. Nothing
changes until a button is clicked.

The alert remembers through the stored test runs, so a deploy or a restart
never repeats one. Every run, manual or nightly, is kept in
`integration_test_run`. On crm-test that table is emptied by the nightly
reset, so its history is one day long.

### 8.8 Switching it off

Set `INTEGRATIONS_TAB` back to off. The settings return to the Settings
tab's groups with their values unchanged, the sub-tabs disappear, and the
nightly test stops. Nothing is lost: the setup's place, the stored test
runs and Ask Claude's spending stay in the database for when it is switched
on again.

The two refusals in § 8.3 stay active with the switch off. With every
*in use* setting at its default of Yes they refuse nothing.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.6 | 11-20-26 04:20 | Claude (Claude Code) | § 4: Chapter News, its switch and its publishers' team (v0.353.0). |
| 1.5 | 11-18-26 01:39 | Claude (Claude Code) | § 4: the Settings tab's sub-tabs, word-by-word search, and where restart-required and service settings go (`SETTINGS_AREAS`, v0.345.0). |
| 1.4 | 11-15-26 18:38 | Claude (Claude Code) | § 8.2, § 8.4 to § 8.7: each sub-tab is a status screen with one button and Other Actions ▾; Setup, Fix and Review run in the setup dialog (v0.337.0, Doug's rulings 11-15-26). |
| 1.3 | 11-15-26 15:04 | Claude (Claude Code) | § 8.5: Back reaches the screens the wizard opened past, and Review the screens (v0.336.1). |
| 1.2 | 11-15-26 13:41 | Claude (Claude Code) | Stale text corrected (Doug's approval 11-15-26): § 1 and § 2 name the Business Mentors Association's system as the test system; § 5 rewritten to the 08-28-26 ruling (three read-only settings; secrets and the CRM connection editable through the checked save; the 10-minute countdown); § 4's "What this page cannot switch on" became "Settings that need a restart"; the troubleshooting row follows. |
| 1.1 | 11-15-26 13:30 | Claude (Claude Code) | § 8, the Integrations tab (v0.321.0 to v0.335.0), written from what was built: the switch, the sub-tabs, "in use" and its refusals, Test Integration, the set-up wizard, Ask Claude and its budget, the nightly test and its alert, switching it off. Revision header and change log added. |
| 1.0 | 11-09-26 | — | The document as it stood before the revision header was added (last changed with the chapter website runbook). |
