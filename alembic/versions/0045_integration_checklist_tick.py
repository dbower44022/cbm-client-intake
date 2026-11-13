"""Hand ticks on the setup checklists (prds/integrations-tab-plan.md § 7,
phase 4).

``integration_checklist_tick`` — one row per tick or untick of a manual step:
the guide's step number, the sub-tab it was ticked from, ticked or not, who and
when. A step's state is its latest row. Training data on the sandbox
(core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_integration_checklist_tick"
down_revision = "0044_evaluation_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_checklist_tick",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("step_id", sa.String(16), nullable=False),
        sa.Column("integration", sa.String(40), nullable=False),
        sa.Column("ticked", sa.Boolean, nullable=False),
        sa.Column("actor_id", sa.String(32)),
        sa.Column("actor", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_integration_checklist_tick_step", "integration_checklist_tick",
        ["step_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_checklist_tick_step", table_name="integration_checklist_tick")
    op.drop_table("integration_checklist_tick")
