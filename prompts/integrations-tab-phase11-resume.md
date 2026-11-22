# Resume prompt — Integrations tab, phase 11: the rest of the live review, then closing

Last Updated: 11-21-26 23:58 · Revision 0.1 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). The phase prompt
`prompts/integrations-tab-phase11-prompt-v0.1.md` (revision 0.2, approved)
still governs: its stopping points 3 and 4 remain. Open every reply with the
local time from `date`; the first reply states the operating mode and the
`CLAUDE.md` files loaded.

Read before any work:

- `prompts/integrations-tab-build-orchestrator-v0.1.md` (the rules for every
  phase session and how a phase is closed);
- `OPEN-ITEMS.md` item 82, its **Phase 11** block (what was found, fixed and
  proved 11-15-26 to 11-18-26) and owed items (11a) to (11e);
- `setup/CLAUDE.md` (the Integrations tab's rules) and
  `SYSTEM-SETTINGS-SETUP.md` § 8;
- `CHANGELOG.md` 0.336.1, 0.337.0, 0.338.1, 0.339.1 and 0.339.2.

## Where it stands

- Part 1, the documentation, is done.
- The live review runs on the Business Mentors Association's system from the
  runbook https://claude.ai/artifact/11KuG6XaP1nN6dvP6Gon5c (revision 2.1;
  its HTML is not in the repository: read it with the Artifact tool and
  republish it from a file in the new session's scratchpad to update it).
  Doug walked it through section 4 (Zoom Meetings) and reached step 5.1. He
  has not yet sent section 4's report line (the scopes, the first co-host
  read).
- Zoom Webinars: the Association has no Webinars add-on. The agreed next
  action is step 5.1 answered **No** (Back to step 1 in its setup dialog), so
  it reads *Not used by this chapter*; steps 5.2 to 5.6 are then skipped.
- Doug's overall plan for the next sittings is the page
  https://claude.ai/artifact/Qn5NDnxXGWMfNRSuzFyHYN (What's Next, 11-18-26):
  its sections 1 and 2 (the Zoom scope and the Event hosting fixes) and 3.1
  to 3.2 (EspoCRM) are done.

## What to do

1. **Ask Doug for section 4's report line and step 5.1's result.** Put each
   finding to him as a fix or an open item, one at a time (the phase
   prompt's stopping point 3). Fix what he approves, with tests, on its own
   version: read `git log` first, since other sessions take versions too.
2. **Sections 6 to 9 of the runbook** follow the same way. Before section 6,
   check that its steps still match the page (the status screen and dialog,
   v0.337.0) and republish if not.
3. **(11a) The vault wording**, ruled A by Doug 11-16-26: every setup step in
   `prds/chapter-network/deployment-guide/steps/stage-*.yaml` whose `wizard:`
   text says "the vault" names it in full, "the Operations vault in the
   chapter's Proton Pass" (32 mentions on 27 steps). Only `wizard:` text;
   `scripts/render_deployment_guide.py --check` must still pass. **Another
   session may have uncommitted edits in the step files: check
   `git status` and stop to ask before touching a file it is editing.**
4. **(11d)** goes to the event hosting session, not here.
5. **Closing (stopping point 4)**, as the orchestrator requires: the State
   column; item 82 cut to what is still owed; switching the tab on in
   production written as the next step for Doug's decision, with what
   production lacks (credentials, the CRM changes in #80 and #84, the
   chapters' release train).

## Things learned in this phase

- **Commit with an explicit path list** and audit with `git show --stat`;
  several sessions share this checkout and index.
- **Read the Association's CRM with the admin login in
  `~/.config/cbm-bma/bma.env`, parsed in Python, never sourced by a shell.**
  That is how finding 5 (a renamed email template) was found.
- **A step that the setup cannot pass in order is a defect, not a user
  error** (finding 4b: the token waited for a value asked three steps later).
  Check each test-check step's dependencies against the steps before it.
- Doug's standards from this phase: never a link styled as a button; one
  primary button plus **Other Actions ▾** (memory
  `no-links-as-buttons-other-actions-menu`); every process step by step in a
  dialog; one question at a time.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 23:58 | Claude (Claude Code) | Written at the end of the 11-15-26 to 11-18-26 session, on Doug's "update docs and close". |
