# New Chapter Deployment Guide — Methods for the Hosting Accounts, the Website and the Policy Documents

**Document:** The written-out steps for three stages — opening the hosting and video
meeting accounts (stage 5), building the chapter's public website (stage 6), and
writing and publishing the policy documents (stage 7)
**Version:** 0.2
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 02:05

---

## What this is

Three stages that come before any technology is installed. They set up the accounts
the chapter's system will run in, the website the public will reach it through, and
the four documents every applicant agrees to.

None of the three has been done for a chapter. The trial chapter built on 31 August
2026 ran in Doug's own existing hosting account, had no website and had no policy
documents. So every step below is written from the design and from what Cleveland
runs today, and every step is marked **not yet tried**.

Each step carries the same eight headings as the other methods documents.

Two rulings shape these stages. **Each chapter owns its own accounts** and grants
the central support organization access to run them (ruling 5). Neither side can
lock the other out: the central support organization can stop working, and the
chapter can stop paying and withdraw access. And **nobody at the chapter holds an
administrator account on the CRM** (ruling 6). That is safe only because the chapter
owns the server the CRM runs on, which is why the hosting account in stage 5 must be
the chapter's and nobody else's.

Parts of stage 7 are legal work. The central support organization does not give
legal advice. The steps say what the software needs from each document, and say
plainly that the chapter gets the legal content from its own adviser.

---

# Stage 5 — Open the hosting and video meeting accounts

**Stage status: not yet tried.** The trial chapter's server and application were
built inside Doug's own hosting account, so no chapter-owned account has ever been
opened or handed over.

The hosting provider is DigitalOcean. The chapter's CRM server, its applications and
its application database all run there.

---

### 5.1 Create the server hosting account

**Done when:** the account exists in the chapter's name, using a chapter mailbox.

**Who:** the chapter.

**First:** the chapter's Google Workspace and mailboxes exist (stage 4).

**How to do it today:** the chapter's setup contact signs up at DigitalOcean using a
chapter mailbox, never a personal address. Use a mailbox that more than one person
can reach, such as the shared operations mailbox, so the account does not depend on
one person.

**How it will be done later:** unchanged. The account is the chapter's by ruling, so
the chapter creates it.

**How you know it worked:** the chapter's setup contact signs in, and the account's
profile shows the chapter's name and the chapter mailbox.

**What goes wrong:** signing up with a founder's personal email address. The account
then belongs, in practice, to whoever reads that inbox. That is the same ownership
problem the step that moves the domain registrar account to a chapter mailbox
(step 4.14) exists to fix.

**Status:** not yet tried.

---

### 5.2 Set up billing on the hosting account

**Done when:** a chapter payment method is on file and the billing contact is a
chapter mailbox.

**Who:** the chapter.

**First:** step 5.1, and the chapter's bank account (step 1.6).

**How to do it today:** add the chapter's own card or bank payment method in the
hosting account's billing settings. Set the billing email to a chapter mailbox that
the chapter's treasurer reads.

**How it will be done later:** unchanged.

**How you know it worked:** the billing settings show the chapter's payment method
and the chapter mailbox.

**What goes wrong:** a volunteer's personal card on the account. When that person
leaves, the card goes with them, the bills stop being paid, and the chapter's system
is eventually switched off by the hosting provider. The chapter pays its hosting
directly, not through the central support organization (ruling 5).

**Status:** not yet tried.

---

### 5.3 Apply for the nonprofit hosting credits

**Done when:** the application is submitted and the expected answer date is
recorded.

**Who:** the chapter, with the central support organization's help.

**First:** step 5.2, and the chapter's nonprofit status or sponsorship arrangement
(step 1.5).

**How to do it today:** ruling 5 names two routes for hosting credits: the hosting
provider's own nonprofit programme, and credits obtained through TechSoup. Their
current terms have not been checked for this guide. Apply in the chapter's own name,
so the credits belong to the chapter. Write down which route was used and when an
answer is expected.

**How it will be done later:** unchanged.

**How you know it worked:** a confirmation of the application, and an answer date,
are written on the chapter's account list (step 5.7).

**What goes wrong:** a chapter under a sponsoring nonprofit has no nonprofit status
of its own to apply with. That case is an open question in the plan. Until it is
answered, a sponsored chapter may not qualify, and it should budget for the full
price.

**Status:** not yet tried.

---

### 5.4 Grant the central support organization access to the hosting account

**Done when:** the central support organization can create and manage servers in the
account under its own named sign-in, and the chapter can remove that access itself.

**Who:** the chapter grants; the central support organization accepts.

**First:** step 5.1, and the agreement on access (step 2.4).

**How to do it today:** in the hosting account's team settings, the chapter invites
a named person from the central support organization by that person's own email
address. Give them a role that can create and manage servers, databases and
applications. The chapter keeps the owner role. The exact names of the roles on that
screen have not been checked for this guide.

**How it will be done later:** unchanged. The fleet console then works inside the
chapter's account using this same access.

**How you know it worked:** two checks. The central support organization's named
person signs in and sees the chapter's account. And the chapter's owner can see the
remove button beside that person's name. There is no need to press it.

**What goes wrong:** sharing the chapter's own sign-in with the central support
organization instead of inviting a named person. Then nobody can tell who did what,
and the chapter cannot withdraw access without changing its own password.

**Status:** not yet tried. The August build worked inside Doug's own account, so no
access was ever granted.

---

### 5.5 Create the video meeting account, or record that it is not needed

**Done when:** either the account exists with a chapter mailbox as its host address
and an app that lets the software schedule webinars through it, or a note records
that this chapter runs no public webinars.

**Who:** the chapter decides; the central support organization sets up the
connection.

**First:** the chapter's mailboxes exist (stage 4).

**How to do it today:** first decide whether the chapter will run public webinars
through the software. The video meeting account is used only for the public webinar
programme. Mentoring sessions never use it: each mentor uses their own meeting link.

If it is needed, the chapter opens a Zoom account with a chapter mailbox as the host
address. Cleveland's host address is `zweb@cbmentors.org`. The software then also
needs a Zoom "Server-to-Server OAuth" app on that account, which produces three
values: an account identifier, a client identifier and a client secret.
`EVENTS-SETUP.md` section 5 describes creating it.

If it is not needed, write "no public webinars through Zoom" on the chapter's
account list.

**How it will be done later:** unchanged.

**How you know it worked:** the chapter's host mailbox signs in to Zoom. The Zoom
connection itself cannot be checked until the applications are deployed.

**What goes wrong:** two things.

The first: the host address setting in the software defaults to Cleveland's. A
chapter that forgets to change the setting would try to create its webinars under
Cleveland's Zoom host.

The second: the three values from the Zoom app are not on the chapter information
form, and the client secret is not among the form's seven secrets. See "What writing
these steps found".

The Zoom connection is switched off on every deployment today, and it has never been
run against a real Zoom account.

**Status:** not yet tried.

---

### 5.6 Turn on two-step sign-in for both accounts

**Done when:** two-step sign-in is on and recovery does not depend on one person.

**Who:** the chapter.

**First:** steps 5.1 and 5.5.

**How to do it today:** switch on two-step sign-in in the security settings of the
hosting account and of the Zoom account. Store the recovery codes where a second
named person at the chapter can reach them. A second person holding the owner role
on the hosting account also covers this.

**How it will be done later:** unchanged.

**How you know it worked:** signing in to each account asks for the second step, and
a second named person confirms they can reach the recovery codes.

**What goes wrong:** the recovery codes kept only on the phone of the person who
turned two-step sign-in on. When that phone is lost, so is the account.

**Status:** not yet tried.

---

### 5.7 Write down every account the chapter now owns

**Done when:** one list names each account, its web address, who holds the top-level
sign-in, and who else has access.

**Who:** the chapter, checked by the central support organization.

**First:** steps 5.1 to 5.6, and the domain registrar and Google Workspace accounts
from stages 3 and 4.

**How to do it today:** one document, held by the chapter, with one line per account:
the domain registrar, Google Workspace, the hosting account, the Zoom account if
there is one. For each: the web address to sign in at, who holds the top-level
sign-in, who else has access, where the recovery codes are, and the nonprofit
discount or credit applied, if any. No passwords on the list.

**How it will be done later:** the fleet console holds the list for every chapter.

**How you know it worked:** a second person at the chapter can find every account on
the list without asking anyone.

**What goes wrong:** the list goes stale. It is handed over again at the end
(step 18.4), and that is the moment to check it.

**Status:** not yet tried.

---

# Stage 6 — Build the chapter's public website

**Stage status: not yet tried.** The trial chapter had no website. Its form used
made-up addresses.

The public website is the chapter's own marketing site. The software does not build
it. The software needs four things from it: the addresses of the policy documents,
a place to host the colour file, a link to the public application forms, and a way
to send visitors to the events programme page the applications serve.

---

### 6.1 Choose the website platform

**Done when:** the choice is made and someone is named to build and maintain the
site.

**Who:** the chapter.

**First:** the chapter's domain names are registered (stage 3).

**How to do it today:** a chapter that already has a website keeps it. For a new one,
any platform that can publish pages, host a small file and redirect one address to
another will do. Cleveland's site runs on WordPress with the Elementor page builder.

**How it will be done later:** unchanged.

**How you know it worked:** the platform and the person's name are written on the
chapter's account list (step 5.7).

**What goes wrong:** nobody named to maintain it. A website built by a volunteer who
then leaves is a website nobody can change.

**Status:** not yet tried.

---

### 6.2 Publish the website

**Done when:** the site loads at the chapter's website domain over a secure
connection.

**Who:** the chapter.

**First:** step 6.1.

**How to do it today:** publish the site at the chapter's website domain. The address
must begin `https://`.

**How it will be done later:** unchanged.

**How you know it worked:** the site opens in a private browser window at
`https://` and the chapter's domain, with no security warning.

**What goes wrong:** a certificate that is not renewed. The site then shows a
security warning to every visitor.

**Status:** not yet tried.

---

### 6.3 Confirm the website can redirect an address to another site

**Done when:** a test address on the site sends the visitor to a page on another site,
by a temporary redirect. (Checking that the site can embed a page returns once the
public mentor directory page is built and its method is decided.)

**Who:** the chapter.

**First:** step 6.2.

**How to do it today:** on the website, add a temporary redirect (the kind numbered
302) from a test address, such as `/redirect-test`, to any page on another site.
Open the test address in a private browser window. Then remove the redirect. Most
website platforms do this through a redirect setting or a redirect add-on.

**How it will be done later:** unchanged.

**How you know it worked:** the test address lands on the other site's page.

**What goes wrong:** a website platform that cannot redirect one address without a
paid plan. Find out now, not at stage 13. This step replaced an embedding check on
09-18-26: on 09-11-26 it was ruled that the chapter's website sends visitors to the
events page the applications serve, by a redirect. The public mentor directory is
still designed to be embedded, but it is not built.

**Status:** not yet tried.

---

### 6.4 Confirm someone at the chapter can edit the website

**Done when:** a named person at the chapter has signed in and made a change.

**Who:** the chapter.

**First:** step 6.2.

**How to do it today:** the named person signs in to the website with their own
sign-in, changes one word on one page, and changes it back.

**How it will be done later:** unchanged.

**How you know it worked:** the change appeared on the public site.

**What goes wrong:** the only sign-in belongs to the person or company who built the
site. Stages 7 and 13 both need changes made to the website.

**Status:** not yet tried.

---

### 6.5 Choose the chapter's colours and publish the colour file

**Done when:** the chapter's colours are chosen, written into a small stylesheet, and
published at a web address the software can load. Colours are the only visual
difference between chapters in the software, so a chapter that skips this looks
exactly like Cleveland.

**Who:** the chapter chooses the colours; the central support organization writes
the file.

**First:** step 6.2.

**How to do it today:** the software's colours are named settings in its stylesheet,
`frontend/shared/tokens.css`. The main ones are the primary colour `--cbm-navy`
(Cleveland's is `#173B60`), the secondary colour `--cbm-gold` (`#CB963B`, used on
buttons), and the body text colour `--cbm-text`. The colour file for a chapter is a
second, small stylesheet that sets new values for some of these names and nothing
else. It may only contain names starting `--cbm-`, set on `:root`. Anything it leaves
out keeps Cleveland's value.

Publish the file on the chapter's website, so it has a web address. That address
goes on the chapter information form (step 8.3) and into the setting
`CHAPTER_TOKENS_URL`.

There is no starter file to copy. That is item 4 on the work list.

**How it will be done later:** a starter file listing every colour name with
Cleveland's values, which the chapter edits.

**How you know it worked:** once the applications are deployed, the public forms
show the chapter's colours. Until then, open the file's address in a browser: it
should show the stylesheet's text.

**What goes wrong:** three things.

The first: the file sets something other than a colour name, such as a style for a
page element. The rule exists so a chapter's file cannot break the pages.

The second: some website platforms refuse to host a stylesheet file, or serve it as
a download. This has not been checked for any platform.

The third: the colour file changes only the applications. The CRM keeps its own look.

**Status:** not yet tried.

---

### 6.6 Produce the chapter's logo image

**Done when:** an image file of the chapter's logo exists in a form the CRM system
accepts. The applications carry no logo; the CRM system does, and it is the only
per-chapter image in the whole system.

**Who:** the chapter.

**First:** the chapter's name (step 1.1).

**How to do it today:** produce the logo as an image file. Cleveland's CRM logo is a
PNG file. There is no written specification of the size or shape the CRM displays
best. That is item 4 on the work list. The logo is loaded into the CRM's own
settings, as its company logo, when the CRM is set up (stage 9).

**How it will be done later:** a written specification: file type, size, and where it
is loaded.

**How you know it worked:** the file exists and opens.

**What goes wrong:** a chapter that expects its logo on the application pages. The
applications carry no logo and no browser tab icon, by a ruling of 26 August 2026.
Tell the chapter this before it asks.

**Status:** not yet tried.

---

### 6.7 Decide where the chapter's help documentation lives

**Done when:** either the chapter has its own documentation site published at its own
address, or it is recorded that the chapter points at a shared one. Two later steps
link to this address, so it cannot be left undecided.

**Who:** the chapter, with the central support organization.

**First:** step 6.2.

**How to do it today:** this is an open question in the plan, and it is not decided
here. What is known: Cleveland publishes its own documentation site at
`docs.clevelandbusinessmentors.org`, on the BookStack platform, readable without
signing in. The address is used in two places. The applications' portal links to it
through the setting `DOCS_SITE_URL`, which defaults to Cleveland's site. And the
CRM's navigation bar carries a link to it (step 9.15).

Until the question is answered, record one of two things on the chapter information
form: the chapter's own documentation address, or "none yet".

**How it will be done later:** depends on the answer to the open question.

**How you know it worked:** the form carries an address or "none yet". It is never
blank.

**What goes wrong:** leaving the setting at its default. The chapter's staff are then
sent to Cleveland's documentation, which names Cleveland throughout.

**Status:** not yet tried.

---

# Stage 7 — Write and publish the policy documents

**Stage status: not yet tried.** The trial chapter recorded made-up addresses for
all four documents.

**The chapter writes these documents with its own legal adviser.** The central
support organization does not give legal advice, and nothing below says what the
documents must say in law. It says what the software needs from them.

What the software needs is this. Every public form carries one required consent box.
The box reads "I have read and agree to the Code of Conduct, Terms of Use, and
Privacy Policy". On the client application form it reads "Client Code of Conduct".
The software turns each of those phrases into a link to the chapter's own document.
The addresses come from four settings: `POLICY_CLIENT_CONDUCT_URL`,
`POLICY_MENTOR_ETHICS_URL`, `POLICY_TERMS_URL` and `POLICY_PRIVACY_URL`. The event
sign-up form links to the same documents. All four settings default to Cleveland's
documents. A chapter that forgets them shows its applicants Cleveland's privacy
policy, which is a legal problem rather than a cosmetic one.

The wording of the consent box is the same for every chapter, because every chapter
runs the same software (ruling 4). So the chapter's documents should carry those
titles, so that an applicant who clicks "Terms of Use" lands on a document of that
name.

---

### 7.1 Write and publish the client code of conduct

**Done when:** the document is published on the chapter's website and opens without
signing in.

**Who:** the chapter.

**First:** the website is published (step 6.2), and someone can edit it (step 6.4).

**How to do it today:** write the document with the chapter's adviser, and publish it
as a page on the chapter's website. Cleveland's is at
`clevelandbusinessmentors.org/client-code-of-conduct/`. It is linked from the
consent box on the client application form, and on the partner and funder forms, as
"Code of Conduct".

**How it will be done later:** unchanged.

**How you know it worked:** the page opens in a private browser window.

**What goes wrong:** a page published as a draft, or behind a sign-in. It then opens
for the person who wrote it and for nobody else. The private window is what catches
this.

**Status:** not yet tried.

---

### 7.2 Write and publish the mentor code of ethics

**Done when:** the document is published and opens without signing in.

**Who:** the chapter.

**First:** step 6.4.

**How to do it today:** as step 7.1. This is a different document from the client
code of conduct. The volunteer application form's "Code of Conduct" link goes to
this document, not to the client one. Cleveland's is at
`clevelandbusinessmentors.org/mentor-code-of-ethics/`.

**How it will be done later:** unchanged.

**How you know it worked:** the page opens in a private browser window.

**What goes wrong:** publishing one code for both. The software links two different
addresses, and a mentor applicant would then agree to the client code of conduct.

**Status:** not yet tried.

---

### 7.3 Write and publish the terms

**Done when:** the document is published and opens without signing in.

**Who:** the chapter.

**First:** step 6.4.

**How to do it today:** as step 7.1. It is linked as "Terms of Use". Cleveland's is
at `clevelandbusinessmentors.org/legal-notices/`.

**How it will be done later:** unchanged.

**How you know it worked:** the page opens in a private browser window.

**What goes wrong:** nothing known yet.

**Status:** not yet tried.

---

### 7.4 Write and publish the privacy policy

**Done when:** the document is published, opens without signing in, and names this
chapter rather than any other organization.

**Who:** the chapter writes it; the central support organization says what the
software collects.

**First:** step 6.4.

**How to do it today:** the chapter's adviser needs to know what personal
information the software collects and where it keeps it. The central support
organization supplies that as a plain list. The list is drawn from the record of what
every public form collects (`field-mapping-completion-plan.md`) and from the
description of where records are kept (`data-model.md`). In outline:

- the public forms collect names, contact details and business details, and store
  them in the chapter's CRM;
- submissions are also held in the application database;
- mentoring email is copied onto the client's record;
- documents are kept in the chapter's Google shared drive.

It is published as a page on the chapter's website. Cleveland's is at
`clevelandbusinessmentors.org/privacy-policy/`.

**How it will be done later:** the central support organization keeps a standing
description of what the software collects, updated with each release that changes
it.

**How you know it worked:** the page opens in a private browser window, and the
organization it names is this chapter.

**What goes wrong:** starting from another chapter's policy and missing a name. The
finishing test for this step exists for that reason.

**Status:** not yet tried. The plain list of what the software collects does not
exist as one document yet.

---

### 7.5 Have the four documents reviewed

**Done when:** whoever advises the chapter on legal matters has read all four and
confirmed they may be published.

**Who:** the chapter.

**First:** steps 7.1 to 7.4.

**How to do it today:** the chapter's adviser reads all four and confirms in writing.
The central support organization plays no part in this review.

**How it will be done later:** unchanged.

**How you know it worked:** the written confirmation is kept with the chapter's
records.

**What goes wrong:** publishing first and reviewing later. The documents are live as
soon as they are published, and the consent box starts pointing at them as soon as
the applications are deployed.

**Status:** not yet tried.

---

### 7.6 Record the four web addresses

**Done when:** all four addresses are written on the chapter information form and each
one has been opened and checked.

**Who:** the chapter, checked by the central support organization.

**First:** step 7.5.

**How to do it today:** copy each address from the browser's address bar, not from
memory, onto the chapter information form (step 8.3). Open each one in a private
browser window from the form itself.

**How it will be done later:** unchanged.

**How you know it worked:** all four open from the form.

**What goes wrong:** a changed address later. If the chapter moves a document on its
website, the consent box links break silently. Nothing reports it. Moving a policy
document needs a change request (step 18.2), so the setting is changed at the same
time.

**Status:** not yet tried.

---

## What writing these steps found

**1. Step 6.3 tests the wrong thing.** The step checks that the website can display a
page embedded from another site. On 09-11-26 it was ruled that the events programme
is served by the applications and reached by a redirect from the chapter's website,
not embedded. The public mentor directory is still designed to be embedded, but it is
not built, and the software sends no header that would allow it to be embedded on a
chapter's site. So what a chapter's website must be able to do today is redirect one
of its addresses to another site. Recommended correction to the step list: rename
step 6.3 "Confirm the website can redirect an address to another site", with "Done
when: a test address on the site sends the visitor to a page on another site." Add
the embedding check back when the mentor directory pages exist.

**2. The Zoom connection needs values the form does not ask for.** A chapter that runs
public webinars through Zoom needs a Zoom Server-to-Server OAuth app, which produces
an account identifier, a client identifier and a client secret. None of the three is
on the chapter information form, and the client secret is not among its seven
secrets. The host address setting also defaults to Cleveland's Zoom host.
Recommended correction: step 5.5 also creates the Zoom app; the form gains the three
values for chapters that run webinars; step 8.7 lists the client secret as an eighth
secret for those chapters.

**3. No chapter-owned account has ever been opened.** Stage 5 is written entirely from
the design. The trial chapter ran in Doug's own account. The first real chapter is
the first test of every step in this stage.

**4. The four policy documents need no software change.** The four settings already
exist and are linked from every public form and from event sign-up. The only risk is
forgetting to change them from Cleveland's defaults. The information check in the
plan covers this.

**5. Mentors will see Cleveland's website in their profile preview.** The My Mentor
Profile page shows a preview copied exactly from Cleveland's public website, so a
chapter's mentors see Cleveland's page design, not their own. This is outside these
three stages. The public pages phase is what retires the copy. The chapter should be
told during training (stage 16).

**6. A plain list of what the software collects does not exist.** Step 7.4 needs one
for the chapter's legal adviser. The source material exists, but in two engineering
documents.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-18-26 02:05 | Step 5.5's finishing test now includes the app the software schedules webinars through. Step 6.3 rewritten to test a redirect rather than an embedded page, matching the step list. |
| 0.1 | 09-18-26 01:37 | First draft of the methods for three stages — opening the hosting and video meeting accounts, building the chapter's public website, and writing and publishing the policy documents. Written from the rulings, the chapter information form's source document, the first-chapter phase plan, Cleveland's live settings and the software's consent-link code. Nothing here has been done for a chapter. Six findings, two of them recommended corrections to the step list: step 6.3 tests embedding where the events programme now uses a redirect, and the Zoom connection needs three values the form does not ask for. |
