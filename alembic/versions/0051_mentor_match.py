"""The mentor match runs (Business Evaluation phase 7, ruling BE28).

Every run of Client Administration's AI analysis is kept (Doug's decision 4,
A, 11-19-26); the Mentor match tab shows the latest. Downgrade drops the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0051_mentor_match"
down_revision = "0050_heartbeat_switches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mentor_match",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("engagement_id", sa.String(32), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_by_id", sa.String(32)),
        sa.Column("run_by_name", sa.String(255)),
        sa.Column("model", sa.String(64)),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost", sa.Float),
        sa.Column("result", JSONB, nullable=False),
    )
    op.create_index("ix_mentor_match_engagement_id", "mentor_match", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_mentor_match_engagement_id", table_name="mentor_match")
    op.drop_table("mentor_match")
