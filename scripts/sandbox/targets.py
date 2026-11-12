"""The two systems that hold invented training data, and nothing else.

Association ruling 77 (11-12-26): the training data crm-test holds is loaded
into the Business Mentors Association's system by rerunning these scripts
against it. Every seeder asks :func:`resolve` which system it is connected to
and refuses any other, so Cleveland's production system, Boston and Lakeside
can never be written to by a seeder, whatever a credential file says.

The scripts' records are WRITTEN in crm-test's terms: addresses on
``sandbox.cbmentors.org``, the organization's name, crm-test's application
address. :func:`localise` turns those into the target's terms at run time, so
both systems hold the same people, companies and histories (the reason for
ruling 77: training material and screenshots match), each on its own
mailbox-less domain. For crm-test it changes nothing.

Credentials: ``--env-file`` names a credential file such as
``~/.config/cbm-bma/bma.env``; it is read with a parser, never sourced, and its
values beat the process environment, so a stale export cannot redirect a run.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

#: The domain, name and address the scripts' records are written with.
WRITTEN_DOMAIN = "sandbox.cbmentors.org"
WRITTEN_ORG = "Cleveland Business Mentors"
WRITTEN_APP_URL = "https://cbm-client-intake-svxs3.ondigitalocean.app"


@dataclass(frozen=True)
class Target:
    """One training system."""

    label: str
    crm_host: str        # the CRM's host name, matched exactly
    email_domain: str    # every invented address; must have NO mailboxes
    login_domain: str    # the training sign-ins' user names
    org_name: str
    app_url: str


TARGETS: tuple[Target, ...] = (
    Target("crm-test", "crm-test.clevelandbusinessmentors.org",
           WRITTEN_DOMAIN, "cbmentors.org", WRITTEN_ORG, WRITTEN_APP_URL),
    # sandbox.mentorsassociation.org: Google answered "Domain not found" and no
    # mail exchange record existed, 11-12-26. It must never become real.
    Target("Business Mentors Association", "crm.businessmentorsassociation.org",
           "sandbox.mentorsassociation.org", "sandbox.mentorsassociation.org",
           "Business Mentors Association", "https://apps.businessmentorsassociation.org"),
)


def resolve(base_url: str) -> Optional[Target]:
    """The training system at ``base_url``, or None for any other CRM."""
    host = (urlparse((base_url or "").strip()).hostname or "").lower()
    return next((t for t in TARGETS if t.crm_host == host), None)


def refusal(base_url: str) -> str:
    return (f"REFUSING: {base_url or '(no CRM address)'!r} is not a training system "
            f"({', '.join(t.crm_host for t in TARGETS)}).")


def localise(value: Any, target: Target) -> Any:
    """``value`` with crm-test's domain, name and address replaced by the
    target's, through nested dicts, lists and tuples. Identity for crm-test."""
    if isinstance(value, str):
        return (value.replace(WRITTEN_DOMAIN, target.email_domain)
                .replace(WRITTEN_ORG, target.org_name)
                .replace(WRITTEN_APP_URL, target.app_url))
    if isinstance(value, dict):
        return {k: localise(v, target) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(localise(v, target) for v in value)
    if isinstance(value, list):
        return [localise(v, target) for v in value]
    return value


def localise_names(module_globals: dict[str, Any], names: tuple[str, ...], target: Target) -> None:
    """Rebind each named module constant to its localised copy."""
    for name in names:
        module_globals[name] = localise(module_globals[name], target)


def load_env_file(path: Optional[str]) -> dict[str, str]:
    """The process environment, overlaid by ``path`` when given (file wins)."""
    from espo_admin import load_env

    if not path:
        return load_env()
    file = Path(os.path.expanduser(path))
    if not file.exists():
        raise SystemExit(f"No such credential file: {file}")
    return load_env(file, prefer_file=True)


def api_connection(env_file: Optional[str]) -> tuple[str, str, int]:
    """(CRM address, the applications' CRM key, timeout) for the seeders that
    run as the applications do. Without ``--env-file``, the application's own
    settings, exactly as before."""
    if not env_file:
        from core.config import get_settings

        s = get_settings()
        return (s.espo_base_url or ""), s.espo_api_key, s.request_timeout_seconds
    env = load_env_file(env_file)
    base = (env.get("ESPO_BASE_URL") or env.get("ESPO_ADMIN_BASE") or "").rstrip("/")
    return base, env.get("ESPO_API_KEY", ""), 30


def add_env_file_argument(parser) -> None:
    parser.add_argument(
        "--env-file", default=None,
        help="credential file for another training system, e.g. ~/.config/cbm-bma/bma.env "
             "(read with a parser; its values win)")
