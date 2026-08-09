"""Operations jobs run from the System Settings page (plan §5, phase 5).

One row per run. A mutating job is TWO rows' worth of lifecycle in one: the
dry-run stores its plan and a fingerprint of it, and the apply step re-derives
the plan and refuses if the fingerprint moved (ruling 7 — you apply the plan you
reviewed, not a fresh one).

Rows survive a page reload and are visible to every admin, so two people can't
unknowingly run the same repair twice.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_app_job"
down_revision = "0025_app_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_key", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),      # dry_run | apply
        sa.Column("status", sa.String(16), nullable=False),    # running | done | failed | refused
        sa.Column("plan_fingerprint", sa.String(64)),
        sa.Column("plan_of", sa.String(36)),   # the dry-run this apply was authorised by
        sa.Column("output", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("actor", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_app_job_started_at", "app_job", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_app_job_started_at", table_name="app_job")
    op.drop_table("app_job")
