"""spa config explain and search: one schema level, shared with a future GUI."""

import json

import pytest

from spa.catalog import feature_command, load_features
from spa.config_edit import _ONE_OF, config_templates
from spa.config_tree import explain_candidates, explain_config, format_explain, search_config
from spa_testutil import PROJECT_ROOT, run_spa

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
        assert {"path", "description"} <= set(item)
        assert set(item) <= {"path", "description", "type", "default", "allowed"}
        assert "command" not in item
        assert "spa config" not in item["description"]
    assert data["total_matches"] >= len(data["matches"])
    assert len(data["matches"]) <= 10


def test_search_matches_shipped_templates_by_name_and_summary():
    for query in ("remote-provider", "tls"):
        data = search_config(query)
        by_path = {item["path"]: item["description"] for item in data["matches"]}
        assert "template.remote-provider" in by_path, query
        assert "TLS" in by_path["template.remote-provider"]
        for item in data["matches"]:
            assert {"path", "description"} <= set(item)
            assert set(item) <= {"path", "description", "type", "default", "allowed"}
            assert "command" not in item
            assert "spa config" not in item["description"]


def test_explain_template_returns_the_merge_command():
    data = explain_config("template.remote-provider")
    assert data["path"] == "template.remote-provider"
    assert "TLS" in data["description"]
    command = "spa config merge remote-provider --yes"
    assert data["command"] == command
    assert data["example"] == command
    with pytest.raises(KeyError):
        explain_config("template.missing")


def _explain_inventory_paths():
    paths = {""}
    queue = list(explain_candidates(""))
    while queue:
        path = queue.pop()
        if path in paths:
            continue
        paths.add(path)
        try:
            queue.extend(explain_candidates(path))
        except TypeError:
            continue
    for item in load_features(PROJECT_ROOT):
        if item.get("id"):
            paths.add(str(item["id"]))
    for row in config_templates(PROJECT_ROOT).get("templates") or []:
        name = row.get("name")
        if name:
            paths.add("template.%s" % name)
    return paths


@pytest.mark.parametrize(
    "path",
    sorted(_explain_inventory_paths()),
    ids=lambda value: value or "<root>",
)
def test_explain_commands_are_human_spelling_on_every_page(path):
    """CFG-CLI-005. Explain command/example never includes --agent, including templates."""
    try:
        data = explain_config(path)
    except (KeyError, TypeError):
        return
    blob = json.dumps(data)
    label = path or "<root>"
    assert "--agent" not in blob, label
    assert "--agent" not in format_explain(data), label
    command = data.get("command")
    if command:
        assert str(command).startswith("spa "), (path, command)


def test_explain_inventory_includes_canonical_human_commands():
    """Inventory-wide command examples without re-walking every explain page."""
    template = explain_config("template.remote-provider")
    assert "config merge" in template["command"]
    seen_commands = []
    for item in load_features(PROJECT_ROOT):
        command = feature_command(item)
        if not command or not command.get("command"):
            continue
        text = command["command"]
        seen_commands.append(text)
        assert "--agent" not in text, text
        assert text.startswith("spa "), text
    assert any(command.startswith("spa config set ") for command in seen_commands)
    assert any(command.startswith("spa config topology ") for command in seen_commands)
    assert any(command.startswith("spa config provider ") for command in seen_commands)
    assert any(command.startswith("spa config add ") for command in seen_commands)
    assert any(command.startswith("spa apps add ") for command in seen_commands)


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


def test_explain_ccm_instance_type_is_global_only():
    data = explain_config("ccm.instance_type")
    assert data["path"] == "ccm.instance_type"
    assert "scope" not in data
    text = (data.get("description") or "").lower()
    assert "every host" in text
    assert "no per-host instance type" in text
    human = format_explain(data)
    assert "every host" in human.lower()
    assert "Per-host" not in human


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


_SEARCH_HIT_FIELDS = {"path", "description", "type", "default", "allowed"}


def test_explain_string_example_uses_unquoted_recommended_not_schema_default():
    """CFG-CLI-005 CFG-CLI-007. Lab instance type is recommended; omit-safe default stays default."""
    data = explain_config("terraform.aws.instance_type")
    assert data["type"] == "string"
    assert data["default"] == "t2.micro"
    assert data["example"] == "spa config set terraform.aws.instance_type t3.medium"
    assert data["command"] == data["example"]
    human = format_explain(data)
    assert "default: t2.micro" in human
    assert 'default: "t2.micro"' not in human
    assert "t3.medium" in human
    assert "'\"t3.medium\"'" not in human


def test_explain_list_and_integer_examples_stay_strict_json():
    """CFG-CLI-005. Unions, lists, and integers keep JSON tokens."""
    packages = explain_config("os.packages")
    shown = packages.get("example") or packages["command"]
    assert shown == "spa config set os.packages '[\"acl\", \"polkit\"]'"
    disk = explain_config("terraform.aws.root_volume_size")
    shown = disk.get("example") or disk["command"]
    assert shown == "spa config set terraform.aws.root_volume_size 50"
    license_file = explain_config("splunk_defaults.splunk_license_file")
    assert license_file["type"] == "string | list[string]"
    shown = license_file.get("example") or license_file.get("command") or ""
    if "VALUE" not in shown:
        assert json.dumps("Splunk_Enterprise.lic") in shown or json.dumps(
            ["Splunk_Enterprise.lic"]
        ) in shown


def test_explain_does_not_borrow_another_feature_snippet():
    """CFG-CLI-007. Example comes from recommended or the selected feature, not the first catalog hit."""
    data = explain_config("terraform.aws.region")
    shown = data.get("example") or data.get("command") or ""
    assert "eu-central-1" not in shown
    assert shown == "spa config set terraform.aws.region VALUE"


def test_explain_children_carry_capped_allowed_and_default():
    """CFG-CLI-007. Immediate children publish small allowed sets inline and default."""
    data = explain_config("ccm")
    by_name = {item["name"]: item for item in data["fields"]}
    disk = by_name["disk_storage"]
    assert disk["allowed"] == [50, 100, 200, 250, 500, 1024, 2048]
    assert disk["default"] == 50
    hours = by_name["operation_hours"]
    assert hours["allowed"] == ["business_hours", "manual"]
    assert hours["default"] == "manual"
    purpose = by_name["business_purpose"]
    assert purpose["allowed"] == ["DeveloperInstance", "SalesOpportunity", "SupportCase"]
    assert purpose["default"] == "DeveloperInstance"
    human = format_explain(data)
    assert "<enum: 50|100|200|250|500|1024|2048>" in human
    hosts = explain_config("splunk_hosts")
    roles = next(item for item in hosts["fields"] if item["name"] == "roles")
    assert "allowed" not in roles
    assert roles["allowed_count"] > 8
    assert "<%s: %s values>" % (roles["type"], roles["allowed_count"]) in format_explain(hosts)


def test_search_hits_include_type_default_and_small_allowed_without_command():
    """CFG-CLI-006. Hits stay command-free; schema paths add type, default, and small allowed."""
    packages = search_config("os.packages")
    hit = next(item for item in packages["matches"] if item["path"] == "os.packages")
    assert hit["type"] == "list[string]"
    assert hit["default"] == []
    assert "command" not in hit
    assert "allowed" not in hit
    assert set(hit) <= _SEARCH_HIT_FIELDS
    disk = search_config("disk_storage")
    hit = next(item for item in disk["matches"] if item["path"] == "ccm.disk_storage")
    assert hit["type"] == "enum"
    assert hit["default"] == 50
    assert hit["allowed"] == [50, 100, 200, 250, 500, 1024, 2048]
    assert "command" not in hit
    roles = search_config("roles")
    hit = next(item for item in roles["matches"] if item["path"] == "splunk_hosts.roles")
    assert hit["type"].startswith("list")
    assert "allowed" not in hit
    assert "command" not in hit
    template = search_config("remote-provider")
    hit = next(item for item in template["matches"] if item["path"] == "template.remote-provider")
    assert set(hit) == {"path", "description"}
    assert "spa config" not in hit["description"]


def test_unknown_explain_path_names_config_search():
    """CFG-CLI-005 CFG-CLI-006. Recovery points at spa config search QUERY plus one example."""
    human = run_spa(["config", "explain", "not.a.path"])
    assert human.returncode == 1
    text = human.stderr
    assert "Unknown config path: not.a.path" in text
    assert "spa config search QUERY" in text
    assert "Example: spa config search instance_type" in text
    agent = run_spa(["--agent", "config", "explain", "not.a.path"])
    error = json.loads(agent.stdout)
    assert agent.returncode == 1
    assert error["ok"] is False
    assert "data" not in error
    assert error["error"] == (
        "Unknown config path: not.a.path. Find paths with: spa config search QUERY\n"
        "Example: spa config search instance_type"
    )
