"""Drop the setup checklist's ticks and the fix plans (prds/integrations-tab-plan.md
§ 10, ruling W4; Integrations tab phase 10).

The set-up wizard replaced the setup checklist with its hand ticks, the setup
assistant with its setup plans, and the diagnosis's fix plans. Their two tables
go:

* ``integration_checklist_tick`` (migration 0045);
* ``integration_fix_plan`` (migration 0046), which held fix plans and setup
  plans alike.

**The monthly budget keeps what Claude has spent** (Doug's decision 11-15-26,
option A): before the drop, every fix or setup plan that cost something is
copied into ``integration_agent_call``, the table the budget now reads alone,
with the status ``fix plan`` or ``setup plan``.

Downgrade recreates both tables empty, as 0045 and 0046 made them, and deletes
the copied rows. The ticks and plans themselves are not restored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0049_drop_checklist_fix_plans"
down_revision = "0048_integration_wizard"
branch_labels = None
depends_on = None

COPIED = ("fix plan", "setup plan")


def upgrade() -> None:
    op.execute(
        "INSERT INTO integration_agent_call "
        "(id, integration, screen, status, answer, cost, asked_by, created_at) "
        "SELECT id, integration, NULL, "
        "CASE WHEN kind = 'setup' THEN 'setup plan' ELSE 'fix plan' END, "
        "diagnosis, cost, created_by, created_at "
        "FROM integration_fix_plan WHERE cost > 0"
    )
    op.drop_index("ix_integration_fix_plan_latest", table_name="integration_fix_plan")
    op.drop_table("integration_fix_plan")
    op.drop_index("ix_integration_checklist_tick_step", table_name="integration_checklist_tick")
    op.drop_table("integration_checklist_tick")


def downgrade() -> None:
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
    op.create_table(
        "integration_fix_plan",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("test_run_id", sa.String(36)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("diagnosis", sa.Text),
        sa.Column("confidence", sa.String(16)),
        sa.Column("steps", JSONB, nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("model", sa.String(64)),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("usage", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(128)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_integration_fix_plan_latest", "integration_fix_plan",
                    ["integration", "created_at"])
    op.execute(
        "DELETE FROM integration_agent_call WHERE screen IS NULL AND status IN ('fix plan', 'setup plan')"
    )
