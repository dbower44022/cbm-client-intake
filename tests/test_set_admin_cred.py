"""scripts/set_admin_cred.py rewrites only the two admin lines of an env file."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("set_admin_cred", ROOT / "scripts/set_admin_cred.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_rewrite_replaces_in_place_and_keeps_the_rest():
    text = "ESPO_ADMIN_BASE=https://x\nESPO_ADMIN_USER=admin\nESPO_ADMIN_PASS=old\nOTHER=1\n"
    got = mod.rewrite(text, {"ESPO_ADMIN_USER": "crm.config", "ESPO_ADMIN_PASS": "new"})
    assert got == "ESPO_ADMIN_BASE=https://x\nESPO_ADMIN_USER=crm.config\nESPO_ADMIN_PASS=new\nOTHER=1\n"


def test_rewrite_adds_missing_keys_and_drops_duplicates():
    got = mod.rewrite("A=1\nESPO_ADMIN_PASS=a\nESPO_ADMIN_PASS=b\n",
                      {"ESPO_ADMIN_USER": "u", "ESPO_ADMIN_PASS": "p"})
    assert got == "A=1\nESPO_ADMIN_PASS=p\nESPO_ADMIN_USER=u\n"


def test_password_rules():
    assert mod.check_password("a" * 23)
    assert mod.check_password("a" * 23 + "!")
    assert mod.check_password("é" * 24)
    assert mod.check_password("Ab3" * 8) == ""
