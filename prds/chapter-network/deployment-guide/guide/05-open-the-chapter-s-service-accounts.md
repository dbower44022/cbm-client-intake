# Stage 5 — Open the chapter's service accounts

**Version:** 0.19  
**Last Updated:** 11-13-26 10:30  
**Generated from** `steps/stage-05.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The chapter's CRM server, its applications and their database all run in a hosting account, and the public webinar programme runs through a video meeting account. This stage opens both in the chapter's own name, so the chapter owns its system and can withdraw access at any time. It makes the two tokens CRMBuilder needs to build the CRM inside the chapter's accounts, and links the hosting account to the code repository the applications are built from. Its last three steps open the other services a chapter runs: the website host, the mailing service and the payment service for donations.

**Who:** The chapter opens and pays for the accounts. The Association is invited in, and creates the two tokens.  
**Time:** About two hours of work. The nonprofit hosting credits can take weeks to be answered, but nothing waits on them.  
**When this stage is done:** Building the CRM (stage 9) can start once the chapter information form is complete, because CRMBuilder now holds the chapter's own tokens. The website (stage 6) is built in the website host account opened in step 5.10.

**Before you start:**

- The chapter's mailboxes on its own domain (stage 4)
- The chapter's bank account (step 1.6)
- The agreement on what access the Association holds (step 2.4)
- The chapter's vault (step 2.7)
- The chapter's domain names in its Cloudflare account, or at its own DNS provider with manual DNS (step 3.7)

**Steps in this stage:**

- 5.1 Create the server hosting account
- 5.2 Set up billing on the hosting account
- 5.3 Apply for the nonprofit hosting credits
- 5.4 Grant the Association access to the hosting account
- 5.5 Create the video meeting account, or record that it is not needed
- 5.6 Turn on two-step sign-in for both accounts
- 5.7 Write down every account the chapter now owns
- 5.8 Create the two tokens CRMBuilder builds with
- 5.9 Link the hosting account to the code repository
- 5.10 Open the website host account
- 5.11 Open the Constant Contact account and its developer application
- 5.12 Open the Stripe account and create the donation link
- 5.13 Create the Fathom team API key, or record that it is not needed
- 5.14 Open the Lob account and store its keys, or record that it is not needed
- 5.15 Open the Twilio account and buy the sender number, or record that it is not needed
- 5.16 Register the sender number with the carriers
- 5.17 Create the Anthropic API key, or record that it is not needed

---

## 5.1 Create the server hosting account

**Why:** The chapter's servers must sit in an account the chapter owns, not in anyone else's.

**Who:** The chapter

**Finish first:**

- step 4.9 Decide who receives the system's warning messages

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. In a browser, go to https://cloud.digitalocean.com/registrations/new and sign up with email, not with a Google or GitHub sign-in. Use admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9, so every password reset reaches the chapter's two owners. Never use a personal address. The exact wording of DigitalOcean's screens has not been checked for this guide.
2. Set a new password, and put it in the chapter's Operations vault straight away.
3. Open the confirmation message DigitalOcean sends to admin@EMAIL-DOMAIN and confirm the address.
4. DigitalOcean does not ask for a team name at sign-up; it names the team My Team (seen 11-08-26). Open https://cloud.digitalocean.com/account/team, click Edit beside Team Name, enter the chapter's name exactly as chosen in step 1.1, and click Update.
   *You should see:* A new, empty DigitalOcean account named after the chapter.
5. Write the account on the chapter's account list (step 5.7): https://cloud.digitalocean.com, signed in as admin@EMAIL-DOMAIN.

**Done when:** The account exists in the chapter's name, signed in with the chapter's administrators group.

**How to check:** The chapter's setup contact signs in, and the account's profile shows the chapter's name and admin@EMAIL-DOMAIN.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Signing up with a founder's personal email address. The account then belongs, in practice, to whoever reads that inbox.

---

## 5.2 Set up billing on the hosting account

**Why:** The chapter pays its own hosting, and a bill tied to a volunteer's card stops being paid when that volunteer leaves.

**Who:** The chapter

**Finish first:**

- step 5.1 Create the server hosting account
- step 1.6 Open a bank account

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Sign in at https://cloud.digitalocean.com as admin@EMAIL-DOMAIN and open Billing. The exact wording of DigitalOcean's screens has not been checked for this guide.
2. Add a payment method: the chapter's own card, or its bank account, from step 1.6. Never a volunteer's personal card.
   *You should see:* The chapter's payment method listed as the default.
3. Set the billing email to an address the chapter's treasurer reads, such as admin@EMAIL-DOMAIN or the treasurer's own chapter address.
   *You should see:* The chapter address shown as the billing contact.
4. Open Billing, then the Spend alerts tab, and click Create alert. Enter Alert name Monthly budget and the monthly budget amount the cost agreement names (step 2.2); leave the thresholds at 50, 75 and 100 percent, and click Create alert. The Association set $75 on 11-08-26.
   *You should see:* The alert listed with its monthly budget and the three thresholds. Alerts go to the team's owners until billing contacts are added.

**Done when:** A chapter payment method is on file and the billing contact is a chapter mailbox.

**How to check:** The billing settings show the chapter's payment method and the chapter mailbox.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A volunteer's personal card on the account. When that person leaves, the bills stop being paid and the hosting provider eventually switches the chapter's system off.

---

## 5.3 Apply for the nonprofit hosting credits

**Why:** Nonprofit credits lower the chapter's hosting bill, and they belong to the chapter only if the chapter applies in its own name.

**Who:** The chapter with the Association's help

**Finish first:**

- step 5.2 Set up billing on the hosting account
- step 1.5 Obtain nonprofit tax status, or a sponsorship arrangement

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Find the current nonprofit route for DigitalOcean credits. Two are known: DigitalOcean's own programme for nonprofits, and the DigitalOcean offer on TechSoup (https://www.techsoup.org). Neither has been checked for this guide, and the terms change. Ask the Association which is open now.
2. Apply in the chapter's own name, with the employer identification number from step 1.3 and the determination letter from step 1.5. Use info@EMAIL-DOMAIN as the contact.
3. Write on the chapter's account list (step 5.7):
   - The route used
   - The date the application went in
   - The expected answer date

   *You should see:* The route and both dates on the list.

**Done when:** The application is submitted and the expected answer date is recorded.

**How to check:** The confirmation of the application and the answer date are on the chapter's account list.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A chapter under a sponsoring nonprofit has no nonprofit status of its own to apply with. That case is an open question. Until it is answered, such a chapter should budget for the full price.

---

## 5.4 Grant the Association access to the hosting account

**Why:** The Association builds and runs the chapter's servers, and must do it under its own named sign-in so the chapter can see who did what and remove access.

**Who:** The chapter and the Association — the chapter grants, the Association accepts

**Finish first:**

- step 5.1 Create the server hosting account
- step 2.4 Agree the access the Association will hold

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. The Association's named person first creates their own DigitalOcean sign-in, at https://cloud.digitalocean.com/registrations/new, with their own work address, and turns on two-step sign-in for it.
2. The chapter signs in at https://cloud.digitalocean.com as admin@EMAIL-DOMAIN, opens the team's settings, and chooses to invite a member. The exact wording of DigitalOcean's screens has not been checked for this guide.
3. Enter the Association's support person's own address, and give them a role that can create and manage servers, databases, applications, domains and tokens. DigitalOcean's role names have changed over time; choose the role that manages every resource but is not Owner, and write its name on the chapter's account list.
   *You should see:* The invitation listed as pending.
4. Keep the Owner role with the chapter's own sign-in, admin@EMAIL-DOMAIN.
5. The invited person accepts from the message DigitalOcean sends, and switches to the chapter's team from their own sign-in.
   *You should see:* The chapter's team, reached from the invited person's own sign-in.
6. The chapter opens the team's member list.
   *You should see:* The Association's support person listed, with a remove option beside them. Do not press it.

**Done when:** The Association can create and manage servers in the account under its own named sign-in, and the chapter can remove that access itself.

**How to check:** The Association's named person sees the chapter's account, and the chapter's owner can see the remove button beside that person's name. There is no need to press it.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Sharing the chapter's own sign-in instead of inviting a named person. Nobody can tell who did what, and the chapter cannot withdraw access without changing its own password.

---

## 5.5 Create the video meeting account, or record that it is not needed

**Why:** The public webinar programme schedules its meetings through the chapter's own Zoom account; mentoring sessions never use it.

**Who:** The chapter and the Association — the chapter decides, the Association sets up the connection

**Finish first:**

- step 4.7 Create the shared operations mailbox

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide whether the chapter will run public webinars through the software. If not, write "No public webinars through Zoom" on the chapter's account list (step 5.7) and stop here. Mentoring sessions never need this account.
2. Create a licensed user for the webinar host in the chapter's Google Workspace, exactly as in step 4.7, with Last name Webinars and Primary email webinars@EMAIL-DOMAIN. Zoom will send its host mail there.
3. In a browser, go to https://zoom.us/signup and create a Zoom account with webinars@EMAIL-DOMAIN. Put the password in the chapter's Operations vault.
4. Buy a paid Zoom plan with a Zoom Webinars licence, and assign that licence to webinars@EMAIL-DOMAIN. Automatic attendance also needs the plan to allow webinar reports. Which plan the chapter needs, and its price, is not decided yet: write it as ZOOM-PLAN on the chapter's account list (step 5.7) until the Association confirms it.
5. Signed in to Zoom as webinars@EMAIL-DOMAIN, go to https://marketplace.zoom.us/user/build. Zoom first asks to accept its Marketplace Terms of Use, and then, on the first Build app, its API License and Terms of Use; the chapter's own person accepts both. Click the plus button beside Developer, then Build app, choose Server to server OAuth app, click Create, and name the app after the chapter, for example Akron Business Mentors Webinars.
   *You should see:* The app's App Credentials page, with Account ID, Client ID and Client Secret, each with a Copy button.
6. On the app's Information page, fill in Short Description, Company Name (the chapter's name), and the developer contact's Name and Email (info@EMAIL-DOMAIN). The page saves by itself.
7. On the Scopes page, add the scopes the software uses:
   - user:read:user:admin (View a user)
   - report:read:list_webinar_participants:admin (View webinar participant reports)
   - webinar:read:webinar:admin, webinar:read:list_webinars:admin, webinar:write:webinar:admin and webinar:update:webinar:admin
   - webinar:write:registrant:admin, and the registrant status scope

   *You should see:* Zoom's scopes are granular (seen 11-08-26): click Add scopes and search each name. The webinar scopes are offered only once the account holds a Webinars licence; the Association, on Pro without the add-on, could add only the first two. The Association checks the set later with scripts/probe_zoom.py, which names any missing scope.
8. On the Activation page, click Activate your app.
   *You should see:* Your app is activated on the account.
9. From the app's App Credentials page, copy three values:
   - Account ID: write it on the chapter information form as the Zoom account identifier
   - Client ID: write it on the form as the Zoom client identifier
   - Client Secret: put it only in the chapter's Operations vault, never on the form
10. On the chapter information form, write webinars@EMAIL-DOMAIN as the Zoom host address. The software reads it as ZOOM_HOST_EMAIL, which otherwise defaults to Cleveland's host.
    *You should see:* The three values on the form and the secret in the vault.

**Done when:** Either the account exists with a chapter mailbox as its host address and an app that lets the software schedule webinars through it, or a note records that this chapter runs no public webinars.

**How to check:** The chapter's host mailbox signs in to Zoom, and the three values are recorded. The connection itself cannot be checked until the applications are deployed.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The host address setting in the software defaults to Cleveland's. A chapter that forgets to change it would create its webinars under Cleveland's Zoom host. The webinar part of the Zoom connection has never been run against a real Zoom account. The chapter information form asks the three Zoom answers only when Zoom webinars is answered yes, so a chapter that checks its credentials before buying the Webinars licence records them in its setup notes until then.

---

## 5.6 Turn on two-step sign-in for both accounts

**Why:** A stolen password must not be enough to take over the chapter's servers or its meetings, and losing one phone must not lock the chapter out.

**Who:** The chapter

**Finish first:**

- step 5.1 Create the server hosting account
- step 5.5 Create the video meeting account, or record that it is not needed

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. In DigitalOcean, signed in as admin@EMAIL-DOMAIN, open the account's security settings and turn on two-factor authentication with an authenticator app. The exact wording of DigitalOcean's screens has not been checked for this guide.
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

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Recovery codes kept only on the phone of the person who turned two-step sign-in on. When that phone is lost, so is the account.

---

## 5.7 Write down every account the chapter now owns

**Why:** Every account must be findable by a second person, so no account depends on the one who opened it.

**Who:** The chapter checked by the Association

**Finish first:**

- step 5.1 Create the server hosting account
- step 5.2 Set up billing on the hosting account
- step 5.3 Apply for the nonprofit hosting credits
- step 5.4 Grant the Association access to the hosting account
- step 5.5 Create the video meeting account, or record that it is not needed
- step 5.6 Turn on two-step sign-in for both accounts

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Make one list, held by the chapter in its Operations vault as a secure note, where the Association's named members can read it, with one line per account:
   - The domain registrar
   - Cloudflare, or with manual DNS the chapter's DNS provider
   - Google Workspace
   - The Proton Pass vault itself
   - The hosting account
   - The Zoom account, if there is one
   - The website host account (step 5.10)
   - The Constant Contact account (step 5.11)
   - The Stripe account (step 5.12)
2. Steps 5.10 to 5.12 open their accounts after this list is made. Leave a line for each, and each of those steps fills its line in.
3. On each line write:
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

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The list goes stale. It is handed over again at the end (step 18.4), and that is the moment to check it.

---

## 5.8 Create the two tokens CRMBuilder builds with

**Why:** CRMBuilder creates the chapter's CRM server and its web address itself, and must do it inside the chapter's own accounts so the chapter can revoke access and keep everything.

**Who:** The Association inside the chapter's accounts

**Finish first:**

- step 5.4 Grant the Association access to the hosting account
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Sign in to DigitalOcean under your own named sign-in from step 5.4, and choose the chapter's team in the team switcher. Then open API, then Tokens, and choose to generate a new token. The exact wording of DigitalOcean's screens has not been checked for this guide. The token must be made under this sign-in, not the chapter's own: DigitalOcean ties its GitHub authorization to a sign-in, not to a team, and step 11.5 builds the applications from GitHub with this token.
   *You should see:* The chapter's team named as the current team, and the Tokens page.
2. Enter:
   - Token name: crmbuilder-SHORT-LABEL, using the chapter's short label from step 8.2
   - Expiration: the longest the screen offers, or no expiry
   - Scopes: full read and write access

   *You should see:* A new token, shown once only.
3. Copy the DigitalOcean token straight into the chapter's Operations vault, named DigitalOcean token for CRMBuilder.
4. With manual DNS (step 3.7), skip every Cloudflare action below: there is no Cloudflare token to make. Go on to the last action of this step.
5. In Cloudflare, open My Profile, then API Tokens, and choose Create Token. Use the Edit zone DNS template.
6. Set exactly:
   - Token name: crmbuilder-SHORT-LABEL
   - Permissions: Zone, DNS, Edit (the template sets this)
   - A second permission line: Zone, Zone, Read. CRMBuilder lists the chapter's zones with it, and the template does not add it.
   - Zone resources: Include, Specific zone, and each of the chapter's domain names; never All zones
   - Client IP address filtering: leave empty
   - TTL: leave empty, for no expiry
7. Choose to continue to the summary, then create the token.
   *You should see:* A new token, shown once only, covering only the chapter's zones.
8. Copy the Cloudflare token straight into the chapter's Operations vault, named Cloudflare DNS token for CRMBuilder.
9. Stop here. The two tokens are entered in CRMBuilder in step 9.3, inside its deploy wizard, and nowhere else. Do not create an engagement for the chapter: in CRMBuilder a chapter is a client holding a deployment grant, and step 9.3 records it.

**Done when all of these are true:**

- A DigitalOcean API token from the chapter's hosting account exists.
- A Cloudflare API token limited to editing DNS in the chapter's zones exists, unless the chapter uses manual DNS.
- Both tokens are in the chapter's vault.

**Note:** CRMBuilder builds the chapter's CRM with the chapter's own accounts, never its own (ruled 09-18-26).

**How to check:** The chapter's Operations vault holds DigitalOcean token for CRMBuilder and, unless the chapter uses manual DNS, Cloudflare DNS token for CRMBuilder. Step 9.3 proves they work, when the deploy wizard's first page reads ✓ Configured — crmbuilder-SHORT-LABEL (this deployment's own) for each.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A Cloudflare token with more permission than it needs, or one covering every zone in the account. And a DigitalOcean token made under the chapter's own sign-in: it builds the CRM server, but step 11.5 fails with GitHub user not authenticated, because the GitHub link from step 5.9 belongs to the Association's support person's sign-in (Boston, 09-24-26).

---

## 5.9 Link the hosting account to the code repository

**Why:** The applications are built from the code repository on GitHub, and the hosting account can fetch it, and take each weekly release by itself, only after GitHub has given it access.

**Who:** The Association inside the chapter's hosting account, signed in to GitHub as the repository's owner

**Finish first:**

- step 5.4 Grant the Association access to the hosting account

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

**Note:** Today the link runs through one personal GitHub account, the repository owner's. Once the Association has its own GitHub organization, the repository moves there and this link is made by that organization's account instead.

**How to check:** The release branch appears in the Branch list on the chapter's Create App screen.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Skipping this step. Nothing complains until step 11.5, where creating the application fails in the middle of the build. Also, every chapter's builds then depend on the GitHub account that made the link: if that account revokes DigitalOcean's access, the chapter's running application keeps working but stops building and stops taking weekly releases. Until the repository moves to the Association's own GitHub organization, that account is one person's.

---

## 5.10 Open the website host account

**Summary:** The chapter chooses the host for its WordPress website (Association ruling 75). Any host must do the five things listed in the first action. The Association runs its own websites on Cloudways, a lightly managed host on DigitalOcean, and tests the chapter connector only there, so the actions below are written for Cloudways. This step opens the account in the chapter's own name; stage 6 builds the website in it.

**Who:** The chapter with the Association invited in

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 2.4 Agree the access the Association will hold
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Choose the host with the chapter's board. Cloudways is the host the Association uses and tests. Any other host must do all five of these (Association ruling 75; website template requirements WT-90 to WT-92):
   - Keeps the server's operating system and PHP up to date
   - Takes daily backups
   - Provides the security certificate
   - Provides a staging copy of the website
   - Never puts the website on the same server as the chapter's CRM
2. Another host only: open its account by the host's own steps, under the same rules as the Cloudways actions below: signed up with admin@EMAIL-DOMAIN, the password and codes in the chapter's Operations vault, paid with the chapter's own card, two-step sign-in on, and the Association's named person invited. Then skip to the last action. The Association has not tested the chapter connector on that host.
3. In a browser, go to https://platform.cloudways.com/signup (it moves to unified.cloudways.com/signup) and sign up with the email form, not the DigitalOcean, LinkedIn, GitHub or Google buttons. Use admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9, so every password reset reaches the chapter's two owners. Paste the address rather than typing it. Tick the terms box and click Sign up.
4. Set a new random password generated by Proton Pass, and save it in the chapter's Operations vault in an item titled Website host (Cloudways), with the sign-in address https://platform.cloudways.com.
5. Cloudways emails a six-digit verification code to admin@EMAIL-DOMAIN. Enter it on Verify Your Email and click Verify and Continue. Then, on Verify Your Phone Number, enter a mobile number, click Send Code and enter the code sent by text.
   *You should see:* The Cloudways dashboard, signed in as admin@EMAIL-DOMAIN.
6. Open the account's billing settings and add the chapter's own payment card from step 1.6. Never a volunteer's personal card.
7. Open the account's security settings and turn on two-factor authentication with an authenticator code. Add the code to the Website host (Cloudways) item in the vault, and save any recovery codes there too.
   *You should see:* Signing in now asks for a six-digit code, and the vault item shows the same code.
8. Open the account's team settings and invite the Association's named person by their own email address, with a role that can manage servers and applications. Cloudways's role names have not been checked for this guide.
   *You should see:* The Association's named person listed as a team member once they accept.
9. Do not create a server yet. Stage 6 creates it, on DigitalOcean, and names it.
10. Fill in the website host line on the chapter's account list (step 5.7).

**Done when all of these are true:**

- The host does all five things in the first action.
- The website host account exists in the chapter's name, signed in with the chapter's administrators group.
- It is paid with the chapter's own card.
- Two-step sign-in is on, and the sign-in and codes are in the chapter's vault.
- The Association's named person is a team member.

**How to check:** A second person at the chapter signs in to the host from the vault item, and the host's team page lists the Association's named person.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A server created now, before stage 6 has chosen its size and region, starts billing at once. Leave the account empty until stage 6. A new account may also be held for a manual check before it can be used ("Your account activation is pending", 11-08-26): email the address Cloudways gives, and allow a day.

---

## 5.11 Open the Constant Contact account and its developer application

**Summary:** Constant Contact is the mailing service the applications keep in step with the CRM: a newsletter subscriber lands in the CRM first, and the applications pass them on. This step opens the chapter's own account and registers the developer application the software connects through. The connection itself is made later, from System Settings, once the applications are running (MAILING-SETUP.md at the repository root, sections 2 and 3).

**Who:** The chapter — the account must be opened by the Constant Contact user who will later connect the software

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. In a browser, go to https://www.constantcontact.com/signup (a free trial; no card at sign-up) and sign up with admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9. Choose the plan the Association names; which plan, and its price, is not decided yet, so write it as MAILING-PLAN on the account list until it is. The exact wording of the sign-up screens has not been checked for this guide.
2. Set a new random password generated by Proton Pass, and save it in the chapter's Operations vault in an item titled Constant Contact.
3. Confirm the address from the Verify Email message sent to admin@EMAIL-DOMAIN. Then turn on two-step sign-in in the account's settings, with the codes in the Constant Contact item: Constant Contact refuses to create a developer application until it is on (Users must be enrolled in MFA to create applications, 11-08-26). Before the trial ends, upgrade to the chosen plan with the chapter's own card from step 1.6.
4. Signed in as admin@EMAIL-DOMAIN, open https://app.constantcontact.com/pages/dma/portal.
   *You should see:* A page headed My Applications, with a New Application button.
5. Click New Application, name it after the chapter, for example Akron Business Mentors applications, select Authorization Code Flow and Implicit Flow, select Rotating Refresh Tokens, and click Create.
   *You should see:* The new application listed under Applications.
6. Next to the new application, click Edit. Copy the API Key (Client Id) into the Constant Contact item in the vault, labelled API key.
7. The Redirect URI box holds https://localhost and is locked. Click the pencil icon beside it, and in Edit this redirect URI replace the address with the one below, then click Confirm, then Save at the top of the page. Put the applications' web address in place of APP-ADDRESS. It is apps. followed by the website domain name chosen in step 3.2, for example apps.akronbusinessmentors.org:
   - https://APP-ADDRESS/api/setup/mailing/callback

   *You should see:* Exactly that address, with https at the start and callback at the end.
8. Click Generate Client Secret and copy the secret straight into the Constant Contact item in the vault, labelled client secret. It is shown only once.
9. Click Save, and fill in the Constant Contact line on the chapter's account list (step 5.7).

**Done when all of these are true:**

- The Constant Contact account exists in the chapter's name, signed in with the chapter's administrators group.
- Its developer application exists, with the applications' callback address as its redirect address.
- The API key and client secret are in the chapter's vault.

**Note:** A developer application is private to the Constant Contact user who created it, so the account the software connects to must be the one that created it.

**How to check:** The application's details page shows the redirect address ending in /api/setup/mailing/callback, and the vault item holds both values.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** An application created under a volunteer's own Constant Contact sign-in. Only that person can then connect the software, and the connection stops when they leave. Every other service that sends mail as the chapter's domain must be in its sender records too; Constant Contact's own sending address setup is not covered by this guide yet.

---

## 5.12 Open the Stripe account and create the donation link

**Summary:** A chapter takes online donations through a Stripe Payment Link in its own Stripe account (Association ruling 30). The website's Donate button opens the link; card details stay with Stripe. This step opens the account and creates the link. The link's address is later entered in the Website group of System Settings, which supplies it to the website.

**Who:** The chapter — the treasurer, or the person the board names

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 1.6 Open a bank account
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. In a browser, go to https://dashboard.stripe.com/register and create the account with admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9. Paste the address rather than typing it: the Association's first try had a typo, and Stripe's verification email went nowhere (11-08-26). The account opens in a test environment Stripe calls a Sandbox.
2. Set a new random password generated by Proton Pass, and save it in the chapter's Operations vault in an item titled Stripe.
3. Turn on two-step sign-in in the account's security settings, with the codes in the Stripe item.
4. Complete Stripe's business details with the chapter's legal name, its employer identification number from step 1.3 and the chapter's bank account from step 1.6 for payouts. A chapter that is not yet able to take real payments stays in test mode and skips this action.
5. Open https://dashboard.stripe.com/test/payment-links/create. Under Select type choose Customers choose what to pay, enter the Title Donation to CHAPTER-NAME, set the button wording to Donate, and click Create link.
   *You should see:* A link address beginning https://donate.stripe.com/, with test_ in it while in test mode.
6. Copy the link's address into the Stripe item in the vault, labelled Donation link, and fill in the Stripe line on the chapter's account list (step 5.7).

**Done when all of these are true:**

- The Stripe account exists in the chapter's name, signed in with the chapter's administrators group.
- Two-step sign-in is on, and the sign-in and codes are in the chapter's vault.
- A donation Payment Link exists, and its address is in the vault.

**How to check:** Opening the link's address in a private browser window shows Stripe's payment page with the chapter's name.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Payouts to a volunteer's personal bank account. Stripe pays out to the account entered here, so it must be the chapter's own (step 1.6). Until the chapter applications record gifts automatically, staff enter each gift by hand and the chapter sends donors' tax acknowledgments itself (Association ruling 30).

---

## 5.13 Create the Fathom team API key, or record that it is not needed

**Summary:** Fathom is the note-taker that records mentoring sessions. The applications read each session's transcript and summary from Fathom with one API key, and a key reads only the meetings its own user recorded or shared with the user's Fathom team. This step makes that key and stores it. A chapter whose mentors do not use Fathom records that instead.

**Who:** The chapter — the person who administers the chapter's Fathom team

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide whether the chapter's mentors will record their sessions with Fathom. If not, write "No Fathom" on the chapter's account list (step 5.7), mark Fathom not in use on the Fathom sub-tab of System Settings once the applications run, and stop here.
2. In a browser, go to https://fathom.video and create the chapter's Fathom team account with admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9. Put the password in the chapter's Operations vault, in an item titled Fathom. The exact wording of Fathom's sign-up screens has not been checked for this guide.
3. In the team's settings, set every new recording to be shared with the team. A mentor's recording that is not shared never reaches the applications.
4. In Fathom's settings, open the API access page and create an API key. Copy it straight into the Fathom item in the vault, labelled API key. The page's exact name has not been checked for this guide.
5. Once the applications run (stage 11), open System Settings, then the Fathom sub-tab of the Integrations tab, and paste the key into the setting Fathom API key.
   *You should see:* The Fathom sub-tab's status line says credentials set.

**Done when:** Either the Fathom API key is stored in the vault and set in System Settings, or a note records that this chapter does not use Fathom.

**How to check:** The Fathom sub-tab of System Settings shows the API key as set, and its Test Integration button passes.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A key made by one mentor's own Fathom user reads only that mentor's recordings. Make the key with the team's administrator, and keep team sharing on.

---

## 5.14 Open the Lob account and store its keys, or record that it is not needed

**Summary:** Lob prints and mails the postcards a marketing campaign sends. Lob gives every account two keys: a test key, beginning test_, that prints nothing, and a live key, beginning live_, that prints and mails for real. This step opens the account and stores both keys. The applications start with the test key.

**Who:** The chapter — the person the board names for marketing

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 1.6 Open a bank account
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide whether the chapter will send postcards. If not, write "No postcards" on the chapter's account list (step 5.7), mark Lob not in use on the Lob sub-tab of System Settings once the applications run, and stop here.
2. In a browser, go to https://dashboard.lob.com and sign up with admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9. Put the password in the chapter's Operations vault, in an item titled Lob, and turn on two-step sign-in. The exact wording of Lob's screens has not been checked for this guide.
3. In Lob's settings, open the API keys page. Copy two keys into the Lob item in the vault:
   - The test key, which begins test_, labelled test key.
   - The live key, which begins live_, labelled live key.
4. Before any real postcard is sent, add the chapter's own card from step 1.6 as Lob's payment method.
5. Once the applications run (stage 11), open System Settings, then the Lob sub-tab of the Integrations tab. Paste the test key into the setting Mail vendor API key, and leave Mail vendor test mode on.
   *You should see:* The Lob sub-tab's integration test reports the key as a test key, and test mode on.

**Done when:** Either both Lob keys are in the vault and the test key is set in System Settings, or a note records that this chapter sends no postcards.

**Note:** Changing to the live key is a separate decision, made when the first real campaign is ready; test mode is switched off at the same moment.

**How to check:** The Lob sub-tab of System Settings shows the key as set, and its Test Integration button passes.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A live key entered while test mode is on. Lob decides by the key alone, so the postcards would be printed and mailed. The Lob integration test fails when the key and test mode disagree.

---

## 5.15 Open the Twilio account and buy the sender number, or record that it is not needed

**Summary:** Twilio sends the text messages a marketing campaign sends, from one phone number the chapter buys. This step opens the account, buys the number and stores the three values the applications need. A chapter that sends no texts records that instead.

**Who:** The chapter — the person the board names for marketing

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 1.6 Open a bank account
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide whether the chapter will send text messages. If not, write "No texts" on the chapter's account list (step 5.7), mark Twilio not in use on the Twilio sub-tab of System Settings once the applications run, and stop here.
2. In a browser, go to https://www.twilio.com/try-twilio and sign up with admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9. Put the password in the chapter's Operations vault, in an item titled Twilio, and turn on two-step sign-in. The exact wording of Twilio's screens has not been checked for this guide.
3. Upgrade the account from trial with the chapter's own card from step 1.6. A trial account can text only numbers it has verified.
4. In Twilio's console, buy a local United States number that can send SMS. Write it in the Twilio item in the vault in the form +12165550123.
5. From the console's Account Info panel, copy two values into the Twilio item in the vault:
   - The Account SID, which begins AC.
   - The Auth Token. Copy the live one, never the test credentials.
6. Once the applications run (stage 11), open System Settings, then the Twilio sub-tab of the Integrations tab, and set three settings:
   - Texting account SID: the Account SID.
   - Texting auth token: the Auth Token.
   - Texting sender number: the number, in the form +12165550123.

   *You should see:* The Twilio sub-tab's integration test finds the account active and the number able to send texts.

**Done when:** Either the Twilio account is upgraded, the number is bought, and the three values are in the vault and set in System Settings, or a note records that this chapter sends no texts.

**How to check:** The Twilio sub-tab of System Settings shows the three values as set, and its Test Integration button passes.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The test credentials copied in place of the live ones. Twilio refuses every read with them, and the integration test says so.

---

## 5.16 Register the sender number with the carriers

**Summary:** United States carriers block texts from an ordinary business number that is not registered with them (the registration Twilio calls A2P 10DLC). This step registers the chapter as a brand and its texts as a campaign, and attaches the number from step 5.15. Approval takes days to weeks, so start it early.

**Who:** The chapter — the person the board names for marketing, with the treasurer for the business details

**Finish first:**

- step 5.15 Open the Twilio account and buy the sender number, or record that it is not needed
- step 1.3 Get a federal employer identification number

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. In Twilio's console, open the A2P 10DLC registration pages. The exact wording of these screens has not been checked for this guide.
2. Register the chapter as a brand with its legal name and its employer identification number from step 1.3.
3. Register one campaign describing the texts the chapter sends: invitations and reminders to people who asked for them, each telling them to reply STOP to stop.
4. Attach the number from step 5.15 to the campaign.
   *You should see:* The campaign's status reads approved. Twilio may take days or weeks.

**Done when:** The chapter's brand and campaign are approved, and the sender number is attached to the campaign.

**How to check:** Twilio's console shows the campaign approved with the number attached.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Texts sent before approval are blocked or filtered by the carriers, with no error in the applications.

---

## 5.17 Create the Anthropic API key, or record that it is not needed

**Summary:** Anthropic's Claude writes the summaries of email conversations and the AI research on leads. Both use one API key, paid by the chapter. This step opens the chapter's own account, sets a monthly spending limit and stores the key. A chapter that switches neither feature on records that instead.

**Who:** The chapter — the treasurer, or the person the board names

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 1.6 Open a bank account
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide whether the chapter will use the AI features. If not, write "No AI features" on the chapter's account list (step 5.7), mark Anthropic not in use on the Anthropic sub-tab of System Settings once the applications run, and stop here.
2. In a browser, go to https://platform.claude.com and create the chapter's organization with admin@EMAIL-DOMAIN, the chapter's administrators group from step 4.9. Put the password in the chapter's Operations vault, in an item titled Anthropic. The exact wording of the console's screens has not been checked for this guide.
3. Add the chapter's own card from step 1.6 for billing, and set a monthly spending limit the board agrees.
4. Create an API key named after the chapter's applications, and copy it straight into the Anthropic item in the vault, labelled API key. It is shown only once.
5. Once the applications run (stage 11), open System Settings, then the Anthropic sub-tab of the Integrations tab, and paste the key into the setting Anthropic API key.
   *You should see:* The Anthropic sub-tab's integration test lists the models and finds each configured model.

**Done when:** Either the key is in the vault and set in System Settings with a monthly spending limit on the account, or a note records that this chapter uses no AI features.

**How to check:** The Anthropic sub-tab of System Settings shows the key as set, and its Test Integration button passes.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A key made under a volunteer's own Anthropic account. The chapter cannot see or limit its spending, and the key stops when the volunteer leaves.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.19 | 11-13-26 10:30 | Steps 5.13 to 5.17 added, each for an outside service the applications use and no step set up: the Fathom team API key, the Lob account and keys, the Twilio account and number, the carrier registration of the number, and the Anthropic API key (mapping approved by Doug 11-13-26). No existing step number changed. Steps that belong to an integration carry the new keys integration and check.auto, read by the setup checklist on System Settings' Integrations tab (prds/integrations-tab-plan.md section 4, mapping approved by Doug 11-13-26). |
| 0.18 | 11-10-26 10:41 | Step 5.5's status records the read-only credentials check for the Business Mentors Association (11-10-26): token issued, host found, webinar listing refused for want of the Webinars licence. Its goes wrong note says the form asks the Zoom answers only when webinars are switched on. |
| 0.17 | 11-09-26 17:42 | Step 5.8 follows CRMBuilder's new deploy wizard (PI-600, accepted 11-09-26): it makes the two tokens and puts them in the vault, and nothing more. The engagement it used to create and the Provider credentials window are gone; the tokens are entered inside the wizard in step 9.3. Applied from CRMBuilder's handoff of 11-09-26. |
| 0.16 | 11-09-26 14:21 | Step 5.10 follows Association ruling 75, which replaces ruling 29: the chapter chooses its website host, any host must do five things, and the Cloudways actions are the path the Association tests. |
| 0.15 | 11-08-26 10:06 | Step 5.10: a new Cloudways account may be held for a manual activation check (the Association's, 11-08-26). |
| 0.14 | 11-08-26 09:31 | Steps 5.5, 5.10, 5.11 and 5.12 from the Association's own accounts, opened 11-08-26: Zoom's two sets of terms, its Build app path, Information fields, granular scopes (webinar scopes only with a Webinars licence) and Activate your app; Cloudways's email code and phone verification; Constant Contact's free-trial sign-up, its demand for two-step sign-in before a developer application, and the locked Redirect URI; Stripe's Sandbox, its Payment Link page and the donate.stripe.com address. |
| 0.13 | 11-08-26 01:33 | Steps 5.1 and 5.2 from the Association's own DigitalOcean account, opened 11-08-26: the team is named My Team at sign-up and renamed afterwards; the billing alert is a spend alert with a monthly budget and thresholds. |
| 0.12 | 11-07-26 15:28 | Every account this stage opens signs in with admin@, the chapter's administrators group from step 4.9, instead of info@, the shared operations mailbox (Doug, 11-07-26, following Association ruling 18): steps 5.1, 5.2, 5.4, 5.6 and 5.10 to 5.12. Contact addresses given to a provider (steps 5.3 and 5.5) stay info@. |
| 0.11 | 11-07-26 15:21 | Corrected while the Business Mentors Association is set up as a chapter (plan association-setup-plan.md, approved by Doug 11-07-26): "the central support organization" is now "the Association", and "the central committee" is "the central technical committee". The stage is renamed "Open the chapter's service accounts" and gains steps 5.10 (the website host account, Association ruling 29), 5.11 (the Constant Contact account and its developer application) and 5.12 (the Stripe account and donation link, Association ruling 30). Step 5.5 writes the Zoom plan as ZOOM-PLAN until it is decided. Step 5.7's account list names the three new accounts. |
| 0.10 | 09-24-26 23:08 | From Boston's build (09-24-26): the DigitalOcean token in step 5.8 must be made under the central support person's own sign-in with the chapter's team chosen, because DigitalOcean ties its GitHub authorization to a sign-in and step 11.5 fails with GitHub user not authenticated on a token made under the chapter's own sign-in. Boston's first token was made that way and had to be replaced. |
| 0.9 | 09-23-26 20:40 | References to stage 9 follow its renumbering from twenty steps to nine (stage 9 version 0.11). |
| 0.8 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. The engagement code is described as the short label in capital letters. |
| 0.7 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): step 5.7's account list names the chapter's DNS provider when the chapter kept its own, and step 5.8 makes only the DigitalOcean token for a chapter on manual DNS. The finishing test changed with the step list (version 0.19). |
| 0.6 | 09-23-26 13:51 | Step 5.8 names the build computer, the central support organization's own computer with CRMBuilder installed, instead of "this computer", and gives the change of folder its own action. |
| 0.5 | 09-23-26 13:39 | Step 5.8 now opens CRMBuilder and creates the chapter's engagement (Code, Name, Purpose, Status) before entering the tokens, because the tokens are stored on the engagement and no step created it (Doug, 09-23-26: in 5.8, code BOSTON for Boston). |
| 0.4 | 09-23-26 13:35 | Step 5.8 names CRMBuilder's real screens for entering the two tokens (Set credentials…, then the Provider credentials window), gives each token the label step 9.2 checks for, and adds the Zone, Zone, Read permission to the Cloudflare token: CRMBuilder asks for Zone:Read and DNS:Edit, and the Edit zone DNS template gives only the second. |
| 0.3 | 09-23-26 12:25 | Step 5.9 added: link the chapter's hosting account to the code repository on GitHub. No step did this, and step 11.5 would have failed for Boston, whose account was opened with email. Done for real on Boston the same day. A note says the link belongs to the central support organization's own GitHub organization once it exists (Doug, 09-23-26). |
| 0.2 | 09-19-26 00:05 | Every action made precise (Doug, 09-19-26): DigitalOcean sign-up, billing, team invitation and API token settings; the Cloudflare DNS token's exact settings; the Zoom Server-to-Server OAuth app with the four scope groups the software uses (from core/zoom.py and EVENTS-SETUP.md); two-step sign-in and recovery codes; the account list kept in the Operations vault. Screen wording not checked on screen is marked as such. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the hosting and video meeting accounts (9-Methods-Hosting-Website-Policies.md, version 0.4) with the step list's finishing tests. |
