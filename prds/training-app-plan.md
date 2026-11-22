# The training application — plan

Last Updated: 11-21-26 22:34 · Revision 0.8 — see change log at the end.

**Status: reviewed by Doug; phase 1's prompt approved as written 11-21-26**
(`prompts/training-app-phase-1-prompt-v0.1.md`, revision 1.0); **phase 1 done 11-21-26** (v0.362.0 and v0.362.2; stop 1 passed on the Association). Elicited 11-21-26 from the planning
prompt `prompts/training-app-planning-prompt-v0.1.md`. Rulings TR1 to TR12
are Doug's answers. The design, the data model and the phases are proposals
that follow from them; nothing is built. Open item `OPEN-ITEMS.md` #92.

## 1. Purpose

Courses are served inside the application behind the member's own sign-in,
and each person's completion is recorded against the course revision they
completed. A course that changes significantly comes due again. This replaces
the Claude page made by `scripts/build_runbook.py`, which knows nobody,
records nothing and needs a Claude session to update.

## 2. Terms

- **Course**: one step-by-step training run, one folder under `training/`,
  written in Markdown in the shape `build_runbook.py` reads.
- **Step**: one numbered action in a course (`### 3.2 …`), with a tick box.
- **Checkpoint**: the line that ends a course section and asks the trainee
  to report something they saw.
- **Checkpoint answer**: what the trainee types at a checkpoint; stored, not
  marked (TR1).
- **Revision**: the course's `Revision N.M` line. A **significant revision**
  changes N; a **minor revision** changes only M (TR4).
- **Completion**: a record that one person finished one course at one
  revision.
- **Due**: a course a person can open and has not completed at its current
  significant revision, and has not dismissed.
- **Reminder**: the notice shown, inside an application and on Needs you,
  for a due course (TR2, TR6).
- **Dismissal**: a person's choice to stop the reminder for one course until
  its next significant revision.
- **Course's applications**: the applications a course lists; it appears
  behind the Training button in each (TR3).
- **Training system**: the deployment the exercises run on, the Business
  Mentors Association's today (TR7).
- **Training sign-ins**: the shared logins on the training system, one per
  role, kept in System Settings (TR7).
- **Training report**: the page showing every person's status per course
  (TR5).
- **Mentor onboarding course**: a course marked as counting toward the
  mentor profile's Training completed box (TR10).
- **Help agent**: the AI agent a trainee opens from a step with **I need
  help**, which answers questions about that step (TR11).

## 3. Doug's rulings

**TR1 — Completed means every step ticked and every checkpoint answered**
(11-21-26, option B). The trainee ticks each step and types an answer at each
checkpoint, such as the reference number or the net promoter score shown. The
application stores the answers with the completion record and does not mark
them right or wrong. Cost, accepted: the answers are evidence, not a grade,
so a wrong answer still completes the course. A quiz or a trainer's sign-off
may be added later, course by course.

**TR2 — A course lives in the application it teaches** (11-21-26, Doug's own
model, in place of the three options offered). Each application shows a
**Training** button that opens its courses, so whoever can open the
application can take its courses: access follows the application's existing
team gate, with no separate assignment. A member who opens an application
with a course they have not completed sees a **reminder** to complete it,
and can dismiss the reminder for future sessions. The reminder never blocks
the application. Doug's words: "a user who has access to client
administration would see a training button and be able to take it directly
from the app."

**TR3 — A course lists every application it serves** (11-21-26, option B).
The evaluation demo, for example, names Client Administration, Client
Management and Mentor Administration, and appears behind the Training button
in all three. Completion and dismissal belong to the course, not to the
application: finishing it or dismissing its reminder in one application
clears it in all of them. Cost, accepted: a member can be reminded of a
course mostly about another role's job. Where that matters, the fix is in
the courses (a short role course listed only in that role's application),
not in the application.

**TR4 — Only a significant revision makes a course due again, shown by its
revision number** (11-21-26, option B). A change to the whole number (1.4 to
2.0) makes the course due again, for everyone who completed it or dismissed
its reminder; the returning reminder shows that revision's change log entry.
A change after the decimal point (1.4 to 1.5) is "updated, no need to
retake". The course's editor decides which, and records why in the change
log; the review before commit checks the judgement. A course still at 0.x is
a draft: completion is recorded, but it never comes due again until it
reaches 1.0. A changed course reaches every chapter with the release that
carries it. Cost, accepted: a real change marked minor reaches nobody.

**TR5 — The trainee sees their own courses; one named team sees a
completion report** (11-21-26, option B). The report shows, per course, each
person's status (completed and at which revision, due again, dismissed, not
started) and their checkpoint answers. "Not started" is everyone who can open
one of the course's applications and has not finished it, worked out from
the existing team gates, never kept by hand. The gate is a new setting,
`TRAINING_REPORT_ALLOWED_TEAMS`, default Mentor Administration Team (proposed
with the question; Doug did not change it). Cost, accepted: one more page and
setting, and a member's dismissal is visible on the report.

**TR6 — A due course is also a Needs you row on the home page** (11-21-26,
option B). "Course due: <course>" opens the course. It is the same reminder
in a second place: completing the course, or dismissing the reminder in
either place, clears both. Where `HOME_V2` is off, members see the
in-application reminder only. Cost, accepted: one more kind of row in a
busy list, eased by the home page's existing collapse and hide.

**TR7 — The course lives in the live application; its exercises run on the
training system** (11-21-26, option A). The trainee reads and ticks the
course in the live application, signed in as themselves, so completion is
credited to the real person; the steps open the training system in a
private window. The course page shows the training sign-ins. They never sit
in a course file, because the repository is public: a course names a role
("the Client Administration sign-in"), and the sign-ins are a System
Settings entry, stored encrypted like every secret, shown only on course
pages. Cost, accepted: the trainee works in two systems at once, and every
member who can open a course's application can read the training passwords,
so the training system's data is theirs to change until it is next
restored.

**TR8 — Every chapter gets every repository course, and a chapter can switch
a course off** (11-21-26, option A). A System Settings entry lists the
courses a deployment hides. Courses are written and reviewed only in the
repository; chapters do not write their own. A course writes the training
system's address as a token, filled in from a System Settings entry, so a
chapter with its own training system needs no copy of the course. Cost,
accepted: a chapter wanting its own course asks for it to be written into
the repository. Chapter-written courses can be added later without changing
this.

**TR9 — Progress and completions live in the application's own database**
(11-21-26, option A). Progress (each step ticked, each checkpoint answer)
and completions (person, course, revision, date, dismissals) are new tables,
arriving by an ordinary migration with the release; no CRM build. Cost,
accepted: training is not visible on a person's CRM record (see TR10 for
the one CRM fact that is).

**TR10 — Completing every mentor onboarding course ticks the mentor
profile's Training completed box** (11-21-26, option B). A course file can
be marked as mentor onboarding. When a member with a `CMentorProfile` has
completed every onboarding course, the application sets
`trainingCompleted = true` and `trainingCompletionDate`. It only ever sets
the box, never clears it: a later significant revision makes the course due
again (TR4) but never undoes an activation check. Each write is recorded in
the action log with old and new values (ruling Q5.4), so it shows on the
profile's History tab. Meets MR-ONBOARD-REQ-002 (`ClevelandBusinessMentors`,
Mentor Recruitment domain PRD) without a separate learning management
system. Cost, accepted: dormant until a mentor onboarding course is
written. Owed at build: read the field live to confirm it is not built
Read-only, which would drop every API write silently.

**TR11 — A help agent on every step, which knows the course and its guides
and reads the training system** (11-21-26, option B; raised by Doug after
revision 0.2: "a button … that would launch a chat window with an AI agent
and answer questions about the step"). The agent is given the step on
screen, the whole course and the user guides of the course's applications,
and has read-only tools that look up the trainee's own records on the
training system, so it can answer "what went wrong" with facts ("your
engagement is still Pending Acceptance, so the analysis has not run") as
well as "why". It follows the Integrations tab's Ask Claude pattern: no tool
that writes, no secret's value, its own monthly budget. Cost, accepted: a
real build (read-only tools scoped to the training system and a sign-in for
the agent there), three to five times the cost per answer of a course-only
agent, and the live application reaching the training system's CRM, which
nothing did before.

**TR12 — Help conversations are kept, and shown on the training report by
step without names** (11-21-26, option C). Each question and the agent's
answer are stored with the course, revision and step, never with the
person. The report shows them under their step, so a step many trainees
are stuck at, and a wrong answer from the agent, can both be found. The
chat window says the questions are kept and read by the report team, since
a question naming the trainee's own client can identify them. Cost,
accepted: no follow-up with the one person who asked; the report's progress
column still shows who is stuck.

## 4. Decisions taken in the session (announced, not asked)

Each follows from the rulings and has one workable answer, or is a routine
choice. Doug may reverse any of them at the first phase's stop.

1. **Demo data** (follows from TR7). A course creates its own records on the
   training system where it can, with the trainee's initials on every name so
   two trainees never collide. A course needing records in place names
   records from the training baseline (`training/demo-records.md`), never
   records an earlier trainee made, because a restore removes them.
2. **The package is `courses/`, the content stays in `training/`.** The
   folder name `training/` is taken by the course content; the code that
   serves it is a separate package. Routes: `/courses/` (the member's list),
   `/courses/{course}` (one course), `/courses/report` (TR5).
3. **A course is two files in its folder**: the Markdown, unchanged in shape,
   and a small `course.yaml` naming its id, title, length in minutes, its
   applications (by route, for example `assignments`, `mentorsessions`,
   `mentoradmin`) and, optionally, `onboarding: mentor`. The revision is read
   from the Markdown's `Last Updated` line only, so it has one source. The
   application finds courses by reading `training/*/course.yaml` at start-up;
   `training/` is already in the image (`.dockerignore` does not exclude it).
4. **One renderer.** The Markdown parser in `scripts/build_runbook.py` moves
   into `courses/render.py`; the script imports it, so the Claude page and
   the in-application page can never read a course differently. The page is
   drawn by the application in its own look, not as an artifact.
5. **Tokens in a course**: `{{org}}` as everywhere, plus `{{training_url}}`
   (the training system's address, TR8) and `{{signin:<role>}}`, which the
   course page replaces with that role's training sign-in from System
   Settings (TR7). The Claude page made by the script prints the role name in
   place of a sign-in, so nothing secret can reach it.
6. **Progress is saved as the trainee ticks**, so a 90-minute course can be
   stopped and resumed on another day or computer. A minor revision keeps a
   trainee's ticks; a significant revision clears ticks made against the old
   one and says so at the top of the course.
7. **"Complete course" is never disabled** (the buttons convention). Pressed
   early, it names the steps not ticked and the checkpoints not answered.
8. **The member's list.** The Training button opens `/courses/?app=<route>`,
   listing that application's courses first and the member's other courses
   below, each with its status. A Training tile is not added to the home
   page; Needs you carries what is due (TR6).
9. **A draft course** (0.x) is listed with the word *Draft*, records
   completion, and is never due (TR4). Reaching 1.0 is a significant revision.
10. **Who the report counts**: every active regular login in a team that
    opens one of the course's applications, plus administrators in at least
    one team, the rule Chapter News's read report uses. The training
    sign-ins themselves are left out by name.
11. **One switch, `TRAINING_COURSES`, off by default**, read per request.
    Off: no button, no reminder, no Needs you row, the pages answer 404.
12. **The action log** records only what changes the CRM: the TR10 tick on a
    mentor profile, with old and new values. Ticks, answers, completions and
    dismissals are the application's own data and are their own record.
13. **The help button is labelled I need help** (Doug's words), one on
    every step. The chat opens in a side panel that never covers the step,
    and keeps that step as its subject until the trainee moves on.
14. **The help agent has its own budget**, `TRAINING_HELP_MONTHLY_BUDGET`,
    default $25 a month, the integration agent's figure, and its own
    switch, `TRAINING_HELP`, off by default. With the month's budget spent
    the button stays visible and says help is unavailable until the first
    of the month and to ask the trainer (buttons are never hidden).
15. **The agent reads the training system as a read-only API user** of its
    own on the training system's CRM, whose role reads and never writes. It
    is told the trainee's initials and looks for their records first; it
    may read any training record, since all of them are made up. The API
    key is a secret setting, `TRAINING_SYSTEM_API_KEY`, beside
    `TRAINING_SYSTEM_URL`, so a chapter with its own training system points
    at its own. Creating that user and role is a CRM change on the
    Association, applied by the `espo-crm-changes` procedure.

## 5. Design

### 5.1 Inside an application

Every application named by a course gains a **Training** button in its
header, drawn by one shared script, `frontend/shared/training.js`, loaded
after `textsize.js`. The script asks `GET /api/courses/mine?app=<route>` once
per page open. With nothing due it shows only the button. With a course due
it shows a reminder bar under the header: the course's name, its length,
**Start** (or **Continue**) and **Don't remind me again**. A course due
again after a significant revision shows that revision's change log entry in
the bar. Dismissing writes the dismissal and removes the bar in every
application (TR3). The bar never covers the application's controls and the
application works with it open (TR2).

### 5.2 The course page

`/courses/{course}` shows the course in the application's shared look: the
revision line, *Before you start* with the training sign-ins filled in, then
the sections and steps. Each step has its tick box, its copy buttons and its
expected result, as on the Claude page today. Each checkpoint has a text
box. A progress count ("7 of 30 steps") sits in the sticky header. Ticking
collapses a step and brings the next one to the top of the window (the
Step-by-Step Instructions standard, rule 1). Ticks and answers save as they
are made. **Complete course** checks everything is done (decision 7), then
writes the completion and shows the course as done, with its date and
revision.

### 5.3 The home page

`portal/needs.py` gains one kind, **Course**, with a chip and the words
"Course due: <name>". Its rows come from the same read as 5.1, across every
application the member can open, and a click opens the course page. Its
place in the order is after the mentoring and staff rows: training waits,
clients do not.

### 5.4 The training report

`/courses/report`, gated by `TRAINING_REPORT_ALLOWED_TEAMS` (TR5). A course
picker, then one shared grid (`CBMGrid`) of people: name, teams, status
(*Completed 1.2 on 11-28-26*, *Due again*, *In progress, 12 of 30*,
*Dismissed*, *Not started*), and a button opening that person's checkpoint
answers. Read only.

### 5.5 Mentor onboarding (TR10)

After a completion, if the course is marked `onboarding: mentor` and the
person has a `CMentorProfile`, the application checks whether every
onboarding course is now completed. If so, and the box is not already
ticked, it writes `trainingCompleted = true` and `trainingCompletionDate`
under the org-wide key and records the change through `core/action_log.py`
with old and new values. Best effort: a refused write is reported on the
completion screen and retried at the person's next completion, never
failing the completion itself.

### 5.6 The help agent (TR11, TR12)

**I need help** on a step opens the side panel. Each question goes to
`POST /api/courses/{course}/help` with the step number; the server builds
the agent's material (the step, the course, the guides its `course.yaml`
lists under `guides:`) and gives it read-only tools over the training
system's CRM (search and read records; nothing that writes). Like Ask
Claude on the Integrations tab, no secret's value reaches it, the training
sign-ins included, and every answer is scrubbed on the way out. Each call's
cost is recorded and checked against the month's budget before the next
call. The question and answer are stored without the person (TR12); the
report shows them under their step, newest first.

### 5.7 System Settings

| Setting | Default | What it does |
|---|---|---|
| `TRAINING_COURSES` | off | The switch (decision 11) |
| `TRAINING_REPORT_ALLOWED_TEAMS` | Mentor Administration Team | Who sees the report (TR5) |
| `TRAINING_SYSTEM_URL` | empty | `{{training_url}}` in courses (TR8) |
| `TRAINING_SIGNINS` | empty, secret | One line per role: role, username, password (TR7) |
| `TRAINING_HIDDEN_COURSES` | empty | Course ids this deployment hides (TR8) |
| `TRAINING_HELP` | off | The help agent's switch (decision 14) |
| `TRAINING_HELP_MONTHLY_BUDGET` | 25.0 | Dollars a month (decision 14) |
| `TRAINING_SYSTEM_API_KEY` | empty, secret | The agent's read-only key on the training system (decision 15) |

Each new setting needs its row in
`tests/fixtures/setup_payload_before_integrations.json`.

## 6. Data model

Five tables in the application's database (TR9), one migration
(`0053_training_courses`, revision id under 32 characters). People are keyed
by their CRM user id, with the name kept for the report.

- **`training_progress`**: user id, course id, revision, item key (a step
  number such as `3.2`, or a checkpoint key such as `cp-3`), ticked or
  answered at, answer text for a checkpoint. Unique on user, course, item.
- **`training_completion`**: user id, user name, course id, revision,
  completed at, and the checkpoint answers copied in as JSON, so a later
  revision's edits never change what was recorded. One row per user, course
  and revision.
- **`training_dismissal`**: user id, course id, the significant revision
  dismissed (the N of N.M), dismissed at. Unique on user, course, N.
- **`training_help`**: course id, revision, step number, question, answer,
  cost, asked at. No user id (TR12).
- **`training_onboarding_write`**: user id, mentor profile id, written at,
  outcome. The record of TR10 writes and failures for the retry.

Due is computed, never stored: a course the member can open, not hidden, at
1.0 or later, with no completion at the current N and no dismissal at the
current N. crm-test's nightly reset truncates new tables, which is harmless
there; the Association's database is not reset nightly.

## 7. Phases and stopping points

Each phase is one release, built dark. Work stops at each named stop for
Doug's check on the Association's system, as a real non-admin.

- **Phase 1 — the course page.** The `courses/` package, `course.yaml`, the
  parser moved into `courses/render.py`, the course page with saved progress,
  checkpoint boxes and completion, the member's list, the migration, the
  switch and the three content settings (`TRAINING_SYSTEM_URL`,
  `TRAINING_SIGNINS`, `TRAINING_HIDDEN_COURSES`). The evaluation demo gains
  its `course.yaml` and its tokens. **Stop 1**: Doug starts the evaluation
  course, stops halfway, resumes on another computer and completes it.
- **Phase 2 — the Training button and the reminder.** `training.js` in every
  application a course names, the reminder bar, dismissal, the due rule.
  **Stop 2**: as Kitty Cat, the reminder in Client Administration, dismissed
  there and gone from Client Management and Mentor Administration; then a
  test revision raised to 2.0 and the reminder back with its change log
  entry.
- **Phase 3 — Needs you and the report.** The Course kind on the home page
  and the training report with its team gate. **Stop 3**: the row on Joe
  Mentor's home page; the report read as a Mentor Administration member.
- **Phase 4 — mentor onboarding.** TR10, after the live read of the field.
  Needs one course marked onboarding; a short test course serves until a
  real one is written. **Stop 4**: a test mentor's box ticked, with its
  History tab row.
- **Phase 5 — the help agent.** TR11 and TR12: the read-only API user on
  the Association's CRM first, then the side panel, the agent, its tools,
  the budget, and the questions on the report. **Stop 5**: as Kitty Cat,
  one "why" question and one "what went wrong" question asked at step 4.1
  of the evaluation course, then both read on the report without her name.
- **Phase 6 — documentation.** `training/CLAUDE.md` (the course format, the
  tokens, the training system now being the Association's), a staff guide to
  the Training button and the report, and retiring the evaluation demo's
  Claude page. **Stop 6**: Doug's review.

## 8. Not in this arc

Quizzes and trainer sign-off (TR1 leaves them for later, course by course).
Assignment by hand and required courses (TR2). Chapter-written courses
(TR8). Training visible in the CRM beyond the TR10 box (TR9). Courses of
slides and video, such as the events marketing manager course: it stays a
separate artifact until it is rewritten as steps or this arc is extended.

## 9. Open questions, decided in their phase

- ~~Where the Training button sits in each application's header~~ —
  **decided 11-21-26 (Doug, option A)**: beside *Signed in as* in Client
  Administration and Client Management; in a new right-hand corner of
  Mentor Administration's header, so it shows on every view.
- Whether the report offers a download of its grid (phase 3).
- Which courses are mentor onboarding; none exists (phase 4 or later).
- Whether the events marketing manager course is rewritten as steps (after
  phase 6).
- Which model the help agent uses, and whether a course's `guides:` may name
  pages on the documentation site as well as repository files (phase 5).

**Superseded by this arc:** the 11-04-26 ruling in
`training/events-marketing-manager/PLAN.md` that a course "carries no
completion record". It still describes the events course as built; courses
served by the training application carry one.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.8 | 11-21-26 22:34 | Claude (Claude Code) | Phase 2 done: stop 2 passed on the Association (v0.363.0, v0.363.1). Phase 3's prompt drafted. |
| 0.7 | 11-21-26 17:17 | Claude (Claude Code) | Phase 2 built (v0.363.0): § 9's button question decided (option A); the test course `training/reminder-test/` at 1.0. |
| 0.6 | 11-21-26 15:58 | Claude (Claude Code) | Phase 1 done: stop 1 passed on the Association after the fix v0.362.2 (a save refused when the browser's sign-in is not the person the course page was opened for). |
| 0.5 | 11-21-26 12:17 | Claude (Claude Code) | Phase 1 built (v0.362.0). As built: the migration is `0054_training_courses` (0053 was taken); it creates the four tables of phases 1 to 4, `training_help` comes with phase 5; the four tables are kept by the sandbox reset (real people's records); `TRAINING_SIGNINS` is one line, entries separated by semicolons, each `role \| username \| password`, since the settings page has no multi-line box. |
| 0.4 | 11-21-26 11:55 | Claude (Claude Code) | Status: Doug approved phase 1's prompt as written. |
| 0.3 | 11-21-26 11:53 | Claude (Claude Code) | TR11 and TR12, the help agent (raised by Doug after revision 0.2): term, decisions 13 to 15, design § 5.6, three settings, the `training_help` table, phase 5; documentation becomes phase 6. |
| 0.2 | 11-21-26 11:46 | Claude (Claude Code) | TR2 to TR10 recorded; purpose, terms, the twelve decisions taken in the session, design, data model, five phases with their stops, scope and open questions added. |
| 0.1 | 11-21-26 11:13 | Claude (Claude Code) | Started during elicitation; TR1 recorded. |
