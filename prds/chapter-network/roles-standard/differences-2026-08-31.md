# Roles: where the two CRMs disagree — the ruling table

> Working copy for § R4 step 5. Captured 2026-08-31: production via
> `scripts/capture_roles.py` run inside the deployed web container
> (`prod-capture-2026-08-31.json`); crm-test from the database over SSH during
> the Lakeside rehearsal (`../rehearsal-2026-08-31/crmtest-capture/`).
> **Where the two agree, that is the standard by default** — only the rows
> below need a ruling. Fill the **Standard** column; the ruled table then moves
> to `phase-1-crm-config.md` as the roles half of the desired state.

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
| CustomAppAPIRole | `Account` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CClientProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CCommunication` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | |
| CustomAppAPIRole | `CContribution` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | |
| CustomAppAPIRole | `CConversation` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | |
| CustomAppAPIRole | `CEngagement` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CEvent` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CEventRegistration` | create: yes, delete: all, edit: all, read: all | create: yes, delete: no, edit: all, read: all | |
| CustomAppAPIRole | `CInformationRequest` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: no | |
| CustomAppAPIRole | `CIntakeSubmission` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CMentorProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CPartnerProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CResource` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CSession` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `CSponsorProfile` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `Contact` | create: yes, delete: all, edit: all, read: all, stream: all | create: yes, delete: no, edit: all, read: all, stream: all | |
| CustomAppAPIRole | `Team` | read: all | create: no, delete: no, edit: no, read: all, stream: no | |

### B — Extension and personal-integration scopes (rule together with **R7**)

| Role | Scope | crm-test | production | Standard |
|---|---|---|---|---|
| Client Assignment Role | `EmailAccountScope` | on | (not set) | |
| Client Assignment Role | `GoogleCalendar` | on | (not set) | |
| Client Assignment Role | `GoogleContacts` | on | (not set) | |
| Marketing Admin Role | `Activities` | (not set) | on | |
| Mentor Role | `EmailAccountScope` | on | (not set) | |
| Mentor Role | `GoogleCalendar` | on | (not set) | |
| Mentor Role | `GoogleContacts` | on | (not set) | |
| Standard User | `Activities` | on | (not set) | |
| Standard User | `Calendar` | on | (not set) | |
| Standard User | `EmailAccountScope` | on | (not set) | |
| Standard User | `ExternalAccount` | on | (not set) | |
| Standard User | `GoogleCalendar` | on | (not set) | |

### C — Individual differences, one decision each

| Role | Scope | crm-test | production | Standard |
|---|---|---|---|---|
| ClientMentorIntakeRole | `CInformationRequest` | create: yes, delete: no, edit: all, read: all, stream: no | create: yes, delete: no, edit: all, read: all, stream: all | |
| ClientMentorIntakeRole | `CResource` | create: yes, delete: no, edit: all, read: all, stream: no | create: yes, delete: no, edit: all, read: all, stream: all | |
| ClientMentorIntakeRole | `User` | (not set) | edit: own, read: all | |
| CustomAppAPIRole | *permission* `assignmentPermission` | all | not-set | |
| CustomAppAPIRole | `OpenApi` | (not set) | on | |
| Marketing Admin Role | `EmailTemplateCategory` | (not set) | create: yes, delete: no, edit: all, read: all, stream: no | |
| Mentor Administration Role | *permission* `auditPermission` | yes | not-set | |
| Mentor Role | `CCommunication` | create: no, delete: no, edit: no, read: all | create: yes, delete: no, edit: own, read: all | |
| Mentor Role | `CConversation` | create: no, delete: no, edit: no, read: all | create: yes, delete: no, edit: own, read: own | |
| Mentor Role | `CPartnerProfile` | create: no, delete: no, edit: own, read: all, stream: no | create: no, delete: no, edit: no, read: all, stream: no | |
| Partner Manager Role | `Team` | (not set) | read: all | |
| Sponsor Manager Role | `CCommunication` | create: no, delete: no, edit: no, read: all | (not set) | |
| Sponsor Manager Role | `CConversation` | create: no, delete: no, edit: no, read: all | (not set) | |
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
