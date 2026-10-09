"""The mailing service connection — one row per deployment (Phase C).

One Constant Contact account, one developer application, one deployment
(plan § 11.1). The row holds the OAuth2 token pair as Fernet ciphertext
(``APP_ENCRYPTION_KEY``, refused without it), the access-token expiry the locked
refresh reads, who connected and when, the re-authorisation mark, and the
caches the push and pull keep (the list id, the pull cursor, the last push).
Not an ``app_setting`` row: nobody edits it, and the history table would gain a
"(secret set)" line per refresh. Kept by the sandbox reset — a connection
crm-test lost every night would be no connection.
Plan: prds/mailing-list-and-event-sponsorship-plan.md § 11.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_mailing_connection"
down_revision = "0029_delivery_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailing_connection",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.Text),
        sa.Column("account_label", sa.String(255)),
        sa.Column("connected_by", sa.String(128)),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("list_id", sa.String(64)),
        sa.Column("pull_cursor", sa.DateTime(timezone=True)),
        sa.Column("last_push_at", sa.DateTime(timezone=True)),
        sa.Column("last_push_summary", postgresql.JSONB),
    )


def downgrade() -> None:
    op.drop_table("mailing_connection")
