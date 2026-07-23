"""Auto-close already-delivered record-creating submissions (2026-07-22).

Doug's ruling: client-intake / volunteer / partner / sponsor submissions that
delivered their CRM records need no Submission-Admin action — the downstream
admin team owns them. New deliveries auto-close going forward (the app); this
back-closes the ones already sitting "completed but open" in the queue so the
open work list is only the info-request / info-email items that need a reply.

Sets the same fields the app's auto-close writes (closed + resolved, actor
"system", reason "Process completed"); leaves any already-closed row untouched
and preserves an existing resolved stamp.
"""

from __future__ import annotations

from alembic import op

revision = "0019_autoclose_backfill"
down_revision = "0018_submission_close"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE submission
        SET closed_at = updated_at,
            closed_by = 'system',
            close_reason = 'Process completed',
            resolved_at = COALESCE(resolved_at, updated_at),
            resolved_by = COALESCE(resolved_by, 'system'),
            request_status = 'Closed'
        WHERE status = 'completed'
          AND form_slug NOT IN ('info-request', 'info-email')
          AND closed_at IS NULL
        """
    )


def downgrade() -> None:
    # Reverse only the rows this backfill (and the app's auto-close) created.
    op.execute(
        """
        UPDATE submission
        SET closed_at = NULL, closed_by = NULL, close_reason = NULL,
            resolved_at = NULL, resolved_by = NULL
        WHERE close_reason = 'Process completed' AND closed_by = 'system'
        """
    )
