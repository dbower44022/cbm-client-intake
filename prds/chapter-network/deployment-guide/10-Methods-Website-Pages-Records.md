# New Chapter Deployment Guide — Methods for the Website Pages and the Existing Records

**Document:** The written-out steps for two stages — putting the chapter's pages on
its website (stage 13), and the first seven steps of bringing in the chapter's
records (stage 15, steps 15.1 to 15.7)
**Version:** 0.2
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 02:05

---

## What this is

Two more stages, written out from the design. Neither was covered by the August
build of the trial chapter, and neither has been done for a chapter.

The website stage is written from the events set-up runbook (`EVENTS-SETUP.md`,
section 6b), the software's own public pages, and the plan for the public mentor
pages (`prds/public-mentor-pages-plan.md`). The records stage is written from the
data model (`data-model.md`) and from the rules the public intake forms already
follow when they create records.

The last three steps of the records stage, which enter the mentors and create their
accounts (steps 15.8 to 15.10), are already written. They are in
`5-Methods-Form-Accounts-Checks.md` and are not repeated here.

Each step carries the same eight headings as the other methods documents.

**Two things change the step list.** The website stage was written when the
chapter's pages were going to be embedded in its website. Since 09-11-26 the events
programme is not embedded: the chapter's website sends visitors to a page the
application serves. And the mentor directory page does not exist yet. Both are set
out at the end, under "What writing these steps found".

---

# Stage 13 — Put the chapter's pages on its website

**Stage status: not yet tried.** The events programme page is live on Cleveland's
production system, but Cleveland's own website does not yet send visitors to it.
The mentor directory page has not been built.

There are two public pages.

- **The events programme page** is served by the application at `/webinars/`, with
  one page per event at `/webinars/` followed by the event's own name. Ruled
  09-11-26: the chapter's website redirects to this page rather than embedding it or
  rebuilding it. A redirect is a rule on the website that sends a visitor from one
  address to another.
- **The mentor directory page** is planned but not built. Its plan was written for
  embedding in the website, before the events ruling.

---

### 13.1 Display the mentor directory page

**Done when:** the page displays on the chapter's website, showing that chapter's
mentors. Blocked: the public mentor directory page is not built, and whether it is
embedded or reached by a redirect is not decided.

**Who:** central support organization, then the chapter for the website change.

**First:** the chapter's website is published (step 6.2), and the applications are
deployed (stage 11). Also the public mentor directory page is built, which it is
not.

**How to do it today:** it cannot be done. There is no public mentor directory page
in the software. The plan for it (`prds/public-mentor-pages-plan.md`, status "not
built") replaces Cleveland's current mentor pages, which are fed from a spreadsheet
through scripts. Until the page is built, a chapter has no mentor directory on its
website at all. Cleveland's spreadsheet method is not something a chapter should
copy.

What the software does have is the list of mentors inside the client application
form. That list lets an applicant name the mentor they would like. It needs no
website change, because the form is served by the application.

**How it will be done later:** the public mentor directory page is built. Then the
method is either a redirect from the website, as for events, or an embedded page, as
the mentor pages plan says. That choice has not been made. See "What writing these
steps found".

**How you know it worked:** a visitor to the chapter's website reaches a list of
that chapter's own mentors.

**What goes wrong:** not known, because the page does not exist.

**Status:** not yet tried. Blocked until the page is built.

---

### 13.2 Send the events address to the events programme page

**Done when:** the chapter's website sends visitors to the application's events page,
and that page shows the chapter's events.

**Who:** the chapter for the website change; central support organization for the
application settings.

**First:** the applications are deployed with the events switches on (stage 11), at
least one event is published, and the chapter's website is published (step 6.2).

**How to do it today:** follow section 6b of `EVENTS-SETUP.md`, replacing
Cleveland's addresses with the chapter's own.

1. Set the chapter's own values on the application: the website address, the
   website menu, the contact address for presenters, and the opening wording
   of the page. They are settings, changed on the application's settings page.
2. In the application's Event Administration page, create and publish each
   upcoming event. Saving through that page is what gives an event its own web
   address.
3. Open the application's `/webinars/` page and check the events appear.
4. On the chapter's website, save a copy of the current events page, if there is
   one. That copy is the way back.
5. On the chapter's website, add a temporary redirect (the kind numbered 302)
   from the website's events address to the application's `/webinars/` page. Use
   a temporary redirect, not a permanent one. Browsers remember a permanent
   redirect for a long time, so it outlives a decision to undo it.
6. Register once for an event with an obviously invented surname, then delete the
   contact and the registration this created.

**How it will be done later:** unchanged. The redirect is one rule on the website,
and removing it is the way back.

**How you know it worked:** in a private browser window, the chapter's own events
address lands on the application's events page, and the page lists that chapter's
events.

**What goes wrong:** three things.

The first: the page will not look like the chapter's website. It uses a copy of
Cleveland's website stylesheet, taken word for word so that the page matches
Cleveland's site. That stylesheet sets Cleveland's navy and gold itself, rather than
reading the chapter's colour file. So the chapter's colour file changes the rest of
the software but not these panels. This was confirmed by reading the stylesheet on
09-18-26.

The second: an event created straight in the CRM, rather than through Event
Administration, has no web address. Its title shows on the page as plain text with
nothing behind it.

The third: the events record in the CRM is also the chapter's internal calendar.
Only an event with "Publish to website" ticked appears on the public page. An
internal meeting published by mistake appears to the public.

**Status:** not yet tried for a chapter. The application's events page runs on
Cleveland's production system. Cleveland's own website has not yet been pointed at
it.

---

### 13.3 Allow only the chapter's own website to display these pages

**Done when:** the chapter's site can display them and a different site cannot.
Applies only to a page embedded in the website. The events programme page is
reached by a redirect, so this step does not apply to it.

**Who:** central support organization.

**First:** steps 13.1 and 13.2.

**How to do it today:** for the events programme page, there is nothing to do. The
page is not displayed inside the chapter's website. The website sends the visitor
to it. Any website can link or redirect to a public page, and that is harmless.

For the mentor directory page, this step matters only if it is embedded in the
website. The mentor pages plan says the application must then send a header naming
the one website allowed to embed it. The application sends no such header today.

**How it will be done later:** if the mentor directory page is embedded, the
application sends that header, set to the chapter's own website address.

**How you know it worked:** for an embedded page, the chapter's website shows it,
and a test page on any other address shows an empty frame.

**What goes wrong:** not known.

**Status:** not yet tried. For the events programme page, this step does not
apply.

---

### 13.4 Confirm links to a single mentor work

**Done when:** opening a link to one mentor lands on that mentor, and the address can
be copied and shared. Blocked until the public mentor directory page is built.

**Who:** central support organization.

**First:** step 13.1.

**How to do it today:** it cannot be done until the mentor directory page is built.

The same check applies to events, and can be done now: open one event's page from
the programme, copy its address from the address bar, and open that address in a
private window. It should land on the same event.

**How it will be done later:** the mentor pages plan keeps each mentor's address
the same as today's website address, so old links still arrive.

**How you know it worked:** a copied address opens the same mentor, or the same
event, in a private window.

**What goes wrong:** an event that is not published answers "not found". That is
deliberate: the events record doubles as the internal calendar, so a page that
merely showed nothing would still reveal that the event exists.

**Status:** not yet tried.

---

### 13.5 Confirm the public pages read properly on a computer and a phone

**Done when:** the pages show with no sideways scrolling and no cut-off text, on a
computer and on a phone.

**Who:** the chapter, checked by the central support organization.

**First:** steps 13.1 and 13.2.

**How to do it today:** for the events programme page, nothing is embedded, so
there is no inner frame to size. Check instead that the application's page reads
properly on a computer and on a phone. It is built to switch to one column at phone
width.

For the mentor directory page, this step waits for the page and for the choice
between redirect and embedding.

**How it will be done later:** unchanged for events.

**How you know it worked:** on a phone, the events page shows one column, with no
sideways scrolling and no text cut off.

**What goes wrong:** a page with no styling at all. The events page depends on class
names in that copied stylesheet. A mismatch shows unstyled panels with no error.
Cleveland shipped exactly this for an hour on 09-11-26, and a test now guards it.

**Status:** not yet tried.

---

# Stage 15, first seven steps — Bring in the chapter's existing records

**Stage status: not yet tried.** No chapter's records have ever been loaded, and the
software has no tool for loading them.

The chapter's records are its existing clients, the companies they run, their
contacts, its partners and funders, and its mentors. In the CRM they are linked in a
fixed order. A company comes first. A contact belongs to a company. A client
profile belongs to exactly one company. Each mentoring request, called an
engagement, belongs to a client profile. A mentor is a contact plus a mentor
profile. The load has to create them in that order, because each record needs the
one before it to link to.

---

### 15.1 Decide whether there are records to bring in

**Done when:** either the sources are listed, or a note records that the chapter
starts with nothing. A chapter starting with nothing skips the load (steps 15.2 to
15.7) but not the mentor steps after it (steps 15.8 to 15.10).

**Who:** the chapter decides; the central support organization records it.

**First:** the CRM system is built (stage 9).

**How to do it today:** the chapter lists every place it keeps records today:
spreadsheets, another CRM, an email list, a mentoring platform. Beside each, write
what kind of records it holds and roughly how many.

**How it will be done later:** unchanged.

**How you know it worked:** a written list of sources, or a written note that there
are none.

**What goes wrong:** a source nobody mentions until after go-live. Ask each member
of staff, not only the chapter's setup contact.

**Status:** not yet tried.

---

### 15.2 Export the existing records

**Done when:** every source has been exported to a file, and the number of records in
each file is written down.

**Who:** the chapter.

**First:** step 15.1.

**How to do it today:** export each source to a spreadsheet file, one file per kind
of record. Count the rows in each file and write the count down beside the file
name. Keep the files where only the people doing the load can reach them. They hold
personal details.

**How it will be done later:** unchanged.

**How you know it worked:** one file per source per kind of record, each with its
row count written down.

**What goes wrong:** an export that silently drops columns or rows. Open each file
and compare its row count with what the old system says it holds.

**Status:** not yet tried.

---

### 15.3 Map the old fields to the CRM's fields

**Done when:** every column in every export file is either mapped to a CRM field or
marked as not being brought across, with a reason.

**Who:** central support organization, with someone from the chapter who knows the
old records.

**First:** step 15.2.

**How to do it today:** list every column of every file in one table. Beside each,
write the CRM record and field it goes to, or "not brought across" and why. The
data model (`data-model.md`) names the records and their links.

Three kinds of field need care.

- **Choice lists.** Many CRM fields accept only values from a fixed list. For each
  such column, list the old values and the CRM value each one becomes. A company's
  type is one of Client, Sponsor, Partner or Other. Funders are "Sponsor" in the
  CRM, not "Donor" or "Donor/Sponsor". A value outside a list is refused, and for a
  multiple-choice field the whole record is refused with it.
- **Phone numbers.** The software stores phone numbers in one international form.
  A number with fewer than ten or more than fifteen digits is dropped rather than
  stored.
- **Mentor email addresses.** A mentor's chapter email address is the one their
  account is built on in step 15.9. Map it, not their personal address.

**How it will be done later:** unchanged.

**How you know it worked:** no column in any file is left without a line in the
table.

**What goes wrong:** a choice-list value mapped by guesswork. It is refused at load
time, or, where the software drops unknown values to save the rest of the record,
it stores nothing and nobody notices.

**Status:** not yet tried.

---

### 15.4 Do a trial load on a copy

**Done when:** the load has been run somewhere that is not the live system, and the
result has been looked at.

**Who:** central support organization.

**First:** step 15.3, and the rule for duplicates written down (step 15.5).

**How to do it today:** load into a copy of the chapter's own CRM server, made from
its latest backup. Create a new server from that backup, exactly as in the restore
test for the CRM server (step 12.3). Load into it, look at the result, then delete
the new server.

This copy is the right place for three reasons. It is the chapter's own CRM at the
chapter's own version and configuration, so the trial proves what the real load
will do. It holds nothing of Cleveland's. And it also completes the restore test for
the CRM server, which has never been done anywhere.

Two places are wrong for a trial. The shared training system holds Cleveland's
records and wipes itself every night. The trial chapter is kept for testing setup
steps, and a chapter's real personal details do not belong on it.

There is no loading tool yet. Either use the CRM's own import screen, one kind of
record at a time and in the order the links need, or write a script for this chapter
that uses the same find-or-create rules as the intake forms. The script is the
better choice when there are engagements to load. Checking whether the CRM's own
import screen can link each record to the one before it has not been done.

**How it will be done later:** a loading tool, built once, that reads the mapping
table from step 15.3.

**How you know it worked:** the counts in the copy match the counts from step 15.2,
with any difference explained. A handful of records, opened in the copy, look right.

**What goes wrong:** the trial copy holds real personal details. Delete it the same
day, and write down when it was deleted.

**Status:** not yet tried.

---

### 15.5 Resolve duplicates

**Done when:** the rule for deciding what counts as the same person or company is
written down and has been applied.

**Who:** central support organization proposes the rule; the chapter approves it.

**First:** step 15.2.

**How to do it today:** use the rule the intake forms already use, so that loaded
records and later form submissions agree.

- A person is the same person when the email address matches.
- A company is the same company when the name matches.
- A company has at most one client profile.

When two rows match, keep one record. Fill in its empty fields from the other row,
and never overwrite a field that already holds a value. This is how the forms treat
a repeat applicant.

**How it will be done later:** the CRM's own duplicate checking does part of this
at load time. Its settings have never been examined on either existing system. That
is item 3 on the work list, and until it is decided this step relies on the rule
above alone.

**How you know it worked:** no two contacts share an email address, and no two
companies share a name, unless the chapter has decided they are genuinely
different.

**What goes wrong:** two records for one mentor. An engagement assigned to the
wrong one is invisible to the mentor, which is a recurring trap on Cleveland's own
systems.

**Status:** not yet tried.

---

### 15.6 Do the real load

**Done when:** the records are in the live CRM and the counts match what was exported,
with any difference explained.

**Who:** central support organization.

**First:** steps 15.4 and 15.5.

**How to do it today:** run exactly the load that ran on the trial copy, into the
chapter's own CRM. Then make sure mentors can see their clients. Mentors see an
engagement only when their account is on that engagement's list of assigned users.
A loaded engagement does not get that entry by itself. Two things add it: the
nightly check that repairs assigned users, or the script
`scripts/audit_assignment_stamps.py` run with its repair option. The
mentor accounts do not exist until step 15.9, so run the repair after that step.

**How it will be done later:** the loading tool runs the repair itself.

**How you know it worked:** the counts in the CRM match the counts from step 15.2,
with any difference explained in writing.

**What goes wrong:** a large list read with a page size over 200. The CRM refuses
it rather than returning fewer rows. Inside a step that tolerates errors, that
refusal reads as "no records". A loading script must read in pages of 200 or fewer.

**Status:** not yet tried.

---

### 15.7 Check a sample

**Done when:** somebody who knows the old records has opened a sample in the CRM and
confirmed they are right.

**Who:** someone at the chapter who knows the old records.

**First:** step 15.6.

**How to do it today:** pick at least ten records of each kind, including the oldest,
the newest and a few with unusual details. Open each in the CRM and compare it with
the old record. Write down which records were checked and anything wrong.

**How it will be done later:** unchanged.

**How you know it worked:** a written list of checked records, each marked right or
corrected.

**What goes wrong:** checking only records that were easy to load. Include the rows
that caused trouble in the trial load.

**Status:** not yet tried.

---

The last three steps of this stage (15.8 to 15.10) are in
`5-Methods-Form-Accounts-Checks.md`.

---

## What writing these steps found

**1. The website stage is written for embedding, and the events programme is no
longer embedded.** Since 09-11-26 the chapter's website redirects to the
application's events page. Recommended step-list corrections:

- Step 13.2: "Done when: the chapter's website sends visitors to the application's
  events page, and that page shows the chapter's events."
- Step 13.3: say it applies only to a page that is embedded.
- Step 13.5: rename it "Confirm the public pages read properly on a computer and a
  phone".

**2. The mentor directory page does not exist, and nobody has decided whether it
will be embedded or reached by a redirect.** Its plan chose embedding on 08-14-26.
The events ruling on 09-11-26 went the other way. One reason it gave: a page shown
inside Cleveland's website falls under that website's restrictions on where images
may come from, so every event image would have had to be passed through the
website. Steps 13.1,
13.3, 13.4 and 13.5 cannot be completed until the page is built and that choice is
made. This belongs on the work list.

**3. The events page will show Cleveland's colours on every chapter's
deployment.** Its stylesheet is Cleveland's website stylesheet, copied word for
word, and it sets Cleveland's navy and gold itself. The chapter's colour file does
not reach it. This belongs on the work list with item 4, the starter colour file.

**4. There is no tool for loading a chapter's records.** Steps 15.4 and 15.6 name
two methods, the CRM's own import screen or a script written for the chapter.
Neither has been tried. Whether the import screen can link each record to the one
before it is unchecked. This belongs on the work list.

**5. The trial load doubles as the missing restore test.** Loading into a copy of
the chapter's CRM made from its backup completes the half of step 12.3 that has
never been done.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-18-26 02:05 | Finishing tests for steps 13.1 to 13.5 updated to match the step list: 13.2 and 13.5 renamed for the redirect, 13.3 applies only to an embedded page, 13.1 and 13.4 marked blocked. |
| 0.1 | 09-18-26 01:38 | First draft of the methods for putting the chapter's pages on its website and for the first seven steps of bringing in its records. Written from the events set-up runbook, the public mentor pages plan, the data model and the intake forms' rules for repeat submitters. Five findings: the website stage assumes embedding that the events ruling replaced, the mentor directory page is unbuilt and its method undecided, the events page carries Cleveland's colours, there is no loading tool, and the trial load can double as the restore test. |
