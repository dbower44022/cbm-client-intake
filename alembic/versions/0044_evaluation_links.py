"""Business Evaluation, phase 1: the evaluation links and the saved answers
(prds/business-evaluation-plan.md § 5, rulings BE12 and BE13).

``evaluation_link`` — one row per link emailed to a client: a random token
(never a CRM id), the engagement and client profile it belongs to, the round,
the area surveys it opens, whether the business profile is still owed, the
company name shown on the first screen (so an open never calls the CRM), when
consent was given, who made it, when it expires and when it was replaced.

``evaluation_answer`` — one row per survey per link: the answers saved as the
client goes, and on submit the time, the submission token and the CRM write's
progress (delivered, or the last error and when to retry).

Training data on the sandbox (core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044_evaluation_links"
down_revision = "0043_integration_test_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_link",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("engagement_id", sa.String(32), nullable=False),
        sa.Column("client_profile_id", sa.String(32), nullable=False),
        sa.Column("round", sa.Integer, nullable=False),
        sa.Column("area_keys", postgresql.JSONB, nullable=False),
        sa.Column("profile_needed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("company_name", sa.String(255)),
        sa.Column("consent_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replaced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token", name="uq_evaluation_link_token"),
    )
    op.create_index("ix_evaluation_link_engagement", "evaluation_link", ["engagement_id", "created_at"])
    op.create_table(
        "evaluation_answer",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("link_id", sa.String(36), nullable=False),
        sa.Column("survey_key", sa.String(64), nullable=False),
        sa.Column("survey_version", sa.String(64), nullable=False),
        sa.Column("answers", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("submission_token", sa.String(64)),
        sa.Column("crm_record_id", sa.String(32)),
        sa.Column("crm_started_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_error", sa.Text),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("link_id", "survey_key", name="uq_evaluation_answer_link_survey"),
    )
    op.create_index("ix_evaluation_answer_due", "evaluation_answer", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_answer_due", table_name="evaluation_answer")
    op.drop_table("evaluation_answer")
    op.drop_index("ix_evaluation_link_engagement", table_name="evaluation_link")
    op.drop_table("evaluation_link")
