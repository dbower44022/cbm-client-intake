"""create submission table (V2 Phase 0 durable capture)

Revision ID: 0001_create_submission
Revises:
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_create_submission"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("form_slug", sa.String(length=64), nullable=False),
        sa.Column("submission_token", sa.String(length=128), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("progress", JSONB()),
        sa.Column("result", JSONB()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "form_slug", "submission_token", name="uq_submission_form_token"
        ),
    )


def downgrade() -> None:
    op.drop_table("submission")
