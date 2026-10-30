# training/ — training programmes for the CBM applications

Last Updated: 10-30-26 01:28 · Revision 1.1

Detail for the training programmes: where a programme lives, the sandbox it is
delivered on, the audiences it is written for, the names it must use, and the
standard a walkthrough is written to.

Claude Code loads this file only when a session reads or edits files in this
folder. It does **not** replace the root `CLAUDE.md` — Claude Code walks up the
tree, so a session rooted here loads both. Keep programme detail here and do
not restate an application rule that already lives in the root file or in an
application folder's own `CLAUDE.md`; point at it instead.

## What this folder is

A **training programme** is how a person is *taught to use* one of the staff or
mentor applications. It is not documentation of how a feature works — that
belongs with the application, in the guides the root `CLAUDE.md` lists.

The difference decides where a document goes:

- *How does the held-company control behave?* → `submission-admin.md`, an
  application guide.
- *What do I put in front of a room of new Client Administration staff for
  forty minutes, and what do they click?* → a programme here.

## One folder per programme

`training/<programme-name>/`, named for its audience and its purpose, holding
that programme's own documents. A programme is a deliverable in its own right,
so it carries revision control and a change log like every other document.

Two training documents exist already and live in this folder:

- `training-guide.md` — what to do when delivering a session on the sandbox:
  the per-audience walkthroughs, the ground rules, the reset. Published to the
  docs site.
- `demo-records.md` — the data reference behind it: which record to open for
  each user type, and what is on each of its tabs. Not published.

They were moved here from the repository root on 10-30-26 (Doug's ruling), and
every reference to them now carries the `training/` path — `publish_docs.py` and
its test, `scripts/sandbox/enrich_training_data.py`, the root `CLAUDE.md`,
`OPEN-ITEMS.md`, `SANDBOX-RESET.md` and the chapter deployment guide's training
method. `CHANGELOG.md` deliberately keeps the old paths, because it is history.

Treat them as the first programme's material, not as the template for the next
one: they are two documents covering nine audiences on one sandbox, which is
where the existing training started, not where a programme has to end up.

## The sandbox reverts every night — a programme cannot rely on its own data

Training is delivered on **crm-test**, which doubles as the training sandbox and
is restored to a fixed snapshot nightly in two halves: the CRM at **04:00 UTC**
(droplet cron) and the application's own Postgres an hour later (the
`delivery-worker`, `SANDBOX_NIGHTLY_RESET`). Runbook: `SANDBOX-RESET.md`.

What this means for a programme:

- **Anything created during the day is gone by morning.** A programme whose
  exercise depends on a record someone made for the rehearsal will work once
  and fail the second time it is delivered.
- **Permanent demo data belongs in the baseline**, through a seeder stage and a
  re-baseline, not through a hand-built record. A CRM change that adds a table
  or a column needs its own seeder stage, or the nightly reset truncates it.
- **Between 04:00 and 05:00 UTC the two halves disagree** — application rows
  outlive the CRM records they point at. Do not schedule a rehearsal there and
  do not write a programme step that reads as a defect in that hour.
- A night can be paused with `touch /var/www/espocrm/.sandbox-hold` on the
  droplet (the CRM half only; the worker flag is separate). Droplet commands
  are Doug's to run.

What survives by design: the CRM team's Entity Manager work, the `/setup`
overrides, roles, teams, email templates and the integration credentials.

## The audiences, and why the sign-in matters

The existing walkthroughs cover nine audiences, each gated by a team:

- Mentors (`/mentorprofile`, `/mentorsessions`, `/directory`)
- Client Administration (`/assignments`)
- Mentor Administration (`/mentoradmin`)
- Partner Management (`/partnersessions`)
- Funder Management (`/sponsorsessions`)
- Submission Admin (`/ops`)
- Workspace Directories (`/directory`)
- Events (`/events`)
- Marketing Management (`/campaigns`)

**Rehearse as a real non-admin in the audience's own team.** EspoCRM
administrators bypass ACL entirely, so a programme walked through on an admin
login proves nothing about what the room will see — it is how several
mentor-only bugs stayed invisible for weeks. The portal gate is per
application, and a missing team shows as a 403 naming the team required.

## Use the user-facing names, never the package or route name

A programme is read by staff, so it uses the words on the screen. The traps:

- **Client Administration** is the page title; the package and route stay
  `assignments`.
- **Client Management** is `/mentorsessions`; **Partner Management** is
  `/partnersessions`; **Funder Management** is `/sponsorsessions`.
- **Funder** is display wording only — the CRM entities stay `CSponsorProfile`.
- **Company** is how the Account entity is presented everywhere.
- The organisation's name is a token in served pages (`{{org}}`) because the
  application serves Cleveland, Boston and Lakeside. A programme naming a
  chapter's web address, colours or sign-ins is **Cleveland-specific** unless
  it says otherwise. The chapter-facing training method is
  `prds/chapter-network/deployment-guide/7-Methods-Training.md`.

## How a walkthrough is written

Every step a human carries out is governed by the **Step-by-Step Instructions**
standard mirrored in `~/.claude/CLAUDE.md`, and the `instruction-discipline`
skill is its operational form — load it before writing steps. The rules that
bite hardest here:

- One action per step.
- Every location exact: the application, then the window or page, then the tab,
  then the panel, then the control. A bare tab name is unusable to someone with
  several applications and the CRM open.
- Every entry click-to-copy, one entry per block.
- **Every form value written out, every time.** Never "use the values from the
  previous step".
- An expected result that says where on screen it appears, and a failure path.
- A "Before you start" block, and a checkpoint naming what to report back.

Three steps or fewer may sit in prose; anything longer is a runbook page.

## Publishing

`scripts/publish_docs.py` is the only publish path, and its `PUBLISHED` tuple is
the registry — a new published programme needs an entry there plus a book and
page on the docs site. The site is **readable without signing in**, so a publish
is refused if the text still carries a live `@cbmentors.org` address or a
credential, and `training-guide.md`'s published copy deliberately omits the six
sign-in usernames. Do not "helpfully" restore them.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-30-26 01:28 | Claude (Claude Code) | `training-guide.md` and `demo-records.md` moved into this folder from the repository root on Doug's ruling, with all 22 references across eight files repointed; `CHANGELOG.md` left carrying the old paths as history. The open question in revision 1.0 is settled. |
| 1.0 | 10-30-26 01:17 | Claude (Claude Code) | Created, after Doug's ruling 10-30-26 that the training programmes live in this repository rather than a separate project folder. Holds the orientation for a training session: what a programme is, the nightly sandbox reset constraint, the nine audiences and the non-admin rehearsal rule, the user-facing names, the step standard, and the publish path. The move of `training-guide.md` and `demo-records.md` under this folder is left open. |
