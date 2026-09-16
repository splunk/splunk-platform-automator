"""Host selector (--hosts names or roles) and spa hosts CLI."""

import json
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT, run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.hosts import (  # noqa: E402
    HostsError,
    format_names,
    group_by_role,
    parse_host_tokens,
    resolve_hosts,
    with_ansible_limit,
)

INVENTORY = {
    "_meta": {"hostvars": {"idx1": {}, "idx2": {}, "sh1": {}, "uf1": {}}},
    "role_indexer": {"hosts": ["idx1", "idx2"]},
    "role_search_head": {"hosts": ["sh1"]},
    "role_universal_forwarder": {"hosts": ["uf1"]},
}


def test_parse_host_tokens_splits_commas_and_repeats():
    assert parse_host_tokens(["idx1,sh1", "uf1"]) == ["idx1", "sh1", "uf1"]
    assert parse_host_tokens(None) == []


def test_resolve_hosts_by_name_and_role():
    assert resolve_hosts(INVENTORY, ["idx1"]) == ["idx1"]
    assert resolve_hosts(INVENTORY, ["indexer"]) == ["idx1", "idx2"]
    assert resolve_hosts(INVENTORY, ["idx1", "indexer"]) == ["idx1", "idx2"]


def test_resolve_hosts_unknown_lists_known():
    with pytest.raises(HostsError, match="Unknown host or role 'nope'") as excinfo:
        resolve_hosts(INVENTORY, ["nope"])
    message = str(excinfo.value)
    assert "idx1" in message
    assert "indexer" in message
    assert "limit" not in message.lower()


def test_with_ansible_limit_injects_unless_already_present():
    assert with_ansible_limit([], ["idx1", "sh1"]) == ["--limit", "idx1:sh1"]
    existing = ["--limit", "all"]
    assert with_ansible_limit(existing, ["idx1"]) == existing
    assert with_ansible_limit(["-v"], None) == ["-v"]


def test_group_by_role_keeps_one_entry_per_host():
    groups = dict(group_by_role(INVENTORY, ["idx1", "idx2", "sh1", "unknown"]))
    assert groups["indexer"] == ["idx1", "idx2"]
    assert groups["search head"] == ["sh1"]
    assert groups["no role"] == ["unknown"]


def test_format_names_trims_long_lists():
    names = ["idx%02d" % index for index in range(1, 51)]
    rendered = format_names(names)
    assert rendered.startswith("idx01, idx02")
    assert rendered.endswith("more")
    assert len(rendered) < 90
    assert format_names(["idx1", "sh1"]) == "idx1, sh1"


def test_spa_help_lists_hosts_and_aliases():
    result = run_spa(["--help"])
    assert result.returncode == 0
    assert "hosts" in result.stdout
    assert "validate" in result.stdout


def test_hosts_list_help_has_hosts_flag_not_limit():
    result = run_spa(["hosts", "list", "--help"])
    assert result.returncode == 0, result.stderr
    assert "--hosts" in result.stdout
    assert "--status" in result.stdout
    assert "--limit" not in result.stdout


def test_deploy_help_has_hosts_not_limit():
    result = run_spa(["deploy", "--help"])
    assert "--hosts" in result.stdout
    assert "--limit" not in result.stdout


def test_alias_val_is_validate():
    result = run_spa(["val", "--help"])
    assert result.returncode == 0, result.stderr
    assert "Validate" in result.stdout or "validate" in result.stdout.lower()


def test_cli_agent_schema_includes_hosts_commands():
    result = run_spa(["agent", "schema"])
    payload = json.loads(result.stdout)
    names = {row["name"] for row in payload["data"]["commands"]}
    assert "hosts list" in names
    assert "hosts ssh" in names
    assert "hosts copy" in names
    deploy = next(row for row in payload["data"]["commands"] if row["name"] == "deploy")
    flags = [item["long"] for item in deploy.get("flags") or []]
    assert "--hosts" in flags
    assert "--limit" not in flags


def test_session_deploy_injects_limit(monkeypatch):
    from spa.api import open_session

    captured = {}

    def fake_run(playbook, paths, args, on_progress=None):
        captured["args"] = args
        return 0

    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr("spa.playbooks.run_playbook", fake_run)
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="aws", provisioned=True),
    )
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: INVENTORY,
    )
    from spa.preflight import ControllerDataState

    monkeypatch.setattr(
        "spa.preflight.check_controller_data",
        lambda paths: ControllerDataState(ok=True),
    )
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.deploy(hosts=["indexer"], confirm=True)
    assert result.ok
    assert result.data["hosts"] == ["idx1", "idx2"]
    assert captured["args"][:2] == ["--limit", "idx1:idx2"]


def test_copy_help_shows_syntax_and_examples():
    result = run_spa(["hosts", "copy", "--help"])
    assert result.returncode == 0, result.stderr
    assert "spa hosts copy [-r] SRC [SRC ...] DST" in result.stdout
    assert "HOST:PATH" in result.stdout
    assert "spa hosts copy app.tgz idx1:/tmp/" in result.stdout


def test_copy_without_destination_explains_syntax():
    result = run_spa(["hosts", "copy", "app.tgz"])
    assert result.returncode == 1
    assert "source and a destination" in result.stderr


def _capture_scp(monkeypatch):
    import spa.shell as shell_mod

    captured = {}
    monkeypatch.setattr(shell_mod.os, "execvp", lambda file, argv: captured.update(argv=argv))
    monkeypatch.setattr(shell_mod, "get_inventory_data", lambda: SSH_INVENTORY)
    monkeypatch.setattr(shell_mod.os.path, "exists", lambda path: True)
    return captured


SSH_INVENTORY = {
    "_meta": {
        "hostvars": {
            "idx1": {
                "ansible_host": "10.0.0.1",
                "ansible_user": "ec2-user",
                "ansible_ssh_private_key_file": "/keys/env.pem",
            }
        }
    },
    "role_indexer": {"hosts": ["idx1"]},
}


def test_run_scp_resolves_host_alias(monkeypatch):
    from spa.shell import run_scp

    captured = _capture_scp(monkeypatch)
    run_scp(["app.tgz", "idx1:/tmp/"])
    argv = captured["argv"]
    assert argv[0] == "scp"
    assert argv[-2:] == ["app.tgz", "ec2-user@10.0.0.1:/tmp/"]
    assert "/keys/env.pem" in argv


def test_run_scp_keeps_flags_before_paths(monkeypatch):
    from spa.shell import run_scp

    captured = _capture_scp(monkeypatch)
    run_scp(["-r", "./myapp", "idx1:/tmp/"])
    argv = captured["argv"]
    assert argv.index("-r") < argv.index("./myapp")


def test_cli_copy_recursive_flag_reaches_scp(monkeypatch):
    import spa.shell as shell_mod

    captured = {}
    monkeypatch.setattr(shell_mod, "run_scp", lambda paths: captured.update(paths=paths))
    monkeypatch.setattr(shell_mod, "apply_spa_env", lambda: None)
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="aws", provisioned=True),
    )
    from spa.cli import main

    rc = main(["--no-agent", "hosts", "copy", "-r", "./myapp", "idx1:/tmp/"])
    assert rc == 0
    assert captured["paths"] == ["-r", "./myapp", "idx1:/tmp/"]


def test_cli_suspend_passes_hosts(monkeypatch):
    called = {}

    class FakeProvider:
        name = "test"

        def suspend(self, **kwargs):
            called.update(kwargs)
            return {"instances": []}

        def resume(self, **kwargs):
            called.update(kwargs)
            return {"instances": []}

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr("spa.shell.get_inventory_data", lambda: INVENTORY)
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="test", provisioned=True),
    )
    from spa.cli import main

    rc = main(["--no-agent", "suspend", "--yes", "--hosts", "idx1"])
    assert rc == 0
    assert called["hosts"] == ["idx1"]
    assert called["yes"] is True


def _hosts_list_session(tmp_path):
    from dataclasses import replace

    from spa.api import LocalSpaSession
    from spa.paths import resolve_spa_paths
    from spa_testutil import write_min_env

    env = write_min_env(tmp_path)
    config_path = env / "config" / "splunk_config.yml"
    config_path.write_text(
        "terraform:\n  aws:\n    region: eu-central-1\n"
        "splunk_hosts:\n  - name: idx1\n  - name: idx2\n"
    )
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=env,
        config_file=config_path,
        inventory_dir=env / "inventory",
        terraform_state_dir=env / "terraform" / "aws",
        roots_differ=True,
    )
    return paths, LocalSpaSession(paths=paths)


def test_hosts_list_status_skips_runtime_when_unprovisioned(tmp_path, monkeypatch):
    from spa.shell import format_host_status

    pinged = []

    def boom_ping(hosts):
        pinged.append(list(hosts))
        raise AssertionError("ansible ping must not run when unprovisioned")

    _paths, session = _hosts_list_session(tmp_path)
    monkeypatch.setattr("spa.shell.get_inventory_data", lambda: INVENTORY)
    monkeypatch.setattr("spa.shell.check_ansible_status", boom_ping)
    monkeypatch.setattr(
        "spa.shell.get_provider_status",
        lambda paths=None: (_ for _ in ()).throw(
            AssertionError("provider status must not run")
        ),
    )
    result = session.hosts_list(status=True)
    assert result.ok
    assert pinged == []
    assert result.data["provisioned"] is False
    assert "spa provision" in result.data["hint"]
    rows = {row["name"]: row for row in result.data["hosts"]}
    assert rows["idx1"]["ansible"] == "unprovisioned"
    assert rows["idx1"]["provider_status"] == "unprovisioned"
    assert format_host_status(rows["idx1"]) == " - unprovisioned"


def test_hosts_list_status_pings_when_provisioned(tmp_path, monkeypatch):
    paths, session = _hosts_list_session(tmp_path)
    paths.terraform_state_dir.mkdir(parents=True, exist_ok=True)
    (paths.terraform_state_dir / "terraform.tfstate").write_text(
        '{"resources": [{"type": "aws_instance"}]}'
    )
    paths.inventory_dir.mkdir(parents=True, exist_ok=True)
    (paths.inventory_dir / "hosts").write_text(
        'idx1 ansible_host="example.invalid"\nidx2 ansible_host="example.invalid"\n'
    )
    pinged = []
    monkeypatch.setattr("spa.shell.get_inventory_data", lambda: INVENTORY)
    monkeypatch.setattr(
        "spa.shell.get_provider_status",
        lambda paths=None: {"name": "aws", "hosts": {}, "error": None},
    )
    monkeypatch.setattr(
        "spa.shell.check_ansible_status",
        lambda hosts: pinged.extend(hosts) or {host: "Success" for host in hosts},
    )
    result = session.hosts_list(status=True)
    assert result.ok
    assert "idx1" in pinged
    assert result.data.get("provisioned") is not False
    rows = {row["name"]: row for row in result.data["hosts"]}
    assert rows["idx1"]["ansible"] == "Success"


def test_require_provisioned_is_the_shared_gate(tmp_path):
    paths, session = _hosts_list_session(tmp_path)
    blocked = session._require_provisioned()
    assert blocked is not None
    assert blocked.ok is False
    assert blocked.data["provisioned"] is False
    assert "spa provision" in blocked.error
    assert "idx1" in blocked.error
    assert "hosts not provisioned:" in blocked.error
    assert "provider: aws" in blocked.error
    assert "terraform.tfstate" not in blocked.error
    assert "Missing hosts:" not in blocked.error

    paths.terraform_state_dir.mkdir(parents=True, exist_ok=True)
    (paths.terraform_state_dir / "terraform.tfstate").write_text(
        '{"resources": [{"type": "aws_instance"}]}'
    )
    paths.inventory_dir.mkdir(parents=True, exist_ok=True)
    (paths.inventory_dir / "hosts").write_text(
        'idx1 ansible_host="example.invalid"\nidx2 ansible_host="example.invalid"\n'
    )
    assert session._require_provisioned() is None


def test_suspend_and_run_use_the_provision_gate(tmp_path, monkeypatch):
    _paths, session = _hosts_list_session(tmp_path)
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: called.append(True) or 0,
    )
    suspend = session.suspend(confirm=True)
    assert suspend.ok is False
    assert "spa provision" in suspend.error
    ping = session.run("verification/ping_hosts")
    assert ping.ok is False
    assert "spa provision" in ping.error
    assert not called
    provision = session.run("aws_provision", confirm=True)
    assert called == [True]
    assert provision.ok


def test_cli_ssh_copy_and_sh_refuse_when_unprovisioned(tmp_path):
    paths, _session = _hosts_list_session(tmp_path)
    extra = {
        "SPA_HOME": str(PROJECT_ROOT),
        "SPA_ENV_DIR": str(paths.spa_env_dir),
        "SPLUNK_CONFIG_FILE": str(paths.config_file),
    }
    for argv in (
        ["hosts", "ssh", "idx1"],
        ["hosts", "copy", "app.tgz", "idx1:/tmp/"],
        ["sh", "idx1"],
        ["suspend", "--yes"],
        ["resume", "--yes"],
        ["run", "verification/ping_hosts"],
    ):
        result = run_spa(["--no-agent", *argv], extra_env=extra, cwd=str(paths.spa_env_dir))
        assert result.returncode != 0, argv
        assert "spa provision" in result.stderr, argv
        assert "hosts not provisioned:" in result.stderr, argv
        assert "provider: aws" in result.stderr, argv
        assert "spa run --list" not in result.stderr, argv
        assert "Traceback" not in result.stderr
