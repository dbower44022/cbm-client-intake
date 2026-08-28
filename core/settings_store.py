"""The System Settings override store (prds/system-settings-plan.md §3).

One row per **overridden** setting in ``app_setting``, plus an append-only
``app_setting_history``. Everything not in the table still comes from the
environment, so an empty table is exactly today's behaviour.

Two rules are enforced here rather than in the UI, because a UI check is not a
control:

* **The denylist is refused server-side.** ``core/settings_registry.DENYLIST``
  covers every secret, the CRM target, the database, and the two switches
  guarding this feature — writing one raises :class:`SettingsError`.
* **A value must parse before it is stored.** Values are TEXT; the write path
  builds a throwaway ``Settings`` with the new value merged in and rejects it if
  pydantic can't coerce it. A stored value that cannot load would otherwise take
  the whole override set down with it on the next refresh.

Ruling 6 governs the read path: :func:`refresh_into_config` swallows failures
and leaves the previous (or environment) configuration in place. The app must
degrade to the overlay, never to the code default.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Table,
    Text,
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from . import config as config_module
from .config import Settings
from .settings_registry import DENYLIST, is_editable
from .store import make_async_engine, metadata

log = logging.getLogger("cbm_intake.settings")

app_setting = Table(
    "app_setting",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("temporary", Boolean, nullable=False, server_default="false"),
    Column("review_at", DateTime(timezone=True)),
    Column("scope_teams", Text),
    Column("scope_users", Text),
    Column("reason", Text),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(128)),
    # --- verified settings (0027) -----------------------------------------
    # `value` is a Fernet ciphertext rather than plain text.
    Column("encrypted", Boolean, nullable=False, server_default="false"),
    # What to restore if this change proves harmful. NULL means "there was no
    # override before", so reverting deletes the row rather than writing a value.
    Column("previous_value", Text),
    # Revert automatically at this time unless confirmed. NULL = no countdown.
    # Deliberately NOT `review_at`, which is advisory and never auto-reverts.
    Column("revert_at", DateTime(timezone=True)),
    Column("confirmed", Boolean, nullable=False, server_default="true"),
)

app_setting_history = Table(
    "app_setting_history",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("key", String(64), nullable=False),
    Column("old_value", Text),
    Column("new_value", Text),
    Column("action", String(16), nullable=False),
    Column("reason", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("actor", String(128)),
    Index("ix_app_setting_history_key", "key"),
)


class SettingsError(Exception):
    """A rejected write — denylisted key, unknown key, or an unparseable value."""


@dataclass(frozen=True)
class Override:
    key: str
    value: str
    temporary: bool = False
    review_at: Optional[datetime] = None
    scope_teams: tuple[str, ...] = ()
    scope_users: tuple[str, ...] = ()
    reason: str = ""
    updated_at: Optional[datetime] = None
    updated_by: str = ""
    # --- verified settings -------------------------------------------------
    encrypted: bool = False
    previous_value: Optional[str] = None
    revert_at: Optional[datetime] = None
    confirmed: bool = True

    @property
    def awaiting_confirmation(self) -> bool:
        """Applied, and it will undo itself unless a human says it is working."""
        return self.revert_at is not None and not self.confirmed

    @property
    def scoped(self) -> bool:
        """A scoped override does NOT change the process-wide configuration; it
        is evaluated per user at request time (plan §5, scoped rollout)."""
        return bool(self.scope_teams or self.scope_users)

    def as_dict(self) -> dict[str, Any]:
        from core.settings_registry import is_secret

        # A secret's value never leaves the server, not even here. The page can
        # set one and can say whether one is set; it can never read one back.
        secret = is_secret(self.key)
        return {
            "key": self.key,
            "value": "" if secret else self.value,
            "isSet": bool(self.value) if secret else None,
            "encrypted": self.encrypted,
            "revertAt": self.revert_at.isoformat() if self.revert_at else None,
            "confirmed": self.confirmed,
            "awaitingConfirmation": self.awaiting_confirmation,
            "temporary": self.temporary,
            "reviewAt": self.review_at.isoformat() if self.review_at else None,
            "scopeTeams": list(self.scope_teams),
            "scopeUsers": list(self.scope_users),
            "scoped": self.scoped,
            "reason": self.reason or "",
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "updatedBy": self.updated_by or "",
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(raw: Optional[str]) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    return tuple(str(v) for v in parsed if str(v).strip()) if isinstance(parsed, list) else ()


def validate_value(key: str, value: str) -> None:
    """Raise :class:`SettingsError` unless ``value`` is storable for ``key``.

    Checks the denylist and the curated registry first, then proves the value
    actually loads by building a ``Settings`` with it merged in — the same merge
    ``get_settings()`` will perform. A value that fails here would poison every
    other override at refresh time.
    """
    if key in DENYLIST:
        # Three keys, each impossible rather than merely risky. Say which.
        why = {
            "database_url":
                "the stored settings live inside this database, so a setting "
                "moving the app elsewhere would be left behind in the database "
                "being abandoned",
            "app_encryption_key":
                "rotating it makes every already-encrypted stored secret "
                "permanently unreadable, which no verification can undo",
            "release_tag":
                "it is stamped into the container image, so an override would "
                "make this deployment misreport which build it is running",
        }.get(key, "it is a foundation of the application")
        raise SettingsError(
            f"'{key}' cannot be changed here — {why}. Change it in the "
            "deployment configuration."
        )
    if not is_editable(key):
        raise SettingsError(f"'{key}' is not an editable setting.")
    try:
        Settings(**{**config_module.env_values(), key: value})
    except Exception as exc:  # noqa: BLE001 — surfaced to the user verbatim
        raise SettingsError(f"'{value}' is not a valid value for {key}: {exc}") from exc


def _history_value(key: str, value: Optional[str]) -> Optional[str]:
    """History must never carry a credential.

    The whole point of the history tab is answering "when did this change and
    who did it". For a secret, the answer to "to what" is nobody's business and
    storing it would put plaintext credentials in a table nothing encrypts.
    """
    from core.settings_registry import is_secret

    if value is None:
        return None
    return "(secret set)" if is_secret(key) else value


class SettingsStore:
    """Read/write the override table. One instance per process is fine."""

    def __init__(self, database_url: str, cipher: Any = None) -> None:
        self._engine = make_async_engine(database_url)
        # Secrets may now be stored here (Doug's ruling, 2026-08-28), so the
        # store needs the same Fernet cipher `app_config` uses. Without one,
        # storing a secret is REFUSED rather than written in plain text — the
        # failure mode of quietly writing a plaintext credential to a database
        # that gets backed up is not one to fail open on.
        self._cipher = cipher

    def _encode(self, key: str, value: str) -> tuple[str, bool]:
        from core.settings_registry import is_secret

        if not is_secret(key):
            return value, False
        if self._cipher is None:
            raise SettingsError(
                f"'{key}' is a secret and cannot be stored without an encryption "
                "key. Set APP_ENCRYPTION_KEY in the deployment configuration first."
            )
        return self._cipher.encrypt(value), True

    def _decode(self, value: str, encrypted: bool) -> str:
        if not encrypted:
            return value
        if self._cipher is None:
            log.warning("a stored secret cannot be decrypted: no encryption key")
            return ""
        try:
            return self._cipher.decrypt(value)
        except Exception as exc:  # noqa: BLE001 — a bad row must not break the load
            log.warning("could not decrypt a stored secret: %s", exc)
            return ""

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def load(self) -> dict[str, Override]:
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(app_setting))).mappings().all()
        out: dict[str, Override] = {}
        for row in rows:
            out[row["key"]] = Override(
                key=row["key"],
                value=self._decode(row["value"], bool(row["encrypted"])),
                encrypted=bool(row["encrypted"]),
                previous_value=row["previous_value"],
                revert_at=row["revert_at"],
                confirmed=bool(row["confirmed"]),
                temporary=bool(row["temporary"]),
                review_at=row["review_at"],
                scope_teams=_json_list(row["scope_teams"]),
                scope_users=_json_list(row["scope_users"]),
                reason=row["reason"] or "",
                updated_at=row["updated_at"],
                updated_by=row["updated_by"] or "",
            )
        return out

    async def set(
        self,
        key: str,
        value: str,
        *,
        actor: str = "",
        reason: str = "",
        temporary: bool = False,
        review_at: Optional[datetime] = None,
        scope_teams: Optional[list[str]] = None,
        scope_users: Optional[list[str]] = None,
        revert_at: Optional[datetime] = None,
    ) -> Override:
        validate_value(key, value)
        existing = (await self.load()).get(key)
        now = _now()
        stored, encrypted = self._encode(key, value)
        # What to go back to if this proves harmful. None means there was no
        # override before, so undoing it deletes the row rather than writing a
        # value — and the difference matters: writing back the environment's own
        # value would create an override that merely LOOKS like the default and
        # would then survive a later change to the deployment configuration.
        previous = existing.value if existing else None
        if previous is not None and existing is not None and existing.encrypted:
            previous, _ = self._encode(key, previous)
        record = Override(
            key=key,
            value=value,
            encrypted=encrypted,
            previous_value=previous,
            revert_at=revert_at,
            confirmed=revert_at is None,
            temporary=temporary,
            review_at=review_at,
            scope_teams=tuple(scope_teams or ()),
            scope_users=tuple(scope_users or ()),
            reason=reason,
            updated_at=now,
            updated_by=actor,
        )
        values = {
            "key": key,
            "value": stored,
            "encrypted": encrypted,
            "previous_value": previous,
            "revert_at": revert_at,
            # A change with a deadline starts UNconfirmed. That is the whole
            # mechanism: silence undoes it.
            "confirmed": revert_at is None,
            "temporary": temporary,
            "review_at": review_at,
            "scope_teams": json.dumps(list(scope_teams)) if scope_teams else None,
            "scope_users": json.dumps(list(scope_users)) if scope_users else None,
            "reason": reason or None,
            "updated_at": now,
            "updated_by": actor or None,
        }
        stmt = (
            pg_insert(app_setting)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={k: v for k, v in values.items() if k != "key"},
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)
            await conn.execute(
                app_setting_history.insert().values(
                    id=str(uuid.uuid4()),
                    key=key,
                    old_value=_history_value(key, existing.value if existing else None),
                    new_value=_history_value(key, value),
                    encrypted=False,
                    action="set",
                    reason=reason or None,
                    created_at=now,
                    actor=actor or None,
                )
            )
        return record

    async def clear(self, key: str, *, actor: str = "", reason: str = "") -> bool:
        """Delete the override so the setting reverts to its environment value.
        Returns False when there was nothing to clear."""
        existing = (await self.load()).get(key)
        if existing is None:
            return False
        now = _now()
        async with self._engine.begin() as conn:
            await conn.execute(delete(app_setting).where(app_setting.c.key == key))
            await conn.execute(
                app_setting_history.insert().values(
                    id=str(uuid.uuid4()),
                    key=key,
                    old_value=_history_value(key, existing.value),
                    new_value=None,
                    action="clear",
                    reason=reason or None,
                    created_at=now,
                    actor=actor or None,
                )
            )
        return True

    async def confirm(self, key: str, *, actor: str = "") -> bool:
        """A human says the system still works. Cancels the countdown."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                app_setting.update()
                .where(app_setting.c.key == key)
                .values(confirmed=True, revert_at=None)
            )
        ok = bool(result.rowcount)
        if ok:
            log.info("settings: %s confirmed by %s", key, actor or "?")
        return ok

    async def due_reverts(self, now: Optional[datetime] = None) -> list[Override]:
        """Changes whose deadline has passed with no confirmation."""
        moment = now or _now()
        return [
            o for o in (await self.load()).values()
            if o.revert_at is not None and not o.confirmed and o.revert_at <= moment
        ]

    async def revert(self, key: str, *, actor: str = "system", reason: str = "") -> bool:
        """Undo a change: restore the previous override, or delete the row when
        there was none. Used by the countdown sweep and by a failed post-apply
        check."""
        existing = (await self.load()).get(key)
        if existing is None:
            return False
        now = _now()
        async with self._engine.begin() as conn:
            if existing.previous_value is None:
                await conn.execute(delete(app_setting).where(app_setting.c.key == key))
                new_value = None
            else:
                await conn.execute(
                    app_setting.update()
                    .where(app_setting.c.key == key)
                    .values(
                        value=existing.previous_value,
                        previous_value=None,
                        revert_at=None,
                        confirmed=True,
                        updated_at=now,
                        updated_by=actor or None,
                    )
                )
                new_value = self._decode(existing.previous_value, existing.encrypted)
            await conn.execute(
                app_setting_history.insert().values(
                    id=str(uuid.uuid4()),
                    key=key,
                    old_value=_history_value(key, existing.value),
                    new_value=_history_value(key, new_value),
                    action="revert",
                    reason=reason or "reverted automatically — not confirmed in time",
                    created_at=now,
                    actor=actor or None,
                )
            )
        log.warning("settings: %s REVERTED (%s)", key, reason or "not confirmed")
        return True

    async def history(self, key: str = "", limit: int = 50) -> list[dict[str, Any]]:
        stmt = select(app_setting_history).order_by(
            app_setting_history.c.created_at.desc()
        ).limit(limit)
        if key:
            stmt = stmt.where(app_setting_history.c.key == key)
        async with self._engine.begin() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [
            {
                "key": r["key"],
                "oldValue": r["old_value"],
                "newValue": r["new_value"],
                "action": r["action"],
                "reason": r["reason"] or "",
                "actor": r["actor"] or "",
                "at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def dispose(self) -> None:
        await self._engine.dispose()


def make_settings_store(settings: Settings) -> Optional[SettingsStore]:
    """A store when a database is configured, else None (env-only behaviour).

    Carries the Fernet cipher when one is configured, which is what allows a
    secret to be set from the page. Without it the store still works for every
    ordinary setting and REFUSES secrets — never writing one in plain text.
    """
    if not settings.database_url:
        return None
    cipher = None
    if settings.app_encryption_key:
        try:
            from core.crypto import SecretCipher

            cipher = SecretCipher(settings.app_encryption_key)
        except Exception as exc:  # noqa: BLE001 — no cipher is a working state
            log.warning("settings store: encryption unavailable (%s)", exc)
    return SettingsStore(settings.database_url, cipher)


def global_overrides(rows: dict[str, Override]) -> dict[str, str]:
    """The subset that changes process-wide configuration.

    Scoped overrides are deliberately excluded — they are per-user decisions
    evaluated at request time, and applying one globally would turn a "just for
    the Mentor Team" rollout into an everyone rollout.

    **Denylisted keys are dropped here too**, not only at the write path. A row
    can outlive the rule that allowed it — as the boot-read keys did in
    v0.190.1, where a stored ``events_enabled`` override kept making the portal
    advertise an app whose routes were never mounted. Filtering on read makes a
    newly-denylisted key inert immediately, with no cleanup migration.
    """
    return {
        k: o.value
        for k, o in rows.items()
        if not o.scoped and k not in DENYLIST
    }


# --- scoped rollout (plan §5, phase 4) --------------------------------------
#
# Scoped overrides never reach `apply_overrides`; they are held here and applied
# per user. A scope can only be evaluated where there IS a user — the web
# process. Worker-side features stay instance-wide, which the UI enforces by
# refusing to scope a setting whose component is "worker".

_scoped: dict[str, Override] = {}


def scoped_overrides() -> dict[str, Override]:
    return dict(_scoped)


def _matches(override: Override, user: Optional[dict[str, Any]]) -> bool:
    if not user:
        return False
    if override.scope_users:
        name = str(user.get("userName") or "")
        if name and name in override.scope_users:
            return True
    if override.scope_teams:
        teams = {str(t) for t in (user.get("teams") or [])}
        if teams & set(override.scope_teams):
            return True
    return False


def setting_for_user(key: str, user: Optional[dict[str, Any]], settings: Settings) -> Any:
    """The value of ``key`` for this specific user.

    Identical to ``getattr(settings, key)`` unless a **scoped** override exists
    and the user matches it — that is the whole point of scoped rollout: turn a
    feature on for one team or one person and watch it in production before
    everyone gets it.
    """
    override = _scoped.get(key)
    if override is not None and _matches(override, user):
        try:
            merged = {**config_module.env_values(), key: override.value}
            return getattr(Settings(**merged), key)
        except Exception as exc:  # noqa: BLE001 — fall through to the global value
            log.warning("scoped override for %s unusable: %s", key, exc)
    return getattr(settings, key, None)


def feature_enabled_for(key: str, user: Optional[dict[str, Any]], settings: Settings) -> bool:
    return bool(setting_for_user(key, user, settings))


async def refresh_into_config(store: Optional[SettingsStore], settings: Settings) -> bool:
    """Re-read the overrides and install them. Returns True when applied.

    Never raises (ruling 6): on any failure the previously-installed
    configuration stays in force and the app keeps running on the overlay's
    values rather than reverting to code defaults.
    """
    if store is None or not settings.settings_overrides:
        return False
    try:
        rows = await store.load()
    except Exception as exc:  # noqa: BLE001 — a DB blip must not reconfigure the app
        log.warning("settings override refresh failed (keeping current config): %s", exc)
        return False
    global _scoped
    _scoped = {k: o for k, o in rows.items() if o.scoped and k not in DENYLIST}
    config_module.apply_overrides(global_overrides(rows))
    return True


async def sweep_reverts(store: Optional[SettingsStore]) -> list[str]:
    """Undo any change whose confirmation deadline has passed. Returns the keys.

    This is the half of the confirm-or-revert mechanism that actually saves you,
    and it runs in BOTH processes on the ordinary settings timer. That is
    deliberate rather than redundant:

    * The web process is the one that can be locked out — if a change made the
      page unreachable, the sweep still runs there because it is a background
      task, not a request.
    * The worker is the backstop for the web process being down entirely.
    * It operates on the database directly, so it keeps working even when the
      change under test was ``settings_overrides=false`` — which switches off
      the very layer that would otherwise be asked to undo it.

    Idempotent: two processes sweeping the same row is safe, because the second
    revert finds nothing to do.
    """
    if store is None:
        return []
    try:
        due = await store.due_reverts()
    except Exception as exc:  # noqa: BLE001 — a sweep failure must not kill the loop
        log.debug("revert sweep failed: %s", exc)
        return []
    done: list[str] = []
    for override in due:
        try:
            if await store.revert(
                override.key,
                actor="system",
                reason=(
                    "reverted automatically: nobody confirmed the system was still "
                    "working before the deadline"
                ),
            ):
                done.append(override.key)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not revert %s: %s", override.key, exc)
    if done:
        log.warning(
            "settings: reverted %d unconfirmed change(s): %s",
            len(done), ", ".join(done),
        )
    return done


async def overdue_reviews(store: Optional[SettingsStore]) -> list[Override]:
    """Temporary overrides whose review date has passed (ruling 5 — reported,
    never auto-reverted)."""
    if store is None:
        return []
    try:
        rows = await store.load()
    except Exception as exc:  # noqa: BLE001
        log.debug("overdue-review check failed: %s", exc)
        return []
    now = _now()
    return sorted(
        (o for o in rows.values() if o.temporary and o.review_at and o.review_at <= now),
        key=lambda o: o.review_at or now,
    )
