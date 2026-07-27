"""Intake-receipt redesign (2026-07-27): link each submission row to its CRM
CIntakeSubmission receipt so the app can update the receipt as status /
disposition changes and the reconciliation sweep can compare the two systems.

Revision ID: 0023_crm_receipt_id
Revises: 0022_analytics_definitions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_crm_receipt_id"
down_revision = "0022_analytics_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submission", sa.Column("crm_receipt_id", sa.String(64)))
    op.create_index("ix_submission_crm_receipt", "submission", ["crm_receipt_id"])


def downgrade() -> None:
    op.drop_index("ix_submission_crm_receipt", table_name="submission")
    op.drop_column("submission", "crm_receipt_id")
