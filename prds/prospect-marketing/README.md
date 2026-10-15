# Prospect marketing and Campaign Management

Last Updated: 10-14-26 22:44 · Revision 1.0 — change log at the end.

**Read this first if you are working on prospects or campaigns.** This
directory is the whole arc: the rulings, the build plan, and the record of
how they were reached. It is deliberately separate from the application's
other feature arcs, which each live in one plan document under `prds/`;
this one outgrew a single file on 10-14-26, when three sessions in one day
left three documents that disagreed. The repository's `CLAUDE.md` is the
anchor for *the application*; this file is the anchor for *this arc*.

## What the arc is

A chapter receives a filtered list of new businesses every month (an outside
process does the filtering), mails each one a postcard carrying a QR code,
and reads the scan, the landing page and the standard intake forms as the
business climbs a funnel from prospect to client. Around that sit the
Campaign Management application (marketing users create campaigns of five
kinds and the links that carry a campaign into the public forms), two import
doors, a call screen, an SMS consent tick, and the reporting that reads the
funnel. **Nothing of it is built. No CRM is changed. No vendor account
exists.**

## The documents, and what each one binds

| File | What it is | How it changes |
|---|---|---|
| `rulings.md` | **The binding record.** Rulings 1–27 and requirements CM-1 to CM-11, verbatim, with the ladder and the walk tables | Append only. A new decision is ruling 28 onward, dated |
| `build-plan.md` | **The one plan**, v0.2: the record model in Entity Manager vocabulary, the doors, the campaign engine, the landing page, conversion, reporting, five phases with their CRM handoffs and verification scripts, and § 9, the open questions | Revised in place with a change-log row. Never forked, never a second plan document |
| `history/prospect-marketing-plan.md` | The process plan, v0.6: the 2026-08-11 elicitation, the September funnel discussions, the 2026-10-13/14 walk and the 10-14-26 definition session, with every proposal, working position and strawman labelled | Frozen on 10-14-26. Read it for *why*; cite `rulings.md` for *what* |
| `history/prompts/` | The three kickoff prompts that produced the above, each marked done | Frozen |
| `history/prospect-marketing-funnel-2026-09-02.png` | Doug's funnel diagram, which the ladder table transcribes | Frozen |
| `prompts/prospect-marketing-crm-handoff-prompt-v0.1.md` (repository root) | **The live kickoff**: the next session | Lives with the other kickoff prompts until it is spent, then moves here |

Where things will land when they are written, by the house conventions:
the CRM handoffs at the repository root (`contact-sms-opt-in-crm-handoff.md`,
`coutreach-entities-crm-handoff.md`), their plan files under
`scripts/plans/`, the role script under `scripts/`, and the code in a
`campaigns/` package and a `forms/prospect_response/` form.

## State, as of 10-14-26 22:44

- **Settled:** the process end to end (rulings 1–27) and the Campaign
  Management application (CM-1 to CM-11). None of it is reopened by any
  session.
- **Written:** build plan v0.3 — v0.2 (10-14-26 22:09) revised against
  CM-1 to CM-11, then v0.3 (22:43) for Doug's answers to the four
  shape-changing questions (rulings 28–31): custom entities, `Unverified`,
  **multiple referring partners on an engagement** (against the
  recommendation — a many-to-many `referringPartners`, seventeen links in
  all), links in the application database. Eight questions stay open; none
  changes the CRM.
- **Owed, in this order:**
  1. ~~Doug answers the four questions that change the CRM's shape~~ —
     **done 10-14-26 22:41**, rulings 28–31.
  2. **The CRM handoff session**, from the live kickoff prompt (v0.1.4, the
     gate is open): two handoffs, two plan files, one role script, dry-run
     fingerprints from crm-test. No apply. **This is the next session.**
  3. **Doug applies on crm-test** from `prds/chapter-network/crm-update-runbook.md`;
     the shape is verified in `GET /Metadata`, the grants as the org-wide
     key and as a real non-admin; soak.
  4. **The Phase 1 build session** (its kickoff is written at the end of
     step 2): one real card, one real scan, dark behind `CAMPAIGNS_ENABLED`.
  5. **Before the first real card:** questions 2 (what the outside filter
     delivers), 4 (the mail vendor — Doug opens the account) and 5 (the card
     itself).
  6. **Production at the Sunday 17:00 UTC slot, Boston with its release**,
     and a seeder plus a sandbox re-baseline, because both handoffs add
     tables the nightly reset truncates.
- **Open and not blocking:** questions 6, 7, 10, 11 and 12.

## Rules for working in this directory

- **One session writes here at a time.** On 10-14-26 three sessions worked
  the arc in one afternoon and evening; the build plan was revised in one
  while another was gated on the revision and a third rewrote the pointers.
  Parallel sessions share one git index. Before starting a session on this
  arc, check `git log -3 -- prds/prospect-marketing` and the memory note
  `prospect-marketing-rulings`, and close the other session first.
- **`rulings.md` holds Doug's words and nothing else.** A proposal, a
  working position or a strawman goes in the build plan, labelled, or in
  the session's own record under `history/`. A question answered in
  conversation is written to `rulings.md` in the same session, dated.
- **The build plan is the only plan.** A new requirement revises it (a new
  version, a change-log row, the sections named). It is never answered with
  a second plan document or a parallel section elsewhere.
- **The house rules apply to every screen in the arc** — build plan § 10
  lists them, and `CLAUDE.md` *Conventions* is their source.
- **Terminology.** A **rung** is a position on the funnel ladder; a **side
  exit** is a reason a record left it; a **touch** is one attempt to reach a
  business or person; a **door** is any place a record enters; **promotion**
  is the creation of a Company or Contact from a prospect record (ruling
  21); **conversion** is a relationship beginning through a standard intake
  form (ruling 22); a **campaign** is ours and a **notice** is a Constant
  Contact send (CM-11).

## Related

`prds/mailing-list-and-event-sponsorship-plan.md` (the notice vocabulary,
the Constant Contact push, the unbuilt Phase D whose button reads *Link a
notice*); `prds/chapter-network/crm-update-runbook.md` (how every CRM
change in the arc is applied); `forms/client_intake/orchestrator.py` (the
partner-link precedent for the campaign id); `core/crm_upsert.py` (the
null-fill rule, the website key, the one sanctioned relabel);
`research/registry-enrichment/enrichment-findings.md` (the filing data the
import contract starts from).

---

## Revision control

| Field | Value |
|---|---|
| Document | Prospect marketing — directory README |
| Version | 1.1 |
| Last Updated | 10-14-26 22:44 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-14-26 22:44 | Claude (Claude Code) | State: the four shape-changing questions answered (rulings 28–31, build plan v0.3); the next session is the CRM handoff. |
| 1.0 | 10-14-26 22:26 | Claude (Claude Code) | Created. Doug's ruling the same evening: consolidate the arc's three sessions' output into one directory on the chapter-network pattern. The process plan, the build plan, the funnel diagram and the three spent kickoff prompts moved here; `rulings.md` extracted; the live kickoff stays in `prompts/`. |
