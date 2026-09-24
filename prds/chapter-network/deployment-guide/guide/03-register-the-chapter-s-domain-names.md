# Stage 3 — Register the chapter's domain names

**Version:** 0.3  
**Last Updated:** 09-23-26 13:51  
**Generated from** `steps/stage-03.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Every address the chapter uses hangs off its domain names: its email, its website, its CRM and its applications. This stage buys them in the chapter's name, protects the account that holds them, and moves their DNS to Cloudflare, the DNS provider CRMBuilder writes records into itself. A chapter that already has its DNS at another provider may keep it there instead (manual DNS, step 3.7). Losing the account that holds the domain names loses the chapter's email and website together.

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

1. Use the setup contact's own existing email address. It must be an address the setup contact reads every day, because the registrar, Cloudflare and Proton Pass send their confirmation codes to it.
2. Create an item in the chapter's vault, in the Operations vault, titled "Founding email address — temporary", holding:
   - The address.
   - The setup contact's name.
   - The words "Replace in step 4.14".

   *You should see:* The item in the Operations vault.

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

1. Explain the two choices to the chapter's board. Whether a chapter needs one domain name or two is an open question in the plan:
   - Two domain names, as Cleveland has: one for the public website (clevelandbusinessmentors.org) and a second, shorter one for email and mentor logins (cbmentors.org). Mentors' addresses are short, but there are two names to renew.
   - One domain name for everything. Simpler and cheaper, but the email addresses are tied to the website's name for good.
2. Write down the choice as three values:
   - The website domain name, for example akronbusinessmentors.org.
   - The email domain name, for example akronmentors.org. With one domain name, it is the same as the website domain name.
   - The mentor email domain name. For every chapter so far it is the same as the email domain name.
3. Do not buy separate domain names for the CRM or the applications. They get names under the email or website domain name, created in later steps:
   - crm. for the CRM, for example crm.akronbusinessmentors.org.
   - apps. for the applications, for example apps.akronbusinessmentors.org.
4. Search the registrar the chapter will use for each domain name chosen.
   *You should see:* Each name shown as available to register.

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

1. Choose the registrar. Any ordinary registrar works, because the domain's DNS moves to Cloudflare in step 3.7. Cleveland uses Porkbun (https://porkbun.com); the trial chapter's domain is at GoDaddy. The actions below were written against Porkbun, and its screen labels have not been checked.
2. Open the registrar's sign-up page and create the account with:
   - Email: the founding email address from step 3.1.
   - Password: a new random password of at least 20 characters, generated by Proton Pass.
3. In the account's contact or profile details, enter the chapter as the account holder:
   - Organization: the chapter's legal name, exactly as in the stamped articles (step 1.2).
   - Name: the setup contact's name, as the person acting for the chapter.
   - Address: the chapter's registered address.
4. Create an item in the Operations vault titled "Domain registrar", holding the registrar's web address, the sign-in email and the password.
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

1. In the registrar account, search for each domain name chosen in step 3.2 and add it to the basket.
2. For each domain name, set:
   - Registration period: at least 1 year. Two or more years lowers the risk of a lapse.
   - Registrant: the chapter's legal name, from the account's contact details.
   - Privacy (hiding the owner's details from public lookups): on, if the registrar offers it free. Porkbun does.
3. Pay with the chapter's own payment card from step 1.6, not a personal one.
   *You should see:* Each domain name listed in the account, with an expiry date at least a year ahead.
4. Check the owner of each domain name in the registrar's domain details.
   *You should see:* The chapter as the registrant. With privacy on, a public lookup shows the privacy service instead, so the registrar's own page is the check.

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

1. In the registrar account, open the list of domain names. For each one, turn automatic renewal on. The switch is usually labelled auto-renew; the exact label has not been checked.
   *You should see:* Each domain name shows automatic renewal as on.
2. Open the account's payment methods and check the chapter's card is the default, and its expiry date is more than a year away.
3. Put a reminder in the chapter treasurer's calendar for one month before the card's expiry date, to update the card at the registrar.

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

1. In the registrar account's security settings, turn on two-step sign-in with an authenticator code, not a text message. Use Proton Pass as the authenticator: add the code to the "Domain registrar" item in the Operations vault, so any owner can produce it.
   *You should see:* Signing in now asks for a six-digit code, and the vault item shows the same code.
2. Save the recovery codes the registrar shows into the same "Domain registrar" item in the Operations vault.
   *You should see:* A second chapter officer can open the item and see the recovery codes.

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

1. Find out where each domain name's DNS is hosted today. From a terminal, type the line below, putting the domain name in place of DOMAIN:
   - dig +short NS DOMAIN

   *You should see:* Two or more name servers. Names ending in ns.cloudflare.com mean the DNS is already at Cloudflare. Any other names, such as nsc1.squarespacedns.com, mean another DNS provider hosts it.
2. Decide with the central support organization whether the DNS moves to Cloudflare or stays where it is. A chapter whose email and website already run on its domain may keep its DNS provider; this is called manual DNS (ruled 09-23-26). Moving costs two to three hours and touches the chapter's live email and website. Keeping it means every DNS record in this guide is added by hand at the chapter's DNS provider.
   *You should see:* One answer, agreed by both: Cloudflare, or manual DNS at the named provider.
3. Manual DNS only: do the next three actions, then skip every Cloudflare action in this step.
4. Manual DNS only: in the Operations vault, create an item titled DNS provider, holding:
   - The words Manual DNS, and the provider's name.
   - The provider's sign-in address.
   - The sign-in email and the password. If the registrar from step 3.3 hosts the DNS, name the registrar's item instead.
5. Manual DNS only: give the central support organization's named people the ability to add DNS records at the provider. Use the provider's own team or member feature if it has one; otherwise they use the sign-in held in the vault. Providers name this feature differently, and this guide does not give the labels.
   *You should see:* A named person from the central support organization able to open the domain's DNS records.
6. Manual DNS only: check that two-step sign-in is on for the DNS provider account, with its codes in the DNS provider item. Leave DNSSEC as it is: it only matters when the name servers change, and manual DNS does not change them.
7. Open https://dash.cloudflare.com/sign-up and create the account with:
   - Email: the founding email address from step 3.1. Step 4.14 changes it to a chapter mailbox.
   - Password: a new random password generated by Proton Pass.
8. Create an item in the Operations vault titled "Cloudflare", holding the sign-in email and the password.
9. Add each domain name to the account. The button is labelled Add a domain or Onboard a domain, depending on the dashboard's version. Enter the domain name, and choose the Free plan.
   *You should see:* Cloudflare lists the DNS records it found at the registrar, and then shows two name servers, each ending in ns.cloudflare.com.
10. Compare Cloudflare's list of records with the registrar's. Any record missing from Cloudflare's list, add in Cloudflare now, or it stops working when the name servers change.
11. In the registrar account, open the domain's name server settings (at Porkbun, the domain's name server details; the exact label has not been checked). Delete the registrar's name servers and enter Cloudflare's two, exactly as Cloudflare shows them.
12. In Cloudflare, open your profile's authentication settings and turn on two-step sign-in with an authenticator code, stored in the "Cloudflare" item in the vault. Save Cloudflare's backup codes into the same item.
13. In Cloudflare, open the account's members page and invite each of the central support organization's named people by email, with the Administrator role. The exact page and role names have not been checked.
    *You should see:* Each invited person listed as a member once they accept.
14. Wait for Cloudflare to report each domain name as active. It can take up to a day. From a terminal, this command shows the name servers the world sees; put the domain name in place of DOMAIN:
    - dig +short NS DOMAIN

    *You should see:* Cloudflare's two name servers from the command, and each domain name shown as active in Cloudflare.

**Done when all of these are true:**

- Each domain name is a zone in a Cloudflare account the chapter owns, or, with manual DNS, is hosted in a DNS provider account the chapter owns.
- The registrar points at Cloudflare's name servers, or, with manual DNS, at the chapter's DNS provider's.
- Two-step sign-in is on.
- The central support organization's named people are members.
- The sign-in and recovery codes are in the chapter's vault.

**Note:** CRMBuilder writes DNS records only into Cloudflare. With manual DNS it shows each record, and a person adds it at the chapter's DNS provider (ruled 09-23-26).

**How to check:** Cloudflare shows each domain name as active, and a name-server lookup on each domain name returns Cloudflare's two servers. With manual DNS, the lookup returns the chapter's DNS provider's servers, and a person from the central support organization can open the domain's DNS records there.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** From now on every DNS record is made in Cloudflare, not at the registrar. And Cloudflare's proxy must stay off for the CRM and the applications: both addresses are "DNS only", with the grey cloud, or their certificates fail to issue or renew. The public website can use the proxy; Cleveland's does.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-23-26 13:51 | Manual DNS added (Doug, 09-23-26, amending the 09-18-26 Cloudflare ruling): step 3.7 first looks up where each domain's DNS is hosted, then either moves it to Cloudflare as before or keeps it at the chapter's existing provider, with the provider's sign-in in the vault and the central support organization able to add records there. The finishing test and note changed with the step list (version 0.19). Boston is the first chapter on manual DNS, at Squarespace Domains. |
| 0.2 | 09-19-26 00:35 | Every action made precise (Doug, 09-19-26): what goes in the vault for each account and under what title; the registrar account's fields, with Porkbun as the worked example (Cleveland's registrar, checked by lookup on 09-19-26); the registration settings; an authenticator code held in Proton Pass for two-step sign-in; the Cloudflare sign-up, plan, record check, name server change and member invitation; and the command that confirms the name servers. Registrar and Cloudflare screen labels are not checked, and the steps say so. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for registering the domain names (8-Methods-Organization-Domains-Google.md, version 0.5) with the step list's finishing tests. Step 3.7 now signs up to Cloudflare with the founding address, because the chapter has no mailbox until stage 4. |
