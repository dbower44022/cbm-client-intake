"""The qualification ladder's manual snapshot (prds/prospect-marketing/
build-plan.md § 7e.3; rulings 106, 117).

``lead_level_manual`` — one row per lead whose level a person set by hand:
the level, the facts the lead held at that moment (named person, phone,
email, referrer), who set it and when. The CRM holds the level and the who
and when (``CProspect.qualificationLevel``, ``levelSetByHand``,
``levelSetAt``); only the facts snapshot lives here, because ruling 106 moves
a hand-set level forward only when a fact ABSENT at the setting is now
present. Training data on the sandbox: reset nightly (core/sandbox_reset.py
RESET_TABLES), and a hand-set level with no snapshot is never moved (117).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_lead_level_manual"
down_revision = "0033_enrichment_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_level_manual",
        sa.Column("lead_id", sa.String(32), primary_key=True),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("facts", postgresql.JSONB, nullable=False),
        sa.Column("set_by_id", sa.String(32)),
        sa.Column("set_by", sa.String(128)),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lead_level_manual")
