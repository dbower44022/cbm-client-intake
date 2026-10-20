# Kickoff — finish the lead model's live pass, then prospect marketing's next step

Revision 1.0 · Last Updated: 10-19-26 23:34 · Prepared by Claude (Claude Code) for D. Bower

| Rev | Date (MM-DD-YY HH:MM) | Change |
|---|---|---|
| 1.0 | 10-19-26 23:34 | First version, written at the end of the lead-model code session (v0.265.0–v0.265.3, rulings 51–54). |

Operating mode: DETAIL.

## What this session does

1. Finishes the live pass of the lead model on crm-test (build plan § 7a.5
   step 3): sections G4 and H, which are the only ones not yet run, then
   closes the pass in the documents.
2. Then puts the next step of the arc to Doug: production's CRM slot for the
   lead model (§ 7a.5 step 4), or the § 6 removals, or Boston.

Commit in this clone. Doug reviews and pushes: he answers "push" when he wants
a push, and a push builds crm-test **and** production.

## Read first, in this order

1. The repository's root `CLAUDE.md`, especially *Campaign Management* (the
   lead-model bullet) and the current-status block for v0.265.0.
2. `prds/prospect-marketing/README.md`, *Rules for working in this
   directory*. Check `git log -3 -- prds/prospect-marketing` first: one
   session on this arc at a time.
3. `prds/prospect-marketing/rulings.md`, rulings 41–54 (51–54 were made on
   10-19-26).
4. `prds/prospect-marketing/build-plan.md` § 7a.5 (step 2 records what was
   built and decided).
5. `coutreach-lead-model-crm-handoff.md` rev 1.2 (§ 1 table, § 3a, § 5, § 7).
6. `OPEN-ITEMS.md` item #51 (its first paragraph is the lead model's owed list).
7. The live-pass page: https://claude.ai/artifact/DPSsyZMYPhvHQRUnL696Rk
   (revision 1.4, 58 steps). Its generator is
   `make_runbook.py` in the previous session's scratchpad and is gone; read the
   page with the Artifact tool (`action: "read"`) and edit the saved HTML.

## Where the pass stands (read back from crm-test by Claude, 10-19-26 23:30)

- **A** (deploy and the release's CRM steps): done. v0.265.0 deployed;
  `touchpos`, `leadlayouts`, `leadmove` applied; campaign switches on.
  A8/A9 (ruling 54, Marketing Admin Role reads every Company) applied by Doug
  at 12:23 and seen working.
- **B–F matched**, checked against the CRM: two filing leads Qualified, two
  Unqualified, five list leads Unqualified; Franchise Burger 112 Disqualified
  with its reason in the notes; the postcard campaign Complete with 8 sent;
  Fulton Rd Hardware converted to a Company and its Contact from an email
  alone; Lorain Ave Tailor converted to a Company only; Storer Ave Laundromat
  left Unqualified; the call list of 6; Detroit Ave Bakery Interested with no
  email, still Unqualified, called again; Tremont Print Shop and Clark Ave
  Diner converted; Lakeshore Bike Repair stopped by Declined.
- **G1–G3 matched:** one lead *Lead Model Bakery*, Lead Source Mentor request,
  Converted, after two submissions.
- **Owed:** **G4** (the information request: Ian Leadmodel's Contact at
  Engaged and a lead with Lead Source Information request) and **H** (the
  Analytics *Campaigns* page: the funnel, Touches by campaign, Leads by Lead
  Source). Doug did not send checkpoints E–G; the read-back above stands in
  for them.
- **crm-test's nightly reset (04:00 UTC, midnight Eastern) removed the pass's
  leads, touches and campaigns on 10-20-26.** Section A survives (CRM plans,
  roles, layouts, `/setup` overrides). H's expected numbers depend on the B–F
  data, so H needs that data again. Put this to Doug first, as a decision:
  re-run B–F before G4 and H on one day (about 45 minutes), or run G4 alone
  and check H's tables for shape only. Recommend the re-run: H's numbers are
  the only proof that the three counts of ruling 46 agree across screens.

## Defects the pass found, all fixed and live (v0.265.1–v0.265.3)

- The lead's page showed no notes (C5) — fixed.
- A marketing user could not name *Who calls*: linking a Team needs Team read,
  which the Marketing Admin Role lacks — the write now retries that one
  refusal as the admin account (F1).
- The call screen hid the lead's own email; an opened call could not be
  cancelled — the boxes now prefill and a Cancel button exists (F6).
- Not a defect: Mark Marketing had no Companies in the CRM because the role
  never held Account; ruling 54 granted read.

## Rules this session follows

- **Step-by-step rule 9 (new, 10-19-26):** every form value is written out
  every time; never "sandbox answers", "same values as step X" or "repeat
  steps X to Y". The standard is block v=1.2 on the wiki page
  `Standards.Step-by-Step Instructions`; `~/.claude/CLAUDE.md` carries it.
- Every step names the application and the tab; values are pre-filled from a
  CRM read first; Claude does the CRM read-backs (memory notes).
- A stale browser page reads as a defect: ask for Ctrl+Shift+R first.
- The session classifier refuses Claude's own CRM writes (`--apply`, role
  scripts); Doug runs them with `!`.
- Read-only CRM reads work as the org-wide key (`core.config.get_settings`,
  `EspoClient`) or as the admin (`scripts/run_with_admin.py <script>`).

## Also owed, outside this pass

- **Production at a Sunday 17:00 UTC slot** (handoff § 1): the lead-model
  plan, the touch-positions plan, the labels, the layouts, the value move
  (dry run first, records counted — ruling 45), and the role script for
  ruling 54. Then Boston with its release. Then § 6's removals, on Doug's
  approval.
- **The roles standard** (`prds/chapter-network/roles-standard/`) updated for
  ruling 54.
- **The step-by-step mirror page** https://claude.ai/artifact/87zLT1sxFkLBreM95kynUn:
  section A passed 16:39; Doug's preferences hold a stray MIRROR NOTICE
  paragraph after the block's END marker (deletion owed); section B (a fresh
  Claude Code session quoting v=1.2) not yet run. Close the Mirror Registry
  entry when both are done.
- Leave alone: `uv.lock`, `prds/chapter-network/chapter-values -Boston.md`,
  `scripts/rehearsal/api-half-result.json` — not this arc's.
