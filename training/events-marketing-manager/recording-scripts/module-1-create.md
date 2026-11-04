# Recording script — Module 1, Create the event

Last Updated: 11-04-26 01:05 · Revision 1.0 — see change log at the end.

Three walkthroughs for module 1 of *Running an event*. One section per video.
Numbering restarts in each section.

Every value you must type is in its own block so it can be copied whole.

## Before you start

- You are recording on the **training sandbox**, never on production. Its
  address is
  ```
  https://cbm-client-intake-svxs3.ondigitalocean.app/
  ```
- You are signed in as **Mark Marketing**, whose user address is
  ```
  mark.marketing@cbmentors.org
  ```
  Ask an administrator for the password; the sandbox addresses are not real
  mailboxes, so a password-reset email will never arrive.
- **Do not record as an administrator.** An EspoCRM administrator bypasses
  access control and sees a different application, so an admin recording
  teaches screens the audience will never meet. Mark Marketing holds the
  Marketing Admin Team, which is what gates Event Administration.
- **Record all three videos in one sitting.** The sandbox is restored to a
  fixed snapshot every night, so the event you create in section 1 is gone by
  morning and sections 2 and 3 would have to start again.
- Close every other application window. A notification from a real mailbox in
  shot is a re-record.
- Set the browser window wide enough that the event form shows its panels in
  columns. The form opens sized to your screen and can be dragged bigger by its
  **bottom-right corner**.

---

## Section 1 — Create a virtual public webinar

The spine of the module: the form, the four fields that carry behaviour, the
save, and the Zoom webinar.

1. In the browser, go to the address below and press Enter:
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/
   ```
   You should see the portal sign-in page, with the organisation's name above
   the form. If you see a list of intake forms instead, you are on the dev
   deployment; stop and tell me exactly what the address bar says.

2. In the sign-in form, type the address below into the **Email** box:
   ```
   mark.marketing@cbmentors.org
   ```
   You should see the address in the box and no error. If the box rejects it,
   stop and tell me exactly what it says.

3. In the sign-in form, type Mark Marketing's password into the **Password**
   box and press Enter.
   You should see the portal home page, with a tile for **Event
   Administration**. If you see "that team is required", stop and tell me
   exactly which team it names.

4. On the portal home page, click the **Event Administration** tile.
   You should see the event list, with a **+ New event** button above it and a
   **Shown** column on the right of each row.

   **Say:** this is where every event starts, because this screen is what gives
   an event its web address.

5. On the event list, click **+ New event**.
   You should see the event form open as a large window with **Save** and
   **Cancel** pinned at the bottom.

6. In the event form, type the line below into **Title**:
   ```
   Cash Flow Basics for Small Business
   ```
   You should see the title in the box.

   **Say:** the title generates the web address, and the address is then fixed
   — later title edits do not move it, so links already shared keep working.

7. In the event form, type the line below into **Summary**:
   ```
   A one-hour look at the cash flow numbers every small business owner should watch.
   ```
   You should see the sentence in the box.

8. In the event form, set **Format** to:
   ```
   Virtual
   ```
   You should see Virtual selected.

   **Say:** format is what decides whether a Zoom webinar gets created. Virtual
   and Hybrid get one; In-Person does not.

9. In the event form, set **Event type** to:
   ```
   Online Webinar
   ```
   You should see Online Webinar selected.

10. In the event form, set **Topic** to:
    ```
    Operations
    ```
    You should see Operations selected.

11. In the event form, set **Starts** to a date **two weeks after the day you
    are recording**, at this time:
    ```
    12:00 PM
    ```
    You should see the date and time in the control. The date must be in the
    future — a past start changes what the calendar and the Zoom button do, and
    this walkthrough is about an upcoming event.

12. In the event form, set **Duration** to:
    ```
    60
    ```
    You should see 60 minutes.

13. In the event form, leave **Capacity** empty.

    **Say:** empty means unlimited. Zero does not mean full — it also means
    unlimited, which is the one trap on this form.

14. In the event form, leave **Registration closes** empty.

    **Say:** left empty, registration closes when the event starts.

15. At the bottom of the event form, click **Save**.
    You should see the form close and the new event appear in the list, with
    its **Shown** column reading **Hidden**.

    **Say:** saving creates the event. It does not show it anywhere and it does
    not create a Zoom webinar — both are separate, deliberate acts.

16. In the event list, click the row for **Cash Flow Basics for Small
    Business**.
    You should see the event's own screen, with its tabs across the top.

17. On the event's screen, click **Create / sync Zoom webinar**.
    You should see a confirmation that the webinar was created, and a join link
    stored on the event. If the button answers that Zoom is not connected, stop
    and tell me exactly what it says.

    **Say:** this provisions the webinar under the shared Zoom host.
    Registration is auto-approved, so people who sign up on the website are
    added to the webinar automatically.

18. On the event's screen, open the event form again and tick **Show this
    event**.
    You should see the tick set.

19. In the event form, set **Audience** to:
    ```
    Public
    ```
    You should see Public selected.

    **Say:** three separate questions decide who sees an event. Show this event
    decides whether, Audience decides where, Display from decides when.

20. At the bottom of the event form, click **Save**.
    You should see the list's **Shown** column for this event now read
    **Public**. If it reads Hidden, stop and tell me exactly what the Publishing
    group of the form shows.

**Checkpoint.** Send me the recording of section 1 and the **Shown** value you
ended on.

---

## Section 2 — Create an internal event limited to teams

The same form, answering the three visibility questions differently. This is
where the Zoom button goes away and a Join URL box appears in its place.

1. On the event list in Event Administration, click **+ New event**.
   You should see the event form open.

2. In the event form, type the line below into **Title**:
   ```
   Marketing Team Planning Session
   ```
   You should see the title in the box.

3. In the event form, type the line below into **Summary**:
   ```
   An internal working session for the marketing team.
   ```
   You should see the sentence in the box.

4. In the event form, set **Format** to:
   ```
   Virtual
   ```
   You should see Virtual selected.

5. In the event form, set **Event type** to:
   ```
   Online Webinar
   ```
   You should see Online Webinar selected.

6. In the event form, set **Topic** to:
   ```
   Operations
   ```
   You should see Operations selected.

7. In the event form, set **Starts** to a date **ten days after the day you are
   recording**, at this time:
   ```
   10:00 AM
   ```
   You should see the date and time in the control.

8. In the event form, set **Duration** to:
   ```
   60
   ```
   You should see 60 minutes.

9. In the event form, set **Audience** to:
   ```
   Internal
   ```
   You should see Internal selected, and a **Join URL** box appear under Place
   & capacity. If no Join URL box appears, stop and tell me exactly what the
   Place & capacity group shows.

   **Say:** an Internal event never gets a Zoom webinar, even from the button —
   so the form offers a Join URL box instead, for your own Zoom room, Meet or
   Teams. On a Public event the box is not offered, because Zoom owns that link
   and would write over anything typed there.

10. In the event form, type the line below into **Join URL**:
    ```
    https://example.com/internal-planning-room
    ```
    You should see the address in the box.

11. In the event form, set **Limit to teams** to:
    ```
    Marketing Admin Team
    ```
    You should see Marketing Admin Team listed in the box.

    **Say:** this decides who sees the event on the portal. It is not a
    permission — anyone who can read events in the CRM can still find it, so
    genuinely confidential meetings stay off the calendar altogether.

12. In the event form, tick **Takes registrations**.
    You should see the tick set.

    **Say:** this gives members a Register button. It also decides who sees the
    join link: with registrations off the link shows to everyone, with them on
    it shows only to members who have registered.

13. In the event form, tick **Show this event**.
    You should see the tick set.

14. At the bottom of the event form, click **Save**.
    You should see the list's **Shown** column for this event read **Internal,
    limited**. If it reads anything else, stop and tell me exactly what it says.

**Checkpoint.** Send me the recording of section 2 and the **Shown** value you
ended on.

---

## Section 3 — The graphic and the presenters

Both attach to a **saved** event, which is why this section works on the event
created in section 1 rather than starting a new one.

1. On the event list in Event Administration, click the row for **Cash Flow
   Basics for Small Business**.
   You should see the event's own screen.

2. On the event's screen, open the event form and scroll to the **Content**
   group.
   You should see an **Event graphic** control with a **Choose image…** button.

3. In the Content group, click **Choose image…** and pick any JPEG or PNG under
   5 MB from your own machine.
   You should see the file's name appear beside the buttons.

4. In the Content group, click **Upload graphic**.
   You should see the picture appear in the control. If it refuses the file,
   stop and tell me exactly what it says.

   **Say:** without a graphic the website's calendar card falls back to the
   recording's video thumbnail — and an upcoming event has no recording, so it
   would have no picture at all.

5. In the event form, scroll to the **Presenters** group under Sponsorship.
   You should see a search box. If there is no Presenters group, stop and tell
   me what the Sponsorship group shows — the group needs Presenters on events
   switched on.

6. In the Presenters group, type the name below into the search box:
   ```
   Joe Mentor
   ```
   You should see Joe Mentor offered, marked **Mentor**.

7. In the list of results, click **Joe Mentor**.
   You should see him added as a presenter entry carrying his biography, his
   mentor title and his photo.

   **Say:** adding a mentor copies their public biography, title and photo onto
   this event's entry — once. From here it is the event's own text: editing it
   changes nothing on his profile, and it is never re-copied. A past event's
   page is the record of what was presented.

8. In the Presenters group, click **+ New presenter**.
   You should see a small form asking for first name, last name, email, title
   and company.

9. In the new-presenter form, type the value below into **First name**:
   ```
   Dana
   ```

10. In the new-presenter form, type the value below into **Last name**:
    ```
    Whitfield
    ```

11. In the new-presenter form, type the value below into **Email**:
    ```
    dana.whitfield@sandbox.cbmentors.org
    ```

12. In the new-presenter form, type the value below into **Title**:
    ```
    Controller
    ```

13. In the new-presenter form, type the value below into **Company**:
    ```
    Harrowgate Family Trust
    ```

14. In the new-presenter form, click **Add**.
    You should see Dana Whitfield added as a second presenter entry, with her
    title and company filled and her biography empty.

    **Say:** the email is what the CRM is checked against, so a presenter
    already on file is reused rather than duplicated.

15. In the Presenters group, on Dana Whitfield's row, click **Up**.
    You should see her move above Joe Mentor.

16. In the Presenters group, on Dana Whitfield's row, click **Down**.
    You should see her move back below Joe Mentor.

17. In the event form, in the **Publishing** group, tick **Show presenter
    biographies**.
    You should see the tick set.

    **Say:** ticked, the event page shows each presenter's biography under
    their name. To hide one presenter's biography while showing the others,
    leave theirs empty — which is exactly what Dana's entry is.

18. At the bottom of the event form, click **Save**.
    You should see the form close with no error.

**Checkpoint.** Send me the recording of section 3, and tell me whether the
graphic and both presenters were still on the event after the save.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-04-26 01:05 | Claude (Claude Code) | Created with module 1 of the course. Three sections, one per video, written from `event-administration.md` and the training sandbox's own demo records. Interface labels are taken from that guide; any that the live screen words differently should be corrected here before recording. |
