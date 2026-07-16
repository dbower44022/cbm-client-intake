"""Documents: Google Drive document metadata (DOC-MGMT PRD §4).

One row per managed document. Drive holds the bytes (drive_file_id is the sole
durable pointer); this table holds the relational truth — record association,
business type, uploader, lifecycle status. The composite index supports the
per-record listing query.

Revision ID: 0005_app_document
Revises: 0004_comms_sync
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_app_document"
down_revision = "0004_comms_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_document",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("drive_file_id", sa.String(length=128), nullable=False),
        sa.Column("drive_folder_id", sa.String(length=128)),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("record_name", sa.String(length=255)),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128)),
        sa.Column("doc_type", sa.String(length=64)),
        sa.Column("web_view_link", sa.String(length=512)),
        sa.Column("uploaded_by", sa.String(length=128)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_time", sa.DateTime(timezone=True)),
        sa.Column("checksum_md5", sa.String(length=64)),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
    )
    op.create_index(
        "ix_app_document_drive_file_id", "app_document", ["drive_file_id"], unique=True
    )
    op.create_index("ix_app_document_entity_type", "app_document", ["entity_type"])
    op.create_index("ix_app_document_record_id", "app_document", ["record_id"])
    op.create_index(
        "ix_app_document_record",
        "app_document",
        ["entity_type", "record_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_app_document_record", table_name="app_document")
    op.drop_index("ix_app_document_record_id", table_name="app_document")
    op.drop_index("ix_app_document_entity_type", table_name="app_document")
    op.drop_index("ix_app_document_drive_file_id", table_name="app_document")
    op.drop_table("app_document")
