"""The Website images (prds/chapter-website-plan.md, piece A, decision 4.3).

``website_image`` — one row per image the chapter website shows: the logo and
the header graphic, uploaded in System Settings and served at
``/api/website/images/{name}``. Configuration, so the sandbox's nightly reset
keeps it (core/sandbox_reset.py KEEP_TABLES).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_website_image"
down_revision = "0041_login_integrity_fault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_image",
        sa.Column("name", sa.String(16), primary_key=True),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("website_image")
