"""CLI tests for spa run, agent envelope, and playbook resolution."""

import json
import sys

import pytest

from spa_testutil import PROJECT_ROOT, LIB, run_spa, run_spa_init, spa_env

pytestmark = pytest.mark.local

sys.path.insert(0, str(LIB))

from spa.playbooks import PlaybookError, resolve  # noqa: E402
from spa.paths import resolve_spa_paths  # noqa: E402


def test_spa_help():
    result = run_spa(["--help"])
    assert result.returncode == 0
    assert "init" in result.stdout
    assert "run" in result.stdout


def test_shell_help_is_the_shell_parser():
    """spa shell -h must reach shell.py, not the spa dispatcher."""
    result = run_spa(["shell", "--help"])
    assert result.returncode == 0, result.stderr
    assert "usage: spa shell" in result.stdout
    assert "-l, --list" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["shell", "-l"],
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

    # A global option value that matches a command name is not the command.
    head, native = _split_native(["--start-dir", "aws", "aws", "--list-regions"])
    assert head == ["--start-dir", "aws", "aws"]
    assert native == ["--list-regions"]

    # Non-passthrough commands keep their flags on the spa parser.
    head, native = _split_native(["run", "--list"])
    assert head == ["run", "--list"]
    assert native == []


def test_run_list_includes_verification(tmp_path):
    result = run_spa(["run", "--list"])
    assert result.returncode == 0, result.stderr
    assert "verification/ping_hosts" in result.stdout
    assert "deploy_site" in result.stdout
    # bare verification stem is not listed as ping_hosts alone as the catalog name
    names = [line.split("\t")[0] for line in result.stdout.splitlines() if line.strip()]
    assert "ping_hosts" not in names


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
    assert "single_node.yml" in payload["data"]


def test_no_agent_text_list():
    result = run_spa(["--no-agent", "init", "--list"])
    assert result.stdout.strip().startswith("single_node.yml") or "single_node.yml" in result.stdout
    assert not result.stdout.strip().startswith("{")


def test_agent_schema():
    result = run_spa(["agent", "schema"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    names = {c["name"] for c in payload["data"]["commands"]}
    assert "run" in names
    assert "shell" in names


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
