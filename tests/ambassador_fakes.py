"""Fakes for the Ambassador Program tests: an in-memory report store and a
small CRM that answers the filters the program sends."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

from ambassador import store as store_mod
from core.espo import EspoError


def _match(row: dict, c: dict, links: dict) -> bool:
    t, a, v = c["type"], c.get("attribute"), c.get("value")
    if t == "or":
        return any(_match(row, s, links) for s in v)
    have = row.get(a)
    if t == "equals":
        return have == v
    if t == "notEquals":
        return have is not None and have != v
    if t == "in":
        return have in v
    if t == "isTrue":
        return bool(have)
    if t == "isFalse":
        return not have
    if t == "isNull":
        return have in (None, "")
    if t == "isNotNull":
        return have not in (None, "")
    if t == "contains":
        return v.lower() in str(have or "").lower()
    if t == "startsWith":
        return str(have or "").lower().startswith(v.lower())
    if t == "endsWith":
        return str(have or "").lower().endswith(v.lower())
    if t == "linkedWith":
        return any(x in links.get((row.get("_entity"), row["id"], a), []) for x in v)
    if t in ("after", "before"):
        return bool(have) and (str(have) > str(v) if t == "after" else str(have) < str(v))
    raise AssertionError(f"unexpected filter {t}")


class FakeCrm:
    def __init__(self, *, built: bool = True) -> None:
        self.data: dict[str, dict[str, dict]] = {}
        self.links: dict[tuple, list[str]] = {}
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, str, dict]] = []
        self.related: list[tuple[str, str, str, str]] = []
        self.built = built
        self.fail_on: Optional[str] = None   # an entity whose create raises once

    def add(self, entity: str, **row) -> dict:
        row.setdefault("id", uuid.uuid4().hex[:17])
        row["_entity"] = entity
        self.data.setdefault(entity, {})[row["id"]] = row
        return row

    def link(self, entity: str, rid: str, link: str, other: str) -> None:
        self.links.setdefault((entity, rid, link), []).append(other)

    def rows(self, entity: str) -> list[dict]:
        return list(self.data.get(entity, {}).values())

    async def metadata(self, key: str):
        if not self.built:
            return None
        if key.endswith(".links"):
            entity = key.split(".")[1]
            return {"cReferredBy": {}} if entity == "Contact" else {"referredBy": {}}
        if key.endswith(".fields"):
            entity = key.split(".")[1]
            fields = {"activityType": {}} if entity == "CAmbassadorActivity" else {}
            if entity == "CPartnerProfile":
                fields["partnershipStatus"] = {}
            if entity == "CSponsorProfile":
                fields["funderStatus"] = {}
            return fields
        return None

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        rows = [r for r in self.rows(entity) if all(_match(r, c, self.links) for c in where or [])]
        if order_by:
            rows.sort(key=lambda r: str(r.get(order_by) or ""), reverse=(order == "desc"))
        return {"total": len(rows), "list": [dict(r) for r in rows[offset:offset + max_size]]}

    async def get(self, entity, rid, select=None):
        row = self.data.get(entity, {}).get(rid)
        if row is None:
            raise EspoError(f"get {entity}/{rid} failed: HTTP 404 Not Found")
        return dict(row)

    async def find_one(self, entity, attribute, value, select="id"):
        for r in self.rows(entity):
            if r.get(attribute) == value:
                return dict(r)
        return None

    async def create(self, entity, payload):
        if self.fail_on == entity:
            self.fail_on = None
            raise EspoError(f"create {entity} failed: HTTP 503")
        row = self.add(entity, **dict(payload))
        self.created.append((entity, dict(payload)))
        return dict(row)

    async def update(self, entity, rid, payload):
        self.data[entity][rid].update(payload)
        self.updated.append((entity, rid, dict(payload)))
        return dict(self.data[entity][rid])

    async def relate(self, entity, rid, link, other):
        self.related.append((entity, rid, link, other))
        self.link(entity, rid, link, other)

    async def list_related(self, entity, rid, link, **kw):
        return {"total": 0, "list": []}


class MemoryReportStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def capture(self, *, token, user_id, user_name, mentor_profile_id, payload,
                      lease_seconds, now=None):
        for r in self.rows.values():
            if r["submission_token"] == token:
                return dict(r), False
        now = now or datetime.now(timezone.utc)
        row = {"id": uuid.uuid4().hex, "reference": store_mod.new_reference(),
               "submission_token": token, "user_id": user_id, "user_name": user_name,
               "mentor_profile_id": mentor_profile_id,
               "payload": json.loads(json.dumps(payload)), "status": "pending", "attempts": 0,
               "next_attempt_at": now, "lease_until": now + timedelta(seconds=lease_seconds),
               "progress": {}, "activity_id": None, "last_error": None,
               "created_at": now, "updated_at": now}
        self.rows[row["id"]] = row
        return dict(row), True

    async def get(self, rid):
        return dict(self.rows[rid]) if rid in self.rows else None

    async def save_progress(self, rid, progress):
        self.rows[rid]["progress"] = dict(progress)

    async def delivered(self, rid, activity_id):
        self.rows[rid].update(status="delivered", activity_id=activity_id, lease_until=None)

    async def failed_attempt(self, rid, error, now=None):
        r = self.rows[rid]
        r["attempts"] += 1
        due = store_mod.next_after(r["attempts"], now or datetime.now(timezone.utc))
        r["status"] = "pending" if due else "failed"
        r["next_attempt_at"] = due or r["next_attempt_at"]
        r["lease_until"] = None
        r["last_error"] = error
        return r["status"]

    async def claim_due(self, limit, lease_seconds, now=None):
        now = now or datetime.now(timezone.utc)
        out = []
        for r in self.rows.values():
            if r["status"] == "pending" and r["next_attempt_at"] <= now and (
                    r["lease_until"] is None or r["lease_until"] < now):
                r["lease_until"] = now + timedelta(seconds=lease_seconds)
                out.append(dict(r))
        return out[:limit]

    async def undelivered_for(self, user_id):
        return [dict(r) for r in self.rows.values()
                if r["user_id"] == user_id and r["status"] != "delivered"]


def settings(**kw) -> SimpleNamespace:
    base = dict(
        organization_name="Test Mentors", mentor_email_domain="mentors.test",
        ambassador_free_mail_domains_set=frozenset({"gmail.com", "yahoo.com"}),
        ambassador_review_teams_list=["Marketing Admin Team"], ambassador_program=True,
        ambassador_edit_days=14, alert_email_to_list=["alerts@example.org"],
        ops_mailbox="info@example.org", app_base_url="https://apps.example.org",
        partner_team_name="Partner Management Team", sponsor_team_name="Sponsor Management Team",
        sandbox_address_domain="",
    )
    base.update(kw)
    return SimpleNamespace(**base)
