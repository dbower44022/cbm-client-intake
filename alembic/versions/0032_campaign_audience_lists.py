"""Campaign audiences as named lists (prds/prospect-marketing/build-plan.md
§ 7c; rulings 58–68). Ruling 64: lists live in the application's database,
like campaign links (ruling 31); touches stay in the CRM.

``audience_list`` — one named list: its kind (static / dynamic), status
(active / retired), current version and its recipe (an ordered list of steps,
JSON), with the last run's counts. ``audience_list_version`` — the recipe at
each saved change, so a campaign can name the version it sent to.
``audience_list_member`` — the membership a run produced, plus hand ticks on a
static list (``source`` hand, ``state`` in / out), so "Run again" keeps them.
``audience_list_entry`` — a dynamic list's standing entries, always include or
always exclude (ruling 65). ``campaign_audience`` — the list a campaign sends
to, the version it last built from and what that build resolved.

All five are training data on the sandbox and are RESET nightly
(core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_campaign_audience_lists"
down_revision = "0031_campaign_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audience_list",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("recipe", postgresql.JSONB, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_by", sa.String(128)),
        sa.Column("last_run", postgresql.JSONB),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_by", sa.String(128)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_audience_list_name", "audience_list", ["name"])
    op.create_table(
        "audience_list_version",
        sa.Column("list_id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("recipe", postgresql.JSONB, nullable=False),
        sa.Column("saved_by", sa.String(128)),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audience_list_member",
        sa.Column("list_id", sa.String(36), primary_key=True),
        sa.Column("target_key", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("step", sa.Integer),
        sa.Column("added_by", sa.String(128)),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audience_list_member_list", "audience_list_member", ["list_id", "state"])
    op.create_table(
        "audience_list_entry",
        sa.Column("list_id", sa.String(36), primary_key=True),
        sa.Column("target_key", sa.String(64), primary_key=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "campaign_audience",
        sa.Column("campaign_id", sa.String(32), primary_key=True),
        sa.Column("list_id", sa.String(36), nullable=False),
        sa.Column("include_every_contact", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("set_by", sa.String(128)),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("built_version", sa.Integer),
        sa.Column("built_at", sa.DateTime(timezone=True)),
        sa.Column("build", postgresql.JSONB),
    )
    op.create_index("ix_campaign_audience_list", "campaign_audience", ["list_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_audience_list", table_name="campaign_audience")
    op.drop_table("campaign_audience")
    op.drop_table("audience_list_entry")
    op.drop_index("ix_audience_list_member_list", table_name="audience_list_member")
    op.drop_table("audience_list_member")
    op.drop_table("audience_list_version")
    op.drop_index("ix_audience_list_name", table_name="audience_list")
    op.drop_table("audience_list")
