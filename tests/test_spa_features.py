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
    assert "topology.s1" in result.stdout
    for extra in ("topology.two_envs", "topology.dual_cm", "topology.ds_hf", "topology.idx_shc"):
        assert extra not in result.stdout
    assert "provider.aws" in result.stdout
    assert "setting.os" not in result.stdout
    assert "\nos  " in "\n" + result.stdout


def test_os_guidance_says_what_the_block_provides():
    """The title alone cannot tell an operator what an os: block covers."""
    result = run_spa(["--json", "features", "list"])
    assert result.returncode == 0, result.stderr
    features = {
        item.get("selector") or item.get("id") or item.get("title"): item
        for item in json.loads(result.stdout)["data"]["features"]
    }
    guidance = features["os"]["when_to_use"].lower()
    for topic in ("packages", "hostname", "time", "selinux", "ssh", "splunk user"):
        assert topic in guidance, topic
    assert "after init" in guidance
    assert "ssh_username" in features["os"]["when_not_to_use"]
    assert "id" not in features["os"]


def test_implemented_settings_have_operator_guidance():
    """Records that write YAML must say what they do, not only a title."""
    result = run_spa(["--json", "features", "list"])
    assert result.returncode == 0, result.stderr
    show = run_spa(["--json", "features", "show", "splunk_app_deployment"])
    assert show.returncode == 0, show.stderr
    apps = json.loads(show.stdout)["data"]["feature"]
    blob = (apps.get("when_to_use") or "").lower()
    for topic in ("splunkbase", "local", "target_roles", "lookup"):
        assert topic in blob, topic
    assert "SPLUNKBASE" in (apps.get("snippet") or "")
    for item in json.loads(result.stdout)["data"]["features"]:
        label = item.get("selector") or item.get("id") or item.get("title")
        assert item.get("when_to_use") or item.get("when_not_to_use"), label
        if item.get("kind") == "setting" and item.get("selector"):
            assert len(item.get("when_to_use") or item.get("when_not_to_use") or "") >= 24, label


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


def test_every_list_record_has_decision_guidance():
    result = run_spa(["--json", "features", "list"])
    assert result.returncode == 0, result.stderr
    features = json.loads(result.stdout)["data"]["features"]
    assert features
    for feature in features:
        label = feature.get("selector") or feature.get("id") or feature.get("title")
        assert feature.get("title"), label
        assert feature.get("when_to_use") or feature.get("when_not_to_use"), label
        assert "snippet" not in feature
        assert "keys" not in feature


def test_features_search_ssl():
    result = run_spa(["features", "search", "ssl"])
    assert result.returncode == 0, result.stderr
    assert "splunk_defaults.splunk_ssl" in result.stdout
    assert "setting.ssl" not in result.stdout


def test_features_search_os():
    result = run_spa(["features", "search", "os"])
    assert result.returncode == 0, result.stderr
    assert "\nos  " in "\n" + result.stdout
    assert "setting.os" not in result.stdout


def test_features_show_c1():
    result = run_spa(["features", "show", "topology.c1"])
    assert result.returncode == 0, result.stderr
    assert "C1" in result.stdout
    assert "cm_2idxc_sh_uf" in result.stdout
    assert "keys:" not in result.stdout


def test_features_show_keys_includes_schema_metadata_and_placeholders():
    result = run_spa(["features", "show", "splunk_hosts[].name", "--keys"])
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
    rows = json.loads(trailing.stdout)["data"]["features"]
    ids = [item["id"] for item in rows if item.get("id")]
    assert "topology.c1" in ids
    assert all(not str(item.get("selector", "")).startswith("setting.") for item in rows)
    assert all(not str(item.get("id", "")).startswith("setting.") for item in rows)


def test_features_keys_misuse_is_enveloped_in_agent_mode():
    result = run_spa(["--json", "features", "list", "--keys"])
    assert result.returncode == 2
    assert not result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "show SELECTOR --keys" in payload["error"]


def test_features_keys_cover_schema():
    result = run_spa(["features", "keys"])
    assert result.returncode == 0, result.stderr
    assert "missing:" not in result.stdout
    assert "missing detail:" not in result.stdout


def test_features_json_search():
    result = run_spa(["--json", "features", "search", "architecture"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    rows = payload["data"]["features"]
    selectors = [item.get("selector") for item in rows]
    assert "splunk_defaults.splunk_architecture" in selectors
    assert rows[0]["match_reason"]
    assert "matched_keys" in rows[0]
    assert "snippet" not in payload["data"]["features"][0]
    assert "keys" not in payload["data"]["features"][0]


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
        "Defaults",
        "Hosts",
        "Apps",
        "Clustering",
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
        "<!-- Generated by spa features schema --markdown. Do not edit by hand. -->\n"
    )
    assert "\n## Defaults\n" in text
    assert "-----BEGIN" not in text
    literal = re.compile(
        r"(?im)^[ \t-]*[\w.]*password\w*\s*:\s*(?!.*(?:lookup\(|vault)).+$"
    )
    assert literal.findall(text) == []


def test_features_schema_markdown_is_human_dump():
    result = run_spa(["--no-agent", "features", "schema", "--markdown"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(
        "<!-- Generated by spa features schema --markdown. Do not edit by hand. -->"
    )
    assert not result.stdout.lstrip().startswith("{")


def test_features_schema_markdown_stays_json_in_agent_mode():
    result = run_spa(["--json", "features", "schema", "--markdown"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["areas"]
    assert "<!-- Generated by spa features schema --markdown" not in result.stdout


def test_features_markdown_requires_schema_action():
    result = run_spa(["features", "list", "--markdown"])
    assert result.returncode == 2
    assert "spa features schema --markdown" in result.stderr
    assert not result.stdout.strip().startswith("{")


def test_features_json_show_only_adds_details_with_keys_flag():
    compact = run_spa(["--json", "features", "show", "splunk_defaults.splunk_indexer_volumes"])
    detailed = run_spa(
        ["--json", "features", "show", "splunk_defaults.splunk_indexer_volumes", "--keys"]
    )
    assert compact.returncode == 0, compact.stderr
    assert detailed.returncode == 0, detailed.stderr
    compact_feature = json.loads(compact.stdout)["data"]["feature"]
    detailed_feature = json.loads(detailed.stdout)["data"]["feature"]
    assert "keys" not in compact_feature
    assert "key_details" not in compact_feature
    paths = {item["path"] for item in detailed_feature["key_details"]}
    assert "splunk_defaults.splunk_indexer_volumes.<volume>.path" in paths
    assert "id" not in detailed_feature
    assert detailed_feature["apply"]["merge"] in {"deep", "replace"}
    assert "splunk_defaults.splunk_indexer_volumes" in detailed_feature["apply"]["paths"]


def test_schema_selectors_reject_old_ids_and_expose_apply():
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

    listed = run_spa(["--json", "features", "list"])
    assert listed.returncode == 0, listed.stderr
    assert "setting." not in listed.stdout
    for row in json.loads(listed.stdout)["data"]["features"]:
        if row.get("configurable") and row.get("kind") == "setting":
            assert row["selector"]
            assert "id" not in row

    rejected = run_spa(["features", "show", "setting.ssl"])
    assert rejected.returncode != 0
    assert "Unknown feature" in rejected.stderr

    tls = json.loads(run_spa(["--json", "features", "search", "tls"]).stdout)
    assert tls["data"]["features"][0]["selector"] == "splunk_defaults.splunk_ssl"
    assert tls["data"]["features"][0]["match_reason"] == "search term"
    assert "matched_keys" in tls["data"]["features"][0]

    exact = json.loads(
        run_spa(["--json", "features", "search", "splunk_defaults.splunk_ssl"]).stdout
    )
    assert exact["data"]["features"][0]["selector"] == "splunk_defaults.splunk_ssl"
    assert exact["data"]["features"][0]["match_reason"] in {"selector", "schema path"}

    roles = json.loads(run_spa(["--json", "features", "search", "cluster_manager"]).stdout)
    assert any(
        "splunk_hosts[].roles" in row.get("matched_keys", [])
        for row in roles["data"]["features"]
    )

    empty = json.loads(run_spa(["--json", "features", "search", "zzznosupport"]).stdout)
    assert empty["data"]["features"] == []

    gone = run_spa(["features", "show", "LDAP authentication"])
    assert gone.returncode != 0
    assert "Unknown feature" in gone.stderr
    listed = run_spa(["features", "list"])
    assert "not a splunk_config.yml setting" not in listed.stdout
    assert "GCP provider" not in listed.stdout
    assert "Apps management CLI" not in listed.stdout

    layout = json.loads(
        run_spa(["--json", "features", "show", "provider.aws", "--keys"]).stdout
    )
    assert layout["data"]["feature"]["id"] == "provider.aws"
    assert layout["data"]["feature"].get("suggest")
    assert "apply" not in layout["data"]["feature"]

    shown = json.loads(
        run_spa(["--json", "features", "show", "os", "--keys"]).stdout
    )
    apply = shown["data"]["feature"]["apply"]
    assert apply["merge"] in {"deep", "replace"}
    assert "os" in apply["paths"]
    assert "-----BEGIN" not in apply["snippet"]
    assert "lookup('env'" in apply["snippet"] or "password:" not in apply["snippet"].lower()

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

    shown = json.loads(run_spa(["--json", "features", "show", "os", "--keys"]).stdout)
    by_path = {row["path"]: row for row in shown["data"]["feature"]["key_details"]}
    assert by_path["os.enable_time_sync_cron"]["description"] == cron
    assert "note" not in by_path["os.enable_time_sync_cron"]
    assert by_path["splunk_hosts[].os.time_zone"]["description"] == texts[
        "splunk_hosts[].os.time_zone"
    ]
    assert "Java 21" in by_path["splunk_hosts[].os.packages"]["description"]
    assert "Java 21" not in by_path["os.packages"]["description"]


def test_show_accepts_selector_without_brackets():
    human = run_spa(["features", "show", "splunk_app_deployment.apps.premium_app"])
    assert human.returncode == 0, human.stderr
    assert "'splunk_app_deployment.apps[].premium_app'" in human.stdout
    payload = json.loads(
        run_spa(
            ["--json", "features", "show", "splunk_app_deployment.apps.premium_app"]
        ).stdout
    )
    assert payload["data"]["feature"]["selector"] == "splunk_app_deployment.apps[].premium_app"
    keys = run_spa(["features", "show", "splunk_hosts.name", "--keys"])
    assert keys.returncode == 0, keys.stderr
    assert "'splunk_hosts[].name'" in keys.stdout
    detailed = json.loads(
        run_spa(["--json", "features", "show", "splunk_hosts.name", "--keys"]).stdout
    )
    paths = {row["path"] for row in detailed["data"]["feature"]["key_details"]}
    assert "splunk_hosts[].name" in paths
    listed = run_spa(["features", "list"])
    assert "'splunk_hosts[].name'" in listed.stdout
    found = json.loads(
        run_spa(
            ["--json", "features", "search", "splunk_app_deployment.apps.premium_app"]
        ).stdout
    )
    assert found["data"]["features"][0]["selector"] == "splunk_app_deployment.apps[].premium_app"
    assert found["data"]["features"][0]["match_reason"] == "selector"


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
        run_spa(
            ["--json", "features", "show", "splunk_defaults.splunk_env_name", "--keys"]
        ).stdout
    )
    details = {row["path"]: row for row in shown["data"]["feature"]["key_details"]}
    assert details["splunk_defaults.splunk_env_name"]["default"] == "splk"
    human = run_spa(["features", "show", "splunk_defaults.splunk_env_name", "--keys"])
    assert human.returncode == 0, human.stderr
    assert "default='splk'" in human.stdout
