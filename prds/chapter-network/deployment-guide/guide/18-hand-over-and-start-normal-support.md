# Stage 18 — Hand over and start normal support

**Version:** 0.3  
**Last Updated:** 09-23-26 13:54  
**Generated from** `steps/stage-18.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

This stage moves the chapter from being set up to being supported, and proves the chapter can reach everything it owns without help. The central support organization holds the only administrator accounts, so asking for help has to work well, or chapters start asking for administrator accounts of their own.

**Who:** The central support organization, with the chapter's officers.  
**Time:** About two hours of meetings, plus the review three months later.  
**When this stage is done:** Normal support. The chapter is live.

**Before you start:**

- The final checks passed (stage 17)
- The chapter's first point of contact named (step 16.5)
- Access to the ClickUp system for the chapter's people (work list item 8)

**Steps in this stage:**

- 18.1 Publish how to get help
- 18.2 Explain how to ask for a change
- 18.3 Explain the release schedule
- 18.4 Hand over the account and access list
- 18.5 Confirm the chapter can get in without the central support organization
- 18.6 Confirm the leaving terms in practice
- 18.7 Set the first review date

---

## 18.1 Publish how to get help

**Why:** The chapter needs to know where every request goes and what to expect, so nobody waits in silence.

**Who:** The central support organization

**Finish first:**

- step 2.6 Sign the agreement
- step 16.5 Name the chapter's own first point of contact

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Invite the chapter's first point of contact to the ClickUp system the support team uses for requests, at their chapter email address. The address of that ClickUp space, and how a chapter's people are given access to it, are not settled yet (work list item 8). The central support organization supplies both.
   *You should see:* The first point of contact signed in to ClickUp and able to see the chapter's requests.
2. Show them the three kinds of request, and how to raise each one in ClickUp:
   - Support request: an everyday task needing an administrator, such as adding a person, changing someone's team or resetting a password. Handled by the support team as it arrives.
   - Defect report: something that worked and has stopped, or does the wrong thing. Include the page address, what was expected, what happened, and the version number from the page footer.
   - New feature request: anything that would change the software. Reviewed by the central committee every two weeks.
3. Have them raise one test support request, titled "Test request from CHAPTER-NAME — please close", and watch it to its answer.
   *You should see:* The request acknowledged and closed by the support team.
4. Send the chapter's first point of contact an email, and keep a copy, saying:
   - Every request goes into ClickUp.
   - No request is treated as urgent.
   - Everyday requests are handled as they arrive.
   - No response time is committed.
   - Before raising a request, a forgotten password can be reset from "Forgot your password?" on the sign-in page.

**Done when all of these are true:**

- The chapter has in writing how to raise a request.
- The chapter has in writing that no request is treated as urgent.
- The chapter has in writing that everyday requests are handled as they arrive.
- The chapter has in writing that no response time is committed (ruled 09-18-26).

**How to check:** The first point of contact's test request was acknowledged and closed, and the email is sent.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Everyday requests held for the committee. A new volunteer who waits weeks for an account is how a chapter starts asking for an administrator account of its own.

---

## 18.2 Explain how to ask for a change

**Why:** Every chapter runs the same software, so a change is made for everyone or not at all, and the chapter needs to know who decides.

**Who:** The central support organization

**Finish first:**

- step 18.1 Publish how to get help

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Say the rule in these words: "Every chapter runs the same software. A change you ask for is made for every chapter, or it is not made. There is no third answer."
2. Show them how to raise a new feature request in ClickUp, as in step 18.1.
3. Explain what happens to it:
   - The central committee reviews and schedules features and defects every two weeks.
   - An accepted request goes into a weekly release (step 18.3).

**Done when all of these are true:**

- The chapter knows where to send a request that would change the software for everyone.
- The chapter knows who decides.
- The chapter knows how often those decisions are made.

**Note:** The central committee decides, every two weeks (ruled 09-18-26).

**How to check:** The chapter can say, without looking it up, that a change is for everyone or not at all.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A request that is "only for us". Granting one exception is how the rule ends.

---

## 18.3 Explain the release schedule

**Why:** Software changes arrive without anyone at the chapter doing anything, so they need to know when, and what to do if something looks wrong.

**Who:** The central support organization

**Finish first:**

- step 11.8 Set the update policy to Latest Stable

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Explain when: a new release is named each week at 17:00 UTC on Sunday. That is 1 p.m. Eastern in summer and 12 noon Eastern in winter. The chapter's application then takes it by itself.
2. Explain that every chapter moves to the same release at the same time.
3. Explain what to do if something looks wrong afterwards:
   - Refresh the page fully: Ctrl and Shift and R on Windows, or Cmd and Shift and R on a Mac. A browser can keep an old copy of a page.
   - If it is still wrong, raise a defect report in ClickUp (step 18.1) with the version number from the page footer.
4. Open any application page with the first point of contact and point to the footer.
   *You should see:* The version number in the footer, for example v0.231.1, followed by (Production).
5. Show where the release itself is reported: open APP-ADDRESS/healthz.
   *You should see:* A line named releaseTag, with the release's name.

**Done when all of these are true:**

- The chapter knows software updates arrive automatically on a weekly schedule.
- The chapter knows roughly when.
- The chapter knows what to do if something looks wrong afterwards.

**How to check:** The first point of contact finds the version number in the footer without help.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A missed weekly slot. It has happened. A late release is harmless, but a chapter told "every Sunday" that sees nothing change should be told why.

---

## 18.4 Hand over the account and access list

**Why:** The chapter owns its accounts, and must know every one of them, who holds it, and how to reach it.

**Who:** The central support organization prepares it; the chapter keeps it

**Finish first:**

- step 5.7 Write down every account the chapter now owns

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Bring the account list from step 5.7 up to date. It has one line per account, with the address to sign in at:
   - The domain registrar: the registrar's own sign-in address
   - Cloudflare: https://dash.cloudflare.com, or with manual DNS the chapter's DNS provider's sign-in address
   - Google Workspace: https://admin.google.com
   - The hosting account: https://cloud.digitalocean.com
   - The video meeting account, if there is one: https://zoom.us
   - The chapter's vault: https://pass.proton.me
   - The CRM's administrator accounts: CRM-ADDRESS
   - The documentation site, if the chapter has its own: its address
2. On each line, write:
   - Who holds the top-level sign-in
   - Who else has access
   - That the password and recovery codes are in the chapter's vault. Never the password itself.
3. Check each top-level sign-in address. None may be a volunteer's personal email address; each must be a chapter mailbox.
   *You should see:* Chapter email addresses only.
4. Go through the list line by line with a named chapter officer.
   *You should see:* The officer recognising every account on it.

**Done when all of these are true:**

- The chapter holds the list of every account.
- The list says who has the top-level sign-in.
- The list says who else has access.
- A named chapter officer can reach every one of them.

**How to check:** The named officer reads the list and confirms every account is one they recognise.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An account whose top-level sign-in is a volunteer's personal email address. When that volunteer leaves, the chapter loses the account.

---

## 18.5 Confirm the chapter can get in without the central support organization

**Why:** The promise that neither side can lock the other out is only real once a chapter officer has done it.

**Who:** The chapter and the central support organization — the chapter officer does it; the central support organization watches

**Finish first:**

- step 18.4 Hand over the account and access list

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. With someone from the central support organization watching, the chapter officer signs in with their own sign-in, not a shared one, to each of these:
   - The hosting account, at https://cloud.digitalocean.com
   - The Google Workspace admin console, at https://admin.google.com
   - The domain registrar account, at the registrar's own sign-in address
   *You should see:* Each account's home page, under the officer's own name.
2. In the hosting account, the officer opens the CRM server's page and opens its web console. The exact label of the console action is not verified.
   *You should see:* A command prompt on the CRM server.
3. What the officer does once inside the server, to regain the CRM without the central support organization, is not written yet (work list item 5). Until it is, record this part as blocked.
4. Add the date and the officer's name to the chapter's entry in the list of watched systems (step 12.5).

**Done when all of these are true:**

- A named chapter officer has demonstrated, not merely been told, that they can reach the server on their own.
- The officer has demonstrated the same for the hosting account.
- The officer has demonstrated the same for the Google Workspace account.
- The officer has demonstrated the same for the domain registrar account.

**Note:** The agreement says neither side can lock the other out; this is the step that makes that true rather than stated.

**How to check:** The officer has signed in to all four, and the date is recorded.

**If it didn't work:** Record the step as blocked on the emergency access procedure, and carry on.

**What usually goes wrong:** Being told instead of shown. An access route nobody has used is a promise, not a capability.

---

## 18.6 Confirm the leaving terms in practice

**Why:** A chapter should know exactly what it keeps if it leaves, before it ever needs to.

**Who:** The central support organization

**Finish first:**

- step 2.5 Agree the leaving terms

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Walk the chapter through the four parts of the leaving kit, and who produces each:
   - The CRM. Already on the chapter's own server, so nobody needs to produce it.
   - An export of the application's own database. Produced by the central support organization. No script produces it yet (work list item 9).
   - The shared drive documents. Already in the chapter's own Google Workspace.
   - A licence to the last version of the software received. Written in the agreement.
2. Explain what only the application's database holds, so keeping the CRM is not keeping all the data:
   - The discussion notes on partner and funder records.
   - The history of every public form submission and the replies to it.
   - The chapter's own analytics pages.
3. Explain that the chapter's mail, documents and calendars are already in its own Google Workspace, so they stay with it.

**Done when:** The chapter has been shown exactly what it would receive if it left, and who produces each part.

**How to check:** The chapter can list the four parts of the leaving kit.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Forgetting the application's own database. Keeping the CRM is not keeping all the data.

---

## 18.7 Set the first review date

**Why:** The first months show what the guide and the support route got wrong, and a booked review makes sure someone looks.

**Who:** The chapter and the central support organization

**Finish first:**

- step 18.1 Publish how to get help
- step 18.2 Explain how to ask for a change
- step 18.3 Explain the release schedule
- step 18.4 Hand over the account and access list
- step 18.5 Confirm the chapter can get in without the central support organization
- step 18.6 Confirm the leaving terms in practice

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Book a one-hour meeting 90 days after the chapter's go-live date, titled "CHAPTER-NAME: first review", and invite:
   - The chapter's first point of contact
   - The chapter officer named in step 18.4
   - One member of the central committee
   - One member of the support team
   *You should see:* The meeting in both organizations' calendars.
2. Put this agenda in the invitation:
   - The requests raised in ClickUp, and how they went.
   - Any feature requests, and their answers.
   - Whether a restore test has run since go-live.
   - Whether the account list from step 18.4 is still right.

**Done when:** A date is booked to review how the first months have gone.

**How to check:** The meeting is in both calendars, with the agenda.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): the handover account list names the chapter's own DNS provider when it kept one. |
| 0.2 | 09-19-26 00:04 | Actions made precise (Doug, 09-19-26): the three kinds of ClickUp request and what each contains, a test request, the exact wording to send, the release time in Eastern time and the health address, each account's sign-in address, the server console check, the four parts of the leaving kit with who produces each, and the review meeting's invitees and agenda. The ClickUp space address and how chapters get access to it are not settled, and step 18.1 says so. |
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for the handover (11-Methods-Handover.md, version 0.5) with the step list's finishing tests. |
