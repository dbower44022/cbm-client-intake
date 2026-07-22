"""Staff-set request status on submissions (Submission Admin, 2026-07-22).

``request_status`` is the staff work state of the REQUEST itself (New /
In Progress / Responded / Closed — the same vocabulary as the CRM's
``CInformationRequest.requestStatus``), distinct from the machine-managed
delivery ``status`` and the binary resolved marker. NULL reads as "New"
(every pre-existing row starts untouched).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_submission_request_status"
down_revision = "0014_email_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission", sa.Column("request_status", sa.String(32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("submission", "request_status")
