# Open items to address

Running list of known issues and pending decisions that don't belong to any
single feature doc. Add new items at the top of their section with the date
found; move resolved items to the bottom with the resolution date.

## Needs a fix / decision

1. **Prod Account schema drift: `cAccountType` no longer exists** (found
   2026-07-24 during the partner data migration). Prod's `Account` entity has
   no `cAccountType` field — a where clause on it 400s ("Not existing
   attribute") and the metadata offers only **`cCompanyType`** (multiEnum with
   a "Partner" option). crm-test still has the cAccountType shape. The intake
   orchestrators (client-intake, partner, sponsor, info-request) all write
   `cAccountType=[...]` on Account creates; EspoCRM silently ignores unknown
   attributes, so **on prod the Account type stamp stores nothing** — even
   though it verified at go-live 2026-06-24, meaning the field was
   dropped/renamed CRM-side since. To address:
   - Confirm with the CRM team whether `cCompanyType` is the intended
     replacement and whether crm-test should be aligned to match.
   - Update the orchestrators to write the surviving field (or feature-detect
     and write whichever exists, as the 2026-07-24 migration script did).
   - Check anything that reads/filters Accounts by `cAccountType` (directory
     Company pop-up already uses `cCompanyType`).
   - Memory: `prod-account-caccounttype-missing`.

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
