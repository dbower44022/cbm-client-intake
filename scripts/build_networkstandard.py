"""Build ``CNetworkStandard`` on this deployment's CRM — the whole of
``cnetworkstandard-entity-crm-handoff.md`` as one idempotent script.

Covers every step of the handoff: the entity and its five fields (§ 1–2, read
from ``scripts/plans/cnetworkstandard.json``, the plan crm-test was built
from), the § 4 role grant that makes the entity visible to the application, the
§ 1 no-navigation-tab rule, and the § 5 verification — run as the **org-wide
API key**, because an admin check proves nothing about a grant.

Self-contained on purpose: the ``.claude`` skill directory that holds the
general-purpose applier is gitignored and so never reaches the deployed image,
and production's admin credential exists only inside the deployed web
container. This script uses only modules that ship in the image.

Dry run by default. ``--apply`` writes; ``--expect <fingerprint>`` refuses to
apply if the plan moved since the dry run that printed it; ``--production``
acknowledges a non-crm-test target. Everything already correct is skipped, so
running it against a finished instance is a no-op that doubles as verification.

Production run, inside the deployed **web** container (Sunday slot)::

    ESPO_ADMIN_BASE="$ESPO_BASE_URL" ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME" \
    ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD" PYTHONPATH=/app \
      .venv/bin/python scripts/build_networkstandard.py                # dry run
    ...same... scripts/build_networkstandard.py --apply --production --expect <fp>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

def _repo_root() -> Path:
    """Next to this script in the repo; /app when run from a copy in a
    container (the rehearsal path uploads it to /tmp); else the cwd."""
    for cand in (Path(__file__).resolve().parents[1], Path("/app"), Path.cwd()):
        if (cand / "scripts" / "plans" / "cnetworkstandard.json").exists():
            return cand
    raise SystemExit("cannot find scripts/plans/cnetworkstandard.json")


REPO = _repo_root()
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

from assignments.auth import AuthError, login_token  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

PLAN_PATH = REPO / "scripts" / "plans" / "cnetworkstandard.json"
ENTITY = "CNetworkStandard"
ROLE_DEFAULT = "CustomAppAPIRole"
# What § 4 grants: the app READS the stamp; only the applier (admin) writes it.
GRANT = {"create": "no", "read": "all", "edit": "no", "delete": "no", "stream": "no"}


def _env() -> dict[str, str]:
    """Environment first; ``.env`` fills gaps for a laptop run against crm-test.
    Parsed as text, never sourced — a shell interprets password punctuation."""
    env = dict(os.environ)
    dotenv = REPO / ".env"
    if dotenv.exists():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


class Builder:
    def __init__(self, client: EspoClient, plan: dict, apply: bool) -> None:
        self.c = client
        self.plan = plan
        self.apply = apply
        self.actions: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    async def _req(self, method: str, path: str, *, params=None, body=None) -> httpx.Response:
        return await self.c._request(
            method, f"{self.c._base}/{path}", op=f"{method} {path}",
            params=params, json_body=body,
        )

    async def _meta(self, key: str) -> Any:
        """A missing metadata key answers HTTP 200 with an EMPTY body (measured
        on crm-test 2026-08-27), which resp.json() chokes on — so read it here."""
        resp = await self._req("GET", "Metadata", params={"key": key})
        if resp.status_code >= 400:
            raise EspoError(f"metadata {key} failed: HTTP {resp.status_code}")
        return resp.json() if resp.content else None

    async def _write(self, method: str, path: str, body: dict, what: str) -> bool:
        if not self.apply:
            self.actions.append(what)
            return True
        resp = await self._req(method, path, body=body)
        if resp.status_code < 300:
            self.actions.append(what)
            return True
        self.failed.append(f"{what} -> HTTP {resp.status_code} {resp.text[:200]}")
        return False

    # --- § 1: the entity ---------------------------------------------------
    async def entity(self) -> bool:
        """Returns True when the entity newly needs creating (rebuild owed)."""
        spec = dict(self.plan["entities"][0])
        given = spec["name"]                       # 'NetworkStandard', unprefixed
        assert "C" + given == ENTITY, "plan and script disagree on the name"
        if await self._meta(f"scopes.{ENTITY}"):
            self.skipped.append(f"entity {ENTITY} exists")
            return False
        if await self._meta("scopes.CCNetworkStandard"):
            self.failed.append(
                "CCNetworkStandard exists — a previous build typed the C. "
                "Delete it in Entity Manager and re-run; do not rename around it.")
            return False
        return await self._write(
            "POST", "EntityManager/action/createEntity", spec,
            f"create entity {ENTITY} (typed '{given}', type {spec.get('type')})")

    async def rebuild(self) -> None:
        """A new entity is invisible to the field endpoints until a rebuild."""
        if not self.apply:
            return
        resp = await self._req("POST", "Admin/rebuild")
        if resp.status_code >= 300:
            self.failed.append(f"rebuild -> HTTP {resp.status_code}")

    # --- § 2: the fields ---------------------------------------------------
    async def fields(self, entity_pending: bool) -> None:
        for spec in self.plan.get("fields", []):
            spec = dict(spec)
            spec.pop("entity", None)
            name = spec["name"]                    # custom entity: stored as typed
            what = f"create field {ENTITY}.{name} ({spec.get('type')})"
            if entity_pending and not self.apply:
                self.actions.append(what)
                continue
            resp = await self._req("GET", f"Admin/fieldManager/{ENTITY}/{name}")
            if resp.status_code == 200:
                self.skipped.append(f"field {ENTITY}.{name} exists")
                continue
            await self._write("POST", f"Admin/fieldManager/{ENTITY}", spec, what)

    # --- § 4: the role grant ------------------------------------------------
    async def role_grant(self, role_name: str) -> None:
        resp = await self._req("GET", "Role", params={"maxSize": 200})
        if resp.status_code >= 400:
            self.failed.append(f"read roles -> HTTP {resp.status_code} — apply "
                               f"handoff § 4 by hand in Administration -> Roles")
            return
        roles = [r for r in resp.json().get("list", []) if r.get("name") == role_name]
        if not roles:
            names = ", ".join(sorted(r.get("name", "?") for r in resp.json()["list"]))
            self.failed.append(f"role '{role_name}' not found (roles here: {names})")
            return
        role = (await self._req("GET", f"Role/{roles[0]['id']}")).json()
        data = dict(role.get("data") or {})
        current = data.get(ENTITY)
        if isinstance(current, dict) and current.get("read") == "all" and all(
            current.get(k, "no") == "no" for k in ("create", "edit", "delete")
        ):
            self.skipped.append(f"role {role_name}: {ENTITY} already read=all, no writes")
            return
        data[ENTITY] = GRANT                      # surgical: only this scope's key
        await self._write("PUT", f"Role/{roles[0]['id']}", {"data": data},
                          f"role {role_name}: grant {ENTITY} read=all, no writes "
                          f"(was {current!r})")

    # --- § 1's tab rule -----------------------------------------------------
    async def tab_list(self) -> None:
        resp = await self._req("GET", "Settings")
        tabs = list(resp.json().get("tabList") or [])
        if ENTITY not in tabs:
            self.skipped.append(f"tabList: {ENTITY} not present ({len(tabs)} tabs)")
            return
        await self._write("PUT", "Settings",
                          {"tabList": [t for t in tabs if t != ENTITY]},
                          f"tabList: remove {ENTITY} ({len(tabs)} -> {len(tabs) - 1})")

    async def clear_cache(self) -> None:
        if self.apply:
            await self._req("POST", "Admin/clearCache")

    # --- § 5: verification --------------------------------------------------
    async def verify(self, org_key: str, base: str) -> list[str]:
        problems: list[str] = []
        if self.apply or not self.actions:
            defs = await self._meta(f"entityDefs.{ENTITY}") or {}
            fields = set(defs.get("fields") or {})
            wanted = {f["name"] for f in self.plan.get("fields", [])}
            if missing := wanted - fields:
                problems.append(f"metadata: fields missing: {sorted(missing)}")
            custom_links = {
                k for k, v in (defs.get("links") or {}).items() if v.get("isCustom")
            }
            if custom_links:
                problems.append(f"metadata: unexpected custom links: {sorted(custom_links)}")
            if await self._meta("scopes.CCNetworkStandard"):
                problems.append("CCNetworkStandard exists — a doubled prefix")
        if not org_key:
            problems.append("no org-wide API key in the environment (ESPO_API_KEY) — "
                            "handoff § 5 must be run by hand")
            return problems
        async with httpx.AsyncClient(timeout=15) as h:
            r = await h.get(f"{base}/api/v1/{ENTITY}", params={"maxSize": 1},
                            headers={"X-Api-Key": org_key})
        if r.status_code == 200:
            total = r.json().get("total")
            print(f"org API key: GET {ENTITY} -> HTTP 200, total {total} — "
                  + ("the expected 'built, never applied to' state."
                     if total == 0 else "a stamp row exists."))
        elif self.apply or not self.actions:
            meaning = {403: "the § 4 role grant is missing",
                       404: "the entity does not exist under this name"}
            problems.append(f"org API key: GET {ENTITY} -> HTTP {r.status_code} — "
                            f"{meaning.get(r.status_code, r.text[:120])}")
        else:
            print(f"org API key today: GET {ENTITY} -> HTTP {r.status_code} "
                  f"(expected before an --apply)")
        return problems


def fingerprint(plan: dict, role: str) -> str:
    blob = json.dumps({"plan": plan, "role": role, "grant": GRANT},
                      sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="make the changes (default is a dry run)")
    parser.add_argument("--expect", metavar="FINGERPRINT",
                        help="refuse to apply unless the plan still has this "
                             "fingerprint (printed by the dry run)")
    parser.add_argument("--production", action="store_true",
                        help="acknowledge that the target is not crm-test")
    parser.add_argument("--role", default=ROLE_DEFAULT,
                        help=f"role attached to the org-wide API user "
                             f"(default: {ROLE_DEFAULT})")
    args = parser.parse_args()

    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    fp = fingerprint(plan, args.role)

    env = _env()
    base = (env.get("ESPO_ADMIN_BASE") or "").rstrip("/")
    user, password = env.get("ESPO_ADMIN_USER", ""), env.get("ESPO_ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE / ESPO_ADMIN_USER / ESPO_ADMIN_PASS. Inside a "
              "deployed container:\n  ESPO_ADMIN_BASE=\"$ESPO_BASE_URL\" "
              "ESPO_ADMIN_USER=\"$ESPO_PROVISION_USERNAME\" "
              "ESPO_ADMIN_PASS=\"$ESPO_PROVISION_PASSWORD\"", file=sys.stderr)
        return 2
    if args.apply and "crm-test" not in base and not args.production:
        print(f"Target is {base}, which is not crm-test. Production goes at the "
              f"Sunday 17:00 UTC slot, run by a person from inside the deployed "
              f"container — pass --production only then.", file=sys.stderr)
        return 2
    if args.apply and args.expect and args.expect != fp:
        print(f"Plan fingerprint is {fp}, you expected {args.expect} — the plan "
              f"moved since your dry run. Re-run the dry run and read it again.",
              file=sys.stderr)
        return 2
    if args.apply and not args.expect:
        print("Refusing --apply without --expect <fingerprint>. Dry-run first; "
              "apply exactly the plan you reviewed.", file=sys.stderr)
        return 2

    try:
        name, token = await login_token(base, user, password, 30)
    except AuthError as exc:
        print(f"{base}: login rejected for {user} ({exc})", file=sys.stderr)
        return 2
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{profile.get('userName')} is type={profile.get('type')}; this "
              f"needs an Admin-type account.", file=sys.stderr)
        return 2
    print(f"CRM:  {base}\nUser: {profile.get('userName')} (type=admin)\n"
          f"Plan: {PLAN_PATH.name}, fingerprint {fp}\n"
          f"Mode: {'APPLY' if args.apply else 'dry run'}\n")

    b = Builder(client, plan, args.apply)
    pending = await b.entity()
    if pending:
        await b.rebuild()
    await b.fields(pending)
    await b.role_grant(args.role)
    await b.tab_list()
    await b.clear_cache()
    problems = await b.verify(env.get("ESPO_API_KEY", ""), base)

    for line in b.skipped:
        print(f"  ok      {line}")
    for line in b.actions:
        print(f"  {'DONE' if args.apply else 'WOULD'}    {line}")
    for line in b.failed:
        print(f"  FAILED  {line}")
    for line in problems:
        print(f"  PROBLEM {line}")

    if b.failed or problems:
        return 1
    if not args.apply and b.actions:
        print(f"\nDry run only. To apply exactly this:  --apply --expect {fp}"
              + ("" if "crm-test" in base else " --production"))
    if not b.actions:
        print("\nNothing to do — this instance already matches the handoff.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
