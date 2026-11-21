# Chapter News — user guide

Last Updated: 11-21-26 02:40 · Revision 2.0 — see change log at the end.

Chapter News is news written once that every member sees on their home page
when they sign in. The publisher decides who it is for, how prominent it is,
and whether members must confirm they have read it. Everything is stored in
the CRM.

This guide is for three readers: the members who read the news, the
publishers who write it, and the administrator who switches it on. The
step-by-step demo that trains a new user on every key feature is
`training/chapter-news-course/chapter-news-demo.md`.

**Status.** Draft for Doug's review. It is not yet published to the
documentation site. When it is, the published copy carries no sign-in user
names, because that site can be read without signing in.

## Terms

- **News item**: one piece of news, with a title, a summary and a body.
- **Publisher**: a member of the publishers' team, or an administrator. Only
  a publisher opens the Chapter News page.
- **Audience**: the teams an item is for. An item with no team ticked goes
  to every member. A member outside the audience never sees the item.
- **Importance**: how an item is listed — Normal, Pinned or Must
  acknowledge.
- **Read**: a member has either dismissed the item or acknowledged it.
  Being shown an item is not recorded.
- **Status**: the CRM holds three — Draft, Published and Withdrawn. The
  Chapter News page also shows two worked out from the dates:
  **Scheduled** (published, publish date still in the future) and
  **Expired** (past its expiry date).

## Setting it up (administrators)

All of it is at **System Settings** (`/setup`), which only CRM
administrators open.

- **Features → New home page** must be on. Chapter News lives on the new
  home page.
- **Features → Chapter News** switches the feature on: the News section on
  the home page, past news, and the Chapter News page.
- **Features → Chapter News weekly digest** is optional. It switches on the
  Monday email of unread news.
- **Team gates → Chapter News — publishers** names the team whose members
  may write, publish and withdraw. The default is **Marketing Admin Team**
  (Doug's ruling, 11-21-26). Copy the team's name exactly. Administrators
  can always publish.

The CRM must also hold the two Chapter News record types
(`cchapternews-entities-crm-handoff.md`). Until it does, the Chapter News
page says so and members see nothing. Today only the Business Mentors
Association's CRM holds them.

## What members do

On the home page, **Chapter News** is the first section. Each item shows
its title and summary. A click on the item opens it, showing the body and
any button. Items are listed in this order: items to acknowledge first,
then pinned items, then the rest, newest first.

- **Dismiss** takes a read item off the page.
- **I have read this** confirms an item marked *Read & confirm*. The CRM
  records who confirmed and when.
- While an item to acknowledge is waiting, the Chapter News section cannot
  be hidden. **Hide** says why instead.
- **Past news** lists every item the member could see, each with how it
  stands: Dismissed, Acknowledged, Unread, Expired, or Not acknowledged.
- **Email me a weekly digest of unread news**, under the list, is the
  member's own choice. It shows only while the weekly digest is switched
  on.

## The Chapter News page (publishers)

A publisher sees **Chapter News** in the white bar at the top of the home
page. It opens the Chapter News page in its own tab.

The page opens on a grid of every item. Its toolbar:

- **Filter**, on the left, opens the filters: Status, Importance, Audience
  and Publish date (From, To). The filters in force show as chips beside
  the button; a click on a chip's × clears it. Withdrawn items are hidden
  by default (the chip *Withdrawn hidden*). **Reset filters** goes back to
  the default. The browser remembers the filters.
- **Search titles and summaries…**, in the middle, narrows the grid as you
  type.
- **Create**, **Edit** and **Actions ▾**, on the right.

The columns are Title (with its summary below), Status, Importance,
Audience, Publish at, Expires, Read and Last changed. A click on a column
heading sorts by it, and column edges can be dragged. A click on a row
selects it; a double-click, or Enter, opens it in View.

**Actions ▾** holds View, Publish, Move back to draft, Duplicate as a new
draft, Withdraw… and Send me a test digest. An action that does not apply
to the selected item says why, rather than doing nothing.

## Writing an item

**Create** opens a pop-up nearly the size of the window. The form is on
the left and the preview on the right.

1. **What it says.** A **Title** (required, up to 150 characters) and a
   short **Summary** (up to 500). Members see both before they open the
   item, and the weekly digest shows them too. The **Body** keeps
   formatting and images; paste or drop an image straight into the editor.
   A very large picture is shrunk before it is uploaded.
2. **Who and when.** The **Audience** chips: choose teams, or **Every
   member**. The **Importance**:
   - *Normal* — listed with the rest, newest first. Members dismiss it when
     read.
   - *Pinned* — shown above the normal items until it is dismissed or
     expires.
   - *Must acknowledge* — stays at the top until each member clicks
     **I have read this**. Use it for policies and anything you may be
     asked about later.

   **Publish at** is when the item goes live; empty means the moment you
   publish. **Expires at** is optional. At that time the item leaves the
   home page and the digest, and stays in past news. An expired item to
   acknowledge stops asking.
3. **Button, optional.** **Button text** and **Button address** add a call
   to action under the item, for example "Open the handbook" and its web
   address. Give both or neither. The address starts with `https://`,
   `http://` or `/` (a page of this application, such as
   `/mentorprofile/`). **Open this address** checks it goes where you
   expect.
4. **Preview — as a member sees it** shows the item exactly as a member
   will see it. The **Closed** and **Opened** tabs switch between the two.
5. **Save draft** keeps the item to yourself. **Publish** sends it. A
   missing field is named when you save. Closing with unsaved changes asks
   first.

A save closes the pop-up, refreshes the grid, selects the item and says
what happened, for example "is published. Members see it on their home
page." An item with a future Publish at shows as **Scheduled** and goes
live on its own.

## Viewing an item

**View** (or a double-click on a row) opens a reading screen: the title
with its status, a strip of facts (importance, audience, dates, button
address, who created and last changed it), the item as members see it,
opened, and **Who has read it**. **Edit** and **Actions ▾** are at the top.
**← Back to news**, or Escape, returns to the grid.

## Changing, duplicating and withdrawing

- **Edit** opens the same pop-up with the item in it. For a published item
  the button is **Save changes**. **Editing a published item resets no
  one's read status**: a member who dismissed it does not see it again.
  For a material change, such as a corrected policy, publish a new item.
- **Move back to draft** takes a published item away from members. It can
  be published again.
- **Duplicate as a new draft** opens a copy, titled "Copy of …", that is
  not saved until you save it.
- **Withdraw…** asks inside the page first, then removes the item from
  every member at once, past news included. A withdrawn item stays on the
  list, cannot be edited and cannot be published again; duplicate it
  instead.

Every save, publish, withdraw and test digest is recorded in the action
history with the publisher's name. The CRM's own history names the API
user, because the application writes news under its organisation-wide
key.

## Who has read it

The grid's **Read** column says, for each item that has gone out, how many
of its audience have read it, out of how many, with a bar. **Who has read
it**, on the View screen, lists who has not read it yet and who dismissed
it, and, for an item to acknowledge, who acknowledged it and when.
**Refresh** reads it again.

The audience is counted from the CRM's members as they are now: every
active login in a team the item is for (every login, for an item to every
member). A member who has since left the audience is not counted.

## The weekly digest

With *Chapter News weekly digest* switched on, once a week (Monday at 08:00
chapter time unless changed at System Settings), every member with unread
news gets one email from the shared mailbox listing it, items to confirm
first. A member with nothing unread gets nothing. A member who has unticked
the digest on their home page gets nothing. Training addresses are never
mailed.

**Send me a test digest**, under Actions ▾, sends your own digest to you at
once, so you can see it without waiting for Monday. With nothing unread it
lists every live item you may see. It is refused when your login has no
email address, or when its address is a training address.

## Rules worth knowing

- **Who sees an item is one rule**, in the application's server: the
  status, the audience, Publish at and Expires at together. Nothing else
  filters news.
- **A withdrawn item disappears everywhere at once**, past news included.
  The read counts stop where they were.
- **Read status survives edits.** Publish a new item for a material change.
- **An action that cannot apply says why.** No button is ever switched off.

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 2.0 | 11-21-26 02:40 | Rewritten as the user guide for members, publishers and administrators, after the publisher page's redesign (v0.357.0 to v0.359.0): the grid, filters, search and Actions menu, the Create and Edit pop-up, the View screen; terms, setup, rules worth knowing and a pointer to the training demo. |
| 1.3 | 11-21-26 01:45 | Publishers' default team: Marketing Admin Team (v0.359.4). |
| 1.2 | 11-20-26 02:46 | The weekly digest (phase 7, v0.356.0). |
| 1.1 | 11-20-26 02:33 | Who has read it (phase 6, v0.355.0). |
| 1.0 | 11-20-26 02:12 | First version, with phase 5 (v0.353.0). |
