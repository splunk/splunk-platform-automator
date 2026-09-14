"""Scaffold a temp env, parse inventory, and assert the clone is not written."""

import os
import subprocess
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, spa_env

pytestmark = pytest.mark.local


def _ensure_software_stubs(stub_dir: Path) -> None:
    (stub_dir / "spa_ci_stub" / "org_ds_secure_server").mkdir(parents=True, exist_ok=True)
    (stub_dir / "spa_ci_stub" / "org_cluster_manager_base").mkdir(parents=True, exist_ok=True)
    for name in (
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
        "splunk-9.4.0-ci-linux-amd64.tgz",
        "splunkforwarder-9.4.0-ci-linux-amd64.tgz",
    ):
        path = stub_dir / name
        if not path.exists():
            path.write_text("# CI stub\n", encoding="utf-8")


def _clone_snapshots():
    return {
        PROJECT_ROOT / "inventory" / "hosts": (
            (PROJECT_ROOT / "inventory" / "hosts").read_bytes()
            if (PROJECT_ROOT / "inventory" / "hosts").is_file()
            else None
        ),
        PROJECT_ROOT / "terraform" / "aws" / "terraform.tfvars": (
            (PROJECT_ROOT / "terraform" / "aws" / "terraform.tfvars").read_bytes()
            if (PROJECT_ROOT / "terraform" / "aws" / "terraform.tfvars").is_file()
            else None
        ),
        PROJECT_ROOT / "config" / "aws_ec2.yml": (
            (PROJECT_ROOT / "config" / "aws_ec2.yml").read_bytes()
            if (PROJECT_ROOT / "config" / "aws_ec2.yml").is_file()
            else None
        ),
    }


def _assert_clone_untouched(before):
    for path, content in before.items():
        if content is None:
            assert not path.exists(), "separate env wrote %s under the clone" % path
        else:
            assert path.read_bytes() == content, "separate env modified %s under the clone" % path


def test_separate_env_inventory_does_not_write_clone(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr

    stub = tmp_path / "Software"
    _ensure_software_stubs(stub)

    before = _clone_snapshots()

    env = spa_env()
    env["SPA_HOME"] = str(PROJECT_ROOT)
    env["SPA_ENV_DIR"] = str(dest)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env.pop("ANSIBLE_INVENTORY", None)

    ansible_tmp = tmp_path / "ansible_tmp"
    ansible_tmp.mkdir()
    env["ANSIBLE_LOCAL_TEMP"] = str(ansible_tmp)

    cmd = [
        "ansible-inventory",
        "--list",
        "-i",
        str(dest / "config" / "splunk_config.yml"),
    ]
    parsed = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert parsed.returncode == 0, parsed.stderr + parsed.stdout
    assert '"shidx"' in parsed.stdout
    assert '"spa_env_dir"' in parsed.stdout
    assert str(dest) in parsed.stdout
    assert not (dest / "ansible").exists()

    assert (dest / "inventory" / "hosts").is_file()
    _assert_clone_untouched(before)


def test_validate_separate_env(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr

    stub = PROJECT_ROOT / "tests" / "fixtures" / "baseconfig"
    _ensure_software_stubs(stub)

    before = _clone_snapshots()
    env = spa_env()
    env["SPA_HOME"] = str(PROJECT_ROOT)
    env["SPA_ENV_DIR"] = str(dest)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible_tmp")
    collections = PROJECT_ROOT / "tests" / ".collections"
    if collections.is_dir():
        env["ANSIBLE_COLLECTIONS_PATH"] = str(collections)
    (tmp_path / "ansible_tmp").mkdir()

    validated = run_spa(
        ["validate", str(dest / "config" / "splunk_config.yml")],
        env=env,
    )
    out = validated.stderr + validated.stdout
    assert "Schema OK" in out, out
    assert "Inventory OK" in out, out
    assert "License role pairing OK" in out, out
    if validated.returncode != 0:
        assert "win_stat" in out, out
    _assert_clone_untouched(before)


def test_clone_equal_inventory_still_parses(tmp_path):
    stub = PROJECT_ROOT / "tests" / "fixtures" / "baseconfig"
    _ensure_software_stubs(stub)
    env = spa_env()
    env.pop("SPA_HOME", None)
    env.pop("SPA_ENV_DIR", None)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible_tmp")
    os.makedirs(env["ANSIBLE_LOCAL_TEMP"], exist_ok=True)

    cfg = tmp_path / "splunk_config.yml"
    cfg.write_text((PROJECT_ROOT / "examples" / "single_node.yml").read_text())
    parsed = subprocess.run(
        ["ansible-inventory", "--list", "-i", str(cfg)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert parsed.returncode == 0, parsed.stderr + parsed.stdout
    assert '"shidx"' in parsed.stdout


def test_create_linkpage_writes_env_not_clone(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr

    stub = tmp_path / "Software"
    _ensure_software_stubs(stub)

    clone_index = PROJECT_ROOT / "config" / "index.html"
    clone_index_before = clone_index.read_bytes() if clone_index.is_file() else None
    before = _clone_snapshots()

    env = spa_env()
    env["SPA_HOME"] = str(PROJECT_ROOT)
    env["SPA_ENV_DIR"] = str(dest)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env["ANSIBLE_INVENTORY"] = str(dest / "config" / "splunk_config.yml")
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible_tmp")
    os.makedirs(env["ANSIBLE_LOCAL_TEMP"], exist_ok=True)
    collections = PROJECT_ROOT / "tests" / ".collections"
    if collections.is_dir():
        env["ANSIBLE_COLLECTIONS_PATH"] = str(collections)

    played = subprocess.run(
        ["ansible-playbook", str(PROJECT_ROOT / "ansible" / "create_linkpage.yml")],
        cwd=dest,
        capture_output=True,
        text=True,
        env=env,
    )
    assert played.returncode == 0, played.stderr + played.stdout
    assert (dest / "config" / "index.html").is_file()
    html = (dest / "config" / "index.html").read_text(encoding="utf-8")
    assert "Splunk Platform Automator Host List" in html

    if clone_index_before is None:
        assert not clone_index.exists(), "link page was written under the clone"
    else:
        assert clone_index.read_bytes() == clone_index_before
    _assert_clone_untouched(before)
