# Chapter News publisher page — redesign plan

Last Updated: 11-21-26 01:28 · Revision 1.3 — change log at the end.

**Status: CLOSED 11-21-26.** All three stops built (v0.357.0 to v0.359.0), pushed, and checked by Doug on the Business Mentors Association's system 11-21-26: every step of the check matched.

## 1. The request

Doug, 11-20-26: the Chapter News create and edit forms did not match the
rest of the applications. The list must be a standard grid — filters top
left, search at the top, action buttons on the right: Create, Edit and other
actions. Create opens a pop-up form; saving returns to the grid. Edit shows
the item in a form. View shows a screen built for reading, not an edit form.

## 2. Rulings

- **R1 (11-20-26): Edit uses the same pop-up as Create.** One form, two
  titles; a save returns to the grid either way. Cost, accepted: a long item
  is edited in a pop-up sized to nearly the full window.

## 3. The design

**The grid.** The page opens on it. Toolbar as the Workspace Directories:
Filter (left, with chips naming the filters in force), Search over title
and summary (centre), Create · Edit · Actions ▾ (right). Columns: Title
(summary below it), Status, Importance, Audience, Publish at, Expires, Read
("14 of 32" and a bar), Last changed; the shared grid (`CBMGrid`) sorts and
sizes them, newest Publish at first. A click selects a row; a double-click
or Enter views it. Edit with nothing selected says so — no button is ever
switched off.

**Shown status.** The CRM holds Draft, Published, Withdrawn. The grid also
shows **Scheduled** (published, publish date in the future) and **Expired**
(past its expiry date), worked out in the browser; nothing new is stored.

**Filters.** Status (several), Importance, Audience team (or Every member),
publish date from and to. Withdrawn is hidden by default. The choice is
remembered in that browser.

**Actions ▾.** View · Publish · Move back to draft · Duplicate as a new
draft · Withdraw… (confirmed inside the page) · Send me a test digest. An
action that does not apply to the selected item says why.

**Create and edit (stop 2).** A pop-up nearly the size of the window. Left,
the form in three sections — *What it says* (title, summary with a
character count, body), *Who and when* (audience as team chips with Every
member, importance as three explained choices, publish and expiry dates),
*Button, optional* (text, address, an Open-this-address check). Right, the
live preview, Closed and Opened tabs. Footer: Cancel · Save draft · Publish
(Save changes when already published). A missing field is named on Save;
closing with unsaved changes asks first; a save closes the pop-up, refreshes
the grid and selects the row.

**View (stop 3).** A reading screen: title, status pill, Edit and Actions;
a facts strip (importance, audience, dates, button address, last change);
the item as members see it, opened; the read report with its bar and the
name lists. "← Back to news" returns to the grid.

No server change beyond the summary in the list response; no CRM change.

## 4. Stopping points

Work pauses for Doug's go-ahead after each; each is its own version,
checked on the Business Mentors Association's system.

1. The grid, toolbar, filters and Actions menu — **built, v0.357.0.** Until
   stop 2, Create, Edit and View open the previous editor in place of the
   grid, with "← Back to news".
2. The create and edit pop-up — **built, v0.358.0.** Until stop 3, View
   shows the item as a member sees it, opened, with the read report.
3. The View screen — **built, v0.359.0.**

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 11-21-26 01:28 | Claude (Claude Code) | Closed: Doug ran the 38-step check (runbook https://claude.ai/artifact/7BZJ1otQKQf8xGv1UPj9gb) on the Association 11-21-26, "all matched". |
| 1.2 | 11-21-26 00:18 | Claude (Claude Code) | Stop 3 built (v0.359.0). Made on the way: the View screen has its own Actions menu (no View or digest entry), Escape returns to the grid, and an item now carries who created and last changed it. |
| 1.1 | 11-20-26 23:33 | Claude (Claude Code) | Stop 2 built (v0.358.0). Made on the way: a withdrawn item cannot be edited (Edit says to duplicate it); Withdraw left the form for Actions; the pop-up is a div, not a dialog element, so the editor's own pop-ups stay on top. |
| 1.0 | 11-20-26 20:08 | Claude (Claude Code) | Plan approved by Doug in chat, with ruling R1; stop 1 built. |
