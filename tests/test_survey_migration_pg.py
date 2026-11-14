"""Migration 0047 (the survey engine, ruling BE23) up and down on tables that
hold rows, as production's do. Runs only when TEST_DATABASE_URL is set: it
makes a scratch database beside that one, migrates it to 0046, writes a
Business Evaluation link and its answers in the old layout, upgrades, checks
every value landed in the new layout, downgrades, checks every value came
back, and drops the scratch database."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

asyncpg = pytest.importorskip("asyncpg")

_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
SCRATCH = "cbm_survey_migration_test"
T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


def _plain(url: str, database: str | None = None) -> str:
    parts = urlsplit(url.replace("postgresql+asyncpg://", "postgresql://"))
    path = f"/{database}" if database else parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    done = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-2000:]


@pytest.fixture
async def scratch():
    admin = await asyncpg.connect(_plain(_URL))
    await admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
    await admin.execute(f"CREATE DATABASE {SCRATCH}")
    url = _plain(_URL, SCRATCH)
    try:
        yield url
    finally:
        await admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        await admin.close()


async def _one(url: str, sql: str, *args):
    conn = await asyncpg.connect(url)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


async def test_0047_up_and_down_on_tables_with_rows(scratch):
    _alembic(scratch, "upgrade", "0046_integration_fix_plan")
    conn = await asyncpg.connect(scratch)
    try:
        await conn.execute(
            "INSERT INTO evaluation_link (id, token, engagement_id, client_profile_id, round, "
            "area_keys, profile_needed, company_name, consent_at, created_by, created_at, "
            "expires_at, replaced_at) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, "
            "$11, $12, NULL)",
            "L1", "tok-1", "ENG1", "CP1", 2, json.dumps(["finance", "marketing"]), False,
            "Quarry Street Coffee", T0, "joe.mentor", T0, T0 + timedelta(days=30))
        await conn.execute(
            "INSERT INTO evaluation_answer (id, link_id, survey_key, survey_version, answers, "
            "crm_record_id, attempts) VALUES ($1, $2, $3, $4, $5::jsonb, $6, 0)",
            "A1", "L1", "finance", "finance.v1", json.dumps({"budget": "No"}), "BE1")
    finally:
        await conn.close()

    _alembic(scratch, "upgrade", "0047_survey_engine")
    [link] = await _one(scratch, "SELECT * FROM survey_link")
    assert (link["purpose"], link["entity_type"], link["record_id"]) == (
        "business-evaluation", "CEngagement", "ENG1")
    assert json.loads(link["data"]) == {"client_profile_id": "CP1", "round": 2,
                                        "area_keys": ["finance", "marketing"],
                                        "profile_needed": False}
    assert link["display_name"] == "Quarry Street Coffee" and link["token"] == "tok-1"
    assert link["consent_at"] == T0 and link["created_by"] == "joe.mentor"
    assert "engagement_id" not in link.keys()
    [answer] = await _one(scratch, "SELECT * FROM survey_answer")
    assert answer["link_id"] == "L1" and json.loads(answer["answers"]) == {"budget": "No"}
    names = {r["conname"] for r in await _one(
        scratch, "SELECT conname FROM pg_constraint WHERE conrelid IN "
                 "('survey_link'::regclass, 'survey_answer'::regclass)")}
    assert names == {"survey_link_pkey", "uq_survey_link_token", "survey_answer_pkey",
                     "uq_survey_answer_link_survey"}
    indexes = {r["indexname"] for r in await _one(
        scratch, "SELECT indexname FROM pg_indexes WHERE tablename IN ('survey_link', 'survey_answer')")}
    assert {"ix_survey_link_record", "ix_survey_answer_due"} <= indexes

    # A link of another purpose, which the old layout cannot hold.
    conn = await asyncpg.connect(scratch)
    try:
        await conn.execute(
            "INSERT INTO survey_link (id, token, purpose, entity_type, record_id, data, "
            "created_at, expires_at) VALUES ('L2', 'tok-2', 'event-feedback', 'CEvent', 'EV1', "
            "'{}'::jsonb, $1, $2)", T0, T0 + timedelta(days=30))
        await conn.execute(
            "INSERT INTO survey_answer (id, link_id, survey_key, survey_version, answers, "
            "attempts) VALUES ('A2', 'L2', 'feedback', 'feedback.v1', '{}'::jsonb, 0)")
    finally:
        await conn.close()

    _alembic(scratch, "downgrade", "0046_integration_fix_plan")
    [old] = await _one(scratch, "SELECT * FROM evaluation_link")
    assert (old["id"], old["token"], old["engagement_id"], old["client_profile_id"]) == (
        "L1", "tok-1", "ENG1", "CP1")
    assert old["round"] == 2 and json.loads(old["area_keys"]) == ["finance", "marketing"]
    assert old["profile_needed"] is False and old["company_name"] == "Quarry Street Coffee"
    assert "purpose" not in old.keys()
    [answer] = await _one(scratch, "SELECT * FROM evaluation_answer")
    assert answer["id"] == "A1" and json.loads(answer["answers"]) == {"budget": "No"}
    names = {r["conname"] for r in await _one(
        scratch, "SELECT conname FROM pg_constraint WHERE conrelid IN "
                 "('evaluation_link'::regclass, 'evaluation_answer'::regclass)")}
    assert names == {"evaluation_link_pkey", "uq_evaluation_link_token",
                     "evaluation_answer_pkey", "uq_evaluation_answer_link_survey"}
    indexes = {r["indexname"] for r in await _one(
        scratch, "SELECT indexname FROM pg_indexes WHERE tablename IN "
                 "('evaluation_link', 'evaluation_answer')")}
    assert {"ix_evaluation_link_engagement", "ix_evaluation_answer_due"} <= indexes

    # And up again, as a redeploy after a rollback would.
    _alembic(scratch, "upgrade", "0047_survey_engine")
    assert len(await _one(scratch, "SELECT id FROM survey_link")) == 1
