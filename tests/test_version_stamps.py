"""The chapter network's two version stamps at ``/healthz``.

``version`` answers "what code is this" and always has. These add "what
*promotion* is this" (``releaseTag``, baked into the image at build time) and
"what configuration does the CRM behind it hold" (``crmConfig``, read from the
``CNetworkStandard`` record). A promotion pins the **pair**, and an instance is
conformant when it holds the pair the release train pinned — not when each half
independently looks plausible.

Most of what is asserted here is the **shape**, deliberately: the fleet console
is built against this contract before there is anything interesting to put in
it, and both halves report null on every instance today.

The classification tests are the ones that matter. Absent, forbidden and
unreachable are three different facts, and collapsing them turns "your API key
lost its role" into "your CRM is missing an entity" — the exact defect the
conformance check was rewritten to stop making. It is not hypothetical here:
production's ``CNetworkStandard`` is owed at a Sunday release slot and this code
may deploy before it, so ``absent`` is production's expected reading for a while
and must never read as a fault.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core import network_standard as ns
from core.config import Settings
from core.espo import EspoError, EspoTransportError
from core.settings_registry import BOOT_READ_KEYS, DENYLIST
from main import app


@pytest.fixture(autouse=True)
def _clean_cache():
    ns.reset()
    yield
    ns.reset()


class _FakeClient:
    """Answers `list` with a canned envelope, or raises a canned error."""

    def __init__(self, *, envelope=None, error=None):
        self._envelope = envelope
        self._error = error
        self.calls: list[tuple] = []

    async def list(self, entity, **kw):
        self.calls.append((entity, kw))
        if self._error is not None:
            raise self._error
        return self._envelope


# --- The /healthz shape -----------------------------------------------------

def test_healthz_carries_both_stamps():
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert "releaseTag" in body
    assert "crmConfig" in body


def test_untagged_build_reports_null_rather_than_guessing():
    body = TestClient(app).get("/healthz").json()
    assert body["releaseTag"] is None


def test_release_tag_comes_from_the_image_stamp():
    assert Settings(release_tag="v0.213.1").release_tag == "v0.213.1"
    assert Settings().release_tag == ""


def test_crm_config_block_keeps_the_three_documented_keys():
    """A consumer that only knows the documented contract must still work."""
    block = TestClient(app).get("/healthz").json()["crmConfig"]
    for key in ("version", "appliedAt", "fingerprint"):
        assert key in block
        assert block[key] is None


def test_probe_is_dark_by_default():
    """0 disables, and 0 is the default: this ships off and is switched on
    per deployment, crm-test first."""
    assert Settings().crm_config_refresh_seconds == 0
    assert TestClient(app).get("/healthz").json()["crmConfig"]["state"] == "disabled"


@pytest.mark.anyio
async def test_healthz_serves_the_cache_and_never_calls_the_crm_inline():
    """The handler reads whatever the background refresh last cached. A CRM
    outage must not take the web tier down, so there is no network call on the
    request path — priming the cache once must be the ONLY call, however many
    health checks follow."""
    client = _FakeClient(envelope={"total": 1, "list": [{"standardVersion": "2026.08.1"}]})
    await ns.refresh(client)
    assert len(client.calls) == 1

    http = TestClient(app)
    for _ in range(3):
        block = http.get("/healthz").json()["crmConfig"]
        assert block["version"] == "2026.08.1"  # served, so the cache is the source
    assert len(client.calls) == 1  # and no health check added one


# --- Classification: the three facts that must not collapse -----------------

@pytest.mark.anyio
async def test_a_stamped_crm_reports_its_version():
    client = _FakeClient(envelope={"total": 1, "list": [{
        "standardVersion": "2026.08.1",
        "appliedAt": "2026-08-30 17:04:00",
        "planFingerprint": "sha256:abc123",
    }]})
    got = await ns.read(client)
    assert got.state == ns.STATE_STAMPED
    assert got.version == "2026.08.1"
    assert got.applied_at == "2026-08-30 17:04:00"
    assert got.fingerprint == "sha256:abc123"


@pytest.mark.anyio
async def test_entity_present_but_empty_is_unstamped_not_an_error():
    """'Configured to report, never applied to' — the honest state of every
    instance until an applier first runs."""
    got = await ns.read(_FakeClient(envelope={"total": 0, "list": []}))
    assert got.state == ns.STATE_UNSTAMPED
    assert got.version is None


@pytest.mark.anyio
async def test_missing_entity_reads_as_absent():
    """Production before its Sunday build. Not a fault."""
    got = await ns.read(_FakeClient(error=EspoError("list CNetworkStandard failed: HTTP 404")))
    assert got.state == ns.STATE_ABSENT


@pytest.mark.anyio
async def test_denied_read_is_forbidden_never_absent():
    """The whole point: a credential problem must not read as a configuration
    problem. This is the grant that was missed on crm-test on 2026-08-27."""
    got = await ns.read(_FakeClient(error=EspoError("list CNetworkStandard failed: HTTP 403")))
    assert got.state == ns.STATE_FORBIDDEN
    assert got.state != ns.STATE_ABSENT


@pytest.mark.anyio
async def test_crm_outage_is_unreachable_not_absent():
    """Unknown is not the same as bad — the fleet console has to be able to
    say '18 conformant, 1 drifted, 1 unreachable'."""
    got = await ns.read(_FakeClient(error=EspoTransportError("connect timeout")))
    assert got.state == ns.STATE_UNREACHABLE


@pytest.mark.anyio
async def test_an_unexpected_failure_never_escapes():
    got = await ns.read(_FakeClient(error=RuntimeError("boom")))
    assert got.state == ns.STATE_UNREACHABLE


@pytest.mark.anyio
async def test_a_row_with_no_version_does_not_claim_conformance():
    """Claiming a conformance we cannot name is worse than claiming none."""
    got = await ns.read(_FakeClient(envelope={"total": 1, "list": [{"appliedAt": "x"}]}))
    assert got.state == ns.STATE_UNSTAMPED


@pytest.mark.anyio
async def test_refresh_updates_the_cache_read_by_healthz():
    assert ns.current().state == ns.STATE_DISABLED
    await ns.refresh(_FakeClient(envelope={"total": 1, "list": [{"standardVersion": "2026.08.1"}]}))
    assert ns.current().version == "2026.08.1"


@pytest.mark.anyio
async def test_the_page_size_stays_inside_the_crm_list_limit():
    """A maxSize over the CRM's limit is a 403, not a truncation — and inside a
    best-effort handler that reads as 'no records'."""
    client = _FakeClient(envelope={"total": 0, "list": []})
    await ns.read(client)
    entity, kw = client.calls[0]
    assert entity == "CNetworkStandard"
    assert kw["max_size"] <= 200


# --- Boot-read discipline ---------------------------------------------------

def test_both_are_on_the_settings_page_marked_restart_required():
    """Doug's ruling, 2026-08-28: every setting belongs on the Settings page.
    Both of these are read once at process start, so they live in the
    "Restart required" group, which shows the value in force beside the stored
    one. `release_tag` is there read-only — it comes from the image, and an
    override would make the deployment misreport which image it is running."""
    from core.settings_registry import BY_KEY, GROUP_RESTART

    for key in ("crm_config_refresh_seconds", "release_tag"):
        assert key in BOOT_READ_KEYS
        assert BY_KEY[key].group == GROUP_RESTART
        assert BY_KEY[key].restart
    assert not BY_KEY["crm_config_refresh_seconds"].readonly
    assert BY_KEY["release_tag"].readonly
    assert "release_tag" in DENYLIST
