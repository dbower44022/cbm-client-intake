# Kickoff — M8: lists only and the campaign page

Last Updated: 10-30-26 01:40 · Revision 1.1 — change log at the end.

> **RETIRED 10-30-26 — do not run.** M8 was built from this prompt as
> v0.291.0 (commit `73d311e`, 10-27-26), fixed as v0.291.1 (`be45316`),
> pushed, and live-passed on crm-test 10-27-26 18:15. Its three decisions
> were ruled the same day (build plan § 7e.13, item 8). Kept as the record
> of what the M8 session was asked to do.

Operating mode: DETAIL. **The plan below is a draft, not yet approved.**
The session's **first reply** states the operating mode and the loaded
`CLAUDE.md` files as usual, says what `git log origin/main..main` shows
as unpushed, then presents the four stopping points below and every
decision that passes the two-part test and is not settled here, and
**waits for Doug's approval before building anything**. Once he approves
(he may say "run all four stops", as he did for M4 to M7), work through
stops A, B, C and D without pausing, then stop and report. Pause only for
a decision that passes the two-part test and is not settled below.

**State at the time of writing (10-27-26 12:45).** M7 (v0.290.0) is
live-passed on crm-test, and v0.290.1 (the connection-store fix the pass
found) is pushed. The docs commit `22e4148` recording the pass was
committed and not pushed. **Do not push during this session**; Doug
pushes. A push redeploys crm-test and production.

## 1. Read first

1. `CLAUDE.md` (loads itself), then `campaigns/CLAUDE.md` — the bullets
   *Campaign lists* (M6, M7), *Phase 4* (the email kind), *One page, six
   tabs* (M1: the shared `window.CBMMarketing` object, the `ls_` / `cl_`
   id prefixes, the ruling-number guard).
2. `prds/prospect-marketing/build-plan.md`:
   - § 7e.9, the second half: *Lists only*, *The campaign page*, *The
     grid*, *+ New campaign*. **Promote this event is M10, and the send
     report and the Recipients tab are M9 — not this step.**
   - § 7e.11 (storage). Its "migration 0034" for the ready-made lists was
     never cut: 0034 to 0038 went to the ladder, the imports, the import
     lease, M6's lists and M7's copy. **This step cuts migration 0039.**
   - § 7e.12 Draft 9 (system lists: undeletable, copyable) and § 7e.13:
     the M8 line, and the M2 to M7 entries for how a step records itself.
3. `prds/prospect-marketing/rulings.md`: 99 (a campaign always sends to a
   list; each channel's consent rules still apply on top), 100 (the strip
   and the six tabs), 101 (the grid), 102 (+ New campaign), 112 (no
   screen cites a ruling number), 14 (one postcard per business), and
   M7's 1-a (an email campaign must choose a list).
4. The code:
   - Each kind's `select_targets`: `campaigns/postcard.py:107`,
     `campaigns/email.py:126`, `campaigns/sms.py:89`,
     `campaigns/calls.py:143`. Each becomes the recipe of a ready-made
     list.
   - `campaigns/audience.py` — `resolve_targets` and its per-channel
     checks (consent, exits, dead addresses, one card per business). These
     stay; they are what makes ruling 99's "never an unlawful send" true.
   - `campaigns/audience_store.py`, `campaigns/lists_router.py` and
     `campaigns/frontend/lists.js`, as M6 and M7 left them (the Include /
     Leave out condition model, static and dynamic kinds, Copy).
   - `campaigns/service.py` — `_MANUAL_MOVES` (line 300) and the status
     moves; `campaigns/router.py` — the build and sign-off routes per
     kind, and the grid's answer (line 267: the 60-row partner cutoff).
   - `campaigns/frontend/index.html` — the four rule boxes (`.cm__rule`,
     lines 518–572) and the record panel's tabs (Overview, Links,
     Responses, Analytics, from line 477); `campaigns/frontend/app.js` —
     the rule payloads (around line 549 and 887), the record panel, the
     grid, and the New campaign dialog.
5. The tests: `tests/test_campaign_lists.py`, `tests/test_list_copy_routes.py`,
   `tests/test_campaigns_email.py`, `tests/test_campaigns_phase4.py`,
   `tests/test_campaigns_one_page.py`, and each kind's tests (grep
   `select_targets` and `rule` under `tests/`).

## 2. What M8 builds (build plan § 7e.9 second half)

**Every campaign sends to a list; the campaign page gets the strip and its
tabs; the grid and + New campaign follow rulings 101 and 102.** Ruling 99
removes a way of working, so this ships behind a new switch,
**`CAMPAIGN_LISTS_ONLY`** (read per request; off ⇒ the rule cards and
today's page exactly as now). One migration, **0039**.

**Routine choices, to be announced in the first reply and built as
written unless Doug says otherwise:**

- **The ready-made lists** (Draft 9). Migration 0039 adds `system` (bool)
  to `audience_list` and creates five dynamic lists: *All leads for
  postcards*, *Opted-in prospects (Engaged and later)*, *Prospects with
  text consent*, *Leads and prospects with a phone*, *Dormant clients (a
  year)*. Delete and the kind change refuse a system list in words; Copy
  works and makes an ordinary list. Rename is refused too, so the names
  stay recognisable across chapters.
- **The sandbox.** The nightly reset empties `audience_list`, so the
  system lists would vanish on crm-test every night. The worker re-creates
  any missing system list at start and once per cycle (the same pattern as
  the demo campaign links, `sandbox_demo.py`). This also covers a chapter
  whose database predates the migration.
- **Build always reads the campaign's list.** The `rule` payloads and the
  four rule boxes go when the switch is on. `resolve_targets` keeps every
  per-channel check. A campaign with no list gets "Next: choose a list
  (Audience and content)" on its strip, as the email campaign does since
  M7.
- **The strip** (ruling 100) maps today's `campaignStatus`, with no CRM
  change. Draft is Draft while the list or the content is missing; Ready
  is Awaiting sign-off; Signed off is Signed off; Sent is Running for a
  postcard, a text and a call, and the email pick for an email; Results is
  Complete. It highlights the current stage and names the one next action.
  `_MANUAL_MOVES` stays for Cancel.
- **The tabs.** Overview (facts, partners, funders, event, notes);
  *Audience and content* (the list picker, the per-channel counts, the
  kind's content: text wording, postcard template, the picked email);
  Links (the personal form first, with Copy); Responses; *Results*
  (today's Analytics, renamed). **Recipients is M9.** Until then the
  Touches table stays where it is, under Responses, and no empty
  Recipients tab is shown.
- **The grid** (ruling 101). Columns: Campaign, Channel, Stage, Event,
  Partners, Funders, Owner, Dates, Reached, Responses. Event, Partner,
  Funder, Channel and Stage are filters. Partners and funders come from
  one batched related-list read, so the 60-row cutoff goes. The filters
  stay in the browser while the grid holds 200 rows or fewer; crm-test and
  production hold far fewer today (count both before building). The Event
  cell links to the event; its roll-up tab is M10.
- **+ New campaign** (ruling 102): channel, name, owner (the creator by
  default), optional event, partners and funders. It creates the Draft
  and opens it in its own tab, as M7's create already does.
- **Names, never numbers, on the screen** (ruling 112). Buttons are never
  hidden or disabled.

**Decisions that may pass the two-part test — put them to Doug in the
first reply with the plan, using the consequential decision template, or
state that none does:**

1. **What happens to a campaign already built by a rule.** Turning the
   switch on leaves Draft and Awaiting sign-off campaigns whose people came
   from a rule box, with no list. Either the migration (or the switch's
   first read) gives each one its kind's ready-made list, so it carries on
   unchanged; or each is sent back to "choose a list" and must be rebuilt.
   Count these on crm-test and production first. Likely a real decision:
   it decides whether staff redo work in flight.
2. **How a ready-made list is defined.** Each recipe can be written in
   M6's Include / Leave out conditions, which staff can read and copy; or
   it can be a built-in recipe that calls the kind's selection code and
   shows a plain-words description instead of conditions. Check first
   which recipes the condition model can express. *Dormant clients (a
   year)* needs an engagement's last activity, and *one postcard per
   business* is a send rule, not a list condition. If every recipe can be
   expressed, say so and announce conditions as the routine choice. If not,
   this is a real decision: a copy of a built-in recipe would have nothing
   to edit.
3. **The CRM layout for the lead's new fields** (handoff
   `marketing-redesign-crm-handoff.md` § 7, still open). Whether *Level*,
   *Referred by* and *Assigned User* go on the CRM's own lead detail
   layout, or the application's lead page stays the only place they show.
   It is not M8's work, but it is the one question the arc has left open.
   Put it to Doug once, briefly, with a recommendation, and record his
   answer in the build plan.

### Stop A — the ready-made lists and lists only

- Migration 0039 (`system` and the five lists); `audience_store.py` reads
  and the refusals; the worker's re-create pass.
- Build reads the campaign's list for every kind behind the switch; the
  `rule` payloads accepted only with the switch off.
- Tests: each ready-made list selects what its kind's rule selected
  (compare against `select_targets` over the same fake CRM); delete,
  rename and the kind change refused in words; Copy allowed; a campaign
  without a list refused at build in words; each per-channel consent check
  still holds through a list; the re-create pass idempotent. The migration
  on a local Postgres: up from 0038, down, up again.

### Stop B — the strip and the tabs

- The record panel: the strip, Audience and content, Results renamed,
  Links' order, the rule boxes gone behind the switch.
- Tests: the strip's mapping for each kind and status; the one-page guard
  (no duplicate ids, no ruling numbers); switch off ⇒ today's page.

### Stop C — the grid and + New campaign

- The grid's columns, filters and the batched related-list read; the New
  campaign form.
- The browser check against the real application over the test fakes (the
  scratchpad `serve.py` pattern M6 and M7 used); `javascript_tool` scripts
  under a second of awaits, one mutating action per call.

### Stop D — documents, release and the live pass

- `CHANGELOG.md` (read HEAD's `pyproject.toml` first; expected 0.291.0),
  `pyproject.toml` and `uv.lock`, `campaigns/CLAUDE.md` (one revision),
  the root `CLAUDE.md` status window, the build plan (§ 7e.9's second half
  marked built, § 7e.13 M8, Draft 9, the header revision, a change-log
  row), `OPEN-ITEMS.md` #57. Commit; **never push**.
- Then the live-pass step page, published as an artifact, following the
  Step-by-Step Instructions standard and the memory notes
  [[runbook-never-leave-the-surface-mid-section]],
  [[steps-name-the-app-and-the-tab]] and [[runbook-steps-prefilled-values]].
  **Claude runs the pass itself** in a tab Doug signs in as Mark Marketing
  (Doug's ask, 10-25-26), with an administrator sign-in first for the
  switch at /setup. One campaign per kind: pick a ready-made list, build,
  read the counts against what the old rule gave, sign off. The email
  campaign's sign-off syncs its list's copy; **do not send a real email
  again** unless Doug asks — M7 proved that path.

## 3. Things this session must know

- **Parallel sessions share this clone and its git index.** Stage files by
  name, never `git add -A`; audit `git show --stat HEAD` after each
  commit; re-read a file right before each edit.
- `uv run pytest -q` is the suite (about 4½ minutes; run it in the
  background). `tests/test_comms_endpoints.py::test_disabled_returns_503`
  fails in the full run on `main` too and passes alone. It is
  order-dependent and known (`CHANGELOG.md` 0.290.1).
- **A store or engine is built once per process, never per request**
  (v0.290.1: `core/mailing.shared_connection_store`; a per-request
  database engine exhausted crm-test's connections in four requests). Any
  new store follows the app-state pattern.
- **crm-test reverts every night at 04:00 UTC**, CRM and app database
  alike — hence the system lists' re-create pass.
- A local Postgres for the migration: `docker run --rm` of the
  `postgres:16-alpine` image on a spare port, `alembic upgrade` to 0038,
  seed, upgrade to head, downgrade, upgrade again. Stop the container
  afterwards. Write a server's pid to a file and kill by pid, never
  `pkill -f`.
- Memory notes to honour: [[buttons-never-disabled-validate-on-click]],
  [[no-page-width-caps-density-by-packing]],
  [[sessions-appjs-single-scope-collisions]], [[lists-one-item-per-line]],
  [[steps-name-the-app-and-the-tab]], [[never-read-env-with-a-shell]].

## 4. The report at the end

Review list: what changed, where, what to look at, what to test; what the
live pass found. Then **What next**: the pushes Doug owes, and M9 (the
send report and the Recipients tab) as the recommended next step, with
the M5 live pass and D2 as the alternatives.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-27-26 12:45 | Claude (Claude Code) | Written after the M7 live pass, at Doug's request; the plan is a draft for his approval in the M8 session's first reply. |
| 1.1 | 10-30-26 01:40 | Claude (Claude Code) | Marked retired at Doug's request: M8 was built, pushed and live-passed on 10-27-26; a session given this prompt on 10-30-26 found it stale. |
