"""spa config explain and search: one schema level, shared with a future GUI."""

import json

import pytest

from spa.config_edit import _ONE_OF
from spa.config_tree import explain_candidates, explain_config, search_config
from spa_testutil import run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_host_identity_registry_matches_the_validator():
    plugin = __import__("pathlib").Path(__file__).resolve().parents[1] / "ansible" / "plugins" / "inventory"
    import sys

    sys.path.insert(0, str(plugin))
    from schema import SplunkHost

    with pytest.raises(Exception) as caught:
        SplunkHost(roles=["indexer"])
    text = str(caught.value)
    for name in ("name", "list", "iter"):
        assert name in text
    assert _ONE_OF[("splunk_hosts",)] == ("name", "list", "iter")
    assert _ONE_OF[("splunk_idxclusters",)] == ("idxc_name",)
    assert _ONE_OF[("splunk_shclusters",)] == ("shc_name",)
    assert _ONE_OF[("splunk_environments",)] == ("splunk_env_name",)


def test_user_paths_hide_empty_brackets_and_split_host_identity():
    data = explain_config("splunk_hosts")
    assert data["path"] == "splunk_hosts"
    assert "[]" not in data["path"]
    assert [item["name"] for item in data["identity"]["one_of"]] == ["name", "list", "iter"]
    names = [item["name"] for item in data["fields"]]
    assert "roles" in names
    assert "name" not in names
    assert "os" in names
    assert all("." not in item["name"] for item in data["fields"])
    assert "when_to_use" in data
    assert "when_not_to_use" not in data
    assert "indexer" in data["example"]
    assert "cluster_manager" not in data["example"]
    assert "spa config merge" in data["note"]


def test_scope_names_the_other_route_and_how_values_combine():
    global_packages = explain_config("os.packages")
    assert global_packages["scope"] == {
        "applies_to": "all_hosts",
        "per_host_path": "splunk_hosts.os.packages",
        "behavior": "merge",
    }
    host_packages = explain_config("splunk_hosts.os.packages")
    assert host_packages["scope"]["applies_to"] == "one_host"
    assert host_packages["scope"]["global_path"] == "os.packages"
    assert host_packages["scope"]["behavior"] == "merge"
    assert explain_config("os.time_zone")["scope"]["behavior"] == "replace"
    assert explain_config("custom")["scope"]["behavior"] == "mixed"
    version = explain_config("splunk_defaults.splunk_version")
    assert version["scope"]["per_host_path"] == "splunk_hosts.splunk_version"
    assert version["scope"]["behavior"] == "replace"
    assert "scope" not in explain_config("splunk_defaults.splunk_ssl")
    assert "scope" not in explain_config("splunk_hosts.roles")
    os_page = explain_config("os")
    packages = next(item for item in os_page["fields"] if item["name"] == "packages")
    assert "splunk_hosts.os.packages" in packages["description"]
    host_page = explain_config("splunk_hosts")
    host_os = next(item for item in host_page["fields"] if item["name"] == "os")
    assert "os" in host_os["description"]
    found = {item["path"]: item["description"] for item in search_config("packages")["matches"]}
    assert "All hosts" in found["os.packages"]
    assert "splunk_hosts.os.packages" in found["os.packages"]
    assert "Per-host" in found["splunk_hosts.os.packages"]
    assert "os.packages" in found["splunk_hosts.os.packages"]


def test_explain_os_keeps_decisions_on_the_selected_node_only():
    data = explain_config("os")
    assert "Linux guest" in data["when_to_use"]
    assert "ssh_username" in data["when_not_to_use"]
    packages = next(item for item in data["fields"] if item["name"] == "packages")
    assert "when_to_use" not in packages
    assert "acl" in data["example"]
    child = explain_config("os.packages")
    assert child["path"] == "os.packages"
    assert "fields" not in child or child["fields"] == []


def test_host_role_field_has_no_separate_decision_and_uses_a_selector():
    data = explain_config("splunk_hosts.roles")
    assert data["path"] == "splunk_hosts.roles"
    assert "when_to_use" not in data
    assert "when_not_to_use" not in data
    assert "allowed" in data
    assert "indexer" in data["allowed"]
    assert "splunk_hosts[name=NAME].roles" in data["command"]
    assert "[]" not in json.dumps(data["path"])


def test_search_returns_paths_and_one_line_without_commands():
    data = search_config("packages")
    paths = [item["path"] for item in data["matches"]]
    assert "os.packages" in paths
    assert "splunk_hosts.os.packages" in paths
    for item in data["matches"]:
        assert set(item) == {"path", "description"}
        assert "spa config" not in item["description"]
    assert data["total_matches"] >= len(data["matches"])
    assert len(data["matches"]) <= 10


def test_candidates_are_user_paths_for_a_later_shell():
    roots = explain_candidates("")
    assert "splunk_hosts" in roots
    assert "os" in roots
    assert all("[]" not in path for path in roots)
    children = explain_candidates("splunk_defaults")
    assert any(path.startswith("splunk_defaults.") for path in children)
    assert "splunk_defaults" not in children or children != ["splunk_defaults"]


def test_secret_example_uses_an_environment_lookup():
    data = explain_config("splunk_defaults.splunk_admin_password")
    assert "--from-env" in data["command"]
    blob = json.dumps(data)
    assert "lookup('env'" not in blob or "--from-env" in data["command"]
    assert "password" not in data.get("example", "").lower() or "--from-env" in data.get("example", "")


def test_cli_explain_is_the_human_page_and_the_same_agent_data():
    human = run_spa(["config", "explain", "splunk_hosts"])
    assert human.returncode == 0, human.stderr
    assert "IDENTITY" in human.stdout
    assert "WHEN:" in human.stdout
    assert "[]" not in human.stdout
    agent = run_spa(["--agent", "config", "explain", "splunk_hosts"])
    payload = json.loads(agent.stdout)
    assert payload["ok"] is True
    assert payload["data"]["path"] == "splunk_hosts"
    assert "text" not in payload["data"]
    bare = run_spa(["--agent", "config", "schema", "--markdown"])
    assert bare.returncode == 2
    error = json.loads(bare.stdout)
    assert error["ok"] is False
    assert "data" not in error
    assert "config explain" in error["error"]


def test_features_command_is_removed():
    result = run_spa(["features", "list"])
    assert result.returncode == 2
    assert "config explain" in result.stderr
