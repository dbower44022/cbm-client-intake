# Kickoff prompt — Phase 0, de-Clevelanding

**Written 2026-08-20. For a fresh Claude Code session rooted in
`cbm-client-intake`.** This is the first **build** session of the chapter-network
arc. The two before it were planning; this one ships code.

---

## The prompt

`prds/multi-chapter-deployment-plan.md` extends CBM's application suite to a
network of mentoring chapters. Its **Phase 0 — De-Cleveland** is your job: remove
Cleveland's identity from the product so a second chapter can be onboarded
without the software telling its users it belongs to someone else.

Phase 0 was chosen to go first because it is the one phase that depends on
nothing — no ruling from Doug, no answer from the CRMBuilder repo, no decision
forum. The plan also claims it is **worth doing whatever happens with the
chapters**. Treat that as the standard to hold yourself to: if a change you are
about to make is only justified by chapters that may never exist, it does not
belong in Phase 0.

### Read first

1. This repo's `CLAUDE.md` in full — especially *Conventions* and *Gotchas*.
   Every rule there applies; this session writes real code.
2. `prds/multi-chapter-deployment-plan.md`, all of it, but Phase 0 and the
   **"Branding, and the public pages"** section in particular.
3. `frontend/shared/footer.js` and `frontend/shared/tokens.css`.

### Your first deliverable is the inventory, and you must measure it yourself

The plan's figures are **known to be low** and this prompt deliberately gives you
none. Produce the real inventory before changing anything, and write it into the
plan's Phase 0 section so the planning document and the build agree.

Three things to get right while measuring:

- **Search wider than "Cleveland."** `cbmentors` and `CBM` are just as
  Cleveland-specific, and they appear in HTML, JS, CSS and Python.
- **Split brand-as-content from brand-as-identifier.** This is the distinction
  that keeps the workstream from doing damage. The shared JS namespace
  (`CBMBusy`, `CBMDateTime`, `CBMRichText`, `CBMConversation`, `CBMEvents`), the
  `--cbm-*` CSS custom properties, the `cbm-` class prefixes and the
  `data-cbm-*` attributes are **identifiers**. They must not move. Renaming them
  is enormous churn for zero benefit and would break every page. Say this
  explicitly in the inventory so nobody later "finishes the job".
- **There are two names in use**, not one — the product says both "Cleveland
  Business Mentors" and "Cleveland Business Mentoring", in different places.
  Decide whether that is a bug to fix or two deliberate names to parameterize
  separately, and raise it with Doug if it changes the design. Do not silently
  collapse them.

### What Phase 0 has to achieve

**Every place the product names its owner becomes configurable, with Cleveland
as the default.** Say what each item is:

- **a setting** (already parameterized in `core/config.py` — some Cleveland
  values already live there and simply need a non-Cleveland default story),
- **an override** (per-chapter values supplied at deploy or via `/setup`),
- or **a markup edit** (the name is baked into a static file).

The markup is the real work, and it is not one shape. From a scan on 2026-08-20
there are at least three, and you should confirm and extend this list:

1. **Page titles** — `<title>Cleveland Business Mentors — Client
   Administration</title>` and its equivalents, on essentially every page.
2. **Footers** — `&copy; <span data-cbm-year>2026</span> Cleveland Business
   Mentors.` alongside the existing `data-cbm-version` span.
3. **Body prose in the public forms** — "How did you hear about Cleveland
   Business Mentoring?", "A member of the Cleveland Business Mentors team will be
   in touch", and similar. These are read by a member of the public, they are the
   hardest to parameterize cleanly, and they are the ones most likely to be
   missed.

### The mechanism already exists — extend it, do not invent one

`frontend/shared/footer.js` already fills `[data-cbm-year]` locally and
`[data-cbm-version]` from `/healthz`, with the environment name appended. That is
exactly the shape this needs: a data attribute in the markup, a value from the
server, one shared script. Extending it to the organisation name is the obvious
route and it is the one I would take.

Design it properly rather than by reflex, though:

- Where does the name come from — a new setting, and does it surface on
  `/healthz` next to `version` and `environment`, or somewhere else? `/healthz`
  is public, so consider whether that matters (the name is on every page anyway).
- **Page titles are the awkward case.** There is no build step and the pages are
  static files, so a JS fill happens after first paint and the browser tab will
  flicker. Weigh a client fill against rewriting the title server-side on serve,
  and pick one deliberately — do not leave a flash and call it done.
- **Body prose may not be worth attributing at all.** A per-chapter markup edit
  might be the honest answer for a handful of sentences on five public forms.
  Say which you chose and why.
- **The `data-cbm-*` attribute prefix stays `cbm-`.** It is an identifier.

### The safety property that governs everything here

**With no chapter configuration set, every page must render byte-identical to
today.** Cleveland is the default, not a special case. That is what makes this
shippable with `deploy_on_push: true` on `main` — remember a push deploys dev,
crm-test *and* production — and it is why Phase 0 needs no feature flag. If you
find yourself wanting a flag, you have probably made the default do something
new, which is the thing to avoid.

### Also in scope, from the plan

- **Per-chapter `tokens.css` overrides.** Establish the override mechanism —
  what a chapter supplies, where it loads, and how it cannot break the base
  tokens. `tokens.css` is 162 lines of custom properties extracted from
  Cleveland's own site; the header comment says so and will need rewording.
- **The logo.** The plan says "per-chapter `tokens.css` + logo", but a scan
  found **no logo asset in the app at all** — verify that. If it is true, Phase 0
  is *introducing* a logo slot rather than parameterizing an existing one, which
  is a scope question, not a find-and-replace. Raise it before building it.
- The Cleveland-bearing settings defaults in `core/config.py`. Note that
  `mentorprofile/frontend/` and `wp-plugin/cbm-events/cbm-events.css` are
  **verbatim copies of Cleveland's website** and are explicitly *out* of Phase 0
  — ruling 8 and Phase 4 retire them. Do not touch them; say in the inventory
  that you left them and why.

### How to work

- **This is a build session** — `CLAUDE.md`'s conventions are binding. Notably:
  every page loads `frontend/shared/busy.js` first; never cap page width; action
  buttons are never disabled or hidden; tests live in `tests/`; bump the version
  in `pyproject.toml` and add a `CHANGELOG.md` entry.
- **A guard test is the deliverable that keeps this done.** The pattern already
  exists in this repo — `tests/test_shared_address.py` fails when a new address
  page forgets the paste-parser, and there is a test that fails on any new quoted
  `"datetime-local"`. Write the equivalent: a test that fails when a new page
  hardcodes the organisation name. Without it, Phase 0 decays with the next
  feature.
- **Commit early and in coherent pieces** — inventory, then mechanism, then the
  sweep. Uncommitted work is the one category this project's salvage procedure
  cannot rescue (`OPEN-ITEMS.md`, the Dropbox/`.git` item; cite entries by title,
  the numbering has duplicates).
- **Write findings back into `prds/multi-chapter-deployment-plan.md`'s Phase 0**
  as you go. One document for this arc — no second plan, no summary file.
- **Verify before asserting.** Measure against the code, not against this prompt.
  Where a claim needs a live deployment to confirm, say it is unverified.
- **Ask one question at a time, in prose** — a recommendation, the reasoning, and
  the single question that blocks you. No stacked option menus, no bulleted issue
  lists.
- **Do not push.** Claude commits in this clone; Doug reviews and pushes. Check
  `git log origin/main..main` before you finish and tell Doug exactly what is
  waiting — a stale "nothing is unpushed" note in `CLAUDE.md` shipped a feature
  to production unintentionally on 2026-08-20.

### Out of scope

- **Phase 1 and everything after it.** Phase 1 has its own session and prompt
  (`prompts/multi-chapter-phase1-reframe-prompt-v0.1.md`) and runs next.
- **The CRMBuilder repo** — governed by a requirement-first process; write
  nothing there.
- **The two verbatim Cleveland website copies**, as above.
- **Actually onboarding a chapter.** Phase 0 makes the product neutral; it does
  not add a second tenant.

### What done looks like

The organisation's identity is configurable end to end, Cleveland is the default,
and a fresh clone with no chapter settings renders exactly what it renders today.
The inventory is written into the plan, with each item classified as setting,
override or markup edit, and with brand-as-identifier explicitly fenced off. A
guard test fails if a new page hardcodes the name. The version is bumped, the
changelog says what changed, and the commits are sitting unpushed with a clear
note of what they are.

**If the session ends with only the inventory and the mechanism — the name
plumbed through one page properly, with the guard test — that is a good session.**
The sweep across the remaining pages is mechanical once the shape is right, and
getting the shape wrong is what would have to be undone.
