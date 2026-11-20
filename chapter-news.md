# Chapter News — a guide for publishers

Last Updated: 11-20-26 02:46 · Revision 1.2 — change log at the end.

Chapter News is news you write once and every member sees on their home page
when they sign in. You decide who it is for, how prominent it is, and whether
members must confirm they have read it. Everything is stored in the CRM.

## Who can publish

Members of the publishers' team, set at System Settings → Team gates →
*Chapter News — publishers* (default: System Management Team).
Administrators can always publish. A publisher sees a **Chapter News** tile on
the home page; it opens the Chapter News page in its own tab.

The feature is behind two switches at System Settings → Features: *New home
page* and *Chapter News*. The CRM must also hold the two Chapter News record
types (`cchapternews-entities-crm-handoff.md`); until it does, the page says
so and members see nothing.

## Writing an item

1. On the Chapter News page, choose **New item**.
2. Give it a **Title** and a short **Summary**. Members see the title and
   summary before they open the item, and the weekly digest shows them too.
3. Write the **Body**. Formatting and images are kept; paste or drop an image
   straight into the editor.
4. Choose the **Importance**:
   - *Normal* — listed newest first.
   - *Pinned* — listed above the normal items.
   - *Must acknowledge* — listed first, with **I have read this** instead of
     Dismiss. The member's home page cannot hide Chapter News while one is
     waiting. Use it for policies and anything you may be asked about later:
     the CRM records who confirmed and when.
5. Choose the **Audience**: tick the teams the item is for. Tick none and it
   goes to every member. A member outside the audience never sees the item.
6. **Publish at** is when it goes live. Leave it empty to publish at once.
   **Expires at** is optional: at that time the item leaves the home page and
   the digest, and stays in past news. An expired item to acknowledge stops
   asking.
7. Optional **Button text** and **Button address** add a call to action, for
   example "Open the handbook" and its web address. Give both or neither.
8. The **Preview** beside the editor shows the item exactly as a member will
   see it, closed and opened.
9. **Save draft** keeps it to yourself. **Publish** sends it.

## Changing and withdrawing

Open an item from the list to edit it. **Editing a published item resets no
one's read status**: a member who dismissed it does not see it again. For a
material change, such as a corrected policy, publish a new item.

**Withdraw** removes an item from every member at once, past news included.
It stays on your list, marked Withdrawn, and can be published again.

Every save, publish and withdraw is recorded in the action history with your
name.

## Who has read it

The list's **Read** column says, for each item that has gone out, how many of
its audience have read it, out of how many. Open an item to see its **Read
report** under the preview: who has not read it yet, who dismissed it, and,
for an item to acknowledge, who acknowledged it and when. **Refresh** reads
it again.

The audience is counted from the CRM's members as they are now: every
active login in a team the item is for (every login, for an item to every
member). A member who has since left the audience is not counted.

## The weekly digest

With *Chapter News weekly digest* on (System Settings → Features), once a
week, Monday at 08:00 chapter time unless changed there, every member with
unread news gets one email from the shared mailbox listing it, items to
confirm first. A member with nothing unread gets nothing. A member can
untick *Email me a weekly digest of unread news* under Chapter News on their
home page. Training addresses are never mailed.

**Send me a test digest**, above the list, sends your own digest to you at
once, so you can see it without waiting for Monday. With nothing unread it
lists every live item you may see.

## What members do

On the home page, Chapter News is the first section. Each item shows its
title and summary; a click on the title opens it. **Dismiss** takes a read
item off the page; **I have read this** confirms an item to acknowledge.
**Past news** lists every item the member could see, with how it stands:
Dismissed, Acknowledged, Unread, Expired, or Not acknowledged.

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 1.2 | 11-20-26 02:46 | The weekly digest (phase 7, v0.356.0). |
| 1.1 | 11-20-26 02:33 | Who has read it (phase 6, v0.355.0). |
| 1.0 | 11-20-26 02:12 | First version, with phase 5 (v0.353.0). |
