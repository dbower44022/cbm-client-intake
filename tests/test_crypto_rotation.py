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
