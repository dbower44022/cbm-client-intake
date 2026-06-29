"""The environment label powering the per-form corner badge.

``Settings.environment`` is derived from the CRM target (or an explicit
override) and surfaced on ``/healthz`` for ``shared/footer.js`` to render.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.config import Settings
from main import app


def test_dry_run_is_dev():
    assert Settings(espo_dry_run=True).environment == "dev"


def test_crm_test_url_is_test():
    s = Settings(
        espo_dry_run=False,
        espo_base_url="https://crm-test.clevelandbusinessmentors.org",
    )
    assert s.environment == "test"


def test_live_prod_crm_is_production():
    s = Settings(
        espo_dry_run=False,
        espo_base_url="https://crm.clevelandbusinessmentors.org",
    )
    assert s.environment == "production"


def test_explicit_label_overrides_derivation():
    s = Settings(espo_dry_run=False, env_label="STAGING")
    assert s.environment == "STAGING"


def test_healthz_reports_environment():
    resp = TestClient(app).get("/healthz")
    assert resp.status_code == 200
    # Default test config is dry-run, so the app reports the dev environment.
    assert resp.json()["environment"] == "dev"


def test_index_page_shows_environment_badge():
    # The server-rendered landing page (no shared footer.js) embeds the badge
    # directly; default test config is dry-run => the DEV badge.
    html = TestClient(app).get("/").text
    assert 'role="status"' in html
    assert "DEV · DRY-RUN" in html
