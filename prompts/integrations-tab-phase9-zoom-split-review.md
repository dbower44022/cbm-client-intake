# Phase 9, stopping point 1 — the Zoom split for review

Last Updated: 11-15-26 02:50 · Revision 0.2 — see change log at the end.

**Approved by Doug 11-15-26 (option A) and built as v0.333.0.** The rulings are EH1, EH5 to
EH8 and EH11 (`prds/events/event-hosting-plan.md`); the wizard rulings are W1
to W6 (`prds/integrations-tab-plan.md` § 10).

## 1. The settings

Existing keys are kept and relabelled for Zoom Webinars, so no chapter's
stored value is stranded.

**Zoom Webinars (the existing `zoom` integration, renamed).**

- `zoom_in_use` — "Zoom Webinars in use" (was "Zoom in use").
- `zoom_events` — "Zoom webinar provisioning" (unchanged).
- `zoom_account_id` — "Zoom Webinars account ID (separate account only)".
- `zoom_client_id` — "Zoom Webinars client ID (separate account only)".
- `zoom_client_secret` — "Zoom Webinars client secret (separate account only)", secret.
- `zoom_host_email` — "Zoom Webinars host (separate account only)". Its
  default stays Cleveland's `zweb@cbmentors.org`.
- **New** `zoom_webinars_same_account` — "Zoom Webinars on the same account as
  Zoom Meetings", Yes/No, default Yes (EH7).

**Zoom Meetings (a new integration, key `zoom_meetings`).**

- `zoom_meetings_in_use` — "Zoom Meetings in use", default Yes, like every
  other "in use" setting.
- `zoom_meetings_events` — "Zoom meeting provisioning", default off. **Not in
  the prompt's list of five; added because it is needed.** It is the switch
  the Events side reads before creating a meeting, the switch the "in use"
  refusals count, and what puts Zoom Meetings in the nightly test. It is the
  twin of `zoom_events`.
- `zoom_meetings_account_id` — "Zoom Meetings account ID".
- `zoom_meetings_client_id` — "Zoom Meetings client ID".
- `zoom_meetings_client_secret` — "Zoom Meetings client secret", secret,
  stored encrypted.
- `zoom_event_host_email` — "Event host user" (EH8), empty by default. Every
  Zoom event is created under this user, webinars too when Zoom Webinars is
  on the same account.
- `zoom_meetings_capacity` — "Zoom Meetings capacity limit", a whole number,
  default 100 (EH6).

**Events (Settings tab, Features group, beside the confirmation emails).**

- `events_default_method_public` — "Default hosting method, public events".
- `events_default_method_members` — "Default hosting method, members-only events".

Each offers four choices. The stored values are the CRM's; the page shows
the names in brackets: `CBM Zoom` (Zoom Webinars), `Zoom Meetings`,
`Other platform`, `Outside host`. Both default to `CBM Zoom`, today's
behaviour. The settings page does not show choice labels today; it gains
them. Both are listed under each Zoom integration's "Used by", for
information only: a default naming an integration that is not in use is not
refused here. The event form will show the method as "Not set up" (EH4).

**One rule chooses the webinar credentials**, kept in one helper
(`core/zoom.py`) that the test, the wizard and the Events side all call.
Zoom Webinars uses Zoom Meetings' account, app and event host user when
"same account" is Yes **and** all three Zoom Meetings credentials are set.
Otherwise it uses its own four settings. The "otherwise" protects Cleveland's
production. It holds Webinars credentials today and no Meetings ones, and a
plain "Yes" default would move its webinars to an empty account.

## 2. Zoom Meetings' test

In order:

1. **Settings present.** The account ID, client ID, client secret and event
   host user are set.
2. **Token by Server-to-Server OAuth.** Fact: the scopes on the token.
3. **The meeting scopes.** All eleven are on the token:
   `user:read:user:admin` plus the ten in plan § 3. Failed names each one
   missing. Unknown if Zoom does not report the token's scopes. Any later
   refusal carrying Zoom's code 4711 shows Zoom's own words ("does not
   contain scopes:[…]").
4. **The event host user.** `GET /users/{host}`. Must be Licensed (`type`
   2). Failed for Basic: "a Basic user cannot take registrations". Facts:
   the host, its licence type, the account number.
5. **Co-host.** `GET /users/{host}/settings` → `in_meeting.co_host`. Off
   fails: "turn on Co-host, or a co-presenter cannot share their screen
   (EH11)". Unknown when Zoom does not report it. Fact: the meeting capacity
   (`feature.meeting_capacity`) beside the capacity limit setting, for
   example "Zoom 100 · limit setting 100".
6. **The host's meetings.** `GET /users/{host}/meetings?type=upcoming`.
   Fact: how many are scheduled.
7. **Attendance report.** The participant report of the latest past meeting.
   **No past meeting is skipped**, not unknown ("can be read after the first
   meeting"). Otherwise a new account could never pass the whole test, and
   the wizard's last screen could never be done. **Zoom Webinars' attendance
   check gets the same change** (it reads unknown today).

Zoom Webinars' test is unchanged, except that it reads the credentials
through the rule in § 1.

**Feature readiness.** The "Zoom webinars" row reads the effective
credentials. A new "Zoom meetings" row has flag `zoom_meetings_events` and
needs the four Meetings settings. **The nightly test** covers Zoom Meetings
once `zoom_meetings_events` is on.

## 3. The guide

Step 5.5 is split in two. **Step 5.5** becomes Zoom Meetings: the chapter's
Zoom account, the events@ host and the app with the eleven scopes. A new
**step 5.18** covers Zoom Webinars: the add-on, on the same account or a
separate one, with `first: ["5.5"]`. No step is renumbered. Step 5.6
(two-step sign-in) changes "webinars@" to "events@". Each step carries its
own integration's screens; no engine change is needed.

## 4. Zoom Meetings' screens, as Doug will see them

**1. Does this chapter hold online events on Zoom Meetings?** *(question)*
- What: Zoom Meetings with registration. Each registrant gets a personal join link, and attendance is read from Zoom afterwards, as with webinars.
- Why: It costs a Zoom Pro user, about $14 to $17 a month, against $67 to $89 more for Webinars, and holds about 100 people on Pro. Mentoring sessions never use this account; each mentor uses their own meeting link.
- Yes sets Zoom Meetings in use, then next. No sets it not in use, and the wizard ends.
- Check: answered.

**2. Does the chapter already have a Zoom account with a Server-to-Server OAuth app?** *(question)*
- What: A paid Zoom account, and an app on it through which this application signs in.
- Why: If both exist, the app only needs the meeting scopes added before its three values are copied here.
- Yes goes to screen 8 (the scopes). No goes to the next screen.

**3. Create the event host mailbox** *(Done)*
- What: A licensed Google Workspace user named events@ on the chapter's email domain.
- Why: Every Zoom event is created under this user. Zoom sends its host mail there, and the account belongs to the chapter rather than to a volunteer.
- How: In the Google Admin console, open Directory, then Users, then Add new user. Use Events as the last name, and events@ followed by the chapter's email domain as the primary email.
- See: The new user in the Users list, with a licence.
- If not: Stop and ask the Association.

**4. Sign up for Zoom** *(Done)*
- What: The chapter's own Zoom account, signed up with the events@ address.
- Why: The event host and the app both live on this account.
- How: In a browser, go to https://zoom.us/signup and sign up with the events@ address. Put the password in the chapter's Operations vault.
- See: Zoom's welcome page, signed in as the events@ address.
- If not: Stop and ask the Association.

**5. Buy a Zoom Pro plan** *(Done)*
- What: A paid licence for the events@ user.
- Why: A Basic (free) user cannot take registrations. Screen 14 checks the licence.
- How: In Zoom's web portal, open Plans and Billing and buy Pro (or larger) for the events@ user. The exact wording of Zoom's billing screens has not been checked for this guide.
- See: The events@ user listed as Licensed.
- If not: Stop and ask the Association which plan to buy.

**6. Create the Server-to-Server OAuth app** *(Done)*
- What: The app this application signs in to Zoom through.
- Why: Zoom gives an application its access only through an app like this.
- How: Signed in to Zoom as the events@ user, go to https://marketplace.zoom.us/user/build. Accept Zoom's terms if asked. Click the plus button beside Developer, then Build app, choose Server to server OAuth app, and click Create. Name it after the chapter, for example Akron Business Mentors Events.
- See: The app's App Credentials page, with Account ID, Client ID and Client Secret, each with a Copy button.
- If not: Stop and ask the Association.

**7. Fill in the app's information page** *(Done)*
- What: The short description, the company name and the developer contact Zoom asks for.
- Why: Zoom will not activate an app without them.
- How: On the app's Information page, fill in Short Description, Company Name (the chapter's name), and the developer contact's Name and Email (info@ followed by the chapter's email domain). The page saves by itself.
- See: No field on the Information page marked as missing.
- If not: Stop and tell the Association which field Zoom marks.

**8. Add the meeting scopes** *(Done; each scope with a Copy button)*
- What: The permissions the application uses in Zoom Meetings.
- Why: Each one lets the application do one thing, such as create a meeting, register someone or read who attended. Screen 13 reports any that are missing.
- How: On the app's Scopes page, click Add Scopes, then search for each scope below by name and tick it. The search box on the Scopes page itself searches only the scopes already added; use the one inside Add Scopes.
- Copy: `user:read:user:admin`, `user:read:settings:admin`, `meeting:read:list_meetings:admin`, `meeting:read:meeting:admin`, `meeting:write:meeting:admin`, `meeting:update:meeting:admin`, `meeting:delete:meeting:admin`, `meeting:write:registrant:admin`, `meeting:read:list_registrants:admin`, `meeting:update:registrant_status:admin`, `report:read:list_meeting_participants:admin`.
- See: All eleven listed on the Scopes page.
- If not: If a scope is not offered, stop and tell the Association its name.

**9. Activate the app** *(Done)*
- What: Switching the app on for the account.
- Why: An app that is not activated cannot issue a token.
- How: On the app's Activation page, click Activate your app. (An existing app that is already active only needs the scopes saved.)
- See: The message Your app is activated on the account.
- If not: Zoom names what is missing on the Activation page. Fix it and click Activate your app again.

**10. Paste the Account ID** *(box: Zoom Meetings account ID; check: set)*
- How: On the app's App Credentials page, click Copy beside Account ID, paste it in the box below, and click Save.

**11. Paste the Client ID** *(box: Zoom Meetings client ID; check: set)*
- How: As screen 10, with Client ID.

**12. Paste the client secret** *(box, secret; check: the token)*
- How: Click Copy beside Client Secret, paste it below, and click Save. Also put it in the chapter's Operations vault, and nowhere else.
- If not: Zoom refused the three values together. Copy all three again from the same app; the client secret changes if it was regenerated.

**13. Check the scopes** *(Done; check: the meeting scopes)*
- What: Whether the app holds all eleven scopes.
- Why: A missing scope only shows when the application first tries that action, perhaps on the day of an event.
- How: Click Done. The application reads the scopes from Zoom.
- If not: The scopes named above are missing. Add them as on screen 8 and click Done again.

**14. Confirm the event host user** *(box: Event host user; check: the host)*
- What: The Zoom user every Zoom event is created under, normally the events@ address.
- Why: Only a Licensed user can take registrations. Someone signed in as this user starts each meeting (EH11).
- How: Type the address in the box below and click Save.
- If not: Zoom has no such Licensed user on this account. Use the address you signed up with, and check it is on a paid plan.

**15. Turn on co-host** *(Done; check: co-host)*
- What: Zoom's Co-host setting, on the chapter's account.
- Why: Only the host shares the screen in the chapter's meetings (EH11). A co-presenter shares by being made co-host during the meeting, which needs this setting on.
- How: Signed in to Zoom as the events@ user, open Settings, then the Meeting tab, then In Meeting (Basic). Switch Co-host on, then click Done here. The exact wording of Zoom's settings screen has not been checked for this guide.
- If not: The setting may be locked by the account owner. Sign in as the owner and switch it on there.

**16. Confirm the capacity limit** *(box: Zoom Meetings capacity limit; check: set)*
- What: The largest event the application will put on Zoom Meetings.
- Why: A fully online event with a larger capacity is refused for Zoom Meetings, with the reason (EH6). Zoom reports the account's own limit, shown below.
- How: Check the number against the capacity Zoom reports, change it if the chapter's plan is larger, and click Save.

**17. Use Zoom Meetings by default for…** *(question)*
- What: Which events start on Zoom Meetings when staff create them. Staff can still choose another method per event.
- Why: A sensible default means staff rarely choose, and a chapter with both Zoom products does not set up a meeting by accident when it meant a webinar (EH5).
- Answers: "Members-only events" (sets the members-only default), "All events" (sets both), "Neither".
- Check: answered.

**18. Turn Zoom Meetings on?** *(question; check: the whole test)*
- What: The switch that lets the Events application create Zoom meetings.
- Why: Until it is on, nothing in the Events application uses Zoom Meetings, even with everything set up.
- Answers: Yes (sets Zoom meeting provisioning on), Not yet.

## 5. Zoom Webinars' screens, as Doug will see them

The pilot's 14 screens, reworded, and one new screen (2). Screens marked
*separate account* appear only when screen 2 is answered No.

**1. Does this chapter run public webinars on Zoom Webinars?** *(question)*
- What: Zoom Webinars, a paid add-on for large public events where attendees watch and cannot speak or show video.
- Why: It costs about $67 to $89 a month on top of a Zoom plan. Most chapters can hold their events on Zoom Meetings instead. Mentoring sessions never use this account.
- Yes sets Zoom Webinars in use. No sets it not in use, and the wizard ends.

**2. Is Zoom Webinars on the same Zoom account as Zoom Meetings?** *(question, new, EH7)*
- What: Whether the Webinars add-on is bought on the account set up for Zoom Meetings, or on an account of its own.
- Why: On the same account, Zoom Webinars uses Zoom Meetings' app and event host user, so nothing needs copying twice. Answer No if the chapter does not use Zoom Meetings.
- Yes sets "same account" Yes, then screen 5. No sets it No, then next.
- Check: answered.

**3. Does the chapter already have its Zoom account and app?** *(question, separate account)*
- Unchanged, except Yes goes to the Account ID screen.

**4. Create the webinar host mailbox** *(Done, separate account)* — unchanged (webinars@).

**5. Sign up for Zoom** *(Done, separate account)* — unchanged.

**6. Buy the Webinars licence** *(Done; two screens, one per answer to screen 2)*
- How (same account): In Zoom's web portal, open Plans and Billing, buy the Zoom Webinars add-on, and assign it to the event host user. How (separate account): as today, to the webinars@ user. Only the text for the answer given is shown.
- Why: Zoom offers the webinar scopes only to an account holding a Webinars licence. The last screen checks it.

**7. Create the Server-to-Server OAuth app** *(Done, separate account)* — unchanged.

**8. Fill in the app's information page** *(Done, separate account)* — unchanged.

**9. Add the webinar scopes** *(Done; the seven scopes with Copy buttons)*
- How: On the app's Scopes page, click Add Scopes and search for each scope below by name. On the same account, this is the app made for Zoom Meetings. The Scopes page's own search box searches only the scopes already added.
- If not: If the webinar scopes are not offered, the account has no Webinars licence yet; go back to screen 6.

**10. Activate the app** *(Done, separate account)* — unchanged.

**11. Paste the Account ID**, **12. Paste the Client ID**, **13. Paste the client secret** *(separate account)* — unchanged; the boxes are the Zoom Webinars settings.

**14. Confirm the webinar host** *(box, separate account; check: the host)* — unchanged.

**15. Turn webinars on?** *(question; check: the whole test)* — unchanged.
- What gains: "On the same account, webinars are created under the event host user."

**Decided unless Doug objects**: screen 6 is built as two screens with
`when:`, one for each answer to screen 2. The engine already supports that,
and it keeps one text per screen. On the same account, Zoom Webinars shows
5 screens (1, 2, 6, 9, 15); on a separate account, 15.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-15-26 02:50 | Claude (Claude Code) | Approved by Doug (option A); built as v0.333.0. Step 5.5's values are entered in the wizard, not on the chapter information form (the guide's information check). |
| 0.1 | 11-15-26 02:25 | Claude (Claude Code) | Draft for phase 9 stopping point 1. |
