"""CLI tests for spa run, agent envelope, and playbook resolution."""

import json
import os
import sys
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, LIB, run_spa, run_spa_init, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.playbooks import PlaybookError, resolve  # noqa: E402
from spa.paths import resolve_spa_paths  # noqa: E402


def test_spa_help():
    result = run_spa(["--help"])
    assert result.returncode == 0
    assert "init" in result.stdout
    assert "run" in result.stdout
    # argparse would otherwise dump every alias into usage: spa {init,val,...}
    assert "{init," not in result.stdout
    assert "COMMAND" in result.stdout


@pytest.mark.no_spa_env
def test_spa_doctor_and_agent_schema_from_clone():
    doctor = run_spa(["--json", "doctor", "--spa-home", str(PROJECT_ROOT)])
    assert doctor.returncode == 0, doctor.stderr
    schema = run_spa(["agent", "schema"])
    assert schema.returncode == 0, schema.stderr
    listed = run_spa(["init", "--list"])
    assert listed.returncode == 0, listed.stderr


@pytest.mark.no_spa_env
def test_spa_validate_from_clone_requires_env_dir():
    result = run_spa(["validate"], extra_env={"SPA_HOME": str(PROJECT_ROOT)})
    assert result.returncode == 2
    combined = result.stderr + result.stdout
    assert "environment directory" in combined
    assert "spa init" in combined


def test_shell_help_is_the_shell_parser():
    """spa shell -h must reach shell.py, not the spa dispatcher."""
    result = run_spa(["shell", "--help"])
    assert result.returncode == 0, result.stderr
    assert "usage: spa shell" in result.stdout
    assert "-c, --copy" in result.stdout
    assert "-l" not in result.stdout


def test_shell_list_flag_is_gone():
    result = run_spa(["shell", "-l"])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "unrecognized arguments" in combined or "error" in combined.lower()


@pytest.mark.parametrize(
    "args",
    [
        ["sh", "idx1"],
        ["shell", "-c", "local.txt", "idx1:/tmp/"],
        ["aws", "--check-auth", "--json"],
        ["licenses", "--json"],
    ],
)
def test_native_flags_are_not_parsed_by_spa(args):
    """argparse.REMAINDER drops a leading option; these must never bubble up."""
    result = run_spa(args)
    assert "unrecognized arguments" not in (result.stdout + result.stderr)


def test_aws_and_licenses_help_use_own_parser():
    for command, usage in (("aws", "usage: spa aws"), ("licenses", "usage: spa licenses")):
        result = run_spa([command, "--help"])
        assert result.returncode == 0, result.stderr
        assert usage in result.stdout


def test_split_native_keeps_spa_globals():
    from spa.cli import _split_native, _split_passthrough

    head, extra = _split_passthrough(["shell", "idx1", "--", "-L", "8000:localhost:8000"])
    head, native = _split_native(head)
    assert head == ["shell"]
    assert native == ["idx1"]
    assert extra == ["-L", "8000:localhost:8000"]

    head, native = _split_native(["sh", "idx1"])
    assert head == ["sh"]
    assert native == ["idx1"]

    # A global option value that matches a command name is not the command.
    head, native = _split_native(["--start-dir", "aws", "aws", "--list-regions"])
    assert head == ["--start-dir", "aws", "aws"]
    assert native == ["--list-regions"]

    # Non-passthrough commands keep their flags on the spa parser.
    head, native = _split_native(["run", "--list"])
    assert head == ["run", "--list"]
    assert native == []


def test_provision_help_includes_yes():
    result = run_spa(["provision", "--help"])
    assert result.returncode == 0, result.stderr
    assert "--yes" in result.stdout
    assert "-y" in result.stdout


def test_provision_yes_after_subcommand_auto_approves(monkeypatch):
    """spa provision --yes must be a subcommand flag, not only spa --yes provision."""
    captured = {}

    class FakeProvider:
        name = "test"

        def provision(self, extra):
            captured["extra"] = extra
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    from spa.cli import main

    rc = main(["--no-agent", "provision", "--yes"])
    assert rc == 0
    assert captured["extra"][:2] == ["-e", "auto_approve=true"]


@pytest.mark.parametrize("argv", [["-y", "provision"], ["provision", "-y"]])
def test_provision_yes_works_before_or_after_subcommand(monkeypatch, argv):
    captured = []

    class FakeProvider:
        name = "test"

        def provision(self, extra):
            captured.extend(extra)
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    from spa.cli import main

    rc = main(["--no-agent", *argv])
    assert rc == 0
    assert captured[:2] == ["-e", "auto_approve=true"]


def test_destroy_yes_after_subcommand_auto_approves(monkeypatch):
    captured = {}

    class FakeProvider:
        name = "test"

        def destroy(self, extra):
            captured["extra"] = extra
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    from spa.cli import main

    rc = main(["--no-agent", "destroy", "--yes"])
    assert rc == 0
    assert captured["extra"][:2] == ["-e", "auto_approve=true"]


@pytest.mark.parametrize("command", ["suspend", "resume"])
def test_lifecycle_commands_dispatch_to_provider(monkeypatch, command):
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
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="test", provisioned=True),
    )
    from spa.cli import main

    rc = main(["--no-agent", command, "--yes"])
    assert rc == 0
    assert called == {"yes": True, "agent": False, "wait": True, "hosts": None}


def test_broken_spa_venv_dir_falls_back(tmp_path):
    """An empty .venv (interrupted create) must not break every spa command."""
    from spa.executil import resolve_venv_dir

    broken = tmp_path / "env" / ".venv"
    broken.mkdir(parents=True)
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(tmp_path / "env")})
    paths = resolve_spa_paths(start_dir=tmp_path / "env", environ=env)
    monkey = os.environ.get("SPA_VENV_DIR")
    os.environ["SPA_VENV_DIR"] = str(broken)
    try:
        assert resolve_venv_dir(paths) != broken
    finally:
        if monkey is None:
            os.environ.pop("SPA_VENV_DIR", None)
        else:
            os.environ["SPA_VENV_DIR"] = monkey


def test_missing_tool_raises_actionable_error(tmp_path):
    from spa.executil import ToolNotFound, tool_path

    paths = resolve_spa_paths(start_dir=PROJECT_ROOT)
    with pytest.raises(ToolNotFound) as excinfo:
        tool_path(paths, "spa-no-such-tool")
    message = str(excinfo.value)
    assert "spa-no-such-tool not found" in message
    assert "spa_venv.sh --create" in message
    assert "spa doctor" in message


def test_missing_host_tool_does_not_suggest_venv(monkeypatch):
    from spa.executil import ToolNotFound, tool_path
    import spa.executil as executil

    monkeypatch.setattr(executil.shutil, "which", lambda name: None)
    paths = resolve_spa_paths(start_dir=PROJECT_ROOT)
    with pytest.raises(ToolNotFound) as excinfo:
        tool_path(paths, "vagrant")
    message = str(excinfo.value)
    assert "vagrant is not on PATH" in message
    assert "not part of the SPA Python venv" in message
    assert "spa_venv.sh" not in message
    assert "Active venv" not in message
    assert "Install:" in message
    assert "spa doctor" in message


def test_run_list_groups_by_root(tmp_path):
    result = run_spa(["run", "--list"])
    assert result.returncode == 0, result.stderr
    assert "Framework playbooks" in result.stdout
    assert "Verification playbooks" in result.stdout
    # The source belongs in --json, not as a column next to every name.
    assert "\tansible" not in result.stdout
    entries = [line for line in result.stdout.splitlines() if line.startswith("  ")]
    names = [line.split()[0] for line in entries]
    assert "deploy_site" in names
    assert "splunk_cli" in names
    assert "verification/ping_hosts" in names
    # bare verification stem is not listed as ping_hosts alone as the catalog name
    assert "ping_hosts" not in names
    assert "run_splunk_command" not in names
    # Summaries start in one column for every group, so they read as a table.
    starts = {
        len(line) - len(line.split(maxsplit=1)[1])
        for line in entries
        if len(line.split(maxsplit=1)) == 2
    }
    assert len(starts) == 1


def test_run_list_json():
    result = run_spa(["--json", "run", "--list"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    names = {row["name"] for row in payload["data"]}
    assert "verification/ping_hosts" in names
    sources = {row["name"]: row["source"] for row in payload["data"]}
    assert sources["verification/ping_hosts"] == "verification"
    assert sources["deploy_site"] == "ansible"
    deploy = next(row for row in payload["data"] if row["name"] == "deploy_site")
    assert deploy.get("summary")
    assert deploy.get("risk") == "mutating"
    assert deploy.get("requires_confirmation") is True
    ping = next(row for row in payload["data"] if row["name"] == "verification/ping_hosts")
    assert ping.get("requires_provisioned") is True
    aws = next(row for row in payload["data"] if row["name"] == "aws_provision")
    assert aws.get("requires_provisioned") is False
    ping = next(row for row in payload["data"] if row["name"] == "verification/ping_hosts")
    assert ping.get("requires_confirmation") is False
    names = {row["name"] for row in payload["data"]}
    assert "splunk_start" in names
    assert "start_splunk" not in names


def test_run_playbook_help_does_not_execute(monkeypatch):
    called = []

    def fake_run(*args, **kwargs):
        called.append(True)
        return 0

    monkeypatch.setattr("spa.playbooks.run_playbook", fake_run)
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_cli", "--help"])
    assert rc == 0
    assert not called


def test_run_playbook_help_text():
    result = run_spa(["run", "splunk_cli", "--help"])
    assert result.returncode == 0, result.stderr
    assert "splunk_command" in result.stdout
    assert "--hosts" in result.stdout
    assert "--limit" not in result.stdout
    assert "confirmation: required" in result.stdout


def test_run_playbook_help_json():
    result = run_spa(["--json", "run", "splunk_cli", "--help"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["name"] == "splunk_cli"
    assert payload["data"]["metadata"]["risk"] == "mutating"
    assert payload["data"]["requires_confirmation"] is True


def test_run_legacy_stem_help():
    result = run_spa(["run", "run_splunk_command", "--help"])
    assert result.returncode == 0, result.stderr
    assert "use spa run splunk_cli" in result.stdout


def test_run_help_passthrough_after_dashdash(monkeypatch):
    captured = {}

    def fake_run(playbook, paths, extra, on_progress=None):
        captured["extra"] = extra
        captured["playbook"] = str(playbook)
        return 0

    monkeypatch.setattr("spa.playbooks.run_playbook", fake_run)
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_cli", "--yes", "--", "--help"])
    assert rc == 0
    assert captured.get("extra") == ["--help"]
    assert captured["playbook"].endswith("splunk_cli.yml")


def test_env_dir_playbook_resolves(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", str(dest)])
    custom = dest / "custom"
    custom.mkdir()
    play = custom / "foo.yml"
    play.write_text("---\n- hosts: localhost\n  gather_facts: false\n  tasks: []\n")
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)})
    paths = resolve_spa_paths(start_dir=dest, environ=env)
    found = resolve("custom/foo", paths)
    assert found.resolve() == play.resolve()
    with pytest.raises(PlaybookError):
        resolve("foo", paths)

    listing = run_spa(["run", "--list", "--dir", "custom"], env=env)
    assert "Env playbooks" in listing.stdout
    assert "custom/foo" in listing.stdout
    json_listing = run_spa(["--json", "run", "--list", "--dir", "custom"], env=env)
    payload = json.loads(json_listing.stdout)
    foo = next(row for row in payload["data"] if row["name"] == "custom/foo")
    assert foo.get("missing") is True
    assert foo.get("metadata") is None
    assert foo.get("requires_confirmation") is True


def test_run_path_escape_rejected(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", str(dest)])
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}
    result = run_spa(["run", "../ansible/deploy_site"], env=env)
    assert result.returncode != 0
    assert "escape" in (result.stderr + result.stdout).lower() or "unknown" in (
        result.stderr + result.stdout
    ).lower()


def test_agent_json_envelope():
    result = run_spa(["--agent", "init", "--list"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    ids = [item["id"] for item in payload["data"]["topologies"]]
    assert "single_node" in ids


def test_no_agent_text_list():
    result = run_spa(["--no-agent", "init", "--list"])
    assert "Topologies:" in result.stdout
    assert "single_node" in result.stdout
    assert not result.stdout.strip().startswith("{")


def test_agent_schema():
    result = run_spa(["agent", "schema"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    names = {c["name"] for c in payload["data"]["commands"]}
    assert "run" in names
    assert "features" in names
    assert "shell" in names
    run = next(c for c in payload["data"]["commands"] if c["name"] == "run")
    flags = [item["long"] for item in run.get("flags") or []]
    assert "--hosts" in flags
    assert "--list" in flags
    assert "--yes" in flags
    assert "spa --json run --list" in run["summary"]
    by_name = {c["name"]: c for c in payload["data"]["commands"]}
    for name in ("provision", "destroy", "deploy", "suspend", "resume"):
        assert by_name[name].get("requires_confirmation") is True


def test_agent_help_documents_schema():
    result = run_spa(["--no-agent", "agent", "--help"])
    assert result.returncode == 0, result.stderr
    assert "usage: spa agent [schema]" in result.stdout
    assert "ACTION" in result.stdout
    assert "spa agent schema" in result.stdout
    assert "requires_confirmation" in result.stdout
    # The schema covers commands; playbooks are discovered separately.
    assert "spa --json run --list" in result.stdout
    assert "--markdown" in result.stdout
    assert "docs/commands.md" in result.stdout


def test_agent_rejects_unknown_action():
    result = run_spa(["--no-agent", "agent", "bogus"])
    assert result.returncode != 0
    assert "invalid choice" in result.stderr


def test_agent_default_action_is_schema():
    """spa agent and spa agent schema must print the same envelope."""
    bare = run_spa(["agent"])
    explicit = run_spa(["agent", "schema"])
    assert bare.returncode == 0, bare.stderr
    assert json.loads(bare.stdout) == json.loads(explicit.stdout)


def test_agent_schema_markdown_is_not_json():
    result = run_spa(["--no-agent", "agent", "schema", "--markdown"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("<!-- Generated by spa agent schema --markdown.")
    assert "# spa commands" in result.stdout
    assert not result.stdout.strip().startswith("{")


def test_agent_schema_markdown_stays_json_in_agent_mode():
    result = run_spa(["--json", "agent", "schema", "--markdown"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "commands" in payload["data"]


def test_global_agent_flags_have_help():
    result = run_spa(["--no-agent", "--help"])
    assert result.returncode == 0, result.stderr
    assert "Force agent mode" in result.stdout
    assert "Force human mode" in result.stdout


def test_env_export_is_shell(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", str(dest)])
    result = run_spa(
        ["env", "--export"],
        extra_env={"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    assert "export SPA_ENV_DIR=" in result.stdout
    assert str(dest) in result.stdout
    assert not result.stdout.strip().startswith("{")


def _fake_run_playbook(monkeypatch):
    called = []

    def fake_run(*args, **kwargs):
        called.append(True)
        return 0

    monkeypatch.setattr("spa.playbooks.run_playbook", fake_run)
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="aws", provisioned=True),
    )
    return called


def test_agent_run_mutating_requires_yes(monkeypatch):
    called = _fake_run_playbook(monkeypatch)
    from spa.cli import main

    rc = main(["--agent", "run", "splunk_remove"])
    assert rc != 0
    assert not called


def test_agent_run_readonly_without_yes(monkeypatch):
    called = _fake_run_playbook(monkeypatch)
    from spa.cli import main

    rc = main(["--agent", "run", "verification/ping_hosts"])
    assert rc == 0
    assert called


def test_human_run_mutating_cancel(monkeypatch):
    called = _fake_run_playbook(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_remove"])
    assert rc != 0
    assert not called


def test_human_run_mutating_accept(monkeypatch):
    called = _fake_run_playbook(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_remove"])
    assert rc == 0
    assert called


def test_human_run_prompt_names_playbook_and_risk(monkeypatch):
    from spa.confirm import prompt_text

    seen = []
    called = _fake_run_playbook(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_remove"])
    assert rc != 0
    assert not called
    assert seen == [prompt_text("run splunk_remove", risk="destructive")]


@pytest.mark.parametrize(
    ("command", "risk"),
    [("provision", "mutating"), ("destroy", "destructive"), ("deploy", "mutating")],
)
def test_human_lifecycle_prompt_names_command_and_risk(monkeypatch, command, risk):
    from spa.confirm import prompt_text

    seen = []
    called = []

    class FakeProvider:
        name = "test"

        def provision(self, extra):
            called.append("provision")
            return 0

        def destroy(self, extra):
            called.append("destroy")
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    from spa.preflight import ControllerDataState
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="test", provisioned=True),
    )
    monkeypatch.setattr(
        "spa.preflight.check_controller_data",
        lambda paths: ControllerDataState(ok=True),
    )
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append("deploy") or 0
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    from spa.cli import main

    rc = main(["--no-agent", command])
    assert rc != 0
    assert not called
    assert seen == [prompt_text(command, risk=risk)]


@pytest.mark.parametrize("command", ["provision", "destroy", "deploy"])
def test_agent_lifecycle_requires_yes(monkeypatch, command):
    called = []

    class FakeProvider:
        name = "test"

        def provision(self, extra):
            called.append("provision")
            return 0

        def destroy(self, extra):
            called.append("destroy")
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    from spa.preflight import ControllerDataState
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="test", provisioned=True),
    )
    monkeypatch.setattr(
        "spa.preflight.check_controller_data",
        lambda paths: ControllerDataState(ok=True),
    )
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append("deploy") or 0
    )
    from spa.cli import main

    rc = main(["--agent", command])
    assert rc != 0
    assert not called


def test_env_playbook_without_metadata_requires_yes(tmp_path, monkeypatch, capsys):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", str(dest)])
    custom = dest / "custom"
    custom.mkdir()
    (custom / "foo.yml").write_text("---\n- hosts: localhost\n  gather_facts: false\n  tasks: []\n")
    called = _fake_run_playbook(monkeypatch)
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(dest))
    from spa.cli import main

    rc = main(["--agent", "run", "--dir", "custom", "custom/foo"])
    assert rc != 0
    assert not called
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "requires -y/--yes" in payload["error"]
    assert "Unknown playbook" not in payload["error"]


def test_human_env_playbook_prompt_mentions_missing_metadata(tmp_path, monkeypatch):
    from spa.confirm import prompt_text

    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", str(dest)])
    custom = dest / "custom"
    custom.mkdir()
    (custom / "foo.yml").write_text("---\n- hosts: localhost\n  gather_facts: false\n  tasks: []\n")
    called = _fake_run_playbook(monkeypatch)
    seen = []
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(dest))
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    from spa.cli import main

    rc = main(["--no-agent", "run", "--dir", "custom", "custom/foo"])
    assert rc != 0
    assert not called
    assert seen == [prompt_text("run custom/foo", risk=None)]
    assert "no playbook metadata" in seen[0]
