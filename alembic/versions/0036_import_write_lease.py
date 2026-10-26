"""The import batch's write lease (build plan § 7e.7; found on the M4 live
pass, 10-25-26): two presses of Confirm for one batch within a second — two
tabs, a fast double press, or an automation retry — ran two applies that both
passed the "already created" check before either had recorded a row, and
every lead was created twice. ``write_lease_at`` / ``write_lease_by`` on
``prospect_import_batch`` let the apply and Undo claim the batch for one
request at a time; a second request while it is held is refused naming who
holds it. A lease older than five minutes is stale (a request that died) and
can be taken again.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_import_write_lease"
down_revision = "0035_import_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prospect_import_batch", sa.Column("write_lease_at", sa.DateTime(timezone=True)))
    op.add_column("prospect_import_batch", sa.Column("write_lease_by", sa.String(128)))


def downgrade() -> None:
    op.drop_column("prospect_import_batch", "write_lease_by")
    op.drop_column("prospect_import_batch", "write_lease_at")
