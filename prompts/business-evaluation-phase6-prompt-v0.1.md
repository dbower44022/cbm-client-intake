# Kickoff prompt — Business Evaluation, phase 6: the partner and funder offering

Last Updated: 11-16-26 11:59 · Revision 0.3 — see change log at the end.

> **Superseded, do not run (11-16-26).** Plan revision 0.13 moved the partner
> and funder offering to **phase 10** and changed it: rulings BE34 to BE36
> (the link skips "more details?", co-branding with the partner's logo, the
> recommendation score in the roll-up). This prompt is rewritten as phase
> 10's at the close of phase 9, from what phases 6 to 9 built. The text
> below is kept as approved on 11-16-26, for that rewrite.

**Approved by Doug 11-16-26.** Written at the close of phase 5
(v0.338.0, checked by Doug on the Business Mentors Association's system
11-16-26). Start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, tell it to read this file, and tell it
to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** Before
choosing a version number or an Alembic migration number, read `git log`,
the working tree's `pyproject.toml` and `alembic/versions/`, and take the
next free one; never take numbers from this prompt. Commit only this
phase's lines, staged and committed in one step, then audit with
`git show --stat`.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds ruling **BE21** and plan
  § 6's phase 6 row.
- `evaluation/CLAUDE.md`: what phases 1 to 5 built, and their rules.
- `sessions/CLAUDE.md`: Partner and Funder Management (the partner's intake
  link on its Details tab, the Referred Clients tab, the Events tab's
  roll-up, which is the nearest pattern for counts shown to a partner's
  managers), and the Evaluations tab.
- The root `CLAUDE.md`, "The five public intake forms": a partner's intake
  link (`client-intake/?partner=<CPartnerProfile id>`, validate-or-drop,
  `referring_partner_id`) and `campaigns/attribution.py`.
- `OPEN-ITEMS.md` #83: what is owed.
- `forms/client_intake/` (schema, orchestrator, frontend), and
  `evaluation/sending.py` (rounds, statuses) and `evaluation/report.py`
  (the scores).

## Scope of this phase

Build the partner and funder offering, dark behind `BUSINESS_EVALUATION`:

1. **The `offer=evaluation` referral** (BE21):
   `client-intake/?partner=<id>&offer=evaluation`. The member becomes a
   client through normal intake, credited to the partner, and nothing else
   about intake changes. An unknown `offer` value is dropped, never fatal.
2. **The engagement flag**: the engagement shows that an evaluation was
   requested, so its mentor knows to offer it. Where it is stored and where
   it shows are decided at stopping point (a). A CRM change goes through a
   plan in `crm-plans/` with a handoff file.
3. **The anonymized roll-up**: scores by evaluation area for the clients a
   partner (or funder) referred, shown only for a group of five or more
   clients, never naming a client or showing one client's scores.
4. **Every staff action recorded** through `core/action_log.py`, if this
   phase adds any.
5. **Tests**: the flag set from the link and dropped for a bad value, the
   roll-up's group-of-five rule (four shows nothing), no client name or
   single score in the roll-up, the switch off.
6. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building, put to Doug, with a recommendation
for each:

- **How a funder offers it.** BE21 names partners and funders, but the
  intake link credits a `CPartnerProfile` only. The choices: a funder's own
  link (a new attribution path), or funders offer through a partner record.
- **The engagement flag**: a field on the engagement or on the client
  profile; whether intake also creates the round automatically (Sent, no
  areas chosen) or only flags it; where the mentor sees it.
- **The roll-up's content**, the plan's stopping point for this phase:
  - which scores count (Approved and Reviewed with Client reports only, or
    drafts too);
  - which round counts when a client has several;
  - the measure (average per rubric dimension, or the spread across
    1 to 5);
  - where it shows (a tab on the partner and funder record, Analytics, or
    both);
  - whether the group of five counts clients per area or overall.
- Whether the roll-up is computed under the org-wide key after the user's own
  read gates the tab (the Events tab precedent), since the Partner Manager
  and Sponsor Manager roles cannot read engagements.

Show Doug a **sample roll-up** built from made-up scores at this stop.

After Doug's go-ahead, build steps 1 to 6.

**Stopping point (b)**: Doug runs a runbook on **the Business Mentors
Association's system** (his choice for phase 5, 11-15-26; not crm-test).
He submits a client intake through a partner's `&offer=evaluation` link
and sees the flag on the new engagement as its mentor. As the partner's
manager, he sees the roll-up hidden below five clients and shown at five or
more. The made-up scores can come from `scripts/evaluation_sample_reports.py
--env-file ~/.config/cbm-bma/bma.env` on five engagements, or from a seeding
script this phase writes. CRM changes go to the Association with
`scripts/evaluation_bma.sh` extended, or a script like it. Lessons from
phase 5's runbook:

- A plan's fingerprint covers the work still to do, not the file. Take it
  from a dry run made after every plan it depends on is applied.
- While the Integrations tab is on, a setting tagged with an integration is
  on that integration's sub-tab, not the Settings tab.
- Saving a new session asks "Create a Calendar Invite". The answer is
  Save without invite.

Close the phase only after Doug's check.

## Not in this phase

The pilot review and the other four areas (phase 7); prompts and rubrics
editable in System Settings (plan § 7 question 6, planned at phase 7).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-16-26 01:10 | Claude (Claude Code) | Drafted at the close of phase 5, from the orchestrator and what phases 1 to 5 built. |
| 0.2 | 11-16-26 01:22 | Claude (Claude Code) | Approved by Doug. |
| 0.3 | 11-16-26 11:59 | Claude (Claude Code) | Superseded by plan revision 0.13: the partner offering is phase 10, to be rewritten at the close of phase 9. Body unchanged. |
