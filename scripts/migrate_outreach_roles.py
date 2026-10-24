"""Grant the roles that prospect marketing and Campaign Management need (Phase 1).

The grants of ``prds/prospect-marketing/build-plan.md`` v0.3 § 7 Phase 1, for the
three entities ``scripts/plans/coutreach-entities.json`` creates (``CProspect``,
``COutreachCampaign``, ``COutreachTouch``). Handoff:
``coutreach-entities-crm-handoff.md`` § 4. Modelled on
``scripts/migrate_presenter_roles.py``.

* **CustomAppAPIRole** (the org-wide API key the application runs on) —
  ``CProspect`` create yes, read all, edit all (the imports, the promotion
  links, the rung); ``COutreachTouch`` create yes, read all, edit all (the
  selection run, the scan, the vendor callback); ``COutreachCampaign`` read all and edit all (the worker's run moves it to Running and Complete)
  (the resolve of a campaign id at delivery, and the ``partnerProfiles``
  relationship read — a relationship read needs read on both ends, and the
  role holds ``CPartnerProfile`` read already). Re-checked, never lowered:
  ``CEngagement`` edit all and ``CPartnerProfile`` edit all (the
  ``referringPartners`` relate checks both sides), ``Contact`` and ``Account``
  edit all (the new stage fields and the campaign link).
* **Marketing Admin Role** (CM-1: the Marketing Admin Team creates and runs
  campaigns) — all three entities create yes, read all, edit all; no delete
  anywhere (a campaign is Cancelled, never deleted). **Assignment Permission
  ``all``**: a role that creates a record the application leaves unassigned
  needs it (the presenters finding of 10-08-26, read from EspoCRM's own
  ``Acl/AssignmentChecker/Helper.php``: at *not set* or *team* a record with
  neither a team nor an assigned user is refused outright). Re-checked:
  ``CEvent`` read all (the events picker, CM-6) and ``CPartnerProfile`` read all
  (the partners picker, CM-2) — both held on crm-test 10-14-26. ``User``
  read all, edit own (ruling 78: changing a campaign's owner links a User
  the role must be able to read).
* **Mentor Role** (ruling 36, Phase 3: a mentor on a campaign naming the Mentor
  Team makes calls as themself) — ``COutreachTouch`` read all and edit all,
  ``CProspect`` read all. Re-checked: ``Contact`` read all.

**Field-level access is reported, never changed.** A role with a ``fieldData``
rule on ``Contact`` or ``Account`` silently strips a write to a field the rule
does not name (HTTP 200, nothing stored). Both plan files add fields to those
two entities (``cSmsOptIn``; ``cFunnelStage`` and ``cEntryStage``), so this
script prints every role's ``fieldData`` for them and flags any rule that
would strip the new fields. On crm-test 10-14-26 no role carried a
``fieldData`` rule at all. ``--field-acl-only`` runs that report alone, which
is what ``contact-sms-opt-in-crm-handoff.md`` § 3 needs on a CRM that has no
``COutreach*`` entity.

**Idempotent and merge-only.** A level already at or above the wanted one is
left alone; nothing is ever lowered or removed. Needs an Admin-type login::

    PYTHONPATH=. uv run python scripts/run_with_admin.py \\
        scripts/migrate_outreach_roles.py                    # dry run
    ... scripts/migrate_outreach_roles.py --apply             # apply
    ... scripts/migrate_outreach_roles.py --field-acl-only    # the fieldData report alone

Order: crm-test first, then production at the Sunday 17:00 UTC slot from inside
the deployed web container, then Boston with its release. A CRM whose org-wide
API user holds a role with a different name needs that name in the table
below first — check with
``GET /User?where[0][type]=equals&where[0][attribute]=type&where[0][value]=api``.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assignments.auth import login_token  # noqa: E402
from core.espo import EspoClient  # noqa: E402

#: The three entities the plan file creates. All must exist before any grant.
NEW_ENTITIES: tuple[str, ...] = ("CProspect", "COutreachCampaign", "COutreachTouch")

#: (role name, scope, minimum levels). Order matches the handoff's table.
ROLE_SCOPE_GRANTS: list[tuple[str, str, dict[str, str]]] = [
    ("CustomAppAPIRole", "CProspect", {"create": "yes", "read": "all", "edit": "all"}),
    ("CustomAppAPIRole", "COutreachTouch", {"create": "yes", "read": "all", "edit": "all"}),
    # Edit as well as read: the worker's run moves the campaign to Running and
    # Complete and stamps runStartedAt / runCompletedAt under this role. Read
    # alone (the plan's § 7 list) left the run refused every minute with
    # "No edit access" on crm-test, 10-15-26 15:37.
    ("CustomAppAPIRole", "COutreachCampaign", {"read": "all", "edit": "all"}),
    # Re-checks: held on crm-test 10-14-26, named here so a CRM that lacks one
    # gains it rather than failing the referringPartners relate or a stage write.
    ("CustomAppAPIRole", "CEngagement", {"edit": "all"}),
    ("CustomAppAPIRole", "CPartnerProfile", {"edit": "all"}),
    ("CustomAppAPIRole", "Contact", {"edit": "all"}),
    ("CustomAppAPIRole", "Account", {"edit": "all"}),
    # Ruling 69 (10-20-26): stream all on the two stream-enabled entities.
    # EspoCRM lets a user post a Note on a record only with stream access to
    # it, so at "no" every Campaign Management history note was refused
    # (HTTP 403 "No create access") for every non-admin user.
    ("Marketing Admin Role", "CProspect", {"create": "yes", "read": "all", "edit": "all", "stream": "all"}),
    ("Marketing Admin Role", "COutreachCampaign", {"create": "yes", "read": "all", "edit": "all", "stream": "all"}),
    ("Marketing Admin Role", "COutreachTouch", {"create": "yes", "read": "all", "edit": "all"}),
    # Re-checks for the two pickers on a campaign (CM-2 partners, CM-6 events).
    ("Marketing Admin Role", "CEvent", {"read": "all"}),
    ("Marketing Admin Role", "CPartnerProfile", {"read": "all"}),
    # Ruling 54 (10-19-26, the lead model): marketing staff read every Company,
    # read only — a converted lead leads them to its Company. Creates and edits
    # stay the application's, under the API role (ruling 33). An absent scope
    # gains explicit "no" for the other actions, so the grant stays read-only.
    ("Marketing Admin Role", "Account", {"read": "all"}),
    # Ruling 78 (10-22-26): handing a campaign to a colleague writes its
    # Assigned User, and EspoCRM refuses a link to a User the acting role
    # cannot read ("No foreign record access"; the role held only the
    # default read own, so a marketer could assign a campaign to themself
    # alone). The shape the Client Assignment Role got on 09-07-26.
    ("Marketing Admin Role", "User", {"read": "all", "edit": "own"}),
    # Build plan § 7e.5 and § 7e.11 (rulings 109, 118; marketing-redesign-crm-
    # handoff.md § 4): a reply to a personal email is attached to the lead as a
    # CConversation, and the lead's page reads the thread AS THE USER
    # (comms/service.py list_conversations / conversation_thread). The sync
    # stamps the mailbox owner into assignedUsers (comms/crm.stamp_owners), so
    # read "own" is enough for the assignee — the Mentor Role's shape. The
    # messages are read all, as the Mentor Role has them: a CCommunication is
    # reached only through a conversation the user can read. Creates and the
    # record link stay the application's, under the API role.
    ("Marketing Admin Role", "CConversation", {"read": "own"}),
    ("Marketing Admin Role", "CCommunication", {"read": "all"}),
    # Ruling 36 (10-18-26, Phase 3): callers are the members of the teams named
    # on a call campaign, each acting as themself, so a mentor on a campaign
    # naming the Mentor Team reads the call list and records the outcome on the
    # touch as themself. The rung and the side exit the outcome causes are the
    # application's writes, under the API role — the Mentor Role gains no
    # CProspect edit. Contact read all is held (re-checked: a phone can live on
    # a Contact typed Prospect).
    ("Mentor Role", "COutreachTouch", {"read": "all", "edit": "all"}),
    ("Mentor Role", "CProspect", {"read": "all"}),
    ("Mentor Role", "Contact", {"read": "all"}),
]

#: Role-level permissions (not per scope): (role name, permission, minimum level).
ROLE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("Marketing Admin Role", "assignmentPermission", "all"),
]

#: Field-level rules (ruling 40, 10-18-26): the eight campaign fields the
#: APPLICATION writes are readable but not editable by the people who run
#: campaigns. They were built Read-only, which turned out to be a global ACL
#: restriction that drops every API write — the application's own included —
#: so ``scripts/plans/coutreach-campaign-app-fields.json`` clears Read-only and
#: this rule keeps staff off them instead. The application writes them under
#: the API role, which carries no field rule. The ONE place this script
#: restricts rather than grants: it only ever adds ``edit: no`` on these named
#: fields, and leaves every other field rule alone.
APP_OWNED_CAMPAIGN_FIELDS: tuple[str, ...] = (
    "selectionRule", "selectionSummary", "pieceCount", "estimatedCost",
    "signedOffByName", "signedOffAt", "runStartedAt", "runCompletedAt",
)
FIELD_RULES: list[tuple[str, str, tuple[str, ...], dict[str, str]]] = [
    ("Marketing Admin Role", "COutreachCampaign", APP_OWNED_CAMPAIGN_FIELDS, {"read": "yes", "edit": "no"}),
    # Build plan § 7d.5, rulings 74 and 40 (10-22-26): the lead code is the
    # application's to mint and copy. The team that runs campaigns reads it and
    # cannot hand-edit it; New code and promotion write it under the API role.
    # Applied after scripts/plans/lead-code.json (lead-code-crm-handoff.md § 3).
    ("Marketing Admin Role", "CProspect", ("leadCode",), {"read": "yes", "edit": "no"}),
    ("Marketing Admin Role", "Contact", ("cLeadCode",), {"read": "yes", "edit": "no"}),
]

#: The fields the two plan files add to native entities, as STORED.
NEW_NATIVE_FIELDS: dict[str, tuple[str, ...]] = {
    "Contact": ("cSmsOptIn", "cFunnelStage", "cEntryStage", "cOutreachCampaign", "cLeadCode"),
    "Account": ("cFunnelStage", "cEntryStage", "cOutreachCampaign"),
}

# ``create`` is yes/no; the others are no/own/team/all. One ranking covers both.
LEVEL_RANK: dict[str, int] = {"no": 0, "not-set": 0, "own": 1, "team": 2, "all": 3, "yes": 3}


def _rank(level: Any) -> int:
    return LEVEL_RANK.get(level, 0) if isinstance(level, str) else 0


async def _find_role(client: EspoClient, name: str) -> dict[str, Any] | None:
    page = await client.list(
        "Role", where=[{"type": "equals", "attribute": "name", "value": name}],
        select="id,name", max_size=5,
    )
    for row in page.get("list", []):
        if row.get("name") == name:
            return await client.get("Role", row["id"])
    return None


def field_acl_findings(role: dict[str, Any]) -> list[str]:
    """What a role's ``fieldData`` would do to the new native fields.

    EspoCRM applies a scope's ``fieldData`` as a per-field read/edit level;
    a field the rule does not name falls back to the scope level, so a rule
    only strips when it names the field at a lower level than the scope. A
    rule naming any field on the scope is still worth a line: the person
    reading the report decides, the script never edits ``fieldData``.
    """
    out: list[str] = []
    data = role.get("data") or {}
    field_data = role.get("fieldData") or {}
    for scope, fields in NEW_NATIVE_FIELDS.items():
        rule = field_data.get(scope)
        if not isinstance(rule, dict) or not rule:
            continue
        scope_edit = (data.get(scope) or {}).get("edit") if isinstance(data.get(scope), dict) else None
        out.append(f"{role.get('name')}: fieldData.{scope} names {sorted(rule)} "
                   f"(scope edit={scope_edit!r})")
        for field in fields:
            levels = rule.get(field)
            if isinstance(levels, dict) and _rank(levels.get("edit")) < _rank(scope_edit):
                out.append(f"  ! {role.get('name')}: {scope}.{field} edit is "
                           f"{levels.get('edit')!r} below the scope's {scope_edit!r} — "
                           f"a write to it would be STRIPPED (HTTP 200, nothing stored)")
    return out


async def report_field_acl(client: EspoClient) -> list[str]:
    """Every role that can edit Contact or Account, and what its fieldData says."""
    lines: list[str] = []
    page = await client.list("Role", select="id,name", max_size=200)
    for row in page.get("list", []):
        role = await client.get("Role", row["id"])
        data = role.get("data") or {}
        edits = []
        for scope in NEW_NATIVE_FIELDS:
            level = (data.get(scope) or {}).get("edit") if isinstance(data.get(scope), dict) else None
            if _rank(level) > 0:
                edits.append(f"{scope} edit={level}")
        if not edits:
            continue
        lines.append(f"{role.get('name')}: {', '.join(edits)}")
        findings = field_acl_findings(role)
        lines.extend(findings or ["  no fieldData rule on Contact or Account — nothing can be stripped"])
    return lines


async def main() -> int:
    apply = "--apply" in sys.argv
    field_acl_only = "--field-acl-only" in sys.argv
    base = (os.environ.get("ESPO_ADMIN_BASE") or os.environ.get("ADMIN_BASE", "")).rstrip("/")
    user = os.environ.get("ESPO_ADMIN_USER") or os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ESPO_ADMIN_PASS") or os.environ.get("ADMIN_PASS", "")
    if not (base and user and password):
        print("Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.", file=sys.stderr)
        return 2
    name, token = await login_token(base, user, password, 30)
    client = EspoClient.for_user_token(base, name, token)
    profile = (await client.app_user()).get("user", {})
    if profile.get("type") != "admin":
        print(f"{user} is type={profile.get('type')} - role changes need an Admin-type account.",
              file=sys.stderr)
        return 2
    print(f"CRM:  {base}")
    print(f"User: {name} (type={profile.get('type')})")
    mode = "FIELD-ACL REPORT ONLY" if field_acl_only else ("APPLY" if apply else "DRY RUN - nothing will change")
    print(f"Mode: {mode}\n")

    print("FIELD-LEVEL ACCESS on Contact and Account (every role that edits either; read-only report):")
    for line in await report_field_acl(client):
        print(f"  {line}")
    print()
    if field_acl_only:
        return 0

    # The entities must exist first (scripts/plans/coutreach-entities.json).
    missing = []
    for entity in NEW_ENTITIES:
        meta = await client.metadata(f"entityDefs.{entity}")
        if not (isinstance(meta, dict) and meta.get("fields")):
            missing.append(entity)
    if missing:
        print(f"{', '.join(missing)} do not exist on this CRM - apply "
              f"scripts/plans/coutreach-entities.json first.", file=sys.stderr)
        return 2

    done: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    touched = False
    for role_name, scope, wanted in ROLE_SCOPE_GRANTS:
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        data: dict[str, Any] = dict(role.get("data") or {})
        current = data.get(scope)
        current_map: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        new_map = dict(current_map)
        changes: list[str] = []
        for action, level in wanted.items():
            if _rank(current_map.get(action)) >= _rank(level):
                skipped.append(f"{role_name}: {scope}.{action} already '{current_map.get(action)}'")
                continue
            new_map[action] = level
            changes.append(f"{action}: {current_map.get(action, '(not set)')} -> {level}")
        if not changes:
            continue
        # A scope that was absent (no access at all) gets explicit 'no' for the
        # actions not granted, so the stored map is complete and readable.
        for action in ("create", "read", "edit", "delete", "stream"):
            new_map.setdefault(action, "no")
        label = f"{role_name}: {scope} {{{', '.join(changes)}}}"
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        data[scope] = new_map
        try:
            await client.update("Role", role["id"], {"data": data})
            back = await client.get("Role", role["id"])
            stored = (back.get("data") or {}).get(scope) or {}
            short = [a for a, lv in wanted.items() if _rank(stored.get(a)) < _rank(lv)]
            if short:
                failed.append(f"{label} - read-back is missing {short}: {stored}")
            else:
                done.append(f"set {label} - read back OK: {stored}")
                touched = True
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label} - {exc}")

    for role_name, permission, level in ROLE_PERMISSIONS:
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        current = role.get(permission)
        if _rank(current) >= _rank(level):
            skipped.append(f"{role_name}: {permission} already '{current}'")
            continue
        label = f"{role_name}: {permission} {current or '(not set)'} -> {level}"
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        try:
            await client.update("Role", role["id"], {permission: level})
            back = await client.get("Role", role["id"])
            if _rank(back.get(permission)) < _rank(level):
                failed.append(f"{label} - read-back is '{back.get(permission)}'")
            else:
                done.append(f"set {label} - read back OK")
                touched = True
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label} - {exc}")

    for role_name, scope, fields, rule in FIELD_RULES:
        role = await _find_role(client, role_name)
        if role is None:
            failed.append(f"role '{role_name}' does not exist on this instance")
            continue
        field_data: dict[str, Any] = dict(role.get("fieldData") or {})
        scope_rules: dict[str, Any] = dict(field_data.get(scope) or {})
        todo = [f for f in fields if (scope_rules.get(f) or {}) != rule]
        if not todo:
            skipped.append(f"{role_name}: {scope} field rules already {rule} on {len(fields)} fields")
            continue
        label = f"{role_name}: {scope} fields {', '.join(todo)} -> {rule}"
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        for f in todo:
            scope_rules[f] = dict(rule)
        field_data[scope] = scope_rules
        try:
            await client.update("Role", role["id"], {"fieldData": field_data})
            back = await client.get("Role", role["id"])
            stored = ((back.get("fieldData") or {}).get(scope) or {})
            short = [f for f in fields if (stored.get(f) or {}) != rule]
            if short:
                failed.append(f"{label} - read-back differs on {short}")
            else:
                done.append(f"set {label} - read back OK")
                touched = True
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label} - {exc}")

    if touched:
        resp = await client._request(
            "POST", f"{client._base}/Admin/rebuild", op="rebuild", json_body={}
        )
        (done if resp.status_code < 300 else failed).append(f"rebuild -> HTTP {resp.status_code}")
    elif not apply and done:
        done.append("WOULD rebuild")

    for title, rows in (("CHANGES", done), ("SKIPPED (already correct)", skipped), ("FAILED", failed)):
        if rows:
            print(f"{title}:")
            for row in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {row}")
            print()
    if not apply:
        print("Dry run only. Re-run with --apply to make these changes.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
