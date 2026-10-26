# Kickoff — M7: Constant Contact per list and the email campaign

Last Updated: 10-26-26 09:20 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. **The plan below is a draft, not yet approved.**
The session's **first reply** states the operating mode and the loaded
`CLAUDE.md` files as usual. It then presents the four stopping points
below and every decision that passes the two-part test and is not settled
here, and **waits for Doug's approval before building anything**. Once he
approves (he may say "run all four stops", as he did for M4, M5 and M6),
work through stops A, B, C and D without pausing, then stop and report.
Pause only for a decision that passes the two-part test and is not settled
below.

**Push state at the time of writing.** v0.288.0 (M5) and v0.289.0 (M6)
were committed and not pushed: Doug was running the M5 live pass on
crm-test, which builds from `main`. Read `git log origin/main..main`
before anything else and say in the first reply what is unpushed. **Do not
push during this session**; Doug pushes. A push redeploys crm-test under
any live pass in progress.

## 1. Read first

1. `CLAUDE.md` (loads itself), then `campaigns/CLAUDE.md` — the bullets
   *Campaign lists* (rewritten by M6), *Phase 4* (the email kind),
   *The lead code*, and *One page, six tabs*.
2. `prds/prospect-marketing/build-plan.md`:
   - § 7e.9, the first half: *A kept-current copy per list* and *The email
     campaign*. **The send report is M9, not this step**, and *Lists
     only*, the campaign page, the grid, *+ New campaign* and *Promote
     this event* are M8 and M10.
   - § 7d.2's **Email** paragraph: the vendor custom field
     `cbm_lead_code` and the address to paste into a notice. Ruling 126
     moved it into M7.
   - § 7e.11 (storage). Its "migration 0034" for the list columns was
     never cut: 0034 to 0037 went to the ladder, the import templates, the
     import lease and M6's lists. **This step cuts migration 0038.**
   - § 7e.12 Draft 8 (the vendor endpoints are inferred) and § 7e.13: the
     M7 line, and the M2 to M6 entries for how a step records itself.
3. `prds/prospect-marketing/rulings.md` rulings 95 (a kept-current copy
   per list), 96 (the send report — M9's, but the pick of the email is
   here), 100 (the strip's *Sent* for an email is the pick), 112 (no
   screen cites a ruling number), 126 (D3's email pieces ride M7). Also
   the Constant Contact rulings 1–7 in
   `prds/mailing-list-and-event-sponsorship-plan.md`, and its § 11 (the
   connection, the push, the pull, § 11.10's unverified items).
4. The code:
   - `core/mailing_sync.py` — the whole module: `audience`, `members`,
     `vendor_unsubscribed`, `build_plan`, `apply_plan`, `run_push`,
     `run_pull`, `mark_opted_out`, `alerts_for`. Today it serves one list,
     named by `MAILING_LIST_NAME`, with its id on the singleton
     `mailing_connection` row.
   - `core/mailing.py` — `MailingClient` (`find_list`, `create_list`,
     `import_contacts`, `remove_from_list`, `activity`,
     `wait_for_activity`), the connection store, the pacing and retries.
   - `campaigns/email.py` — `select_targets`, `build_list`, `sign_off`,
     `push_campaign` (goes), `run_email_cycle`, `mark_as_sent` (goes).
   - `campaigns/audience.py` — `resolve_targets`'s email branch,
     `address_for_email`, `email_consented`, `cbm_emails`. The consent and
     address rule is shared with the push (§ 7e.9).
   - `campaigns/audience_store.py` and `campaigns/lists_router.py`, as M6
     left them; `campaigns/frontend/lists.js` (the list page's top line is
     where ruling 98's *Constant Contact copy* status and *Sync now* go;
     M6 left them out).
   - `campaigns/leadcode.py` (minting and the org-wide-key write rule).
   - The worker's mailing loop (`grep -n mailing worker.py`) and
     `setup/` (the Readiness line for the mailing connection).
   - `campaigns/router.py`'s email routes and the Links tab in
     `campaigns/frontend/app.js`.
5. The tests: `tests/test_mailing_sync.py`, `tests/test_mailing.py`,
   `tests/test_campaigns_email.py`, `tests/test_campaigns_phase4.py`,
   `tests/test_campaign_lists.py`, `tests/test_campaigns_one_page.py`.

## 2. What M7 builds (build plan § 7e.9 first half; § 7d.2 email)

**A list can keep a copy in Constant Contact, and the email campaign sends
to that copy.** Behind a new switch, **`CAMPAIGN_LIST_SYNC`** (read per
request; off ⇒ everything as today). One migration, **0038**.

**Routine choices, to be announced in the first reply and built as
written unless Doug says otherwise:**

- **The sync is the standing list's code, parameterised.** `audience()`,
  `build_plan()` and `apply_plan()` take the people to hold (already
  consent-filtered, through the same rule as `resolve_targets`'s email
  branch, so a chapter member is held at their `cbmEmail`) and the list's
  name and id. The standing *Event notices* list keeps working exactly as
  today; it is not a row in the Lists tab.
- **The columns** (migration 0038, on `audience_list`): `cc_sync` (bool),
  `cc_list_id`, `cc_last_sync_at`, `cc_last_sync` (JSON summary). The
  `system` column waits for M8. The sandbox reset already empties
  `audience_list`; no seeder change.
- **The worker** runs the standing list, then every `cc_sync` list, in
  one pass. `vendor_unsubscribed` is fetched once per pass. Alert keys are
  per list (`mailing_list_<id>_failed`). A dynamic list is run for its
  sync (its members as a campaign would see them); a static list syncs its
  hand rows.
- **The list page**: a *Keep a copy in Constant Contact* tick, the copy's
  status on the top line (last sync, counts, or the error in words), and
  *Sync now* (a route running one list's pass, action-logged, answering
  the counts). A rename renames the copy (`PUT /contact_lists/{id}`, a new
  `MailingClient` method). Retiring stops the sync and never deletes the
  copy. Unticking stops the sync and keeps the copy.
- **The email campaign** (ruling 95): sign-off requires the campaign's
  list to have its copy on, runs *Sync now* for it, and moves the campaign
  to Signed off. `push_campaign` and its `Campaign — <name>` list go.
  The strip then says "Next: send it in Constant Contact to <list>, then
  pick that email here". *Pick the email* lists the account's email
  campaigns sent in the last 30 days to that list (new `MailingClient`
  methods over the email-campaign endpoints; `campaign_data` is already
  granted). Picking stores the id on `COutreachCampaign.vendorEmailId`
  (the field exists on crm-test from the redesign handoff;
  feature-detect it) and moves the campaign to Sent. *Mark as sent* goes.
- **The lead code in the vendor** (§ 7d.2): the application creates the
  custom field `cbm_lead_code` once through the custom-fields endpoint and
  checks it on every push (Readiness says *custom field missing* if an
  administrator deleted it). Every push writes it as the
  `cf:cbm_lead_code` column of the JSON import, minting a code for any
  contact that has none (under the org-wide key, the lead-code rule). The
  Links tab shows each link twice — the plain address, and the address to
  paste into a notice, `{APP_BASE_URL}/c/{link}/[[custom.cbm_lead_code]]`,
  with a Copy button.
- **Every vendor shape not yet called is marked inferred in the code**
  (custom fields, the list rename, the email-campaign listing and its
  per-list filter, the merge tag's spelling). The live send in stop D is
  the check (Draft 8).
- **Names, never numbers, on the screen** (ruling 112).

**Decisions that may pass the two-part test — put them to Doug in the
first reply with the plan, using the consequential decision template, or
state that none does:**

1. **An email campaign before M8.** Sign-off now needs a list with its
   copy on, but the email kind's own rule (`select_targets`, the rule card)
   lives until M8 replaces every rule with ready-made lists. Either an
   email campaign must name a list from M7 on (the rule card stays for the
   other kinds), or the rule card stays for email too and sign-off of a
   rule-built email is refused in words until a list is chosen. Likely a
   real decision: it changes what staff see on an email campaign between
   M7 and M8.
2. **What a built email campaign writes as touches.** Today *Build the
   list* writes Planned touches for an email campaign. With the send
   report (M9) writing one touch per real recipient, M7 can keep the
   Planned touches (and M9 reconciles them), or stop writing them (the
   campaign shows the list's count until M9). Likely a real decision.
3. **Whether the lead's level and phone join the default list fields**
   (owed from M6: its live pass adds them at /setup). Likely routine:
   announce yes, since the ready-made lists of M8 filter on the level.

### Stop A — the sync per list and the store

- Migration 0038; `audience_store.py` gains the columns and their reads.
- `core/mailing_sync.py` parameterised; the worker's loop over the
  standing list and every `cc_sync` list; per-list alerts.
- `MailingClient`: rename a list; create and read a custom field; the
  `cf:` column in the import.
- Tests: `test_mailing_sync.py` parameterised (the standing list
  unchanged, a second list synced, an unsubscribe never re-added, a
  retired list skipped and its copy kept), the custom field created once
  and checked, a code minted for a contact without one.

### Stop B — the API and the email campaign

- `lists_router.py`: the tick, *Sync now*, the copy's status in the list
  answer, rename carried to the copy.
- `campaigns/email.py` and the router: sign-off requires the copy and
  syncs it; *Pick the email* (list and pick); `vendorEmailId`; the moves
  to Signed off and Sent; `push_campaign` and *Mark as sent* removed.
- Tests through `build()` for each route and each refusal in words;
  `test_campaigns_email.py` and `test_campaigns_phase4.py` rewritten where
  they pinned the per-campaign push.

### Stop C — the screens

- The list page: the tick, the status, *Sync now* (ids `ls_`, buttons
  never hidden or disabled).
- The email campaign's strip and *Pick the email* dialog (the page's own
  dialog, never `confirm()`); the Links tab's paste address with Copy.
- The browser check against the real application over the test fakes, as
  M6 did (the scratchpad `serve.py` pattern: `tests/test_campaign_lists.py`
  fakes behind uvicorn, Mark Marketing patched in), with a fake mailing
  client; `javascript_tool` scripts under a second of awaits, one mutating
  action per call.

### Stop D — documents, release and the live send

- `CHANGELOG.md` (read HEAD's `pyproject.toml` first; expected 0.290.0),
  `pyproject.toml` and `uv.lock`, `campaigns/CLAUDE.md` (the *Campaign
  lists* and *Phase 4* bullets, one revision), the root `CLAUDE.md` status
  window (one block in, the oldest out, keep four), the build plan
  (§ 7e.9's first half marked built, § 7e.13 M7, the header revision, a
  change-log row), `OPEN-ITEMS.md` #57, `MAILING-SETUP.md` if the setup
  steps changed. Commit; **never push**.
- Then the live-pass step page, published as an artifact, following the
  Step-by-Step Instructions standard and the memory notes
  [[runbook-never-leave-the-surface-mid-section]] and
  [[steps-name-the-app-and-the-tab]]: every value pre-filled from a read
  of crm-test (parse `.env` in Python, never `source` it). The pass runs
  as Mark Marketing on crm-test's **separate trial Constant Contact
  account** (only Doug's own CBM login can re-authorise it if the
  connection lapsed): tick a list's copy, *Sync now*, see the list and the
  `cbm_lead_code` field at the vendor, sign off an email campaign, send
  **one real email to one address Doug controls** from Constant Contact
  with the paste address in it, pick that email in the app, and follow the
  link to see the lead code resolve. That send is the check of every
  inferred vendor shape; record each one's outcome in the build plan.

## 3. Things this session must know

- **Parallel sessions share this clone and its git index.** Stage files by
  name, never `git add -A`; audit `git show --stat HEAD` after each
  commit; read `git log --oneline -5` before writing `pyproject.toml`,
  `CHANGELOG.md` or `OPEN-ITEMS.md`, and re-read a file right before each
  edit.
- `uv run pytest -q` is the suite (about 4½ minutes; run it in the
  background). `tests/test_comms_endpoints.py::test_disabled_returns_503`
  fails in the full run and passes alone — order-dependent, known.
- **The vendor is paced and rate-limited** (`MailingClient._pace`, the
  retry on 429). A pass over many lists must stay inside the worker's
  cycle; never sync from a web request except *Sync now* for one list,
  and keep that request under a minute (the web process's requests are
  cut off after about a minute).
- **crm-test reverts every night at 04:00 UTC**, CRM and app database
  alike. A Constant Contact list the pass creates survives at the vendor;
  its `cc_list_id` row does not. The next sync after a reset must find the
  copy by name rather than create a second one.
- A local Postgres for the migration: `docker run --rm` of the
  `postgres:16-alpine` image on a spare port, then `alembic upgrade` to
  0037, seed, upgrade to head, downgrade, upgrade again (M6 found its
  re-upgrade bug this way). Stop the container afterwards.
- Write a server process's pid to a file and kill by pid: `pkill -f` on a
  pattern found in the shell's own command line killed the shell in M6.
- Memory notes to honour: [[buttons-never-disabled-validate-on-click]],
  [[no-page-width-caps-density-by-packing]],
  [[sessions-appjs-single-scope-collisions]],
  [[steps-name-the-app-and-the-tab]],
  [[runbook-never-leave-the-surface-mid-section]], [[lists-one-item-per-line]],
  [[gmail-delegation-needs-licensed-mailbox]] (for any alert email),
  [[constant-contact-arc-rulings]], [[never-read-env-with-a-shell]].

## 4. The report at the end

Review list: what changed, where, what to look at, what to test; which
vendor shapes the live send confirmed and which are still inferred; what
the live pass needs on crm-test that is not there yet. Then **What next**:
the step page's address, the pushes Doug owes, M8 (lists only and the
campaign page, § 7e.9 second half) as the recommended next step, and the
handoff's § 7 layout question still open.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-26-26 09:20 | Claude (Claude Code) | Written at the end of the M6 session, at Doug's request; the plan is a draft for his approval in that session's first reply. |
