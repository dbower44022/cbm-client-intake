"""
Load a HubSpot snapshot into a chapter's EspoCRM, under ruling 4.1 option B.

:author: Doug
:date: 2026-09-26
:description: Step 5 of ``prds/chapter-network/chapters/boston-hubspot-migration.md``.
    Reads the snapshot written by ``pull_snapshot.py`` and writes, in order:
    mentors (Contact + CMentorProfile + User) for every HubSpot owner, then
    for every HubSpot contact either the client spine (Account → Contact →
    CClientProfile → CEngagement, assigned to the owning mentor) when there is
    evidence of mentoring, or a Prospect Contact assigned to the mentor when
    there is none; then mentor notes and meetings as CSession records, intake
    notes as stream posts, and note attachments. Everything without a home in
    the standard lands in a dated "Imported from HubSpot" block on the
    record's description. **No CRM field is created.**

    Idempotent through a ledger beside the snapshot (``ledger-<host>.json``):
    every created id is recorded as it lands, and a re-run adds only what is
    missing. Dry-run by default: reads the target for real, fakes every write,
    and prints the plan.

Usage::

    uv run --with tenacity python scripts/hubspot/load_boston.py \\
        --target ~/.config/cbm-lakeside/lakeside.env            # plan only
    uv run --with tenacity python scripts/hubspot/load_boston.py \\
        --target ~/.config/cbm-lakeside/lakeside.env --write    # apply

``--target`` names the env file holding ``ESPO_ADMIN_BASE``,
``ESPO_PROVISION_USERNAME`` and ``ESPO_PROVISION_PASSWORD`` (the load runs as
the provisioning admin because User creation is admin-only). ``--snapshot``
names the snapshot folder (default: the newest under
``~/.config/cbm-boston/hubspot-snapshot``). Passwords are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
import logging
import re
import secrets
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assignments.auth import AuthError, login_token  # noqa: E402
from core.crm_upsert import create_dropping_invalid, find_create_or_fill  # noqa: E402
from core.enum_filter import EnumSanitizer  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from core.phone import e164_or_none  # noqa: E402
from pull_snapshot import DEFAULT_OUT_ROOT, HubSpot, read_token  # noqa: E402

logger = logging.getLogger(__name__)

# --- Constants ---

LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(module)s - %(levelname)s - %(funcName)s"
    " - %(lineno)d --- %(message)s"
)
IMPORT_MARK = "Imported from HubSpot"
MENTOR_TEAM = "Mentor Team"
# Shared inboxes that own records but are not a person: their contacts have no
# mentor (a client among them is created Submitted, for Client Administration).
MARKETING_OWNER_EMAILS = {"marketing@bbmentors.org", "connect@bbmentors.org"}
# Archived owners that were a mentor's earlier address. Every other archived
# owner (typo'd or pre-onboarding duplicates) owns nothing and creates nothing.
OWNER_ALIASES = {
    "rkstutzman2012@gmail.com": "rob.stutzman@bbmentors.org",
    "rkstutzman@stutzco.net": "rob.stutzman@bbmentors.org",
}
CLIENT_FORM_NAMES = ("Connect with a Mentor",)

# HubSpot ``referral`` value -> Contact.cHowDidYouHear option.
HOW_HEARD = {
    "Friend, Colleague": "Personal Referral",
    "Advertising": "Other",
    "Event, Trade Show, Business Expo": "Workshop or Event",
    "Google Search": "Online Search",
    "LinkedIn": "Social Media",
    "Facebook": "Social Media",
    "Instagram": "Social Media",
    "Social Media": "Social Media",
    "Alignable": "Social Media",
    "Roxbury Community College": "Partner Referral",
    "None, Direct Request": "Other",
    "Other": "Other",
}
# HubSpot ``contact_me_via`` option label -> (cPreferredContactMethod, cNotificationPreference)
CONTACT_VIA = {
    "Text": ("Text", "Text"),
    "Email": ("Email", "Email"),
    "No Preference": ("Email", None),
}


# --- Configuration and ledger ---


@dataclass
class Target:
    """
    The EspoCRM being loaded.

    :param base_url: CRM root, e.g. ``https://crm.bbmentors.org``.
    :type base_url: str
    :param admin_user: Provisioning admin user name.
    :type admin_user: str
    :param admin_pass: Provisioning admin password (never logged).
    :type admin_pass: str
    """

    base_url: str
    admin_user: str
    admin_pass: str
    fallback_user: str = ""
    fallback_pass: str = ""

    @property
    def host(self) -> str:
        """The host name, used to key the ledger."""
        return re.sub(r"^https?://", "", self.base_url).strip("/")


def read_target(env_file: Path) -> Target:
    """
    Parse the target env file in Python (never through a shell).

    :param env_file: dotenv-style file.
    :type env_file: Path
    :returns: The target.
    :rtype: Target
    :raises ValueError: If a required key is missing.
    """
    text = env_file.read_text(encoding="utf-8")
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.MULTILINE))
    try:
        return Target(
            base_url=env["ESPO_ADMIN_BASE"].strip().strip('"'),
            admin_user=env["ESPO_PROVISION_USERNAME"].strip().strip('"'),
            admin_pass=env["ESPO_PROVISION_PASSWORD"].strip().strip('"'),
            fallback_user=env.get("ESPO_ADMIN_USER", "").strip().strip('"'),
            fallback_pass=env.get("ESPO_ADMIN_PASS", "").strip().strip('"'),
        )
    except KeyError as exc:
        raise ValueError(f"{env_file} lacks {exc}") from None


class Ledger:
    """
    The HubSpot-id → EspoCRM-id map that makes the load idempotent.

    :param path: JSON file to persist to.
    :type path: Path
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict[str, Any]] = defaultdict(dict)
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            for k, v in loaded.items():
                self.data[k] = v
            logger.info(f"Ledger loaded from {path}: " + ", ".join(f"{k}={len(v)}" for k, v in self.data.items()))

    def get(self, kind: str, key: str) -> Any:
        """Return the stored value for ``kind``/``key`` or None."""
        return self.data[kind].get(str(key))

    def put(self, kind: str, key: str, value: Any) -> None:
        """Store and flush one mapping."""
        self.data[kind][str(key)] = value
        self.flush()

    def flush(self) -> None:
        """Write the ledger to disk."""
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")


# --- Clients ---


class PlanningClient:
    """
    Dry-run client: real reads against the target, faked writes.

    Reads go to the wrapped :class:`EspoClient` so the plan reflects what the
    target already holds; every create/update/relate is counted and answered
    with a synthetic id.

    :param real: The authenticated client used for reads.
    :type real: EspoClient
    """

    def __init__(self, real: EspoClient) -> None:
        self._real = real
        self.counts: Counter[str] = Counter()
        self._n = 0

    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.counts[f"create {entity}"] += 1
        self._n += 1
        return {"id": f"dry-{entity}-{self._n}", **payload}

    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.counts[f"update {entity}"] += 1
        return {"id": record_id, **payload}

    async def relate(self, entity: str, record_id: str, link: str, related_id: str) -> None:
        self.counts[f"relate {entity}.{link}"] += 1

    async def upload_attachment(self, **kwargs: Any) -> str:
        self.counts["create Attachment"] += 1
        self._n += 1
        return f"dry-Attachment-{self._n}"

    async def find_one(self, *args: Any, **kwargs: Any) -> Optional[dict[str, Any]]:
        return await self._real.find_one(*args, **kwargs)

    async def get(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if args and str(args[1]).startswith("dry-"):
            return {"id": args[1]}
        return await self._real.get(*args, **kwargs)

    async def list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._real.list(*args, **kwargs)

    async def metadata_enum_options(self, *args: Any, **kwargs: Any) -> Any:
        return await self._real.metadata_enum_options(*args, **kwargs)


class CountingClient:
    """
    Write client that counts every operation it forwards.

    :param real: The authenticated client.
    :type real: EspoClient
    """

    def __init__(self, real: EspoClient) -> None:
        self._real = real
        self.counts: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.counts[f"create {entity}"] += 1
        return await self._real.create(entity, payload)

    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.counts[f"update {entity}"] += 1
        return await self._real.update(entity, record_id, payload)

    async def relate(self, entity: str, record_id: str, link: str, related_id: str) -> None:
        self.counts[f"relate {entity}.{link}"] += 1
        await self._real.relate(entity, record_id, link, related_id)

    async def upload_attachment(self, **kwargs: Any) -> str:
        self.counts["create Attachment"] += 1
        return await self._real.upload_attachment(**kwargs)


# --- Snapshot model ---


@dataclass
class Snapshot:
    """
    The HubSpot snapshot, indexed for the load.

    :param root: Snapshot folder.
    :type root: Path
    """

    root: Path
    contacts: list[dict[str, Any]] = field(default_factory=list)
    companies: dict[str, dict[str, Any]] = field(default_factory=dict)
    owners: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes_by_contact: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    meetings_by_contact: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    misc_by_contact: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    alias: dict[str, str] = field(default_factory=dict)

    def resolve(self, owner_id: Optional[str]) -> Optional[str]:
        """
        The ACTIVE owner id behind ``owner_id``: itself, its alias, or None.

        :param owner_id: A HubSpot owner id (may be archived or None).
        :type owner_id: str | None
        :returns: An active owner id, or None when nobody current stands behind it.
        :rtype: str | None
        """
        if not owner_id:
            return None
        oid = str(owner_id)
        o = self.owners.get(oid)
        if not o:
            return None
        if not o.get("archived"):
            return oid
        return self.alias.get(oid)

    def load(self) -> "Snapshot":
        """Read the JSON files and build the per-contact indexes."""
        obj = self.root / "objects"
        self.contacts = json.loads((obj / "contacts.json").read_text(encoding="utf-8"))
        self.companies = {c["id"]: c for c in json.loads((obj / "companies.json").read_text(encoding="utf-8"))}
        owners = json.loads((self.root / "owners.json").read_text(encoding="utf-8"))
        for o in owners["active"]:
            self.owners[o["id"]] = {**o, "archived": False}
        by_email = {(o.get("email") or "").lower(): o["id"] for o in owners["active"]}
        for o in owners["archived"]:
            self.owners[o["id"]] = {**o, "archived": True}
            target = OWNER_ALIASES.get((o.get("email") or "").lower())
            if target and target in by_email:
                self.alias[o["id"]] = by_email[target]
        for n in json.loads((obj / "notes.json").read_text(encoding="utf-8")):
            for cid in assoc_ids(n, "contacts"):
                self.notes_by_contact[cid].append(n)
        for m in json.loads((obj / "meetings.json").read_text(encoding="utf-8")):
            for cid in assoc_ids(m, "contacts"):
                self.meetings_by_contact[cid].append(m)
        for kind, title_key in (("tasks", "hs_task_subject"), ("emails", "hs_email_subject"), ("calls", "hs_call_title")):
            path = obj / f"{kind}.json"
            if not path.exists():
                continue
            for rec in json.loads(path.read_text(encoding="utf-8")):
                p = rec.get("properties") or {}
                line = f"{kind[:-1]} {(p.get('hs_timestamp') or '')[:10]}: {p.get(title_key) or p.get('hs_body_preview') or ''}".strip()
                for cid in assoc_ids(rec, "contacts"):
                    self.misc_by_contact[cid].append(line[:300])
        logger.info(
            f"Snapshot {self.root}: {len(self.contacts)} contacts, {len(self.companies)} companies, "
            f"{len(self.owners)} owners, notes on {len(self.notes_by_contact)} contacts"
        )
        return self

    def is_person(self, owner_id: Optional[str]) -> bool:
        """True when ``owner_id`` is an active owner that is a mentor, not a shared inbox."""
        o = self.owners.get(owner_id or "")
        return bool(o) and not o.get("archived") and (o.get("email") or "").lower() not in MARKETING_OWNER_EMAILS

    def owner_name(self, owner_id: Optional[str]) -> str:
        """Display name for an owner id."""
        o = self.owners.get(str(owner_id or ""))
        if not o:
            return f"owner {owner_id}" if owner_id else ""
        return f"{o.get('firstName', '')} {o.get('lastName', '')}".strip() or (o.get("email") or "")


JUNK_COMPANY = {"n/a", "na", "none", "no", "-", "--", "self", "myself", "me", "tbd", "test", "test account", "individual", "personal", "not yet", "n.a.", "null"}


def company_text(value: Optional[str]) -> Optional[str]:
    """
    The company name a person typed, or None when it is a placeholder.

    :param value: Raw ``company`` property.
    :type value: str | None
    :returns: A usable name or None.
    :rtype: str | None
    """
    v = (value or "").strip()
    if len(v) < 2 or v.lower() in JUNK_COMPANY:
        return None
    return v[:249]


def cp_website(snap: "Snapshot", c: dict[str, Any]) -> Optional[str]:
    """The associated company's website text, for the imported block."""
    for cid in assoc_ids(c, "companies"):
        cand = snap.companies.get(cid)
        if cand and (cand.get("properties") or {}).get("website"):
            return cand["properties"]["website"]
    return None


def assoc_ids(rec: dict[str, Any], kind: str) -> list[str]:
    """
    Distinct associated ids of ``kind`` (HubSpot lists each pair once per label).

    :param rec: A snapshot record with an ``associations`` block.
    :type rec: dict[str, Any]
    :param kind: ``contacts`` or ``companies``.
    :type kind: str
    :returns: Ids in first-seen order.
    :rtype: list[str]
    """
    seen: dict[str, None] = {}
    for r in ((rec.get("associations") or {}).get(kind) or {}).get("results", []):
        seen.setdefault(str(r.get("id")), None)
    return list(seen)


# --- Helpers ---


def strip_html(text: Optional[str]) -> str:
    """
    Plain text from HubSpot HTML (notes are stored as HTML).

    :param text: HTML or None.
    :type text: str | None
    :returns: Plain text with collapsed whitespace.
    :rtype: str
    """
    if not text:
        return ""
    t = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def clean_name(value: Optional[str], limit: int = 150) -> str:
    """
    A record name that passes EspoCRM's ``$noBadCharacters`` pattern.

    A HubSpot note's first line can open with ``<`` or hold an ``=``; the CRM
    refuses those in a name field (400, ``type: pattern``).

    :param value: Raw text.
    :type value: str | None
    :returns: The cleaned name, never empty.
    :rtype: str
    """
    # The CRM's $noBadCharacters pattern is ``[^<>=]+`` (read from metadata
    # 2026-09-26): angle brackets and the equals sign, nothing else.
    cleaned = re.sub(r"[<>=]", " ", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:limit]
    return cleaned or "Session"


def clean_url(value: Optional[str]) -> Optional[str]:
    """
    A URL EspoCRM's ``url`` validator accepts, or None.

    HubSpot stores whatever was typed: ``tomterrific.com``, ``www.x.com/``,
    a bare word. A scheme is added when missing; anything without a dotted
    host is dropped (the raw value survives in the imported block).

    :param value: Raw website text.
    :type value: str | None
    :returns: ``https://…`` or None.
    :rtype: str | None
    """
    if not value:
        return None
    v = value.strip().split()[0]
    if not re.match(r"^https?://", v, re.I):
        v = "https://" + v
    host = re.sub(r"^https?://", "", v, flags=re.I).split("/")[0]
    if not re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(:\d+)?$", host):
        return None
    return v[:255]


def espo_dt(value: Optional[str]) -> Optional[str]:
    """
    HubSpot ISO timestamp -> EspoCRM ``YYYY-MM-DD HH:MM:SS`` in UTC.

    :param value: e.g. ``2026-03-04T15:22:10.123Z``.
    :type value: str | None
    :returns: EspoCRM stamp or None.
    :rtype: str | None
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def espo_date(value: Optional[str]) -> Optional[str]:
    """Date part of a HubSpot timestamp."""
    return value[:10] if value else None


def option_label(props: dict[str, Any], name: str, value: Optional[str]) -> list[str]:
    """
    Labels for a HubSpot enumeration value (``;``-separated for multi-select).

    :param props: Property definitions keyed by name.
    :type props: dict[str, Any]
    :param name: Property name.
    :type name: str
    :param value: Stored value.
    :type value: str | None
    :returns: Labels, or the raw values when no option matches.
    :rtype: list[str]
    """
    if not value:
        return []
    labels = {o["value"]: o.get("label", o["value"]) for o in (props.get(name) or {}).get("options", [])}
    return [labels.get(v, v) for v in value.split(";") if v]


def imported_block(lines: list[tuple[str, Any]], hs_id: str) -> str:
    """
    The dated "Imported from HubSpot" text placed on a description.

    :param lines: (label, value) pairs; empty values are skipped.
    :type lines: list[tuple[str, Any]]
    :param hs_id: HubSpot record id.
    :type hs_id: str
    :returns: The block.
    :rtype: str
    """
    out = [f"{IMPORT_MARK} on {datetime.now(timezone.utc):%Y-%m-%d} (HubSpot id {hs_id})"]
    for label, value in lines:
        if value in (None, "", [], False):
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        out.append(f"{label}: {value}")
    return "\n".join(out)


# --- Classification (ruling 4.1 B) ---


@dataclass
class Verdict:
    """
    What one HubSpot contact becomes.

    :param client: True when an engagement is created.
    :type client: bool
    :param reasons: The evidence found.
    :type reasons: list[str]
    :param status: Engagement status when ``client``.
    :type status: str
    """

    client: bool
    reasons: list[str]
    status: str = ""


def classify(snap: Snapshot, c: dict[str, Any]) -> Verdict:
    """
    Apply ruling 4.1 B to one contact.

    :param snap: Snapshot.
    :type snap: Snapshot
    :param c: HubSpot contact.
    :type c: dict[str, Any]
    :returns: The verdict.
    :rtype: Verdict
    """
    p = c.get("properties") or {}
    reasons: list[str] = []
    owner = snap.owners.get(snap.resolve(p.get("hubspot_owner_id")) or "")
    mentor_owner = bool(owner) and (owner.get("email") or "") not in MARKETING_OWNER_EMAILS
    mentor_notes = [
        n for n in snap.notes_by_contact.get(c["id"], [])
        if snap.is_person(snap.resolve((n.get("properties") or {}).get("hubspot_owner_id")))
    ]
    if mentor_notes:
        reasons.append(f"{len(mentor_notes)} mentor note(s)")
    if snap.meetings_by_contact.get(c["id"]):
        reasons.append(f"{len(snap.meetings_by_contact[c['id']])} meeting(s)")
    if p.get("contact_type") == "Client":
        reasons.append("Contact Type = Client")
    if re.search(r"cl?ient", p.get("classification") or "", re.I):
        reasons.append(f"classification '{p.get('classification')}'")
    if p.get("lifecyclestage") == "customer":
        reasons.append("lifecycle customer")
    conv = p.get("first_conversion_event_name") or ""
    if any(conv.startswith(n) for n in CLIENT_FORM_NAMES):
        reasons.append(f"form '{conv}'")
    if not reasons:
        return Verdict(False, [])
    active = bool(mentor_notes) or bool(snap.meetings_by_contact.get(c["id"]))
    if not mentor_owner:
        status = "Submitted"
    elif active:
        status = "Active"
    else:
        status = "Assigned"
    return Verdict(True, reasons, status)


# --- The loader ---


@dataclass
class Loader:
    """
    Holds the clients, the snapshot, the ledger and the per-run counters.

    :param client: Write client (counting or planning).
    :type client: Any
    :param snap: Snapshot.
    :type snap: Snapshot
    :param ledger: Ledger.
    :type ledger: Ledger
    :param hubspot: HubSpot client for attachment downloads (None in dry-run).
    :type hubspot: HubSpot | None
    """

    client: Any
    snap: Snapshot
    ledger: Ledger
    hubspot: Optional[HubSpot]
    send_access_info: bool = False
    props: dict[str, dict[str, Any]] = field(default_factory=dict)
    san: Any = None
    team_id: Optional[str] = None
    stats: Counter = field(default_factory=Counter)
    problems: list[str] = field(default_factory=list)

    async def setup(self) -> None:
        """Read property definitions, the enum sanitizer and the Mentor Team id."""
        pfile = self.snap.root / "properties" / "contacts.json"
        self.props = {p["name"]: p for p in json.loads(pfile.read_text(encoding="utf-8"))["results"]}
        self.san = EnumSanitizer(self.client)
        team = await self.client.find_one("Team", "name", MENTOR_TEAM)
        if not team:
            raise RuntimeError(f"Team '{MENTOR_TEAM}' not found on the target")
        self.team_id = team["id"]

    # --- mentors ---

    async def load_mentors(self) -> None:
        """Contact + CMentorProfile + User for every HubSpot owner that is a person."""
        for oid, o in self.snap.owners.items():
            email = (o.get("email") or "").lower()
            if not email or email in MARKETING_OWNER_EMAILS or o.get("archived"):
                continue
            if self.ledger.get("mentors", oid):
                self.stats["mentor already in ledger"] += 1
                continue
            first = (o.get("firstName") or "").strip()
            last = (o.get("lastName") or "").strip()
            if not last:
                local = email.split("@")[0]
                parts = local.split(".")
                first = first or parts[0].title()
                last = parts[-1].title() if len(parts) > 1 else "Mentor"
                self.problems.append(f"owner {oid} {email} had no name; used {first} {last}")
            name = f"{first} {last}".strip()
            status = "Active"

            contact_id, action = await find_create_or_fill(
                self.client, "Contact",
                match_attr="emailAddress", match_value=email,
                create_payload={
                    "firstName": first, "lastName": last, "emailAddress": email,
                    "cContactType": ["Mentor"], "cPreferredContactMethod": "Email",
                },
                fill_keys=("firstName", "lastName"),
            )
            self.stats[f"mentor contact {action}"] += 1

            profile = await self.client.find_one("CMentorProfile", "cbmEmail", email, select="id,assignedUserId,assignedUsersIds")
            if profile:
                profile_id = profile["id"]
                self.stats["mentor profile matched"] += 1
            else:
                created = await self.client.create("CMentorProfile", {
                    "name": name, "cbmEmail": email, "mentorStatus": status,
                    "mentorType": "Mentor", "acceptingNewClients": True,
                    "contactRecordId": contact_id,
                    "description": imported_block([("HubSpot owner", name)], oid),
                })
                profile_id = created["id"]
                self.stats["mentor profile created"] += 1

            user_id = None
            if True:
                user = await self.client.find_one("User", "userName", email)
                if user:
                    user_id = user["id"]
                    self.stats["mentor user matched"] += 1
                else:
                    payload = {
                        "userName": email, "firstName": first, "lastName": last,
                        "emailAddress": email, "type": "regular", "isActive": True,
                        "teamsIds": [self.team_id], "defaultTeamId": self.team_id,
                        "password": secrets.token_urlsafe(24),
                    }
                    if self.send_access_info:
                        payload["sendAccessInfo"] = True
                    created = await self.client.create("User", payload)
                    user_id = created["id"]
                    self.stats["mentor user created"] += 1
                link = {"assignedUserId": user_id, "assignedUsersIds": [user_id]}
                await self.client.update("CMentorProfile", profile_id, link)
                await self.client.update("Contact", contact_id, link)
            self.ledger.put("mentors", oid, {"contact": contact_id, "profile": profile_id, "user": user_id, "email": email, "name": name})

    def mentor(self, owner_id: Optional[str]) -> Optional[dict[str, Any]]:
        """Ledger entry for an owner id, or None."""
        resolved = self.snap.resolve(owner_id)
        return self.ledger.get("mentors", resolved) if resolved else None

    # --- contacts ---

    async def load_contacts(self) -> None:
        """Every HubSpot contact: client spine or prospect contact."""
        total = len(self.snap.contacts)
        for i, c in enumerate(self.snap.contacts, 1):
            if i % 100 == 0:
                logger.info(f"contacts: {i}/{total}")
            try:
                await self.load_contact(c)
            except EspoError as exc:
                logger.exception(f"contact {c['id']} failed: {exc}")
                self.problems.append(f"contact {c['id']}: {exc}")
                self.stats["contact FAILED"] += 1

    async def load_contact(self, c: dict[str, Any]) -> None:
        """One contact end to end (contact, then engagement, then activity)."""
        p = c.get("properties") or {}
        hs_id = c["id"]
        verdict = classify(self.snap, c)
        mentor = self.mentor(p.get("hubspot_owner_id"))
        # A co-owner that resolves to the owner (an aliased old address, or the
        # same person twice) must not repeat: a duplicated assignedUsersIds entry
        # makes EspoCRM 500 AFTER inserting the row (Lakeside rehearsal 2026-09-26).
        co_mentors = []
        for x in (p.get("co_owner_s_") or "").split(";"):
            m = self.mentor(x) if x else None
            if m and m is not mentor and m not in co_mentors and (not mentor or m["profile"] != mentor["profile"]):
                co_mentors.append(m)
        user_ids = list(dict.fromkeys(m["user"] for m in [mentor, *co_mentors] if m and m.get("user")))

        first = (p.get("firstname") or "").strip()
        last = (p.get("lastname") or "").strip()
        email = (p.get("email") or "").strip().lower()
        if not last:
            last = first or (email.split("@")[0] if email else "Unknown")
            first = "" if last == first else first
        via = option_label(self.props, "contact_me_via", p.get("contact_me_via"))
        pref, notif = ("Email", None)
        for label in via:
            if label in CONTACT_VIA:
                pref, notif = CONTACT_VIA[label]
                break
        opt_in = "Yes, please" in option_label(self.props, "news_and_updates", p.get("news_and_updates")) or p.get("sign_up_for_news_and_updates") == "true"
        contact_types = ["Client"] if verdict.client else ["Prospect"]
        if p.get("contact_type") == "Partner":
            contact_types.append("Partner")
        block = imported_block([
            ("HubSpot owner", self.snap.owner_name(p.get("hubspot_owner_id"))),
            ("Co-owners", [self.snap.owner_name(x) for x in (p.get("co_owner_s_") or "").split(";") if x]),
            ("Created in HubSpot", espo_date(p.get("createdate"))),
            ("Source", p.get("hs_object_source_detail_1") or p.get("hs_object_source_label")),
            ("Contact type", p.get("contact_type")),
            ("Classification", p.get("classification")),
            ("Company (text)", p.get("company")),
            ("Industry (text)", p.get("industry")),
            ("Website", p.get("website")),
            ("Company website", cp_website(self.snap, c)),
            ("How they heard (raw)", ", ".join(option_label(self.props, "referral", p.get("referral")))),
            ("Website button", p.get("button_source")),
            ("Mentor requested", p.get("mentor_name__if_known_")),
            ("Wants to meet with", ", ".join(option_label(self.props, "i_d_like_to_meet_with", p.get("i_d_like_to_meet_with")))),
            ("Secondary email", p.get("secondary_email")),
            ("Tertiary email", p.get("tertiary_email")),
            ("Message", strip_html(p.get("message"))),
            ("Assistance", p.get("assistance") or p.get("how_can_a_mentor_assist_you_") or p.get("how_can_we_help_you_today_")),
            ("Activity", self.snap.misc_by_contact.get(hs_id)),
            ("Basis for client status", verdict.reasons),
        ], hs_id)

        payload: dict[str, Any] = {
            "firstName": first, "lastName": last,
            "cContactType": contact_types,
            "cPreferredContactMethod": pref,
            "cMarketingOptIn": opt_in,
            "addressCity": p.get("city"), "addressState": p.get("state"),
            "addressPostalCode": p.get("zip"), "addressCountry": p.get("country"),
            "addressStreet": p.get("address"),
            "title": p.get("jobtitle"),
            "description": block,
        }
        if email:
            payload["emailAddress"] = email
        phone = e164_or_none(p.get("phone") or p.get("mobilephone"))
        if phone:
            payload["phoneNumber"] = phone
        if notif:
            payload["cNotificationPreference"] = notif
        heard = HOW_HEARD.get((p.get("referral") or "").split(";")[0])
        if heard:
            payload["cHowDidYouHear"] = await self.san.enum("Contact", "cHowDidYouHear", heard)
        if user_ids:
            payload["assignedUserId"] = user_ids[0]
            payload["assignedUsersIds"] = user_ids
        payload = {k: v for k, v in payload.items() if v not in (None, "")}

        contact_id = self.ledger.get("contacts", hs_id)
        if contact_id:
            self.stats["contact already in ledger"] += 1
        elif email:
            contact_id, action = await find_create_or_fill(
                self.client, "Contact", match_attr="emailAddress", match_value=email,
                create_payload=payload,
                fill_keys=[k for k in payload if k not in ("emailAddress", "cContactType", "assignedUserId", "assignedUsersIds")],
            )
            self.stats[f"contact {action}"] += 1
            if action != "created":
                await self._merge_users("Contact", contact_id, user_ids)
            self.ledger.put("contacts", hs_id, contact_id)
        else:
            created = await self.client.create("Contact", payload)
            contact_id = created["id"]
            self.stats["contact created (no email)"] += 1
            self.ledger.put("contacts", hs_id, contact_id)

        if not verdict.client:
            self.stats["prospect"] += 1
            await self.load_posts(c, contact_id, engagement_id=None, mentor=None, team=[])
            return

        self.stats[f"client → {verdict.status}"] += 1
        engagement_id = await self.load_client_spine(c, contact_id, verdict, mentor, co_mentors, user_ids, first, last)
        await self.load_posts(c, contact_id, engagement_id, mentor, team=user_ids)

    async def _merge_users(self, entity: str, record_id: str, user_ids: list[str]) -> None:
        """Merge ``user_ids`` into a record's assignedUsers (never overwrite)."""
        if not user_ids:
            return
        rec = await self.client.get(entity, record_id, select="assignedUserId,assignedUsersIds")
        current = list(rec.get("assignedUsersIds") or [])
        merged = current + [u for u in user_ids if u not in current]
        payload: dict[str, Any] = {"assignedUsersIds": merged}
        if not rec.get("assignedUserId"):
            payload["assignedUserId"] = user_ids[0]
        if merged != current or "assignedUserId" in payload:
            await self.client.update(entity, record_id, payload)

    # --- the client spine ---

    async def load_client_spine(
        self, c: dict[str, Any], contact_id: str, verdict: Verdict,
        mentor: Optional[dict[str, Any]], co_mentors: list[dict[str, Any]],
        user_ids: list[str], first: str, last: str,
    ) -> str:
        """Account → CClientProfile → CEngagement for a client contact."""
        p = c.get("properties") or {}
        hs_id = c["id"]
        person = f"{first} {last}".strip()

        # The Account is named from what the PERSON typed as their company, or
        # after the person. HubSpot's associated company is used only to enrich
        # (website, address) and only when its name is the same company: most
        # of those records were auto-created from the email DOMAIN, so naming
        # from them merged strangers at one university, and four people who
        # typed "N/A", onto one client profile (Lakeside rehearsal 2026-09-26).
        typed = company_text(p.get("company"))
        account_name = (typed or person).strip()
        cp: dict[str, Any] = {}
        for cid in assoc_ids(c, "companies"):
            cand = (self.snap.companies.get(cid) or {}).get("properties") or {}
            if typed and (cand.get("name") or "").strip().lower() == typed.lower():
                cp = cand
                break

        account_id = self.ledger.get("accounts", hs_id)
        if not account_id:
            existing = await self.client.find_one("Account", "name", account_name)
            if existing:
                account_id = existing["id"]
                self.stats["account matched"] += 1
                await self._merge_users("Account", account_id, user_ids)
            else:
                acc: dict[str, Any] = {
                    "name": account_name, "cCompanyType": ["Client"],
                    "website": clean_url(cp.get("website") or p.get("website")),
                    "phoneNumber": e164_or_none(cp.get("phone")),
                    "billingAddressStreet": cp.get("address"),
                    "billingAddressCity": cp.get("city") or p.get("city"),
                    "billingAddressState": cp.get("state") or p.get("state"),
                    "billingAddressPostalCode": cp.get("zip") or p.get("zip"),
                    "billingAddressCountry": cp.get("country"),
                    "description": strip_html(cp.get("description")),
                }
                industry = await self.san.enum("Account", "industry", (cp.get("industry") or p.get("industry") or "").title())
                if industry:
                    acc["industry"] = industry
                if user_ids:
                    acc["assignedUserId"] = user_ids[0]
                    acc["assignedUsersIds"] = user_ids
                acc = {k: v for k, v in acc.items() if v not in (None, "")}
                created = await create_dropping_invalid(self.client, "Account", acc, droppable=("website", "phoneNumber"))
                account_id = created["id"]
                self.stats["account created"] += 1
            self.ledger.put("accounts", hs_id, account_id)

        profile_id = self.ledger.get("profiles", hs_id)
        if not profile_id:
            profile_id, action = await find_create_or_fill(
                self.client, "CClientProfile",
                match_attr="linkedCompanyId", match_value=account_id,
                create_payload={
                    "name": account_name, "clientcontactId": contact_id, "linkedCompanyId": account_id,
                    **({"assignedUserId": user_ids[0], "assignedUsersIds": user_ids} if user_ids else {}),
                },
                fill_keys=("clientcontactId",),
            )
            self.stats[f"client profile {action}"] += 1
            if action != "created":
                await self._merge_users("CClientProfile", profile_id, user_ids)
            self.ledger.put("profiles", hs_id, profile_id)

        engagement_id = self.ledger.get("engagements", hs_id)
        if engagement_id:
            return engagement_id
        notes = self.snap.notes_by_contact.get(hs_id, [])
        stamps = sorted(filter(None, [(n.get("properties") or {}).get("hs_timestamp") for n in notes]))
        needs = strip_html(p.get("message")) or "Imported from HubSpot; no request text was recorded."
        eng: dict[str, Any] = {
            "name": clean_name(f"{person} — {account_name}" if account_name != person else person, 255),
            "engagementStatus": verdict.status,
            "mentoringNeedsDescription": html.escape(needs).replace("\n", "<br>"),
            "engagementClientId": profile_id,
            "primaryEngagementContactId": contact_id,
            "clientOrganizationId": account_id,
            "engagementStartDate": espo_date(p.get("createdate")),
            "description": html.escape(imported_block([
                ("Mentor requested", p.get("mentor_name__if_known_")),
                ("Website button", p.get("button_source")),
                ("Basis for client status", verdict.reasons),
            ], hs_id)).replace("\n", "<br>"),
        }
        if mentor:
            eng["mentorProfileId"] = mentor["profile"]
            eng["engagementAssignedDate"] = espo_dt(p.get("hubspot_owner_assigneddate")) or espo_dt(p.get("createdate"))
        if stamps:
            eng["lastContactDate"] = espo_dt(stamps[-1])
            eng["lastSessionDate"] = espo_date(stamps[-1])
        if user_ids:
            eng["assignedUserId"] = user_ids[0]
            eng["assignedUsersIds"] = user_ids
        eng = {k: v for k, v in eng.items() if v not in (None, "")}
        created = await self.client.create("CEngagement", eng)
        engagement_id = created["id"]
        self.stats["engagement created"] += 1
        self.ledger.put("engagements", hs_id, engagement_id)
        await self.client.relate("CEngagement", engagement_id, "engagementContacts", contact_id)
        for m in co_mentors:
            try:
                await self.client.relate("CEngagement", engagement_id, "additionalMentors", m["profile"])
                self.stats["co-mentor linked"] += 1
            except EspoError as exc:
                self.problems.append(f"co-mentor link {hs_id} → {m['name']}: {exc}")
        return engagement_id

    # --- notes, meetings, attachments ---

    async def load_posts(
        self, c: dict[str, Any], contact_id: str, engagement_id: Optional[str], mentor: Optional[dict[str, Any]],
        team: list[str],
    ) -> None:
        """Mentor notes and meetings → CSession; other notes → stream posts.

        ``team`` is the engagement's mentor team (mentor + co-mentors' user ids).
        Every session is stamped with the author AND the team, as the app's
        ``create_session`` does: the Mentor Role reads CSession at "own", so a
        session stamped only with its author is invisible to the engagement's
        mentor when another mentor wrote the note (Lakeside check, 2026-09-26).
        """
        hs_id = c["id"]
        for n in self.snap.notes_by_contact.get(hs_id, []):
            if self.ledger.get("notes", n["id"]):
                self.stats["note already in ledger"] += 1
                continue
            np = n.get("properties") or {}
            author = self.mentor(np.get("hubspot_owner_id"))
            author_name = self.snap.owner_name(np.get("hubspot_owner_id"))
            attachment_ids = [a for a in (np.get("hs_attachment_ids") or "").split(";") if a]
            if engagement_id and author:
                sid = await self._session_from_note(n, engagement_id, contact_id, author, author_name, team)
                await self._attach(attachment_ids, "CSession", sid, f"Attachments from HubSpot note {n['id']} of {espo_date(np.get('hs_timestamp'))}")
                self.ledger.put("notes", n["id"], {"session": sid})
                self.stats["session from note"] += 1
            else:
                text = f"[HubSpot note {n['id']}, {espo_date(np.get('hs_timestamp'))}, by {author_name or 'unknown'}]\n{strip_html(np.get('hs_note_body'))}"
                att = await self._upload(attachment_ids, "Note")
                post = {"type": "Post", "parentType": "Contact", "parentId": contact_id, "post": text[:60000]}
                if att:
                    post["attachmentsIds"] = att
                created = await self.client.create("Note", post)
                self.ledger.put("notes", n["id"], {"post": created["id"]})
                self.stats["stream post from note"] += 1

        for m in self.snap.meetings_by_contact.get(hs_id, []):
            if self.ledger.get("meetings", m["id"]):
                continue
            mp = m.get("properties") or {}
            if engagement_id:
                owner = self.mentor(str(mp.get("hubspot_owner_id") or "")) or mentor
                start = espo_dt(mp.get("hs_meeting_start_time") or mp.get("hs_timestamp"))
                end = espo_dt(mp.get("hs_meeting_end_time"))
                in_past = bool(start) and datetime.strptime(start, "%Y-%m-%d %H:%M:%S") < datetime.now(timezone.utc).replace(tzinfo=None)
                body = strip_html(mp.get("hs_meeting_body") or mp.get("hs_internal_meeting_notes"))
                payload: dict[str, Any] = {
                    "name": clean_name(mp.get("hs_meeting_title") or "Meeting"),
                    "engagementId": engagement_id, "sessionType": "Client Session",
                    "status": "Completed" if in_past else "Scheduled",
                    "dateStart": start, "dateEnd": end,
                    "sessionNotes": html.escape(body).replace("\n", "<br>") if body else None,
                    "description": f"{IMPORT_MARK} meeting {m['id']}",
                }
                stamp = list(dict.fromkeys(([owner["user"]] if owner and owner.get("user") else []) + team))
                if stamp:
                    payload["assignedUserId"] = stamp[0]
                    payload["assignedUsersIds"] = stamp
                payload = {k: v for k, v in payload.items() if v not in (None, "")}
                created = await self.client.create("CSession", payload)
                await self.client.relate("CSession", created["id"], "sessionAttendees", contact_id)
                self.ledger.put("meetings", m["id"], {"session": created["id"]})
                self.stats["session from meeting"] += 1
            else:
                text = f"[HubSpot meeting {m['id']}, {espo_date(mp.get('hs_meeting_start_time'))}] {mp.get('hs_meeting_title') or ''}\n{strip_html(mp.get('hs_meeting_body'))}".strip()
                created = await self.client.create("Note", {"type": "Post", "parentType": "Contact", "parentId": contact_id, "post": text})
                self.ledger.put("meetings", m["id"], {"post": created["id"]})
                self.stats["stream post from meeting"] += 1

    async def _session_from_note(
        self, n: dict[str, Any], engagement_id: str, contact_id: str, author: dict[str, Any], author_name: str,
        team: list[str],
    ) -> str:
        """A Completed CSession carrying the note as its session notes."""
        np = n.get("properties") or {}
        body_html = np.get("hs_note_body") or ""
        plain = strip_html(body_html)
        first_line = next((ln.strip() for ln in plain.splitlines() if ln.strip()), "Session note")
        start = espo_dt(np.get("hs_timestamp")) or espo_dt(np.get("hs_createdate"))
        payload: dict[str, Any] = {
            "name": clean_name(first_line, 80),
            "engagementId": engagement_id,
            "sessionType": "Client Session",
            "status": "Completed",
            "dateStart": start,
            "sessionNotes": body_html,
            "description": f"{IMPORT_MARK} note {n['id']} by {author_name}",
        }
        stamp = list(dict.fromkeys(([author["user"]] if author.get("user") else []) + team))
        if stamp:
            payload["assignedUserId"] = stamp[0]
            payload["assignedUsersIds"] = stamp
        payload = {k: v for k, v in payload.items() if v not in (None, "")}
        created = await self.client.create("CSession", payload)
        await self.client.relate("CSession", created["id"], "sessionAttendees", contact_id)
        return created["id"]

    async def _upload(self, file_ids: list[str], related_type: str) -> list[str]:
        """Download HubSpot files by id and upload them as EspoCRM attachments."""
        out: list[str] = []
        for fid in file_ids:
            known = self.ledger.get("files", fid)
            if known:
                out.append(known)
                continue
            if self.hubspot is None:
                out.append(f"dry-Attachment-{fid}")
                self.stats["attachment (planned)"] += 1
                continue
            try:
                meta = self.hubspot.request("GET", f"/files/v3/files/{fid}")
                signed = self.hubspot.request("GET", f"/files/v3/files/{fid}/signed-url")
                data = httpx.get(signed["url"], timeout=120).content
            except (httpx.HTTPError, KeyError) as exc:
                logger.warning(f"HubSpot file {fid} not downloadable: {exc}")
                self.problems.append(f"file {fid}: {exc}")
                continue
            name = meta.get("name") or fid
            ext = meta.get("extension")
            if ext and not name.lower().endswith(f".{ext.lower()}"):
                name = f"{name}.{ext}"
            content_type = signed.get("type") or meta.get("type") or "application/octet-stream"
            if "/" not in content_type:
                content_type = "application/octet-stream"
            att_id = await self.client.upload_attachment(
                filename=name, content_type=content_type,
                data_base64=base64.b64encode(data).decode(),
                related_type=related_type, field="attachments",
            )
            self.ledger.put("files", fid, att_id)
            self.stats["attachment uploaded"] += 1
            out.append(att_id)
        return out

    async def _attach(self, file_ids: list[str], parent_type: str, parent_id: str, caption: str) -> None:
        """Attach HubSpot files to a record through a stream post."""
        if not file_ids:
            return
        att = await self._upload(file_ids, "Note")
        if att:
            await self.client.create("Note", {
                "type": "Post", "parentType": parent_type, "parentId": parent_id,
                "post": caption, "attachmentsIds": att,
            })


# --- Ledger rebuild ---


async def rebuild_ledger(client: EspoClient, ledger: Ledger) -> None:
    """
    Recover the ledger from the markers every imported record carries.

    Needed when the ledger file is behind the CRM (two runs written at once, a
    crash between a create and its flush). Contacts, engagements and sessions
    carry ``HubSpot id N`` / ``note N`` / ``meeting N`` in their description,
    stream posts carry ``[HubSpot note N`` in their text, mentors are keyed by
    ``cbmEmail`` and Users by ``userName``. Accounts and client profiles are
    recovered through the engagement's links. Only missing entries are added.

    :param client: Admin client.
    :type client: EspoClient
    :param ledger: Ledger to fill.
    :type ledger: Ledger
    """
    async def every(entity: str, select: str, where: Optional[list[dict[str, Any]]] = None):
        offset = 0
        while True:
            page = await client.list(entity, select=select, where=where, max_size=200, offset=offset)
            rows = page.get("list") or []
            for r in rows:
                yield r
            if len(rows) < 200:
                return
            offset += 200

    added: Counter[str] = Counter()
    id_re = re.compile(r"HubSpot id (\d+)")
    async for r in every("Contact", "id,description"):
        m = id_re.search(r.get("description") or "")
        if m and not ledger.get("contacts", m.group(1)):
            ledger.data["contacts"][m.group(1)] = r["id"]
            added["contacts"] += 1
    async for r in every("CEngagement", "id,description,engagementClientId,clientOrganizationId"):
        m = id_re.search(html.unescape(r.get("description") or ""))
        if not m:
            continue
        hs = m.group(1)
        for kind, key in (("engagements", "id"), ("profiles", "engagementClientId"), ("accounts", "clientOrganizationId")):
            if r.get(key) and not ledger.get(kind, hs):
                ledger.data[kind][hs] = r[key]
                added[kind] += 1
    sess_re = re.compile(r"Imported from HubSpot (note|meeting) (\d+)")
    async for r in every("CSession", "id,description"):
        m = sess_re.search(r.get("description") or "")
        if m:
            kind = "notes" if m.group(1) == "note" else "meetings"
            if not ledger.get(kind, m.group(2)):
                ledger.data[kind][m.group(2)] = {"session": r["id"]}
                added[kind] += 1
    post_re = re.compile(r"^\[HubSpot (note|meeting) (\d+)")
    async for r in every("Note", "id,post", where=[{"type": "equals", "attribute": "type", "value": "Post"}]):
        m = post_re.match(r.get("post") or "")
        if m:
            kind = "notes" if m.group(1) == "note" else "meetings"
            if not ledger.get(kind, m.group(2)):
                ledger.data[kind][m.group(2)] = {"post": r["id"]}
                added[kind] += 1
    ledger.flush()
    logger.info(f"Ledger rebuilt from the CRM; added {dict(added) or 'nothing'}")


# --- Session stamp repair ---


async def repair_session_stamps(client: Any, ledger: Ledger) -> Counter:
    """
    Merge each imported session's engagement mentor team into its assignedUsers.

    Repairs sessions written before the team stamp existed. Idempotent: a
    session already carrying its team is left alone.

    :param client: Write client.
    :type client: Any
    :param ledger: Ledger naming the sessions.
    :type ledger: Ledger
    :returns: Counts of sessions checked and updated.
    :rtype: Counter
    """
    counts: Counter[str] = Counter()
    team_cache: dict[str, list[str]] = {}
    session_ids = [v["session"] for kind in ("notes", "meetings") for v in ledger.data.get(kind, {}).values() if isinstance(v, dict) and v.get("session")]
    for i, sid in enumerate(session_ids, 1):
        if i % 200 == 0:
            logger.info(f"session stamps: {i}/{len(session_ids)}")
        try:
            sess = await client.get("CSession", sid, select="engagementId,assignedUserId,assignedUsersIds")
        except EspoError as exc:
            logger.warning(f"session {sid} unreadable: {exc}")
            counts["unreadable"] += 1
            continue
        eng_id = sess.get("engagementId")
        if not eng_id:
            counts["no engagement"] += 1
            continue
        if eng_id not in team_cache:
            eng = await client.get("CEngagement", eng_id, select="assignedUsersIds")
            team_cache[eng_id] = list(eng.get("assignedUsersIds") or [])
        current = list(sess.get("assignedUsersIds") or [])
        merged = current + [u for u in team_cache[eng_id] if u not in current]
        counts["checked"] += 1
        if merged != current:
            payload: dict[str, Any] = {"assignedUsersIds": merged}
            if not sess.get("assignedUserId") and merged:
                payload["assignedUserId"] = merged[0]
            await client.update("CSession", sid, payload)
            counts["updated"] += 1
    logger.info(f"Session stamp repair: {dict(counts)}")
    return counts


# --- Entry point ---


def setup_logging(log_file: Path) -> None:
    """Console at INFO, rotating file at DEBUG."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(LOG_FORMAT)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)
    fh = RotatingFileHandler(log_file, maxBytes=5_242_880, backupCount=3)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def newest_snapshot(root: Path) -> Path:
    """The most recent dated snapshot folder under ``root``."""
    dirs = sorted(d for d in root.iterdir() if d.is_dir() and (d / "objects").exists())
    if not dirs:
        raise FileNotFoundError(f"No snapshot under {root}")
    return dirs[-1]


async def run(args: argparse.Namespace) -> int:
    """
    Plan or apply the load.

    :param args: Parsed arguments.
    :type args: argparse.Namespace
    :returns: Exit code.
    :rtype: int
    """
    snap_dir = Path(args.snapshot) if args.snapshot else newest_snapshot(DEFAULT_OUT_ROOT)
    target = read_target(Path(args.target).expanduser())
    setup_logging(snap_dir / f"load-{target.host}.log")
    mode = "WRITE" if args.write else "DRY RUN"
    logger.info(f"{mode}: {snap_dir} → {target.base_url} as {target.admin_user}")

    try:
        user_name, token = await login_token(target.base_url, target.admin_user, target.admin_pass, 30)
    except AuthError:
        if not target.fallback_user:
            raise
        # The provisioning account's stored password can lag the CRM (Lakeside,
        # 2026-09-26); the CRM admin is the same privilege level for this job.
        logger.warning(f"{target.admin_user} rejected; signing in as {target.fallback_user} instead")
        user_name, token = await login_token(target.base_url, target.fallback_user, target.fallback_pass, 30)
    real = EspoClient.for_user_token(target.base_url, user_name, token, timeout=60)
    # A dry run plans from an empty scratch ledger; the repair mode reads the
    # REAL ledger in both modes (it only ever reads it).
    scratch = not args.write and not args.repair_session_stamps
    ledger = Ledger(snap_dir / f"ledger-{target.host}{'-dryrun' if scratch else ''}.json")
    if scratch and ledger.path.exists():
        ledger.path.unlink()
        ledger = Ledger(ledger.path)
    hubspot = HubSpot(read_token(Path(args.hubspot_env).expanduser())) if args.write else None
    client: Any = CountingClient(real) if args.write else PlanningClient(real)

    if args.rebuild_ledger and args.write:
        await rebuild_ledger(real, ledger)
    if args.repair_session_stamps:
        counts = await repair_session_stamps(client, ledger)
        print(f"\n{mode} session stamp repair against {target.base_url}: {dict(counts)}")
        return 0

    snap = Snapshot(snap_dir).load()
    loader = Loader(client=client, snap=snap, ledger=ledger, hubspot=hubspot, send_access_info=args.send_access_info)
    await loader.setup()

    verdicts = Counter()
    for c in snap.contacts:
        v = classify(snap, c)
        verdicts["client " + v.status if v.client else "prospect"] += 1
    logger.info(f"Ruling 4.1 B classification: {dict(verdicts)}")
    if args.classify_only:
        return 0

    await loader.load_mentors()
    if not args.mentors_only:
        await loader.load_contacts()

    print(f"\n{mode} against {target.base_url}")
    print("Records:")
    for k, v in sorted(loader.stats.items()):
        print(f"  {k:36} {v}")
    print("CRM operations:")
    for k, v in sorted(client.counts.items()):
        print(f"  {k:36} {v}")
    if loader.problems:
        print(f"Problems ({len(loader.problems)}):")
        for pr in loader.problems[:40]:
            print("  " + pr)
    report = {"mode": mode, "target": target.base_url, "stats": dict(loader.stats), "ops": dict(client.counts), "problems": loader.problems, "verdicts": dict(verdicts)}
    (snap_dir / f"load-report-{target.host}{'' if args.write else '-dryrun'}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    if not args.write:
        ledger.path.unlink(missing_ok=True)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="env file of the EspoCRM to load")
    parser.add_argument("--snapshot", help="snapshot folder (default: newest)")
    parser.add_argument("--hubspot-env", default=str(Path.home() / ".config" / "cbm-boston" / "hubspot.env"))
    parser.add_argument("--write", action="store_true", help="apply (default is a dry run)")
    parser.add_argument("--mentors-only", action="store_true", help="stop after the mentor roster")
    parser.add_argument("--rebuild-ledger", action="store_true", help="first recover the ledger from the CRM's import markers (with --write)")
    parser.add_argument("--repair-session-stamps", action="store_true", help="stamp every imported session with its engagement's mentor team, then stop")
    parser.add_argument("--classify-only", action="store_true", help="print the ruling 4.1 B counts and stop")
    parser.add_argument("--send-access-info", action="store_true", help="have EspoCRM email each new mentor login (never in a rehearsal)")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
