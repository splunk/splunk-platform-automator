"""Playbook metadata parser, catalog completeness, and legacy stems."""

import json
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.api import open_session  # noqa: E402
from spa.confirm import (  # noqa: E402
    ConfirmationError,
    ensure_confirmed,
    prompt_text,
    requires_confirmation,
)
from spa.playbooks import (  # noqa: E402
    MetadataError,
    catalog,
    describe,
    parse_playbook_metadata,
    rewrite_legacy_name,
)
from spa.paths import resolve_spa_paths  # noqa: E402


def test_rewrite_legacy_stem():
    assert rewrite_legacy_name("run_splunk_command") == ("splunk_cli", "run_splunk_command")
    assert rewrite_legacy_name("ansible/start_splunk.yml")[0].endswith("splunk_start.yml")
    assert rewrite_legacy_name("splunk_cli") == ("splunk_cli", None)


def test_parse_metadata_happy(tmp_path):
    path = tmp_path / "ok.yml"
    path.write_text(
        "---\n"
        "# spa-run:\n"
        "#   schema: 1\n"
        "#   summary: One line.\n"
        "#   description: Longer text.\n"
        "#   category: operations\n"
        "#   risk: read-only\n"
        "- hosts: localhost\n"
    )
    meta = parse_playbook_metadata(path)
    assert meta["summary"] == "One line."
    assert meta["risk"] == "read-only"


def test_parse_metadata_malformed(tmp_path):
    path = tmp_path / "bad.yml"
    path.write_text("---\n# spa-run:\n#   schema: 1\n#   summary: [\n- hosts: localhost\n")
    with pytest.raises(MetadataError):
        parse_playbook_metadata(path)


def test_parse_metadata_unknown_risk(tmp_path):
    path = tmp_path / "risk.yml"
    path.write_text(
        "---\n"
        "# spa-run:\n"
        "#   schema: 1\n"
        "#   summary: x\n"
        "#   description: y\n"
        "#   category: operations\n"
        "#   risk: dangerous\n"
        "- hosts: localhost\n"
    )
    with pytest.raises(MetadataError, match="risk"):
        parse_playbook_metadata(path)


def test_parse_metadata_missing_summary(tmp_path):
    path = tmp_path / "nosum.yml"
    path.write_text(
        "---\n"
        "# spa-run:\n"
        "#   schema: 1\n"
        "#   description: y\n"
        "#   category: operations\n"
        "#   risk: mutating\n"
        "- hosts: localhost\n"
    )
    with pytest.raises(MetadataError, match="summary"):
        parse_playbook_metadata(path)


def test_first_party_catalog_has_valid_metadata():
    paths = resolve_spa_paths(start_dir=str(PROJECT_ROOT))
    rows = catalog(paths)
    first_party = [row for row in rows if row["source"] in {"ansible", "verification"}]
    assert first_party
    for row in first_party:
        assert row.get("missing") is False, row["name"]
        assert row.get("summary"), row["name"]
        assert row["metadata"]["schema"] == 1
        want = row["risk"] != "read-only"
        assert row.get("requires_confirmation") is want, row["name"]


def test_session_describe_does_not_run(monkeypatch):
    called = []
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0)
    session = open_session(start_dir=str(PROJECT_ROOT))
    result = session.describe_playbook("splunk_cli")
    assert result.ok
    assert result.data["name"] == "splunk_cli"
    assert not called
    json.dumps(result.data)


def test_describe_legacy_stem():
    paths = resolve_spa_paths(start_dir=str(PROJECT_ROOT))
    data = describe("provision_terraform_aws", paths)
    assert data["name"] == "aws_provision"
    assert data["renamed_from"] == "provision_terraform_aws"
    assert data.get("requires_confirmation") is True


def test_requires_confirmation_from_risk():
    assert requires_confirmation(risk="read-only", missing_metadata=False) is False
    assert requires_confirmation(risk="mutating", missing_metadata=False) is True
    assert requires_confirmation(risk="destructive", missing_metadata=False) is True
    assert requires_confirmation(missing_metadata=True) is True
    assert requires_confirmation(risk=None, missing_metadata=False) is True


def test_ensure_confirmed_agent_never_prompts(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("prompted")))
    with pytest.raises(ConfirmationError, match="requires -y/--yes"):
        ensure_confirmed("destroy", confirm=False, agent=True)
    ensure_confirmed("destroy", confirm=True, agent=True)


def test_prompt_text_names_command_and_risk():
    destroy = prompt_text("destroy", risk="destructive")
    assert destroy.startswith("destroy ")
    assert "permanently remove or uninstall" in destroy
    assert destroy.endswith("Proceed? [y/N] ")

    deploy = prompt_text("deploy", risk="mutating")
    assert deploy.startswith("deploy ")
    assert "change hosts or configuration" in deploy

    unknown = prompt_text("run custom/foo", risk=None)
    assert unknown.startswith("run custom/foo ")
    assert "no playbook metadata" in unknown


def test_ensure_confirmed_human_prompt_uses_risk(monkeypatch):
    seen = []
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    with pytest.raises(ConfirmationError, match="run splunk_remove cancelled"):
        ensure_confirmed("run splunk_remove", confirm=False, agent=False, risk="destructive")
    assert seen == [prompt_text("run splunk_remove", risk="destructive")]


def test_ensure_confirmed_prints_hosts_not_extra_vars(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    ensure_confirmed(
        "deploy",
        confirm=False,
        agent=False,
        risk="mutating",
        details=["hosts: idx1, sh1"],
    )
    captured = capsys.readouterr()
    assert "hosts: idx1, sh1" in captured.err
    assert "extra-var" not in captured.err
    assert "password" not in captured.err.lower()
