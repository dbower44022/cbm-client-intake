# Chapter website — the applications' side

**Document:** Plan for the chapter applications' side of the chapter website
**Version:** 0.1
**Status:** Draft — awaiting Doug's answers to section 4 and approval of the stopping points in section 6
**Owner:** Doug Bower
**Last Updated:** 11-07-26 11:25

---

## 1. What this round delivers

A test chapter website, built from the template, running at `chapter-demo.mentorsassociation.org` on Cloudways and connected to crm-test, so the integration between the website and these applications can be tested end to end (Association ruling 68). Production is not part of this round.

Every piece is built dark behind a feature flag, switched on in crm-test's overlay, and reviewed live there. Every push to `main` deploys dev, crm-test and Cleveland's production, so the flag is the only gate (`DEPLOYMENT.md` § *Reviewing a change before it reaches production*).

Every setup step a chapter's technical person takes is written as a runbook, to the step-by-step instructions standard.

## 2. What this plan rests on

- The kickoff prompt: `~/Dropbox/Projects/business-mentors-association/docs/prompts/cbm-client-intake-website-kickoff.md`, version 1.2.
- The Association's rulings 24 to 68 in `~/Dropbox/Projects/business-mentors-association/DECISIONS.md`. The prompt's reading list stops at 63. Rulings 64 (separate Our Partners and Our Sponsors pages), 67 (the header graphic is a Website setting) and 68 (the test site and its address) also bind this work.
- The website template requirements, `~/Dropbox/Projects/business-mentors-association/docs/website-template-prd.md`, version 0.7. Numbers such as WT-22 refer to it.
- The prototype, `~/Dropbox/Projects/chapter-website-prototype/`. Its stand-in, `mock-apps/server.py`, is the contract the chapter connector already calls. Section 3 records the two places where the contract must change.
- `prds/public-mentor-pages-plan.md`. It is not built, but its rules on who appears and on publish readiness still apply.

## 3. Findings from reading the code, 11-07-26

Each finding is marked verified (read in the code) or not checked.

1. **The campaign tag breaks between the website and the forms (verified).** The chapter connector writes the campaign into the frame's address as `campaign=CMP-2026-POSTCARD` (`chapter-connector/campaign.js:52`). The forms accept only a CRM record identifier there: `frontend/shared/campaign-link.js:23` checks it against `^[A-Za-z0-9]{1,32}$` and throws away anything else, silently. Also, when a campaign link sends a visitor to a website page, the address carries only the campaign. The link token (`link=`), which credits the specific campaign link, is lost. Decision 4.1.
2. **The Website group repeats settings that already exist (verified).** The Presentation group in `core/settings_registry.py` holds the organisation name, the chapter acronym, the chapter postal address, the organisation logo URL, the organisation website, the website menu and the chapter design-token override (which carries the colours today). Ruling 45 and WT-11 put the name, abbreviation, address, logo and colours in the Website group. Decision 4.2.
3. **"Placement" already names something here (verified).** `campaigns/ladder.py` uses "placement" for setting a lead's qualification level. The website's tag for which button a visitor pressed is therefore called the **button placement** in this repository's code, CRM fields and documents. The address parameter stays `placement`, because the chapter connector already sends it under that name.
4. **Any website can frame the forms today (verified).** The application sends no `X-Frame-Options` and no Content Security Policy `frame-ancestors` header; its only header middleware is the cross-origin resource sharing (CORS) one. A frame allow-list would cut off any site that frames a form today. Before the framing flag is switched on anywhere, Cleveland's current website pages are checked for frames pointing at these applications.
5. **`allowed_origins` is application-wide (verified).** It is passed to the CORS middleware for every address (`core/app.py:683`). Adding the chapter website there would let it fetch from every application programming interface (API) address. The website needs only `/api/website/*`, so it gets its own setting limited to those addresses.
6. **Partners, sponsors and client stories cannot be served this round (verified in the requirements).** Section 7 of the website template requirements lists them as feature requests 2 and 3, owed to the committee under ruling 3, and the prompt puts those out of scope. WT-50 says those pages stay hand-edited until then. So the Website group refuses to switch on the `partners`, `sponsors` and `stories` page keys (WT-10), and their addresses answer `404`. The stand-in serves partners and sponsors; the chapter connector already handles a page the applications do not serve (WT-22).
7. **Who appears in the mentor directory is already ruled (verified).** `prds/public-mentor-pages-plan.md`: a mentor appears when `mentorStatus` is Active **and** `publicProfile` is true. `acceptingNewClients` changes the Request This Mentor button, never visibility.
8. **The contract has no version rule (verified).** The stand-in's settings carry `"version": 1`, and WT-27 requires the chapter connector to work with older application releases. Section 5 states the rule.
9. **The test site is public on a real domain and shows crm-test's training mentors.** It must tell search engines not to index it (noindex). Its runbook must say that Website settings survive crm-test's nightly reset, because they live in `app_setting`, but CRM edits do not.
10. **The public addresses call the CRM and take no sign-in.** The mentor search runs on every keystroke. Each address therefore reads through a server-side cache, as `events/public.py` already does, and the search address is rate-limited by the existing public-request limiter.

## 4. Decisions owed by Doug

Taken one at a time, in this order. Each recommendation is Claude's, not a ruling.

### 4.1 What the website carries as the campaign

The chapter connector remembers a campaign for the visit and passes it into every form. Today it carries a human-readable code that the forms reject.

- **A. The campaign link token.** The redirect sends `?cmp=<link token>`; the chapter connector stores and passes it on; the forms already accept `link=` and credit both the link and its campaign. Keeps per-link credit. Costs a one-line change in the chapter connector (`campaign=` becomes `link=`).
- **B. The campaign's CRM record identifier.** Matches what the forms accept today. Loses the credit to the specific link, so two links for one campaign cannot be told apart.
- **C. Make the forms accept the human-readable code.** No change to the chapter connector. Needs a code field on every campaign, and a lookup on every form load.

Recommended: **A**, because it keeps the per-link credit the campaign reports already show, and the chapter connector change is one line.

### 4.2 Which group holds the chapter-wide values

- **A. The Website group takes them over.** The name, acronym, postal address, logo and colours move from Presentation into Website, under the same setting keys, so nothing that reads them changes. Presentation keeps the application-only settings. One place for an administrator to look. Costs a move in `core/settings_registry.py` and an update to `SYSTEM-SETTINGS-SETUP.md` and `chapter-colours.md`.
- **B. The Website group shows them read-only, with a link to Presentation.** No move. The administrator still sets the website's values in two groups.

Recommended: **A**, because WT-11 asks for each value set once in one place, and the keys do not change.

The colours follow the same choice. Today `CHAPTER_TOKENS_URL` points at a stylesheet of `--cbm-*` colour variables. The Website group holds eight colour values (`base`, `contrast`, `accent-1` to `accent-6`). Recommended: the applications build their own `--cbm-*` stylesheet from those eight values, and `CHAPTER_TOKENS_URL` stays as an override for a chapter that already has one.

### 4.3 How the logo and header graphic are stored and served

- **A. Uploaded in System Settings, stored in the application database, served at `/assets/logo` and `/assets/header`.** The chapter needs no other hosting. Costs an upload control in System Settings, which has none today.
- **B. An address of an image hosted elsewhere, as `ORGANIZATION_LOGO_URL` is today.** No new storage. The chapter must host the image somewhere public, and a moved image breaks the website.

Recommended: **A**, because a chapter on the template has no other obvious place to host an image.

### 4.4 Where the button placement is written

- **A. On the lead record.** Ruling 48 gives every new public-form record a lead, and the lead already holds the Lead Source. Costs one new field on the lead entity, and a repeat submitter gets no lead, so their placement is kept only in the captured submission.
- **B. Beside the campaign, on the relationship record each form creates** (the engagement, mentor profile, partner profile and so on). Every submission keeps it. Costs a field on five entities.

Recommended: **A**, because "which button brings clients" is a question about new arrivals, which is what leads record. In both options the button placement is also kept in the captured submission.

### 4.5 How the mentor page content is built

- **A. Fresh `cmw-` markup, using the field mapping and publish-readiness rules of `prds/public-mentor-pages-plan.md`.** The `mentorprofile/` preview is a copy of Cleveland's Elementor page, with Cleveland's class names. Costs writing the markup.
- **B. Adapt the `mentorprofile/` template, renaming its classes.** Starts from a proven look. Costs carrying Elementor's structure into every chapter, and the preview and the public page drift apart the first time either changes.

Recommended: **A**, because ruling 33 and WT-44 require every class to start with `cmw-`, and the template is Cleveland's design rather than the Association's.

## 5. What is built

Each piece has its own feature flag, off by default and read per request.

**A. The Website group and its settings address.** Flag `WEBSITE_API`.
`GET /api/website/settings` returns the stand-in's shape: `version`, `colors`, `fonts`, the logo, `chapter` (name, abbreviation, email, phone, address, employer identification number, social media addresses, payment link), `headerImage` and `pages`. The `version` field is the contract version. It goes up only when a field changes meaning or is removed. New fields are added without a version change, and the chapter connector ignores fields it does not know. System Settings refuses to switch on `partners`, `sponsors` and `stories` (finding 6). A new setting, `WEBSITE_ORIGINS`, names the chapter website's addresses. It is used for CORS on `/api/website/*` only, and for the framing allow-list in piece C.

**B. The key page content.** Flag `WEBSITE_API`.
- `GET /api/website/pages/{mentors,events,recordings}` and `GET /api/website/pages/mentors/{slug}`, each `{title, description, html}`; `404` for an unknown or hidden mentor.
- `GET /api/website/sitemap` and `GET /api/website/mentors.json?q=`.
- `GET /assets/website.css` and `GET /assets/search.js`.
- The events and recordings pages reuse `events/public.py` and its visibility rule (`events/visibility.py`), never a query of their own.
- An automated test fails on any class name in this content that does not start with `cmw-` (WT-44).
- Every address reads through a server-side cache.

**C. Forms in frames.** Flag `FORM_FRAMING`.
- A `frame-ancestors` header naming `WEBSITE_ORIGINS`.
- The frame-sizing script inside every public form, posting only to the website addresses named in `WEBSITE_ORIGINS` (the prototype's script posts to every address).
- Embed styles, used when the form is opened with `?embed=1`: the form's `--cbm-*` colour and font variables mapped to the Website settings, and the form's own heading, footer and background hidden (WT-56b).
- A link that opens the same form full-screen (WT-58).

**D. Campaigns through the website.** Flag `WEBSITE_CAMPAIGNS`.
- A campaign link may name a website page as its destination. The page must be under an address in `WEBSITE_ORIGINS`, so the link cannot send a visitor to an arbitrary website. The redirect adds the campaign tag decided in 4.1.
- The forms read `placement` from their address and write the button placement where 4.4 decides. The field is declared on `core/forms.BaseSubmission`, because capture drops an undeclared key.

**E. The newsletter signup form.** Flag `NEWSLETTER_FORM`.
A sixth public form creating a Contact with marketing consent set (ruling 43), a lead per ruling 48, and the campaign and button placement like every public form. The existing Constant Contact synchronisation passes the contact on. Before building, check which Contact field the synchronisation reads as consent.

**F. The test website.** Not code in this repository.
The chapter connector installed on Cloudways at `chapter-demo.mentorsassociation.org`, pointed at crm-test, with noindex set. Built from the Association's own setup runbook (`docs/setup-runbook.md` and `docs/runbooks/` in the Association repository). This repository adds the crm-test half.

**Runbooks** (in this repository, one per piece, published to the documentation site only with Doug's agreement):
- switching each flag on;
- filling in the Website group;
- naming the website in `WEBSITE_ORIGINS`;
- pointing a campaign link at a website page.

## 6. Order and stopping points

Work pauses for Doug's go-ahead at each stop. Between two stops it proceeds without asking. Claude commits in this local clone; Doug reviews and pushes.

1. **Stop 1 — decisions.** Doug answers 4.1 to 4.5, one at a time. The answers go into this plan as version 0.2.
2. Build piece A, with tests.
3. **Stop 2 — review piece A.** Doug reviews the diff and pushes. Claude switches the flag on crm-test's overlay, and Doug looks at the Website group live.
4. Build piece B, with tests. Point the prototype's chapter connector at crm-test instead of the stand-in, locally.
5. **Stop 3 — review piece B** on crm-test, through the local prototype.
6. Check Cleveland's website pages for existing frames (finding 4), then build piece C.
7. **Stop 4 — review piece C** on crm-test, with a form framed in the local prototype.
8. Build pieces D and E.
9. **Stop 5 — review pieces D and E** on crm-test.
10. Write the runbooks. Doug sets up the test site from them (piece F).
11. **Stop 6 — the end-to-end test** on `chapter-demo.mentorsassociation.org`: settings, key pages, mentor search, a framed form, a campaign link followed to a page and then to a submission, and a newsletter signup. Findings go to `OPEN-ITEMS.md`.

## 7. Out of scope this round

- Production, for every piece.
- Shared events between chapters (rulings 39 and 40).
- The seven feature requests in section 7 of the requirements, including partners and sponsors on the website, client stories and the events calendar feed.
- The chapter connector's own changes, apart from the one-line campaign change if 4.1 is answered A. Those belong to the prototype repository.
- Translating text. New visitor-facing text is kept in one place per piece, so it can be translated later (ruling 41).

---

## Change log

| Version | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-07-26 11:25 | Claude (Claude Code) | First draft, from the kickoff prompt version 1.2 and a reading of this repository, the Association repository and the prototype. |
