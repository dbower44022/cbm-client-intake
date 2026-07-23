"""Submission Admin collaboration — activity feed + presence (2026-07-22).

``submission_activity`` is the automatic, ordered log of everything that
happens to a submission (system + staff); ``submission_presence`` records each
admin's last view so the detail page can show "Bob viewed 4 min ago" — the
anti-double-reply cue in the no-owner model.

See prds/submission-admin-collaboration-plan.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_submission_activity"
down_revision = "0016_submission_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission_activity",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128)),
        sa.Column("actor_name", sa.String(255)),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_activity_submission", "submission_activity",
        ["submission_id", "created_at"],
    )
    op.create_table(
        "submission_presence",
        sa.Column("submission_id", sa.String(36), primary_key=True),
        sa.Column("user_name", sa.String(128), primary_key=True),
        sa.Column("display_name", sa.String(255)),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("submission_presence")
    op.drop_index("ix_activity_submission", table_name="submission_activity")
    op.drop_table("submission_activity")
