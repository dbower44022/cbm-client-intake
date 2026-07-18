"""Audit column for /ops actions (P1-11, reliability review 2026-07-17).

``acted_by`` records the signed-in staff username on redrive/discard — the
answer to "who discarded this submission?", previously unanswerable by design.

Revision ID: 0008_submission_acted_by
Revises: 0007_worker_heartbeat
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_submission_acted_by"
down_revision = "0007_worker_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("acted_by", sa.String(length=128)))


def downgrade() -> None:
    op.drop_column("submission", "acted_by")
