# Kickoff prompt — flesh out the multi-chapter deployment plan

**Written 2026-08-19. For a fresh Claude Code session rooted in
`cbm-client-intake`.** The architecture is settled; this session turns it into
something buildable.

---

## The prompt

We are extending CBM's application suite to a network of mentoring chapters.
The architecture was settled with Doug across two sessions and is recorded in
**`prds/multi-chapter-deployment-plan.md`**. Your job this session is to **flesh
that plan out** — not to redesign it, and not to build anything.

### Read first

1. This repo's `CLAUDE.md` in full.
2. `prds/multi-chapter-deployment-plan.md` — the plan you are extending. Note
   its eight rulings, its six proposals awaiting Doug's decision, and its
   "Still open" list.
3. `prompts/crmbuilder-chapter-network-prompt-v0.1.md` — the parallel work in
   the CRMBuilder repo, and the read of that repo which changes this plan's
   Phase 1.
4. `prds/public-mentor-pages-plan.md` — ruling 8 makes it a network prerequisite
   rather than a Cleveland nicety.
5. `OPEN-ITEMS.md` for what is already owed on the single-chapter system. Some
   of it (live-verification debt, the CRM prerequisites) becomes materially more
   expensive once there are six chapters, and the plan should say so.

### The eight rulings are settled — do not reopen them

A funded central services organization; one EspoCRM per chapter; mixed Google
Workspace; strictly identical function (core or nothing); chapter-owned
infrastructure with services-org administration; services-org-only EspoCRM
admin; a release train moving all chapters together; and the app serving the
public pages for every chapter.

If you believe one of them is wrong, say so **once**, in a sentence, with the
evidence — and then continue working within it unless Doug changes it. Do not
relitigate by degrees.

### What "flesh out" means here

The plan currently says *what* and *why*. It does not yet say *how much*, *in
what order*, *done how you'd know*, or *by whom*. Produce that. Specifically:

1. **Rewrite Phase 1 around CRMBuilder.** The plan as written proposes building
   a CRM-config applier by generalizing `scripts/migrate_event_schema.py`. A
   review on 2026-08-18 established that CRMBuilder already covers most of it —
   a Qt-free 12-step CHECK→ACT pipeline, managers for roles, teams, email
   templates, security rules, entity settings and filtered tabs, an Audit that
   reverse-engineers a live CRM into the same YAML the engine consumes, a
   reconcile package for drift, and in-place EspoCRM upgrades. **Phase 1 becomes
   adoption, not construction.** Note the dependency honestly: the CRMBuilder
   work is governed by a different repo's requirement-first process, so its
   shape is not ours to assume. Write Phase 1 so it degrades gracefully if that
   repo's answer differs from what we expect.
2. **Give every phase acceptance criteria.** What must be demonstrably true for
   the phase to be finished. Prefer things that can be observed against a live
   system over things that can be asserted in a document — this project's
   standing weakness is a verification backlog, not a documentation one.
3. **Sequence and dependency.** Which phases can run in parallel, which are hard
   prerequisites, and what the critical path actually is. Phases 0 and 1 are
   stated as worth doing whatever happens with the chapters; test that claim and
   say whether it survives.
4. **Size the work honestly**, in relative terms rather than invented hours: what
   is a weekend, what is a month, and what is genuinely open-ended. Name anything
   whose cost cannot be estimated until a decision lands.
5. **Convert the six proposals into a decision list for Doug** — release cadence,
   crm-test as the network staging tenant, the change forum, preferring
   bring-your-own Workspace, labour-only fees, and the exit rehearsal. Each needs
   the consequence of each option stated tightly enough to decide from.
6. **Design the six still-open items** to the depth the rest of the plan has: the
   change-request route, the onboarding runbook (both Workspace branches), the
   cost model, the de-Clevelanding workstream, the fleet console, and the
   emergency path through the release train.

### Where to go deeper than the plan currently does

- **The fleet console.** The plan asserts it aggregates signals that already
  exist. Verify that: `/healthz` reports version, environment, `dryRun`,
  `durableStore`, worker liveness and `settingsVersion`; `core/monitoring.py`
  computes backlog, oldest pending, stranded leases and open failures;
  `/setup`'s environment-diff compares exactly one peer. Establish what is
  genuinely missing versus merely un-aggregated, and whether the console belongs
  here or in CRMBuilder — it needs signals from both sides.
- **De-Clevelanding.** Produce the actual inventory, don't estimate it. Four
  settings defaults in `core/config.py` and 18 frontend HTML files carrying the
  name in markup were measured on 2026-08-18 — re-measure rather than quoting,
  and enumerate what a per-chapter identity actually consists of (name, domains,
  logo, `tokens.css` overrides, `docs_site_url`, mailbox display names, Zoom
  host). Say which are settings, which are overrides, and which are markup edits.
- **The exit kit.** The plan names a Postgres export as mandatory because
  `record_comment`, the submission store with its Gmail thread anchors, authored
  analytics metrics and pages, and `app_setting` overrides exist nowhere else.
  Verify that list against the live schema and complete it — a missing table is
  a chapter's data lost at the worst possible moment.
- **The release train's mechanics.** How a tag is cut, how a chapter's app is
  pinned to it, how CRM config is promoted in the same motion, and what the
  emergency path skips. `deploy_on_push: true` on `main` is currently how all
  three apps deploy; the plan calls turning that off the single most consequential
  operational change, and it deserves the detail that implies.
- **What breaks first at N chapters.** The plan lists risks. Add the operational
  ones this codebase already knows about: one poller may run per shared mailbox
  (`OPS_MAILBOX` on two environments double-captures), Gmail sync and Drive
  reconciliation are per-deployment worker loops, and alert routing is per
  deployment — six chapters means six alert streams reaching one support team.

### How to work

- **Write to the plan file as you go.** The first session on this arc lost
  everything to a power cut because the reasoning lived only in the session.
  Append rulings and findings to `prds/multi-chapter-deployment-plan.md` the
  moment they land. Commit early — uncommitted work is the one category this
  project's salvage procedure cannot rescue (`OPEN-ITEMS.md` item 1).
- **Update the plan in place.** One document for this arc. Do not create a
  second plan, a summary, or a v2 file.
- **Verify before asserting.** Measure counts and check field names against the
  live code rather than repeating figures from this prompt or the plan. Where a
  claim needs a live CRM or a deployed environment to confirm, say it is
  unverified rather than implying it was checked.
- **Ask one question at a time, in prose.** Doug does not want stacked option
  menus or bulleted issue lists — a recommendation, the reasoning, and the
  single question that actually blocks you. Verify the premise of a question
  against the live system before putting it to him.
- **Do not touch the CRMBuilder repo.** It is governed by a requirement-first
  process; anything it needs goes through
  `prompts/crmbuilder-chapter-network-prompt-v0.1.md` and its own session.
- **Do not start building.** No app changes, no new modules, no feature flags.
  The output of this session is a plan good enough to build from, plus the
  decisions Doug still owes it.

### What done looks like

`prds/multi-chapter-deployment-plan.md` reads as something a small team could
execute: every phase with deliverables and acceptance criteria, a critical path,
an honest cost shape, the six proposals reduced to a decision list, and the six
open items designed. Anything deliberately left out is stated as left out, with
the reason.

If the session ends with Phase 1 rewritten around CRMBuilder and the decision
list in front of Doug, that is a good session — those two gate everything else.
