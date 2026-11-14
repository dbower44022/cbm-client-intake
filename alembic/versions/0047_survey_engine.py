"""The survey engine's tables (prds/business-evaluation-plan.md, ruling BE23;
phase 2b).

Business Evaluation's ``evaluation_link`` and ``evaluation_answer`` become the
engine's ``survey_link`` and ``survey_answer``. A link now names its survey
purpose, the CRM record it points at (entity type and id), the purpose's own
data as JSON, and a display snapshot. Every existing row is filled in as
Business Evaluation's: purpose ``business-evaluation``, entity
``CEngagement``, record id from ``engagement_id``; ``data`` holds
``client_profile_id``, ``round``, ``area_keys`` and ``profile_needed``; the
display snapshot is ``company_name``. Those six columns are then dropped.
``survey_answer`` keeps every column; only its name and its constraint and
index names change.

The downgrade restores both tables as migration 0044 made them, refilling the
old columns from ``data``. It deletes links of any other survey purpose, and
their answers, which the old layout cannot hold.

Training data on the sandbox (core/sandbox_reset.py RESET_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047_survey_engine"
down_revision = "0046_integration_fix_plan"
branch_labels = None
depends_on = None

PURPOSE = "business-evaluation"


def upgrade() -> None:
    # 1. The names.
    op.rename_table("evaluation_link", "survey_link")
    op.rename_table("evaluation_answer", "survey_answer")
    op.execute("ALTER TABLE survey_link RENAME CONSTRAINT uq_evaluation_link_token "
               "TO uq_survey_link_token")
    op.execute("ALTER TABLE survey_link RENAME CONSTRAINT evaluation_link_pkey "
               "TO survey_link_pkey")
    op.execute("ALTER TABLE survey_answer RENAME CONSTRAINT uq_evaluation_answer_link_survey "
               "TO uq_survey_answer_link_survey")
    op.execute("ALTER TABLE survey_answer RENAME CONSTRAINT evaluation_answer_pkey "
               "TO survey_answer_pkey")
    op.execute("ALTER INDEX ix_evaluation_answer_due RENAME TO ix_survey_answer_due")

    # 2. The new columns, empty for now.
    op.add_column("survey_link", sa.Column("purpose", sa.String(64)))
    op.add_column("survey_link", sa.Column("entity_type", sa.String(64)))
    op.add_column("survey_link", sa.Column("record_id", sa.String(32)))
    op.add_column("survey_link", sa.Column("data", postgresql.JSONB))
    op.add_column("survey_link", sa.Column("display_name", sa.String(255)))

    # 3. Every existing link is Business Evaluation's.
    op.execute(sa.text(
        "UPDATE survey_link SET purpose = :purpose, entity_type = 'CEngagement', "
        "record_id = engagement_id, display_name = company_name, "
        "data = jsonb_build_object('client_profile_id', client_profile_id, 'round', round, "
        "'area_keys', area_keys, 'profile_needed', profile_needed)"
    ).bindparams(purpose=PURPOSE))

    # 4. Required from now on.
    for column in ("purpose", "entity_type", "record_id", "data"):
        op.alter_column("survey_link", column, nullable=False)

    # 5. The old columns and index go; the new index comes.
    op.drop_index("ix_evaluation_link_engagement", table_name="survey_link")
    for column in ("engagement_id", "client_profile_id", "round", "area_keys",
                   "profile_needed", "company_name"):
        op.drop_column("survey_link", column)
    op.create_index("ix_survey_link_record", "survey_link",
                    ["purpose", "entity_type", "record_id", "created_at"])


def downgrade() -> None:
    # 5. Back: the old index and columns.
    op.drop_index("ix_survey_link_record", table_name="survey_link")
    op.add_column("survey_link", sa.Column("engagement_id", sa.String(32)))
    op.add_column("survey_link", sa.Column("client_profile_id", sa.String(32)))
    op.add_column("survey_link", sa.Column("round", sa.Integer))
    op.add_column("survey_link", sa.Column("area_keys", postgresql.JSONB))
    op.add_column("survey_link", sa.Column("profile_needed", sa.Boolean,
                                           nullable=False, server_default=sa.true()))
    op.add_column("survey_link", sa.Column("company_name", sa.String(255)))

    # 3. Back: the old layout holds Business Evaluation links only.
    op.execute(sa.text(
        "DELETE FROM survey_answer WHERE link_id IN "
        "(SELECT id FROM survey_link WHERE purpose <> :purpose)").bindparams(purpose=PURPOSE))
    op.execute(sa.text("DELETE FROM survey_link WHERE purpose <> :purpose")
               .bindparams(purpose=PURPOSE))
    op.execute(
        "UPDATE survey_link SET engagement_id = record_id, company_name = display_name, "
        "client_profile_id = data->>'client_profile_id', round = (data->>'round')::int, "
        "area_keys = COALESCE(data->'area_keys', '[]'::jsonb), "
        "profile_needed = COALESCE((data->>'profile_needed')::boolean, true)"
    )
    for column in ("engagement_id", "client_profile_id", "round", "area_keys"):
        op.alter_column("survey_link", column, nullable=False)
    op.create_index("ix_evaluation_link_engagement", "survey_link",
                    ["engagement_id", "created_at"])

    # 2. Back: the new columns go.
    for column in ("purpose", "entity_type", "record_id", "data", "display_name"):
        op.drop_column("survey_link", column)

    # 1. Back: the names.
    op.execute("ALTER INDEX ix_survey_answer_due RENAME TO ix_evaluation_answer_due")
    op.execute("ALTER TABLE survey_answer RENAME CONSTRAINT survey_answer_pkey "
               "TO evaluation_answer_pkey")
    op.execute("ALTER TABLE survey_answer RENAME CONSTRAINT uq_survey_answer_link_survey "
               "TO uq_evaluation_answer_link_survey")
    op.execute("ALTER TABLE survey_link RENAME CONSTRAINT survey_link_pkey "
               "TO evaluation_link_pkey")
    op.execute("ALTER TABLE survey_link RENAME CONSTRAINT uq_survey_link_token "
               "TO uq_evaluation_link_token")
    op.rename_table("survey_answer", "evaluation_answer")
    op.rename_table("survey_link", "evaluation_link")
