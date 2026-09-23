# Stage 5 — Open the hosting and video meeting accounts

**Version:** 0.7  
**Last Updated:** 09-23-26 13:54  
**Generated from** `steps/stage-05.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The chapter's CRM server, its applications and their database all run in a hosting account, and the public webinar programme runs through a video meeting account. This stage opens both in the chapter's own name, so the chapter owns its system and can withdraw access at any time. It ends with the two tokens CRMBuilder needs to build the CRM inside the chapter's accounts, and with the hosting account linked to the code repository the applications are built from.

**Who:** The chapter opens and pays for the accounts. The central support organization is invited in, and creates the two tokens.  
**Time:** About two hours of work. The nonprofit hosting credits can take weeks to be answered, but nothing waits on them.  
**When this stage is done:** Building the CRM (stage 9) can start once the chapter information form is complete, because CRMBuilder now holds the chapter's own tokens.

**Before you start:**

- The chapter's mailboxes on its own domain (stage 4)
- The chapter's bank account (step 1.6)
- The agreement on what access the central support organization holds (step 2.4)
- The chapter's vault (step 2.7)
- The chapter's domain names in its Cloudflare account, or at its own DNS provider with manual DNS (step 3.7)

**Steps in this stage:**

- 5.1 Create the server hosting account
- 5.2 Set up billing on the hosting account
- 5.3 Apply for the nonprofit hosting credits
- 5.4 Grant the central support organization access to the hosting account
- 5.5 Create the video meeting account, or record that it is not needed
- 5.6 Turn on two-step sign-in for both accounts
- 5.7 Write down every account the chapter now owns
- 5.8 Create the two tokens CRMBuilder builds with
- 5.9 Link the hosting account to the code repository

---

## 5.1 Create the server hosting account

**Why:** The chapter's servers must sit in an account the chapter owns, not in anyone else's.

**Who:** The chapter

**Finish first:**

- step 4.7 Create the shared operations mailbox

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In a browser, go to https://cloud.digitalocean.com/registrations/new and sign up with email, not with a Google or GitHub sign-in. Use info@EMAIL-DOMAIN, the shared operations mailbox from step 4.7. Never use a personal address. The exact wording of DigitalOcean's screens has not been checked for this guide.
2. Set a new password, and put it in the chapter's Operations vault straight away.
3. Open the confirmation message DigitalOcean sends to info@EMAIL-DOMAIN and confirm the address.
4. When DigitalOcean asks for a team name, enter the chapter's name exactly as chosen in step 1.1.
   *You should see:* A new, empty DigitalOcean account named after the chapter.
5. Write the account on the chapter's account list (step 5.7): https://cloud.digitalocean.com, signed in as info@EMAIL-DOMAIN.

**Done when:** The account exists in the chapter's name, using a chapter mailbox.

**How to check:** The chapter's setup contact signs in, and the account's profile shows the chapter's name and the chapter mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Signing up with a founder's personal email address. The account then belongs, in practice, to whoever reads that inbox.

---

## 5.2 Set up billing on the hosting account

**Why:** The chapter pays its own hosting, and a bill tied to a volunteer's card stops being paid when that volunteer leaves.

**Who:** The chapter

**Finish first:**

- step 5.1 Create the server hosting account
- step 1.6 Open a bank account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in at https://cloud.digitalocean.com as info@EMAIL-DOMAIN and open Billing. The exact wording of DigitalOcean's screens has not been checked for this guide.
2. Add a payment method: the chapter's own card, or its bank account, from step 1.6. Never a volunteer's personal card.
   *You should see:* The chapter's payment method listed as the default.
3. Set the billing email to an address the chapter's treasurer reads, such as info@EMAIL-DOMAIN or the treasurer's own chapter address.
   *You should see:* The chapter address shown as the billing contact.
4. Set a billing alert, so the chapter hears when a month's spend passes a set amount. Use the amount the cost agreement names (step 2.2).

**Done when:** A chapter payment method is on file and the billing contact is a chapter mailbox.

**How to check:** The billing settings show the chapter's payment method and the chapter mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A volunteer's personal card on the account. When that person leaves, the bills stop being paid and the hosting provider eventually switches the chapter's system off.

---

## 5.3 Apply for the nonprofit hosting credits

**Why:** Nonprofit credits lower the chapter's hosting bill, and they belong to the chapter only if the chapter applies in its own name.

**Who:** The chapter with the central support organization's help

**Finish first:**

- step 5.2 Set up billing on the hosting account
- step 1.5 Obtain nonprofit tax status, or a sponsorship arrangement

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Find the current nonprofit route for DigitalOcean credits. Two are known: DigitalOcean's own programme for nonprofits, and the DigitalOcean offer on TechSoup (https://www.techsoup.org). Neither has been checked for this guide, and the terms change. Ask the central support organization which is open now.
2. Apply in the chapter's own name, with the employer identification number from step 1.3 and the determination letter from step 1.5. Use info@EMAIL-DOMAIN as the contact.
3. Write on the chapter's account list (step 5.7):
   - The route used
   - The date the application went in
   - The expected answer date
   *You should see:* The route and both dates on the list.

**Done when:** The application is submitted and the expected answer date is recorded.

**How to check:** The confirmation of the application and the answer date are on the chapter's account list.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter under a sponsoring nonprofit has no nonprofit status of its own to apply with. That case is an open question. Until it is answered, such a chapter should budget for the full price.

---

## 5.4 Grant the central support organization access to the hosting account

**Why:** The central support organization builds and runs the chapter's servers, and must do it under its own named sign-in so the chapter can see who did what and remove access.

**Who:** The chapter and the central support organization — the chapter grants, the central support organization accepts

**Finish first:**

- step 5.1 Create the server hosting account
- step 2.4 Agree the access the central support organization will hold

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The central support organization's named person first creates their own DigitalOcean sign-in, at https://cloud.digitalocean.com/registrations/new, with their own work address, and turns on two-step sign-in for it.
2. The chapter signs in at https://cloud.digitalocean.com as info@EMAIL-DOMAIN, opens the team's settings, and chooses to invite a member. The exact wording of DigitalOcean's screens has not been checked for this guide.
3. Enter the central support person's own address, and give them a role that can create and manage servers, databases, applications, domains and tokens. DigitalOcean's role names have changed over time; choose the role that manages every resource but is not Owner, and write its name on the chapter's account list.
   *You should see:* The invitation listed as pending.
4. Keep the Owner role with the chapter's own sign-in, info@EMAIL-DOMAIN.
5. The invited person accepts from the message DigitalOcean sends, and switches to the chapter's team from their own sign-in.
   *You should see:* The chapter's team, reached from the invited person's own sign-in.
6. The chapter opens the team's member list.
   *You should see:* The central support person listed, with a remove option beside them. Do not press it.

**Done when:** The central support organization can create and manage servers in the account under its own named sign-in, and the chapter can remove that access itself.

**How to check:** The central support organization's named person sees the chapter's account, and the chapter's owner can see the remove button beside that person's name. There is no need to press it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Sharing the chapter's own sign-in instead of inviting a named person. Nobody can tell who did what, and the chapter cannot withdraw access without changing its own password.

---

## 5.5 Create the video meeting account, or record that it is not needed

**Why:** The public webinar programme schedules its meetings through the chapter's own Zoom account; mentoring sessions never use it.

**Who:** The chapter and the central support organization — the chapter decides, the central support organization sets up the connection

**Finish first:**

- step 4.7 Create the shared operations mailbox

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Decide whether the chapter will run public webinars through the software. If not, write "No public webinars through Zoom" on the chapter's account list (step 5.7) and stop here. Mentoring sessions never need this account.
2. Create a licensed user for the webinar host in the chapter's Google Workspace, exactly as in step 4.7, with Last name Webinars and Primary email webinars@EMAIL-DOMAIN. Zoom will send its host mail there.
3. In a browser, go to https://zoom.us/signup and create a Zoom account with webinars@EMAIL-DOMAIN. Put the password in the chapter's Operations vault.
4. Buy a paid Zoom plan with a Zoom Webinars licence, and assign that licence to webinars@EMAIL-DOMAIN. Automatic attendance also needs the plan to allow webinar reports. Which plan the chapter needs has not been checked for this guide; the central support organization confirms it.
5. Signed in to Zoom as webinars@EMAIL-DOMAIN, go to https://marketplace.zoom.us and open Develop, then Build App. Choose Server-to-Server OAuth and name the app after the chapter, for example Akron Business Mentors Webinars.
6. On the app's Information page, fill in the company name (the chapter's name) and a developer contact (info@EMAIL-DOMAIN).
7. On the Scopes page, add the scopes the software uses:
   - Webinars: read and write
   - Webinar registrants: read and write
   - Reports: read
   - Users: read
   *You should see:* Four groups of scopes added. Zoom's exact scope names have changed over time; pick the ones matching these four descriptions, and the central support organization checks them later with scripts/probe_zoom.py, which names any missing scope.
8. On the Activation page, activate the app.
   *You should see:* The app shown as activated.
9. From the app's App Credentials page, copy three values:
   - Account ID: write it on the chapter information form as the Zoom account identifier
   - Client ID: write it on the form as the Zoom client identifier
   - Client Secret: put it only in the chapter's Operations vault, never on the form
10. On the chapter information form, write webinars@EMAIL-DOMAIN as the Zoom host address. The software reads it as ZOOM_HOST_EMAIL, which otherwise defaults to Cleveland's host.
   *You should see:* The three values on the form and the secret in the vault.

**Done when:** Either the account exists with a chapter mailbox as its host address and an app that lets the software schedule webinars through it, or a note records that this chapter runs no public webinars.

**How to check:** The chapter's host mailbox signs in to Zoom, and the three values are recorded. The connection itself cannot be checked until the applications are deployed.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The host address setting in the software defaults to Cleveland's. A chapter that forgets to change it would create its webinars under Cleveland's Zoom host. The Zoom connection has never been run against a real Zoom account.

---

## 5.6 Turn on two-step sign-in for both accounts

**Why:** A stolen password must not be enough to take over the chapter's servers or its meetings, and losing one phone must not lock the chapter out.

**Who:** The chapter

**Finish first:**

- step 5.1 Create the server hosting account
- step 5.5 Create the video meeting account, or record that it is not needed

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In DigitalOcean, signed in as info@EMAIL-DOMAIN, open the account's security settings and turn on two-factor authentication with an authenticator app. The exact wording of DigitalOcean's screens has not been checked for this guide.
   *You should see:* Signing in now asks for a code.
2. Save DigitalOcean's recovery codes straight into the chapter's Operations vault.
3. Set up the same authenticator on a second named person's device, from the same set-up code, so one lost phone does not lock the chapter out. Or store the set-up code itself in the vault.
4. In Zoom, signed in as webinars@EMAIL-DOMAIN, open the account's security settings and turn on two-factor authentication with an authenticator app. The exact wording of Zoom's screens has not been checked for this guide.
   *You should see:* Signing in to Zoom now asks for a code.
5. Save Zoom's recovery codes in the chapter's Operations vault.
6. A second named person opens the vault and finds both sets of recovery codes.
   *You should see:* Both sets present, reachable by two people.

**Done when:** Two-step sign-in is on and recovery does not depend on one person.

**How to check:** Signing in to each account asks for the second step, and a second named person confirms they can reach the recovery codes.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Recovery codes kept only on the phone of the person who turned two-step sign-in on. When that phone is lost, so is the account.

---

## 5.7 Write down every account the chapter now owns

**Why:** Every account must be findable by a second person, so no account depends on the one who opened it.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 5.1 Create the server hosting account
- step 5.2 Set up billing on the hosting account
- step 5.3 Apply for the nonprofit hosting credits
- step 5.4 Grant the central support organization access to the hosting account
- step 5.5 Create the video meeting account, or record that it is not needed
- step 5.6 Turn on two-step sign-in for both accounts

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Make one list, held by the chapter in its Operations vault as a secure note, where the central support organization's named members can read it, with one line per account:
   - The domain registrar
   - Cloudflare, or with manual DNS the chapter's DNS provider
   - Google Workspace
   - The Proton Pass vault itself
   - The hosting account
   - The Zoom account, if there is one
2. On each line write:
   - The web address to sign in at
   - Who holds the top-level sign-in
   - Who else has access
   - Where the recovery codes are
   - Any nonprofit discount or credit applied, or applied for
   *You should see:* No passwords on the list. Passwords and recovery codes are in the chapter's vault (step 2.7).

**Done when all of these are true:**

- One list names each account.
- The list gives each account's web address.
- The list says who holds the top-level sign-in.
- The list says who else has access.

**How to check:** A second person at the chapter finds every account on the list without asking anyone.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The list goes stale. It is handed over again at the end (step 18.4), and that is the moment to check it.

---

## 5.8 Create the two tokens CRMBuilder builds with

**Why:** CRMBuilder creates the chapter's CRM server and its web address itself, and must do it inside the chapter's own accounts so the chapter can revoke access and keep everything.

**Who:** The central support organization inside the chapter's accounts

**Finish first:**

- step 5.4 Grant the central support organization access to the hosting account
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's DigitalOcean account, open API, then Tokens, and choose to generate a new token. The exact wording of DigitalOcean's screens has not been checked for this guide.
2. Enter:
   - Token name: crmbuilder-CHAPTER-SLUG, using the chapter's short label from step 8.2
   - Expiration: the longest the screen offers, or no expiry
   - Scopes: full read and write access
   *You should see:* A new token, shown once only.
3. Copy the DigitalOcean token straight into the chapter's Operations vault, named DigitalOcean token for CRMBuilder.
4. With manual DNS (step 3.7), skip every Cloudflare action below: there is no Cloudflare token to make, and the Cloudflare box in CRMBuilder stays empty. Go on to the action that begins Work at the build computer.
5. In Cloudflare, open My Profile, then API Tokens, and choose Create Token. Use the Edit zone DNS template.
6. Set exactly:
   - Token name: crmbuilder-CHAPTER-SLUG
   - Permissions: Zone, DNS, Edit (the template sets this)
   - A second permission line: Zone, Zone, Read. CRMBuilder lists the chapter's zones with it, and the template does not add it.
   - Zone resources: Include, Specific zone, and each of the chapter's domain names; never All zones
   - Client IP address filtering: leave empty
   - TTL: leave empty, for no expiry
7. Choose to continue to the summary, then create the token.
   *You should see:* A new token, shown once only, covering only the chapter's zones.
8. Copy the Cloudflare token straight into the chapter's Operations vault, named Cloudflare DNS token for CRMBuilder.
9. Work at the build computer: the central support organization's own computer, the one with CRMBuilder installed. Open a terminal window on it, type the line below and press Enter:
   - cd ~/Dropbox/Projects/crmbuilder
10. Start CRMBuilder. Type the line below and press Enter:
   - ./start-v2.sh
   *You should see:* CRMBuilder's main window. If a window titled Cloud backend not configured appears instead, the build computer is not connected to CRMBuilder's online service: stop and ask.
11. Create the chapter's engagement, which holds the two tokens. Click the strip across the top of the window, which names the current engagement, then Manage engagements… at the bottom of the list. On the Engagements page, click New Engagement.
   *You should see:* A window titled New engagement, with four boxes.
12. Fill in each box, then save:
   - Code: the chapter's short label from step 8.2 in capital letters, for Boston BOSTON. Two to ten capital letters and digits, starting with a letter. It cannot be changed later.
   - Name: the chapter's full name from step 8.2
   - Purpose: Build and run the chapter's CRM and applications.
   - Status: active
   *You should see:* The new engagement listed with an identifier of the form ENG-NNN, and named in the strip across the top of the window. If another engagement is named there, click the strip and choose the chapter's.
13. Open the tab 11 · CRM Deployment, click Instances in the side bar, then Deploy new…, and on Step 1 of 5 — Providers click Set credentials….
   *You should see:* A window titled Provider credentials, with one box for DigitalOcean and one for Cloudflare.
14. In each box, paste the token into Token, type crmbuilder-CHAPTER-SLUG into Label, and click Save token. Then click Close, and click Cancel to leave the deploy window; step 9.2 runs it.
   *You should see:* Step 1 reading DigitalOcean: ✓ Configured — crmbuilder-CHAPTER-SLUG, and the same for Cloudflare. The token itself is never shown again.

**Done when all of these are true:**

- A DigitalOcean API token from the chapter's hosting account exists.
- A Cloudflare API token limited to editing DNS in the chapter's zones exists, unless the chapter uses manual DNS.
- Both tokens are in the chapter's vault.
- Both tokens are entered in CRMBuilder as the chapter's provider credentials.

**Note:** CRMBuilder builds the chapter's CRM with the chapter's own accounts, never its own (ruled 09-18-26).

**How to check:** CRMBuilder's provider credentials screen shows both configured for the chapter's engagement, and lists the chapter's Cloudflare zones. With manual DNS, only the DigitalOcean line needs to be configured.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A Cloudflare token with more permission than it needs, or one covering every zone in the account. Also, leaving the engagement on CRMBuilder's own tokens by mistake. The server then appears in the wrong hosting account, and nothing says so until someone looks.

---

## 5.9 Link the hosting account to the code repository

**Why:** The applications are built from the code repository on GitHub, and the hosting account can fetch it, and take each weekly release by itself, only after GitHub has given it access.

**Who:** The central support organization inside the chapter's hosting account, signed in to GitHub as the repository's owner

**Finish first:**

- step 5.4 Grant the central support organization access to the hosting account

**Do this:**

1. Sign in at https://cloud.digitalocean.com under your own named sign-in from step 5.4.
   *You should see:* The DigitalOcean control panel.
2. Open the team switcher and choose the chapter's team. The exact placement of the team switcher has not been checked for this guide.
   *You should see:* The chapter's team name shown as the current team. If the chapter's team is not in the list, the step 5.4 invitation has not been accepted yet.
3. Choose Create, then App Platform.
   *You should see:* The Create App screen, with a list of places to take code from, including GitHub.
4. Choose GitHub.
   *You should see:* Either a Repository box, or a button to connect GitHub. The button's label may be Connect GitHub account or Manage Access. If the Repository box is already there, go on to the action that types the repository's name.
5. Choose the button to connect GitHub. If GitHub asks you to sign in, sign in as the repository's owner, today dbower44022.
   *You should see:* A GitHub page asking you to authorize or install DigitalOcean.
6. Give DigitalOcean access to the repository cbm-client-intake only. If the page offers All repositories or Only select repositories, choose Only select repositories and pick cbm-client-intake. Then choose the Authorize or Install button the page shows. If GitHub says the DigitalOcean app is already installed, check that cbm-client-intake is listed under Repository access, and add it and choose Save if it is not.
   *You should see:* GitHub returning you to DigitalOcean's Create App screen.
7. Click into the Repository box and type cbm-client-intake.
   *You should see:* dbower44022/cbm-client-intake offered in a short list under the Repository box. If it is not offered, stop: step 11.5 will fail.
8. Choose dbower44022/cbm-client-intake from that list.
   *You should see:* The Repository box reads dbower44022/cbm-client-intake, and a Branch drop-down appears below it, most likely reading main. Do not change it.
9. Click the Branch drop-down to open its list. Do not pick anything from it.
   *You should see:* release among the branch names. That is the whole test.
10. Press Esc to close the list.
   *You should see:* The Branch list closed. Nothing on this screen is saved.
11. Do not choose Next or Create. Choose App Platform in the left menu to leave the screen. Going on would create a billed application with the wrong settings.
   *You should see:* The chapter's App Platform page, with no application. An empty page may show a getting-started panel or a Create App button instead of a list.

**Done when all of these are true:**

- The chapter's DigitalOcean team is authorized to read the code repository on GitHub.
- The repository's release branch is offered on the chapter's Create App screen.
- No application was created.

**Note:** Today the link runs through one personal GitHub account, the repository owner's. Once the central support organization has its own GitHub organization, the repository moves there and this link is made by that organization's account instead.

**How to check:** The release branch appears in the Branch list on the chapter's Create App screen.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Skipping this step. Nothing complains until step 11.5, where creating the application fails in the middle of the build. Also, every chapter's builds then depend on the GitHub account that made the link: if that account revokes DigitalOcean's access, the chapter's running application keeps working but stops building and stops taking weekly releases. Until the repository moves to the central support organization's own GitHub organization, that account is one person's.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.7 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): step 5.7's account list names the chapter's DNS provider when the chapter kept its own, and step 5.8 makes only the DigitalOcean token for a chapter on manual DNS. The finishing test changed with the step list (version 0.19). |
| 0.6 | 09-23-26 13:51 | Step 5.8 names the build computer, the central support organization's own computer with CRMBuilder installed, instead of "this computer", and gives the change of folder its own action. |
| 0.5 | 09-23-26 13:39 | Step 5.8 now opens CRMBuilder and creates the chapter's engagement (Code, Name, Purpose, Status) before entering the tokens, because the tokens are stored on the engagement and no step created it (Doug, 09-23-26: in 5.8, code BOSTON for Boston). |
| 0.4 | 09-23-26 13:35 | Step 5.8 names CRMBuilder's real screens for entering the two tokens (Set credentials…, then the Provider credentials window), gives each token the label step 9.2 checks for, and adds the Zone, Zone, Read permission to the Cloudflare token: CRMBuilder asks for Zone:Read and DNS:Edit, and the Edit zone DNS template gives only the second. |
| 0.3 | 09-23-26 12:25 | Step 5.9 added: link the chapter's hosting account to the code repository on GitHub. No step did this, and step 11.5 would have failed for Boston, whose account was opened with email. Done for real on Boston the same day. A note says the link belongs to the central support organization's own GitHub organization once it exists (Doug, 09-23-26). |
| 0.2 | 09-19-26 00:05 | Every action made precise (Doug, 09-19-26): DigitalOcean sign-up, billing, team invitation and API token settings; the Cloudflare DNS token's exact settings; the Zoom Server-to-Server OAuth app with the four scope groups the software uses (from core/zoom.py and EVENTS-SETUP.md); two-step sign-in and recovery codes; the account list kept in the Operations vault. Screen wording not checked on screen is marked as such. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the hosting and video meeting accounts (9-Methods-Hosting-Website-Policies.md, version 0.4) with the step list's finishing tests. |
