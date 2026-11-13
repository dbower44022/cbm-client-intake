"""The two "in use" refusals (rulings I5 and I13), enforced in the save path.

* Marking an integration **not in use** is refused while any of its switches is
  on. The message names each switch that is on.
* Switching a feature **on** is refused while its integration is marked not in
  use. The message says to mark the integration in use first.

"Its switches" are the integration's own switches and the used-by features that
cannot work at all without it (``Integration.blocking_switches``). A scoped
override that switches a feature on for some people counts as on: the feature
is running for them.

Called by ``setup/router.py`` for a save AND for a reset to the deployment
value, because a reset can switch a feature on just as a save can. Always
active: with every "in use" setting at its default of true, it refuses nothing.
"""

from __future__ import annotations

from typing import Any, Optional

from core.settings_registry import spec_for

from .registry import IN_USE_KEYS, Integration, Switch, in_use, integrations_switched_by

_FALSE = {"", "0", "false", "no", "off"}


def _label(key: str) -> str:
    spec = spec_for(key)
    return f"{spec.label} ({key})" if spec else key


def _switch_on(sw: Switch, settings: Any, scoped: dict[str, Any]) -> bool:
    if sw.is_on(getattr(settings, sw.key, None)):
        return True
    override = scoped.get(sw.key)
    return override is not None and sw.is_on(getattr(override, "value", None))


def switches_on(integ: Integration, settings: Any, scoped: Optional[dict[str, Any]] = None) -> list[str]:
    """The keys of every switch of ``integ`` that is on now, in registry order."""
    scoped = scoped or {}
    return [sw.key for sw in integ.blocking_switches if _switch_on(sw, settings, scoped)]


def refusal(
    key: str, new_value: Any, settings: Any, scoped: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Why setting ``key`` to ``new_value`` is refused, or None when it is allowed."""
    integ = IN_USE_KEYS.get(key)
    if integ is not None:
        if str(new_value if new_value is not None else "").strip().lower() not in _FALSE:
            return None
        on = switches_on(integ, settings, scoped)
        if not on:
            return None
        return (
            f"{integ.name} cannot be marked not in use while "
            + ("this is" if len(on) == 1 else "these are")
            + " switched on: " + "; ".join(_label(k) for k in on)
            + ". Switch " + ("it" if len(on) == 1 else "them") + " off first."
        )
    for integ, sw in integrations_switched_by(key):
        if not sw.is_on(new_value):
            continue
        if in_use(integ, settings):
            continue
        return (
            f"{_label(key)} cannot be switched on while {integ.name} is marked not "
            f"used by this chapter. Mark {integ.name} in use first: Integrations, "
            f"{integ.name}, {integ.name} in use."
        )
    return None
