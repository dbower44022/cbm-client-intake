"""Analytics cache — materialized results for the analytics platform (Phase A).

Metrics that sweep the CRM are expensive; their results are cached here and
refreshed on a per-metric cadence by the worker (a miss recomputes live). Keyed
by ``(metric_key, context_key, range_key)``. App-only; mirrors
``analytics.store.analytics_cache``.

See prds/analytics-app-plan.md. Phase B adds the metric/panel/page definition
tables (with the authoring UI that fills them); Phase A only needs the cache.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_analytics_cache"
down_revision = "0020_record_comment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_cache",
        sa.Column("metric_key", sa.String(128), primary_key=True),
        sa.Column("context_key", sa.String(160), primary_key=True),
        sa.Column("range_key", sa.String(96), primary_key=True),
        sa.Column("result", sa.Text, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_analytics_cache_expires", "analytics_cache", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_cache_expires", table_name="analytics_cache")
    op.drop_table("analytics_cache")
