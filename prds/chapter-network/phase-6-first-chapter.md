# Phase 6 — The first chapter

**Status: rehearsed.** The runbook is proven by use, not by writing — and steps
2, 4 and 6 were used on 2026-08-31, against a throwaway instance for a chapter
that does not exist (`crm-lakeside`, "Lakeside Business Mentors"). Record:
[rehearsal-2026-08-31/](rehearsal-2026-08-31/) and [TASKS.md](TASKS.md) § Closed.
Steps 1, 3 and 5 are still unrehearsed; step 3 is next, on the same instance.

**The dress rehearsal needed no chapter**, exactly as predicted: Phase 1's
acceptance criterion 13 — stand up a throwaway EspoCRM, apply the standard, have
the conformance check pass, and have a **real non-admin** user in each gated team
open each app — was this runbook's dry run. Admins bypass ACL, so an admin test
proves nothing; none was used.

---

## Onboarding a chapter

A runbook, executed by the services org inside accounts the chapter owns
(ruling 5):

1. **Accounts.** Chapter creates its DigitalOcean account and (branch A) its
   Google Workspace; grants the services org admin access to both. Nonprofit
   credits claimed in the chapter's own name.
2. **CRM.** Provision the EspoCRM instance with the CRMBuilder desktop's deploy
   wizard (Dockerized on a droplet in the chapter's account; **tick *Extra SSH
   keys*** — the services org needs a shell for the next part, and the run's
   own key is CRMBuilder's). Then, as rehearsed: (a) the **file half** — copy
   **both** trees, `custom/Espo/Custom/` *and* `client/custom/src/`, from the
   standard onto the droplet (the path depends on the installer version:
   `data/espocrm/persistent/custom` and `…/custom-client` on the 10.x
   installer), `chown www-data`, `php command.php rebuild`; (b) the **extensions
   the roles depend on**, if R7 rules them in (Advanced Pack, Google
   Integration) — *before* the roles; (c) the **API half** as the admin login —
   teams, roles (validated against the target's `entityDefs`; stripped scopes
   are *unapplyable*, exit 4), role→team attachments, email templates, the
   org-wide API user and its role, the services-org admin accounts, the § E
   instance settings and tab list, rebuild. Verify with `preflight_crm.py` as
   the new API key, and with CRMBuilder's Audit, before anything is pointed at
   it. Until the applier exists, `scripts/rehearsal/` holds the scripts that
   did (c) and the values file that drove step 4.
3. **Google.** Branch A (bring your own): the chapter's super-admin enters the
   domain-wide delegation grant **in their own console** with the exact scope
   list — a known recurring failure point, and the impersonation subject must be
   a real licensed mailbox, never a group or alias, which fails with an error
   naming nothing useful ([[gmail-delegation-needs-licensed-mailbox]]). Branch B
   (provisioned): a domain under the network Workspace, with the exit consequence
   below stated **before** the branch is chosen.
4. **App.** Generate the spec from template + values, create web + worker +
   PRE_DEPLOY jobs, run migrations, deploy the current pinned tag. Rehearsed:
   `scripts/rehearsal/render_spec.py` is the whole of the generator, and
   `doctl apps create --spec` went ACTIVE on first deploy in seven minutes.
   Note the app builds a *branch*; a pinned tag needs Phase 2's mechanism, and
   `releaseTag` honestly reads null until then.
5. **Website.** Install the chapter events plugin and the embed snippets, pointed
   at that chapter's app; set `frame-ancestors` for that chapter's domain.
6. **Go-live verification** as a real non-admin in each gated team — admins bypass
   ACL, so an admin test proves nothing. Rehearsed: one `regular` user per gated
   team (`scripts/rehearsal/stage4_users.py`), the 7×12 gate matrix through the
   portal API, then a human pass — public form → Client Administration assigns →
   Client Management shows it → Submission Admin shows it closed. **Also sign in
   to the CRM itself as admin and look at it** — the app suite passed while the
   CRM's own UI was blank (the missing `client/custom/src/` tree).


---

## The exit rehearsal

[Proposal 6](DECISIONS.md) makes the exit rehearsal a deliverable of this phase
with a named owner, rather than a clause in an agreement: run it once on crm-test
like a restore drill. An unexecuted exit path is a promise, not a capability. What
it must produce is in [governance-and-exit.md](governance-and-exit.md).
