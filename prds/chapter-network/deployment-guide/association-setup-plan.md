# Correcting the guide while the Association is set up as a chapter — plan

**Document:** Plan for correcting the New Chapter Deployment Guide stage by stage while the Business Mentors Association is set up as a chapter (Association rulings 71 and 72)
**Version:** 1.7
**Status:** Approved by Doug 11-07-26 15:17, with the four recommendations of section 5 and both of section 6
**Owner:** Doug Bower
**Last Updated:** 11-08-26 10:06

---

## 1. What this plan does

Doug sets the Association up as a chapter by following the New Chapter Deployment Guide. Before he follows a stage, this session checks the stage against the Association's rulings, corrects what is wrong and adds the steps that are missing. The guide's source is the stage data files in `steps/`; the pages in `guide/` are rendered from them by `scripts/render_deployment_guide.py` and never edited by hand.

The first stages Doug needs are 3 to 5: domain names, Google Workspace, and the service accounts. They come first. Later stages follow the order of section 5 of the Association's demo chapter plan (`business-mentors-association/docs/demo-chapter-plan.md`), and each gets its own short plan when it is reached, not now.

## 2. The repository's state at the start (read 11-07-26 15:03)

- `main` is one commit ahead of GitHub: `fcc3bb3 docs: chapter website plan 0.6`. It is not this session's.
- Another line of work has 24 changed files and 5 new files uncommitted: campaign, form, newsletter and settings code, a test file, two training screenshots and `crm-plans/chapter-website.json`. This session never stages, stashes, resets or discards any of them.
- The renderer's check passes on the current data (`--check`, exit 0).
- **A push of this session's commits would also carry `fcc3bb3`, and a push to `main` deploys crm-test and production.** This session commits locally and pushes only on Doug's go-ahead at a stopping point.

## 3. The files this session may change

- The stage data files: `steps/stage-01.yaml` to `steps/stage-18.yaml`, and `steps/placeholders.yaml`.
- The rendered pages in `guide/`, written only by the renderer.
- `2-The-Step-List.md`. Each step's finishing test is kept word for word with this list (`steps/README.md`), so a changed or new finishing test changes it too.
- `steps/README.md`, where a field's meaning changes, such as the wording of `who`.
- This plan.
- `OPEN-ITEMS.md` at the repository root, at the end of the session.
- **Two files outside `prds/chapter-network/`, only if Doug approves item 4.1 below:** `scripts/render_deployment_guide.py` and `scripts/chapter_form/page_template.html`. Both print "the central support organization" themselves, so the wording cannot be corrected in the data alone.

Every commit stages these files by path and is audited with `git show --stat`.

## 4. The work, batch by batch

### Batch 1 — wording, the two contradictions of ruling 1, and stages 3 to 5

4.1. **"The central support organization" becomes "the Association"** in every stage data file, the step list, the renderer's two built-in phrases and the chapter information form's page template (review finding 5). The data value `who: central` keeps its spelling, because the onboarding application reads it; only the printed words change. The numbered method notes (`1-` to `11-`) are history and keep the old wording.

4.2. **Step 2.3, "Accept the identical-software rule"**, is rewritten to Association ruling 3: one application, with chapters differing only through optional settings and their own processes, and new features asked for by feature request. **Step 14.3, "Confirm nobody at the chapter holds an administrator account"**, is rewritten to Association ruling 1: the chapter holds its own administrator accounts, and the Association holds a named account for backup support. The step names change; their numbers do not.

4.3. **Stage 3, domain names.** Step 3.2 stops treating the number of domain names as open: the Association recommends two, one for the website and a shorter one for email (ruling 25), and a chapter may still choose one. The worked registrar stays "any ordinary registrar", because registering through Cloudflare is only a drafted item, not a ruling. Each action is checked against the Step-by-Step Instructions standard (one action, exact location, expected result, failure path).

4.4. **Stage 4, Google Workspace.** Checked against rulings 18 and 20, and the two accepted costs recorded with ruling 72. Step 4.6, the Association's own administrator account in the chapter's Google Workspace, is checked against ruling 1. Open work item G1-10 in `TASKS.md` (no check that the email signing key took effect) is fixed here if it is small.

4.5. **Stage 5, service accounts.** Step 5.4, the Association's access to the hosting account, is checked against ruling 1. Step 5.5 names Zoom as settled (ruling 72) and carries the plan and its price as a placeholder until decision D4 is answered. Steps for the missing services are added at the end of the stage, under the numbering in section 5, question 1:

- 5.10 Open the website host account (Cloudways, ruling 29).
- 5.11 Open the Constant Contact account and its developer application. The applications connect to it later, from System Settings, after stage 11. The plan and price are a placeholder until D4.
- 5.12 Open the Stripe account and create the Payment Link (ruling 30). For the Association it is in test mode (ruling 71).

The stage is renamed from "Open the hosting and video meeting accounts" to "Open the chapter's service accounts", and steps 5.6 and 5.7 (two-step sign-in, and the account list) cover the new accounts. Each new value a step produces is needed by a later step, so the renderer's information check keeps passing: the Payment Link address, for example, is needed by the Website group of System Settings (ruling 47).

Cloudflare Web Analytics (ruling 63) is not added here. It needs the website to exist, so it goes into stage 6 in batch 3.

4.6. Render, run the check, commit locally with a `docs:` message. No push.

**Stop 2 — Doug reviews batch 1.** He reads the rendered stages 3 to 5 and the two rewritten steps. Decision D4, the Zoom and Constant Contact plans and prices, is put to him here, because stage 5 needs it. One more question is put to him here, because the guide and the Association's own setup runbook disagree: which address every account signs in with. The guide uses `info@`, a mailbox; the Association's setup runbook uses `admin@`, a group, so both owners receive every reset (ruling 18).

### Batch 2 — what Doug follows for stages 3 to 5

4.7. The instructions Doug follows for stages 3 to 5 are produced in the form chosen in section 5, question 3, with the Association's own values filled in: businessmentorsassociation.org, mentorsassociation.org, the registrar as a placeholder until Doug names it, and placeholder values for anything that waits on the Association being formed, such as the employer identification number (rulings 23 and 24). Stages 1 and 2 are not done: the Association is not formed. Where stage 3 assumes them (the bank account, the vault), the instructions point at the Association's setup runbook, which already covers the vault.

**Stop 3 — Doug follows stages 3 to 5.** This is Stop C of the demo chapter plan: every account open and recorded. Each screen that differs from the guide is corrected in the data, re-rendered and committed. Doug decides at this stop whether to push.

### Later batches — one short plan each, at its own stop

- **Batch 3, stages 6 and 7:** the website rewritten for WordPress on Cloudways, the chapter connector, the Website group of System Settings and framed forms (rulings 26 to 70; review finding 1), with Cloudflare Web Analytics added. `prds/chapter-website-plan.md` cites the Association's rulings under their old numbers; each citation is checked by its wording.
- **Batch 4, stage 8:** the chapter information form for the Association. Stop D of the demo chapter plan.
- **Batch 5, stage 9:** the CRM system, built by Doug with CRM Builder. Decision D2 first. Stop E.
- **Batch 6, stages 10 to 12.** Stop F.
- **Batch 7, stage 13**, the switch-over of the test website. Decision D1a first. Stop G.
- **Batch 8, stages 14 to 17.** Decision D3 first. Stop H. Stage 18 is recorded as not applicable apart from the check that the accounts can be reached without help.

## 5. The four questions the kickoff prompt puts to Doug, with Claude's recommendations

These are recommendations, not decisions.

1. **Where the steps for the missing services go.** Recommended: at the end of existing stages (5.10 to 5.12, and a new last step in stage 6), so no existing step number changes and no ruling is needed. Cost: stage 5 grows to twelve steps, the account list (5.7) comes before three accounts it must list, and the stage's page gets a new name, so links to the old page name break. The other option, a new stage between 5 and 6, renumbers stages 6 to 18 and every reference to them, and needs a ruling.
2. **Notes at each step for a setup like the Association's**, with real accounts and invented data. Recommended: no notes in the guide. The Association's setup is a one-off; its differences go in the instructions Doug follows (batch 2) and in the Association's own records. Cost: a later reader of the guide does not see how the shared test system differs from a chapter.
3. **What Doug follows by hand.** Recommended: one runbook page per stage, published as a private page with one done box per step, as his Step-by-Step Instructions standard requires, built from the corrected stage data with the Association's values filled in. The rendered pages in `guide/` do not meet that standard: they have no done boxes, and their entries are not each in their own copyable block. Cost: the runbook is a second copy that can drift from the stage data; each runbook names the stage version it was built from, and is rebuilt when that version changes. The other option, teaching the renderer to write runbook pages, serves every later chapter too, but it is new code in the application repository and a larger piece of work.
4. **Where the stopping points fall.** As in section 4: Stop 2 after batch 1, Stop 3 after Doug follows stages 3 to 5, then one stop per later batch, matching Stops C to H of the demo chapter plan.

## 6. Two conflicts Claude found, for Doug to settle

- **This session was started in the Association's repository**, not in `cbm-client-intake` as the kickoff prompt intended. The work is done here with full paths, and this repository's `CLAUDE.md` was read by hand. The Association's `CLAUDE.md` asks every session there to update its `NEXT-STEPS.md` before ending, while the kickoff prompt makes that repository read-only. Recommended: Claude updates `NEXT-STEPS.md` at the end of the session only, and only with Doug's go-ahead.
- **Where Doug's runbook pages are kept**, if question 3 is answered as recommended. They are the Association's own instructions, so they belong in the Association's repository under `docs/runbooks/`, which is read-only from this session. Recommended: publish them as private pages from Claude's scratch folder, and have them committed to the Association's repository with `NEXT-STEPS.md` at the end of the session.

## 7. Progress

**Batch 1 done 11-07-26 15:21, committed locally, not pushed.** Three things differ from section 4:

- The same contradiction of ruling 1 also stood in step 2.1's failure, step 2.4's access schedule, and the summaries of stages 14 and 18. They were corrected with steps 2.3 and 14.3.
- Stage 2's name held the old wording too, so its page was renamed as well as stage 5's. The two old pages were removed; nothing linked to them.
- Steps 5.10 to 5.12 each turn on two-step sign-in and fill in their own line on the account list, instead of steps 5.6 and 5.7 covering them, because those two steps come first. Step 5.7 now names the three accounts and leaves a line for each.
- Step 5.9 was in the stage data but missing from the step list; it was added.

**Stop 2, first answer, 11-07-26 15:28:** Doug chose admin@, the administrators group, as the sign-in address for every account a chapter opens. Applied to steps 3.7, 4.9, 4.14, 5.1, 5.2, 5.4, 5.6 and 5.10 to 5.12. Because every member of the group receives every account's password resets, step 4.9 now asks for at least two chapter officers, and adds a person from the Association only if the access schedule of step 2.4 says so (Association ruling 1). Decision D4 is next.

**Stop 2, decision D4, 11-07-26 15:34:** Doug chose a Zoom Pro seat without the Webinars add-on, and Constant Contact Lite paid monthly, about $25 to $30 a month together (prices from third-party guides, not checked on the vendors' pages). Webinars and attendance stay untested until the add-on is bought; if Lite does not allow the developer application, the fallback is Standard. The guide keeps ZOOM-PLAN and MAILING-PLAN, because each chapter chooses its own plans; the Association's choice goes into its stage 5 runbook. D4 is recorded in the Association's repository at the end of the session.

**Batch 2 started:** the stage 3 runbook for the Association is published at https://claude.ai/artifact/CVYeUihJjLicGJgkxQMPM3 (version 1.0, built from guide stage 3 version 0.5). A public lookup on 11-07-26 15:31 showed both domains registered at GoDaddy that morning, still on GoDaddy's name servers. Stages 4 and 5 follow.

**Stage 3 done, 11-07-26:** both domains moved from GoDaddy's name servers to Cloudflare (pablo and penny.ns.cloudflare.com). Doug skipped the GoDaddy account section: its steps did not match GoDaddy's screens and the organization name was not worth the time. Guide step 3.7 was corrected three times from his run.

**Working method changed, 11-08-26:** Doug found the stage 4 runbook's steps unclear and wrong against Google's screens, and asked Claude to do the work in his browser instead. From then on Claude works in Chrome and hands Doug only passwords, payments, two-step codes, and a yes before each change that costs money or cannot easily be undone. The stage 4 runbook (https://claude.ai/artifact/4npGt6PfSSgzw7ynCBZYxp) is superseded by the corrected guide stage 4.

**Stage 4 done, 11-08-26 01:24:**
- Google Workspace on mentorsassociation.org, Business Starter, Flexible plan ($8.40 per mailbox a month from 11-21-26; Google had started a Business Plus trial). Two mailboxes: doug.bower@ (Super Admin; created as admin@ and renamed) and info@. Groups admin@ (System Administrators; outside senders allowed, members only read, invitation only) and allmembers@.
- Mail records clean in Cloudflare: one MX, SPF, the current DKIM key, DMARC p=none reporting to admin@, Google's verification. Eleven stray records removed (GoDaddy's defaults and older Google records). Tested both ways: outside mail reaches admin@; a reply passes SPF, DKIM and DMARC.
- Cloudflare's account email moved to admin@ (step 4.14). GoDaddy stays on businessmentors@dougbower.com by Doug's decision (11-08-26).
- Guide stage 4 corrected from the real screens (version 0.7).

**Owed from stages 3 and 4:**
- The second owner (ruling 18): not named. Then: a second Super Admin in Google, a member of admin@, a Cloudflare member, a Proton Pass administrator.
- GoDaddy auto-renew on both domains (they expire 11-07-27) and GoDaddy two-step sign-in.
- Two-step sign-in on doug.bower@ and info@, then compulsory two-step sign-in for the Workspace (Doug: not yet, 11-08-26).
- DMARC from p=none to p=quarantine on or after 12-06-26, once the reports show only the Association's own mail.
- Guide step 2.7: where Proton's organization members are managed was not found (Doug, 11-07-26).

**Stage 5 done, 11-08-26 09:32** (Stop 3 of this plan; Stop C of the demo chapter plan). Every account signs in with admin@mentorsassociation.org unless noted:
- DigitalOcean: team Business Mentors Association; spend alert at $75 a month (50, 75 and 100 percent).
- Zoom Pro, without the Webinars add-on (decision D4). Server-to-Server OAuth app Business Mentors Association Webinars, active, with only user:read:user:admin and report:read:list_webinar_participants:admin: the webinar scopes need the Webinars licence. Zoom signs in with admin@ rather than the guide's webinars@ mailbox, because there is no webinar host yet.
- Constant Contact, free trial, Lite to be bought before it ends (decision D4). Developer application Business Mentors Association applications (API key 37d80aac-bf3d-4428-85a2-75334d4cf443), redirect https://apps.businessmentorsassociation.org/api/setup/mailing/callback, to change if stage 8 picks another applications address.
- Stripe, Sandbox (test mode). Donation link https://donate.stripe.com/test_fZu3cvcvZ4gxe1R7t3ds400. Signs in with doug.bower@mentorsassociation.org: the sign-up had admin@ misspelled.
- Cloudways, the Association's own account (Doug, 11-08-26, superseding ruling 70's "in Doug's own account for now" for the account itself). No server yet: stage 6 builds it.
- Not applicable to the Association: 5.3 (nonprofit credits: not formed), 5.4 (the Association is the chapter). Not yet done: 5.8 and 5.9 (CRMBuilder tokens and the GitHub link), which belong with stage 9.
- Guide stage 5 corrected from the real screens (version 0.14).

**Owed from stage 5:** two-step sign-in on DigitalOcean, Zoom, Stripe and Cloudways (Constant Contact's is on); Constant Contact Lite before the trial ends; Stripe's email moved to admin@; the Zoom Webinars add-on and its scopes when webinars are tested; the admin@ group's spam handling (it holds suspicious messages for approval; Claude was not permitted to change it); the account list in Proton Pass (step 5.7).

### Batch 3 plan — stage 6, the website (drafted 11-08-26 09:57, awaiting Doug)

Stage 6 in the guide predates the website rulings (review finding 1). It still has a colour file (6.5), a logo held only in the CRM (6.6) and a redirect check for an events page (6.3). Under Association rulings 26 to 70 a chapter's website is WordPress on Cloudways (rulings 28 and 29), built from the template, with the chapter connector applying the colours, fonts, logo and key pages set in the Website group of System Settings (ruling 34), forms in frames (ruling 44) and Cloudflare Web Analytics (ruling 63). Track 1's test website runbook (`business-mentors-association/docs/runbooks/test-website-runbook.html`) already covers the Cloudways server, the DNS record and the chapter connector for the Association's test site; batch 3 folds it into the guide and runs it in the Association's own Cloudways account.

1. **Rewrite guide stage 6** for any chapter: choose WordPress or keep another platform (ruling 27's basic path); in the Cloudways account from step 5.10, launch the server and WordPress; point the address at it in Cloudflare (DNS only); attach the domain and its certificate; install the template and the chapter connector; name a website editor; Cloudflare Web Analytics; where the help documentation lives. The colours, logo and header graphic move to the Website group (stage 13). Step numbers 6.1 to 6.7 keep their numbers where the step survives; a step whose subject disappears is renamed, and new steps are appended, so no ruling is needed.
2. **Do stage 6 for the Association**, in Doug's browser. Doug's part: a yes before the server (about $14 a month, from memory), the DNS record and the certificate step (Claude's permissions block DNS changes), and anything needing a password. Claude's part: the Cloudways screens, WordPress, the chapter connector settings, and correcting the guide from what the screens show.
3. **Stop 4 of this plan:** Doug opens the website and reviews it; the guide's stage 6 is committed locally.

**Batch 3 approved, 11-08-26 10:00:** Doug chose `chapter-demo.mentorsassociation.org` for the website, as ruling 70 says; D1a stays open until stage 13. The Association's Cloudways account is held for Cloudways' manual activation check; Doug emailed av@cloudways.com 11-08-26. **Guide stage 6 rewritten 11-08-26 10:06** (version 0.7, committed locally); the Association's stage 6 waits on Cloudways. Owed with it: the chapter connector's zip in the prototype repository is still 0.2.0 while its source is 0.2.1; guide stage 13 still names the old redirect step 6.3 in its Before you start, to be corrected with stage 13.

## 8. At the end of the session

The closing reply reports what changed in the guide, which stages are ready for Doug to follow, and which open decisions blocked a step. Work still owed is recorded in `OPEN-ITEMS.md`.

---

## Change log

| Version | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.7 | 11-08-26 10:06 | Claude (Claude Code) | Batch 3 approved with the website address; guide stage 6 rewritten; Cloudways activation pending. |
| 1.6 | 11-08-26 09:57 | Claude (Claude Code) | Batch 3 plan, stage 6, drafted for Doug's approval. |
| 1.5 | 11-08-26 09:32 | Claude (Claude Code) | Stage 5 recorded as done, with what is owed. |
| 1.4 | 11-08-26 01:24 | Claude (Claude Code) | Stages 3 and 4 recorded as done, the change of working method, and what is owed. |
| 1.3 | 11-07-26 15:34 | Claude (Claude Code) | Decision D4 and the stage 3 runbook recorded in section 7. |
| 1.2 | 11-07-26 15:28 | Claude (Claude Code) | Doug's answer on the sign-in address recorded in section 7. |
| 1.1 | 11-07-26 15:21 | Claude (Claude Code) | Section 7, progress: batch 1 done, with the four differences from the plan. |
| 1.0 | 11-07-26 15:17 | Claude (Claude Code) | Approved by Doug as written. |
| 0.1 | 11-07-26 15:06 | Claude (Claude Code) | First draft, from the kickoff prompt version 1.2. |
