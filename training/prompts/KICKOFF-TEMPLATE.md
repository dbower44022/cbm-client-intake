# Kickoff prompt template — a training programme session

Last Updated: 10-30-26 01:17 · Revision 1.0 — see change log at the end.

Copy this file to `training/prompts/<programme>-session-<MM-DD-YY>.md`, fill the
four bracketed places, delete this header and the notes block at the end, and
paste the result into a fresh Claude Code session rooted in `cbm-client-intake`.

Its purpose is to keep a training session a *training* session: pointed at
`training/`, in a mode suited to writing for a room rather than to editing code,
and not reconstructing the state of the programme from scratch each time.

---

## Kickoff

Operating mode: **[ARCHITECTURE for designing a programme · DETAIL for writing
the steps of one · TEACHING only if the subject is teaching Doug something]**.

Read `CLAUDE.md` in this repository first and confirm it is the one in force,
then `training/CLAUDE.md`. Open every reply with the local time from `date`.

Load the `instruction-discipline` skill before writing any step a human
carries out.

This session works in `training/` only. Do not edit application code, an
application guide or a `prds/` plan from here — if the programme turns out to
need an application change, say so and stop rather than making it.

### The programme

**Audience:** [who is in the room, and which team their sign-in is in]

**What they must be able to do when it ends:** [the outcome, in their words,
not in feature names]

**Where it stands:** [nothing yet · outline agreed · steps drafted · rehearsed
on the sandbox · delivered once]

### What binds it

- Delivery is on **crm-test**, which reverts nightly — the programme may rely
  only on baseline demo data, never on a record made for the rehearsal.
- Rehearse as a **real non-admin** in the audience's own team; an EspoCRM
  administrator bypasses ACL and sees a different application.
- User-facing names only, and every form value written out every time.
- `training-guide.md` and `demo-records.md` are the existing material for the
  sandbox walkthroughs — read them before writing a new programme for an
  audience they already cover.

### The work, in order

1. [first step]
2. [second step]

Stop after [the step at which you want to review] and report.

---

## Notes for whoever fills this in (delete before use)

- Name the audience by the team gate as well as the job title: the gate decides
  what the room can see, and it is the commonest reason a rehearsal and a real
  delivery diverge.
- Say explicitly what state the programme is in. A session told "nothing yet"
  will elicit requirements; a session told "steps drafted" will not re-litigate
  the outline.
- Keep the ordered work list short. A training programme is written in passes,
  and a long list in a kickoff prompt reads as approval to run them all.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-30-26 01:17 | Claude (Claude Code) | Created with the `training/` folder, after Doug's ruling 10-30-26 that the training programmes live in this repository. |
