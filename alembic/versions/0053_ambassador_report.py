"""The Ambassador Program's report store (prds/Ambassador Program/
ambassador-program-prd.md § 4.1).

``ambassador_report``: one row per report a mentor submitted, written before
any CRM call; the delivery's progress rides on it so a retry resumes.
Downgrade drops the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053_ambassador_report"
down_revision = "0052_feedback_send"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ambassador_report",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reference", sa.String(16), nullable=False),
        sa.Column("submission_token", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("user_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("mentor_profile_id", sa.String(32), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("progress", sa.Text, nullable=False, server_default="{}"),
        sa.Column("activity_id", sa.String(32)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("submission_token", name="uq_ambassador_report_token"),
        sa.UniqueConstraint("reference", name="uq_ambassador_report_reference"),
    )
    op.create_index("ix_ambassador_report_due", "ambassador_report",
                    ["status", "next_attempt_at"])
    op.create_index("ix_ambassador_report_user", "ambassador_report", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ambassador_report_user", table_name="ambassador_report")
    op.drop_index("ix_ambassador_report_due", table_name="ambassador_report")
    op.drop_table("ambassador_report")
