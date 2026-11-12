# Loading the training data into the Association's system — plan

**Document:** Plan for loading crm-test's invented training data into the Business Mentors Association's customer relationship management system, under Association ruling 77 (guide stage 15, with the training sign-ins of stage 14)
**Version:** 1.3
**Status:** Approved by Doug 11-12-26 00:33, with option A of section 9
**Owner:** Doug Bower
**Last Updated:** 11-12-26 01:28

---

## 1. What this plan does

The customer relationship management system (CRM system below, meaning the EspoCRM server that holds a chapter's records) at crm.businessmentorsassociation.org gets the same invented people, companies and mentoring histories that crm-test holds. The scripts in `scripts/sandbox/` that built crm-test's training data are rerun against it. Every invented address goes on `sandbox.mentorsassociation.org`, a domain with no mailboxes. Records typed into crm-test by hand are not copied; that is ruling 77's accepted cost, and section 2 says what it loses.

## 2. What crm-test holds, and what ruling 77 loses — counted, read-only

Read 11-12-26 05:27 UTC with the applications' CRM key. Every script was also run without `--apply` against crm-test, which writes nothing and reports what it would add.

**Every record of every kind the scripts make is named in a script.** On crm-test: 26 mentor profiles, 34 companies, 61 contacts, 18 client profiles, 18 engagements, 85 sessions, 8 partners, 6 funders, 3 email threads with 12 messages, 5 contributions, 5 events, 3 event registrations, 17 leads, 6 campaigns and 10 campaign touches. No company, contact, mentor, session, lead or campaign on crm-test is missing from the scripts.

**What no script made, and so is not carried over:**

- **All 25 sign-ins.** The scripts never create one. Twelve of them are training identities the Association needs (section 5). The other thirteen are people's own test sign-ins and staff test accounts; none belongs on the Association's system.
- **10 email templates**: eight event templates and two others. These are CRM standard work, not training data. The Association's CRM holds 2; the five event templates it lacks are already recorded at guide stage 9 (`OPEN-ITEMS.md` item 76).
- **7 intake receipts**, release-test leftovers from 10-19-26 and 10-20-26.
- **94 action-history rows**: the history of what people did on crm-test.
- **Documents and native emails**: the applications' key cannot read them, so they were not counted. No script makes documents.
- **The application database's rows** (the Submission Admin queue, discussion comments, the Drive index). The nightly restore empties them on crm-test anyway.

So in practice ruling 77 loses nothing that training uses, apart from the twelve sign-ins, which are created again by hand.

**crm-test holds less than the scripts make.** The dry runs report 60 changes there today, among them: the three event presenters (crm-test has none), the presenters' sponsor and partner links, five engagement notes, three referring-partner credits, about 140 field values on the showcase records, and their session attendees. The cause was not checked. The Association's system will therefore hold slightly more than crm-test, in the scripts' favour. Recorded as an open item.

**The Association's CRM today:** 3 sign-ins, the 10 standard teams, and the stage 11 test records (1 mentor, 1 company, 2 contacts, 1 engagement, 1 session, 1 event, 8 receipts). They stay; stage 17 removes them. The applications' key cannot read leads, campaigns, campaign touches, event presenters or partner associations there (item 76, part 5).

## 3. The scripts, their order, and every place they assume Cleveland

Order, as `SANDBOX-RESET.md` runs them:

1. `seed_training_data.py` — mentors, companies, contacts, client profiles, engagements, sessions, partners, funders, team stamps. Applications' key.
2. `enrich_training_data.py` — threads, partner and funder sessions, contributions, events, presenters, notes, referrals. Applications' key.
3. `deepen_showcase_records.py` — every field of the showcase records, the photo, registrations, attendees. Applications' key.
4. `seed_outreach_data.py` — leads, campaigns, touches, converted prospects, additional managers. The CRM administrator's sign-in.
5. `seed_import_templates.py` — the import tool's demo template, in the application database. Needs the database address, so it runs in the deployed container.
6. `audit_showcase_records.py` and `check_containment.py` — read-only checks.

`make_volume_leads.py` (3,000 throwaway leads for a speed test) and `purge_crm_records.py` are not part of the training data and are not run.

Cleveland assumptions found:

- **Every script refuses any CRM whose address lacks "crm-test".** The Association's CRM is refused. This alone means a code change is needed.
- **The address domain `sandbox.cbmentors.org` is fixed in the code** in four scripts: `enrich_training_data.py` (5 places), `deepen_showcase_records.py` (`DOMAIN`), `seed_outreach_data.py` (5 addresses) and `check_containment.py` (`SANDBOX_EMAIL_DOMAIN`). Only the seed script takes `--email-domain`.
- **The ten training sign-ins are `@cbmentors.org`** in `seed_training_data.py` (`MENTORS_WITH_LOGINS`).
- **The organization's name in one record**: the draft text campaign's message begins "Cleveland Business Mentors:".
- **Invented Cleveland content**: Cleveland street addresses, 216 phone numbers, "Cuyahoga Small Business Alliance", "Ohio filings — September 2026", a City of Cleveland permit, the Cleveland Orchestra in a mentor's interests. Kept as they are: ruling 77 wants the same records on both systems so training material and screenshots match.
- **The application side refuses too.** `campaigns/sandbox_demo.py` (the demo campaign links and the import template the worker puts back) and `core/sandbox_reset.py` both refuse any CRM but crm-test.
- **Settings**: the seed script reads the partner and funder team names from the application's settings; the defaults match the Association's teams.

## 4. Pointing the scripts at the Association's system — a code change

Run-time settings cannot do it: the refusals and the fixed domain are in the code. The change, under this repository's process (local commit, tests, Doug pushes):

- One small module, `scripts/sandbox/targets.py`, lists the two training systems and nothing else: crm-test with `sandbox.cbmentors.org`, and the Association's CRM with `sandbox.mentorsassociation.org`. Each script asks it which system it is connected to and refuses any other. Cleveland's production CRM, Boston and Lakeside stay refused.
- The address domain and the training sign-ins' domain come from that list, never from a fixed string. crm-test's behaviour does not change.
- Each script takes `--env-file`, so the Association's credentials come from `~/.config/cbm-bma/bma.env` without touching `.env`. The file is read with a parser, never sourced.
- The campaign message's opening uses the target system's organization name.
- `campaigns/sandbox_demo.py` accepts the Association too, so the demo campaign links can be put back from System Settings. `core/sandbox_reset.py`, the destructive nightly restore, is left refusing everything but crm-test in this session (section 7).
- `tests/test_sandbox_seed_scripts.py` gains tests: an unknown CRM is refused, Cleveland's production address is refused, and each target gets its own domain.

## 5. The training sign-ins

The Association needs twelve sign-ins, the ten the seed script attaches profiles to plus the two the training guide uses:

- Mentor Team: Joe Mentor, Matt Mentor, Tony Tiger, Wally Walrus, Tom Gold, Jim Beem, Tommy Tranell.
- Kitty Cat: Client Administration Team and Mentor Team.
- Partner Manager: Partner Management Team and Mentor Team.
- Sally Sponsor: Sponsor Management Team.
- Mentor Admin: Mentor Administration Team and Mentor Team. Regular, not Admin as on crm-test (guide step 14.2 says never Admin).
- Mark Marketing: Marketing Admin Team.

Each user name and email address is on `sandbox.mentorsassociation.org`, for example `joe.mentor@sandbox.mentorsassociation.org`, so the sign-in and the mentor profile's chapter address are the same.

They are created by an administrator, as guide step 14.2 says, in the CRM's own Users screen. Claude fills in the fields in Doug's browser; Doug types each password and keeps it in Proton Pass. This is the first time step 14.2 is done on EspoCRM 10, so its four unchecked labels get checked and the guide corrected. They are not created through Mentor Administration (guide step 15.9): that path would check Google for the address, add it to the real `allmembers@` group and try to email it. Training identities are the one exception, which the guide does not need to carry (the setup plan's question 2 answer: no Association-only notes in the guide).

## 6. Keeping the invented contacts out of Constant Contact, mail and invitations

**The Association is not contained the way crm-test is**, and this is the one decision in the plan (section 9). The local copy of its deployment settings, read 11-12-26 (the live settings could not be read in this session), shows `OPS_MAILBOX=info@mentorsassociation.org`, Gmail sync, Drive documents, calendar events and the `allmembers@` group switched on. crm-test has `OPS_MAILBOX` unset and its own shared drive.

What the address domain already stops: a mentor's email and calendar invitation are sent as the mentor's own chapter address, and an address on a domain the Workspace does not hold cannot be impersonated, so nothing goes out. Verified 11-12-26: Google reports "Domain not found" for `sandbox.mentorsassociation.org`, no user or group is on it, and public lookups show no mail exchange record and no address record, nor a catch-all on the parent domain.

What it does not stop:

- **Submission Admin and the quick-compose send as `info@`** when `OPS_MAILBOX` is set. A trainee's reply to an invented contact would leave from the Association's real mailbox and bounce, which is the harm ruling 72 names.
- **Drive** would create folders in the Association's real shared drive and try to grant invented addresses, failing every night and alerting.
- **Constant Contact**: the standing list takes only contacts with the marketing opt-in ticked, and no script ticks it. The switch `MAILING_SYNC` is off by default; whether System Settings turned it on was not read.

## 7. The nightly restore

Recommended: not in this session. Ruling 15 wants it, but the restore also wipes sign-ins created after the baseline, and the Association's system still has stages 14, 16 and 17 to do as a real chapter. Arming it needs the CRM half's refusal widened, the script installed and scheduled on the Association's server, the application half's refusal widened and its switch set, and a baseline captured once stage 17 is done. `SANDBOX-RESET.md` then needs a section per system: server address, schedule and hold file. Recorded as an open item.

## 8. Checks after loading

- The section 2 counts, taken again on the Association's system: the same as crm-test for every scripted record type, plus the 60 additions of section 2, plus the stage 11 test records.
- `audit_showcase_records.py` and `check_containment.py` against the Association: no blocking issue, every training address on the sandbox domain.
- Sign in at https://apps.businessmentorsassociation.org as Joe Mentor: Client Management lists his six clients with sessions, Brightline Bakehouse's Communications tab shows its thread. Then Kitty Cat, Partner Manager, Sally Sponsor and Mark Marketing open their own pages with data.

## 9. The decision Doug makes at Stop 1

How the invented contacts are kept from receiving mail sent as `info@`, and from the Association's real drive and group. Three options:

- **A. A sandbox-address guard in the applications (recommended).** One setting, the sandbox address domain, empty by default. When set, the applications never send to, share a Drive folder with, add to a Google group, or push to Constant Contact an address on that domain, and say so in the message. Four places in the code: the Gmail send, the Drive grant, the group membership and the mailing push. Cost: a real code change, built dark and reviewed on crm-test; it reaches the Association only at a release, so the load waits for the Sunday 11-15 train or an early release that also updates Boston and Lakeside.
- **B. Switch the Association's outward features off** (`OPS_MAILBOX`, Drive documents, the members group) while it serves as the training system. No code. Cost: stage 11's mail, Drive and group tests no longer hold, and stage 17 cannot pass on a system with them off.
- **C. Rely on the addresses alone**, as crm-test does. No code, no delay. Cost: `info@` replies and Drive grants reach out, which ruling 72 says must not happen.

Recommendation: A, because the Association is both a real chapter and the training system, and only a guard lets both hold at once.

## 10. Stopping points

- **Stop 1 — now.** Doug approves this plan and answers section 9.
- Work 1: the code of section 4, and of section 9 if A. Tests. Local commit only.
- **Stop 2.** Doug reviews the change and decides the push. The push also carries the four documentation commits already waiting (`2a81ffc3` to `1ecb608d`) and deploys crm-test and Cleveland's production; the guard ships switched off. Doug decides whether to cut a release early.
- Work 2: read the Association's live settings and System Settings overrides, and the API role's gaps against the roles standard. Draft the role change (item 76, part 5), which the enrichment script needs to make presenters.
- **Stop 3.** Doug's go-ahead for the role change and the guard setting on the Association's system.
- Work 3: the twelve sign-ins (section 5), Doug typing passwords. Then every script without `--apply` against the Association's system, and the report.
- **Stop 4.** Doug's go-ahead for `--apply`.
- Work 4: the load in section 3's order; the import template from the container console, which Doug runs; the checks of section 8; guide stages 14 and 15 corrected from what the screens showed; `OPEN-ITEMS.md`.
- **Stop 5.** Doug reviews; commit; push decision; the closing report for the Association's repository.

## 11. Progress

**Stop 1 passed, 11-12-26 00:33** (Doug: "approved - a").

**Work 1 done, 11-12-26 00:46, committed locally as v0.319.0, not pushed.** The guard of section 9 option A, named `SANDBOX_ADDRESS_DOMAIN` (System Settings → Email → Sandbox address domain), in the four places; the demo-links job allowed where it is set; `scripts/sandbox/targets.py` and every sandbox script pointed at it, with `--env-file`. Two differences from section 4: the application's address in the draft text campaign's message is localised too (crm-test's own address was written into it), and `check_containment.py`'s deployment half stays crm-test's, telling the operator to confirm the setting at `/setup` on the Association's system. All 3,592 tests pass; crm-test's dry runs are unchanged. Next: Stop 2.

**Stop 2 passed, 11-12-26 00:47** (Doug: push, and release now). `main` pushed; release v0.319.0 cut and pushed out of turn. By 00:53 the Association, Boston, crm-test and production all reported 0.319.0 and healthy.

**Work 2, 11-12-26 00:53.** Read, nothing changed:
- The Association's System Settings: shared mailbox `info@`, Gmail sync, calendar events, Drive documents, the Google directory check and `allmembers@` all on from the deployment settings; mailing sync off, Marketing Management off, the nightly wipe off, the sandbox address domain empty.
- The applications' CRM role, `CustomAppAPIRole`, on both systems: the Association's lacks six record types crm-test's has — leads, campaigns, campaign touches, event presenters, partner associations and enrichment findings. Every other scope matches, bar the stream setting on information requests.
- **Found:** on crm-test the same role may read event presenters but not create them, so `enrich_training_data.py` stopped at its first presenter and skipped everything after it (inferred from its dry run, which still lists the presenters, links, topics, notes and referrals; corrected 11-12-26 10:53: the notes and referrals are written on every run and always listed, so only the links and topics were really missing). Fixed locally (`a6461452`): a refused presenter is reported and the run goes on. Presenters stay absent on both systems unless added in Event Administration.

**Stop 3 passed, 11-12-26 00:55** (Doug: "all three").

**Work 3, 11-12-26 01:01.**
- Sandbox address domain set to `sandbox.mentorsassociation.org` at the Association's System Settings, read back.
- `CustomAppAPIRole` on the Association's CRM given the six record types, by `scripts/migrate_api_role_newer_entities.py` (crm-test reports nothing to do); read back, rebuilt, and the applications' key now reads all six. Item 76, part 5, done for the Association; Boston still to check.
- **The twelve sign-ins were created through the API, not the Users screen** (`scripts/sandbox/training_logins.py`), with no password. Section 5's plan had Claude fill in the screen while Doug typed passwords; the CRM asked for a sign-in in the browser first, and an API create with passwords set by Doug through a keyboard prompt keeps every password away from Claude. Cost: guide step 14.2's four unchecked screen labels were not checked. Doug sets the passwords with `~/.config/cbm-bma/set-training-passwords.sh`.
- Every script run without `--apply`: the seed would create 26 mentor profiles, 32 companies, 58 contacts, 18 client profiles, 18 engagements, 8 partners and 6 funders, and its sessions; all ten mentor sign-ins found; every address on `sandbox.mentorsassociation.org`; no Cleveland domain, name or address in any output. The later scripts' warnings are all "not created yet", because a dry run of a later script cannot see what an earlier one would create. The containment check's one failure is the stage 11 test mentor, `doug.bower@mentorsassociation.org`, which stage 17 removes.

**Stop 4 passed, 11-12-26 01:05** (Doug: "yes").

**Work 4 done, 11-12-26 01:28.** The load ran in section 3's order on the Association's system. The enrichment script first failed on a name clash of its own (a local variable hid the new module), leaving one thread's conversation without messages; fixed and rerun, it completed the thread. Its presenter step was refused by the applications' role, as section 2 inferred, and the run went on. The demo links, lead codes and import template were made through System Settings → Operations. Section 8's counts: every scripted record type equals crm-test's, plus the stage 11 test records; the audit reads 197 of 207 fields and 70 of 95 relationships (crm-test 69). The containment check's only failure is the stage 11 test mentor. The sign-in checks wait for Doug's passwords. Guide stage 15 is version 0.6 (step 15.4 no longer says the training system holds Cleveland's records); stage 14 needed no change from this work. `SANDBOX-RESET.md` revision 1.4. Owed work: `OPEN-ITEMS.md` item 81.

---

## Change log

| Version | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 11-12-26 01:28 | Claude (Claude Code) | Stop 4 and Work 4: the load done. |
| 1.2 | 11-12-26 01:02 | Claude (Claude Code) | Stops 2 and 3, Works 2 and 3. |
| 1.1 | 11-12-26 00:46 | Claude (Claude Code) | Section 11, progress: Stop 1 and Work 1. |
| 1.0 | 11-12-26 00:33 | Claude (Claude Code) | Approved by Doug, option A. |
| 0.1 | 11-12-26 00:31 | Claude (Claude Code) | First draft, from kickoff prompt version 1.1, with the read-only counts of 11-12-26. |
