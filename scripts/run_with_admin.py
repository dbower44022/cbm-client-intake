"""Run another script with the admin credentials in its environment.

**Never `source .env` in a shell to do this.** A password containing shell
metacharacters gets interpreted rather than assigned, and bash echoes the
fragments it could not parse — which exposed a live credential in this project
on 2026-08-27, in a session that had warned about the same hazard an hour
earlier. This launcher reads ``.env`` with a parser, puts the values straight
into the child process's environment, and never renders them.

It also supplies the older ``ADMIN_*`` spelling that
``scripts/migrate_*_schema.py`` expect, so those run unchanged.

Usage::

    PYTHONPATH=. uv run python \\
      scripts/run_with_admin.py \\
      scripts/migrate_grant_schema.py            # add --apply as needed
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from espo_admin import credentials, load_env  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    base, user, password = credentials(load_env())
    if not (base and user and password):
        print("No admin credential in .env — see SETUP.md.", file=sys.stderr)
        return 2
    if password.startswith("<") and password.endswith(">"):
        print("ESPO_ADMIN_PASS in .env is still the example placeholder.",
              file=sys.stderr)
        return 2

    env = dict(os.environ)
    env.update({
        "ESPO_ADMIN_BASE": base, "ESPO_ADMIN_USER": user, "ESPO_ADMIN_PASS": password,
        "ADMIN_BASE": base, "ADMIN_USER": user, "ADMIN_PASS": password,
        "PYTHONPATH": str(REPO),
    })
    # No shell: the arguments go to exec directly, so nothing can interpret,
    # word-split or echo the password.
    return subprocess.call([sys.executable, *sys.argv[1:]], env=env, cwd=REPO)


if __name__ == "__main__":
    raise SystemExit(main())
