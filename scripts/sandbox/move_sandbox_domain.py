"""Move the Business Mentors Association's invented addresses to ``bma.test``.

Association ruling 79 (11-17-26, amending ruling 77): the training data's
invented addresses and sign-ins move from ``sandbox.mentorsassociation.org`` to
``bma.test`` — a name reserved for testing, which can never have a mailbox —
so a trainee signs in as ``joe.mentor@bma.test``. Two sign-ins also take a
first.last name: ``tt`` becomes ``tommy.tranell`` and ``mentoradmin`` becomes
``mentor.admin`` (``targets.py``).

What it changes, found by a field survey of the CRM on 11-17-26:

* **Sign-ins** (``User``): the user name and email address. Passwords,
  teams and roles are untouched. Only an administrator may rename a sign-in,
  so this runs as the CRM administrator (``ESPO_ADMIN_*`` in ``--env-file``).
* **Email address fields** on Contact, Company (Account) and User: every
  address in ``emailAddressData``, keeping which one is primary.
* **Text fields** that carry an address or the domain in their text:
  ``CMentorProfile.cbmEmail``, ``CProspect.email``, ``Account.website``,
  ``CCommunication`` from, to and source mailbox, ``CActionLog`` name, summary
  and details, and stream posts (``Note.post``).

What it does not change: the CRM's own address list (``EmailAddress``) keeps
a row for each old address, linked to nothing once its owner moves. Nothing
reads those rows; the mailbox-less old domain stays harmless.

The applications' own setting must move in the same sitting: System Settings
→ Email → *Sandbox address domain* = ``bma.test``.

Refuses every CRM but the Association's. Read-only unless ``--apply``. With
``--apply --one`` it moves a single Contact and reads it back, to prove the
CRM accepts a ``.test`` address before the rest is moved. Safe to rerun: a
second dry run must report nothing left.

    uv run python scripts/sandbox/move_sandbox_domain.py --env-file ~/.config/cbm-bma/bma.env
    uv run python scripts/sandbox/move_sandbox_domain.py --env-file ~/.config/cbm-bma/bma.env --apply --one
    uv run python scripts/sandbox/move_sandbox_domain.py --env-file ~/.config/cbm-bma/bma.env --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import targets  # noqa: E402  (puts the repository and scripts/ on the path)

from core.espo import EspoError  # noqa: E402
from espo_admin import connect  # noqa: E402

OLD = "sandbox.mentorsassociation.org"
ASSOCIATION = "crm.businessmentorsassociation.org"

#: Email-type fields: every address in ``emailAddressData`` moves.
EMAIL_FIELDS: tuple[tuple[str, str], ...] = (
    ("User", "emailAddress"), ("Contact", "emailAddress"), ("Account", "emailAddress"),
)
#: Plain text fields: the old domain is replaced wherever it appears.
TEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("User", "userName"),
    ("CMentorProfile", "cbmEmail"),
    ("CProspect", "email"),
    ("Account", "website"),
    ("CCommunication", "fromAddress"),
    ("CCommunication", "toAddresses"),
    ("CCommunication", "sourceMailbox"),
    ("CActionLog", "name"),
    ("CActionLog", "summary"),
    ("CActionLog", "details"),
    ("Note", "post"),
)
_PAGE = 200  # a list maxSize over 200 is a 403 (root CLAUDE.md)


def move_text(value: str, new: str, renames: dict[str, str]) -> str:
    """``value`` with the old domain replaced, and a renamed sign-in's old
    address replaced by its new one."""
    for old_local, new_local in renames.items():
        # The whole local part only: "matt@" must not become "matommy.tranell@".
        value = re.sub(rf"(?<![\w.+-]){re.escape(old_local)}@{re.escape(OLD)}",
                       f"{new_local}@{new}", value)
    return value.replace(OLD, new)


def move_address(address: str, new: str, renames: dict[str, str]) -> str:
    return move_text(address, new, renames)


async def _matching(client: Any, entity: str, field: str) -> list[dict[str, Any]]:
    where = [{"type": "like", "attribute": field, "value": f"%{OLD}%"}]
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        env = await client.list(entity, where=where, select=f"id,name,{field}",
                                max_size=_PAGE, offset=offset)
        page = env.get("list", []) or []
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


async def plan(client: Any, new: str, renames: dict[str, str]) -> list[tuple[str, str, dict, str]]:
    """Every change: (entity, id, payload, a one-line description)."""
    changes: dict[tuple[str, str], tuple[dict, list[str]]] = {}

    def add(entity: str, rid: str, payload: dict, line: str) -> None:
        pay, lines = changes.setdefault((entity, rid), ({}, []))
        pay.update(payload)
        lines.append(line)

    for entity, field in EMAIL_FIELDS:
        for row in await _matching(client, entity, field):
            rec = await client.get(entity, row["id"], select="id,emailAddressData")
            data = rec.get("emailAddressData") or []
            moved = [{**d, "emailAddress": move_address(d.get("emailAddress") or "", new, renames)}
                     for d in data]
            if moved != data:
                primary = next((d["emailAddress"] for d in moved if d.get("primary")),
                               moved[0]["emailAddress"] if moved else "")
                add(entity, row["id"], {"emailAddressData": moved, "emailAddress": primary},
                    f"{field}: {row.get(field)} -> {primary}")
    for entity, field in TEXT_FIELDS:
        try:
            rows = await _matching(client, entity, field)
        except EspoError as exc:
            print(f"! {entity}.{field} could not be searched ({exc}) — skipped")
            continue
        for row in rows:
            old = row.get(field) or ""
            if not isinstance(old, str):
                continue
            value = move_text(old, new, renames)
            if value != old:
                shown = (f"{old} -> {value}" if len(old) < 90
                         else f"{old.count(OLD)} mention(s) moved")
                add(entity, row["id"], {field: value}, f"{field}: {shown}")
    return [(e, rid, pay, f"{e} {rid}: " + "; ".join(lines))
            for (e, rid), (pay, lines) in changes.items()]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--one", action="store_true",
                        help="with --apply: move one Contact, read it back, and stop")
    parser.add_argument("--all", action="store_true", help="list every change, not a sample")
    targets.add_env_file_argument(parser)
    args = parser.parse_args()

    env = targets.load_env_file(args.env_file)
    client, me = await connect(env)
    base = (env.get("ESPO_ADMIN_BASE") or env.get("ADMIN_BASE") or "").rstrip("/")
    target = targets.resolve(base)
    if target is None or target.crm_host != ASSOCIATION:
        print(f"REFUSING: {base!r} is not the Business Mentors Association's CRM.")
        return 2
    if me.get("type") != "admin":
        print("Renaming a sign-in needs an Admin-type account.")
        return 2
    new = target.email_domain
    renames = dict(target.login_renames)
    print(f"{target.label} ({base}): {OLD} -> {new} — "
          f"{'APPLY' if args.apply else 'dry run'}\n")

    changes = await plan(client, new, renames)
    counts: dict[str, int] = {}
    for entity, *_ in changes:
        counts[entity] = counts.get(entity, 0) + 1
    for entity, n in sorted(counts.items()):
        print(f"  {entity}: {n} record(s)")
    print(f"  total: {len(changes)} record(s)\n")

    if args.apply and args.one:
        pick = next((c for c in changes if c[0] == "Contact"), None)
        if pick is None:
            print("No Contact left to move.")
            return 0
        entity, rid, payload, line = pick
        print(line)
        await client.update(entity, rid, payload)
        back = await client.get(entity, rid, select="id,emailAddress,emailAddressData")
        ok = back.get("emailAddress") == payload["emailAddress"]
        print(f"read back: {back.get('emailAddress')} — {'OK' if ok else 'NOT STORED'}")
        return 0 if ok else 1

    shown = changes if args.all else [c for c in changes if c[0] == "User"] + [
        c for c in changes if c[0] != "User"][:12]
    for *_, line in shown:
        print(" ", line)
    if not args.all and len(shown) < len(changes):
        print(f"  … and {len(changes) - len(shown)} more (--all lists every one)")

    if not args.apply:
        print("\nDry run: nothing written. Add --apply to write.")
        return 0
    failed = 0
    for entity, rid, payload, line in changes:
        try:
            await client.update(entity, rid, payload)
        except EspoError as exc:
            failed += 1
            print(f"! refused: {line} ({exc})")
    print(f"\nMoved {len(changes) - failed} of {len(changes)} record(s). "
          "Run again without --apply: it must report 0.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
