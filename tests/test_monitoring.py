"""V2 Phase 3: alerting thresholds + CRM schema-drift detection."""

from __future__ import annotations

from datetime import datetime, timezone

from core.config import Settings
from core.monitoring import run_alert_check, run_schema_drift_check

_NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def _settings(**over):
    base = dict(
        alert_needs_attention_threshold=1,
        alert_pending_age_minutes=30,
        alert_cooldown_seconds=3600,
    )
    base.update(over)
    return Settings(**base)


class FakeMetricsStore:
    def __init__(self, metrics):
        self._metrics = metrics

    async def metrics(self):
        return self._metrics


def _collector():
    sent = []

    async def send(text):
        sent.append(text)

    return sent, send


# --- alerting ---------------------------------------------------------------

async def test_alerts_on_needs_attention():
    sent, send = _collector()
    store = FakeMetricsStore({"needsAttention": 3, "oldestPendingAgeSeconds": None})
    await run_alert_check(store, _settings(), {}, now=_NOW, send=send)
    assert any("need attention" in t for t in sent)


async def test_alerts_on_backlog_age():
    sent, send = _collector()
    store = FakeMetricsStore({"needsAttention": 0, "oldestPendingAgeSeconds": 60 * 60})
    await run_alert_check(store, _settings(), {}, now=_NOW, send=send)
    assert any("backlog" in t.lower() for t in sent)


async def test_no_alert_when_healthy():
    sent, send = _collector()
    store = FakeMetricsStore({"needsAttention": 0, "oldestPendingAgeSeconds": 30})
    await run_alert_check(store, _settings(), {}, now=_NOW, send=send)
    assert sent == []


async def test_alert_cooldown_suppresses_repeat():
    sent, send = _collector()
    store = FakeMetricsStore({"needsAttention": 2, "oldestPendingAgeSeconds": None})
    state: dict = {}
    await run_alert_check(store, _settings(), state, now=_NOW, send=send)
    await run_alert_check(store, _settings(), state, now=_NOW, send=send)  # same window
    assert len(sent) == 1


async def test_alerts_on_stranded_rows():
    """P1-6: a lease-expired processing row (dead worker mid-delivery) alerts."""
    sent, send = _collector()
    store = FakeMetricsStore(
        {"needsAttention": 0, "oldestPendingAgeSeconds": None, "stranded": 2}
    )
    await run_alert_check(store, _settings(), {}, now=_NOW, send=send)
    assert any("stranded" in t.lower() for t in sent)


async def test_no_stranded_alert_when_zero():
    sent, send = _collector()
    store = FakeMetricsStore(
        {"needsAttention": 0, "oldestPendingAgeSeconds": None, "stranded": 0}
    )
    await run_alert_check(store, _settings(), {}, now=_NOW, send=send)
    assert sent == []


# --- schema drift -----------------------------------------------------------

def _full_options(entity, field):
    # A superset that satisfies every EXPECTED_ENUMS entry (derived from the
    # contract so it stays aligned as fields are added).
    from core.schema_contract import EXPECTED_ENUMS

    superset: set[str] = set()
    for values in EXPECTED_ENUMS.values():
        superset.update(values)
    return sorted(superset)


async def test_schema_drift_alerts_on_missing_value():
    sent, send = _collector()

    async def fetch(entity, field):
        if (entity, field) == ("CEngagement", "engagementStatus"):
            return ["Submitted"]  # "Pending Acceptance" removed
        return _full_options(entity, field)

    s = _settings(espo_dry_run=False, espo_api_key="k")
    await run_schema_drift_check(s, {}, now=_NOW, fetch=fetch, send=send)
    assert any("schema drift" in t.lower() and "engagementStatus" in t for t in sent)


async def test_schema_drift_silent_when_aligned():
    sent, send = _collector()

    async def fetch(entity, field):
        return _full_options(entity, field)

    s = _settings(espo_dry_run=False, espo_api_key="k")
    await run_schema_drift_check(s, {}, now=_NOW, fetch=fetch, send=send)
    assert sent == []


async def test_schema_drift_skipped_in_dry_run():
    sent, send = _collector()
    called = []

    async def fetch(entity, field):
        called.append((entity, field))
        return None

    await run_schema_drift_check(
        _settings(espo_dry_run=True), {}, now=_NOW, fetch=fetch, send=send
    )
    assert sent == [] and called == []


# --- email alert channel (2026-07-20 — CBM uses no messaging service) ----------


class _CapturingGmail:
    sent: list = []

    def __init__(self, sa_info, mailbox, timeout=20):
        self.mailbox = mailbox

    async def send(self, mime, thread_id=None):
        _CapturingGmail.sent.append((self.mailbox, mime))
        return {"id": "sent1"}

    async def aclose(self):
        pass


async def _wire_email(monkeypatch):
    import core.gmail as gmail_mod
    import comms.service as comms_service

    _CapturingGmail.sent = []
    monkeypatch.setattr(gmail_mod, "GmailClient", _CapturingGmail)

    async def fake_sa(settings):
        return {"client_email": "sa@x"}

    monkeypatch.setattr(comms_service, "get_service_account", fake_sa)


async def test_alert_email_sends_via_delegation(monkeypatch):
    from core.monitoring import send_alert

    await _wire_email(monkeypatch)
    s = _settings(
        alert_email_to="doug@example.com, ops@cbmentors.org",
        alert_email_from="alerts.bot@cbmentors.org",
    )
    await send_alert(s, "3 submission(s) need attention — delivery failed.\nDetails…")
    [(mailbox, mime)] = _CapturingGmail.sent
    assert mailbox == "alerts.bot@cbmentors.org"
    assert mime["To"] == "doug@example.com, ops@cbmentors.org"
    assert "[CBM Intake" in mime["Subject"]
    assert "3 submission(s) need attention" in mime["Subject"]
    assert "CBM Intake Alerts" in mime["From"]


async def test_alert_email_falls_back_to_ops_mailbox_sender(monkeypatch):
    from core.monitoring import send_alert

    await _wire_email(monkeypatch)
    s = _settings(alert_email_to="doug@example.com", ops_mailbox="info@cbmentors.org")
    await send_alert(s, "backlog growing")
    [(mailbox, _)] = _CapturingGmail.sent
    assert mailbox == "info@cbmentors.org"


async def test_alert_email_failure_never_raises(monkeypatch, caplog):
    from core.monitoring import send_alert

    await _wire_email(monkeypatch)

    async def boom(self, mime, thread_id=None):
        raise RuntimeError("delegation rejected")

    monkeypatch.setattr(_CapturingGmail, "send", boom)
    s = _settings(alert_email_to="doug@example.com", alert_email_from="a@cbmentors.org")
    with caplog.at_level("WARNING", logger="cbm_intake.monitoring"):
        await send_alert(s, "the alert text")  # must not raise
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "alert email failed" in text and "the alert text" in text


async def test_alert_without_any_channel_still_logs(caplog):
    from core.monitoring import send_alert

    with caplog.at_level("WARNING", logger="cbm_intake.monitoring"):
        await send_alert(_settings(), "nobody is listening")
    assert any("nobody is listening" in r.getMessage() for r in caplog.records)


# --- web-side worker-liveness watch (2026-07-23) ----------------------------

from datetime import timedelta

from core.monitoring import run_worker_liveness_check


async def test_liveness_alerts_on_stale_heartbeat():
    sent, send = _collector()
    store = FakeMetricsStore({"workerHeartbeatAgeSeconds": 400})
    await run_worker_liveness_check(store, _settings(), {}, now=_NOW, send=send)
    assert len(sent) == 1 and "heartbeat is stale" in sent[0]


async def test_liveness_quiet_when_fresh():
    sent, send = _collector()
    store = FakeMetricsStore({"workerHeartbeatAgeSeconds": 5})
    await run_worker_liveness_check(store, _settings(), {}, now=_NOW, send=send)
    assert sent == []


async def test_liveness_cooldown_then_recovery_notice():
    sent, send = _collector()
    state = {}
    stale = FakeMetricsStore({"workerHeartbeatAgeSeconds": 400})
    await run_worker_liveness_check(stale, _settings(), state, now=_NOW, send=send)
    await run_worker_liveness_check(stale, _settings(), state, now=_NOW, send=send)
    assert len(sent) == 1  # cooldown suppresses the repeat
    healthy = FakeMetricsStore({"workerHeartbeatAgeSeconds": 3})
    await run_worker_liveness_check(healthy, _settings(), state, now=_NOW, send=send)
    assert len(sent) == 2 and "recovered" in sent[1]
    # A NEW incident after recovery alerts immediately (cooldown was cleared).
    await run_worker_liveness_check(stale, _settings(), state, now=_NOW, send=send)
    assert len(sent) == 3 and "stale" in sent[2]


async def test_liveness_never_stamped_gets_grace_then_alerts():
    sent, send = _collector()
    state = {}
    store = FakeMetricsStore({"workerHeartbeatAgeSeconds": None})
    # First check right after boot: inside the grace window — quiet.
    await run_worker_liveness_check(store, _settings(), state, now=_NOW, send=send)
    assert sent == []
    # Still no heartbeat after the threshold has elapsed — alert.
    later = _NOW + timedelta(seconds=400)
    await run_worker_liveness_check(store, _settings(), state, now=later, send=send)
    assert len(sent) == 1 and "never" in sent[0]
