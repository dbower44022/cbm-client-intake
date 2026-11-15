# Phase 9, stopping point 4 — the other seven integrations' wizard screens for review

Last Updated: 11-15-26 11:23 · Revision 0.2 — see change log at the end.

**Approved by Doug 11-15-26 and built as v0.334.0.** The wizard rulings are W1 to
W6 (`prds/integrations-tab-plan.md` § 10). Google Workspace's screens are in
`prompts/integrations-tab-phase9-google-review.md`; Doug chose its scope B on
11-15-26: **the wizard covers what the application connects to, and the guide
alone covers work done before the application exists.** The same rule is
applied here. It affects only EspoCRM: its server build (guide steps 9.3 to
9.5, CRMBuilder) gets no screens.

Each screen gives its type and check in brackets. "Done" means the person
clicks Done. A check written `test:x/y` runs integration x's test and reads
its line y. Every vendor-account screen says where the password goes (the
chapter's Operations vault) and that the vendor's screen wording has not been
checked, as the guide does.

## What these screens need that does not exist yet

**Decided unless Doug objects:**

1. **A copy value may name this deployment's address.** Constant Contact's
   redirect address, Lob's webhook address and Twilio's reply address all
   start with the applications' own web address. A copy value written
   `{APP_BASE_URL}/api/…` is filled in from the setting when the screen is
   drawn. That way the person copies the real address, not a placeholder.
2. **A screen kind for Constant Contact's Connect** (`connect: mailing`). It
   shows the existing Connect button. Constant Contact's sign-in page returns
   to System Settings, and the wizard resumes on that screen and checks the
   connection.
3. **The `runs:` screen kind** proposed for Google's shared drive also serves
   Twilio's Look up the sender number.

No new check kind is needed: every screen below is checked by a line the
integration tests already have.

## EspoCRM — 9 screens, from steps 8.5, 9.7 and 9.9

No "in use" question: EspoCRM is always in use. Signing in to this page
already needs the CRM address and key, so on a working system the wizard
starts past screen 2. It serves repair.

1. **The CRM's address** *(box: CRM address; check: set)* — how: the address chosen in step 3.2, beginning https://. Why: every read and write goes there. A wrong one is refused before it is stored, as today.
2. **The applications' CRM key** *(box, secret: CRM API key; check: `test:espocrm/sign_in`)* — how: from the vault item CRM key for the applications (step 9.7). If not: the CRM refused the key; check the API user is active in the CRM.
3. **The CRM matches the standard** *(Done; check: `test:espocrm/conformance`)* — what: the entities, fields, teams and email templates the applications use. If not: the missing items are named; step 9.7's script applies them.
4. **The applications can read every record type** *(Done; check: `test:espocrm/read_access`)* — if not: a role grant was missed in stage 9; the line names the record type.
5. **The forms' lists match the CRM** *(Done; check: `test:espocrm/enums`)* — if not: a list option the CRM lacks; it is dropped on save until the lists are synced.
6. **Will the applications create mentors' CRM logins?** *(question)* — why: EspoCRM lets only an administrator create a login, so the applications use a separate provisioning account. Yes goes to screen 7. No goes to screen 9.
7. **The provisioning account's name** *(box: Provisioning admin username; check: set)* — how: from the vault item CRM provisioning administrator (step 9.7).
8. **The provisioning account's password** *(box, secret; check: `test:espocrm/provisioning`)*.
9. **The whole EspoCRM test** *(Done; check: `test:espocrm`)*.

## Fathom — 7 screens, from step 5.13

1. **Will mentors record their sessions with Fathom?** *(question; sets Fathom in use; No ends)* — why: Fathom's recordings give each session a transcript and action items without the mentor typing them.
2. **Does the chapter already have a Fathom team account?** *(question)* — Yes goes to screen 5.
3. **Create the Fathom team account** *(Done)* — how: at https://fathom.video, sign up with admin@ on the chapter's domain.
4. **Share every recording with the team** *(Done)* — why: a recording that is not shared never reaches the applications.
5. **Create the API key** *(Done)* — how: in Fathom's settings, the API access page. Copy the key straight into the vault item Fathom.
6. **Paste the API key** *(box, secret: Fathom API key; check: `test:fathom/meetings`)* — if not: Fathom refused the key, or it has no team recordings to read yet.
7. **Turn on Fathom transcripts?** *(question; Yes sets Fathom transcripts on; check: `test:fathom`)*.

## Constant Contact — 12 screens, from steps 5.11 and 11.19

1. **Will the chapter send mailings through Constant Contact?** *(question; sets Constant Contact in use; No ends)* — why: the chapter's mailing list is kept in step with the CRM, and campaign emails go through it.
2. **Does the chapter already have the account and its developer application?** *(question)* — Yes goes to screen 8.
3. **Sign up** *(Done)* — how: https://www.constantcontact.com/signup, with admin@ on the chapter's domain. It is a free trial with no card.
4. **Confirm the address and turn on two-step sign-in** *(Done)* — why: Constant Contact refuses to create a developer application until two-step sign-in is on.
5. **Choose the plan** *(Done)* — how: before the trial ends, upgrade to the plan the Association names, with the chapter's own card.
6. **Create the developer application** *(Done)* — how: open https://app.constantcontact.com/pages/dma/portal, click New Application, name it after the chapter, tick Authorization Code Flow and Implicit Flow, tick Rotating Refresh Tokens, click Create.
7. **Set its redirect address** *(Done; the address with a Copy button, filled in from this deployment)* — how: click Edit beside the application, click the pencil beside Redirect URI, replace https://localhost with the address below, Confirm, then Save. Copy: `{APP_BASE_URL}/api/setup/mailing/callback`.
8. **Paste the API key** *(box: Mailing service client ID; check: set)* — how: the API Key (Client Id) on the application's Edit page.
9. **Paste the client secret** *(box, secret: Mailing service client secret; check: set)* — how: click Generate Client Secret, copy it into the vault first, then here. It is shown only once.
10. **Connect** *(Connect button; check: `test:constant_contact/connection`)* — how: click Connect, sign in to Constant Contact as admin@, allow the access it asks for. You come back to this screen.
11. **Check the list and the lead-code field** *(Done; check: `test:constant_contact/list` and `test:constant_contact/field`, both)* — what: the named list (Mailing list name, shown) and the field that carries a lead code. If not: the line says which is missing.
12. **Turn on list sync?** *(question; Yes sets Mailing list sync on; check: `test:constant_contact`)*.

## Lob — 11 screens, from steps 5.14 and 11.20

1. **Will the chapter send postcards?** *(question; sets Lob in use; No ends)*.
2. **Does the chapter already have a Lob account?** *(question)* — Yes goes to screen 4.
3. **Sign up for Lob** *(Done)* — how: https://dashboard.lob.com with admin@ on the chapter's domain; turn on two-step sign-in.
4. **Copy both keys into the vault** *(Done)* — how: in Lob's settings, the API keys page. Copy the test key (begins test_) and the live key (begins live_).
5. **Paste the test key** *(box, secret: Mail vendor API key; check: `test:lob/postcards`)* — why: test mode first; nothing is printed or charged. Mail vendor test mode stays on and is shown on the screen.
6. **Create the delivery webhook** *(Done; the address with a Copy button, filled in from this deployment)* — how: in Lob's webhooks page, create a webhook to the address below, for the delivered and returned-to-sender postcard events. Copy: `{APP_BASE_URL}/api/campaigns/postal/events`.
7. **Paste the webhook secret** *(box, secret: Mail vendor webhook secret; check: `test:lob/webhook`)*.
8. **Make Lob the mail vendor?** *(question; Yes sets Mail vendor to lob; check: `test:lob`)* — why: until then postcards are only simulated.
9. **Send real postcards now?** *(question)* — why: in test mode nothing is printed. Going live costs money per card. Yes goes to screen 10. Not yet ends here; the wizard can be opened again later.
10. **Add the chapter's card to Lob** *(Done; only after Yes)*.
11. **Paste the live key** *(box, secret: Mail vendor API key; only after Yes; check: `test:lob/mode`)* — Saving also sets Mail vendor test mode off. If not: the key does not begin live_.

## Twilio — 15 screens, from steps 5.15, 5.16 and 11.21

1. **Will the chapter send text messages?** *(question; sets Twilio in use; No ends)*.
2. **Does the chapter already have a Twilio account with a number?** *(question)* — Yes goes to screen 6.
3. **Sign up for Twilio** *(Done)* — how: https://www.twilio.com/try-twilio with admin@; turn on two-step sign-in.
4. **Upgrade from trial** *(Done)* — why: a trial account can text only numbers it has verified.
5. **Buy a number** *(Done)* — how: a local United States number that can send SMS.
6. **Paste the Account SID** *(box: Texting account SID; check: set)* — how: from the console's Account Info panel; it begins AC.
7. **Paste the Auth Token** *(box, secret: Texting auth token; check: `test:twilio/account`)* — if not: the test credentials were copied; use the live Auth Token.
8. **Look up the sender number** *(button Look up the sender number, the phase 7 coded action; check: Texting sender number set)* — if not: the account has several numbers; type the one to use on the next screen.
9. **Confirm the sender number** *(box: Texting sender number; check: `test:twilio/number`)* — how: in the form +12165550123.
10. **Register the chapter as a brand** *(Done)* — what: carrier registration (A2P 10DLC), which US carriers require before they deliver business texts. How: in Twilio's console, the A2P 10DLC pages; the chapter's legal name and its employer identification number.
11. **Register the campaign** *(Done)* — how: one campaign describing the texts: invitations and reminders to people who asked for them, each saying to reply STOP to stop.
12. **Attach the number to the campaign** *(Done)* — see: the campaign approved. Twilio may take days or weeks; the wizard keeps its place.
13. **Send replies to the applications** *(Done; the address with a Copy button, filled in from this deployment)* — how: on the number's messaging settings, set A message comes in to the address below, HTTP POST. Copy: `{APP_BASE_URL}/api/campaigns/sms/inbound`.
14. **Check the sending hours** *(Done; check: `test:twilio/hours`)* — what: Texting hours and Texting time zone, shown on the screen. Why: no text is sent outside them.
15. **Make Twilio the texting service?** *(question; Yes sets Texting service to twilio; check: `test:twilio`)*.

## Anthropic — 8 screens, from step 5.17

1. **Will the chapter use the AI features?** *(question; sets Anthropic in use; No ends)* — what: summaries of email conversations, AI research on leads, and Ask Claude in this wizard.
2. **Does the chapter already have an Anthropic organization?** *(question)* — Yes goes to screen 5.
3. **Create the organization** *(Done)* — how: https://platform.claude.com with admin@.
4. **Add the card and a monthly spending limit** *(Done)* — why: the limit is the board's ceiling on what Anthropic can charge.
5. **Create the API key** *(Done)* — how: named after the chapter's applications; copy it straight into the vault. It is shown only once.
6. **Paste the API key** *(box, secret: Anthropic API key; check: `test:anthropic/configured`)* — what the check proves: the key works and every model the settings name exists.
7. **Turn on AI conversation summaries?** *(question; Yes sets AI conversation summaries on; check: `test:anthropic`)*.
8. **Turn on AI research on leads?** *(question; Yes sets AI research on; check: `test:anthropic`)* — the research's monthly budget is shown on the screen.

## YouTube — 6 screens, from step 10.6

1. **Does the chapter have recorded webinars on YouTube to bring in?** *(question; sets YouTube in use; No ends)*.
2. **Switch on the YouTube service** *(Done)* — how: in the Google Cloud project from step 10.1, APIs and services, Library, YouTube Data API v3, Enable.
3. **Create an API key** *(Done)* — how: APIs and services, Credentials, Create credentials, API key.
4. **Limit the key to YouTube** *(Done)* — how: edit the key; under API restrictions allow only YouTube Data API v3. Copy it into the vault.
5. **Paste the API key** *(box, secret: YouTube API key; check: set)*.
6. **Name the playlists** *(box: YouTube playlists; check: `test:youtube/playlists`)* — how: for each playlist, the part of its web address after list=, separated by commas. If not: the line names each playlist YouTube does not find.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-15-26 11:23 | Claude (Claude Code) | Approved by Doug; built as v0.334.0. |
| 0.1 | 11-15-26 11:15 | Claude (Claude Code) | Draft for phase 9 stopping point 4. |
