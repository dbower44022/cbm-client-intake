# Open items to address

Running list of known issues and pending decisions that don't belong to any
single feature doc. Add new items at the top of their section with the date
found; move resolved items to the bottom with the resolution date.

## Needs a fix / decision

0. **Analytics on the record views — two surfaces have nowhere to live**
   (2026-07-27; decisions + full context in `prds/analytics-app-plan.md` §17).
   Doug ruled that a dashboard can be attached to every record view (Mentor,
   Company, Contact, Engagement, Client, Partner, Funder), one dashboard per
   record type. **The five with a host screen shipped in v0.187.0** (Mentor,
   Engagement, Partner, Funder, Contact — each with a starter dashboard). The
   remaining two need a call before they can be built:
   - **Company** — there is no full `Account` page, only the Companies grid,
     its preview strip and a View pop-up. Dashboard inside the pop-up, or build
     a Company record page like the Contact page (v0.144.0)? Recommendation:
     the real page.
   - **Client** — `CClientProfile` has no screen anywhere (only a card on the
     engagement's Details tab and a peek pop-up). Does "client analytics" mean
     the engagement view, the company view, or a new client page?

## Smaller follow-ups from the 2026-07-24 partner migration

2. **Fatherhood Initiative – Cuyahoga County has no partner manager on prod**
   — its crm-test manager (Tom Mendelsohn) has no prod CMentorProfile. Assign
   an owner in Partner Management / the CRM.
3. **The 3 new prod partner records carry no Team** — the intake API user
   can't read Teams on prod, so the Partner Management Team stamp was skipped
   (Fatherhood Initiative, Global Cleveland, Sea Change + their Accounts). If
   partner-manager visibility relies on team-scope reads, set the team in the
   CRM UI.
4. **Prod "SBA - Cleveland" partner lists Korin Green (ECDI's director, with
   her @ecdi.org email) as its primary contact** — looks misfiled; verify and
   correct in the CRM.
5. **Fatherhood Initiative account's website field holds an email address**
   (`cuyahoga-fatherhood-initiative@jfs.ohio.gov`, copied as-is from
   crm-test) — fix in the CRM UI if wanted.

## Data cleanup

9. **Intake-receipt redesign — CRM-side finish** (2026-07-27; app arc
   COMPLETE and converged — see the CLAUDE.md Current-status block). Three
   Doug-side items, both CRMs unless noted:
   - **Delete the old `reason` and `status` fields** on Intake Submission in
     Entity Manager (`cintake-submission-redesign.md` §6) — the migration is
     verified on both environments, nothing writes or reads them anymore.
   - The **§7 live pass** when convenient: a test form submission (watch it go
     Received → Completed in Submission Admin AND on the CRM receipt), an
     outside email to info@ (a Held-Email receipt exists in the CRM before
     anyone touches it), and a Discard-with-reason (who/when/why on the
     receipt).
   - Delete the live-probe receipt **ZZTEST `6a66f5b4bbe3805ee`** (crm-test).

7. **Partner Accounts carry a bogus industry sector** (found 2026-07-25).
   `Account.cIndustrySector` used to default to "Agriculture, Forestry, Fishing
   and Hunting", and it stuck on 7 of 8 crm-test partner Accounts — including
   Key Bank and Global Cleveland. The **default is now cleared on both CRMs**
   (verified `default=None` 2026-07-25), so new records are fine, but the
   already-stored values are wrong and now **visible**: v0.153.0 shows the
   company's industry on the partner/funder Overview rail. Doug is correcting
   these by hand in the CRM.

## Other follow-ups

6. **Re-save the session whose notes were lost to the pasted-image failure**
   (found 2026-07-24, fixed in v0.148.0). Prod CSession `6a604b7b26efd8e3f`:
   the 04:37 UTC save 500'd in the CRM ("Data too long for column
   'session_notes'" — a pasted image as base64), so those notes never stored.
   After the v0.150.0 deploy, re-enter/re-save the notes — pasting the image
   inline now works (v0.150.0 stores it as a CRM attachment). Live check while
   there: the pasted image dims briefly, then the save succeeds and the image
   renders on the Overview feed, the session view, and in the EspoCRM UI.

## Resolved

- **Account type stamp wrote a field that no longer exists** — found
  2026-07-24 on prod, where `Account.cAccountType` had been removed; all four
  intake orchestrators wrote it, and EspoCRM silently ignores unknown
  attributes, so the type stamp stored nothing. **Resolved 2026-07-28:** the
  Account entity is presented as **Company** and its type field is
  **`cCompanyType`** (Doug). A live probe found `cAccountType` gone from
  **both** CRMs and `cCompanyType` identical on both — multiEnum
  `['', 'Client', 'Sponsor', 'Partner', 'Other']` — so the fix is a straight
  retarget, no feature detection. All four orchestrators now write
  `cCompanyType`, and the sponsor form's value changed from `"Donor/Sponsor"`
  (rejected by the CRM — it is not an option) to **`"Sponsor"`**. The drift
  monitor (`core/schema_contract.py`) was retargeted with it. Verified live on
  crm-test: Client/Partner/Sponsor each stored, `"Donor/Sponsor"` refused.

- **Account-level partner fields duplicated (and contradicted) the partnership
  record** — found 2026-07-24 during Doug's partner review; `cPartnerStatus`,
  `cPartnerContactCadence`, `cPartnerType`, `cPartnershipStartDate` and
  `cPartnershipAgreementDate` were editable on the Company card while the grid
  and Overview read the `CPartnerProfile` twins, and live data had already
  drifted apart (Glide: Account "Monthly" vs partnership "As-Needed"; every
  Account "Prospect" regardless of real status). **Resolved 2026-07-25:** Doug
  deleted all five CRM-side, verified MISSING on crm-test AND prod, and
  v0.153.0 removed the app's references (the Company group is now organization
  type + announcements). The `cIndustrySector` stamped default was cleared in
  the same pass — see item 7 for the stored values it left behind.
