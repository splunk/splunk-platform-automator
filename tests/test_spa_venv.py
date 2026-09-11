"""Tests for bin/spa_venv.sh (shared venv) and the lab .envrc it is wired into.

Venv resolution is checked with --path (no side effects). Creation is checked
with --no-install so no pip/galaxy download is needed.
"""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "bin" / "spa_venv.sh"
INIT = PROJECT_ROOT / "bin" / "init_spa_dir.sh"


def _run(args, env=None):
    full_env = os.environ.copy()
    # A venv activated by the test runner must not leak into resolution tests.
    full_env.pop("SPA_VENV_DIR", None)
    full_env.pop("SPA_LAB_DIR", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_venv_script_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], cwd=PROJECT_ROOT)
    assert result.returncode == 0


def test_path_defaults_to_shared_venv():
    result = _run(["--path"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_lab_venv_wins_when_present(tmp_path):
    lab = tmp_path / "lab"
    (lab / ".venv").mkdir(parents=True)
    result = _run(["--path", "--lab", str(lab)])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(lab / ".venv")


def test_lab_without_venv_falls_back_to_shared(tmp_path):
    lab = tmp_path / "lab"
    lab.mkdir()
    result = _run(["--path", "--lab", str(lab)])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_env_override_wins(tmp_path):
    lab = tmp_path / "lab"
    (lab / ".venv").mkdir(parents=True)
    explicit = tmp_path / "explicit"
    result = _run(
        ["--path", "--lab", str(lab)], env={"SPA_VENV_DIR": str(explicit)}
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(explicit)


def test_dir_flag_wins_over_env(tmp_path):
    result = _run(
        ["--path", "--dir", str(tmp_path / "flag")],
        env={"SPA_VENV_DIR": str(tmp_path / "env")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path / "flag")


def test_create_without_install(tmp_path):
    venv = tmp_path / "venv"
    result = _run(["--create", "--no-install", "--dir", str(venv)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (venv / "bin" / "activate").is_file()


def test_incomplete_venv_is_recreated(tmp_path):
    """A half-created venv (interrupted install) must not be sourced as-is."""
    venv = tmp_path / "broken"
    (venv / "include").mkdir(parents=True)
    result = _run(["--create", "--no-install", "--dir", str(venv)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "recreating" in (result.stderr + result.stdout)
    assert (venv / "bin" / "activate").is_file()


def test_incomplete_venv_reported_with_no_create(tmp_path):
    venv = tmp_path / "broken"
    (venv / "include").mkdir(parents=True)
    result = _run(["--no-create", "--dir", str(venv)])
    assert result.returncode != 0
    assert "incomplete venv" in result.stderr


def test_no_create_does_not_create(tmp_path):
    venv = tmp_path / "missing"
    result = _run(["--no-create", "--dir", str(venv)])
    assert not venv.exists()
    assert "no venv at" in (result.stderr + result.stdout)


def test_unknown_option_fails():
    result = _run(["--nope"])
    assert result.returncode != 0
    assert "Unknown option" in result.stderr


def test_init_writes_envrc(tmp_path):
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    envrc = lab / ".envrc"
    assert envrc.is_file()
    body = envrc.read_text()
    assert "spa_venv.sh" in body
    assert "spa_env.sh" in body
    assert str(PROJECT_ROOT) in body
    assert subprocess.run(["bash", "-n", str(envrc)]).returncode == 0

    # A stale SPA_LAB_DIR / SPLUNK_CONFIG_FILE from another lab must not win.
    env = os.environ.copy()
    env["SPA_LAB_DIR"] = "/somewhere/else"
    env["SPLUNK_CONFIG_FILE"] = "/somewhere/else/config/splunk_config.yml"
    sourced = subprocess.run(
        ["bash", "-c", 'source .envrc >/dev/null 2>&1; echo "$SPA_LAB_DIR"; echo "$SPLUNK_CONFIG_FILE"'],
        cwd=lab,
        capture_output=True,
        text=True,
        env=env,
    )
    lines = sourced.stdout.split()
    assert lines[0] == str(lab)
    assert lines[1] == str(lab / "config" / "splunk_config.yml")


def test_envrc_puts_spa_home_bin_on_path(tmp_path):
    """A lab has no bin/, so .envrc must supply SPA_HOME/bin, ahead of any other clone."""
    lab = tmp_path / "lab"
    other_bin = tmp_path / "other-clone" / "bin"
    other_bin.mkdir(parents=True)
    (other_bin / "spash").write_text("#!/bin/sh\nexit 0\n")
    (other_bin / "spash").chmod(0o755)
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    env = os.environ.copy()
    env["PATH"] = env["PATH"] + os.pathsep + str(other_bin)
    sourced = subprocess.run(
        ["bash", "-c", 'source .envrc >/dev/null 2>&1; command -v spash'],
        cwd=lab,
        capture_output=True,
        text=True,
        env=env,
    )
    assert sourced.stdout.strip() == str(PROJECT_ROOT / "bin" / "spash")


def test_init_no_envrc(tmp_path):
    lab = tmp_path / "lab"
    result = subprocess.run(
        [str(INIT), "--example", "single_node.yml", "--no-envrc", "--skip-doctor", str(lab)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (lab / ".envrc").exists()


def test_collections_install_is_forced_into_target_path():
    """galaxy says 'nothing to do' when ~/.ansible has them; the target must still fill."""
    body = SCRIPT.read_text()
    assert "collection install --force" in body


def test_collections_not_reinstalled_when_present():
    """Detection must match the on-disk namespace/name, or every activation reinstalls."""
    collections = PROJECT_ROOT / ".collections" / "ansible_collections"
    if not (PROJECT_ROOT / ".venv" / "bin" / "activate").is_file() or not collections.is_dir():
        pytest.skip("shared venv/collections not built on this machine")
    result = _run(["--no-create"])
    assert result.returncode == 0, result.stderr
    assert "Installing Ansible collections" not in (result.stdout + result.stderr)


def test_run_venv_wrapper_uses_tests_venv():
    """tests/run_venv.sh must stay on tests/.venv, not the shared venv."""
    body = (PROJECT_ROOT / "tests" / "run_venv.sh").read_text()
    assert "bin/spa_venv.sh" in body
    assert ".venv" in body
    result = subprocess.run(
        ["bash", "-n", str(PROJECT_ROOT / "tests" / "run_venv.sh")],
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0
