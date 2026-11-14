"""The survey engine's store against a real Postgres (migrations 0044 and
0047): a link and its answer rows, consent recorded once, saves refused once
a survey is submitted, a repeated submit returning the first, the delivery
bookkeeping, the due query, Resend and Expire. Runs only when
TEST_DATABASE_URL is set (same Postgres as test_store_pg.py), migrated to
head. Also checks the migrations and the store declare the same columns,
which needs no database. The migration itself, up and down on tables with
rows: ``tests/test_survey_migration_pg.py``."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from datetime import timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from surveys.store import WEB_GRACE, survey_answer, survey_link

_URL = os.environ.get("TEST_DATABASE_URL")
_VERSIONS = Path(__file__).resolve().parents[1] / "alembic/versions"
T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def _created_columns(table: str) -> set[str]:
    src = (_VERSIONS / "0044_evaluation_links.py").read_text(encoding="utf-8")
    src = src.split("def downgrade", 1)[0]
    block = src.split(f'"{table}",', 1)[1].split("op.create_index", 1)[0]
    return set(re.findall(r'sa\.Column\("(\w+)"', block))


def _engine_columns() -> set[str]:
    """survey_link as 0044 made it, with 0047's columns added and dropped."""
    src = (_VERSIONS / "0047_survey_engine.py").read_text(encoding="utf-8")
    up = src.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    added = set(re.findall(r'op\.add_column\("survey_link", sa\.Column\("(\w+)"', up))
    dropped_block = up.split("for column in (", 2)[2].split(")", 1)[0]
    dropped = set(re.findall(r'"(\w+)"', dropped_block))
    return (_created_columns("evaluation_link") - dropped) | added


def test_the_migrations_and_the_store_declare_the_same_columns():
    assert _engine_columns() == {c.name for c in survey_link.columns}
    assert _created_columns("evaluation_answer") == {c.name for c in survey_answer.columns}


needs_pg = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


@pytest.fixture
async def store():
    from surveys.store import SurveyStore

    s = SurveyStore(_URL)
    async with s._engine.begin() as conn:
        await conn.execute(text("delete from survey_answer"))
        await conn.execute(text("delete from survey_link"))
    yield s
    await s.dispose()


async def _link(store):
    return await store.create_link(
        purpose="business-evaluation", entity_type="CEngagement", record_id="E1",
        data={"client_profile_id": "CP1", "round": 1, "area_keys": ["finance"],
              "profile_needed": True},
        display_name="Quarry Street Coffee", created_by="t", days=30,
        surveys=[("business-profile", "business-profile.v1", None), ("finance", "finance.v1", "BE1")],
        now=T0)


@needs_pg
async def test_a_link_and_its_rows(store):
    link = await _link(store)
    assert len(link["token"]) == 32
    assert link["expires_at"] == T0 + timedelta(days=30)
    got = await store.link_by_token(link["token"])
    assert got["data"]["area_keys"] == ["finance"] and got["display_name"] == "Quarry Street Coffee"
    assert (got["purpose"], got["entity_type"], got["record_id"]) == (
        "business-evaluation", "CEngagement", "E1")
    rows = {r["survey_key"]: r for r in await store.answers_for(link["id"])}
    assert set(rows) == {"business-profile", "finance"}
    assert rows["finance"]["crm_record_id"] == "BE1" and rows["finance"]["answers"] == {}
    assert await store.link_by_token("nope") is None


@needs_pg
async def test_consent_is_recorded_once(store):
    link = await _link(store)
    assert await store.set_consent(link["id"], T0) == T0
    assert await store.set_consent(link["id"], T0 + timedelta(hours=1)) == T0


@needs_pg
async def test_save_submit_and_delivery(store):
    link = await _link(store)
    saved = await store.save_answers(link["id"], "finance", {"budget": "No"}, T0)
    assert saved["answers"] == {"budget": "No"}
    assert await store.mark_started(saved["id"], T0) is True
    assert await store.mark_started(saved["id"], T0) is False

    first = await store.submit(link["id"], "finance", {"budget": "Yes"}, "s1", T0)
    assert first["submitted_at"] == T0 and first["next_attempt_at"] == T0 + WEB_GRACE
    again = await store.submit(link["id"], "finance", {"budget": "No"}, "s2", T0 + timedelta(minutes=1))
    assert again["submission_token"] == "s1" and again["answers"] == {"budget": "Yes"}
    assert await store.save_answers(link["id"], "finance", {"budget": "No"}, T0) is None
    assert await store.submit(link["id"], "funding", {}, "s3", T0) is None

    assert await store.due(T0) == []
    assert [r["id"] for r in await store.due(T0 + WEB_GRACE)] == [first["id"]]
    await store.mark_failed(first["id"], "HTTP 503", T0 + timedelta(hours=1))
    assert await store.due(T0 + WEB_GRACE) == []
    await store.mark_delivered(first["id"], T0 + timedelta(hours=1))
    row = next(r for r in await store.answers_for(link["id"]) if r["survey_key"] == "finance")
    assert row["delivered_at"] and row["attempts"] == 2 and row["delivery_error"] is None
    assert await store.due(T0 + timedelta(days=1)) == []


@needs_pg
async def test_resend_moves_the_answers_and_consent_and_ends_the_old_link(store):
    old = await _link(store)
    await store.set_consent(old["id"], T0)
    await store.save_answers(old["id"], "finance", {"q": 1}, T0)
    new = await store.replace_link(await store.link_by_id(old["id"]), created_by="t", days=30,
                                   now=T0 + timedelta(days=1))
    assert new["token"] != old["token"] and new["data"]["round"] == 1 and new["consent_at"] == T0
    assert new["purpose"] == "business-evaluation" and new["record_id"] == "E1"
    assert (await store.link_by_id(old["id"]))["replaced_at"] == T0 + timedelta(days=1)
    rows = {r["survey_key"]: r for r in await store.answers_for(new["id"])}
    assert rows["finance"]["answers"] == {"q": 1}
    assert await store.answers_for(old["id"]) == []
    links = await store.links_for_record("business-evaluation", "CEngagement", "E1")
    assert [l["id"] for l in links] == [old["id"], new["id"]]
    assert await store.links_for_record("another-purpose", "CEngagement", "E1") == []


@needs_pg
async def test_expire_ends_a_link_once(store):
    link = await _link(store)
    assert await store.end_link(link["id"], T0) is True
    assert await store.end_link(link["id"], T0 + timedelta(hours=1)) is False
    assert (await store.link_by_id(link["id"]))["replaced_at"] == T0
