"""Analytics definition tables (Phase B) — the metric library + authored pages.

`analytics_metric` is the reusable builder-metric library (entity + filters +
aggregation in `definition`); `analytics_page` is an admin-curated page whose
panels are stored inline as a JSON list. Mirrors
`analytics.store.analytics_metric` / `analytics.store.analytics_page`.

See prds/analytics-app-plan.md (Phase B). App-only; no CRM change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_analytics_definitions"
down_revision = "0021_analytics_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_metric",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("source", sa.String(16), nullable=False, server_default="crm"),
        sa.Column("result_shape", sa.String(16), nullable=False),
        sa.Column("default_viz", sa.String(16), nullable=False),
        sa.Column("entity", sa.String(64)),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("applies_to", sa.Text, nullable=False, server_default='["system"]'),
        sa.Column("context_param", sa.String(64)),
        sa.Column("cache_mode", sa.String(16), nullable=False, server_default="cached"),
        sa.Column("refresh_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("time_aware", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128)),
    )
    op.create_table(
        "analytics_page",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("scope", sa.String(64), nullable=False, server_default="system"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.Text),
        sa.Column("team_gate", sa.Text, nullable=False, server_default="[]"),
        sa.Column("portal_dashboard", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("default_range", sa.String(32), nullable=False, server_default="last12mo"),
        sa.Column("panels", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("analytics_page")
    op.drop_table("analytics_metric")
