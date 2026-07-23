"""Record discussion — a generalized staff-internal comment stream (2026-07-23).

A sibling of ``submission_comment`` keyed to any record by ``(parent_type,
parent_id)`` — the session tools' Partner/Funder Discussion pane. App-only
(never mirrored to the CRM); append-only. Separate table so the Submission
Admin queue is untouched.

See prompts/record-discussion-pane-prompt.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_record_comment"
down_revision = "0019_autoclose_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "record_comment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parent_type", sa.String(64), nullable=False),
        sa.Column("parent_id", sa.String(64), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("author_name", sa.String(255)),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_record_comment_parent", "record_comment",
        ["parent_type", "parent_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_record_comment_parent", table_name="record_comment")
    op.drop_table("record_comment")
