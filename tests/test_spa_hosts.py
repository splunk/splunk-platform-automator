"""Host selector (--hosts names or roles) and spa hosts CLI."""

import json
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT, run_spa

pytestmark = pytest.mark.local

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
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: INVENTORY,
    )
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.deploy(hosts=["indexer"])
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
    from spa.cli import main

    rc = main(["--no-agent", "suspend", "--yes", "--hosts", "idx1"])
    assert rc == 0
    assert called["hosts"] == ["idx1"]
    assert called["yes"] is True
