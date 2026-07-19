"""Staff triage notes on submissions (Submission Admin rebuild, 2026-07-19).

Free-text notes staff add/edit in /ops while resolving a submission (most
often an info-request). Staff-only — never delivered to the CRM.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_submission_notes"
down_revision = "0010_conversation_seen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("submission", "notes")
