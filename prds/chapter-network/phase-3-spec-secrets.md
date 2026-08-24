# Phase 3 — Spec generation and secrets

**Status: not started.**

**Why it matters beyond chapters.** Today the ability to deploy this product lives
with whoever holds the two gitignored overlays on one laptop. That is the services
org's bus factor before the services org exists, and it is listed in the risk
register for exactly that reason.

**What Phase 1 changed about this phase.** It is **no longer a prerequisite for
Phase 1's deploy gate** — the conformance check needs only the org-wide API key
every app already has. It remains a prerequisite for automating the *apply* step,
and that dependency moved with the apply step to
[Phase 2](phase-2-release-train.md).

---

## Per-chapter configuration and secrets

Today `.do/app.prod.yaml` and `.do/app.prod-crm.yaml` are gitignored overlays
holding plaintext secrets, applied by hand with `doctl`, and regenerating one
encrypts the secrets into unreadable `EV[…]` blobs
([[overlay-regen-encrypts-secrets]]). That is already fragile for two apps. Across
N chapter-owned accounts it is not viable.

- **One spec template plus a per-chapter values file.** The template is in this
  repo and versions with the release; the values file carries only what differs —
  chapter name, domains, CRM URL, Workspace subject, Drive id, Zoom host, feature
  flags.
- **Secrets in a real store**, referenced by the generator, never in a file on one
  laptop. This is also what makes the services org survivable as an organization:
  today the ability to deploy lives with whoever holds the overlays.
- **`/setup` remains the runtime control** for anything not boot-read. The
  denylist and `BOOT_READ_KEYS` rules are unchanged and matter more now — an
  override that silently does not apply is worse across six chapters than one.


---

## Inherited from Phase 0: locale

Cleveland's **timezone** is hardcoded in four places and is not the same thing as
Cleveland's name:

- `portal/birthday.py:47` — `_LOCAL = ZoneInfo("America/New_York")`
- `assignments/service.py:942` — the assignment stamp
- `events/config.py:72` — `PUBLIC_TIMEZONE`
- `core/zoom.py:247` — a default argument
- (`comms_digest_tz` is already a setting with the same default)

A chapter outside Eastern time would show wrong calendar days on birthdays,
assignment stamps and the public events programme. It was left out of Phase 0 by
the standard that phase held itself to — fixing it is justified only by chapters
that may never exist, and Cleveland gains nothing — and it belongs in the
per-chapter values file this phase builds.
