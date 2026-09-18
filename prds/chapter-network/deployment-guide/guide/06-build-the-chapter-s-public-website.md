# Stage 6 — Build the chapter's public website

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-06.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The public website is the chapter's own marketing site. The software does not build it, but it needs four things from it - addresses for the policy documents, a place to host the chapter's colour file, a link to the public application forms, and a way to send visitors to the events page the applications serve. This stage makes sure the site can do all four, and that someone at the chapter can change it.

**Who:** The chapter. The central support organization writes the colour file and helps with the help documentation decision.  
**Time:** Not known. A chapter that already has a website finishes in an hour; building a new site can take weeks.  
**Before you start:** The chapter's domain names (stage 3); The chapter's name (step 1.1)  
**When this stage is done:** The policy documents (stage 7) can be published on the site, and the chapter information form (stage 8) can be filled in with the site's addresses.

**Steps in this stage:** 6.1 Choose the website platform, 6.2 Publish the website, 6.3 Confirm the website can redirect an address to another site, 6.4 Confirm someone at the chapter can edit the website, 6.5 Choose the chapter's colours and publish the colour file, 6.6 Produce the chapter's logo image, 6.7 Decide where the chapter's help documentation lives

---

## 6.1 Choose the website platform

**Why:** The site must be able to publish pages, host a small file and redirect one address to another, and someone must own it.

**Who:** The chapter  
**Finish first:** step 3.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. If the chapter already has a website, keep it. Otherwise choose any platform that can publish pages, host a small file and redirect one address to another. Cleveland's runs on WordPress with the Elementor page builder.
2. Name the person who will build and maintain the site, and write the platform and their name on the chapter's account list (step 5.7).
   *You should see:* The platform and a named person on the list.

**Done when:** The choice is made and someone is named to build and maintain the site.

**How to check:** The platform and the person's name are on the chapter's account list.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Nobody named to maintain it. A website built by a volunteer who then leaves is a website nobody can change.

---

## 6.2 Publish the website

**Why:** Every later page the software links to lives on this site, and it must load securely.

**Who:** The chapter  
**Finish first:** step 6.1

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Publish the site at the chapter's website domain, at an address beginning https://.
2. Open the site in a private browser window.
   *You should see:* The site, with no security warning.

**Done when:** The site loads at the chapter's website domain over a secure connection.

**How to check:** The site opens in a private browser window at https:// and the chapter's domain, with no security warning.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A certificate that is not renewed. The site then shows a security warning to every visitor.

---

## 6.3 Confirm the website can redirect an address to another site

**Why:** The chapter's events page will be a redirect to the page the applications serve, so the site must be able to do one.

**Who:** The chapter  
**Finish first:** step 6.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. On the website, add a temporary redirect (the kind numbered 302) from a test address, such as /redirect-test, to any page on another site. Most platforms do this through a redirect setting or a redirect add-on.
2. Open the test address in a private browser window.
   *You should see:* The other site's page.
3. Remove the redirect.

**Done when:** A test address on the site sends the visitor to a page on another site, by a temporary redirect. (Checking that the site can embed a page returns once the public mentor directory page is built and its method is decided.)

**How to check:** The test address lands on the other site's page.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A website platform that cannot redirect one address without a paid plan. Find out now, not at stage 13.

---

## 6.4 Confirm someone at the chapter can edit the website

**Why:** The policy documents (stage 7) and the events redirect (stage 13) both need changes on the site, made by someone at the chapter.

**Who:** The chapter  
**Finish first:** step 6.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The named person signs in to the website with their own sign-in.
2. They change one word on one page, check the public site, and change it back.
   *You should see:* The change on the public site, then gone again.

**Done when:** A named person at the chapter has signed in and made a change.

**How to check:** The change appeared on the public site.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The only sign-in belongs to the person or company who built the site.

---

## 6.5 Choose the chapter's colours and publish the colour file

**Why:** Colours are the only visual difference between chapters in the software, so a chapter that skips this looks exactly like Cleveland.

**Who:** The chapter and the central support organization — the chapter chooses the colours, the central support organization writes the file  
**Finish first:** step 6.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Choose the chapter's colours. The main ones are the primary colour (Cleveland's navy,
2. The central support organization writes a small stylesheet that sets new values only for colour names starting --cbm-, on :root, and nothing else. The names are in frontend/shared/tokens.css. Anything left out keeps Cleveland's value. There is no starter file yet (work list item 4).
3. Publish the file on the chapter's website, so it has its own web address.
4. Open the file's address in a browser.
   *You should see:* The stylesheet's text, not a download and not an error.
5. Write the address on the chapter information form. It becomes the setting CHAPTER_TOKENS_URL.

**Done when:** The chapter's colours are chosen, written into a small stylesheet, and published at a web address the software can load. Colours are the only visual difference between chapters in the software, so a chapter that skips this looks exactly like Cleveland.

**How to check:** The file's address shows the stylesheet's text in a browser. Once the applications are deployed, the public forms show the chapter's colours.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Three things. The file sets something other than a colour name, which the rule forbids so a chapter's file cannot break the pages. Some website platforms refuse to host a stylesheet, or serve it as a download; this has not been checked for any platform. And the colour file changes only the applications - the CRM and the public events page keep their own look (work list item 11).

---

## 6.6 Produce the chapter's logo image

**Why:** The CRM shows the chapter's logo, and it is the only per-chapter image in the whole system.

**Who:** The chapter  
**Finish first:** step 1.1

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Produce the logo as an image file. Cleveland's CRM logo is a PNG file. There is no written specification of the best size or shape yet (work list item 4).
   *You should see:* An image file that opens.
2. Keep the file where the central support organization can reach it. It is loaded into the CRM's settings as its company logo in step 9.14.

**Done when:** An image file of the chapter's logo exists in a form the CRM system accepts. The applications carry no logo; the CRM system does, and it is the only per-chapter image in the whole system.

**How to check:** The file exists and opens.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter that expects its logo on the application pages. The applications carry no logo and no browser tab icon, by a ruling of 26 August 2026. Tell the chapter this before it asks.

---

## 6.7 Decide where the chapter's help documentation lives

**Why:** The applications' portal and the CRM's navigation bar both link to the help documentation, and leaving it undecided sends the chapter's staff to Cleveland's.

**Who:** The chapter and the central support organization — the chapter, with the central support organization  
**Finish first:** step 6.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Record one of two things on the chapter information form - the chapter's own documentation address, or "none yet". Whether each chapter publishes its own or shares one site is an open question in the plan.
   *You should see:* An address or "none yet" on the form. Never blank.

**Done when:** Either the chapter has its own documentation site published at its own address, or it is recorded that the chapter points at a shared one. Two later steps link to this address, so it cannot be left undecided.

**How to check:** The form carries an address or "none yet".

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Leaving the setting DOCS_SITE_URL at its default. The chapter's staff are then sent to Cleveland's documentation, which names Cleveland throughout.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the public website (9-Methods-Hosting-Website-Policies.md, version 0.4, including the redirect version of step 6.3) with the step list's finishing tests. |
