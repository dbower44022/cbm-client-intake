"""Build Chapter News in the CRM: ``CChapterNews`` and ``CChapterNewsReceipt``.

prds/home-page-plan.md § 6.4 (phase 5); handoff
``cchapternews-entities-crm-handoff.md``. Two stages, both idempotent, both a
dry run unless ``--apply``:

1. **The schema**, from ``crm-plans/chapter-news.json`` through the plan
   applier (``scripts/apply_crm_plan.py``), with one addition the plan file
   cannot hold: ``CChapterNews.audienceTeams`` offers the CRM's own team
   names, read at run time. A team the field does not offer yet is added;
   nothing is ever removed. A team renamed later needs this script run again
   (and the old name stays on the items that carry it).
2. **The grants**: the org-wide API key's role (``CustomAppAPIRole``)
   creates, reads and edits both record types. Members read news and write
   their receipts under that key, and publishers write items under it, gated
   by the publisher team in the application (decision 3 of the phases 5 to 7
   prompt, 11-20-26). No member or publisher role changes. Merge-only.

**Only the Business Mentors Association's CRM** (Doug's authorization,
11-20-26): the script refuses any other address, whatever the credential file
says. Extending it to crm-test, Cleveland's production or a chapter needs
Doug's ruling and an edit to ``ALLOWED`` below. Credentials come from
``--env-file``, read with a parser and never printed::

    PYTHONPATH=. uv run python scripts/migrate_chapter_news_schema.py \\
        --env-file ~/.config/cbm-bma/bma.env                       # dry run
    ... --apply --expect <fingerprint from the dry run>              # apply
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from apply_crm_plan import Applier  # noqa: E402
from espo_admin import connect, credentials  # noqa: E402
from sandbox.targets import load_env_file, resolve  # noqa: E402

PLAN = REPO / "crm-plans" / "chapter-news.json"
NEWS = "CChapterNews"
RECEIPT = "CChapterNewsReceipt"
AUDIENCE = "audienceTeams"
#: The CRMs this script may write to (by the training-system label).
ALLOWED = ("Business Mentors Association",)
API_ROLE = "CustomAppAPIRole"
GRANTS: dict[str, dict[str, str]] = {
    NEWS: {"create": "yes", "read": "all", "edit": "all"},
    RECEIPT: {"create": "yes", "read": "all", "edit": "all"},
}
LEVEL_RANK = {"no": 0, "not-set": 0, "own": 1, "team": 2, "all": 3, "yes": 3}


def refusal_for(base: str) -> str | None:
    """Why this CRM may not be written to, or None when it may."""
    target = resolve(base)
    if target is None or target.label not in ALLOWED:
        return (f"REFUSING: {base or '(no CRM address)'!r} is not "
                f"{' or '.join(ALLOWED)}'s CRM. Chapter News is built there only "
                "(Doug, 11-20-26).")
    return None


def plan_with_teams(plan: dict[str, Any], teams: list[str],
                    offered: list[str] | None) -> dict[str, Any]:
    """The plan, with ``audienceTeams`` offering every team.

    ``offered`` is what the live field already offers (None when the field
    does not exist): a new field is created with every team; an existing one
    gains only the teams it lacks, through ``enumOptions``, never losing one."""
    out = copy.deepcopy(plan)
    names = sorted({t for t in teams if t})
    for field in out.get("fields", []):
        if field["entity"] == NEWS and field["name"] == AUDIENCE:
            field["options"] = names
    if offered is not None:
        missing = [t for t in names if t not in offered]
        if missing:
            out.setdefault("enumOptions", []).append(
                {"entity": NEWS, "field": AUDIENCE, "add": missing})
    return out


def _rank(level: Any) -> int:
    return LEVEL_RANK.get(level, 0) if isinstance(level, str) else 0


async def grants(client, apply: bool, present: set[str]) -> tuple[list[str], list[str], list[str]]:
    done: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    page = await client.list("Role", select="id,name", max_size=50,
                             where=[{"type": "equals", "attribute": "name", "value": API_ROLE}])
    row = next((r for r in page.get("list") or [] if r.get("name") == API_ROLE), None)
    if row is None:
        return done, skipped, [f"role '{API_ROLE}' does not exist on this CRM"]
    role = await client.get("Role", row["id"])
    data: dict[str, Any] = dict(role.get("data") or {})
    changed = False
    for entity, wanted in GRANTS.items():
        current = data.get(entity) if isinstance(data.get(entity), dict) else {}
        new_map = dict(current)
        changes = []
        for action, level in wanted.items():
            if _rank(current.get(action)) >= _rank(level):
                skipped.append(f"{API_ROLE}: {entity}.{action} already '{current.get(action)}'")
                continue
            new_map[action] = level
            changes.append(f"{action}: {current.get(action, '(not set)')} -> {level}")
        if not changes:
            continue
        for action in ("create", "read", "edit", "delete", "stream"):
            new_map.setdefault(action, "no")
        label = f"{API_ROLE}: {entity} {{{', '.join(changes)}}}"
        if not apply or entity not in present:
            done.append(f"WOULD set {label}")
            continue
        data[entity] = new_map
        changed = True
        done.append(f"set {label}")
    if changed:
        await client.update("Role", role["id"], {"data": data})
        stored = (await client.get("Role", role["id"])).get("data") or {}
        for entity, wanted in GRANTS.items():
            short = [a for a, lv in wanted.items()
                     if _rank((stored.get(entity) or {}).get(a)) < _rank(lv)]
            if short:
                failed.append(f"{API_ROLE}: {entity} read-back is missing {short}")
            else:
                done.append(f"verified {API_ROLE}: {entity} {stored.get(entity)}")
        resp = await client._request("POST", f"{client._base}/Admin/rebuild",
                                     op="rebuild", json_body={})
        (done if resp.status_code < 300 else failed).append(f"rebuild -> HTTP {resp.status_code}")
    return done, skipped, failed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", required=True,
                        help="the Association's credential file, ~/.config/cbm-bma/bma.env")
    parser.add_argument("--apply", action="store_true", help="make the changes")
    parser.add_argument("--expect", metavar="FINGERPRINT",
                        help="refuse to apply if the schema plan moved since the dry run")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    base, _, _ = credentials(env)
    why = refusal_for(base)
    if why:
        print(why, file=sys.stderr)
        return 2
    client, profile = await connect(env)
    if profile.get("type") != "admin":
        print(f"{profile.get('userName')} is type={profile.get('type')}: the build needs "
              "an Admin-type account.", file=sys.stderr)
        return 2
    print(f"CRM:  {base}\nUser: {profile.get('userName')} (type=admin)")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN - nothing will change'}\n")

    teams = [t["name"] for t in (await client.list("Team", select="id,name", max_size=200))
             .get("list") or []]
    resp = await client._request("GET", f"{client._base}/Admin/fieldManager/{NEWS}/{AUDIENCE}",
                                 op="read audienceTeams")
    offered = list((resp.json() or {}).get("options") or []) if resp.status_code == 200 else None
    plan = plan_with_teams(json.loads(PLAN.read_text(encoding="utf-8")), teams, offered)

    app = Applier(client, plan, apply=False)
    await app.run()
    print_rows = lambda title, rows, mark: rows and print(  # noqa: E731
        f"{title}:\n" + "\n".join(f"  {mark} {r}" for r in rows) + "\n")
    if args.apply:
        if args.expect and app.fingerprint() != args.expect:
            print(f"The schema plan has moved: expected {args.expect}, now {app.fingerprint()}. "
                  "Nothing was changed; run the dry run again.", file=sys.stderr)
            return 2
        app = Applier(client, plan, apply=True)
        await app.run()
    print("== The schema ==")
    print_rows("CHANGED" if args.apply else "WOULD CHANGE", app.actions, "-")
    print_rows("ALREADY CORRECT", app.skipped, "=")
    print_rows("FAILED", app.failed, "!")

    present = {e for e in (NEWS, RECEIPT)
               if isinstance(await client.metadata(f"entityDefs.{e}"), dict)}
    done, skipped, failed = await grants(client, args.apply, present)
    print("== The API role's grants ==")
    print_rows("CHANGED" if args.apply else "WOULD CHANGE", done, "-")
    print_rows("ALREADY CORRECT", skipped, "=")
    print_rows("FAILED", failed, "!")
    if not args.apply:
        print(f"Dry run only. Schema plan fingerprint: {app.fingerprint()}")
    return 1 if (app.failed or failed) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
