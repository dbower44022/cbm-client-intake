"""Mentor login integrity, step 4b (prds/mentor-login-integrity-plan.md § 4.2):
the integrity digest, the fault list and acknowledging in Mentor
Administration, and the badge on its portal tile — all behind
INTEGRITY_DIGEST, the switch Doug turns on per instance after reading its
report-only backlog."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import Settings, get_settings
from forms import info_request, volunteer
from integrity import digest
from tests.test_attention import FakeEspo, _login, _user

T0 = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def _row(rid, cond, summary, *, notified=None, ack=None, mentors=None):
    return {"id": rid, "fault_key": f"{cond}:{rid}", "condition": cond, "summary": summary,
            "mentors": mentors if mentors is not None else [{"id": "MP-" + rid, "name": "M " + rid}],
            "login": {"id": "u", "userName": "x@y"}, "first_seen": T0, "last_seen": T0,
            "closed_at": None, "notified_at": notified, "ack_at": ack,
            "ack_by": "Sue" if ack else None, "ack_note": "on it" if ack else None}


class Store:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.notified: list[str] = []
        self.acked: list[tuple] = []

    async def mark_notified(self, ids, now=None):
        self.notified.extend(ids)

    async def open_faults(self):
        return self.rows

    async def open_count(self, unacknowledged=True):
        return sum(1 for r in self.rows if not (unacknowledged and r["ack_at"]))

    async def acknowledge(self, fid, *, by_id, by, note, now=None):
        for r in self.rows:
            if r["id"] == fid:
                r.update(ack_at=T0, ack_by=by, ack_note=note)
                self.acked.append((fid, by, note))
                return r
        return None


# --- the digest ----------------------------------------------------------------

async def test_the_digest_lists_open_faults_marks_new_and_skips_acknowledged():
    s = Settings(app_base_url="https://apps.example.org/", alert_email_to="ops@x.org",
                 integrity_digest_to="staff@x.org")
    rows = [_row("a", 1, "The login doug is on 2 mentor profiles."),
            _row("b", 4, "Jane is Active but has no login.", notified=T0),
            _row("c", 6, "Acked one.", ack=T0)]
    store, sent = Store(), []

    async def send(to, subject, text):
        sent.append((to, subject, text))

    ok = await digest.send_integrity_digest(
        s, store, {"open": rows, "new": [rows[0]], "closed": [_row("z", 2, "gone")]}, send=send)
    assert ok and len(sent) == 1
    to, subject, text = sent[0]
    assert to == ["staff@x.org"]
    assert "Login integrity: 2 open faults, 1 new" in subject
    assert "NEW · The login doug is on 2 mentor profiles." in text
    assert "  Jane is Active but has no login." in text and "NEW · Jane" not in text
    assert "Acked one." not in text and "Acknowledged and not listed: 1." in text
    assert "Fixed since the last check: 1." in text
    assert "https://apps.example.org/mentoradmin/?mentor=MP-a" in text
    assert "https://apps.example.org/mentoradmin/?faults=1" in text
    assert store.notified == ["a"]  # only the new one is stamped


async def test_no_email_when_nothing_is_open_or_no_recipient():
    sent = []

    async def send(*a):
        sent.append(a)

    s = Settings(alert_email_to="ops@x.org")
    assert not await digest.send_integrity_digest(
        s, Store(), {"open": [_row("c", 6, "x", ack=T0)], "closed": []}, send=send)
    assert not await digest.send_integrity_digest(
        Settings(), Store(), {"open": [_row("a", 1, "x")], "closed": []}, send=send)
    assert sent == []


async def test_the_daily_run_sends_the_digest_only_with_its_switch_on():
    from tests.test_integrity_check import FakeCrm, FakeStore, TEAMS, _snap
    from integrity import run

    sent = []

    async def send(to, subject, text):
        sent.append(subject)

    on = Settings(integrity_digest=True, alert_email_to="ops@x.org")
    store = FakeStore()
    store.mark_notified = Store().mark_notified
    await run.run_integrity_check(Settings(alert_email_to="ops@x.org"), FakeCrm(_snap(), TEAMS),
                                  store, send=send)
    assert sent == []
    await run.run_integrity_check(on, FakeCrm(_snap(), TEAMS), store, send=send)
    assert len(sent) == 1 and "4 open faults" in sent[0]


# --- the fault list in Mentor Administration ------------------------------------

_USER = {"userId": "u1", "userName": "boss", "name": "Mentor Boss", "isAdmin": True, "token": "tok"}


def _app(monkeypatch, store, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("integrity.store.get_store", lambda settings: store)
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())
    return create_app([info_request.SPEC])


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_list_is_off_until_the_switch(monkeypatch):
    with TestClient(_app(monkeypatch, Store([_row("a", 1, "x")]))) as c:
        assert c.get("/mentoradmin/api/session").json()["integrityFaults"] is False
        r = c.get("/mentoradmin/api/integrity/faults")
    assert r.status_code == 404 and "INTEGRITY_DIGEST" in r.json()["detail"]


def test_the_list_and_acknowledging(monkeypatch):
    logged = []

    async def fake_log(**kw):
        logged.append(kw)
        return True

    monkeypatch.setattr("mentoradmin.router.action_log.log_action", fake_log)
    store = Store([_row("a", 1, "The login doug is on 2 mentor profiles.")])
    with TestClient(_app(monkeypatch, store, INTEGRITY_DIGEST="true")) as c:
        assert c.get("/mentoradmin/api/session").json()["integrityFaults"] is True
        faults = c.get("/mentoradmin/api/integrity/faults").json()["faults"]
        assert faults[0]["conditionLabel"] == "One login on several mentor profiles"
        assert faults[0]["isNew"] and faults[0]["acknowledged"] is None
        assert faults[0]["mentors"] == [{"id": "MP-a", "name": "M a"}]

        r = c.post("/mentoradmin/api/integrity/faults/a/acknowledge", json={"note": "  "})
        assert r.status_code == 400 and "Write a note" in r.json()["detail"]
        r = c.post("/mentoradmin/api/integrity/faults/a/acknowledge",
                   json={"note": "Repair booked with Milt"})
        assert r.status_code == 200
        assert r.json()["fault"]["acknowledged"]["by"] == "Mentor Boss"
        r = c.post("/mentoradmin/api/integrity/faults/zzz/acknowledge", json={"note": "x"})
        assert r.status_code == 404 and "no longer open" in r.json()["detail"]
    assert store.acked == [("a", "Mentor Boss", "Repair booked with Milt")]
    assert len(logged) == 1
    entry = logged[0]
    assert entry["action"] == "Login Fault Acknowledged"
    assert entry["parent_type"] == "CMentorProfile" and entry["parent_id"] == "MP-a"
    assert "Repair booked with Milt" in entry["summary"]


# --- the portal badge -------------------------------------------------------------

def _portal(monkeypatch, store, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("integrity.store.get_store", lambda settings: store)
    monkeypatch.setattr("portal.router.client_for", lambda settings, user: FakeEspo())
    return create_app([info_request.SPEC, volunteer.SPEC])


def test_the_badge_counts_unacknowledged_faults_for_mentor_administration(monkeypatch):
    store = Store([_row("a", 1, "x"), _row("b", 2, "y"), _row("c", 6, "z", ack=T0)])
    with TestClient(_portal(monkeypatch, store, INTEGRITY_DIGEST="true")) as c:
        _login(monkeypatch, c, _user(teams=["Mentor Administration Team"]))
        items = c.get("/api/portal/attention").json()["items"]
    fault = [i for i in items if i.get("kind") == "fault"]
    assert fault == [{"url": "/mentoradmin/", "kind": "fault", "count": 2,
                      "label": "Login faults to look at"}]
    assert any(i["url"] == "/mentoradmin/" and "kind" not in i for i in items)


def test_no_badge_with_the_switch_off_or_off_the_team(monkeypatch):
    store = Store([_row("a", 1, "x")])
    with TestClient(_portal(monkeypatch, store)) as c:
        _login(monkeypatch, c, _user(teams=["Mentor Administration Team"]))
        assert not [i for i in c.get("/api/portal/attention").json()["items"] if i.get("kind")]
    with TestClient(_portal(monkeypatch, store, INTEGRITY_DIGEST="true")) as c:
        _login(monkeypatch, c, _user(teams=["Mentor Team"]))
        assert not [i for i in c.get("/api/portal/attention").json()["items"] if i.get("kind")]
