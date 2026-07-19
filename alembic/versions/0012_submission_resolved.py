"""Staff resolution marker on submissions (Submission Admin, 2026-07-19).

"Is anyone still waiting on us?" — independent of the delivery status.
NULL resolved_at = open; the /ops grid defaults to open rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_submission_resolved"
down_revision = "0011_submission_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("submission", sa.Column("resolved_by", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("submission", "resolved_by")
    op.drop_column("submission", "resolved_at")
