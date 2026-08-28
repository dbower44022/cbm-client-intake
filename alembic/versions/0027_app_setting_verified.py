"""Verified settings — encrypted values, and changes that revert themselves.

Doug's ruling, 2026-08-28: *"All settings should be editable, unless a change
would make the system unusable. Then there must be a verification that the
system is still functional."*

That puts two new obligations on this table.

**Secrets can now be stored here**, which the 0025 docstring explicitly assumed
would never happen (*"secrets are never stored here at all … so this table needs
no encryption"*). They are encrypted with the same Fernet key that already
protects ``app_config``, and ``encrypted`` marks a row whose ``value`` is a
ciphertext rather than plain text. A secret's value is **never** rendered back:
the page can set one and can say whether one is set, and that is all.

**A dangerous change must be able to undo itself.** ``previous_value`` is what to
go back to, ``revert_at`` is when to do it automatically, and ``confirmed``
records that a human said the system still works. This is deliberately NOT the
existing ``temporary``/``review_at`` pair, which is advisory by ruling 5 —
"reported, never auto-reverted". These two mechanisms look alike and mean
opposite things, so they are separate columns rather than a reused flag.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_app_setting_verified"
down_revision = "0026_app_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A ciphertext, not plain text. Nullable-with-default so every existing row
    # reads as plain, which is what they all are.
    op.add_column(
        "app_setting",
        sa.Column("encrypted", sa.Boolean, nullable=False, server_default="false"),
    )
    # What to restore if this change turns out to break the system. Empty string
    # and NULL mean different things: NULL is "there was no override before, so
    # reverting means deleting the row".
    op.add_column("app_setting", sa.Column("previous_value", sa.Text))
    # When to revert automatically unless confirmed. NULL = no countdown.
    op.add_column(
        "app_setting", sa.Column("revert_at", sa.DateTime(timezone=True))
    )
    # A human has confirmed the system still works with this value.
    op.add_column(
        "app_setting",
        sa.Column("confirmed", sa.Boolean, nullable=False, server_default="true"),
    )
    # The sweep asks "anything past its deadline and unconfirmed?" on a timer.
    op.create_index(
        "ix_app_setting_revert_at", "app_setting", ["revert_at"]
    )
    # History gains the same, so "it reverted itself at 14:02" is answerable.
    op.add_column(
        "app_setting_history",
        sa.Column("encrypted", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("app_setting_history", "encrypted")
    op.drop_index("ix_app_setting_revert_at", table_name="app_setting")
    op.drop_column("app_setting", "confirmed")
    op.drop_column("app_setting", "revert_at")
    op.drop_column("app_setting", "previous_value")
    op.drop_column("app_setting", "encrypted")
