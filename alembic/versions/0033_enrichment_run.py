"""Lead enrichment phase 2 — the AI research runs (prds/lead-enrichment/
build-plan-phase-2.md § 3).

``enrichment_run`` — one run a person started: on what (leads or one
company), the estimate, its state, who started it. ``enrichment_run_item`` —
one record researched within a run, with what it actually cost. The month's
spend, which the budget check reads (rulings E8, E9), is the sum of the
items' costs; it is real money, so both tables are KEPT through the
sandbox's nightly reset (core/sandbox_reset.py KEEP_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_enrichment_run"
down_revision = "0032_campaign_audience_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrichment_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("estimate", sa.Float, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model", sa.String(64)),
        sa.Column("started_by", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text),
    )
    op.create_index("ix_enrichment_run_status", "enrichment_run", ["status"])
    op.create_table(
        "enrichment_run_item",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("target_id", sa.String(64), primary_key=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cost", sa.Float, nullable=False, server_default="0"),
        sa.Column("findings", sa.Integer, nullable=False, server_default="0"),
        sa.Column("detail", postgresql.JSONB),
        sa.Column("error", sa.Text),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_enrichment_run_item_finished", "enrichment_run_item", ["finished_at"])


def downgrade() -> None:
    op.drop_index("ix_enrichment_run_item_finished", table_name="enrichment_run_item")
    op.drop_table("enrichment_run_item")
    op.drop_index("ix_enrichment_run_status", table_name="enrichment_run")
    op.drop_table("enrichment_run")
