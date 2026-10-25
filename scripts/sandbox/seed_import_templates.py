"""Give the training sandbox its demo import template — the fifth seeder.

The import tool's templates (build plan § 7e.7, M4) live in the APPLICATION
database, not the CRM: ``import_template`` is in ``core.sandbox_reset.RESET_TABLES``,
so the app half of the nightly reset empties it whatever the CRM baseline
holds. The worker puts the one demo template back straight after that reset
(``campaigns/sandbox_demo.restore_demo_template``), and ``/setup`` → Operations
→ *Sandbox demo campaign links* does the same on demand. This script is the
same restore from a shell, for the morning the baseline is recaptured — run it
wherever the application database is reachable (the deployed container's
console, or a machine on the database's trusted-source list), with
``DATABASE_URL`` in the environment or in ``.env``. It never reaches the CRM.

The template is *State filing — Ohio Secretary of State*: the columns the demo
leads were made from (an entity name, a charter number, the principal office
address, the statutory agent's name split into first and last, the agent's
phone and email, the web site; the filing type ignored), entering Qualified
on the filing filter's verdict. Idempotent by name. Read-only unless
``--apply``. Refuses any CRM address but crm-test, by the reset's own check.

    uv run python scripts/sandbox/seed_import_templates.py
    uv run python scripts/sandbox/seed_import_templates.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from campaigns import sandbox_demo as demo  # noqa: E402
from core.sandbox_reset import SANDBOX_URL_MARKER  # noqa: E402
from espo_admin import load_env  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="actually write")
    args = parser.parse_args()
    env = load_env()
    base = (env.get("ESPO_BASE_URL") or "").lower()
    if SANDBOX_URL_MARKER not in base:
        print(f"REFUSING: ESPO_BASE_URL is not the sandbox ({base!r}).")
        return 2
    database_url = env.get("DATABASE_URL") or ""
    if not database_url:
        print("No DATABASE_URL: the templates live in the application database, which this machine cannot see. "
              "Run this in the deployed container's console, or use /setup → Operations → Sandbox demo campaign links.")
        return 2
    from campaigns.store import CampaignStore

    store = CampaignStore(database_url)
    try:
        present = any(t.get("name") == demo.DEMO_TEMPLATE["name"] for t in await store.list_templates())
        print(f"Import template \"{demo.DEMO_TEMPLATE['name']}\": " + ("already present." if present else "would create."))
        if not args.apply:
            print("Re-run with --apply.")
            return 0
        totals = await demo.restore_demo_template(store)
        print(f"{totals['created']} created, {totals['present']} present.")
        return 0
    finally:
        await store.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
