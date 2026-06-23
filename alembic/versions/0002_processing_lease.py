"""add processing lease (locked_until) + claim index

Lets the worker reclaim a "processing" row whose lease expired — a row stranded
by a worker that died mid-delivery (redeploy/OOM/SIGKILL) would otherwise stay
in "processing" forever, never re-claimed and never delivered. See
core/store.py:claim_batch.

Revision ID: 0002_processing_lease
Revises: 0001_create_submission
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_processing_lease"
down_revision = "0001_create_submission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_submission_claim",
        "submission",
        ["status", "next_attempt_at", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_submission_claim", table_name="submission")
    op.drop_column("submission", "locked_until")
