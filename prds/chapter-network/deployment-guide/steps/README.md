# The deployment guide as data

**Version:** 0.1
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 16:50

---

## What this folder is

The New Chapter Deployment Guide, held as structured data: one YAML file per
stage, one entry per step. It is the single source for two things (ruled
09-18-26):

- **The readable guide.** `scripts/render_deployment_guide.py` turns these files
  into one Markdown page per stage in `../guide/`. Nobody edits `../guide/` by
  hand; edit the YAML and re-render.
- **The specification of the onboarding app.** The app CRMBuilder is asked to
  build (`prompts/crmbuilder-chapter-onboarding-requirements-v0.1.md`) interviews
  the chapter for the information each step `needs`, does the steps marked
  `automated`, instructs a person through the rest, and runs each step's `check`.

The numbered method documents beside this folder (`3-` to `11-Methods-*.md`)
are now the notes and history behind the steps: rulings, findings, what the
August build found. The reader never needs them.

---

## A stage file

```yaml
stage: 9
name: Build the CRM system
why: >-            # two to four plain sentences: what the stage achieves, and why it matters
who: >-            # who does the stage
time: >-           # rough time, or "not known yet"
before_you_start:  # what must be finished first, named in words
  - The hosting account and its tokens (stage 5)
unlocks: >-        # what can start once this stage is done
steps: [...]
```

## A step

| Field | Meaning |
|---|---|
| `id` | The step number, as a string: `"9.2"`. Never renumbered. |
| `name` | The step's name, unchanged from the step list. |
| `why` | One sentence: why this step exists, in the reader's terms. |
| `who` | `chapter`, `central` (the central support organization) or `both`, then any detail. |
| `first` | Step ids that must be finished first. |
| `needs` | Values from the chapter information form, or secrets, this step uses. |
| `produces` | Values or secrets this step creates. These include the chapter information form's values and the working values the build passes between steps (an account list, a duplicate rule). Every value is produced by exactly one step and needed by at least one: that is the plan's information check, and the renderer runs it every time. A step that only records a value created earlier (stage 8, filling in the form) lists it under `needs`, not `produces`. |
| `mode` | What the onboarding app will do: `automated` (the app does it), `guided` (a person does it; the app instructs and then checks) or `offline` (a person does it outside any system; the app only records that it is done). |
| `actions` | Numbered actions. Each has `do` (one action), `items` when the action involves a list (each item renders on its own line), and, where it helps, `see` (what the person should see — a sentence, or a list when there are several things to see). Click-level where the screens are known; coarser where they are not, and `status` says so. |
| `done_when` | The finishing test, word for word from the step list. A test with several conditions is a list, one condition per item, rendered as "Done when all of these are true". Only conditions go in it. |
| `note` | A sentence that explains the finishing test without being a condition, such as "There are two sets, not one." Printed after the conditions, and kept word for word with the step list's Note line. |
| `check` | `how`: how a person confirms it. `probe`: what the app would check automatically, in plain words, or `none`. |
| `if_not` | What to do when the check fails. Default: stop and ask the central support organization. |
| `goes_wrong` | The known failure and how to recognise it, or `nothing known yet`. |
| `later` | The automation that will replace a manual method, or `unchanged`. |
| `status` | `done-for-real` or `not-yet-tried`, plus a short note. |
| `source` | Where the history lives, e.g. `3-Methods-CRM-Google-Applications.md#9.2`. |

The readable guide shows `why`, `who`, `first`, `actions`, `done_when`,
`check.how`, `if_not` and `goes_wrong`, plus one line when a step has never been
done for real. `mode`, `needs`, `produces`, `probe`, `later` and `source` are for
the app and the people maintaining the guide.

## Writing rules

The guide's language rules apply (section 3 of `1-How-We-Will-Build-The-Guide.md`):
short sentences, common words, the full name of a thing every time. Each action
is one thing to do. **Every list puts each item on its own line** (Doug,
09-18-26): never write three or more things as a run of commas inside a
sentence — use `items` in an action, or a YAML list. Never invent a screen label: if the exact wording of a
screen is not known, say so in the action.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 16:50 | First version. The guide becomes structured data that drives both the readable guide and the onboarding app CRMBuilder is asked to build (Doug, 09-18-26). |
