"""Re-encrypt every stored secret with the newest APP_ENCRYPTION_KEY.

OPEN-ITEMS #33, Doug's option B (11-04-26). Run INSIDE the deployment's web
container, while ``APP_ENCRYPTION_KEY`` holds two keys, newest first
(``NEW,OLD``)::

    cd /app && PYTHONPATH=. .venv/bin/python scripts/rotate_encryption_key.py          # dry run
    cd /app && PYTHONPATH=. .venv/bin/python scripts/rotate_encryption_key.py --apply  # rotate

(``scripts/rotate_encryption_key.sh`` and ``… apply`` are the short forms.)

What it touches — every place the application stores ciphertext:

* ``app_setting.value`` and ``app_setting.previous_value`` where ``encrypted``
  (the secrets saved at /setup; the change history stores "(secret set)", not
  the secret);
* ``app_config.value_encrypted`` (Email Setup's Google service-account blob);
* ``mailing_connection.access_token`` / ``refresh_token`` (Constant Contact).

The dry run counts each value as already on the newest key, on an older key
(to re-encrypt), or unreadable with every key given (left alone and named —
it was written under a key that is not in the setting). ``--apply`` re-encrypts
the older-key values in ONE transaction and reads every one back. It never
prints a secret. Safe to run again: a second run finds nothing to do.

Afterwards set ``APP_ENCRYPTION_KEY`` to the new key alone and redeploy.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, select, update  # noqa: E402

from core.app_config import app_config  # noqa: E402
from core.config import Settings  # noqa: E402
import hashlib  # noqa: E402

from core.crypto import CryptoError, SecretCipher, split_keys  # noqa: E402
from core.mailing import mailing_connection  # noqa: E402
from core.settings_store import app_setting  # noqa: E402
from core.store import make_async_engine  # noqa: E402

# (table, key column, [encrypted columns], only rows where this column is true)
TARGETS = [
    (app_setting, "key", ["value", "previous_value"], "encrypted"),
    (app_config, "key", ["value_encrypted"], None),
    (mailing_connection, "id", ["access_token", "refresh_token"], None),
]


def classify(cipher: SecretCipher, token):
    """'current', 'old', 'empty' or 'unreadable' — never the plaintext."""
    if token is None or token == "":
        return "empty"
    if cipher.is_current(token):
        return "current"
    try:
        cipher.decrypt(token)
        return "old"
    except CryptoError:
        return "unreadable"


async def main() -> int:
    apply = "--apply" in sys.argv[1:]
    settings = Settings()
    if not settings.database_url:
        print("DATABASE_URL is not set — run this inside the web container.")
        return 2
    try:
        cipher = SecretCipher(settings.app_encryption_key)
    except CryptoError as exc:
        print(f"APP_ENCRYPTION_KEY: {exc}")
        return 2
    prints = [hashlib.sha256(k.encode()).hexdigest()[:8] for k in split_keys(settings.app_encryption_key)]
    print(f"Keys in APP_ENCRYPTION_KEY: {cipher.key_count}, fingerprints {', '.join(prints)} "
          "(the first is the one values move to)")
    if cipher.key_count < 2 and apply:
        print("Only one key is set, so there is nothing to rotate to. Set NEW,OLD first.")
        return 2
    print("Mode:", "APPLY" if apply else "DRY RUN — nothing will change")

    engine = make_async_engine(settings.database_url)
    totals = {"current": 0, "old": 0, "unreadable": 0, "empty": 0}
    unreadable: list[str] = []
    changes: list[tuple] = []   # (table, keycol, keyval, {col: new_token})
    try:
        async with engine.begin() as conn:
            names = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
            for table, keycol, cols, flag in TARGETS:
                if table.name not in names:
                    print(f"  {table.name}: no such table here — skipped")
                    continue
                q = select(table.c[keycol], *[table.c[c] for c in cols])
                if flag:
                    q = q.where(table.c[flag].is_(True))
                rows = (await conn.execute(q)).all()
                counts = {"current": 0, "old": 0, "unreadable": 0, "empty": 0}
                for row in rows:
                    keyval = row[0]
                    new: dict[str, str] = {}
                    for i, col in enumerate(cols, start=1):
                        kind = classify(cipher, row[i])
                        counts[kind] += 1
                        if kind == "old":
                            new[col] = cipher.rotate(row[i])
                        elif kind == "unreadable":
                            unreadable.append(f"{table.name}.{col} [{keycol}={keyval}]")
                    if new:
                        changes.append((table, keycol, keyval, new))
                for k, v in counts.items():
                    totals[k] += v
                print(f"  {table.name}: {len(rows)} row(s) — {counts['current']} on the newest key, "
                      f"{counts['old']} to re-encrypt, {counts['unreadable']} unreadable, "
                      f"{counts['empty']} empty")

            if apply and changes:
                for table, keycol, keyval, new in changes:
                    await conn.execute(update(table).where(table.c[keycol] == keyval).values(**new))
                # Read every changed value back inside the transaction.
                for table, keycol, keyval, new in changes:
                    row = (await conn.execute(
                        select(*[table.c[c] for c in new]).where(table.c[keycol] == keyval)
                    )).one()
                    for i, col in enumerate(new):
                        if not cipher.is_current(row[i]):
                            raise RuntimeError(f"{table.name}.{col} [{keycol}={keyval}] did not read back on the newest key")
    finally:
        await engine.dispose()

    print()
    print(f"Totals: {totals['current']} on the newest key, {totals['old']} "
          f"{'re-encrypted' if apply else 'to re-encrypt'}, {totals['unreadable']} unreadable, "
          f"{totals['empty']} empty.")
    for u in unreadable:
        print(f"  UNREADABLE with every key given (left as it is): {u}")
    if apply:
        print("Done, in one transaction, every value read back on the newest key."
              if changes else "Nothing to re-encrypt.")
        print("Next: set APP_ENCRYPTION_KEY to the new key alone and redeploy.")
    else:
        print("Dry run only. Re-run with --apply to re-encrypt.")
    return 0 if not unreadable else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
