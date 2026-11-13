"""The diagnosis agent's tables (prds/integrations-tab-plan.md § 6.6 and § 7,
phase 6).

``integration_fix_plan`` — one row per diagnosis: the diagnosis, the steps,
their fingerprint and progress, the status, who approved it, the model, the
token use and the cost. ``kind`` is ``fix`` now and ``setup`` from phase 7.

``integration_event`` — each integration's recent errors, written by the
top-level error handler of its own job in either process, scrubbed of
secrets, kept 14 days (Doug's decision 11-13-26, § 6.6).

Both are training data on the sandbox (core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0046_integration_fix_plan"
down_revision = "0045_integration_checklist_tick"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_fix_plan",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("test_run_id", sa.String(36)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("diagnosis", sa.Text),
        sa.Column("confidence", sa.String(16)),
        sa.Column("steps", JSONB, nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("model", sa.String(64)),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("usage", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(128)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_integration_fix_plan_latest", "integration_fix_plan",
                    ["integration", "created_at"])
    op.create_table(
        "integration_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration", sa.String(40), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_event_recent", "integration_event",
                    ["integration", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_integration_event_recent", table_name="integration_event")
    op.drop_table("integration_event")
    op.drop_index("ix_integration_fix_plan_latest", table_name="integration_fix_plan")
    op.drop_table("integration_fix_plan")
