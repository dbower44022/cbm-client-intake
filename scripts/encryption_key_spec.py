"""Production's APP_ENCRYPTION_KEY rotation — the build computer's half.

OPEN-ITEMS #33, Doug's option B (11-04-26). Pairs with
``scripts/rotate_encryption_key.sh`` inside the web container. It never prints a
key: only an 8-character fingerprint (the first 8 hex of its SHA-256), which
the container script prints too, so the two can be compared.

    uv run python scripts/encryption_key_spec.py generate        # a new key, saved 0600
    uv run python scripts/encryption_key_spec.py fingerprints    # old (overlay) and new
    uv run python scripts/encryption_key_spec.py prepare rotate  # live spec, key = NEW,OLD
    uv run python scripts/encryption_key_spec.py prepare final   # live spec, key = NEW
    uv run python scripts/encryption_key_spec.py overlay         # the local overlay's key -> NEW

* The new key lives in ``~/.config/cbm-cleveland/new-encryption-key`` (0600).
* The OLD key is read from the local production overlay's **web** component
  (``.do/app.prod-crm.yaml``). The overlay is stale and half-edited (OPEN-ITEMS
  #33), so the step page proves OLD is the live key — the container prints the
  live key's fingerprint — before anything is applied.
* ``prepare`` starts from the LIVE spec (``doctl apps spec get``; secrets come
  back as ``EV[…]`` blobs, which DigitalOcean accepts on update), changes only
  ``APP_ENCRYPTION_KEY`` on every component that has it, and writes
  ``~/.config/cbm-cleveland/prod-spec-<stage>.yaml`` (0600). Nothing is sent:
  the step page runs ``doctl apps update`` with that file.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PROD_APP = "aa1ddf69-f359-4b53-91ba-035cbed7bd53"
HOME = Path.home() / ".config" / "cbm-cleveland"
NEW_FILE = HOME / "new-encryption-key"
OVERLAY = REPO / ".do" / "app.prod-crm.yaml"
KEY = "APP_ENCRYPTION_KEY"


def fp(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def components(spec: dict):
    for kind in ("services", "workers", "jobs", "static_sites", "functions"):
        for comp in spec.get(kind) or []:
            yield kind, comp


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(path, 0o600)


def new_key() -> str:
    if not NEW_FILE.exists():
        sys.exit(f"No new key yet — run: uv run python scripts/encryption_key_spec.py generate")
    return NEW_FILE.read_text().strip()


def old_key() -> str:
    spec = yaml.safe_load(OVERLAY.read_text())
    for kind, comp in components(spec):
        if comp.get("name") == "web":
            for env in comp.get("envs") or []:
                if env.get("key") == KEY:
                    value = str(env.get("value") or "")
                    if value.startswith("EV["):
                        sys.exit("The overlay's web key is an EV[...] blob, not the key itself.")
                    return value.split(",")[0].strip()
    sys.exit(f"No {KEY} on the web component of {OVERLAY}.")


def cmd_generate() -> int:
    if NEW_FILE.exists():
        print(f"A new key already exists at {NEW_FILE} (fingerprint {fp(new_key())}); keeping it.")
        return 0
    from cryptography.fernet import Fernet
    write_private(NEW_FILE, Fernet.generate_key().decode() + "\n")
    print(f"New key saved to {NEW_FILE} (readable by you only). Fingerprint {fp(new_key())}.")
    print("Save it in your password manager as well before going on.")
    return 0


def cmd_fingerprints() -> int:
    print(f"OLD (the overlay's web key): {fp(old_key())}")
    print(f"NEW ({NEW_FILE.name}):        {fp(new_key())}")
    return 0


def cmd_prepare(stage: str) -> int:
    if stage not in ("rotate", "final"):
        sys.exit("prepare takes 'rotate' or 'final'")
    new = new_key()
    value = f"{new},{old_key()}" if stage == "rotate" else new
    raw = subprocess.run(["doctl", "apps", "spec", "get", PROD_APP, "--format", "yaml"],
                         check=True, capture_output=True, text=True).stdout
    spec = yaml.safe_load(raw)
    changed = []
    for kind, comp in components(spec):
        for env in comp.get("envs") or []:
            if env.get("key") == KEY:
                env["value"] = value
                env["type"] = "SECRET"
                changed.append(comp.get("name"))
    if not changed:
        sys.exit(f"The live spec has no {KEY} on any component — stop and tell Claude.")
    out = HOME / f"prod-spec-{stage}.yaml"
    write_private(out, yaml.safe_dump(spec, sort_keys=False))
    keys = ", ".join(fp(k) for k in value.split(","))
    print(f"Wrote {out} (readable by you only): {KEY} = [{keys}] on {', '.join(changed)}.")
    print(f"Next: doctl apps update {PROD_APP} --spec {out}")
    return 0


def cmd_overlay() -> int:
    new = new_key()
    spec = yaml.safe_load(OVERLAY.read_text())
    changed = []
    for kind, comp in components(spec):
        for env in comp.get("envs") or []:
            if env.get("key") == KEY:
                env["value"] = new
                env["type"] = "SECRET"
                changed.append(comp.get("name"))
    write_private(OVERLAY, yaml.safe_dump(spec, sort_keys=False))
    print(f"{OVERLAY}: {KEY} set to the new key ({fp(new)}) on {', '.join(changed)}.")
    print("The overlay is otherwise unchanged — still stale; prefer the live spec for any update.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["generate"]:
        return cmd_generate()
    if args[:1] == ["fingerprints"]:
        return cmd_fingerprints()
    if args[:1] == ["prepare"] and len(args) == 2:
        return cmd_prepare(args[1])
    if args[:1] == ["overlay"]:
        return cmd_overlay()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
