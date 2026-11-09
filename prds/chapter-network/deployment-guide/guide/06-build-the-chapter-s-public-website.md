# Stage 6 — Build the chapter's public website

**Version:** 0.8  
**Last Updated:** 11-09-26 15:57  
**Generated from** `steps/stage-06.yaml` — do not edit this page; edit the YAML and re-render.

---

## Summary

The chapter's public website is a WordPress site built from the Association's template, on the host the chapter chose at step 5.10, with the Association's WordPress add-on, the chapter connector (Association rulings 28, 34 and 75). The actions are written for Cloudways, a lightly managed host on DigitalOcean, the host the Association uses and tests; on another host, follow that host's own screens to the same result. The chapter owns the site, its pages and its words. The chapter connector fetches the parts that come from the CRM system: the colours, fonts, logo and header graphic set in the Website group of System Settings, the key pages such as the mentor directory and events, and the framed forms. This stage publishes the site, installs the template and the chapter connector, names the person who edits it, gathers the colours and images the Website group will hold, and turns on visitor statistics without cookies. A chapter that keeps another platform, such as Squarespace, uses the embed code instead (Association ruling 27), and steps 6.2 and 6.3 differ for it.

**Who:** The chapter. The Association helps on request (Association ruling 33).  
**Time:** About two hours for a new WordPress site on the template, plus up to a day for a new address to be seen everywhere. The chapter's own pages and words take as long as the chapter wants.  
**When this stage is done:** The policy documents (stage 7) can be published on the site, and the chapter information form (stage 8) can be filled in with the site's address. The site's key pages and colours appear once the chapter's applications are deployed and the Website group is filled in (stage 13).

**Before you start:**

- The chapter's domain names in its Cloudflare account (step 3.7)
- The website host account (step 5.10)
- The chapter's name (step 1.1)

**Steps in this stage:**

- 6.1 Choose the website platform
- 6.2 Publish the website
- 6.3 Install the template and the chapter connector
- 6.4 Confirm someone at the chapter can edit the website
- 6.5 Choose the chapter's colours, fonts and header graphic
- 6.6 Produce the chapter's logo image
- 6.7 Decide where the chapter's help documentation lives
- 6.8 Turn on visitor statistics without cookies

---

## 6.1 Choose the website platform

**Summary:** The Association recommends its WordPress template with the chapter connector (Association rulings 28 and 34). A chapter may keep the platform it has; it then shows the CRM's parts through the embed code, a frame the chapter applications serve, without page switches (Association ruling 27).

**Who:** The chapter

**Finish first:**

- step 3.4 Register and pay for the domain names

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide one of two answers with the chapter's board:
   - The Association's WordPress template, on the host chosen at step 5.10 (the full path). Steps 6.2 and 6.3 build it, with actions written for Cloudways, the host the Association tests (Association ruling 75).
   - The chapter's existing website platform (the basic path). The site stays where it is, and the CRM's parts are added with the embed code at stage 13.
2. Name the person who builds and maintains the site, and write on the chapter's account list (step 5.7): the platform, the address the editors sign in at, and that person's name.
   *You should see:* The website on the account list, with a named person.

**Done when:** The choice is made and someone is named to build and maintain the site.

**How to check:** The platform and the person's name are on the chapter's account list.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Nobody named to maintain it. A website built by a volunteer who then leaves is a website nobody can change. On WordPress, someone must also keep WordPress itself up to date; the template switches on its automatic updates (Association ruling 28).

---

## 6.2 Publish the website

**Summary:** On the full path, a small server at the chapter's host runs WordPress at the chapter's website domain, with a free security certificate. The actions are for Cloudways on DigitalOcean (Association ruling 75); on another host, follow its own screens to the same result. On the basic path, the chapter's existing site only needs to load securely at its domain.

**Who:** The chapter

**Finish first:**

- step 6.1 Choose the website platform
- step 5.10 Open the website host account
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Basic path only: open https://WEBSITE-DOMAIN/ in a private browser window, check it shows with no security warning, and skip to step 6.4.
2. In Cloudways (https://platform.cloudways.com), signed in as admin@EMAIL-DOMAIN, click Add Application on the home page (or Add Server on the Servers page). Screens checked on the Association's account on 11-09-26: a four-step form headed Deploy your First Server and Application.
3. Step 1 of 4, Choose your Application Type. Set these, then click Choose Server:
   - Application type: WordPress
   - Additional Configuration: Basic (plain WordPress; Optimized adds Cloudways' own plugins)
   - Application Stack: Lightning Stack (the recommended one)
4. Step 2 of 4, Choose Your Cloud Provider. Set these, then click Choose Server Size:
   - Cloud provider: DigitalOcean
   - Region: the one nearest the chapter (New York for Ohio)
5. Step 3 of 4, Configure your Server. Set these, then click Review & Launch:
   - Database: MariaDB (the recommended one)
   - Server Type: Basic
   - Server Size: click Standard at the right of the slider (it starts on Premium), then drag the slider's handle to the far left, 1 GB. The handle does not move on a click; drag it. Cloudways warns that 1 GB is for staging or low-traffic sites: use 2 GB for a live chapter site.

   *You should see:* The price at the bottom right: on the Association's account, $0 during the 5-day free trial and $11.00 a month after it (1 GB Standard, 11-09-26).
6. Step 4 of 4, Review and Launch Application. Replace the three names Cloudways fills in (My First App, My First Server, My First Project):
   - Application Name: SHORT-LABEL-site
   - Server Name: SHORT-LABEL-web
   - Project Name: CHAPTER-NAME
7. Read the monthly price at the bottom right, then click Launch Now.
   *You should see:* The Servers page, with the server marked Adding Server. It took about ten minutes on the Association's account; the server then shows as running.
8. In Cloudways, open the server, then Master Credentials, and copy the Public IP.
   *You should see:* Four numbers separated by dots.
9. In Cloudflare, open the website domain, then DNS, then Records, and add a record with these values, then Save:
   - Type: A
   - Name: @ for the domain itself, or the part before the domain for an address under it
   - IPv4 address: the Public IP from Cloudways
   - Proxy status: DNS only (grey cloud), so the certificate in the next action can be issued

   *You should see:* The record listed as DNS only.
10. In Cloudways, open Applications, then SHORT-LABEL-site, then Domain Management. Click Add Domain, enter WEBSITE-DOMAIN, tick Make primary if offered, and save.
    *You should see:* WEBSITE-DOMAIN listed as the primary domain.
11. In the same application, open SSL Certificate, choose Let's Encrypt, enter admin@EMAIL-DOMAIN as the contact and WEBSITE-DOMAIN as the domain, and click Install Certificate. Then switch on HTTPS Redirection if offered.
    *You should see:* After a minute or two, a message that the certificate is installed.
12. Open https://WEBSITE-DOMAIN/ in a private browser window.
    *You should see:* A plain WordPress site with a padlock and no security warning.

**Done when:** The site loads at the chapter's website domain over a secure connection.

**How to check:** The site opens in a private browser window at https:// and the chapter's domain, with no security warning.

**If it didn't work:**

- The certificate fails because the domain does not point at the server: wait ten minutes for the DNS record to be seen, and try once more.
- Anything else: stop, and ask the Association before going on.

**What usually goes wrong:** A new Cloudways account held for a manual check before it can launch a server ("Your account activation is pending", 11-08-26): email the address Cloudways gives, and wait. And a site meant only for testing left open to search engines: switch on WordPress's Discourage search engines setting (Settings, then Reading) on any test site.

---

## 6.3 Install the template and the chapter connector

**Summary:** The chapter connector is the Association's WordPress add-on. It carries the template's pages, header and footer, and it fetches the colours, key pages and forms from the chapter's applications. It needs no password (Association ruling 34). Until the chapter's applications are deployed, it can point at the Association's shared test system.

**Who:** The chapter with the Association on request

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Basic path only: skip this step. The embed code is added at stage 13.
2. In Cloudways, open the application's Access Details and copy the WordPress Admin Panel address, username and password into the chapter's Operations vault, in an item titled WordPress administrator.
3. Sign in at https://WEBSITE-DOMAIN/wp-admin with those details.
   *You should see:* The WordPress Dashboard.
4. Open Appearance, then Themes, and check the active theme is Twenty Twenty-Five, the template's starter theme; activate it if not.
5. Open Plugins, then Add New Plugin. Search for Chapter Connector and install the Association's chapter connector. Until it is published in WordPress's add-on directory (Association ruling 36), choose Upload Plugin instead and upload the zip file the Association supplies.
   *You should see:* Chapter Connector in the Plugins list, and a Chapter connector item in the left menu, once you click Activate.
6. Open Chapter connector. In the Chapter applications address field, enter the chapter's applications address (APP-ADDRESS, with https://), or, until those are deployed, the address the Association names for its shared test system. Click Save address.
7. On the same screen, click Install the template's pages, header and footer.
   *You should see:* A message that the template's pages, header and footer are installed.
8. Open Settings, then General, and set Site Title to the chapter's name. Open Settings, then Reading: on a test site, tick Discourage search engines from indexing this site.
9. Open https://WEBSITE-DOMAIN/ in a private browser window.
   *You should see:* The template's home page, with a Request a Mentor button. The colours, logo and key pages appear once the Website group is filled in (stage 13).

**Done when all of these are true:**

- The chapter connector is installed and active.
- The template's pages, header and footer are installed.
- The chapter connector names the chapter's applications address, or the shared test system's.

**How to check:** The home page shows the template, and the Chapter connector screen shows the applications address.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A cache that still shows the plain theme after installing: in Cloudways, open the application and purge its cache (Varnish), then reload. And the chapter's applications not yet naming the website among their allowed addresses: the framed forms then stay empty until stage 13 adds it.

---

## 6.4 Confirm someone at the chapter can edit the website

**Why:** The policy documents (stage 7) and the chapter's own pages need changes on the site, made by someone at the chapter with a sign-in of their own.

**Who:** The chapter

**Finish first:**

- step 6.3 Install the template and the chapter connector

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. On WordPress, signed in as the administrator from step 6.3, open Users, then Add New User, and create a user for the named person from step 6.1 with their own chapter address and the Editor role (Administrator if they also maintain WordPress). On another platform, use its own way of adding an editor.
2. The named person signs in with their own sign-in, changes one word on the home page and publishes it.
3. They open https://WEBSITE-DOMAIN/ in a private browser window.
   *You should see:* The changed word.
4. They change the word back, publish, and reload the private window.
   *You should see:* The original word again.

**Done when:** A named person at the chapter has signed in and made a change.

**How to check:** The change appeared on the public site.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The only sign-in belongs to the person or company who built the site.

---

## 6.5 Choose the chapter's colours, fonts and header graphic

**Summary:** The chapter's look is set once, in the Website group of System Settings, and the chapter connector applies it to the whole site; the applications build their own colours from the same values (Association ruling 34). This step only chooses the values; they are entered at stage 13. A separate colour file is no longer needed.

**Who:** The chapter

**Finish first:**

- step 6.1 Choose the website platform

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Choose eight colours as six-digit codes: base (the background), contrast (the text), and accent 1 to accent 6 (headings, buttons, links and highlights). Start from the template's defaults, shown in the Website group, and change only what the chapter wants.
2. Choose the heading font and the body font from the fonts the Website group offers.
3. Produce the header graphic: a wide image shown tall on the home page and as a narrow strip on every other page (Association rulings 67 and 69).
4. Write all of these in a note in the chapter's shared drive, for stage 13.
5. On the chapter information form, leave the question Web address (URL) of the colour file empty. It becomes CHAPTER_TOKENS_URL, now an override for a chapter that already has its own colour file.

**Done when all of these are true:**

- The chapter's eight colours and two fonts are chosen and written down.
- The header graphic exists.

**How to check:** The note and the image are in the chapter's shared drive.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Colours with too little contrast. The template must meet the Web Content Accessibility Guidelines (WCAG) version 2.2 at level AA (Association ruling 64), so text on its background must stay readable.

---

## 6.6 Produce the chapter's logo image

**Why:** The logo shows on the website, uploaded in the Website group, and in the CRM.

**Who:** The chapter

**Finish first:**

- step 1.1 Choose the chapter's name

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Produce the chapter's logo as a PNG image file. Name it SHORT-LABEL-logo.png, for example lakeside-logo.png.
2. The best size and shape are not specified yet (work list item 4). Until they are, open Cleveland's CRM, note the size the logo shows at, and make the chapter's the same shape.
   *You should see:* A PNG file that opens.
3. Put the file in the chapter's shared drive folder, and write its file name on the chapter information form under crm: logo_file. It is loaded into the CRM as its company logo in step 9.7, and uploaded to the Website group at stage 13.

**Done when:** An image file of the chapter's logo exists in a form the CRM system and the Website group accept.

**How to check:** The file exists and opens.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A logo that only works on a white background. The website shows it on the header's colour, so check it there at stage 13.

---

## 6.7 Decide where the chapter's help documentation lives

**Why:** The applications' portal and the CRM's navigation bar both link to the help documentation, and leaving it undecided sends the chapter's staff to Cleveland's.

**Who:** The chapter and the Association — the chapter, with the Association

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

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

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** Leaving the setting DOCS_SITE_URL at its default. The chapter's staff are then sent to Cleveland's documentation, which names Cleveland throughout.

---

## 6.8 Turn on visitor statistics without cookies

**Summary:** Cloudflare Web Analytics counts visitors without cookies, so the website needs no consent banner (Association ruling 63). It is free in the Cloudflare account the chapter already owns.

**Who:** The chapter

**Finish first:**

- step 6.2 Publish the website

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. In Cloudflare, open Analytics, then Web analytics, and add the website's domain. For a site whose address is proxied through Cloudflare, choose the automatic setup; for a DNS only address, choose the JavaScript snippet. The exact labels have not been checked for this guide.
2. If Cloudflare gives a snippet, paste it into the site: on WordPress, in the chapter connector's settings if it offers a box for it, otherwise in the footer of the template through Appearance, then Editor. On another platform, in its place for code in the page footer.
3. Open the website in a private browser window, then wait an hour and open Web analytics in Cloudflare.
   *You should see:* At least one visit counted.

**Done when:** Cloudflare Web Analytics counts the website's visits, and the site sets no tracking cookie.

**How to check:** Cloudflare's Web analytics shows visits, and the browser's site data shows no analytics cookie.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A second statistics service, such as Google Analytics, added as well. It sets cookies, and the site then needs a consent banner after all.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.8 | 11-09-26 15:57 | Step 6.2's Cloudways actions rewritten from the Association's own account (11-09-26): the four-step Deploy your First Server and Application form, Standard 1 GB at $11 a month, 2 GB advised for a live site. The stage summary, step 6.1 and step 6.2's summary follow Association ruling 75, which replaces ruling 29: the host is the one the chapter chose at step 5.10, and the actions are written for Cloudways, the host the Association tests. |
| 0.7 | 11-08-26 10:05 | Rewritten for the Association's website rulings (review finding 1; plan association-setup-plan.md, batch 3, approved by Doug 11-08-26). The site is WordPress from the Association's template on Cloudways, with the chapter connector, or the chapter's own platform with the embed code (Association rulings 26 to 29 and 34). Step 6.2 launches the Cloudways server, the DNS record and the certificate. Step 6.3, formerly the redirect check, now installs the template and the chapter connector: the events page is a key page the chapter connector serves. Step 6.4 adds the editor's own WordPress user. Step 6.5, formerly the colour file, now chooses the eight colours, two fonts and header graphic the Website group of System Settings will hold; the colour file becomes an optional override. Step 6.6 notes the logo is also uploaded to the Website group. New step 6.8 turns on Cloudflare Web Analytics (Association ruling 63). No step number changed. |
| 0.6 | 11-07-26 15:21 | Corrected while the Business Mentors Association is set up as a chapter (plan association-setup-plan.md, approved by Doug 11-07-26): "the central support organization" is now "the Association", and "the central committee" is "the central technical committee". |
| 0.5 | 09-23-26 20:40 | References to stage 9 follow its renumbering from twenty steps to nine (stage 9 version 0.11). |
| 0.4 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.3 | 09-23-26 12:49 | Step 6.5: the chapter enters its four colours on the chapter information page, and the values-file writer produces the colour file from them (Doug, 09-23-26). |
| 0.2 | 09-19-26 00:04 | Every action made precise (Doug, 09-19-26): the three things the platform must do, the exact curl checks for the site, the redirect test at /redirect-test and the colour file, the exact lines of chapter-tokens.css with the four --cbm- colour names, the logo file name, and the form keys each value is written under. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the public website (9-Methods-Hosting-Website-Policies.md, version 0.4, including the redirect version of step 6.3) with the step list's finishing tests. |
