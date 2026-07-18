"""Worker liveness heartbeat (P1-6, reliability review 2026-07-17).

One fixed row the delivery worker upserts each loop iteration; /healthz reports
the beat's age so an external uptime check can see a dead or wedged worker —
the in-worker alerter cannot alert on its own death.

Revision ID: 0007_worker_heartbeat
Revises: 0006_app_document_client
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_worker_heartbeat"
down_revision = "0006_app_document_client"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.String(length=16), primary_key=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeat")
