"""Feature catalog quality and spa config explain/search."""

import json
import sys
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_root_explain_includes_topologies_and_os():
    result = run_spa(["config", "explain"])
    assert result.returncode == 0, result.stderr
    assert "topology.c1" in result.stdout
    assert "topology.s1" in result.stdout
    for extra in ("topology.two_envs", "topology.dual_cm", "topology.ds_hf", "topology.idx_shc"):
        assert extra not in result.stdout
    assert "provider.aws" in result.stdout
    assert "setting.os" not in result.stdout
    assert "\n  os " in result.stdout or "\n  os<" in result.stdout or "os <" in result.stdout


def test_os_guidance_says_what_the_block_provides():
    """The title alone cannot tell an operator what an os: block covers."""
    result = run_spa(["--json", "config", "explain", "os"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    guidance = data["when_to_use"].lower()
    for topic in ("packages", "hostname", "time", "selinux", "ssh", "splunk user"):
        assert topic in guidance, topic
    assert "after init" in guidance
    assert "ssh_username" in data["when_not_to_use"]
    assert "id" not in data


def test_implemented_settings_have_operator_guidance():
    """Records that write YAML must say what they do, not only a title."""
    from spa.catalog import load_features

    features = load_features(PROJECT_ROOT)
    apps = next(item for item in features if item.get("selector") == "splunk_app_deployment")
    blob = (apps.get("when_to_use") or "").lower()
    for topic in ("splunkbase", "local", "target_roles", "lookup"):
        assert topic in blob, topic
    assert "SPLUNKBASE" in (apps.get("snippet") or "")
    for item in features:
        label = item.get("selector") or item.get("id") or item.get("title")
        assert item.get("when_to_use") or item.get("when_not_to_use"), label
        if item.get("kind") == "setting" and item.get("selector"):
            assert len(item.get("when_to_use") or item.get("when_not_to_use") or "") >= 24, label


def test_feat_alias_is_removed():
    result = run_spa(["feat", "list"])
    assert result.returncode == 2
    assert "config explain" in result.stderr


def test_list_guidance_is_aligned_under_the_title():
    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa.catalog import format_feature_rows

    rows = [
        {"id": "topology.s1", "title": "S1 single node", "sva": "S1", "when_to_use": "Config-test."},
        {"selector": "splunk_apps", "title": "Save apps", "when_to_use": "Pull apps back."},
    ]
    lines = format_feature_rows(rows, width=100).splitlines()
    title_column = lines[0].index("S1 single node")
    assert title_column == len("topology.s1") + 2
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


def test_every_catalog_record_has_decision_guidance():
    from spa.catalog import list_payload

    features = list_payload(PROJECT_ROOT)["features"]
    assert features
    for feature in features:
        label = feature.get("selector") or feature.get("id") or feature.get("title")
        assert feature.get("title"), label
        assert feature.get("when_to_use") or feature.get("when_not_to_use"), label
        assert "snippet" not in feature
        assert "keys" not in feature


def test_config_search_ssl():
    result = run_spa(["config", "search", "ssl"])
    assert result.returncode == 0, result.stderr
    assert "splunk_defaults.splunk_ssl" in result.stdout
    assert "setting.ssl" not in result.stdout


def test_config_search_os():
    result = run_spa(["config", "search", "os"])
    assert result.returncode == 0, result.stderr
    assert "os " in result.stdout or result.stdout.startswith("os ")
    assert "setting.os" not in result.stdout


def test_explain_c1():
    result = run_spa(["config", "explain", "topology.c1"])
    assert result.returncode == 0, result.stderr
    assert "C1" in result.stdout
    assert "cm_2idxc_sh_uf" in result.stdout
    assert "keys:" not in result.stdout


def test_explain_host_roles_includes_schema_metadata():
    result = run_spa(["config", "explain", "splunk_hosts.roles"])
    assert result.returncode == 0, result.stderr
    assert "list[enum]" in result.stdout
    assert "cluster_manager" in result.stdout
    assert "[]" not in result.stdout


def test_explain_aws_keeps_catalog_guidance_off_child_lines():
    result = run_spa(["config", "explain", "terraform.aws"])
    assert result.returncode == 0, result.stderr
    assert "ssh_username" in result.stdout
    assert "root_volume_type" in result.stdout
    assert "allowed=gp3|gp2" not in result.stdout
    username = run_spa(["config", "explain", "terraform.aws.ssh_username"])
    assert username.returncode == 0, username.stderr
    assert "Login user must match the AMI" in username.stdout or "AMI" in username.stdout


def test_config_keys_schema_owns_former_orphans():
    result = run_spa(["--json", "config", "keys"])
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


def test_explain_rejects_a_recursive_keys_flag():
    result = run_spa(["config", "explain", "os", "--keys"])
    assert result.returncode == 2
    assert "longer path" in result.stderr
    assert not result.stdout.strip().startswith("{")


def test_config_json_after_subcommand():
    trailing = run_spa(["config", "explain", "os", "--json"])
    leading = run_spa(["--json", "config", "explain", "os"])
    assert trailing.returncode == 0, trailing.stderr
    assert leading.returncode == 0, leading.stderr
    assert json.loads(trailing.stdout) == json.loads(leading.stdout)
    assert json.loads(trailing.stdout)["data"]["path"] == "os"


def test_explain_keys_misuse_is_enveloped_in_agent_mode():
    result = run_spa(["--json", "config", "explain", "--keys"])
    assert result.returncode == 2
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "data" not in payload
    assert "longer path" in payload["error"]


def test_config_keys_cover_schema():
    result = run_spa(["config", "keys"])
    assert result.returncode == 0, result.stderr
    assert "missing:" not in result.stdout
    assert "missing detail:" not in result.stdout


def test_config_json_search():
    result = run_spa(["--json", "config", "search", "architecture"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    rows = payload["data"]["matches"]
    paths = [item["path"] for item in rows]
    assert "splunk_defaults.splunk_architecture" in paths
    assert set(rows[0]) == {"path", "description"}


def test_config_schema_payload_lists_each_schema_path_once():
    from spa.catalog import config_schema_payload, schema_key_details

    payload = config_schema_payload(PROJECT_ROOT)
    paths = [key["path"] for area in payload["areas"] for key in area["keys"]]
    assert paths.count("splunk_defaults.splunk_version") == 1
    assert paths.count("terraform.aws.ssh_username") == 1
    assert len(paths) == len(set(paths))
    assert set(paths) == set(schema_key_details())
    titles = [area["title"] for area in payload["areas"]]
    assert titles[:8] == [
        "Identity",
        "General",
        "OS",
        "Provider",
        "Clustering",
        "Defaults",
        "Hosts",
        "Apps",
    ]
    provider = next(area["keys"] for area in payload["areas"] if area["title"] == "Provider")
    provider_paths = [key["path"] for key in provider]

    def _first(prefix: str) -> int:
        return next(
            index
            for index, path in enumerate(provider_paths)
            if path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[]")
        )

    assert _first("terraform") < _first("virtualbox") < _first("aws")


def test_config_schema_omits_secret_defaults_and_keeps_env_lookups():
    from spa.catalog import config_schema_payload

    payload = config_schema_payload(PROJECT_ROOT)
    by_path = {key["path"]: key for area in payload["areas"] for key in area["keys"]}
    snippets = "\n".join(
        item.get("yaml") or ""
        for area in payload["areas"]
        for item in area.get("snippets") or []
    )
    for path in (
        "splunk_defaults.splunk_admin_password",
        "splunk_app_deployment.splunkbase_password",
    ):
        assert "default" not in by_path[path]
    assert "lookup('env'" in snippets
    assert "SPLUNK_ADMIN_PASSWORD" in snippets
    assert "SPLUNKBASE_PASSWORD" in snippets


def test_config_markdown_header_groups_defaults_and_hides_secrets():
    import re

    from spa.catalog import format_config_markdown

    text = format_config_markdown(PROJECT_ROOT)
    assert text.startswith(
        "<!-- Generated by spa config schema --markdown. Do not edit by hand. -->\n"
    )
    assert "\n## Defaults\n" in text
    assert "-----BEGIN" not in text
    literal = re.compile(
        r"(?im)^[ \t-]*[\w.]*password\w*\s*:\s*(?!.*(?:lookup\(|vault)).+$"
    )
    assert literal.findall(text) == []


def test_config_schema_markdown_is_human_dump():
    result = run_spa(["--no-agent", "config", "schema", "--markdown"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(
        "<!-- Generated by spa config schema --markdown. Do not edit by hand. -->"
    )
    assert not result.stdout.lstrip().startswith("{")


def test_config_schema_markdown_is_not_an_agent_payload():
    result = run_spa(["--json", "config", "schema", "--markdown"])
    assert result.returncode == 2
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "config explain" in payload["error"]


def test_removed_features_command_points_at_explain():
    human = run_spa(["features"])
    assert human.returncode == 2
    assert "spa features was removed." in human.stderr
    assert "spa config explain" in human.stderr
    assert not human.stdout.strip()
    agent = run_spa(["--json", "feat"])
    assert agent.returncode == 2
    assert not agent.stderr
    payload = json.loads(agent.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "spa config explain" in payload["error"]


def test_config_schema_rejects_a_path():
    result = run_spa(["config", "schema", "splunk_defaults.splunk_admin_password"])
    assert result.returncode == 2
    assert "spa config schema does not take a path." in result.stderr
    assert "spa config explain PATH" in result.stderr
    assert "spa config schema --markdown" in result.stderr
    assert not result.stdout.strip()
    agent = run_spa(["--json", "config", "schema"])
    assert agent.returncode == 2
    payload = json.loads(agent.stdout)
    assert "data" not in payload
    assert "config explain" in payload["error"]


def test_config_keys_rejects_an_extra_argument():
    result = run_spa(["config", "keys", "extra"])
    assert result.returncode == 2
    assert "spa config keys does not take an argument." in result.stderr


def test_config_action_help_lists_only_that_actions_arguments():
    explain = run_spa(["config", "explain", "--help"])
    assert explain.returncode == 0, explain.stderr
    assert "PATH" in explain.stdout
    assert "--keys" not in explain.stdout
    assert "--command" not in explain.stdout
    assert "--markdown" not in explain.stdout
    schema = run_spa(["config", "schema", "--help"])
    assert schema.returncode == 0, schema.stderr
    assert "--markdown" in schema.stdout
    assert "rejected_path" not in schema.stdout


def test_markdown_requires_schema_action():
    result = run_spa(["config", "explain", "--markdown"])
    assert result.returncode == 2
    assert "spa config schema --markdown" in result.stderr
    assert not result.stdout.strip().startswith("{")


def test_explain_shows_one_level_of_indexer_volumes():
    result = run_spa(["--json", "config", "explain", "splunk_defaults.splunk_indexer_volumes"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    names = [item["name"] for item in data.get("fields") or []]
    assert names
    assert "path" not in names
    assert "id" not in data
    assert "apply" not in data
    child = run_spa(["--json", "config", "explain", "splunk_defaults.splunk_indexer_volumes.<volume>"])
    assert child.returncode == 0, child.stderr
    child_names = [item["name"] for item in json.loads(child.stdout)["data"].get("fields") or []]
    assert "path" in child_names


def test_schema_selectors_reject_old_ids_and_keep_snippets_examples_only():
    import re

    from spa.catalog import (
        config_schema_payload,
        format_config_markdown,
        load_features,
        path_is_schema_backed,
        record_paths,
        schema_key_details,
    )

    features = load_features(PROJECT_ROOT)
    schema = schema_key_details()
    selectors = []
    for item in features:
        assert item.get("when_to_use") or item.get("when_not_to_use"), item["id"]
        if item.get("kind") == "setting" and record_paths(item):
            selector = item["selector"]
            assert selector in record_paths(item)
            assert path_is_schema_backed(selector, schema)
            selectors.append(selector)
        else:
            assert "selector" not in item
    assert len(selectors) == len(set(selectors))

    listed = run_spa(["--json", "config", "explain"])
    assert listed.returncode == 0, listed.stderr
    assert "setting." not in listed.stdout

    rejected = run_spa(["config", "explain", "setting.ssl"])
    assert rejected.returncode != 0
    assert "Unknown config path" in rejected.stderr

    tls = json.loads(run_spa(["--json", "config", "search", "tls"]).stdout)
    assert tls["data"]["matches"][0]["path"] == "splunk_defaults.splunk_ssl"

    exact = json.loads(
        run_spa(["--json", "config", "search", "splunk_defaults.splunk_ssl"]).stdout
    )
    assert exact["data"]["matches"][0]["path"] == "splunk_defaults.splunk_ssl"

    roles = json.loads(run_spa(["--json", "config", "search", "roles"]).stdout)
    assert any(row["path"] == "splunk_hosts.roles" for row in roles["data"]["matches"])

    empty = json.loads(run_spa(["--json", "config", "search", "zzznosupport"]).stdout)
    assert empty["data"]["matches"] == []

    gone = run_spa(["config", "explain", "LDAP authentication"])
    assert gone.returncode != 0
    assert "Unknown config path" in gone.stderr
    root = run_spa(["config", "explain"])
    assert "not a splunk_config.yml setting" not in root.stdout
    assert "GCP provider" not in root.stdout
    assert "Apps management CLI" not in root.stdout

    layout = json.loads(run_spa(["--json", "config", "explain", "provider.aws"]).stdout)
    assert layout["data"]["path"] == "provider.aws"
    assert layout["data"].get("suggest")
    assert "apply" not in layout["data"]

    shown = json.loads(run_spa(["--json", "config", "explain", "os"]).stdout)
    feature = shown["data"]
    assert "apply" not in feature
    assert feature["fields"]
    blob = json.dumps(feature)
    assert "-----BEGIN" not in blob

    text = format_config_markdown(PROJECT_ROOT)
    assert re.search(r"\b(setting|topology|provider)\.[A-Za-z0-9_.]+", text) is None
    assert "LDAP authentication" not in text
    assert "## Other" not in text
    payload = config_schema_payload(PROJECT_ROOT)
    for area in payload["areas"]:
        for key in area["keys"]:
            assert len(key["description"]) >= 12
            assert key["path"].lower() != key["description"].lower()
        for snippet in area["snippets"]:
            assert snippet["selector"]
            assert "id" not in snippet


def _is_schema_container(path, schema):
    return any(
        other.startswith(path + ".") or other.startswith(path + "[].")
        for other in schema
        if other != path
    )


def _host_override_of(path):
    host = "splunk_hosts[]."
    if not path.startswith(host):
        return None
    rest = path[len(host):]
    for root in ("os", "virtualbox", "terraform"):
        if rest == root or rest.startswith(root + "."):
            return rest
    return None


def test_key_descriptions_state_behavior_and_omit_defaults():
    """Each schema key describes itself. Containers do not narrate their children."""
    import re

    import yaml

    from spa.catalog import load_features, public_key_description, schema_key_details

    schema = schema_key_details()
    features = load_features(PROJECT_ROOT)
    texts = {}
    seen = {}
    for path, detail in schema.items():
        raw = str(detail.get("description") or "").strip()
        assert raw, path
        text = public_key_description(path, detail, features, schema)
        texts[path] = text
        assert "-----BEGIN" not in text
        assert re.search(r"\b(setting|topology|provider)\.[A-Za-z0-9_.]+", text) is None
        if _is_schema_container(path, schema):
            assert "\n" not in text
            assert "Default " not in text
            assert "No default" not in text
            assert "Required." not in text
            kids = set()
            for other in schema:
                if not (
                    other.startswith(path + ".") or other.startswith(path + "[].")
                ):
                    continue
                rest = other[len(path):]
                if rest.startswith("[]."):
                    rest = rest[3:]
                elif rest.startswith("."):
                    rest = rest[1:]
                leaf = rest.split(".", 1)[0].replace("[]", "")
                if leaf.startswith("<") and leaf.endswith(">"):
                    continue
                kids.add(leaf)
            for kid in kids:
                assert re.search(r"\b%s\b" % re.escape(kid), text) is None, (path, kid)
            continue
        if detail.get("required"):
            assert "Required." in text, path
        elif detail.get("default") is not None:
            assert "Omit the key to keep that" not in text, path
        else:
            assert "Default " in text or "No default" in text, path
        assert text not in seen, (path, seen.get(text))
        seen[text] = path

    for path, text in texts.items():
        other = _host_override_of(path)
        if other is None:
            continue
        prefix = "Per-host override of `%s`: " % other
        assert text.startswith(prefix), path
        body = text[len(prefix):]
        raw = str(schema[path]["description"])
        behavior = re.split(r"\s+Default ", raw, maxsplit=1)[0]
        assert behavior in body or body.startswith(behavior)

    prefix_text = texts["splunk_hosts[].iter.prefix"]
    assert "before" in prefix_text
    assert "nothing" in prefix_text
    cron = texts["os.enable_time_sync_cron"]
    assert "Default false" not in cron
    assert "VirtualBox" in cron
    assert texts["splunk_hosts[].os.time_zone"].startswith(
        "Per-host override of `os.time_zone`"
    )

    defaults = yaml.safe_load(
        (PROJECT_ROOT / "defaults" / "splunk_defaults.yml").read_text(encoding="utf-8")
    )
    admin = (defaults.get("splunk_defaults") or {}).get("splunk_admin_password")
    blob = "\n".join(texts.values())
    if isinstance(admin, str) and "lookup" not in admin and len(admin) > 3:
        assert admin not in blob

    shown = json.loads(run_spa(["--json", "config", "explain", "os"]).stdout)
    by_name = {row["name"]: row for row in shown["data"]["fields"]}
    assert "Default false" not in by_name["enable_time_sync_cron"]["description"]
    host_packages = json.loads(
        run_spa(["--json", "config", "explain", "splunk_hosts.os.packages"]).stdout
    )
    assert "Java 21" in host_packages["data"]["description"]
    assert "Java 21" not in by_name["packages"]["description"]


def test_explain_accepts_a_path_without_brackets():
    human = run_spa(["config", "explain", "splunk_app_deployment.apps.premium_app"])
    assert human.returncode == 0, human.stderr
    assert human.stdout.splitlines()[0] == "PATH: splunk_app_deployment.apps.premium_app"
    payload = json.loads(
        run_spa(["--json", "config", "explain", "splunk_app_deployment.apps.premium_app"]).stdout
    )
    assert payload["data"]["path"] == "splunk_app_deployment.apps.premium_app"
    keys = run_spa(["config", "explain", "splunk_hosts.name"])
    assert keys.returncode == 0, keys.stderr
    assert keys.stdout.startswith("PATH: splunk_hosts.name")
    found = json.loads(
        run_spa(["--json", "config", "search", "splunk_app_deployment.apps.premium_app"]).stdout
    )
    assert found["data"]["matches"][0]["path"] == "splunk_app_deployment.apps.premium_app"


def test_folded_selectors_stay_unique():
    from spa.catalog import load_features, resolve_feature

    features = load_features(PROJECT_ROOT)
    folded = {}
    for item in features:
        selector = item.get("selector")
        if not selector:
            continue
        key = selector.replace("[]", "")
        assert key not in folded, (key, folded.get(key), selector)
        folded[key] = selector
    ambiguous = [
        {"selector": "a[].b", "kind": "setting", "title": "A", "when_to_use": "One host name."},
        {"selector": "a.b[]", "kind": "setting", "title": "B", "when_to_use": "Another host name."},
    ]
    assert resolve_feature(ambiguous, "a.b") is None
    assert resolve_feature(ambiguous, "a[].b")["title"] == "A"


def test_omit_default_is_a_payload_field():
    """The shipped omit value is a default field, not only a sentence."""
    from spa.catalog import config_schema_payload

    payload = config_schema_payload(PROJECT_ROOT)
    by_path = {key["path"]: key for area in payload["areas"] for key in area["keys"]}
    assert by_path["splunk_defaults.splunk_env_name"]["default"] == "splk"
    assert "Default splk" not in by_path["splunk_defaults.splunk_env_name"]["description"]
    assert by_path["os.enable_time_sync_cron"]["default"] is False
    assert by_path["splunk_hosts[].os.enable_time_sync_cron"]["default"] is False
    assert by_path["os.packages"]["default"] == []
    assert by_path["virtualbox.memory"]["default"] == 512
    assert "default" not in by_path["splunk_hosts[].iter.prefix"]
    assert "default" not in by_path["splunk_defaults.splunk_admin_password"]
    assert "default" not in by_path["terraform.aws.ssh_private_key_file"]

    shown = json.loads(
        run_spa(["--json", "config", "explain", "splunk_defaults.splunk_env_name"]).stdout
    )
    assert shown["data"]["default"] == "splk"
    human = run_spa(["config", "explain", "splunk_defaults.splunk_env_name"])
    assert human.returncode == 0, human.stderr
    assert 'default: "splk"' in human.stdout


def test_ansible_defaults_do_not_ship_admin_or_cluster_passwords():
    """Admin and cluster passwords come from splunk_config.yml, not defaults/*.yml."""
    files = {
        "splunk_defaults.yml": "splunk_admin_password",
        "splunk_idxclusters.yml": "idxc_password",
        "splunk_shclusters.yml": "shc_password",
    }
    for name, key in files.items():
        text = (PROJECT_ROOT / "defaults" / name).read_text(encoding="utf-8")
        assert "must be set in splunk_config.yml" in text
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith("%s:" % key), name


def test_explain_command_is_read_only_and_one_per_feature():
    """CFG-ADD-005."""
    from spa.catalog import feature_class, feature_command, load_features, public_feature

    shown = run_spa(["--json", "config", "explain", "splunk_hosts"])
    assert shown.returncode == 0, shown.stderr
    feature = json.loads(shown.stdout)["data"]
    assert "spa config add 'splunk_hosts[name=NAME]' JSON_OBJECT" in feature["command"]
    assert "apply" not in feature
    human = run_spa(["config", "explain", "splunk_hosts"])
    assert human.returncode == 0, human.stderr
    assert "spa config add 'splunk_hosts[name=idx1]'" in human.stdout
    refused = run_spa(["--json", "config", "explain", "--command"])
    assert refused.returncode == 2
    assert "longer path" in json.loads(refused.stdout)["error"]

    features = load_features(PROJECT_ROOT)
    supported = {"set", "add", "topology", "provider", "apps add"}
    commands = []
    for item in features:
        command = feature_command(item)
        public = public_feature(item, features)
        if feature_class(item) == "unsupported":
            assert command is None
            assert public["configurable"] is False
            continue
        assert command is not None
        assert set(command) == {"action", "path", "command"}
        assert command["action"] in supported
        assert command["command"].startswith("spa ")
        assert "\n" not in command["command"]
        commands.append(command)
    by_path = {item.get("selector") or item.get("id"): feature_command(item) for item in features}
    assert by_path["splunk_idxclusters[].idxc_name"]["action"] == "add"
    assert by_path["splunk_shclusters[].shc_name"]["action"] == "add"
    assert by_path["splunk_hosts[].splunk_outputs"]["action"] == "set"
    assert by_path["splunk_hosts[].splunk_outputs"]["command"].startswith("spa config set ")
    assert by_path["splunk_defaults.splunk_admin_password"]["command"].endswith("--from-env NAME")
    assert by_path["splunk_app_deployment.apps[].app_id"]["action"] == "apps add"
    assert by_path["splunk_app_deployment.apps[].content_pack_apps"]["command"].startswith(
        "spa apps add "
    )
    assert by_path["os"]["command"] == "spa config set os VALUE"
    assert by_path["topology.c1"]["command"] == "spa config topology topology.c1"
    assert by_path["provider.aws"]["command"] == "spa config provider provider.aws"
    assert feature_command({"id": "note.example", "kind": "note", "title": "Not configurable"}) is None
    assert commands
