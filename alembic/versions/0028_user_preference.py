"""Per-user preferences — the portal calendar's filter first (F3).

Doug's F3 ruling 8 (09-28-26): each member chooses what the portal calendar
shows, "saved in their preferences" — so it follows them to another computer,
which browser storage would not. One row per (CRM user, preference key) with a
small JSON value; general on purpose, so the next per-user setting needs no
migration. Kept by the sandbox reset (configuration, not training data).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_user_preference"
down_revision = "0027_app_setting_verified"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preference",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("pref_key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_preference")
