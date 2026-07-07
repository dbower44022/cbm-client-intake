"""One-off LIVE check of the mentor assignment tool against crm-test.

Logs in as a real staff user (their EspoCRM username/password) and runs the
same service code the web app uses. Without an engagement+mentor it just lists
what the dashboard would show (read-only). With both set it performs a real
assignment and GET-verifies the engagement + related records. Not part of the
test suite — writes real data; use a throwaway/ZZTEST engagement.

Env:
  ESPO_BASE_URL                 (from .env)
  ASSIGN_USERNAME, ASSIGN_PASSWORD   real staff login
  ASSIGN_ALLOWED_ROLES          (optional; admins bypass the gate)
  ASSIGN_ENGAGEMENT_ID          (optional) engagement to assign
  ASSIGN_MENTOR_PROFILE_ID      (optional) CMentorProfile to assign it to
"""

from __future__ import annotations

import asyncio
import os

from assignments import auth, service
from assignments.espo_user import client_for
from core.config import Settings


async def main() -> None:
    settings = Settings(
        session_secret="verify-script",
        assign_allowed_roles=os.environ.get("ASSIGN_ALLOWED_ROLES", ""),
    )
    user = await auth.authenticate(
        settings, os.environ["ASSIGN_USERNAME"], os.environ["ASSIGN_PASSWORD"]
    )
    print(f"Logged in as {user['name']} ({user['userName']}), admin={user['isAdmin']}")
    client = client_for(settings, user)

    engs = await service.list_submitted_engagements(client)
    print(f"\nSubmitted engagements ({len(engs)}):")
    for e in engs:
        print(f"  {e['id']}  {e['name']}  | client={e['clientName']} contact={e['contactName']}")

    mentors = (await service.list_eligible_mentors(client))["mentors"]
    print(f"\nEligible mentors ({len(mentors)}):")
    for m in mentors:
        print(f"  {m['id']}  {m['name']}  | userId={m['userId']} cap={m['availableCapacity']}")

    eng_id = os.environ.get("ASSIGN_ENGAGEMENT_ID")
    mentor_id = os.environ.get("ASSIGN_MENTOR_PROFILE_ID")
    if not (eng_id and mentor_id):
        print("\n(Set ASSIGN_ENGAGEMENT_ID + ASSIGN_MENTOR_PROFILE_ID to perform a live assignment.)")
        return

    print(f"\nAssigning engagement {eng_id} -> mentor {mentor_id} ...")
    result = await service.assign_engagement(client, eng_id, mentor_id)
    print("  result:", result)

    eng = await client.get(
        service.ENGAGEMENT, eng_id,
        select="engagementStatus,assignedUsersIds,mentorProfileId,"
        "primaryEngagementContactId,engagementClientId,clientOrganizationId",
    )
    print("  engagement now:", {
        "status": eng.get("engagementStatus"),
        "assignedUsersIds": eng.get("assignedUsersIds"),  # CEngagement uses collaborators
        "mentorProfileId": eng.get("mentorProfileId"),
    })
    # CClientProfile also uses assignedUsers; Contact/Account use single assignedUser.
    for entity, rid, sel in [
        (service.CONTACT, eng.get("primaryEngagementContactId"), "name,assignedUserName"),
        (service.CLIENT_PROFILE, eng.get("engagementClientId"), "name,assignedUsersIds"),
        (service.ACCOUNT, eng.get("clientOrganizationId"), "name,assignedUserName"),
    ]:
        if rid:
            rec = await client.get(entity, rid, select=sel)
            print(f"  {entity} {rid}: {rec.get('assignedUserName') or rec.get('assignedUsersIds')}")


asyncio.run(main())
