# Business Evaluation — plan

Last Updated: 11-20-26 02:20 · Revision 0.19 — see change log at the end.

This is the design record for the **Business Evaluation** offering. It holds
the terms, the flow, the rulings, the CRM data model, and the build phases with
their stopping points. The build orchestrator
(`prompts/business-evaluation-build-orchestrator-v0.1.md`) and the per-phase
build prompts are written from this file. Phase 1 is built (v0.324.0); phase 2
is built (v0.328.0); phase 2b is built (v0.330.0); phase 3 is built (v0.332.0); phase 4 is built (v0.336.0); phase 5 is built (v0.338.0) and checked; phase 6 is built (v0.339.0) and checked; phase 7 is built (v0.350.0) and checked; phases 8 and 9 are built together (v0.354.0), their combined check owed. The planning session on wider uses (11-16-26) added three uses, § 3b, rulings BE24 to BE36, and re-cut the phases from 6 onward (§ 6); the partner offering, once phase 6, is now phase 10.

**Status of the rulings.** All rulings, BE1 to BE23, are approved by Doug
(11-13-26). Rulings BE1 to BE6 restate what Doug described; BE7 to BE23 were
proposed by Claude and approved without change. Rulings BE24 to BE36
write down Doug's answers and decisions in the planning session on wider
uses, and are **approved by Doug** (11-16-26). Where one changes an earlier
ruling, it says so; the earlier ruling's text is not edited.

## 1. What the offering is

When a mentor is assigned a new client, the mentor offers a free, structured
evaluation of the client's business. The client chooses areas to evaluate. The
mentor clicks an action button that emails the client one survey per area. The
client fills in each survey on a public page, with no login. When the client
submits, the application stores the answers in the CRM and uses the Claude API
to write a draft report in a standard format. The mentor and the subject matter
experts assigned to the client review the draft and correct it. The mentor then
holds a session to go through the results with the client. The report ends in a
list of recommended action items for the mentor to work on with the client.

The offering can also be promoted by partners and funders to their members.

**Worked example.** Quarry Street Coffee is assigned to a mentor. At the first
session the owner chooses Finance and Marketing. The mentor clicks **Send
Evaluation** on the engagement. The owner gets one email with a link, answers
the short business profile once, then the Finance and Marketing surveys, and
submits each. Ten minutes later the engagement's Evaluations tab shows two draft
reports. The mentor and a co-mentor with a finance background edit the Finance
draft, approve both, and schedule a review session. At that session the owner
agrees to six action items, which are then tracked on the engagement.

**Wider uses, added 11-16-26.** The same survey engine serves three more
uses, set out in § 3b. A new client gets the business profile survey
automatically when their intake arrives, and may choose detailed areas then.
Client Administration uses those answers, and an AI mentor match, to pick
the mentor. Feedback surveys, with a 0-to-10 recommendation score, measure
how well the organization helped, after sessions, engagements, events and
evaluations, and are totalled in Analytics.

## 2. Terms

- **Evaluation area**: one subject the offering can analyze, for example
  Finance. Each evaluation area has one survey, one analysis prompt and one
  scoring rubric.
- **Business profile survey**: a short survey answered once per engagement,
  before any area survey. It records industry, stage, size, revenue range and
  the owner's goals. Every analysis receives it as context.
- **Area survey**: the questions for one evaluation area.
- **Survey definition**: the file that holds one survey's questions, answer
  types and help text, with a version number.
- **Evaluation link**: the link emailed to the client. It opens the client's
  surveys with no login. It is tied to one engagement.
- **Business Evaluation record**: the CRM record for one evaluation area for one
  engagement. It holds the answers, the draft report, the reviewed report and
  the status.
- **Evaluation round**: the set of Business Evaluation records sent together. A
  later re-evaluation is a new round. Earlier rounds are kept.
- **Analysis prompt**: the versioned instructions the Claude API receives for
  one evaluation area.
- **Scoring rubric**: the named dimensions an evaluation area is scored on, each
  from 1 to 5, with a description of each level.
- **Draft report**: the report the Claude API writes. It is never shown to the
  client.
- **Reviewed report**: the draft report after the mentor and subject matter
  experts have corrected it and the mentor has approved it.
- **Reviewer**: the engagement's mentor or a co-mentor on the engagement. A
  subject matter expert is added to an engagement as a co-mentor.
- **Action item**: one recommended step in the report, with a reason, a
  priority and a time horizon.
- **Survey engine**: the shared package, `surveys/`, that any kind of survey
  uses: the survey definition format and loader, the public answer page, the
  link store, the saved answers and the submit retry (ruling BE23).
- **Survey purpose**: one kind of survey built on the survey engine. It decides
  which surveys a link opens, what the first screen says, and what happens on
  submit. Business Evaluation is the first survey purpose.
- **Intake survey**: the business profile survey sent automatically when a
  client intake is delivered, before any mentor is assigned (BE24). It is
  the same survey as the business profile survey; only the moment differs.
- **Area picker**: the screen, after the intake survey, where the client
  ticks the evaluation areas they want help with (BE25).
- **Mentor match**: the AI analysis Client Administration staff can run on
  an engagement waiting for a mentor (BE28).
- **Feedback survey**: a survey about how well the organization helped,
  built on the survey engine as a second survey purpose, `feedback` (BE29).
- **Recommendation score**: the answer, 0 to 10, to "how likely are you to
  recommend us". A score of 6 or below is a **low score**.
- **Feedback moment**: an event that sends a feedback survey (BE30).
- **Survey Response record**: the CRM record for one submitted feedback
  survey (BE31).
- **Quiet period**: the number of days after one feedback survey during
  which a person is not sent another automatic one (BE33).
- **Co-branding**: the referring partner's logo shown beside the
  organization's own on what the application makes for that client (BE35).

## 3. The flow

1. **Offer.** The mentor offers the evaluation in conversation. Nothing is
   recorded if the client declines, unless the mentor records the decline (BE14).
2. **Send.** On the engagement in Client Management, the mentor clicks **Send
   Evaluation**, picks the evaluation areas, and sends. The application creates
   one Business Evaluation record per area, status **Sent**, and emails the
   evaluation link from the mentor's own mailbox.
3. **Answer.** The client opens the link, gives consent, answers the business
   profile survey once, then each area survey. Answers save as the client goes,
   so the client can stop and come back. Submitting an area moves its record to
   **Submitted**.
4. **Analyze.** The worker picks up each submitted record, sends the business
   profile, the area answers and the analysis prompt to the Claude API, and
   writes the draft report to the record. Status becomes **Draft Ready**, and
   the mentor is notified.
5. **Review.** The mentor and co-mentors open the Evaluations tab, read the
   answers and the draft report, and edit the report. The mentor clicks
   **Approve**. Status becomes **Approved**.
6. **Review session.** The mentor schedules a session with the client through
   the existing session scheduling. The session is linked to the evaluation
   round.
7. **Release and act.** After the session the mentor releases the client
   version of the report and confirms the action items the client agreed to.
   Status becomes **Reviewed with Client**.

## 3b. The wider uses (11-16-26)

Doug's answers in the planning session, confirmed by him as written at its
first stopping point.

**Use 1: the intake survey.** A client intake is delivered. Nobody clicks
anything: the application emails the client from the shared mailbox, along
the lines of "We'll get back to you soon; while you wait, tell us more about
your business." The link opens the business profile survey only. At its end
the client is asked "Do you have time to provide more details?" A yes opens
the area picker, which lists the available evaluation areas as areas the
client would like help with; the client ticks theirs and answers them. A no
ends there, and nothing is lost. The answers go where the mentor's own
evaluation puts them, so a later **Send Evaluation** does not ask the
business profile again. Client Administration sees the business profile
answers and the areas picked while choosing the mentor; the assigned mentor
then sees everything on the Evaluations tab.

*Example.* Brightline Bakehouse submits the intake on Monday evening. Within
minutes the owner has the email, answers the business profile, says yes,
picks Finance and answers it on Tuesday. On Thursday a Client Administration
staff member reads the answers and the Finance pick before assigning.

**Use 2: the mentor match.** On an engagement waiting for a mentor, a Client
Administration staff member clicks **AI analysis**. The Claude API reads the
business profile answers and the areas picked, and the mentor profiles with
each mentor's room for another client. It returns a short statement of the
client's needs, the kind of mentor that would suit, and a few named mentors
with the reason for each. Advice only: the staff member still chooses and
clicks **Assign**. Mentors' past engagements are left for later.

**Use 3: feedback surveys.** Surveys about how well the organization helped:
a recommendation score, yes/no questions and short text answers. They go out
automatically when an engagement closes, when its third session is logged,
after each event or webinar, and after a Business Evaluation report is
released to the client; and on demand, sent by a mentor or a staff member. A
mentor sees the responses about their own work; staff see every response
and the totals in Analytics, by mentor, by event and over time. A low score
alerts staff at once.

*Example.* Brightline Bakehouse's third session is logged. The owner gets
the mentoring feedback survey and answers 9, "yes" to "Is your mentor
responsive?", and "Joe helped me see my cash flow problem clearly." Joe
Mentor sees it on the engagement; the Mentor Administration Team sees it in
Analytics in Joe's average.

**The partner offering, refined.** A partner promotes "Sign up for our free
mentoring program, and get a full business evaluation." The member signs up
through normal intake, credited to the partner; the evaluation is part of
mentoring, never offered on its own. From there the process is the standard
one, with the partner's logo beside the organization's on everything the
application makes for that client.

## 4. Rulings

### Described by Doug, 11-13-26

| # | Ruling |
|---|---|
| BE1 | The offering is made by the mentor to a newly assigned client. It is free. |
| BE2 | The evaluation areas at launch are Finance, Competition, Marketing, Funding, Product and Information Technology. |
| BE3 | The mentor starts it with an action button in Client Management. The application emails the client. |
| BE4 | There is one survey per evaluation area. The client fills it in on a public page of this application reached by a link that carries the engagement, the same pattern as the client intake form. No client login. |
| BE5 | Submitted answers are written to the CRM, tied to the engagement, and are reviewed by the mentor in Client Management. |
| BE6 | The Claude API turns the answers into a report in a standard format. The mentor and the subject matter experts assigned to the client correct it before the mentor reviews it with the client in a session. The report gives recommended action items. |

### Proposed by Claude, approved by Doug 11-13-26

| # | Ruling | Why |
|---|---|---|
| BE7 | **Each evaluation area for each engagement is its own Business Evaluation record**, a new CRM entity linked to the engagement and to the client profile, rather than new fields on the client profile. It shows on the client's information as an Evaluations tab. | Six areas of about 20 questions would add over 100 fields to the client profile, and a re-evaluation would overwrite the first one. A record per area keeps history and lets areas be added without CRM changes. The cost: one more entity to secure and reconcile. |
| BE8 | **A short business profile survey is answered once per engagement**, before the first area survey, and every analysis receives it. | Without it, each area survey repeats the same questions or each analysis lacks context. |
| BE9 | **Survey definitions, analysis prompts and scoring rubrics are versioned files in this repository**, one set per evaluation area. Each Business Evaluation record stores the versions that produced it. They are not editable in the application in this build. | Results stay comparable and explainable. Adding an area is a content change, not a code change. The cost: a staff member cannot change a question without a release. |
| BE10 | **The mentor may send any number of areas, but the Send dialog advises two or three per round.** It warns above three and still sends. | Six long surveys at once will not be finished. Buttons are never disabled, by this repository's convention. |
| BE11 | **The survey page asks for consent before the first question**: the answers are processed by an AI service and kept with the client's CBM record. No consent, no submit. The time of consent is stored. | Required before partners will offer it, and the honest default. |
| BE12 | **The evaluation link is a random token stored in the application database**, never the CRM id, the same as the campaign links (ruling 31). It expires after `EVALUATION_LINK_DAYS` (default 30). The mentor can resend, which issues a new link and ends the old one. | The link carries access to the client's answers, so it must not be guessable. |
| BE13 | **Answers save as the client goes**, in the application database, and are written to the CRM only on submit. | Lets the client stop and return. Keeps half-finished answers out of the CRM. |
| BE14 | **Business Evaluation status values**: Sent, In Progress, Submitted, Draft Ready, Approved, Reviewed with Client, Declined, Expired, Analysis Failed. | One status per step in § 3. Declined lets the mentor record a refusal for reporting. |
| BE15 | **The analysis runs in the worker, one Claude API call per area, with schema-checked structured output**, the pattern in `comms/summarize.py`. Feature switch `BUSINESS_EVALUATION`, default off. A failed call sets Analysis Failed and offers **Retry**. | Proven pattern in this repository. The worker keeps the client's submit fast. |
| BE16 | **Every report has the same sections**: summary; a score per rubric dimension with the reason; strengths; gaps; recommended action items (title, reason, priority, time horizon); information the client did not give; and the points the analysis is unsure of. | A standard format is what makes reports comparable and reviewable. |
| BE17 | **The draft report is never shown or sent to the client.** Only the mentor can approve. Reviewers edit the reviewed report; the draft report is kept unchanged beside it. | Keeps a person responsible for every word the client reads. Keeping the draft lets CBM measure what reviewers change and improve the prompts. |
| BE18 | **Subject matter experts are added as co-mentors** on the engagement, through the existing Add Co-Mentors action. Every co-mentor can edit the reviewed report. | Reuses the existing access model; no new role. The cost: a subject matter expert sees the whole engagement, not only the evaluation. |
| BE19 | **The client version of the report** is the reviewed report without the internal sections (the points the analysis is unsure of, reviewer notes). The mentor releases it after the review session: it is filed in the engagement's Documents and emailed from the mentor's mailbox. | The client gets a clean document; reviewers keep their working notes. |
| BE20 | **Action items the client agrees to become records on the engagement**, each with an owner and a due date, so later sessions can track them. Which CRM entity holds them is open question 1. | A list inside a document gets forgotten. |
| BE21 | **Partners and funders offer it through the existing partner referral link**: `client-intake/?partner=<id>&offer=evaluation`. The member becomes a CBM client through normal intake, credited to the partner, and the engagement shows that an evaluation was requested. A later phase gives each partner and funder an anonymized roll-up of scores by area, only for groups of five or more clients. | Keeps one way into CBM and one data model. The evaluation becomes a way in to mentoring, not a separate product. |
| BE22 | **Pilot first**: build every phase with Finance and Marketing only, run it with 5 to 10 clients, then add the other four areas as content. | Most of the risk is in question quality and report quality, not code. |
| BE23 | **The survey definition format and loader, the public answer page, the link store, the saved answers and the submit retry are a shared survey engine**, the `surveys/` package, not part of Business Evaluation. A survey link names its survey purpose and the CRM record it points at (entity type and id). Business Evaluation is the first survey purpose; everything specific to it stays in `evaluation/`, and the engine holds no code specific to it. Added 11-13-26, after phase 1 was built and while phase 2 was running: phase 2b moves the engine pieces into `surveys/` after phase 2 and before phase 3 builds on them. | Later surveys, such as customer satisfaction after an engagement or feedback after an event, then need only their own definitions and a small purpose layer. Every later phase would make the move more expensive. The cost: one extra phase of refactoring now. |

### From Doug's answers in the planning session on wider uses, approved by Doug 11-16-26

| # | Ruling | Why |
|---|---|---|
| BE24 | **The intake survey.** When a client intake is delivered, the application makes an evaluation link for the new engagement that opens the business profile survey, and emails it to the client from the shared mailbox (`OPS_MAILBOX`). Best-effort: a failure is logged and never fails the intake. Its own switch, default off, so each chapter decides. **Amends BE1 and BE3**: the evaluation is no longer offered only by the mentor, with a button; it can also begin at intake. | Doug: get more from the client while they wait, without a long first ask. There is no mentor yet, so the shared mailbox sends, as for staff-tool mail. |
| BE25 | **"Do you have time to provide more details?"** ends the intake survey. A yes opens the area picker: the client ticks the evaluation areas they want help with, and one Business Evaluation record per area picked is created then, round 1. A no ends the survey. **Amends BE10**: here the client picks the areas, not the mentor; the picker shows the same advice of two or three. Only the areas that have a survey are listed (BE22). | Doug: keep the first ask short so the client does not give up, and let a willing client give more. |
| BE26 | **Client Administration sees the business profile answers and the areas picked** on an engagement waiting for a mentor. It never sees a draft report (BE17 unchanged). **Assign moves the engagement's Business Evaluation records to the mentor** with the rest of the engagement. | Doug: the answers are for a better mentor match. |
| BE27 | **Whether an area submitted before assignment is analyzed at once is a System Settings switch**, default off. Off: it waits as Submitted, and assigning a mentor starts the analysis. On: the draft is written at once and waits for a reviewer. Either way the draft-ready email goes to the mentor once one is assigned. **Amends BE17** by one sentence: a draft may exist before the engagement has a reviewer; it is still shown only to reviewers. | Doug, decision 1 (11-16-26): a chapter may not want to pay for an analysis of a junk submission. |
| BE28 | **The mentor match.** An **AI analysis** button in Client Administration, on an engagement waiting for a mentor. It sends the business profile answers, the areas picked and the mentor profiles (industry experience, expertise, background) with each mentor's active clients and maximum to the Claude API. It returns the client's needs, the kind of mentor that would suit, and a few named mentors, each with a reason. **Advice only**: staff still choose and click Assign. No contact details are sent. The prompt is a versioned file (as BE9). Recorded in the action log. Its own switch, default off. Mentors' past engagements are left for later. | Doug: a better match, faster. Capacity matters as much as fit. |
| BE29 | **Feedback surveys are a second survey purpose**, `feedback`, in a package of its own. Their definitions are versioned files in this repository, changed through a release (as BE9); a staff survey builder is later. They use the existing yes/no and text questions and a **new 0-to-10 question type** for the recommendation score. Its own switch, default off. | Doug: more than the single net promoter question; written here first. |
| BE30 | **The feedback moments.** Automatic: an engagement closes; its third session is logged as Completed; an event or webinar ends (to registrants marked Attended); a Business Evaluation report is released. On demand: a mentor (for their own engagements) or staff. The automatic moments are found by a worker sweep, so a change made in the CRM directly is caught too. Each automatic moment can be switched off on its own. | Doug's list, 11-16-26. A sweep, because staff also close engagements in the CRM. |
| BE31 | **A submitted feedback survey is a Survey Response record in the CRM**: the survey and its version, the moment, the recommendation score as a number, every answer as readable text and as JSON, and links to what it is about (engagement and mentor, or event) and the contact. | Doug, decision 2 (11-16-26): the CRM is the system of record, and Analytics' metric builder works over CRM records, so staff can build their own feedback measures. |
| BE32 | **Who sees feedback.** A mentor sees the responses about their own work; staff see every response; Analytics totals them. Event feedback goes to staff only. A **low score** (6 or below) sets a needs-follow-up flag on the record and alerts staff at once: the Mentor Administration Team for mentoring feedback, the Marketing Admin Team for event feedback. Staff mark the follow-up done. | Doug, 11-16-26. Six or below is the standard net promoter cut-off. |
| BE33 | **The quiet period.** A person sent any feedback survey in the last N days (System Settings, default 30; 0 turns it off) is not sent an automatic one; the skip is logged. The engagement-closing survey and on-demand sends always go. Counted per email address, across every kind of feedback survey. | Doug, decision 3 (11-16-26): fewer asks, better answers; the closing survey matters most. |
| BE34 | **The partner's link, refined (BE21 stands).** The partner promotes the mentoring program with the evaluation included; the member signs up through normal intake, credited to the partner. The link marks the engagement "Evaluation requested", the intake page says the evaluation is included, and the intake survey skips "Do you have time to provide more details?" and goes straight to the area picker. Everything after that is the standard process. | Doug, decision 4 (11-16-26): the member gets what the partner promised; the evaluation is part of mentoring, never offered alone. |
| BE35 | **Co-branding.** A partner record gains a logo, uploaded on its Details tab in Partner Management. For a client referred by a partner with a logo, the logo appears beside the organization's own, never in its place, on everything the application makes for that client: the intake page, the intake survey email, the survey page, the report PDF, the release email and the feedback surveys. **Never on a mentor's own mail.** The partner credited with the referral is the one shown. | Doug, decisions 4 and 5 (11-16-26): the partner's brand stays on what we make; the mentor's voice stays theirs. |
| BE36 | **The partners' roll-up gains the recommendation score**: the average for the clients a partner referred, under the same group-of-five rule as the evaluation scores (BE21). | Feedback is the partner's best evidence that the referral helped its members. |

## 5. CRM data model

New entity **CBusinessEvaluation** (label "Business Evaluation"), Base type,
collaborators (Multiple Assigned Users), stamped with the engagement's
`assignedUsers` and kept in step by the nightly assignment reconciliation.

| Field | Type | Notes |
|---|---|---|
| name | varchar | "{Area} — {Company}", generated. |
| engagement | link CEngagement | Required. |
| clientProfile | link CClientProfile | Required. |
| evaluationArea | enum | Finance, Competition, Marketing, Funding, Product, Information Technology. |
| evaluationRound | int | 1 for the first round. |
| status | enum | BE14. Audited. |
| surveyVersion, promptVersion, rubricVersion | varchar | BE9. |
| answers | text | The submitted answers as JSON, for the analysis. |
| answersReadable | wysiwyg | The same answers as question-and-answer text, for reviewers. |
| scores | text | JSON: dimension → score and reason. |
| draftReport | wysiwyg | Read-only. Written by the worker. |
| reviewedReport | wysiwyg | Edited by reviewers. Starts as a copy of draftReport. |
| sentAt, consentAt, submittedAt, analyzedAt, approvedAt, releasedAt | datetime | |
| approvedBy | link User | |
| reviewSession | link CSession | Set when the review session is scheduled. |
| analysisError | text | Last failure, for Retry. |

The business profile survey answers are written to the client profile (one
text field, `evaluationProfile`, JSON, plus `evaluationProfileAt`), since there
is one per engagement.

The application database holds the survey link tokens and the saved-as-you-go
answers (both in the survey engine, BE23) and the analysis job queue. None of
it is business data once submitted.

### Added 11-16-26 for the wider uses (BE24 to BE36)

New entity **CSurveyResponse** (label "Survey Response"), Base type,
collaborators, stamped with the engagement's `assignedUsers` when it is
about an engagement. One record per submitted feedback survey (BE31).

| Field | Type | Notes |
|---|---|---|
| name | varchar | "{Survey} — {Contact}", generated. |
| surveyKey, surveyVersion | varchar | Which definition, which version. |
| moment | enum | Engagement Closed, Third Session, Event, Evaluation Released, On Demand. |
| recommendScore | int | 0 to 10; empty when not answered. |
| answers | text | JSON. |
| answersReadable | wysiwyg | Question-and-answer text. |
| engagement | link CEngagement | When about an engagement. |
| mentorProfile | link CMentorProfile | The engagement's mentor at the time, for totals by mentor. |
| event | link CEvent | When about an event. |
| contact | link Contact | Who answered. |
| needsFollowUp | bool | Set for a low score (BE32). |
| followUpDone | bool | Set by staff. |
| followUpNote | text | |
| consentAt, submittedAt | datetime | |

Also: **CPartnerProfile** gains a logo (image field, BE35), and
**CEngagement** gains an "Evaluation requested" flag (BE34). Where each sits
exactly, and the role grants (a mentor reads responses about their own
engagements; the Client Administration Team reads the business profile
answers), are settled at the phase's first stopping point and go through a
plan in `crm-plans/` with a handoff file.

The application database adds what the quiet period needs (when each person
was last sent a feedback survey) and the moments already sent, so a sweep
never sends twice. Both in the `feedback` package's own tables or the survey
engine's link store, settled in phase 8.

**Settled at phases 8 and 9's stopping point (a), 11-20-26** (Doug, every
decision as recommended; detail in `feedback/CLAUDE.md`):

- **The CRM plan**, as above, plus a `businessEvaluation` link and
  `followUpDoneAt`. The moment "Third Session" is **"Session Milestone"**,
  because the number of sessions is a System Settings value
  (`FEEDBACK_SESSION_COUNT`, default 3; Doug's addition to decision 6).
- **The grants**: the Mentor Role reads own; the Mentor Administration Role
  and the Marketing Admin Role read and edit every response (A).
- **The two application-database records** are the `feedback` package's own
  tables, `feedback_send` and `feedback_alert` (A).

## 6. Build phases and stopping points

| Phase | What it builds | Stopping points for Doug |
|---|---|---|
| 1 | The foundation: the CRM plan applied to crm-test; the survey definition format and loader; the business profile, Finance and Marketing survey drafts; the link store; the public survey page with consent, save-as-you-go and submit to the CRM; all dark behind `BUSINESS_EVALUATION`. | (a) the CRM plan and the three survey drafts, before the page is built; (b) the survey page working on a local run. |
| 2 | The mentor side: the Evaluations tab in Client Management, **Send Evaluation**, the email template, status display, answers view, resend and expire. | The Send dialog and email, on crm-test. |
| 2b | The survey engine (BE23): the definition loader, link store, saved answers, submit retry and public page moved from `evaluation/` into `surveys/` behind a purpose registry, with Business Evaluation as the first survey purpose; the old `/evaluation/…` links redirect to `/survey/…`. No change a client, mentor or staff member can see. | (a) the purpose registry and the table migration, before code moves; (b) the phase 1 live check repeated on crm-test. |
| 3 | The analysis: the worker job, the Finance and Marketing analysis prompts and rubrics, the structured output, the report template, failure and Retry, cost logging. | Sample reports written from made-up answers, reviewed by Doug before the phase closes. |
| 4 | Review and approval: the report editor, co-mentor editing, Approve, keeping the draft beside the reviewed report, scheduling the review session. | — |
| 5 | Release and action items: the client version, filing and email, action items as records. Needs open question 1 answered. | The client version of a sample report. |
| 6 | The intake survey (BE24 to BE27): the link and email made when a client intake is delivered; "Do you have time to provide more details?" and the area picker on the survey page; the business profile answers and areas picked in Client Administration; Assign moving the evaluation records; the analyze-before-assignment switch. | (a) the email's wording, the picker screen and the Client Administration panel, before building; (b) Doug's check on the Business Mentors Association's system. |
| 7 | The mentor match (BE28): the **AI analysis** button, the matching prompt and its structured output, the mentor-profile fields sent, the result panel. | (a) the fields sent and the prompt; (b) sample matches from made-up clients against the Association's mentors, reviewed by Doug. |
| 8 | Feedback surveys, the foundation (BE29, BE31 to BE33): the `feedback` survey purpose, the 0-to-10 question type, the Survey Response CRM plan, the mentoring, event and evaluation feedback survey drafts, the on-demand send, the mentor's view of their own responses, the low-score alert and follow-up, the quiet period. | (a) the CRM plan and the survey drafts; (b) Doug's check on the Association's system. |
| 9 | Feedback moments and Analytics (BE30): the worker sweep for the four automatic moments, each with its own switch; starter Analytics panels (recommendation score by mentor, by event, over time). | Doug's check on the Association's system. |
| 10 | The partner offering (BE21, BE34 to BE36), formerly phase 6: the referral link, the "Evaluation requested" flag, co-branding and the partner logo, the anonymized roll-up of evaluation and recommendation scores, how a funder offers it. Its approved prompt is rewritten at the close of phase 9. | The roll-up's content. |
| 11 | The pilot review, then the other four areas as content. Formerly phase 7. | Pilot results. |
| 12 | Documentation, training material, the live review, the production handoff. Formerly phase 8. | Production go-ahead. |

**The order, 11-16-26.** The intake survey first: it reuses most and feeds
the mentor match. Feedback next, since the partner roll-up needs its
recommendation score. The partner offering last of the new work, so it is
built once, with co-branding on every page that exists by then. The pilot
(BE22) can begin once phase 6 is live: its 5 to 10 clients exercise phases 1
to 6.

## 7. Open questions

1. **Which CRM entity holds action items?** The engagement's sessions have
   next steps today, but there is no action-item entity known to this plan.
   Options: a new `CActionItem` linked to the engagement, or the CRM's own Task
   entity. Needed by phase 5. **Answered by Doug 11-15-26: a new `CActionItem`**
   (the owner is a Contact, so the client can own an item; Task's owner must
   be a CRM login and no role reads Task today).
2. **Who writes the survey questions and rubrics?** Phase 1 drafts the
   business profile, Finance and Marketing surveys for review. Should a CBM
   mentor with that background review each one before the pilot?
3. **Should the analysis read the client's website and named competitors?**
   The Claude API can search the web. It improves the Competition and Marketing
   reports and adds cost and a source to check. Proposed for phase 11 (the pilot review, formerly phase 7), off by
   default.
4. **Should the client attach documents**, such as financial statements? It
   improves the Finance report and means handling sensitive files. Proposed as
   a later addition, not in the pilot.
5. **Further evaluation areas** after the pilot, for example Operations, Legal
   and Compliance, People, and Strategy.
6. **Prompts and rubrics editable in System Settings.** Doug, 11-14-26: BE9
   stands for the pilot (versioned files, changed through a session and a
   release), but the analysis prompts and scoring rubrics are to become
   editable in System Settings in a later phase, each save a new version.
   To be planned at the phase 11 pilot review (formerly phase 7), when mentors' corrections show
   how often they change. It needs: an editor, version storage in the
   application database, a test run before a version goes live, and an
   amendment to BE9.

## 8. Later survey purposes — outside this build

Ruling BE23 prepares for these. **Feedback surveys are now in this build**
(§ 3b, BE29 to BE33, phases 8 and 9), which settles the first example below
and the Survey Response record; the rest of this section stays later.
Each other purpose needs its own plan when it is wanted. A customer satisfaction survey, for example after an
engagement closes or after an event, would need: a general Survey Response
record in the CRM that can attach to any record; sending to many people at
once through the existing marketing lists; totals across responses, for
example average scores by mentor or by event, in Analytics; and, eventually,
surveys staff can edit without a release.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 00:42 | Claude (Cowork) | Created from Doug's description of 11-13-26: rulings BE1 to BE6 as described, BE7 to BE22 proposed, the CRM data model, eight phases, five open questions. |
| 0.2 | 11-13-26 00:57 | Claude (Cowork) | Doug approved every ruling, BE1 to BE22, without change. |
| 0.3 | 11-13-26 10:45 | Claude (Claude Code) | Phase 1 built, v0.324.0. Two departures from § 5, approved by Doug: `draftReport` is not Read-only, and `engagement` and `clientProfile` are required by the application. |
| 0.4 | 11-13-26 13:55 | Claude (Claude Code) | Phase 2 built, v0.328.0: the mentor side. Doug's choices 11-13-26: the email wording lives in this repository, and Resend carries the client's answers and consent to the new link. |
| 0.5 | 11-13-26 14:22 | Claude (Cowork) | Ruling BE23 added and approved by Doug: the shared survey engine. Status paragraph, two terms in § 2, § 5's storage sentence, phase 2b in § 6, and § 8 for later survey purposes. Merged by Claude (Claude Code) 11-13-26 14:24 from `Claude outputs/be23-plan-and-orchestrator-changes.md`. |
| 0.6 | 11-13-26 22:58 | Claude (Claude Code) | Phase 2b built, v0.330.0: the survey engine `surveys/`, Business Evaluation its first survey purpose; `/evaluation/{token}` redirects to `/survey/{token}`. Doug's option A: the shared "no longer valid" page keeps phase 1's words. |
| 0.7 | 11-14-26 13:17 | Claude (Claude Code) | Open question 6 added: Doug's decision 11-14-26 that BE9 stands for the pilot and that prompts and rubrics become editable in System Settings later, planned at the phase 7 review. |
| 0.8 | 11-14-26 13:35 | Claude (Claude Code) | Phase 3 built, v0.332.0: the analysis. Doug's choices 11-14-26: the mentor is told by email (A); the prompts revised to a measured voice, areas worth looking at and questions to explore; the report's section on missing information headed "Questions to explore"; the CRM status, not a database table, is the analysis queue. |
| 0.9 | 11-15-26 12:20 | Claude (Claude Code) | Phase 4 built, v0.336.0: review and approval, and the review session. Doug's choices 11-14-26, all as recommended: every reviewer can still edit an approved report, and a saved change withdraws the approval; the draft is shown beside the editor; no images in the report; the review session is an upcoming session picked or a new one made. Checked by Doug on a local run against crm-test 11-15-26. |
| 0.10 | 11-15-26 23:20 | Claude (Claude Code) | Phase 5 built, v0.338.0: release and action items. Doug's choices 11-15-26, all as recommended: open question 1 answered, a new `CActionItem`; the client version a PDF filed on the Documents tab with a header, the agreed action items and a closing note; one Release dialog per area; a released report is final; the release email as shown; the check on the Business Mentors Association's system, not crm-test. |
| 0.11 | 11-16-26 01:10 | Claude (Claude Code) | Phase 5 checked by Doug on the Business Mentors Association's system 11-16-26: release as Joe Mentor, the PDF, the action items, Release refused as Matt Mentor. |
| 0.12 | 11-16-26 02:05 | Claude (Claude Code) | Phase 6 on hold: Doug wants a planning session on wider uses of the evaluation first (`prompts/business-evaluation-expansion-planning-prompt-v0.1.md`). |
| 0.13 | 11-16-26 11:59 | Claude (Claude Code) | The planning session on wider uses: § 3b (the intake survey, the mentor match, feedback surveys, the partner offering refined), confirmed by Doug as written; terms in § 2; rulings BE24 to BE36 from Doug's answers and decisions 1 to 5; § 5's CSurveyResponse, partner logo and engagement flag; § 6 re-cut, phases 6 to 12, the partner offering moved to phase 10; § 8 updated. |
| 0.14 | 11-16-26 12:04 | Claude (Claude Code) | Rulings BE24 to BE36 and the re-cut phases approved by Doug as written. |
| 0.15 | 11-16-26 13:30 | Claude (Claude Code) | Phase 6 built, v0.339.0: the intake survey, behind `INTAKE_SURVEY`. Doug's choices at stopping point (a) 11-16-26, all as recommended: the email as drafted; a no on "more details?" can still become a yes; a *Business profile* tab in Client Administration's popup; no CRM grant, the areas read under the org-wide key. § 5's Client Administration grant is therefore not needed. Its check on the Association owed. |
| 0.16 | 11-19-26 22:30 | Claude (Claude Code) | Phase 6 checked by Doug on the Business Mentors Association's system 11-19-26: intake, email, profile, Marketing picked and answered, the Business profile tab as Kitty Cat, Assign, Marketing on Joe Mentor's Evaluations tab. His finding on the tab fixed in v0.340.1. |
| 0.17 | 11-19-26 23:36 | Claude (Claude Code) | Phase 7 built, v0.350.0: the mentor match (BE28), behind `MENTOR_MATCH`. Doug's choices at stopping point (a) 11-19-26, all as recommended: the profile lists, the website texts and the last-assigned date sent (A); the prompt as drafted, a mentor at capacity suggested only when clearly best (A); a fourth tab, *Mentor match* (A); every run kept (A); samples on the Association plus a made-up roster of 50 (A). |
| 0.18 | 11-20-26 00:59 | Claude (Claude Code) | Phase 7 checked by Doug on the Business Mentors Association's system 11-20-26 ("worked great"). Added at his request during the check: each suggestion shows the mentor's last new client date, and *Assign this mentor* in the mentor popup assigns. |
| 0.19 | 11-20-26 02:20 | Claude (Claude Code) | Phases 8 and 9 built together, v0.354.0: feedback surveys. Doug's eight decisions at stopping point (a) 11-20-26, all as recommended, with one addition (the session count a setting). § 5 records what was settled. The combined check on the Association is owed. |
