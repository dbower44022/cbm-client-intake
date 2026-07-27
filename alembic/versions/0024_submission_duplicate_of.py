"""Near-duplicate hold (2026-07-27): record which earlier submission a held
duplicate is a duplicate OF, so Submission Admin can link the reviewer straight
to the original for comparison instead of making them search for it.

NULL on every row that is not a held duplicate.

Revision ID: 0024_submission_duplicate_of
Revises: 0023_crm_receipt_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_submission_duplicate_of"
down_revision = "0023_crm_receipt_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("duplicate_of", sa.String(36)))
    # The lookup is "show me the duplicates of this submission" on the detail
    # view; partial so the index only carries the rare non-NULL rows.
    op.create_index(
        "ix_submission_duplicate_of",
        "submission",
        ["duplicate_of"],
        postgresql_where=sa.text("duplicate_of IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_submission_duplicate_of", table_name="submission")
    op.drop_column("submission", "duplicate_of")
