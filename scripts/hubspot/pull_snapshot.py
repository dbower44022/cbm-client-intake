"""
Pull a complete read-only snapshot of a HubSpot portal and summarise it.

:author: Doug
:date: 2026-09-26
:description: Step 1 and 2 of the Boston HubSpot to EspoCRM migration. Reads
    every CRM object type (standard, engagement and custom) with every
    property and its associations, plus owners, pipelines, lists, files and
    forms, into a dated snapshot folder outside the repository. Then writes an
    inventory (counts, property fill rates, picklist values) beside it. The
    portal is never written to: every call is a GET or a search/batch-read
    POST.

Usage::

    uv run --with tenacity python scripts/hubspot/pull_snapshot.py
    uv run --with tenacity python scripts/hubspot/pull_snapshot.py --inventory-only

The access token is read from ``~/.config/cbm-boston/hubspot.env`` (line
``HUBSPOT_TOKEN=…``) and never printed. Override the file with ``--env-file``
and the output root with ``--out``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# --- Constants ---

HUBSPOT_API = "https://api.hubapi.com"
DEFAULT_ENV_FILE = Path.home() / ".config" / "cbm-boston" / "hubspot.env"
DEFAULT_OUT_ROOT = Path.home() / ".config" / "cbm-boston" / "hubspot-snapshot"
LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(module)s - %(levelname)s - %(funcName)s"
    " - %(lineno)d --- %(message)s"
)

# The standard CRM objects and the engagement objects, all served by the same
# v3 objects endpoints. Custom objects are discovered from /crm/v3/schemas.
STANDARD_OBJECTS = ["contacts", "companies", "deals", "tickets"]
ENGAGEMENT_OBJECTS = ["notes", "calls", "emails", "meetings", "tasks", "communications"]
PAGE_SIZE = 100
BATCH_SIZE = 100
# HubSpot allows 100 requests per 10 seconds on a private app; a small pause
# between calls keeps a full pull under that without needing to count.
PAUSE_SECONDS = 0.12


class RetryableHttpError(Exception):
    """Raised for 429 and 5xx responses so tenacity retries them."""


class ForbiddenError(Exception):
    """Raised for 403 so a missing scope is recorded rather than retried."""


# --- Configuration ---


@dataclass
class Config:
    """
    Run configuration.

    :param token: HubSpot private app access token.
    :type token: str
    :param out_dir: Dated snapshot folder.
    :type out_dir: Path
    :param inventory_only: Skip the pull and rebuild the inventory from disk.
    :type inventory_only: bool
    """

    token: str
    out_dir: Path
    inventory_only: bool = False
    forbidden: list[str] = field(default_factory=list)


def setup_logging(log_file: Path) -> None:
    """
    Configure console and rotating file logging.

    :param log_file: Path of the log file.
    :type log_file: Path
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter(LOG_FORMAT)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)
    handler = RotatingFileHandler(log_file, maxBytes=5_242_880, backupCount=3)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    # httpx logs every request URL at INFO; the URLs carry no secret but the
    # volume drowns the milestones.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def read_token(env_file: Path) -> str:
    """
    Read ``HUBSPOT_TOKEN`` from a dotenv-style file without a shell.

    :param env_file: File holding a ``HUBSPOT_TOKEN=`` line.
    :type env_file: Path
    :returns: The token.
    :rtype: str
    :raises FileNotFoundError: If the file is missing.
    :raises ValueError: If no token line is present.
    """
    logger.debug(f"Reading token from {env_file}")
    text = env_file.read_text(encoding="utf-8")
    match = re.search(r"^HUBSPOT_TOKEN=(\S+)\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"No HUBSPOT_TOKEN line in {env_file}")
    return match.group(1)


# --- HubSpot client ---


class HubSpot:
    """
    Minimal read-only HubSpot v3 client.

    :param token: Private app access token.
    :type token: str
    """

    def __init__(self, token: str) -> None:
        self._client = httpx.Client(
            base_url=HUBSPOT_API,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(60.0),
        )

    @retry(
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((RetryableHttpError, httpx.TransportError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """
        Issue one request and return its JSON body.

        :param method: HTTP method.
        :type method: str
        :param path: Path under the API root.
        :type path: str
        :returns: Decoded JSON body.
        :rtype: dict[str, Any]
        :raises ForbiddenError: On 403 (a scope the app was not granted).
        :raises RetryableHttpError: On 429 or 5xx, after retries.
        :raises httpx.HTTPStatusError: On any other non-2xx status.
        """
        time.sleep(PAUSE_SECONDS)
        response = self._client.request(method, path, **kwargs)
        logger.debug(f"{method} {path} -> {response.status_code}")
        if response.status_code == 403:
            raise ForbiddenError(f"{method} {path}: {response.text[:300]}")
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableHttpError(f"{method} {path}: {response.status_code}")
        response.raise_for_status()
        return response.json()

    def paged(self, path: str, params: Optional[dict[str, Any]] = None) -> Iterator[dict[str, Any]]:
        """
        Iterate every result of a cursor-paged GET endpoint.

        :param path: Endpoint path.
        :type path: str
        :param params: Query parameters (``limit`` and ``after`` are managed here).
        :type params: dict[str, Any] | None
        :returns: Each result object.
        :rtype: Iterator[dict[str, Any]]
        """
        query = dict(params or {})
        query["limit"] = PAGE_SIZE
        after: Optional[str] = None
        while True:
            if after:
                query["after"] = after
            body = self.request("GET", path, params=query)
            for item in body.get("results", []):
                yield item
            after = (body.get("paging") or {}).get("next", {}).get("after")
            if not after:
                return


# --- Pull ---


def write_json(path: Path, data: Any) -> None:
    """
    Write JSON to disk, creating parents.

    :param path: Destination file.
    :type path: Path
    :param data: JSON-serialisable content.
    :type data: Any
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    logger.debug(f"Wrote {path}")


def guarded(cfg: Config, label: str, fn: Any, default: Any) -> Any:
    """
    Run one pull step, recording a 403 as a missing scope instead of failing.

    :param cfg: Run configuration (collects the forbidden labels).
    :type cfg: Config
    :param label: Name of the step for the inventory.
    :type label: str
    :param fn: Zero-argument callable performing the step.
    :type fn: Any
    :param default: Value to return when the step is forbidden.
    :type default: Any
    :returns: The step result or ``default``.
    :rtype: Any
    """
    try:
        return fn()
    except ForbiddenError:
        logger.warning(f"Forbidden (scope not granted): {label}")
        cfg.forbidden.append(label)
        return default


def pull_object_type(hs: HubSpot, cfg: Config, object_type: str, assoc_types: list[str]) -> list[dict[str, Any]]:
    """
    Pull every record of one object type with all properties and associations.

    :param hs: Client.
    :type hs: HubSpot
    :param cfg: Run configuration.
    :type cfg: Config
    :param object_type: HubSpot object type name or custom objectTypeId.
    :type object_type: str
    :param assoc_types: Object types whose associations to request.
    :type assoc_types: list[str]
    :returns: The records.
    :rtype: list[dict[str, Any]]
    """
    logger.info(f"Pulling {object_type}")
    props = guarded(cfg, f"properties/{object_type}", lambda: hs.request("GET", f"/crm/v3/properties/{object_type}"), {"results": []})
    write_json(cfg.out_dir / "properties" / f"{object_type}.json", props)
    names = [p["name"] for p in props.get("results", [])]
    if not names:
        return []

    ids: list[str] = []
    assoc_by_id: dict[str, Any] = {}

    def list_ids() -> None:
        params = {"properties": "hs_object_id", "associations": ",".join(assoc_types)}
        for item in hs.paged(f"/crm/v3/objects/{object_type}", params):
            ids.append(item["id"])
            if item.get("associations"):
                assoc_by_id[item["id"]] = item["associations"]

    guarded(cfg, f"objects/{object_type}", list_ids, None)
    logger.info(f"{object_type}: {len(ids)} ids")

    records: list[dict[str, Any]] = []
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        body = {"properties": names, "inputs": [{"id": i} for i in chunk]}
        page = hs.request("POST", f"/crm/v3/objects/{object_type}/batch/read", json=body)
        for rec in page.get("results", []):
            rec["associations"] = assoc_by_id.get(rec["id"], {})
            records.append(rec)
        logger.debug(f"{object_type}: read {len(records)}/{len(ids)}")
    write_json(cfg.out_dir / "objects" / f"{object_type}.json", records)
    logger.info(f"{object_type}: {len(records)} records saved")
    return records


def pull_all(hs: HubSpot, cfg: Config) -> None:
    """
    Pull the whole portal into the snapshot folder.

    :param hs: Client.
    :type hs: HubSpot
    :param cfg: Run configuration.
    :type cfg: Config
    """
    schemas = guarded(cfg, "schemas", lambda: hs.request("GET", "/crm/v3/schemas"), {"results": []})
    write_json(cfg.out_dir / "schemas.json", schemas)
    custom_types = [s["objectTypeId"] for s in schemas.get("results", [])]
    logger.info(f"Custom object types: {custom_types or 'none'}")

    object_types = STANDARD_OBJECTS + ENGAGEMENT_OBJECTS + custom_types
    assoc_types = STANDARD_OBJECTS + custom_types
    for object_type in object_types:
        pull_object_type(hs, cfg, object_type, [t for t in assoc_types if t != object_type])

    owners = guarded(cfg, "owners", lambda: list(hs.paged("/crm/v3/owners")), [])
    archived = guarded(cfg, "owners-archived", lambda: list(hs.paged("/crm/v3/owners", {"archived": "true"})), [])
    write_json(cfg.out_dir / "owners.json", {"active": owners, "archived": archived})

    for kind in ("deals", "tickets"):
        pipelines = guarded(cfg, f"pipelines/{kind}", lambda k=kind: hs.request("GET", f"/crm/v3/pipelines/{k}"), {"results": []})
        write_json(cfg.out_dir / "pipelines" / f"{kind}.json", pipelines)

    lists = guarded(cfg, "lists", lambda: hs.request("POST", "/crm/v3/lists/search", json={"count": 500}), {"lists": []})
    write_json(cfg.out_dir / "lists.json", lists)

    files = guarded(cfg, "files", lambda: list(hs.paged("/files/v3/files/search")), [])
    write_json(cfg.out_dir / "files.json", files)

    forms = guarded(cfg, "forms", lambda: list(hs.paged("/marketing/v3/forms")), [])
    write_json(cfg.out_dir / "forms.json", forms)

    write_json(cfg.out_dir / "forbidden.json", cfg.forbidden)


# --- Inventory ---


def is_empty(value: Any) -> bool:
    """
    Decide whether a property value counts as unset.

    :param value: Raw property value.
    :type value: Any
    :returns: True when nothing meaningful is stored.
    :rtype: bool
    """
    return value is None or (isinstance(value, str) and value.strip() == "")


def build_inventory(cfg: Config) -> dict[str, Any]:
    """
    Summarise the snapshot: counts, property fill rates, picklists, associations.

    :param cfg: Run configuration.
    :type cfg: Config
    :returns: The inventory document.
    :rtype: dict[str, Any]
    """
    inventory: dict[str, Any] = {"objects": {}, "forbidden": []}
    forbidden_file = cfg.out_dir / "forbidden.json"
    if forbidden_file.exists():
        inventory["forbidden"] = json.loads(forbidden_file.read_text(encoding="utf-8"))

    for prop_file in sorted((cfg.out_dir / "properties").glob("*.json")):
        object_type = prop_file.stem
        props = json.loads(prop_file.read_text(encoding="utf-8")).get("results", [])
        rec_file = cfg.out_dir / "objects" / f"{object_type}.json"
        records = json.loads(rec_file.read_text(encoding="utf-8")) if rec_file.exists() else []
        fill: Counter[str] = Counter()
        values: dict[str, Counter[str]] = {}
        assoc: Counter[str] = Counter()
        for rec in records:
            for name, value in (rec.get("properties") or {}).items():
                if not is_empty(value):
                    fill[name] += 1
            for other, block in (rec.get("associations") or {}).items():
                assoc[other] += len(block.get("results", []))
        enum_names = {p["name"] for p in props if p.get("type") == "enumeration"}
        for rec in records:
            for name in enum_names:
                value = (rec.get("properties") or {}).get(name)
                if not is_empty(value):
                    values.setdefault(name, Counter())[str(value)] += 1

        prop_rows = []
        for p in props:
            populated = fill.get(p["name"], 0)
            if populated == 0:
                continue
            row: dict[str, Any] = {
                "name": p["name"],
                "label": p.get("label"),
                "type": p.get("type"),
                "fieldType": p.get("fieldType"),
                "custom": not p.get("hubspotDefined", False),
                "populated": populated,
            }
            if p["name"] in values:
                row["values"] = dict(values[p["name"]].most_common())
                row["options"] = [o.get("label") for o in p.get("options", [])]
            prop_rows.append(row)
        prop_rows.sort(key=lambda r: (-r["custom"], -r["populated"]))
        inventory["objects"][object_type] = {
            "records": len(records),
            "properties_defined": len(props),
            "properties_custom": sum(1 for p in props if not p.get("hubspotDefined", False)),
            "properties_populated": len(prop_rows),
            "associations": dict(assoc),
            "properties": prop_rows,
        }

    for name in ("owners", "lists", "files", "forms", "schemas"):
        path = cfg.out_dir / f"{name}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if name == "owners":
            inventory["owners"] = {
                "active": [{"id": o["id"], "email": o.get("email"), "name": f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()} for o in data.get("active", [])],
                "archived": len(data.get("archived", [])),
            }
        elif name == "lists":
            inventory["lists"] = [{"name": l.get("name"), "type": l.get("processingType"), "object": l.get("objectTypeId")} for l in data.get("lists", [])]
        elif name == "schemas":
            inventory["custom_objects"] = [{"name": s.get("name"), "objectTypeId": s.get("objectTypeId"), "label": (s.get("labels") or {}).get("plural")} for s in data.get("results", [])]
        else:
            inventory[name] = len(data)

    pipelines_dir = cfg.out_dir / "pipelines"
    if pipelines_dir.exists():
        inventory["pipelines"] = {}
        for pf in pipelines_dir.glob("*.json"):
            data = json.loads(pf.read_text(encoding="utf-8"))
            inventory["pipelines"][pf.stem] = [
                {"name": pl.get("label"), "stages": [s.get("label") for s in pl.get("stages", [])]}
                for pl in data.get("results", [])
            ]
    return inventory


def print_summary(inventory: dict[str, Any]) -> None:
    """
    Print the counts a reader needs first.

    :param inventory: Inventory document.
    :type inventory: dict[str, Any]
    """
    print("\nObject                records  props(defined/custom/populated)  associations")
    for name, obj in inventory["objects"].items():
        assoc = ", ".join(f"{k}:{v}" for k, v in obj["associations"].items()) or "-"
        print(f"{name:22}{obj['records']:8}  {obj['properties_defined']:>4}/{obj['properties_custom']:<4}/{obj['properties_populated']:<6}          {assoc}")
    print(f"\nowners: {len(inventory.get('owners', {}).get('active', []))} active, {inventory.get('owners', {}).get('archived', 0)} archived")
    print(f"lists: {len(inventory.get('lists', []))}   files: {inventory.get('files', '?')}   forms: {inventory.get('forms', '?')}   custom objects: {len(inventory.get('custom_objects', []))}")
    for kind, pls in (inventory.get("pipelines") or {}).items():
        for pl in pls:
            print(f"pipeline {kind}/{pl['name']}: {' > '.join(pl['stages'])}")
    if inventory["forbidden"]:
        print(f"forbidden (scope not granted): {inventory['forbidden']}")


# --- Entry point ---


def main(argv: Optional[list[str]] = None) -> int:
    """
    Parse arguments and run the pull and/or the inventory.

    :param argv: Command-line arguments (defaults to ``sys.argv``).
    :type argv: list[str] | None
    :returns: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--date", default=date.today().isoformat(), help="snapshot folder name (default today)")
    parser.add_argument("--inventory-only", action="store_true", help="rebuild the inventory from an existing snapshot")
    args = parser.parse_args(argv)

    out_dir = args.out / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(out_dir / "pull.log")
    logger.info(f"Snapshot folder: {out_dir}")

    try:
        token = read_token(args.env_file)
    except (FileNotFoundError, ValueError):
        logger.exception("Token file unreadable")
        return 2
    cfg = Config(token=token, out_dir=out_dir, inventory_only=args.inventory_only)

    if not cfg.inventory_only:
        hs = HubSpot(token)
        try:
            pull_all(hs, cfg)
        except (httpx.HTTPStatusError, RetryableHttpError):
            logger.exception("Pull failed; the snapshot is partial")
            return 1

    inventory = build_inventory(cfg)
    write_json(out_dir / "inventory.json", inventory)
    print_summary(inventory)
    logger.info(f"Inventory written to {out_dir / 'inventory.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
