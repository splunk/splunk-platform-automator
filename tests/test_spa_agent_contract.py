"""Agent-mode detection, envelopes, errors, and output-format contract."""

import json

import pytest

from spa_testutil import AGENT_ENV_VARS, PROJECT_ROOT, run_spa, write_min_env


pytestmark = [pytest.mark.local, pytest.mark.cli]


def _payload(result):
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert isinstance(payload["ok"], bool)
    return payload


def test_agent_and_json_flags_have_the_same_success_envelope():
    by_agent = run_spa(["--agent", "init", "list"])
    by_json = run_spa(["--json", "init", "list"])
    assert by_agent.returncode == 0, by_agent.stderr
    assert by_json.returncode == 0, by_json.stderr
    assert _payload(by_agent) == _payload(by_json)


def test_json_and_agent_flags_work_after_the_subcommand():
    trailing = run_spa(["init", "list", "--json"])
    leading = run_spa(["--json", "init", "list"])
    assert trailing.returncode == 0, trailing.stderr
    assert leading.returncode == 0, leading.stderr
    assert _payload(trailing) == _payload(leading)


@pytest.mark.parametrize("variable", AGENT_ENV_VARS)
def test_every_supported_environment_variable_enables_agent_mode(variable):
    result = run_spa(["init", "list"], extra_env={variable: "1"})
    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert payload["ok"] is True
    ids = [item["id"] for item in payload["data"]["topologies"]]
    assert "single_node" in ids


def test_no_agent_overrides_detected_agent_mode():
    result = run_spa(
        ["--no-agent", "init", "list"],
        extra_env={"SPA_AGENT": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "single_node" in result.stdout
    assert "Topologies:" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_agent_runtime_failure_is_json_on_stdout_only():
    result = run_spa(["--agent", "run", "does_not_exist"])
    assert result.returncode != 0
    payload = _payload(result)
    assert payload["ok"] is False
    assert "Unknown playbook" in payload["error"]
    assert "data" not in payload


def test_agent_parse_failure_is_json_on_stdout_only():
    result = run_spa(["--agent", "does-not-exist"])
    assert result.returncode == 2
    payload = _payload(result)
    assert payload["ok"] is False
    assert "invalid choice" in payload["error"]


def test_human_runtime_failure_is_text_on_stderr():
    result = run_spa(["--no-agent", "run", "does_not_exist"])
    assert result.returncode != 0
    assert "Unknown playbook" in result.stderr
    assert not result.stdout.strip().startswith("{")


def test_agent_confirmation_failure_is_versioned_json(monkeypatch, capsys):
    """Direct CLI dispatch must not prompt and must preserve the envelope."""
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("agent prompted")),
    )
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    from spa.cli import main

    rc = main(["--agent", "run", "splunk_remove"])
    assert rc != 0
    captured = capsys.readouterr()
    assert not captured.err
    payload = json.loads(captured.out)
    assert payload == {
        "ok": False,
        "schema_version": 1,
        "error": "run splunk_remove requires -y/--yes in agent mode.",
    }


def test_native_help_remains_native_text_when_agent_is_auto_detected():
    """aws/licenses/shell own their output contract and are not JSON-wrapped."""
    result = run_spa(["aws", "--help"], extra_env={"SPA_AGENT": "1"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: spa aws")
    assert not result.stdout.startswith("{")


def _assert_agent_json_only(result):
    """--agent/--json: one JSON object on stdout and no human text on stderr."""
    assert result.stderr == "", result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert isinstance(payload["ok"], bool)
    assert result.stdout == json.dumps(payload, separators=(",", ":")) + "\n"
    return payload


@pytest.mark.parametrize(
    "argv",
    [
        ["--agent", "init", "list"],
        ["--json", "doctor"],
        ["--agent", "environment", "list"],
        ["--agent", "agent", "schema"],
        ["--agent", "run", "list"],
        ["--agent", "config", "search", "region"],
        ["--agent", "apps", "search", "unix"],
        ["--agent", "skills"],
        ["--agent", "venv"],
        ["--agent", "logs", "list"],
        ["--agent", "hosts", "list"],
        ["--agent", "validate"],
    ],
)
def test_read_only_agent_commands_print_json_only(argv):
    result = run_spa(argv)
    _assert_agent_json_only(result)


def test_agent_content_packs_list_prints_json_only(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    cache = tmp_path / "cache"
    conf = (
        cache
        / "content_pack_DA-ITSI-ContentLibrary"
        / "content_pack_app_confs"
        / "2.5.1"
        / "DA-ITSI-CP-nix"
        / "default"
    )
    conf.mkdir(parents=True)
    (conf / "app.conf").write_text(
        "[ui]\nlabel = Unix and Linux\n[launcher]\nversion = 1\n",
        encoding="utf-8",
    )
    (env / "config" / "splunk_config.yml").write_text(
        "splunk_app_deployment:\n  temp_dir: %s\n" % cache,
        encoding="utf-8",
    )
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPA_APPS_DIR", str(tmp_path / "apps"))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(env / "config" / "splunk_config.yml"))
    monkeypatch.setattr("spa.executil.venv_required_error", lambda _paths: None)
    from spa.cli import main

    for flag in ("--agent", "--json"):
        rc = main([flag, "apps", "content-packs", "list", "5391", "--version", "2.5.1"])
        captured = capsys.readouterr()
        assert rc == 0, captured.err
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["ok"] is True
        assert payload["data"]["version"] == "2.5.1"
        assert [row["name"] for row in payload["data"]["packs"]] == ["DA-ITSI-CP-nix"]
        assert payload["data"]["source"] == "cached"
        assert captured.out == json.dumps(payload, separators=(",", ":")) + "\n"


@pytest.mark.parametrize(
    "argv",
    [
        ["--agent", "aws", "--bogus"],
        ["aws", "--json", "--bogus"],
        ["--agent", "licenses", "--bogus"],
        ["licenses", "--json", "--bogus"],
    ],
)
def test_native_usage_errors_are_json_only(argv):
    """aws and licenses own their JSON. It is not the spa envelope."""
    result = run_spa(argv)
    assert result.returncode == 2
    assert result.stderr == "", result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "unrecognized arguments" in payload["error"]
    assert "schema_version" not in payload
    assert "data" not in payload
    assert result.stdout == json.dumps(payload, separators=(",", ":")) + "\n"


def test_agent_hosts_ssh_provision_error_is_json_only(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setattr("spa.executil.venv_required_error", lambda _paths: None)
    from spa.api import CommandResult

    monkeypatch.setattr(
        "spa.api.LocalSpaSession._require_provisioned",
        lambda self, extra_line=None: CommandResult(
            ok=False, error="hosts not provisioned: idx1", code=1
        ),
    )
    from spa.cli import main

    rc = main(["--agent", "hosts", "ssh", "idx1"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert "hosts not provisioned: idx1" in payload["error"]
    assert payload["schema_version"] == 1


def test_agent_hosts_copy_provision_error_is_json_only(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setattr("spa.executil.venv_required_error", lambda _paths: None)
    from spa.api import CommandResult

    monkeypatch.setattr(
        "spa.api.LocalSpaSession._require_provisioned",
        lambda self, extra_line=None: CommandResult(
            ok=False, error="hosts not provisioned: idx1", code=1
        ),
    )
    from spa.cli import main

    rc = main(["--agent", "hosts", "copy", "app.tgz", "idx1:/tmp/"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "hosts not provisioned: idx1" in payload["error"]
    assert "data" not in payload


def test_agent_hosts_copy_shell_error_is_json_only(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setattr("spa.executil.venv_required_error", lambda _paths: None)
    monkeypatch.setattr(
        "spa.api.LocalSpaSession._require_provisioned",
        lambda self, extra_line=None: None,
    )
    from spa.shell import ShellError

    def _fail(_paths):
        raise ShellError("scp failed: idx1")

    monkeypatch.setattr("spa.shell.run_scp", _fail)
    from spa.cli import main

    rc = main(["--agent", "hosts", "copy", "app.tgz", "idx1:/tmp/"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert payload["error"] == "scp failed: idx1"
    assert "data" not in payload
