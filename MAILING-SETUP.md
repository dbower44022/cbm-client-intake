# Mailing list sync — Constant Contact setup and activation runbook

Last Updated: 10-08-26 10:40 · Revision 0.3 — change log at the end.

How to register this application with Constant Contact, connect one
deployment to one Constant Contact account, and switch the audience push on.
Written for **crm-test first**; production is a separate, later pass with its
own Constant Contact application. Plan and the rulings behind it:
`prds/mailing-list-and-event-sponsorship-plan.md` (§ 11 is the Phase C
design this runbook follows).

**Status (2026-10-07): designed, nothing built.** Section 1 can be done today
— the developer application and its redirect address do not depend on any
code. Sections 2 to 4 describe a Settings page panel and a worker job that
do not exist yet; they are written now so the design can be judged as the
person doing it will meet it. **Ruled 2026-10-07 (plan § 11.11): crm-test
connects to a separate Constant Contact account of its own**, created in
section 0a; the organisation's real account is production's alone.

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
   Refresh**. (The application stores each new refresh token the moment it
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

---

## 2. In the application, signed in as an EspoCRM administrator — enter the credentials

*Not built yet. This is what the panel will ask for; it follows the shape of
the Zoom and Fathom rows on the same page.*

Why this section exists: the API key and client secret let the application
ask Constant Contact for an authorisation; without them the Connect button
explains itself and does nothing else.

1. In a browser, open the deployment's Settings page — for crm-test:
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/setup/
   ```
   You should see the System Settings page with its group headings. If you
   are asked to sign in, sign in with your EspoCRM administrator login.

2. On the System Settings page, under the **Integrations** heading, find the
   row **Mailing service client ID** and paste the *API key* from section 1,
   step 8, then click that row's **Save**.
   You should see the row show the pasted value and a saved confirmation.

3. On the same page, in the row **Mailing service client secret**, paste the
   *client secret* from section 1, step 11, then click that row's **Save**.
   You should see the row read **set** (the value itself is never shown
   back). If it says the secret cannot be stored without an encryption key,
   stop and tell me — the deployment is missing `APP_ENCRYPTION_KEY`.

4. On the same page, in the row **Mailing service redirect address**,
   confirm the address shown is, character for character, the address you
   registered in section 1, step 9.
   If the two differ in any character, do not continue; stop and tell me
   both addresses exactly.

---

## 3. In the application — connect the account

*Not built yet.*

Why this section exists: the connection is a one-time browser authorisation
by the Constant Contact user who created the application; it gives the
application a refresh token, which it keeps encrypted and renews by itself.

1. On the System Settings page, under the **Integrations** heading, in the
   row **Mailing service connection**, click **Connect**.
   You should be taken to a Constant Contact sign-in page.

2. On the Constant Contact sign-in page, sign in as the same user who
   created the application in section 1.
   You should see a permission screen naming the application and listing
   what it asks for: contact data, campaign data, account information, and
   continued access when you are not signed in.

3. On the permission screen, click **Allow**.
   You should be returned to the System Settings page, and the row **Mailing
   service connection** should read **Connected as** followed by the
   Constant Contact account's organisation name and the date. If the row
   instead shows a red message, stop and tell me its exact wording.

---

## 4. In the application — switch the sync on and watch the first pass

*Not built yet.*

Why this section exists: the connection alone sends nothing anywhere. The
switch starts the worker's nightly push and hourly pull, and the first push
must be read as a plan before it is allowed to write.

1. On the System Settings page, under the **Operations** tab, find the job
   **Mailing audience push** and click **Dry run**.
   You should see a plan: how many Contacts qualify, how many would be
   added to the list named in **Mailing list name** (default *Event
   notices*), how many would be removed, and the list's current size in
   Constant Contact. Nothing has been written.

2. Read the plan. The number to be added should be close to the number of
   CRM Contacts with the marketing opt-in ticked and a usable email address.
   If the number to be removed is large on a first run against a list staff
   already use, stop and tell me the numbers — the removals are the people
   staff entered directly, and plan ruling 4 says they are migrated into the
   CRM first, not dropped.

3. On the same Operations tab, click **Apply** on that same plan.
   You should see the result: added, removed, skipped, and any addresses
   Constant Contact refused by name. If the plan has moved since the dry
   run, the apply refuses and says so; run the dry run again.

4. On the System Settings page, under **Features**, set **Mailing list sync**
   to **on** and click its **Save**.
   You should see the readiness panel's **Mailing list sync** line turn
   ready, naming the worker as the component that runs it.

5. The next morning, on the System Settings page, under **Operations**, open
   the job's history.
   You should see one overnight push with counts, and hourly pulls each
   reporting how many unsubscribes were applied (usually 0).

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
| 0.3 | 10-08-26 10:40 | Claude (Claude Code) | § 0a rewritten: the quick-start's developer sign-in address is a 404 (Doug hit it, verified); sign-up now goes through the My Applications address, which sends an unsigned-in browser to the Constant Contact sign-in/sign-up. |
| 0.2 | 10-07-26 23:55 | Claude (Claude Code) | Ruling recorded: crm-test gets a separate Constant Contact account; section 0a added to create it through the developer sign-up. |
| 0.1 | 10-07-26 23:40 | Claude (Claude Code) | First version from the Phase C design: the three shaping facts, the fixed redirect address per deployment, the developer-application steps (doable today), and the Settings panel, connection and first-pass steps as the design has them. |
