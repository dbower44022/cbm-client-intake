"""Identify and probe an EspoCRM administrative credential.

**Why this exists.** EspoCRM returns the same shapes for "you may not do this"
and "this does not exist" often enough that a credential problem gets diagnosed
as a configuration problem, and vice versa. Before planning any structural
change, establish what you are actually authenticated as and which
administrative endpoints answer for it. That takes seconds and saves an hour.

There is no partial administrator in EspoCRM: the org-wide API key is refused on
every ``Admin/*`` endpoint and on ``Role`` — measured on crm-test 2026-08-26 —
so structural work needs an Admin-type user login. See this skill's ``SETUP.md``.

Usage::

    # who am I, and which administrative endpoints answer?
    PYTHONPATH=. uv run python scripts/espo_admin.py whoami

    # can this credential reach a particular endpoint? (read-only)
    ... espo_admin.py probe Role
    ... espo_admin.py probe Admin/fieldManager/CEngagement/engagementStatus

    # read a metadata key, e.g. to check a name actually landed
    ... espo_admin.py metadata entityDefs.CEngagement.links

Credentials come from the environment or ``.env`` and are never logged::

    ESPO_ADMIN_BASE / ESPO_ADMIN_USER / ESPO_ADMIN_PASS
    (ADMIN_BASE / ADMIN_USER / ADMIN_PASS are accepted as the older spelling)

Exit codes::

    0  fine — an Admin-type credential that can reach the admin endpoints
    2  credential problem — rejected, or not admin-type
    3  could not be checked — transport failure, instance unreachable
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from assignments.auth import AuthError, login_token  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

# Endpoints worth knowing about before planning a change. Each is a read.
PROBES: tuple[tuple[str, str], ...] = (
    ("Metadata", "read the configuration at all"),
    ("Admin/fieldManager/Contact/name", "create and alter fields"),
    ("Role?maxSize=1", "read and alter permissions"),
    ("Team?maxSize=1", "read teams"),
    ("Contact/layout/list", "read and alter screen layouts"),
)


def load_env() -> dict[str, str]:
    """Read ``.env`` directly. These are developer credentials, deliberately
    absent from ``core.config.Settings`` — the application itself must never be
    able to change the CRM's structure."""
    env = dict(os.environ)
    path = REPO / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def credentials(env: dict[str, str]) -> tuple[str, str, str]:
    base = env.get("ESPO_ADMIN_BASE") or env.get("ADMIN_BASE") or ""
    user = env.get("ESPO_ADMIN_USER") or env.get("ADMIN_USER") or ""
    password = env.get("ESPO_ADMIN_PASS") or env.get("ADMIN_PASS") or ""
    return base.rstrip("/"), user, password


async def connect(env: dict[str, str]) -> tuple[EspoClient, dict[str, Any]]:
    """Log in and return the client plus the account's own profile.

    Raises SystemExit with the documented exit codes rather than a traceback,
    because the caller is usually a person trying to find out why something is
    refused and a stack trace answers nothing.
    """
    base, user, password = credentials(env)
    if not (base and user and password):
        print(
            "No admin credential configured. Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER\n"
            "and ESPO_ADMIN_PASS (in .env for crm-test) — see SETUP.md in this\n"
            "skill directory for creating the account itself.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    # Catch an unsubstituted example before spending a login on it. Otherwise the
    # CRM rejects the placeholder as a password and the message sends you hunting
    # for two-factor authentication, which is a genuinely expensive wrong turn.
    placeholders = [
        f"{name}={value}"
        for name, value in (("ESPO_ADMIN_BASE", base), ("ESPO_ADMIN_USER", user),
                            ("ESPO_ADMIN_PASS", password))
        if value.startswith("<") and value.endswith(">")
    ]
    if placeholders:
        print(
            "These are still the example placeholders, not real values:\n  "
            + "\n  ".join(placeholders)
            + "\n\nPut real values in .env rather than on the command line — "
              "that keeps\nthe password out of your shell history and out of "
              "anything this prints.\nSee SETUP.md in this skill directory.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        name, token = await login_token(base, user, password, 30)
    except AuthError as exc:
        print(
            f"{base}: login rejected for {user} ({exc}).\n"
            "If the password is definitely right, check two-factor "
            "authentication — a service account cannot answer a challenge, and "
            "the failure looks identical to a bad password.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except EspoError as exc:
        print(f"{base}: could not be reached ({exc}).", file=sys.stderr)
        raise SystemExit(3) from exc
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    return client, profile


async def probe(client: EspoClient, path: str) -> int:
    resp = await client._request(
        "GET", f"{client._base}/{path}", op=f"probe {path}"
    )
    return resp.status_code


async def cmd_whoami(env: dict[str, str]) -> int:
    base, _, _ = credentials(env)
    client, profile = await connect(env)
    kind = profile.get("type")
    print(f"CRM:  {base}")
    print(f"User: {profile.get('userName')} (type={kind})\n")

    worst = 0
    for path, meaning in PROBES:
        try:
            code = await probe(client, path)
        except EspoError as exc:
            print(f"  ???  {path:44} {exc}")
            worst = max(worst, 3)
            continue
        mark = "ok " if code == 200 else "NO "
        print(f"  {mark} {code}  {path:40} — {meaning}")

    if kind != "admin":
        print(
            f"\nThis is a {kind}-type account, so structural changes will be "
            "refused.\nEspoCRM has no partial administrator: a regular user with "
            "every role\nattached is still 403 on Admin/*. See SETUP.md.",
            file=sys.stderr,
        )
        return 2
    print("\nAdmin-type credential. Structural changes can be applied with this.")
    return worst


async def cmd_probe(env: dict[str, str], path: str) -> int:
    client, profile = await connect(env)
    code = await probe(client, path)
    print(f"{code}  GET {path}   (as {profile.get('userName')}, type={profile.get('type')})")
    if code == 403:
        print(
            "\n403 is a refusal, not an absence. Read it as 'this credential may "
            "not',\nnever as 'this does not exist' — the two are indistinguishable "
            "at the\ntransport layer and confusing them has cost this project real time."
        )
    return 0 if code < 400 else 1


async def cmd_metadata(env: dict[str, str], key: str) -> int:
    client, _ = await connect(env)
    print(json.dumps(await client.metadata(key), indent=2, sort_keys=True))
    return 0


async def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    env = load_env()
    command, rest = args[0], args[1:]
    if command == "whoami":
        return await cmd_whoami(env)
    if command == "probe" and rest:
        return await cmd_probe(env, rest[0])
    if command == "metadata" and rest:
        return await cmd_metadata(env, rest[0])
    print(f"Unknown command {command!r}. Try --help.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
