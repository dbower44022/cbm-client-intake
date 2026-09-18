# Stage 5 — Open the hosting and video meeting accounts

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-05.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The chapter's CRM server, its applications and their database all run in a hosting account, and the public webinar programme runs through a video meeting account. This stage opens both in the chapter's own name, so the chapter owns its system and can withdraw access at any time. It ends with the two tokens CRMBuilder needs to build the CRM inside the chapter's accounts.

**Who:** The chapter opens and pays for the accounts. The central support organization is invited in, and creates the two tokens.  
**Time:** About two hours of work. The nonprofit hosting credits can take weeks to be answered, but nothing waits on them.  
**When this stage is done:** Building the CRM (stage 9) can start once the chapter information form is complete, because CRMBuilder now holds the chapter's own tokens.

**Before you start:**

- The chapter's mailboxes on its own domain (stage 4)
- The chapter's bank account (step 1.6)
- The agreement on what access the central support organization holds (step 2.4)
- The chapter's vault (step 2.7)
- The chapter's domain names in its Cloudflare account (step 3.7)

**Steps in this stage:**

- 5.1 Create the server hosting account
- 5.2 Set up billing on the hosting account
- 5.3 Apply for the nonprofit hosting credits
- 5.4 Grant the central support organization access to the hosting account
- 5.5 Create the video meeting account, or record that it is not needed
- 5.6 Turn on two-step sign-in for both accounts
- 5.7 Write down every account the chapter now owns
- 5.8 Create the two tokens CRMBuilder builds with

---

## 5.1 Create the server hosting account

**Why:** The chapter's servers must sit in an account the chapter owns, not in anyone else's.

**Who:** The chapter

**Finish first:**

- step 4.7 Create the shared operations mailbox

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign up for a DigitalOcean account using a chapter mailbox that more than one person can read, such as the shared operations mailbox. Never use a personal address.
   *You should see:* A new, empty DigitalOcean account.
2. Put the account's sign-in in the chapter's Operations vault.
   *You should see:* The sign-in listed in the vault.

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

1. In the hosting account's billing settings, add the chapter's own card or bank payment method.
   *You should see:* The chapter's payment method listed.
2. Set the billing email to a chapter mailbox the chapter's treasurer reads.
   *You should see:* The chapter mailbox shown as the billing contact.

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

1. Apply for hosting credits in the chapter's own name, through the hosting provider's own nonprofit programme or through TechSoup. The current terms of both have not been checked for this guide.
2. Write down which route was used and when an answer is expected, on the chapter's account list (step 5.7).
   *You should see:* The route and the answer date on the list.

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

1. In the hosting account's team settings, invite a named person from the central support organization by that person's own email address.
   *You should see:* The invitation listed as pending.
2. Give that person a role that can create and manage servers, databases and applications. The exact names of the roles on that screen have not been checked for this guide.
3. Keep the owner role with the chapter.
4. The invited person accepts the invitation and signs in.
   *You should see:* The chapter's account, reached from the invited person's own sign-in.

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

1. Decide whether the chapter will run public webinars through the software. If not, write "no public webinars through Zoom" on the chapter's account list and stop here.
2. Open a Zoom account with a chapter mailbox as the host address.
   *You should see:* The host mailbox signs in to Zoom.
3. On that Zoom account, create a "Server-to-Server OAuth" app, as section 5 of EVENTS-SETUP.md describes.
   *You should see:* Three values - an account identifier, a client identifier and a client secret.
4. Put the client secret in the chapter's Operations vault. Write the host address and the two identifiers on the chapter information form.
   *You should see:* The secret in the vault, and three values on the form.

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

1. In the hosting account's security settings, turn on two-step sign-in.
   *You should see:* Signing in now asks for a second step.
2. Do the same in the Zoom account, if there is one.
   *You should see:* Signing in to Zoom asks for a second step.
3. Put the recovery codes for both in the chapter's vault, where a second named person can reach them.
   *You should see:* The recovery codes listed in the vault.

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

1. Make one list, held by the chapter, with one line per account:
   - The domain registrar.
   - Cloudflare.
   - Google Workspace.
   - The hosting account.
   - The Zoom account, if there is one.
2. On each line write:
   - The web address to sign in at.
   - Who holds the top-level sign-in.
   - Who else has access.
   - Where the recovery codes are.
   - Any nonprofit discount or credit applied.
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

1. In the chapter's DigitalOcean account, create an API token with write access. The screen is under the account's API settings; its exact labels have not been checked for this guide.
   *You should see:* A new token, shown once.
2. In the chapter's Cloudflare account, create an API token with the "Zone, DNS, Edit" permission, limited to the chapter's own zones.
   *You should see:* A new token covering only the chapter's zones.
3. Put both tokens in the chapter's Operations vault.
   *You should see:* Both tokens listed in the vault.
4. In CRMBuilder, enter both as the provider credentials on the chapter's engagement.
   *You should see:* Both credentials shown as configured, and the chapter's Cloudflare zones listed.

**Done when all of these are true:**

- A DigitalOcean API token from the chapter's hosting account exists.
- A Cloudflare API token limited to editing DNS in the chapter's zones exists.
- Both tokens are in the chapter's vault.
- Both tokens are entered in CRMBuilder as the chapter's provider credentials.

**Note:** CRMBuilder builds the chapter's CRM with the chapter's own accounts, never its own (ruled 09-18-26).

**How to check:** CRMBuilder's provider credentials screen shows both configured for the chapter's engagement, and lists the chapter's Cloudflare zones.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A Cloudflare token with more permission than it needs, or one covering every zone in the account. Also, leaving the engagement on CRMBuilder's own tokens by mistake. The server then appears in the wrong hosting account, and nothing says so until someone looks.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the hosting and video meeting accounts (9-Methods-Hosting-Website-Policies.md, version 0.4) with the step list's finishing tests. |
