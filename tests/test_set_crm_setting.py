"""``scripts/set_crm_setting.py`` writes one admin setting and proves it landed.
These pin the safety rules: a dry run writes nothing, a name the CRM did not
show is refused, an apply sends only that key and reads it back, an
already-equal value writes nothing, and a read-back mismatch fails."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


setter = _load("scripts/set_crm_setting.py", "set_crm_setting_under_test")


class _Resp:
    def __init__(self, status: int, body=None):
        self.status_code = status
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return json.loads(self.content)


class _FakeCrm:
    """A CRM whose Settings hold a few admin items. ``ignore_writes`` models a
    CRM that answers 200 and stores nothing; ``store_as`` one that normalises."""

    _base = "https://crm-test.example/api/v1"

    def __init__(self, *, ignore_writes=False, store_as=None):
        self.settings = {"cleanupActionHistoryPeriod": "15 days",
                         "cleanupAuthLogPeriod": "2 months",
                         "outboundEmailIsShared": False}
        self.writes: list[tuple[str, str, dict]] = []
        self.ignore_writes = ignore_writes
        self.store_as = store_as

    async def _request(self, method, url, op="", params=None, json_body=None):
        assert url == f"{self._base}/Settings"
        if method == "GET":
            return _Resp(200, dict(self.settings))
        self.writes.append((method, url, json_body))
        if not self.ignore_writes:
            for k, v in json_body.items():
                self.settings[k] = self.store_as if self.store_as is not None else v
        return _Resp(200, dict(self.settings))


def _run(crm, name, value, apply):
    return asyncio.run(setter.set_setting(crm, name, value, apply=apply))


def test_dry_run_writes_nothing(capsys):
    crm = _FakeCrm()
    assert _run(crm, "cleanupActionHistoryPeriod", "30 days", False) == 0
    assert crm.writes == []
    out = capsys.readouterr().out
    assert '"15 days"' in out and '"30 days"' in out and "Dry run" in out


def test_unknown_key_is_refused_and_never_written(capsys):
    crm = _FakeCrm()
    assert _run(crm, "authApiUserLogDisabled", True, True) == 2
    assert crm.writes == []
    assert "set_authlog_switch.sh" in capsys.readouterr().err


def test_apply_writes_only_the_key_and_verifies(capsys):
    crm = _FakeCrm()
    assert _run(crm, "cleanupActionHistoryPeriod", "30 days", True) == 0
    assert crm.writes == [("PUT", f"{crm._base}/Settings",
                           {"cleanupActionHistoryPeriod": "30 days"})]
    assert crm.settings["cleanupActionHistoryPeriod"] == "30 days"
    assert "read-back matches" in capsys.readouterr().out


def test_already_equal_is_a_no_op(capsys):
    crm = _FakeCrm()
    crm.settings["cleanupActionHistoryPeriod"] = "30 days"
    assert _run(crm, "cleanupActionHistoryPeriod", "30 days", True) == 0
    assert crm.writes == []
    assert "Already set" in capsys.readouterr().out


def test_read_back_mismatch_exits_non_zero(capsys):
    crm = _FakeCrm(ignore_writes=True)
    assert _run(crm, "cleanupActionHistoryPeriod", "30 days", True) == 1
    assert len(crm.writes) == 1
    assert "MISMATCH" in capsys.readouterr().err


def test_normalised_value_is_a_mismatch_too():
    crm = _FakeCrm(store_as="30 days ")
    assert _run(crm, "cleanupActionHistoryPeriod", "30 days", True) == 1


def test_json_values_compare_by_type():
    assert setter.parse_value("true", True) is True
    assert setter.parse_value("true", False) == "true"
    crm = _FakeCrm()
    assert _run(crm, "outboundEmailIsShared", True, True) == 0
    assert crm.writes[0][2] == {"outboundEmailIsShared": True}


def test_a_number_is_not_a_boolean():
    # Review finding 11-05-26: 1 == True in Python; the CRM's true is not 1.
    crm = _FakeCrm()
    crm.settings["outboundEmailIsShared"] = True
    # A stored true does not count as "already 1": the apply writes.
    assert _run(crm, "outboundEmailIsShared", 1, True) == 0
    assert crm.writes == [("PUT", f"{crm._base}/Settings", {"outboundEmailIsShared": 1})]


def test_a_secret_setting_is_never_printed(capsys):
    crm = _FakeCrm()
    crm.settings["smtpPassword"] = "hunter2"
    _run(crm, "smtpPassword", "other", False)
    out = capsys.readouterr().out
    assert "hunter2" not in out and "other" not in out
    assert "(set, not shown)" in out
