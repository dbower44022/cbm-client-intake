"""scripts/set_authlog_switch.sh, run for real against a throwaway local
container from the same EspoCRM image crm-test runs, with a sample
data/ directory mounted in. Nothing here reaches a droplet.

Skipped when docker or the image is not available (CI has neither)."""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "set_authlog_switch.sh"
IMAGE = os.environ.get("AUTHLOG_TEST_IMAGE", "espocrm/espocrm:9.3.10-fpm")  # the 10.0.10 image passes too

# EspoCRM's own on-disk format: two-space indent, no comma after the last item.
SAMPLE = """<?php
return [
  'database' => [
    'host' => 'espocrm-db',
    'dbname' => 'espocrm'
  ],
  'logger' => [
    'level' => 'WARNING'
  ],
  'isInstalled' => true,
  'cryptKey' => 'abc\\'def'
];
"""


def _docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ready(), reason=f"needs docker and the {IMAGE} image")


@pytest.fixture
def crm(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    name = f"authlog-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "--entrypoint", "sleep",
         "-v", f"{data}:/var/www/html/data", IMAGE, "300"],
        check=True, capture_output=True,
    )

    def put(text: str, owner: str = "33:33") -> None:
        (data / "config-internal.php").write_text(text)
        (data / "config.php").write_text("<?php\nreturn [\n  'useCache' => true\n];\n")
        subprocess.run(["docker", "exec", "-u", "0", name, "chown", "-R", owner, "/var/www/html/data"],
                       check=True)

    def run(*args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, CONTAINER=name)
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def php(code: str) -> str:
        return subprocess.run(["docker", "exec", "-w", "/var/www/html", name, "php", "-r", code],
                              capture_output=True, text=True, check=True).stdout

    def owner() -> str:
        return subprocess.run(["docker", "exec", name, "stat", "-c", "%u:%g %a",
                               "/var/www/html/data/config-internal.php"],
                              capture_output=True, text=True, check=True).stdout.strip()

    try:
        yield put, run, php, owner, data
    finally:
        subprocess.run(["docker", "exec", "-u", "0", name, "chown", "-R", f"{os.getuid()}:{os.getgid()}",
                        "/var/www/html/data"], capture_output=True)
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


VALUE = 'var_export((include "data/config-internal.php")["authApiUserLogDisabled"] ?? "absent");'


def test_check_writes_nothing(crm):
    put, run, php, owner, data = crm
    put(SAMPLE)
    r = run()
    assert r.returncode == 0, r.stderr
    assert "effective authApiUserLogDisabled: not set" in r.stdout
    assert "nothing written" in r.stdout
    assert (data / "config-internal.php").read_text() == SAMPLE


def test_apply_adds_the_line_keeps_everything_else_and_the_owner(crm):
    put, run, php, owner, data = crm
    put(SAMPLE)
    subprocess.run(["chmod", "644", str(data / "config-internal.php")], check=False)
    before = owner()
    r = run("--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT: authApiUserLogDisabled is now true" in r.stdout
    assert php(VALUE) == "true"
    assert owner() == before
    text = (data / "config-internal.php").read_text()
    assert "'authApiUserLogDisabled' => true," in text
    assert "authLogDisabled'" not in text
    backups = list(data.glob("config-internal.php.bak-authlog-*"))
    assert len(backups) == 1 and backups[0].read_text() == SAMPLE
    assert not list(data.glob("*.candidate-*"))
    # every other setting reads back unchanged
    assert php('echo (include "data/config-internal.php")["cryptKey"];') == "abc'def"


def test_apply_twice_is_a_no_op_and_off_undoes_it(crm):
    put, run, php, owner, data = crm
    put(SAMPLE)
    assert run("--apply").returncode == 0
    r = run("--apply")
    assert r.returncode == 0 and "RESULT: unchanged" in r.stdout
    assert run("--off").returncode == 0
    assert php(VALUE) == "false"
    assert run("--apply").returncode == 0
    assert php(VALUE) == "true"
    assert (data / "config-internal.php").read_text().count("authApiUserLogDisabled") == 1


def test_warns_on_the_everything_off_key_and_never_touches_it(crm):
    put, run, php, owner, data = crm
    put(SAMPLE.replace("  'isInstalled' => true,", "  'isInstalled' => true,\n  'authLogDisabled' => true,"))
    r = run()
    assert "WARNING: authLogDisabled is TRUE" in r.stdout
    assert run("--apply").returncode == 0
    assert php('var_export((include "data/config-internal.php")["authLogDisabled"]);') == "true"


def test_unparsable_file_is_refused_and_left_alone(crm):
    put, run, php, owner, data = crm
    broken = "<?php\nreturn 'not an array';\n"
    put(broken)
    r = run("--apply")
    assert r.returncode == 1
    assert (data / "config-internal.php").read_text() == broken
    assert not list(data.glob("config-internal.php.bak-*"))


def test_an_override_file_that_wins_fails_the_apply(crm):
    # Review finding 11-05-26: the apply must not report success when an
    # override file sets the key the other way.
    put, run, php, owner, data = crm
    (data / "config-internal-override.php").write_text(
        "<?php\nreturn [\n  'authApiUserLogDisabled' => false,\n];\n")
    put(SAMPLE)
    r = run("--apply")
    assert r.returncode == 1
    assert "NOT in force" in r.stderr


def test_a_file_not_owned_by_www_data_is_refused(crm):
    put, run, php, owner, data = crm
    put(SAMPLE, owner="0:0")
    r = run("--apply")
    assert r.returncode == 1
    assert "not www-data" in r.stderr
    assert "authApiUserLogDisabled" not in (data / "config-internal.php").read_text()
