"""The training sign-ins a training system needs, created by an administrator.

``seed_training_data.py`` attaches mentor profiles to sign-ins that already
exist; EspoCRM lets only an administrator create one (deployment guide step
14.2). crm-test's were made by hand. This creates the same twelve on another
training system (Association ruling 77), each a Regular user on the teams the
training guide's walkthroughs need, with its user name and email on the
target's mailbox-less sandbox domain (``targets.py``).

Two halves, so a password never passes through anyone but the person who
keeps it:

* ``--apply`` creates each missing sign-in **with no password** — it cannot
  be signed in to yet. Never lowers or removes anything on an existing one.
* ``--set-passwords`` asks for each sign-in's password at the keyboard
  (nothing echoed, nothing written down) and sets it. Run it yourself, in your
  own terminal, and keep the passwords in the password vault.

Needs the CRM administrator's sign-in (``ESPO_ADMIN_*``) from ``--env-file``::

    uv run python scripts/sandbox/training_logins.py --env-file ~/.config/cbm-bma/bma.env
    uv run python scripts/sandbox/training_logins.py --env-file ~/.config/cbm-bma/bma.env --apply
    uv run python scripts/sandbox/training_logins.py --env-file ~/.config/cbm-bma/bma.env --set-passwords

Refuses crm-test (its sign-ins exist and use their own domain) and every CRM
that is not a training system.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import targets  # noqa: E402  (puts the repository and scripts/ on the path)

from espo_admin import connect, credentials  # noqa: E402

MENTOR = "Mentor Team"

#: (user name before the @, first name, last name, teams — the first is the default)
LOGINS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("joe.mentor", "Joe", "Mentor", (MENTOR,)),
    ("matt.mentor", "Matt", "Mentor", (MENTOR,)),
    ("tony.tiger", "Tony", "Tiger", (MENTOR,)),
    ("wally.walrus", "Wally", "Walrus", (MENTOR,)),
    ("tom.gold", "Tom", "Gold", (MENTOR,)),
    ("jim.beem", "Jim", "Beem", (MENTOR,)),
    ("tt", "Tommy", "Tranell", (MENTOR,)),
    ("kitty.cat", "Kitty", "Cat", ("Client Administration Team", MENTOR)),
    ("partner.manager", "Partner", "Manager", ("Partner Management Team", MENTOR)),
    ("sally.sponsor", "Sally", "Sponsor", ("Sponsor Management Team",)),
    # crm-test's Mentor Admin is an Admin-type user; guide step 14.2 says never.
    ("mentoradmin", "Mentor", "Admin", ("Mentor Administration Team", MENTOR)),
    ("mark.marketing", "Mark", "Marketing", ("Marketing Admin Team",)),
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="create the missing sign-ins")
    parser.add_argument("--set-passwords", action="store_true",
                        help="ask for and set each sign-in's password")
    targets.add_env_file_argument(parser)
    args = parser.parse_args()

    env = targets.load_env_file(args.env_file)
    base = credentials(env)[0]
    target = targets.resolve(base)
    if target is None or target is targets.TARGETS[0]:
        print(targets.refusal(base) if target is None else
              "REFUSING: crm-test's training sign-ins already exist; this is for another training system.")
        return 2
    client, me = await connect(env)
    if me.get("type") != "admin":
        print("Creating a sign-in needs an Admin-type account.")
        return 2

    teams = {t["name"]: t["id"] for t in
             (await client.list("Team", select="id,name", max_size=200)).get("list", [])}
    users = {(u.get("userName") or "").lower(): u for u in
             (await client.list("User", select="id,userName,type,teamsIds,isActive",
                                max_size=200)).get("list", [])}
    print(f"{target.label}: {base}\n")

    missing_team = sorted({t for *_, ts in LOGINS for t in ts} - set(teams))
    if missing_team:
        print(f"! teams missing on this CRM: {', '.join(missing_team)} — nothing done")
        return 1

    for local, first, last, team_names in LOGINS:
        user_name = f"{local}@{target.login_domain}"
        existing = users.get(user_name)
        team_ids = [teams[t] for t in team_names]
        if args.set_passwords:
            if not existing:
                print(f"  {user_name}: does not exist yet — run --apply first")
                continue
            while True:
                pw = getpass.getpass(f"  password for {user_name} (blank skips): ")
                if not pw:
                    break
                if pw == getpass.getpass("  again: "):
                    await client.update("User", existing["id"],
                                        {"password": pw, "passwordConfirm": pw})
                    print("    set")
                    break
                print("    the two did not match — try again")
            continue
        if existing:
            print(f"  {user_name}: exists ({existing.get('type')})")
            continue
        print(f"  {'create' if args.apply else 'would create'} {user_name} — "
              f"{first} {last}, Regular, teams {', '.join(team_names)}")
        if args.apply:
            await client.create("User", {
                "userName": user_name, "type": "regular", "isActive": True,
                "firstName": first, "lastName": last, "emailAddress": user_name,
                "teamsIds": team_ids, "defaultTeamId": team_ids[0],
            })
    if not (args.apply or args.set_passwords):
        print("\nDry run. Re-run with --apply to create.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
