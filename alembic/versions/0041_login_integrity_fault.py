"""The login integrity check's faults (prds/mentor-login-integrity-plan.md
§ 4.2, step 4a).

``login_integrity_fault`` — one row per fault the daily check found: the
condition (1-7), a stable key, a one-sentence summary, the mentors and login
it names, when it was first and last seen, when it closed, and (step 4b) who
acknowledged it and when it was emailed. At most one OPEN row per key (a
partial unique index), so a fault found again after closing is a new row.
Training data on the sandbox: reset nightly (core/sandbox_reset.py
RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_login_integrity_fault"
down_revision = "0040_list_stored_counts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_integrity_fault",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fault_key", sa.String(300), nullable=False),
        sa.Column("condition", sa.Integer, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("mentors", postgresql.JSONB),
        sa.Column("login", postgresql.JSONB),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("ack_by_id", sa.String(32)),
        sa.Column("ack_by", sa.String(128)),
        sa.Column("ack_at", sa.DateTime(timezone=True)),
        sa.Column("ack_note", sa.Text),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_login_integrity_fault_open", "login_integrity_fault", ["fault_key"],
        unique=True, postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index("ix_login_integrity_fault_closed", "login_integrity_fault", ["closed_at"])


def downgrade() -> None:
    op.drop_index("ix_login_integrity_fault_closed", table_name="login_integrity_fault")
    op.drop_index("uq_login_integrity_fault_open", table_name="login_integrity_fault")
    op.drop_table("login_integrity_fault")
