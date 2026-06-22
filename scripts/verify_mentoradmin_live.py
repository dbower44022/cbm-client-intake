"""One-off LIVE check of the Mentor Admin tool against crm-test.

Logs in as a real staff user (their EspoCRM username/password) and runs the same
service code the web app uses. Without a mentor id it just lists what the tool
would show (read-only): the roster + the live editable-field options. With a
mentor id it fetches the full detail; with a field+value it performs a real
edit, GET-verifies it, then restores the original value (a clean round-trip)
unless MA_NO_RESTORE is set. Not part of the test suite — writes real data.

Env:
  ESPO_BASE_URL                 (from .env)
  MA_USERNAME, MA_PASSWORD      real staff login (Mentor Administration Team / admin)
  MENTOR_ADMIN_ALLOWED_TEAMS    (optional override; admins bypass the gate)
  MA_MENTOR_ID                  (optional) CMentorProfile to inspect / edit
  MA_FIELD, MA_VALUE            (optional) editable field + new value to write
  MA_NO_RESTORE                 (optional, any value) keep the edit instead of reverting
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

    field = os.environ.get("MA_FIELD")
    if not field:
        print("\n(Set MA_FIELD + MA_VALUE to perform a live edit.)")
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
