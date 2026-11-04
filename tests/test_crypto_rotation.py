"""Rotating APP_ENCRYPTION_KEY (OPEN-ITEMS #33, Doug's option B, 11-04-26):
the setting may hold NEW,OLD; new values use NEW, old ones still decrypt, and
scripts/rotate_encryption_key.py moves every stored value onto NEW."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.crypto import CryptoError, SecretCipher, split_keys

OLD = SecretCipher.generate_key()
NEW = SecretCipher.generate_key()


def _script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "rotate_encryption_key.py"
    spec = importlib.util.spec_from_file_location("rotate_encryption_key", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_one_key_behaves_as_before():
    c = SecretCipher(OLD)
    assert c.key_count == 1
    assert c.decrypt(c.encrypt("s3cret")) == "s3cret"


def test_two_keys_encrypt_with_the_first_and_read_both():
    old_token = SecretCipher(OLD).encrypt("old value")
    both = SecretCipher(f"{NEW}, {OLD}")
    assert both.key_count == 2
    assert both.decrypt(old_token) == "old value"
    fresh = both.encrypt("new value")
    assert SecretCipher(NEW).decrypt(fresh) == "new value"          # written with NEW
    with pytest.raises(CryptoError):
        SecretCipher(OLD).decrypt(fresh)                           # not readable with OLD
    assert both.is_current(fresh) and not both.is_current(old_token)
    rotated = both.rotate(old_token)
    assert SecretCipher(NEW).decrypt(rotated) == "old value"       # NEW alone reads it


def test_split_keys_and_a_bad_key():
    assert split_keys(" a , b ,") == ["a", "b"]
    with pytest.raises(CryptoError):
        SecretCipher("")
    with pytest.raises(CryptoError):
        SecretCipher(f"{NEW},not-a-key")


def test_the_script_classifies_without_reading_out_a_secret():
    mod = _script()
    both = SecretCipher(f"{NEW},{OLD}")
    stranger = SecretCipher(SecretCipher.generate_key()).encrypt("x")
    assert mod.classify(both, both.encrypt("a")) == "current"
    assert mod.classify(both, SecretCipher(OLD).encrypt("a")) == "old"
    assert mod.classify(both, stranger) == "unreadable"
    assert mod.classify(both, "") == "empty" and mod.classify(both, None) == "empty"
    # Every table that stores ciphertext is covered.
    covered = {t.name: cols for t, _k, cols, _f in mod.TARGETS}
    assert covered == {
        "app_setting": ["value", "previous_value"],
        "app_config": ["value_encrypted"],
        "mailing_connection": ["access_token", "refresh_token"],
    }


def test_the_spec_helper_never_prints_a_key(tmp_path, monkeypatch, capsys):
    path = Path(__file__).resolve().parent.parent / "scripts" / "encryption_key_spec.py"
    spec = importlib.util.spec_from_file_location("encryption_key_spec", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "NEW_FILE", tmp_path / "new-key")
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(f"services:\n- name: web\n  envs:\n  - key: APP_ENCRYPTION_KEY\n    value: {OLD}\n    type: SECRET\n")
    monkeypatch.setattr(mod, "OVERLAY", overlay)
    assert mod.cmd_generate() == 0
    assert (tmp_path / "new-key").stat().st_mode & 0o777 == 0o600
    assert mod.cmd_fingerprints() == 0
    assert mod.cmd_overlay() == 0
    out = capsys.readouterr().out
    new = (tmp_path / "new-key").read_text().strip()
    assert new not in out and OLD not in out
    assert mod.fp(OLD) in out and mod.fp(new) in out
    assert new in overlay.read_text() and OLD not in overlay.read_text()
