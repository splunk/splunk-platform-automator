"""Tests for spa config move role and spa config move host."""

from __future__ import annotations

import json

import pytest
import yaml

from spa_testutil import run_spa, run_spa_init

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _cfg(env_dir):
    return yaml.safe_load((env_dir / "config" / "splunk_config.yml").read_text())


def _roles(cfg, name):
    for host in cfg["splunk_hosts"]:
        if host.get("name") == name:
            return list(host.get("roles") or [])
    return []


def test_bare_config_move_names_role_and_host():
    result = run_spa(["--no-agent", "config", "move"])
    assert result.returncode == 2
    assert "spa config move role" in result.stderr
    assert "spa config move host" in result.stderr


def test_move_role_relocates_monitoring_console(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    result = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "role",
            "monitoring_console",
            "--from",
            "cm",
            "--to",
            "mc",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["changed"] is True
    cfg = _cfg(dest)
    assert "monitoring_console" not in _roles(cfg, "cm")
    assert _roles(cfg, "mc") == ["monitoring_console"]
    names = [host.get("name") for host in cfg["splunk_hosts"]]
    assert "mc" in names
    assert "cm" in names


def test_move_role_requires_from(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    result = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "role",
            "monitoring_console",
            "--to",
            "mc",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 2


def test_move_host_renames_one_identity(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    result = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "host",
            "cm",
            "--to",
            "acme-cm",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    cfg = _cfg(dest)
    names = [host.get("name") for host in cfg["splunk_hosts"] if host.get("name")]
    assert "acme-cm" in names
    assert "cm" not in names


def test_move_host_prefix_is_idempotent(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    first = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "host",
            "--prefix",
            "acme-",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert first.returncode == 0, first.stderr
    second = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "host",
            "--prefix",
            "acme-",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert second.returncode == 0, second.stderr
    cfg = _cfg(dest)
    names = []
    for host in cfg["splunk_hosts"]:
        if host.get("name"):
            names.append(host["name"])
        iteration = host.get("iter") or {}
        if iteration.get("prefix"):
            names.append(iteration["prefix"])
    assert names
    assert all(item.startswith("acme-") for item in names)
    assert not any(item.startswith("acme-acme-") for item in names)


def test_move_host_postfix_is_idempotent(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    first = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "host",
            "--postfix=-lab",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert first.returncode == 0, first.stderr
    second = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "move",
            "host",
            "--postfix=-lab",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert second.returncode == 0, second.stderr
    cfg = _cfg(dest)
    names = []
    iter_postfixes = []
    for host in cfg["splunk_hosts"]:
        if host.get("name"):
            names.append(host["name"])
        iteration = host.get("iter") or {}
        if iteration:
            assert not str(iteration.get("prefix") or "").endswith("-lab")
            iter_postfixes.append(str(iteration.get("postfix") or ""))
    assert names
    assert all(item.endswith("-lab") for item in names)
    assert not any(item.endswith("-lab-lab") for item in names)
    assert iter_postfixes
    assert all(item.endswith("-lab") for item in iter_postfixes)
    assert not any(item.endswith("-lab-lab") for item in iter_postfixes)
