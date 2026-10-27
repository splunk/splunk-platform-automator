"""CLI tests for spa run, agent envelope, and playbook resolution."""

import json
import os
import sys
from pathlib import Path

import pytest

from spa_testutil import (
    PROJECT_ROOT,
    LIB,
    run_spa,
    run_spa_init,
    satisfy_env_lookups,
    spa_env,
    write_min_env,
)

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.playbooks import PlaybookError, resolve  # noqa: E402
from spa.paths import resolve_spa_paths  # noqa: E402


INHERITED_PATH_VARS = (
    "SPA_HOME",
    "SPA_ENV_DIR",
    "SPA_VENV_DIR",
    "SPA_SOFTWARE_DIR",
    "SPA_BASECONFIG_DIR",
    "SPA_APPS_DIR",
    "SPLUNK_CONFIG_FILE",
    "ANSIBLE_CONFIG",
    "ANSIBLE_INVENTORY",
    "ANSIBLE_ROLES_PATH",
    "ANSIBLE_INVENTORY_PLUGINS",
    "ANSIBLE_LOOKUP_PLUGINS",
    "ANSIBLE_VARS_PLUGINS",
    "ANSIBLE_CACHE_PLUGIN_CONNECTION",
)


def test_spa_env_drops_inherited_spa_and_ansible_paths(monkeypatch):
    for name in INHERITED_PATH_VARS:
        monkeypatch.setenv(name, "/dirty-shell/%s" % name.lower())

    clean = spa_env()

    for name in INHERITED_PATH_VARS:
        assert name not in clean


@pytest.mark.parametrize(
    ("markexpr", "selects_local"),
    [
        ("local", True),
        ("local and cli", True),
        ("local or aws", True),
        ("not local", False),
        ("aws", False),
        ("cli", False),
    ],
)
def test_local_marker_expression_selects_only_local_runs(markexpr, selects_local):
    from spa_testutil import selects_local_tests

    assert selects_local_tests(markexpr) is selects_local


def test_spa_env_keeps_explicit_test_path_overrides(monkeypatch):
    for name in INHERITED_PATH_VARS:
        monkeypatch.setenv(name, "/dirty-shell/%s" % name.lower())
    explicit = {name: "/test/%s" % name.lower() for name in INHERITED_PATH_VARS}

    clean = spa_env(explicit)

    assert {name: clean[name] for name in INHERITED_PATH_VARS} == explicit


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
    listed = run_spa(["init", "list"])
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


@pytest.mark.parametrize(
    ("argv", "expected_head", "expected_extra"),
    [
        (
            ["run", "splunk_cli", "--yes", "--", "--help", "-vv"],
            ["run", "splunk_cli", "--yes"],
            ["--help", "-vv"],
        ),
        (
            ["shell", "idx1", "--", "-L", "8000:localhost:8000"],
            ["shell", "idx1"],
            ["-L", "8000:localhost:8000"],
        ),
        (["run", "--list"], ["run", "--list"], []),
    ],
)
def test_split_passthrough_contract(argv, expected_head, expected_extra):
    from spa.cli import _split_passthrough

    assert _split_passthrough(argv) == (expected_head, expected_extra)


@pytest.mark.parametrize(
    ("argv", "expected_head", "expected_native"),
    [
        (["sh", "idx1"], ["sh"], ["idx1"]),
        (["lic", "--json"], ["lic"], ["--json"]),
        (["--json", "aws", "--list-regions"], ["--json", "aws"], ["--list-regions"]),
        (
            ["--env", "aws", "--start-dir", "licenses", "aws", "--json"],
            ["--env", "aws", "--start-dir", "licenses", "aws"],
            ["--json"],
        ),
        (["run", "--list"], ["run", "--list"], []),
    ],
)
def test_split_native_contract(argv, expected_head, expected_native):
    from spa.cli import _split_native

    assert _split_native(argv) == (expected_head, expected_native)


@pytest.mark.parametrize(
    ("argv", "expected_target"),
    [
        (["run", "--help"], ""),
        (["--start-dir", "/tmp/lab", "run", "splunk_cli", "--help"], "splunk_cli"),
        (["run", "--start-dir", "/tmp/lab", "splunk_cli", "--help"], "splunk_cli"),
        (["--env", "lab", "run", "splunk_cli", "--help"], "splunk_cli"),
        (["run", "--env", "lab", "splunk_cli", "--help"], "splunk_cli"),
        (
            [
                "run",
                "--hosts",
                "idx1",
                "--apps-playbook",
                "install_es",
                "splunk_cli",
                "--help",
            ],
            "splunk_cli",
        ),
        (["run", "splunk_cli", "--yes"], None),
    ],
)
def test_run_help_target_contract(argv, expected_target):
    from spa.cli import _run_help_target

    assert _run_help_target(argv) == expected_target


@pytest.mark.parametrize(
    "argv",
    [
        ["--json", "--env", "lab", "run", "splunk_cli", "--help"],
        ["--json", "run", "--env", "lab", "splunk_cli", "--help"],
    ],
)
def test_run_help_uses_selected_environment(monkeypatch, argv):
    from types import SimpleNamespace

    from spa.api import CommandResult
    from spa import cli

    captured = {}

    def fake_paths(start_dir, env_selector=None):
        captured["start_dir"] = start_dir
        captured["env_selector"] = env_selector
        return SimpleNamespace(
            spa_env_dir=Path("/selected-env"),
            config_file=Path("/selected-env/config/splunk_config.yml"),
        )

    class FakeSession:
        def describe_playbook(self, name):
            return CommandResult(ok=True, data={"name": name})

    monkeypatch.setattr(cli, "_paths", fake_paths)
    monkeypatch.setattr(cli, "open_session", lambda **_kwargs: FakeSession())

    assert cli.main(argv) == 0
    assert captured == {"start_dir": None, "env_selector": "lab"}


def test_run_help_rejects_conflicting_env(monkeypatch, capsys):
    """spa run NAME --help exits 2 when two --env values differ."""
    from types import SimpleNamespace

    from spa.api import CommandResult
    from spa import cli

    captured = {}

    def fake_paths(start_dir, env_selector=None):
        captured["env_selector"] = env_selector
        return SimpleNamespace(
            spa_env_dir=Path("/selected-env"),
            config_file=Path("/selected-env/config/splunk_config.yml"),
        )

    class FakeSession:
        def describe_playbook(self, name):
            return CommandResult(ok=True, data={"name": name})

    monkeypatch.setattr(cli, "_paths", fake_paths)
    monkeypatch.setattr(cli, "open_session", lambda **_kwargs: FakeSession())

    assert (
        cli.main(["--json", "--env", "one", "run", "--env", "two", "splunk_cli", "--help"])
        == 2
    )
    assert "env_selector" not in captured
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "data" not in payload
    assert "one" in payload["error"]
    assert "two" in payload["error"]
    assert "spa --env one run NAME --help" in payload["error"]


def test_global_env_reaches_validate(monkeypatch):
    """spa --env lab validate must resolve lab when the subcommand omits --env."""
    from types import SimpleNamespace

    from spa.api import CommandResult
    from spa import cli

    captured = {}

    def fake_paths(start_dir, env_selector=None):
        captured["env_selector"] = env_selector
        return SimpleNamespace(
            spa_env_dir=Path("/lab"),
            spa_home=Path("/spa"),
            pre3_cwd=None,
            config_file=Path("/lab/config/splunk_config.yml"),
        )

    class FakeSession:
        def validate(self, **_kwargs):
            return CommandResult(ok=True)

    monkeypatch.setattr(cli, "_paths", fake_paths)
    monkeypatch.setattr(cli, "open_session", lambda **_kwargs: FakeSession())

    assert cli.main(["--env", "lab", "validate", "--json"]) == 0
    assert captured["env_selector"] == "lab"


def _stub_validate_success(monkeypatch):
    """Keep path resolution real and skip schema/ansible validation."""
    from spa.api import CommandResult, open_session
    from spa import cli

    # apply_paths_env setdefaults SPLUNK_CONFIG_FILE. Track it so a prior
    # in-process spa command cannot pin the next test's config_file.
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", "")
    monkeypatch.delenv("SPLUNK_CONFIG_FILE")

    def fake_open(**kwargs):
        session = open_session(**kwargs)

        def validate(**_kwargs):
            return CommandResult(ok=True, data={"steps": []})

        session.validate = validate
        return session

    monkeypatch.setattr(cli, "open_session", fake_open)


def test_agent_validate_envelope_identifies_registered_env(tmp_path, monkeypatch, capsys):
    """spa --agent --env lab validate puts registry identity before data."""
    from spa.registry import register_environment
    from spa import cli

    dest = write_min_env(tmp_path / "lab")
    register_environment("lab", dest)
    _stub_validate_success(monkeypatch)

    assert cli.main(["--agent", "--env", "lab", "validate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == [
        "ok",
        "schema_version",
        "resolved_env_name",
        "env_dir",
        "config_file",
        "data",
    ]
    assert payload["ok"] is True
    assert payload["resolved_env_name"] == "lab"
    assert Path(payload["env_dir"]) == dest.resolve()
    assert Path(payload["config_file"]) == (dest / "config" / "splunk_config.yml").resolve()


def test_agent_validate_check_licenses_hides_filesystem_paths(tmp_path, monkeypatch, capsys):
    """Six license files stay as basename, status, and expiration unless --details."""
    import copy

    from spa.api import CommandResult, open_session
    from spa.registry import register_environment
    from spa import cli

    files = [
        {
            "basename": "license-%d.lic" % index,
            "path": "/tmp/Software/license-%d.lic" % index,
            "size_bytes": 100 + index,
            "license_type": "enterprise",
            "status": "valid",
            "expires_at": "2099-01-%02d" % index,
            "addons": [],
            "capabilities": ["enterprise"],
        }
        for index in range(1, 7)
    ]
    scan = {
        "ok": True,
        "software_dir": "/tmp/Software",
        "software_dir_exists": True,
        "discovered_files": files,
    }
    summary = {
        "configured_splunk_license_file": ["license-1.lic"],
        "license_manager_in_config": True,
        "itsi_in_config": False,
        "es_in_config": False,
        "files_found": 6,
    }
    data = {
        "config_file": "/lab/config/splunk_config.yml",
        "steps": [{"id": "license_files", "ok": True, "message": "License check OK"}],
        "licenses": summary,
        "license_scan": scan,
        "license_validation": {"errors": [], "warnings": []},
    }

    def fake_open(**kwargs):
        session = open_session(**kwargs)

        def validate(**_kwargs):
            assert _kwargs.get("check_licenses") is True
            return CommandResult(ok=True, data=copy.deepcopy(data))

        session.validate = validate
        return session

    dest = write_min_env(tmp_path / "lab")
    register_environment("lab", dest)
    monkeypatch.setattr(cli, "open_session", fake_open)

    assert cli.main(["--no-agent", "--env", "lab", "validate", "--check-licenses"]) == 0
    human = capsys.readouterr()
    assert "/tmp/Software/license-1.lic" in human.out
    assert "License check OK" in human.out

    assert cli.main(["--agent", "--env", "lab", "validate", "--check-licenses"]) == 0
    payload = json.loads(capsys.readouterr().out)
    body = payload["data"]
    assert body["licenses"] == summary
    encoded = json.dumps(body["license_scan"])
    assert "software_dir" not in body["license_scan"]
    assert "/tmp/Software/license-" not in encoded
    assert '"path"' not in encoded
    assert body["license_scan"]["discovered_files"] == [
        {
            "basename": "license-%d.lic" % index,
            "status": "valid",
            "expiration": "2099-01-%02d" % index,
        }
        for index in range(1, 7)
    ]

    assert cli.main(["--agent", "--env", "lab", "validate", "--check-licenses", "--details"]) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert detailed["data"]["license_scan"]["software_dir"] == "/tmp/Software"
    assert detailed["data"]["license_scan"]["discovered_files"][0]["path"] == "/tmp/Software/license-1.lic"


def test_detected_agent_uses_json_for_licenses_and_aws(monkeypatch):
    """A detected agent gets the JSON payload. --no-agent stays text. Shell stays text."""
    from types import SimpleNamespace

    from spa import cli

    seen = {}

    def fake_licenses(argv=None, as_agent=False):
        seen["licenses"] = as_agent
        return 0

    def fake_aws(argv=None, as_agent=False):
        seen["aws"] = as_agent
        return 0

    def fake_shell(argv=None, as_agent=False):
        seen["shell"] = as_agent
        return 0

    for name in (
        "SPA_AGENT",
        "CLAUDECODE",
        "CLAUDE_CODE",
        "CURSOR_AGENT",
        "CURSOR_TRACE_ID",
        "CODEX_THREAD_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPA_AGENT", "1")
    monkeypatch.setattr(
        cli,
        "_paths",
        lambda *args, **kwargs: SimpleNamespace(
            spa_env_dir=Path("/lab"),
            config_file=Path("/lab/config/splunk_config.yml"),
        ),
    )
    monkeypatch.setattr(cli, "open_session", lambda **kwargs: object())
    monkeypatch.setattr(cli, "_envelope_identity", lambda paths: None)
    monkeypatch.setattr(cli, "env_dir_required_error", lambda paths: None)
    monkeypatch.setattr(cli, "venv_required_error", lambda paths: None)
    monkeypatch.setattr("spa.licenses.main", fake_licenses)
    monkeypatch.setattr("spa.aws.main", fake_aws)
    monkeypatch.setattr("spa.shell.main", fake_shell)

    assert cli.main(["licenses"]) == 0
    assert seen["licenses"] is True
    assert cli.main(["aws", "--region", "eu-central-1", "--validate"]) == 0
    assert seen["aws"] is True
    assert cli.main(["--no-agent", "licenses"]) == 0
    assert seen["licenses"] is False

    seen.clear()
    monkeypatch.delenv("SPA_AGENT", raising=False)
    assert cli.main(["licenses"]) == 0
    assert seen["licenses"] is False


def test_agent_validate_unregistered_env_dir_identity_name_is_null(tmp_path, monkeypatch, capsys):
    """A directory that is not in the registry still reports identity, with a null name."""
    from spa import cli

    dest = write_min_env(tmp_path / "loose")
    _stub_validate_success(monkeypatch)

    assert cli.main(["--agent", "--env", str(dest), "validate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == [
        "ok",
        "schema_version",
        "resolved_env_name",
        "env_dir",
        "config_file",
        "data",
    ]
    assert payload["resolved_env_name"] is None
    assert Path(payload["env_dir"]) == dest.resolve()
    assert Path(payload["config_file"]) == (dest / "config" / "splunk_config.yml").resolve()


def test_agent_skills_success_omits_env_identity(monkeypatch, capsys):
    """Commands that do not accept --env omit the identity keys."""
    from spa import cli

    monkeypatch.setattr(
        "spa.skills.install_skills",
        lambda **_kwargs: {"installed": []},
    )

    assert cli.main(["--agent", "skills", "install"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "resolved_env_name" not in payload
    assert "env_dir" not in payload
    assert "config_file" not in payload


def test_agent_unknown_env_omits_identity(capsys):
    """A missing environment is a failure envelope with no data and no identity."""
    from spa import cli

    assert cli.main(["--agent", "--env", "missing-lab", "validate"]) != 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert list(payload) == ["ok", "schema_version", "error"]
    assert "data" not in payload
    assert "missing-lab" in payload["error"]


def test_conflicting_env_exits_2(monkeypatch, capsys):
    """spa --env one validate --env two exits 2 and names both values."""
    from types import SimpleNamespace

    from spa.api import CommandResult
    from spa import cli

    resolved = {}

    def fake_paths(start_dir, env_selector=None):
        resolved["env_selector"] = env_selector
        return SimpleNamespace(
            spa_env_dir=Path("/lab"),
            spa_home=Path("/spa"),
            pre3_cwd=None,
            config_file=Path("/lab/config/splunk_config.yml"),
        )

    class FakeSession:
        def validate(self, **_kwargs):
            return CommandResult(ok=True)

    monkeypatch.setattr(cli, "_paths", fake_paths)
    monkeypatch.setattr(cli, "open_session", lambda **_kwargs: FakeSession())

    assert cli.main(["--env", "one", "validate", "--env", "two", "--json"]) == 2
    assert "env_selector" not in resolved
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "data" not in payload
    assert "one" in payload["error"]
    assert "two" in payload["error"]
    assert "spa --env one validate" in payload["error"]


def test_agent_identity_does_not_leak_between_cli_main_calls(tmp_path, monkeypatch, capsys):
    """The active identity is cleared after each cli.main invocation."""
    from spa.registry import register_environment
    from spa import cli

    lab = write_min_env(tmp_path / "lab")
    register_environment("lab", lab)
    _stub_validate_success(monkeypatch)

    assert cli.main(["--agent", "--env", "lab", "validate"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["resolved_env_name"] == "lab"

    assert cli.main(["--agent", "--help"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["ok"] is True
    assert "resolved_env_name" not in second
    assert "env_dir" not in second
    assert "config_file" not in second


def _write_env_config(dest: Path) -> Path:
    path = dest / "config" / "splunk_config.yml"
    path.write_text("{}\n", encoding="utf-8")
    return path


def test_agent_validate_config_mismatch_exits_2(tmp_path, monkeypatch, capsys):
    """--env plus a different --config is a usage error and does not validate."""
    from spa.registry import register_environment
    from spa.api import CommandResult, open_session
    from spa import cli

    lab = write_min_env(tmp_path / "lab")
    other = write_min_env(tmp_path / "other")
    lab_config = _write_env_config(lab)
    other_config = _write_env_config(other)
    register_environment("lab", lab)
    register_environment("other", other)

    called = {}

    def fake_open(**kwargs):
        session = open_session(**kwargs)

        def validate(**validate_kwargs):
            called["config"] = validate_kwargs.get("config")
            called["splunk_config_file"] = os.environ.get("SPLUNK_CONFIG_FILE")
            return CommandResult(ok=True, data={"steps": []})

        session.validate = validate
        return session

    monkeypatch.setattr(cli, "open_session", fake_open)
    monkeypatch.delenv("SPLUNK_CONFIG_FILE", raising=False)

    for argv in (
        ["--agent", "--env", "lab", "validate", "--config", str(other_config)],
        ["--agent", "validate", "--env", "lab", "--config", str(other_config)],
    ):
        called.clear()
        assert cli.main(argv) == 2
        assert called == {}
        assert os.environ.get("SPLUNK_CONFIG_FILE") != str(other_config.resolve())
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "ok": False,
            "schema_version": 1,
            "error": payload["error"],
        }
        error = payload["error"]
        assert str(other_config.resolve()) in error
        assert str(lab_config.resolve()) in error
        assert "Drop --config" in error
        assert "validated" not in error.lower()


def test_agent_validate_config_mismatch_names_shell_config_source(
    tmp_path, monkeypatch, capsys
):
    """A shell-selected expected config is identified as SPLUNK_CONFIG_FILE."""
    from spa.registry import register_environment
    from spa import cli

    lab = write_min_env(tmp_path / "lab")
    lab_config = _write_env_config(lab)
    other = write_min_env(tmp_path / "other")
    other_config = _write_env_config(other)
    register_environment("lab", lab)
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(lab_config))
    _stub_validate_success(monkeypatch)

    assert (
        cli.main(
            ["--agent", "--env", "lab", "validate", "--config", str(other_config)]
        )
        == 2
    )
    error = json.loads(capsys.readouterr().out)["error"]
    assert "from SPLUNK_CONFIG_FILE" in error
    assert str(lab_config.resolve()) in error


def test_config_argument_falls_back_to_spa_home(tmp_path, monkeypatch):
    """CLI matching and validation use the same fallback for a relative config."""
    from types import SimpleNamespace

    from spa.cli import _resolved_config_argument
    from spa.validate import resolve_config_path

    spa_home = tmp_path / "spa-home"
    config = spa_home / "relative.yml"
    config.parent.mkdir(parents=True)
    config.write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    paths = SimpleNamespace(spa_home=spa_home)

    assert resolve_config_path("relative.yml", paths) == config.resolve()
    assert _resolved_config_argument("relative.yml", paths) == config.resolve()


def test_agent_validate_matching_config_keeps_env_identity(tmp_path, monkeypatch, capsys):
    """--env and --config of that env's file succeed with that env's identity."""
    from spa.registry import register_environment
    from spa import cli

    lab = write_min_env(tmp_path / "lab")
    lab_config = _write_env_config(lab)
    register_environment("lab", lab)
    _stub_validate_success(monkeypatch)

    assert (
        cli.main(["--agent", "--env", "lab", "validate", "--config", str(lab_config)])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["resolved_env_name"] == "lab"
    assert Path(payload["env_dir"]) == lab.resolve()
    assert Path(payload["config_file"]) == lab_config.resolve()

    monkeypatch.chdir(lab)
    assert (
        cli.main(
            ["--agent", "--env", "lab", "validate", "--config", "config/splunk_config.yml"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolved_env_name"] == "lab"
    assert Path(payload["config_file"]) == lab_config.resolve()


def test_agent_validate_config_without_env_follows_file_env(tmp_path, monkeypatch, capsys):
    """Without --env, validate --config reports the env that owns the file."""
    from spa.registry import register_environment
    from spa import cli

    neutral = tmp_path / "cwd"
    neutral.mkdir()
    monkeypatch.chdir(neutral)
    monkeypatch.delenv("SPA_ENV_DIR", raising=False)

    other = write_min_env(tmp_path / "other")
    _write_env_config(other)
    register_environment("other", other)
    lab = write_min_env(tmp_path / "lab")
    lab_config = _write_env_config(lab)
    (lab / ".spa.yml").unlink()
    register_environment("lab", lab)
    _stub_validate_success(monkeypatch)

    assert cli.main(["--agent", "validate", "--config", str(lab_config)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolved_env_name"] == "lab"
    assert Path(payload["env_dir"]) == lab.resolve()
    assert Path(payload["config_file"]) == lab_config.resolve()
    assert Path(payload["env_dir"]) != other.resolve()


def _validate_paths_seen(monkeypatch):
    """Capture validate_env's re-resolved paths without stubbing session.validate."""
    from types import SimpleNamespace

    from spa import validate

    seen = []
    original_resolve = validate.resolve_spa_paths

    def capture_resolve(*args, **kwargs):
        paths = original_resolve(*args, **kwargs)
        seen.append(paths.spa_env_dir)
        return paths

    monkeypatch.setattr(validate, "resolve_spa_paths", capture_resolve)
    monkeypatch.setattr("spa.cli.venv_required_error", lambda _paths: None)
    monkeypatch.setattr(validate, "tool_path", lambda _paths, tool: tool)
    monkeypatch.setattr(
        validate.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="schema stopped"),
    )
    return seen


def test_agent_validate_config_owner_selects_owner_for_validation(tmp_path, monkeypatch, capsys):
    """A file-owned config validates against its owner, not the registered default."""
    from spa.registry import register_environment
    from spa import cli

    default = write_min_env(tmp_path / "default")
    _write_env_config(default)
    register_environment("default", default)
    lab = write_min_env(tmp_path / "lab")
    lab_config = _write_env_config(lab)
    register_environment("lab", lab)
    monkeypatch.delenv("SPA_ENV_DIR", raising=False)
    monkeypatch.delenv("SPLUNK_CONFIG_FILE", raising=False)
    seen = _validate_paths_seen(monkeypatch)

    assert cli.main(["--agent", "validate", "--config", str(lab_config)]) == 1
    assert seen == [lab.resolve()]
    assert json.loads(capsys.readouterr().out)["error"] == "schema stopped"


def test_agent_validate_explicit_env_selects_env_for_validation(tmp_path, monkeypatch, capsys):
    """An explicit --env keeps validation on that env despite shell defaults."""
    from spa.registry import register_environment
    from spa import cli

    default = write_min_env(tmp_path / "default")
    _write_env_config(default)
    register_environment("default", default)
    lab = write_min_env(tmp_path / "lab")
    lab_config = _write_env_config(lab)
    register_environment("lab", lab)
    monkeypatch.setenv("SPA_ENV_DIR", str(default))
    monkeypatch.delenv("SPLUNK_CONFIG_FILE", raising=False)
    seen = _validate_paths_seen(monkeypatch)

    assert (
        cli.main(["--agent", "--env", "lab", "validate", "--config", str(lab_config)])
        == 1
    )
    assert seen == [lab.resolve()]
    assert json.loads(capsys.readouterr().out)["error"] == "schema stopped"


def test_agent_validate_config_without_env_follows_unregistered_spa_yml(
    tmp_path, monkeypatch, capsys
):
    """An unregistered directory with .spa.yml still owns its config file."""
    from spa.registry import register_environment
    from spa import cli

    neutral = tmp_path / "cwd"
    neutral.mkdir()
    monkeypatch.chdir(neutral)
    monkeypatch.delenv("SPA_ENV_DIR", raising=False)

    other = write_min_env(tmp_path / "other")
    _write_env_config(other)
    register_environment("other", other)
    loose = write_min_env(tmp_path / "loose")
    loose_config = _write_env_config(loose)
    _stub_validate_success(monkeypatch)

    assert cli.main(["--agent", "validate", "--config", str(loose_config)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolved_env_name"] is None
    assert Path(payload["env_dir"]) == loose.resolve()
    assert Path(payload["config_file"]) == loose_config.resolve()
    assert "data" in payload


def test_agent_validate_unowned_config_omits_identity(tmp_path, monkeypatch, capsys):
    """Without --env, a config file with no owning env omits identity."""
    from spa.registry import register_environment
    from spa import cli

    neutral = tmp_path / "cwd"
    neutral.mkdir()
    monkeypatch.chdir(neutral)
    monkeypatch.delenv("SPA_ENV_DIR", raising=False)

    other = write_min_env(tmp_path / "other")
    _write_env_config(other)
    register_environment("other", other)
    orphan = tmp_path / "orphan"
    (orphan / "config").mkdir(parents=True)
    orphan_config = orphan / "config" / "splunk_config.yml"
    orphan_config.write_text("{}\n", encoding="utf-8")
    _stub_validate_success(monkeypatch)

    assert cli.main(["--agent", "validate", "--config", str(orphan_config)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "resolved_env_name" not in payload
    assert "env_dir" not in payload
    assert "config_file" not in payload
    assert "data" in payload

    plain = tmp_path / "loose.yml"
    plain.write_text("{}\n", encoding="utf-8")
    assert cli.main(["--agent", "validate", "--config", str(plain)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "resolved_env_name" not in payload
    assert "env_dir" not in payload
    assert "config_file" not in payload


def test_provision_help_includes_yes():
    result = run_spa(["provision", "--help"])
    assert result.returncode == 0, result.stderr
    assert "--yes" in result.stdout
    assert "-y" in result.stdout


def test_provision_yes_after_subcommand_auto_approves(monkeypatch):
    """spa provision --yes must be a subcommand flag, not only spa --yes provision."""
    satisfy_env_lookups(monkeypatch)
    captured = {}

    class FakeProvider:
        name = "test"

        def provision(self, extra, **_kwargs):
            captured["extra"] = extra
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    from spa.cli import main

    rc = main(["--no-agent", "provision", "--yes"])
    assert rc == 0
    assert captured["extra"][:2] == ["-e", "auto_approve=true"]


@pytest.mark.parametrize("argv", [["-y", "provision"], ["provision", "-y"]])
def test_provision_yes_works_before_or_after_subcommand(monkeypatch, argv):
    satisfy_env_lookups(monkeypatch)
    captured = []

    class FakeProvider:
        name = "test"

        def provision(self, extra, **_kwargs):
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

        def destroy(self, extra, **_kwargs):
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
    assert called.pop("run_log") is not None
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
    assert "spa venv create --shared --yes" in message
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
    result = run_spa(["run", "list"])
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
    result = run_spa(["--json", "run", "list"])
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

    def fake_run(playbook, paths, extra, on_progress=None, **_kwargs):
        captured["extra"] = extra
        captured["playbook"] = str(playbook)
        return 0

    monkeypatch.setattr("spa.playbooks.run_playbook", fake_run)
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_cli", "--yes", "--", "--help"])
    assert rc == 0
    assert captured.get("extra") == ["--help"]
    assert captured["playbook"].endswith("splunk_cli.yml")


@pytest.mark.parametrize(
    "argv",
    [
        ["--no-agent", "run", "splunk_cli", "--yes", "-vvv"],
        ["--no-agent", "-vvv", "run", "splunk_cli", "--yes"],
    ],
)
def test_run_repeatable_verbose_reaches_ansible(monkeypatch, argv):
    captured = {}

    def fake_run(playbook, paths, extra, on_progress=None, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("spa.playbooks.run_playbook", fake_run)
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="aws", provisioned=True),
    )
    from spa.cli import main

    rc = main(argv)
    assert rc == 0
    assert captured["verbosity"] == 3


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

    listing = run_spa(["run", "list", "--dir", "custom"], env=env)
    assert "Env playbooks" in listing.stdout
    assert "custom/foo" in listing.stdout
    json_listing = run_spa(["--json", "run", "list", "--dir", "custom"], env=env)
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
    result = run_spa(["--agent", "init", "list"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    ids = [item["id"] for item in payload["data"]["topologies"]]
    assert "single_node" in ids


def test_no_agent_text_list():
    result = run_spa(["--no-agent", "init", "list"])
    assert "Topologies:" in result.stdout
    assert "single_node" in result.stdout
    assert not result.stdout.strip().startswith("{")


def test_agent_schema():
    result = run_spa(["agent", "schema"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    names = {c["name"] for c in payload["data"]["commands"]}
    assert "run" in names
    assert "config explain" in names
    assert "features" not in names
    assert "shell" in names
    run = next(c for c in payload["data"]["commands"] if c["name"] == "run")
    flags = [item["long"] for item in run.get("flags") or []]
    assert "--hosts" in flags
    assert "--list" not in flags
    assert "--yes" in flags
    assert "spa --agent run list" in run["summary"]
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
    assert "spa --agent run list" in result.stdout
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
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_remove"])
    assert rc != 0
    assert not called


def test_human_run_mutating_accept(monkeypatch):
    called = _fake_run_playbook(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")
    from spa.cli import main

    rc = main(["--no-agent", "run", "splunk_remove"])
    assert rc == 0
    assert called


def test_human_run_prompt_names_playbook_and_risk(monkeypatch):
    from spa.confirm import prompt_text

    seen = []
    called = _fake_run_playbook(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
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
    satisfy_env_lookups(monkeypatch)
    from spa.confirm import prompt_text

    seen = []
    called = []

    class FakeProvider:
        name = "test"

        def provision(self, extra, **_kwargs):
            called.append("provision")
            return 0

        def destroy(self, extra, **_kwargs):
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
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
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

        def provision(self, extra, **_kwargs):
            called.append("provision")
            return 0

        def destroy(self, extra, **_kwargs):
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


def _assert_usage_rejection(argv, message):
    human = run_spa(["--no-agent", *argv])
    assert human.returncode == 2, human.stderr
    assert message in human.stderr
    assert human.stdout.strip() == ""
    agent = run_spa(["--json", *argv])
    assert agent.returncode == 2, agent.stdout
    assert agent.stderr == ""
    payload = json.loads(agent.stdout)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "data" not in payload
    assert message in payload["error"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["run"], "spa run needs a playbook or list."),
        (["run", "--list"], "Listing playbooks is: spa run list"),
        (["run", "--list", "--help"], "Listing playbooks is: spa run list"),
        (["init", "--list"], "Listing examples is: spa init list"),
        (["environment", "init", "--list"], "Listing examples is: spa init list"),
        (["hosts"], "spa hosts needs an action."),
        (["hosts", "--status"], "spa hosts needs an action."),
        (["logs"], "spa logs needs a run."),
        (["logs", "list", "--last"], "spa logs list does not take --last or --follow."),
        (["run", "list", "--yes"], "spa run list does not take run options."),
    ],
)
def test_catalog_usage_names_the_legal_command(argv, message):
    _assert_usage_rejection(argv, message)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["aws", "--list-regions"], "Listing regions is: spa aws regions list"),
        (["aws", "--list-amis"], "Listing amis is: spa aws amis list"),
        (["aws", "--list-instance-types"], "Listing instance-types is: spa aws instance-types list"),
        (["aws", "--list-key-pairs"], "Listing key-pairs is: spa aws key-pairs list"),
        (["aws", "--list-security-groups"], "Listing security-groups is: spa aws security-groups list"),
    ],
)
def test_aws_retired_list_flags_name_the_list_command(argv, message):
    result = run_spa(["--no-agent", *argv])
    assert result.returncode == 2, result.stderr
    assert message in result.stderr
    assert "Regions" not in result.stdout
    assert not result.stdout.lstrip().startswith("{")


def test_hidden_alias_expands_after_a_flag():
    from spa.cli import _expand_hidden_aliases

    assert _expand_hidden_aliases(["config", "--env", "lab", "sea", "region"]) == [
        "config",
        "--env",
        "lab",
        "search",
        "region",
    ]
    assert _expand_hidden_aliases(["config", "--yes", "top", "cm_2idxc_sh"]) == [
        "config",
        "--yes",
        "topology",
        "cm_2idxc_sh",
    ]


def test_aws_retired_list_flag_json_names_the_list_command():
    result = run_spa(["--json", "aws", "--list-regions"])
    assert result.returncode == 2
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload == {"ok": False, "error": "Listing regions is: spa aws regions list"}


def test_aws_list_help_keeps_flags_on_their_kind():
    parent = run_spa(["aws", "--help"])
    assert parent.returncode == 0, parent.stderr
    for flag in (
        "--list-regions",
        "--list-amis",
        "--list-instance-types",
        "--list-key-pairs",
        "--list-security-groups",
    ):
        assert flag not in parent.stdout
    amis = run_spa(["aws", "amis", "list", "--help"])
    types = run_spa(["aws", "instance-types", "list", "--help"])
    assert amis.returncode == 0, amis.stderr
    assert "--family" not in amis.stdout
    assert "--name-filter" in amis.stdout
    assert types.returncode == 0, types.stderr
    assert "--name-filter" not in types.stdout
    assert "--family" in types.stdout


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
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    from spa.cli import main

    rc = main(["--no-agent", "run", "--dir", "custom", "custom/foo"])
    assert rc != 0
    assert not called
    assert seen == [prompt_text("run custom/foo", risk=None)]
    assert "no playbook metadata" in seen[0]


def test_agent_config_header_set_replaces_the_comment_and_drops_omitted_fields(tmp_path):
    """A header set replaces the leading comment; a later set drops omitted fields."""
    dest = write_min_env(tmp_path / "env")
    config = dest / "config" / "splunk_config.yml"
    config.write_text(
        "# intent: previous\n# requirements: previous\n# notes: retire this line\nsplunk_hosts: []\n",
        encoding="utf-8",
    )
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}
    first = run_spa(
        [
            "--agent",
            "config",
            "header",
            "set",
            "--intent",
            "config-test",
            "--deploy",
            "spa provision --yes && spa deploy --yes",
            "--yes",
        ],
        env=env,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert first.stderr == ""
    payload = json.loads(first.stdout)
    assert payload["ok"] is True
    assert "data" in payload
    text = config.read_text(encoding="utf-8")
    assert text == (
        "# intent: config-test\n"
        "# deploy: spa provision --yes && spa deploy --yes\n"
        "splunk_hosts: []\n"
    )

    second = run_spa(
        ["--agent", "config", "header", "set", "--intent", "other", "--yes"],
        env=env,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert second.stderr == ""
    payload = json.loads(second.stdout)
    assert payload["ok"] is True
    assert list(second.stdout.splitlines()) == [second.stdout.strip()]
    text = config.read_text(encoding="utf-8")
    assert "# deploy:" not in text
    assert text == "# intent: other\nsplunk_hosts: []\n"


def test_human_config_header_set_unknown_flag_names_the_command_once():
    """Human stderr names spa config header set once."""
    result = run_spa(["--no-agent", "config", "header", "set", "--not-a-flag"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    error_lines = [line for line in result.stderr.splitlines() if ": error:" in line]
    assert error_lines == [
        "spa: error: spa config header set: unrecognized arguments: --not-a-flag"
    ]
    assert error_lines[0].count("spa config header set") == 1


def test_config_header_flag_value_set_is_not_the_action():
    """A value of set after config header is not the set action."""
    result = run_spa(["--no-agent", "config", "header", "--intent", "set"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert "spa config header needs an action" in result.stderr
    assert "spa config header set:" not in result.stderr


def test_human_config_header_set_prompt_names_the_config_file(tmp_path, monkeypatch):
    """The human prompt says the command changes splunk_config.yml and does not write."""
    dest = write_min_env(tmp_path / "env")
    config = dest / "config" / "splunk_config.yml"
    original = "splunk_hosts: []\n"
    config.write_text(original, encoding="utf-8")
    seen = []
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(dest))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    from spa.cli import main

    rc = main(["--no-agent", "config", "header", "set", "--intent", "config-test"])
    assert rc != 0
    assert len(seen) == 1
    assert "will change splunk_config.yml" in seen[0]
    assert "host" not in seen[0]
    assert config.read_text(encoding="utf-8") == original


def test_agent_config_header_set_unknown_flag_names_the_command():
    """An unknown flag on header set exits 2 and names spa config header set."""
    result = run_spa(["--agent", "config", "header", "set", "--not-a-flag"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == ""
    assert list(result.stdout.splitlines()) == [result.stdout.strip()]
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert payload["schema_version"] == 1
    assert payload["error"] == "spa config header set: unrecognized arguments: --not-a-flag"


def test_agent_config_header_set_dry_run_requires_yes_and_does_not_write(tmp_path):
    """Agent dry-run still requires --yes, and --yes does not write the file."""
    dest = write_min_env(tmp_path / "env")
    config = dest / "config" / "splunk_config.yml"
    original = "# intent: previous\nsplunk_hosts: []\n"
    config.write_text(original, encoding="utf-8")
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}

    refused = run_spa(
        ["--agent", "config", "header", "set", "--intent", "config-test", "--dry-run"],
        env=env,
    )
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert refused.stderr == ""
    assert list(refused.stdout.splitlines()) == [refused.stdout.strip()]
    body = json.loads(refused.stdout)
    assert body == {
        "ok": False,
        "schema_version": 1,
        "error": "spa config header set requires -y/--yes in agent mode.",
    }
    assert config.read_text(encoding="utf-8") == original

    preview = run_spa(
        [
            "--agent",
            "config",
            "header",
            "set",
            "--intent",
            "config-test",
            "--dry-run",
            "--yes",
        ],
        env=env,
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert preview.stderr == ""
    body = json.loads(preview.stdout)
    assert body["ok"] is True
    assert config.read_text(encoding="utf-8") == original
