# Kickoff — M5: personal outreach

Last Updated: 10-25-26 23:20 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. **The plan below is approved by Doug (10-25-26
23:17) with its four stopping points, and he has asked for all four to be
run in one session**: work through stops A, B, C and D without pausing, then
stop and report. Pause only for a decision that passes the two-part test and
is not settled below. The one decision the plan put to him is settled:
**ruling 128 — the lead's page gets the full email composer**, lifted from
the session tools into `frontend/shared/` so both pages serve one component
(option 2 of two).

## 1. Read first

1. `CLAUDE.md` (loads itself), then `campaigns/CLAUDE.md` — the bullets
   *The lead model*, *The qualification ladder and the Leads tab*, *Review
   is the research queue*, *The import tool*; and the root file's *Email*
   section under *Cross-cutting subsystems* (the two sending identities,
   templates, signatures, the shared conversation renderer).
2. `prds/prospect-marketing/build-plan.md` § 7e.5 (the step), § 7e.11
   (the handoff: the conversation link, the optional campaign on a touch,
   the two channel options — all applied on crm-test 10-25-26), § 7e.13
   (where M5 sits), and the M2, M3 and M4 entries under § 7e.13 for how a
   step records itself.
3. `prds/prospect-marketing/rulings.md` rulings 107, 108, 109 (personal
   outreach), 115 (Calls holds campaign lists only), 118 (only assigned
   leads are matched), 119 (the campaign-less touch), 120 (the sender's
   mailbox), 122 (the opt-out sentence and the postal address), 128 (the
   full composer), and 47, 36, 20 (what Interested and Declined do).
4. The code. The composer: `sessions/frontend/app.js` `composeMessage`
   (about lines 2778–3700: From, To with the address book, Cc/Bcc,
   Subject, the rich-text body with the signature, templates with
   `/emailtemplates` and `…/parse`, attachments local and from the record's
   Documents and a forwarded message, drafts, reply/reply-all/forward, the
   send to `/records/{id}/messages`, the write-back retry screen) and
   `sessions/frontend/styles.css` (the `sx__` compose rules);
   `sessions/router.py` (`/mailbox`, `/emailtemplates`,
   `/records/{parent_id}/emailtemplates/{template_id}/parse`,
   `/records/{parent_id}/messages`, `/records/{parent_id}/communications/{communication_id}/attachments`,
   `/attachments/{attachment_id}`); `comms/service.py` (`send_message` and
   its `ref=` parameter, `_record_ref`, the mailbox lookup at lines 90–105
   through `sessions.service.resolve_manager_profile`, `list_conversations`,
   `conversation_thread`, the `PARENT_LINKS` loop at line 643);
   `comms/crm.py` (`RecordRef`, `MailboxScope`, `PARENT_LINKS`,
   `build_scopes`, `stamp_owners`); `comms/scopes.py` (`WATCHED_ENTITIES`,
   `ScopeCache`); `comms/sync.py` (where an inbound message is matched to a
   record and ingested); `comms/attachments.py:143` and
   `myemail/service.py:147` (the other `PARENT_LINKS` loops);
   `campaigns/calls.py` (`record_outcome`, `_convert_on_interest`, the
   Declined write at line ~503); `campaigns/conversion.py` (`convert_lead`,
   `mark_converted`); `campaigns/leads.py` (`assign_payload`, the
   `assigned` and `replied` filters, `COUNT_KEYS`); `campaigns/router.py`
   (`assign_prospect`, `convert_prospect`, `_lead_or_404`, `_lead_select`,
   `_api_client`, `_actor`); `campaigns/config.py` (`TOUCH_SELECT`, the
   outcome and channel constants); and in `campaigns/frontend/app.js` the
   lead's page (`loadLead`, `renderLead`, `leadWhyNot`, `convertLead`,
   `assignLead`, `notYet`, the `ld_email` and `ld_call` buttons at
   line ~1974) and `index.html`'s record panel (`ld_` ids).
5. The tests: `tests/test_comms_scopes.py`, `tests/test_comms_sync.py`,
   `tests/test_comms_endpoints.py` (the compose endpoints through the
   session tools), `tests/test_campaign_lead_page.py`,
   `tests/test_campaign_leads.py`, `tests/test_campaigns_phase3.py` (the
   call outcomes), `tests/test_campaigns_one_page.py` (the id and
   ruling-number guards; `imports.js` is the model for a tab script that
   reaches the page only through `window.CBMMarketing`).

## 2. What M5 builds (build plan § 7e.5)

Personal outreach on the lead's page: *Email* sends one message from the
assignee's own mailbox through the full composer; *Log a call* records a
campaign-less call with one of three outcomes; the email sync attaches a
reply to the assigned lead as a conversation and flags it *Replied*; the
lead's page shows the touches and the conversations. Dark behind
**`LEAD_OUTREACH`** (a new `Settings` bool, off, read per request); with it
off, the two buttons keep today's "arrives with personal outreach" notice and
the sync is unchanged. One new setting, **`CHAPTER_POSTAL_ADDRESS`** (text,
filled at /setup; ruling 122). No new migration unless Stop C needs one.

**Routine choices, already made and announced to Doug** — build them as
written:

- **The composer is one shared component** (ruling 128):
  `frontend/shared/compose.js` + `compose.css`, lifted from
  `sessions/frontend/app.js`'s `composeMessage` with its styles, and the
  session tools switched to it in the same release (their tests stay
  green; their page loads the shared files after `busy.js` and before
  `app.js`, like `richtext.js`). The component takes a **host object**:
  `{ api, endpoints: { mailbox, templates, parse, messages, attachments,
  documents?, addressBook? }, features: { cc, templates, attachments,
  documents, drafts, reply }, record: { entity, id, name } }`. The session
  tools pass every feature; the lead's page passes `cc: false`,
  `documents: false`, `reply: false` (ruling 107 — one person to one
  person; a lead has no Drive folder; replies are read on the lead's page
  and answered from My Email as today). Address book on a lead: the lead's
  own email, fixed.
- **The sender** (ruling 120): `GET /campaigns/api/mailbox` resolves, in
  order, the user's linked `CMentorProfile.cbmEmail`, else the user's own
  `emailAddress` when its domain is `MENTOR_EMAIL_DOMAIN`, else a refusal
  naming what is missing ("no chapter mailbox on your profile or your
  user"). One resolver, `comms/service.sender_mailbox(user_client, user,
  settings)`, used by the compose, the send and the sync scopes.
- **The send**: `POST /campaigns/api/prospects/{id}/messages` with the
  composer's body (subject, body, attachments). Guardrails on the server:
  the lead is Qualified at Contactable or Referred, has no side exit, is
  assigned to the sender (an unassigned lead is refused: "Assign the lead
  to yourself first"), has an email, and the message has exactly one
  recipient, the lead's email. The server appends the opt-out sentence
  "If you'd rather not hear from us, reply and say so and we won't write
  again." and the chapter's postal address when either is missing; an
  empty `CHAPTER_POSTAL_ADDRESS` refuses the send naming the setting. The
  send runs through `comms.service.send_message(ref=RecordRef(entity=
  "CProspect", id=…, name=…, addresses={email}))` as the user; the
  conversation is linked through `CProspect.conversations` (the ingest
  write-through, under the API client). One **`COutreachTouch`** per send,
  channel *Personal email*, status Sent, `sentAt` now, the subject as its
  name, no campaign, `prospectId`; its `teams` stamped as the call kind
  stamps them. Action-log row *Lead Emailed* (subject in the summary,
  never the body).
- **Templates on a lead**: `GET /campaigns/api/emailtemplates` lists the
  templates whose native category is *Marketing* when any has it, else
  every template; `POST …/prospects/{id}/emailtemplates/{template_id}/parse`
  renders through EspoCRM's `prepare` with the lead as `relatedType/Id`
  (the `{CProspect.*}` placeholders resolve; unresolved ones stay literal
  and the UI warns, as today).
- **Log a call**: `POST /campaigns/api/prospects/{id}/calls` with
  `outcome` (Interested, Not interested, No reply yet), `notes`, and the
  number called (`calledPhone`, defaulting to the lead's phone). One
  campaign-less *Personal call* touch, status Done, `doneAt` now, written
  as the user with the teams stamped. The consequences are **the campaign
  calls' own code, shared**: pull the Interested and Declined branches of
  `calls.record_outcome` into `calls.apply_outcome(api_client, lead_id,
  outcome, note)` and call it from both. *Interested* converts under the
  API client (needs an email or a website; otherwise the call is recorded
  and the refusal says so in words, as the campaign call does); *Not
  interested* sets `sideExit` Declined with the note (required) and never
  over another exit; *No reply yet* writes the touch only. Then
  `ladder.after_write`. Action-log row *Lead Called*.
- **The sync** (rulings 109, 118, 120): `comms/crm.PARENT_LINKS` gains
  `"CProspect": "prospects"`; `comms/scopes.WATCHED_ENTITIES` gains
  `CProspect`; `build_scopes` gains a source: every lead with an
  `assignedUserId` and an email joins the scope of that user's mailbox
  (resolved by the same resolver; a user with no mailbox contributes no
  scope), as a `RecordRef(entity="CProspect")`. A mailbox that is a
  marketer's own address and not on any mentor profile gets a scope of its
  own built from those leads alone. An inbound message matched to a lead
  sets `CProspect.replied = true` under the API client (feature-detected,
  `ladder.FIELDS` already names it) — the lead's own address only, exact
  match, never a domain match; `conversion.mark_converted` clears it. The
  three `PARENT_LINKS` loops take the new entry without special cases.
- **The lead's page**: *Email* opens the composer (or says in words why
  not: not assigned to you, not Contactable or Referred, no email, no
  mailbox); *Log a call* opens the page's own dialog (never `confirm()`)
  with the outcome, the notes and the number; a **Conversations** block
  lists the lead's threads through `comms.service.list_conversations` as
  the user and opens each with the shared renderer (`CBMConversation`); an
  **Activity** block lists the touches newest first (personal and campaign
  alike, ruling 115); a *Replied* badge with a one-line prompt and the
  *Convert* button beside it. The grid's *Mine* filter is the existing
  Assigned-to filter preset to the signed-in user, one chip. Ids `ld_`;
  buttons never hidden or disabled.
- The Marketing Admin Role already holds `COutreachTouch` create/read/edit,
  `CConversation` read own and `CCommunication` read all (the handoff § 4);
  the touch's teams stamp is what makes the role's own write pass. Check,
  do not assume, that `COutreachTouch.outreachCampaign` is not required
  on crm-test (the handoff's § 5 read it so).
- Every served file: plain words, no ruling numbers (the guard test).

### Stop A — the shared composer

- `frontend/shared/compose.js` + `compose.css`, lifted from the session
  tools with the host object; the session tools switched to it; no
  behaviour change there (the existing tests prove it); the write-back
  retry screen, drafts, reply/forward, templates, attachments and the
  address book all behind the host's features.
- Tests: `tests/test_shared_compose.py` — the component is served, both
  pages load it in the right order, the session tools' compose tests
  still pass; a guard that `sessions/frontend/app.js` no longer declares
  `composeMessage`'s body.

### Stop B — the server side of outreach

- The two settings; the sender resolver; `/mailbox`, `/emailtemplates`,
  `…/parse`, `…/messages`, `…/calls` on the campaigns router; the
  guardrails; the opt-out and postal append; the touch per send and per
  call; `calls.apply_outcome` shared with the campaign calls.
- Tests: a new `tests/test_campaign_outreach.py` — each guardrail's
  refusal in words, the append (present / absent / empty setting), the
  touch written, the three outcomes and their consequences, the resolver's
  three cases, templates filtered, through `build()`; `test_campaigns_phase3.py`
  still green.

### Stop C — the sync

- `PARENT_LINKS`, `WATCHED_ENTITIES`, the assigned-lead scope source, the
  marketer-only mailbox scope, the Replied write and its clearing at
  conversion, the lead page's conversations read.
- Tests: `test_comms_scopes.py` and `test_comms_sync.py` gain the lead
  source (a lead matched only when assigned; exact address; a stranger
  sharing a domain not matched; Replied set; cleared by conversion).

### Stop D — the page, documents and release

- The lead page: the composer wired, the call dialog, Conversations,
  Activity, the Replied badge and prompt, the Mine chip; the browser check
  against the stub harness ([[sessions-frontend-stub-harness]]), one
  action per call (the memory note's lesson from the M4 pass).
- `CHANGELOG.md` (read HEAD's `pyproject.toml` first; expected 0.288.0),
  `pyproject.toml` and `uv.lock`, `campaigns/CLAUDE.md` (one bullet),
  the root `CLAUDE.md` (the Email section's two-identities bullet gains
  the lead case; the status window, one block, keep four), the build
  plan (§ 7e.5 marked built, § 7e.13 M5 with the routine choices, header
  revision, the Revision control table, a change-log row),
  `OPEN-ITEMS.md` #57, `email-management.md` (one paragraph: personal
  outreach to leads). Commit; **never push**.
- Then the live-pass step page, published as an artifact, following the
  Step-by-Step Instructions standard and the memory notes
  [[runbook-never-leave-the-surface-mid-section]] and
  [[steps-name-the-app-and-the-tab]]: every value pre-filled from a read
  of crm-test (parse `.env` in Python, never `source` it). The pass needs
  a lead assigned to Mark Marketing with an email the tester controls, and
  Mark's mailbox resolvable by ruling 120 — read crm-test for both before
  writing the page and say in the report what is missing (a mentor profile
  for Mark, or a user address on the mail domain, and whether the Gmail
  delegation can read it). The reply test: the tester answers the email
  from the lead's address and the sync attaches it within one pass.

## 3. Things this session must know

- **Parallel sessions share this clone and its git index.** Stage files by
  name, never `git add -A`; audit `git show --stat HEAD` after each commit;
  read `git log --oneline -5` before writing `pyproject.toml`,
  `CHANGELOG.md` or `OPEN-ITEMS.md`, and re-read a file right before each
  edit. Never open a file for writing before you have read it.
- `uv run pytest -q` is the suite (about 4 minutes; run it in the
  background). `tests/test_comms_endpoints.py::test_disabled_returns_503`
  fails in the full run and passes alone — order-dependent, known, not
  yours.
- The web process's requests are cut off after about a minute; a send is
  one request and must stay one.
- A CRM id is 17 alphanumerics; the test fakes' hyphenated ids are refused
  by `_CRM_ID` — give test records explicit ids where an endpoint checks
  them.
- The impersonation subject must be a real licensed mailbox
  ([[gmail-delegation-needs-licensed-mailbox]]); CBM members are addressed
  at their `cbmEmail` only ([[cbm-members-cbm-email-only]]).
- Memory notes to honour: [[buttons-never-disabled-validate-on-click]],
  [[no-page-width-caps-density-by-packing]],
  [[sessions-appjs-single-scope-collisions]] (one IIFE per page script;
  grep a name before declaring it), [[shared-conversation-renderer]],
  [[steps-name-the-app-and-the-tab]],
  [[runbook-never-leave-the-surface-mid-section]], [[lists-one-item-per-line]].

## 4. The report at the end

Review list: what changed, where, what to look at, what to test; what the
live pass needs on crm-test that is not there yet. Then **What next**: the
step page's address, the push Doug owes, M6 (lists, § 7e.8) as the
recommended next step, and the handoff's § 7 layout question still open.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-25-26 23:20 | Claude (Claude Code) | Written at the end of the M4 session from the M5 plan Doug approved for a one-session run of all four stops; ruling 128 (the full composer, shared) settled the compose question. |
