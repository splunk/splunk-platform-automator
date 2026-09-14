"""Framework tarball and install.sh (Distribution M3)."""

import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from spa_testutil import PROJECT_ROOT, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

PACK = PROJECT_ROOT / "scripts" / "pack-framework.sh"
INSTALL = PROJECT_ROOT / "install.sh"


def _pack(tmp_path: Path) -> Path:
    out = tmp_path / "spa-framework.tgz"
    result = subprocess.run(
        ["bash", str(PACK), "-o", str(out)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert out.is_file()
    return out


def test_pack_framework_excludes_tests_and_lab_config(tmp_path):
    archive = _pack(tmp_path)
    names = [
        name[2:] if name.startswith("./") else name
        for name in tarfile.open(archive).getnames()
    ]
    assert "ansible.cfg" in names
    assert "bin/spa" in names
    assert "install.sh" in names
    assert "defaults/aws.yml" in names
    assert "template/terraform_aws.tfvars.j2" in names
    assert not any(n == "tests" or n.startswith("tests/") for n in names)
    assert not any(n.startswith(".git/") or n == ".git" for n in names)
    assert "config/splunk_config.yml" not in names
    assert not any(n.startswith("inventory/") for n in names)


def test_install_from_tarball_and_extract_anywhere(tmp_path):
    archive = _pack(tmp_path)
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    result = subprocess.run(
        [
            "bash",
            str(INSTALL),
            "--from",
            str(archive),
            "--prefix",
            str(prefix),
            "--bindir",
            str(bindir),
            "--skip-venv",
            "--skip-doctor",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (prefix / "bin" / "spa").is_file()
    assert (prefix / "ansible.cfg").is_file()
    assert not (prefix / "tests").exists()
    wrapper = bindir / "spa"
    assert wrapper.is_file()
    text = wrapper.read_text()
    assert str(prefix) in text
    assert "GITHUB_TOKEN" not in text

    env = spa_env()
    env["PYTHONPATH"] = str(prefix / "lib")
    env["SPA_HOME"] = str(prefix)
    help_run = subprocess.run(
        [sys.executable, str(prefix / "bin" / "spa"), "--help"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(prefix),
    )
    assert help_run.returncode == 0, help_run.stderr + help_run.stdout
    assert "init" in help_run.stdout

    extract = tmp_path / "anywhere"
    extract.mkdir()
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(extract)], check=True)
    # spa init creates SPA_HOME/.venv when missing; stub activate so tests skip pip.
    activate = extract / ".venv" / "bin" / "activate"
    activate.parent.mkdir(parents=True)
    activate.write_text("# test stub\n")
    env["PYTHONPATH"] = str(extract / "lib")
    env["SPA_HOME"] = str(extract)
    dest = tmp_path / "env"
    init = subprocess.run(
        [
            sys.executable,
            str(extract / "bin" / "spa"),
            "init",
            "--skip-doctor",
            "--example",
            "single_node.yml",
            str(dest),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(extract),
    )
    assert init.returncode == 0, init.stderr + init.stdout
    spa_yml = yaml.safe_load((dest / ".spa.yml").read_text())
    assert Path(spa_yml["spa_home"]).resolve() == extract.resolve()
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert not (dest / "ansible").exists()


def test_install_refuses_existing_prefix_without_force(tmp_path):
    archive = _pack(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "keep.txt").write_text("no")
    result = subprocess.run(
        [
            "bash",
            str(INSTALL),
            "--from",
            str(archive),
            "--prefix",
            str(prefix),
            "--bindir",
            str(tmp_path / "bin"),
            "--skip-venv",
            "--skip-doctor",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert (prefix / "keep.txt").read_text() == "no"
