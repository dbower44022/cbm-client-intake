# Business Evaluation — user guide

Last Updated: 11-21-26 02:29 · Revision 0.1 — see change log at the end.

This guide is for staff of the organization. It covers the whole evaluation journey, from a new client's first intake to the feedback afterwards, including the parts mentors and clients do. The step-by-step demo that trains new staff on this journey is `training/evaluation-staff-course/evaluation-demo.md`.

**Status.** Draft for Doug's review. It is not yet published to the documentation site. When it is, the published copy carries no sign-in user names, because that site can be read without signing in.

## What the offering is

A business evaluation is a free, structured look at a client's business. The client answers short surveys on a web page, with no login. The answers go into the client's record, and an AI service writes a first draft of a report for each area. The client's mentor, and any co-mentor with the right background, correct the draft. The mentor goes through the results with the client in a session, and then releases the client's own copy with the action items they agreed.

The same survey pages also carry **feedback surveys**: short surveys, opening with a 0-to-10 question, that ask how well the organization helped.

## Terms

- **Evaluation area**: one subject the evaluation can analyse, such as Finance or Marketing. Each area has one survey. At launch only Finance and Marketing have surveys; the other four areas follow after the pilot.
- **Business profile**: a short survey of about 14 questions about the business as a whole (what it sells, its stage, size and goals). It is answered once per engagement, and every report uses it.
- **Intake survey**: the business profile survey, emailed to a new client automatically when their intake arrives.
- **Business Evaluation record**: the record in the CRM for one area of one engagement. It holds the answers, the draft report, the reviewed report and the status.
- **Round**: the areas sent together. A later re-evaluation is a new round, and earlier rounds are kept.
- **Draft report**: what the AI service writes. **It is never shown or sent to the client.**
- **Reviewed report**: the draft after the mentor and co-mentors have corrected it. It starts as a copy of the draft.
- **Review session**: the mentoring session where the mentor goes through the results with the client.
- **Action item**: one step the client agreed to at the review session, with an owner and a due date.
- **Mentor match**: an AI analysis that suggests mentors for an engagement waiting for one. It is advice only.
- **Recommendation score**: the answer, from 0 to 10, to "How likely are you to recommend …". A score of 6 or below is a **low score**.
- **Follow-up**: a feedback response that needs a person to act. A low score sets it, and so does a yes to "contact me" or, on the event survey, to "talk with a mentor".

## The journey, and who does what

1. **The client asks for a mentor.** They submit the public form **Request a Mentor**. An engagement is created, waiting for a mentor.
2. **The intake survey arrives.** Within a few minutes the client gets an email, *While you wait: tell us about your business*, from the shared mailbox. It links to the business profile. At its end the client is asked *Do you have time to provide more details?* A yes lets them pick areas and answer those surveys too. A no ends there, and they can still change their mind from the same link.
3. **Client Administration chooses a mentor.** On the engagement's **Business profile** tab, staff read the client's answers and the areas picked. On the **Mentor match** tab, **Run AI analysis** suggests up to three mentors, each with a reason and how much room they have. Staff still choose, and press **Assign**.
4. **The draft reports are written.** Once a mentor is assigned, each submitted area is analysed by the worker, usually within a few minutes. The record moves from Submitted to **Draft Ready**, and the mentor is emailed.
5. **The mentor reviews.** On the engagement's **Evaluations** tab in Client Management, a Draft Ready row opens the review screen. The mentor edits the **Reviewed report**, with the draft, the answers and the business profile on side tabs, presses **Save report**, and then **Approve**. Only the engagement's mentor can approve. Co-mentors can edit.
6. **The review session.** When every report in the round is approved, the round's line offers **Schedule review session**. The mentor picks an upcoming session or schedules a new one.
7. **Release.** After the session, **Release to client** on the review screen opens a dialog. The mentor ticks the action items the client agreed to, and chooses an owner and a due date for each. **Release** then files the client's copy as a PDF on the Documents tab, marks the report **Reviewed with Client**, and opens the email with the PDF attached for the mentor to check and send. A released report cannot be changed. The action items appear under the Evaluations tab, where their status is changed (Open, Done, Dropped).
8. **Feedback.** Feedback surveys go out at moments a chapter switches on:
   - when an engagement closes;
   - after its third completed session;
   - after an event, to the people who attended;
   - three days after an evaluation round is released.

   A mentor can also send the mentoring survey by hand, from the engagement's **Feedback** tab. A follow-up emails the responsible staff team at once: the Mentor Administration Team, or the Marketing Admin Team for event feedback. Staff close it on the mentor's **Feedback** tab in Mentor Administration, or the event's in Event Administration, with a note saying what was done.

## A mentor sending an evaluation by hand

A client who did not answer at intake can still be evaluated. On the engagement's Evaluations tab the mentor presses **Send Evaluation**, ticks the areas (two or three is advised; more is allowed), and presses **Send**. The email opens in the composer from the mentor's own mailbox. The mentor checks it and presses Send there. The business profile is asked only if the client has not answered it already.

The round's line also offers:

- **Resend**: a new link, carrying the client's answers so far. The old link stops working.
- **Expire**: the link stops working, and unanswered areas become Expired.
- **Record a decline**: unanswered areas become Declined, for reporting.

## Rules worth knowing

- **The draft report never reaches the client.** Only reviewers see it. The client's copy is made from the reviewed report, without the reviewers-only *Points to check* section.
- **Answers are processed by an AI service.** The client agrees to this on the first screen, and nothing is saved before they do. No email address, phone number or street address is sent to the AI service.
- **A survey link is not the client's record number.** It is a random code that expires (30 days by default), and Resend replaces it.
- **The client's answers save as they go.** They can stop and come back to the same link.
- **Mentors see the feedback about their own work, and no figures.** Staff see every response, and totals on the **Feedback** page in Analytics.
- **The quiet period.** A person sent any feedback survey in the last 30 days is not sent another automatic one. The closing survey and surveys sent by hand always go.

## The switches

All of this is switched on or off per chapter, by an administrator, at **System Settings** (`/setup`), on the Settings tab:

| Setting | What it turns on |
|---|---|
| Business Evaluation | The surveys, the Evaluations tab, review and release |
| Intake survey | The business profile emailed when an intake arrives |
| Evaluation analysis interval | How often the draft reports are written (0 stops them) |
| Analyze evaluations before a mentor is assigned | Drafts written before Assign |
| Mentor match | The Mentor match tab in Client Administration |
| Feedback surveys | Feedback tabs, follow-up alerts, the Feedback page |
| Feedback when an engagement closes, at the session milestone, after an event, after an evaluation | Each automatic feedback moment |

The AI service needs the Anthropic integration set up on the **Integrations** tab.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 02:29 | Claude (Claude Code) | Drafted on Doug's decisions of 11-21-26: the whole journey, for staff (A); written here, then published to the documentation site (A). |
