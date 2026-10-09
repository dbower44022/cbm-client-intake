# Kickoff prompt — Track F, after the presenters live pass

Last Updated: 10-08-26 23:50 · Revision 1.1 — see change log at the end.

Paste this into a fresh Claude Code session rooted in `cbm-client-intake`.
It carries the state of the events arc (Track F of the Finalization Plan) at
the close of the 10-07/08-26 sessions, so the next session starts working
rather than reconstructing.

---

## Kickoff

Operating mode: ARCHITECTURE.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.
Then read the memory note `events-track-f-state` and `OPEN-ITEMS.md` #39.
Open every reply with the local time from `date`.

### Where the work stands

Everything is pushed. `git log origin/main..main` should be empty; if it is
not, say so before anything else. All three Cleveland apps report
**v0.241.1** (confirmed 10-08-26 22:36).

Track F is the set of five features found by Doug's review and required before
the website redirect (`prds/events/CBM_Events_Finalization_Plan.md` § Track F):

| Feature | State |
|---|---|
| F2 / F3 — audience and display time | Live on production and crm-test. Boston owed. |
| F5 — portal calendar | Live on production and crm-test, switch on both. Boston owed. |
| F5 D3 — Join URL editable for Internal events | v0.240.0, live; live check rides the next crm-test pass. |
| **F4 — presenters** | **v0.241.0/.1, live and DARK** (`EVENT_PRESENTERS` on crm-test only). crm-test's CRM side done. **Live pass done 10-08-26** as real non-admins; every step matched after two defects it found were fixed. Production and Boston CRM owed. |
| F1 — multi-value topic with a user-entered value | Catalogued, undesigned. **Next design.** |

Design records: `prds/events/CBM_Events_Presenters_Design.md` (rev 0.8, § 11
as-built), `CBM_Events_Portal_Calendar_Design.md`,
`CBM_Events_Audience_and_Display_Design.md`. CRM handoffs:
`cevent-presenters-crm-handoff.md`, `cevent-audience-display-crm-handoff.md`.

### What the presenters pass taught (do not re-learn)

- **A role that creates a record the application leaves unassigned needs
  Assignment Permission `all`.** EspoCRM refuses, at *not set* or *team*, a
  new record with neither a team nor an assigned user (read from
  `Acl/AssignmentChecker/Helper.php` on crm-test). `scripts/migrate_presenter_roles.py`
  sets it; the API, Partner Manager and Client Assignment roles already had it.
- **`Contact.title` is not stored.** It mirrors the person's role at their
  primary Company (`notStorable`); a Company-less Contact has no title and a
  typed one is silently discarded, HTTP 200. Keep a job title on the record
  that needs it.
- A live pass runs from a **private step page** (artifact) in the
  instruction-discipline format, one action per step with the expected
  result; chat carries the same steps in full. Verify every "it passed" against
  the server log (`doctl apps logs <crm-test id> web --type run`) and a CRM
  read before recording it.

### The work, in order

1. **Production's presenters CRM change — Sunday 17:00 UTC slot, Doug runs it
   from inside the deployed web container.** `cevent-presenters-crm-handoff.md`
   § 5: plan dry run, plan apply, role script dry run, role script apply, the
   § 4 reads (metadata; `GET /CEventPresenter?maxSize=1` as the org key is
   200). Then `EVENT_PRESENTERS` on at `/setup`, and § 4 step 3 as a real
   non-admin. **The step page is written (10-08-26 23:40):**
   https://claude.ai/artifact/1KzCM3LbjyvGWp4k2BXP23 — it needs production on
   v0.241.2, the build that ships the applier (`scripts/apply_crm_plan.py`).
   Do not run anything against production yourself. Record the result in the
   handoff's § 0 and `OPEN-ITEMS.md` #39.
2. **Boston** takes F2/F3, F5 and F4's CRM changes with its next release
   (`CHAPTER_KEY=boston` first, per the F2/F3 notes). Owed, not scheduled.
3. **Two small things owed from the pass**, when Doug offers them: his
   decision on whether a guest presenter's title and company should carry
   from one event's entry to the next (today they live on each entry and the
   Contact holds neither — `OPEN-ITEMS.md` #39 (e)); and the wording of the
   red message when the event save was refused twice at step 3.18 of the pass
   (the server logged only two 400s — #39 (f)). Neither blocks anything.
4. **F1 — the event topic takes several values and a user-entered one.**
   Elicit the requirements **one question per turn**, in executive register,
   from the open questions in the plan's F1 section (who may enter a value;
   whether it appears in the public filter; where it is stored; promotion into
   the curated list; how a two-topic event is counted in reports), the way F4's
   were gathered on 10-07/08-26: a plain question, a concrete example from
   crm-test's data, each option with what the staff member or visitor
   experiences, the cost of the recommendation, one recommendation, a request
   to choose. Record each ruling in the plan's F1 section as a numbered
   requirement with a change-log row, one commit each. Verify the premise on
   crm-test before asking (`CEvent.topic` is a single enum of ten values
   today; `cfg.TOPIC_ORDER` orders the public filter). When the list is
   complete, draft `prds/events/CBM_Events_Topics_Design.md` in the shape of
   the Presenters design, with its plan file, and stop for Doug's review.

### Standing rules that bite here

- Doug pushes, by convention; push only when he says the word.
- crm-test first, always; production is Doug's, at the Sunday slot, from the
  container. Never between 04:00 and 05:00 UTC on crm-test.
- Verify a CRM change against live metadata from the system itself, never
  from a document's state table.
- Every reply opens with the time; a decision stops the reply; work ends with
  a review list and one closing.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-08-26 23:50 | Claude (Claude Code) | Item 1's step page written and linked; v0.241.2 (the applier ships in the image) named as its prerequisite. |
| 1.0 | 10-08-26 22:43 | Claude (Claude Code) | Written at the close of the 10-07/08-26 sessions: v0.240.0 and v0.241.0/.1 live, the presenters live pass done, F1 next. |
