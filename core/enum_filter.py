"""Drop enum/multiEnum values the live CRM no longer accepts, so one drifted
option can't fail a whole record create.

When the CRM team renames/removes an enum option, a submission carrying the old
value 400s on create (``validationFailure``) and the record — including the
person's contact details — is never created. For lead-capture forms that's the
wrong trade: better to create the record with the *valid* data and simply omit
the unrecognized value, leaving a note so staff can follow up.

:class:`EnumSanitizer` validates fields against the live option set
(``EspoApi.metadata_enum_options``), caching each field's options for the life of
one delivery, and remembers what it dropped (for a record note + logs). It
**fails open**: if options can't be fetched (e.g. dry-run, or a metadata error)
the value is kept unchanged, so this never drops data it couldn't verify.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .espo import EspoApi

log = logging.getLogger("cbm_intake.enum_filter")


class EnumSanitizer:
    """Validate enum-backed payload values for one entity against live CRM options."""

    def __init__(self, client: EspoApi, entity: str) -> None:
        self._client = client
        self._entity = entity
        self._cache: dict[str, Optional[list[str]]] = {}
        # field -> values that were dropped (for note()/visibility)
        self.dropped: dict[str, list[str]] = {}

    async def _options(self, field: str) -> Optional[list[str]]:
        if field not in self._cache:
            try:
                self._cache[field] = await self._client.metadata_enum_options(
                    self._entity, field
                )
            except Exception as exc:  # noqa: BLE001 — fail open, never block the create
                log.warning(
                    "enum options fetch failed for %s.%s (%s); keeping value as-is",
                    self._entity, field, exc,
                )
                self._cache[field] = None
        return self._cache[field]

    async def enum(self, field: str, value: Any) -> Any:
        """A single enum: return ``value`` if valid (or unverifiable), else ``None``."""
        if value in (None, ""):
            return value
        options = await self._options(field)
        if options is None:  # couldn't verify — keep
            return value
        if value in options:
            return value
        self.dropped.setdefault(field, []).append(value)
        log.warning(
            "%s.%s: dropping unrecognized value %r (not in live enum)",
            self._entity, field, value,
        )
        return None

    async def multi(self, field: str, values: Any) -> Any:
        """A multiEnum: return only the valid values (or all, if unverifiable)."""
        if not values:
            return values
        options = await self._options(field)
        if options is None:
            return values
        kept = [v for v in values if v in options]
        dropped = [v for v in values if v not in options]
        if dropped:
            self.dropped.setdefault(field, []).extend(dropped)
            log.warning(
                "%s.%s: dropping unrecognized values %s (not in live enum)",
                self._entity, field, dropped,
            )
        return kept

    def note(self) -> str:
        """One-line summary of dropped values, for a record's notes field. Empty
        when nothing was dropped."""
        if not self.dropped:
            return ""
        parts = [f"{field}: {', '.join(map(str, vals))}" for field, vals in self.dropped.items()]
        return (
            "Some submitted values were not recognized by the CRM and were left "
            "blank — follow up with the applicant. " + "; ".join(parts)
        )
