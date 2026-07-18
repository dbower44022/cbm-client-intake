"""Gmail sync loss prevention (P1-5, reliability review 2026-07-17).

- ``email_sync_state.failed_ids``: {"<gmail id>": consecutive failing passes} —
  while any id is failing the cursor is held back so nothing is skipped.
- ``email_sync_state.dead_letter``: ids skipped after GMAIL_DEAD_LETTER_PASSES
  consecutive failures (decision D6 = 5) — bounded, logged, in /ops metrics.
- ``conversation_thread``: local (mailbox, Gmail thread id) -> conversation id
  map, making empty conversation shells findable (a failed first message create
  used to leave an unfindable shell; the retry minted a duplicate) and letting
  the send path persist the include override BEFORE the write-through ingest.

Revision ID: 0009_comms_loss_prevention
Revises: 0008_submission_acted_by
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_comms_loss_prevention"
down_revision = "0008_submission_acted_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_sync_state", sa.Column("failed_ids", sa.Text()))
    op.add_column("email_sync_state", sa.Column("dead_letter", sa.Text()))
    op.create_table(
        "conversation_thread",
        sa.Column("mailbox", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("mailbox", "thread_id"),
    )


def downgrade() -> None:
    op.drop_table("conversation_thread")
    op.drop_column("email_sync_state", "dead_letter")
    op.drop_column("email_sync_state", "failed_ids")
