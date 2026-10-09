"""Shared fixtures.

The CRM client keeps two pieces of process-wide state — the shared connection
pool and the metadata cache (v0.245.0 / v0.246.0). A test that builds an app
arms the cache for the whole process, so every test starts disarmed and empty
and leaves no pooled sockets behind.
"""

import pytest

from core import espo


@pytest.fixture(autouse=True)
def _isolate_crm_client_state():
    espo.arm_metadata_cache(False)
    espo.clear_metadata_cache()
    yield
    espo.arm_metadata_cache(False)
    espo.clear_metadata_cache()
