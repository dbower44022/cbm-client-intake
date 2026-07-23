"""Submission Admin collaboration — Close-with-reason + collision signal
(2026-07-22).

``closed_at``/``closed_by``/``close_reason``/``close_note`` back the single
terminal Close action (it also sets ``resolved_at`` and ``request_status`` so
the queue, the resolved flag, and the CRM never drift). ``last_activity_at``/
``last_activity_by`` are the grid's "who touched it last" collision signal —
bumped by staff-meaningful events only (comments, replies, status changes),
never by system delivery.

See prds/submission-admin-collaboration-plan.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_submission_close"
down_revision = "0017_submission_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column("submission", sa.Column("closed_by", sa.String(128)))
    op.add_column("submission", sa.Column("close_reason", sa.String(64)))
    op.add_column("submission", sa.Column("close_note", sa.Text))
    op.add_column(
        "submission", sa.Column("last_activity_at", sa.DateTime(timezone=True))
    )
    op.add_column("submission", sa.Column("last_activity_by", sa.String(128)))


def downgrade() -> None:
    for col in (
        "last_activity_by", "last_activity_at",
        "close_note", "close_reason", "closed_by", "closed_at",
    ):
        op.drop_column("submission", col)
