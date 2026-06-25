"""add app_config table (encrypted runtime config)

Holds runtime-editable config that can't be an env var because it's set from
inside the app — notably the Google Workspace service-account credentials,
configured via the Mentor-Admin "Email Setup" screen. Values are encrypted at
rest (Fernet, keyed by APP_ENCRYPTION_KEY); see core/app_config.py + core/crypto.py.

Revision ID: 0003_app_config
Revises: 0002_processing_lease
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_app_config"
down_revision = "0002_processing_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_config")
