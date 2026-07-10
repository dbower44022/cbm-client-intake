"""Communications: Gmail sync state + conversation curation overrides.

Per-mailbox incremental-sync cursors (Gmail historyId) and the record-level
include/exclude overrides for attaching conversations to engagement/partner/
sponsor records. See prds/communications-gmail-integration.md §5.2/§5.4.

Revision ID: 0004_comms_sync
Revises: 0003_app_config
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_comms_sync"
down_revision = "0003_app_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_sync_state",
        sa.Column("mailbox", sa.String(length=255), primary_key=True),
        sa.Column("history_id", sa.String(length=32)),
        sa.Column("initial_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        # JSON list of contact addresses already backfilled for this mailbox —
        # a new address (new record/contact) triggers a targeted history query.
        sa.Column("known_addresses", sa.Text()),
    )
    op.create_table(
        "conversation_override",
        sa.Column("parent_entity", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),  # include | exclude
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("parent_entity", "parent_id", "conversation_id"),
    )
    op.create_index(
        "ix_conversation_override_conv", "conversation_override", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_override_conv", table_name="conversation_override")
    op.drop_table("conversation_override")
    op.drop_table("email_sync_state")
