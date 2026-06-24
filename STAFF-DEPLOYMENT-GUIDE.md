# CBM Intake Forms — Staff Deployment Guide

A plain-language guide to **putting the CBM intake forms online and keeping them
running**, written for CBM staff rather than engineers. Everything here is done
through the DigitalOcean **website** (the "console") — you don't need to use a
terminal or type any commands.

> **Engineers:** the detailed, command-line runbook is [`DEPLOYMENT.md`](DEPLOYMENT.md).
> This guide is the non-technical companion to it. If the two ever disagree,
> `DEPLOYMENT.md` is the source of truth.

---

## 1. What this app is

It's a website that hosts CBM's **intake forms** — branded, step-by-step forms
that people fill out. There are five:

- **Client intake** — a business owner requesting a SCORE mentor.
- **Volunteer** — someone applying to become a mentor.
- **Information request** — a general "tell me more" inquiry.
- **Partner** — an organization applying to become a partner.
- **Sponsor** — an organization applying to become a sponsor/donor.

When someone finishes a form, the app creates the matching records in **EspoCRM**
(CBM's customer database — the "system of record").

The same website also hosts three **staff tools** — internal pages that CBM staff
sign in to (with their own EspoCRM username and password); the public never sees
them:

- **Client Administration** (`/assignments/`) — assign incoming mentoring
  requests to a mentor.
- **Mentor Administration** (`/mentoradmin/`) — review and edit mentor records,
  and approve mentors (which can automatically create their EspoCRM login).
- **Submission Operations** (`/ops/`) — a behind-the-scenes view of submissions
  for troubleshooting.

Other than that internal record-keeping, the app stores nothing itself; it passes
completed forms into EspoCRM.

## 2. Where it lives (the key facts)

| Thing | Value |
|---|---|
| **Hosting** | DigitalOcean **App Platform** (a managed hosting service) |
| **DigitalOcean login** | `admin@cbmentors.org` |
| **App name** | `cbm-client-intake` |
| **Live address** | https://cbm-client-intake-svxs3.ondigitalocean.app |
| **Forms index** | the live address `/` lists every form and the staff tools |
| **Client form** | https://cbm-client-intake-svxs3.ondigitalocean.app/client-intake/ |
| **Volunteer form** | https://cbm-client-intake-svxs3.ondigitalocean.app/volunteer/ |
| **Client Administration** (staff) | …ondigitalocean.app/assignments/ |
| **Mentor Administration** (staff) | …ondigitalocean.app/mentoradmin/ |
| **Source code** | GitHub repo `dbower44022/cbm-client-intake` |

App Platform handles the server, security certificates (the padlock in the
browser), and restarts for you. There is no server to log into or maintain.

## 3. Two modes: "dry-run" vs "live"

The app runs in one of two modes, controlled by a single setting:

- **Dry-run** — the forms work and submissions are checked, but **nothing is
  written to EspoCRM**. Use this for demos and gathering feedback. Submissions
  are *not saved anywhere* — they're only noted in the temporary activity log.
- **Live** — finished forms **create real records in EspoCRM**.

As of this writing the app is **live** and writing to the **test** CRM
(`crm-test`). You can always tell which mode the app is in: visit
`https://cbm-client-intake-svxs3.ondigitalocean.app/healthz` in a browser and
look for `"dryRun": true` (dry-run) or `"dryRun": false` (live).

## 4. Logging in to DigitalOcean

1. Go to https://cloud.digitalocean.com and sign in as `admin@cbmentors.org`.
2. Click **Apps** in the left sidebar.
3. Click **cbm-client-intake**. This is the app's dashboard — everything below
   happens here.

## 5. How everyday updates get published

You normally **don't** deploy by hand. When an engineer improves the forms and
saves their changes to GitHub, App Platform **automatically rebuilds and
republishes** the app within a few minutes. Your live settings (which mode it's
in, the CRM connection) are **kept** during these automatic updates.

So in day-to-day operation there's nothing for staff to do. The sections below
are for the less-frequent tasks: setting the app up fresh, switching it to live,
adding a custom web address, and checking on it.

## 6. Check that the app is healthy

Anyone can do this — no login needed:

1. Open the **live address** (Section 2). The form index should load.
2. Open **/client-intake/** and **/volunteer/** — both wizards should appear.
3. Open **/healthz** — you should see a short line of text containing
   `"status":"ok"`. The `"dryRun"` value tells you the mode (Section 3).

If all three load, the app is up.

## 7. Set the app up from scratch (first-time or rebuild)

Only needed if the app is being created fresh (for example, a brand-new
**production** app separate from the test one). Through the console:

1. **Apps** → **Create App**.
2. Choose **GitHub** as the source and authorize the
   `dbower44022/cbm-client-intake` repository, branch **main**. (This GitHub
   connection is a one-time approval.)
3. App Platform detects the app's build recipe automatically — accept the
   defaults it proposes (smallest instance size is fine; this is a light app).
4. Click through to **Create Resources** and wait for the first deploy to finish
   (a few minutes).
5. When it's done, open the app's public address and confirm the forms load
   (Section 6). A fresh app starts in **dry-run** mode.

> If you're creating a **second, production** app so it's separate from the test
> one, give it a distinct name (e.g. `cbm-client-intake-prod`) so the two never
> get confused. An engineer should do this step or pair with you — see
> `DEPLOYMENT.md`, "Reproduce the deployment in production".

## 8. Switch the app to "live" (write to EspoCRM)

This connects the app to EspoCRM so real records get created. Do this carefully —
it requires a secret key from EspoCRM. In the console:

1. App dashboard → **Settings**.
2. Select the **web** component → **Environment Variables** → **Edit**.
3. Set these three values:

   | Setting | Value |
   |---|---|
   | `ESPO_DRY_RUN` | `false` |
   | `ESPO_BASE_URL` | the CRM web address — `https://crm-test.clevelandbusinessmentors.org` for testing, or the **production** CRM address for go-live |
   | `ESPO_API_KEY` | the intake user's secret key from EspoCRM — mark this one **Encrypted** |

4. **Save.** The app redeploys automatically (a couple of minutes).
5. Confirm: open **/healthz** and check it now shows `"dryRun": false`.

The EspoCRM key belongs to a dedicated "intake" user that can only **create**
records (it cannot delete) — so test records you create through the forms have
to be removed by hand in EspoCRM (Section 11).

### The staff tools (optional)

The staff pages (Client Administration, Mentor Administration, Submission
Operations) only turn on when a few extra environment variables are set on the
**web** component (same Edit screen as above). Staff sign in with their own
EspoCRM username/password; access is restricted by EspoCRM **Team**.

| Setting | Value |
|---|---|
| `SESSION_SECRET` | a long random string — **Encrypted**. Turns the staff tools on. |
| `ASSIGN_ALLOWED_TEAMS` | EspoCRM team allowed into Client Administration — `Client Administration Team` |
| `MENTOR_ADMIN_ALLOWED_TEAMS` | EspoCRM team allowed into Mentor Administration — `Mentor Administration Team` |

### Auto-creating mentor logins on approval (optional)

In Mentor Administration, setting a mentor to **Approved** can automatically
create their EspoCRM login, place it in a team, and email them a welcome link.
Because creating users is an admin-only action in EspoCRM, this runs as a
dedicated **admin** EspoCRM account (never a staff member's own login). To turn
it on, add these to the **web** component and create that admin account first:

| Setting | Value |
|---|---|
| `MENTOR_PROVISION_USERS` | `true` |
| `ESPO_PROVISION_USERNAME` | the dedicated admin account's username |
| `ESPO_PROVISION_PASSWORD` | that account's password — **Encrypted** |
| `MENTOR_TEAM_NAME` | the team to put new mentor logins in — `Mentor Team` (only needed if your team has a different name) |

The admin account's **Type must be "Admin"** in EspoCRM (a regular user with
roles is not enough). Leave `MENTOR_PROVISION_USERS` unset (or `false`) to keep
this off — approving a mentor then just changes their status.

**Optional safety check — does the mentor's `@cbmentors.org` mailbox exist?**
You can have the app confirm a mentor's CBM mailbox actually exists in Google
Workspace *before* it creates their login. If the mailbox is missing, the login
isn't created and the screen tells you to create the mailbox first — this stops a
welcome email from bouncing into nowhere and leaving the mentor unable to sign in.
It needs a Google service account set up by an engineer (see the engineers'
`DEPLOYMENT.md`); once that exists, turn it on with `GOOGLE_DIRECTORY_CHECK` =
`true` plus `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DELEGATED_ADMIN`
(**Encrypted**). Left off, approval works exactly as above.

> **Important:** these settings stick through normal automatic updates. The one
> thing that could wipe them is running the engineers' command-line deploy script
> against the live app — which is why that script has a built-in safety block.
> If you only use the console as described here, you're safe.

## 9. Add a branded web address (optional)

The default `…ondigitalocean.app` address works fine, but for a public
production form you may want something like
`intake.clevelandbusinessmentors.org`:

1. App dashboard → **Settings** → **Domains** → **Add Domain**.
2. Enter the desired address.
3. App Platform shows a **DNS record** to add. Give that record to whoever
   manages the `clevelandbusinessmentors.org` domain's DNS settings.
4. Once the DNS is in place, App Platform sets up and renews the security
   certificate automatically — nothing further to do.

## 10. See what's happening (activity log)

To watch submissions and errors in real time:

1. App dashboard → **Runtime Logs**.
2. Each finished form shows a line like `volunteer ok …` (success). A failed
   submission shows a line beginning with `ERROR` that explains what went wrong
   (the person filling the form only sees a generic error message, so the log is
   where the real reason lives).

Remember: in **dry-run** mode submissions appear in the log but are **not saved**
anywhere — the log is temporary and resets when the app updates.

## 11. Clean up test records in EspoCRM

Because the intake user can only create (not delete) records, any **test**
submissions you make through the live forms must be deleted **inside EspoCRM**:

1. Log in to EspoCRM.
2. Find the obviously-labelled test records (use clear test names like
   `ZZTEST…` when submitting so they're easy to spot).
3. Delete them there. A client-intake test leaves an Account, Contact, Client
   Profile, and Engagement; a volunteer test leaves a Contact and a Mentor
   Profile.

## 12. If something looks wrong

| What you see | Likely cause | What to do |
|---|---|---|
| Forms won't load at all | App is down or mid-update | Wait 2–3 min, recheck. Look at **Runtime Logs** and **Activity** in the console. |
| "Submitted, but nothing showed up in EspoCRM" | App is in **dry-run**, or the visitor had an old cached page | Check **/healthz** for the mode; ask them to refresh / use a private window. |
| A form shows an error after the last step | A submitted value didn't match what EspoCRM expects | Check **Runtime Logs** for the `ERROR` line and send it to an engineer. |
| Padlock / security warning in browser | Certificate or domain issue | Usually self-resolves after DNS finishes; if it persists, contact an engineer. |

When in doubt, **don't change settings** — capture what you see (a screenshot of
the console and the relevant **Runtime Logs** line) and pass it to an engineer.

## 13. Things NOT to do

- **Don't delete the app** in the console — that takes the live forms offline.
- **Don't change the Environment Variables** unless you're intentionally
  switching modes (Section 8). Changing `ESPO_BASE_URL` points the forms at a
  different CRM; clearing `ESPO_API_KEY` breaks live writes.
- **Don't share the EspoCRM API key.** It's a secret; keep it encrypted in the
  console only.

## 14. Plain-language glossary

- **App Platform** — DigitalOcean's managed hosting; runs the app for us so
  there's no server to maintain.
- **EspoCRM** — CBM's customer database; the system of record the forms write to.
- **crm-test / production CRM** — the test copy of EspoCRM vs. the real one.
- **Dry-run** — forms work but write nothing to EspoCRM (for demos/feedback).
- **Live** — forms create real EspoCRM records.
- **Deploy / redeploy** — publishing a new version of the app (usually automatic).
- **Environment variable** — a named setting (like the mode or the CRM address)
  configured in the console.
- **/healthz** — a status page that reports whether the app is up and which mode
  it's in.
- **DNS** — the internet's address book; used to point a branded web address at
  the app.

---

## 15. The other documents

This guide is one of several. If you need more than the staff-level view:

- [`DEPLOYMENT.md`](DEPLOYMENT.md) — the **engineer-level runbook**: command
  line, deploy script, rollback, production reproduction, full troubleshooting.
- [`README.md`](README.md) — an **overview of the app** and how it's structured
  for developers, plus how to run it locally.
- [`CLAUDE.md`](CLAUDE.md) — the **current state of the deployment**, always kept
  up to date (app ID, live URL, what's wired, open follow-ups).
- [`prds/CBM_Client_Intake_Requirements_Specification.md`](prds/CBM_Client_Intake_Requirements_Specification.md)
  — **what the forms must do** (the requirements).
- [`prds/CBM_Client_Intake_Technical_Design.md`](prds/CBM_Client_Intake_Technical_Design.md)
  — **how the app is built** (the technical design, including the EspoCRM mapping).
