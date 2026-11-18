"""The worker's heartbeat carries the switches it runs with
(prds/events/event-hosting-plan.md § 8, item 1).

On the Business Mentors Association's system (11-18-26) the web part ran with
Events on and the worker with it off, so every confirmation was skipped and
nothing on System Settings could show it: the page reads the web part's own
settings. The worker now writes its effective switches beside each beat, and
Feature readiness compares them with the web part's.

One nullable column; a worker on an older build leaves it empty, which the page
reads as "not reported yet". Downgrade drops it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0050_heartbeat_switches"
down_revision = "0049_drop_checklist_fix_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("worker_heartbeat", sa.Column("switches", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("worker_heartbeat", "switches")
