"""System Settings — the runtime override layer (prds/system-settings-plan.md).

``app_setting`` holds ONLY the keys an admin has overridden; every other setting
still comes from the environment. ``app_setting_history`` records old→new for
each change so the environment diff can answer "when did these two drift apart?"
without storing snapshots of its own (ruling 8).

Values are stored as TEXT and coerced back to the field's declared type by
``Settings`` on load — secrets are never stored here at all (they are on the
never-overridable denylist in ``core/settings_registry.py``), so this table
needs no encryption, unlike ``app_config``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_app_setting"
down_revision = "0024_submission_duplicate_of"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        # Ruling 5: a change can be marked temporary with a review date. Nothing
        # ever auto-reverts — the worker only reports overdue ones.
        sa.Column("temporary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("review_at", sa.DateTime(timezone=True)),
        # Phase 4 — scoped rollout. NULL/empty => the override applies to
        # everyone; otherwise a JSON list of team names / usernames.
        sa.Column("scope_teams", sa.Text),
        sa.Column("scope_users", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128)),
    )
    op.create_table(
        "app_setting_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text),
        sa.Column("action", sa.String(16), nullable=False),  # set | clear
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(128)),
    )
    op.create_index("ix_app_setting_history_key", "app_setting_history", ["key"])


def downgrade() -> None:
    op.drop_index("ix_app_setting_history_key", table_name="app_setting_history")
    op.drop_table("app_setting_history")
    op.drop_table("app_setting")
