"""The Business Evaluation store against a real Postgres (migration 0044): a
link and its answer rows, consent recorded once, saves refused once a survey
is submitted, a repeated submit returning the first, the delivery bookkeeping
and the due query. Runs only when TEST_DATABASE_URL is set (same Postgres as
test_store_pg.py), migrated to head. Also checks the migration and the store
declare the same columns, which needs no database."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from evaluation.store import WEB_GRACE, evaluation_answer, evaluation_link

_URL = os.environ.get("TEST_DATABASE_URL")
_MIGRATION = Path(__file__).resolve().parents[1] / "alembic/versions/0044_evaluation_links.py"
T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def _migrated_columns(table: str) -> set[str]:
    src = _MIGRATION.read_text(encoding="utf-8").split("def downgrade", 1)[0]
    block = src.split(f'"{table}",', 1)[1].split("op.create_index", 1)[0]
    return set(re.findall(r'sa\.Column\("(\w+)"', block))


def test_the_migration_and_the_store_declare_the_same_columns():
    assert _migrated_columns("evaluation_link") == {c.name for c in evaluation_link.columns}
    assert _migrated_columns("evaluation_answer") == {c.name for c in evaluation_answer.columns}


needs_pg = pytest.mark.skipif(not _URL, reason="set TEST_DATABASE_URL to run")


@pytest.fixture
async def store():
    from evaluation.store import EvaluationStore

    s = EvaluationStore(_URL)
    async with s._engine.begin() as conn:
        await conn.execute(text("delete from evaluation_answer"))
        await conn.execute(text("delete from evaluation_link"))
    yield s
    await s.dispose()


async def _link(store):
    return await store.create_link(
        engagement_id="E1", client_profile_id="CP1", round_no=1, area_keys=["finance"],
        profile_needed=True, company_name="Quarry Street Coffee", created_by="t", days=30,
        surveys=[("business-profile", "business-profile.v1", None), ("finance", "finance.v1", "BE1")],
        now=T0)


@needs_pg
async def test_a_link_and_its_rows(store):
    link = await _link(store)
    assert len(link["token"]) == 32
    assert link["expires_at"] == T0 + timedelta(days=30)
    got = await store.link_by_token(link["token"])
    assert got["area_keys"] == ["finance"] and got["company_name"] == "Quarry Street Coffee"
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
