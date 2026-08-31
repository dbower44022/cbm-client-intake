# Roles: where the two CRMs disagree — the ruling table

> Working copy for § R4 step 5. Captured 2026-08-31: production via
> `scripts/capture_roles.py` run inside the deployed web container
> (`prod-capture-2026-08-31.json`); crm-test from the database over SSH during
> the Lakeside rehearsal (`../rehearsal-2026-08-31/crmtest-capture/`).
> **RULED (Doug, 2026-08-31): production is the standard for every row.**
> Group A's crm-test `delete: all` is a **sanctioned staging-only deviation**
> — the nightly recycle deletes app-created records through the API, and
> production (and every chapter) must never grant the API delete. crm-test was
> updated to match on groups B and C; the re-capture verification and its six
> leftovers are in the postscript.

Both CRMs hold the **same 12 roles** and the **same 9 teams**. Of the compared
cells, 415 agree outright and 213 differ only in representation (empty-vs-absent
maps, an explicit `stream: no`, `not-set` vs `no` — identical effective ACL);
**43 cells and one team attachment differ for real.**

## The one attachment difference

| Role | crm-test | production | Standard |
|---|---|---|---|
| Data Integrity Team Role | attached to **Data Integrity Team** | **no team** — the role currently grants nothing to anyone | |

The third occurrence of the attachments-go-missing failure class
([[espo-403-diagnosis-merged-team-roles]]). Tracked as a Cleveland defect in
`OPEN-ITEMS.md` #29. Read via `Role/{id}/teams` on both instances — the record
GET returns empty lists even where attachments exist, which is why
`capture_roles.py` was fixed the same day to read the relationship endpoint.

## The 43 cell differences

Values are EspoCRM's own (`create/read/edit/delete/stream` levels; boolean
scopes shown as on/off; *(not set)* means the role does not mention the scope).

### A — `CustomAppAPIRole`: crm-test grants **delete: all**, production **delete: no** (one decision, 17 scopes)

| Role | Scope | crm-test | production | Standard |
|---|---|---|---|---|
| CustomAppAPIRole | `Account` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CClientProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CCommunication` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | **production** |
| CustomAppAPIRole | `CContribution` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | **production** |
| CustomAppAPIRole | `CConversation` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | **production** |
| CustomAppAPIRole | `CEngagement` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CEvent` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CEventRegistration` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | **production** |
| CustomAppAPIRole | `CInformationRequest` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: no | **production** |
| CustomAppAPIRole | `CIntakeSubmission` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CMentorProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CPartnerProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CResource` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CSession` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `CSponsorProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `Contact` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| CustomAppAPIRole | `Team` | read: all | create: no, delete: no, edit: no, read: all, stream: no | **production** |

### B — Extension and personal-integration scopes (rule together with **R7**)

| Role | Scope | crm-test | production | Standard |
|---|---|---|---|---|
| Client Assignment Role | `EmailAccountScope` | on | (not set) | **production** |
| Client Assignment Role | `GoogleCalendar` | on | (not set) | **production** |
| Client Assignment Role | `GoogleContacts` | on | (not set) | **production** |
| Marketing Admin Role | `Activities` | (not set) | on | **production** |
| Mentor Role | `EmailAccountScope` | on | (not set) | **production** |
| Mentor Role | `GoogleCalendar` | on | (not set) | **production** |
| Mentor Role | `GoogleContacts` | on | (not set) | **production** |
| Standard User | `Activities` | on | (not set) | **production** |
| Standard User | `Calendar` | on | (not set) | **production** |
| Standard User | `EmailAccountScope` | on | (not set) | **production** |
| Standard User | `ExternalAccount` | on | (not set) | **production** |
| Standard User | `GoogleCalendar` | on | (not set) | **production** |

### C — Individual differences, one decision each

| Role | Scope | crm-test | production | Standard |
|---|---|---|---|---|
| ClientMentorIntakeRole | `CInformationRequest` | create: yes, delete: no, edit: all, read: all, stream: no | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| ClientMentorIntakeRole | `CResource` | create: yes, delete: no, edit: all, read: all, stream: no | create: yes, delete: no, edit: all, read: all, stream: all | **production** |
| ClientMentorIntakeRole | `User` | (not set) | edit: own, read: all | **production** |
| CustomAppAPIRole | *permission* `assignmentPermission` | all | not-set | **production** |
| CustomAppAPIRole | `OpenApi` | (not set) | on | **production** |
| Marketing Admin Role | `EmailTemplateCategory` | (not set) | create: yes, delete: no, edit: all, read: all, stream: no | **production** |
| Mentor Administration Role | *permission* `auditPermission` | yes | not-set | **production** |
| Mentor Role | `CCommunication` | create: no, delete: no, edit: no, read: all | create: yes, delete: no, edit: own, read: all | **production** |
| Mentor Role | `CConversation` | create: no, delete: no, edit: no, read: all | create: yes, delete: no, edit: own, read: own | **production** |
| Mentor Role | `CPartnerProfile` | create: no, delete: no, edit: own, read: all, stream: no | create: no, delete: no, edit: no, read: all, stream: no | **production** |
| Partner Manager Role | `Team` | (not set) | read: all | **production** |
| Sponsor Manager Role | `CCommunication` | create: no, delete: no, edit: no, read: all | (not set) | **production** |
| Sponsor Manager Role | `CConversation` | create: no, delete: no, edit: no, read: all | (not set) | **production** |
| Standard User | field locks on `Account` | cClientProfile: edit: no, read: no, cCompanyPartnerProfile: edit: no, read: no, cSponsorProfile: edit: no, read: no |  | |

## Notes for the ruling

- **Group A** is one question: may the org-wide API key delete records?
  Production's `delete: no` is tighter and everything works there; the app's
  deleters (cleanup scripts, docs rollback) run rarely and could escalate to
  the admin account. Production is probably the standard.
- **Group B** is R7 in table form: `GoogleCalendar`/`GoogleContacts` ship with
  the Google Integration extension; `EmailAccountScope`/`ExternalAccount`/
  `Activities`/`Calendar` are personal-UI surfaces, not app behaviour. Ruling
  R7 (are the extensions part of the standard?) settles most of this block.
- In **group C**, three rows change what real users can do today: Mentor
  Role's `CCommunication`/`CConversation` (production lets mentors create and
  edit their own; crm-test is read-only), Mentor Role's `CPartnerProfile`
  (edit `own` on crm-test, `no` on production), and `ClientMentorIntakeRole`'s
  `User` grant (production only). The `Standard User` field-locks row carries
  the stale `cCompanyPartnerProfile` entry (field deleted 2026-08-14, finding
  F6) — whichever side is ruled, that entry must not enter the standard:
  EspoCRM 10 rejects the whole role over it.

## Verification, 2026-08-31 18:37 UTC — after the ruling

crm-test was re-captured and re-diffed against production. Groups B and C are
substantially aligned; group A's 17 delete cells remain different **by ruling**
(sanctioned). **Six cells still differ and are owed a crm-test edit** (the
standard is production's value in each):

| Role | Scope | crm-test now | production (= standard) |
|---|---|---|---|
| Mentor Role | `EmailAccountScope` | on | not set |
| Standard User | `ExternalAccount` | on | not set |
| Marketing Admin Role | `Activities` | not set | on |
| Sponsor Manager Role | `CCommunication` | read: all | not set |
| Sponsor Manager Role | `CConversation` | read: all | not set |
| CustomAppAPIRole | *permission* `assignmentPermission` | all | not-set |

(Also inside group A's sanctioned block, `CInformationRequest` differs on
`stream` — crm-test `all`, production `no` — not part of the delete deviation,
so it should follow production too.) The stale `Standard User` field lock (F6)
is GONE from crm-test — the update cleared it.
