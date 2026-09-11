"""Tests for spa doctor host prerequisite checks."""

import os
import shutil
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, spa_env

pytestmark = pytest.mark.local


def test_doctor_passes_on_dev_machine():
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "python3" in (result.stdout + result.stderr).lower()


def test_doctor_warns_when_spa_comes_from_another_clone(tmp_path):
    other_bin = tmp_path / "other-clone" / "bin"
    other_bin.mkdir(parents=True)
    (other_bin / "spa").write_text("#!/bin/sh\nexit 0\n")
    (other_bin / "spa").chmod(0o755)
    env = spa_env()
    env["PATH"] = str(other_bin) + os.pathsep + env["PATH"]
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    output = result.stdout + result.stderr
    assert str(other_bin / "spa") in output
    assert "another checkout wins" in output


def test_doctor_ok_when_spa_comes_from_spa_home():
    env = spa_env()
    env["PATH"] = str(PROJECT_ROOT / "bin") + os.pathsep + env["PATH"]
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"spa resolves to {PROJECT_ROOT}/bin/spa" in result.stdout


def test_doctor_aws_strict_fails_without_terraform():
    if shutil.which("terraform"):
        pytest.skip("terraform is installed")
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--aws"], env=env)
    assert result.returncode != 0
    assert "terraform" in (result.stdout + result.stderr).lower()


def test_init_runs_doctor_by_default(tmp_path):
    dest = tmp_path / "env"
    result = run_spa(["init", "--example", "cm_2idxc_sh_uf_aws.yml", str(dest)])
    out = result.stderr + result.stdout
    assert "SPA host prerequisites" in out
    if result.returncode != 0:
        assert "terraform" in out.lower()


def test_init_skip_doctor(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SPA host prerequisites" not in (result.stdout + result.stderr)


def test_doctor_skips_vagrant_without_virtualbox(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "cm_2idxc_sh_uf_aws.yml", "--skip-doctor", str(dest)])
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "vagrant required" not in out.lower()
    assert "vagrant is on PATH" not in out


def test_doctor_reports_incomplete_venv_for_the_env_under_test(tmp_path):
    """--env decides which .venv is checked, not the caller's SPA_ENV_DIR."""
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    (dest / ".venv" / "include").mkdir(parents=True)
    other = tmp_path / "other"
    (other / ".venv" / "include").mkdir(parents=True)
    env = spa_env({"SPA_ENV_DIR": str(other)})
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "incomplete venv at %s" % (dest / ".venv") in out
    assert str(other / ".venv") not in out


def test_doctor_warns_when_hook_missing(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    assert "direnv" in out.lower()
    if shutil.which("direnv"):
        assert "fix-direnv" in out or "shell" in out.lower()


def test_doctor_fix_direnv_writes_zshrc(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--fix-direnv"], env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    zshrc = tmp_path / ".zshrc"
    assert zshrc.is_file()
    assert "direnv hook zsh" in zshrc.read_text()


def test_doctor_ok_when_hook_in_sourced_zshrc(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    nested = tmp_path / ".config" / "zsh" / "extra.zsh"
    nested.parent.mkdir(parents=True)
    nested.write_text('eval "$(direnv hook zsh)"\n')
    (tmp_path / ".zshrc").write_text('source "$HOME/.config/zsh/extra.zsh"\n')
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    if not shutil.which("direnv"):
        pytest.skip("direnv not installed")
    assert "set up in your shell" in out or "environment is loaded" in out
    assert "does not load it yet" not in out


def test_doctor_fix_direnv_skips_when_nested_hook_exists(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    nested = tmp_path / ".zsh" / "direnv.zsh"
    nested.parent.mkdir(parents=True)
    nested.write_text('eval "$(direnv hook zsh)"\n')
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("source ~/.zsh/direnv.zsh\n")
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--fix-direnv"], env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "direnv hook" not in zshrc.read_text()
    assert "Added direnv" not in (result.stdout + result.stderr)


def test_doctor_ok_when_hook_present(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    (tmp_path / ".zshrc").write_text('eval "$(direnv hook zsh)"\n')
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    if not shutil.which("direnv"):
        pytest.skip("direnv not installed")
    assert "set up in your shell" in out or "environment is loaded" in out
    assert "does not load it yet" not in out


def test_doctor_virtualbox_requires_vagrant(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "vagrant" in out.lower()
    if result.returncode != 0:
        assert "virtualbox" in out.lower() or "vagrant" in out.lower()
