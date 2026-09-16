"""Agent-mode detection, envelopes, errors, and output-format contract."""

import json

import pytest

from spa_testutil import AGENT_ENV_VARS, PROJECT_ROOT, run_spa


pytestmark = [pytest.mark.local, pytest.mark.cli]


def _payload(result):
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert isinstance(payload["ok"], bool)
    return payload


def test_agent_and_json_flags_have_the_same_success_envelope():
    by_agent = run_spa(["--agent", "init", "--list"])
    by_json = run_spa(["--json", "init", "--list"])
    assert by_agent.returncode == 0, by_agent.stderr
    assert by_json.returncode == 0, by_json.stderr
    assert _payload(by_agent) == _payload(by_json)


def test_json_and_agent_flags_work_after_the_subcommand():
    trailing = run_spa(["init", "--list", "--json"])
    leading = run_spa(["--json", "init", "--list"])
    assert trailing.returncode == 0, trailing.stderr
    assert leading.returncode == 0, leading.stderr
    assert _payload(trailing) == _payload(leading)


@pytest.mark.parametrize("variable", AGENT_ENV_VARS)
def test_every_supported_environment_variable_enables_agent_mode(variable):
    result = run_spa(["init", "--list"], extra_env={variable: "1"})
    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert payload["ok"] is True
    ids = [item["id"] for item in payload["data"]["topologies"]]
    assert "single_node" in ids


def test_no_agent_overrides_detected_agent_mode():
    result = run_spa(
        ["--no-agent", "init", "--list"],
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
