"""Gmail thread anchoring on submissions (info@ mailbox integration, 2026-07-19).

``thread_ids`` holds the Gmail thread ids that belong to a submission — the
threads staff started from /ops (recorded after each send as the shared
info@ mailbox) and, for an email-originated submission, the inbound thread
itself. The Submission Admin conversation view shows exactly these threads
instead of an address search, so a submitter's unrelated mail never appears.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_submission_threads"
down_revision = "0012_submission_resolved"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("thread_ids", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("submission", "thread_ids")
