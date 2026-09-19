# Stage 13 — Put the chapter's pages on its website

**Version:** 0.2  
**Last Updated:** 09-19-26 00:15  
**Generated from** `steps/stage-13.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The public learns about the chapter through its website. This stage connects that website to the pages the software serves: the events programme now, and the mentor directory once it is built. The events page is reached by a redirect from the website, not shown inside it (ruled 09-11-26).

**Who:** The chapter makes the website change; the central support organization sets up the application side.  
**Time:** About an hour for the events page. The mentor directory cannot be done yet.  
**When this stage is done:** The final checks before going live can include the website (step 17.8).

**Before you start:**

- The chapter's website, published (step 6.2)
- The website able to redirect an address (step 6.3)
- The applications, deployed with the events switches on (stage 11)
- At least one published event

**Steps in this stage:**

- 13.1 Display the mentor directory page
- 13.2 Send the events address to the events programme page
- 13.3 Allow only the chapter's own website to display these pages
- 13.4 Confirm links to a single mentor work
- 13.5 Confirm the public pages read properly on a computer and a phone

---

## 13.1 Display the mentor directory page

**Why:** Visitors to the chapter's website should be able to find the chapter's own mentors.

**Who:** The central support organization then the chapter for the website change

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Nothing can be done yet. The software has no public mentor directory page (work list item 10). Record the step as blocked.
2. Do not copy Cleveland's current method, which feeds its mentor pages from a spreadsheet through scripts.

**Done when:** The page displays on the chapter's website, showing that chapter's mentors. Blocked: the public mentor directory page is not built, and whether it is embedded or reached by a redirect is not decided.

**How to check:** A visitor to the chapter's website reaches a list of that chapter's own mentors.

**If it didn't work:** Record the step as blocked and carry on.

---

## 13.2 Send the events address to the events programme page

**Why:** The chapter's website sends visitors to the events page the application serves, so every registration reaches the chapter's CRM.

**Who:** The chapter and the central support organization — the chapter for the website change; the central support organization for the application settings

**Finish first:**

- step 6.2 Publish the website
- step 6.3 Confirm the website can redirect an address to another site

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open https://APP-ADDRESS/setup/ and sign in as the central support organization's administrator. Set these settings, one at a time, and save each:
   - ORGANIZATION_WEBSITE_URL: the chapter's website address, for example https://WEBSITE-DOMAIN
   - ORGANIZATION_SITE_NAV: the website's menu, as Label|path pairs separated by commas, for example Home|/,About|/about/,Webinars|/webinars/,Contact|/contact/
   - EVENTS_CONTACT_EMAIL: the address presenters write to; empty uses the shared operations mailbox
   - EVENTS_HERO_TAGLINE: the heading at the top of the events page
   - EVENTS_HERO_PILLARS: the short line under the heading
   - EVENTS_HERO_BAND: the gold band's wording; empty hides it
   - EVENTS_PUBLIC_BASE_URL: leave empty, so event links point at this application
   *You should see:* Each setting shown with its new value.
2. Open https://APP-ADDRESS/events/ and choose + New event. For each upcoming event fill in its title, format, topic, start and duration, and tick Publish to website, then save.
   *You should see:* Each event in the grid, shown as published to the website.
3. Open https://APP-ADDRESS/webinars/ in a browser.
   *You should see:* The published events in the left panel, and the recorded library on the right.
4. In the website's administration, open the current events page and export or copy its content to a file. This is the way back. The export's label depends on the website platform.
   *You should see:* A file you can open and read. If you cannot export it, stop.
5. In the website's administration, add a redirect. Use a temporary redirect (numbered 302), never a permanent one, because browsers remember a permanent redirect long after it is removed. The menu is called Redirection, Tools then Redirects, or similar, depending on the website platform's redirect tool:
   - From: /webinars/
   - To: https://APP-ADDRESS/webinars/
   - Type: 302 (temporary)
6. Open https://WEBSITE-DOMAIN/webinars/ in a private browser window.
   *You should see:* The application's events page, with the published events.
7. Choose Sign Up on one event and register with an obviously invented surname, ZZTEST.
   *You should see:* A confirmation message in the sign-up window.
8. In the CRM, open the contact named ZZTEST and delete it, then delete its event registration.
   *You should see:* Neither record present.

**Done when:** The chapter's website sends visitors to the application's events page, and that page shows the chapter's events.

**How to check:** In a private browser window, the chapter's events address lands on the application's events page, listing the chapter's events.

**If it didn't work:** Remove the redirect. The website's old events page comes back at once.

**What usually goes wrong:** Three things. The page shows Cleveland's navy and gold, because its stylesheet is a copy of Cleveland's and never reads the chapter's colours (work list item 11). An event created straight in the CRM has no web address. And the events record doubles as the internal calendar: only an event with "Publish to website" ticked appears, and an internal meeting published by mistake appears to the public.

---

## 13.3 Allow only the chapter's own website to display these pages

**Why:** An embedded page should appear only inside the chapter's own website, never someone else's.

**Who:** The central support organization

**Finish first:**

- step 13.1 Display the mentor directory page
- step 13.2 Send the events address to the events programme page

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. For the events page, nothing to do. It is reached by a redirect, and any website may link to a public page. Record the step as not applying.
2. For the mentor directory page, this step applies only if the page is embedded. The application would then have to send a header naming the one website allowed to embed it, and it does not do that today. Record the step as blocked.

**Done when:** The chapter's site can display them and a different site cannot. Applies only to a page embedded in the website. The events programme page is reached by a redirect, so this step does not apply to it.

**How to check:** For an embedded page, the chapter's website shows it and a test page on any other address shows an empty frame.

**If it didn't work:** Record the step as not applying, or as blocked, and carry on.

---

## 13.4 Confirm links to a single mentor work

**Why:** People share links to one mentor, and a shared link must land on that mentor.

**Who:** The central support organization

**Finish first:**

- step 13.1 Display the mentor directory page

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. For mentors, nothing can be done until the mentor directory page is built. Record that half as blocked.
2. For events, open https://WEBSITE-DOMAIN/webinars/ and select one event's title.
   *You should see:* The event's own page, at an address of the form https://APP-ADDRESS/webinars/EVENT-SLUG.
3. Copy the address from the browser's address bar and open it in a private browser window.
   *You should see:* The same event.

**Done when:** Opening a link to one mentor lands on that mentor, and the address can be copied and shared. Blocked until the public mentor directory page is built.

**How to check:** A copied address opens the same mentor, or the same event, in a private window.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An unpublished event answers "not found". That is deliberate: a page that showed nothing would still reveal the event exists.

---

## 13.5 Confirm the public pages read properly on a computer and a phone

**Why:** Most visitors arrive on a phone, and a page that scrolls sideways or cuts off text loses them.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 13.2 Send the events address to the events programme page

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. On a computer, open https://WEBSITE-DOMAIN/webinars/ with the browser window at full width.
   *You should see:* The calendar and the recorded library side by side, filling the window.
2. On a phone, open the same address.
   *You should see:*
   - One column
   - No sideways scrolling
   - No text cut off
   - Every panel styled, with no plain unstyled blocks

**Done when:** The pages show with no sideways scrolling and no cut-off text, on a computer and on a phone.

**How to check:** On a phone, the events page shows one column with nothing cut off.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A page with no styling at all. The events page depends on class names in its copied stylesheet, and a mismatch shows unstyled panels with no error. Cleveland shipped exactly this for an hour on 09-11-26.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-19-26 00:15 | Every action made precise (Doug, 09-19-26): the exact settings to set on the settings page, the exact addresses, the redirect's exact from, to and type, and the ZZTEST registration check, from EVENTS-SETUP.md section 6b. |
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for putting the chapter's pages on its website (10-Methods-Website-Pages-Records.md, version 0.2) with the step list's finishing tests. |
