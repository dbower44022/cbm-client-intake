"""In-memory twins for the feedback survey tests (phases 8 and 9): the
``feedback_send`` / ``feedback_alert`` store and a small CRM that answers the
list filters the feedback code uses."""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

from core.espo import EspoError
from feedback.store import (ALERT_RETRY_EVERY, ALERT_RETRY_FOR, FAILED, MAX_ATTEMPTS, PENDING, SENT,
                            STALE_PENDING, norm_email)


class MemoryFeedbackStore:
    def __init__(self):
        self.sends: dict[str, dict] = {}
        self.alerts: dict[str, dict] = {}

    async def claim(self, send_key, *, moment, survey_key, entity_type, record_id, email,
                    contact_id=None, created_by="", now=None):
        now = now or datetime.now(timezone.utc)
        row = self.sends.get(send_key)
        if row is None:
            self.sends[send_key] = {"send_key": send_key, "moment": moment,
                                    "survey_key": survey_key, "entity_type": entity_type,
                                    "record_id": record_id, "email": norm_email(email),
                                    "contact_id": contact_id, "outcome": PENDING, "attempts": 1,
                                    "reason": None, "link_id": None, "created_at": now,
                                    "updated_at": now}
            return True
        if (row["outcome"] == FAILED and row["attempts"] < MAX_ATTEMPTS) or (
                row["outcome"] == PENDING and row["updated_at"] < now - STALE_PENDING):
            row.update(outcome=PENDING, attempts=row["attempts"] + 1, email=norm_email(email),
                       updated_at=now)
            return True
        return False

    async def finish(self, send_key, outcome, *, link_id=None, reason=None, now=None):
        row = self.sends[send_key]
        row.update(outcome=outcome, reason=reason, updated_at=now or datetime.now(timezone.utc))
        if link_id:
            row["link_id"] = link_id

    async def recently_sent(self, email, since):
        address = norm_email(email)
        return any(r["email"] == address and r["outcome"] == SENT and r["updated_at"] >= since
                   for r in self.sends.values())

    async def get(self, send_key):
        row = self.sends.get(send_key)
        return copy.deepcopy(row) if row else None

    async def claim_alert(self, response_id, now=None):
        now = now or datetime.now(timezone.utc)
        row = self.alerts.get(response_id)
        if row is None:
            self.alerts[response_id] = {"outcome": PENDING, "created_at": now, "updated_at": now}
            return True
        if row["outcome"] == FAILED:
            row.update(outcome=PENDING, updated_at=now)
            return True
        return False

    async def finish_alert(self, response_id, outcome, reason=None, now=None):
        row = self.alerts.setdefault(response_id, {"created_at": now or datetime.now(timezone.utc)})
        row.update(outcome=outcome, reason=reason, updated_at=now or datetime.now(timezone.utc))

    async def failed_alerts(self, now=None):
        now = now or datetime.now(timezone.utc)
        return [k for k, v in self.alerts.items() if v["outcome"] == FAILED
                and v["updated_at"] <= now - ALERT_RETRY_EVERY
                and v["created_at"] >= now - ALERT_RETRY_FOR]


def _match(row: dict, clause: dict) -> bool:
    t, a, v = clause["type"], clause.get("attribute"), clause.get("value")
    have = row.get(a)
    if t == "equals":
        return have == v
    if t == "in":
        return have in v
    if t == "isTrue":
        return bool(have)
    if t == "isFalse":
        return not have
    if t in ("after", "before"):
        if not have:
            return False
        return str(have) > str(v) if t == "after" else str(have) < str(v)
    raise AssertionError(f"unexpected filter {t}")


class FakeCrm:
    """Records by entity; ``links[(entity, id, link)]`` lists related ids;
    ``meta`` answers metadata reads; ``denied`` makes reads of a record 403
    (to stand in for the Mentor Role's read own)."""

    def __init__(self, *, has_entity: bool = True):
        self.data: dict[str, dict[str, dict]] = {}
        self.links: dict[tuple[str, str, str], list[str]] = {}
        self.has_entity = has_entity
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, str, dict]] = []
        self.visible: Optional[set[str]] = None   # CSurveyResponse ids this caller may read

    def add(self, entity: str, row: dict) -> dict:
        row = dict(row)
        row.setdefault("id", uuid.uuid4().hex[:17])
        self.data.setdefault(entity, {})[row["id"]] = row
        return row

    async def metadata(self, key: str):
        if key.startswith("entityDefs.CSurveyResponse"):
            if not self.has_entity:
                return None
            if key.endswith(".moment"):
                return {"type": "enum", "options": ["", "Engagement Closed", "Session Milestone",
                                                    "Event", "Evaluation Released", "On Demand"]}
            return {"recommendScore": {"type": "int"}}
        return None

    def _rows(self, entity):
        rows = list(self.data.get(entity, {}).values())
        if entity == "CSurveyResponse" and self.visible is not None:
            rows = [r for r in rows if r["id"] in self.visible]
        return rows

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        assert max_size <= 200, "a page above 200 is a 403"
        rows = [r for r in self._rows(entity) if all(_match(r, c) for c in where or [])]
        if order_by:
            rows.sort(key=lambda r: str(r.get(order_by) or ""), reverse=order == "desc")
        return {"total": len(rows), "list": copy.deepcopy(rows[offset:offset + max_size])}

    async def get(self, entity, record_id, select=None):
        row = self.data.get(entity, {}).get(record_id)
        if row is None:
            raise EspoError(f"404 {entity} {record_id}")
        if entity == "CSurveyResponse" and self.visible is not None and record_id not in self.visible:
            raise EspoError(f"403 {entity} {record_id}")
        return copy.deepcopy(row)

    async def create(self, entity, payload):
        row = self.add(entity, payload)
        self.created.append((entity, copy.deepcopy(payload)))
        return copy.deepcopy(row)

    async def update(self, entity, record_id, payload):
        self.data[entity][record_id].update(payload)
        self.updated.append((entity, record_id, copy.deepcopy(payload)))
        return copy.deepcopy(self.data[entity][record_id])

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        ids = self.links.get((entity, record_id, link), [])
        rows = []
        for rid in ids:
            for ent in self.data.values():
                if rid in ent:
                    rows.append(copy.deepcopy(ent[rid]))
        return {"total": len(rows), "list": rows}


class Outbox:
    def __init__(self, fail: bool = False):
        self.sent: list[dict] = []
        self.fail = fail

    async def __call__(self, settings, to, subject, body):
        if self.fail:
            raise RuntimeError("Gmail said no")
        self.sent.append({"to": list(to), "subject": subject, "body": body})


def settings(**kw) -> Any:
    base = dict(
        feedback_surveys=True, feedback_link_days=30, feedback_quiet_days=30,
        feedback_lookback_days=7, feedback_session_count=3, feedback_on_close=True,
        feedback_on_sessions=True, feedback_on_event=True, feedback_on_evaluation=True,
        ops_mailbox="info@example.org", organization_name="Example Mentors",
        sender_display_name="Example Mentors", app_base_url="https://apps.example.org",
        mentor_email_domain="example-mentors.org", sms_timezone="America/New_York",
        mentor_admin_allowed_teams_list=["Mentor Administration Team"],
        ops_allowed_teams_list=["Marketing Admin Team"], alert_email_to_list=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)
