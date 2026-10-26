"""A list's kept-current copy in Constant Contact (build plan § 7e.9; ruling 95).

Four columns on ``audience_list``:

- ``cc_sync`` — the *Keep a copy in Constant Contact* tick. The worker's
  mailing pass syncs every active list that has it.
- ``cc_list_id`` — the copy's id at the vendor. The sandbox reset empties this
  table every night while the copy survives at the vendor, so the sync finds
  the copy by name when the id is missing and never creates a second one.
- ``cc_last_sync_at`` and ``cc_last_sync`` — when the last sync ran and its
  summary (the counts, or the error in words), shown on the list's page.

Unticking or retiring a list stops the sync and keeps the copy; nothing here
deletes a vendor list.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0038_list_constant_contact_copy"
down_revision = "0037_lists_include_leave_out"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audience_list", sa.Column("cc_sync", sa.Boolean(), nullable=False,
                                             server_default=sa.false()))
    op.add_column("audience_list", sa.Column("cc_list_id", sa.String(64)))
    op.add_column("audience_list", sa.Column("cc_last_sync_at", sa.DateTime(timezone=True)))
    op.add_column("audience_list", sa.Column("cc_last_sync", JSONB))


def downgrade() -> None:
    for column in ("cc_last_sync", "cc_last_sync_at", "cc_list_id", "cc_sync"):
        op.drop_column("audience_list", column)
