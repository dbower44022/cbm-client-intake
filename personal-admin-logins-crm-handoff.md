# CRM handoff — personal administrator logins, and the shared accounts

Last Updated: 11-05-26 11:04 · Revision 1.0 — see change log at the end.

Every administrative action in the CRM should be signed by a person. From
the mentor login integrity plan (`prds/mentor-login-integrity-plan.md`,
§ 4.8; Doug's ruling Q6.3, 11-05-26). This is mostly a people change, so
the deliverable is a checklist, not a script.

## 0. Current state — read this first

Three shared accounts signed in to production's CRM screens in the 60 days
to 11-04-26 (`scripts/crm_signin_report.sh`, run by Doug):

| Account | Direct sign-ins | What it is | Seen doing (Action History, 10-17 to 11-04) |
|---|---|---|---|
| `admin` | 31 | EspoCRM's original administrator | — (none in the window) |
| `admin@cbmentors.org` | 15 | Also the DigitalOcean sign-in (`STAFF-DEPLOYMENT-GUIDE.md`) and the Google Cloud project owner (`GDRIVE-DOCS-SETUP.md`) | Deleted intake submissions and event registrations; viewed users, roles, teams, email templates |
| `mentoradmin@cbmentors.org` | 39 | The application's provisioning service account (Administrator type; `ESPO_PROVISION_USERNAME`); runbooks apply CRM changes as it | Role views and changes, 10-18-26 around 04:40 |

Who uses `admin` and `admin@cbmentors.org` is not known. Boston: not read.

## 1. The checklist (each chapter)

1. **Doug names the people who administer this chapter's CRM.**
2. For each, an Administrator-type login of their own, user name their
   CBM address. If they already have a regular login, Doug decides whether
   to raise that login to Administrator type or keep a separate one; a
   separate one keeps day-to-day work out of administrator power.
3. **`admin`:** change its password; Doug holds it; it is used only in an
   emergency, and each use is noted in the open items.
4. **`admin@cbmentors.org`:** if it is a CRM login, set it inactive in the
   CRM. Its DigitalOcean and Google roles are unaffected. **Do not** change
   the Google account itself.
5. **`mentoradmin@cbmentors.org`:** keep it; the application needs it. Change
   its password only together with the application's `ESPO_PROVISION_*`
   setting (`/setup` or the overlay), or provisioning breaks. Runbooks keep
   using it from inside the container; nobody signs in to the screens with
   it.

**Trap.** Setting `mentoradmin@` inactive, or changing its password alone,
silently breaks mentor provisioning: Mentor Administration reports
"provisioning is disabled" or a sign-in failure only when the next mentor
is approved.

## 2. Check

- The daily digest's shared-account report (plan § 4.2, item 9) shows no
  screen sign-ins by `admin@cbmentors.org` or `mentoradmin@cbmentors.org`
  after the change, and `admin` only when an emergency was noted.
- Approve a test mentor on crm-test: provisioning still creates the login.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the mentor login integrity design session. |
