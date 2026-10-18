# Kickoff prompt — prospect marketing Phase 3: lists, review, calls

> **Done — history.** This kickoff was run on 10-18-26 (00:09–00:50):
> question 6 was put to Doug first and answered "a" (ruling 36 — callers are
> the campaign's teams, each acting as themself), then the rung question
> ("a", ruling 37, built as v0.260.2). Phase 3 was built as v0.261.0
> (`campaigns/review.py`, `calls.py`, `stale.py`, `reporting.py`, the Calls
> page, `analytics/campaigns.py`, 26 new tests, suite green), committed,
> not pushed. Doug's six-step pass is `OPEN-ITEMS.md` #51, step page
> https://claude.ai/artifact/D8atEqEdRaRBKh4mmxiPsj. The next kickoff is
> `prompts/prospect-marketing-phase-4-build-prompt-v0.1.md`.

**Written 10-17-26 02:22; revised 10-18-26 00:10 for a fresh Claude Code
session rooted in `cbm-client-intake`, to run tonight in parallel with the
end of the Phase 2 live pass.** A build session: the list import, the Review tab, the
call kind with its recording screen, the Declined and Stale side exits, and
the first two Analytics reads of the funnel. One flag inside
`CAMPAIGNS_ENABLED`: `CAMPAIGNS_CALLS`. No CRM change.

**The arc lives in `prds/prospect-marketing/`** — read its `README.md`
first, then `rulings.md` (binding, 1–35) and `build-plan.md` (v0.5).

Operating mode: DETAIL for the code.

---

## The gate — open, by Doug's decision (10-18-26 00:05)

Doug lifted the gate on the Phase 2 live pass: build Phase 3 now, while the
pass finishes in another session tomorrow (10-18-26). Where the pass stands:

- **Matched on crm-test 10-17-26:** sections A–E of the step page
  https://claude.ai/artifact/JLZyupBD4i6scAogws6sWD — a card through to
  delivery, two partners (ruling 30), a partner link plus a campaign link,
  ruling 27 — after two fixes the pass found: **v0.259.1** (the worker's
  `core/resumable.ResumableClient` lacked `metadata` and `list_related`, so
  every worker delivery dropped the campaign) and **ruling 35** (our entity
  and links labelled *Outreach Campaign* in the CRM, beside EspoCRM's native
  *Campaign*; `scripts/relabel_outreach_campaign.py`, crm-test done).
- **Owed tomorrow:** section F's registrations (the carry-through itself was
  seen working in the web log), G, H and I. crm-test's nightly reset at
  04:00 UTC removed every record of the pass.
- **Also live:** v0.260.0, the browser error reporter (`client-error` lines
  in the web log). One commit is unpushed: `d33ad50` (an unreadable report
  writes a `client-error-unread` line). Doug pushes.

**Working beside the pass session.** Parallel sessions share one git index
(`[[parallel-sessions-share-one-git-index]]`). Stage only your own files by
name, commit atomically, audit with `git show --stat`, and never `git add -u`
or `-A`. The pass session may land a fix in `campaigns/attribution.py`,
`core/resumable.py`, the five orchestrators or the runbook; if you must touch
one of those, check `git log -3 -- <file>` first and say so. A defect the pass
finds in Phase 2 code is fixed in the pass session, not here.

## The first thing in the session: question 6

Build plan § 9 question 6 is unanswered and this phase builds the screen it
concerns. **Put it to Doug before writing any code**, as a consequential
decision (the eight-part template), then stop and wait:

- **Who makes the calls?** Recommended (§ 3.4 drafts it): members of the
  teams named on the campaign (the BasePlus `teams` field), default the
  Marketing Admin Team; naming the Mentor Team on a campaign opens its call
  screen to mentors with no second gate. Cost: a mentor who calls needs read
  and edit on `COutreachTouch` and read on `CProspect` in the Mentor Role — a
  role change on every CRM, by the role script. The alternative is a fixed
  gate (Marketing Admin Team only), no role change, and mentors never call.

Record the answer as ruling 36 in `rulings.md`, dated, before building.

**Then the second question, also before any code** — raised on the Phase 2
pass and not yet ruled: the information request and registration doors
write `cFunnelStage = Warm Lead` on every matched Contact, including one
already typed Client, Partner, Sponsor or Mentor (seen on Pia Phase,
10-17-26). The build plan says a client's rung is never stored — reports
read it from the engagement. Recommended: those two doors skip the rung on a
Contact already holding a relationship type (one condition in
`campaigns/attribution.advance_rung`'s callers). Cost: a person who is both
a client and a fresh information requester gets no rung movement at all,
which is the plan's rule anyway. Put it as a consequential decision; record
the answer as ruling 37; build it first if ruled, with a test — it is Phase 2
code, so check `git log -3 -- forms/info_request forms/event_registration
campaigns/attribution.py` before touching it.

## The prompt

Read, in order:

1. This repo's `CLAUDE.md` — the Conventions and the **Campaign Management**
   section (the standing rules Phases 1 and 2 set, including who acts under
   which credential and the Phase 2 attribution rules).
2. `prds/prospect-marketing/build-plan.md` § 2.3 (the list import), § 3.4
   (the call kind), § 3.8 (the screens: Prospects, Review, Calls), § 1.2 (the
   side exits, `Declined`, `Stale`), § 6 items 2 and 3 (touches by campaign,
   entry rung per door), § 7 Phase 3 (the build list and the six-step live
   verification).
3. `campaigns/imports.py` (the state-filing import this one extends with
   `list_source`), `campaigns/postcard.py` (the selection-and-run shape the
   call kind mirrors: build the list, sign off, the worker's cycle — a call
   campaign has no vendor, its Planned touches are the call list),
   `campaigns/service.py` (`advance_stage`, `manual_moves`,
   `_link_or_escalate`), `campaigns/router.py` and `campaigns/frontend/` (the
   Prospects grid the Review tab pre-filters), `analytics/records.py` and
   `analytics/registry.py` (how a built-in page and metric are declared —
   the new Analytics page goes beside them).
4. `worker.py` (where the nightly jobs run — the Stale sweep is one) and
   `setup/` (`/setup` → Operations: a mutating job is dry-run → apply that
   exact plan).

Build what § 7 Phase 3 lists, each piece green before the next:

1. **The list import** (§ 2.3): the same file contract plus `list_source`
   (stored in `importBatch`); rows enter at `funnelStage=Unverified`,
   `entryStage=Unverified`, `entryDoor=List`; a row with an email or website
   promotes exactly as the state-filing import does (identity is separate
   from fit).
2. **The Review tab** (§ 3.8): the Prospects grid pre-filtered to
   Unverified, with *Qualify* (stamps `qualifiedBy` and `qualifiedAt`, moves
   to Qualified) and *Unqualified* (note required, the `Unqualified` side
   exit, reviewer stamped); *Do Not Contact* and *Not the same company* (the
   latter clears `alreadyKnownCompany` and the Already-known exit) as row
   actions on every prospect record; every action action-logged.
3. **The call kind** (§ 3.4): the selection rule (a phone held on the
   prospect record or on a Contact typed Prospect with `doNotCall` false and
   `phoneNumberIsOptedOut` false; rung in the chosen set; no side exit; not
   Declined anywhere); *Build the list* and *Sign off* as the postcard kind,
   no piece count and no vendor; the Calls grid — every Planned touch of
   every Running call campaign, filtered by question 6's rule — and the
   recording screen with the three outcomes (*No answer*: Done, and *Call
   again* plans a fresh row; *Interested*: Done and the record moves to Lead,
   advance-only; *Declined*: Done and the record leaves by the `Declined`
   exit), `callNotes` free text, `calledPhone` the snapshot, the warning
   above the list that an unrecorded call reads as never contacted. Dark
   behind `CAMPAIGNS_CALLS`.
4. **The nightly Stale sweep** in the worker, `PROSPECT_STALE_DAYS`
   (default per § 1.2), also runnable from `/setup` → Operations as dry-run
   → apply: a Qualified or Unverified record with no touch inside the window
   leaves by `Stale`; a record with a scan or a response inside it does not.
5. **The two Analytics reads** (§ 6 items 2 and 3) as built-in metrics on a
   new built-in page *Prospect marketing*: touches by campaign (planned,
   sent, delivered, returned, scanned, responded, converted, with
   `stageAtTouch`) and entry rung per door — every number from
   `campaigns/reporting.py` so the grids and the page agree; system metrics
   under the org-wide key.

Tests for every piece; the suite green; commit; do not push. Then write
Doug's live verification as a runbook page — the six steps of § 7 Phase 3 —
following the Step-by-Step Instructions standard in the global `CLAUDE.md`
(one action per done box, naming the application or window AND the tab in
every step, click-to-copy entries, a report-back line per section).

### Guardrails

- The names in the build plan are the names.
- `Unqualified` is a side exit, `Unverified` is a rung (ruling 29); never
  one word for both.
- A side exit is never written over another side exit without a ruling;
  *Not the same company* clears one, nothing else does.
- Nothing here needs a CRM change; if something seems to, stop and say so.
  Question 6's role change, if ruled, goes through
  `scripts/migrate_outreach_roles.py` (merge-only) and the handoff's § 4
  table, never a hand step.
- The applier's `--apply`, the role script's `--apply` and any mutating SSH
  are refused to Claude by the session classifier — Doug runs those with the
  `!` prefix; `scripts/prospect_crm_test.sh` is the one-word wrapper.
- **One session on this arc at a time.** Check
  `git log -3 -- prds/prospect-marketing campaigns forms` before writing;
  if another session touched them in the last hour, stop and say so.

### At the end of the session

State what is built, what is verified by tests only, and the runbook page's
address. Update `prds/prospect-marketing/README.md` *State*, `OPEN-ITEMS.md`
#51 and `CHANGELOG.md`; move this prompt to
`prds/prospect-marketing/history/prompts/` marked done; name the next
kickoff (Phase 4 — email and SMS campaigns, the funnel, the campaign
dashboard). Remind Doug of what the arc still owes outside its code:
production's CRM change at a Sunday 17:00 UTC slot (both plans, the receipt
option, the role script, the notes conversion, the tab list, the three
entities' layouts, the relabel script, the "Outreach Campaign" labels — `coutreach-entities-crm-handoff.md`
§ 7), Boston with its release, the sandbox seeder plus re-baseline, and
questions 2, 4 and 5 before the first real card.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing Phase 3 build |
| Version | v0.2 |
| Last Updated | 10-18-26 00:10 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.2 | 10-18-26 00:10 | Claude (Claude Code) | Gate opened by Doug to build in parallel with the end of the Phase 2 pass; the pass's state, the two fixes it found and the parallel-session rules recorded; the rung-on-a-client question added as the second question (ruling 37). |
| v0.1 | 10-17-26 02:22 | Claude (Claude Code) | Written at the close of the Phase 2 build session; gated on Doug's Phase 2 live pass; question 6 made the session's first step. |
