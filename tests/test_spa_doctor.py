"""Tests for bin/spa_doctor.sh host prerequisite checks."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = PROJECT_ROOT / "bin" / "spa_doctor.sh"
INIT = PROJECT_ROOT / "bin" / "init_spa_dir.sh"


def test_doctor_bash_syntax():
    assert subprocess.run(["bash", "-n", str(DOCTOR)], cwd=PROJECT_ROOT).returncode == 0


def test_doctor_passes_on_dev_machine():
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "python3" in (result.stdout + result.stderr).lower()


def test_doctor_warns_when_spash_comes_from_another_clone(tmp_path):
    other_bin = tmp_path / "other-clone" / "bin"
    other_bin.mkdir(parents=True)
    (other_bin / "spash").write_text("#!/bin/sh\nexit 0\n")
    (other_bin / "spash").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(other_bin) + os.pathsep + env["PATH"]
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    output = result.stdout + result.stderr
    assert str(other_bin / "spash") in output
    assert "another checkout wins" in output


def test_doctor_ok_when_spash_comes_from_spa_home(tmp_path):
    env = os.environ.copy()
    env["PATH"] = str(PROJECT_ROOT / "bin") + os.pathsep + env["PATH"]
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"spash resolves to {PROJECT_ROOT}/bin/spash" in result.stdout


def test_doctor_aws_strict_fails_without_terraform(tmp_path, monkeypatch):
    """When --aws is set and terraform is absent, doctor must fail."""
    if shutil.which("terraform"):
        pytest.skip("terraform is installed")
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT), "--aws"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "terraform" in (result.stdout + result.stderr).lower()


def test_init_runs_doctor_by_default(tmp_path):
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "cm_2idxc_sh_uf_aws.yml", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    out = result.stderr + result.stdout
    assert "SPA host prerequisites" in out
    if result.returncode != 0:
        assert "terraform" in out.lower()


def test_init_skip_doctor(tmp_path):
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SPA host prerequisites" not in (result.stdout + result.stderr)


def test_doctor_skips_vagrant_without_virtualbox(tmp_path):
    lab = tmp_path / "lab"
    subprocess.run(
        [str(INIT), "--example", "cm_2idxc_sh_uf_aws.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT), "--lab", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    assert "vagrant" not in out.lower()


def test_doctor_warns_when_hook_missing(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    assert "direnv" in out.lower()
    if shutil.which("direnv"):
        assert "fix-direnv" in out or "shell" in out.lower()


def test_doctor_fix_direnv_writes_zshrc(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT), "--fix-direnv"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    zshrc = tmp_path / ".zshrc"
    assert zshrc.is_file()
    assert "direnv hook zsh" in zshrc.read_text()


def test_doctor_ok_when_hook_in_sourced_zshrc(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    nested = tmp_path / ".config" / "zsh" / "extra.zsh"
    nested.parent.mkdir(parents=True)
    nested.write_text('eval "$(direnv hook zsh)"\n')
    (tmp_path / ".zshrc").write_text('source "$HOME/.config/zsh/extra.zsh"\n')
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    if not shutil.which("direnv"):
        pytest.skip("direnv not installed")
    assert "set up in your shell" in out or "environment is loaded" in out
    assert "does not load it yet" not in out


def test_doctor_fix_direnv_skips_when_nested_hook_exists(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    nested = tmp_path / ".zsh" / "direnv.zsh"
    nested.parent.mkdir(parents=True)
    nested.write_text('eval "$(direnv hook zsh)"\n')
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("source ~/.zsh/direnv.zsh\n")
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT), "--fix-direnv"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "direnv hook" not in zshrc.read_text()
    assert "Added direnv" not in (result.stdout + result.stderr)


def test_doctor_ok_when_hook_present(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    (tmp_path / ".zshrc").write_text('eval "$(direnv hook zsh)"\n')
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    if not shutil.which("direnv"):
        pytest.skip("direnv not installed")
    assert "set up in your shell" in out or "environment is loaded" in out
    assert "does not load it yet" not in out


def test_doctor_virtualbox_requires_vagrant(tmp_path):
    lab = tmp_path / "lab"
    subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        [str(DOCTOR), "--spa-home", str(PROJECT_ROOT), "--lab", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    assert "vagrant" in out.lower()
    if result.returncode != 0:
        assert "virtualbox" in out.lower() or "vagrant" in out.lower()
