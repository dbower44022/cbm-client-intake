# Stage 13 — Put the chapter's pages on its website

**Version:** 0.1  
**Last Updated:** 09-18-26 17:30  
**Generated from** `steps/stage-13.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The public learns about the chapter through its website. This stage connects that website to the pages the software serves: the events programme now, and the mentor directory once it is built. The events page is reached by a redirect from the website, not shown inside it (ruled 09-11-26).

**Who:** The chapter makes the website change; the central support organization sets up the application side.  
**Time:** About an hour for the events page. The mentor directory cannot be done yet.  
**Before you start:** The chapter's website, published (step 6.2); The website able to redirect an address (step 6.3); The applications, deployed with the events switches on (stage 11); At least one published event  
**When this stage is done:** The final checks before going live can include the website (step 17.8).

**Steps in this stage:** 13.1 Display the mentor directory page, 13.2 Send the events address to the events programme page, 13.3 Allow only the chapter's own website to display these pages, 13.4 Confirm links to a single mentor work, 13.5 Confirm the public pages read properly on a computer and a phone

---

## 13.1 Display the mentor directory page

**Why:** Visitors to the chapter's website should be able to find the chapter's own mentors.

**Who:** The central support organization then the chapter for the website change  
**Finish first:** step 6.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Nothing can be done yet. There is no public mentor directory page in the software (work list item 10).
2. Do not copy Cleveland's current method, which feeds its mentor pages from a spreadsheet through scripts.

**Done when:** The page displays on the chapter's website, showing that chapter's mentors. Blocked: the public mentor directory page is not built, and whether it is embedded or reached by a redirect is not decided.

**How to check:** A visitor to the chapter's website reaches a list of that chapter's own mentors.

**If it didn't work:** Record the step as blocked and carry on.

---

## 13.2 Send the events address to the events programme page

**Why:** The chapter's website sends visitors to the events page the application serves, so every registration reaches the chapter's CRM.

**Who:** The chapter and the central support organization — the chapter for the website change; the central support organization for the application settings  
**Finish first:** step 6.2, step 6.3

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. On the application's settings page, set the chapter's website address, the website menu, the contact address for presenters and the opening wording of the events page.
2. In the application's Event Administration page, create and publish each upcoming event. Saving there is what gives an event its own web address.
3. Open the application's /webinars/ page.
   *You should see:* The chapter's published events.
4. On the chapter's website, save a copy of the current events page, if there is one. That copy is the way back.
5. On the chapter's website, add a temporary redirect, the kind numbered 302, from the website's events address to the application's /webinars/ page.
   *You should see:* The redirect saved. Never use a permanent redirect; browsers remember it long after it is removed.
6. Register once for an event with an obviously invented surname, then delete the contact and registration this created.

**Done when:** The chapter's website sends visitors to the application's events page, and that page shows the chapter's events.

**How to check:** In a private browser window, the chapter's events address lands on the application's events page, listing the chapter's events.

**If it didn't work:** Remove the redirect. The website's old events page comes back at once.

**What usually goes wrong:** Three things. The page shows Cleveland's navy and gold, because its stylesheet is a copy of Cleveland's and never reads the chapter's colours (work list item 11). An event created straight in the CRM has no web address. And the events record doubles as the internal calendar: only an event with "Publish to website" ticked appears, and an internal meeting published by mistake appears to the public.

---

## 13.3 Allow only the chapter's own website to display these pages

**Why:** An embedded page should appear only inside the chapter's own website, never someone else's.

**Who:** The central support organization  
**Finish first:** step 13.1, step 13.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. For the events page, nothing to do. It is reached by a redirect, and any website may link to a public page.
2. For the mentor directory page, this step applies only if it is embedded. The application would then have to name the one website allowed to embed it. It does not do that today.

**Done when:** The chapter's site can display them and a different site cannot. Applies only to a page embedded in the website. The events programme page is reached by a redirect, so this step does not apply to it.

**How to check:** For an embedded page, the chapter's website shows it and a test page on any other address shows an empty frame.

**If it didn't work:** Record the step as not applying, or as blocked, and carry on.

---

## 13.4 Confirm links to a single mentor work

**Why:** People share links to one mentor, and a shared link must land on that mentor.

**Who:** The central support organization  
**Finish first:** step 13.1

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. For mentors, nothing can be done until the mentor directory page is built.
2. Do the same check for events now. Open one event's page from the programme and copy its address.
3. Open the copied address in a private browser window.
   *You should see:* The same event.

**Done when:** Opening a link to one mentor lands on that mentor, and the address can be copied and shared. Blocked until the public mentor directory page is built.

**How to check:** A copied address opens the same mentor, or the same event, in a private window.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An unpublished event answers "not found". That is deliberate: a page that showed nothing would still reveal the event exists.

---

## 13.5 Confirm the public pages read properly on a computer and a phone

**Why:** Most visitors arrive on a phone, and a page that scrolls sideways or cuts off text loses them.

**Who:** The chapter checked by the central support organization  
**Finish first:** step 13.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the events page on a computer.
   *You should see:* The page filling the window, with the calendar and the recorded library side by side.
2. Open the same page on a phone.
   *You should see:* One column, no sideways scrolling, no text cut off.

**Done when:** The pages show with no sideways scrolling and no cut-off text, on a computer and on a phone.

**How to check:** On a phone, the events page shows one column with nothing cut off.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A page with no styling at all. The events page depends on class names in its copied stylesheet, and a mismatch shows unstyled panels with no error. Cleveland shipped exactly this for an hour on 09-11-26.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for putting the chapter's pages on its website (10-Methods-Website-Pages-Records.md, version 0.2) with the step list's finishing tests. |
