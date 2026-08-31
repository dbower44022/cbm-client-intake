#!/usr/bin/env python3
"""Stage 4: one real NON-ADMIN user per gated team on the throwaway, plus the
Contact + CMentorProfile the Mentor Team user needs so the session tools can
resolve them as a manager. Idempotent; passwords minted alphanumeric and
written to lakeside-users.env (scratchpad). --apply writes."""
import asyncio, json, secrets, string, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assignments.auth import login_token
from core.espo import EspoClient, EspoError
S = Path(__file__).resolve().parent
USERS = [  # userName, first, last, team
    ("lakeside.clientadmin", "Casey", "ClientAdmin", "Client Administration Team"),
    ("lakeside.mentoradmin", "Morgan", "MentorAdmin", "Mentor Administration Team"),
    ("lakeside.mentor", "Jordan", "Mentor", "Mentor Team"),
    ("lakeside.partner", "Riley", "PartnerMgr", "Partner Management Team"),
    ("lakeside.funder", "Avery", "FunderMgr", "Sponsor Management Team"),
    ("lakeside.marketing", "Sam", "Marketing", "Marketing Admin Team"),
    ("lakeside.analytics", "Quinn", "Analytics", "Analytics Admin Team"),
]
def env(p):
    d = {}
    for l in Path(p).read_text().splitlines():
        if l.strip() and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); d[k.strip()] = v.strip()
    return d
def pw(): return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20))
async def main(apply):
    e = env(S / "lakeside.env"); ue_path = S / "lakeside-users.env"; ue = env(ue_path) if ue_path.exists() else {}
    n, t = await login_token(e["ESPO_ADMIN_BASE"], e["ESPO_ADMIN_USER"], e["ESPO_ADMIN_PASS"], 30)
    c = EspoClient.for_user_token(e["ESPO_ADMIN_BASE"], n, t, timeout=60)
    teams = {x["name"]: x["id"] for x in (await c._request("GET", c._base + "/Team", op="teams", params={"maxSize": 200})).json()["list"]}
    users = {x["userName"]: x for x in (await c._request("GET", c._base + "/User", op="users", params={"maxSize": 200, "select": "userName,type,teamsIds"})).json()["list"]}
    for uname, first, last, team in USERS:
        if uname in users:
            print("exists  ", uname); uid = users[uname]["id"]
        elif apply:
            p = pw()
            r = await c.create("User", {"userName": uname, "firstName": first, "lastName": last, "type": "regular",
                                        "isActive": True, "password": p, "passwordConfirm": p,
                                        "teamsIds": [teams[team]], "defaultTeamId": teams[team],
                                        "emailAddress": f"{uname}@lakeside.example.invalid"})
            uid = r["id"]; ue[uname] = p
            with ue_path.open("a") as fh: fh.write(f"{uname}={p}\n")
            print("created ", uname, "->", team)
        else:
            print("would create", uname, "->", team); uid = None
        if uname == "lakeside.mentor" and uid:
            # Contact + CMentorProfile for the mentor, assigned to the login
            found = (await c._request("GET", c._base + "/CMentorProfile", op="mp", params={"maxSize": 5, "where[0][type]": "equals", "where[0][attribute]": "cbmEmail", "where[0][value]": "jordan.mentor@lakeside.example.invalid"})).json()
            if found.get("total"):
                print("exists   CMentorProfile for lakeside.mentor"); continue
            if not apply:
                print("would create Contact + CMentorProfile for lakeside.mentor"); continue
            contact = await c.create("Contact", {"firstName": first, "lastName": last, "emailAddress": "jordan.mentor@lakeside.example.invalid",
                                                 "cContactType": ["Mentor"], "assignedUsersIds": [uid]})
            body = {"name": f"{first} {last}", "contactRecordId": contact["id"], "mentorStatus": "Active",
                    "acceptingNewClients": True, "cbmEmail": "jordan.mentor@lakeside.example.invalid",
                    "assignedUserId": uid, "assignedUsersIds": [uid], "termsAccepted": True,
                    "ethicsAgreementAccepted": True, "mentorCodeAccepted": True}
            try:
                mp = await c.create("CMentorProfile", body)
            except EspoError as ex:
                print("CMentorProfile create failed:", ex); continue
            back = await c.get("CMentorProfile", mp["id"])
            print("created  Contact", contact["id"], "CMentorProfile", mp["id"], "assignedUserId=", back.get("assignedUserId"), "assignedUsersIds=", back.get("assignedUsersIds"))
asyncio.run(main("--apply" in sys.argv))
