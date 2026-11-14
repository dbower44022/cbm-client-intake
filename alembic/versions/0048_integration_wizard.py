"""The setup wizard's storage (prds/integrations-tab-plan.md § 10, phase 8).

``integration_wizard`` — one row per integration: where its wizard stands
(the current screen, the screens visited, the answers given, the last
failure and Claude's last answer), kept for the whole deployment (decided
under ruling W5, 11-14-26).

``integration_agent_call`` — one row per "Ask Claude about this" (ruling
W6), with its cost: the monthly budget counts these with the diagnoses.

Both are training data on the sandbox (core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0048_integration_wizard"
down_revision = "0047_survey_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_wizard",
        sa.Column("integration", sa.String(40), primary_key=True),
        sa.Column("progress", JSONB, nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "integration_agent_call",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration", sa.String(40), nullable=False),
        sa.Column("screen", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("answer", sa.Text),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("asked_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_agent_call_month", "integration_agent_call", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_integration_agent_call_month", table_name="integration_agent_call")
    op.drop_table("integration_agent_call")
    op.drop_table("integration_wizard")
