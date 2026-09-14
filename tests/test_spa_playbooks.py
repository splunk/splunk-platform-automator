"""Playbook metadata parser, catalog completeness, and legacy stems."""

import json
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT

pytestmark = pytest.mark.local

sys.path.insert(0, str(LIB))

from spa.api import open_session  # noqa: E402
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
