"""Per-user conversation read state (unread badges — My Email + the record
Communications tabs). Unread = the conversation's lastMessageAt is newer than
this user's stamp; a conversation the user never opened counts as unread only
inside a recent window (comms.service.enrich_conversation_rows).

Revision ID: 0010_conversation_seen
Revises: 0009_comms_loss_prevention
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_conversation_seen"
down_revision = "0009_comms_loss_prevention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_seen",
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("username", "conversation_id"),
    )


def downgrade() -> None:
    op.drop_table("conversation_seen")
