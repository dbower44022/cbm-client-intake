"""The training courses' store (prds/training-app-plan.md § 6, TR9).

``training_progress`` (each step ticked, each checkpoint answered),
``training_completion`` (one per person, course and revision, the answers
copied in), ``training_dismissal`` (phase 2) and ``training_onboarding_write``
(phase 4). The help agent's table arrives with phase 5. Downgrade drops all
four.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054_training_courses"
down_revision = "0053_ambassador_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_progress",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("course_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.String(16), nullable=False),
        sa.Column("item_key", sa.String(32), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer", sa.Text),
        sa.UniqueConstraint("user_id", "course_id", "item_key", name="uq_training_progress_item"),
    )
    op.create_table(
        "training_completion",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("user_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("course_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.String(16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answers", sa.Text, nullable=False, server_default="{}"),
        sa.UniqueConstraint("user_id", "course_id", "revision", name="uq_training_completion"),
    )
    op.create_index("ix_training_completion_course", "training_completion",
                    ["course_id", "completed_at"])
    op.create_table(
        "training_dismissal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("course_id", sa.String(64), nullable=False),
        sa.Column("major", sa.Integer, nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "course_id", "major", name="uq_training_dismissal"),
    )
    op.create_table(
        "training_onboarding_write",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("mentor_profile_id", sa.String(32), nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("training_onboarding_write")
    op.drop_table("training_dismissal")
    op.drop_index("ix_training_completion_course", table_name="training_completion")
    op.drop_table("training_completion")
    op.drop_table("training_progress")
