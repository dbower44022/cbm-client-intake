# Mentor Directory — functional reference

Plain-language guide to the **Mentors directory** and the **mentor profile
page** it opens. For CBM staff and mentors. (Engineer/build detail lives in
`CLAUDE.md` and `prds/workspace-directories-plan.md`.)

## What it is

The Mentors directory is one of the Workspace directories, reached from the
portal home. It lists every mentor in a searchable, filterable grid so you can
find a colleague — for example, to get to know the roster, or to decide who
might make a good co-mentor on a client.

Two ways to look at a mentor:

- **Select a row** → a quick preview appears in the side panel.
- **Click the mentor's name** → their full **mentor profile page** opens in its
  own browser tab (re-clicking the same mentor reuses that tab).

## The mentor profile page

A warm, read-only "get to know this colleague" view — deliberately different
from the internal CRM screen and from the public website page. It shows:

- **Header** — photo (or initials if none set), name, headline, and status
  chips (whether they're accepting new clients, their status, their type).
- **Mentoring availability** — how many client openings they have right now
  (their maximum capacity minus their active clients), with a little slot bar.
  This lets you see whether someone is **fully committed** even if they're still
  marked "accepting new clients." If it can't be calculated it falls back to
  showing their stated capacity.
- **Expertise & focus** — areas of expertise, industries served, preferred
  business stages, and languages.
- **About / Professional background** — their narrative bio.
- **Get to know them** — **personal interests**, birthday (month and day only),
  spouse name, and city.
- **Reach out** — CBM email, personal email, phone, and LinkedIn. Clicking an
  email opens a compose window so you can introduce yourself.

### Resizing the page

The page uses the full width of your screen. A **drag bar** sits between the
main column and the "Get to know them" side column — drag it left or right (or
click it and use the ← / → arrow keys) to make the side column wider or
narrower. Your choice is remembered the next time you open a mentor.

## Where the information comes from — and how to change it

Everything on this page is read from the mentor's own CRM record. It is
**read-only here.** Mentors edit their own details in **My Profile**
(`/mentorprofile/`):

- **Personal interests** is the "Personal interests" box in My Profile (write
  about hobbies, family, what you enjoy outside work — it's shown to fellow CBM
  members here).
- Photo, headline, expertise, industries, languages, about/bio, and LinkedIn
  are all edited in My Profile too.
- Birthday, spouse name, and city live on the mentor's contact details (also in
  My Profile / their contact record).

If a section looks empty, it's usually because that mentor hasn't filled it in
yet — the directory is only as rich as each mentor's own profile.

## Who can see it

Anyone who can already reach the Workspace directories — Mentor Team members and
administrators. Everything is read as the signed-in user, so the CRM's own
permissions apply. The **availability number** is the one exception: it's
computed centrally (not client-by-client), because a mentor can't normally read
another mentor's engagements — so everyone browsing sees the same openings
count. It's only a count; no client names or details are exposed.
