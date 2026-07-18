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
