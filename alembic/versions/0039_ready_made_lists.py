"""The ready-made lists (build plan § 7e.9 second half, § 7e.12 Draft 9; M8).

``audience_list`` gains ``system`` (bool, default false), and the five
ready-made dynamic lists are created under fixed ids:

- *All leads for postcards*
- *Opted-in prospects (Engaged and later)*
- *Prospects with text consent*
- *Leads and prospects with a phone*
- *Dormant clients (a year)* — a built-in selection, not conditions

The recipes below are a frozen copy of ``campaigns/ready_made.LISTS`` as of
this migration (a test keeps the two equal). The application's
``ready_made.ensure`` is the live source: it re-creates a missing list after
the sandbox's nightly reset, and never touches one that exists.

The downgrade deletes the five lists (and their versions, members and any
campaign's choice of them) and drops the column.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0039_ready_made_lists"
down_revision = "0038_list_constant_contact_copy"
branch_labels = None
depends_on = None

ACTOR = "migration 0039"
_OPEN = ["Unqualified", "Qualified"]
_STAGES = ["Prospect", "Engaged", "Opportunity"]
_PROSPECT = {"field": "cContactType", "op": "anyOf", "value": ["Prospect"]}
_RELATIONSHIP = {"kind": "match", "type": "contact",
                 "conditions": [{"field": "cContactType", "op": "anyOf",
                                 "value": ["Client", "Mentor", "Partner", "Sponsor"]}]}

LISTS = (
    ("ready-made-postcard-leads", "All leads for postcards",
     "Every lead still being worked, Unqualified or Qualified. A postcard goes only to a lead with a usable, "
     "complete address, and never to a business that already had a card.",
     {"include": [{"kind": "match", "type": "lead",
                   "conditions": [{"field": "leadStatus", "op": "in", "value": _OPEN}]}], "exclude": []}),
    ("ready-made-opted-in-prospects", "Opted-in prospects (Engaged and later)",
     "Contacts typed Prospect at Engaged or Opportunity who ticked the marketing email box. Anyone who is "
     "already a client, partner, funder or mentor is left out.",
     {"include": [{"kind": "match", "type": "contact",
                   "conditions": [_PROSPECT, {"field": "cFunnelStage", "op": "in", "value": ["Engaged", "Opportunity"]},
                                  {"field": "cMarketingOptIn", "op": "isTrue", "value": None}]}],
      "exclude": [_RELATIONSHIP]}),
    ("ready-made-text-consent", "Prospects with text consent",
     "Contacts typed Prospect, at any stage, who ticked the text-message box. A text goes only to a number "
     "not opted out. Anyone who already holds a relationship is left out.",
     {"include": [{"kind": "match", "type": "contact",
                   "conditions": [_PROSPECT, {"field": "cFunnelStage", "op": "in", "value": _STAGES},
                                  {"field": "cSmsOptIn", "op": "isTrue", "value": None}]}],
      "exclude": [_RELATIONSHIP]}),
    ("ready-made-leads-with-phone", "Leads and prospects with a phone",
     "Leads still being worked and contacts typed Prospect at any stage. A call goes only to someone with a "
     "phone number who has not asked not to be called or declined before.",
     {"include": [{"kind": "match", "type": "lead",
                   "conditions": [{"field": "leadStatus", "op": "in", "value": _OPEN}]},
                  {"kind": "match", "type": "contact",
                   "conditions": [_PROSPECT, {"field": "cFunnelStage", "op": "in", "value": _STAGES}]}],
      "exclude": [_RELATIONSHIP]}),
    ("ready-made-dormant-clients", "Dormant clients (a year)",
     "Clients whose engagements are all closed, the latest more than a year ago. An email goes only to those "
     "who ticked the marketing email box.",
     {"include": [{"kind": "builtin", "type": "contact", "builtin": "dormant_clients", "days": 365}],
      "exclude": []}),
)


def upgrade() -> None:
    op.add_column("audience_list", sa.Column("system", sa.Boolean(), nullable=False, server_default=sa.false()))
    lists = sa.table(
        "audience_list", sa.column("id", sa.String), sa.column("name", sa.String), sa.column("notes", sa.Text),
        sa.column("kind", sa.String), sa.column("status", sa.String), sa.column("version", sa.Integer),
        sa.column("recipe", JSONB), sa.column("created_by", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_by", sa.String), sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("needs_rebuild", sa.Boolean), sa.column("cc_sync", sa.Boolean), sa.column("system", sa.Boolean),
    )
    versions = sa.table(
        "audience_list_version", sa.column("list_id", sa.String), sa.column("version", sa.Integer),
        sa.column("kind", sa.String), sa.column("recipe", JSONB), sa.column("saved_by", sa.String),
        sa.column("saved_at", sa.DateTime(timezone=True)),
    )
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    present = {r[0] for r in conn.execute(sa.text("SELECT id FROM audience_list"))}
    for list_id, name, notes, recipe in LISTS:
        if list_id in present:
            continue
        conn.execute(lists.insert().values(
            id=list_id, name=name, notes=notes, kind="dynamic", status="active", version=1, recipe=recipe,
            created_by=ACTOR, created_at=now, updated_by=ACTOR, updated_at=now, needs_rebuild=False,
            cc_sync=False, system=True))
        conn.execute(versions.insert().values(list_id=list_id, version=1, kind="dynamic", recipe=recipe,
                                              saved_by=ACTOR, saved_at=now))


def downgrade() -> None:
    ids = [x[0] for x in LISTS]
    conn = op.get_bind()
    for table, column in (("campaign_audience", "list_id"), ("audience_list_member", "list_id"),
                          ("audience_list_version", "list_id"), ("audience_list", "id")):
        conn.execute(sa.text(f"DELETE FROM {table} WHERE {column} = ANY(:ids)"), {"ids": ids})
    op.drop_column("audience_list", "system")
