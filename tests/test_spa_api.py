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
    "validate": ("config", "check_licenses", "splunk_config", "agent"),
    "doctor": ("spa_home", "env_dir", "provider", "strict"),
    "skills": ("action", "platform", "name", "all_packages", "confirm", "agent"),
    "venv": ("action", "environment", "python", "no_install", "confirm", "agent"),
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
        "skip_doctor",
        "rebuild_venv",
        "software_dir",
        "baseconfig_dir",
        "apps_dir",
        "provider",
        "registry_name",
        "architecture",
    ),
    "list_examples": (),
    "environment_list": (),
    "environment_set": (
        "env_dir",
        "provider",
        "software_dir",
        "baseconfig_dir",
        "apps_dir",
        "default",
    ),
    "environment_remove": ("name", "confirm", "force"),
    "environment_cleanup": ("confirm", "agent"),
    "config": (
        "action",
        "paths",
        "value",
        "operand",
        "file",
        "value_file",
        "from_env",
        "from_env_fields",
        "explicit_default",
        "effective",
        "full",
        "dry_run",
        "expect_revision",
        "resolve",
        "resolve_file",
        "stdin_text",
        "confirm",
        "agent",
        "check_hand_edits",
        "header_fields",
        "move_role",
        "move_from",
        "move_to",
        "move_prefix",
        "move_postfix",
    ),
    "architecture_plan": ("path",),
    "architecture_apply": ("path", "confirm", "agent", "dry_run", "expect_revision"),
    "architecture_check": ("path",),
    "apps": (
        "action",
        "query",
        "app_id",
        "limit",
        "app_type",
        "kind",
        "version",
        "roles",
        "source",
        "extract",
        "overwrite",
        "customize",
        "set_values",
        "explicit_default",
        "content_packs",
        "install_all_content_packs",
        "content_pack",
        "archive",
        "force_new",
        "dry_run",
        "expect_revision",
        "resolve",
        "resolve_file",
        "stdin_text",
        "confirm",
        "agent",
    ),
    "provision": (
        "extra",
        "confirm",
        "agent",
        "ansible_output",
        "native_output",
        "verbosity",
        "timestamps",
        "color",
    ),
    "destroy": (
        "extra",
        "confirm",
        "agent",
        "ansible_output",
        "native_output",
        "verbosity",
        "timestamps",
        "color",
    ),
    "deploy": (
        "extra",
        "verbose",
        "hosts",
        "confirm",
        "agent",
        "ansible_output",
        "native_output",
        "verbosity",
        "timestamps",
        "color",
    ),
    "suspend": ("confirm", "wait", "agent", "hosts", "ansible_output"),
    "resume": ("confirm", "wait", "agent", "hosts", "ansible_output"),
    "run": (
        "name",
        "extra",
        "extra_dir",
        "verbose",
        "hosts",
        "confirm",
        "agent",
        "apps_playbook",
        "ansible_output",
        "native_output",
        "verbosity",
        "timestamps",
        "color",
    ),
    "logs": ("run_id", "last", "follow", "wait", "ansible_output", "timestamps", "color"),
    "aws": ("argv",),
    "provider": (
        "child",
        "action",
        "resource",
        "subaction",
        "hours",
        "days",
        "confirm",
        "agent",
    ),
    "licenses": ("software_dir", "config", "env_recommend"),
    "hosts_list": ("status", "hosts"),
    "hosts_register": (
        "name",
        "ssh_host",
        "user",
        "key",
        "ssh_port",
        "roles",
        "ip_addr",
        "confirm",
        "agent",
    ),
    "hosts_unregister": ("name", "confirm", "agent"),
    "hosts_check": ("hosts",),
    "shell_list": ("verbose", "hosts"),
    "completion_script": ("shell",),
    "complete": ("words", "index"),
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
    assert "cm_2idxc_sh" in ids
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
    result = run_spa(["--json", "validate", "--config", str(PROJECT_ROOT / "does-not-exist.yml")])
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


def test_session_init_messages(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    dest = tmp_path / "env"
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.init(
        str(dest),
        example="single_node.yml",
        example_set=True,
        provider="aws",
        skip_doctor=True,
    )
    assert result.ok, result.error
    assert result.data["env_dir"] == str(dest.resolve())
    assert result.data["messages"]
    json.dumps(result.data)
    assert capsys.readouterr().out == ""
    assert (dest / "config" / "splunk_config.yml").is_file()


def test_session_ccm_lifecycle_does_not_use_vagrant(tmp_path, monkeypatch):
    from dataclasses import replace

    from spa.paths import resolve_spa_paths

    env = tmp_path / "mylab"
    config_path = env / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "ccm: {}\nsplunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
        encoding="utf-8",
    )
    (env / "inventory").mkdir()
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=env,
        config_file=config_path,
        inventory_dir=env / "inventory",
        roots_differ=True,
    )
    session = LocalSpaSession(paths=paths)
    seen = []

    class FakeCcm:
        name = "ccm"

        def provision(self, extra, **kwargs):
            del extra
            seen.append(kwargs["run_log"].playbook)
            return {"deployment_id": "dep-9"}

        def destroy(self, extra, **kwargs):
            del extra
            seen.append(kwargs["run_log"].playbook)
            return {"deployment_id": "dep-9"}

    monkeypatch.setattr("spa.providers.get_provider", lambda _paths: FakeCcm())
    monkeypatch.setattr(session, "_venv_gate", lambda: None)
    monkeypatch.setattr(session, "_env_gate", lambda: None)
    monkeypatch.setattr(session, "_env_lookup_gate", lambda: None)
    monkeypatch.setattr(session, "_schema_stamp_gate", lambda: None)

    provisioned = session.provision(confirm=True)
    assert provisioned.ok, provisioned.error
    destroyed = session.destroy(confirm=True)
    assert destroyed.ok, destroyed.error
    assert seen == ["ccm_provision", "ccm_destroy"]
    assert all("vagrant" not in name for name in seen)

    class FakeCcmPower(FakeCcm):
        def suspend(self, **kwargs):
            seen.append(kwargs["run_log"].playbook)
            return {"action": "suspend"}

        def resume(self, **kwargs):
            seen.append(kwargs["run_log"].playbook)
            return {"action": "resume"}

        def provision_state(self):
            from spa.providers import ProvisionState

            return ProvisionState(provider="ccm", provisioned=True)

    monkeypatch.setattr("spa.providers.get_provider", lambda _paths: FakeCcmPower())
    monkeypatch.setattr(session, "_require_provisioned", lambda extra_line=None: None)
    suspended = session.suspend(confirm=True)
    assert suspended.ok, suspended.error
    resumed = session.resume(confirm=True)
    assert resumed.ok, resumed.error
    assert seen[-2:] == ["suspend", "resume"]
    assert all("vagrant" not in name for name in seen)


def test_session_ccm_hosts_list_status_uses_instance_state(tmp_path, monkeypatch):
    import json
    from dataclasses import replace

    from spa.paths import resolve_spa_paths
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient
    from spa.shell import format_host_status

    env = tmp_path / "mylab"
    config_path = env / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "ccm:\n  instance_type: t3a.medium\n"
        "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
        encoding="utf-8",
    )
    inventory_dir = env / "inventory"
    inventory_dir.mkdir()
    (inventory_dir / "hosts").write_text(
        'idx1 ansible_host="1.1.1.1" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n',
        encoding="utf-8",
    )
    state_dir = env / "ccm"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "deployment_id": "dep-9",
                "ttl": "2026-11-01T00:00:00.000Z",
                "hosts": {"idx1": {"instance_id": "i-aaa"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=env,
        config_file=config_path,
        inventory_dir=inventory_dir,
        roots_differ=True,
    )

    class FakeResponse:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class Opener:
        def open(self, req, timeout=None):
            body = json.dumps(
                {
                    "data": {
                        "deployment_id": "dep-9",
                        "ttl": "2026-11-24T13:26:51.000Z",
                        "instances_data": [
                            {
                                "instance_id": "i-aaa",
                                "ip_address": "1.1.1.1",
                                "state": "stopped",
                            }
                        ],
                    }
                }
            ).encode("utf-8")
            return FakeResponse(200, body)

    provider = CcmProvider(
        paths,
        {"instance_type": "t3a.medium", "ssh_username": "ec2-user"},
        client=UrllibCcmClient(token="test-ccm-token", opener=Opener()),
    )
    session = LocalSpaSession(paths=paths)
    monkeypatch.setattr("spa.providers.get_provider", lambda _paths: provider)
    monkeypatch.setattr(session, "_env_gate", lambda: None)
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: {
            "_meta": {"hostvars": {"idx1": {"ansible_host": "1.1.1.1"}}},
            "role_indexer": {"hosts": ["idx1"]},
        },
    )
    monkeypatch.setattr(
        "spa.shell.check_ansible_status",
        lambda hosts, paths=None: (_ for _ in ()).throw(
            AssertionError("stopped CCM hosts must not be pinged")
        ),
    )
    result = session.hosts_list(status=True)
    assert result.ok, result.error
    rows = {row["name"]: row for row in result.data["hosts"]}
    assert rows["idx1"]["provider"] == "ccm"
    assert rows["idx1"]["provider_status"] == "stopped"
    assert rows["idx1"]["ansible"] == "N/A"
    assert rows["idx1"]["ttl"] == "2026-11-24T13:26:51.000Z"
    assert rows["idx1"]["ttl"] != "2026-11-01T00:00:00.000Z"
    rendered = format_host_status(rows["idx1"])
    assert "CCM" in rendered
    assert "stopped" in rendered
    assert "expires " in rendered
    assert "2026-11-24T13:26:51.000Z" not in rendered
