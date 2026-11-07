# Stage 2 — Sign the agreement with the Association

**Version:** 0.5  
**Last Updated:** 11-07-26 15:21  
**Generated from** `steps/stage-02.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Everything after this stage involves one organization spending money and holding administrative access inside another organization's accounts. The agreement sets out what the Association does, what it costs, the rule that every chapter runs the one application unchanged, what access is held, and what the chapter takes if it leaves. The stage ends by setting up the chapter's password vault, so every account created from stage 3 onward has a safe home.

**Who:** The chapter's board and the Association together.  
**Time:** Not known yet. A draft of the standard agreement exists and is in review (09-18-26).  
**When this stage is done:** The chapter's domain names can be registered (stage 3), and every account created from then on goes into the chapter's vault.

**Before you start:**

- The chapter's board, bylaws and named signers (step 1.4)
- The person who acts for the chapter during setup (step 1.7)

**Steps in this stage:**

- 2.1 Agree what the Association does
- 2.2 Agree the cost
- 2.3 Accept the one-application rule
- 2.4 Agree the access the Association will hold
- 2.5 Agree the leaving terms
- 2.6 Sign the agreement
- 2.7 Set up the chapter's password vault

---

## 2.1 Agree what the Association does

**Why:** The chapter needs to know what it will get, what it will not, and how to ask for help, before it relies on anyone.

**Who:** The chapter and the Association

**Finish first:**

- step 1.7 Name the person who acts for the chapter during setup

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Open the standard agreement's schedule of services. A draft of the standard agreement exists and is in review; until it is final, the Association supplies the current draft. Check the schedule says what is provided:
   - Building and running the CRM and the applications.
   - The weekly software release.
   - Support.
2. Check the schedule says what is not provided:
   - The chapter's legal, tax and banking work.
   - Its website's content.
   - Its own training beyond the first sessions.
3. Check the schedule says how requests are made. All three kinds go into one ClickUp system, managed by the whole support team:
   - Feature requests.
   - Defect reports.
   - Support requests.
4. Check the schedule says how requests are answered:
   - No response time is committed.
   - No request is treated as urgent.
   - Everyday requests, such as adding a person or resetting a password, are handled as they arrive.
   - Feature requests and defects are reviewed and scheduled by the central technical committee every two weeks.
5. Give the chapter's board a copy of the schedule.
   *You should see:* The board's copy, with the four checks above all present.

**Done when all of these are true:**

- The chapter has in writing the list of what is provided.
- The chapter has in writing what is not provided.
- The chapter has in writing how quickly ordinary requests are answered.

**How to check:** The chapter can answer, from the document, "who do I ask to add a new staff member, and how is it handled?"

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Slow answers to everyday requests. A chapter that waits too long changes its own system with its own administrator account instead, and its application stops being the same as every other chapter's.

---

## 2.2 Agree the cost

**Why:** The chapter's treasurer must know every recurring cost and who it is paid to, so the budget has no surprises.

**Who:** The chapter and the Association

**Finish first:**

- step 2.1 Agree what the Association does

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Make a cost sheet with one line per supplier. Look up each current price on the supplier's own page on the day the sheet is made, and write the date beside it. Prices change, so this guide does not state them:
   - Hosting: DigitalOcean, https://www.digitalocean.com/pricing/droplets. One server for the CRM, plus the application and its managed database.
   - Google Workspace: https://www.google.com/nonprofits/offerings/workspace/. Nonprofits may get it free or discounted once step 4.13 is approved.
   - Domain names: the registrar's price for each name per year. Cleveland uses Porkbun, https://porkbun.com/products/domains.
   - Cloudflare: the free plan, https://www.cloudflare.com/plans/. No cost unless a paid plan is ever needed. A chapter that keeps its own DNS provider (manual DNS, step 3.7) writes that provider's price instead, often included with the domain name.
   - Proton Pass: Pass Professional, https://proton.me/business/pass. Priced per user per month, with a minimum of three users. Professional is the plan that includes the command-line tool the settings generator needs.
   - Zoom: only for a chapter that runs public webinars (step 5.5).
2. Add one line for the fee paid to the Association. The amount comes from the standard agreement. It is proposed, not ruled, that the fee covers labour only.
3. Add one line marked "open" for the two paid CRM add-on products. Whether they are part of the standard is not decided (work list item 2). Do not quote a total without saying this line is open.
4. Have the chapter's treasurer and the Association both initial the cost sheet.
   *You should see:* A cost sheet with every line priced or marked open, dated and initialled by both.

**Done when:** The fee is agreed in writing, and it is clear which costs the chapter pays directly to other companies rather than through the fee.

**How to check:** The chapter's treasurer can name every recurring cost and who it is paid to.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The CRM add-on products. The permission roles depend on two paid products that a chapter would have to license, and whether they are part of the standard is still open.

---

## 2.3 Accept the one-application rule

**Why:** One release works for every chapter only if every chapter runs the application as the Association designs it, so the chapter agrees to change it only through a feature request (Association ruling 3).

**Who:** The chapter and the Association — the Association explains, the chapter's board accepts

**Finish first:**

- step 2.1 Agree what the Association does

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Send the board this rule in writing, as a page of its own: "One application. Every chapter runs the application as the Association designs it, and does not change it. Chapters may differ through the application's optional settings and through their own processes. A change a chapter wants, such as a new field, is sent to the Association as a feature request. If the central technical committee accepts it, it is built and delivered to every chapter."
2. Show the board how to raise a feature request in the ClickUp system, and that the central technical committee reviews and schedules feature requests every two weeks.
3. At its next meeting, the board minutes a resolution in words like these: "The board has read the one-application rule and accepts it. The chapter holds its own administrator accounts and will not use them to change the application. Any change the chapter wants will be raised as a feature request."
   *You should see:* The signed minute.
4. Send a copy of the minute to the Association.

**Done when:** The chapter's board has been told in writing that the chapter runs the application as the Association designs it and does not change it, that it may differ only through optional settings and its own processes, and has been shown how to ask for a change through a feature request.

**How to check:** The board minutes record that the rule was read and accepted.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A field or a role changed at the chapter "just for us". The chapter can do it, because it holds its own administrator accounts (Association ruling 1), so only this agreement prevents it. The next release may undo the change, and the conformance check reports it.

---

## 2.4 Agree the access the Association will hold

**Why:** The Association works inside the chapter's accounts, so the chapter must know which ones, and that it can withdraw that access.

**Who:** The chapter and the Association

**Finish first:**

- step 2.1 Agree what the Association does

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Write an access schedule into the agreement, one line per account, naming the access each account gives the Association and the step that grants it:
   - The hosting account (DigitalOcean): a team member able to create and manage resources. Granted in step 5.4.
   - The Cloudflare account, or with manual DNS the chapter's DNS provider account: a member able to edit DNS. Granted in step 3.7.
   - Google Workspace: an administrator account of the Association's own. Created in step 4.6.
   - The video meeting account (Zoom), if there is one: an administrator. Granted in step 5.5.
   - The chapter's vault (Proton Pass): a member of the Operations vault only, never the Board vault. Granted in step 2.7.
   - The CRM: an administrator account of the Association's own, for support. Created in steps 9.3 and 9.7. The chapter's own technical person holds an administrator account too (step 14.3).
2. Write in the rule: the chapter holds ultimate authority over its own technology, including its own CRM administrator accounts (Association ruling 1). The Association supports the chapter's own technical person, and works directly on the chapter's system only when that person is unavailable. Chapter staff hold ordinary accounts.
3. Write in the other half of the rule: the chapter can always get in through the server it owns, and can withdraw the Association's access to any account at any time, by removing its members.

**Done when:** It is written down which of the chapter's accounts the Association will administer, and that the chapter may withdraw that access at any time.

**How to check:** The list is in the agreement, and each account on it has a named later step that grants the access.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Promising emergency access with no written way to use it. The emergency access procedure is on the work list (item 5).

---

## 2.5 Agree the leaving terms

**Why:** A chapter must be able to leave with all its data, and the Association must never be able to lock it out.

**Who:** The chapter and the Association

**Finish first:**

- step 2.4 Agree the access the Association will hold

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Write the notice period into the agreement as a number of days, for example 90. The standard agreement sets the number; the draft is in review.
2. Write in the wind-down: what the Association keeps doing during the notice period (the weekly release, backups and support) and what stops on the last day.
3. Write in the leaving kit, with who produces each part:
   - A copy of the CRM's database. Produced by the Association.
   - An export of the application's own database. Produced by the Association.
   - A transfer of the chapter's documents in Google Drive. Nothing to produce: they are already in the chapter's own Google Workspace.
   - The chapter's own files, such as its logo and colour file. Produced by the Association.
4. Write in a perpetual licence to the last version of the software the chapter received.
5. Write in that the Association may stop working for a chapter that stops paying, but can never lock it out.

**Done when all of these are true:**

- The notice period is written into the agreement.
- The wind-down is written into the agreement.
- The list of everything the chapter takes with it is written into the agreement.

**How to check:** Each item in the leaving kit names what it is and who produces it.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Leaving out the application's own database. Some of the chapter's records live only there. The partner and funder discussion notes are there. So is the full history of every submission. So are any analytics pages the chapter built.

---

## 2.6 Sign the agreement

**Why:** Nothing after this stage should happen inside the chapter's accounts without a signed agreement.

**Who:** The chapter and the Association

**Finish first:**

- step 2.1 Agree what the Association does
- step 2.2 Agree the cost
- step 2.3 Accept the one-application rule
- step 2.4 Agree the access the Association will hold
- step 2.5 Agree the leaving terms
- step 1.4 Appoint a board and adopt bylaws

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Check the final agreement includes all four attachments:
   - The schedule of services (step 2.1).
   - The cost sheet (step 2.2).
   - The access schedule (step 2.4).
   - The leaving terms (step 2.5).
2. The officers the board minute names as signers (step 1.4) sign for the chapter, with the date. An authorised person signs for the Association.
3. Save the signed copy as a PDF named "YYYY-MM-DD agreement with the Association.pdf" in a place at least two chapter officers can reach, and send the Association its copy.
   *You should see:* Both sides holding a copy signed and dated by both.

**Done when:** Both sides have signed and each holds a copy.

**How to check:** Both copies are signed and dated.

**If it didn't work:** Stop, and ask the Association before going on.

---

## 2.7 Set up the chapter's password vault

**Why:** Every sign-in, recovery code and machine secret needs one safe place that the chapter owns and the Association can reach.

**Who:** The chapter and the Association — the chapter owns the vault; the Association sets it up alongside

**Finish first:**

- step 2.6 Sign the agreement

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Open https://proton.me/business/pass and buy Pass Professional in the chapter's name, paid with the chapter's card (step 1.6). Choose Professional, not Essentials: Professional includes the command-line tool the settings generator needs. The plan has a minimum of three users.
   *You should see:* A Proton business organization named after the chapter.
2. Sign up the first owner with the founding email address (step 3.1 names it; the chapter has no mailbox of its own until stage 4). Step 4.14 moves the organization's contact address to a chapter mailbox later.
3. In the organization's settings, make two chapter officers administrators of the organization. The exact screen labels have not been checked; look for the organization's user or member settings.
   *You should see:* Two chapter officers listed with administrator rights.
4. Create two vaults, spelled exactly:
   - Operations — shared with the Association's named people. Every sign-in, recovery code and machine secret the system runs on goes here.
   - Board — kept to the chapter, for anything the Association has no need to see.
5. Invite at least two named people from the Association as members of the Operations vault only, with the editor role (able to add and change items, not to manage sharing).
   *You should see:* Their names listed as members of the Operations vault, and not of the Board vault.
6. Turn on two-step sign-in for every chapter owner, and store each owner's Proton recovery phrase in that owner's own safekeeping, not in the vault it unlocks.

**Done when:** The chapter owns a Proton Pass business organization with at least two chapter owners, and at least two named people from the Association are members of its shared operations vault (ruled 09-18-26).

**How to check:** A second chapter owner and a second named person from the Association each sign in and open the Operations vault without help.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A vault owned by the Association instead of the chapter. The chapter could then lose access to its own credentials in a dispute. Also, from stage 3 on, every account must go into the vault the moment it is created, not gathered up afterwards. Use named sign-ins wherever a system allows; the vault holds only what cannot belong to one person.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.5 | 11-07-26 15:21 | Corrected while the Business Mentors Association is set up as a chapter (plan association-setup-plan.md, approved by Doug 11-07-26): "the central support organization" is now "the Association", and "the central committee" is "the central technical committee". Step 2.3 becomes "Accept the one-application rule", rewritten to Association ruling 3. The stage summary, step 2.1's failure and step 2.4's access schedule no longer say the Association holds the only CRM administrator accounts (Association ruling 1). |
| 0.4 | 09-23-26 20:40 | References to stage 9 follow its renumbering from twenty steps to nine (stage 9 version 0.11). |
| 0.3 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): the cost sheet and the access schedule name the chapter's own DNS provider when it keeps one instead of moving to Cloudflare. |
| 0.2 | 09-19-26 00:25 | Every action made precise (Doug, 09-19-26): each schedule's contents as a checklist; a cost sheet with each supplier's own pricing page; the access schedule naming the access and the step that grants it for every account; the wording of the board's resolution; the attachments the signed agreement must carry; and the Proton Pass plan (Pass Professional, which carries the command-line tool, minimum three users), the two vault names and the central members' role. Proton Pass's plans were read from its own page on 09-19-26; its organization screen labels are not checked, and the step says so. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for signing the agreement (8-Methods-Organization-Domains-Google.md, version 0.5) with the step list's finishing tests. Step 2.1 brought up to the 09-18-26 rulings: requests go into ClickUp, the central committee meets every two weeks, and no response time is committed. |
