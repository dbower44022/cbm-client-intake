"""Documents: client_record_id for engagement-anchored documents (PRD v1.2).

Decision D-07: client-work documents anchor to the CEngagement record; the
parent client record id is denormalized here for cross-engagement client
reporting. Null for non-engagement anchors (mentor Contact documents, partner/
sponsor profiles).

Revision ID: 0006_app_document_client
Revises: 0005_app_document
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_app_document_client"
down_revision = "0005_app_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_document", sa.Column("client_record_id", sa.String(length=64))
    )
    op.create_index(
        "ix_app_document_client_record_id", "app_document", ["client_record_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_app_document_client_record_id", table_name="app_document")
    op.drop_column("app_document", "client_record_id")
