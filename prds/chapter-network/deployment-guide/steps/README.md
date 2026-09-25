# The deployment guide as data

**Version:** 0.5
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-25-26 12:50

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
summary: >-        # a short paragraph: what the stage does and why it matters; printed as Summary
why: >-            # older form, one to four sentences; printed as Why this stage when there is no summary
who: >-            # who does the stage
time: >-           # rough time, or "not known yet"
before_you_start:  # what must be finished first, named in words
  - The hosting account and its tokens (stage 5)
owed:              # optional: what the standard cannot supply yet; the build goes ahead without it
  - Duplicate checking, saved views and automated rules (work list item 3)
unlocks: >-        # what can start once this stage is done
steps: [...]
```

## A step

| Field | Meaning |
|---|---|
| `id` | The step number, as a string: `"9.2"`. Changed only by a ruling, and then every reference in the guide, the step list and `scripts/chapter_form/` changes with it, and the stage's change log gives the old-to-new map. Stage 9 was renumbered this way on 09-23-26 (Doug). The method notes keep the old numbers. |
| `name` | The step's name, unchanged from the step list. |
| `summary` | Two to four plain sentences: what the step does and why it matters, in the reader's terms. Printed as **Summary** at the top of the step. A step has this or `why`, not both; `summary` is the form new and rewritten stages use (Doug, 09-25-26, for stage 10). |
| `why` | The older form: one sentence, why this step exists. Printed as **Why** when the step has no `summary`. |
| `who` | `chapter`, `central` (the central support organization) or `both`, then any detail. |
| `first` | Step ids that must be finished first. |
| `needs` | Values from the chapter information form, or secrets, this step uses. |
| `produces` | Values or secrets this step creates. These include the chapter information form's values and the working values the build passes between steps (an account list, a duplicate rule). Every value is produced by exactly one step and needed by at least one: that is the plan's information check, and the renderer runs it every time. A step that only records a value created earlier (stage 8, filling in the form) lists it under `needs`, not `produces`. |
| `mode` | What the onboarding app will do: `automated` (the app does it), `guided` (a person does it; the app instructs and then checks) or `offline` (a person does it outside any system; the app only records that it is done). |
| `actions` | Numbered actions. Each has `do` (one action), `items` when the action involves a list (each item renders on its own line), and, where it helps, `see` (what the person should see — a sentence, or a list when there are several things to see). Click-level where the screens are known; coarser where they are not, and `status` says so. |
| `done_when` | The finishing test, word for word from the step list. A test with several conditions is a list, one condition per item, rendered as "Done when all of these are true". Only conditions go in it. |
| `note` | A sentence that explains the finishing test without being a condition, such as "There are two sets, not one." Printed after the conditions, and kept word for word with the step list's Note line. |
| `check` | `how`: how a person confirms it — a sentence, or a list with one concrete check per item, each naming where to look and what must be seen. `probe`: what the app would check automatically, in plain words, or `none`. |
| `if_not` | What to do when the check fails: a sentence, or a list with one failure case per item, each naming how to recognise it. Default: stop and ask the central support organization. |
| `goes_wrong` | The known failure and how to recognise it, or `nothing known yet`. |
| `later` | The automation that will replace a manual method, or `unchanged`. |
| `status` | `done-for-real` or `not-yet-tried`, plus a short note. |
| `fields` | Stage 8 only: the questions of the chapter information form, one entry per answer. Each has `key` (where the answer sits in the values file, e.g. `web.website_base_url`), `label`, `by` (`chapter` or `central`), `kind` (`text`, `slug`, `url`, `email`, `domain`, `bool` or `choice`), `required`, and the three explanations `meaning`, `source` and `wrong`. Optional: `example`, `default` (the recommended answer), `options` (for `choice`), `later` (the step that answers it), `show_if` (a switch that must be yes for it to be asked). The guide prints them; `scripts/chapter_form/` builds the web page and the values file from them. |
| `source` | Where the history lives, e.g. `3-Methods-CRM-Google-Applications.md#9.2`. |

The readable guide shows `summary` (or `why`), `who`, `first`, `actions`, `done_when`,
`check.how`, `if_not` and `goes_wrong`, plus one line when a step has never been
done for real. `mode`, `needs`, `produces`, `probe`, `later` and `source` are for
the app and the people maintaining the guide.

## Words in capitals

A word in capitals inside a command, such as SHORT-LABEL or CRM-ADDRESS, stands
for a value the reader types in its place. Every one used in more than one stage
is listed in `placeholders.yaml` (`name`, `means`, `from`), which the renderer
prints at the foot of the guide's index page. A new shared placeholder goes
there. One used in a single step is explained in that step. A placeholder uses
the form's own name for the value, never a developer's word: SHORT-LABEL, not
CHAPTER-SLUG (Doug, 09-23-26).

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
| 0.5 | 09-25-26 12:50 | A stage or a step may carry `summary`, what is done and why in a few sentences, printed as Summary in place of Why (Doug, 09-25-26, for stage 10). `check.how` may be a list, one concrete check per item. |
| 0.4 | 09-23-26 20:40 | Step numbers may change by ruling, with every reference following (Doug, 09-23-26, for stage 9). A stage may carry an `owed` list, printed as Not possible yet. `if_not` may be a list, one failure case per item. The renderer indents an action's lines to the width of its number, so Markdown no longer breaks the list at action 10. |
| 0.3 | 09-23-26 14:27 | `placeholders.yaml` added: the shared words in capitals, printed on the guide's index page. CHAPTER-SLUG renamed SHORT-LABEL, the form's own name (Doug, 09-23-26). |
| 0.2 | 09-23-26 12:03 | The `fields` list added, for the chapter information form's questions (Doug, 09-23-26: the form becomes a web page built from stage 8). |
| 0.1 | 09-18-26 16:50 | First version. The guide becomes structured data that drives both the readable guide and the onboarding app CRMBuilder is asked to build (Doug, 09-18-26). |
