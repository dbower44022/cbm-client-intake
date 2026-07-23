"""Submission Admin collaboration — internal discussion comments (2026-07-22).

Replaces the single ``submission.notes`` blob with an attributed, timestamped
comment stream so a group of admins can discuss a submission without clobbering
each other. On upgrade the existing notes value is folded in as one seed comment
(author "legacy") so no history is lost; the ``notes`` column is left in place,
read-only, and dropped in a later release.

See prds/submission-admin-collaboration-plan.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_submission_comments"
down_revision = "0015_submission_request_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission_comment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("author_name", sa.String(255)),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_comment_submission", "submission_comment",
        ["submission_id", "created_at"],
    )
    # Fold the existing notes blob into a seed comment (keeps the history).
    # gen_random_uuid() is built into Postgres 13+ (no extension needed on the
    # DO managed instances).
    op.execute(
        """
        INSERT INTO submission_comment
            (id, submission_id, author, author_name, body, created_at)
        SELECT gen_random_uuid()::text, id, 'legacy', 'Imported note',
               notes, received_at
        FROM submission
        WHERE notes IS NOT NULL AND btrim(notes) <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_comment_submission", table_name="submission_comment")
    op.drop_table("submission_comment")
