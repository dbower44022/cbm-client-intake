"""Staff-supplied values merged over a submission's payload at delivery.

The company-website hold (Doug's ruling 2026-10-07): a public submission that
names a company already in the CRM at a different web address is held, and
Submission Admin resolves it as "same company" (drop the submitted website)
or "different company" (a qualified name). Either is a small JSON of payload
keys the worker merges over the captured payload — which is never rewritten,
being the record of what the visitor sent. Plan: prds/company-website-hold-plan.md
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_delivery_overrides"
down_revision = "0028_user_preference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("delivery_overrides", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("submission", "delivery_overrides")
