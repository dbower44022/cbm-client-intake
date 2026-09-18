# New Chapter Deployment Guide — Methods for the Form, the Accounts and the Final Checks

**Document:** The written-out steps for three stages — filling in the chapter
information form (stage 8), creating the staff accounts (stage 14), entering the
mentors and creating their accounts (the last three steps of stage 15), and checking
everything works before going live (stage 17)
**Version:** 0.2
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 00:55

---

## What this is

Three more stages of the eighteen, written out in full. They come next because the
August build of the trial chapter tested all three, in whole or in part. The plan
for the guide was corrected on 09-15-26 to say so, but the methods for these three
were never written. Everything below comes from the record of that build, the
filled-in form it left behind, and the script that created its test users.

Each step carries the same eight headings as the methods for the CRM system, the
Google permissions and the applications. Where a heading has nothing to say, it
says so.

**The two labels mean what they meant before.** A step marked **done for real** was
performed on 31 August on the trial chapter and worked. A step marked **not yet
tried** has not been performed, and is written from the design plus whatever
failures are already known.

**Two things were found by writing these steps**, and each needs action.
They are set out at the end, under "What writing these steps found".

---

# Stage 8 — Fill in the chapter information form

**Stage status: done for real, apart from storing the secrets.**

The chapter information form is the list of roughly thirty-five values that differ
from one chapter to the next. Its blank copy is the last section of
`prds/chapter-network/chapter-values.md`. The trial chapter's filled-in copy is
`prds/chapter-network/rehearsal-2026-08-31/lakeside-values.yaml`, and it is the best
example to work from.

A chapter will not be able to fill in most of this form alone. The form is written
in the names the software uses, not in plain words. So this stage is done by the
chapter's setup contact and someone from the central support organization,
together.

---

### 8.1 Obtain the blank form

**Done when:** the chapter has the current blank form, and each section has a named
person responsible for it.

**Who:** central support organization supplies the form; the chapter names the
people.

**First:** the agreement is signed (step 2.6).

**How to do it today:** copy the blank form from the end of `chapter-values.md`.
Send the filled-in trial chapter form alongside it as a worked example. Mark each
section with who fills it in. The chapter's setup contact fills in the name, the
web addresses and the policy addresses. The central support organization fills in
the CRM details, the feature switches and the list of secrets.

**How it will be done later:** the fleet console asks for these values on screen
and checks each one as it is typed.

**How you know it worked:** every section of the form has a name beside it.

**What goes wrong:** the blank form falls behind the software. A new setting that
differs by chapter gets added to the software but not to the form. The information
check in the plan exists to catch this. Run it again whenever the software gains a
per-chapter setting.

**Status:** done for real. The trial chapter's form was filled in from this blank.

---

### 8.2 Fill in the chapter's name and identity

**Done when:** the chapter name, short label, time zone, currency and language are
filled in.

**Who:** the chapter.

**First:** the chapter's name is chosen (step 1.1).

**How to do it today:** write the name exactly as it should appear on every page,
for example "Akron Business Mentors". The short label is a lower-case single word,
used to name the chapter's servers and secrets, for example "akron". Currency and
language are almost always US dollars and US English.

**How it will be done later:** unchanged.

**How you know it worked:** the name matches the legal name, or the trading name
the board chose, letter for letter.

**What goes wrong:** the time zone. The software has the Eastern time zone written
into its code in four places. A chapter outside the Eastern United States gets wrong
dates without any error. Until the software is changed, write the chapter's real
time zone on the form. Then write "not supported yet" beside it, so nobody assumes
it has been applied. See the open time zone question in the plan.

**Status:** done for real. The trial chapter recorded Eastern time, which was the
only honest value available.

---

### 8.3 Fill in the web addresses

**Done when:** the application address, the website address, the events page
address, the documentation address, the colour file address and the four policy
addresses are filled in.

**Who:** the chapter, checked by the central support organization.

**First:** the website is published (step 6.2), the help documentation decision is
made (step 6.7), and the four policy addresses are recorded (step 7.6).

**How to do it today:** copy each address from the website, opening each one in a
browser first. Leave the application address empty. It does not exist until the
applications are deployed, and the deployment stage fills it in.

**How it will be done later:** unchanged.

**How you know it worked:** every address, opened in a private browser window, shows
the right page.

**What goes wrong:** a policy address that does not load. The public application
form links to all four policies from its consent box. A broken link there is a
legal problem, not a cosmetic one.

**Status:** done for real, with made-up addresses. The trial chapter had no
website, so nothing was opened.

---

### 8.4 Fill in the Google details

**Done when:** the branch chosen, the main domain, the shared operations mailbox, the
alert sending and receiving addresses, the members group, the shared drive and the
mentor email domain are filled in.

**Who:** the chapter, checked by the central support organization.

**First:** Google Workspace is set up (stage 4).

**How to do it today:** copy each address from the Google Workspace admin console.
The shared drive is recorded by its identifier, the string of letters in its web
address.

**How it will be done later:** unchanged.

**How you know it worked:** each mailbox named exists in the Google Workspace admin
console as a mailbox.

**What goes wrong:** writing a group where a mailbox is needed. The alert sending
address and the shared operations mailbox must both be real mailboxes with a
licence. A group or a second name for a mailbox fails later, with an error that does
not name the cause. Cleveland found this out when its administrator address turned
out to be a group.

**Status:** not yet tried. The trial chapter has no Google account, so this section
of its form is blank.

---

### 8.5 Fill in the CRM details

**Done when:** the CRM address, the name shown inside the CRM, the sending name, the
sending address and the logo file are filled in.

**Who:** central support organization.

**First:** the CRM's web address is chosen, and the logo image is produced
(step 6.6).

**How to do it today:** the CRM address is the web address the CRM will be published
at in step 9.6. The name shown inside the CRM and the sending name are usually the
chapter name. The sending address is a mailbox from step 4.

**How it will be done later:** unchanged.

**How you know it worked:** the section is complete, and the sending address is a
real mailbox.

**What goes wrong:** nothing known yet.

**Status:** done for real, apart from the sending address and the logo. The trial
chapter had neither.

---

### 8.6 Decide every feature switch

**Done when:** each switch has been deliberately set to on or off, and the branch the
application follows is recorded as the release branch rather than the development
branch.

**Who:** central support organization proposes; the chapter agrees.

**First:** steps 8.2 to 8.5.

**How to do it today:** go down the switch list in the form and write on or off for
each one. Never leave a switch blank. Every switch that uses Google stays off until
the Google checks at the end of the deployment stage pass (steps 11.14 to 11.18).
Automatic deployment is always off.

**How it will be done later:** the fleet console holds a standard set of switches
for a new chapter, and the chapter changes only what it needs.

**How you know it worked:** no blank switch on the form.

**What goes wrong:** a switch in the software that the form does not list. Until
09-18-26 the blank form was missing five switches the trial chapter needed. It has
been brought up to date, but it can fall behind again whenever the software gains a
switch.

**Status:** done for real.

---

### 8.7 List the secrets by name

**Done when:** all seven are listed by name with the holder named beside each. No
secret value is written on the form.

**Who:** central support organization.

**First:** step 8.6.

**How to do it today:** list the seven by name: the CRM key the applications use,
the name and password of the administrator account for creating logins, the
database address, the session secret, the encryption key for stored data, and the
Google key. Write beside each one who holds it.

**How it will be done later:** the secrets store lists them itself.

**How you know it worked:** seven names, seven holders, no values.

**What goes wrong:** listing six. Until 09-18-26 the blank form named six and
missed the encryption key, and the trial chapter's form missed the Google key. The
blank form now lists all seven. The encryption key is the one that matters. Changing the encryption key later makes every stored secret permanently
unreadable, so it is fixed from the moment it is created.

**Status:** done for real, as six. The seventh is known from writing the methods for
the deployment stage.

---

### 8.8 Put the chapter's secrets into the store

**Done when:** all seven of the chapter's secrets are held in the central support
organization's secrets store, at least two named people can reach each one, and none
of them exists only in a file on one person's computer.

**Who:** central support organization.

**First:** step 8.7, and the secrets store existing, which it does not.

**How to do it today:** it cannot be done. There is no secrets store. The trial
chapter's secrets sit in files on one laptop. This is item 1 in the work list
document, and this step stays blocked until it is built.

**How it will be done later:** the secrets are written into the store as each one is
created, rather than gathered here afterwards.

**How you know it worked:** a second named person opens each secret without help.

**What goes wrong:** treating a file on one laptop as good enough for a real chapter.
Regenerating the deployment settings from the hosting provider scrambles the
passwords inside them. Cleveland has lost working passwords that way.

**Status:** not yet tried. Blocked.

---

### 8.9 Review the completed form

**Done when:** two people have read the whole form together in one sitting and both
have signed it off.

**Who:** the chapter's setup contact and someone from the central support
organization.

**First:** steps 8.2 to 8.7.

**How to do it today:** go through the form line by line. Open every address. Read
every switch aloud with its setting.

**How it will be done later:** unchanged. A person still signs it off.

**How you know it worked:** both names and the date are written at the top of the
form.

**What goes wrong:** nothing known yet.

**Status:** not yet tried. The trial chapter's form was written and used by one
person.

---

### 8.10 Store the form where the central support organization can reach it

**Done when:** the form is in the agreed place and the central support organization
has confirmed it can open it.

**Who:** central support organization.

**First:** step 8.9.

**How to do it today:** add the form to the chapter-network folder in the software's
code repository, as the trial chapter's form was. Never store a secret value
in the form.

**How it will be done later:** the fleet console holds the form.

**How you know it worked:** a second person at the central support organization
opens it.

**What goes wrong:** a secret pasted into the form by mistake. The code repository
is not a secrets store.

**Status:** done for real.

---

# Stage 14 — Create the staff accounts

**Stage status: done for real.**

Only an administrator can create staff accounts, and nobody at the chapter holds an
administrator account. So the central support organization does this whole stage,
from a list the chapter approves. Mentors are not created here. Their accounts come
from their mentor records, at the end of the records stage (step 15.9).

---

### 14.1 Agree which staff get an account and which team they are on

**Done when:** a list names every member of staff, their email address and their
team, approved by the chapter. Mentors are not on this list.

**Who:** the chapter writes the list; the central support organization checks it.

**First:** the CRM system is built (stage 9).

**How to do it today:** the chapter lists each person with their chapter email
address and one team. There are nine teams, and seven of them open a page in the
applications:

- Client Administration Team
- Mentor Administration Team
- Mentor Team
- Partner Management Team
- Sponsor Management Team
- Marketing Admin Team
- Analytics Admin Team

A person who needs two jobs gets two teams. Give every person the fewest teams that
cover their work.

**How it will be done later:** the list is typed into the fleet console.

**How you know it worked:** every person on the list has a chapter email address and
at least one team.

**What goes wrong:** a personal email address on the list. Members of the chapter are
addressed at their chapter email address only. A personal address causes duplicate
calendar invitations and mail going to the wrong place.

**Status:** done for real, with seven made-up people, one per team.

---

### 14.2 Create the staff accounts

**Done when:** every person on the list has an account in the CRM on the right team.

**Who:** central support organization.

**First:** step 14.1.

**How to do it today:** create each account as an ordinary user, not an
administrator, with its teams from the list. The trial chapter's accounts were
created by the script `scripts/rehearsal/stage4_users.py`, which mints a password
of letters and numbers only. It is a trial script with the seven made-up people
written into it, so for a real chapter either adapt it to read the list, or create
the accounts by hand on the CRM's user administration screen. Tick the box that
emails each person their sign-in details.

**How it will be done later:** the fleet console creates the accounts from the list.

**How you know it worked:** each person signs in to the applications and sees a tile
for each of their teams, and no others.

**What goes wrong:** two known failures.

The first: a role missing from a team. A team gives its members permissions only
through the roles attached to it. On Cleveland's test system, two of the nine teams
carry no role at all, so a person whose only team is the Analytics Admin Team can
read nothing in the CRM. Check that the roles are attached (step 9.12) before
blaming the person's account.

The second: a partner or funder manager who has no mentor profile. The pages that
choose who manages a partner or a funder list mentor profiles, not user accounts.
A manager with an account but no mentor profile cannot be chosen. Give each partner
and funder manager a mentor profile in Mentor Administration. Fill in its chapter
email address first, exactly matching their account's user name. The software then
links the account that already exists instead of creating a second one.

**Status:** done for real. Seven accounts were created and each reported exactly its
one team on sign-in.

---

### 14.3 Confirm nobody at the chapter holds an administrator account

**Done when:** the only administrator accounts belong to the central support
organization. Chapter staff hold ordinary accounts.

**Who:** central support organization.

**First:** step 14.2.

**How to do it today:** on the CRM's user administration screen, filter by type and
read the list of administrators. Expect exactly two: the central support
organization's own administrator account (step 9.18) and the account the
applications use to create logins (step 9.17).

**How it will be done later:** the checking tool reports administrator accounts as
part of its run.

**How you know it worked:** the list holds those two and nothing else.

**What goes wrong:** a chapter asks for administrator access "just to fix one thing".
An administrator skips every permission check. That breaks the rule that every
chapter runs the same software, because an administrator can change the CRM's
setup. Refuse it, and route the request through a change request (step 18.2).

**Status:** done for real.

---

### 14.4 Confirm every member of staff has signed in

**Done when:** each member of staff has signed in at least once and set their own
password.

**Who:** the chapter chases; the central support organization checks.

**First:** step 14.2.

**How to do it today:** on the CRM's user administration screen, read the last
sign-in date for each account. Chase anyone blank. A person who has lost their
welcome email uses "Forgot your password?" on the applications' sign-in page.

**How it will be done later:** the fleet console shows the list.

**How you know it worked:** no account on the list has a blank last sign-in date.

**What goes wrong:** the welcome email going to spam, because the chapter's sending
address is new. Ask each person to check spam before re-sending.

**Status:** done for real for the seven test accounts. Not tried for real people.

---

# Stage 15, last three steps — Enter the mentors and create their accounts

**Stage status: not yet tried.**

Only the last three steps of this stage are written here. They moved here from the
staff accounts stage on 09-18-26, because a mentor's account has to be created from
their mentor record. The first seven steps, which load the chapter's existing
records, are still to be written from the design.

These three steps run for every chapter. A chapter starting with nothing skips the
load, but still has mentors.

---

### 15.8 Enter every mentor the load did not bring in

**Done when:** every current mentor has a mentor record in the CRM, with a linked
contact. For a chapter starting with nothing, this is every mentor.

**Who:** the chapter's mentor administrator.

**First:** the staff accounts, including the mentor administrator's (stage 14), and
the load, if there was one (step 15.7).

**How to do it today:** either have each mentor fill in the public volunteer form,
which creates both the contact and the mentor record, or enter each one in Mentor
Administration. The form is better for a large group. Each mentor types their own
details, and agrees to the code of ethics as they submit.

**How it will be done later:** unchanged.

**How you know it worked:** the Mentor Administration list holds every current
mentor, and each one shows a linked contact.

**What goes wrong:** the same mentor entered twice, once by the load and once by
hand. Two records with the same name make assignments go to the wrong one, and the
mentor then sees no clients. Search Mentor Administration by surname before entering
anyone.

**Status:** not yet tried.

---

### 15.9 Create the mentor accounts

**Done when:** every current mentor has an account, created from their mentor record
in Mentor Administration, and none was created by hand.

**Who:** the chapter's mentor administrator, with the central support organization
present for the first few.

**First:** step 15.8.

**How to do it today:** never create a mentor's account by hand. Open the mentor in
Mentor Administration and set their status to Active. The software then creates the
mentor's chapter mailbox if Google is switched on, creates their CRM account on the
Mentor Team, links the account to the mentor record, and emails the mentor their
sign-in details. The software records every one of these runs. The mentor
administrator does not need an administrator account for this. The software uses its
own administrator account to create the login (step 9.17).

**How it will be done later:** unchanged. Mentor Administration is the method.

**How you know it worked:** each mentor shows as complete in the Mentor
Administration list.

**What goes wrong:** an account created by hand before the mentor record has its
chapter email address. The software then treats the hand-made account as belonging
to a different person with the same name. It creates a second account with a number
added to the address, and sends a second welcome email. Cleveland had to clean up a
run of these duplicates.

**Status:** not yet tried. The trial chapter's one mentor account was created by a
script together with its mentor record, which a real chapter should not copy.

---

### 15.10 Confirm every mentor has signed in

**Done when:** each mentor has signed in at least once and set their own password.

**Who:** the chapter's mentor administrator chases; the central support organization
checks.

**First:** step 15.9.

**How to do it today:** as for staff (step 14.4). Read the last sign-in date for each
mentor's account on the CRM's user administration screen, and chase anyone blank.

**How it will be done later:** the fleet console shows the list.

**How you know it worked:** no mentor's account has a blank last sign-in date.

**What goes wrong:** as for staff: the welcome email lands in spam.

**Status:** not yet tried.

---

# Stage 17 — Check everything works before going live

**Stage status: done for real, apart from the website pages and the clean-up.**

Every check in this stage is done as an ordinary user. An administrator account
skips every permission check, so a check done as an administrator proves nothing.
Several of Cleveland's permission faults stayed hidden for weeks because they were
only ever tested by an administrator.

---

### 17.1 Create one ordinary test user per team

**Done when:** there is one non-administrator test account for each team.

**Who:** central support organization.

**First:** the staff accounts are created (stage 14).

**How to do it today:** run `scripts/rehearsal/stage4_users.py`, changing the
chapter name in it, or create the seven accounts by hand. Each account is an
ordinary user with exactly one team. The Mentor Team test user also needs a mentor
record linked to its account. Create that in Mentor Administration, as in step 15.9.

**How it will be done later:** the fleet console creates and removes a standard set
of test users.

**How you know it worked:** each test user signs in, and the sign-in reports exactly
one team.

**What goes wrong:** giving test users a second team "to make testing easier". The
check then proves nothing about the single-team case, which is the case real staff
are in.

**Status:** done for real.

---

### 17.2 Confirm each test user sees only what their team allows

**Done when:** every test user can open their own team's pages and is refused on
every other team's pages.

**Who:** central support organization.

**First:** step 17.1.

**How to do it today:** sign in as each test user and try every restricted page. The
trial chapter did this through the applications' own sign-in and recorded the
answer for seven users and twelve pages. The record is
`rehearsal-2026-08-31/nonadmin-gate-matrix.json`. Compare the new chapter's results
with it. Each user opens their own team's pages and is refused on the rest. The
Mentor Team user also opens the directory and My Email. Partner and funder managers
also open My Email.

**How it will be done later:** a script signs in as each test user and produces the
same table.

**How you know it worked:** the new table matches the trial chapter's table.

**What goes wrong:** reading "not found" as "refused". The settings page answered
"not found" to every trial user, and nobody knows why. The trial chapter's form
says the page was switched on. The page answers "not found" only when it is
switched off or has no database, so one of those was true, or the check asked for
the wrong address. The script that ran the check was not kept, so the question
cannot be settled from the record. On a real chapter, an ordinary user should be
refused with a message saying the page is for administrators. Treat "not found" as
a failure to explain, not a pass.

**Status:** done for real, apart from the settings page, whose answer is
unexplained.

---

### 17.3 Submit the public application form

**Done when:** a submission made from the public website arrives in the system.

**Who:** central support organization, or anyone at the chapter.

**First:** step 17.2, and the chapter's pages on its website (stage 13).

**How to do it today:** open the chapter's website in a private browser window.
Follow its link to the client application form and submit it with a made-up
business and a test email address the chapter controls. Write down the made-up
names, because step 17.9 removes them.

**How it will be done later:** unchanged. A person should do this once by hand.

**How you know it worked:** the form thanks the applicant and gives a reference
number. The submission appears in Submission Admin.

**What goes wrong:** the consent box's policy links. Open all four before
submitting.

**Status:** done for real, from the applications' own address. The trial chapter had
no website, so the website's link to the form was not tested.

---

### 17.4 Assign the submission

**Done when:** a client administrator test user assigns it to a mentor.

**Who:** central support organization, signed in as the Client Administration Team
test user.

**First:** step 17.3.

**How to do it today:** open Client Administration, find the new engagement, and
assign it to the Mentor Team test user's mentor record.

**How it will be done later:** unchanged.

**How you know it worked:** the engagement shows the mentor and the status "Pending
Acceptance", and the email to the mentor opens ready to send.

**What goes wrong:** the mentor list is empty. A mentor appears only when they are
Active, accepting new clients, and linked to an account. A second failure: the
assignment is refused with a permission error about users. The client
administration role needs permission to read users. Cleveland's role lacked it and
production still needs the fix. Check the role before the chapter's first real
assignment.

**Status:** done for real.

---

### 17.5 Confirm the mentor sees it

**Done when:** the mentor test user finds the assignment and can open their own
profile.

**Who:** central support organization, signed in as the Mentor Team test user.

**First:** step 17.4.

**How to do it today:** open Client Management and find the engagement. Then open My
Mentor Profile.

**How it will be done later:** unchanged.

**How you know it worked:** the engagement is listed and opens. The profile page
shows the mentor's own details.

**What goes wrong:** Client Management is empty. Nearly always, the mentor record is
not linked to the test user's account, or the engagement was assigned to a
duplicate mentor record with the same name. Check the link before anything else.

**Status:** done for real.

---

### 17.6 Confirm the submission closes

**Done when:** the submission shows as completed and closed to the user who handles
submissions.

**Who:** central support organization, signed in as the Marketing Admin Team test
user.

**First:** step 17.3.

**How to do it today:** open Submission Admin and find the submission.

**How it will be done later:** unchanged.

**How you know it worked:** its intake status reads Completed and it is closed, with
the reason "Process completed".

**What goes wrong:** the submission sits at Received. The background worker is not
running, or cannot reach the CRM. The application's health page reports whether
the worker is alive.

**Status:** done for real.

---

### 17.7 Confirm the CRM's own screen works for an ordinary user

**Done when:** a non-administrator signs in to the CRM itself and sees a working
screen.

**Who:** central support organization.

**First:** step 17.1.

**How to do it today:** sign in to the CRM's own web address as any test user.

**How it will be done later:** the checking tool loads the CRM's screen as an
ordinary user.

**How you know it worked:** the CRM's home screen and menu appear.

**What goes wrong:** a blank page. The CRM's standard setup has one custom screen
file stored outside the main configuration folder. If that file is not copied, the
CRM shows nothing at all. The trial chapter hit exactly this. The fix is in step 9.8.

**Status:** done for real, after the fix.

---

### 17.8 Confirm the website pages work for a member of the public

**Done when:** someone not signed in to anything opens the mentor directory and
events pages on the chapter's website and they work.

**Who:** the chapter.

**First:** stage 13.

**How to do it today:** open the chapter's website in a private browser window, on a
computer and on a phone. Open the mentor directory, one mentor, the events
programme and one event.

**How it will be done later:** unchanged.

**How you know it worked:** each page shows the chapter's own content in the
chapter's colours, with the chapter's name.

**What goes wrong:** a page with no styling at all. The events pages use the
website's own stylesheet. A mismatch between the page and that stylesheet shows
unstyled pages with no error. Cleveland shipped exactly this for an hour.

**Status:** not yet tried. The trial chapter had no website.

---

### 17.9 Remove the test records

**Done when:** the test submissions, test assignments and test users created for this
stage are gone or disabled, and it is written down what was removed.

**Who:** central support organization.

**First:** steps 17.2 to 17.8.

**How to do it today:** in the CRM, delete the made-up company, its contact, its
client profile and its engagement. In Submission Admin, the submission stays, closed.
It is the record that the path worked. Set the seven test users to inactive rather
than deleting them, so the check can be repeated after a later release. Write the
list of what was removed into the chapter's handover notes.

**How it will be done later:** the fleet console removes its own standard test data.

**How you know it worked:** the CRM holds no record with the made-up names, and the
seven test users cannot sign in.

**What goes wrong:** a test record left behind turns up in the chapter's reports. The
analytics pages count every engagement.

**Status:** not yet tried. The trial chapter's test records were kept on purpose.

---

## What writing these steps found

**1. Mentor accounts cannot come before mentor records.** The step list created the
staff and mentor accounts (stage 14) before bringing in the chapter's existing
records (stage 15). A mentor's account has to be created from their mentor record,
through Mentor Administration, or the software creates duplicate accounts. Ruled
09-18-26: mentor accounts move to the end of the records stage, as steps 15.8 to
15.10, and the staff accounts stage keeps staff only. The step list is corrected.

**2. The blank form is behind the trial chapter's form.** The blank form in
`chapter-values.md` names six secrets and nine switches. The trial chapter needed a
seventh secret and thirteen switches. The blank form has been brought up to the
trial chapter's version (09-18-26).

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-18-26 00:55 | Mentor accounts moved out of the staff accounts stage and written as the last three steps of the records stage (15.8 to 15.10), after Doug ruled on 09-18-26. Stage 14 is now staff only, and step 14.5 became step 14.4. The advice for partner and funder managers now says how to give them a mentor profile without creating a duplicate account. The blank form in `chapter-values.md` was brought up to date the same day. |
| 0.1 | 09-18-26 00:40 | First draft of the methods for three stages — filling in the chapter information form, creating the staff and mentor accounts, and checking everything works before going live. Written from the record of the 31 August build, the trial chapter's filled-in form, the script that created its test users, and the table of which pages each test user could open. Two findings: mentor accounts cannot come before mentor records, and the blank form is behind the trial chapter's form. One gap in the August record noted: the settings page answered "not found" to every test user, and the record cannot say why. |
