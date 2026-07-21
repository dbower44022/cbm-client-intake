"""core.action_log — the dual-write action-history helper (plan §4)."""

from __future__ import annotations

import pytest

from core import action_log


class FakeEspo:
    def __init__(self, scopes_has=True, fail_create=False):
        self.created: list[tuple[str, dict]] = []
        self._scopes_has = scopes_has
        self._fail_create = fail_create

    async def metadata(self, key):
        if key == "scopes":
            return {"CActionLog": {}, "Contact": {}} if self._scopes_has else {"Contact": {}}
        return {}

    async def create(self, entity, payload):
        if self._fail_create:
            raise RuntimeError("boom")
        self.created.append((entity, payload))
        return {"id": "log1"}


@pytest.fixture(autouse=True)
def _clear_cache():
    action_log._exists_cache.clear()
    yield
    action_log._exists_cache.clear()


@pytest.mark.anyio
async def test_log_action_writes_a_row_when_entity_exists(monkeypatch):
    fake = FakeEspo(scopes_has=True)
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: fake)
    ok = await action_log.log_action(
        app=action_log.APP_CLIENT_ADMIN, category=action_log.CAT_ASSIGNMENT,
        action=action_log.ACT_MENTOR_ASSIGNED, parent_type="CEngagement",
        parent_id="E1", summary="Mentor assigned: Jane.",
        actor_id="u1", actor_name="Bob Staff", details={"n": 3},
    )
    assert ok is True
    assert len(fake.created) == 1
    entity, payload = fake.created[0]
    assert entity == "CActionLog"
    assert payload["actionType"] == "Mentor Assigned"      # free-text verb, verbatim
    assert payload["category"] == "Assignment"
    assert payload["app"] == "Client Administration"
    assert payload["parentType"] == "CEngagement" and payload["parentId"] == "E1"
    assert payload["actorId"] == "u1" and payload["actorName"] == "Bob Staff"
    assert '"n": 3' in payload["details"]                  # details serialized to JSON
    assert payload["outcome"] == "Success"


@pytest.mark.anyio
async def test_log_action_skipped_silently_until_entity_is_built(monkeypatch):
    fake = FakeEspo(scopes_has=False)  # CActionLog not in the CRM yet
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: fake)
    ok = await action_log.log_action(
        app=action_log.APP_MENTOR_ADMIN, category=action_log.CAT_PROVISIONING,
        action=action_log.ACT_LOGIN_PROVISIONED, parent_type="CMentorProfile",
        parent_id="M1", summary="Login created.",
    )
    assert ok is False
    assert fake.created == []  # no write attempted


@pytest.mark.anyio
async def test_log_action_is_best_effort_on_write_failure(monkeypatch):
    fake = FakeEspo(scopes_has=True, fail_create=True)
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: fake)
    ok = await action_log.log_action(
        app=action_log.APP_CLIENT_ADMIN, category=action_log.CAT_ASSIGNMENT,
        action="Some Brand New Action", parent_type="CEngagement", parent_id="E1",
        summary="x",
    )
    assert ok is False  # swallowed, never raised


@pytest.mark.anyio
async def test_log_action_no_client_in_dry_run(monkeypatch):
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: None)
    ok = await action_log.log_action(
        app=action_log.APP_INTAKE, category=action_log.CAT_INTAKE,
        action=action_log.ACT_MENTOR_ASSIGNED, parent_type="X", parent_id="1",
        summary="x",
    )
    assert ok is False


@pytest.mark.anyio
async def test_entity_probe_cached_false_rechecks(monkeypatch):
    """A False probe result re-checks after the TTL so the log activates once
    the CRM entity is built, without a metadata GET per action."""
    calls = {"n": 0}

    class Probe(FakeEspo):
        async def metadata(self, key):
            calls["n"] += 1
            return await super().metadata(key)

    fake = Probe(scopes_has=False)
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: fake)
    await action_log.log_action(app="a", category="c", action="x",
                                parent_type="P", parent_id="1", summary="s")
    await action_log.log_action(app="a", category="c", action="x",
                                parent_type="P", parent_id="1", summary="s")
    assert calls["n"] == 1  # second call used the cached False, no re-probe


@pytest.mark.anyio
async def test_record_action_posts_note_and_logs(monkeypatch):
    user_client = FakeEspo(scopes_has=True)   # receives the Note (as the user)
    api_client = FakeEspo(scopes_has=True)    # receives the CActionLog row
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: api_client)
    await action_log.record_action(
        user_client, app=action_log.APP_MENTOR_ADMIN,
        category=action_log.CAT_PROVISIONING, action=action_log.ACT_LOGIN_PROVISIONED,
        parent_type="CMentorProfile", parent_id="M1",
        summary="Login created (jane@cbmentors.org).", actor_name="Bob Staff",
    )
    # Stream note posted as the user, with [App] … · by Actor decoration.
    notes = [p for e, p in user_client.created if e == "Note"]
    assert len(notes) == 1
    assert notes[0]["type"] == "Post" and notes[0]["parentId"] == "M1"
    assert notes[0]["post"] == "[Mentor Administration] Login created (jane@cbmentors.org). · by Bob Staff"
    # CActionLog row written via the API-key client.
    logs = [p for e, p in api_client.created if e == "CActionLog"]
    assert len(logs) == 1 and logs[0]["actionType"] == "Login Provisioned"


@pytest.mark.anyio
async def test_record_action_custom_note_text_preserved(monkeypatch):
    user_client = FakeEspo(scopes_has=True)
    monkeypatch.setattr(action_log, "_actionlog_client", lambda: FakeEspo())
    await action_log.record_action(
        user_client, app=action_log.APP_CLIENT_ADMIN, category=action_log.CAT_ASSIGNMENT,
        action=action_log.ACT_MENTOR_REASSIGNED, parent_type="CEngagement",
        parent_id="E1", summary="ignored for note", note="Mentor X replaced with Y by Bob.",
    )
    notes = [p for e, p in user_client.created if e == "Note"]
    assert notes[0]["post"] == "Mentor X replaced with Y by Bob."
