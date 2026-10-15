"""Campaign Management, Phase 1: the campaign links, their visits, and the
prospect import ledger (prds/prospect-marketing/build-plan.md § 2, § 3.7;
ruling 31: links live in the application's database, never as a CRM entity).

``campaign_link`` — one row per link a marketing user makes inside a campaign
(CM-7): its own name, one destination, a short token, a state. The resolve route
``/c/{token}`` reads this table and never the CRM. ``campaign_link_visit`` — one
row per resolve, write-heavy, kept out of the CRM on purpose; the address is a
salted hash, never the address. ``prospect_import_batch`` / ``prospect_import_row``
— the ledger that makes a re-upload of the same file a no-op and records what
each row became.

All four are training data on the sandbox and are RESET nightly
(core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_campaign_links"
down_revision = "0030_mailing_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_link",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(32), nullable=False),
        sa.Column("token", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("destination_kind", sa.String(32), nullable=False),
        sa.Column("destination_target", sa.String(200)),
        sa.Column("destination_slug", sa.String(200)),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_by", sa.String(128)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("history", postgresql.JSONB),
        sa.UniqueConstraint("token", name="uq_campaign_link_token"),
    )
    op.create_index("ix_campaign_link_campaign", "campaign_link", ["campaign_id", "created_at"])
    op.create_table(
        "campaign_link_visit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("link_id", sa.String(36), nullable=False),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("address_hash", sa.String(64)),
        sa.Column("late", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("agent_class", sa.String(16)),
        sa.Column("scan_token", sa.String(16)),
    )
    op.create_index("ix_campaign_link_visit_link", "campaign_link_visit", ["link_id", "visited_at"])
    op.create_table(
        "prospect_import_batch",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("door", sa.String(32), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("plan", postgresql.JSONB),
        sa.Column("result", postgresql.JSONB),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_prospect_import_batch_file", "prospect_import_batch", ["file_sha256"])
    op.create_table(
        "prospect_import_row",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("external_reference", sa.String(100)),
        sa.Column("business_name", sa.String(255)),
        sa.Column("postal_code", sa.String(40)),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("prospect_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prospect_import_row_batch", "prospect_import_row", ["batch_id"])
    op.create_index("ix_prospect_import_row_hash", "prospect_import_row", ["row_hash"])


def downgrade() -> None:
    op.drop_index("ix_prospect_import_row_hash", table_name="prospect_import_row")
    op.drop_index("ix_prospect_import_row_batch", table_name="prospect_import_row")
    op.drop_table("prospect_import_row")
    op.drop_index("ix_prospect_import_batch_file", table_name="prospect_import_batch")
    op.drop_table("prospect_import_batch")
    op.drop_index("ix_campaign_link_visit_link", table_name="campaign_link_visit")
    op.drop_table("campaign_link_visit")
    op.drop_index("ix_campaign_link_campaign", table_name="campaign_link")
    op.drop_table("campaign_link")
