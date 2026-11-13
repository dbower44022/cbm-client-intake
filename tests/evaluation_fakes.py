"""In-memory twin of ``evaluation/store.EvaluationStore`` for the Business
Evaluation tests. ``tests/test_evaluation_store_pg.py`` runs the real store;
every other test uses this, which keeps the same contract."""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone

from evaluation.store import WEB_GRACE, new_token


class MemoryStore:
    """In-memory twin of EvaluationStore."""

    def __init__(self):
        self.links: dict[str, dict] = {}
        self.rows: dict[str, dict] = {}

    async def create_link(self, *, engagement_id, client_profile_id, round_no, area_keys,
                          profile_needed, company_name, created_by, days, surveys, now=None):
        now = now or datetime.now(timezone.utc)
        link = {"id": str(uuid.uuid4()), "token": new_token(), "engagement_id": engagement_id,
                "client_profile_id": client_profile_id, "round": round_no,
                "area_keys": list(area_keys), "profile_needed": profile_needed,
                "company_name": company_name, "consent_at": None, "created_by": created_by,
                "created_at": now, "expires_at": now + timedelta(days=days), "replaced_at": None}
        self.links[link["id"]] = link
        for key, version, record_id in surveys:
            rid = str(uuid.uuid4())
            self.rows[rid] = {"id": rid, "link_id": link["id"], "survey_key": key,
                              "survey_version": version, "answers": {}, "updated_at": None,
                              "submitted_at": None, "submission_token": None,
                              "crm_record_id": record_id, "crm_started_at": None,
                              "delivered_at": None, "delivery_error": None, "attempts": 0,
                              "next_attempt_at": None}
        return copy.deepcopy(link)

    async def link_by_token(self, token):
        return next((copy.deepcopy(l) for l in self.links.values() if l["token"] == token), None)

    async def link_by_id(self, link_id):
        return copy.deepcopy(self.links.get(link_id))

    async def links_for_engagement(self, engagement_id):
        return sorted((copy.deepcopy(l) for l in self.links.values()
                       if l["engagement_id"] == engagement_id), key=lambda l: l["created_at"])

    async def end_link(self, link_id, at):
        link = self.links[link_id]
        if link["replaced_at"]:
            return False
        link["replaced_at"] = at
        return True

    async def replace_link(self, old, *, created_by, days, now=None):
        now = now or datetime.now(timezone.utc)
        link = {"id": str(uuid.uuid4()), "token": new_token(), "engagement_id": old["engagement_id"],
                "client_profile_id": old["client_profile_id"], "round": old["round"],
                "area_keys": list(old["area_keys"]), "profile_needed": old["profile_needed"],
                "company_name": old.get("company_name"), "consent_at": old.get("consent_at"),
                "created_by": created_by, "created_at": now,
                "expires_at": now + timedelta(days=days), "replaced_at": None}
        self.links[link["id"]] = link
        for row in self.rows.values():
            if row["link_id"] == old["id"]:
                row["link_id"] = link["id"]
        if not self.links[old["id"]]["replaced_at"]:
            self.links[old["id"]]["replaced_at"] = now
        return copy.deepcopy(link)

    async def set_consent(self, link_id, at):
        link = self.links[link_id]
        link["consent_at"] = link["consent_at"] or at
        return link["consent_at"]

    async def answers_for(self, link_id):
        return [copy.deepcopy(r) for r in self.rows.values() if r["link_id"] == link_id]

    def _row(self, link_id, key):
        return next((r for r in self.rows.values()
                     if r["link_id"] == link_id and r["survey_key"] == key), None)

    async def save_answers(self, link_id, key, answers, at):
        row = self._row(link_id, key)
        if row is None or row["submitted_at"]:
            return None
        row.update(answers=copy.deepcopy(answers), updated_at=at)
        return copy.deepcopy(row)

    async def submit(self, link_id, key, answers, token, at):
        row = self._row(link_id, key)
        if row is None:
            return None
        if not row["submitted_at"]:
            row.update(answers=copy.deepcopy(answers), updated_at=at, submitted_at=at,
                       submission_token=token, next_attempt_at=at + WEB_GRACE)
        return copy.deepcopy(row)

    async def mark_started(self, answer_id, at):
        row = self.rows[answer_id]
        if row["crm_started_at"]:
            return False
        row["crm_started_at"] = at
        return True

    async def mark_delivered(self, answer_id, at):
        self.rows[answer_id].update(delivered_at=at, delivery_error=None, next_attempt_at=None,
                                    attempts=self.rows[answer_id]["attempts"] + 1)

    async def mark_failed(self, answer_id, error, retry_at):
        self.rows[answer_id].update(delivery_error=error, next_attempt_at=retry_at,
                                    attempts=self.rows[answer_id]["attempts"] + 1)

    async def due(self, now, limit=50):
        return [copy.deepcopy(r) for r in self.rows.values()
                if r["submitted_at"] and not r["delivered_at"] and r["next_attempt_at"] <= now]
