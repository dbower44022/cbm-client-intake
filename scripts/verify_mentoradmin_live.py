"""One-off LIVE check of the Mentor Admin tool against crm-test.

Logs in as a real staff user (their EspoCRM username/password) and runs the same
service code the web app uses. Without a mentor id it just lists what the tool
would show (read-only): the roster + the live editable-field options. With a
mentor id it fetches the full detail; with a field+value it performs a real
edit, GET-verifies it, then restores the original value (a clean round-trip)
unless MA_NO_RESTORE is set. With MA_APPROVE it instead drives the status ->
Approved transition and verifies the auto-provisioned login user (creation,
team, profile link), then restores. Not part of the test suite — writes real
data; creating Users needs an admin (or User-create-granted) login.

Env:
  ESPO_BASE_URL                 (from .env)
  MA_USERNAME, MA_PASSWORD      real staff login (Mentor Administration Team / admin)
  MENTOR_ADMIN_ALLOWED_TEAMS    (optional override; admins bypass the gate)
  MENTOR_TEAM_NAME              (optional; default "Mentor Team")
  MA_MENTOR_ID                  (optional) CMentorProfile to inspect / edit / approve
  MA_FIELD, MA_VALUE            (optional) editable field + new value to write
  MA_APPROVE                    (optional, any value) run the approval-provisioning check
  MA_NO_RESTORE                 (optional, any value) keep the edit/approval instead of reverting
"""

from __future__ import annotations

import asyncio
import os

from assignments import auth
from assignments import service as assign_service
from assignments.espo_user import client_for
from core.config import Settings
from mentoradmin import service

_TYPES = {f["name"]: f["type"] for f in service.EDITABLE_FIELDS}


def _coerce(field: str, raw: str):
    """Turn the string env value into the right type for the field."""
    t = _TYPES.get(field, "varchar")
    if t == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if t == "int":
        return None if raw == "" else int(raw)
    if t == "multiEnum":
        return [v.strip() for v in raw.split(",") if v.strip()]
    if t == "date":
        return raw or None
    return raw


async def approval_check(client, settings, mentor_id: str) -> None:
    """Drive status -> Approved and verify the provisioned login, then restore."""
    pre = await client.get(
        service.MENTOR_PROFILE, mentor_id,
        select="name,mentorStatus,assignedUserId,assignedUserName",
    )
    original_status = pre.get("mentorStatus")
    had_user = bool(pre.get("assignedUserId"))
    print(f"\n=== Approval provisioning check: {pre.get('name')!r} ===")
    print(f"  before: status={original_status!r} assignedUser={pre.get('assignedUserName')!r}")
    if original_status == service.STATUS_APPROVED:
        print("  NOTE: already Approved — the transition won't re-trigger provisioning.")
    if had_user:
        print("  NOTE: already has a linked user — provisioning is skipped by design.")

    # The script is run by an admin, so the admin's own client is the privileged
    # provisioning client (the app uses the service API key instead).
    result = await service.update_mentor(
        client, mentor_id, {"mentorStatus": service.STATUS_APPROVED},
        team_name=settings.mentor_team_name, admin_client=client,
    )
    prov = result.get("provision")
    print(f"  provision summary: {prov}")

    if prov and prov.get("ok"):
        uid = prov["userId"]
        u = await client.get(
            "User", uid,
            select="userName,emailAddress,type,isActive,teamsNames,defaultTeamName",
        )
        teams = list((u.get("teamsNames") or {}).values())
        print(f"  User {uid}: userName={u.get('userName')!r} email={u.get('emailAddress')!r} "
              f"type={u.get('type')!r} active={u.get('isActive')} teams={teams}")
        print(f"  team OK: {prov['team'] in teams}")
        prof = await client.get(
            service.MENTOR_PROFILE, mentor_id,
            select="mentorStatus,assignedUserId,assignedUserName,cbmEmail",
        )
        print(f"  profile: status={prof.get('mentorStatus')!r} "
              f"assignedUser={prof.get('assignedUserName')!r} ({prof.get('assignedUserId')}) "
              f"cbmEmail={prof.get('cbmEmail')!r}")
        print(f"  link OK: {prof.get('assignedUserId') == uid}")
    elif prov:
        print(f"  PROVISION FAILED: {prov.get('error')}")
    else:
        print("  (no provisioning ran — see the NOTEs above.)")

    if os.environ.get("MA_NO_RESTORE"):
        print("  MA_NO_RESTORE set — leaving status Approved and the new user in place.")
        return
    # Restore directly (bypass the whitelist) so we can also unlink a user we made.
    restore = {"mentorStatus": original_status}
    if prov and prov.get("ok") and not had_user:
        restore["assignedUserId"] = None
    await client.update(service.MENTOR_PROFILE, mentor_id, restore)
    print(f"  restored: status -> {original_status!r}"
          + ("; unlinked the new user" if "assignedUserId" in restore else ""))
    if prov and prov.get("ok"):
        print(f"  CLEANUP: delete the created User {prov['userId']} "
              f"({prov['userName']}) in the EspoCRM UI — this script does not delete.")


async def main() -> None:
    settings = Settings(
        session_secret="verify-script",
        mentor_admin_allowed_teams=os.environ.get(
            "MENTOR_ADMIN_ALLOWED_TEAMS", "Mentor Administration Team"
        ),
    )
    user = await auth.authenticate(
        settings, os.environ["MA_USERNAME"], os.environ["MA_PASSWORD"],
        allowed_teams=settings.mentor_admin_allowed_teams_list, allowed_roles=[],
    )
    print(f"Logged in as {user['name']} ({user['userName']}), admin={user['isAdmin']}")
    client = client_for(settings, user)

    roster = await assign_service.list_all_mentors(client)
    print(f"\nMentor roster ({len(roster)}):")
    for m in roster[:25]:
        print(f"  {m['id']}  {m['name']!r:32}  status={m['status']}  "
              f"accepting={m['acceptingNewClients']}  cap={m['availableCapacity']}")
    if len(roster) > 25:
        print(f"  ... +{len(roster) - 25} more")

    options = await service.field_options(client)
    print(f"\nLive enum options for {len(options)} fields:")
    for name, opts in options.items():
        print(f"  {name}: {opts}")

    mentor_id = os.environ.get("MA_MENTOR_ID")
    if not mentor_id:
        print("\n(Set MA_MENTOR_ID to fetch a full mentor detail; add MA_FIELD+MA_VALUE to edit.)")
        return

    rec = await service.get_mentor(client, mentor_id)
    print(f"\nMentor {mentor_id}: {rec.get('name')!r}  status={rec.get('mentorStatus')}")
    for f in service.EDITABLE_FIELDS:
        print(f"  {f['name']} ({f['type']}): {rec.get(f['name'])!r}")

    if os.environ.get("MA_APPROVE"):
        await approval_check(client, settings, mentor_id)
        return

    field = os.environ.get("MA_FIELD")
    if not field:
        print("\n(Set MA_FIELD + MA_VALUE to perform a live edit, or MA_APPROVE to test approval.)")
        return
    if field not in service.EDITABLE_NAMES:
        print(f"\n{field!r} is not an editable field — aborting.")
        return

    original = rec.get(field)
    new_value = _coerce(field, os.environ.get("MA_VALUE", ""))
    print(f"\nEditing {field}: {original!r} -> {new_value!r} ...")
    await service.update_mentor(client, mentor_id, {field: new_value})
    after = await service.get_mentor(client, mentor_id)
    print(f"  now: {after.get(field)!r}  (match={after.get(field) == new_value})")

    if os.environ.get("MA_NO_RESTORE"):
        print("  MA_NO_RESTORE set — leaving the edit in place.")
        return
    print(f"  restoring original {field}={original!r} ...")
    await service.update_mentor(client, mentor_id, {field: original})
    restored = await service.get_mentor(client, mentor_id)
    print(f"  restored: {restored.get(field)!r}  (match={restored.get(field) == original})")


asyncio.run(main())
