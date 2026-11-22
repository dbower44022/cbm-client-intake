# Training stop 3: Needs you and the training report

Last Updated: 11-21-26 23:05 · Revision 1.0 — see change log at the end.

The check of the training application's phase 3 (v0.364.0) on the Business Mentors Association's system. Joe Mentor's home page shows the course that is due; the training report, read as Mentor Admin, leaves the training sign-ins out (Doug's option A at stop 3, 11-21-26); and your own row on the report moves as you take the reminder test course yourself. About 20 minutes, most of it waiting for the deploy.

## Before you start

- Chrome, with private windows allowed.
- **Keep your own sign-in in a normal window, and every training sign-in in a private window.** A browser holds one sign-in per site in its normal windows and another in its private windows.
- The two training sign-ins this check uses are in **System Settings** on the Association's system, entry **Training sign-ins**: the **Mentor** one (Joe Mentor) and the **Mentor Administration** one (Mentor Admin).

## 1. Push and wait for the deploy

### 1.1 Open a terminal

- **Where:** your desktop computer (host name doug-System-Product-Name).
- **Action:** press Ctrl+Alt+T.
- **You should see:** a terminal window with a prompt ending in `$`.
- **If not:** stop and tell me what you see.
- **What it does:** gives you a terminal on the computer that holds the repository.

### 1.2 Move to the repository

- **Where:** the terminal from step 1.1.
- **Action:** type the line below and press Enter.

```
cd ~/Dropbox/Projects/cbm-client-intake
```

- **You should see:** the prompt again, now ending in `cbm-client-intake$`.
- **If not:** stop and tell me exactly what it printed.
- **What it does:** puts the terminal in the repository folder.

### 1.3 Push

- **Where:** the terminal, prompt ending in `cbm-client-intake$`.
- **Action:** type the line below and press Enter.

```
git push origin main
```

- **You should see:** a last line ending in `main -> main`.
- **If not:** stop and paste the last lines it printed.
- **What it does:** sends v0.364.0 to GitHub; the Association's application builds from it.

### 1.4 Wait for the new version

- **Where:** Chrome, a normal window, a new tab.
- **Action:** paste the address below into the address bar and press Enter. Reload the tab every two minutes until the version changes; the build takes about 8 minutes.

```
https://apps.businessmentorsassociation.org/healthz
```

- **You should see:** a line of text containing `"version":"0.364.0"`.
- **If not:** after 15 minutes, stop and tell me the version it shows.
- **What it does:** confirms the Association runs phase 3.

**Checkpoint:** type the version the health page shows.

## 2. Joe Mentor's home page (private window)

### 2.1 Open the home page in a private window

- **Where:** Chrome.
- **Action:** press Ctrl+Shift+N, then paste the address below into the new private window's address bar and press Enter.

```
https://apps.businessmentorsassociation.org/
```

- **You should see:** the sign-in page.
- **If not:** stop and tell me what the page shows.
- **What it does:** opens the application signed out, away from your own sign-in.

### 2.2 Sign in as Joe Mentor

- **Where:** the private window, the sign-in page.
- **Action:** type the **Mentor** training sign-in's username and password (System Settings, Training sign-ins), then press **Sign in**.
- **You should see:** the home page, with Joe Mentor's name in the header bar and the **Needs you** panel.
- **If not:** stop and tell me what the page shows.
- **What it does:** signs in as the mentor the reminder test course is due for.

### 2.3 Read the Course row

- **Where:** the private window, the home page, the **Needs you** panel.
- **Action:** find the row with the green **Course** chip; it is the last row of the panel.
- **You should see:** the bold line *Course due: Training reminder test*, and under it either *Due again, revision 2.0: Raised to 2.0 to test a course that comes due again (stop 2, section 5). Nothing else changed.* or *About 2 minutes*.
- **If not:** stop and tell me every row the Needs you panel shows. (Joe Mentor has no row if he dismissed or completed the course at 2.0 during stop 2.)
- **What it does:** checks the Course kind on Needs you (TR6).

### 2.4 Open the course from the row

- **Where:** the private window, the **Needs you** panel.
- **Action:** click *Course due: Training reminder test*.
- **You should see:** a new tab, *Training reminder test*, with *Signed in as Joe Mentor*. Do not tick anything on it.
- **If not:** stop and tell me what opened.
- **What it does:** checks the row opens the course page.

### 2.5 Close the private window

- **Where:** the private window.
- **Action:** press Ctrl+Shift+W.
- **You should see:** the private window, with both its tabs, gone.
- **If not:** close it with the window's own close button.
- **What it does:** ends Joe Mentor's sign-in, so the next private window starts signed out.

**Checkpoint:** type the two lines of the Course row exactly as they read.

## 3. The report as Mentor Admin (private window)

### 3.1 Open the report in a private window

- **Where:** Chrome.
- **Action:** press Ctrl+Shift+N, then paste the address below into the new private window's address bar and press Enter.

```
https://apps.businessmentorsassociation.org/courses/report
```

- **You should see:** the page *Training report* with the box *Sign in to read the training report*.
- **If not:** stop and tell me what the page shows.
- **What it does:** opens the report signed out.

### 3.2 Sign in as Mentor Admin

- **Where:** the private window, the *Training report* page, the sign-in box.
- **Action:** type the **Mentor Administration** training sign-in's username and password (System Settings, Training sign-ins), then press **Sign in**.
- **You should see:** *Signed in as Mentor Admin*, the **Course** picker and a grid of people.
- **If not:** stop and tell me exactly what the page says.
- **What it does:** reads the report as a real non-admin in the report's team (Mentor Administration Team).

### 3.3 Choose the reminder test course

- **Where:** the private window, the *Training report* page.
- **Action:** in the **Course** picker, choose *Training reminder test — 2.0*.
- **You should see:** a line of counts such as *5 people · 0 completed · 0 due again · …*, and a grid with the columns Name, Teams, Status, Last activity and Answers. **Kitty Cat, Joe Mentor and Mentor Admin are not in the grid.**
- **If not:** stop and tell me the counts line and every name in the grid.
- **What it does:** checks who is listed (decision 10) and that the training sign-ins are left out.

### 3.4 Filter by a count

- **Where:** the private window, the *Training report* page, the counts line.
- **Action:** click the count ending in *not started*.
- **You should see:** that count highlighted, and only rows whose Status reads *Not started*.
- **If not:** stop and tell me what the grid shows.
- **What it does:** checks the counts filter the grid.

### 3.5 Clear the filter

- **Where:** the private window, the *Training report* page, the counts line.
- **Action:** click the first count, the one ending in *people*.
- **You should see:** every row back in the grid.
- **If not:** stop and tell me what the grid shows.
- **What it does:** returns to the whole list.

### 3.6 Download the grid

- **Where:** the private window, the *Training report* page, beside the Course picker.
- **Action:** press **Download**.
- **You should see:** a file named like `training-reminder-test-11-21-26.csv` in Chrome's downloads, and beside the button *Downloaded … The checkpoint answers stay on this page.*
- **If not:** stop and tell me the message beside the button.
- **What it does:** checks the download (your option B at stop 3a).

### 3.7 Find your own row

- **Where:** the private window, the *Training report* page, the grid.
- **Action:** find the row with your own name. Leave this private window open; section 5 comes back to it.
- **You should see:** your name, your teams, and a Status of *Not started* (or *Dismissed* if you dismissed this course as yourself earlier).
- **If not:** stop and tell me whether your name is in the grid at all.
- **What it does:** gives the starting point for sections 4 to 7.

**Checkpoint:** type the counts line, every name in the grid, and your own row's Status.

## 4. Start the course as yourself (normal window)

### 4.1 Open your course list

- **Where:** Chrome, a normal window, a new tab.
- **Action:** paste the address below into the address bar and press Enter. If a sign-in box shows, sign in as yourself.

```
https://apps.businessmentorsassociation.org/courses/
```

- **You should see:** the page *Training*, *Signed in as* your own name, a **Training report** button at the top, and *Training reminder test* among your courses.
- **If not:** stop and tell me what the page shows.
- **What it does:** checks the report's link, shown only to those the report admits.

### 4.2 Open the course

- **Where:** the normal window, the *Training* page.
- **Action:** click *Training reminder test*.
- **You should see:** the course page *Training reminder test*, with *0 of 1 steps · 0 of 1 checkpoints* at the top.
- **If not:** stop and tell me what opened.
- **What it does:** opens the course under your own name.

### 4.3 Tick the step

- **Where:** the normal window, the *Training reminder test* course page, step 1.1.
- **Action:** tick the box of step 1.1 *Read this step*.
- **You should see:** *1 of 1 steps · 0 of 1 checkpoints* at the top.
- **If not:** stop and tell me any message on the page.
- **What it does:** puts you in progress, with the checkpoint not yet answered.

**Checkpoint:** type what the top of the course page says after the tick.

## 5. Your row in progress (private window)

### 5.1 Reload the report

- **Where:** the private window from section 3, the *Training report* tab.
- **Action:** press F5.
- **You should see:** the report again on *Training reminder test — 2.0*, and your row's Status reading *In progress, 1 of 2*, with today's date under Last activity.
- **If not:** stop and tell me your row's Status.
- **What it does:** checks the in-progress status.

**Checkpoint:** type your row's Status and Last activity.

## 6. Complete the course (normal window)

### 6.1 Answer the checkpoint

- **Where:** the normal window, the *Training reminder test* course page, the checkpoint box under *type the word test*.
- **Action:** type the word below in the box.

```
test
```

- **You should see:** the answer saved (the box keeps the word after you click outside it).
- **If not:** stop and tell me any message on the page.
- **What it does:** answers the course's one checkpoint.

### 6.2 Complete the course

- **Where:** the normal window, the *Training reminder test* course page.
- **Action:** press **Complete course**.
- **You should see:** the line *You completed this course, revision 2.0, on* today's date (as MM-DD-YY).
- **If not:** stop and tell me the message on the page.
- **What it does:** writes your completion.

**Checkpoint:** type the completion line the course page shows.

## 7. Your completion and answers (private window)

### 7.1 Reload the report

- **Where:** the private window from section 3, the *Training report* tab.
- **Action:** press F5.
- **You should see:** your row's Status reading *Completed 2.0 on* today's date (as MM-DD-YY), and the *completed* count one higher than in section 3.
- **If not:** stop and tell me your row's Status and the counts line.
- **What it does:** checks the completed status.

### 7.2 Open your answers

- **Where:** the private window, the *Training report* page, your row.
- **Action:** press **Answers** on your row.
- **You should see:** a pane on the right, *Answers:* and your name, the heading *Completed at 2.0 on* today's date, a small grey question ending in *type the word test.*, and under it *test* in a tinted box.
- **If not:** stop and tell me what the pane shows.
- **What it does:** checks the answers pane.

### 7.3 Close the private window

- **Where:** the private window.
- **Action:** press Ctrl+Shift+W.
- **You should see:** the private window gone.
- **If not:** close it with the window's own close button.
- **What it does:** ends Mentor Admin's sign-in.

**Checkpoint:** type what the answers pane showed, and whether anything on the report looked wrong or hard to read.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-21-26 23:05 | Claude (Claude Code) | Written for stop 3 after Doug's option A: the report shows no training sign-in, so the report half uses Doug's own row. |
