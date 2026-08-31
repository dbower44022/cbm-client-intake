# Rehearsal scripts — the Lakeside dress rehearsal, 2026-08-31

The three scripts that carried the **API half** of the standard, the test
users, and the app spec onto the throwaway chapter instance in Phase 1's
acceptance criterion 13. They are rehearsal artifacts, not the applier — the
record they produced is `prds/chapter-network/rehearsal-2026-08-31/`, and what
each one measured is in that directory's `coverage-record.md`.

| Script | What it does | Reads | Writes |
|---|---|---|---|
| `apply_api_half.py --env FILE [--apply]` | Teams, roles (+ attachments), email templates, the org-wide API user, a provisioning admin, the § E instance settings, then `Admin/rebuild`. Idempotent; strips role scopes the target lacks and reports them `unapplyable` (exit 4) | the crm-test capture in `prds/chapter-network/rehearsal-2026-08-31/crmtest-capture/`; `ESPO_ADMIN_*` from FILE | minted secrets appended to FILE; `api-half-result.json` next to the script |
| `stage4_users.py [--apply]` | One `regular` user per gated team + the Mentor Team user's Contact and `CMentorProfile` | `lakeside.env` next to the script | `lakeside-users.env` next to the script |
| `render_spec.py VALUES ENV OUT` | Renders a DigitalOcean App Platform spec (web + worker + Postgres + PRE_DEPLOY migrate, `deploy_on_push: false`) from a chapter-values file and a secrets env file | `lakeside-values.yaml`, an env file | a plaintext-secret YAML for `doctl apps create --spec` — never commit it |

The file half (entities, fields, links, layouts, labels, client-side custom
code) is not a script: it is `rsync` of two trees from a source instance —
`custom/Espo/Custom/` and `client/custom/src/` — followed by
`php command.php rebuild`. See the coverage record.

Credentials never live in this directory. The env files sit in
`~/.config/cbm-lakeside/` on the operator's machine.
