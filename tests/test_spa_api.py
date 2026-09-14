"""In-process SpaSession contract (GUI/backend), not the spa CLI."""

import json
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT, run_spa

pytestmark = pytest.mark.local

sys.path.insert(0, str(LIB))

from spa.api import (  # noqa: E402
    SCHEMA_VERSION,
    CommandResult,
    RemoteSessionNotImplemented,
    jsonable,
    open_session,
)


def test_open_session_rejects_remote_url():
    with pytest.raises(RemoteSessionNotImplemented):
        open_session(url="https://controller.example")


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
    assert "single_node.yml" in result.data
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
