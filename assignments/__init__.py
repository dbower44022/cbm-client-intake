"""Staff-only mentor assignment dashboard (``/assignments``).

Reads ``CEngagement`` records with ``engagementStatus="Submitted"`` and lets an
authenticated CBM staff user assign each to a mentor who is accepting new
clients. The selection sets the engagement's assigned user + mentor profile,
moves it to ``Pending Acceptance``, and re-assigns the engagement's contacts and
client records to the mentor's user.

Unlike the public intake forms, every action authenticates against EspoCRM with
the user's own username/password and runs as that user (their token), so EspoCRM
enforces their permissions and records them as the modifier.
"""

from .router import router

__all__ = ["router"]
