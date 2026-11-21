# Business Evaluation — the training demo

Last Updated: 11-21-26 13:47 · Revision 0.4 — see change log at the end.

A step-by-step demo for training new staff on the evaluation journey. The trainee plays every part in turn: the client, the Client Administration staff member who assigns a mentor, the mentor, and the Mentor Administration staff member who closes a follow-up. It runs on the Business Mentors Association's training system and takes about 90 minutes. The background is in `business-evaluation-guide.md` at the repository root.

**Status.** Draft for Doug's review, not yet run end to end. Where Training courses is switched on, trainees take it in the application, at `/courses/evaluation-demo`, where their ticks and answers are saved and their completion recorded. Until then they use the step-by-step page made from this file (Doug's choice A, 11-21-26): https://claude.ai/artifact/TVxJtFYFi4h3oqytAszX2t. This file is the one source of both: after an edit, rebuild the page with `uv run python scripts/build_runbook.py training/evaluation-staff-course/evaluation-demo.md --out <page.html> --title "Evaluation Training Demo"` and publish it again.

Every value to type is in its own box. On the documentation site each box has a copy button: copy it and paste it rather than typing.

## Before you start

**Once, by an administrator** (in **System Settings** on the training system, the Settings tab), check that these read On or a number above 0: Business Evaluation, Intake survey, Evaluation analysis interval, Mentor match, Feedback surveys. Check also that **Analyze evaluations before a mentor is assigned** reads Off, so the trainee sees the draft written after Assign.

**Each trainee needs:**

- Chrome, with private windows allowed.
- **Keep this course page in a normal window, and do every exercise in a private window.** A browser holds one sign-in per site in its normal windows and another in its private windows. Where the training system is the same site as this course, signing in to an exercise in the window that holds the course would sign the course out of your name.
- **Their own real email address.** The client's emails go there, because the training system's own addresses cannot receive mail.
- Three training sign-ins. The course page in the application fills them in below; a page made from this file names them only, because it is public, so ask the trainer.
  - **Client Administration** login (Kitty Cat): {{signin:Client Administration}}
  - **Mentor** login (Joe Mentor): {{signin:Mentor}}
  - **Mentor Administration** login (Mentor Admin): {{signin:Mentor Administration}}
- About 90 minutes. Each run costs about $0.30 in AI analysis, and leaves a made-up client on the training system until it is next restored.

**The business everyone uses** is *Riverside Candle Co.*, a one-person candle maker. Add your initials to its name, so that two trainees' clients never mix.

## 1. The client asks for a mentor

### 1.1 Open the request form

- **Where:** Chrome, a new private window (not signed in to anything).
- **Action:** paste the address below into the address bar and press Enter.

```
{{training_url}}/client-intake/
```

- **You should see:** the page *Request a Mentor*, on its first step, *About You*.
- **If not:** stop and tell the trainer what the page shows.
- **What it does:** this is the public form a new client fills in.

### 1.2 About You

- **Where:** the *Request a Mentor* form, step *About You*.
- **Action:** fill in each field with the value below, then press **Next**.

First Name:

```
Morgan
```

Last Name:

```
Reyes
```

Email Address, and again in Confirm Email: **your own real email address**.

Phone Number:

```
(216) 555-0143
```

Zip Code:

```
44113
```

How did you hear about the organization: choose **Online Search**.

- **You should see:** the step *Your Mentoring Request*.
- **If not:** a red message names the field to fix. Fix it and press Next.
- **What it does:** creates the client's contact details.

### 1.3 Your Mentoring Request

- **Where:** the *Request a Mentor* form, step *Your Mentoring Request*.
- **Action:** under *Area(s) of Mentoring*, tick **Finance & Cash Flow Management** and **Marketing & Branding**. Paste the text below into *Describe Your Mentoring Needs*. Leave the mentor as **No preference**. Meeting Preference: **Video**. Notification Preference: **Email**. Press **Next**.

Describe Your Mentoring Needs:

```
I make hand-poured soy candles and sell them online, at weekend markets and through three local gift shops. Sales grew last year but I never seem to have cash when the wax order is due. I want help understanding my numbers and pricing, and getting more wholesale customers.
```

- **You should see:** the step *Your Business*.
- **If not:** a red message names the field to fix.
- **What it does:** tells the organization what help the client wants.

### 1.4 Your Business

- **Where:** the *Request a Mentor* form, step *Your Business*.
- **Action:** Business Stage: **Early Stage**. Paste each value below into its field, adding your initials at the end of the business name. Industry Sector: **Manufacturing**. Industry Subsector: **Other**. Press **Next**.

Business Name (then add your initials, for example *Riverside Candle Co. DB*):

```
Riverside Candle Co.
```

Business Website:

```
riversidecandle.example
```

Year Formed:

```
2023
```

Number of Employees:

```
1
```

- **You should see:** the step *Review & Submit*, listing everything entered.
- **If not:** a red message names the field to fix.
- **What it does:** describes the business.

### 1.5 Submit

- **Where:** the *Request a Mentor* form, step *Review & Submit*.
- **Action:** tick **I have read and agree to the Client Code of Conduct, Terms of Use, and Privacy Policy.** Leave the other two boxes unticked. Press **Submit Request**.
- **You should see:** *Thank you!* and a reference number.
- **If not:** stop and tell the trainer the message shown.
- **What it does:** creates the client, the business and an engagement waiting for a mentor.

**Checkpoint:** type the reference number shown on the *Thank you!* page.

## 2. The client answers the intake survey

### 2.1 Open the intake survey email

- **Where:** your own email inbox.
- **Action:** wait up to five minutes, then open the email *While you wait: tell us about your business*. Click **Tell us about your business**.
- **You should see:** in a new tab, the page *Tell us about your business*, on *Before you start*.
- **If not:** check the spam folder. If it is not there after ten minutes, tell the trainer.
- **What it does:** this email goes automatically to every new client.

### 2.2 Give consent

- **Where:** the survey page, *Before you start*.
- **Action:** tick the consent box and press **Continue**. On *Your surveys*, press **Start** beside *About your business*.
- **You should see:** the first section, *What you do*.
- **What it does:** nothing is saved before the client agrees that an AI service may process their answers.

### 2.3 What you do

- **Where:** the survey *About your business*, section *What you do*.
- **Action:** paste the text below into the first question. Then choose: **Manufacturing or making products**; **A mix of these**; tick **Online**, **At markets, events or pop-ups** and **Through other stores or distributors**. Press **Next**.

In a sentence or two, what does your business sell, and to whom?

```
Hand-poured soy candles and wax melts, sold to shoppers online and at markets, and wholesale to local gift shops.
```

- **What it does:** the plain-language picture every report starts from.

### 2.4 Where the business is today

- **Where:** the same survey, section *Where the business is today*.
- **Action:** for the stage, choose **Open 1 to 3 years**. Paste the number below into *How many people work in the business*. Then choose **Yes, full time**; **$25,000 to $100,000**; **About even**. Press **Next**.

How many people work in the business, including you?

```
1
```

### 2.5 Where you want to go

- **Where:** the same survey, section *Where you want to go*.
- **Action:** tick **Get more customers**, **Raise my prices or improve my margins** and **Get my finances organized**. Paste the three texts below into their questions. Choose **3 to 6 hours** for the weekly time. Press **Submit survey**.

What is the biggest challenge in your business right now?

```
Cash. I buy wax and fragrance in bulk twice a year and it empties the account, then the shops pay me 30 to 60 days later.
```

Is there anything you have already tried to fix that challenge?

```
I asked the shops to pay faster and started a small savings pot, but I still run short in the spring.
```

Is there anything else you would like your mentor to know about your business?

```
The holiday season is about half of my yearly sales.
```

- **You should see:** *Thank you. Do you have time to provide more details?*
- **If not:** a message names the questions still needing an answer.
- **What it does:** the business profile is written to the client's record.

### 2.6 Choose an area

- **Where:** the survey page, the question *Do you have time to provide more details?*
- **Action:** press **Yes, choose areas**. Tick **Finance** only. Press **Continue**. Then press **Start** beside *Finance*.
- **You should see:** the Finance survey, section *Keeping track*.
- **What it does:** each area picked becomes a Business Evaluation record.

### 2.7 Finance: Keeping track

- **Where:** the survey *Finance*, section *Keeping track*.
- **Action:** choose **A spreadsheet**; **Yes**; **Every few months**; **Yes, only for taxes**; **2** on the confidence scale. Press **Next**.

### 2.8 Finance: Money coming in

- **Where:** the survey *Finance*, section *Money coming in*.
- **Action:** choose **A tenth to a quarter**; **Yes, a lot**; **It varies a lot**; **I matched what competitors charge**; **Never**. Press **Next**.

### 2.9 Finance: Money going out and cash on hand

- **Where:** the survey *Finance*, section *Money going out and cash on hand*.
- **Action:** tick **Materials, stock or ingredients** and **Marketing and advertising**. Then choose **1 to 3 months**; **Once or twice**; tick **A credit card balance carried month to month**; **Yes, when there is money left over**; **Only in my head**. Paste the text below into the last question. Press **Submit survey**.

What worries you most about the money side of your business?

```
I do not know which candles actually make money once the wholesale discount and the market fees come off.
```

- **You should see:** *Your Finance answers have been submitted. Thank you.*
- **What it does:** the Finance record waits, Submitted, for a mentor. Close this tab.

**Checkpoint:** type the names of the two surveys you submitted.

## 3. Client Administration chooses the mentor

### 3.1 Open the engagement

- **Where:** Chrome, a new private window, signed in to the training system with the **Client Administration** login. Open **Client Administration** from the home page.
- **Action:** type the text below into the box *Search engagements — name, client, contact, mentor, notes…*. Click the engagement's name in the *Engagement* column.

```
Riverside Candle
```

- **You should see:** the engagement's window, on its *Details* tab, with the tabs *Business profile* and *Mentor match*.
- **If not:** if no row appears, tell the trainer.

### 3.2 Read the business profile

- **Where:** the engagement's window, the **Business profile** tab.
- **Action:** read it.
- **You should see:** each question as a small grey label with the answer in a box, and *Finance* listed as an area picked. No report is shown here, ever.
- **What it does:** helps choose the right mentor.

### 3.3 Run the mentor match

- **Where:** the engagement's window, the **Mentor match** tab.
- **Action:** press **Run AI analysis** and wait about half a minute.
- **You should see:** *What this client needs*, *The kind of mentor who would suit* and *Suggested mentors*, each mentor with a reason, their room ("N of M clients, K available") and when they last got a new client.
- **If not:** if a message says the analysis failed, press **Run again** once, then tell the trainer.
- **What it does:** advice only. You still choose.

### 3.4 Assign Joe Mentor

- **Where:** Client Administration, the engagement's row in the grid (close the window first).
- **Action:** in the row's dropdown *Select a mentor…*, choose **Joe Mentor**. Press **Assign**. In the box *Assign "…" to Joe Mentor?*, press **Assign**. When the email composer opens, press **Cancel**, and if asked, **Discard draft** (training mentors' mailboxes cannot receive).
- **You should see:** a green line starting *Assigned "…" to Joe Mentor — status now Pending Acceptance*.
- **What it does:** the engagement and its records move to Joe Mentor, and the Finance analysis can now start.

**Checkpoint:** type the names of the mentors the match suggested, separated by commas.

## 4. The mentor reviews the draft report

### 4.1 Open the engagement as the mentor

- **Where:** Chrome, a new private window, signed in with the **mentor** login (Joe Mentor). Open **Client Management** from the home page.
- **Action:** find *Riverside Candle Co.* in the list (type its name in the search box above the list) and open it. Click the **Evaluations** tab.
- **You should see:** the Evaluations table with one row: Round 1, Finance. Its Status reads **Draft Ready**.
- **If not:** if it reads Submitted, the draft is still being written. Wait five minutes and click the Evaluations tab again. After 15 minutes, tell the trainer.

### 4.2 Read and correct the draft

- **Where:** Client Management, *Riverside Candle Co.*, the Evaluations tab, the Finance row.
- **Action:** click the row. On the review screen, read the side tabs **Draft report**, **Finance answers** and **Business profile**. In the **Reviewed report** on the left, add the sentence below at the end of the summary. Press **Save report**.

```
We agreed in our first session to start with a simple monthly cash plan before looking at prices.
```

- **You should see:** *Report saved.*
- **What it does:** the mentor's corrections go into the reviewed report. The draft stays as the AI wrote it.

### 4.3 Approve

- **Where:** the review screen.
- **Action:** press **Approve**. Then press **Close**.
- **You should see:** *Approved. When every report in round 1 is approved, schedule the review session from the round's line on the Evaluations tab.*
- **What it does:** only the engagement's mentor can approve.

**Checkpoint:** type the Status the Finance row shows on the Evaluations tab after you approved it.

## 5. The review session

### 5.1 Schedule it

- **Where:** Client Management, *Riverside Candle Co.*, the Evaluations tab, the line *Round 1 · link: …*.
- **Action:** press **Schedule review session**, then **Schedule a new session**. In the session editor set Status to **Completed**, the Start date to **today** and the time to the last half hour, and Duration to **1 hour**. Leave the title as it is. Press **Save session**.
- **You should see:** the session saved, and on the Evaluations tab the round's line ends *review session: … Business Evaluation review*.
- **What it does:** the session where the mentor goes through the results with the client. For the demo, we record it as held.

**Checkpoint:** type the review session's title, as the round's line shows it.

## 6. Release the client's copy

### 6.1 Choose the action items

- **Where:** the Evaluations tab, the Finance row, the review screen.
- **Action:** press **Release to client**. In *Release Finance to the client*, tick the first two action items. For each, choose **Morgan Reyes** in *Who…* and leave the due date. Press **Release**.
- **You should see:** the client's copy filed, and the email composer opening with the PDF attached.
- **If not:** if a message names something missing, fix it and press Release again.

### 6.2 Do not send the email

- **Where:** the email composer.
- **Action:** read the email, then press **Cancel**, and if asked, **Discard draft**. (In real use the mentor presses Send.)
- **What it does:** keeps the demo from emailing.

### 6.3 See the results

- **Where:** Client Management, *Riverside Candle Co.*
- **Action:** open the **Documents** tab, then the **Evaluations** tab.
- **You should see:** on Documents, an *Evaluation report* PDF. On Evaluations, the Finance row reads **Reviewed with Client**, and under *Action items* the two items, each with its owner and due date. Change one item's Status to **Done**.
- **What it does:** a released report is final. The action items are followed up in later sessions.

**Checkpoint:** type the two action items, each with its owner.

## 7. The client gives feedback

### 7.1 Make the feedback survey

- **Where:** Client Management, *Riverside Candle Co.*, the **Feedback** tab.
- **Action:** press **Send feedback survey**. Choose **Morgan Reyes (primary)** and press **Open the email**. In the composer, right-click **Answer the survey** and choose **Copy link address**. Then press **Cancel**, and if asked, **Discard draft**.
- **What it does:** a mentor's own survey would go from their mailbox. The training mentor's cannot send, so we open the link by hand.

### 7.2 Answer it as the client

- **Where:** Chrome, a new private window (not signed in).
- **Action:** paste the copied address and press Enter. Tick the consent box, press **Continue**, then **Start**. Choose **4** on the 0-to-10 row. For *Would you like someone from … to contact you about your experience?* choose **Yes**. Paste the text below into *What could we do better?* Press **Submit survey**.

```
The report was useful but I would have liked the session sooner.
```

- **You should see:** a thank-you.
- **What it does:** a score of 4 is a low score. The response is flagged for follow-up, and the Mentor Administration Team is emailed at once.

**Checkpoint:** type the score you gave on the 0-to-10 row.

## 8. Mentor Administration closes the follow-up

### 8.1 Open Joe Mentor's feedback

- **Where:** Chrome, a new private window, signed in with the **Mentor Administration** login (Mentor Admin). Open **Mentor Administration** from the home page.
- **Action:** find **Joe Mentor** in the roster and open him. Click the **Feedback** tab.
- **You should see:** the responses about Joe's engagements. The row with score 4 reads **Needs follow-up** in red.

### 8.2 Mark it done

- **Where:** Mentor Administration, Joe Mentor, the Feedback tab, the row with score 4.
- **Action:** click the row. Read the answers. Paste the note below into *What was done* and press **Mark follow-up done**.

```
Called Morgan to apologise for the wait and booked the next session for next week.
```

- **You should see:** *Follow-up marked done.* The row reads **Done**.
- **What it does:** closes the follow-up, with a record of who did what.

### 8.3 The Feedback page

- **Where:** the same window. Open **Analytics** from the home page and click the **Feedback** tab at the top.
- **You should see:** responses received, the net promoter score with the average, the monthly charts, *By mentor* and *Open follow-ups*.
- **What it does:** the totals staff use. Mentors never see these figures.

**Checkpoint:** type the net promoter score the Feedback page shows.

## What to tell the trainee at the end

- The draft report never reaches the client. Everything the client reads has been checked by their mentor.
- The mentor match is advice. Staff choose the mentor.
- A low score or a "contact me" emails the Mentor Administration Team at once. Close it with a note when someone has acted.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 02:29 | Claude (Claude Code) | Drafted on Doug's decisions of 11-21-26: the whole journey for staff (A), on the documentation site (A), each trainee starting a new client from the intake form (A). |
| 0.2 | 11-21-26 10:51 | Claude (Claude Code) | One line per paragraph (Doug saw hard breaks); the step-by-step page built from this file by `scripts/build_runbook.py` (Doug's choice A). |
| 0.3 | 11-21-26 12:04 | Claude (Claude Code) | Served in the application (training app phase 1): `course.yaml` added; the training system's address written as `{{training_url}}` and the three sign-ins as `{{signin:…}}`; each checkpoint worded as something the trainee types. Minor revision: still a draft (decision 9). |
| 0.4 | 11-21-26 13:47 | Claude (Claude Code) | *Before you start*: keep the course page in a normal window and every exercise in a private window (found at stop 1: on the Association, signing in to an exercise in the course's window sent the course's saves in as the training login). Minor revision. |
