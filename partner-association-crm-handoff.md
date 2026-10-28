# CRM handoff — partner and funder associations: `CPartnerAssociation`

Last Updated: 10-28-26 02:10 · Revision 0.1 — see change log at the end.

One new record type, one record per tie between a partner or funder and a
business (or a person or lead with no business yet), and one new link on event
registrations. Plus five role grants. Plan and rulings:
`prds/partner-association-plan.md` (Doug, 10-28-26).

**Additive.** One entity, 2 fields, 8 links, 5 role grants. Nothing removed,
renamed or narrowed. Safe ahead of the code: the application feature-detects
the entity and the new link, and writes nothing until both exist.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Not applied.** Dry run 10-28-26: every name free, fingerprint `8dd9d9264170`. | The applier's dry run. |
| Production | **Not applied.** At a Sunday 17:00 UTC slot, after crm-test's live pass. | — |
| Boston | **Owed** with its release. | — |

Decided here, and said so:

- **A record per tie, not a many-to-many link.** A tie carries a reason, the
  event or engagement it came from, the person who carried it and a date; a
  plain link can hold none of them.
- **`company`, `contact` and `lead` are all optional.** A tie sits on the
  company when there is one; on the contact or the lead until there is; the
  contact stays as the person who carried it after the tie moves to the
  company (ruling 2).
- **Exactly one of `partnerProfile` and `sponsorProfile`** is set; the
  application enforces it.
- **No field is Read-only** — the application writes every one (ruling 40).
- **The entity is type Base**, no stream. `name` is required by that type, so
  the application names each record ("Lakewood Library — Referred to CBM").
- **Grants:** `CustomAppAPIRole` create, read all, edit all — every
  association is written by the application, including a mentor's referral.
  Marketing Admin Role, Client Assignment Role, Partner Manager Role and
  Sponsor Manager Role read all, so the associations show in the CRM. Mentor
  Role nothing. Nobody deletes.
- **`CEventRegistration.registrationCompany`** is new and optional: the
  company the person was with when they registered (ruling 3).
- **No sandbox seeder stage.** Associations are made by the application; a
  reset that removes them leaves nothing broken, and the backfill job can
  rebuild them.

## 1. Names

`CPartnerAssociation` (typed `PartnerAssociation`; the CRM adds the `C`). Its
fields are stored as written. The links as stored, read from the dry run:

| On `CPartnerAssociation` | Points at | Stored on the other side as |
|---|---|---|
| `partnerProfile` | CPartnerProfile | `associations` |
| `sponsorProfile` | CSponsorProfile | `associations` |
| `company` | Account | `cPartnerAssociations` |
| `contact` | Contact | `cPartnerAssociations` |
| `lead` | CProspect | `partnerAssociations` |
| `event` | CEvent | `partnerAssociations` |
| `engagement` | CEngagement | `partnerAssociations` |

And `CEventRegistration.registrationCompany` → Account, stored on Account as
`cEventRegistrations`.

## 2. Apply on crm-test

From the build computer, in `~/Dropbox/Projects/cbm-client-intake`:

```
scripts/partner_association_crm_test.sh plan
```

```
scripts/partner_association_crm_test.sh roles
```

The first creates and reads back the entity, its fields and every link. The
second sets and reads back the five grants and rebuilds.

## 3. Verify

1. `GET /Metadata` → `entityDefs.CPartnerAssociation`: the two fields, none
   Read-only, and the seven links in § 1; each other side carries its stored
   link name.
2. As the org-wide key: `GET /CPartnerAssociation?maxSize=1` answers 200.
3. A real non-admin pass (the live pass): a Marketing Admin Team member's
   list selects by an association; a mentor's *Refer to a partner* writes one.

## 4. Production and Boston

Production at a Sunday slot, from inside the production web container: the
applier with this plan and fingerprint, then
`scripts/migrate_partner_association_roles.py --apply` under the admin login.
Claude writes the step page when the slot is booked. Boston:
`scripts/apply_plan.sh boston scripts/plans/cpartner-association.json
8dd9d9264170`, then the role script against Boston.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 10-28-26 02:10 | Claude (Claude Code) | Created; dry run on crm-test clean. |
