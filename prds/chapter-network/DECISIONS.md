# Decisions — settled rulings, open proposals, and who owns what

The rulings below are **Doug's**, given in the planning session of 2026-08-17/18
and preserved verbatim in substance; the whole design follows from them. The
proposals at the bottom are **mine, not his** — they are the open decisions, and
each one blocks work that is otherwise ready to start.

**How to use this file.** Nothing here is a task. A ruling changes only when Doug
changes it, and then the phase files change to follow. A proposal leaves this
section only by being ruled — record the ruling in place, dated, and move the
consequence into the phase file that owns it.

---

## Rulings — the settled architecture

*The planning session that produced these ended in a power cut, and the document
was reconstructed afterwards. Everything in this section is Doug's, preserved
verbatim in substance.*

1. **A central services organization owns development and support.** CBM and the
   other chapters fund one organization that provides all services. Immediate
   propagation requires central operational control, and this supplies it without
   making Cleveland the landlord of its peers — the franchisor model minus the
   franchisor.
2. **One EspoCRM per chapter.** Not one shared multi-tenant database.
3. **Google Workspace is mixed** — some chapters have one, some do not. The two
   branches ("bring your own Workspace and grant delegation to our service
   account" vs "we provision a domain under the network Workspace") differ in an
   onboarding runbook, not in code.
4. **Strictly identical function — core or nothing.** No per-chapter fields, enum
   values or form questions. A want becomes core for everyone, or it does not
   exist.
5. **Each chapter owns its own infrastructure** — its DigitalOcean account and its
   Google Workspace — and grants the services org administrative access to run
   them. Lock-out is impossible in either direction: the services org can stop
   working, the chapter can stop paying and revoke access, neither can destroy the
   other. Dividend: each chapter claims **its own** nonprofit grants (Workspace
   for Nonprofits, TechSoup/DO credits), so the co-op fee is purely labour.
6. **The services org holds the only EspoCRM admin accounts.** Chapter staff get
   non-admin roles. This is what makes ruling 4 enforceable rather than requested:
   EspoCRM has no partial admin, so anyone who can add a user can open Entity
   Manager and add a field. Safe because ruling 5 leaves the chapter able to break
   glass through the droplet it owns.
7. **A release train — all chapters move together.** Every merge deploys to a
   services-org staging instance and soaks; on a fixed cadence all chapters move
   to that tag at once. Chosen over ring promotion because rings create deliberate
   **version skew**, which is what ruling 4 exists to prevent and which makes every
   support call begin with "which version are you on". The guinea pig is a machine
   the co-op owns, not a member.
8. **The app serves the public pages for every chapter**, and each chapter's
   WordPress site embeds them.

### What ruling 4 costs, and who pays it

Ruling 6 makes ruling 4 real, and together they move every configuration change
onto the services org's desk. That is the trade: sameness is bought with
responsiveness. **If the change-request route is slow, chapters will route around
it** — not by hacking, but by asking their own admin, and there will not be one,
so they will ask for one, and the first exception granted ends the architecture.
The governance design — [governance-and-exit.md](governance-and-exit.md) — is
therefore not paperwork; it is the load-bearing half of ruling 4.


---

## Proposals — mine, not rulings. Please rule.

1. ~~**Release cadence: weekly**, with the staging soak being the week itself, and
   a documented emergency path for security fixes.~~ **RULED weekly, 2026-08-26.**
   The emergency path for security fixes rides with it: it bypasses the cadence
   but never staging.
2. **The staging instance is CBM's current crm-test app**, repurposed and renamed
   as the network staging tenant rather than standing up a new one. **Still
   open** — and my recommendation has changed since I first wrote this proposal:
   see [TASKS.md](TASKS.md) § D4, which now argues for a services-org machine
   instead, deferred until a second chapter is in sight, with crm-test as the
   interim. Not urgent: nothing in Phase 2 except the soak itself depends on it.
3. **The change forum meets monthly**, with operational requests explicitly out of
   scope and answered on a published turnaround instead.
4. **Prefer branch A (bring your own Workspace)** for every chapter that can, and
   treat branch B as a transitional state with a documented path to A — because
   branch B is the only hard exit in the architecture.
5. **The fee is labour only**, chapters paying hosting and Workspace directly in
   their own accounts under their own nonprofit grants (ruling 5).
6. **The exit rehearsal is a Phase 6 deliverable with a named owner**, not a
   clause.
7. **Phase 1's decision trigger fires 2026-09-19, and Doug owns it** — the date
   is mine, the event and the owner are not negotiable for the trigger to mean
   anything. See [Phase 1 § The decision trigger](phase-1-crm-config.md#the-decision-trigger): if the CRMBuilder requirements
   session has not answered the product-vs-artifact boundary and the headless
   requirement by then, Layer 3 proceeds in full and its sunk cost is accepted
   deliberately.


---

## Decisions taken since the planning session

| Date | Decision | Where it landed |
|---|---|---|
| 2026-08-26 | **Release cadence is WEEKLY, cut Sunday 17:00 UTC** (proposal 1). Every merge lands on staging immediately; on a weekly cadence a tag is cut and every chapter moves to it together, the soak being the week itself. A security fix may bypass the cadence but never staging. **Note 17:00 UTC is Sunday *afternoon* in Cleveland** — 13:00 EDT / 12:00 EST — not night. | [phase-2](phase-2-release-train.md); the procedure is [crm-update-runbook.md](crm-update-runbook.md) |
| 2026-08-26 | **D1 — the CRM's configuration version lives in a new single-record custom entity, `CNetworkStandard`.** Not in EspoCRM Settings (reading those needs admin, and admin is genuinely closed to the app's credential — the org-wide key 403s on `Role`), and not as a `CActionLog` row (append-only history is the wrong shape for a current-state assertion). | Build handoff written: `cnetworkstandard-entity-crm-handoff.md`. [TASKS.md](TASKS.md) § R0 |
| 2026-08-26 | **D2 — the CRMBuilder decision trigger stands at 2026-09-19, Doug owning it.** If the requirements session has not answered the product-vs-artifact boundary and the headless requirement by then, Layer 3 proceeds in full and its sunk cost is accepted deliberately. | [phase-1](phase-1-crm-config.md) § *The decision trigger*; the action is [TASKS.md](TASKS.md) § A1 |
| 2026-08-26 | **D3 — no logo and no favicon.** Chapters get colours, not marks. The plan's "per-chapter `tokens.css` + logo" was describing a feature that does not exist — the application contains no image asset of any kind — so the phrase comes out of the plan rather than becoming a backlog item. | [phase-0](phase-0-decleveland.md) § 6; [phase-4](phase-4-public-pages.md) |
| 2026-08-24 | **The chapter-network project gets its own directory and its own tracker, inside this repo, splitting out at Phase 2** when the services org becomes real. The app-derived half of the desired state is maintained in the same commit as the code that requires it, which a separate repo would split; Phases 2/3/5/6 belong to the services org and are what will justify the move. | This directory |
| 2026-08-20 | **"Cleveland Business Mentoring" (with -ing) in seven public-form strings is a copy bug, not a second brand.** Sweep them into `{{org}}` rather than introducing a second token. | [Phase 0](phase-0-decleveland.md) § 5; shipped in v0.205.0 |
| 2026-08-20 | **Phase 0 ships with no feature flag.** The safety property — an unconfigured deployment renders byte-identical to before — is what makes a flag unnecessary, and it means the rollback is a revert. | [Phase 0](phase-0-decleveland.md) § 9 |
| 2026-08-20 | **The `legal-links.js` policy URLs are not swept blind.** Making them settings is in scope; *where they should point* is a decision, and three of the four pointed at a WPEngine staging host. | Ruled and shipped in v0.206.0 — prod now serves the four production URLs |

---

## Open questions that are nobody's yet

These are not proposals — I have no recommendation to offer on them — and they
are not tracked as tasks because there is no work to start until they are
answered. They are recorded so they are asked rather than rediscovered.

- **Does the network standard live as a CRMBuilder product capability, or as a
  CBM-network artifact that merely uses CRMBuilder?** The two answers put Phase
  1's applier in different repos under different governance. Only the CRMBuilder
  requirements session can answer it. **The trigger date is confirmed at
  2026-09-19 (Doug, 2026-08-26)** — if the session has not run by then, Layer 3
  proceeds in full. See [phase-1](phase-1-crm-config.md#the-decision-trigger).
- **Which of the two live CRMs is the standard, where their roles differ?** The
  capture is mechanical; the adjudication is a ruling, and it is the riskiest part
  of Phase 1's applier.
- **Do Cleveland's instances have EspoCRM duplicate-checking configured on
  `Account` or `Contact`?** Unverified, and it is a behavioural dependency of the
  intake orchestrators rather than a staff convenience — this app sends no
  `X-Skip-Duplicate-Check` header anywhere.
