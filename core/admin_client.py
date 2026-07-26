"""The provisioning admin service account, as a lazy client factory.

A few operations are impossible under a staff user's own token no matter how
the CRM roles are set — EspoCRM reserves User creation for admins, and Team
membership likewise — so those run as a dedicated **admin service account**
(``ESPO_PROVISION_USERNAME`` / ``ESPO_PROVISION_PASSWORD``) via the
``App/user`` token flow. This module owns that login: the token cache, the
re-login on expiry, and the "not configured" answer.

Callers get an async factory and await it only when they actually need the
privileged client, so a normal request never logs the service account in.

Deliberately narrow: escalate a SINGLE operation the signed-in user has
already been authorized for by other means, never a whole request. See
``sessions.service.add_comentor`` for the pattern — the user's own token
performs the write and EspoCRM's own check on the parent record is the gate;
only the foreign-record half is retried as the admin.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from assignments.auth import login_token, session_expired

from .config import Settings
from .espo import EspoClient, EspoError

log = logging.getLogger("cbm_intake.admin_client")

AdminClientFactory = Callable[[], Awaitable[EspoClient]]

# Auth tokens for the admin service account, keyed by base URL + username, for
# the life of the process. Logging in with the PASSWORD on every call meant a
# rotated password turned each sweep into a run of failed admin logins — enough
# to trip EspoCRM's brute-force lockout on the service account.
_TOKEN_CACHE: dict[str, tuple[str, str]] = {}


def admin_client_factory(settings: Settings) -> Optional[AdminClientFactory]:
    """A lazy login factory for the provisioning admin, or ``None`` when the
    credentials aren't configured (or the app is in dry-run).

    Callers that additionally gate on a feature flag should check it themselves;
    this function only answers "are admin credentials usable here?".
    """
    if settings.espo_dry_run or not (
        settings.espo_provision_username and settings.espo_provision_password
    ):
        return None

    async def factory() -> EspoClient:
        cache_key = f"{settings.espo_base_url}:{settings.espo_provision_username}"
        cached = _TOKEN_CACHE.get(cache_key)
        if cached:
            client = EspoClient.for_user_token(
                settings.espo_base_url, cached[0], cached[1],
                settings.request_timeout_seconds,
            )
            try:
                # One cheap read validates the cached token; only a dead token
                # costs a fresh password login.
                await client.app_user()
                return client
            except EspoError as exc:
                if not session_expired(exc):
                    raise
                _TOKEN_CACHE.pop(cache_key, None)
        user_name, token = await login_token(
            settings.espo_base_url,
            settings.espo_provision_username,
            settings.espo_provision_password,
            settings.request_timeout_seconds,
        )
        _TOKEN_CACHE[cache_key] = (user_name, token)
        return EspoClient.for_user_token(
            settings.espo_base_url, user_name, token, settings.request_timeout_seconds
        )

    return factory
