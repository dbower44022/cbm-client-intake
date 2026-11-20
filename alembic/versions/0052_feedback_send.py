"""Feedback surveys (Business Evaluation phases 8 and 9, rulings BE30, BE32,
BE33; decision 5, A, 11-20-26).

``feedback_send``: one row per moment per person. Its unique ``send_key``
makes "never twice" a database guarantee; ``email`` serves the quiet period;
a skip is a row too. ``feedback_alert``: one row per Survey Response whose
follow-up alert was sent, so a retried submit never alerts twice.
Downgrade drops both tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052_feedback_send"
down_revision = "0051_mentor_match"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_send",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("send_key", sa.String(160), nullable=False),
        sa.Column("moment", sa.String(32), nullable=False),
        sa.Column("survey_key", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("contact_id", sa.String(32)),
        sa.Column("link_id", sa.String(36)),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("send_key", name="uq_feedback_send_key"),
    )
    op.create_index("ix_feedback_send_email", "feedback_send", ["email", "updated_at"])
    op.create_index("ix_feedback_send_record", "feedback_send", ["entity_type", "record_id"])
    op.create_table(
        "feedback_alert",
        sa.Column("response_id", sa.String(32), primary_key=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feedback_alert")
    op.drop_index("ix_feedback_send_record", table_name="feedback_send")
    op.drop_index("ix_feedback_send_email", table_name="feedback_send")
    op.drop_table("feedback_send")
