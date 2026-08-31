#!/usr/bin/env python3
"""Rehearsal applier for the API half of the CBM standard.

Applies, idempotently, everything the file baseline (custom/Espo/Custom + rebuild)
does NOT carry, using an Admin-type login supplied by environment:

  teams, roles (data + fieldData + permissions), role->team attachments,
  email templates, the org-wide API user + its role, a provisioning admin
  service account, and the EspoCRM instance settings (chapter-values § E).

Source of truth for teams/roles/templates: the crm-test database capture in
``crmtest-db/`` next to this file (read-only SELECTs, 2026-08-31).

Dry-run by default; ``--apply`` writes. Emits a JSON result (C5 shape) to
``api-half-result.json`` on every exit. Exit codes follow the interface
contract: 0 conformant/applied, 1 drift (dry run found work), 2 apply failed,
3 could not be checked.

Credentials: ESPO_ADMIN_BASE / ESPO_ADMIN_USER / ESPO_ADMIN_PASS, read from the
file named by --env (never sourced by a shell). Secrets this script MINTS (the
API key, the provisioning password) are appended to that same file.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import secrets
import string
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from assignments.auth import AuthError, login_token  # noqa: E402
from core.espo import EspoClient, EspoError, EspoTransportError  # noqa: E402

HERE = Path(__file__).resolve().parent
CAP = REPO / "prds" / "chapter-network" / "rehearsal-2026-08-31" / "crmtest-capture"

CHAPTER_NAME = "Lakeside Business Mentors"
API_USER = "customapps"
API_ROLE = "CustomAppAPIRole"
PROVISION_USER = "lakeside.provision"

ROLE_PERMISSION_KEYS = [
    "assignmentPermission", "userPermission", "exportPermission",
    "massUpdatePermission", "portalPermission", "dataPrivacyPermission",
    "followerManagementPermission", "groupEmailAccountPermission",
    "messagePermission", "auditPermission", "mentionPermission",
]

# chapter-values.md § E, for the fictional chapter. timeZone stays Eastern
# because the app's four timezone hardcodes are Eastern (§ C, not parameterized).
SETTINGS = {
    "applicationName": CHAPTER_NAME,
    "outboundEmailFromName": CHAPTER_NAME,
    "timeZone": "America/New_York",
    "dateFormat": "MM/DD/YYYY",
    "timeFormat": "HH:mm",
    "weekStart": 0,
    "defaultCurrency": "USD",
    "baseCurrency": "USD",
    "currencyList": ["USD"],
    "language": "en_US",
}


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def append_env(path: Path, key: str, value: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


def alnum_password(n: int = 28) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


class Result:
    def __init__(self, instance: str, mode: str) -> None:
        self.doc: dict[str, Any] = {
            "instance": instance, "standardVersion": None, "mode": mode,
            "counts": {}, "directives": [],
        }

    def add(self, category: str, target: str, outcome: str, reason: str = "") -> None:
        self.doc["directives"].append(
            {"category": category, "target": target, "outcome": outcome, "reason": reason}
        )
        c = self.doc["counts"]
        c[outcome] = c.get(outcome, 0) + 1

    def write(self, path: Path, exit_code: int) -> None:
        self.doc["exitCode"] = exit_code
        path.write_text(json.dumps(self.doc, indent=1), encoding="utf-8")


async def _get(client: EspoClient, path: str, params: dict | None = None) -> Any:
    resp = await client._request("GET", f"{client._base}/{path}", op=f"GET {path}", params=params)
    if resp.status_code >= 400:
        raise EspoError(f"GET {path} -> HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


async def _put(client: EspoClient, path: str, body: dict) -> Any:
    resp = await client._request("PUT", f"{client._base}/{path}", op=f"PUT {path}", json_body=body)
    if resp.status_code >= 400:
        raise EspoError(f"PUT {path} -> HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.text else {}


async def _post(client: EspoClient, path: str, body: dict | None = None) -> Any:
    resp = await client._request("POST", f"{client._base}/{path}", op=f"POST {path}", json_body=body)
    if resp.status_code >= 400:
        raise EspoError(f"POST {path} -> HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.text else {}


async def list_all(client: EspoClient, entity: str, select: str | None = None) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        params: dict[str, Any] = {"maxSize": 200, "offset": offset}
        if select:
            params["select"] = select
        page = await _get(client, entity, params)
        rows = page.get("list", [])
        out.extend(rows)
        if len(rows) < 200:
            return out
        offset += 200


async def run(args: argparse.Namespace) -> int:
    env_path = Path(args.env)
    env = read_env(env_path)
    base = env.get("ESPO_ADMIN_BASE", "").rstrip("/")
    user = env.get("ESPO_ADMIN_USER", "")
    password = env.get("ESPO_ADMIN_PASS", "")
    if not (base and user and password):
        print("missing ESPO_ADMIN_BASE / ESPO_ADMIN_USER / ESPO_ADMIN_PASS in", env_path, file=sys.stderr)
        return 2
    mode = "apply" if args.apply else "check"
    res = Result(base, mode)
    out_path = HERE / "api-half-result.json"

    try:
        name, token = await login_token(base, user, password, 30)
    except AuthError as exc:
        print(f"login rejected for {user}: {exc}", file=sys.stderr)
        res.add("auth", user, "unchecked", str(exc)); res.write(out_path, 3)
        return 3
    except EspoError as exc:
        print(f"unreachable: {exc}", file=sys.stderr)
        res.add("auth", base, "unchecked", str(exc)); res.write(out_path, 3)
        return 3
    client = EspoClient.for_user_token(base, name, token, timeout=60)
    me = (await client.app_user()).get("user", {})
    if not (me.get("isAdmin") or me.get("type") in ("admin", "super-admin")):
        print(f"{user} is not an admin (type={me.get('type')}); refusing", file=sys.stderr)
        res.add("auth", user, "unchecked", "not admin"); res.write(out_path, 2)
        return 2
    try:
        settings_now = await _get(client, "Settings")
        print(f"EspoCRM version on {base}: {settings_now.get('version')}")
        res.doc["espoVersion"] = settings_now.get("version")
    except EspoError as exc:
        print(f"could not read Settings: {exc}")
        settings_now = {}

    drift = 0
    failed = 0
    unapplyable = 0
    apply = args.apply
    target_scopes = set((await client.metadata("scopes")).keys())
    target_defs = await client.metadata("entityDefs")

    # ---- teams --------------------------------------------------------------
    cap_teams = json.loads((CAP / "teams.json").read_text())
    live_teams = {t["name"]: t for t in await list_all(client, "Team", "name")}
    for t in cap_teams:
        if t["name"] in live_teams:
            res.add("team", t["name"], "conformant", "exists")
            continue
        if apply:
            try:
                created = await client.create("Team", {"name": t["name"]})
                live_teams[t["name"]] = created
                res.add("team", t["name"], "applied", "created")
            except EspoError as exc:
                failed += 1; res.add("team", t["name"], "failed", str(exc))
        else:
            drift += 1; res.add("team", t["name"], "drifted", "would create")

    # ---- roles --------------------------------------------------------------
    cap_roles = json.loads((CAP / "roles.json").read_text())
    live_roles = {r["name"]: r for r in await list_all(client, "Role", "name")}
    role_ids: dict[str, str] = {r["name"]: r["id"] for r in live_roles.values()}
    for r in cap_roles:
        raw_data = json.loads(r["data"]) if r["data"] else {}
        raw_fd = json.loads(r["fieldData"]) if r["fieldData"] else {}
        stripped = sorted((set(raw_data) | set(raw_fd)) - target_scopes)
        for sc in stripped:
            unapplyable += 1
            res.add("roleScope", f"{r['name']}: {sc}", "unapplyable",
                    "scope does not exist on the target (extension not installed)")
        fd_clean: dict[str, Any] = {}
        for sc, fields in raw_fd.items():
            if sc not in target_scopes:
                continue
            have = set(((target_defs.get(sc) or {}).get("fields") or {}).keys())
            keep = {f: v for f, v in (fields or {}).items() if f in have}
            for f in sorted(set(fields or {}) - have):
                unapplyable += 1
                res.add("roleField", f"{r['name']}: {sc}.{f}", "unapplyable",
                        "field-level entry names a field the target does not have (stale on the source)")
            fd_clean[sc] = keep
        want = {
            "name": r["name"],
            "data": {k: v for k, v in raw_data.items() if k in target_scopes},
            "fieldData": fd_clean,
        }
        for k in ROLE_PERMISSION_KEYS:
            if r.get(k) is not None:
                want[k] = r[k]
        if r["name"] not in live_roles:
            if apply:
                try:
                    created = await client.create("Role", want)
                    role_ids[r["name"]] = created["id"]
                    # read back: does the CRM hold what we sent?
                    back = await client.get("Role", created["id"])
                    same = (back.get("data") or {}) == want["data"] and \
                           (back.get("fieldData") or {}) == want["fieldData"]
                    res.add("role", r["name"], "applied" if same else "failed",
                            "created and read back" if same else "created but read-back differs")
                    if not same:
                        failed += 1
                except EspoError as exc:
                    failed += 1; res.add("role", r["name"], "failed", str(exc))
            else:
                drift += 1; res.add("role", r["name"], "drifted", f"would create ({len(want['data'])} scopes)")
        else:
            full = await client.get("Role", live_roles[r["name"]]["id"])
            diffs = []
            if (full.get("data") or {}) != want["data"]:
                diffs.append("data")
            if (full.get("fieldData") or {}) != want["fieldData"]:
                diffs.append("fieldData")
            for k in ROLE_PERMISSION_KEYS:
                if k in want and full.get(k) != want[k]:
                    diffs.append(k)
            if not diffs:
                res.add("role", r["name"], "conformant", "matches capture")
            elif apply:
                try:
                    await client.update("Role", full["id"], {k: want[k] for k in ["data", "fieldData"] + ROLE_PERMISSION_KEYS if k in want})
                    res.add("role", r["name"], "applied", "updated: " + ",".join(diffs))
                except EspoError as exc:
                    failed += 1; res.add("role", r["name"], "failed", str(exc))
            else:
                drift += 1; res.add("role", r["name"], "drifted", "differs: " + ",".join(diffs))

    # ---- role -> team attachments -------------------------------------------
    cap_rt = json.loads((CAP / "role_team.json").read_text())
    cap_role_by_id = {r["id"]: r["name"] for r in cap_roles}
    cap_team_by_id = {t["id"]: t["name"] for t in cap_teams}
    wanted_pairs = {(cap_role_by_id[x["roleId"]], cap_team_by_id[x["teamId"]]) for x in cap_rt
                    if x["roleId"] in cap_role_by_id and x["teamId"] in cap_team_by_id}
    team_ids = {t["name"]: t["id"] for t in live_teams.values() if "id" in t}
    for role_name, team_name in sorted(wanted_pairs):
        target = f"{role_name} -> {team_name}"
        rid, tid = role_ids.get(role_name), team_ids.get(team_name)
        if not (rid and tid):
            if apply:
                failed += 1; res.add("roleTeam", target, "failed", "role or team missing")
            else:
                drift += 1; res.add("roleTeam", target, "drifted", "would attach (after create)")
            continue
        attached = await _get(client, f"Role/{rid}/teams", {"maxSize": 200})
        if any(t["id"] == tid for t in attached.get("list", [])):
            res.add("roleTeam", target, "conformant", "attached")
        elif apply:
            try:
                await client.relate("Role", rid, "teams", tid)
                res.add("roleTeam", target, "applied", "attached")
            except EspoError as exc:
                failed += 1; res.add("roleTeam", target, "failed", str(exc))
        else:
            drift += 1; res.add("roleTeam", target, "drifted", "would attach")

    # ---- email templates ----------------------------------------------------
    cap_tpl = json.loads((CAP / "templates.json").read_text())
    live_tpl = {t["name"]: t for t in await list_all(client, "EmailTemplate", "name")}
    for t in cap_tpl:
        if t["name"] in live_tpl:
            res.add("emailTemplate", t["name"], "conformant", "exists"); continue
        body = {"name": t["name"], "subject": t["subject"] or "", "body": t["body"] or "",
                "isHtml": bool(t["isHtml"])}
        if t.get("status"):
            body["status"] = t["status"]
        if apply:
            try:
                await client.create("EmailTemplate", body)
                res.add("emailTemplate", t["name"], "applied", "created")
            except EspoError as exc:
                failed += 1; res.add("emailTemplate", t["name"], "failed", str(exc))
        else:
            drift += 1; res.add("emailTemplate", t["name"], "drifted", "would create")

    # ---- the org-wide API user ----------------------------------------------
    users = {u["userName"]: u for u in await list_all(client, "User", "userName,type,isActive")}
    if API_USER in users:
        res.add("user", API_USER, "conformant", "exists")
        uid = users[API_USER]["id"]
    elif apply and API_ROLE in role_ids:
        try:
            created = await client.create("User", {
                "userName": API_USER, "type": "api", "authMethod": "ApiKey", "isActive": True,
                "lastName": "App API", "rolesIds": [role_ids[API_ROLE]],
            })
            uid = created["id"]
            res.add("user", API_USER, "applied", "created (type api, ApiKey)")
        except EspoError as exc:
            uid = None; failed += 1; res.add("user", API_USER, "failed", str(exc))
    else:
        uid = None; drift += 1; res.add("user", API_USER, "drifted", "would create")
    if uid and apply and "ESPO_API_KEY" not in env:
        full = await client.get("User", uid)
        key = full.get("apiKey")
        if key:
            append_env(env_path, "ESPO_API_KEY", key); env["ESPO_API_KEY"] = key
            res.add("secret", "ESPO_API_KEY", "applied", "read from the API user, stored in env file")
        else:
            failed += 1; res.add("secret", "ESPO_API_KEY", "failed", "User record carries no apiKey")
    if uid and apply:
        # the API user must hold the role directly, as on crm-test
        roles_on = await _get(client, f"User/{uid}/roles", {"maxSize": 200})
        if not any(r["name"] == API_ROLE for r in roles_on.get("list", [])) and API_ROLE in role_ids:
            try:
                await client.relate("User", uid, "roles", role_ids[API_ROLE])
                res.add("userRole", f"{API_USER} -> {API_ROLE}", "applied", "attached")
            except EspoError as exc:
                failed += 1; res.add("userRole", f"{API_USER} -> {API_ROLE}", "failed", str(exc))
        else:
            res.add("userRole", f"{API_USER} -> {API_ROLE}", "conformant", "attached")

    # ---- the provisioning admin service account -----------------------------
    if PROVISION_USER in users:
        res.add("user", PROVISION_USER, "conformant", "exists")
    elif apply:
        pw = alnum_password()
        try:
            await client.create("User", {
                "userName": PROVISION_USER, "type": "admin", "isActive": True,
                "firstName": "Lakeside", "lastName": "Provisioning", "password": pw,
                "passwordConfirm": pw,
            })
            append_env(env_path, "ESPO_PROVISION_USERNAME", PROVISION_USER)
            append_env(env_path, "ESPO_PROVISION_PASSWORD", pw)
            res.add("user", PROVISION_USER, "applied", "created (type admin); password stored in env file")
        except EspoError as exc:
            failed += 1; res.add("user", PROVISION_USER, "failed", str(exc))
    else:
        drift += 1; res.add("user", PROVISION_USER, "drifted", "would create")

    # ---- instance settings (§ E) + tab list --------------------------------
    cap_settings = json.loads((CAP / "settings-tablist.json").read_text()) if (CAP / "settings-tablist.json").exists() else {}
    want_settings = dict(SETTINGS)
    if cap_settings.get("tabList"):
        # drop crm-test's per-chapter url tab (the Cleveland docs link) — per chapter-values § B
        want_settings["tabList"] = [x for x in cap_settings["tabList"]
                                    if not (isinstance(x, dict) and x.get("type") == "url")]
    if cap_settings.get("quickCreateList"):
        want_settings["quickCreateList"] = cap_settings["quickCreateList"]
    diffs = {k: v for k, v in want_settings.items() if settings_now.get(k) != v}
    if not diffs:
        res.add("settings", "Settings", "conformant", "all keys match")
    elif apply:
        try:
            await _put(client, "Settings", diffs)
            after = await _get(client, "Settings")
            still = [k for k, v in diffs.items() if after.get(k) != v]
            if still:
                failed += 1; res.add("settings", "Settings", "failed", "did not take: " + ",".join(still))
            else:
                res.add("settings", "Settings", "applied", "set: " + ",".join(diffs))
        except EspoError as exc:
            failed += 1; res.add("settings", "Settings", "failed", str(exc))
    else:
        drift += 1; res.add("settings", "Settings", "drifted", "would set: " + ",".join(diffs))

    # ---- rebuild ------------------------------------------------------------
    if apply:
        try:
            await _post(client, "Admin/rebuild")
            res.add("rebuild", "Admin/rebuild", "applied", "ok")
        except EspoError as exc:
            failed += 1; res.add("rebuild", "Admin/rebuild", "failed", str(exc))

    code = 2 if failed else (1 if (drift and not apply) else (4 if unapplyable else 0))
    res.write(out_path, code)
    for d in res.doc["directives"]:
        print(f"{d['outcome']:<10} {d['category']:<14} {d['target']}: {d['reason']}")
    print("counts:", res.doc["counts"], "exit", code)
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True, help="env file with ESPO_ADMIN_*; minted secrets are appended here")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        return asyncio.run(run(args))
    except EspoTransportError as exc:
        print(f"unreachable: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
