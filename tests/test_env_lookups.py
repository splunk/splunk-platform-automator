"""SPA rejects unset environment lookups before inventory, provision, or deploy."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from spa.api import LocalSpaSession
from spa.paths import resolve_spa_paths
from spa.validate import validate_env
from spa_testutil import PROJECT_ROOT

pytestmark = [pytest.mark.local, pytest.mark.cli]

LOOKUP_CONFIG = """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
custom:
  token: "{{ lookup('env', 'NESTED_TOKEN') }}"
items:
  - "{{ lookup('env', 'LIST_SECRET') }}"
splunk_hosts:
  - name: cm
    roles: [cluster_manager]
"""

LITERAL_CONFIG = """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: kept-literal
splunk_hosts:
  - name: cm
    roles: [cluster_manager]
"""

SENTINEL = "sentinel-secret-value"


def _paths(tmp_path, body):
    config_path = tmp_path / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(body, encoding="utf-8")
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    return replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=tmp_path / "inventory",
        terraform_state_dir=tmp_path / "terraform" / "aws",
        roots_differ=True,
    )


def _clear(monkeypatch):
    for name in ("SPLUNK_ADMIN_PASSWORD", "NESTED_TOKEN", "LIST_SECRET"):
        monkeypatch.delenv(name, raising=False)


def test_validate_names_every_missing_lookup_before_subprocess(tmp_path, monkeypatch):
    """CFG-SEC-003."""
    _clear(monkeypatch)
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", SENTINEL)
    monkeypatch.setenv("LIST_SECRET", "")

    def fail_subprocess(*_args, **_kwargs):
        raise AssertionError("validation continued past the environment-variable gate")

    monkeypatch.setattr("spa.validate.subprocess.run", fail_subprocess)
    result = validate_env(_paths(tmp_path, LOOKUP_CONFIG))
    assert result.ok is False
    assert result.error == (
        "Environment variables required by splunk_config.yml are not set: "
        "LIST_SECRET, NESTED_TOKEN.\n"
        "Export each variable to a non-empty value and rerun the command."
    )
    assert SENTINEL not in result.error
    assert SENTINEL not in json.dumps(result.data)
    assert result.data["steps"] == [
        {
            "id": "env_lookups",
            "ok": False,
            "message": result.error,
        }
    ]
    assert result.data["env_lookups"] == [
        {"name": "LIST_SECRET", "state": "not set"},
        {"name": "NESTED_TOKEN", "state": "not set"},
        {"name": "SPLUNK_ADMIN_PASSWORD", "state": "set"},
    ]


def test_human_validate_prints_the_missing_lookup_message_once(tmp_path, monkeypatch, capsys):
    """CFG-SEC-003. The formatted report already contains the error."""
    _clear(monkeypatch)
    _paths(tmp_path, LOOKUP_CONFIG)
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(tmp_path))
    from spa.cli import _run

    assert _run(["--no-agent", "--start-dir", str(tmp_path), "validate"]) == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert combined.count("are not set:") == 1
    assert combined.count("Export each variable to a non-empty value") == 1


def test_validate_accepts_literal_passwords_and_set_lookups(tmp_path, monkeypatch):
    """CFG-SEC-003."""
    _clear(monkeypatch)
    for name in ("SPLUNK_ADMIN_PASSWORD", "NESTED_TOKEN", "LIST_SECRET"):
        monkeypatch.setenv(name, "present")
    called = {"schema": False}

    def record_subprocess(*_args, **_kwargs):
        called["schema"] = True
        raise SystemExit("stop after the environment-variable gate")

    monkeypatch.setattr("spa.validate.subprocess.run", record_subprocess)
    with pytest.raises(SystemExit, match="environment-variable gate"):
        validate_env(_paths(tmp_path, LOOKUP_CONFIG))
    assert called["schema"] is True

    called["schema"] = False
    with pytest.raises(SystemExit, match="environment-variable gate"):
        validate_env(_paths(tmp_path, LITERAL_CONFIG))
    assert called["schema"] is True


def test_init_reports_readiness_without_values_or_failure(tmp_path, monkeypatch):
    """CFG-SEC-003."""
    monkeypatch.setattr("spa.init.create_venv", lambda *args, **kwargs: None)
    monkeypatch.setattr("spa.init.run_doctor", lambda *args, **kwargs: None)
    monkeypatch.delenv("SPLUNK_IDXC_PASSWORD", raising=False)
    monkeypatch.delenv("SPLUNK_SHC_PASSWORD", raising=False)
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", SENTINEL)
    session = LocalSpaSession(paths=resolve_spa_paths(start_dir=PROJECT_ROOT))
    result = session.init(
        str(tmp_path / "env"),
        example="cm_2idxc1site_3shc_uf",
        example_set=True,
        provider="aws",
        skip_doctor=True,
    )
    assert result.ok is True, result.error
    text = "\n".join(result.data["messages"])
    assert "Environment references:" in text
    assert "SPLUNK_IDXC_PASSWORD: not set" in text
    assert "SPLUNK_SHC_PASSWORD: not set" in text
    assert "SPLUNK_ADMIN_PASSWORD: set" in text
    assert SENTINEL not in text
    assert SENTINEL not in json.dumps(result.data)


def test_provision_and_deploy_stop_before_later_work(tmp_path, monkeypatch):
    """CFG-SEC-003."""
    _clear(monkeypatch)
    monkeypatch.setenv("NESTED_TOKEN", SENTINEL)
    paths = _paths(tmp_path, LOOKUP_CONFIG)
    session = LocalSpaSession(paths=paths)
    called = {"confirm": False, "provider": False, "hosts": False, "playbook": False}

    def confirm(*_args, **_kwargs):
        called["confirm"] = True
        raise AssertionError("confirmation ran")

    def provider(*_args, **_kwargs):
        called["provider"] = True
        raise AssertionError("provider ran")

    def hosts(*_args, **_kwargs):
        called["hosts"] = True
        raise AssertionError("host resolution ran")

    def playbook(*_args, **_kwargs):
        called["playbook"] = True
        raise AssertionError("ansible ran")

    monkeypatch.setattr("spa.confirm.ensure_confirmed", confirm)
    monkeypatch.setattr("spa.providers.get_provider", provider)
    monkeypatch.setattr("spa.hosts.resolve_hosts", hosts)
    monkeypatch.setattr("spa.playbooks.run_playbook", playbook)

    provision = session.provision(confirm=True)
    deploy = session.deploy(confirm=True)
    for result in (provision, deploy):
        assert result.ok is False
        assert result.error == (
            "Environment variables required by splunk_config.yml are not set: "
            "LIST_SECRET, SPLUNK_ADMIN_PASSWORD.\n"
            "Export each variable to a non-empty value and rerun the command."
        )
        assert SENTINEL not in result.error
        assert SENTINEL not in json.dumps(result.data)
    assert called == {"confirm": False, "provider": False, "hosts": False, "playbook": False}


def test_user_guide_explains_required_environment_references():
    """CFG-SEC-003."""
    guide = (PROJECT_ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    assert "export the variable to a non-empty value" in guide
    assert "spa validate" in guide
    assert "SPLUNK_ADMIN_PASSWORD" in guide
