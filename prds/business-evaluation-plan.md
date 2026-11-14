# Business Evaluation — plan

Last Updated: 11-13-26 22:58 · Revision 0.6 — see change log at the end.

This is the design record for the **Business Evaluation** offering. It holds
the terms, the flow, the rulings, the CRM data model, and the build phases with
their stopping points. The build orchestrator
(`prompts/business-evaluation-build-orchestrator-v0.1.md`) and the per-phase
build prompts are written from this file. Phase 1 is built (v0.324.0); phase 2
is built (v0.328.0); phase 2b is built (v0.330.0).

**Status of the rulings.** All rulings, BE1 to BE23, are approved by Doug
(11-13-26). Rulings BE1 to BE6 restate what Doug described; BE7 to BE23 were
proposed by Claude and approved without change.

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

## 6. Build phases and stopping points

| Phase | What it builds | Stopping points for Doug |
|---|---|---|
| 1 | The foundation: the CRM plan applied to crm-test; the survey definition format and loader; the business profile, Finance and Marketing survey drafts; the link store; the public survey page with consent, save-as-you-go and submit to the CRM; all dark behind `BUSINESS_EVALUATION`. | (a) the CRM plan and the three survey drafts, before the page is built; (b) the survey page working on a local run. |
| 2 | The mentor side: the Evaluations tab in Client Management, **Send Evaluation**, the email template, status display, answers view, resend and expire. | The Send dialog and email, on crm-test. |
| 2b | The survey engine (BE23): the definition loader, link store, saved answers, submit retry and public page moved from `evaluation/` into `surveys/` behind a purpose registry, with Business Evaluation as the first survey purpose; the old `/evaluation/…` links redirect to `/survey/…`. No change a client, mentor or staff member can see. | (a) the purpose registry and the table migration, before code moves; (b) the phase 1 live check repeated on crm-test. |
| 3 | The analysis: the worker job, the Finance and Marketing analysis prompts and rubrics, the structured output, the report template, failure and Retry, cost logging. | Sample reports written from made-up answers, reviewed by Doug before the phase closes. |
| 4 | Review and approval: the report editor, co-mentor editing, Approve, keeping the draft beside the reviewed report, scheduling the review session. | — |
| 5 | Release and action items: the client version, filing and email, action items as records. Needs open question 1 answered. | The client version of a sample report. |
| 6 | The partner offering: the `offer=evaluation` referral, the engagement flag, the anonymized roll-up for partners and funders. | The roll-up's content. |
| 7 | The pilot review, then the other four areas as content. | Pilot results. |
| 8 | Documentation, training material, the live review on crm-test, the production handoff. | Production go-ahead. |

## 7. Open questions

1. **Which CRM entity holds action items?** The engagement's sessions have
   next steps today, but there is no action-item entity known to this plan.
   Options: a new `CActionItem` linked to the engagement, or the CRM's own Task
   entity. Needed by phase 5.
2. **Who writes the survey questions and rubrics?** Phase 1 drafts the
   business profile, Finance and Marketing surveys for review. Should a CBM
   mentor with that background review each one before the pilot?
3. **Should the analysis read the client's website and named competitors?**
   The Claude API can search the web. It improves the Competition and Marketing
   reports and adds cost and a source to check. Proposed for phase 7, off by
   default.
4. **Should the client attach documents**, such as financial statements? It
   improves the Finance report and means handling sensitive files. Proposed as
   a later addition, not in the pilot.
5. **Further evaluation areas** after the pilot, for example Operations, Legal
   and Compliance, People, and Strategy.

## 8. Later survey purposes — outside this build

Ruling BE23 prepares for these; none is built here. Each needs its own plan
when it is wanted. A customer satisfaction survey, for example after an
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
