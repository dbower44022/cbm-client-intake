# Chapter network — open work

The project's own list, in the shape of the repo's `OPEN-ITEMS.md`: newest at the
top of its section, dated, and moved to *Closed* with the evidence rather than
deleted. It exists because the plan document was doing this job and doing it
badly — two live production defects sat inside a 1,235-line narrative for three
days with nothing pointing at them.

**What belongs here:** work owed by a chapter-network phase.
**What does not:** a Cleveland defect that chapter work merely *found*. Those go
to `OPEN-ITEMS.md`, where the people who fix Cleveland defects are looking. This
file links to them.

---

## Ready to start — no decision needed

1. **`/healthz` gains the two version slots** ([Phase 1](phase-1-crm-config.md),
   the week's tranche). A `crmConfig` block — `{version, appliedAt, fingerprint}`,
   **all null until an applier has written a stamp**, which is the honest reading
   of every instance today — and a `releaseTag` key, null on an untagged build.
   Neither exists: `/healthz` today returns `status`, `version`, `environment`,
   `organization`, `dryRun`, `forms`, `assignments`, `durableStore`, `database`, a
   `worker` block and a `settings` block. Read on the same refresh loop that
   already serves `settingsVersion`. Acceptance criterion 11.

2. **Decide Stamp B's home against a live CRM.** Three candidates in preference
   order, **none verified against a live instance** — the plan calls this the
   first hour of the applier work, and it is cheap to do now:
   `CNetworkStandard` single-record entity (preferred) / a key under admin
   Settings / a `CActionLog` row. The deciding constraints are already written in
   [interface-contract.md](interface-contract.md): it must be readable by the
   app's ordinary org-wide API key with no admin escalation, and it must not share
   a surface the CRM team edits by hand.

3. **Wire the conformance check as a PRE_DEPLOY gate on the crm-test app**, with
   the break-glass variable. Read-only, org-wide API key, no admin — that is what
   makes this safe to do before the applier exists. Acceptance criterion 12 is the
   test: a hand-introduced drift blocks a deploy, the break-glass lets that same
   deploy through with a bypass logged, removing the drift restores a clean
   deploy — all three observed on a real deployment, not asserted.

4. **Carry the interface contract into the CRMBuilder prompt.**
   `prompts/crmbuilder-chapter-network-prompt-v0.1.md` tells its session what
   CRMBuilder can do and nothing about what its consumer needs, so the session
   cannot answer the question the [decision trigger](phase-1-crm-config.md) waits
   on. Add [interface-contract.md](interface-contract.md) as a "what the consumer
   requires" section. Cheap, and it is a precondition for the trigger being
   answerable rather than merely expiring.

5. **Capture both CRMs' roles, read-only, and tabulate the divergence.** The
   adjudication is a ruling and not ours; the *capture* is mechanical and it is
   the riskiest unknown inside the applier month. Doing it now converts an unknown
   into a table Doug can rule on. This repo names teams everywhere and names no
   role anywhere, by design — so this cannot be derived from code and has to be
   read from the instances.

6. **Fix the stale count in `CLAUDE.md`.** It says `sync_form_options.py` manages
   "8 lists"; the tree has **16** managed `crm-enum` blocks across 4 `options.js`
   files, from **14** distinct `Entity.field` sources. Flagged during the Phase 1
   rewrite and never fixed.

## Blocked on a decision

7. **The applier's write path** (Layer 3) — blocked on the
   [decision trigger](phase-1-crm-config.md#the-decision-trigger), **2026-09-19,
   Doug**. This is the only part of Phase 1 at risk: the desired-state definition,
   the conformance check, the exit-code contract, the JSON result and both stamps
   are the app-derived half this repo owns under either answer. What is genuinely
   sunk if CRMBuilder is adopted after this is built is the directive executor,
   the plan-fingerprint plumbing and their tests — two to three weeks. **Build
   order is chosen around this**: the check and the stamps first, the applier last.

8. **The seven proposals** in [DECISIONS.md](DECISIONS.md). Two of them gate work
   that is otherwise ready: proposal 1 (release cadence) and proposal 2 (whether
   the staging tenant is CBM's repurposed crm-test app) are both
   [Phase 2](phase-2-release-train.md) preconditions.

9. **The logo slot** — a feature, not a parameterization, and the application
   currently contains no image asset of any kind.
   [Phase 0](phase-0-decleveland.md) § 6.

## Verification owed

10. **Phase 0's live pass** — no-flicker in a real browser, the two authenticated
    direct-read pages, the two `<meta name="cbm-org">` readers, and the `/setup`
    round trip on `ORGANIZATION_NAME`. Tracked in full in `OPEN-ITEMS.md`
    § *Live verification owed*; listed here because Phase 0 does not close
    without it.

11. **Acceptance criterion 13, the throwaway-instance round trip** — stand up a
    fresh EspoCRM, apply the standard, have the check pass, and have a **real
    non-admin** in each gated team open each app. It needs the applier, so it is
    downstream of task 7, but it needs **no chapter** — which is what turns
    [Phase 6](phase-6-first-chapter.md) into a rehearsal rather than a first
    attempt.

## Found here, owed to Cleveland

Not chapter work. Recorded in `OPEN-ITEMS.md` and linked from here so the finding
is not lost between the two lists.

| Finding | Where it is tracked |
|---|---|
| Production holds `MentorAssignmentNotice` **twice**; the app looks templates up by name, so which one staff send is arbitrary | `OPEN-ITEMS.md` item 26 |
| Prod's `CMentorProfile.howDidYouHearAboutCBM` differs from the static list in **order only** | `OPEN-ITEMS.md` item 26 |
| Five `Event*` email templates missing on **both** instances | `OPEN-ITEMS.md` item 19 (an events blocker already) |

---

## Closed

- **The conformance check is built and has been run against both live instances**
  (2026-08-21, `ac6f1b4`). `scripts/preflight_crm.py` rewritten to C1–C5 with
  `tests/test_preflight_conformance.py`; acceptance criteria 1–5 and 7 met for
  real, exit codes 1 and 3 produced live. It also corrected **three dead
  requirements in its own contract** — `Account.cAccountType` and
  `CIntakeSubmission.reason` / `.status`, required for months and written by
  nothing — because a gate that reports drift nobody can fix is a gate that gets
  ignored. Full result: [Phase 1](phase-1-crm-config.md) § *Measured, 2026-08-21*.

- **The drift narrative was wrong, and now there is a measurement instead**
  (2026-08-21). The two CRMs are far closer than assumed: **identical teams**
  (7 required, 9 present, same lists), **identical enum values across all 16
  managed option lists**, and one ordering difference. Where they actually differ
  is **email templates**, which nothing was watching.

- **Phase 0's mechanism** (v0.205.0–v0.206.0, deployed and prod-verified).
  `ORGANIZATION_NAME` + the `{{org}}` token substituted server-side,
  `CHAPTER_TOKENS_URL`, `ops_mailbox_name` derived from the organisation name,
  `organization` at `/healthz`, and `tests/test_shared_branding.py` (24 cases) as
  the thing that keeps it done.
