"""Inbound email attachments auto-filed to Documents (email-quality plan §3.1).

Two pieces: ``content_sha256`` on ``app_document`` (the per-record dedup key —
a five-reply thread re-attaching the same PDF stores it once), and the
``comm_attachment`` filing ledger — one row per (message part, target record),
which is both the thread view's chip render source and the retry ledger for
failed filings.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_email_attachments"
down_revision = "0013_submission_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_document", sa.Column("content_sha256", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_app_document_content_sha256", "app_document", ["content_sha256"]
    )
    op.create_table(
        "comm_attachment",
        sa.Column("rfc_message_id", sa.String(255), nullable=False),
        sa.Column("part_index", sa.Integer, nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255)),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("size", sa.BigInteger),
        sa.Column("sha256", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("document_id", sa.String(36)),
        sa.Column("gmail_message_id", sa.String(100)),
        sa.Column("source_mailbox", sa.String(255)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "rfc_message_id", "part_index", "entity_type", "record_id"
        ),
    )
    op.create_index(
        "ix_comm_attachment_record", "comm_attachment", ["entity_type", "record_id"]
    )
    op.create_index("ix_comm_attachment_status", "comm_attachment", ["status"])


def downgrade() -> None:
    op.drop_table("comm_attachment")
    op.drop_index("ix_app_document_content_sha256", table_name="app_document")
    op.drop_column("app_document", "content_sha256")
