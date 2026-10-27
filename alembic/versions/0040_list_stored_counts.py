"""Stored counts for every list (build plan § 7e.14, ruling 131; M11).

``audience_list`` gains:

- ``counts`` (JSONB) — the members and how many each channel reaches:
  ``{"people", "email", "text", "postcard", "notReachable"}``.
- ``counted_at`` — when those numbers were taken.

``audience_list_member`` gains ``reach`` — the channels that member reaches,
as letters (``e`` email, ``t`` text, ``p`` postcard; empty = none; NULL = not
counted since the member row was written). The View page filters by it.

The nightly count pass and *Refresh* fill all three. The downgrade drops
them; nothing else reads them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0040_list_stored_counts"
down_revision = "0039_ready_made_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audience_list", sa.Column("counts", JSONB(), nullable=True))
    op.add_column("audience_list", sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("audience_list_member", sa.Column("reach", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("audience_list_member", "reach")
    op.drop_column("audience_list", "counted_at")
    op.drop_column("audience_list", "counts")
