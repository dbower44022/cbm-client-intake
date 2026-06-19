"""Build a per-user EspoCRM client from the session."""

from __future__ import annotations

from typing import Any

from core.config import Settings
from core.espo import EspoClient


def client_for(settings: Settings, session_user: dict[str, Any]) -> EspoClient:
    """An ``EspoClient`` that acts as the logged-in user (their auth token)."""
    return EspoClient.for_user_token(
        settings.espo_base_url,
        session_user["userName"],
        session_user["token"],
        settings.request_timeout_seconds,
    )
