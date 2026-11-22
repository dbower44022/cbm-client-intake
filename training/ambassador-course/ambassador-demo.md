# The Ambassador Program — demo

Last Updated: 11-21-26 22:59 · Revision 0.1 — see change log at the end.

A hands-on tour of the Ambassador Program for test users. You play both parts: first a member logging three activities, then the program team answering one of them. It runs on the Business Mentors Association's training system and takes about 25 minutes. What the program is for is in *The Ambassador Program — how it works*; the screens are explained in *The Ambassador Program — user guide*.

**Status.** Draft (decision AM10, Doug 11-21-26), not yet run end to end by a test user.

Every value to type is in its own box. Copy it and paste it rather than typing.

## Before you start

**Once, by an administrator** (in **System Settings** on the training system, the Settings tab), check that **Ambassador Program** and **Training courses** read On, and that **Training sign-ins** holds an entry for the role *Ambassador program team*.

**Each test user needs:**

- Chrome, with private windows allowed.
- **Keep this course page in a normal window, and do every exercise in a private window.** A browser holds one sign-in per site in its normal windows and another in its private windows. The training system is the same site as this course, so signing in to an exercise in the window that holds the course would sign the course out of your name.
- **Your initials**, two letters such as DB. You add them to every name you make up, so two test users' records never mix.
- Two training sign-ins. The course page in the application fills them in below; a page made from this file names them only, because it is public, so ask the trainer.
  - **Mentor** login (Joe Mentor): {{signin:Mentor}}
  - **Ambassador program team** login (Mark Marketing): {{signin:Ambassador program team}}
- About 25 minutes. Your reports stay on the training system, credited to Joe Mentor, until it is next restored.

## 1. A member logs a shared post

### 1.1 Open the activity page

- **Where:** Chrome, a new private window (Ctrl+Shift+N), the address bar.
- **Action:** paste the address below and press Enter.

```
{{training_url}}/ambassador/
```

- **You should see:** the page *Ambassador Activity* with a sign-in box titled *Sign in to log an activity*, on the page itself.
- **If not:** stop and tell the trainer what the page shows.
- **What it does:** this is the page a member bookmarks on a phone; it signs them in where they are.

### 1.2 Sign in as the member

- **Where:** the sign-in box on the *Ambassador Activity* page.
- **Action:** type the **Mentor** login's username and password from *Before you start*, then press **Sign in**.
- **You should see:** the form: *When did you do it?* with today's date, six activity buttons, and *My activity* further down.
- **If not:** stop and tell the trainer the message under the password box.
- **What it does:** the report will be credited to Joe Mentor, because the sign-in says who he is: the form never asks.

### 1.3 Choose the activity

- **Where:** the form, *What did you do?*
- **Action:** click the first button, *I liked or shared a {{abbr}} post*.
- **You should see:** that button turns blue, and no boxes for a contact appear.
- **If not:** stop and tell the trainer.
- **What it does:** sharing a post has no contact to record.

### 1.4 Answer the follow-up question

- **Where:** the form, *Does {{abbr}} need to follow up?*
- **Action:** click **No**.
- **You should see:** **No** turns blue.
- **If not:** stop and tell the trainer.
- **What it does:** every report answers it; only a Yes reaches the program team.

### 1.5 Save the report

- **Where:** the bottom of the form.
- **Action:** click **Save my report**.
- **You should see:** *Thank you*, the line *Thanks for helping more people discover {{org}}. Your report was saved.*, and a reference such as AMB-7K2M9QXA. *My activity* lists the report at the top.
- **If not:** stop and tell the trainer the words of the red message.
- **What it does:** the report is saved at once, then recorded in the CRM.

**Checkpoint:** type the reference shown on the *Thank you* panel.

## 2. A member meets someone we already know

### 2.1 Start a second report

- **Where:** the *Thank you* panel.
- **Action:** click **Log another activity**, then click *I made a community introduction*.
- **You should see:** boxes appear under *Who did you talk to? (optional)*: Email address, First name, Last name, Organization, Title, Phone.
- **If not:** stop and tell the trainer.
- **What it does:** a community introduction may name a person.

### 2.2 Type the person's email address

- **Where:** *Who did you talk to?*, the box **Email address**.
- **Action:** paste the address below, then press Tab.

```
trish.callahan@bma.test
```

- **You should see:** First name *Trish*, Last name *Callahan* and her organization fill in, tinted blue, with the line *From our records.* and **Not this person**. *This person is…* answers itself: *From an organization we already work with*.
- **If not:** stop and tell the trainer what filled in.
- **What it does:** the form fills in only what a member could already see in the directories, and never says whether someone is a client.

### 2.3 Answer the follow-up question

- **Where:** the form, *Does {{abbr}} need to follow up?*
- **Action:** click **No**.
- **You should see:** **No** turns blue.
- **If not:** stop and tell the trainer.
- **What it does:** this report needs nothing from the program team.

### 2.4 Write a note

- **Where:** the box under *Anything we should know?*
- **Action:** paste the text below.

```
Met at the chamber mixer.
```

- **You should see:** the box holds the text.
- **If not:** stop and tell the trainer.
- **What it does:** the note goes with the report to Trish's partner record.

### 2.5 Save the report

- **Where:** the bottom of the form.
- **Action:** click **Save my report**.
- **You should see:** the same *Thank you* as before. It says nothing about where Trish was found.
- **If not:** stop and tell the trainer the words of the red message.
- **What it does:** Trish's partner record gains an *Ambassador Contact* session, and its manager is told. The thank-you is the same for every report, so the form cannot reveal who is a client.

**Checkpoint:** type the name of the organization that filled in for Trish Callahan.

## 3. A member refers someone and asks for help

### 3.1 Start a referral

- **Where:** the *Thank you* panel.
- **Action:** click **Log another activity**, then click *I referred someone to {{abbr}}*.
- **You should see:** the boxes appear under *Who did you refer?*
- **If not:** stop and tell the trainer.
- **What it does:** a referral must name a person.

### 3.2 Type the referred person's email address

- **Where:** *Who did you refer?*, the box **Email address**.
- **Action:** paste the address below, then replace **xx** with your initials, then press Tab.

```
sam.xx@harborbakery.example.com
```

- **You should see:** nothing fills in: the CRM does not know this person.
- **If not:** if a name fills in, someone used your initials; change them and press Tab again.
- **What it does:** an address the CRM does not know will become a new person. An `example.com` address never receives mail.

### 3.3 Type the referred person's name and business

- **Where:** *Who did you refer?*, the boxes **First name**, **Last name** and **Organization**.
- **Action:** paste each value below into its box. In Last name and Organization, replace **XX** with your initials.

First name:

```
Sam
```

Last name:

```
Baker XX
```

Organization:

```
Harbor Bakery XX
```

- **You should see:** the three boxes hold the values.
- **If not:** stop and tell the trainer.
- **What it does:** the person and the business are created from these.

### 3.4 Say who the person is

- **Where:** the form, *This person is…*, then *Did they agree to hear from {{abbr}}?*
- **Action:** click **A potential client**, then click **Yes**.
- **You should see:** both turn blue.
- **If not:** stop and tell the trainer.
- **What it does:** a potential client is created as a prospect credited to Joe Mentor; Yes adds them to the marketing list.

### 3.5 Ask for follow-up

- **Where:** the form, *Does {{abbr}} need to follow up?*
- **Action:** click **Yes**.
- **You should see:** **Yes** turns blue, and the hint under *Anything we should know?* asks what help you need.
- **If not:** stop and tell the trainer.
- **What it does:** the program team is emailed and the request goes on their review list.

### 3.6 Say what help is needed

- **Where:** the box under *Anything we should know?*
- **Action:** paste the text below.

```
Wants help with the lease for a second shop.
```

- **You should see:** the box holds the text.
- **If not:** stop and tell the trainer.
- **What it does:** a follow-up request must say what is needed.

### 3.7 Save the referral

- **Where:** the bottom of the form.
- **Action:** click **Save my report**.
- **You should see:** *Thank you*, plus *You asked for follow-up: the program team will review it.*
- **If not:** stop and tell the trainer the words of the red message.
- **What it does:** Sam is created, credited to Joe Mentor, and the program team is alerted.

### 3.8 Correct the first report

- **Where:** *My activity*, the row *I liked or shared a {{abbr}} post* with today's date.
- **Action:** click **Correct**, choose *I identified a success story* in the **Activity** list, then click **Save correction**.
- **You should see:** the dialog closes and that row's Activity reads *I identified a success story*.
- **If not:** stop and tell the trainer the words of the red message.
- **What it does:** a member may correct the date, activity and note of a report for 14 days.

### 3.9 Sign the member out

- **Where:** the top of the *Ambassador Activity* page.
- **Action:** click **Sign out**.
- **You should see:** the sign-in box again.
- **If not:** stop and tell the trainer.
- **What it does:** section 4 signs in as the program team in this same private window.

**Checkpoint:** type what the *Referral* column of *My activity* said for Sam Baker before you signed out.

## 4. The program team answers

### 4.1 Open the review list

- **Where:** the same private window, the address bar.
- **Action:** paste the address below and press Enter.

```
{{training_url}}/ambassador/review/
```

- **You should see:** a sign-in box titled *Sign in to the review list*.
- **If not:** stop and tell the trainer what the page shows.
- **What it does:** this is the program team's list.

### 4.2 Sign in as the program team

- **Where:** the sign-in box on the review page.
- **Action:** type the **Ambassador program team** login's username and password from *Before you start*, then press **Sign in**.
- **You should see:** *Ambassador Review*, a count of items to review, and a list. Your row reads *Sam Baker XX* with your initials, marked *Follow-up*. Other test users' rows may be there too.
- **If not:** stop and tell the trainer what the page shows.
- **What it does:** the program team sees every member's open requests.

### 4.3 Open your row

- **Where:** the review list.
- **Action:** click the row for *Sam Baker* with your initials.
- **You should see:** the report in full, with a *Follow-up* section and the box *What was done*.
- **If not:** stop and tell the trainer.
- **What it does:** the full report is what the program team acts on.

### 4.4 Mark the follow-up done

- **Where:** the *Follow-up* section, the box *What was done*.
- **Action:** paste the text below, then click **Mark follow-up done**.

```
Called Sam; a lease review with a mentor is booked.
```

- **You should see:** *Marked done. The ambassador has been told.*, then the list again without your row.
- **If not:** stop and tell the trainer the words of the red message.
- **What it does:** the request is closed with a note, and the member is emailed the note.

### 4.5 Read the figures

- **Where:** the same private window, the address bar.
- **Action:** paste the address below, press Enter, click *Ambassador Program* among the page buttons, then click the page's own **Refresh** button.

```
{{training_url}}/analytics/
```

- **You should see:** *Active ambassadors* at 1 or more, *Activities reported* counting every test user's reports, and *Activities by type* with a bar for *Referred someone*.
- **If not:** stop and tell the trainer what the panels say.
- **What it does:** this is how the program team sees the program's reach. Figures are kept for an hour; **Refresh** works them out again.

### 4.6 Sign the program team out

- **Where:** the top right of the *Analytics* page.
- **Action:** click **Sign out**.
- **You should see:** the sign-in page.
- **If not:** stop and tell the trainer.
- **What it does:** section 5 signs in as the member again.

**Checkpoint:** type the number shown under *Activities reported* after you pressed Refresh.

## 5. The member sees the answer

### 5.1 Sign in as the member again

- **Where:** the same private window, the address bar.
- **Action:** paste the address below, press Enter, then sign in with the **Mentor** login from *Before you start*.

```
{{training_url}}/ambassador/
```

- **You should see:** the form, and *My activity* below it.
- **If not:** stop and tell the trainer.
- **What it does:** the member's own list shows what happened to each report.

### 5.2 Read your referral's row

- **Where:** *My activity*, the row for *Sam Baker* with your initials.
- **Action:** read its *Follow-up* column.
- **You should see:** *Done*. Pointing at it shows the program team's note.
- **If not:** stop and tell the trainer what the row says.
- **What it does:** the member sees that the request was handled.

### 5.3 Sign out and close the private window

- **Where:** the top of the *Ambassador Activity* page.
- **Action:** click **Sign out**, then close the private window.
- **You should see:** this course page, still signed in as you, in the normal window.
- **If not:** stop and tell the trainer.
- **What it does:** leaves the training sign-ins for the next test user.

**Checkpoint:** type what the *Follow-up* column said for Sam Baker.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 22:59 | Claude (Claude Code) | Created (decisions AM8 and AM10, Doug 11-21-26): a member's three reports and a correction, the program team's follow-up and figures, and the member reading the answer. Draft. |
