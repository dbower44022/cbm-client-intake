"""The import tool's storage (prds/prospect-marketing/build-plan.md § 7e.7 and
§ 7e.11; rulings 79-88, 111, 123, 127) — step M4 of the Marketing Management
redesign.

``import_template`` — one row per saved template (ruling 79, shared by the
team): the Lead Source, the list source, *Qualified by*, *Enters at* (ruling
111), the referrer partner, the column mapping with its fixes (ruling 82) and
the header signature recognition scores against (ruling 81). Training data on
the sandbox (core/sandbox_reset.py RESET_TABLES); the nightly restore puts the
demo template back (campaigns/sandbox_demo.py).

``prospect_import_batch`` gains: the preview as a worker job (ruling 123 —
``plan_status`` queued → running → ready / failed, ``plan_error``,
``plan_progress`` and the lease stamp ``plan_claimed_at``), the rows the
reviewer excluded (``excluded_rows``, their hashes), the template and file the
batch came from, and the Undo stamp (ruling 87: ``undone_at``, ``undone_by``,
``undo_result`` — the ids deleted, the touched leads left).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_import_templates"
down_revision = "0034_lead_level_manual"
branch_labels = None
depends_on = None

_BATCH_COLUMNS = (
    sa.Column("excluded_rows", postgresql.JSONB),
    sa.Column("undone_at", sa.DateTime(timezone=True)),
    sa.Column("undone_by", sa.String(128)),
    sa.Column("undo_result", postgresql.JSONB),
    sa.Column("plan_status", sa.String(16)),
    sa.Column("plan_error", sa.Text),
    sa.Column("plan_progress", postgresql.JSONB),
    sa.Column("plan_claimed_at", sa.DateTime(timezone=True)),
    sa.Column("template_id", sa.String(36)),
    sa.Column("file_name", sa.String(255)),
)


def upgrade() -> None:
    op.create_table(
        "import_template",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("door", sa.String(32), nullable=False),
        sa.Column("list_source", sa.String(255)),
        sa.Column("qualified_by", sa.String(255)),
        sa.Column("enters_at", sa.String(16), nullable=False),
        sa.Column("referrer_partner_id", sa.String(32)),
        sa.Column("referrer_partner_name", sa.String(200)),
        sa.Column("mapping", postgresql.JSONB, nullable=False),
        sa.Column("header_signature", postgresql.JSONB, nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_batch_id", sa.String(36)),
    )
    for column in _BATCH_COLUMNS:
        op.add_column("prospect_import_batch", column)
    op.create_index("ix_prospect_import_batch_plan", "prospect_import_batch", ["plan_status"])


def downgrade() -> None:
    op.drop_index("ix_prospect_import_batch_plan", table_name="prospect_import_batch")
    for column in reversed(_BATCH_COLUMNS):
        op.drop_column("prospect_import_batch", column.name)
    op.drop_table("import_template")
