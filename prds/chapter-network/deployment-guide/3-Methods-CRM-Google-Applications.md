# New Chapter Deployment Guide — Methods for the CRM, Google and the Applications

**Document:** The written-out steps for three stages — building the CRM system
(stage 9), setting up the Google permissions (stage 10), and deploying the
chapter's applications (stage 11)
**Version:** 0.2
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-15-26 00:19

---

## What this is

Three stages out of the eighteen, written out in full. Two of them — building the
CRM system and deploying the applications — were chosen because they are the only
stages that have been done for real — a complete
chapter was built on a throwaway system on 31 August 2026, and a written record
of what happened exists. Everything below comes from that record, from the
existing update procedure, and from the scripts that did the work.

Each step carries eight headings. Where a heading has nothing to say, it says so
rather than being left out.

The third stage, setting up the Google permissions, is written from the design
instead. It has never been performed, and it was ruled on 09-15-26 that it will not
be rehearsed before a real chapter needs it.

**A warning about the two labels.** A step marked **done for real** was performed
on 31 August and worked. A step marked **not yet tried** has not been, and is
written from the design plus whatever failures are already known. Both kinds appear
below, and the Google steps are all of the second kind.

---

# Stage 9 — Build the CRM system

**Stage status: done for real, with two exceptions noted at the steps.**

Before starting this stage you need an administrator account on the CRM system.
Not the key the applications use — that key is refused on permissions work. The
CRM has no partial administrator, so there is no smaller credential that will do.

---

### 9.1 Obtain the current standard from the central support organization

**Done when:** the build has, in writing, the CRM version to install, the version
of each of the two add-on products, and which release of the standard
configuration is being applied.

**Who:** central support organization.

**First:** nothing.

**How to do it today:** ask. There is no published document, which is why this is
on the work list. For now, record the versions Cleveland's own systems run and
the date the configuration was last captured.

**How it will be done later:** the standard is published with a version number
that the checking tool compares against.

**How you know it worked:** three numbers written down where the rest of the
stage can read them.

**What goes wrong:** skipping this and installing whatever version is current.
The August build did exactly that and ended up a whole major version ahead of
Cleveland — it worked, but nobody planned it.

**Status:** not yet tried as written. The August build had no standard to obtain.

---

### 9.2 Create the server

**Done when:** a server is running in the chapter's own hosting account and the
central support organization can reach it.

**Who:** central support organization, inside the chapter's account.

**First:** the hosting account and its access grant (steps 5.1 and 5.4).

**How to do it today:** use the deployment tool's wizard, which builds the server
with the CRM already packaged on it. **Tick the box for extra sign-in keys.**

**How it will be done later:** unchanged.

**How you know it worked:** the server appears in the chapter's hosting account
and responds.

**What goes wrong:** not ticking the extra keys box. The wizard then leaves
nobody with a command line on the machine, and the next four steps are
impossible. The August build hit this and had to paste a key through the hosting
provider's own console window as a rescue.

**Status:** done for real.

---

### 9.3 Install the CRM software at the version the standard names

**Done when:** the installed version matches the version from step 9.1.

**Who:** central support organization.

**First:** step 9.2.

**How to do it today:** the wizard installs it. If the version it installs is not
the version the standard names, stop and raise it rather than carrying on.

**How it will be done later:** the version is pinned by the deployment tool.

**How you know it worked:** the CRM's own administration page reports the
version.

**What goes wrong:** see step 9.1. Also worth knowing: the August build moved a
configuration captured from an older version onto a newer one and it rebuilt
cleanly, so a version difference is not automatically fatal. It is simply
unplanned.

**Status:** done for real.

---

### 9.4 Confirm command line access, and record who holds the key

**Done when:** the central support organization can open a command line on the
server, and the key is in the secrets store with at least two people able to
reach it.

**Who:** central support organization.

**First:** step 9.2.

**How to do it today:** sign in over a secure shell. Put the key in the secrets
store.

**How it will be done later:** the deployment tool holds and shares the key it
created.

**How you know it worked:** a command runs on the server and returns.

**What goes wrong:** the key exists on one person's laptop only. That is the
situation today and it is on the work list.

**Status:** done for real, except the secrets store part.

---

### 9.5 Point the CRM's web address at the server

**Done when:** the address resolves to the server.

**Who:** central support organization.

**First:** the domain names exist (stage 3).

**How to do it today:** add the address record at the domain registrar.

**How it will be done later:** unchanged.

**How you know it worked:** a name lookup returns the server's address.

**What goes wrong:** nothing known.

**Status:** done for real.

---

### 9.6 Publish the CRM at its own web address

**Done when:** the CRM loads over a secure connection and the certificate renews
by itself.

**Who:** central support organization.

**First:** step 9.5.

**How to do it today:** the packaged CRM obtains its own certificate on first
start once the address points at it. Confirm renewal is automatic.

**How it will be done later:** unchanged.

**How you know it worked:** the sign-in page loads with no certificate warning,
and the renewal timer is active.

**What goes wrong:** a certificate that has to be renewed by hand expires about
ninety days after go-live, and the whole system stops.

**Status:** done for real, except the renewal check.

---

### 9.7 Install the two paid add-on products

**Done when:** both are installed at the versions the standard names, licensed to
this chapter, and listed in the CRM's own list of installed products.

**Who:** central support organization. The chapter pays for the licences.

**First:** step 9.3.

**How to do it today:** buy a licence for each, then install through the CRM's
own administration screen.

**How it will be done later:** unchanged. These are paid products and cannot be
copied between chapters.

**How you know it worked:** both appear in the installed products list.

**What goes wrong:** **doing this after the permission roles instead of before.**
The roles name features that live inside these two products. If the products are
not there, the CRM rejects the whole role rather than skipping the part it does
not recognise, and the roles cannot be applied at all. The August build hit this:
seventy-one separate role entries had to be stripped out and the run finished in
a partial state.

**Status:** not yet tried. The August build did not install them, which is how the
failure was found.

---

### 9.8 Copy on the standard configuration files

**Done when:** both sets of files are in place, owned by the web server user, and
the rebuild command has finished without errors.

**Who:** central support organization.

**First:** steps 9.4 and 9.7.

**How to do it today:** copy two directories from the source system onto the new
server. One holds the custom records, fields, links, screen layouts, wording and
rules. The other holds a small piece of screen code the CRM's own navigation bar
needs. Then hand ownership to the web server user and run the rebuild command
inside the CRM's container.

The location of these directories on disk changed between installer versions.
Find them rather than assuming: an older installer puts them under a `custom`
folder, a newer one under a `persistent` folder with the screen code in a second
folder beside it.

**How it will be done later:** the configuration is packaged and installed rather
than copied.

**How you know it worked:** the rebuild finishes with no errors in the log. On
the August build it took three seconds.

**What goes wrong:** **copying only one of the two directories.** The CRM's
applications still work, so everything looks fine — but the CRM's own screen is
blank, because the navigation bar refers to a file that is not there. This is why
step 9.9 exists as a separate check.

**Status:** done for real.

---

### 9.9 Confirm the CRM's own screen loads

**Done when:** an administrator signs in and sees the normal working screen.

**Who:** central support organization.

**First:** step 9.8.

**How to do it today:** open the CRM in a browser and sign in. Look at it.

**How it will be done later:** unchanged. This one stays human.

**How you know it worked:** the screen has a navigation bar and records on it.

**What goes wrong:** a blank page means the second directory from step 9.8 is
missing. Nothing else produces that symptom.

**Status:** done for real.

---

### 9.10 Create the teams

**Done when:** every team the standard names exists, spelled exactly as the
standard spells it.

**Who:** central support organization.

**First:** step 9.9.

**How to do it today:** the rehearsal script creates all of them from the
captured standard. Run it without the apply option first to see what it would do,
then again with it.

**How it will be done later:** the same work moves inside the deployment tool.

**How you know it worked:** the script reports every team applied, and the teams
list in the CRM matches.

**What goes wrong:** a misspelled team name. Every permission gate in the
software looks for an exact name, so a chapter with a misspelled team has a
feature nobody can reach, and the error message says nothing useful.

**Status:** done for real — nine of nine.

---

### 9.11 Create the permission roles

**Done when:** every role the standard names exists, and reading each one back
matches what was sent.

**Who:** central support organization.

**First:** steps 9.7 and 9.10. The add-on products must already be installed.

**How to do it today:** the same script. Before it writes anything it checks each
role against what this CRM actually has, and removes any entry naming something
that is not there, reporting each removal.

**How it will be done later:** inside the deployment tool, with the same check.

**How you know it worked:** the script reports every role applied and read back
identical. If it reports entries it had to remove, the run is incomplete — see
below.

**What goes wrong:** two things, both seen in August.

An entry naming a feature the CRM does not have. The CRM refuses the entire role,
not just that entry. Installing the add-on products first is the fix.

An entry naming a field that has since been deleted on the source system. The
source tolerates the stale entry; the target refuses the whole role for it. The
source needs cleaning, not the target.

**Status:** done for real — twelve of twelve applied and read back identical, with
seventy-three entries removed because the add-on products were absent.

---

### 9.12 Attach the roles to the teams

**Done when:** each team carries the role it is meant to carry, and no team is
left without one.

**Who:** central support organization.

**First:** step 9.11.

**How to do it today:** the same script does the attachments.

**How it will be done later:** unchanged.

**How you know it worked:** every attachment reports applied, and no team in the
list has an empty role.

**What goes wrong:** a team with no role at all. Its members then have no access
to anything, and it is invisible until somebody on that team tries to work. Two
of Cleveland's own teams are in this state today.

**Status:** done for real — seven of seven.

---

### 9.13 Create the email templates

**Done when:** every template the standard names exists.

**Who:** central support organization.

**First:** step 9.9.

**How to do it today:** the same script.

**How it will be done later:** unchanged.

**How you know it worked:** the templates appear in the CRM.

**What goes wrong:** the templates carry no chapter name inside them, which was
checked deliberately, so they are the same everywhere and need no editing. Do not
edit them per chapter.

**Status:** done for real — two of two, which is all the source system holds. Five
others named by the standard are missing on both Cleveland systems too.

---

### 9.14 Apply the instance settings

**Done when:** the chapter's name, sending name, sending address, web address,
logo, time zone, date format, time format, currency, language and week start are
all set from the chapter information form, and reading them back matches.

**Who:** central support organization.

**First:** the chapter information form (stage 8) and step 9.9.

**How to do it today:** the same script applies them and reads them back.

**How it will be done later:** unchanged.

**How you know it worked:** each setting reads back equal to what was sent.

**What goes wrong:** the sending name here is separate from anything the
applications display. Anything the CRM sends directly carries this name, whatever
the applications say. Cleveland's production system has had the wrong name in this
field for some time.

Also: currency fields refuse to save unless their paired currency setting is
right, so this is not decoration.

**Status:** done for real.

---

### 9.15 Apply the navigation tabs and the quick-add list

**Done when:** the tabs match the standard, the chapter's own documentation link
is in place of any other chapter's, and the quick-add list matches.

**Who:** central support organization.

**First:** step 9.14, and the documentation address decision (step 6.7).

**How to do it today:** the same script.

**How it will be done later:** unchanged.

**How you know it worked:** the tab bar in the CRM matches, and the documentation
tab opens this chapter's documentation.

**What goes wrong:** the documentation link is the one item in an otherwise
identical tab bar that differs per chapter. The August build dropped it entirely
because the fictional chapter had no documentation site.

**Status:** done for real.

---

### 9.16 Apply the standard's duplicate checking, saved views and automated rules

**Done when:** the settings the standard names are applied and read back
correctly.

**Who:** central support organization.

**First:** step 9.9.

**How to do it today:** **not possible yet.** The standard does not say what these
should be, because nobody has examined them on either existing system. This is on
the work list.

**How it will be done later:** part of the standard like everything else.

**How you know it worked:** cannot be checked until the standard says what is
expected.

**What goes wrong:** duplicate checking is not only a convenience. The software
that creates records during client intake behaves differently depending on
whether it is switched on, and that dependency has never been tested either way.

**Status:** not yet tried, and blocked.

---

### 9.17 Create the account the applications sign in with

**Done when:** the account exists, its key is in the secrets store, and a test
request using that key succeeds.

**Who:** central support organization.

**First:** step 9.12.

**How to do it today:** the same script creates the account, attaches its role
directly to it, and writes the newly created key into the secrets file.

**How it will be done later:** unchanged, with the key going straight into the
store.

**How you know it worked:** a request using the key returns a normal answer.
An empty result is fine; a refusal is not.

**What goes wrong:** a refusal means a permission was missed and the feature will
be invisible to the applications rather than producing an error anybody sees.

**Status:** done for real.

---

### 9.18 Create the administrator account for the central support organization

**Done when:** the account exists and its password is in the secrets store.

**Who:** central support organization.

**First:** step 9.9.

**How to do it today:** the same script creates it and writes the password to the
secrets file.

**How it will be done later:** unchanged.

**How you know it worked:** the account signs in.

**What goes wrong:** this password ends up on a laptop. On Cleveland's production
system it deliberately exists only inside the running application, and anything
needing it is run from inside that container rather than copied out.

**Status:** done for real.

---

### 9.19 Create the configuration version record

**Done when:** the record saying which version of the standard this CRM holds
exists and can be read by the applications' own key.

**Who:** central support organization.

**First:** step 9.17.

**How to do it today:** a separate script builds it. Run it without the apply
option, read the plan it prints, then run it again with the apply option and the
fingerprint the dry run printed, so it refuses if anything moved in between.

**How it will be done later:** the tool that applies the configuration writes the
record itself, and only after a completely successful run.

**How you know it worked:** a request using the applications' own key returns the
record.

**What goes wrong:** writing the version after an incomplete run. A system
claiming to hold a version it does not hold is worse than one claiming nothing,
because everything downstream believes it. In August the version was deliberately
left unwritten for exactly this reason.

**Status:** done for real.

---

### 9.20 Run the checking tool until it reports no differences

**Done when:** the tool reports that the CRM matches the standard, and any
deliberate difference is listed and explained in writing.

**Who:** central support organization.

**First:** every step above.

**How to do it today:** run the checking tool using the applications' own key,
asking for the machine-readable output, and keep the file.

The result codes mean different things and should not be collapsed together.
Nothing to fix. Something differs. And could not be checked at all — which is not
the same as bad, and usually means a credential or network problem rather than a
CRM problem.

**How it will be done later:** the same check runs automatically before every
deployment and refuses the deployment when the CRM does not match.

**How you know it worked:** the tool reports nothing to fix.

**What goes wrong:** the August build could not reach that state, and neither can
Cleveland's own test system — both report the same five missing email templates.
Until those templates exist somewhere, "matches the standard" is not reachable and
the honest result is a recorded, explained difference.

**Status:** done for real, with that difference.

---

# Stage 10 — Set up the Google permissions the software needs

**Stage status: not yet tried.** Every step below is written from the design and
from two failures that have been seen on Cleveland's own systems. None of it has
been performed on a new chapter. Ruled 09-15-26: it will not be rehearsed on the
trial chapter, so the first real chapter is the rehearsal, with someone from the
central support organization beside them while they do it.

**Read this before starting.** The chapter's own Google administrator has to be at
the keyboard for two of these steps. The permission grant is entered inside the
chapter's own Google admin console, and nobody else can enter it. Book that time
in advance rather than discovering it halfway through.

---

### 10.1 Create the machine account

**Done when:** the account the software will use exists in the chapter's Google
account.

**Who:** central support organization, inside the chapter's Google account.

**First:** the chapter's Google Workspace exists (stage 4).

**How to do it today:** create a service account in the chapter's Google cloud
project and note its client identifier. This is an account for a program, not a
person — it has no mailbox of its own and nobody signs in as it.

**How it will be done later:** unchanged.

**How you know it worked:** the account appears with a client identifier.

**What goes wrong:** nothing known.

---

### 10.2 Download and store its key

**Done when:** the key file is in the secrets store.

**Who:** central support organization.

**First:** step 10.1.

**How to do it today:** create a key for the machine account and download it. It
is a single file. Put it straight into the secrets store.

**How it will be done later:** unchanged.

**How you know it worked:** the file is in the store and nowhere else.

**What goes wrong:** the file goes to a downloads folder and stays there. It is
the whole of the chapter's Google access in one file, and it is not
password-protected.

---

### 10.3 Enter the permission grant

**Done when:** the grant is entered in the chapter's own Google admin console with
the exact list of permissions, checked one at a time.

**Who:** the chapter's Google administrator, with the central support organization
reading out the list.

**First:** step 10.1.

**How to do it today:** in the chapter's Google admin console, grant the machine
account permission to act on behalf of users in the chapter, and paste in the list
of permissions. The list covers reading and sending mail, managing calendar
events, reading and managing user accounts in the directory, managing groups, and
optionally files on the shared drive.

Check each permission against the list rather than trusting a paste. A single
missing one does not fail here — it fails later, in a way that does not say which
permission is missing.

**How it will be done later:** unchanged. This step cannot be automated, because
it happens inside an account the central support organization only administers by
the chapter's grant.

**How you know it worked:** the grant appears in the console with the machine
account's client identifier and the full permission list beside it.

**What goes wrong:** this is named in the existing planning documents as a
recurring failure point, and the reason is that the error arrives much later and
names nothing useful. If the verification in stage 11 fails, come back and read
this list again before looking anywhere else.

---

### 10.4 Name the mailbox the software acts as

**Done when:** the mailbox is named, and it is a real licensed mailbox.

**Who:** central support organization, with the chapter.

**First:** the shared operations mailbox exists (step 4.7).

**How to do it today:** record the address on the chapter information form. It
must be a mailbox with its own licence and its own storage.

**How it will be done later:** unchanged.

**How you know it worked:** the address appears in the chapter's list of mailboxes
as a mailbox, not as an alias or a group.

**What goes wrong:** using a group address or a forwarding alias. Both look like
email addresses and neither works. The refusal names nothing useful and has cost
this project time before. If the address does not have a licence attached to it, it
is not a mailbox.

---

### 10.5 Create the shared drive and add the machine account

**Done when:** the shared drive exists and the machine account is a member of it.

**Who:** central support organization, inside the chapter's Google account.

**First:** step 10.1.

**How to do it today:** create the shared drive, then add the machine account to it
as a member with permission to create and manage files.

**How it will be done later:** unchanged.

**How you know it worked:** the machine account appears in the drive's member
list.

**What goes wrong:** creating an ordinary folder in somebody's personal drive
instead of a shared drive. It works until that person leaves.

---

# Stage 11 — Deploy the chapter's applications

**Stage status: done for real, except everything involving Google, which was
deliberately switched off.**

---

### 11.1 Generate the session secret

**Done when:** a new random session secret exists for this chapter alone and is
in the secrets store.

**Who:** central support organization.

**First:** nothing.

**How to do it today:** the settings generator creates it the first time it runs
and writes it into the secrets file.

**How it will be done later:** created directly in the store.

**How you know it worked:** the value is present and is not the same as any other
chapter's.

**What goes wrong:** copying another chapter's.

**Status:** done for real.

---

### 11.2 Generate the deployment settings

**Done when:** the settings are produced from the chapter information form, and
every value traces back to a line on that form.

**Who:** central support organization.

**First:** the chapter information form (stage 8) and the CRM's key (step 9.17).

**How to do it today:** run the settings generator with the chapter information
form and the secrets file. It produces a settings file containing the secret
values in plain text. **That file must never be committed anywhere.**

**How it will be done later:** the generator reads secrets from the store and
never writes them to a file at all.

**How you know it worked:** the generator refuses to run if the CRM key or the
administrator credentials are missing, so a successful run means those exist.

**What goes wrong:** there is a seventh secret nobody's list mentions — an
encryption key the applications use for stored data. The generator creates it
quietly on first run. **Changing it later destroys the data it protects**, so it
has to be treated as permanent from the moment it exists. No planning document
lists it, and the step list said six secrets. It is seven.

**Status:** done for real.

---

### 11.3 Load the secrets

**Done when:** every secret is loaded into the deployment and none appears in a
file anyone can read.

**Who:** central support organization.

**First:** step 11.2.

**How to do it today:** the generated settings file carries them. The database
connection is not a secret anybody holds — the hosting platform supplies it to
the application directly.

**How it will be done later:** from the store.

**How you know it worked:** the application starts.

**What goes wrong:** the settings file with plain text secrets is left on a
laptop or, worse, committed. Regenerating it from the platform afterwards does not
help: the platform hands back the secrets scrambled into an unreadable form.

**Status:** done for real, and this is the weakest point in the whole stage.

---

### 11.4 Create the database

**Done when:** the database exists in the chapter's hosting account and the
application can reach it.

**Who:** central support organization.

**First:** step 5.1.

**How to do it today:** it is created as part of the application, named after the
chapter's short label.

**How it will be done later:** unchanged.

**How you know it worked:** the application connects.

**What goes wrong:** the hosting provider adds an instruction to the connection
details that the application's database library rejects. The software already
strips it out, so this is handled — but it is the kind of thing that looks like a
broken database.

**Status:** done for real.

---

### 11.5 Create the application parts

**Done when:** the web part, the background worker part and the setup job all
exist.

**Who:** central support organization.

**First:** steps 11.2 and 11.4.

**How to do it today:** hand the generated settings file to the hosting
platform's create command.

**How it will be done later:** unchanged for now.

**How you know it worked:** all three parts appear.

**What goes wrong:** creating only the web part. The background worker is what
sends mail, keeps the calendar in step and sweeps up unfinished work. Without it
the system looks fine and quietly does nothing.

**Status:** done for real — active on the first attempt, in seven minutes.

---

### 11.6 Run the database setup

**Done when:** the setup job has completed and the database holds the expected
tables.

**Who:** central support organization.

**First:** step 11.5.

**How to do it today:** the setup job runs by itself before the application
starts.

**How it will be done later:** unchanged.

**How you know it worked:** the job reports success in the deployment log.

**What goes wrong:** nothing known.

**Status:** done for real.

---

### 11.7 Deploy the released version

**Done when:** the application is running the version the release schedule names
and reports that version when asked.

**Who:** central support organization.

**First:** step 11.6.

**How to do it today:** the application follows the release branch, which always
points at the most recent released version.

**How it will be done later:** unchanged.

**How you know it worked:** the application's health address reports the release
version.

**What goes wrong:** it reports nothing where the version should be. That happens
when the application is following the development branch instead of the release
branch, and it is the honest answer rather than a fault.

**Status:** done for real, twice — once in August and again in September.

---

### 11.8 Set the update policy to Latest Stable

**Done when:** all three parts of the application follow the release branch and
the policy script reports it.

**Who:** central support organization.

**First:** step 11.7.

**How to do it today:** run the policy script against the application with the
Latest Stable setting. Add the option that forces a fresh deployment, or the
application stays one release behind while reporting itself healthy.

**How it will be done later:** a button.

**How you know it worked:** the script reads all three parts back and they agree.

**What goes wrong:** setting one part and not the others. An application has three
parts, each with its own setting, and nothing on the platform tells you that you
have half-updated it. That is the entire reason this is a script rather than a
note.

**Status:** done for real.

---

### 11.9 Confirm the application does not follow the development branch

**Done when:** no part of the deployment follows the main development branch.

**Who:** central support organization.

**First:** step 11.8.

**How to do it today:** read the three parts back with the policy script.

**How it will be done later:** the fleet view reports any deployment following the
wrong branch.

**How you know it worked:** all three name the release branch.

**What goes wrong:** **this step replaces what the earlier planning documents said,
and the change matters.** Those documents say automatic deployment must be off on
a chapter's application. That was true when the release version was carried inside
each deployment's settings. It is no longer how it works: the version is now
stamped into the software itself when a release is cut, so an application
following the release branch with automatic deployment on updates itself correctly
and safely. The danger was never automatic deployment — it is automatic deployment
from the **development** branch, which delivers untested software straight to a
chapter's live system.

**Status:** done for real, and the reason the mechanism changed.

---

### 11.10 Point the application's web address at the application

**Done when:** the address resolves to the application.

**Who:** central support organization.

**First:** stage 3.

**How to do it today:** add the address record at the registrar, then tell the
hosting platform about the address.

**How it will be done later:** unchanged.

**How you know it worked:** a name lookup returns the application.

**What goes wrong:** nothing known.

**Status:** not yet tried. The August build used the address the platform supplies
by default.

---

### 11.11 Publish the application at its own web address

**Done when:** the application loads over a secure connection and the certificate
renews by itself.

**Who:** central support organization.

**First:** step 11.10.

**How to do it today:** the hosting platform issues and renews the certificate.

**How it will be done later:** unchanged.

**How you know it worked:** the page loads with no warning.

**What goes wrong:** nothing known.

**Status:** not yet tried.

---

### 11.12 Confirm the application is healthy

**Done when:** the health address reports the application running, names the
chapter correctly, and shows the background worker alive.

**Who:** central support organization.

**First:** step 11.7.

**How to do it today:** open the health address and read it.

**How it will be done later:** the fleet view reads it for every chapter at once.

**How you know it worked:** the chapter's own name appears, not Cleveland's. That
single line is the proof that removing the hard-coded chapter name actually
worked.

**What goes wrong:** the health check runs before the new software has finished
starting and reports a failure that is not real. Wait and read it again.

**Status:** done for real.

---

### 11.13 Confirm the application can read the CRM

**Done when:** a request through the application returns CRM data.

**Who:** central support organization.

**First:** steps 9.17 and 11.12.

**How to do it today:** open a page in the application that lists records.

**How it will be done later:** unchanged.

**How you know it worked:** records appear, or an empty list appears. Both are
fine.

**What goes wrong:** a refusal rather than an empty list means a permission was
missed back in stage 9.

Separately: a page that asks for more than two hundred records at once is refused
outright rather than being trimmed, and inside the software that refusal reads as
"there are no records". This once emptied every selection list on Cleveland's live
system.

**Status:** done for real.

---

### 11.14 Confirm incoming mail

**Done when:** a message sent to the shared operations mailbox appears in the
application.

**Who:** central support organization.

**First:** the Google permissions (stage 10), and the mail feature switched on.

**How to do it today:** switch on the mail feature, restart the background worker,
and read its log. The first thing to look for is the line naming the mailbox the
worker is acting as. If that line is absent or names the wrong address, stop —
nothing after this will work and the cause is in stage 10, not here.

Then send a message from an outside address to the shared operations mailbox and
watch for it in the application.

**How it will be done later:** unchanged.

**How you know it worked:** the log names the right mailbox, and the message
appears against a record in the application.

**What goes wrong:** **only one deployment may read a given mailbox.** If two do,
each takes roughly half the messages and neither is obviously broken. Before
switching this on, confirm no other deployment is reading the same address.

**Status:** not yet tried.

---

### 11.15 Confirm outgoing mail

**Done when:** a message sent from a record arrives, and the sender shown is the
chapter.

**Who:** central support organization.

**First:** step 11.14.

**How to do it today:** open a record in the application, send a message from it to
an outside address, and look at what arrives.

**How it will be done later:** unchanged.

**How you know it worked:** the message arrives, and the name on it is the
chapter's own.

**What goes wrong:** the address the software sends warnings from must also be a
real licensed mailbox. A group or an alias is refused, and the refusal names the
wrong thing — it reads as though the machine account is not authorised at all,
rather than as though the address is unusable.

**Status:** not yet tried.

---

### 11.16 Confirm the calendar

**Done when:** a meeting created through the application appears on the calendar
with the right people invited.

**Who:** central support organization.

**First:** step 11.14, and the calendar feature switched on.

**How to do it today:** switch on the calendar feature, create a session through
the application, and look at the calendar.

**How it will be done later:** unchanged.

**How you know it worked:** the meeting is on the calendar and the invitations
went out.

**What goes wrong:** the calendar permission is a separate entry in the grant from
stage 10, and it is the one most often missed, because mail working makes
everything look fine.

**Status:** not yet tried.

---

### 11.17 Confirm the shared drive

**Done when:** the application creates a folder on the shared drive and it appears.

**Who:** central support organization.

**First:** steps 10.5 and 11.14, and the documents feature switched on.

**How to do it today:** switch on the documents feature and create a record that
should get a folder.

**How it will be done later:** unchanged.

**How you know it worked:** the folder appears on the shared drive.

**What goes wrong:** the machine account is not a member of the shared drive, or
the drive identifier on the chapter information form is wrong. Both produce a
silence rather than an error.

**Status:** not yet tried.

---

### 11.18 Confirm a new mentor gets a mailbox

**Done when:** a mentor taken through approval ends up with a real working mailbox
on the chapter's mentor email domain.

**Who:** central support organization.

**First:** steps 10.3 and 11.14, and the mentor account feature switched on.

**How to do it today:** take a test mentor through approval in the application and
watch for the mailbox being created.

This is the last check because it exercises the most: the directory permissions
from stage 10, the mentor email domain from the chapter information form, and the
application's own approval process.

**How it will be done later:** unchanged.

**How you know it worked:** the new mailbox exists and the mentor can sign in to
it.

**What goes wrong:** the mentor email domain was a fixed value inside the software
until the August build reached this step and found it. It is a setting now, but it
is a setting somebody has to fill in, and a chapter whose mentor addresses are on a
different domain from its staff addresses has to say so.

Two directory permissions are needed here rather than one — reading the directory
and changing it. A grant with only the reading one gets all the way to this step
before failing.

**Status:** not yet tried.

---

## A note on what "not yet tried" costs here

Ruled 09-15-26: the Google connection will not be rehearsed on the trial chapter.
The first real chapter is the rehearsal.

That is a deliberate trade and it is worth stating what it means in practice. Five
of the ten Google steps have a known failure attached to them, and every one of
those failures reports something that does not name the cause. Written from design,
these steps say what to do and what usually goes wrong; they do not say what the
screens look like, how long each part takes, or what the error text actually reads.

So the first chapter through this stage should have someone from the central
support organization present while it happens, and whoever is present should
correct these ten steps the same day, while the screens are still fresh. Until
that has happened, this part of the guide is a design document wearing a runbook's
clothes.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-15-26 00:19 | Stage 10, setting up the Google permissions, added — five steps written from the design after Doug ruled on 09-15-26 that the Google connection will not be rehearsed on the trial chapter. The five Google checks at the end of the deployment stage written the same way, replacing the placeholder. A closing note records what "not yet tried" costs here and what the first real chapter is expected to do about it. |
| 0.1 | 09-14-26 18:13 | First draft of the methods for two stages — building the CRM system and deploying the applications. Written from the record of the 31 August build, the existing update procedure, and the scripts that did the work. Two corrections to the step list came out of writing it: there are seven secrets rather than six, and the rule about automatic deployment was out of date. |
