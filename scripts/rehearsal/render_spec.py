#!/usr/bin/env python3
"""Render a DigitalOcean App Platform spec for a chapter from its values file
plus its secrets env file. A measurement for Phase 3 (spec generator): this is
the whole of what a generator has to do. Output is plaintext-secret YAML that
must never be committed; feed it straight to `doctl apps create --spec`."""
import secrets, sys, yaml
from pathlib import Path

values = yaml.safe_load(Path(sys.argv[1]).read_text())
env = {}
for raw in Path(sys.argv[2]).read_text().splitlines():
    if raw.strip() and not raw.startswith("#") and "=" in raw:
        k, v = raw.split("=", 1); env[k.strip()] = v.strip()
slug = values["chapter"]["slug"]
db = f"{slug}-db"
missing = [k for k in ("ESPO_API_KEY", "ESPO_PROVISION_USERNAME", "ESPO_PROVISION_PASSWORD") if k not in env]
if missing:
    sys.exit(f"secrets not yet minted: {missing}")
for k, n in (("SESSION_SECRET", 48), ("APP_ENCRYPTION_KEY", 32)):
    if k not in env:  # mint once and persist — rotating APP_ENCRYPTION_KEY later would be data loss
        env[k] = secrets.token_urlsafe(n)
        with open(sys.argv[2], "a") as fh: fh.write(f"{k}={env[k]}\n")

def ev(key, value, secret=False, scope="RUN_TIME"):
    d = {"key": key, "scope": scope, "value": str(value)}
    if secret: d["type"] = "SECRET"
    return d

f = values["flags"]; w = values["web"]; c = values["crm"]
common = [
    ev("ESPO_DRY_RUN", str(f["espo_dry_run"]).lower()),
    ev("ESPO_BASE_URL", c["base_url"]),
    ev("ESPO_API_KEY", env["ESPO_API_KEY"], secret=True),
    ev("DATABASE_URL", f"${{{db}.DATABASE_URL}}"),
    ev("ASYNC_DELIVERY", str(f["async_delivery"]).lower()),
    ev("ANALYTICS_ENABLED", str(f["analytics_enabled"]).lower()),
    ev("ORGANIZATION_NAME", values["chapter"]["name"]),
    ev("GMAIL_SYNC", "false"), ev("GCAL_EVENTS", "false"), ev("GDRIVE_DOCS", "false"),
]
web_only = [
    ev("SESSION_SECRET", env["SESSION_SECRET"], secret=True),
    ev("APP_ENCRYPTION_KEY", env["APP_ENCRYPTION_KEY"], secret=True),
    ev("SESSION_COOKIE_SECURE", "true"),
    ev("SETUP_ENABLED", str(f["setup_enabled"]).lower()),
    ev("EVENTS_ENABLED", str(f["events_enabled"]).lower()),
    ev("EVENTS_PUBLIC_API", str(f["events_public_api"]).lower()),
    ev("RECORD_QUICK_ADD", str(f["record_quick_add"]).lower()),
    ev("MENTOR_PROVISION_USERS", str(f["mentor_provision_users"]).lower()),
    ev("GOOGLE_DIRECTORY_CHECK", "false"),
    ev("ESPO_PROVISION_USERNAME", env["ESPO_PROVISION_USERNAME"]),
    ev("ESPO_PROVISION_PASSWORD", env["ESPO_PROVISION_PASSWORD"], secret=True),
    ev("CRM_CONFIG_REFRESH_SECONDS", "300"),
    ev("POLICY_CLIENT_CONDUCT_URL", w["policy_client_conduct_url"]),
    ev("POLICY_MENTOR_ETHICS_URL", w["policy_mentor_ethics_url"]),
    ev("POLICY_TERMS_URL", w["policy_terms_url"]),
    ev("POLICY_PRIVACY_URL", w["policy_privacy_url"]),
    ev("EVENTS_PUBLIC_BASE_URL", w["events_public_base_url"]),
    ev("ALLOWED_ORIGINS", "http://localhost:8000"),
    ev("ENV_LABEL", "Rehearsal"),
]
if w.get("app_base_url"): web_only.append(ev("APP_BASE_URL", w["app_base_url"]))
if w.get("docs_site_url"): web_only.append(ev("DOCS_SITE_URL", w["docs_site_url"]))
if env.get("RELEASE_TAG"): web_only.append(ev("RELEASE_TAG", env["RELEASE_TAG"], scope="RUN_AND_BUILD_TIME"))
gh = {"repo": "dbower44022/cbm-client-intake", "branch": "main", "deploy_on_push": bool(f["deploy_on_push"])}
spec = {
    "name": f"{slug}-intake",
    "region": "nyc",
    "databases": [{"name": db, "engine": "PG", "version": "16", "production": False}],
    "jobs": [{"name": "migrate", "kind": "PRE_DEPLOY", "dockerfile_path": "Dockerfile",
              "github": {"repo": gh["repo"], "branch": gh["branch"]},
              "instance_count": 1, "instance_size_slug": "apps-s-1vcpu-0.5gb",
              "run_command": ".venv/bin/alembic upgrade head",
              "envs": [ev("DATABASE_URL", f"${{{db}.DATABASE_URL}}")]}],
    "services": [{"name": "web", "dockerfile_path": "Dockerfile", "github": gh,
                  "http_port": 8080, "instance_count": 1, "instance_size_slug": "basic-xxs",
                  "health_check": {"http_path": "/healthz"}, "envs": common + web_only}],
    "workers": [{"name": "delivery-worker", "dockerfile_path": "Dockerfile", "github": gh,
                 "instance_count": 1, "instance_size_slug": "basic-xxs",
                 "run_command": ".venv/bin/python -m worker", "envs": common}],
    "ingress": {"rules": [{"component": {"name": "web"}, "match": {"path": {"prefix": "/"}}}]},
}
Path(sys.argv[3]).write_text(yaml.safe_dump(spec, sort_keys=False))
print("wrote", sys.argv[3], "with", len(common), "shared +", len(web_only), "web-only env vars")
