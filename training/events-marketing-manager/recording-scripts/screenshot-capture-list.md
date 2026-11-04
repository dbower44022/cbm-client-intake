# Screenshot capture list — Module 1, Create the event

Last Updated: 11-04-26 12:50 · Revision 1.2 — see change log at the end.

Seven screenshots, one per slide in module 1. Each one exists because its slide
names a control the reader has to find; none is decorative.

Until a file is in place the course shows a note naming the screenshot it wants,
so you can capture them in any order and drop them in as you go. No change to
the course is needed when you do.

## Before you start

- Capture these **in the same sitting as the module 1 recording**, and after
  it. Four of the seven are taken on the two events that
  `module-1-create.md` creates, and the sandbox is restored to a fixed
  snapshot every night, so the events are gone by morning.
- You are signed in as **Mark Marketing** on the training sandbox:
  ```
  https://cbm-client-intake-svxs3.ondigitalocean.app/
  ```
- **Hide your bookmarks bar and close other tabs** before the first capture.
  Tab titles and bookmarks end up in frame and date the screenshot.
- Capture **the control and enough around it to locate it**, not the whole
  screen. A full-screen shot of a 4K monitor reduces the thing being pointed at
  to a few pixels.
- Save every file as **PNG**, not as the capture tool's own `.smk` format — a
  browser cannot display a `.smk`, so the course cannot show one. If it is
  easier to save the `.smk` and convert afterwards, save it in the same folder
  and run:
  ```
  uv run python /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/smk-to-png.py
  ```
- **Capture the application only.** If the capture tool's own window, its
  layers panel or its filmstrip of recent captures is in frame, the screenshot
  teaches the tool instead of the application and has to be taken again.
- **Saving a file does not put it in the course.** Tell me when captures are
  in the folder and I publish them; that is what carries the images onto the
  page.
- Each step below gives the whole path to save to, in full, so you never have
  to look back at this block. They all land in this one folder, which already
  exists:
  ```
  /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/
  ```

---

## Section 1 — On the event list

1. In Event Administration, open the event list.
   You should see the list with **+ New event** above it and a **Shown** column
   on the right of each row.

2. Capture the list from the **+ New event** button down to four or five rows,
   including the whole **Shown** column.
   The frame must contain the + New event button and at least one row whose
   Shown column reads **Public** and one that reads **Hidden**. If no row reads
   Hidden, use the event you created in section 1 of the recording script
   before you ticked Show this event.

3. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-event-list.png
   ```

---

## Section 2 — On the new-event form

1. In Event Administration, click **+ New event**.
   You should see the event form open.

2. Capture the top of the form, from **Title** down far enough to include
   **Format**, **Capacity** and **Registration closes**.
   All four field labels must be legible in the frame. The boxes may be empty.

3. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-form-behaviour-fields.png
   ```

4. In the same event form, scroll to the **Publishing** group.
   You should see **Show this event**, **Audience** and **Display from**.

5. Capture the Publishing group so that all three controls are in one frame.

6. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-publishing-group.png
   ```

7. In the same event form, set **Audience** to:
   ```
   Internal
   ```
   You should see a **Limit to teams** box appear.

8. Capture the Audience control and the **Limit to teams** box together, in one
   frame, so the reader can see that one brought out the other.

9. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-limit-to-teams.png
   ```

10. At the bottom of the event form, click **Cancel**.
    You should see the form close with no new event in the list. This form was
    opened only for the three captures above.

---

## Section 3 — On the event created in the recording

These three are taken on **Cash Flow Basics for Small Business**, the event
section 1 of `module-1-create.md` creates.

1. In Event Administration, click the row for **Cash Flow Basics for Small
   Business**.
   You should see the event's own screen.

2. Capture the part of the event screen that holds the **Create / sync Zoom
   webinar** button, with enough around it to show it sits on the event.
   The button's full label must be legible.

3. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-zoom-button.png
   ```

4. On the event's screen, open the event form and scroll to the **Content**
   group.
   You should see the **Event graphic** control.

5. Capture the Event graphic control, including the **Choose image…** and
   **Upload graphic** buttons and the picture already uploaded during the
   recording.

6. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-event-graphic.png
   ```

7. In the same event form, scroll to the **Presenters** group under
   Sponsorship.
   You should see the two presenter entries added during the recording, Joe
   Mentor and Dana Whitfield.

8. Capture the Presenters group with both entries and the row controls
   (**Edit**, the photo buttons, **Up**, **Down**, **Remove**) in frame.

9. Save the capture as:
   ```
   /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/course/shots/m1-presenters.png
   ```

10. At the bottom of the event form, click **Cancel**.
    You should see the form close. Nothing in this section changes the event.

---

## Checkpoint

Tell me which of the seven files you captured, and name any control that was
worded differently on screen from the way this list writes it — the labels here
come from `event-administration.md`, and if the screen disagrees, the course
slides need correcting too.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 11-04-26 12:50 | Claude (Claude Code) | After the first capture came back as a `.smk` with the editor in frame, and did not appear because the shots were never in the publish: the PNG requirement and the converter, the capture-the-application-only rule, and the fact that a saved file reaches the page only when the course is published again. |
| 1.1 | 11-04-26 10:52 | Claude (Claude Code) | Doug, 11-04-26: always give full paths. Every save step now carries the whole path to save to, rather than a bare filename under a folder named once in the opening block. |
| 1.0 | 11-04-26 10:20 | Claude (Claude Code) | Created after Doug's 11-04-26 decision to carry the explanatory weight with screenshots rather than per-step clips. Seven captures, one per module 1 slide, each tied to a control its slide names. |
