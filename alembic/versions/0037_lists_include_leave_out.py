"""Lists described by Include and Leave out (build plan § 7e.8; rulings 90–94).

A dynamic list's recipe was an ordered list of steps; it becomes
``{"include": [group, …], "exclude": [group, …]}``, where a group is a record
type with conditions (``match``), everyone on another list (``list``) or the
records a file names (``import``). A static list has no recipe at all: its
members are the rows added by hand.

What this migration converts, list by list:

- **A dynamic list.** *Add* → an Include match group; *Remove* → a Leave out
  match group; *Add list* → an Include list group; *Remove list* → a Leave out
  list group; *import* → an Include import group. A *Keep only* step has no
  place in the new model and is dropped, and a recipe where an adding step
  came after a removing one (so the order changed who was on the list) is
  converted as written. Either way the list is marked ``needs_rebuild`` and
  its page says so until someone checks it and saves it again.
- **Its standing entries.** The *always exclude* entries become the hand rows
  of a new static list named "<list> — exceptions", which the dynamic list
  leaves out. The *always include* entries have no place (ruling 92) and are
  dropped, each one named in the migration's log.
- **A static list.** Its current members (the last run plus anyone added by
  hand) become hand rows; rows that took a person out by hand are dropped;
  its recipe is emptied and its last run cleared.

Every converted list gets a new version, saved by "migration 0037". The
recipes already in ``audience_list_version`` stay as they were saved: they are
history. ``audience_list_member.step`` is renamed ``group_index`` (the Include
group that brought a member in; null until a dynamic list runs again), and
``audience_list_entry`` is dropped after the conversion.

Lists exist only on crm-test, as test data the sandbox empties every night;
production has none. The conversion is written for correctness, not scale.

The downgrade restores the columns and the entry table but not the old
recipes: a list converted here keeps its groups.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0037_lists_include_leave_out"
down_revision = "0036_import_write_lease"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0037")

ACTOR = "migration 0037"
_INCLUDE_STEPS = ("add", "addList", "import")
_EXCLUDE_STEPS = ("remove", "removeList")


def _conditions(step: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"field": c.get("field"), "op": c.get("op"), "value": c.get("value")}
            for c in step.get("conditions") or [] if isinstance(c, dict)]


def convert_steps(recipe: Any) -> tuple[dict[str, Any], bool]:
    """An old recipe (``{"steps": [...]}``) as groups, and whether the list
    needs rebuilding by hand. Pure, so the test can run it without a database.
    A recipe already in the new shape (an upgrade run again after a downgrade)
    is returned as it is."""
    if isinstance(recipe, dict) and "steps" not in recipe and ("include" in recipe or "exclude" in recipe):
        return {"include": list(recipe.get("include") or []), "exclude": list(recipe.get("exclude") or [])}, False
    out: dict[str, list[dict[str, Any]]] = {"include": [], "exclude": []}
    needs_rebuild = False
    seen_exclude = False
    for s in (recipe or {}).get("steps") or []:
        if not isinstance(s, dict):
            continue
        action = s.get("action")
        if action == "keep":
            needs_rebuild = True
            continue
        if action in _INCLUDE_STEPS and seen_exclude:
            needs_rebuild = True            # the order changed the result
        if action in ("add", "remove"):
            group = {"kind": "match", "type": s.get("type") or "", "conditions": _conditions(s)}
        elif action in ("addList", "removeList"):
            group = {"kind": "list", "listId": s.get("listId") or ""}
        elif action == "import":
            group = {"kind": "import", "type": s.get("type") or "", "values": list(s.get("values") or [])}
        else:
            needs_rebuild = True
            continue
        if action in _EXCLUDE_STEPS:
            seen_exclude = True
            out["exclude"].append(group)
        else:
            out["include"].append(group)
    return out, needs_rebuild


def _j(value: Any) -> str:
    return json.dumps(value)


def upgrade() -> None:
    op.add_column("audience_list", sa.Column("needs_rebuild", sa.Boolean, nullable=False,
                                             server_default=sa.false()))
    op.alter_column("audience_list_member", "step", new_column_name="group_index")

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    lists = conn.execute(sa.text("SELECT id, name, kind, version, recipe FROM audience_list")).mappings().all()
    entries = conn.execute(sa.text(
        "SELECT list_id, target_key, mode FROM audience_list_entry ORDER BY created_at")).mappings().all()

    def new_version(list_id: str, version: int, kind: str, recipe: dict[str, Any]) -> None:
        conn.execute(sa.text(
            "INSERT INTO audience_list_version (list_id, version, kind, recipe, saved_by, saved_at) "
            "VALUES (:id, :v, :k, CAST(:r AS JSONB), :by, :at)"),
            {"id": list_id, "v": version, "k": kind, "r": _j(recipe), "by": ACTOR, "at": now})

    for row in lists:
        empty = {"include": [], "exclude": []}
        if row["kind"] == "static":
            conn.execute(sa.text(
                "DELETE FROM audience_list_member WHERE list_id = :id AND state <> 'in'"), {"id": row["id"]})
            conn.execute(sa.text(
                "UPDATE audience_list_member SET source = 'hand', group_index = NULL WHERE list_id = :id"),
                {"id": row["id"]})
            conn.execute(sa.text(
                "UPDATE audience_list SET recipe = CAST(:r AS JSONB), version = :v, last_run_at = NULL, "
                "last_run_by = NULL, last_run = NULL, updated_by = :by, updated_at = :at WHERE id = :id"),
                {"r": _j(empty), "v": row["version"] + 1, "by": ACTOR, "at": now, "id": row["id"]})
            new_version(row["id"], row["version"] + 1, "static", empty)
            continue

        groups, needs_rebuild = convert_steps(row["recipe"])
        mine = [e for e in entries if e["list_id"] == row["id"]]
        for e in mine:
            if e["mode"] == "include":
                log.warning("0037: dropped the always-include entry %s on the list %r (%s) — "
                            "a dynamic list has no place for one", e["target_key"], row["name"], row["id"])
        excluded = [e["target_key"] for e in mine if e["mode"] == "exclude"]
        if excluded:
            ex_id = str(uuid.uuid4())
            conn.execute(sa.text(
                "INSERT INTO audience_list (id, name, notes, kind, status, version, recipe, needs_rebuild, "
                "created_by, created_at, updated_by, updated_at) VALUES (:id, :name, :notes, 'static', "
                "'active', 1, CAST(:r AS JSONB), false, :by, :at, :by, :at)"),
                {"id": ex_id, "name": (row["name"] + " — exceptions")[:200],
                 "notes": f"The people always excluded from \"{row['name']}\" before lists changed to "
                          "Include and Leave out.", "r": _j(empty), "by": ACTOR, "at": now})
            new_version(ex_id, 1, "static", empty)
            for key in excluded:
                conn.execute(sa.text(
                    "INSERT INTO audience_list_member (list_id, target_key, source, state, group_index, "
                    "added_by, added_at) VALUES (:id, :k, 'hand', 'in', NULL, :by, :at)"),
                    {"id": ex_id, "k": key, "by": ACTOR, "at": now})
            groups["exclude"].append({"kind": "list", "listId": ex_id})
        conn.execute(sa.text("UPDATE audience_list_member SET group_index = NULL WHERE list_id = :id"),
                     {"id": row["id"]})
        conn.execute(sa.text(
            "UPDATE audience_list SET recipe = CAST(:r AS JSONB), version = :v, needs_rebuild = :nr, "
            "updated_by = :by, updated_at = :at WHERE id = :id"),
            {"r": _j(groups), "v": row["version"] + 1, "nr": needs_rebuild, "by": ACTOR, "at": now,
             "id": row["id"]})
        new_version(row["id"], row["version"] + 1, "dynamic", groups)

    op.drop_table("audience_list_entry")


def downgrade() -> None:
    op.create_table(
        "audience_list_entry",
        sa.Column("list_id", sa.String(36), primary_key=True),
        sa.Column("target_key", sa.String(64), primary_key=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.alter_column("audience_list_member", "group_index", new_column_name="step")
    op.drop_column("audience_list", "needs_rebuild")
