# Stage 18 — Hand over and start normal support

**Version:** 0.1  
**Last Updated:** 09-18-26 17:30  
**Generated from** `steps/stage-18.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

This stage moves the chapter from being set up to being supported, and proves the chapter can reach everything it owns without help. The central support organization holds the only administrator accounts, so asking for help has to work well, or chapters start asking for administrator accounts of their own.

**Who:** The central support organization, with the chapter's officers.  
**Time:** About two hours of meetings, plus the review three months later.  
**Before you start:** The final checks passed (stage 17); The chapter's first point of contact named (step 16.5); Access to the ClickUp system for the chapter's people (work list item 8)  
**When this stage is done:** Normal support. The chapter is live.

**Steps in this stage:** 18.1 Publish how to get help, 18.2 Explain how to ask for a change, 18.3 Explain the release schedule, 18.4 Hand over the account and access list, 18.5 Confirm the chapter can get in without the central support organization, 18.6 Confirm the leaving terms in practice, 18.7 Set the first review date

---

## 18.1 Publish how to get help

**Why:** The chapter needs to know where every request goes and what to expect, so nobody waits in silence.

**Who:** The central support organization  
**Finish first:** step 2.6, step 16.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Give the chapter's first point of contact access to the ClickUp system the support team uses for new feature requests, defect reports and support requests.
2. Show them how to raise each of the three kinds, and how to follow one to its answer.
3. Explain the three kinds. Everyday requests, such as adding a person, changing someone's team or resetting a password, are handled as they arrive. Defect reports include the version number from the page footer. New feature requests go to the central committee.
4. Tell them plainly that no request is treated as urgent, and that no response time is committed.

**Done when:** The chapter has in writing how to raise a request, that no request is treated as urgent, that everyday requests are handled as they arrive, and that no response time is committed (ruled 09-18-26).

**How to check:** The first point of contact raises a test request in ClickUp and sees it acknowledged.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Everyday requests held for the committee. A new volunteer who waits weeks for an account is how a chapter starts asking for an administrator account of its own.

---

## 18.2 Explain how to ask for a change

**Why:** Every chapter runs the same software, so a change is made for everyone or not at all, and the chapter needs to know who decides.

**Who:** The central support organization  
**Finish first:** step 18.1

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Explain the rule. A requested change is made for every chapter, or it is not made. There is no third answer.
2. Show how to raise a new feature request in ClickUp.
3. Explain that the central committee reviews and schedules features and defects every two weeks, and that an accepted request goes into a weekly release.

**Done when:** The chapter knows where to send a request that would change the software for everyone, who decides, and how often those decisions are made. The central committee decides, every two weeks (ruled 09-18-26).

**How to check:** The chapter can say, without looking it up, that a change is for everyone or not at all.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A request that is "only for us". Granting one exception is how the rule ends.

---

## 18.3 Explain the release schedule

**Why:** Software changes arrive without anyone at the chapter doing anything, so they need to know when, and what to do if something looks wrong.

**Who:** The central support organization  
**Finish first:** step 11.8

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Explain that a new release is named each week at the Sunday 17:00 UTC slot, and the chapter's application takes it by itself.
2. Explain that every chapter moves to the same release at the same time.
3. Explain what to do if something looks wrong on Monday. First refresh the page properly, because a browser can keep an old page. Then raise a defect report with the version number from the page footer.
4. Show the first point of contact where the version number is.
   *You should see:* The version number in the page footer.

**Done when:** The chapter knows software updates arrive automatically on a weekly schedule, roughly when, and what to do if something looks wrong afterwards.

**How to check:** The first point of contact finds the version number in the footer.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A missed weekly slot. It has happened. A late release is harmless, but a chapter told "every Sunday" that sees nothing change should be told why.

---

## 18.4 Hand over the account and access list

**Why:** The chapter owns its accounts, and must know every one of them, who holds it, and how to reach it.

**Who:** The central support organization prepares it; the chapter keeps it  
**Finish first:** step 5.7

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Bring the account list from step 5.7 up to date. It covers the domain registrar, Cloudflare, Google Workspace, the hosting account, the video meeting account if there is one, the chapter's vault, the CRM's administrator accounts, and the documentation site if the chapter has its own.
2. For each account, write who holds the top-level sign-in and who else has access. No passwords on the list; those are in the chapter's vault.
3. Check that no top-level sign-in belongs to a volunteer's personal email address.
4. Go through the list with a named chapter officer.
   *You should see:* The officer recognising every account on it.

**Done when:** The chapter holds the list of every account, who has the top-level sign-in, and who else has access — and a named chapter officer can reach every one of them.

**How to check:** The named officer reads the list and confirms every account is one they recognise.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An account whose top-level sign-in is a volunteer's personal email address. When that volunteer leaves, the chapter loses the account.

---

## 18.5 Confirm the chapter can get in without the central support organization

**Why:** The promise that neither side can lock the other out is only real once a chapter officer has done it.

**Who:** The chapter and the central support organization — the chapter officer does it; the central support organization watches  
**Finish first:** step 18.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. While someone watches, the officer signs in to the hosting account with their own sign-in.
2. The officer signs in to the Google Workspace admin console.
3. The officer signs in to the domain registrar account.
4. The officer reaches the CRM server through the hosting account. No written procedure exists for this yet (work list item 5), so this action cannot be completed.
5. Record the date on the chapter's entry in the list of watched systems.

**Done when:** A named chapter officer has demonstrated, not merely been told, that they can reach the server, the hosting account, the Google Workspace account and the domain registrar account on their own. The agreement says neither side can lock the other out; this is the step that makes that true rather than stated.

**How to check:** The officer has signed in to all four, and the date is recorded.

**If it didn't work:** Record the step as blocked on the emergency access procedure, and carry on.

**What usually goes wrong:** Being told instead of shown. An access route nobody has used is a promise, not a capability.

---

## 18.6 Confirm the leaving terms in practice

**Why:** A chapter should know exactly what it keeps if it leaves, before it ever needs to.

**Who:** The central support organization  
**Finish first:** step 2.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Walk the chapter through the four parts of the leaving kit. The CRM, which is already on the chapter's own server. An export of the application's own database. The shared drive documents. A licence to the last version received.
2. Explain that some records live only in the application's database, such as partner and funder discussion notes and the history of every public form submission, so keeping the CRM is not keeping all the data.
3. Explain which parts depend on the chapter's choice of Google Workspace branch.

**Done when:** The chapter has been shown exactly what it would receive if it left, and who produces each part.

**How to check:** The chapter can list the four parts, and knows which depend on its Google Workspace branch.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter that chose a Google Workspace provided by the central support organization finding out only now what leaving costs. Nobody has produced a leaving kit yet (work list item 9).

---

## 18.7 Set the first review date

**Why:** The first months show what the guide and the support route got wrong, and a booked review makes sure someone looks.

**Who:** The chapter and the central support organization  
**Finish first:** step 18.1, step 18.2, step 18.3, step 18.4, step 18.5, step 18.6

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Book a meeting about three months out, in both organizations' calendars.
2. At it, go through the requests raised, any feature requests and their answers, whether a restore test has run since go-live, and whether the account list is still right.

**Done when:** A date is booked to review how the first months have gone.

**How to check:** The meeting is in both calendars.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for the handover (11-Methods-Handover.md, version 0.5) with the step list's finishing tests. |
