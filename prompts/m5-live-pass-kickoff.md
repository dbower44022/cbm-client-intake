# Kickoff — the M5 live pass: personal outreach from the lead's page

Last Updated: 11-04-26 01:50 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. The session's **first reply** states the operating
mode, the loaded `CLAUDE.md` files and what `git log origin/main..main`
shows as unpushed. It then states what it found in step 2 below and
presents the pass as a short plan with its stopping points, and **waits
for Doug's approval before touching crm-test**.

## 1. What is being passed

M5 is built as v0.288.0 (10-26-26; build plan § 7e.5; rulings 107–109,
115, 118–120, 122, 128): Email and Log a call on the lead's page, the
shared composer (`frontend/shared/compose.js`), the sync's lead source,
the Replied flag, and the Leads tab's Mine chip. It is dark behind
**`LEAD_OUTREACH`** on both deployments, and needs the setting
**`CHAPTER_POSTAL_ADDRESS`** (every personal email ends with the opt-out
sentence and that address). It is the one Marketing Management switch
still off on production for want of a pass (`OPEN-ITEMS.md` #57).

**The open question the pass must answer:** Mark Marketing has no mentor
profile, so ruling 120 resolves his mailbox by his user address on the
mail domain. Whether the Gmail delegation can send as and read that
mailbox is unknown. A group or an alias 403s `unauthorized_client`
(memory note `gmail-delegation-needs-licensed-mailbox`).

## 2. Read and verify first — state has moved since the step page was written

1. `campaigns/CLAUDE.md`, the bullet *Personal outreach from the lead's
   page*; build plan § 7e.5; `OPEN-ITEMS.md` #57.
2. The step page written 10-26-26:
   https://claude.ai/artifact/X7zFhDzMThqXBUWaGJX9GZ — read it with the
   Artifact tool. It predates M7 to M11 and the 11-03-26 production
   go-live, so check each step against the live system and the code
   before reusing it. Re-publish it to the same address if it needs
   changing, following the Step-by-Step Instructions standard.
3. Whether Mark Marketing's user address on the mail domain (read it from
   his CRM user record; it is not written here) is a real licensed
   mailbox, which only Doug can confirm in Google Admin. Put it to him first: the answer
   decides whether the pass runs as Mark Marketing or as a user with a
   mentor profile.

## 3. Rules for the pass

- Claude runs the pass in a tab Doug signs in (Doug's ask, 10-25-26);
  an administrator sign-in first, for the two settings at `/setup`.
- **A personal email is a real send.** Send only to an address Doug names
  in chat, and only after his yes in this session.
- crm-test reverts at 04:00 UTC: a pass left half-done overnight starts
  again.
- If an extension blocks the tab after a sign-in ("Cannot access a
  chrome-extension:// URL"), open a fresh tab; the sign-in carries over
  (memory note `chrome-extension-blocks-tab`).
- Record the result in `OPEN-ITEMS.md` #57, the build plan § 7e.13 item
  5, `campaigns/CLAUDE.md` if a rule changed, and the root `CLAUDE.md`
  status window. Commit; never push unless Doug asks.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-04-26 01:50 | Claude (Claude Code) | Written at the close of the M10 session, as the recommended next step. |
