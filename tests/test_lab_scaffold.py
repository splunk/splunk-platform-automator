"""Scaffold a temp lab, parse inventory, and assert the clone is not written."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INIT = PROJECT_ROOT / "bin" / "init_spa_dir.sh"
VALIDATE = PROJECT_ROOT / "bin" / "validate_splunk_config.sh"


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
    """Paths under the clone that a separate lab must not create or change."""
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
            assert not path.exists(), "separate lab wrote %s under the clone" % path
        else:
            assert path.read_bytes() == content, "separate lab modified %s under the clone" % path


def test_separate_lab_inventory_does_not_write_clone(tmp_path):
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    stub = tmp_path / "Software"
    _ensure_software_stubs(stub)

    before = _clone_snapshots()

    env = os.environ.copy()
    env["SPA_HOME"] = str(PROJECT_ROOT)
    env["SPA_LAB_DIR"] = str(lab)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env.pop("ANSIBLE_INVENTORY", None)

    # Fresh inventory dir so a leftover clone inventory is not required.
    ansible_tmp = tmp_path / "ansible_tmp"
    ansible_tmp.mkdir()
    env["ANSIBLE_LOCAL_TEMP"] = str(ansible_tmp)

    cmd = [
        "ansible-inventory",
        "--list",
        "-i",
        str(lab / "config" / "splunk_config.yml"),
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
    assert '"spa_lab_dir"' in parsed.stdout
    assert str(lab) in parsed.stdout
    assert not (lab / "ansible").exists()

    # Lab inventory was created; clone inventory/hosts was not.
    assert (lab / "inventory" / "hosts").is_file()
    _assert_clone_untouched(before)


def test_validate_separate_lab(tmp_path):
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    stub = PROJECT_ROOT / "tests" / "fixtures" / "baseconfig"
    _ensure_software_stubs(stub)

    before = _clone_snapshots()
    env = os.environ.copy()
    env["SPA_HOME"] = str(PROJECT_ROOT)
    env["SPA_LAB_DIR"] = str(lab)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible_tmp")
    collections = PROJECT_ROOT / "tests" / ".collections"
    if collections.is_dir():
        env["ANSIBLE_COLLECTIONS_PATH"] = str(collections)
    (tmp_path / "ansible_tmp").mkdir()

    validated = subprocess.run(
        [str(VALIDATE), str(lab / "config" / "splunk_config.yml")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    out = validated.stderr + validated.stdout
    assert "Schema OK" in out, out
    assert "Inventory OK" in out, out
    assert "License role pairing OK" in out, out
    if validated.returncode != 0:
        # deploy_site.yml syntax-check needs ansible.windows (win_stat). That
        # collection is not in requirements.yml; do not treat it as an M1 miss.
        assert "win_stat" in out, out
    _assert_clone_untouched(before)


def test_clone_equal_inventory_still_parses(tmp_path):
    """Unset roots keep today's checkout layout (existing suite contract)."""
    stub = PROJECT_ROOT / "tests" / "fixtures" / "baseconfig"
    _ensure_software_stubs(stub)
    env = os.environ.copy()
    env.pop("SPA_HOME", None)
    env.pop("SPA_LAB_DIR", None)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible_tmp")
    os.makedirs(env["ANSIBLE_LOCAL_TEMP"], exist_ok=True)

    # Copy so the plugin's aws_ec2.yml sidecar does not land under examples/.
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


def test_create_linkpage_writes_lab_not_clone(tmp_path):
    """create_linkpage.yml must write $SPA_LAB_DIR/config/index.html even when CWD is the lab."""
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    stub = tmp_path / "Software"
    _ensure_software_stubs(stub)

    clone_index = PROJECT_ROOT / "config" / "index.html"
    clone_index_before = clone_index.read_bytes() if clone_index.is_file() else None
    before = _clone_snapshots()

    env = os.environ.copy()
    env["SPA_HOME"] = str(PROJECT_ROOT)
    env["SPA_LAB_DIR"] = str(lab)
    env["SPA_SOFTWARE_DIR"] = str(stub)
    env["SPA_BASECONFIG_DIR"] = str(stub)
    env["ANSIBLE_CONFIG"] = str(PROJECT_ROOT / "ansible.cfg")
    env["ANSIBLE_INVENTORY"] = str(lab / "config" / "splunk_config.yml")
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible_tmp")
    os.makedirs(env["ANSIBLE_LOCAL_TEMP"], exist_ok=True)
    collections = PROJECT_ROOT / "tests" / ".collections"
    if collections.is_dir():
        env["ANSIBLE_COLLECTIONS_PATH"] = str(collections)

    played = subprocess.run(
        ["ansible-playbook", str(PROJECT_ROOT / "ansible" / "create_linkpage.yml")],
        cwd=lab,
        capture_output=True,
        text=True,
        env=env,
    )
    assert played.returncode == 0, played.stderr + played.stdout
    assert (lab / "config" / "index.html").is_file()
    html = (lab / "config" / "index.html").read_text(encoding="utf-8")
    assert "Splunk Platform Automator Host List" in html

    if clone_index_before is None:
        assert not clone_index.exists(), "link page was written under the clone"
    else:
        assert clone_index.read_bytes() == clone_index_before
    _assert_clone_untouched(before)
