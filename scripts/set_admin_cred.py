"""Put a CRM administrator credential into an env file, without a shell.

    uv run python scripts/set_admin_cred.py ~/.config/cbm-bma/bma.env

Asks for the user name and the password (the password without echo) and
rewrites the ``ESPO_ADMIN_USER`` and ``ESPO_ADMIN_PASS`` lines of the file,
adding them when absent. Every other line is kept as it is. The file is left
readable by its owner only. Nothing secret is printed.

Exists because the espo-crm-changes skill forbids putting a password on a
command line or reading an env file with a shell (SETUP.md, "Confirm it
worked"): both have leaked a live password here. Letters and digits only,
24 or more characters, for the same reason.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path


def rewrite(text: str, values: dict[str, str]) -> str:
    """The file's text with ``values`` set, each key once, order kept."""
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in values:
            if key in seen:
                continue  # a duplicate line would shadow or be shadowed
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in values.items() if k not in seen)
    return "\n".join(out) + "\n"


def check_password(password: str) -> str:
    """Empty when acceptable, else the reason it is refused."""
    if len(password) < 24:
        return "it is shorter than 24 characters"
    if not password.isascii() or not password.isalnum():
        return "it holds a character other than a letter or a digit"
    return ""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 64
    path = Path(argv[1]).expanduser()
    if not path.is_file():
        print(f"No file at {path}.", file=sys.stderr)
        return 66
    user = input("Administrator user name: ").strip()
    if not user:
        print("No user name given; nothing changed.", file=sys.stderr)
        return 65
    password = getpass.getpass("Password (not shown): ").strip()
    again = getpass.getpass("The same password again: ").strip()
    if password != again:
        print("The two passwords differ; nothing changed.", file=sys.stderr)
        return 65
    reason = check_password(password)
    if reason:
        print(f"Password refused: {reason}. Nothing changed.", file=sys.stderr)
        return 65
    path.write_text(rewrite(path.read_text(), {
        "ESPO_ADMIN_USER": user, "ESPO_ADMIN_PASS": password}))
    os.chmod(path, 0o600)
    print(f"Saved: ESPO_ADMIN_USER={user} and the password ({len(password)} "
          f"characters) in {path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
