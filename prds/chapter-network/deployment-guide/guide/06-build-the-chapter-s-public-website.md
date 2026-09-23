# Stage 6 — Build the chapter's public website

**Version:** 0.4  
**Last Updated:** 09-23-26 14:27  
**Generated from** `steps/stage-06.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The public website is the chapter's own marketing site. The software does not build it, but it needs four things from it. The policy documents need addresses on it. The chapter's colour file needs a place to live on it. The public application forms need a link from it. And visitors need to be sent from it to the events page the applications serve. This stage makes sure the site can do all four, and that someone at the chapter can change it.

**Who:** The chapter. The central support organization writes the colour file and helps with the help documentation decision.  
**Time:** Not known. A chapter that already has a website finishes in an hour; building a new site can take weeks.  
**When this stage is done:** The policy documents (stage 7) can be published on the site, and the chapter information form (stage 8) can be filled in with the site's addresses.

**Before you start:**

- The chapter's domain names (stage 3)
- The chapter's name (step 1.1)

**Steps in this stage:**

- 6.1 Choose the website platform
- 6.2 Publish the website
- 6.3 Confirm the website can redirect an address to another site
- 6.4 Confirm someone at the chapter can edit the website
- 6.5 Choose the chapter's colours and publish the colour file
- 6.6 Produce the chapter's logo image
- 6.7 Decide where the chapter's help documentation lives

---

## 6.1 Choose the website platform

**Why:** The site must be able to publish pages, host a small file and redirect one address to another, and someone must own it.

**Who:** The chapter

**Finish first:**

- step 3.4 Register and pay for the domain names

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. If the chapter already has a website, keep it. Otherwise choose a platform that can do all three of these:
   - Publish ordinary pages at addresses the chapter chooses, such as /privacy-policy/.
   - Send one address to another site by a temporary redirect, the kind numbered 302.
   - Serve a small stylesheet file with the file type text/css, or link to one hosted elsewhere.
2. For reference, Cleveland's website runs on WordPress with the Elementor page builder. That is an example, not a requirement.
3. Add a line to the chapter's account list (step 5.7) with exactly these entries:
   - Account: the website
   - Platform: the platform's name
   - Sign-in address: the address the site's editors sign in at
   - Built and maintained by: the named person
   *You should see:* The website on the account list, with a named person.

**Done when:** The choice is made and someone is named to build and maintain the site.

**How to check:** The platform and the person's name are on the chapter's account list.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Nobody named to maintain it. A website built by a volunteer who then leaves is a website nobody can change.

---

## 6.2 Publish the website

**Why:** Every later page the software links to lives on this site, and it must load securely.

**Who:** The chapter

**Finish first:**

- step 6.1 Choose the website platform

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Publish the site at https://WEBSITE-DOMAIN/, where WEBSITE-DOMAIN is the chapter's website domain from stage 3, for example lakesidebusinessmentors.org.
2. Open a terminal and run exactly:
   - curl -sI https://WEBSITE-DOMAIN/
   *You should see:* A first line of HTTP/2 200, or a 301 redirect to the same site with www added, which is also fine.
3. Open https://WEBSITE-DOMAIN/ in a private browser window.
   *You should see:* The site, with no security warning.

**Done when:** The site loads at the chapter's website domain over a secure connection.

**How to check:** The site opens in a private browser window at https:// and the chapter's domain, with no security warning.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A certificate that is not renewed. The site then shows a security warning to every visitor.

---

## 6.3 Confirm the website can redirect an address to another site

**Why:** The chapter's events page will be a redirect to the page the applications serve, so the site must be able to do one.

**Who:** The chapter

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. On the website, add a temporary redirect with exactly these values. On WordPress the free Redirection plugin does this; on other platforms look for a setting named redirects:
   - From: /redirect-test
   - To: https://example.com/
   - Type: 302 (temporary)
2. In a terminal, run exactly:
   - curl -sI https://WEBSITE-DOMAIN/redirect-test
   *You should see:*
   - A first line of HTTP/2 302 (or HTTP/1.1 302).
   - A line location: https://example.com/
3. Delete the /redirect-test redirect.
4. Run the same command again:
   - curl -sI https://WEBSITE-DOMAIN/redirect-test
   *You should see:* A first line of HTTP/2 404. The test redirect is gone.

**Done when:** A test address on the site sends the visitor to a page on another site, by a temporary redirect. (Checking that the site can embed a page returns once the public mentor directory page is built and its method is decided.)

**How to check:** The test address lands on the other site's page.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A website platform that cannot redirect one address without a paid plan. Find out now, not at stage 13.

---

## 6.4 Confirm someone at the chapter can edit the website

**Why:** The policy documents (stage 7) and the events redirect (stage 13) both need changes on the site, made by someone at the chapter.

**Who:** The chapter

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The named person from step 6.1 signs in to the website's editor at its sign-in address, with their own sign-in, not a shared one.
2. They change one word on the home page and publish the change.
3. They open https://WEBSITE-DOMAIN/ in a private browser window.
   *You should see:* The changed word.
4. They change the word back, publish, and reload the private window.
   *You should see:* The original word again.

**Done when:** A named person at the chapter has signed in and made a change.

**How to check:** The change appeared on the public site.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The only sign-in belongs to the person or company who built the site.

---

## 6.5 Choose the chapter's colours and publish the colour file

**Why:** Colours are the only visual difference between chapters in the software, so a chapter that skips this looks exactly like Cleveland.

**Who:** The chapter and the central support organization — the chapter chooses the colours, the central support organization writes the file

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The chapter chooses four colours, each as a six-digit colour code, and enters them in the four colour questions on the chapter information page (step 8.3). Cleveland's are shown for comparison:
   - Primary colour, used for headings. Cleveland: #173B60 (navy).
   - Button colour. Cleveland: #CB963B (gold).
   - Button colour when the mouse is over it, about ten per cent darker. Cleveland: #b8842f.
   - Body text colour. Cleveland: #7A7A7A (grey).
2. The central support organization writes a file named chapter-tokens.css containing exactly these lines, with the chapter's four colour codes in place of the capitalised words. The values-file writer in step 8.10 produces this file from the page's answers, as prds/chapter-network/chapters/SHORT-LABEL-chapter-tokens.css:
   - :root {
   - --cbm-navy: PRIMARY-COLOUR;
   - --cbm-gold: BUTTON-COLOUR;
   - --cbm-btn-bg-hover: BUTTON-HOVER-COLOUR;
   - --cbm-text: BODY-TEXT-COLOUR;
   - }
3. Add nothing else to the file. It may only set names that start --cbm-, and only inside :root. Every name it leaves out keeps Cleveland's value from frontend/shared/tokens.css, where the full list of names is.
4. Publish the file so it has its own address, for example https://WEBSITE-DOMAIN/chapter-tokens.css. Whether the chapter's platform can serve a .css file has not been checked for any platform. If it cannot, the central support organization hosts the file elsewhere.
5. In a terminal, run exactly:
   - curl -sI https://WEBSITE-DOMAIN/chapter-tokens.css
   *You should see:*
   - A first line of HTTP/2 200.
   - A line content-type: text/css. Browsers ignore a stylesheet from another site served with any other type.
6. Enter the file's full address on the chapter information page, in the question Web address (URL) of the colour file. It becomes the setting CHAPTER_TOKENS_URL.

**Done when all of these are true:**

- The chapter's colours are chosen.
- The colours are written into a small stylesheet.
- The stylesheet is published at a web address the software can load.

**Note:** Colours are the only visual difference between chapters in the software, so a chapter that skips this looks exactly like Cleveland.

**How to check:** The file's address shows the stylesheet's text in a browser. Once the applications are deployed, the public forms show the chapter's colours.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Three things. The file sets something other than a colour name, which the rule forbids so a chapter's file cannot break the pages. Some website platforms refuse to host a stylesheet, or serve it as a download; this has not been checked for any platform. And the colour file changes only the applications - the CRM and the public events page keep their own look (work list item 11).

---

## 6.6 Produce the chapter's logo image

**Why:** The CRM shows the chapter's logo, and it is the only per-chapter image in the whole system.

**Who:** The chapter

**Finish first:**

- step 1.1 Choose the chapter's name

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Produce the chapter's logo as a PNG image file, the type Cleveland's CRM logo uses. Name it SHORT-LABEL-logo.png, for example lakeside-logo.png.
2. The best size and shape are not specified yet (work list item 4). Until they are, open Cleveland's CRM, note the size the logo shows at, and make the chapter's the same shape.
   *You should see:* A PNG file that opens.
3. Put the file in the chapter's shared drive folder, and write its file name on the chapter information form under crm: logo_file. It is loaded into the CRM as its company logo in step 9.14.

**Done when:** An image file of the chapter's logo exists in a form the CRM system accepts. The applications carry no logo; the CRM system does, and it is the only per-chapter image in the whole system.

**How to check:** The file exists and opens.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter that expects its logo on the application pages. The applications carry no logo and no browser tab icon, by a ruling of 26 August 2026. Tell the chapter this before it asks.

---

## 6.7 Decide where the chapter's help documentation lives

**Why:** The applications' portal and the CRM's navigation bar both link to the help documentation, and leaving it undecided sends the chapter's staff to Cleveland's.

**Who:** The chapter and the central support organization — the chapter, with the central support organization

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Decide one of two answers, then write it on the chapter information form under web: docs_site_url:
   - The chapter's own documentation site's full address, beginning https://.
   - none yet — until the open question of shared or per-chapter documentation is settled.
   *You should see:* An address or "none yet" on the form. Never blank.
2. If an address was written, run exactly:
   - curl -sI DOCS-ADDRESS
   *You should see:* A first line of HTTP/2 200.
3. The answer becomes the setting DOCS_SITE_URL. Its default is Cleveland's, https://docs.clevelandbusinessmentors.org, so it must never be left unset.

**Done when:** Either the chapter has its own documentation site published at its own address, or it is recorded that the chapter points at a shared one. Two later steps link to this address, so it cannot be left undecided.

**How to check:** The form carries an address or "none yet".

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Leaving the setting DOCS_SITE_URL at its default. The chapter's staff are then sent to Cleveland's documentation, which names Cleveland throughout.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.4 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.3 | 09-23-26 12:49 | Step 6.5: the chapter enters its four colours on the chapter information page, and the values-file writer produces the colour file from them (Doug, 09-23-26). |
| 0.2 | 09-19-26 00:04 | Every action made precise (Doug, 09-19-26): the three things the platform must do, the exact curl checks for the site, the redirect test at /redirect-test and the colour file, the exact lines of chapter-tokens.css with the four --cbm- colour names, the logo file name, and the form keys each value is written under. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the public website (9-Methods-Hosting-Website-Policies.md, version 0.4, including the redirect version of step 6.3) with the step list's finishing tests. |
