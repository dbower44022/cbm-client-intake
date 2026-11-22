# The Ambassador Program — how it works

Last Updated: 11-21-26 22:59 · Revision 1.0 — see change log at the end.

For the people who run the Ambassador Program and for the board. It says
what the program is for, who does what, and what the application does with
every report a member makes. How to use the screens is in the user guide,
*The Ambassador Program — user guide* (`ambassador-program.md`). The design
decisions behind it are recorded in `prds/Ambassador Program/`.

## What the program is for

Every member spreads the word about the organization in small ways: sharing
a post, telling an entrepreneur about free mentoring, introducing someone
at a networking event, standing at a table at a fair. The Ambassador
Program counts that work, makes sure nothing a member learns is lost, and
credits members for the people they bring in.

A member reports each activity in under a minute, on a phone if they like.
The report then does three jobs on its own:

1. **It is counted.** One report is one activity, credited to the member.
2. **It reaches the right person.** A contact the organization already
   knows is recorded on that partner, funder or client, and their manager or
   mentor is told.
3. **It credits a referral.** A person the member refers is recorded at
   once, credited to the member, and the credit follows them when they
   apply, by any route.

## Who does what

**Members** log their own activities and see their own history. They never
see anyone else's reports, and they never see whether a person they named
is a client: that stays private to the client's mentor.

**The program team** (by default the Marketing Admin Team) answers members'
requests for follow-up, places contacts the application could not place,
and reads the program's figures.

**Partner and funder managers, and client mentors** are told when an
ambassador met one of their contacts. The meeting appears on their record's
Sessions tab as an *Ambassador Contact*, which is not a mentoring session
and counts as none.

**Partner Management and Funder Management** receive the organizations
members refer as potential partners or funders, already in their lists.

## The six activities

1. Liked or shared a post.
2. Referred someone (a potential client, partner or funder).
3. Invited someone to an event.
4. Made a community introduction.
5. Represented the organization at an event.
6. Identified a success story.

## What happens to a report

The member's report is saved the moment they press Save, before anything
else happens, so a report is never lost, even if the CRM is briefly out of
reach. The application then works through it:

**When the member names someone.** The application looks the person up.

- **Someone at a partner or funder:** an Ambassador Contact session is
  recorded on that partner or funder, and its manager is emailed.
- **Someone at a client:** an Ambassador Contact session is recorded on the
  client's current engagement, and the client's mentor is emailed.
- **A new potential client:** the person is created as a prospect, with
  their company and a lead whose source is *Ambassador referral*, credited to
  the member (*Referred by*).
- **A new potential partner or funder:** the same, plus a starting record in
  Partner Management (*Candidate*) or Funder Management (*Prospective*), and
  that team is emailed.
- **A fellow member:** not recorded as a contact.
- **Anyone the application cannot place** (unknown and said to be from an
  organization we work with, or matching more than one person): held on the
  program team's review list.

**When the member asks for follow-up.** The program team is emailed, an
*Ambassador follow-up* row appears on their home page, and the request sits
on the review list until someone marks it done with a note. The member is
emailed that note.

**When a referred person applies.** Whichever way they apply (the public
form, a partner's link, a staff screen), the application finds them by email
address. A new client's engagement carries the member's credit; a partner
or funder application uses the starting record instead of making a second
one. The member's report then reads *Applied*, and the member is emailed.

## Rules that protect members and clients

- **The thank-you is the same for every report.** It never says whether, or
  where, a contact was found, so the form cannot be used to learn who is a
  client.
- **A member's report never changes a record the organization keeps.** If a
  member corrects a name or a company the application filled in, the
  correction is noted on the report for the program team; the record itself
  is changed only by staff, in its own screen.
- **The first member to refer someone keeps the credit.**
- **A person is added to marketing mail only when the member says they
  agreed**, and nothing a member reports ever removes someone's agreement.
- **An Ambassador Contact is never counted as mentoring.** It does not move
  an engagement to Active, does not trigger a feedback survey, does not count
  as contact with the client, and is left out of every session figure.

## What is measured

The Ambassador Program page in Analytics, for the program team and the
Analytics Admin Team:

- active ambassadors, and active ambassadors by month;
- activities reported, and activities by type;
- open follow-ups;
- contacts awaiting review;
- referrals made and referrals that applied, for clients, partners and
  funders;
- ambassador contacts recorded on partners, funders and clients.

Members see no figures, only their own list. Mentor Administration sees each
member's activities on the member's record, read-only.

## Where it lives in the application

- **Ambassador Activity** (`/ambassador/`): the member's page. It signs the
  member in on the page itself, so a phone bookmark goes straight to the form.
- **Ambassador Review** (`/ambassador/review/`): the program team's list.
- **Analytics → Ambassador Program**: the figures.
- **Mentor Administration → a member → Ambassador**: one member's activities.

Everything is switched on and off by one setting, *Ambassador Program*, in
System Settings. Switching it off hides every screen; the records stay.

## Not in this version

Named so they are not lost, each a later phase if the program needs it:

- a personal referral link and QR code for each member, which would credit a
  person who applies from a different email address;
- pasting a whole email signature or business card's text into the form;
- the member's recent contacts as one-tap choices;
- choosing the event from the calendar when reporting an event.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-21-26 22:59 | Claude (Claude Code) | Created (decision AM9, Doug 11-21-26), from the build as checked on the Business Mentors Association's system (v0.360.0 to v0.361.0). |
