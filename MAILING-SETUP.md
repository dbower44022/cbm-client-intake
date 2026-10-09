# Mailing list sync — Constant Contact setup and activation runbook

Last Updated: 10-09-26 02:17 · Revision 0.6 — change log at the end.

How to register this application with Constant Contact, connect one
deployment to one Constant Contact account, and switch the audience push on.
Written for **crm-test first**; production is a separate, later pass with its
own Constant Contact application. Plan and the rulings behind it:
`prds/mailing-list-and-event-sponsorship-plan.md` (§ 11 is the Phase C
design this runbook follows).

**Status (2026-10-09): sections 2, 3 and 4 are BUILT** — sections 2 and 3
in v0.243.0 (deployed to crm-test and production 2026-10-09 02:10, dark:
nothing connects until an administrator does), section 4 in v0.244.0
(deployed to both 2026-10-09 09:33): the push and pull as two Operations jobs and the worker's
nightly and hourly timers behind the *Mailing list sync* switch. Doug's live
run of sections 2–4 on crm-test is the first browser pass. **Ruled 2026-10-07 (plan § 11.11): crm-test
connects to a separate Constant Contact account of its own**, created in
section 0a; the organisation's real account is production's alone.

**crm-test: sections 0a and 1 are DONE (2026-10-08, Doug).** The separate
account exists (owned by Doug's own CBM mailbox — the only user who can
authorise crm-test's connection, since a developer application is private
to its creator); the application `Cleveland Business Mentors applications —
TEST` exists with the crm-test redirect address saved; the API key and
client secret are in Doug's password manager; the details screen reads
*OAuth Type: Authorization Code/Implicit* and *Rotating Refresh Tokens*
(read back from the screen 2026-10-08). Section 2 waits on the Phase C
build. Production's sections 1 to 4 wait on access to the real account.

**Audience:** an EspoCRM administrator who can sign in to the organisation's
Constant Contact account. No command line is needed.

---

## 0. Before you start

Three facts shape everything below. Each was read from the vendor's own
developer documentation on 2026-10-07; sources are in plan § 10.

- **A new developer application is private to the Constant Contact user who
  created it.** Only that user can authorise it. So the application must be
  created while signed in as the Constant Contact user that will connect the
  deployment — the organisation-owned login staff use to send, never a
  personal developer sign-up. Opening an application to other users means
  telephoning the vendor's support line and an approval process; this design
  never needs that.
- **One Constant Contact account, one developer application, one
  deployment.** Production connects to the organisation's real account.
  crm-test connects to whatever the open decision settles on, through its
  own application. The dev deployment never connects (it has no CRM to push
  from). Boston registers its own application in its own account when its
  turn comes.
- **The redirect address must match, character for character, an address
  registered on the application.** This application builds the address from
  its `APP_BASE_URL` setting, never from the browser's address bar, so the
  address to register is fixed per deployment:

| Deployment | Redirect address to register |
|---|---|
| production | `https://apps.clevelandbusinessmentors.org/api/setup/mailing/callback` |
| crm-test | `https://cbm-client-intake-svxs3.ondigitalocean.app/api/setup/mailing/callback` |
| Boston | `https://apps.bbmentors.org/api/setup/mailing/callback` |

Once the Settings page panel exists it shows this exact address with a copy
button, so nobody types it. Until then, copy it from the table.

You will need:

- For production: the sign-in for the organisation's Constant Contact
  account. For crm-test: the sign-in of the separate account section 0a
  creates.
- Somewhere safe to hold two values for a few minutes: the **API key** (the
  application's public identifier, also called the client ID) and the
  **client secret** (shown once, never again).

---

## 0a. crm-test only — create the separate Constant Contact account

Why this section exists: the ruling is that crm-test never touches the
organisation's real Constant Contact account. The My Applications page needs
a Constant Contact account to sign in with, and the vendor's sign-up creates
a trial account that is crm-test's. Skip this section for production.

(The address the vendor's older quick-start guide gives for a developer
sign-in, `v3.developer.constantcontact.com/login/…`, answers *page not
found* — verified 2026-10-08. The current developer portal says: "You need
to have a Constant Contact account to use My Applications.")

1. In a browser where you are **not** signed in to Constant Contact (a
   private window is simplest), open this address:
   ```
   https://app.constantcontact.com/pages/dma/portal
   ```
   You should see a Constant Contact sign-in page (the address bar moves to
   `login.constantcontact.com`), with a **Sign up** link or button on it.
   If you see the My Applications page straight away, the browser is
   already signed in to a Constant Contact account; stop and tell me which
   account name it shows.

2. On that sign-in page, click **Sign up**.
   You should see Constant Contact's account sign-up form. It asks for at
   least an email address and a password; it may also ask for your name,
   organisation name and phone number, and it may describe itself as a free
   trial. If it asks for a credit card, stop and tell me.

3. In the sign-up form, in the email box, type an address the organisation
   controls that is not already a Constant Contact user — the test mailbox
   the sandbox already uses is the natural choice. Where it asks for an
   organisation name, type:
   ```
   Cleveland Business Mentors — TEST
   ```
   Fill the remaining boxes and store the password with the other sandbox
   sign-ins.

4. In the sign-up form, click the button that completes it (its label is
   **Get Started**, **Sign up** or **Create account**, depending on the
   layout).
   You should see either the My Applications page or the Constant Contact
   product's home screen. If you are asked to confirm the email address
   first, do so in that mailbox and then continue. If the page says the
   email is already in use, stop and tell me which address you used.

5. If step 4 left you on the Constant Contact product's home screen rather
   than My Applications, open this address again in the same browser:
   ```
   https://app.constantcontact.com/pages/dma/portal
   ```
   You should see a page headed **My Applications** with a **New
   Application** button. If instead you see a message about the API or
   developer access being unavailable to this account, stop and tell me its
   exact wording.

Continue with section 1, signed in as this new account. (How long the trial
account lives is not stated in the vendor's documentation; if it expires,
repeat this section and section 1, then section 3.)

---

## 1. In the Constant Contact developer portal — create the application

Why this section exists: the application is how Constant Contact recognises
this deployment, and the redirect address registered on it is the only
address Constant Contact will send an authorisation back to.

1. In a browser, signed in to Constant Contact as the organisation-owned
   user (for crm-test: the account from section 0a), open this address:
   ```
   https://app.constantcontact.com/pages/dma/portal
   ```
   You should see a page headed **My Applications**, with a **New
   Application** button. If instead you see a sign-up form asking for an
   organisation name and phone number, you are not signed in as an existing
   Constant Contact user; stop and tell me exactly what the page shows.

2. On the My Applications page, click **New Application**.
   You should see a dialog asking for an application name.

3. In the New Application dialog, in the name box, type:
   ```
   Cleveland Business Mentors applications
   ```
   (for crm-test type `Cleveland Business Mentors applications — TEST`; for
   Boston, Boston's organisation name). This is the name the authorising
   user sees on the permission screen, so it must say whose application it
   is.

4. In the same dialog, under the OAuth2 flow choice, select **Authorization
   Code Flow and Implicit Flow**. (The other two choices, PKCE and Device
   Authorization, are for applications that cannot keep a secret; this one
   runs on a server and can.)

5. In the same dialog, under the refresh-token method, select **Rotating
   Refresh Tokens** (the other choice reads *Long Lived Refresh Tokens*;
   wording verified on the application's details screen 2026-10-08). (The
   application stores each new refresh token the moment it
   receives one and lets only one process refresh at a time, which is what
   makes rotation safe here.)

6. In the same dialog, click **Create**.
   You should see the My Applications page again with the new application
   listed under **Applications**.

7. On the My Applications page, next to the new application's name, click
   **edit**.
   You should see the application's details, including a value labelled
   **API Key**.

8. On the application's details screen, copy the **API Key** value into
   your safe place, labelled *API key*.
   It is a long string of letters, digits and hyphens.

9. On the same screen, find the box for the redirect address. It is labelled
   **Redirect URI** or **Redirect URIs**, depending on the layout; it may
   already hold `http://localhost`. Replace its contents with the address
   for this deployment from the table in section 0 — for crm-test:
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/api/setup/mailing/callback
   ```
   You should see exactly that address in the box, with `https` at the
   start and `callback` at the end and nothing after it. If the screen
   offers no such box at all, stop and tell me exactly which fields the
   screen shows.

10. On the same screen, click **Generate Client Secret**.
    You should see a secret value and a warning that it is shown only once.

11. Copy the client secret into your safe place, labelled *client secret*.
    If you lose it, come back to this screen and generate a new one; the
    old one stops working the moment you do.

12. On the same screen, click **Save**.
    You should see the My Applications page or the details screen with no
    unsaved-changes warning. If a message says the redirect address is not
    valid, stop and tell me the exact wording.

**What the details screen shows afterwards** (read back on crm-test's
application 2026-10-08, so the build can rely on it): a heading
*Application OAuth2 Settings*; *OAuth Type: Authorization Code/Implicit*;
a *Private* notice saying the application can only use data from the
creating account and that making it public means telephoning the vendor's
support line (this is the fact section 0 rests on); the authorisation
address `https://authz.constantcontact.com/oauth2/default/v1/authorize`
(GET) and the token address
`https://authz.constantcontact.com/oauth2/default/v1/token` (POST, exchanges
authorisation codes for bearer tokens); and the refresh-token choice with
*Rotating Refresh Tokens* selected.

---

## 2. In the application, signed in as an EspoCRM administrator — enter the credentials

*Built 2026-10-09 (v0.243.0). The two credential rows sit with the other
integrations; the connection itself lives on the **Feature readiness** tab.*

Why this section exists: the API key and client secret let the application
ask Constant Contact for an authorisation; without them the Connect button
explains itself and does nothing else.

1. In a browser, open the deployment's Settings page — for crm-test:
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/setup/
   ```
   You should see the System Settings page with the **Settings** tab open and
   its group headings (Features, Integrations, …). If you are asked to sign
   in, sign in with your EspoCRM administrator login.

2. On the Settings tab, under the **Integrations** heading, click the row
   named **Mailing service client ID**.
   You should see a dialog headed **Change setting** with a Value box and a
   Reason box.

3. In the Change setting dialog, paste the *API key* from section 1, step 8
   into the Value box, type a reason such as `crm-test Constant Contact
   application` into the Reason box, and click **Save**.
   You should see the dialog close and the row show the pasted value with an
   *override* chip.

4. On the Settings tab, under the **Integrations** heading, click the row
   named **Mailing service client secret**.
   You should see the Change setting dialog again.

5. In the Change setting dialog, paste the *client secret* from section 1,
   step 11 into the Value box, type a reason, and click **Save**.
   You should see the dialog close and the row read **set** — the value is
   never shown back. If a message says the secret cannot be stored without
   an encryption key, stop and tell me: the deployment is missing
   `APP_ENCRYPTION_KEY` (crm-test has carried one since 2026-09-12; this is
   the first secret ever stored from the page there).

6. At the top of the page, click the **Feature readiness** tab.
   You should see one block per feature; find **Mailing list sync**. Its
   checks should read `mailing_client_id` ✓ set, `mailing_client_secret` ✓
   set, `DATABASE_URL` ✓ attached, and **connection ✗ not connected**. Below
   the checks is a line *Not connected.*, the redirect address with a
   **Copy** button, and the buttons **Connect** and **Disconnect**.

7. In the Mailing list sync block, compare the redirect address shown with
   the address you registered in section 1, step 9 — for crm-test:
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/api/setup/mailing/callback
   ```
   They should be identical, character for character. If they differ, do
   not continue; stop and tell me both addresses exactly (the app builds its
   address from `APP_BASE_URL`, so a difference means that setting is wrong).

---

## 3. In the application — connect the account

*Built 2026-10-09 (v0.243.0).*

Why this section exists: the connection is a one-time browser authorisation
by the Constant Contact user who created the application; it gives the
application a refresh token, which it keeps encrypted and renews by itself.

1. On the Feature readiness tab, in the **Mailing list sync** block, click
   **Connect**.
   You should be taken to a Constant Contact sign-in page, or straight to a
   permission screen if that browser is already signed in to Constant
   Contact. If instead a message appears beside the buttons, it names what
   is missing (a credential, `APP_BASE_URL`, the encryption key); stop and
   tell me its exact wording.

2. On the Constant Contact sign-in page, sign in as the same user who
   created the application in section 1 (for crm-test: the section 0a
   account).
   You should see a permission screen naming **Cleveland Business Mentors
   applications — TEST** and listing what it asks for: contact data,
   campaign data, account information, and continued access when you are
   not signed in.

3. On the permission screen, click **Allow**.
   You should be returned to the System Settings page, open on the Feature
   readiness tab, with a blue banner reading **Mailing service connected as**
   followed by the account's organisation name. In the Mailing list sync
   block the check now reads **connection ✓ connected as …** and the line
   reads *Connected as … by <your login> on <today's date>*. If the banner
   is red, or says *declined* or *could not be connected*, stop and tell me
   its exact wording.

**To disconnect** (not part of the setup): in the same block click
**Disconnect** twice within five seconds — the second click is the
confirmation, because the page cannot show a confirm dialog. The row is
deleted and the action recorded; Connect again restores it.

---

## 4. In the application — switch the sync on and watch the first pass

*Built 2026-10-09 (v0.244.0).*

Why this section exists: the connection alone sends nothing anywhere. The
switch starts the worker's nightly push and hourly pull, and the first push
must be read as a plan before it is allowed to write.

1. At the top of the System Settings page, click the **Operations** tab and
   find the job **Mailing list push**.
   You should see its description, a Reason box, and two buttons: **Dry
   run** and **Apply the plan**.

2. In the Mailing list push job, click **Dry run**.
   You should see a plan appear under the job, beginning `Mailing list:
   'Event notices'`, then *Audience (CRM, opted in, address usable)*, *On the
   list now*, *Already in step*, *ADD to the list* with one `+ address` line
   per person, and *REMOVE from the list (stay in the account)* with one
   `- address` line per person. On a trial account that has never held the
   list, the first line ends *does not exist yet; apply CREATES it* and
   nothing is on the list. Nothing has been written. If the text begins
   *Not connected* or *Re-authorisation needed*, stop and tell me its exact
   wording.

3. Read the plan. The audience number should be close to the number of CRM
   Contacts with the marketing opt-in ticked and a usable email address. If
   the REMOVE count is large on a first run against a list staff already
   use, stop and tell me the numbers — the removals are the people staff
   entered directly, and plan ruling 4 says they are migrated into the CRM
   first, not dropped. (crm-test's trial account holds nobody, so this
   cannot arise there.)

4. In the Mailing list push job, type a reason into the Reason box and
   click **Apply the plan**.
   You should see the same plan again followed by `Applied: added N, removed
   M, list created.` If it says *The plan changed since you reviewed it —
   nothing was applied*, the world moved between the two clicks; click Dry
   run again and then Apply the plan. If it ends *PARTIAL*, stop and tell me
   the line after it.

5. On the Settings tab, under the **Features** heading, click the row
   **Mailing list sync**, choose **On** in the Change setting dialog, type a
   reason, and click **Save**.
   You should see the row read **On** with an *override* chip. On the Feature
   readiness tab the Mailing list sync block should read **ready**, badged
   *worker*; if it instead warns that the worker has not checked in, stop and
   tell me.

6. The next day, on the Feature readiness tab, read the Mailing list sync
   block's line.
   You should see *Last push <date time>: audience N, added A, removed R.*
   On the Operations tab, **Mailing list unsubscribe pull** can be dry-run at
   any time to see who unsubscribed since the last pass; the worker applies
   it hourly.

---

## 5. Troubleshooting

| Symptom | Meaning |
|---|---|
| Constant Contact shows an error page with `redirect_uri` in it after Connect | The registered address and the application's address differ. Compare section 1, step 9 with section 2, step 4 character by character. |
| The permission screen says the application is not available to this user | The signed-in Constant Contact user is not the one who created the application. Sign out of Constant Contact and sign in as that user. |
| **Connected as** disappears and the row reads **Re-authorise** | The refresh token was refused — the user's password changed, the secret was regenerated, or the token went unused for 180 days. Repeat section 3. An alert email names this when it happens. |
| The push reports HTTP 429 | The vendor's rate limit (10,000 calls a day, 4 a second). The push paces itself; a 429 means something else on the same key is calling too. |
| The nightly push never runs | The switch is on but the worker has not refreshed its settings, or the worker is down — check the readiness panel's worker heartbeat. |

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.6 | 10-09-26 02:17 | Claude (Claude Code) | § 4 rewritten to the built Operations jobs (Mailing list push / unsubscribe pull, dry run then apply, the plan's exact lines), the Features switch, and the last-push line. Status updated; v0.243.0 deployment recorded. |
| 0.5 | 10-09-26 00:40 | Claude (Claude Code) | §§ 2–3 rewritten to the built page (v0.243.0): the two credential rows and the Change setting dialog, the Mailing list sync block on the Feature readiness tab with the connection line, the redirect address with Copy, Connect / Disconnect, and the outcome banner. Status updated. |
| 0.4 | 10-08-26 21:40 | Claude (Claude Code) | crm-test sections 0a and 1 recorded done (Doug, 2026-10-08). Step 5 carries the vendor's exact refresh-token wording; a read-back of the application details screen (OAuth type, Private notice, the authorise and token addresses) added after step 12 for the build. |
| 0.3 | 10-08-26 10:40 | Claude (Claude Code) | § 0a rewritten: the quick-start's developer sign-in address is a 404 (Doug hit it, verified); sign-up now goes through the My Applications address, which sends an unsigned-in browser to the Constant Contact sign-in/sign-up. |
| 0.2 | 10-07-26 23:55 | Claude (Claude Code) | Ruling recorded: crm-test gets a separate Constant Contact account; section 0a added to create it through the developer sign-up. |
| 0.1 | 10-07-26 23:40 | Claude (Claude Code) | First version from the Phase C design: the three shaping facts, the fixed redirect address per deployment, the developer-application steps (doable today), and the Settings panel, connection and first-pass steps as the design has them. |
