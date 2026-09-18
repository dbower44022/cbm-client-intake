# Stage 3 — Register the chapter's domain names

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-03.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Every address the chapter uses hangs off its domain names: its email, its website, its CRM and its applications. This stage buys them in the chapter's name, protects the account that holds them, and moves their DNS to Cloudflare, the only DNS provider CRMBuilder can build with. Losing the account that holds the domain names loses the chapter's email and website together.

**Who:** The chapter's setup contact, with the central support organization for the Cloudflare step.  
**Time:** About an hour of work. A change of name servers can take up to a day to be seen everywhere.  
**When this stage is done:** Google Workspace and the chapter's email can be set up on the domain (stage 4).

**Before you start:**

- The chapter's name (step 1.1) and bank account (step 1.6)
- The person who acts for the chapter during setup (step 1.7)
- The chapter's vault (step 2.7)

**Steps in this stage:**

- 3.1 Choose the founding email address used for setup
- 3.2 Decide how many domain names the chapter needs, and choose them
- 3.3 Create the domain registrar account
- 3.4 Register and pay for the domain names
- 3.5 Turn on automatic renewal
- 3.6 Turn on two-step sign-in for the registrar account
- 3.7 Move the domain names' DNS to the chapter's Cloudflare account

---

## 3.1 Choose the founding email address used for setup

**Why:** The chapter has no email of its own until stage 4, so the first accounts must be opened with someone's existing address, and everyone must know it is temporary.

**Who:** The chapter — the setup contact

**Finish first:**

- step 1.7 Name the person who acts for the chapter during setup

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Use the setup contact's own existing email address.
2. Write down the address, the person's name, and that the address is temporary. Step 4.14 replaces it.

**Done when:** One named person's existing working email address is recorded as the address that will create the first accounts, and it is understood that this is temporary.

**How to check:** The address and the person's name are written down, marked temporary.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Forgetting the address is temporary. The domain names then stay tied to one volunteer's personal email for years.

---

## 3.2 Decide how many domain names the chapter needs, and choose them

**Why:** The email domain name becomes part of every mentor's address for good, so it has to be chosen deliberately.

**Who:** The chapter advised by the central support organization

**Finish first:**

- step 1.1 Choose the chapter's name

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Explain both choices to the chapter. Cleveland uses two domain names: one for the public website, and a second, shorter one for email addresses and mentor logins. One domain name for everything is simpler, but ties the email addresses to the marketing name for good. Whether a chapter needs one or two is an open question in the plan.
2. Record which the chapter chose.
3. Choose the names. The CRM and the applications get names under a domain the chapter owns, such as crm. and apps., not new domain names.
4. Search a domain registrar for each chosen name.
   *You should see:* Each name shown as available.

**Done when:** The names are chosen and confirmed available. See the open question in the plan document about whether a chapter needs one domain name or two.

**How to check:** The chosen names are written down, and a registrar's search shows each one available.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A long email domain name. Every mentor's address is their first and last name at that domain name, so a long domain name makes long addresses.

---

## 3.3 Create the domain registrar account

**Why:** The domain names must sit in an account that belongs to the chapter, not to a person.

**Who:** The chapter — the setup contact

**Finish first:**

- step 3.1 Choose the founding email address used for setup
- step 3.2 Decide how many domain names the chapter needs, and choose them

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open an account at an ordinary domain registrar.
2. Enter the chapter's legal name as the account holder, not the setup contact's own name.
3. Use the founding email address from step 3.1.
4. Put the sign-in in the chapter's vault, in the Operations vault.
   *You should see:* The registrar's account page shows the chapter's legal name.

**Done when all of these are true:**

- The account exists.
- The account is in the chapter's name.
- The account uses the founding email address.

**How to check:** The registrar's account page shows the chapter's legal name.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An account in a person's own name. If that person leaves, the registrar may refuse to hand the domain names to the chapter.

---

## 3.4 Register and pay for the domain names

**Why:** The domain names must be bought in the chapter's name and paid for by the chapter, so they do not lapse when one person's card expires.

**Who:** The chapter — the setup contact

**Finish first:**

- step 3.3 Create the domain registrar account
- step 1.6 Open a bank account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Register each domain name chosen in step 3.2, for at least a year.
2. Pay with the chapter's own payment card, not a personal one.
3. Look up the ownership of each domain name.
   *You should see:* The chapter as the registrant. If the registrar hides the owner behind a privacy service, the registrar's own account page is the check.

**Done when:** A public ownership lookup returns the chapter as the registrant, and the registration runs at least a year ahead.

**How to check:** An ownership lookup, or the registrar's account page, shows the chapter as registrant and an expiry date at least a year ahead.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Paying with a personal card. When that card expires, the renewal fails, and nobody at the chapter is told.

---

## 3.5 Turn on automatic renewal

**Why:** A lapsed domain name stops the chapter's email, website, CRM and applications all at once.

**Who:** The chapter — the setup contact

**Finish first:**

- step 3.4 Register and pay for the domain names

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the registrar account, turn on automatic renewal for every domain name.
   *You should see:* Each domain name shows automatic renewal as on.
2. Check the expiry date of the payment card on file.

**Done when:** Every domain name is set to renew automatically and a working payment method is on file.

**How to check:** Each domain name shows automatic renewal as on, and the card on file is in date.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A lapsed domain name. The chapter's email and website stop together, and so do the CRM and the applications, whose addresses are under that domain name.

---

## 3.6 Turn on two-step sign-in for the registrar account

**Why:** Whoever signs in to the registrar account controls every address the chapter has.

**Who:** The chapter — the setup contact

**Finish first:**

- step 3.3 Create the domain registrar account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the registrar account, turn on two-step sign-in.
   *You should see:* Signing in now asks for a second step.
2. Put the recovery codes in the chapter's vault, where at least two officers can reach them.

**Done when:** Signing in requires a second factor, and the recovery codes are stored where more than one person can reach them.

**How to check:** Signing in asks for the second step, and a second officer can open the recovery codes in the vault.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The second step tied to one person's phone, and the recovery codes held by the same person.

---

## 3.7 Move the domain names' DNS to the chapter's Cloudflare account

**Why:** CRMBuilder writes the CRM's address into Cloudflare itself, so the chapter's domain names must live in a Cloudflare account the chapter owns.

**Who:** The chapter and the central support organization — the chapter's setup contact, with the central support organization

**Finish first:**

- step 3.4 Register and pay for the domain names
- step 3.6 Turn on two-step sign-in for the registrar account
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Create a Cloudflare account in the chapter's name. The free plan is enough. The chapter has no mailbox of its own yet, so sign up with the founding email address and change it to a chapter mailbox after stage 4, as step 4.14 does for the registrar.
2. Add each domain name to the Cloudflare account.
   *You should see:* Cloudflare reads the existing records and gives two name servers ending in ns.cloudflare.com.
3. In the registrar account, replace the name servers with Cloudflare's two.
4. Turn on two-step sign-in in Cloudflare. Put the sign-in and recovery codes in the chapter's vault.
5. Invite the central support organization's named people as members of the Cloudflare account.
6. Wait for Cloudflare to report each domain name as active. It can take up to a day.
   *You should see:* Each domain name shown as active in Cloudflare.

**Done when all of these are true:**

- Each domain name is a zone in a Cloudflare account the chapter owns.
- The registrar points at Cloudflare's name servers.
- Two-step sign-in is on.
- The central support organization's named people are members.
- The sign-in and recovery codes are in the chapter's vault.
- CRMBuilder supports no other DNS provider.

**How to check:** Cloudflare shows each domain name as active, and a name-server lookup on each domain name returns Cloudflare's two servers.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** From now on every DNS record is made in Cloudflare, not at the registrar. And Cloudflare's proxy must stay off for the CRM and the applications: both addresses are "DNS only", with the grey cloud, or their certificates fail to issue or renew. The public website can use the proxy; Cleveland's does.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for registering the domain names (8-Methods-Organization-Domains-Google.md, version 0.5) with the step list's finishing tests. Step 3.7 now signs up to Cloudflare with the founding address, because the chapter has no mailbox until stage 4. |
