# Open items to address

Running list of known issues and pending decisions that don't belong to any
single feature doc. Add new items at the top of their section with the date
found; move resolved items to the bottom with the resolution date.

## Needs a fix / decision

59. **The postcard landing page misreads a printed address whose first line
    is not the street, and saves the misreading** (found in the D1 live
    pass, 10-25-26). `campaigns/service.parse_address_text` takes line 1 as
    the street and line 2 as the city. The sandbox's demo touches print
    the business name first, so Tremont Coffee Roasters' page showed street
    "Tremont Coffee Roasters" and city "2368 W 11th St", and the response —
    though nothing was edited — wrote those boxes onto the lead as a
    correction (state and ZIP emptied). Cards the application prints
    (`postcard.address_text`) start with the street, but a street with a
    second line (a suite) shifts the same way. Fix owed: find the
    "City, ST ZIP" line instead of counting lines, and write a correction
    only for a box the person changed. crm-test's nightly reset restores
    the lead. Not fixed on 10-25-26 because another session had uncommitted
    edits in `campaigns/service.py`.

58. **Lead enrichment — production, Boston and the real-model test owed**
    (2026-10-25, moved here from the root `CLAUDE.md` status window).
    Phase 1, the fit score (v0.269.0, `ENRICHMENT_FREE_PASS` /
    `ENRICHMENT_WEB_CHECKS`, live-passed on crm-test 10-21-26) and phase 2,
    the AI research pass (v0.274.0, `ENRICHMENT_AI`, findings as
    `CEnrichmentFinding`, crm-test applied 10-22-26) are pushed and dark.
    Owed: phase 2's staff test on crm-test finished and recorded — the real
    model DID run on 10-22-26 (Doug on crm-test: the Great Lakes Brewing
    Company lead, which found the `www.` duplicate fixed in v0.277.1 — still
    owed: press Accept on that lead's website finding on crm-test; it should
    turn Accepted and leave the website unchanged), but
    which sections of the step page
    https://claude.ai/artifact/JePeP4H6XSGY4PnXsUVKgV were completed is not
    recorded (corrected 10-26-26 11:56); both phases' CRM fields on production at a Sunday slot and on
    Boston with its release; the list button when lists go on. Campaign
    lists L2 (v0.271.0, live-passed 10-21-26) likewise owes production and
    Boston with the arc's slot and the close-date Read-only finding (#51).

57. **Marketing Management redesign — nine Drafts owed, then the build**
    (2026-10-23). Doug ruled the whole redesign 10-22/23-26 (rulings
    79–116, `prds/prospect-marketing/rulings.md` v1.47). The build is
    `prds/prospect-marketing/build-plan.md` § 7e: ten steps (M1 one page
    with six tabs; M2 the qualification ladder and Leads tab; M3 Review as
    a research queue; M4 the import tool; M5 personal outreach; M6 lists;
    M7 Constant Contact per list; M8 lists-only campaigns and the campaign
    page; M9 the send report and Recipients; M10 Promote this event and
    Calls). The nine Drafts in § 7e.12 ruled 10-23-26 (rulings 117–125).
    M1 built (v0.279.0/.1) and live-passed on crm-test 10-24-26 14:46. The
    one CRM handoff (`marketing-redesign-crm-handoff.md`, plan fingerprint
    `6bb03652454a`) written 10-24-26 and **applied on crm-test 10-25-26**
    by Doug; its § 5 proof passed 02:12 (shape, org-wide key write-and-
    clear, role read-back, conformance unchanged). **M2 built as v0.284.0
    (10-25-26)**: the ladder (`campaigns/ladder.py`), the Leads tab's
    counts, columns and *Assign to*, the lead's page at
    `/campaigns/lead/{id}`, *New code* on the lead's and the Contact's
    pages (ruling 126); dark behind `LEAD_LADDER`. **Live-passed on
    crm-test 10-25-26 12:00** by Doug (23 steps, step page
    https://claude.ai/artifact/EE5rBgsV4LxeiNTWqx4BVN); the double save on
    Enter found at step 14 is fixed in v0.284.1. `LEAD_LADDER` is on at
    crm-test's /setup; step 21's Convert re-run and read back 12:08 (all
    23 steps hold). **M3 built as v0.285.0 (10-25-26)**: Review as the
    research queue — *Judge Unqualified leads* and *Find contacts for
    Identified leads*, the contacts row's write with `seenLevel`, AI
    research on every row filling the boxes from the lead's findings,
    ruling 121 in `enrichment.runs.decide`; rides `LEAD_LADDER`. Checked
    against the stub harness and by tests; pushed 10-25-26 13:14.
    **Live-passed on crm-test 10-25-26 18:35** by Doug as Mark Marketing
    (step pages https://claude.ai/artifact/CoUeWPYhsjV8pgf7GpA391 and
    https://claude.ai/artifact/FAL7ijgrPFYaxGHuLVcXej; four *Lead Contact
    Found* rows read back, counts 3 · 4 · 4 · 1). Found and fixed on the
    way: the row's link opened the old pop-up (v0.285.1, pushed 13:30).
    Not exercised live: the row's 409 refusal of a lead moved since
    (unit-tested). **M4 plan approved 10-25-26 18:44** (four stops in one
    session; ruling 127: Undo deletes under the org-wide key, the API role
    gains delete on `CProspect` — handoff § 4's third cell). **M4 built as
    v0.286.0 (10-25-26)**: templates, Excel, recognition and the four
    fixes, the preview as a worker job, fills, the level per row, Undo;
    dark behind `IMPORT_TEMPLATES`; migration 0035; `openpyxl`. Checked
    against the stub harness and by 31 tests. **Live pass started
    10-25-26 ~19:50 Eastern** (sections 1–7 passed: the role cell, the
    push of v0.286.0, the switch, the demo template, both rehearsal
    imports, the fills read back); section 8 found Undo deleting the two
    filled leads (the fills were inside the five-minute window) and the
    *Import Undone* row refused by the CRM (hung on a deleted lead) —
    both fixed in **v0.286.1**. **Round two run by Claude 10-25-26
    20:12–20:49** in a tab Doug signed in as Mark Marketing (results page
    https://claude.ai/artifact/XpyHhSrvfQBuat1R7J4UKK): two more defects
    found and fixed on the way — a deleted lead's stale ledger rows made a
    re-import read it as a repeat row (v0.286.2) and then skip it at the
    apply (v0.286.3) — then **sections 10–14 passed on v0.286.3** exactly as
    the step page expects (Undo: "2 deleted, 2 left — filled by a later
    import"; the history row on a surviving lead). v0.286.1–v0.286.3 pushed
    and live on both deployments (the tool is off on production).
    **v0.286.4** (an ignored column no longer reads as a new column) is
    committed, not pushed. **Found and fixed**: the apply had no lock — two
    presses of Confirm for one batch within a second created every row
    twice; v0.287.0 adds the batch write lease (migration 0036), the second
    press answers 409 naming who holds it. Also owed: the sandbox
    carries two rehearsal leads (Parkside Dental Lab, Westown Upholstery)
    and a second template until tonight's reset. **Owed, in order**:
    (1) ~~the role cell~~ done 10-25-26 by Doug; (2) ~~the push~~ done;
    (3) ~~the live pass~~ done (step page
    https://claude.ai/artifact/5bnDamVEDRKpHYFVaZkvbG rev 1.1, 74 steps;
    the demo template restored through the Operations job in section 3);
    (4) ~~Doug pushes v0.286.4~~ done 22:47; (5) ~~the apply lease~~ built
    as v0.287.0 (migration 0036), pushed 23:14. **M5 plan approved
    10-25-26 23:17** (four stops in one session; ruling 128: the full
    composer, shared); run it from `prompts/m5-personal-outreach-kickoff.md`
    in a fresh session. **M5 built as v0.288.0 (10-26-26)**, all four
    stops in one session: the shared composer (`frontend/shared/compose.js`,
    the session tools switched to it), Email and Log a call on the lead's
    page, the sync's lead source and the Replied flag, Conversations and
    the Mine chip; dark behind `LEAD_OUTREACH`; new setting
    `CHAPTER_POSTAL_ADDRESS`; no migration. Checked against the stub
    harness and by 3,030 tests. **Owed, in order**: (1) ~~Doug pushes
    v0.288.0~~ pushed 10-26-26 00:16, live on crm-test; (2) at crm-test's /setup, switch on *Personal outreach to
    leads* and fill in *Chapter postal address*; (3) the live pass (step
    page https://claude.ai/artifact/X7zFhDzMThqXBUWaGJX9GZ rev 1.0, 28 steps) — Mark Marketing has no mentor
    profile and his user address is `mark.marketing@cbmentors.org`, so
    ruling 120 resolves him; the pass stands or falls on whether the Gmail
    delegation can read that mailbox (a sandbox login may be no real
    Workspace mailbox — if not, run the pass as a user who has one, or give
    Mark a mentor profile with a real `cbmEmail`); the only lead assigned
    to him, Marigold Pet Grooming, has no email yet, so the tester adds one
    they control first; (4) the reply test: answer from the lead's address
    and watch the sync attach it within one pass. **M6 built as v0.289.0
    (10-26-26)**, all four stops in one session: lists described by
    Include and Leave out (rulings 90–94, 98) — a dynamic list is a search,
    a static list is people added by hand, Exclude onto a static exclusion
    list, the kind fixed, Copy, the per-channel counts, *Brought in by*,
    *Used by*; rides `CAMPAIGN_LISTS`; **migration 0037** (converts the
    crm-test test lists, drops `audience_list_entry`). Checked against the
    real app over the test fakes, the migration against a local Postgres,
    and by 3,040+ tests. Pushed 10-26-26 09:19, live on both deployments
    09:22. **Live-passed on crm-test 10-26-26 ~11:45** by Doug (step page
    https://claude.ai/artifact/CyUnHZcBtjB79d3VkJozv1, 28 steps as Mark
    Marketing); read back: the November postcard sends to *Leads with a
    phone*, one Planned card (Gordon Square Florist). **Owed:** (1) **list
    actions write no action-log row** — found on the read-back: a list has
    no CRM record, `core/action_log.log_action` sends an empty
    `recordType`/`recordId`, and the CRM refuses the row (HTTP 400, `field:
    record, type: pattern`; eight refusals in crm-test's web log during
    the pass). Since v0.270.0. Fix: leave the record reference out when
    there is none — **fixed in v0.289.1 (10-26-26 11:56, not pushed)**, a record-less
    row proven to store on crm-test; (2)
    decide whether `qualificationLevel` and `phone` join
    `audience.DEFAULT_FIELDS` (M7's prompt treats it as routine: yes) —
    **done in v0.290.0**. **M7 built as v0.290.0 (10-26-26)**, all four
    stops in one session: a list's copy in Constant Contact (*Keep a copy*,
    the status, *Sync now*, rename carried, one worker pass for every list)
    and the email campaign that sends to it (a list required, no touches at
    build, sign-off syncs the copy, *Pick the email*), the lead code written
    to the vendor field `cbm_lead_code` by every push, the paste address on
    the Links tab. Dark behind **`CAMPAIGN_LIST_SYNC`**; **migration 0038**.
    Pushed 10-26-26. **Live-passed on crm-test 10-27-26 12:22**, run by
    Claude in a tab Doug signed in as Mark Marketing (step page
    https://claude.ai/artifact/3YmoAaiHHAi2XFcJYAfK47): one real email
    from Constant Contact to doug@dougbower.com, the delivered link opened
    `…/info-request/?campaign=…&link=s65n7qrq&lead=b862ryw9ur5q`, the pick
    moved the campaign to Running. Four inferred vendor shapes confirmed,
    the list rename not exercised (build plan § 7e.12 Draft 8). **Found and
    fixed as v0.290.1** (pushed 10-27-26 ~12:00): every web request to
    Constant Contact built a new connection store and database pool, never
    closed — the pick answered 500 (`TooManyConnectionsError`). Smaller
    findings from the pass: (a) the form opened with the name and email
    empty, which is by design until D2 (§ 7d.6) — the step page wrongly
    promised it filled; (b) the build notice says "1 members"; (c) crm-test's
    `Contact.cSuffix` enum offers only "Jr" with no blank, so every Contact
    made on the CRM screen is stamped "Jr" and the CRM refuses to clear it
    (a CRM fix, not ours); (d) Constant Contact names a pasted-HTML email
    itself ("Live Send Test Email <date>"), and that name is what *Pick the
    email* shows.
    **M8 built as v0.291.0 (10-27-26)**, all four stops in one session
    (plan approved by Doug 10-27-26 13:30: Decision 2 a built-in recipe for
    *Dormant clients*, Decision 3 the layout question below): every
    campaign sends to a list, five ready-made lists (migration 0039), the
    stage strip, the *Audience and content* tab, ruling 101's grid and the
    short + New campaign. Dark behind **`CAMPAIGN_LISTS_ONLY`**. Committed,
    **not pushed**; live pass owed on crm-test (step page
    https://claude.ai/artifact/N1S4U7qvjYUZk2v3Y56uqQ, run by Claude in a tab Doug signs in as Mark Marketing). Production's count of
    rule-built campaigns in flight was not read (its credentials live only
    in the container); the build gives any such campaign its kind's
    ready-made list either way.
    Next: the M8 live pass, then M9 (the send report and the Recipients
    tab). Still owed: the handoff on production at the arc's slot and on
    Boston with its release (now with the third role cell). **The layout
    question in the handoff's § 7 is ruled** (Doug, 10-27-26, as
    recommended): *Level*, *Referred by* and *Assigned User* stay off the
    CRM's own lead layout; the application's lead page is the only place
    they show.

53. **Attendee linking escalation — live pass owed** (v0.258.6, 2026-10-15).
    A mentor whose Mentor Role reads/edits `CSession` at "own" could not
    attach an attendee assigned to someone else: EspoCRM checks edit on
    BOTH sides of a relate, the `sessionAttendees` link 403'd with
    `noAccessToForeignRecord`, and the save reported "1 attendee change(s)
    could not be applied" (Greg Malkin, production 2026-10-15, the Betsy
    Nero intake session). `_sync_attendees` and the create-path relate loop
    now route through `_link_or_escalate`, the same foreign-record
    escalation co-mentor linking uses. **Verified by tests only.** The live
    check is a real non-admin mentor (not an admin — admins bypass ACL and
    prove nothing) attaching an attendee assigned to someone else and
    confirming the save is clean with no attendee warning. No test and no
    stub harness exercises the admin fallback against a live CRM.

54. **Prospect marketing — the lead model (rulings 41–50), CRM half on
    crm-test DONE 10-19-26; code rework owed** (found 10-18-26). Handoff
    `coutreach-lead-model-crm-handoff.md`: the additive plan
    (`scripts/plans/coutreach-lead-model.json`, fingerprint `6e228dbb7d33`)
    and the Outreach Lead labels applied by Doug 10-19-26, read back as the
    admin and the org-wide key, opened as Mark Marketing (non-admin). Owed, in
    order: the code rework (build plan § 7a.5 step 2, kickoff
    `prompts/kickoff-lead-model-code-rework.md`) with the value move and the
    layouts; the stage steps of the Phase 1–4 passes re-run on crm-test;
    production and Boston at their slots (plan, labels, value move — count
    production's leads by the move's dry run first, ruling 45); then Doug's
    ruling on the proposed removals (handoff § 6).

51. **Prospect marketing — the lead model BUILT, LIVE (dark) and
    **Campaign lists L1 (v0.270.0, build plan § 7c, rulings 58–68):
    LIVE-PASSED on crm-test 10-21-26 15:36** by Doug as Mark Marketing from
    https://claude.ai/artifact/2jDCeJN96LR2cHvA2Mddro (rev 1.1): static list
    14 → 9 → 8, a hand take-out kept through Run again, the postcard build
    reaching Gordon Square Florist and Detroit Shoreway Signs (4 carded, 1
    exit skipped); the dynamic list 29, Pavel Novak always excluded → 28,
    the email build reaching Dana Okoro and Walter Kemp — Walter at his
    chapter address, read back by Claude. Lead `industry` applied on
    crm-test. One finding, fixed locally and unpushed: the saved recipe's
    problems box stayed up while a new list was edited. `CAMPAIGN_LISTS` is
    ON on crm-test (override). **L2 built as v0.271.0 (10-21-26 16:01), not pushed**
    (clients, partners, funders, links, lists of lists, imports, Include
    every contact, funder status in Funder Management). **L2 LIVE-PASSED on
    crm-test 10-21-26 22:30** by Doug (Sally Sponsor, then Mark Marketing) from
    https://claude.ai/artifact/BcETZsL5hFi3h9Bpm3wNUd (rev 1.3): funder
    status set on the Details tab and shown in the grid; "Do not market"
    removed from "Partners and funders" (1 → 3 → 2); a list including
    itself refused; Completed clients started over a year ago plus a file
    (1 matched, 1 counted unmatched); the email build reaching 2, then 3 with
    Include every contact, then 1 from the clients list (Rosa Medina skipped,
    no consent), read back from the CRM. `funderStatus` applied on crm-test.
    **Finding: `CEngagement.closeDate` is Read-only in crm-test's CRM**, so
    every API write to it is dropped and no engagement there has a close
    date — "closed more than N days ago" can never match, nor can the email
    kind's ruling-25 dormant-client rule. Production not yet checked; the
    fix — **ruling 70 (option A), built as v0.273.0 (10-21-26 22:48)**: clear
    Read-only (`cengagement-close-date-crm-handoff.md`, crm-test by
    `scripts/prospect_crm_test.sh closedate`, Doug runs it; production at the
    slot; Boston) and stamp the date on Completed / Inactive / Abandoned.
    Production read 10-21-26: Read-only too, no formula, 0 of 7 Completed
    dated. Pushed (live on both 00:29); **crm-test's Read-only cleared 10-22-26 00:30**
    by Doug (verified). **Live-checked 10-22-26 00:37** by Doug as Joe Mentor
    (Nightjar Studios → Completed from the Overview badge; Close date stamped,
    read back). Owed: production and Boston at their slots; the backfill
    question. v0.272.0 (the status picker on the partner and
    funder Overview) pushed and checked live on crm-test 10-21-26 22:36 by Doug as
    Sally Sponsor (Harrowgate Family Trust → Lapsed, read back). Owed also: production and Boston with the arc's eventual slot.
    LIVE-PASSED on crm-test (v0.265.0–3, 10-19-26; rulings 41–54).**
    **Production DEFERRED by Doug 10-20-26 15:06: "defer production until
    we finish testing new campaign functionality"** — no Sunday slot is
    planned until he says the testing is finished. The
    pass ran 23:44 from https://claude.ai/artifact/DPSsyZMYPhvHQRUnL696Rk
    (rev 1.5), every section matched, and the three defects it found are
    fixed. **Production waits until lead and campaign development is
    finished** (Doug, 10-20-26 14:36, "B" — one slot for everything). Known cost
    meanwhile, by design: production's CRM still holds the old options, so
    an information request or registration there writes no stage, and no
    new public-form record gets a lead behind it (no backfill is built).
    Owed: production at a Sunday slot (the lead-model plan, the
    touch-positions plan, labels, layouts, the value move from the
    container — handoff § 1) and Boston with its release; the § 6 removals
    after that, on Doug's approval. **Ruling 54 (10-19-26):** the Marketing
    Admin Role gains Account read all — `scripts/prospect_crm_test.sh roles`
    on crm-test (dry run: exactly that one change), production and Boston
    with the role script at their slots, and the roles standard
    (`prds/chapter-network/roles-standard/`) updated to match.
    **The lead code (build plan § 7d.5, rulings 71–75): CRM handoff
    written 10-22-26 01:42** (`lead-code-crm-handoff.md`, plan fingerprint
    `bec909277859`, two field rules in the role script). **Applied on
    crm-test 10-22-26 12:45–12:48 by Doug and read back by Claude 12:50.**
    **D1 built 10-22-26 13:00 (v0.276.0, committed, not pushed)**; its code
    paths tried against crm-test as the org-wide key (mint, copy to the
    contact, resolve, per-form prefill, cleared after). Pushed and live on
    crm-test 10-22-26. The live pass found, before it ran, that the company
    box on the information request, partner and funder forms was never
    filled (v0.278.3, pushed). **D1 LIVE-PASSED on crm-test 10-25-26 11:10**
    by Doug from https://claude.ai/artifact/1GY9zFFjfP16SiBXQJyHKz (rev 1.1),
    read back by Claude as the org-wide key: Tremont's card opened the landing
    page, which converted the lead and handed `lead=sbxscan23459` to the
    information request; the contact Pat Roaster took the lead's code at
    conversion (one code, two holders); the request's receipt carried
    `lead_code` and no `prospect_id`; a form link filled the company for a
    known code and nothing for an unknown one; Ohio City Bike Works' call
    record counted the click with its outcome kept at *No answer*. The count
    read 2 for one intended visit (a second open, or the browser fetching
    the address while it was typed — not diagnosed); D3 must expect mail
    scanners to inflate email clicks the same way. Ruling 126's D3 pieces:
    *New code* built with M2 (v0.284.0), the vendor field `cbm_lead_code`
    with M7 (v0.290.0, live send owed under #57); the caller's link still
    owed with M10. **Owed: D2** (each form's prefill, the *Not you?* line,
    the registration's one press, the text's `{link}`) **and #59**, in the
    next window when no other session is on the arc (Doug, 10-25-26: wait
    for the redesign step in progress to finish first); production and
    Boston with the arc's slot.
    **At the production slot, also do these two (added 10-22-26; both
    live-passed on crm-test 10-22-26 as Mark Marketing). Without them, no
    campaign action records any history on production:**
    (1) **Ruling 69, the stream grant.** The Marketing Admin Role gains
    stream *all* on `COutreachCampaign` and `CProspect`, so history notes
    post for non-admins. It rides the existing `roles` step: in the
    production web console, `bash scripts/prospect_crm_prod.sh roles`
    (dry run), then `… roles apply`.
    (2) **The action-history record types.** `CActionLog.record` gains
    `COutreachCampaign`, `CProspect` and `COutreachTouch`, so action-history
    rows stop being refused. `bash scripts/prospect_crm_prod.sh actionlog`
    (dry run: expect "WOULD add" with those three, and also `CEvent` and
    `CEventRegistration` if production still lacks the 10-07-26 events fix),
    then `… actionlog apply`.
    Check afterwards: one campaign save by a non-admin Marketing Admin Team
    member, then no `stream note … failed` or `action-log write failed` line
    for it in the production web log. Boston needs the same two at its
    release, and the roles standard needs updating for ruling 69.
    **The Leads and Review grids at volume (v0.267.0–v0.267.2, build plan
    § 7b): LIVE-PASSED on crm-test 10-20-26 14:28** by Doug as Mark
    Marketing with 3,017 leads, from
    https://claude.ai/artifact/4FLXfPqnXLJ4Hhytded3uS (rev 1.4). Every count
    matched (searches 90–180 ms); the bulk Do Not Contact wrote 400; the
    second-reviewer guard refused and wrote nothing. The pass found two
    defects, both fixed and live: a typed filter ignored Enter and Tab
    (v0.267.1), and an 800-row import plan made 1,001 sequential CRM calls
    (61.6 s), timed the page out and showed "signal is aborted without
    reason" (v0.267.2: 30 reads, 2.3 s; the apply in parts of 100, about
    80 s for 800; a timeout now says so in words). The import ran as
    *Purchased list* because the page buried Lead Source in a half-sentence
    (fixed in rev 1.4); ruling 53's Qualified path was not re-run at volume —
    its code is unchanged and passed on 10-19-26.
    **Funders on a campaign (v0.268.0, ruling 57): LIVE on crm-test and
    CHECKED 10-20-26 15:04** — the link applied by Doug (verified on both
    sides), the seeder named Harrowgate, Mark Marketing added Blue Heron
    through the picker (read back: both funders), Sally Sponsor saw the
    Campaigns tab on Harrowgate and the empty message on Sterling Mutual
    Bank (both 200 in the web log). From
    https://claude.ai/artifact/6BTc4r1XqKpWq8Zjnf1qNd. Owed: production with
    the lead-model slot, Boston with its release, and a sandbox recapture
    (the new table empties nightly until then; re-run the seeder before a
    demo).
    The earlier passes' record follows.
    **Phase 1 BUILT and LIVE-PASSED on crm-test
    (v0.258.0–v0.258.5, 10-15/17-26, dark behind `CAMPAIGNS_ENABLED`);
    Phase 2 BUILT (v0.259.0, 10-17-26) and LIVE-PASSED (A–E 10-17-26,
    F–I 10-18-26 01:50 from the standalone page
    https://claude.ai/artifact/JwrDqWeg7zwWDoSTMzf6Vj, read back by Claude:
    Sam carries the campaign and Tess none, both Prospect at Warm Lead; Lakeview
    Bakery Prospect → Partner, the partner profile carries the campaign and
    its notes line; the forged id dropped with the worker's warning; the
    relabel script's dry run on crm-test: nothing carries the old shape);
    Phase 3 BUILT and LIVE-PASSED on crm-test (v0.261.0–v0.261.1,
    10-18-26, dark behind `CAMPAIGNS_CALLS`); Phase 4 BUILT and
    LIVE-PASSED on crm-test (v0.262.0–v0.264.1, 10-18-26, dark behind
    `CAMPAIGNS_SMS` / `CAMPAIGNS_EMAIL`); **production's CRM carries every
    change (Phase 1 slot 10-18-26 morning; rulings 36/39/40 slot 10-18-26
    ~16:40, read back by Claude), every switch off there** — Boston owed**
    (**Phase 4 pass, 10-18-26 10:40–15:05, Doug as Mark Marketing; read
    back by Claude:** the email list pushed as *Campaign — Phase 4 pass —
    email* with Ann, Ben, Sam and Tess and marked sent; the text sent to Ann
    only, delivered, her STOP turning her text opt-in off and a second list
    reading 0; Ben attended → Opportunity; the funnel 0/1/1/3/1/7/8
    matched a hand count; the campaign tab's Registered 2, Attended 1. The
    pass found ruling 40 — fixed in v0.264.1 and proven on the text
    campaign's stored sign-off — and a stale Responses tab (fixed, not
    pushed)) (10-14-26, updated 10-18-26 02:24). **Phase 4:** rulings 38
    (the application sends texts — Twilio behind a dry run; the account, a
    sender number and A2P 10DLC registration are Doug's before any real
    text) and 39 (`COutreachCampaign.smsMessage`, plan
    `coutreach-sms-message.json` fingerprint `7a68865149b4`, owed on
    crm-test — `scripts/prospect_crm_test.sh smstext` — production and
    Boston). Step page https://claude.ai/artifact/96dzUAsNAfkbJCx2eDu91g.
    **Ruling 40 (10-18-26, found on the Phase 4 pass, v0.264.1):** the eight
    app-written campaign fields were Read-only, which EspoCRM enforces on
    every writer, so no campaign ever stored its rule, sign-off or run
    times. Owed on every CRM: `prospect_crm_test.sh appfields` (plan
    `coutreach-campaign-app-fields.json`, `965d932407f3`) and `… roles` (the
    Marketing Admin Role's read-not-edit field rule); the same two words in
    `prospect_crm_prod.sh`. **Also suspect, not yet checked:**
    `CNetworkStandard.appliedAt/appliedBy/appliedByTool` are Read-only too
    (crmConfig reads "unstamped" on crm-test), and
    `CEventRegistration.confirmationSentAt/postEventFollowUpSentAt`. **Phase 3 pass, 10-18-26
    00:50–01:32 (Doug):** every step matched on crm-test after one fix —
    **v0.261.1**: the Mentor Role's Assignment Permission is *team*, so
    EspoCRM refused Joe Mentor's save of a call record carrying no team and
    no assigned user; call records now carry the campaign's teams. The
    decisive check (section H) read back as a call **modified by Joe
    Mentor** and the campaign Complete. The staff steps ran as Admin, not
    Mark Marketing (the review stamps read "Admin"), so the Marketing Admin
    Role's own path for review and the call kind is proven by Phase 1's
    grants, not by this pass. **Found, owed:** every Campaign Management
    action's `CActionLog` row is refused (HTTP 400, `record` not valid) —
    `CActionLog.record` does not list `COutreachCampaign`, `CProspect` or
    `COutreachTouch` (the event gap of item 669 again) — fix 10-22-26:
    `scripts/migrate_actionlog_record_entities.py` now adds all three (dry
    run on crm-test: exactly those three); APPLIED on crm-test 10-22-26
    00:56 and live-passed 01:04 (Mark Marketing's edit of "Fall follow-up
    calls" wrote its `CActionLog` row, HTTP 200). Owed: production from inside its web
    container, Boston with its release. **Corrected
    10-20-26:** the stream notes were written only because the pass ran as
    Admin; for every non-admin they were refused (HTTP 403, no stream access).
    **Ruling 69** grants the Marketing Admin Role stream all on
    `COutreachCampaign` and `CProspect` — APPLIED on crm-test 10-22-26 00:40
    (both read back OK, rebuild 200); live-passed 10-22-26 00:51 — Mark
    Marketing's edit of "Fall follow-up calls" posted its note, created by
    him. Owed: production and Boston with the role script at their slots, and the roles
    standard updated to match. A CRM entity-list change on all three CRMs. **Phase 3 (10-18-26):**
    rulings 36 (callers are the campaign's teams, each acting as themself)
    and 37 (no rung on a record holding a relationship type — v0.260.2)
    recorded first; the Review tab, the call kind and the Calls page, the
    Stale sweep, the Campaigns Analytics page. **Owed before the pass:**
    push; `scripts/prospect_crm_test.sh roles` (the Mentor Role's two
    grants — the dry run reads exactly two); *Campaign calls* on at `/setup`
    on crm-test. Step page
    https://claude.ai/artifact/D8atEqEdRaRBKh4mmxiPsj (the list file is
    `prds/prospect-marketing/live-pass/phase-3-list.csv`). **Production's
    role script now plans the Mentor Role's two grants as well** — the
    production slot's step page (written 10-18-26 by another session) says
    "seven grants"; expect nine. Three sessions worked the arc on 10-14-26 and left three
    documents that disagreed; Doug ruled a directory on the chapter-network
    pattern. Start at its `README.md`. `rulings.md` is the binding record
    (rulings 1–27, CM-1 to CM-11, append only); `build-plan.md` v0.2 is the
    one plan (v0.2 against CM-1 to CM-11 at 22:09; **v0.3 at 22:43 with
    Doug's answers to the four shape-changing questions, rulings 28–31** —
    custom entities, `Unverified`, **multiple referring partners on an
    engagement** via a new many-to-many `CEngagement.referringPartners`,
    links in the application database); the process plan and the three
    spent kickoff prompts are under `history/`. **Owed, in order:** (a)
    ~~the four answers~~ done 10-14-26 22:41; (b) ~~the two CRM
    handoffs, plan files and role script~~ **done 10-14-26 23:15** —
    `contact-sms-opt-in-crm-handoff.md` + `scripts/plans/contact-sms-opt-in.json`
    (one change, fingerprint `0bc7219ab932`), `coutreach-entities-crm-handoff.md`
    + `scripts/plans/coutreach-entities.json` (three entities, 57 fields, 17
    links, one enum option: 78 changes, fingerprint `6b29c8928dcf`),
    `scripts/migrate_outreach_roles.py` (merge-only; six grants on crm-test,
    every re-check already held; no role carries a `fieldData` rule on
    Contact or Account), both fingerprints pinned in
    `tests/test_apply_crm_plan.py`; the spent prompt is in
    `prds/prospect-marketing/history/prompts/`; (b′) ~~the one name the plan
    could not store as written~~ **ruled 10-15-26 00:01, ruling 32**:
    `attributedPartnerProfiles` (the drafted name; build plan v0.4; the
    fingerprints stand);
    (c) ~~Doug applies on crm-test~~ **done 10-15-26 01:06–01:19**: both
    plans, the notes conversion and the role script by Doug through
    `scripts/prospect_crm_test.sh` (one word per step; the mutating runs
    are refused to Claude by the session classifier), the tab list and —
    found on the apply — the three entities' detail and list layouts
    (default `name` only) by Claude through the admin API; `mailingAddress`
    accepted as the `address` type; three org-key 200s, sync dry run
    clean, conformance diff empty; (c′) ~~the real non-admin pass~~ **matched 10-15-26 01:49** (Doug as
    Mark Marketing and Sally Sponsor, step page
    https://claude.ai/artifact/ShmRGZgDWWfspETWuU86hQ; the partner relate
    as a Marketing Admin answered *operation requires edit access to
    foreign record*, the expected both-sides check the build handles with
    the admin fallback); soaking to the Sunday slot; (d) ~~Phase 1~~ **built 10-15-26 03:05, v0.258.0** (ruling 33: the
    import's Company and Contact writes run under the intake API client);
    (d′) ~~Doug's Phase 1 live pass on crm-test~~ **run 10-15-26 and
    10-17-26** from the step page
    https://claude.ai/artifact/XSEA7eWTx3yhXkH6Kw9oLD (both switches on at
    `/setup` on crm-test, the receipt option applied 10-15-26 10:23); Doug
    reported the pass complete 10-17-26 01:2x with no failure outstanding
    after the fixes it found — v0.258.1/.2 (`[hidden]` lost to
    `display:grid`, every panel rendered at once), v0.258.3 (a prospect
    create carrying a Company link 403s as a Marketing Admin; a partial
    import now resumes; the Imports route was shadowed), v0.258.4 (the API
    role needs **edit** on `COutreachCampaign` for the worker's run — re-run
    `scripts/migrate_outreach_roles.py` on every CRM) and v0.258.5 (a
    promoted company was selected beside its own prospect record). Two
    notes from the pass, not defects: the portal's CRM link is Mentor Team
    only by the v0.30.0 rule (Doug: leave it); Submission Admin's hardcoded
    form filter list (`ops/frontend/app.js` `FORMS`) lacks
    `prospect-response` and `event-registration` — a delivered response is
    found under the **Closed** chip (cosmetic; owed);
    (d″) ~~Phase 2~~ **built 10-17-26, v0.259.0** (the five doors honour the
    campaign id and the prospect id through `campaigns/attribution.py`; the
    engagement's `referringPartners` and the three union readers; the relabel
    at conversion in `core/crm_upsert.py`; **ruling 34**, the information
    request door's company typed Prospect, with
    `scripts/relabel_info_request_companies.py` for the companies created
    under the old shape — dry-run first, Doug runs it on each CRM once the
    Prospect option is there; the programme page's carry-through; the
    Responses tab's *Responded* / *Converted* and record links; the Submission
    Admin filter note above closed). **Verified by tests only** (2,557 green,
    38 new). (d‴) **Doug's Phase 2 live pass on crm-test** — the six steps of
    build plan § 7 Phase 2, step page https://claude.ai/artifact/JLZyupBD4i6scAogws6sWD, as Mark Marketing for the
    reads and signed out for the forms; and the relabel script's dry run on
    crm-test (`uv run python scripts/relabel_info_request_companies.py`), then
    `--apply`; the pass's B8 found two fields labelled *Campaign* on Contact
    and Company — **ruling 35**, ours labelled *Outreach Campaign* in the CRM,
    crm-test done 10-17-26 22:49 by `scripts/relabel_outreach_campaign.py`,
    production and Boston owed (handoff § 3.4); **pass state 10-18-26 00:05**:
    sections A–E matched (after v0.259.1, the worker dropped every campaign),
    F's carry-through seen in the log, F's registrations and G–I owed on
    10-18-26 (crm-test's 04:00 UTC reset removed the pass's records); Doug
    opened the Phase 3 gate to build in parallel; (e)
    questions 2, 4 and 5 before the first real card; (f) ~~production at the
    Sunday slot~~ **done 10-18-26** (Doug, from
    https://claude.ai/artifact/DPDwikp24BWMsg2UZs3naF; read back from inside
    the container: every check ok, nothing left but Phase 3's two Mentor
    Role grants, which ride Phase 3's own production step; the feature is
    still switched off there), Boston with its release, a seeder and a sandbox re-baseline (the
    outreach handoff adds six tables; the SMS one adds a column, which
    survives the reset); the application's four new tables reset nightly
    too, so a demo campaign's links need the seeder. No CRM change, no vendor account, no
    code. **One session on this arc at a time.**

50. **A partner's own client intake link (v0.255.0) — live on crm-test
    and production 10-12-26 17:42, live pass owed.** Doug's requirement 10-12-26, link form ruled the CRM id;
    no CRM change. **Owed, on crm-test:** as partner.manager open a
    partner's Details tab, copy the *Client intake link* (it should read
    `https://cbm-client-intake-svxs3.ondigitalocean.app/client-intake/?partner=<id>`);
    open it signed out — the banner "You were referred by <partner>"
    shows and "How did you hear" reads *Partner Referral*; submit a test
    request; after delivery the engagement in Client Administration shows
    that Referring partner — the **"Referred by <partner>" band under the
    popup's title, in view AND after pressing Edit** (v0.256.0) — its notes
    carry "Referred through …'s client intake link.", and the partner's
    Referred Clients tab lists it. Then
    the same link with the id altered: no banner, the form works, no
    partner on the engagement. Then production as a real non-admin.

    **Redesign step M1 — one page, six tabs — BUILT as v0.279.0 (10-23-26
    01:33), pushed 04:04 and live on crm-test; v0.279.1 (leaving an unsaved
    list discards the edit) committed 7d116f5, push owed** (build plan
    § 7e.2; rulings 89, 112, 114). Runbook for the live pass, 36 steps:
    https://claude.ai/artifact/PMdnPnnpKG4tVsUvj9W8SU (written 10-23-26
    04:09 against crm-test's running call campaign "Fall follow-up calls",
    which names the Mentor Team, and its two planned touches). **LIVE-PASSED
    on crm-test 10-24-26 14:46** by Doug ("the m1 live pass is completed"):
    all 36 steps, as Mark Marketing and as Joe Mentor. Read back by Claude:
    the Gordon Square Florist touch is Done / No answer, modified by Joe
    Mentor at 18:45:06 UTC, and a new Planned call-again touch was created
    by the API user the same second; Doug confirmed both in the CRM's own
    Touches list 10-24-26 18:14 (runbook
    https://claude.ai/artifact/5kWmwK5CHcnaeM9hH1H7rb). One runbook correction during the
    pass: Enter in the New-list dialog's Name box creates the list, and
    "the index" was renamed "the table of lists" (page version 2). The nine
    Drafts in build plan
    § 7e.12 are ruled (117–125, 10-23-26 03:53); M2 (the ladder and the
    Leads tab, behind `LEAD_LADDER`) waits only on the handoff's lead
    fields on crm-test.
52. **A quick-add from the other door's company inherits its primary
    contact (v0.257.0) — live on crm-test and production by 10-14-26
    22:06, live pass owed** (another session had taken #50 and #51). Doug's
    request the same day; no CRM change. **Owed:** on crm-test as
    partner.manager, "+ Add partner": pick a company that has a funder
    record with a primary contact, leave the contact block empty, save —
    the notice says the primary contact was copied from the funder record,
    and the new partner's Details tab lists that contact, marked Primary;
    then the reverse as sally.sponsor. Then production as a real non-admin.
    ClickUp: https://app.clickup.com/t/86bcm41wq (awaiting qa) — move it to
    released when the pass matches.

49. **The quick-add's Company picker (v0.254.0) — live on crm-test and
    production 10-12-26 14:49; the pass matched (Doug, 10-12-26: "all
    steps passed") — RESOLVED except Boston, which takes it with its
    release.** Doug's question the same day; no CRM change. **Owed:**
    on crm-test as sally.sponsor, "+ Add funder": the Company box offers
    every company with its website beside the name; pick one that already
    has a partner profile (Key Bank, if the sandbox has it), leave the name
    to mirror, save — the funder is linked to that company (the notice says
    "Linked to the existing company"), and the company's type reads
    `Partner, Sponsor` in the CRM; then "+ New company…" still creates a
    typed one. Then production as a real non-admin.

48. **"Make primary" on a partner's or funder's CBM contacts (v0.253.0) —
    live on crm-test and production 10-12-26 14:28; the pass matched
    (Doug, 10-12-26 afternoon: "all steps passed") — RESOLVED except
    Boston, which takes it with its release** (Doug's request and ruling
    2026-10-12: the former manager is kept as an additional manager).
    Needs no CRM change — it rides the additional-managers links, so it
    works wherever those exist (crm-test, production; Boston with its
    release). **Owed:** the pass on crm-test as sally.sponsor on a funder
    that has an additional manager: the Make primary button on that row,
    the swap (the row becomes Funder Manager, the former manager becomes an
    additional manager, the Overview's manager fact follows), one click on
    the former manager's row swapping back, and the former manager's My
    Email still listing the record. Then production as a real non-admin.

47. **Funder Notes as rich text (v0.252.0) — crm-test and production
    converted and passed 10-11-26; Boston's CRM converted 10-11-26, its
    release owed** (Doug's request 2026-10-11). The app follows the field's live type. Step page for the
    whole crm-test rollout: https://claude.ai/artifact/59ZYyJM492BZFG8bMbbLtX
    (private, *Funder Notes Rollout*, written 10-11-26). **Done:** (a)
    crm-test — Doug ran § 1 of `csponsorprofile-description-wysiwyg-crm-handoff.md`
    on 10-11-26 (the field reads `wysiwyg` as the org key, 18:40); the plain
    box it still showed was v0.252.1, live 14:30; (b) v0.252.2 pushed
    10-11-26 19:02 and live on crm-test and production 19:04 — the review
    of the handoff found the session tools did NOT up-convert a legacy
    plain note's line breaks (Client Administration did; the handoff had
    copied its sentence), so step 2.2 of the pass would have failed and
    the first save would have stored the note collapsed; (c) **the pass as
    sally.sponsor done 10-11-26 evening** (Doug: "testing completed on
    test"). (d) **production done 10-11-26** — Doug's first look that
    evening showed the plain box (the unconverted `text` field, not a
    defect); Doug ruled to run it that day rather than at the Sunday slot,
    and ran the step page https://claude.ai/artifact/Gm48QrmUkKyLpMYj1ss8pk
    (private, *Production Notes Conversion*): `scripts/convert_notes_wysiwyg.sh`
    over SSH converted both notes fields at 20:32 (backups stamped
    `20261012-003237` beside the files, both read back `wysiwyg` at 20:37),
    and all three passes — funder manager, client administrator, CRM
    administrator — matched ("all tests passed"). **Owed:** (e) Boston — Doug asked for it the same night (20:43); step
    page https://claude.ai/artifact/NbHtjXjEUHskC5ExWTK7Tg (private, *Boston
    Notes Conversion*, 10-11-26 20:50), command
    `scripts/on_crm.sh boston scripts/convert_notes_wysiwyg.sh` (the wrapper
    exists because Boston's key pushes the bare ssh line past 70
    characters). Read-only probe 20:43: Boston's `CSponsorProfile.description`
    is `text`; its `CEngagement.description` is ALREADY `wysiwyg` (a
    `.bak-desc-wysiwyg` from the chapter build sits beside it), so the run
    converts the funder field only. **(e) ran on the CRM 10-11-26 21:06** —
    found 10-14-26 22:00 by a read-only probe for the Boston release page:
    `CSponsorProfile.description` reads `wysiwyg` under the org key and the
    droplet holds `CSponsorProfile.json.bak-desc-wysiwyg-20261012-010651`
    beside the file; this item had not recorded the run. What remains of
    (e) is the release and the Overview half of the pass (sections 3 and
    5 of https://claude.ai/artifact/Covmt3vPbZnvWpr8WdQBY6, private, *Boston Release
    Changes*, rev 2.0 10-18-26 — one page for both of this arc's Boston
    changes, with #46; not yet run as of 10-18-26 22:50, Boston still at
    v0.232.0). **Boston's applications run v0.232.0**
    (the last release-lane cut), which predates the Overview following the
    live type (v0.252.0) and the line-break fix (v0.252.2). Doug's ruling
    10-11-26 20:5x: **convert the CRM tonight, release next Sunday** — the
    Details tab's Funder notes panel goes rich at once; the Overview stays
    a plain box and shows a rich note's tags until the release (page rev
    1.1 checks the Details tab and tells Boston staff to edit there
    meanwhile). **Next Sunday:** cut v0.252.2 to the release lane
    (`scripts/cut_release.sh`, then its push line; Boston and Lakeside take
    it by themselves) and set Boston's chapter key to `boston` at its
    System Settings page before any event is saved there (v0.233.0).

46. **Additional managers on partner and funder records (v0.251.0) —
    crm-test and production done and passed; Boston owed** (built 2026-10-11 on
    Doug's requirement; changelog has the design). Step page for the whole
    crm-test rollout — apply, push, live pass as the two managers, My Email
    as the added person: https://claude.ai/artifact/9aW3mVrfdcHa3gnKMACHTp
    (private, *Additional Managers Rollout*, written 10-11-26, rev 1.1).
    **crm-test done 2026-10-11:** (a) Doug applied the plan (both links
    created and read back, 13:46); (b) the live pass ran — the partner add
    as partner.manager (POST 200 at 17:49 UTC) and the funder add and remove
    as sally.sponsor (POST 200 at 17:51:41, DELETE 200 at 17:51:56 after the
    expected escalation to the administrator on the mentor-profile side) are
    in the web log, and the CRM read back as administrator afterwards shows
    Acme Bank and Loan on Joe Mentor's `comanagedPartners`. Section 4's
    first wording expected My Email to list records; it lists mail threads,
    so the sandbox's empty inbox was the right result (page rev 1.1).
    **Two follow-ups, neither a build defect:** the Mentor Role holds no
    read on `CSponsorProfile` on crm-test or production, so a mentor named
    additional manager on a FUNDER sees it in neither Funder Management nor
    My Email (the mail sync is unaffected — its scope runs under the org
    key); a role ruling is owed before that case is used. And a Sponsor
    Manager cannot unrelate the mentor profile herself (no edit on
    `CMentorProfile`): the app's escalation covers it, as for co-mentors. The code is live-dark
    until a CRM has the two links. **Owed, in order:** (a) crm-test — Doug
    runs, from the repository root:
    ~~`PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/apply_crm_plan.py scripts/plans/additional-managers.json --apply --expect f2d6a41ea16c`~~
    — done, see above; ~~(b) the live pass on crm-test as~~ done; the rest of (b) as
    partner.manager and sally.sponsor — the Details tab's CBM Contacts card
    offers *Select existing CBM contact…*, the add records a history note,
    the person then appears in the Overview's CBM Contacts, their My Email
    lists the record, Remove works; (c) **production** — Doug found the
    card inactive on production 10-12-26 (both links absent, read from the
    droplet's customization files 13:57) and asked for the steps; step page
    https://claude.ai/artifact/Lq7rbijp2bJVqizQR9TmGT (private, *Production
    Additional Managers*, 10-12-26 14:05): the applier from inside the
    production web console, dry run then `--apply --production --expect
    f2d6a41ea16c`. **Applied by Doug 10-12-26 ~14:00** (as mentoradmin;
    both links created and verified by the applier; both files and the
    mentor-profile reverses read back from the droplet 14:04); **the
    pass as a non-admin Sponsor Management Team member and the Entity
    Manager check both matched the same afternoon** (Doug: "all steps
    passed"). **Owed:** Boston with its next release from the same plan
    (`cpartner-csponsor-additional-managers-crm-handoff.md`) — **prepared
    10-14-26 22:00, awaiting Doug's go**: the read-only probe found both
    links and both mentor-profile reverses absent on Boston, the applier's
    dry run against Boston signed in as its administrator and printed the
    same fingerprint `f2d6a41ea16c`, and Boston holds one mentor profile,
    no partner and no funder records (the add itself cannot be exercised
    there until a second profile exists). Boston's image is v0.232.0, which
    predates the applier shipping in the image, so the apply runs from this
    computer through the new `scripts/apply_plan.sh boston …` wrapper
    (parses `~/.config/cbm-boston/boston.env`, never sources it). Step page
    https://claude.ai/artifact/Covmt3vPbZnvWpr8WdQBY6 (private, *Boston Release
    Changes*, 10-14-26 22:10): sections 1–2 today (apply, Entity Manager),
    3–6 on Sunday (the release cut and push, Boston's chapter label at
    `/setup`, the pass on a test funder, its removal). **State 10-18-26
    22:50 (session closed without the go):** nothing on the page has run —
    Boston still reports v0.232.0, the release lane still points at
    v0.232.0 (main is at v0.264.2), and the re-probe found both links
    still absent with the dry run still printing `f2d6a41ea16c`. The page
    was rebuilt to the 10-17-26 step standard (rev 2.0: done boxes with
    progress and reset, a Before-you-start block, every changing step
    warned with its undo, checkpoints) and its versions refreshed to
    0.264.2. Kickoff for the next session:
    `prompts/boston-release-session-2026-10-18.md`;
    (d) the Gmail sync scope now also covers co-mentored engagements, which
    it never did — watch production's first "scopes rebuilt" line after
    the deploy for a larger record count, not an error.

42. **Events: the production end-to-end test, and the redirect deferred.**
    **Closing state 10-26-26 11:58 (session ended for a reboot; everything pushed,
    production v0.289.0):** the test is complete; D3 confirmation built dark
    (v0.277.0, live pass owed); D2 Follow-up tab, consent-over-false and
    search-by-name built and live; durations on both CRMs. Owed, in order:
    the confirmation's in-person live pass on crm-test, Track C with real
    Zoom (then the online half), production's confirmation plan + seed +
    switch, Boston, then the redirect once Doug lifts the hold. Doug's open
    decisions: the five-week series as one event or five; the Holiday Social
    Internal or Public; the presenter title / photo / topic data points.
    Kickoff for the next session: `prompts/events-session-2026-10-26.md`.
    **THE TEST IS COMPLETE — 10-19-26 00:51.** Every section of the runbook
    (https://claude.ai/artifact/Dkbb1t7MKFb9vnjabpcyMc, rev 2.2) ran on
    production 10-18/19-26 and matched after the corrections below; the
    three test registrations are removed (Doug also removed his 09-15-26
    training-webinar one), the receipts stay by design, the contact is
    intact, and production's programme page carries the website's seven
    sessions, twelve recordings and six presenter cards. **What the test
    settled:** Track F F1 and F4 are on production (CRM, grants, switch, a
    real non-admin pass); the duration list has its three new lengths; the
    library matches the playlists; capture, delivery, the near-duplicate
    hold, discard with its receipt write-through, the portal rail and member
    page, the Registrants tab and counts all work on production data.
    **Fixed on the way:** v0.264.3 (the applier takes integer options; the
    editor reads Duration from the CRM) and v0.264.4 (a registered sign-up
    form locks). **Owed before the redirect, in order:** (1) ~~**Track D D3,
    the confirmation email**~~ **BUILT 10-22-26 13:32 as v0.277.0, dark behind
    `EVENTS_CONFIRMATIONS`** (rulings D3-1/D3-2; design
    `prds/events/CBM_Events_Confirmation_Email_Design.md`; the eight templates
    seeded on crm-test, `Seat Offered` applied on crm-test; owed: the live
    pass of design § 10 on crm-test, production's plan + seed + switch, and
    the online half with Track C); (2) ~~a **ruling on consent**~~ **RULED and BUILT 10-22-26 22:46 (v0.278.4):**
    a ticked consent or opt-in box sets `true` over a stored `false`, never
    the reverse, on every public door (`find_create_or_fill(true_wins=…)`); (3) ~~the
    **Zoom question for webinars**~~ **RULED 10-22-26 12:55 (D3-1):** an online Public
    event is not shown or open for registration until its Join URL exists,
    which Zoom fills once Track C is on; no hand-pasted link on Public events.
    Until Track C, our page offers in-person events only and the website keeps
    the webinars; the two webinars shown on production today fall under the
    rule when it ships; (4) ~~**Submission Admin search by
    name**~~ **BUILT 10-25-26 11:24 (v0.283.1):** the search box matches the submitter's
    name and company; (5) Doug's
    decisions on the **five-week series** (one event or five — check-in is
    per event) and whether the **Holiday Social** should be Internal;
    (6) data: three mentors' `mentorTitle` is a tagline, Cindie Pacheco's
    profile has no photo or biography, Board Fundraising lacks the
    Industry-Specific topic and the 10-22 AI webinar has none; (7) Boston
    takes F1/F4/durations with its release; (8) the redirect itself
    (Track A, A8), in a few weeks by the 10-09-26 ruling.
    **Section 2 DONE on production 10-18-26 23:30–23:40 (Doug, from the web
    container; verified from here 10-18-26 23:43 as the org key):** `CEventPresenter`
    created with its five fields and two links and readable by the API key
    (200), the four role grants read back, `CEvent.topics` created and
    eleven events' single topic copied into it, `CEvent.duration` now offers
    4500/5400/12600, the two recordings imported unshown (13 events in all).
    The conformance check's `exit=1` is the five event email templates Track
    D still owes (`EventReminder` …), pre-existing; nothing else moved (the
    "before" run, step 2, was skipped, so this is read from the findings,
    not a diff). **Sections 3 and 4 DONE 10-18/19-26 (Doug as his regular login; read
    back from here 10-19-26 00:16 as the org key):** the seven sessions saved with
    the right Cleveland times (stored UTC: 23:00 for 7:00 PM, 16:00 for
    12:00 PM), the three new lengths used (1h 15m ×2, 1h 30m, 3h 30m), all
    Public / This chapter with slugs; the public calendar answers seven
    cards and the library twelve, both imports shown with their topics; six
    presenter entries over four events, one Contact per person (Andrew
    Ciszczon on two events, no duplicate), photo routes 200 as a visitor,
    the series page 200 with three cards. Two entry misses, not defects:
    *Get Your Board Fundraising* carries only Finance & Accounting
    (Industry-Specific not ticked) and the 10-22 *AI for Small Business*
    webinar carries no topic. One data point for Doug: the card's title
    line copies `CMentorProfile.mentorTitle`, which three mentors use as a
    tagline (Sue Marrone's reads like a workshop blurb, CiCi Caver's is an
    industry list) and Cindie Pacheco's profile has no photo and no
    biography — edit the card, or the profile. **Section 5 DONE 10-19-26 00:19–00:23 (verified from the database and
    the CRM 10-19-26 00:34):** four event-registration rows captured (two Completed
    and auto-closed, two Held-Duplicate — the deliberate repeat on the
    series and a second submission on the marketing webinar), four receipts
    written, two `CEventRegistration` rows source Online. **The registrant is
    Douglas Bower, not "Test Registrant"**: the email Doug typed is on his own
    contact, and a known email never makes a second contact (by design) — so
    the clean-up removes the two registrations and the four receipts and
    never the contact (runbook rev 2.1). **Finding for a fix:** Submission
    Admin's search box matches the form, email, statuses, reference and
    activity but **not the submitter's name** (`ops/frontend/app.js`
    `matchesSearch`), which is why step 6-6's "Registrant" found nothing;
    the step now searches `event-registration`. **Sections 6 and 7 DONE 10-19-26 00:39** (read back from the database and
    the CRM): the two held rows discarded by `doug.bower@cbmentors.org` with
    the reason, and **the discard reached their receipts** (two
    `CIntakeSubmission` rows now read Discarded, two Completed); the two
    registrations stand on Douglas Bower, source Online; no new contact.
    **Finding (b) for a ruling:** the consent ticked on a public registration
    is written through the null-fill, so an EXISTING contact whose opt-in and
    consent booleans are already `false` keeps `false` — Doug's own contact
    reads opt-in false after a ticked registration. A ticked consent is
    time-stamped evidence and arguably should set `true` over `false`
    (never the reverse); `forms/event_registration/orchestrator._contact_payload`
    plus `core/crm_upsert.find_create_or_fill`. v0.264.4 (the form lock) live
    on production 10-19-26 00:37. **Section 8, 10-19-26 00:45:** the four receipts Doug removed in the CRM were
    **recreated by the receipt sweep at 04:40 UTC** (two Completed, two
    Discarded) — by design, a receipt follows the application's row, which
    is never deleted — so step 8-2 is withdrawn (runbook rev 2.2) and the
    receipts stay as the test's record. **The two registrations dated
    10-19-26 on Douglas Bower were still present (deleted=false, read as the
    administrator 10-19-26 00:45)**: step 8-1 is owed again. The contact is intact,
    no test contact exists, 20 events, 6 presenter entries, the public page
    7 cards and 12 recordings.
    **State 10-18-26 23:22: the step page was rebuilt to the 10-17-26 step standard
    (rev 2.0, done boxes, every value pre-filled from reads) and now carries
    the whole job**: the Track F production apply (#39, #41 — their Sunday
    page is superseded by section 2 here), the new duration choices
    (`scripts/plans/cevent-duration-options.json`, fingerprint `47e42699f2d3`,
    applied on crm-test 10-18-26 23:25; the editor reads the list from the
    CRM since v0.264.3), the two recordings the playlists hold and the CRM
    does not (import dry run from the production container 10-18-26 23:05:
    15 items, 13 in the CRM, 2 to import), the website's **seven** sessions
    (its feed 10-18-26 23:01 — four more than on 10-09-26: Take the Guesswork
    Out of Marketing 10-20, AI for Small Business 10-22 virtual and 11-18 in
    person, the 2026 Holiday Social 12-09) with their presenters (all five
    named on the website are production Mentor contacts with profiles), the
    side-by-side, three registrations, the staff views, Claude's CRM
    read-back and the clean-up. Read from the container the same night:
    **the Track F apply has NOT run on production** (`topics` absent,
    `CEventPresenter` 404), the public calendar holds 0 upcoming events, the
    non-admin account is Doug's own regular login. **Prerequisite: v0.264.3
    pushed** (committed `61075cb`, the applier's integer-option fix). Nothing
    on the page has run.
    Original entry (Doug's ruling 10-09-26: *"We are not planning on modifying the production
    web site for a few weeks. We want to test the events functionality to be
    sure it works and has all current data before we proceed."*). The redirect
    (Track A, A8) waits; the test runs on **production**, approved 10-09-26,
    because that is where the data and the roles are and crm-test wipes itself
    nightly. **Step page written 10-09-26 17:05:**
    https://claude.ai/artifact/Dkbb1t7MKFb9vnjabpcyMc (private, *Events
    Production Test*, rev 1.0): a console check that the Sunday CRM change
    landed and the YouTube import dry run (the library is complete when it
    prints `0 to import`); the three sessions the website lists today created
    in Event Administration as a real non-admin (Business LaunchPad 5-Part
    Weekly Series 10-19 7:00 PM in person at Westlake Porter Public Library;
    Get Your Board Fundraising 10-21 12:00 PM; Is Starting a Nonprofit Right
    for You? 11-18 12:00 PM — read from the live site's Apps Script feed
    10-09-26); the public page side by side with the website; one registration
    through the Sign Up dialog, a second for another session, a repeat of the
    first that the near-duplicate hold should catch; the Registrants tab,
    Submission Admin and the portal rail; the CRM records; the test registrant
    removed, the three sessions kept. **Runs after the Sunday page**
    (#39/#41). Verified from here 10-09-26 16:52: production's public calendar
    holds **0** upcoming events and the library 10 recordings; the website's
    feed holds the three above.
    **Two findings while writing the page, both to settle before the redirect:**
    (a) **both public sign-up doors tell the visitor "Check your email for the
    confirmation" and nothing is sent** — the only email a registration
    triggers is Zoom's (off everywhere) and the confirmation email is Track D
    D3, not built. Either D3 lands first or the wording changes; recommend D3.
    (b) **the Duration list has no 75- or 90-minute choice** (5, 10, 15, 30,
    45 min, 1, 2, 3 h — `CEvent.duration.options` on crm-test 10-09-26, the
    same list the shared control defaults to), and both live webinars run
    75 minutes; the test enters them as 1 hour. Fix is a one-line CRM plan
    adding 4500 and 5400 to the field's options, at a Sunday slot.
    **Decision for Doug:** the five-week in-person series is one entry on the
    website and one event on the page; check-in and attendance are per
    event, so five sessions in one record means one check-in list for the
    series. One event per session (five, each with its presenter) is the
    alternative; recommend it once the test has run, not before.
    Also open from the plan: during the parallel weeks a visitor who registers
    on our page for a **webinar** gets no Zoom join link (Zoom is off), so
    the website keeps taking registrations until the redirect.

34. **The worker reads its mail switches only at start-up, from the
    environment** (found 2026-09-23, reviewing the deployment guide before the
    first real chapter). `worker.py` decides `inbound_on` (the info@ poller) and
    `comms_store` (Gmail sync) around lines 300–318, before the `/setup`
    override layer is loaded at ~399, and never re-evaluates them. So
    `GMAIL_SYNC` / `OPS_MAILBOX` set at `/setup` never start either loop on the
    worker, restart or not — while `/setup` shows them as in force. Cleveland
    never saw it because both overlays set both as environment variables.
    **Worked around for chapters, not fixed:** `scripts/rehearsal/render_spec.py`
    now puts every Google and mail setting in the spec, and guide steps
    11.14–11.18 confirm at `/setup` rather than set there. The real fix is to load
    the boot overrides before those decisions (as `core/boot_overrides.load_at_boot`
    does for the web process) or to re-evaluate them on each settings refresh —
    a runtime change, so it ships dark and is reviewed on crm-test first. Until
    then, `/setup` should not offer these two as live-editable on the worker.
    **Related, owed:** Lakeside's `APP_ENCRYPTION_KEY` was minted by the old
    `render_spec.py` as `secrets.token_urlsafe(32)`, which is not a Fernet key
    (inferred from the script, not checked on the deployment). If so, Lakeside's
    `/setup` refuses every secret. Nothing is stored encrypted there, so it can
    be replaced with a valid key without loss.

33. **Production's `APP_ENCRYPTION_KEY` was published in plain text** (found
    2026-09-23, preparing the v0.231.1 cut). `11e1fed` (09-14, v0.229.1)
    committed `.do/app.prod-crm.yaml.bak-20260914-0100`, a backup of the
    production overlay carrying the key in plain text on web and worker, and
    the repository is public. `.gitignore` covered only the two live overlays.
    The key alone does not open anything: it decrypts the secrets `/setup`
    stores in production's database, so it matters together with a copy of that
    database. **Ruled 2026-09-23 (Doug, option A): replace the key and re-enter
    every `/setup`-stored secret.** Done in the repository: the three `.bak`
    files untracked (kept locally) and `.do/*.bak*` ignored. **Owed, Doug's
    hands:** generate a new key, set it on production's web and worker and in
    the local `.do/app.prod-crm.yaml` (or the next `doctl apps update` puts the
    old one back), redeploy, then re-enter each secret listed at `/setup`. The
    old key stays in public history by choice (history was not rewritten); once
    replaced it is worthless. The other two backups held only DigitalOcean
    `EV[…]` values.

31. **A settings-store test reads the developer's own `.env`** (found
    2026-09-13). `tests/test_settings_store_pg.py::test_override_round_trip_and_
    history` asserts the override history is exactly `["30", "25"]`; with a real
    `.env` present it sees the entries the surrounding tests wrote and fails.
    **Reproduced on v0.228.1**, so it predates the v0.229.0 store change and is
    not caused by it. Invisible in normal runs — the whole file is skipped
    without `TEST_DATABASE_URL` — which is exactly why it rotted unnoticed.
    Same class as the playlist test repaired in v0.225.1. Fix is to scope the
    assertion to the key under test rather than the whole history table.


29. **Cleveland's two live apps misreport which promotion they are running**
    (2026-09-13). Production and crm-test both carry `RELEASE_TAG=v0.217.0` in
    their overlays while running 0.226.0, so `/healthz` names a promotion six
    releases old — the exact "previous promotion as if it were the new one"
    failure the two stamps exist to prevent. **v0.228.0 changes what fixing it
    means**: the tag now travels in `release-tag.txt` and an environment
    variable overrides it, so the overlay line is no longer a thing to refresh
    but a thing to remove. **The decision is what Cleveland should then
    report.** Both apps track `main` with `deploy_on_push` on, so once the
    variable is gone they report `releaseTag: null` except at a cut commit —
    which is honest (continuous deployment is not a named promotion) but is a
    change from what the fleet console was told to expect. The alternative is
    to move Cleveland onto the `release` branch, which is the "take
    `deploy_on_push` off Cleveland's three apps once the train is trusted" step
    Phase 2 already owes and is a larger change than a stamp fix. Doug's call;
    nothing is broken while it waits, beyond the misreport itself.
    `scripts/set_updates_policy.py <app-id> --status` shows the current state
    of any of the three.

28. **Three Cleveland defects the Lakeside dress rehearsal found** (2026-08-31).
    All three surfaced while standing a throwaway chapter instance up from
    crm-test's configuration
    (`prds/chapter-network/rehearsal-2026-08-31/coverage-record.md`); none is
    chapter work.

    - **Two visible "CBM" strings on the public client-intake form** — the
      served page for a non-Cleveland deployment still reads *"How did you hear
      about CBM?"* and *"I consent to receive marketing communication from
      CBM."* Phase 0 treated `CBM` as an identifier; these two are content an
      applicant reads. Sweep them into `{{org}}` (or a neutral phrasing) and
      extend `tests/test_shared_branding.py` to catch a bare `CBM` inside
      visible text. Ten CRM field *labels* carry it too (*CBM Email*, *CBM
      Client*, …) — a CRM-side question, noted in the chapter record, not here.
    - **`Analytics Admin Team` has no role attached on crm-test** (nor does
      System Administration Team). A user whose only team is Analytics Admin
      holds no CRM read grant at all; Cleveland's analytics users happen to sit
      in other teams too. Decide what the role should be and attach it on both
      CRMs.
    - **The `crm.config` structural-admin account on crm-test does not survive
      the nightly reset.** Created 2026-08-27 for the `espo-crm-changes` skill;
      users reset unless re-baselined (`SANDBOX-RESET.md`), and its login is
      refused today. ~~Recreate it and re-baseline~~ — **recreated 2026-09-07**
      without an admin login, from inside the container: a PHP script run by
      `docker exec -u www-data espocrm php` bootstraps EspoCRM's `Application`,
      creates the `admin`-type user and hashes a password minted on the droplet
      (the skill's `SETUP.md` has the recipe). Login verified (`whoami`: all
      five probes 200). **Re-baselined the same evening** (seeder re-run →
      `purge-deleted --apply` → `baseline --apply`, golden captured
      2026-09-07 23:31 UTC), so the account now survives the 04:00 UTC reset.
      Closed.
    - **The roles standard's crm-test capture is stale** (2026-09-07). A
      database re-read of `role` / `team` / `role_team` — saved as
      `prds/chapter-network/roles-standard/crmtest-capture-2026-09-07/`, the
      2026-08-31 rehearsal record left untouched — differs from the 08-31
      capture in ~60 cells across eight roles, only one of which is the User
      grant above. Several are the differences doc's "production wins" rulings
      having been applied (`ClientMentorIntakeRole.User`, `OpenApi`,
      `Partner Manager Role.Team`); others are not obviously ruled
      (`Mentor Role.CConversation` read all → own, `CCommunication` create
      no → yes, `Mentor Administration Role.auditPermission` yes → not-set,
      `Standard User` field locks dropped). Teams and attachments are
      identical. **Owed: Doug rules which side is right, cell by cell**, before
      the standard is re-captured or applied anywhere.
    - **The Client Assignment Role cannot assign a mentor on its own**
      (found 2026-09-07 on Lakeside; fixed there the same day). Assigning writes
      the mentor's login User into `CEngagement.assignedUsers` (and the same
      list on the Contact, CClientProfile and Account), and EspoCRM's link check
      — identical in 9.3.4 and 10.0.6 — refuses that unless the acting user can
      **read** every User being linked. The role, the only one attached to the
      Client Administration Team, grants nothing on `User`, so a member of that
      team and no other gets `403 No foreign record access for link operation
      (CEngagement:assignedUsers)`. Cleveland never saw it because every Client
      Administration Team member on crm-test is an admin or also on the Mentor
      Team / Mentor Administration Team, whose roles carry User read — Kitty
      Cat passes only through her Mentor Team seat. **Doug's ruling: the role
      becomes self-sufficient — `User: read all, edit own`** (the shape prod's
      `ClientMentorIntakeRole` already has), applied by
      `scripts/migrate_client_assignment_role.py` (idempotent, merge-only,
      dry-run by default). **Lakeside: applied and proven 2026-09-07** — a
      throwaway single-team user read the mentor's User as 403 before and 200
      after, then was deleted. **crm-test: applied and proven the same day**
      (same throwaway-user test, 403 → 200), after `crm.config` was recreated
      from inside the container — `role` is a KEEP table, so the grant itself
      survives the nightly reset. **Owed:** (a) production at the Sunday
      17:00 UTC slot — the step-by-step is
      `client-assignment-role-user-grant-crm-handoff.md` (standing page with
      copy buttons: https://claude.ai/code/artifact/2bc5ad86-efa4-4618-ab0c-43adce3ae882); the
      outside-in proof is `scripts/probe_user_read_grant.py`;
      (b) a ruling on the roles-standard drift the re-read exposed — see
      `prds/chapter-network/roles-standard/crmtest-capture-2026-09-07/`; (c)
      the app-side 403 wording — the user saw a generic "security error", and
      the role name it needs is knowable.

27. **The Email Guide's published copy has drifted from the repo**
    (2026-08-26, found by the first live run of `scripts/publish_docs.py`).
    `email-executive-summary.md` is 6963 characters in the repo against 6682 on
    the site. The manifest already marks it `check_only` — the published copy
    was written for that site's audience — so the checker reports the gap and
    refuses to publish over it. **The decision owed is whether those ~280
    characters are deliberate.** If they are, the entry keeps its note and the
    drift is permanent noise on every run; if they are not, reconcile the two
    and make the entry publishable. `data-model.md` needs no decision: it is
    HTML-authored on the site with PNGs replacing the mermaid blocks, so it
    cannot be compared at all and is synced by hand
    ([[data-model-erd-published]]).

26. **Two live CRM defects the chapter conformance check found** (2026-08-21).
    Both surfaced by the first run of `scripts/preflight_crm.py` against the two
    live instances, and both are Cleveland defects rather than chapter work —
    recorded here so they are not stranded in a planning document. Context:
    `prds/chapter-network/phase-1-crm-config.md` § *Measured, 2026-08-21*.

    - **Production holds `MentorAssignmentNotice` TWICE.** The app looks email
      templates up **by name**, so which of the two a member of staff actually
      sends after an Assign or Reassign is arbitrary, and the two may differ.
      Delete or rename one in the prod CRM, then re-run the check. crm-test holds
      2 templates and prod holds 5, so the two CRMs diverge on templates as well
      as roles — templates are the one surface nothing was watching.
    - **Prod drifts on one managed option list, in ORDER only.**
      `sync_form_options.py` inside the prod container exits 1 on
      `CMentorProfile.howDidYouHearAboutCBM`: the same nine values in a different
      sequence. No value would fail to store; the only effect is the order of a
      dropdown on the volunteer form. Worth noting *why* it has no obvious fix
      today — one static `options.js` serves both deploys, so "which order is
      correct" has no answer until the code is the truth, which is what ruling 4
      in the chapter plan reverses.

    The five `Event*` templates the same run found missing on **both** instances
    are already tracked under item 19 as an events blocker, not duplicated here.

23. **The training sandbox — done, with four residuals** (2026-08-22). crm-test
    now doubles as CBM's training sandbox and release-test environment on top of
    its existing job as the pre-production review gate, and the nightly reset
    that keeps those three from ruining each other is **live in both halves**:
    the CRM at 04:00 UTC (droplet cron) and the app database at 01:00
    America/New_York (the worker, `SANDBOX_NIGHTLY_RESET`). Purged, seeded,
    deepened to 194/194 fields and 62/63 relationships on the showcase records,
    contained (`check_containment.py` reports 0 blocking issues), baseline
    captured and the restore proved end to end. Docs: `SANDBOX-RESET.md`
    (engineers), `training-guide.md` (trainers, also published to the docs
    site), `demo-records.md` (the data reference).

    What is still owed:

    - **A separate Google Workspace for the test environment** — Doug's
      direction 2026-08-22, deliberately not urgent. Containment today works by
      *preventing* sends; a test tenant would let them happen inside an isolated
      boundary, which is what release-testing calendar, email and mentor
      provisioning actually needs. The six config changes it implies are
      tabulated in `SANDBOX-RESET.md` § *The eventual fix*.
    - **The Submission Admin queue is empty**, so `/ops` demos the screen and
      not the workflow. Filling it means POSTing the public intake forms so the
      whole capture pipeline runs, then re-baselining.
    - **`CActionLog` (94 rows) and the native `Email`/`Document`/`Meeting`/
      `Call`/`Task` entities** are still outside the API key's grants — no
      delete on the first, no read on the rest, so their contents were never
      inspected. The native email tables are truncated on every reset, so
      nothing accumulates, but nobody has looked at what was in them.
    - **Documents have no demo data** and must not get any until the sandbox
      Drive is exercised — that part is now safe (its own shared drive since
      2026-08-22), so this is just work not yet done.

## Smaller follow-ups from the 2026-07-24 partner migration

**Not defects — Doug's ruling 2026-08-16.** The audit that came out of the
company-link work flagged three prod records as incomplete. They are
*accurately* incomplete, and are to be left alone:
- **The Villages- Sheffield** (partner) has no company because **CBM has no
  company for them yet** — not because the link was lost.
- **key Bank** (funder) has no company and no manager assigned because **the
  manager isn't known yet**.
- **Fatherhood Initiative - Cuyahoga County** has no partner manager (item 2
  below), which stays open for a different reason: its crm-test manager has no
  prod mentor profile to point at.

Do not re-raise the first two as data errors, and do not "repair" them — an
empty company on a partner/funder now renders as "—" and is fixable in the app
(v0.198.0) whenever the real information arrives.


2. **Fatherhood Initiative – Cuyahoga County has no partner manager on prod**
   — its crm-test manager (Tom Mendelsohn) has no prod CMentorProfile. Assign
   an owner in Partner Management / the CRM. **Since v0.197.0 this is doable in
   the app**: Partner Management → the record → Details → Partnership panel →
   Edit → *Partner manager*. It still needs a prod `CMentorProfile` to point at,
   so the choice is a different manager or building Tom's prod profile first.
3. **The 3 new prod partner records carry no Team** — the intake API user
   can't read Teams on prod, so the Partner Management Team stamp was skipped
   (Fatherhood Initiative, Global Cleveland, Sea Change + their Accounts). If
   partner-manager visibility relies on team-scope reads, set the team in the
   CRM UI.
4. **Prod "SBA - Cleveland" partner lists Korin Green (ECDI's director, with
   her @ecdi.org email) as its primary contact** — looks misfiled; verify and
   correct in the CRM.
5. **Fatherhood Initiative account's website field holds an email address**
   (`cuyahoga-fatherhood-initiative@jfs.ohio.gov`, copied as-is from
   crm-test) — fix in the CRM UI if wanted.

## Data cleanup

- **Lakeside: two engagements on a mentor profile with no login**
  (2026-10-24). Repairing Jordan Mentor's three-profile fault removed the
  login from `LMentor Mentor1`, whose engagements *Lori Client1* and *Iva
  Brito* now have a mentor nobody can sign in as; the worker's stamp
  reconciliation warns on them every pass (`profilesWithoutUser: 2`).
  Rehearsal data, harmless. Fix when Lakeside is next used: reassign both
  in Client Administration, or give that profile a login. Also noted
  there: the 50 profiles and bbmentors.org users are the Boston HubSpot
  rehearsal load.

- **Nine production partner records have no company linked** (found
  2026-10-11 by the ownership count for #40: 22 of 31 `CPartnerProfile`
  rows carry a `partnerCompanyId`). Not looked into: which nine, whether
  the company exists unlinked, or whether the record is a programme with
  no organisation (Doug's 2026-08-14 ruling allows that). A read-only
  listing first; the Details tab's "+ New company" picker is the repair
  path for any that should have one.

10. **Two prod CBM members have no linked Contact — and one has no mentor
    status** (found 2026-07-28, probing the birthday roster; both CRMs read
    read-only). On **production**:
    - **Sharon Rose** (Active, has a login; profile `6a47dc983b1894ec6`)
    - **Anita Khayat** (**mentorStatus empty**, has a login; profile
      `6a637b874fcd0e913`)

    The Contact is where a member's personal details live, so an unlinked
    profile means no email/phone/address on the member record, `/mentorprofile`
    refuses every Contact-side save (readable 400 before any write), and they
    can never be greeted on their birthday. Both should already read
    **Incomplete** on Mentor Administration's completeness badge. Fix in
    `/mentoradmin`: link their Contact (create one if none exists) — a staff
    save then runs `reconcile_user_links` and stamps the User on both sides.
    Anita's empty `mentorStatus` is a second gap: with no status she is greeted
    on her own birthday but never **announced** to CBM (the announcement is
    limited to current-member statuses) — set her to Active if that's what she
    is. Context: `birthday-greetings.md`.

9. **Intake-receipt redesign — CRM-side finish** (2026-07-27; app arc
   COMPLETE and converged — see the CLAUDE.md Current-status block). Three
   Doug-side items, both CRMs unless noted:
   - **Delete the old `reason` and `status` fields** on Intake Submission in
     Entity Manager (`cintake-submission-redesign.md` §6) — the migration is
     verified on both environments, nothing writes or reads them anymore.
   - The **§7 live pass** when convenient: a test form submission (watch it go
     Received → Completed in Submission Admin AND on the CRM receipt), an
     outside email to info@ (a Held-Email receipt exists in the CRM before
     anyone touches it), and a Discard-with-reason (who/when/why on the
     receipt).
   - Delete the live-probe receipt **ZZTEST `6a66f5b4bbe3805ee`** (crm-test).

7. **Partner Accounts carry a bogus industry sector** (found 2026-07-25).
   `Account.cIndustrySector` used to default to "Agriculture, Forestry, Fishing
   and Hunting", and it stuck on 7 of 8 crm-test partner Accounts — including
   Key Bank and Global Cleveland. The **default is now cleared on both CRMs**
   (verified `default=None` 2026-07-25), so new records are fine, but the
   already-stored values are wrong and now **visible**: v0.153.0 shows the
   company's industry on the partner/funder Overview rail. Doug is correcting
   these by hand in the CRM.

## Other follow-ups

52. **PHP2Shell aftermath (CVE-2026-109618/9, patched 10-22-26).** All five
   PHP servers on DigitalOcean patched by Doug with
   `scripts/patch_php2shell.sh` (runbook
   https://claude.ai/artifact/Jo5zAXQF7HrEHfv3a2RMX4): crm-test and
   production to PHP 8.4.27 / EspoCRM 9.3.10; Boston and Lakeside to PHP
   8.4.27 / EspoCRM 10.0.10; cbm-docs to PHP 8.5.12 / BookStack v26.09.2
   (verified from the site's own header, 12:36). Production's CRM was
   unreachable 39 seconds (16:01:08–16:01:47 UTC); every app recovered
   with no errors in its logs. Follow-ups:
   - **The CRM compose files are now pinned** to `espocrm/espocrm:9.3.10-fpm`
     (Cleveland) and `10.0.10-fpm` (Boston, Lakeside). The bare `fpm` tag is
     EspoCRM 10 — never re-pin Cleveland to it without an EspoCRM 10 ruling.
     A later EspoCRM security release means re-running the script with the
     new tag.
   - **Database dumps left on each CRM server** at
     `/root/pre-php2shell-20261022-*.sql.gz` (production 226 MB, Lakeside
     49 MB, Boston 34 MB, crm-test 1.9 MB), plus
     `docker-compose.yml.pre-php2shell` in `/var/www/espocrm`. They hold
     personal data: delete them once the patched CRMs have run a week.
   - **EspoCRM versions after the upgrade are inferred, not read** on
     production, Boston and Lakeside (the script's version read failed; the
     containers serve normally, which the image allows only after its
     upgrade step). Confirm at Administration → About on each.
   - **Lakeside decision:** it is kept but costs patching like this; tear
     it down if the rehearsal (TASKS R11) is not coming.

6. **Re-save the session whose notes were lost to the pasted-image failure**
   (found 2026-07-24, fixed in v0.148.0). Prod CSession `6a604b7b26efd8e3f`:
   the 04:37 UTC save 500'd in the CRM ("Data too long for column
   'session_notes'" — a pasted image as base64), so those notes never stored.
   After the v0.150.0 deploy, re-enter/re-save the notes — pasting the image
   inline now works (v0.150.0 stores it as a CRM attachment). Live check while
   there: the pasted image dims briefly, then the save succeeds and the image
   renders on the Overview feed, the session view, and in the EspoCRM UI.

## CRM prerequisites outstanding

**Marketing Admin Role: `User` read all, edit own — crm-test DONE 10-22-26,
production and Boston owed** (ruling 78). Without it a marketer can make
only themself a campaign's owner; handing it to a colleague is refused
("read access to the User record this COutreachCampaign links to").
`scripts/migrate_outreach_roles.py` carries the grant (`scripts/outreach_roles.sh`
wraps it). On crm-test the grant was already held when Doug's dry run read
it at 12:50 — inferred, not checked: a parallel session's `--apply` picked up
the uncommitted line from the shared working tree. Live-passed there 12:51
as Mark Marketing (handed to Sharon Rose, unchanged save writes nothing).
Production at the Sunday slot from inside the web container; Boston with its
release. Campaign Management is dark on both, so nothing breaks meanwhile.

**`CActionLog.record` cannot point at an event — crm-test DONE 2026-10-07,
production and Boston owed** (found 2026-10-07 in the crm-test web log during
the Phase B pass). Applied on crm-test by `scripts/migrate_actionlog_record_entities.py`
(dry-run by default, idempotent, ships in the image for the production
container), read back, and proven by a probe `CActionLog` row with
`recordType: CEvent` that the CRM accepted and that was then deleted. On
production and Boston: the same script with `--apply` from inside the web
container, at the Sunday slot or any time — it is additive and the app
feature-detects nothing here. The parent link's entity list is
Account, Contact, CEngagement, CMentorProfile, CClientProfile,
CPartnerProfile, CSponsorProfile, CSession — no `CEvent`, no
`CEventRegistration`. So the `CActionLog` half of EVERY Event Administration
action (Event Created / Updated / Sponsors Updated, attendance, check-in) is
refused with *400 Field validation failure, field: record* and logged as a
warning; the stream note half still posts, so the history is on the record
but not in the reporting table. Best-effort by design, so nothing fails for
the user. Fix: add `CEvent` and `CEventRegistration` to the entity list of
`CActionLog.record` on crm-test, production and Boston (Entity Manager →
Action Log → Fields → record → Entities), then confirm one event save stops
logging the warning. Production's entity list is inferred to match.

**Partner sponsorship of events becomes many-to-many, and two campaign
fields** (ruled 2026-10-07; plan: `prds/mailing-list-and-event-sponsorship-plan.md`;
the hand removal of `partnerHost` has its own step page and a data check,
`scripts/check_partner_host_removed.py`, which prints `OK` once the old link is
gone and the new one points both ways
§ 5 Phase A, § 6). `CEvent.partnerProfiles` ↔ `CPartnerProfile.events`
replaces the single `partnerHost` / `hostedEvents` link (removed — metadata
only, the column stays; production's events carry no host today).
`CEvent.noticeCampaignId` and `CEventRegistration.noticeCampaignId`, varchar.
**Handoff: `cevent-partner-sponsorship-crm-handoff.md`. crm-test COMPLETE
2026-10-07** (fields, link, the one demo host carried, verified as the org-wide
key; the hand removal of `partnerHost` done by Doug at 12:05 and confirmed by
`scripts/check_partner_host_removed.py`). Then
production at a Sunday 17:00 UTC slot, then Boston with the release that
carries the code. The application reads neither link until Phase B ships.
**Ruled 2026-10-07:** the Marketing Admin Role gets `read: all` on
`CPartnerProfile` and `CSponsorProfile` — applied on crm-test; production and
Boston owed with their Phase A apply, and the roles standard capture
(`prds/chapter-network/roles-standard/prod-capture-2026-08-31.json`) must gain
the two cells when production does, or the conformance check reports crm-test
as drifted.
**Phase C designed 2026-10-07** (plan § 11, `MAILING-SETUP.md`): one
developer application per Constant Contact account per deployment, redirect
address `{APP_BASE_URL}/api/setup/mailing/callback`. **Ruled 2026-10-07:**
crm-test connects to a separate Constant Contact account of its own
(plan § 11.11, option A; runbook § 0a creates it). Nothing of Phase C is
built; Doug's section 0a + 1 of the runbook and the Phase C build can run
in parallel. **2026-10-08: Doug has no access to the organisation's Constant
Contact account yet.** Decided not to defer: crm-test's trial account
(runbook § 0a) and the build need no such access. **Prerequisite for
production's half only:** access to the real account as the
organisation-owned Constant Contact user — production's developer
application, its connection, and the one-time migration all wait on it.
The Phase C build was handed to a separate session on 2026-10-08. **crm-test's
separate Constant Contact account was created by Doug on 2026-10-08**
(runbook § 0a, after its sign-in address was corrected — the vendor's old
developer sign-in page is a 404). **Runbook § 1 done the same evening:**
the TEST developer application exists with the crm-test redirect address,
Authorization Code/Implicit flow and Rotating Refresh Tokens (read back from
its details screen); API key and client secret in Doug's password manager.
**Phase C built 2026-10-09 in the setup session** (§ 11.9 steps 1–3:
v0.243.0 deployed dark to crm-test and production 02:10; v0.244.0, the push
and pull, committed). Next for crm-test: Doug runs runbook §§ 2–4 from the
standing page (the first browser pass, and the first secret ever stored from
/setup on a live deployment). **Live pass 2026-10-09 (Doug, crm-test):** §§ 2–3 passed — the client
secret stored from /setup (the first live secret through that path), Connect
round-tripped, connected as the trial account; § 4 dry run read 0 (correct:
no sandbox Contact was opted in), `scripts/sandbox_mailing_optin.py` ticked
three, the plan listed them, apply created *Event notices* and imported the
three, verified at the vendor. Four of the five inferred shapes answered
correctly (list lookup/create, list members, status read, JSON import);
the fifth (`remove_list_memberships`) runs the first night the reset clears
the ticks. **Still owed:** the pull's unsubscribe path has never run live —
a staff user cannot unsubscribe a contact at the vendor (only Subscribed /
Temporary Hold); proving it needs a real recipient (Doug's own address as a
contact, a test campaign from the trial account, the unsubscribe link
clicked, then the pull dry run). § 11.9 step 4, the one-time migration
script (production only).

**Production's `CEngagement.description` → wysiwyg conversion** (added
2026-08-31) — **DONE 10-11-26 20:32** with the funder-notes conversion (#47
(d)): `scripts/convert_notes_wysiwyg.sh` converted both fields in one run,
and the Client Administration pass as a non-administrator matched. Boston is
owed with #47 (e). It is the switch that turns Client Administration's
Notes column rich on production (the app feature-detects the field's type per
load, so nothing else is needed); crm-test's conversion is done and verified.
The handoff's crm-test commands were verified against that droplet only —
confirm production's paths before running, and repeat the non-admin
Attachment-create check there afterwards, because roles drift between the two
instances.

**The prod CRM's Outbound Emails "From Name" may still say "Cleveland Business
Mentoring"** (with `-ing`). Flagged as a Doug-side item in the v0.131.0
changelog on 2026-07-21 — *"fix to 'Cleveland Business Mentors' in
Administration → Outbound Emails so CRM-native sends match (crm-test is already
correct)"* — but never tracked, so it is unknown whether it was done. Surfaced
again on 2026-08-20 when the same wording turned up in seven places in the app's
own public forms and was ruled a copy bug.

Worth closing for two reasons: it is the name on every **CRM-native** send
(password resets, `sendAccessInfo` welcome emails, workflow notifications),
which the app's `{{org}}` token does not reach; and under the chapter
architecture it is one of the database-half rows the config applier will have to
own (plan § *CRM configuration as a build artifact*). **Check first** — this may
already be fixed.

*(Moved here from CLAUDE.md 2026-07-28 during the CLAUDE.md slim-down. Each is a
CRM-side build/grant the app already feature-detects or degrades around — none
block a deploy.)*

24. **The grant entities — `CGrant`, `CGrantDeliverable`, `CGrantReport`**
    (2026-08-23, IN PROGRESS, and **the first attempt needs redoing**). The
    three entities on crm-test are named **`CCGrant` / `CCGrantDeliverable` /
    `CCGrantReport`** — EspoCRM prepends the `C` itself, and the handoff told
    Doug to type `CGrant`. All three are bare BasePlus shells (stock fields
    only, no custom fields, no links, no records), so **delete and recreate is
    clean** — handoff §0/§2. Type `Grant`, not `CGrant`.

    **`GRANT-CRM-FIX-RUNBOOK.md` is the ordered sequence to follow** — delete,
    rebuild, verify, grant roles, check in the app. State re-read live
    2026-08-24 04:23 UTC: still the three bare `CCGrant*` shells, zero records
    (the 04:00 reset truncated their tables), nothing else built.

    Worth knowing for planning: the reset log shows it truncates records and
    then **rebuilds the schema from live custom metadata**, so entity/field/link
    definitions SURVIVE the nightly reset — only records inside them go. The
    schema can be built any evening; test records cannot outlive the night.

    Either build path works: the rewritten handoff has per-field steps and a
    box-by-box table per link, or `scripts/migrate_grant_schema.py --apply` does
    §3–§5 through the API with no dialog involved (dry-run by default, and it
    verifies each link's direction afterwards). Role grants stay a UI step
    either way. Full build spec, in Entity Manager vocabulary and with each Create
    Link dialog step in its correctly-inverted box:
    **`cgrant-entities-crm-handoff.md`**. Six links —
    `CGrant.sponsorProfile`, `deliverables`, `reports`, `CContribution.grant`,
    `CGrant.fundedEngagements` ↔ `CEngagement`, `grantManager` — plus Sponsor
    Management Team create/read(All)/edit and **no delete** on all three.
    crm-test first, then prod, with an enum-option parity check between them.

    Two fields were added to the handoff *after* Doug began, because building
    the app side surfaced the need: **`CGrantDeliverable.currentValue` and
    `.currentNote`** — manual measurement has nowhere to record progress before
    the reporting engine exists, so without them a deliverable can state a
    target and never show how it is doing. Also changed there:
    `deliverableStatus` and `nextReportDue` should stay **editable**, not
    read-only.

    The app degrades cleanly against any subset of this: `grants_available()`
    fails closed, and every field is filtered against live metadata before it is
    served, so a missing or differently-named field simply drops out of both the
    form and the whitelist. Nothing is blocked; the tab just says the entities
    aren't built yet.

25. **`CRating` — the rating engine's one entity** (2026-08-23, not started).
    Spec: **`crating-entity-crm-handoff.md`**. One entity plus three links, and
    the role grants carry a rule rather than a preference: **Mentor Team reads
    its own with NO edit and NO delete** — the person being rated can never
    alter or remove a response about themselves. Mentor Administration reads all
    and edits (that is how an abusive comment gets redacted); the org-wide API
    key creates (the respondent is a client or attendee with no CRM identity).

    §2.3 (the `parent` link letting a rating point at a session *or* an event)
    is the one step written without being able to read the dialog — it names the
    metadata that must result and gives a two-ordinary-links fallback. Take the
    fallback rather than fighting the dialog, and say which way it went.

11. **`Held-Duplicate` AND `Held-Company` options on
    `CIntakeSubmission.intakeStatus`** — **crm-test DONE 2026-10-07** through
    the applier (`crm-plans/intake-status-held-options.json`, fingerprint
    a2e87df8d798, read back from metadata and seen by the org API key).
    **Production owed** at a Sunday 17:00 UTC slot: the same plan file, run
    from inside the prod web container per the runbook. Handoffs for the
    manual route: `cintake-submission-duplicate-status.md`,
    `cintake-submission-company-status.md`. Two notes: (a) since v0.238.1 the
    receipt engine re-reads the option list within a minute of a miss, so a
    running web/worker picks a new option up with no restart (before that it
    read the list once per process); (b) the live enum carries a stray
    empty-string option `""` from before, left alone.
12. **prod Mentor Role: `CMentorProfile` edit = `all`** — crm-test has it, prod
    has `own`, which 403s "+ Add CBM contact" (co-mentor linking) for every
    non-admin mentor. v0.174.0 added an app-side admin escalation as the second
    layer, but Doug ruled fix both sides.
13. **prod sponsor-team role: `CContribution` create / read(All) / edit, NO
    delete** — done on crm-test 2026-07-21, still TO DO on prod before the
    Contributions tab is used there. Eyeball enum parity while in the CRM.
14. **`documentsFolderUrl`** (CEngagement + Contact) — handoff
    `documentsfolderurl-crm-field.md`. DOC-08 write-back is feature-detected and
    inert until it exists.
15. **prod field parity with crm-test** — confirm these exist on production
    (each is feature-detected, so the feature simply stays dark until then):
    `CSession.sessionAiSummary` (`csession-ai-summary-field.md`),
    `CMentorProfile.preferredMeetingProvider` + `zoomPersonalLink`
    (`cmentorprofile-meeting-fields.md`), `CEngagement.lastContactDate`
    (`clastcontactdate-field.md`).
16. **Partner / Funder domains on prod** — the `Partner Management Team` and
    `Sponsor Management Team` roles need the profile entity readable at **team**
    scope, existing records backfilled with the team, and the intake API role
    granted **Team read** AND **Assignment Permission = all** (until then the
    intake team-stamp is skipped with a WARNING — and with Team read but no
    assignment permission it is *refused*, 403 "Assignment failure", failing
    the whole partner/sponsor create: exactly what crm-test did on 2026-10-07
    after the roles standard gave it Team read. Grant both together). Same list for the session-tool CRM prereqs generally: `CSession`
    create + read-own/edit-own, `assignedUsers` enabled on `CSession`, and the
    `CSession` name formula must be **keep-if-present**.
19. **Meet transcripts — three Google-side changes, none done** (re-probed
    2026-07-27: a delegated token minted fine for `calendar.events` but was
    rejected `unauthorized_client` for `meetings.space.created`, so the DWD scope
    is definitely still missing): (a) Admin console → Meet video settings →
    Transcription ON for the OU; (b) add `meetings.space.created` to the service
    account's DWD row (the field REPLACES — keep the existing scopes; client id
    109317126943210877831); (c) enable the **Meet REST API** in GCP project
    `espcrm-498315`. **Do NOT set `MEET_TRANSCRIPTS=true` before (b) exists** —
    every Scheduled-session save would show mentors a "transcription failed"
    notice. Re-probe recipe + the local SA key path are in
    `csession-transcript-fields.md`.

22. **One prod Gmail message can never be ingested** (gmail id
    `19f298a147e3ba38`). Its subject trips `CConversation.name`'s
    `$noBadCharacters` validation pattern, which exists on both CRMs. The
    field-length half of this class was fixed CRM-side (widened 255→500) and a
    resync recovered the other 7 messages; this one remains. The fix would be
    app-side subject sanitizing on conversation create — deliberately not built,
    since it is a single message. It now surfaces as a dead-letter alert rather
    than silent loss ([[prod-ccommunication-field-length-drift]]).

## Live verification owed

55. **Company website rules — live cases owed** (v0.236.0, v0.237.0,
    2026-10-07; moved here from `CLAUDE.md` "Current status" 10-20-26).
    Both verified by tests only. (a) v0.237.0: "+ Add partner" on crm-test
    for a company whose name exists with another website — expect the
    refusal message naming the existing company. (b) v0.236.0: a funder's
    company submits the partner form on crm-test — expect `cCompanyType`
    to read `Sponsor, Partner` afterwards.

56. **Performance review fixes — live checks owed** (v0.245.0–v0.248.0,
    2026-10-09; moved here from `CLAUDE.md` "Current status" 10-20-26).
    Verified by tests and local timings only. (a) v0.248.0 receipt sweep:
    the first production sweep's summary line after deploy — `updated`
    near 0, and `differing keys:` names whatever still differs (the fix is
    inferred until then). (b) v0.247.0 Gmail scopes: the production worker
    log shows "scopes reused" at debug, one "scopes rebuilt (…)" an hour,
    and the CRM calls per pass falling from about 400 to single figures.
    (c) v0.246.0 metadata cache: a record page's CRM-call count drops on a
    second open within a minute. (d) v0.245.0 connection pool: the same
    pages on crm-test feel faster and the worker log still reaches its
    Gmail passes.

41. **Topics on events (v0.242.0, Track F F1) — live pass DONE on crm-test 10-09-26; production and Boston owed.**
    *10-18-26 23:22: production's apply is section 2 of the Events Production Test page (#42); read from the container 10-18-26 23:05, `CEvent.topics` is still absent.* **PRODUCTION CRM DONE 10-18-26 23:3x** (plan `1a404fc9c337` applied and verified; the copy wrote eleven events, read back as the org key). The non-admin pass done 10-18/19-26 (seven events saved with topics as Doug's regular login). **Production complete.** Boston still owed.
    Doug's ruling 10-08-26: no user-entered topic; an event carries several
    curated topics (`CEvent.topics`, multiEnum). Feature-detected, no switch.
    **crm-test's CRM side is done 10-09-26 03:34 UTC**: `scripts/plans/
    cevent-topics.json` applied by the shipped applier (fingerprint
    `1a404fc9c337`) and read back as the org key; `scripts/migrate_event_topics.py`
    run (dry run, then apply). **The nightly reset empties crm-test's
    `topics` values** (column rebuilt from files, rows restored from the
    snapshot), so the copy is re-run from the repository before a pass.
    **Live pass done 10-09-26 03:50–03:59 UTC by Doug as Mark Marketing** from the
    step page below — every step matched (verified in the web log: the three saves answered 200 at 03:51, 03:52 and 03:53 UTC (AI Tools for Small Business, Reading Your Own Financials, Pricing for Profit), the library read with each of the two topic filters 200, the event page 200 at 03:58, no 4xx or 5xx in the window; the CRM read-back was lost to the 04:00 UTC reset, which ran one minute before it). One step of the page was
    wrong, not the feature: a library card's title plays the recording by
    design, so the eyebrow check opens the event page by address (rev 1.1).
    ~~Owed: (a)~~ Done: (a) the **live pass as Mark Marketing** from the step page
    https://claude.ai/artifact/Me5JXig7rzCzy9c6RwvMNi (private, written 10-08-26;
    crm-test reported v0.242.0 at 23:47 on 10-08-26, so it can run): Topics as a tick list where Topic
    stood, no way to type one, two topics saved and shown on the Overview
    and as two grid chips, a recording with two topics offered under both in
    the public library and found by either, its page's eyebrow naming both,
    an event with no topic still saving. (b) **Production** at a Sunday slot
    from inside the web container: the plan, then the copy (ten published
    recordings expected) — folded into the Sunday step page
    https://claude.ai/artifact/1KzCM3LbjyvGWp4k2BXP23 (rev 2.0, *Track F Production
    Apply*: section 2 steps 11–15, section 5, section 6 step 4). (c) **Boston** with its next release. Design:
    `prds/events/CBM_Events_Topics_Design.md`; handoff
    `cevent-topics-crm-handoff.md`.

39. **Presenters on events (v0.241.0 / v0.241.1, Track F F4) — live pass DONE
    on crm-test; production and Boston CRM owed.** *10-18-26 23:22: production's
    apply is now section 2 of the Events Production Test page (#42), which
    supersedes the Track F Production Apply page; read from the container
    10-18-26 23:05, `CEventPresenter` still answers 404.* **PRODUCTION CRM DONE 10-18-26 23:3x** (plan `5a78484e6b9c` applied and verified, role script applied and read back, API key lists `CEventPresenter` 200); the switch and the non-admin pass DONE 10-18/19-26 (six presenter entries on four production events as Doug's regular login). **Production complete.** Boston still owed. The code ships off
    (`EVENT_PRESENTERS`) and feature-detected. **crm-test's CRM side is
    complete 2026-10-08** (`scripts/plans/cevent-presenters.json` applied and
    read back; `scripts/migrate_presenter_roles.py` applied — Contact create +
    read, mentor-profile read, the new entity, **Assignment Permission `all`**;
    org key reads `CEventPresenter`). **Live pass done 2026-10-08 21:10–22:27
    by Doug as Mark Marketing (Marketing Admin Team, non-admin) and Joe Mentor**,
    from the step pages https://claude.ai/artifact/RrS6SvEtMFNx2dTPckPkaZ and
    https://claude.ai/artifact/Pb5RFr7k5Rn2nzWCn7UpQK (private); every step
    confirmed by Doug and by the server log and a CRM read: mentor copy of
    biography, title and photo; photo replaced on the event only (profile
    untouched); guest created once, typed Presenter, created by Mark; duplicate
    refused; reorder; remove; the same guest reused on a second event with no
    second Contact; both event pages with the cards and the photo routes; the
    cross-event photo 404; the switch on and off. **Two defects found and
    fixed by the pass:** the role needed Assignment Permission `all` (applied,
    script updated — a role that creates a record the app leaves unassigned
    needs it), and a new guest's typed title was lost because `Contact.title`
    is a read-only mirror of the account-contact role (v0.241.1, title copied
    onto the entry — pushed 2026-10-08 22:34, all three apps report 0.241.1). Owed: (b) **Production**: plan
    + role script at a Sunday slot (`cevent-presenters-crm-handoff.md` § 5),
    then the switch at `/setup` — **step page written 10-08-26 (rev 2.0 on 10-09 also carries #41's topics steps; titled *Track F Production Apply*):**
    https://claude.ai/artifact/1KzCM3LbjyvGWp4k2BXP23 (private; console commands with
    expected output, the switch, a non-admin pass on two unticked check
    events, the CRM reads, the clean-up). **Prerequisite: production on
    v0.241.2**, the build that ships the applier (`scripts/apply_crm_plan.py`;
    the skill's copy under `.claude/` was never in a container) — **pushed
    10-08-26 23:05; production and crm-test reported 0.241.2 at 23:07.** The
    page can run at the Sunday slot. (c) **Boston** with its next release. (d) The
    bare `CEvent.presenters` link is unused and still present on every CRM;
    removing it is a separate human decision. (e) **Design follow-up for
    Doug:** a guest's title and company live on each event's entry and do not
    carry to a second event (the Contact holds neither) — decide whether a
    second add should copy from the person's latest entry. (f) Still owed
    from the pass: the wording of the red message when the event save was
    refused twice at step 3.18 (01:13) before succeeding; the server logged
    only the two 400s. Design: `prds/events/CBM_Events_Presenters_Design.md`
    (§ 11 as-built). Next-session kickoff: `prompts/track-f-session-2026-10-08.md`.

38. ~~**An Internal event's join link cannot be set in Event Administration**~~
    **Built 2026-10-07 as v0.240.0** — `virtualMeetingUrl` carries
    `editable_when=("audience", ("Internal",))`: the editor shows a Join URL
    box under Place & capacity for an Internal event, and `_writable` accepts
    the value only when the record as saved is Internal (a Public event's
    posted-back value is dropped, never written over Zoom's). Verified by
    tests only; the live case is an Internal event on crm-test, Join URL typed,
    Join online shown on the member page. Original finding, kept for the
    record: (found 2026-09-30 while writing the F5 live pass). `virtualMeetingUrl`
    ("Join URL") is app-managed in `events/config.EVENT_FIELDS` — Zoom sync
    fills it, and Zoom is for Public events only (D2 of the F2/F3 design). So
    the F5 join-link rule (design § 5, decision D2) can only ever fire for a
    link someone typed into the CRM record by hand; the staff guide today says
    "paste your own meeting link into its description", which the member page
    renders as prose, not as a **Join online** fact. Decision for Doug: make
    the Join URL editable in the editor for Internal events (Zoom keeps owning
    it for Public ones), or drop D2's fact and rely on the description.
    **Ruled by Doug 2026-10-07 (on Claude's recommendation): the Join URL
    becomes editable in Event Administration for Internal events only;** it
    stays read-only for Public events, where Zoom owns it and would overwrite a
    typed value the day it is switched on. Build owed: one conditional field in
    `events/config.EVENT_FIELDS` (app-managed unless audience is Internal), the
    write whitelist to match, a guide line in `event-administration.md`, and
    the staff guide's "paste your own meeting link into its description" line
    replaced. ~~Not yet built.~~ Built.

37. ~~**The portal events rail and member page (v0.235.0, F5) — built dark,
    never seen.**~~ **Live pass done 2026-10-07** by Doug on crm-test as Joe
    Mentor (Mentor Team only) and Mark Marketing (Marketing Admin Team), from
    the step page https://claude.ai/artifact/47kkLsCn5xTSDK56akg9W1 (private):
    the rail beside the tiles with no width cap, the 30-day fold, both switches
    surviving a sign-out and a second browser, Register from a row and from the
    page with the one-line confirmation, Cancel, the member page's graphic and
    its registered/unregistered states, a signed-out deep link signing in and
    landing on the event, a made-up id and a team-limited event both answering
    "That event could not be found", the Team mark for the inside account, and
    `CEventRegistration` source `Portal` — every step matched. **One defect
    found and fixed (v0.239.1, committed, not pushed):** the member page blamed
    the public-pages switch for a Public event that merely had no slug
    (crm-test's seeded webinar; saving it in Event Administration gave it one).
    **The phone strip was NOT exercised on crm-test** — the first version of
    that step sent Doug into Chrome's developer tools and he stopped; it was
    verified instead in a stub harness at 390px (strip shown reading "Next: …
    · 2 more", panel hidden, no horizontal scroll, tap opens the rows and the
    fold line, tap closes) and at 1400px (no strip, two columns, `max-width:
    none`). **Switched on in production by Doug 2026-10-07 22:50** after
    0.239.1 deployed; he confirmed the rail displayed, and from here the member
    page route answers 200 (it 404s while the switch is off). Still owed:
    Boston with its next release. **Resolved for Cleveland.**

36. **CoMentors column and On-Hold as active (v0.234.0 / v0.234.1) — live on
    both environments, never seen as a non-admin** (2026-09-29). Verified by
    tests and one org-wide-key read against crm-test (26 mentors, Joe Mentor
    and Matt Mentor at 1 each). Owed: open Client Administration → Available
    Mentors on crm-test **as a Client Administration user who is not an
    admin**, sort by CoMentors, confirm those two show 1 and no row shows "—"
    (a "—" means that role cannot read `CMentorProfile.engagements`); click a
    name and confirm the popup's stats line carries CoMentors. Then production:
    a mentor with an On-Hold client shows one more Active and one less Available
    than before.

35. **Event audience and display time (v0.233.0, F2 + F3) — reviewed live on
    crm-test 2026-09-30; production done 2026-10-07; Boston owed.** Doug ran the review as
    two real non-admin accounts (Mark Marketing, Joe Mentor): the editor's
    conditional controls, the Shown column, an Internal event limited to a team
    seen by a member and hidden from an outsider, the public page refusing the
    Internal event (404), and a Public event held back until its display time
    and appearing once it passed — all confirmed, and cross-checked from here
    against the live CRM and public API. Not reviewed: portal registration (no
    button until F5). Still owed, in order:
    1. **Ask the CRM team what `CEvent.eventReleaseDate` was made for** (the
       07-25 handoff's unanswered question). Ruling D1 reuses it as the display
       time; if someone claims it, stop and bring it back to Doug.
    2. ~~Live review on crm-test as real non-admins~~ — **done 2026-09-30**
       (above). Only the portal registration
       (`POST /api/portal/events/{id}/register`) remains unexercised live; it is
       F5's Register button that will drive it.
    3. ~~**Production CRM**~~ — **done 2026-10-07**: Doug applied it from the
       production console (step page https://claude.ai/artifact/EoSQ9EuKC4oWPFYWvpxQRe,
       private); verified 21:54 from inside the container as the org-wide key
       — all five fields present, `eventReleaseDate` already existed,
       `registrationSource` offers `Portal`. Doug reported the conformance
       check unchanged and the editor check matched (10-07-26 evening): the
       Publishing panel shows Audience and Reach, and Internal reveals Limit to
       teams and Takes registrations. **Production is complete.** The
       read-back step as first written used `curl`, which the container lacks,
       and then shell-eaten quotes; corrected twice (page revision 1.2).
       Originally: at a Sunday 17:00 UTC slot, from inside the web
       container: `scripts/migrate_event_audience_schema.py`, runbook
       `cevent-audience-display-crm-handoff.md`. Confirms on the way whether
       production has `eventReleaseDate` (inferred, not checked).
    4. **Boston**, when it takes v0.233.0: the same script, and set
       `CHAPTER_KEY=boston` at `/setup` — the default is `cleveland`, and a wrong
       key puts Cleveland into Boston's reach. (Boston's spec predates the
       setting; `scripts/rehearsal/render_spec.py` now writes it for every
       chapter built from here on.)
    Nothing is visible to members until F5 builds the portal list; the public
    pages are unchanged until someone sets an event Internal or gives it a
    display time.


**De-Clevelanding (v0.205.0–v0.206.0): partly verified live, the rest still owed.**

Confirmed on **production** by fetching the served pages on 2026-08-20, after
the push: `/volunteer/`, `/info-request/`, `/assignments/`, `/mentorsessions/`,
`/directory/mentors/` and the **portal root `/`** all render
"Cleveland Business Mentors" in the title, the footer, the public-form prose and
the `cbm-org` meta, with **zero unsubstituted `{{` tokens**, and `/healthz`
reports `organization`. The portal root matters most of those: it is one of
three pages served by a **direct read** rather than the static mount, so it
would have shipped a raw `{{org}}` had the rewrite been missed there.

Reading the live headers in the same pass turned up a real gap in the branded
path (it honoured `If-None-Match` but not `If-Modified-Since`, where the
`FileResponse` it replaced honoured both), fixed in v0.205.1. It was first
written up as a shipped regression; a control test against an untouched asset
disproved that — **HTML has never answered `304` through the DO edge**, before
or after, because the edge strips HTML `ETag`s and ignores `If-Modified-Since`.
Two lessons worth keeping: a matching version number is not the same as a
correct response, and a header that looks wrong in production needs a control
on a file the change did not touch before it is called a regression.

v0.206.0 was verified the same way: prod serves `legal-links.js` with the four
production policy URLs, no tokens and no staging host, all four resolving `200`,
and the other shared assets (including the 619KB vendored Jodit) unchanged by
the rewrite being extended to `.js`.

**Still owed**, none of it reachable with an unauthenticated fetch:

- The two remaining **direct-read** pages, which need a signed-in session:
  a sessions record page (`/mentorsessions/record/{id}`) and a directory record
  page (`/directory/contacts/record/{id}`).
- **No flicker**, which only a browser shows — the whole reason the name is
  substituted server-side instead of filled by JS. Watch the browser tab and the
  public forms' prose on a hard refresh.
- The two scripts that read `<meta name="cbm-org">` rather than fetching: the
  **portal birthday card's eyebrow** and the **directory mentor page's tab
  title**.
- Changing `ORGANIZATION_NAME` at **`/setup`** and confirming the pages follow
  **without a redeploy**, then changing it back — the revert path is the one
  with the subtle failure mode (see v0.205.1).

There is **no feature flag** — the safety property is that an unconfigured
deployment renders what it always did — so the rollback is a revert, not a
toggle.

22. **Two-stage mentor provisioning has never run against real Google**
    (v0.204.0, 2026-08-17). The `Accepted-Provisional` → account + group →
    `Provisional` flow is covered by tests and fakes only. Three things gate the
    live pass, in this order:
    - **The All Members group address.** Doug does not have it yet. Until it is
      set (Email Setup, or `GOOGLE_MEMBERS_GROUP`) the group step is skipped
      silently and everything else works — that is deliberate, so the rest can be
      verified first.
    - **The `admin.directory.group` scope** must be added to the service account's
      domain-wide-delegation grant in the Workspace admin console, and the
      delegated admin needs group-admin privilege. Without it the add 403s
      `unauthorized_client` — the same failure shape as
      [[gmail-delegation-needs-licensed-mailbox]].
    - **"Create missing mailboxes"** must actually be on for the environment
      (check `/setup` or Email Setup — the overlays are gitignored). With it off,
      an `Accepted-Provisional` save correctly reports the mailbox missing and
      stops, which is not the intended outcome.

    Then, on crm-test **as a real non-admin Mentor Administration user**, with a
    throwaway mentor name (there is no test Workspace tenant — delete the mailbox
    and the group membership afterwards): save at `Accepted-Provisional` → the
    account is created, joins the group, the temp password is shown, **no** EspoCRM
    User exists, and the record now reads `Provisional`. Then save at `Approved` →
    the login is created against **that same address**, with no second mailbox, no
    suffixed duplicate, and no demotion back to `Provisional`. Also confirm prod's
    `mentorStatus` enum carries both `Accepted-Provisional` and `Provisional`
    (verified on crm-test 2026-08-17; the two CRMs drift). Plan and rulings:
    `prds/mentor-provisional-provisioning-plan.md`.

19h. **The Company record page and the client dashboard section have never been
    opened by a human** (2026-08-16; renumbered from a second "19f" on
    2026-09-11 — the duplicate numbering made a bare reference ambiguous, and
    19f is the event-registration duplicate-hold item everywhere else that
    cites it). Both shipped 2026-07-28 and are covered by
    tests, and the Company route serves on crm-test — but no one has looked at
    either rendering real data. Worth ten minutes as a real non-admin in the
    Mentor Team:
    - `/directory/companies/` → click a company name → the page opens in its own
      tab, Overview shows the CRM-arranged detail, and the **Analytics** tab
      renders the `record-company` starter (people and activity for that
      company) rather than the "no analytics set up" message.
    - Client Management → any engagement → **Analytics**: two sections, the
      engagement dashboard and the client one beneath it. An engagement with an
      empty `engagementClientId` should show only the first, not an error.
    - Both need `ANALYTICS_ENABLED`; record-scoped metrics always run live as
      the user, so an empty panel means the metric found nothing, not a cache.

19i. ~~**The recorded library would go from full to empty at the redirect**~~ —
    **DONE 2026-09-14.** The import ran against production from inside its own
    container: 13 playlist items across the five playlists, 3 of them in more
    than one playlist, 10 created. All ten were reviewed and published with
    topics the same day, so the production library is populated and its topic
    filter offers Business Fundamentals, Finance & Accounting and
    Industry-Specific. `YOUTUBE_API_KEY` and `YOUTUBE_PLAYLIST_ID` now live in
    production's overlay, so a re-run needs no new setup. Original text below.

    **The recorded library would go from full to empty at the redirect — and
    the fix has never been run** (found 2026-09-12 by the first side-by-side
    against the live page). The marketing page's recorded library is drawn
    straight from the **YouTube playlist** by the Apps Script. Our page draws it
    from `CEvent` rows carrying a `recordingUrl`, and crm-test holds **six
    events and zero recordings**, so `/webinars/` currently renders
    "No recordings matched" where the live page shows a populated library.
    Redirecting in that state replaces a whole section of the page with nothing.

    `scripts/import_youtube_events.py` is written for exactly this: it imports
    each playlist video as a past event carrying the recording link, **dry-run
    by default**, **unpublished** on purpose (a video's upload date is not the
    event date, so a human checks each before it can reach the public page), and
    idempotent. It has never been run against the real playlist.

    **Blocked on two values only Doug can supply**, neither of which is in
    `.env` or in either overlay, and the playlist identifier is not recoverable
    from the live page's source (the Apps Script holds it):
    - a **YouTube Data API v3 key** — used ONLY by this script; rendering the
      library derives thumbnails from the video id with no key and no API call,
      which is what keeps a key out of the browser (EV-05, and the reason the
      current page's exposed key gets rotated at retirement);
    - the **playlist identifiers** — there are **five**, not one (Doug,
      2026-09-13): Startup, New Product Development, AI and Tech, Business
      Planning and Strategy, Nonprofit. `YOUTUBE_PLAYLIST_ID` takes them comma
      separated and they are planned as one list, so a video in two of them is
      imported once (v0.225.0).

    Run the dry run on crm-test first and read the plan: the intake API user
    cannot delete, so a bad import is cleaned up by hand.

19f. ~~**Event registration holds a person's SECOND webinar of the day for staff
    review**~~ — **FIXED 2026-09-13 (v0.229.0).** `FormSpec.duplicate_scope_key`
    adds one payload key to the match; event registration sets it to
    `event_slug`, so two different sessions both deliver and a repeat for the
    same one still holds. No value for the key means no hold, never a fallback
    to the broad match. Covered against real Postgres, not a fake. Original text
    below.

    **Event registration holds a person's SECOND webinar of the day for staff
    review** (found 2026-08-17). `_recent_duplicate_id` matches on form slug +
    email inside `duplicate_hold_seconds` (24h), and event registration rides
    the shared pipeline, so registering for two different events on one day
    captures the second as `held_duplicate` — never delivered, no Zoom
    registration, and the visitor sees a normal thank-you. The guard is right
    for client-intake (a re-filled form used to strip links off the first client
    profile) and wrong here. Fix and rationale:
    `prds/events/CBM_Events_Registration_Recognition_Plan.md`. Not urgent while
    `EVENTS_PUBLIC_API` is crm-test-only, but it must land **before** the
    website cutover.

19d. ~~**The events sign-up consent line under-covers what `consent: true`
    writes**~~ — **SETTLED 2026-09-13 (v0.227.0).** Doug chose option (a): an
    active tick on BOTH public doors, naming the three documents and linking
    each, refusing to register until it is ticked. The links ride
    `CBMEvents.config.policies` from the four `POLICY_*_URL` settings, because
    the renderer is served without template substitution. Original text kept
    below for the reasoning.

    **The events sign-up consent line under-covers what `consent: true`
    writes — and this now BLOCKS the redirect** (2026-08-16; re-scoped
    2026-09-11, v0.222.0). The line copied from the live page — *"By
    registering, you are agreeing to receive emails about our webinars"* — is a
    marketing-email statement, while `consent: true` also stamps terms-of-use,
    privacy-policy and code-of-conduct acceptance on the Contact
    (`forms/event_registration/orchestrator.py`). **Both public doors send
    `false`** — the calendar's modal and the per-event page's own form — which
    claims nothing the visitor was not shown but records **no opt-in at all**.
    That was tolerable while nothing public pointed here. Once
    `clevelandbusinessmentors.org/webinars/` redirects to this app it is real
    traffic, so the wording has to be settled first.

    Two options, both small. (a) **A consent checkbox naming the three
    policies**, as every other public form on the site does — unambiguous
    evidence, at the cost of one more click and a visible change to a page
    visitors know. (b) **Consent text under the button** naming the three
    policies with links, no checkbox — keeps one-click sign-up, weaker evidence.
    Claude's recommendation is (a). Note the constraint: the modal's markup is
    emitted by `wp-plugin/cbm-events/assets/cbm-events.js` against the site's
    verbatim stylesheet, and a guard test requires every emitted class to have a
    rule in that stylesheet — so a checkbox in the **modal** means touching both
    contract files, while the per-event page's own form is ours and can carry
    one today. Whichever is chosen, the two doors must agree.

19e. ~~**The public `/webinars/` pages have been driven only against fabricated
    events**~~ — **largely DISCHARGED 2026-09-14.** Doug drove the production
    pages for real: the programme page, Event Administration, publishing ten
    recordings, and the topic filter. Three defects came out of it and are
    fixed (v0.229.1 the empty-enum save, v0.230.0 the topic filter, v0.230.1 its
    ordering and the clear-to-reload). **Still owed: a registration end to end**
    — no `CEventRegistration` exists on production, so the public sign-up path
    has never run there. Original text below.

    **The public `/webinars/` pages have been driven only against fabricated
    events** (2026-08-16; superseded 2026-09-11, v0.222.0). The preview page is
    no longer the thing to check — the real public pages now exist at
    `/webinars/` and `/webinars/{slug}`, and they are what the marketing site
    will redirect to. A browser pass against **fabricated** events found and
    fixed three defects (wrapper scoping, a broken logo image, a backwards date
    line), so the layout is proven; what is not is any of it against **real**
    crm-test data, as a real visitor.

    The pass, once v0.222.0 is deployed to crm-test:
    - Open `/webinars/` there and compare both panels with
      `clevelandbusinessmentors.org/webinars/` side by side, at a desktop width
      and on a phone. crm-test's seeded events carry **no slug** (they were
      written straight into the CRM rather than saved through the app), so
      **create one event through `/events` first** — that is what generates a
      slug, and without one a title renders as plain text and has no page.
    - Click that title through to `/webinars/<slug>` and check the graphic, the
      overview and syllabus, and the facts rail.
    - Register once from the calendar modal and once from the event page's own
      form, with obvious test data. Both create a genuine Contact +
      CEventRegistration — delete them afterwards.
    - Confirm an **unpublished** event's page 404s rather than rendering empty.

19c. **Events Phase 6 is built but three of its four parts have never met their
    external service** (2026-08-16). All are off everywhere; nothing is at risk
    until each is switched on, but none of it is proven:

    - **6a attendance** — `events/attendance.py` needs a real Zoom webinar with
      real participants. `ZOOM_EVENTS` has never been on in any environment, so
      **Phase 2 is unverified too** and the two have to be tested together: a
      real webinar, real registrants, then confirm the pull marks attended /
      no-show correctly and leaves hand-set attendance alone.
    - **6b follow-up email** — blocked on **five EspoCRM templates**
      (`EventReminder`, `EventRecordingAvailable`, `EventNoShow`,
      `EventMentorCTA`, `EventSurvey`); each send refuses by name until its
      template exists. Also **has no frontend** — the endpoints work but the
      Follow-up tab doesn't call them, so it is API-only today. Never sent a
      real message.
    - **6d YouTube backfill** — never run against the real playlist; needs a
      YouTube Data API v3 key and the playlist id. Run the dry-run on crm-test
      first: the intake API user cannot delete, so a bad import is cleaned up by
      hand.

    **6c reporting is the exception** — built and wired end to end, but every
    surface currently reads empty because no crm-test registration has been
    marked Attended. Setting one attended is the cheapest way to see the
    engagement rollup, the contact history and the programme reports carry real
    numbers.

19g. ~~**Events is still off on production**~~ — **SWITCHED ON 2026-09-14.**
    The schema was probed inside the production container and diffed against
    crm-test: two differences, both harmless (an extra EspoCRM-generated
    `emails hasChildren` link, and a missing default on `attendanceSource`,
    which the app reads as "empty if unset" either way). `EVENTS_ENABLED` and
    `EVENTS_PUBLIC_API` went into the **overlay** rather than `/setup`, because
    both are read at boot and applying the overlay is what restarts the app —
    one operation instead of a settings change plus a restart. Note the first
    attempt silently did nothing: the live app showed no events keys and its
    deployments were all push-triggered, so the apply had never run. Confirm an
    apply by the **Spec Name** in its output — production says
    `cbm-client-intake-prod`. Original text below.

    **Events is still off on production, and switching it on is now most of
    the remaining work** (2026-08-16; re-scoped 2026-09-11, v0.222.0). crm-test
    has `EVENTS_ENABLED` + `EVENTS_PUBLIC_API`; prod has neither, though its CRM
    schema and the `Event Registration` receipt enum have been ready since
    2026-08-09. It stayed off because there was no public site pointing at it.

    That reason is gone: the public programme is a page this app serves at
    `/webinars/`, and the marketing site redirects to it, so there is no plugin
    left to build. What production now needs, in order:

    1. Run `scripts/probe_events_schema.py` inside the prod web container and
       diff it against crm-test (the two CRMs have drifted before).
    2. Set `EVENTS_ENABLED` and `EVENTS_PUBLIC_API` — at `/setup`, which is live
       on prod, so this no longer needs `doctl`.
    3. Confirm `APP_BASE_URL` is set (it is), because that is what
       `EVENTS_PUBLIC_BASE_URL` derives every shared event link from.
    4. Confirm the Marketing Admin Team is who should administer events.
    5. Settle 19d (consent) and land 19f (the per-event duplicate hold) BEFORE
       the redirect is switched on. Both touch what a real visitor gets.
    6. Create the upcoming events in prod `/events` so the page is not empty at
       the swap, then add the redirect on the website.

    Prod's `CEvent` legitimately holds **0 records**, so the first published
    event there will be a real one.


19b. **The v0.198.0 Company picker's CREATE path has never run as a non-admin**
    (2026-08-16). "+ New company" creates the Account through the **intake API
    client** on purpose, because the partner/funder gate roles don't hold
    `Account` create — so an admin test proves nothing (admins bypass ACL). It
    was going to be discharged by repairing the two company-less records, but
    Doug ruled those stay as they are (see the partner-migration follow-ups
    below), so nothing is scheduled to exercise it. **It will be verified the
    first time a real manager adds a company from the Details tab** — if that
    403s, the fallback to the API client is not working and the button fails for
    exactly the users it was built for. Everything else about the picker is
    verified (server payload, save-diff, end-to-end in the preview harness).

20. **Everything through v0.187.0 is DEPLOYED to both environments** (verified
    2026-07-28; only docs commits are unpushed). What is owed is the *live
    eyeball*, not a deploy. Never driven against the live CRM/Gmail/Drive:
    - **The verified-settings path (v0.216.0)** — tests and a stub harness only.
      On **crm-test**, as an EspoCRM admin at `/setup`: (1) set **CRM API key**
      to a wrong value and confirm it is *refused* with the CRM's own 401/403
      message, never stored; (2) set **CRM address** to some unrelated but
      reachable host and confirm it is refused as "not a CRM this application
      can use"; (3) set a real secret (e.g. **YouTube API key**) and confirm the
      row reads *set*, the value never appears in the page payload, and the
      `app_setting` row has `encrypted=true`; (4) toggle **This Settings page**
      off, watch the confirm banner count down, and **let it expire** — the page
      must come back on its own within ~11 minutes with a `revert` row in
      History; (5) repeat and press *It works — keep it* instead. Nobody has
      watched (4) happen for real, and it is the mechanism the whole ruling
      rests on. **First attempt 2026-08-29 (v0.216.1, crm-test): (4) failed at
      the save with HTTP 500 — `Unconsumed column names: encrypted`, the
      history Table missing a column migration 0027 added. Fixed in v0.216.2;
      nothing was stored, so no cleanup. Re-run on v0.216.2 the same
      afternoon: (4) OBSERVED. Set at 15:47:47Z with `revertAt` 15:57:47Z;
      `/healthz` read `settings.page: false`, `settingsVersion 2` within the
      45 s refresh; the sweep reverted it at 15:57:53Z (6 s past the deadline,
      History row `revert` / actor `system` / "nobody confirmed the system was
      still working before the deadline"), version 3, override gone, page
      back to the deployment value. (1), (2), (3) and (5) still owed.**
      **Found on the way — `setup_enabled` is read at boot only** (`core/app.py`
      mounts the router and frontend behind `settings.setup_active` once, and
      nothing checks it per request), so switching *This Settings page* off
      does NOT lock anyone out until a restart; the countdown currently guards
      an outcome that cannot occur without one. Decision owed: a per-request
      gate in `setup/router.py` (404 when `setup_active` is false, taking
      effect within a refresh cycle) so the countdown protects something real
      — or class the key as restart-read. **Ruled and built the same day
      (Doug: per-request gate), v0.216.3:** API and static page both 404 while
      the setting is off, within a refresh cycle. **(4) repeated on v0.216.3
      at 17:57:04Z: page and API 404 within 7 s, held through the deadline,
      back at 18:07:23Z.** Same session, v0.216.3: **(1) PASSED** — wrong key
      refused, "The CRM answered but rejected this key: … HTTP 401", nothing
      stored. **(2) FAILED — example.com was ACCEPTED** (it answered HTTP 404
      and the probe called that "could not reach"; cleared by hand after 11 s;
      the post-apply check missed it the same way). Fixed in v0.216.4; repeat
      (2) there. **(3) blocked on crm-test: the deployment has no
      `APP_ENCRYPTION_KEY`**, so every secret is refused with "cannot be
      stored without an encryption key" — correct behaviour, but it means
      (3) cannot run there until the overlay carries a key (Doug; it is a
      secret, so overlay + `doctl`, never `/setup`). Check prod's overlay
      too before assuming it differs. **(5) PASSED** on v0.216.3 with
      `allowed_origins` (a lockout key whose value is inert here): saved with
      a deadline, `confirm` cleared it — `confirmed: true`, `revertAt` null,
      nothing awaiting — then cleared. **(2) PASSED on v0.216.4** (22:26Z):
      HTTP 400 "That address answered, but it is not a CRM this application
      can use: … HTTP 404", nothing stored. Cosmetic: the detail carries the
      foreign host's HTML body after the status — trim `http_error_detail`
      for non-JSON bodies some day. **(3) is UNBLOCKED as of 2026-09-12**:
      both overlays now carry an `APP_ENCRYPTION_KEY` (a distinct Fernet key
      per deployment, the same key on the web service and the delivery-worker
      within each, applied with `doctl`), so a secret can be stored from the
      page for the first time. The check itself has still not been run — set a
      real secret (`YOUTUBE_API_KEY` is the natural one, since the events
      backfill needs it anyway), confirm the row reads *set*, that the value
      never appears in the page payload, and that the `app_setting` row has
      `encrypted=true`. **Nothing outside the page reports whether the cipher
      loaded**, so this check is the only proof the keys took effect.
    - **The two version stamps (v0.214.0)** — after the R6 `doctl` applies:
      `releaseTag` reads `v0.216.1` on crm-test, `crmConfig.state` reads
      `unstamped` there and `absent` on prod until Sunday's build, then
      `unstamped`.
    - **Editing an engagement from the Client Administration popup (v0.210.0)** —
      the Edit button, its live-metadata enums and its two link pickers were
      verified in a stub harness only, and the pickers are the half that cannot
      be rehearsed there: neither the unit tests (fakes) nor the harness (canned
      JSON) issue a real list request, and this is the same call shape that
      silently emptied every picker in production at `maxSize=500`
      ([[espo-list-maxsize-403]]). As a **non-admin** Client Administration
      team member, on a real intake-created engagement: press **Edit**, confirm
      the **Referring partner** picker actually lists partner profiles and
      **Requested mentor** lists mentor profiles (an empty one is now a genuine
      read-grant finding on that team's role, not the page-size bug), change one
      scalar and one link, Save, and confirm the CRM stored both and the grid's
      Status / Company / Notes columns follow. Then check the two guards that
      only a live CRM exercises: a **required** field left blank comes back as a
      readable message rather than a 502, and the save appears in the
      engagement's stream as an app action. Also confirm the popup opens at 90%
      of the window and the corner grip still resizes it.
    - **The curated link pickers, now that they have options (v0.202.2)** —
      until this release the option list was fetched with `maxSize=500`, which
      EspoCRM 403s, so **every** picker offered only "(none)" for everyone
      including admins. That invalidates the earlier manager-picker sign-off,
      which could only have exercised the stored value. On a real partner and a
      real funder, as a **non-admin** team member: open Details → **Edit** on
      the first panel and confirm the **Company** picker lists the companies
      (~97 prod / 93 crm-test) and the **manager** picker lists mentor
      profiles; change each, Save, and confirm the CRM stored it and the grid
      column follows. If a picker is still empty for a non-admin it is now a
      genuine read-grant finding (Account / `CMentorProfile` on that team's
      role) rather than this bug — the sponsor team's role in particular may
      not read `CMentorProfile` at all.
    - **The events Add/Edit editor (v0.202.0)** — a resizable workspace modal
      with pinned Save/Cancel and the two Content fields on CBMRichText.
      Verified only in a stub harness, but **`/events` is live on crm-test**
      (`/events/api/session` 401s there and 404s on prod), so this can be done
      now. Fold it into the Events Phase 5 pass below: create and edit one
      event, confirm the rich text round-trips to `eventOverview` /
      `eventSyllabus` and renders on the website preview, the Duration select
      still translates into `dateEnd` (a wrong `dateEnd` is the four-hours-early
      class of bug), and the graphic uploads through the new "Choose image…"
      button. Also worth a glance: the page's buttons changed from a white
      outline to the standard navy secondary, since it no longer defines its
      own.
    - **Address paste-parsing (v0.196.0)** — **deployed** on the 2026-08-13
      push and live on both environments; there is no flag, so a revert is the
      only rollback. Verified against a faithful replica of each form shape in
      a browser, NOT against the real pages. What is owed is one live pass on the
      **session tools' Details tab** — the only surface where a State
      `<select>`, disabled shipping inputs and the "Same as billing" mirror are
      all in play at once. Paste a full address into Company **billing** line 1
      with *Same as billing* ticked and confirm shipping mirrors; paste a
      spelled-out state (`Ohio`) and confirm the `<select>` takes `OH`; click
      **Undo** and confirm every box returns, then Save and confirm the CRM
      stored what the boxes showed. Glance at the other five surfaces
      (`/mentoradmin`, `/mentorprofile`, `/directory` edit, volunteer,
      client intake) while you are there. Guide: `address-paste.md`;
      plan: `prds/address-paste-parsing-plan.md`.
    - **Quick add — first non-admin run 2026-10-09 (funder door): refused by the CRM's assignment check; fixed in v0.249.0, re-check owed — see #43.**
    - **Quick add — "+ Add partner" / "+ Add funder" (v0.195.0)** — deployed to
      both environments; `RECORD_QUICK_ADD` gates it and `/setup` can now toggle
      it on either. **The UI is reviewed and signed off** (2026-08-12); what is
      owed is the CRM half. **As a real non-admin partner/funder-team member**
      (admins bypass every ACL this feature depends on), create one of each and
      confirm: the
      Account create lands (it runs through the intake API client), the profile
      is visible in the grid afterwards (team stamp), the contact appears on the
      Details tab, and the manager picker offered a usable list — the sponsor
      team's role may not read `CMentorProfile` at all, in which case the picker
      is legitimately empty and the manager is set later on Details. Then
      re-enter the SAME company and email to prove the reuse path (no duplicate
      Account/Contact, `cCompanyType` gains the type). Only then add the var to
      the prod overlay.
    - **Prod alert-email deep links** — `APP_BASE_URL` was applied to prod on
      2026-08-12 (it had sat unapplied in the overlay), so the next alert email
      and daily digest should carry absolute record links instead of bare
      names. Nobody has seen one yet; glance at the first that arrives.
    - **Analytics record dashboards (v0.187.0)** — open a real Mentor,
      Engagement, Partner, Funder and Contact on crm-test.
    - **Duplicate hold + preferred-mentor dropdown (v0.185.0)** — crm-test's
      roster has only 2 public mentors, neither Active+accepting, so the dropdown
      correctly stays hidden; flip `publicProfile` on a couple of
      Active+accepting crm-test mentors to exercise it.
    - **Co-mentor add as a real non-admin mentor** (`sharon.test`) — v0.174.0.
    - **Mentor permission-teams round-trip** to `User.teamsIds` — v0.155.0.
    - **Partner & Funder review pass** — the Overview rail manager + industry,
      the notes/Discussion splitter, Make primary, the Last Contacted column,
      contact name → peek (v0.153.0 / v0.154.0).
    - **Referred Clients tab** on a real partner (v0.156.0).
    - **Email round two** — forward with a real PDF attachment, grid unread
      chips, the daily digest (v0.157.0); **Other correspondence** reply
      (v0.159.0).
    - **Last Contact auto-advance** on a session save and an outbound email
      (v0.158.0).
    - **Zoom PMI preference** — the first real Scheduled save with the
      preference on (event carries the Zoom link, mints no Meet) (v0.151.0).
    - **Email templates + signatures (the whole ET arc)** — harness-verified
      only, never driven against the live CRM/Gmail.
    - **Google Calendar**: edit→patch, Cancel→cancel-event, and actual
      attendee-invitation delivery (only the create path is live-proven).
    - **Documents Phase 3** — the hand-driven checklist in
      `GDRIVE-DOCS-SETUP.md` Task 6 (assign/unassign grant flow as a mentor,
      `Mentors/` no-grant check, archive/restore against the real drive,
      hand-grant-removal alert).
    - **Reassign Mentor** (v0.81.0) — needs the staff role to carry CSession
      read+edit for the session re-stamp and Note create for the history stamp.
    - **Events Phase 5** signed in as a **real non-admin** Marketing Admin user
      (the browser pass stubbed the session, so the team gate and a non-admin's
      CRM ACL are untested).
    - **Birthday greetings** — nobody has yet watched it fire on a real member's
      birthday. Only 5 of 19 prod members have one recorded, so expect ~5 days a
      year; use `scripts/preview_birthday.py --date MM-DD` to see it on demand.

21. **Test-record sweep in the CRM UI** — the intake API user is create-only, so
    these have to be deleted by hand. Known outstanding on **crm-test**: 3
    `ZZTEST-COMPANYTYPE` Accounts (`6a682c8b3b6038e12`, `6a682c8b788683d2e`,
    `6a682c8bb25b0f76d`); the Fathom probe CSession `6a5f011bce8e19a19`; the
    receipt `6a66f5b4bbe3805ee` (also item 9). On **prod**: 4 `ZZTEST-GMAILPROD*`
    probe records. Older `ZZTEST … GrantCheck` / Stage A/B / provisioning test
    Users may already be gone — the reliable method is a `contains ZZTEST` sweep
    across the entities rather than chasing individual ids. Also on crm-test: the
    duplicate unlinked mentor profile "Doug Bower" (`6a4425f4c82d3f2ec`, alongside
    the real linked "Douglas Bower") and two "Acme Inc" CPartnerProfiles — records
    assigned to an unlinked profile are invisible in the session tools.

24. **Nothing in the grant book has ever run against a real CRM** (v0.212.0,
    2026-08-23) — and it *cannot* until item 24 above is built, which is the
    honest state of it rather than a backlog entry. 36 unit tests and a green
    suite cover the math, the whitelists, the scope gates and the feature
    detection; what no test can cover is the same thing that has bitten this
    repo before — **no test issues a real list request**, and a `maxSize` over
    200 is a 403 that reads as an empty list. The grant paths page at
    `_PAGE` (200), so they are inside the limit by construction; confirm it
    anyway on the first live pass.

    When the entities exist, on crm-test first, signed in as a **real non-admin**
    Sponsor Management Team member (an admin bypasses ACL, so an admin pass
    proves nothing):
    - Switch `GRANTS_ENABLED` on at `/setup` **before** the entities exist and
      confirm the tab shows the "not built yet" panel rather than an error —
      that is the fail-closed path, and it is easiest to test while it is true.
    - Create a grant, then add deliverables of each type. A `Narrative` one must
      show no progress bar at all; a `Numeric` one over its target must clamp at
      100% and read Met.
    - Set a deliverable's status by hand against the arithmetic and confirm the
      typed status wins in the grid.
    - Save an `awardAmount` on a grant whose stored currency is null — the
      backfill is guarding the live defect that 400'd the ledger in v0.123.2, and
      only a real CRM exercises `validCurrency`.
    - Confirm the deliverable rollup is genuinely ONE list request (the grid's
      "N of M met" column), and that a role without `CGrantDeliverable` read
      shows zeroes rather than breaking the grid.
    - Set `firstReportDue` and confirm `nextReportDue` is seeded from it once,
      and that a hand-typed `nextReportDue` is never overwritten.

23. **The Client Administration Company column has never been seen against a
    live CRM** (v0.209.0, 2026-08-23). Status and Company became their own
    sortable grid columns; both were verified in a stub harness, which cannot
    exercise the part that matters. The engagement's own
    `CEngagement.clientOrganization` link is **null on every intake-created
    row** — the Account hangs off `CClientProfile.linkedCompany` — so almost
    every row in the action-needed filter resolves its company through
    `service._fill_company_names`, one read per distinct client profile. What to
    confirm, on crm-test first and then prod, signed in as a **real non-admin**
    Client Administration user (an admin bypasses ACL, so an admin pass proves
    nothing about the read):
    - Intake-created rows show a company, not "—". A whole column of "—" means
      the fallback read is being denied, not that the data is missing.
    - The grid still loads at full size (200 rows) without a visible stall — the
      profile reads are gathered, but there is one per distinct profile.
    - A client with genuinely no company renders "—" and nothing else breaks.

    Blank is also the correct render when the profile read 403s, so the failure
    mode here is silent by design; the app logs a warning per denied profile.

27. **Nobody has watched a *new* calendar invite arrive and be skipped at
    filing time** (v0.208.0, carried forward from the CLAUDE.md status window
    when that block was retired 2026-08-26). The cleanup half is settled — see
    § *Resolved*, "The calendar invites filed as documents are gone" — and the
    matcher itself is proven by it, since the matcher is what selected those 45
    files. What has never been observed is the *live* path: an `.ics` arriving
    on an inbound message and being dropped at the filing step while staying
    visible in **View original**. It is an excluded part, not a non-attachment,
    and that distinction lives only in where the list is applied. Confirm on
    production by sending a meeting invite to info@, then checking the record's
    Documents tab holds nothing new and the message still shows the attachment
    in View original.

40. **The chapter colour file has never been applied to a live deployment**
    (`chapter-colours.md`, 2026-10-07). `CHAPTER_TOKENS_URL` is empty on
    Cleveland, Boston and Lakeside, so the injection in
    `core/branding.render_page` is covered by `tests/test_shared_branding.py`
    and nothing else. Owed: one run of `chapter-colours.md` sections 1–4 on
    crm-test with a throwaway colour file, then Reset (section 6). While it is
    on, look at `/webinars/` and at a second-rank button under the mouse:
    the calendar and library panels keep the marketing site's fixed colours,
    and the second-rank hover colour is hard-coded to Cleveland's dark navy
    (`frontend/shared/tokens.css`, `.cbm-button--secondary:hover`). The hover
    colour is a one-line fix plus a new design token; Doug chose the guide
    over the fix on 2026-10-07, so the fix is still owed.

## Resolved

**RESOLVED 2026-10-24 — #58, the several-profiles guard live pass.** Doug
ran the step page (https://claude.ai/artifact/MjdGx2s9392e5TkzrDvS2p,
revision 1.0) on crm-test 10-24-26 as a non-admin (Joe Mentor): with the
login on Simone Achebe (Paused, no clients, listed first) and on Joe
Mentor (Active, seven clients), Client Management showed Joe's seven rows
and the yellow notice naming both profiles; after the extra link was
removed and the grid refreshed, the notice was gone and the seven rows
stayed. v0.280.0 is live on production and crm-test; Lakeside picks it up
at its next promotion.

**RESOLVED 2026-10-20 — #45, the sandbox re-baseline.** Doug ran the
step page (https://claude.ai/artifact/VSrvvKB49MkmzA2dgHRsfS, revision
2.0) on 10-20-26: v0.266.0 pushed, the four seeders applied, the six demo
links restored from `/setup` → Operations, the baseline recaptured and a
reset proved by hand, the result seen as Mark Marketing. Checked
afterwards (01:00 Eastern): crm-test reports 0.266.0; the outreach
seeder's dry run finds 0 changes after the restore; all six demo link
codes answer 302 to their destinations and the September postcard's first
card opens its landing page (200). The worker's own restore ran at 05:00
UTC the same night after the app-table reset (`sandbox demo links: 6
created, 0 present, 0 skipped` in the worker log), and the codes answered
302 again afterwards. The original item follows.

45. **The training sandbox loses every presenter and partner-event link at
    04:00 UTC, and the demo events had none to lose** (10-11-26, Doug's
    request: demo events with presenters that are also related to a partner
    and a funder). The golden baseline dates from 09-07-26; `c_event_presenter`
    and `c_partner_profile_event` were built after it, and the reset's own log
    names them as the two tables it truncates nightly. **Built (v0.250.0):**
    `enrich_training_data.py` gained `add_event_showcase` — presenters through
    the application's own `add_presenter` (a mentor's biography, title and
    photo copied; a guest `Presenter`-typed Contact created), the partner and
    funder links, `showPresenterBios`, and `topics` (also emptied nightly);
    `seed_training_data.py` gained `stamp_management_teams` (#40a);
    `deepen_showcase_records.py`'s partner relate named the host link removed
    on 10-07 and now names `sponsoredEvents`. All feature-detected, idempotent,
    merge-only; dry runs clean against crm-test 10-11-26 (27 enrichment
    changes, 8 partners + 6 funders missing their team). **Owed — Doug's
    morning after a reset, with no release test running:** the three
    `--apply` runs, the audit and containment checks, then on the droplet
    `purge-deleted --apply` and `baseline --apply`, then `reset --apply` by
    hand and the event, partner and funder opened as Mark Marketing, Partner
    Manager and Sally Sponsor (`SANDBOX-RESET.md` § *Re-baseline*).
    **Step page, every command with a copy button:**
    https://claude.ai/artifact/VSrvvKB49MkmzA2dgHRsfS (Doug's private page,
    written 10-11-26). **When:** the morning after a nightly reset — the CRM
    half runs at 04:00 UTC, which is midnight Eastern on daylight time (23:00
    the evening before once clocks go back on 11-01-26) and the app half an
    hour later, so any time after 01:05 Eastern — on a day with no release
    test running, because the capture freezes whatever is on crm-test. Two
    things the dry run could not prove: (a) whether the intake API key's role
    may CREATE `CEventPresenter` — the org key reads it (handoff § 2); a 403
    on the enrichment apply is the stop-and-report case (the
    `run_with_admin.py` launcher supplies only the `ESPO_ADMIN_*` variables,
    which this script does not read); (b) a tester's half-made record left
    on crm-test at capture time becomes pristine. **Still owed 10-18-26**,
    and the gap has grown: the droplet's baseline is still 09-07-26 and the
    reset of 10-18 truncated **ten** tables newer than it —
    `c_engagement_partner_profile`, `c_event_presenter`,
    `c_outreach_campaign`, `c_outreach_campaign_event`,
    `c_outreach_campaign_partner_profile`, `c_outreach_touch`,
    `c_partner_profile_event`, `c_partner_profile_mentor_profile`,
    `c_prospect`, `c_sponsor_profile_mentor_profile` — so the prospect and
    outreach arc's seeder stage (#51) should land before the same recapture,
    or the recapture is done twice. **That stage is built (v0.266.0,
    10-20-26):** `scripts/sandbox/seed_outreach_data.py` (seventeen leads,
    six campaigns, ten touches, two converted companies and three contacts,
    an engagement's two referring partners, the two additional managers —
    which covers four more of the ten tables), run as the CRM administrator;
    and the demo campaign links, which live in the application's database,
    are put back by the worker after every reset with fixed codes
    (`campaigns/sandbox_demo.py`, Doug's ruling 10-20-26, option 1) or on
    demand at `/setup` → Operations → *Sandbox demo campaign links*. **Applied
    on crm-test 10-20-26 04:17 UTC** (52 changes, a second dry run 0, read
    back under the org key; the November postcard's list selects exactly the
    three leads `demo-records.md` names), so it survives only until 04:00 UTC
    on 10-21-26 unless the recapture runs today. **The step page is rewritten
    for it** (revision 2.0, 10-20-26 00:25, same address): push, the four
    seeders with today's dry-run counts, the Operations job, the recapture,
    the check as Mark Marketing.


**RESOLVED 2026-10-12 — an info@ submission "that created a partner" never
did, and nothing was lost.** Doug asked why the partner from reference
`020223a3` could not be seen. The row is an inbound info@ email (a funder's
sponsorship-payment notice, 10-02-26), not a partner form; its delivery
created the sender's Contact and an Information Request, exactly its scope.
The "partner" was a staff comment on the row, "Added PNC Bank to Partners.",
written six seconds before Approve. Read as administrator on production:
no Company, partner, funder or Contact named PNC exists; nothing
partner-shaped was created or edited on 10-02/03; the Action Log holds no
partner action; and the commenter is in no Partner Management team and
holds no role that creates a partner profile, so the comment describes
something outside the CRM. No defect. Two lessons kept in
`submission-admin.md`: an email never creates a company, and a comment is
a note, not a record. Follow-up is Doug's: ask the commenter where PNC was
added, or enter PNC Bank as a **funder** (the payment makes it one).
**How it was read:** a submission reference is the first eight characters
of the row id; the production row came from `/ops/api/submissions` under
Doug's portal session, and the CRM-side checks ran as Doug's administrator
session in the browser — crm-test's receipts are emptied by the nightly
reset, so a reference that matches nothing there is a production one.**

**RESOLVED 2026-10-11 — #40: verified live by Doug on crm-test as
sally.sponsor after the v0.250.0 deploy: Funder Management listed all the
sandbox funders (grid read 200 at 16:19 UTC in the web log). The nightly
reconciliation re-heals the sandbox after every reset, so no re-baseline
is needed; the morning-after look is the reconciliation's own log line.
Left behind as a separate data gap: nine production partner records with
no company linked — see the Data cleanup section.**

40. **The training sandbox's funders were invisible to the Funder Management
    demo login** (found 2026-10-07 during the Phase B live pass, section 5).
    Sally Sponsor's role (Sponsor Manager Role, the roles standard) reads
    `CSponsorProfile` at **team**, and none of the six sandbox funders carried
    a team or an assigned user, so her grid was empty while an administrator
    saw all six (administrators bypass ACL). The demo in `demo-records.md`
    ("Open: Harrowgate Family Trust") predates crm-test being brought to the
    roles standard on 2026-09-13, which is the likely moment it broke.
    **Worked around 2026-10-07:** all six funders were put in the Sponsor
    Management Team on crm-test by the configuration administrator (data only,
    no role change). **Owed:** (a) ~~the nightly reset restores the data
    snapshot, so this is gone by morning unless the sandbox is re-baselined~~
    — **the seeder stamps it now** (10-11-26, `stamp_management_teams` in
    `seed_training_data.py`, merge-only, both management teams on every
    partner and funder profile); it holds once the re-baseline in #45 is
    captured; (b) check whether production's funder records carry
    the Sponsor Management Team or assigned users — if they do not, every
    non-admin Funder Management user on production sees an empty grid too, and
    the fix is data (teams on the records) rather than the role; (c) the same
    question for partners, whose role reads at **all** today and so hides
    nothing, but would if the standard ever tightened it.
    **2026-10-11 — counted and built (Doug's ruling, option B):** production
    has 4 funders with 1 in the team and 31 partners with 17 (and 9 partners
    with no company at all, a separate data gap not yet looked at); crm-test
    8 funders with 2, 9 partners with 1 — (a) confirmed, the reset un-teamed
    them. **v0.250.0** (pushed 10-11-26 12:13) adds a phase to the worker's
    nightly stamp reconciliation that merges the domain team onto every
    partner / funder record, its company and its contacts, on every
    deployment, every night — no re-baseline, no console run. **First pass
    ran on deploy, 10-11-26 16:15–16:17 UTC, no errors:** production
    `teamRecords 35, teamHealed 27`; crm-test `teamRecords 17, teamHealed
    14` (the six sandbox funders, their companies and contacts joined the
    Sponsor Management Team, named one by one in the worker log). **Owed:**
    sally.sponsor seeing all eight sandbox funders in Funder Management
    (and again the morning after a reset); the production partner records
    with no company (9) remain a separate data gap; then resolve.


**RESOLVED 2026-10-11 — #43 and #44 verified live by Doug on crm-test from the
step page https://claude.ai/artifact/MrVb46cEZE5cdngyzo4NKZ, every step
matched, confirmed in the web log: "+ Add funder" as sally.sponsor answered
200 at 15:54:30 UTC (10 CRM calls), Wendy Kay's Events tab as partner.manager
200 at 15:55:46, an engagement's Events tab as joe.mentor 200 at 15:56:51.
Still open from #43 (c): whether a team-read funder manager can see the
company on an existing, unowned funder record — that is #40.**

44. **A contact's Events tab in the directory 403'd for every
    non-administrator** (found 2026-10-11 by Doug as Pat Partner, opening the
    contact he had just created through "+ Add partner"): *your CRM role is
    missing read access to CEventRegistration records*. The Mentor Role, the
    Partner Manager Role and the Sponsor Manager Role hold no access to the
    registration record type on crm-test or production, and the tab read the
    registrations as the user — as did the engagement record's Events tab in
    Client Management, which no mentor can have seen work either. **Fixed in
    v0.249.2** (pushed 10-11-26 11:42) by Doug's ruling, option B: the user's
    own read of the contact / the engagement's contacts gates the tab, and
    the history reads under the org-wide key (the partner / funder Events
    tab rule). Step page for #43 and #44 together:
    https://claude.ai/artifact/MrVb46cEZE5cdngyzo4NKZ (private, *Quick-Add
    Live Check*, written 10-11-26). **Owed:** (a) the live check after the
    push — the same contact's Events tab as partner.manager shows the history (empty is fine for
    a contact with no registrations: "no events", not a red message); (b)
    an engagement's Events tab as a real mentor on crm-test, never seen
    working by a non-administrator.

43. **"+ Add funder" as a real non-admin was refused by the CRM's assignment
    check, misreported as a missing Contact grant** (found 2026-10-09 by Doug
    on crm-test as Sally Sponsor; the first run of the quick-add create path
    as a non-administrator, which #20 said had never been proven). The Sponsor
    Manager Role holds Contact create; its Assignment Permission is *not-set*
    on both CRMs, and the contact was created with no assigned user and no
    team, so EspoCRM answered `Assignment failure: assigned user or team not
    allowed` and the app's 403 wording blamed the create grant. **Fixed in
    v0.249.0** (pushed 10-09-26 22:29): the new contact is owner-stamped like
    the profile on both doors, and the hint names an assignment refusal.
    **The v0.249.0 live check (10-09-26 22:36 UTC+4) got one step further
    and found two more defects, fixed in v0.249.1 (pushed 10-09-26 22:52):**
    the contact's company link was refused because the company was unowned
    (`cannotRelateForbidden`, Account read), and the company match ran as
    the user, so each attempt created another same-named Account (three
    "Acme Bank" rows on crm-test, gone with the reset). The match, the team
    lookup and the ownership now ride the API client; see the changelog.
    **Owed:** (a) the live check after the next push — "+ Add funder" on
    crm-test as Sally Sponsor saves, and the funder's Contacts table shows
    the contact;
    ~~(b) "+ Add partner" as Pat Partner the same way~~ — **done 2026-10-11
    by Doug** (a partner for "Acme Bank and Loan" with Wendy Kay as the
    contact saved on v0.249.1 and the contact opened from the directory); (c) the company is
    still created unowned under the org-wide key — whether Sally can see it
    on her new funder record is #40's question, not this one; (d) the orphan
    `Account` "Acme Bank and Loan" the failed run left on crm-test — gone
    with the nightly reset, nothing to do.


39. **RESOLVED 2026-10-07 — Phase B of the mailing-list and event-sponsorship
    plan, the partner / funder pickers and the Events tab (v0.239.0).** The
    client-count fix was pushed the same day (crm-test and production both
    built from 951db7e) and re-checked as Sally Sponsor: Harrowgate → Events
    reads *Became clients 1* on the Pricing for Profit row. Every half of the
    pass has now run as a real non-admin. Still open, tracked elsewhere: the
    `CActionLog.record` entity list (CRM prerequisites) and the hand removal of
    `partnerHost` on crm-test (handoff § 5). Original record: **Live pass run
    by Doug on 2026-10-07 as an administrator: every step matched** — the
    pickers, the save, the CRM record's Partners and Sponsor Profiles panels,
    the Events tab on both records, and production showing Funders only. What
    an administrator CANNOT prove is the role half, because administrators
    bypass ACL: that the Marketing Admin Role's read-all grant fills the
    pickers, that the foreign-record denial is retried as the admin account,
    and that the Events tab counts reach a team-scoped Funder Management user.
    **The non-admin halves were then run by Claude on 2026-10-07 in the
    browser, with temporary passwords on the three sandbox logins (restored by
    the nightly reset):** as Mark Marketing the pickers listed ten partners and
    six funders, a relate and an unrelate both saved with the web log showing
    *retrying as the provisioning admin*, and the CRM record held the links;
    as Partner Manager the Northgate Events tab showed the one event with its
    counts; as Sally Sponsor the Harrowgate Events tab showed TWO events (she
    already sponsored *Pricing for Profit* in the demo data) with registered
    and attended counts — and **"Became clients" read "—" on both**, which was
    a real defect: `CEngagement` has no `contactId`, the lookup 400'd, and the
    programme conversion report had the same latent fault. Fixed in the
    working tree (`primaryEngagementContactId`), **not yet pushed**. **One
    re-check owed after the next push:** Harrowgate → Events as Sally reads
    *Became clients 1* on the Pricing for Profit row (the attendee's
    Brightline engagement postdates it). The original checklist, for the
    record:
    - As a **Marketing Admin** (not an admin — admins bypass the read-all
      grant this exercises): open any event in Event Administration → Edit.
      The *Sponsorship* group shows a Partners and a Funders picker listing
      the profiles. Tick a partner and a funder, Save. Expected: the Overview
      facts show both names; the CRM's own Event record shows them under
      Partners / Sponsors; the stream carries "Event Sponsors Updated". The
      relate ran as the admin account only for the foreign half — check the
      log for "retrying as the provisioning admin". Untick one, Save: it is
      removed, the other stays.
    - As a **Partner Management** user: open that partner in Partner
      Management → Events. Expected: the event row with registered / attended
      / became-clients counts and the totals tiles; "—" only where a read
      failed. Same on Funder Management for the funder.
    - On production (no partner link yet): the editor shows **Funders only**,
      and Partner Management's Events tab shows the "does not link events to
      partners yet" explanation rather than an error.
    Also owed: the hand removal of `partnerHost` on crm-test
    (`cevent-partner-sponsorship-crm-handoff.md` § 5) — the app does not
    read it, so this pass does not depend on it.

- **The company-website hold (v0.238.0) passed live on crm-test** (was item
  39; raised and closed 2026-10-07). Doug ran the partner-form script
  (`Company Hold Test Script`, the standing page): the hold, the *Same
  company* decision (company reused, website unchanged, type gained
  Partner), and the *Different company* decision (a new Account and partner
  record under the qualified name) all behaved as specified. Two things the
  pass found that are NOT the feature: (1) **the crm-test intake API role
  refused the Partner Management Team stamp** — `CustomAppAPIRole` had
  Assignment Permission not-set and the user no teams, so *every* partner and
  sponsor submission on crm-test failed at the profile create once the roles
  standard gave the role Team read (production skips the stamp because its
  API user cannot read Teams — item 16); fixed on crm-test during the pass,
  and production's #16 now owes Assignment Permission = all alongside Team
  read. (2) crm-test's Intake Submission layouts predate the receipt
  redesign (`cintake-submission-redesign.md` §2): the page shows the dead
  `status` field, not `intakeStatus`/`intakeMessage`; Doug is not concerned,
  so it stays as a note. Still unrun: the client-intake variant (the hold
  code path is shared; what differs is only which form field names the
  company). The `Held-Company` CRM option is item 11.

- **crm-test writes attachments again, and the event Overview tab is verified
  live** (was item 32 and the first sub-bullet of item 20; raised 2026-09-16,
  closed 2026-09-20). Two things had to hold together, and both do:
  - **The droplet.** Doug copied `scripts/sandbox/reset_crm_sandbox.py` over
    `/usr/local/sbin/reset_crm_sandbox.py` and ran
    `chown -R 33:33 /var/www/espocrm/data/espocrm/data/upload` once. The repair
    was confirmed **after** the following 04:00 UTC reset (2026-09-18): the
    upload folder was owned by `33:33`, no entry belonged to any other user,
    and the installed script matched the repository copy by checksum. That is
    the half that matters — the fix had to survive a reset, not just precede
    one.
  - **The application.** Doug ran the crm-test browser pass and reported every
    check passing: a graphic uploads through `/events` and the editor shows
    **Graphic saved.**, and the event Overview tab renders the record —
    facts left, graphic and rich text right, a dash in each empty slot.
  Production has no nightly reset and was never affected. The diagnosis is kept
  in memory as `sandbox-reset-upload-ownership`, because "uploads fail on
  crm-test only" reads as an application defect and is not one. One caveat kept
  for the record: the Overview tab's ACL half is only as verified as the account
  the pass used, so a later "fields missing" report starts at field-level ACL,
  not the renderer.

- **The mentor detail popup (v0.220.0) is verified live** (was item 31, raised
  and closed 2026-09-01 — the day it shipped). Doug tested the new UI on the
  live system and reported it working well: the popup renders its panels and
  the assign-from-popup flow behaves. Closed on his report. One caveat kept for
  the record: the item's ACL half (which fields a *non-admin* Client
  Administration user's field ACL hides in the popup) is only as verified as
  the account the pass used — if a staff user later reports "fields missing"
  there, start at field-level ACL, not the renderer.

- **Rich-text images and the signature logo are live and verified** (was item
  29, raised and closed 2026-08-31). v0.218.0 (formatting buttons, Insert
  image, the shared inline-attachment pipeline across the session tools,
  Client Administration and My Mentor Profile) and v0.219.0
  (`ORGANIZATION_LOGO_URL` + the signature editor's Insert-logo button) are
  live on all three apps; crm-test's `CEngagement.description` is converted to
  wysiwyg, so its Notes column is rich; Doug ran the non-admin pass and the
  logo deployment on crm-test the same day and reported everything working,
  including the logo arriving in an external mailbox. The one piece that is
  not done is production's field conversion, which waits for a Sunday slot and
  is tracked under *CRM prerequisites outstanding*.

- **The v0.213.1 `/ops` changes are verified** (was item 28, raised and closed
  2026-08-26). Doug exercised **both halves on crm-test** the day after they
  shipped, and both behaved:
  - Closing an info-request submission whose `CInformationRequest` no longer
    exists gives the ordinary **green** confirmation with the "nothing to update
    there" note, and the row closes. crm-test manufactures this condition on its
    own every night — the CRM is restored at 04:00 UTC, the app's tables not
    until 05:00 — so it is the one environment where the case is easy to reach
    deliberately.
  - The page opens on **Open (not closed)** with the dropdown showing it, and
    the `total` chip clears every filter and brings closed rows back. The
    boot-time `syncFilterSelects()` was the half most likely to be wrong; it
    is not.

  **Not separately re-checked on production, and deliberately not tracked as
  owed.** Neither half has an environment-specific dependency: the write-through
  runs under the org-wide API key on both, and the filter default is identical
  static JS. Worth knowing rather than verifying — prod is the real info@ queue,
  so staff there will notice the front page now opens on open work instead of
  the whole archive.



- **`Analytics Admin Team` exists in both CRMs** (was item 17, closed
  2026-08-21). Nobody had checked; the first run of the rewritten conformance
  check (`scripts/preflight_crm.py`, `ac6f1b4`) reported all **7** teams named in
  `core/config.py` present on **both** instances, which hold 9 teams each and
  **identical lists**. This item was one of three failures that run was predicted
  to find, and two of the three predictions were wrong — the check is what proved
  it. Evidence and the rest of that sweep:
  `prds/chapter-network/phase-1-crm-config.md` § *Measured, 2026-08-21*.

- **The calendar invites filed as documents are gone** (was item 24, raised and
  closed 2026-08-23). Doug ran the cleanup on **production** through `/setup` →
  Operations the same day it shipped, and the app's own job record is the
  evidence: two dry runs (16:48, 16:55 UTC) both planned **45 documents across
  30 records**, and the apply at 16:57 — reason *"Remove existing ics files from
  production system"* — reported **"Archived 45 of 45 document(s)"** with no
  failures. `app_document` now reads 45 `Email attachment` rows archived against
  95 still active, which matches the plan exactly. Every one of those files sits
  in its record folder's `_Archived` subfolder and can be restored; nothing was
  deleted.

  Two things this settles beyond the cleanup itself. The **archive path has now
  run for real, at scale** — it had been exercised only by tests, and crm-test
  could not rehearse it ([[crm-test-app-data-empties-nightly]]). And the
  **v0.208.1 Operations-tab fix is verified live by that same sequence**: the
  16:48 dry run is the one that showed "done" and nothing else, which is what
  surfaced the defect; the 16:55 re-run showed the plan, and only then was it
  applied. crm-test remains unrehearsable and unnecessary here.

- **`CMentorProfile.lastClientAssignedDate`** (was item 24, raised and closed
  2026-08-23). The Date-Time field recording when a mentor was last given a new
  client, shipped feature-detected in v0.207.0 and inert until the CRM caught
  up. **Built on both CRMs**, and the ACL both halves depend on is confirmed:
  - **crm-test** — a live Assign stamped the mentor as
    `doug.bower@cbmentors.org`, a `type = regular` user, so the grant was
    exercised rather than bypassed.
  - **production** — read from the role definitions as admin (a write test
    would have proved nothing, since an admin bypasses ACL): the **Client
    Assignment Role**, the only role attached to the Client Administration
    Team, grants `CMentorProfile` `read: all` **and `edit: all`**, and the role
    carries **no field-level locks at all**, so the new field is not blocked.
    Five of the team's eight members are `regular`, so real staffers exercise
    it. Roles merge by the most permissive level, so nothing attached elsewhere
    can revoke this.

  Prod carries no historical values and needs no backfill — the date appears on
  each mentor the next time they are given a client. The **training sandbox was
  backfilled** (`stamp_last_assigned` in `seed_training_data.py`, from the
  latest `engagementAssignedDate` on the engagements each mentor holds), gained
  two clients assigned inside the last month so **Assigned (30d)** is not zero
  across the roster, and was re-baselined so the nightly restore keeps both.
  Handoff: `cmentorprofile-last-client-assigned-field.md`.

- **Analytics on the record views — the last two surfaces** (was item 0,
  decided 2026-07-28, `prds/analytics-app-plan.md` §17). **Both were built the
  same day the ruling was recorded and the item was simply never closed** —
  found 2026-08-16 while picking it up as new work.
  - **Company** — `44d7562` built the full record page at
    `/directory/companies/record/{id}`: the View Contact shell (Overview +
    Analytics, header/footer, single-tab lock) minus Communications, since
    companies talk through their people. `DirectoryConfig.company_page` gates
    the route mount and the `/session` flag; the grid's row-name click opens it
    in a stable named window while the View pop-up and preview strip stay for
    browsing, exactly as ruling 1 asked.
  - **Client** — no screen of its own, per ruling 2. `sessions/service.py` puts
    `clientProfileId` in the engagement detail payload and the Analytics tab
    fetches the `CClientProfile` dashboard as a second section beside the
    engagement one.
  - Starter dashboards `record-company` and `record-client` seeded in `cf23bf0`,
    so all seven record types now have one.
  - Verified 2026-08-16: 51 directory tests + 21 analytics record tests pass,
    and `GET /directory/companies/record/{id}` serves on the deployed crm-test
    app. What is owed is the eyeball, logged under *Live verification owed*.

- **`test_a_full_event_is_NOT_refused` failed on a date roll** (was item 7,
  found 2026-08-13). The shared `make_event()` fixture hard-codes
  `dateStart: 2026-07-28`, and registration closes at `dateStart`, so from that
  date on the event was refused as closed and the EV-15 "full means waitlisted"
  assertion never ran — the suite's only red line, and a permanent one.
  **Resolved 2026-08-16:** that test now builds its own event 30 days out
  rather than inheriting the fixed date, so it tests capacity again and cannot
  rot. The shared fixture keeps its fixed date, which the date-formatting tests
  depend on.

- **Company links were one-to-one, so a second record silently stole the
  company** (was item 00) — `Account.cCompanyPartnerProfile` and
  `Account.cSponsorProfile` were both `hasOne`, so linking a company to a second
  partner/funder profile *moved* it off the first, emptying that record with no
  error. Found 2026-08-13 from a live partner whose company had been taken by a
  duplicate entered nine hours later. **Resolved 2026-08-14 → 2026-08-16:** Doug
  ruled a company can hold **many** partner and funder records (a partnership is
  often with a programme inside an organisation), and recreated both
  relationships as Many-to-One in Entity Manager — partners on prod 2026-08-14
  and crm-test 2026-08-15, funders on both 2026-08-16. Verified via the API each
  time: no link lost anywhere (removing a relationship never drops the column),
  the link names match across environments (`partnerCompany` /
  `cCompanyPartnerProfiles`, `sponsorCompany` / `cSponsorProfiles`), and a
  functional test on crm-test confirmed two records now share one company with
  neither losing it. `CClientProfile.linkedCompany` stays `hasOne`
  **deliberately** — see the ruling in CLAUDE.md.

- **Events: prod schema migration not applied** (was item 18) — the Events
  change list had been applied to crm-test only, leaving prod short 16 fields,
  3 enum additions, 4 `readOnly` flags still set and the `partnerHost` link.
  **Resolved 2026-08-08:** Doug applied the whole list by hand in Entity
  Manager. Verified by running `scripts/probe_events_schema.py` inside the prod
  **web** container and diffing the output against a crm-test run: all 26 items
  present, and the probe reports "No blocking schema problems found" where it
  previously reported four fields whose values EspoCRM would silently strip.
  Only four differences remain and none are on the change list —
  `CEvent.duration` default 300 (prod) vs 3600, an extra `emails hasChildren →
  Email` link on prod, and empty-vs-unset defaults on `attendanceSource` /
  `followUpsSent`.

  **Two traps this exposed, both now recorded in
  `cevent-entities-crm-handoff.md` §2.4:**

  1. **The probe does not check link naming.** The `partnerHost` relationship
     was created **reversed** — prod had `CEvent.hostedEvents` → CPartnerProfile
     with the foreign link named `partnerHost` — and the probe still reported no
     problems, because it only verifies that the two entities exist and that the
     must-write fields aren't `readOnly`. Only a field-by-field diff against
     crm-test caught it. Diff the two instances; don't trust the clean exit.
  2. **The Create Link dialog inverts what you type.** A panel's Name/Label
     define the link that *points to* that panel's entity, so the link is stored
     on the **other** entity. Building from Event with Partner Profile on the
     right, the LEFT panel Name creates the link on **CPartnerProfile** and the
     RIGHT panel Name creates the one on **CEvent**. Specifying it the intuitive
     way round produced the reversed link twice before the labels
     (`GET /I18n?scope=<Entity>`) settled the mapping.

  **Also settled:** prod's `CEvent` legitimately holds **0 records** — the
  entity was never connected to Google, so CBM's org calendar exists only on
  crm-test (94 rows). This is not an ACL blind spot in the intake API key. It
  also means `publishToWebsite` has nothing to protect on prod yet, and the
  first published event there will be a real one rather than one hidden among
  internal meetings.

- **Account type stamp wrote a field that no longer exists** — found
  2026-07-24 on prod, where `Account.cAccountType` had been removed; all four
  intake orchestrators wrote it, and EspoCRM silently ignores unknown
  attributes, so the type stamp stored nothing. **Resolved 2026-07-28:** the
  Account entity is presented as **Company** and its type field is
  **`cCompanyType`** (Doug). A live probe found `cAccountType` gone from
  **both** CRMs and `cCompanyType` identical on both — multiEnum
  `['', 'Client', 'Sponsor', 'Partner', 'Other']` — so the fix is a straight
  retarget, no feature detection. All four orchestrators now write
  `cCompanyType`, and the sponsor form's value changed from `"Donor/Sponsor"`
  (rejected by the CRM — it is not an option) to **`"Sponsor"`**. The drift
  monitor (`core/schema_contract.py`) was retargeted with it. Verified live on
  crm-test: Client/Partner/Sponsor each stored, `"Donor/Sponsor"` refused.

- **Account-level partner fields duplicated (and contradicted) the partnership
  record** — found 2026-07-24 during Doug's partner review; `cPartnerStatus`,
  `cPartnerContactCadence`, `cPartnerType`, `cPartnershipStartDate` and
  `cPartnershipAgreementDate` were editable on the Company card while the grid
  and Overview read the `CPartnerProfile` twins, and live data had already
  drifted apart (Glide: Account "Monthly" vs partnership "As-Needed"; every
  Account "Prospect" regardless of real status). **Resolved 2026-07-25:** Doug
  deleted all five CRM-side, verified MISSING on crm-test AND prod, and
  v0.153.0 removed the app's references (the Company group is now organization
  type + announcements). The `cIndustrySector` stamped default was cleared in
  the same pass — see item 7 for the stored values it left behind.

30. **Production's `Data Integrity Team Role` is attached to NO team** (found
    2026-08-31 by the § R4 roles capture; crm-test attaches it to Data
    Integrity Team). Members of production's Data Integrity Team currently
    hold no CRM grants from this role — same class as the twice-before
    attachment losses ([[espo-403-diagnosis-merged-team-roles]]). Fix is one
    admin action in production EspoCRM: Roles → Data Integrity Team Role →
    Teams → add *Data Integrity Team*. Verify as a member of that team, not
    as an admin.
