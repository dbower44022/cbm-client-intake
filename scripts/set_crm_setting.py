"""Set one EspoCRM administrator setting through the API, and read it back.

Written for the mentor login integrity build (step 0,
``crm-history-settings-crm-handoff.md`` § 1): keep Action History for 30 days
instead of 15. It works for any setting an administrator may change through
``PUT /Settings`` (EspoCRM calls these *admin items*).

Usage, from the repository root, through the launcher that parses ``.env``
(never ``source`` it)::

    # dry run (default): reads the current value, prints the planned change
    PYTHONPATH=. uv run python scripts/run_with_admin.py \\
      scripts/set_crm_setting.py cleanupActionHistoryPeriod "30 days"

    # apply: writes ONLY that key, then reads it back
    ... scripts/set_crm_setting.py cleanupActionHistoryPeriod "30 days" --apply

    # another chapter's CRM: name its credential file
    PYTHONPATH=. uv run python scripts/run_with_admin.py \\
      --env ~/.config/cbm-boston/boston.env \\
      scripts/set_crm_setting.py cleanupActionHistoryPeriod "30 days"

    # a boolean, number or list: parse the value as JSON
    ... scripts/set_crm_setting.py someBooleanSetting true --json

**Trap — the value is a PHP date phrase.** ``cleanupActionHistoryPeriod`` is
fed to PHP's date parser, so ``30 days`` works; ``30`` alone, or ``1 month``
with a trailing space, may not. The script compares the read-back exactly, so
a value the CRM normalised or refused shows up as a mismatch.

**A name the CRM did not show is refused, never written.** ``GET /Settings``
returns the admin items. If the name is absent it is either misspelled or a
*system item* the API cannot set — ``authApiUserLogDisabled`` is one; it is a
line in the server's ``data/config.php`` and goes through
``scripts/set_authlog_switch.sh`` instead.

The target is checked the same way as ``scripts/apply_crm_plan.py``: an apply
against anything but crm-test needs ``--production``, the acknowledgement that
crm-test went first.

Credentials come from ``ESPO_ADMIN_BASE`` / ``ESPO_ADMIN_USER`` /
``ESPO_ADMIN_PASS`` (supplied by ``run_with_admin.py``) and are never printed;
only the CRM's host is.

Exit codes::

    0  done, already set, or a clean dry run
    1  the read-back did not match what was written
    2  refused: unknown setting name, bad value, credential or target problem
    3  could not be completed: transport failure or an HTTP error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.espo import EspoError  # noqa: E402
from espo_admin import connect, credentials, load_env  # noqa: E402


def _show(value: Any) -> str:
    """Render a value unambiguously: strings quoted, so a trailing space shows."""
    return json.dumps(value, ensure_ascii=False)


async def read_settings(client: Any) -> dict[str, Any]:
    resp = await client._request(
        "GET", f"{client._base}/Settings", op="read Settings"
    )
    if resp.status_code != 200:
        raise EspoError(f"GET /Settings answered HTTP {resp.status_code}")
    body = resp.json()
    if not isinstance(body, dict):
        raise EspoError("GET /Settings did not return an object")
    return body


async def set_setting(client: Any, name: str, value: Any, *, apply: bool) -> int:
    """Plan, and with ``apply`` make and verify, one setting change.

    Returns the process exit code. Writes nothing unless ``apply`` is true,
    the name is present in ``GET /Settings``, and the value differs."""
    settings = await read_settings(client)
    if name not in settings:
        print(
            f"Refused: {name!r} is not among the settings this CRM returns.\n"
            "Either the name is wrong (names are case-sensitive), or it is a\n"
            "system item the API cannot set — authApiUserLogDisabled is one;\n"
            "use scripts/set_authlog_switch.sh for that. Nothing was written.",
            file=sys.stderr,
        )
        return 2

    current = settings[name]
    print(f"Setting: {name}")
    print(f"Current: {_show(current)}")
    print(f"Wanted:  {_show(value)}")
    if current == value:
        print("\nAlready set. Nothing to do; nothing was written.")
        return 0

    if not apply:
        print(f"\nPlan: PUT /Settings {{{_show(name)}: {_show(value)}}}")
        print("Dry run — nothing was written. Add --apply to make the change.")
        return 0

    resp = await client._request(
        "PUT", f"{client._base}/Settings", op=f"write setting {name}",
        json_body={name: value},
    )
    if resp.status_code != 200:
        print(f"PUT /Settings answered HTTP {resp.status_code}. "
              "Reading back to see what stands.", file=sys.stderr)

    after = (await read_settings(client)).get(name)
    print(f"Read back: {_show(after)}")
    if after != value:
        print(f"\nMISMATCH: wrote {_show(value)}, the CRM now holds "
              f"{_show(after)}.\nCheck the value's format (a PHP date phrase "
              "for the clean-up periods).", file=sys.stderr)
        return 1
    print("\nDone: the read-back matches.")
    return 0


def parse_value(raw: str, as_json: bool) -> Any:
    if not as_json:
        return raw
    return json.loads(raw)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set one EspoCRM admin setting via PUT /Settings, read back.")
    parser.add_argument("name", help="the setting's name, e.g. cleanupActionHistoryPeriod")
    parser.add_argument("value", help='the value, e.g. "30 days"')
    parser.add_argument("--json", action="store_true",
                        help="parse the value as JSON (booleans, numbers, lists)")
    parser.add_argument("--apply", action="store_true",
                        help="make the change (default is a dry run)")
    parser.add_argument("--production", action="store_true",
                        help="acknowledge that the target is not crm-test")
    args = parser.parse_args(argv)

    try:
        value = parse_value(args.value, args.json)
    except json.JSONDecodeError as exc:
        print(f"--json given, but {args.value!r} is not JSON: {exc}", file=sys.stderr)
        return 2

    env = load_env()
    base, _, _ = credentials(env)
    host = urlparse(base).hostname or base
    if args.apply and "crm-test" not in base and not args.production:
        print(
            f"Target is {host}, which is not crm-test.\n"
            "Changes go to crm-test first, always. If crm-test is done and this\n"
            "is the intended CRM, pass --production.",
            file=sys.stderr,
        )
        return 2

    try:
        client, profile = await connect(env)
    except SystemExit as exc:
        return int(exc.code or 2)
    if profile.get("type") != "admin":
        print(f"{profile.get('userName')} is type={profile.get('type')}. "
              "Settings need an Admin-type account — see SETUP.md.", file=sys.stderr)
        return 2

    print(f"CRM:  {host}")
    print(f"User: {profile.get('userName')} (type=admin)")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN — nothing will change'}\n")
    try:
        return await set_setting(client, args.name, value, apply=args.apply)
    except EspoError as exc:
        print(f"Could not complete: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
