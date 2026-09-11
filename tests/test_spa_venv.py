"""Tests for bin/spa_venv.sh (shared venv) and the env .envrc it is wired into.

Venv resolution is checked with --path (no side effects). Creation is checked
with --no-install so no pip/galaxy download is needed.
"""

import os
import subprocess
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa_init, spa_env

pytestmark = pytest.mark.local

SCRIPT = PROJECT_ROOT / "bin" / "spa_venv.sh"


def _run(args, env=None):
    full_env = spa_env()
    full_env.pop("SPA_VENV_DIR", None)
    full_env.pop("SPA_ENV_DIR", None)
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


def test_env_venv_wins_when_present(tmp_path):
    dest = tmp_path / "env"
    (dest / ".venv").mkdir(parents=True)
    result = _run(["--path", "--env", str(dest)])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(dest / ".venv")


def test_env_without_venv_falls_back_to_shared(tmp_path):
    dest = tmp_path / "env"
    dest.mkdir()
    result = _run(["--path", "--env", str(dest)])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_env_override_wins(tmp_path):
    dest = tmp_path / "env"
    (dest / ".venv").mkdir(parents=True)
    explicit = tmp_path / "explicit"
    result = _run(
        ["--path", "--env", str(dest)], env={"SPA_VENV_DIR": str(explicit)}
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
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    envrc = dest / ".envrc"
    assert envrc.is_file()
    body = envrc.read_text()
    assert "spa_venv.sh" in body
    assert "env --export" in body
    assert str(PROJECT_ROOT) in body
    assert subprocess.run(["bash", "-n", str(envrc)]).returncode == 0

    env = spa_env()
    env["SPA_ENV_DIR"] = "/somewhere/else"
    env["SPLUNK_CONFIG_FILE"] = "/somewhere/else/config/splunk_config.yml"
    sourced = subprocess.run(
        ["bash", "-c", 'source .envrc >/dev/null 2>&1; echo "$SPA_ENV_DIR"; echo "$SPLUNK_CONFIG_FILE"'],
        cwd=dest,
        capture_output=True,
        text=True,
        env=env,
    )
    lines = sourced.stdout.split()
    assert lines[0] == str(dest)
    assert lines[1] == str(dest / "config" / "splunk_config.yml")


def test_envrc_puts_spa_home_bin_on_path(tmp_path):
    dest = tmp_path / "env"
    other_bin = tmp_path / "other-clone" / "bin"
    other_bin.mkdir(parents=True)
    (other_bin / "spa").write_text("#!/bin/sh\nexit 0\n")
    (other_bin / "spa").chmod(0o755)
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout

    env = spa_env()
    env["PATH"] = env["PATH"] + os.pathsep + str(other_bin)
    sourced = subprocess.run(
        ["bash", "-c", 'source .envrc >/dev/null 2>&1; command -v spa'],
        cwd=dest,
        capture_output=True,
        text=True,
        env=env,
    )
    assert sourced.stdout.strip() == str(PROJECT_ROOT / "bin" / "spa")


def test_init_no_envrc(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--no-envrc", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (dest / ".envrc").exists()


def test_collections_install_is_forced_into_target_path():
    body = SCRIPT.read_text()
    assert "collection install --force" in body


def test_collections_not_reinstalled_when_present():
    collections = PROJECT_ROOT / ".collections" / "ansible_collections"
    if not (PROJECT_ROOT / ".venv" / "bin" / "activate").is_file() or not collections.is_dir():
        pytest.skip("shared venv/collections not built on this machine")
    result = _run(["--no-create"])
    assert result.returncode == 0, result.stderr
    assert "Installing Ansible collections" not in (result.stdout + result.stderr)


def test_run_venv_wrapper_uses_tests_venv():
    body = (PROJECT_ROOT / "tests" / "run_venv.sh").read_text()
    assert "bin/spa_venv.sh" in body
    assert ".venv" in body
    result = subprocess.run(
        ["bash", "-n", str(PROJECT_ROOT / "tests" / "run_venv.sh")],
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0
