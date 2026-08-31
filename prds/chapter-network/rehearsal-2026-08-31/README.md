# The Lakeside dress rehearsal — 2026-08-31

Phase 1 acceptance criterion 13, executed for real: a throwaway EspoCRM for a
chapter that does not exist ("Lakeside Business Mentors", `crm-lakeside`),
brought to the CBM standard, put in front of a fresh App Platform app, and
verified as **real non-admins**. Nothing touched Cleveland production or
crm-test (crm-test was read, never written).

| File | What it is |
|---|---|
| `coverage-record.md` | **Start here.** Per configuration category, which mechanism carried it and the outcome; findings F1–F13; the gate results |
| `preflight-crmtest-baseline.json` | `preflight_crm.py --json` on crm-test that morning — exit 1, 20 conformant, one absent |
| `preflight-lakeside.json` | The same check on the throwaway after the standard — identical result |
| `api-half-result.json` | The scripted API half's result document (C5 shape): 33 conformant, 73 unapplyable, exit 4 |
| `nonadmin-gate-matrix.json` | Seven non-admins × twelve gated endpoints through the portal API: 200 on own apps, 403 elsewhere |
| `healthz-lakeside.json` | The app's `/healthz` after first deploy — `releaseTag null`, `crmConfig unstamped` |
| `lakeside-values.yaml` | The per-chapter values file, filled in for the fictional chapter (no secrets) |
| `crmtest-capture/` | crm-test's roles, teams, role→team attachments, email templates, extensions and tab list, read from its database over SSH — the input to the API half, and the crm-test half of task R4 |

The scripts that produced it are in `scripts/rehearsal/`. The instance was
**kept**, by Doug's ruling the same evening, for the Google-integration
rehearsal; teardown is owed when that ends.
