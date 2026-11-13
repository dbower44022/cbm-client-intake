"""Integration test runs (prds/integrations-tab-plan.md § 7, phase 2).

``integration_test_run`` — one row per integration test, manual or nightly:
the integration, the trigger, the start and finish, the outcome, the checks and
the integration facts (scrubbed of every secret value), and who ran it.
Training data on the sandbox (core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0043_integration_test_run"
down_revision = "0042_website_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_test_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration", sa.String(40), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("checks", JSONB, nullable=False),
        sa.Column("facts", JSONB, nullable=False),
        sa.Column("run_by_id", sa.String(32)),
        sa.Column("run_by", sa.String(128)),
    )
    op.create_index(
        "ix_integration_test_run_latest", "integration_test_run",
        ["integration", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_test_run_latest", table_name="integration_test_run")
    op.drop_table("integration_test_run")
