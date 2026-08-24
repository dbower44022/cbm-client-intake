# Phase 6 — The first chapter

**Status: not started.** The runbook is proven by use, not by writing.

**It has a dress rehearsal that needs no chapter.** Phase 1's acceptance criterion
13 — stand up a throwaway EspoCRM, apply the standard, have the conformance check
pass, and have a **real non-admin** user in each gated team open each app — is this
runbook's dry run, and doing it inside Phase 1 is what makes Phase 6 a rehearsal
rather than a first attempt. Admins bypass ACL, so an admin test proves nothing.

---

## Onboarding a chapter

A runbook, executed by the services org inside accounts the chapter owns
(ruling 5):

1. **Accounts.** Chapter creates its DigitalOcean account and (branch A) its
   Google Workspace; grants the services org admin access to both. Nonprofit
   credits claimed in the chapter's own name.
2. **CRM.** Provision the EspoCRM instance (Dockerized on a droplet in the
   chapter's account), install the network extension, run the config applier,
   create the services-org admin accounts and the chapter's non-admin roles.
   Verify with `preflight_crm.py` before anything is pointed at it.
3. **Google.** Branch A (bring your own): the chapter's super-admin enters the
   domain-wide delegation grant **in their own console** with the exact scope
   list — a known recurring failure point, and the impersonation subject must be
   a real licensed mailbox, never a group or alias, which fails with an error
   naming nothing useful ([[gmail-delegation-needs-licensed-mailbox]]). Branch B
   (provisioned): a domain under the network Workspace, with the exit consequence
   below stated **before** the branch is chosen.
4. **App.** Generate the spec from template + values, create web + worker +
   PRE_DEPLOY jobs, run migrations, deploy the current pinned tag.
5. **Website.** Install the chapter events plugin and the embed snippets, pointed
   at that chapter's app; set `frame-ancestors` for that chapter's domain.
6. **Go-live verification** as a real non-admin in each gated team — admins bypass
   ACL, so an admin test proves nothing.


---

## The exit rehearsal

[Proposal 6](DECISIONS.md) makes the exit rehearsal a deliverable of this phase
with a named owner, rather than a clause in an agreement: run it once on crm-test
like a restore drill. An unexecuted exit path is a promise, not a capability. What
it must produce is in [governance-and-exit.md](governance-and-exit.md).
