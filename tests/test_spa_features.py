"""Feature catalog lookup (`spa features`)."""

import json
import sys
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_features_list_includes_topologies_and_os():
    result = run_spa(["features", "list"])
    assert result.returncode == 0, result.stderr
    assert "topology.c1" in result.stdout
    assert "provider.aws" in result.stdout
    assert "setting.os" in result.stdout


def test_os_guidance_says_what_the_block_provides():
    """The title alone cannot tell an operator what an os: block covers."""
    result = run_spa(["--json", "features", "list"])
    assert result.returncode == 0, result.stderr
    features = {item["id"]: item for item in json.loads(result.stdout)["data"]["features"]}
    guidance = features["setting.os"]["when_to_use"].lower()
    for topic in ("packages", "hostname", "time", "selinux", "ssh", "splunk user"):
        assert topic in guidance, topic
    assert "after init" in guidance
    assert "ssh_username" in features["setting.os"]["when_not_to_use"]


def test_implemented_settings_have_operator_guidance():
    """Records that write YAML must say what they do, not only a title."""
    result = run_spa(["--json", "features", "list"])
    assert result.returncode == 0, result.stderr
    show = run_spa(["--json", "features", "show", "setting.apps"])
    assert show.returncode == 0, show.stderr
    apps = json.loads(show.stdout)["data"]["feature"]
    blob = (apps.get("when_to_use") or "").lower()
    for topic in ("splunkbase", "local", "target_roles", "lookup"):
        assert topic in blob, topic
    assert "SPLUNKBASE" in (apps.get("snippet") or "")
    for item in json.loads(result.stdout)["data"]["features"]:
        if item.get("kind") != "setting":
            continue
        if item["id"] in {
            "setting.ldap",
            "setting.cm_deploymentclient",
            "setting.apps_cli",
            "setting.outputs",
            "setting.legacy_aws",
        }:
            assert item.get("when_not_to_use"), item["id"]
            continue
        text = item.get("when_to_use") or ""
        assert len(text) >= 80, item["id"]


def test_feat_alias_lists_features():
    result = run_spa(["feat", "list"])
    assert result.returncode == 0, result.stderr
    assert "topology.c1" in result.stdout
    assert "provider.aws" in result.stdout


def test_list_guidance_is_aligned_under_the_title():
    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa.catalog import format_feature_rows

    rows = [
        {"id": "topology.s1", "title": "S1 single node", "sva": "S1", "when_to_use": "Config-test."},
        {"id": "setting.baseconfig_save", "title": "Save apps", "when_to_use": "Pull apps back."},
    ]
    lines = format_feature_rows(rows, width=100).splitlines()
    title_column = lines[0].index("S1 single node")
    assert title_column == len("setting.baseconfig_save") + 2
    assert lines[0].endswith("[SVA S1]")
    assert lines[1] == " " * title_column + "Config-test."
    assert lines[3] == " " * title_column + "Pull apps back."


def test_show_wraps_prose_but_not_key_lines():
    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa.catalog import format_feature_text

    item = {"id": "setting.os", "title": "OS", "kind": "setting", "when_to_use": "word " * 40}
    details = [{"path": "os.packages", "type": "list[string]", "allowed": ["a" * 120]}]
    lines = format_feature_text(item, key_details=details, width=80).splitlines()
    prose = [line for line in lines if line.startswith("when_to_use") or line.startswith("  word")]
    assert len(prose) > 1
    assert all(len(line) <= 80 for line in prose)
    key_line = next(line for line in lines if line.strip().startswith("os.packages"))
    assert "allowed=" + "a" * 120 in key_line


def test_long_guidance_wraps_with_the_same_indent():
    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa.catalog import format_feature_rows

    rows = [{"id": "provider.aws", "title": "AWS", "when_to_use": "word " * 40}]
    lines = format_feature_rows(rows, width=80).splitlines()
    indent = " " * (len("provider.aws") + 2)
    assert len(lines) > 2
    for line in lines[1:]:
        assert line.startswith(indent)
        assert len(line) <= 80


def test_every_list_record_has_decision_guidance():
    result = run_spa(["--json", "features", "list"])
    assert result.returncode == 0, result.stderr
    features = json.loads(result.stdout)["data"]["features"]
    assert features
    for feature in features:
        assert feature.get("title"), feature["id"]
        assert feature.get("when_to_use") or feature.get("when_not_to_use"), feature["id"]
        assert "snippet" not in feature
        assert "keys" not in feature


def test_features_search_ssl():
    result = run_spa(["features", "search", "ssl"])
    assert result.returncode == 0, result.stderr
    assert "setting.ssl" in result.stdout


def test_features_search_os():
    result = run_spa(["features", "search", "os"])
    assert result.returncode == 0, result.stderr
    assert "setting.os" in result.stdout


def test_features_show_c1():
    result = run_spa(["features", "show", "topology.c1"])
    assert result.returncode == 0, result.stderr
    assert "C1" in result.stdout
    assert "cm_2idxc_sh_uf" in result.stdout
    assert "keys:" not in result.stdout


def test_features_show_keys_includes_schema_metadata_and_placeholders():
    result = run_spa(["features", "show", "setting.hosts", "--keys"])
    assert result.returncode == 0, result.stderr
    assert "keys:" in result.stdout
    assert "splunk_hosts[].roles" in result.stdout
    assert "list[enum]" in result.stdout
    assert "required" in result.stdout
    assert "allowed=cluster_manager" in result.stdout


def test_features_show_keys_merges_catalog_only_metadata():
    result = run_spa(["features", "show", "provider.aws", "--keys"])
    assert result.returncode == 0, result.stderr
    assert "terraform.aws.ssh_username" in result.stdout
    assert "Login user must match the AMI" in result.stdout
    assert "terraform.aws.root_volume_type" in result.stdout
    assert "allowed=gp3|gp2" not in result.stdout
    volume_lines = [
        line
        for line in result.stdout.splitlines()
        if "terraform.aws.root_volume_type" in line
    ]
    assert volume_lines
    assert "string" in volume_lines[0]
    assert "allowed=" not in volume_lines[0]
    assert "lab often uses gp3" in result.stdout.lower()


def test_features_keys_schema_owns_former_orphans():
    result = run_spa(["--json", "features", "keys"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)["data"]
    assert payload.get("missing_key_detail") in (None, [],)
    by_key = {row["key"]: row for row in payload["keys"]}
    for key in (
        "terraform.aws.ssh_username",
        "terraform.aws.root_volume_type",
        "splunk_defaults.splunk_user",
        "splunk_defaults.splunk_group",
    ):
        assert by_key[key]["in_schema"] is True
        assert by_key[key]["has_key_detail"] is True


def test_features_show_keys_rejects_other_actions():
    result = run_spa(["features", "list", "--keys"])
    assert result.returncode == 2
    assert "requires" in result.stderr
    assert not result.stdout.strip().startswith("{")


def test_features_json_after_subcommand():
    trailing = run_spa(["features", "list", "--json"])
    leading = run_spa(["--json", "features", "list"])
    assert trailing.returncode == 0, trailing.stderr
    assert leading.returncode == 0, leading.stderr
    assert json.loads(trailing.stdout) == json.loads(leading.stdout)
    ids = [item["id"] for item in json.loads(trailing.stdout)["data"]["features"]]
    assert "topology.c1" in ids


def test_features_keys_misuse_is_enveloped_in_agent_mode():
    result = run_spa(["--json", "features", "list", "--keys"])
    assert result.returncode == 2
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "show ID --keys" in payload["error"]


def test_features_keys_cover_schema():
    result = run_spa(["features", "keys"])
    assert result.returncode == 0, result.stderr
    assert "missing:" not in result.stdout
    assert "missing detail:" not in result.stdout


def test_features_json_search():
    result = run_spa(["--json", "features", "search", "architecture"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    ids = [item["id"] for item in payload["data"]["features"]]
    assert "setting.splunk_architecture" in ids
    assert "snippet" not in payload["data"]["features"][0]
    assert "keys" not in payload["data"]["features"][0]


def test_features_json_show_only_adds_details_with_keys_flag():
    compact = run_spa(["--json", "features", "show", "setting.volumes"])
    detailed = run_spa(
        ["--json", "features", "show", "setting.volumes", "--keys"]
    )
    assert compact.returncode == 0, compact.stderr
    assert detailed.returncode == 0, detailed.stderr
    compact_feature = json.loads(compact.stdout)["data"]["feature"]
    detailed_feature = json.loads(detailed.stdout)["data"]["feature"]
    assert "keys" not in compact_feature
    assert "key_details" not in compact_feature
    paths = {item["path"] for item in detailed_feature["key_details"]}
    assert "splunk_defaults.splunk_indexer_volumes.<volume>.path" in paths
