# New Chapter Deployment Guide — The Step List

**Document:** The bare list of steps, with no methods yet
**Version:** 0.20
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-23-26 20:40

---

## What this is

This is the skeleton of the guide, and nothing more. It lists every step a new
chapter goes through, in order, and says what must be true when each step is
finished. It does not yet say how to do any of them.

That is deliberate. The three completeness checks in the plan document run against
this list. Filling in polished instructions before the list is checked produces a
document that reads well and still has holes, and once the writing is good the
holes stop being visible.

**How to read a step.** Each one has a number, a short name, and a line beginning
**Done when**. The "done when" line is the test. If you cannot tell whether it has
been met, the step is badly written and needs fixing.

**Who does what** is not marked yet. It is one of the eight headings each step will
carry once the methods are written.

---

## Stage 1 — Set up the chapter as a legal organization

**1.1 Choose the chapter's name.**
Done when:

- The founding group has agreed one name.
- A search of state business registrations and trademarks shows no conflict.
- The matching domain names are still available to buy.

**1.2 Incorporate the chapter.**
Done when: the state has accepted the articles of incorporation and returned a
stamped copy.

**1.3 Get a federal employer identification number.**
Done when: the number has been issued and the confirmation letter is filed.

**1.4 Appoint a board and adopt bylaws.**
Done when:

- Bylaws are adopted.
- Directors are named.
- The minutes record which officers may sign contracts.

**1.5 Obtain nonprofit tax status, or a sponsorship arrangement.**
Done when: either the determination letter from the tax authority has arrived, or a
signed sponsorship agreement is in place naming the sponsoring nonprofit.

**1.6 Open a bank account.**
Done when: the account is open and at least two officers can authorise a payment.

**1.7 Name the person who acts for the chapter during setup.**
Done when: one named person is recorded as the chapter's main contact for the whole
setup, with authority to open accounts and grant access to others.

---

## Stage 2 — Sign the agreement with the central support organization

**2.1 Agree what the central support organization does.**
Done when:

- The chapter has in writing the list of what is provided.
- The chapter has in writing what is not provided.
- The chapter has in writing how quickly ordinary requests are answered.

**2.2 Agree the cost.**
Done when: the fee is agreed in writing, and it is clear which costs the chapter
pays directly to other companies rather than through the fee.

**2.3 Accept the identical-software rule.**
Done when: the chapter's board has been told in writing that no chapter gets its
own custom fields, form questions or list choices, and has been shown how to ask
for a change that would apply to every chapter.

**2.4 Agree the access the central support organization will hold.**
Done when: it is written down which of the chapter's accounts the central support
organization will administer, and that the chapter may withdraw that access at any
time.

**2.5 Agree the leaving terms.**
Done when:

- The notice period is written into the agreement.
- The wind-down is written into the agreement.
- The list of everything the chapter takes with it is written into the agreement.

**2.6 Sign the agreement.**
Done when: both sides have signed and each holds a copy.

**2.7 Set up the chapter's password vault.**
Done when: the chapter owns a Proton Pass business organization with at least two
chapter owners, and at least two named people from the central support organization
are members of its shared operations vault (ruled 09-18-26).

---

## Stage 3 — Register the chapter's domain names

**3.1 Choose the founding email address used for setup.**
Done when: one named person's existing working email address is recorded as the
address that will create the first accounts, and it is understood that this is
temporary.

**3.2 Decide how many domain names the chapter needs, and choose them.**
Done when: the names are chosen and confirmed available. See the open question in
the plan document about whether a chapter needs one domain name or two.

**3.3 Create the domain registrar account.**
Done when:

- The account exists.
- The account is in the chapter's name.
- The account uses the founding email address.

**3.4 Register and pay for the domain names.**
Done when: a public ownership lookup returns the chapter as the registrant, and the
registration runs at least a year ahead.

**3.5 Turn on automatic renewal.**
Done when: every domain name is set to renew automatically and a working payment
method is on file.

**3.6 Turn on two-step sign-in for the registrar account.**
Done when: signing in requires a second factor, and the recovery codes are stored
where more than one person can reach them.

**3.7 Move the domain names' DNS to the chapter's Cloudflare account.**
Done when:

- Each domain name is a zone in a Cloudflare account the chapter owns, or, with manual DNS, is hosted in a DNS provider account the chapter owns.
- The registrar points at Cloudflare's name servers, or, with manual DNS, at the chapter's DNS provider's.
- Two-step sign-in is on.
- The central support organization's named people are members.
- The sign-in and recovery codes are in the chapter's vault.

Note: CRMBuilder writes DNS records only into Cloudflare. With manual DNS it shows each record, and a person adds it at the chapter's DNS provider (ruled 09-23-26).

---

## Stage 4 — Set up Google Workspace and the chapter's email

**4.1 Confirm the chapter will hold its own Google Workspace.**
Done when: the board has recorded that the chapter will hold its own Google Workspace,
in its own name and on its own domain.

Note: Ruled 09-18-26: every chapter hosts its own email on its own Google Workspace. The central support organization does not provide Google Workspace.

**4.2 Create the Google Workspace account.**
Done when: the account exists on the chapter's email domain and the first
administrator can sign in.

**4.3 Verify the domain.**
Done when: Google reports the domain as verified.

**4.4 Switch mail delivery to Google.**
Done when: a message sent from outside to an address on the domain arrives in the
Google mailbox.

**4.5 Create the chapter's own administrator account.**
Done when: a named person at the chapter holds a Google Workspace administrator
account on a chapter address.

**4.6 Create the central support organization's administrator account.**
Done when: the central support organization holds its own named administrator
account, separate from the chapter's.

**4.7 Create the shared operations mailbox.**
Done when: the shared address the software reads and sends from exists as a real
licensed mailbox, not as an alias or a group. An alias will not work.

**4.8 Create the alert sending mailbox.**
Done when: the address the software sends its warning messages from exists as a
real licensed mailbox. An alias or a group will be refused.

**4.9 Decide who receives the system's warning messages.**
Done when: the receiving address is decided and it reaches a person who reads it
during the working week, not an unattended mailbox.

**4.10 Create the members group.**
Done when: the group exists at its own address and the administrator can add and
remove members.

**4.11 Create the staff mailboxes.**
Done when: every member of staff who will use the system has a mailbox on the
chapter's domain. Mentors' mailboxes are created later, from their mentor records
(step 15.9).

**4.12 Require two-step sign-in.**
Done when: two-step sign-in is enforced for every account, and recovery is possible
without one person.

**4.13 Apply for the nonprofit discount.**
Done when: the application has been submitted with the chapter's nonprofit
evidence, and the expected answer date is recorded.

**4.14 Move control of the registrar account to a chapter mailbox.**
Done when:

- The registrar account's contact address is a chapter mailbox.
- The founder's personal address has been removed.
- A password reset test lands in the chapter mailbox.

---

## Stage 5 — Open the hosting and video meeting accounts

**5.1 Create the server hosting account.**
Done when: the account exists in the chapter's name, using a chapter mailbox.

**5.2 Set up billing on the hosting account.**
Done when: a chapter payment method is on file and the billing contact is a chapter
mailbox.

**5.3 Apply for the nonprofit hosting credits.**
Done when: the application is submitted and the expected answer date is recorded.

**5.4 Grant the central support organization access to the hosting account.**
Done when: the central support organization can create and manage servers in the
account under its own named sign-in, and the chapter can remove that access itself.

**5.5 Create the video meeting account, or record that it is not needed.**
Done when: either the account exists with a chapter mailbox as its host address and
an app that lets the software schedule webinars through it, or a note records that
this chapter runs no public webinars.

**5.6 Turn on two-step sign-in for both accounts.**
Done when: two-step sign-in is on and recovery does not depend on one person.

**5.7 Write down every account the chapter now owns.**
Done when:

- One list names each account.
- The list gives each account's web address.
- The list says who holds the top-level sign-in.
- The list says who else has access.

**5.8 Create the two tokens CRMBuilder builds with.**
Done when:

- A DigitalOcean API token from the chapter's hosting account exists.
- A Cloudflare API token limited to editing DNS in the chapter's zones exists, unless the chapter uses manual DNS.
- Both tokens are in the chapter's vault.
- Both tokens are entered in CRMBuilder as the chapter's provider credentials.

Note: CRMBuilder builds the chapter's CRM with the chapter's own accounts, never its own (ruled 09-18-26).

---

## Stage 6 — Build the chapter's public website

**6.1 Choose the website platform.**
Done when: the choice is made and someone is named to build and maintain the site.

**6.2 Publish the website.**
Done when: the site loads at the chapter's website domain over a secure connection.

**6.3 Confirm the website can redirect an address to another site.**
Done when: a test address on the site sends the visitor to a page on another site,
by a temporary redirect. (Checking that the site can embed a page returns once the
public mentor directory page is built and its method is decided.)

**6.4 Confirm someone at the chapter can edit the website.**
Done when: a named person at the chapter has signed in and made a change.

**6.5 Choose the chapter's colours and publish the colour file.**
Done when:

- The chapter's colours are chosen.
- The colours are written into a small stylesheet.
- The stylesheet is published at a web address the software can load.

Note: Colours are the only visual difference between chapters in the software, so a chapter that skips this looks exactly like Cleveland.

**6.6 Produce the chapter's logo image.**
Done when: an image file of the chapter's logo exists in a form the CRM system
accepts. The applications carry no logo; the CRM system does, and it is the only
per-chapter image in the whole system.

**6.7 Decide where the chapter's help documentation lives.**
Done when: either the chapter has its own documentation site published at its own
address, or it is recorded that the chapter points at a shared one. Two later steps
link to this address, so it cannot be left undecided.

---

## Stage 7 — Write and publish the policy documents

**7.1 Write and publish the client code of conduct.**
Done when: the document is published on the chapter's website and opens without
signing in.

**7.2 Write and publish the mentor code of ethics.**
Done when: the document is published and opens without signing in.

**7.3 Write and publish the terms.**
Done when: the document is published and opens without signing in.

**7.4 Write and publish the privacy policy.**
Done when:

- The document is published.
- The document opens without signing in.
- The document names this chapter rather than any other organization.

**7.5 Have the four documents reviewed.**
Done when: whoever advises the chapter on legal matters has read all four and
confirmed they may be published.

**7.6 Record the four web addresses.**
Done when: all four addresses are written on the chapter information form and each
one has been opened and checked.

---

## Stage 8 — Fill in the chapter information form

**8.1 Obtain the blank form.**
Done when: the chapter has the current blank form and knows who fills in each part.

**8.2 Fill in the chapter's name and identity.**
Done when:

- The chapter name is filled in.
- The short label is filled in.
- The time zone is filled in.
- The currency is filled in.
- The language is filled in.

**8.3 Fill in the web addresses.**
Done when:

- The application address is filled in.
- The website address is filled in.
- The events page address is left empty, so the software uses its own events page.
- The documentation address is filled in.
- The colour file address is filled in.
- The four policy addresses are filled in.

**8.4 Fill in the Google details.**
Done when:

- The main domain is filled in.
- The shared operations mailbox is filled in.
- The alert sending address is filled in.
- The alert receiving address is filled in.
- The members group is filled in.
- The mentor email domain is filled in.

**8.5 Fill in the CRM details.**
Done when:

- The CRM address is filled in.
- The name shown inside the CRM is filled in.
- The sending name is filled in.
- The sending address is filled in.
- The logo file is filled in.

**8.6 Decide every feature switch.**
Done when: each switch has been deliberately set to on or off, and the branch the
application follows is recorded as the release branch rather than the development
branch.

**8.7 List the secrets by name.**
Done when:

- All seven are listed by name with the holder named beside each.
- The video meeting app's secret is listed too, for a chapter that runs webinars.
- No secret value is written on the form.

Note: Seven, not six: besides the six the planning documents name, the applications use an encryption key for stored data that the settings generator creates quietly on first run. Changing it later destroys the data it protects, so it is permanent from the moment it exists.

**8.8 Put the chapter's secrets into the store.**
Done when:

- Every secret a person holds is in the chapter's Proton Pass Operations vault (step 2.7). That is all seven except the database connection, which the hosting platform holds (step 11.4).
- At least two named people can reach each one.
- None of them exists only in a file on one person's computer.

**8.9 Review the completed form.**
Done when: two people have read the whole form together in one sitting and both
have signed it off.

**8.10 Store the form where the central support organization can reach it.**
Done when: the form is in the agreed place and the central support organization has
confirmed it can open it.

---

## Stage 9 — Build the CRM system

Not possible yet, and built without for now: the standard's duplicate checking,
saved views and automated rules (work list item 3). Until 09-23-26 this was step
9.16.

**9.1 Write down the versions to build with.**
Done when:

- The CRM build versions note names both add-on products and their versions.
- Both versions support CRM version 10.
- The note names the release of the standard configuration.

**9.2 Prepare the build computer.**
Done when:

- The server sign-in key exists on the build computer, and its public half is in the chapter's DigitalOcean account.
- The CRM administrator password is in the vault, and holds letters and numbers only.
- The chapter's settings file holds the CRM's address and the administrator's name and password.

**9.3 Run CRMBuilder's deploy wizard.**
Done when:

- The run reads Deployment complete.
- The server's address is in the vault.

**9.4 Confirm the server works.**
Done when:

- A command runs on the server over the chapter's sign-in key, and the key is in the vault where a second person can open it.
- The CRM's address leads to the server.
- The CRM loads at its address with no certificate warning, and the certificate renews by itself.
- The CRM's version, 10 or higher, is in the vault.

**9.5 Install the two paid add-on products.**
Done when:

- Both products are installed at the versions in the CRM build versions note.
- Both are licensed to this chapter.

Note: They must be installed before step 9.7, because the roles that step creates refer to them.

**9.6 Copy the standard configuration onto the server.**
Done when:

- Both folders are on the server and owned by the web server's user.
- The rebuild finished without errors.
- The CRM shows its normal working screen.

Note: There are two folders, not one.

**9.7 Apply the standard with one script.**
Done when:

- The script reports every team, role, attachment, template, setting and account applied and read back identical, apart from the expected leftovers described under If it didn't work.
- The Client Assignment Role can read all users.
- The applications' key answers a test request, and is in the vault.
- The provisioning administrator signs in, and its password is in the vault.
- Every team carries a role.

**9.8 Stamp the configuration version.**
Done when: the record exists, and the applications' key can read it.

**9.9 Run the checking tool.**
Done when: the checking tool reports that the CRM matches the standard, apart from
differences that are written down with their reasons.

---

## Stage 10 — Set up the Google permissions the software needs

**10.1 Create the machine account.**
Done when: the account the software will use exists in the chapter's Google
account.

**10.2 Download and store its key.**
Done when: the key file is stored as a secret and is not left on anyone's laptop or
in email.

**10.3 Enter the permission grant.**
Done when: the grant is entered in the chapter's own Google admin console with the
exact list of permissions, and the list has been checked item by item against the
standard. A missing permission fails later with a message that names nothing
useful.

**10.4 Name the mailbox the software acts as.**
Done when: the mailbox is named, and it is a real licensed mailbox rather than a
group or an alias. A group or alias is refused.

**10.5 Create the shared drive and add the machine account.**
Done when: the shared drive exists and the machine account is a member of it.

---

## Stage 11 — Deploy the chapter's applications

**11.1 Generate the session secret.**
Done when: a new random session secret has been generated for this chapter alone
and stored in the secrets store. It is never copied from another chapter.

**11.2 Generate the deployment settings.**
Done when: the settings are produced from the chapter information form and every
value in them traces back to a line on that form.

**11.3 Load the secrets.**
Done when:

- Every secret is loaded into the deployment, including the Google key.
- The session secret is loaded.
- The stored-data encryption key is loaded.
- None of them appears in a file anyone can read.

Note: The database connection is not among them — the hosting platform supplies that to the application directly.

**11.4 Create the database.**
Done when:

- The database exists in the chapter's hosting account.
- Its connection details are supplied to the application by the hosting platform, and no person holds them.
- The application can reach it.

**11.5 Create the application parts.**
Done when: the web part, the background worker part and the setup job all exist.

**11.6 Run the database setup.**
Done when: the setup job has completed and the database holds the expected tables.

**11.7 Deploy the released version.**
Done when: the application is running the version the release schedule names, and
it reports that version when asked.

**11.8 Set the update policy to Latest Stable.**
Done when: all three parts of the application follow the release branch and the
policy script reads all three back in agreement. An application has three parts,
each with its own setting, and setting one without the others half-updates it with
no warning from the platform.

**11.9 Confirm the application does not follow the development branch.**
Done when:

- No part of the deployment follows the main development branch.

Note: This replaces what the earlier planning documents said. Those documents require automatic deployment to be switched off on a chapter's application, which was right when the release version travelled inside each deployment's settings. The version is now stamped into the software itself when a release is cut, so an application following the release branch with automatic deployment on updates itself correctly. The danger was never automatic deployment — it is automatic deployment from the development branch, which delivers untested software straight to a chapter's live system.

**11.10 Point the application's web address at the application.**
Done when: the domain name record for the application address resolves to it.

**11.11 Publish the application at its own web address.**
Done when: the application loads at its address over a secure connection, and the
security certificate is set to renew by itself.

**11.12 Confirm the application is healthy.**
Done when:

- The application's health address reports it is running.
- The health address names the chapter correctly.
- The health address shows the background worker alive.

**11.13 Confirm the application can read the CRM.**
Done when: a request through the application returns CRM data.

**11.14 Confirm incoming mail.**
Done when: a message sent to the shared operations mailbox appears in the
application.

**11.15 Confirm outgoing mail.**
Done when: a message sent from a record arrives, and the sender shown is the
chapter.

**11.16 Confirm the calendar.**
Done when: a meeting created through the application appears on the calendar with
the right people invited.

**11.17 Confirm the shared drive.**
Done when: the application creates a folder on the shared drive and it appears.

**11.18 Confirm a new mentor gets a mailbox.**
Done when: a mentor taken through approval ends up with a real working mailbox on
the chapter's mentor email domain.

---

## Stage 12 — Set up backups and monitoring

**12.1 Back up the CRM server on a schedule.**
Done when: backups run automatically, and the schedule and how long backups are
kept are written down.

**12.2 Back up the application database on a schedule.**
Done when: backups run automatically, and the schedule and retention are written
down.

**12.3 Restore from a backup once.**
Done when: a restore has actually been performed and the result checked. An
untested backup is not a backup.

**12.4 Confirm alerts reach a person.**
Done when: a test alert arrives at an address somebody reads, and it is recorded
who reads it.

**12.5 Add the chapter to the list of systems being watched.**
Done when: the central support organization's list of systems includes this
chapter's CRM and application.

---

## Stage 13 — Put the chapter's pages on its website

**13.1 Display the mentor directory page.**
Done when: the page displays on the chapter's website, showing that chapter's
mentors. Blocked: the public mentor directory page is not built, and whether it is
embedded or reached by a redirect is not decided.

**13.2 Send the events address to the events programme page.**
Done when: the chapter's website sends visitors to the application's events page,
and that page shows the chapter's events.

**13.3 Allow only the chapter's own website to display these pages.**
Done when: the chapter's site can display them and a different site cannot. Applies
only to a page embedded in the website. The events programme page is reached by a
redirect, so this step does not apply to it.

**13.4 Confirm links to a single mentor work.**
Done when: opening a link to one mentor lands on that mentor, and the address can
be copied and shared. Blocked until the public mentor directory page is built.

**13.5 Confirm the public pages read properly on a computer and a phone.**
Done when: the pages show with no sideways scrolling and no cut-off text, on a
computer and on a phone.

---

## Stage 14 — Create the staff accounts

**14.1 Agree which staff get an account and which team they are on.**
Done when:

- A list names every member of staff, with their email address and their team.
- The list is approved by the chapter.

Note: Mentors are not on this list. Their accounts are created from their mentor records, at the end of the records stage (step 15.9).

**14.2 Create the staff accounts.**
Done when: every person on the list has an account in the CRM on the right team.

**14.3 Confirm nobody at the chapter holds an administrator account.**
Done when: the only administrator accounts belong to the central support
organization. Chapter staff hold ordinary accounts.

**14.4 Confirm every member of staff has signed in.**
Done when: each member of staff has signed in at least once and set their own
password.

---

## Stage 15 — Bring in the chapter's records and create the mentor accounts

**15.1 Decide whether there are records to bring in.**
Done when: either the sources are listed, or a note records that the chapter starts
with nothing. A chapter starting with nothing skips the load (steps 15.2 to 15.7)
but not the mentor steps after it (steps 15.8 to 15.10).

**15.2 Export the existing records.**
Done when: every source has been exported to a file, and the number of records in
each file is written down.

**15.3 Map the old fields to the CRM's fields.**
Done when: every column in every export file is either mapped to a CRM field or
marked as not being brought across, with a reason.

**15.4 Do a trial load on a copy.**
Done when: the load has been run somewhere that is not the live system, and the
result has been looked at.

**15.5 Resolve duplicates.**
Done when: the rule for deciding what counts as the same person or company is
written down and has been applied.

**15.6 Do the real load.**
Done when: the records are in the live CRM and the counts match what was exported,
with any difference explained.

**15.7 Check a sample.**
Done when: somebody who knows the old records has opened a sample in the CRM and
confirmed they are right.

**15.8 Enter every mentor the load did not bring in.**
Done when: every current mentor has a mentor record in the CRM, with a linked
contact. For a chapter starting with nothing, this is every mentor.

**15.9 Create the mentor accounts.**
Done when: every current mentor has an account, created from their mentor record in
Mentor Administration, and none was created by hand.

**15.10 Confirm every mentor has signed in.**
Done when: each mentor has signed in at least once and set their own password.

---

## Stage 16 — Train the chapter's staff

**16.1 Get the chapter's staff onto the shared practice system.**
Done when:

- The chapter's trainer holds the sign-in details for the chapter training accounts.
- The passwords were set fresh for this chapter.
- One person from the chapter has signed in once.

Note: Ruled 09-14-26: chapters train on the existing test system rather than on their own live system or on a practice system built for them. Ruled 09-18-26: they sign in with shared training accounts set up specifically for chapter training, never with accounts of their own.

**16.2 Explain how the practice system behaves.**
Done when: everyone being trained has been told two things. The system clears
itself out every night, so anything they create during a session is gone the next
morning — a session cannot be spread across two days using the same records. And
the practice system carries Cleveland's name and Cleveland's example records, so
what they see on screen will not say their own chapter's name.

**16.3 Train each role.**
Done when: every person has been shown the parts of the system their own team uses,
and has done each main task once themselves.

**16.4 Hand over the written guides.**
Done when: the chapter holds the written guides for each role and knows where they
live.

**16.5 Name the chapter's own first point of contact.**
Done when: one person at the chapter is named as the person colleagues ask first,
before contacting the central support organization.

**16.6 Change the training account passwords.**
Done when:

- The chapter training account passwords are changed once training ends.
- The change has survived a nightly reset.
- It is written down when this was done.

Note: People from one chapter do not keep standing access to a system another chapter also uses.

---

## Stage 17 — Check everything works before going live

**17.1 Create one ordinary test user per team.**
Done when: there is one non-administrator test account for each team.

**17.2 Confirm each test user sees only what their team allows.**
Done when: every test user can open their own team's pages and is refused on every
other team's pages. Administrator accounts skip all permission checks, so this must
be done as ordinary users.

**17.3 Submit the public application form.**
Done when: a submission made from the public website arrives in the system.

**17.4 Assign the submission.**
Done when: a client administrator test user assigns it to a mentor.

**17.5 Confirm the mentor sees it.**
Done when: the mentor test user finds the assignment and can open their own
profile.

**17.6 Confirm the submission closes.**
Done when: the submission shows as completed and closed to the user who handles
submissions.

**17.7 Confirm the CRM's own screen works for an ordinary user.**
Done when: a non-administrator signs in to the CRM itself and sees a working
screen.

**17.8 Confirm the website pages work for a member of the public.**
Done when: someone not signed in to anything opens the mentor directory and events
pages on the chapter's website and they work.

**17.9 Remove the test records.**
Done when:

- The test submissions created for this stage are gone or disabled.
- The test assignments created for this stage are gone or disabled.
- The test users created for this stage are gone or disabled.
- It is written down what was removed.

---

## Stage 18 — Hand over and start normal support

**18.1 Publish how to get help.**
Done when:

- The chapter has in writing how to raise a request.
- The chapter has in writing that no request is treated as urgent.
- The chapter has in writing that everyday requests are handled as they arrive.
- The chapter has in writing that no response time is committed (ruled 09-18-26).

**18.2 Explain how to ask for a change.**
Done when:

- The chapter knows where to send a request that would change the software for everyone.
- The chapter knows who decides.
- The chapter knows how often those decisions are made.

Note: The central committee decides, every two weeks (ruled 09-18-26).

**18.3 Explain the release schedule.**
Done when:

- The chapter knows software updates arrive automatically on a weekly schedule.
- The chapter knows roughly when.
- The chapter knows what to do if something looks wrong afterwards.

**18.4 Hand over the account and access list.**
Done when:

- The chapter holds the list of every account.
- The list says who has the top-level sign-in.
- The list says who else has access.
- A named chapter officer can reach every one of them.

**18.5 Confirm the chapter can get in without the central support organization.**
Done when:

- A named chapter officer has demonstrated, not merely been told, that they can reach the server on their own.
- The officer has demonstrated the same for the hosting account.
- The officer has demonstrated the same for the Google Workspace account.
- The officer has demonstrated the same for the domain registrar account.

Note: The agreement says neither side can lock the other out; this is the step that makes that true rather than stated.

**18.6 Confirm the leaving terms in practice.**
Done when: the chapter has been shown exactly what it would receive if it left, and
who produces each part.

**18.7 Set the first review date.**
Done when: a date is booked to review how the first months have gone.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.20 | 09-23-26 20:40 | Stage 9 renumbered from twenty steps to nine (Doug, 09-23-26, amending the rule that step numbers never change). Old to new: 9.1 → 9.1; 9.2 → 9.2 and 9.3; 9.3 to 9.6 → 9.4; 9.7 → 9.5; 9.8 and 9.9 → 9.6; 9.10 to 9.15, 9.17 and 9.18 → 9.7; 9.19 → 9.8; 9.20 → 9.9. Step 9.16 became a note at the head of the stage: it cannot be done until work list item 3 is decided. Finishing tests rewritten to match; references elsewhere in the guide follow. The method notes keep the old numbers. |
| 0.19 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26, amending the 09-18-26 Cloudflare ruling): a chapter may keep its DNS at the provider it already uses. Step 3.7's finishing test and note accept a DNS provider account the chapter owns; step 5.8 needs no Cloudflare token for such a chapter. |
| 0.18 | 09-23-26 13:41 | Steps 9.1 and 9.3 brought in line with the ruling that a new chapter runs the current CRM release and Cleveland moves up later (Doug, 09-23-26). Step 9.1 names the current release CRMBuilder installs as the CRM version; step 9.3 records the installed number rather than comparing it with Cleveland's. |
| 0.17 | 09-19-26 14:45 | Steps 11.4 and 8.8 brought in line with step 11.3 (Doug, 09-19-26): the database connection is supplied to the application by the hosting platform and no person holds it, so it is not kept in the vault. The other six secrets are. |
| 0.16 | 09-19-26 00:30 | Three finishing tests brought in line with later rulings, found by the precision sweep. Step 8.3: the events page address is left empty, so the software uses its own page. Step 8.4: the Google branch condition removed (every chapter holds its own Google Workspace), and the shared drive condition removed, because the shared drive is only created in step 10.5. Step 16.1: the 09-14-26 ruling moved from the conditions into the note. |
| 0.15 | 09-19-26 00:10 | Step 4.1 no longer offers a Google Workspace provided by the central support organization. Every chapter hosts its own email on its own Google Workspace (Doug, 09-18-26); the step now confirms that. |
| 0.14 | 09-18-26 20:05 | In fourteen finishing tests, the sentence that explains rather than tests moved out of the list of conditions into a separate Note line (steps 3.7, 5.8, 6.5, 8.7, 9.1, 9.7, 9.8, 11.3, 11.9, 14.1, 16.1, 16.6, 18.2, 18.5). No condition changed. |
| 0.13 | 09-18-26 16:57 | Every finishing test that packed three or more conditions or items into one sentence is now a list, one condition per line (Doug's rule, 09-18-26: every list puts each item on its own line). Thirty-seven steps: 1.1, 1.4, 2.1, 2.5, 3.3, 3.7, 4.1, 4.14, 5.7, 5.8, 6.5, 7.4, 8.2 to 8.5, 8.7, 8.8, 9.1, 9.7, 9.8, 9.14, 9.15, 9.17, 11.3, 11.4, 11.9, 11.12, 14.1, 16.1, 16.6, 17.9 and 18.1 to 18.5. Words kept; only the connectives changed so each condition reads alone. The step data in `steps/` carries the same lists. |
| 0.12 | 09-18-26 14:45 | Cloudflare added (Doug, 09-18-26). Step 3.7: the chapter's domain names move to a Cloudflare account the chapter owns, because CRMBuilder supports no other DNS provider. Step 5.8: the chapter's own DigitalOcean and Cloudflare tokens are given to CRMBuilder, which never builds a chapter with its own. One hundred and fifty-five steps. |
| 0.11 | 09-18-26 14:30 | Step 2.7 added: the chapter sets up its own Proton Pass business organization, owned by two chapter officers, with the central support organization's named people as members of a shared Operations vault (Doug, 09-18-26). Step 8.8 now names that vault as the secrets store. One hundred and fifty-three steps. |
| 0.10 | 09-18-26 13:50 | Step 18.1: nothing is treated as urgent, and everyday requests are handled as they arrive rather than waiting for the committee (Doug, 09-18-26). |
| 0.9 | 09-18-26 13:45 | Steps 18.1 and 18.2 updated from Doug's rulings on 09-18-26: requests go into the ClickUp system, the central committee reviews and schedules features and defects every two weeks, and there is no committed response time. |
| 0.8 | 09-18-26 02:05 | Corrections found while writing the methods for the remaining stages. Step 4.11: mentors' mailboxes come from their records, not by hand. Step 5.5: the video meeting account also needs the app the software schedules webinars through. Step 6.3: tests a redirect, not an embedded page, since the events programme is reached by a redirect (ruled 09-11-26). Step 8.7: a chapter running webinars has an eighth secret. Stage 13: step 13.2 renamed for the redirect, step 13.3 applies only to an embedded page, step 13.5 renamed, and steps 13.1 and 13.4 marked blocked until the public mentor directory page is built. No steps added or removed. |
| 0.7 | 09-18-26 01:55 | Steps 16.1 and 16.6 rewritten after Doug ruled on 09-18-26 that chapter staff train with shared training accounts set up specifically for chapter training. The shared training system restores its user accounts every night, so per-person accounts could not be created or removed without re-capturing its fixed copy. Step 16.6 renamed "Change the training account passwords". |
| 0.6 | 09-18-26 00:50 | Mentor accounts moved from the staff accounts stage to the end of the records stage (Doug, 09-18-26). A mentor's account has to be created from their mentor record in Mentor Administration, or the software makes a duplicate account, so it cannot come before the records are loaded. Stage 14 renamed "Create the staff accounts" and now has four steps. Stage 15 renamed "Bring in the chapter's records and create the mentor accounts" and gains three steps: entering mentors the load did not bring in, creating the mentor accounts, and confirming each mentor has signed in. A chapter starting with nothing now skips only the load, not the whole stage. Total steps now one hundred and fifty-two. |
| 0.5 | 09-14-26 18:13 | Two corrections found while writing the methods for building the CRM and deploying the applications. There are seven secrets, not six — the applications use a stored-data encryption key that no planning document lists and that cannot be changed later without destroying data. And the rule requiring automatic deployment to be switched off is out of date: the danger is following the development branch, not automatic deployment itself. Steps 8.6, 8.7, 8.8, 11.3, 11.8 and 11.9 changed. |
| 0.4 | 09-14-26 18:09 | Training settled on the existing test system as the shared practice area (Doug, 09-14-26). The training stage grew from four steps to six: getting chapter staff onto that system, explaining that it clears itself nightly and shows Cleveland's name, and removing the accounts when training ends. Total steps now one hundred and fifty. |
| 0.3 | 09-14-26 17:51 | Two of the new steps were reviewed and corrected. Putting the chapter's secrets into the store is a chapter step; building the store is not, and now says so. Applying the duplicate checking, saved views and automated rules is a chapter step; deciding what they should be is not, and now says so. Both now point at the work list document. |
| 0.2 | 09-14-26 17:38 | The three completeness checks were run against version 0.1. Fourteen gaps found and closed; the list grew from one hundred and thirty-seven steps to one hundred and forty-eight. New steps: the place secrets are kept, generating the session secret, choosing the chapter's colours and publishing the colour file, producing the logo image, deciding where help documentation lives, deciding who receives warning messages, obtaining the standard's version numbers, pointing two web addresses at their servers, certificates that renew by themselves, duplicate checking and saved views and automated rules, creating a practice area, and proving the chapter can get into its own accounts unaided. |
| 0.1 | 09-14-26 17:28 | First draft of the bare step list. Eighteen stages, one hundred and thirty-seven steps, each with a name and a finishing test. No methods written yet, by design — the three completeness checks run against this list first. |
