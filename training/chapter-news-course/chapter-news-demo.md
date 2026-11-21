# Chapter News — the training demo

Last Updated: 11-21-26 02:55 · Revision 0.1 — see change log at the end.

A step-by-step demo of every key Chapter News feature, for a new technical
user. The trainee plays two parts in turn: a **publisher**, who writes the
news, and a **member**, who reads it. It runs on the Business Mentors
Association's training system and takes about 40 minutes. The background is
in `chapter-news.md` at the repository root.

**Status.** Draft for Doug's review, not yet run end to end or published.

Every value to type is in its own box. On the documentation site each box
has a copy button: copy it and paste it rather than typing.

## Before you start

**Once, by an administrator** (in **System Settings** on the training
system, the Settings tab), check that these read On: **New home page**,
**Chapter News** and **Chapter News weekly digest**. Check also that
**Chapter News — publishers**, under Team gates, reads exactly
`Marketing Admin Team`.

**Each trainee needs:**

- Chrome, with private windows allowed.
- Two training sign-ins, from the trainer: the **publisher** login (Mark
  Marketing, in the Marketing Admin Team) and the **member** login (Joe
  Mentor, in the Mentor Team). They are not listed here, because this page
  is public.
- **Their initials**, written in place of `XX` in every title below, so
  that two trainees' news never mixes.
- About 40 minutes. Each run leaves its news items on the training system,
  withdrawn, until the system is next restored.

**Two windows are used throughout.** The publisher works in an ordinary
Chrome window. The member works in a private window, so the two sign-ins
never share a session.

## 1. The publisher opens Chapter News

### 1.1 Open the sign-in page

- **Where:** Chrome, an ordinary window.
- **Action:** paste the address below into the address bar and press Enter.

```
https://apps.businessmentorsassociation.org/
```

- **You should see:** the page *Sign in*, with the boxes Username and
  Password.
- **If not:** stop and tell the trainer what the page shows.
- **What it does:** this is the one sign-in for every staff and member
  application.

### 1.2 Sign in as the publisher

- **Where:** the *Sign in* page.
- **Action:** type the publisher's Username and Password from the trainer,
  then press **Sign in**.
- **You should see:** the home page, with a white bar across the top
  listing applications, among them **Chapter News**.
- **If not:** if there is no Chapter News in the bar, stop: either the
  publishers' team setting is wrong or Chapter News is switched off. Tell
  the trainer.
- **What it does:** the Chapter News link shows only to publishers and
  administrators.

### 1.3 Open the Chapter News page

- **Where:** the home page, the white bar at the top.
- **Action:** click **Chapter News**.
- **You should see:** a new tab, *Chapter News*, with a grid under a
  toolbar: **Filter** on the left, the box *Search titles and summaries…*
  in the middle, and **Create**, **Edit** and **Actions ▾** on the right.
  The chip *Withdrawn hidden* sits beside Filter.
- **If not:** if the page says the CRM does not have the Chapter News
  record types, stop and tell the trainer.
- **What it does:** this is where publishers write, schedule and withdraw
  news.

**Checkpoint 1.** Tell the trainer how many items the grid lists.

## 2. Publish a normal item to every member

### 2.1 Start a new item

- **Where:** the Chapter News tab, the toolbar, on the right.
- **Action:** click **Create**.
- **You should see:** a pop-up titled *New news item*, marked Draft. The
  form is on the left, in three sections (*What it says*, *Who and when*,
  *Button*), and *Preview — as a member sees it* is on the right.
- **If not:** stop and tell the trainer what you see.
- **What it does:** one pop-up serves for creating and editing.

### 2.2 Write what it says

- **Where:** the pop-up, the section *What it says*.
- **Action:** fill in each field with the value below. Put your initials in
  place of `XX`.

Title:

```
Demo XX: Welcome to Chapter News
```

Summary:

```
News from the chapter now appears here, on your home page, every time you sign in.
```

Body (click inside the editor, then paste):

```
Chapter News replaces the old email round-ups. Each item stays on your home page until you dismiss it, and you can always find it again under Past news.
```

- **You should see:** the preview on the right fills in as you type.
- **If not:** stop and tell the trainer.
- **What it does:** the title and summary are what members see before they
  open an item.

### 2.3 Choose who and when

- **Where:** the pop-up, the section *Who and when*.
- **Action:** under Audience, click the chip **Every member**. Under
  Importance, click **Normal**. Leave **Publish at** and **Expires at**
  empty.
- **You should see:** Every member highlighted, and Normal chosen.
- **If not:** stop and tell the trainer.
- **What it does:** no team means everyone; an empty Publish at means the
  moment you publish.

### 2.4 Look at the preview

- **Where:** the pop-up, *Preview — as a member sees it*, on the right.
- **Action:** click the tab **Opened**, then the tab **Closed**.
- **You should see:** Opened shows the body under the title and summary;
  Closed shows only the title and summary, with a **Dismiss** button.
- **If not:** stop and tell the trainer.
- **What it does:** the preview is exactly what a member will see.

### 2.5 Publish it

- **Where:** the pop-up, the footer at the bottom.
- **Action:** click **Publish**.
- **You should see:** the pop-up closes, the grid shows the item selected,
  Status *Published*, and a message above the grid: "“Demo XX: Welcome to
  Chapter News” is published. Members see it on their home page."
- **If not:** if a message starts "Not saved yet. It needs …", fill in what
  it names and press Publish again. Anything else: stop and tell the
  trainer.
- **What it does:** the item is live for every member.

## 3. Publish an item members must acknowledge

### 3.1 Start a second item

- **Where:** the Chapter News tab, the toolbar, on the right.
- **Action:** click **Create**.
- **You should see:** the pop-up *New news item*, empty.
- **If not:** stop and tell the trainer.
- **What it does:** starts the item mentors must confirm.

### 3.2 Write what it says

- **Where:** the pop-up, the section *What it says*.
- **Action:** fill in each field with the value below, with your initials
  in place of `XX`.

Title:

```
Demo XX: Please read the updated mentor code of conduct
```

Summary:

```
The code of conduct has changed. Please read it and confirm below.
```

Body:

```
The updated code covers how we handle client information and how quickly we reply to a client. Please read it before your next session.
```

- **You should see:** the preview fills in.
- **If not:** stop and tell the trainer.
- **What it does:** this item will ask each mentor to confirm.

### 3.3 Choose the mentors only, and Must acknowledge

- **Where:** the pop-up, the section *Who and when*.
- **Action:** under Audience, click the chip **Mentor Team**. Under
  Importance, click **Must acknowledge**. Leave both dates empty.
- **You should see:** Mentor Team highlighted, Every member not, and Must
  acknowledge chosen. The preview now shows a *Read & confirm* chip and an
  **I have read this** button.
- **If not:** stop and tell the trainer.
- **What it does:** only Mentor Team members see the item, and it stays at
  the top of their news until they confirm.

### 3.4 Add a button

- **Where:** the pop-up, the section *Button*.
- **Action:** fill in each field with the value below.

Button text:

```
Open my profile
```

Button address:

```
/mentorprofile/
```

- **You should see:** the button appears in the preview's Opened tab.
- **If not:** stop and tell the trainer.
- **What it does:** a call to action under the item. An address starting
  with `/` is a page of this application.

### 3.5 Check the address

- **Where:** the pop-up, the section *Button*.
- **Action:** click **Open this address**, look at the tab it opens, then
  close that tab and return to the Chapter News tab.
- **You should see:** a new tab opens on *My Mentor Profile*, or a message
  that the publisher's login may not open it. Either proves the address
  goes to the right page.
- **If not:** if the pop-up says "The address must start with https://,
  http:// or /.", paste the address again. Anything else: stop and tell
  the trainer.
- **What it does:** a check before members click it.

### 3.6 Publish it

- **Where:** the pop-up, the footer.
- **Action:** click **Publish**.
- **You should see:** the message "“Demo XX: Please read the updated mentor
  code of conduct” is published. Members see it on their home page." In
  the grid, its Read column reads *0 of* a number: the Mentor Team's
  active logins.
- **If not:** stop and tell the trainer.
- **What it does:** the item is live for mentors only.

## 4. Schedule a pinned item for tomorrow

### 4.1 Start a third item

- **Where:** the Chapter News tab, the toolbar, on the right.
- **Action:** click **Create**.
- **You should see:** the pop-up *New news item*, empty.
- **If not:** stop and tell the trainer.
- **What it does:** starts an item that goes live later on its own.

### 4.2 Write what it says

- **Where:** the pop-up, the section *What it says*.
- **Action:** fill in each field with the value below, with your initials
  in place of `XX`.

Title:

```
Demo XX: Volunteer social next month
```

Summary:

```
Join us for the volunteer social. Details and sign-up to follow.
```

- **You should see:** the preview fills in. The Body may stay empty.
- **If not:** stop and tell the trainer.
- **What it does:** a short pinned notice.

### 4.3 Pin it and set tomorrow's date

- **Where:** the pop-up, the section *Who and when*.
- **Action:** under Audience, click **Every member**. Under Importance,
  click **Pinned**. Under **Publish at**, choose **tomorrow's date** in the
  date box, then click the time **9:00 AM** under Morning.
- **You should see:** Publish at reads tomorrow at 9:00 AM.
- **If not:** stop and tell the trainer.
- **What it does:** the item waits until then.

### 4.4 Publish it

- **Where:** the pop-up, the footer.
- **Action:** click **Publish**.
- **You should see:** the message "“Demo XX: Volunteer social next month”
  is published, and goes live on …", naming tomorrow at 9:00 AM. The grid
  shows its Status as *Scheduled*.
- **If not:** stop and tell the trainer.
- **What it does:** no member sees it until tomorrow morning.

**Checkpoint 2.** Tell the trainer the Status and Read columns of your
three items.

## 5. The member reads the news

### 5.1 Open a private window

- **Where:** Chrome.
- **Action:** press Ctrl+Shift+N, then paste the address below into the
  address bar and press Enter.

```
https://apps.businessmentorsassociation.org/
```

- **You should see:** the *Sign in* page, in a dark private window.
- **If not:** stop and tell the trainer.
- **What it does:** a second, separate session for the member.

### 5.2 Sign in as the member

- **Where:** the private window, the *Sign in* page.
- **Action:** type the member's Username and Password from the trainer,
  then press **Sign in**.
- **You should see:** the home page, with **Chapter News** as the first
  section. Your code-of-conduct item is at the top, with a *Read & confirm*
  chip and an **I have read this** button. Your welcome item is below it,
  with **Dismiss**. The volunteer social is not there.
- **If not:** stop and tell the trainer which items you see.
- **What it does:** items to acknowledge come first; the scheduled item is
  not live yet.

### 5.3 Try to hide Chapter News

- **Where:** the private window, the home page, the Chapter News section's
  heading.
- **Action:** click **Hide**.
- **You should see:** the message "Chapter News can't be hidden while an
  item asks you to confirm you have read it." The section stays.
- **If not:** stop and tell the trainer.
- **What it does:** an item to acknowledge cannot be avoided.

### 5.4 Open and confirm the code of conduct

- **Where:** the private window, the Chapter News section.
- **Action:** click the code-of-conduct item's title to open it, read it,
  then click **I have read this**.
- **You should see:** the body and the button **Open my profile** while it
  is open; after the click, the item leaves the list.
- **If not:** stop and tell the trainer.
- **What it does:** the CRM records that this member confirmed, and when.

### 5.5 Dismiss the welcome item

- **Where:** the private window, the Chapter News section.
- **Action:** click **Dismiss** on the welcome item.
- **You should see:** the item leaves the list. With nothing else unread,
  the section reads "No unread news."
- **If not:** stop and tell the trainer.
- **What it does:** dismissing counts as read.

### 5.6 Look at past news

- **Where:** the private window, the Chapter News section.
- **Action:** click **Past news**.
- **You should see:** a list headed *Past news* with your welcome item
  marked **Dismissed** and your code-of-conduct item marked
  **Acknowledged**.
- **If not:** stop and tell the trainer.
- **What it does:** members can always find an item again.

### 5.7 See the digest choice

- **Where:** the private window, the Chapter News section, under the list.
- **Action:** look for the box **Email me a weekly digest of unread news**.
  Leave it as it is.
- **You should see:** the box, ticked.
- **If not:** if there is no box, the weekly digest is switched off; tell
  the trainer and go on.
- **What it does:** each member chooses whether to get the Monday email.

**Checkpoint 3.** Tell the trainer what Past news showed.

## 6. The publisher sees who has read it

### 6.1 Look at the publisher's own home page

- **Where:** the ordinary window, the home page tab.
- **Action:** reload the page (F5).
- **You should see:** in Chapter News, your welcome item, but **not** the
  code-of-conduct item.
- **If not:** stop and tell the trainer.
- **What it does:** proves the audience: the publisher is not in the
  Mentor Team, so the mentors' item is not shown to them.

### 6.2 Refresh the grid

- **Where:** the ordinary window, the Chapter News tab.
- **Action:** reload the page (F5).
- **You should see:** the code-of-conduct item's Read column now reads
  *1 of* the same number as before, with a short bar.
- **If not:** stop and tell the trainer.
- **What it does:** the read counts come from the CRM.

### 6.3 Open the read report

- **Where:** the Chapter News tab, the grid.
- **Action:** double-click the code-of-conduct item's row.
- **You should see:** the View screen: the title with *Published*, a strip
  of facts, *As members see it, opened*, and *Who has read it*, which
  names Joe Mentor as having acknowledged it, with the time.
- **If not:** stop and tell the trainer.
- **What it does:** shows exactly who has confirmed a policy.

### 6.4 Return to the grid

- **Where:** the View screen, top left.
- **Action:** click **← Back to news**.
- **You should see:** the grid.
- **If not:** press Escape.
- **What it does:** View is for reading; the grid is for choosing.

**Checkpoint 4.** Tell the trainer what *Who has read it* said.

## 7. Change, duplicate and withdraw

### 7.1 Edit the welcome item

- **Where:** the Chapter News tab, the grid.
- **Action:** click the welcome item's row once, then click **Edit** in the
  toolbar. Replace the Summary with the value below.

```
News from the chapter now appears on your home page every time you sign in. Past items stay under Past news.
```

- **You should see:** the pop-up titled *Edit news item*, with the footer
  button **Save changes**.
- **If not:** stop and tell the trainer.
- **What it does:** a published item can be corrected in place.

### 7.2 Save the change

- **Where:** the pop-up, the footer.
- **Action:** click **Save changes**.
- **You should see:** "“Demo XX: Welcome to Chapter News” is saved.
  Members see the change at once."
- **If not:** stop and tell the trainer.
- **What it does:** the change is live, but no one's read status is reset.

### 7.3 Check the member was not asked again

- **Where:** the private window, the home page.
- **Action:** reload the page (F5).
- **You should see:** "No unread news." The edited welcome item does not
  come back.
- **If not:** stop and tell the trainer.
- **What it does:** proves edits do not reset who has read it. A material
  change is published as a new item.

### 7.4 Duplicate the scheduled item

- **Where:** the ordinary window, the Chapter News tab, the grid.
- **Action:** click the volunteer social's row once, then click
  **Actions ▾**, then **Duplicate as a new draft**.
- **You should see:** the pop-up titled *Duplicate news item*, marked New
  draft, with the title "Copy of Demo XX: Volunteer social next month", and
  the message "A copy, not saved yet. Change what needs changing, then save
  it."
- **If not:** stop and tell the trainer.
- **What it does:** a quick start for a similar item.

### 7.5 Save the copy as a draft

- **Where:** the pop-up, the footer.
- **Action:** click **Save draft**.
- **You should see:** "“Copy of Demo XX: Volunteer social next month” is
  saved as a draft. Members do not see it." The grid shows it as *Draft*.
- **If not:** stop and tell the trainer.
- **What it does:** a draft is seen by no one but publishers.

### 7.6 Withdraw the code-of-conduct item

- **Where:** the Chapter News tab, the grid.
- **Action:** click the code-of-conduct item's row once, then
  **Actions ▾**, then **Withdraw…**.
- **You should see:** a bar above the grid: "Withdraw “Demo XX: Please read
  the updated mentor code of conduct”? It disappears for every member at
  once, past news included." with **Withdraw** and **Keep it**.
- **If not:** stop and tell the trainer.
- **What it does:** asks before removing an item from everyone.

### 7.7 Confirm the withdrawal

- **Where:** the bar above the grid.
- **Action:** click **Withdraw**.
- **You should see:** "“Demo XX: Please read the updated mentor code of
  conduct” is withdrawn. It has gone from every member's home page and past
  news. The Status filter hides withdrawn items." The item leaves the grid.
- **If not:** stop and tell the trainer.
- **What it does:** withdrawn items stay in the CRM, out of sight.

### 7.8 Check the member's past news

- **Where:** the private window, the home page, Chapter News.
- **Action:** reload the page (F5), then click **Past news**.
- **You should see:** only the welcome item, marked Dismissed. The
  code-of-conduct item is gone.
- **If not:** stop and tell the trainer.
- **What it does:** proves a withdrawal reaches every member at once.

**Checkpoint 5.** Tell the trainer what the member's Past news listed.

## 8. Find items, and the test digest

### 8.1 Search

- **Where:** the ordinary window, the Chapter News tab, the box *Search
  titles and summaries…*.
- **Action:** type your initials after the word Demo, for example:

```
Demo XX
```

- **You should see:** only your own items in the grid, and a count under
  it naming how many are shown.
- **If not:** stop and tell the trainer.
- **What it does:** search covers titles and summaries.

### 8.2 Show the withdrawn item

- **Where:** the Chapter News tab, the toolbar, on the left.
- **Action:** click **Filter**, then under Status tick **Withdrawn**, then
  click **Done**.
- **You should see:** the code-of-conduct item back in the grid, Status
  *Withdrawn*, and a chip *Status: Withdrawn* beside Filter.
- **If not:** stop and tell the trainer.
- **What it does:** withdrawn items can still be found and duplicated.

### 8.3 Reset the filters

- **Where:** the Chapter News tab, the toolbar.
- **Action:** click **Filter**, then **Reset filters**, then **Done**.
- **You should see:** the chip *Withdrawn hidden* again, and the
  withdrawn item gone from the grid.
- **If not:** stop and tell the trainer.
- **What it does:** the browser remembers filters, so a trainee leaves them
  as they found them.

### 8.4 Send a test digest

- **Where:** the Chapter News tab, the toolbar, on the right.
- **Action:** click **Actions ▾**, then **Send me a test digest**.
- **You should see:** "Not sent: Your address … is a training address,
  which is never mailed." The training sign-ins have made-up addresses.
- **If not:** if it says "Sent to …", the publisher's login has a real
  address: tell the trainer to check that inbox.
- **What it does:** on a real login this emails the publisher's own digest
  at once. The training system never mails a training address.

## 9. Tidy up

### 9.1 Withdraw the remaining items

- **Where:** the ordinary window, the Chapter News tab, the grid, with the
  search still reading `Demo XX`.
- **Action:** for each of your three remaining items (the welcome item,
  the volunteer social and its copy), click its row once, then
  **Actions ▾**, then **Withdraw…**, then **Withdraw**.
- **You should see:** after each, the "is withdrawn" message, and the item
  leaves the grid.
- **If not:** stop and tell the trainer.
- **What it does:** no demo news reaches real members of the training
  system.

### 9.2 Sign out

- **Where:** the private window, the home page, the white bar at the top,
  on the right; then the ordinary window, the same place.
- **Action:** click **Sign out** in each, then close the private window.
- **You should see:** the *Sign in* page in each.
- **If not:** close the windows.
- **What it does:** ends both sessions.

**Checkpoint 6.** Tell the trainer the demo is complete, and any step
whose screen did not match.

## What to tell the trainee at the end

- Who sees an item is decided by its audience, its status and its two
  dates, all together.
- *Must acknowledge* is for anything you may be asked about later: the
  read report names who confirmed and when.
- Editing never resets read status. A material change is a new item.
- Withdrawing is immediate and complete, past news included.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 02:55 | Claude (Claude Code) | Drafted in the manner of the Business Evaluation course (Doug, 11-21-26): written in the repository first, then run once on the Association, then published to the documentation site with Doug's yes. Mark Marketing as the publisher (Marketing Admin Team, v0.359.4), Joe Mentor as the member. |
