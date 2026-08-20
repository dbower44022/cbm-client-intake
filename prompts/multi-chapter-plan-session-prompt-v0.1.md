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

1. **Phase 1 is NOT yours — leave it alone.** It has its own session and its
   own prompt, `prompts/multi-chapter-phase1-reframe-prompt-v0.1.md`, because it
   depends on an unstarted requirements session in the CRMBuilder repo and needs
   a three-layer treatment this session should not improvise. Read that prompt so
   you know what Phase 1 will become — an interface contract, CRMBuilder as the
   preferred realization, and the `migrate_event_schema.py` generalization as
   plan-of-record until that answer lands — and write the *other* phases so they
   depend on the contract rather than on a named tool. If Phase 1 has already
   been rewritten when you start, treat what is in the plan as settled.
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
   **Then size the *run* cost, which the plan does not address at all.** Ruling 1
   is a *funded* central services organization and proposal 5 makes the fee
   labour-only, so the fee has to cover a steady-state support load nobody has
   estimated: per chapter per month, what does answering change requests, running
   the release train, watching N alert streams and onboarding actually consume?
   State the chapter count at which that breaks even and the count at which it
   breaks. Doug cannot rule on the fee model without this.
5. **Convert the six proposals into a decision list for Doug** — release cadence,
   crm-test as the network staging tenant, the change forum, preferring
   bring-your-own Workspace, labour-only fees, and the exit rehearsal. Each needs
   the consequence of each option stated tightly enough to decide from.
   **This is a written section of the plan, not an interactive menu** — the "one
   question at a time" rule below governs how you *talk* to Doug, not how the
   decision list is written. Write all six out in the document; ask about at most
   the one that blocks you.
6. **Design the six still-open items** to the depth the rest of the plan has: the
   change-request route, the onboarding runbook (both Workspace branches), the
   cost model, the de-Clevelanding workstream, the fleet console, and the
   emergency path through the release train.
7. **Name the cheapest thing that would falsify the architecture early.** Doug is
   being asked to commit to seven phases before a second chapter has said yes in
   writing — the plan does not name a single prospective chapter. So end the
   document with the smallest, soonest, cheapest test whose failure would change
   the plan rather than merely delay it, and say what each outcome implies.
   The load-bearing assumptions are the place to look: ruling 6 asks an
   independent 501(c)(3) to accept that it holds **no** EspoCRM admin account on
   its own CRM, and ruling 4 tells it that a field it wants is core for everyone
   or does not exist. If no chapter will accept those, the architecture is not
   delayed, it is wrong — and finding that out costs one conversation, not a
   phase. Prefer a test that can be run before Phase 0 ships. If you conclude the
   cheapest real test is still expensive, say that plainly instead of inventing a
   cheap one.

### Where to go deeper than the plan currently does

- **The fleet console.** The plan asserts it aggregates signals that already
  exist. Verify that: `/healthz` reports version, environment, `dryRun`,
  `durableStore`, worker liveness and `settingsVersion`; `core/monitoring.py`
  computes backlog, oldest pending, stranded leases and open failures;
  `/setup`'s environment-diff compares exactly one peer. Establish what is
  genuinely missing versus merely un-aggregated, and whether the console belongs
  here or in CRMBuilder — it needs signals from both sides.
  Two things to reach specifically. **Missing instrumentation**: `/healthz`
  reports the app version and no release tag and no CRM-configuration version
  (verified 2026-08-20 against prod), and the release train needs both — so that
  stamp is one design shared with Phases 1, 2 and 5, not three. **The trust
  model, which is the question that actually decides where the console lives**:
  `setup/snapshot.py` is a bilateral, shared-token, pull design built for two
  instances. Aggregating N deployments inside N *chapter-owned* DO accounts asks
  who holds the tokens, whether instances push or the console pulls, what a
  chapter can revoke, and whether one chapter's view can ever contain a peer's
  numbers. Answer that before designing the panel.
- **De-Clevelanding.** Produce the actual inventory, don't estimate it, and
  **measure it yourself — this prompt gives you no counts on purpose.** The
  figures in the plan are already low: it names four Cleveland-bearing settings
  defaults in `core/config.py` and there are more than four. **Search wider than
  "Cleveland"** — `cbmentors` and `CBM` appear across HTML, JS, CSS and Python,
  and are just as Cleveland-specific.
  **Then split the results in two, because this is where the workstream can do
  real damage.** Much of the `CBM` hit-count is the shared JS *namespace* —
  `CBMBusy`, `CBMDateTime`, `CBMRichText`, `CBMConversation`, `CBMEvents` — which
  is a code identifier, not branding, and renaming it breaks every page in the
  suite. Separate **brand-as-content** (renameable) from **brand-as-identifier**
  (must not move), and say so loudly enough that someone working the list
  mechanically cannot miss it.
  Then enumerate what a per-chapter identity actually consists of (name, domains,
  logo, `tokens.css` overrides, `docs_site_url`, mailbox display names, Zoom
  host). Say which are settings, which are overrides, and which are markup edits.
- **The exit kit.** The plan names a Postgres export as mandatory because
  `record_comment`, the submission store with its Gmail thread anchors, authored
  analytics metrics and pages, and `app_setting` overrides exist nowhere else.
  That list is materially incomplete. **Enumerate every table the migrations
  create and classify all of them** — exported, reconstructible from the CRM or
  from Google, or deliberately discarded — rather than adding two and stopping.
  The omission that matters most is the **Drive documents index**: the files
  survive a Drive transfer and the mapping from CRM record to file does not, so
  "you keep your documents" is false in exactly the way that only becomes
  visible after the wind-down. The Gmail sync state, the attachment ledger and
  the submission collaboration history are in the same position. A missing table
  is a chapter's data lost at the worst possible moment.
- **The release train's mechanics.** How a tag is cut, how a chapter's app is
  pinned to it, how CRM config is promoted in the same motion, and what the
  emergency path skips. `deploy_on_push: true` on `main` is currently how all
  three apps deploy; the plan calls turning that off the single most consequential
  operational change, and it deserves the detail that implies.
  **State plainly what Phase 2 does to the developer's own week**, because it
  lands on CBM before there is a second chapter: commit-push-deployed-everywhere
  becomes commit, push, staging, soak, cut a tag, promote. That is the change
  most likely to be quietly abandoned, and it will be abandoned by the one person
  who can bypass it — the same failure shape as the change-request route being
  slow. Name it as a risk in its own right.
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
  project's salvage procedure cannot rescue (`OPEN-ITEMS.md`, the Dropbox/`.git`
  item). **Cite `OPEN-ITEMS.md` entries by title, never by number** — the
  numbering has duplicates (two 19d, two 19f, two 22s), so a bare number points
  at two different things.
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

**If the session ends with the decision list in front of Doug and nothing else,
that is a good session.** It is the half that is entirely within his gift, it
unblocks the rest, and unlike Phase 1 it depends on no other repo.
