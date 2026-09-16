"""In-process SpaSession contract (GUI/backend), not the spa CLI."""

import json
import inspect
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT, run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.api import (  # noqa: E402
    SCHEMA_VERSION,
    CommandResult,
    LocalSpaSession,
    RemoteSessionNotImplemented,
    SpaSession,
    jsonable,
    open_session,
)
from spa.agent import envelope  # noqa: E402


SESSION_API_PARAMETERS = {
    "schema": (),
    "env": (),
    "catalog": ("extra_dir",),
    "describe_playbook": ("name", "extra_dir"),
    "validate": ("config", "check_licenses", "splunk_config_aws"),
    "doctor": ("spa_home", "env_dir", "aws", "virtualbox", "strict", "fix_direnv"),
    "init": (
        "env_dir",
        "example",
        "example_set",
        "from_dir",
        "migrate_set",
        "keep_source",
        "force",
        "env_venv",
        "python",
        "ansible",
        "pip_pkgs",
        "write_envrc_file",
        "skip_doctor",
        "rebuild_venv",
        "software_dir",
        "baseconfig_dir",
        "apps_dir",
        "provider",
    ),
    "list_examples": (),
    "features": ("action", "ident", "query", "include_keys"),
    "provision": ("extra", "confirm", "agent"),
    "destroy": ("extra", "confirm", "agent"),
    "deploy": ("extra", "verbose", "hosts", "confirm", "agent", "skip_provision_check"),
    "suspend": ("confirm", "wait", "agent", "hosts"),
    "resume": ("confirm", "wait", "agent", "hosts"),
    "run": ("name", "extra", "extra_dir", "verbose", "hosts", "confirm", "agent"),
    "aws": ("argv",),
    "licenses": ("software_dir", "config", "env_recommend"),
    "hosts_list": ("status", "hosts"),
    "shell_list": ("verbose", "hosts"),
}


def test_open_session_rejects_remote_url():
    with pytest.raises(RemoteSessionNotImplemented):
        open_session(url="https://controller.example")


def test_local_session_implements_the_runtime_protocol():
    session = open_session(start_dir=str(PROJECT_ROOT))
    assert isinstance(session, SpaSession)


def test_session_api_surface_is_stable_and_remote_implementable():
    """A later RemoteSpaSession must expose exactly this public port."""
    protocol_methods = {
        name
        for name, value in SpaSession.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
    assert protocol_methods == set(SESSION_API_PARAMETERS)

    for name, expected in SESSION_API_PARAMETERS.items():
        protocol = inspect.signature(getattr(SpaSession, name))
        local = inspect.signature(getattr(LocalSpaSession, name))
        protocol_parameters = tuple(item for item in protocol.parameters if item != "self")
        local_parameters = tuple(item for item in local.parameters if item != "self")
        assert protocol_parameters == expected, name
        assert local_parameters == expected, name
        for parameter in expected:
            assert (
                protocol.parameters[parameter].default
                == local.parameters[parameter].default
            ), (name, parameter)


def test_transport_envelope_matches_command_result_contract():
    success = CommandResult(ok=True, data={"value": 1})
    failure = CommandResult(ok=False, error="failed")
    assert success.to_dict() == envelope(True, data={"value": 1})
    assert failure.to_dict() == envelope(False, error="failed")
    assert success.to_dict() == {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "data": {"value": 1},
    }
    assert failure.to_dict() == {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "error": "failed",
    }


def test_command_result_is_json_serializable():
    from pathlib import Path
    from datetime import datetime, timezone

    result = CommandResult(
        ok=True,
        data={"path": Path("/tmp/env"), "when": datetime(2026, 1, 2, tzinfo=timezone.utc)},
    )
    json.dumps(result.to_dict())
    assert result.data["path"] == "/tmp/env"
    assert result.data["when"].startswith("2026-01-02")


def test_jsonable_roundtrip():
    payload = jsonable({"ok": True, "items": (1, 2), "nested": {"a": True}})
    json.dumps(payload)


def test_session_list_examples_no_stdout(capsys):
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.list_examples()
    assert result.ok
    ids = [item["id"] for item in result.data["topologies"]]
    assert "single_node" in ids
    assert "cm_2idxc_sh_uf" in ids
    providers = [item["id"] for item in result.data["providers"]]
    assert "aws" in providers
    assert "virtualbox" in providers
    json.dumps(result.data)
    assert capsys.readouterr().out == ""


def test_session_catalog_jsonable():
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.catalog()
    assert result.ok
    json.dumps(result.data)
    names = {row["name"] for row in result.data}
    assert "deploy_site" in names


def test_session_schema_version():
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.schema()
    assert result.ok
    assert result.data["schema_version"] == SCHEMA_VERSION
    assert result.data["name"] == "spa"


def test_session_validate_missing_config(capsys, monkeypatch):
    monkeypatch.delenv("SPLUNK_CONFIG_FILE", raising=False)
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.validate(config=str(PROJECT_ROOT / "does-not-exist.yml"))
    assert not result.ok
    assert "not found" in (result.error or "").lower()
    json.dumps(result.data)
    assert capsys.readouterr().out == ""


def test_session_doctor_jsonable(capsys):
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.doctor(spa_home=str(PROJECT_ROOT))
    assert result.data["checks"]
    json.dumps(result.data)
    assert capsys.readouterr().out == ""


def test_cli_validate_json_envelope():
    result = run_spa(["--json", "validate", str(PROJECT_ROOT / "does-not-exist.yml")])
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "not found" in (payload.get("error") or "").lower()
    assert "config_file" in (payload.get("data") or {})


def test_cli_doctor_json_has_checks():
    result = run_spa(["--json", "doctor", "--spa-home", str(PROJECT_ROOT)])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["checks"]
    assert payload["data"]["spa_home"]


def test_cli_agent_schema_version():
    result = run_spa(["agent", "schema"])
    payload = json.loads(result.stdout)
    assert payload["data"]["schema_version"] == SCHEMA_VERSION


def test_session_init_messages(tmp_path, capsys):
    dest = tmp_path / "env"
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.init(
        str(dest),
        example="single_node.yml",
        example_set=True,
        skip_doctor=True,
    )
    assert result.ok, result.error
    assert result.data["env_dir"] == str(dest.resolve())
    assert result.data["messages"]
    json.dumps(result.data)
    assert capsys.readouterr().out == ""
    assert (dest / "config" / "splunk_config.yml").is_file()
