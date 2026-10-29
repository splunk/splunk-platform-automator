"""Tests for spa architecture plan (architecture JSON -> config fragment, read-only).

The input is the architecture file that build_architecture.py writes (schema 0.3.0,
see spa-create-config/references/architecture-input.md).
"""

import copy
import json
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]

LICENSE_VALUE = "Splunk_Enterprise.lic"
GENERATOR_SAMPLE = Path(__file__).resolve().parent / "fixtures" / "architecture_m4_generator.json"


def m4_doc():
    """Architecture file shaped like build_architecture.py output for M4."""
    return {
        "metadata": {
            "source_skill": "splunk-validated-architectures",
            "version": "0.3.0",
            "sva_code": "M4",
        },
        "environment": {"name": "test-m4-lab"},
        "phase_1": {
            "topology": "topology.m4",
            "sva": "M4",
            "sites": ["site1", "site2"],
            "confirmed": True,
        },
        "phase_5": {
            "org_prefix": "test",
            "total_host_count": 13,
            "indexer_cluster": {
                "name": "idxc1",
                "sites": ["site1", "site2"],
                "site_rf": "origin:2, total:3",
                "site_sf": "origin:1, total:2",
                "peers": 4,
                "peers_by_site": {"site1": 2, "site2": 2},
                "replication_port": 9887,
            },
            "shcluster": {
                "name": "shc1",
                "members": 3,
                "members_by_site": {"site1": 2, "site2": 1},
                "shc_site": "site0",
                "replication_port": 9887,
            },
            "optional_roles": [
                {"name": "lm", "role": "license_manager"},
                {"name": "ds", "role": "deployment_server"},
                {"name": "mc", "role": "monitoring_console"},
                {"name": "uf", "role": "universal_forwarder"},
            ],
            "env_lookups": {
                "admin": "SPLUNK_ADMIN_PASSWORD",
                "idxc": "SPLUNK_IDXC_PASSWORD",
                "shc": "SPLUNK_SHC_PASSWORD",
            },
            "_extensions": [],
            "confirmed": True,
        },
        "phase_5b": {
            "roles": [
                "cluster_manager",
                "indexer",
                "search_head",
                "deployer",
                "license_manager",
                "deployment_server",
                "monitoring_console",
                "universal_forwarder",
            ],
            "confirmed": True,
        },
        "phase_6b": {"license_file": LICENSE_VALUE, "confirmed": False},
    }


def plan_for(doc, env=None):
    from spa.architecture import plan_architecture

    return plan_architecture(doc, env=env or {}, spa_home=PROJECT_ROOT)


def host_by_name(hosts, name):
    for entry in hosts:
        if entry.get("name") == name:
            return entry
    raise AssertionError("no host entry for %s" % name)


def hosts_with_role(hosts, role):
    return sorted(entry["name"] for entry in hosts if role in entry.get("roles", []))


# --- Phase 1 and 5: JSON input, host builder ------------------------------------


def test_m4_plan_is_ok_and_reports_phases():
    plan = plan_for(m4_doc())
    assert plan["ok"] is True, plan["errors"]
    phase_names = [row["phase"] for row in plan["phases"]]
    assert "phase_1" in phase_names and "phase_5" in phase_names


def test_host_counts_match_phase_5_selection():
    plan = plan_for(m4_doc())
    assert hosts_with_role(plan["hosts"], "cluster_manager") == ["cm"]
    assert hosts_with_role(plan["hosts"], "indexer") == ["idx1", "idx2", "idx3", "idx4"]
    assert hosts_with_role(plan["hosts"], "search_head") == ["sh1", "sh2", "sh3"]


def test_indexer_site_assignment_follows_peers_by_site():
    plan = plan_for(m4_doc())
    assert host_by_name(plan["hosts"], "idx1")["site"] == "site1"
    assert host_by_name(plan["hosts"], "idx2")["site"] == "site1"
    assert host_by_name(plan["hosts"], "idx3")["site"] == "site2"
    assert host_by_name(plan["hosts"], "idx4")["site"] == "site2"


def test_search_head_site_assignment_follows_members_by_site():
    plan = plan_for(m4_doc())
    assert host_by_name(plan["hosts"], "sh1")["site"] == "site1"
    assert host_by_name(plan["hosts"], "sh2")["site"] == "site1"
    assert host_by_name(plan["hosts"], "sh3")["site"] == "site2"


def test_cluster_manager_and_deployer_are_built_from_phase_5():
    plan = plan_for(m4_doc())
    assert host_by_name(plan["hosts"], "cm")["roles"] == ["cluster_manager"]
    assert "deployer" in host_by_name(plan["hosts"], "ds")["roles"]


def test_missing_phase_5_is_an_error():
    doc = m4_doc()
    doc.pop("phase_5")
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_5 is missing" in error for error in plan["errors"])


def test_missing_topology_is_an_error():
    doc = m4_doc()
    doc["phase_1"].pop("topology")
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_1.topology" in error for error in plan["errors"])


def test_unknown_topology_id_is_an_error():
    doc = m4_doc()
    doc["phase_1"]["topology"] = "topology.nope"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_1.topology" in error for error in plan["errors"])
    assert "topology.nope" not in json.dumps(plan)


# --- Phase 3: optional roles ------------------------------------------------------


def test_optional_roles_add_lm_mc_and_uf_hosts():
    plan = plan_for(m4_doc())
    assert host_by_name(plan["hosts"], "lm")["roles"] == ["license_manager"]
    assert host_by_name(plan["hosts"], "mc")["roles"] == ["monitoring_console"]
    assert host_by_name(plan["hosts"], "uf")["roles"] == ["universal_forwarder"]


def test_optional_deployment_server_named_ds_merges_into_the_deployer_host():
    plan = plan_for(m4_doc())
    ds_entries = [entry for entry in plan["hosts"] if entry.get("name") == "ds"]
    assert len(ds_entries) == 1
    assert set(ds_entries[0]["roles"]) == {"deployer", "deployment_server"}


def test_unknown_optional_role_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["optional_roles"].append({"name": "x", "role": "time_machine"})
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("optional_roles" in error for error in plan["errors"])
    assert "time_machine" not in json.dumps(plan)


def test_duplicate_host_name_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["optional_roles"].append({"name": "lm", "role": "license_manager"})
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("lm" in error and "more than once" in error for error in plan["errors"])


# --- Phase 4: constraints -----------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda d: d["phase_5"]["indexer_cluster"].update(peers=5), "sums to 4"),
        (lambda d: d["phase_5"]["indexer_cluster"].update(site_rf="origin:2, total:5"), "site_rf"),
        (lambda d: d["phase_5"]["indexer_cluster"].update(site_sf="origin:1, total:4"), "site_sf"),
        (lambda d: d["phase_5"]["indexer_cluster"]["peers_by_site"].pop("site2"), "site2"),
        (lambda d: d["phase_5"]["indexer_cluster"].update(site_rf="2 per site"), "site_rf"),
        (lambda d: d["phase_5"]["shcluster"].update(members=2), "members"),
        (
            lambda d: d["phase_5"]["shcluster"].update(members_by_site={"site1": 1, "site2": 1}),
            "members_by_site",
        ),
    ],
)
def test_constraint_violations_are_reported(mutate, needle):
    doc = m4_doc()
    mutate(doc)
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any(needle in error for error in plan["errors"]), plan["errors"]


def test_multisite_cluster_requires_site_rf():
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"].pop("site_rf")
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("site_rf" in error for error in plan["errors"])


def test_multisite_cluster_requires_peers_by_site():
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"].pop("peers_by_site")
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("peers_by_site" in error for error in plan["errors"])


# --- Phase 5: secrets as env var names -------------------------------------------


def test_env_lookups_become_lookups_in_the_fragment():
    plan = plan_for(m4_doc())
    fragment = plan["fragment"]
    assert fragment["splunk_defaults"]["splunk_admin_password"] == (
        "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
    )
    assert fragment["splunk_idxclusters"][0]["idxc_password"] == (
        "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"
    )
    assert fragment["splunk_shclusters"][0]["shc_password"] == (
        "{{ lookup('env', 'SPLUNK_SHC_PASSWORD') }}"
    )


def test_env_lookup_names_come_from_the_file_not_the_defaults():
    doc = m4_doc()
    doc["phase_5"]["env_lookups"]["admin"] = "ORG_ADMIN_PW"
    plan = plan_for(doc)
    assert plan["fragment"]["splunk_defaults"]["splunk_admin_password"] == (
        "{{ lookup('env', 'ORG_ADMIN_PW') }}"
    )


def test_env_lookup_value_that_is_not_an_env_name_is_rejected_without_echo():
    doc = m4_doc()
    doc["phase_5"]["env_lookups"]["admin"] = "hunter2-not-a-name"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert "hunter2" not in json.dumps(plan)


def test_missing_env_lookup_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["env_lookups"].pop("shc")
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("env_lookups" in error and "shc" in error for error in plan["errors"])


def test_secret_env_status_is_reported_as_set_or_not_set_only():
    plan = plan_for(m4_doc(), env={"SPLUNK_ADMIN_PASSWORD": "s3cret-value-xyz"})
    by_key = {row["key"]: row for row in plan["secrets"]}
    assert by_key["admin"]["set"] is True
    assert by_key["idxc"]["set"] is False
    assert "s3cret-value-xyz" not in json.dumps(plan)


def test_credential_shaped_key_with_a_value_is_rejected_without_echo():
    doc = m4_doc()
    doc["phase_5"]["admin_password"] = "letmein-literal"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("admin_password" in error for error in plan["errors"])
    assert "letmein-literal" not in json.dumps(plan)


# --- Phase 6: org_prefix and apps ----------------------------------------------


def test_org_prefix_is_written_as_splunk_env_name():
    plan = plan_for(m4_doc())
    assert plan["fragment"]["splunk_defaults"]["splunk_env_name"] == "test"


def test_invalid_org_prefix_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["org_prefix"] = "Bad Prefix!"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("org_prefix" in error for error in plan["errors"])


def test_plan_has_no_app_manifest():
    plan = plan_for(m4_doc())
    assert "app_manifest" not in plan


def test_apps_by_role_is_ignored_with_a_warning():
    doc = m4_doc()
    doc["phase_5"]["apps_by_role"] = {"site_indexer_peer": ["test_cluster_indexer_base"]}
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert any("apps_by_role" in warning for warning in plan["warnings"])


# --- Phase 9: extensions ----------------------------------------------------------


def test_extensions_are_listed_for_mapping_and_not_written_to_the_fragment():
    doc = m4_doc()
    doc["phase_5"]["_extensions"] = [
        {
            "field_name": "custom_setting_xyz",
            "value": "some_value",
            "reason": "User provided this, not in schema yet",
            "suggested_placement": "unknown",
            "severity": "info",
        }
    ]
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert plan["extensions"][0]["field_name"] == "custom_setting_xyz"
    assert plan["extensions"][0]["status"] == "unmapped"
    assert "custom_setting_xyz" not in json.dumps(plan["fragment"])


def test_extension_with_bad_shape_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["_extensions"] = [{"value": 1}]
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("_extensions" in error for error in plan["errors"])


# --- Phase 8: license and read-only ----------------------------------------------


def test_license_file_is_reported_for_the_apply_step():
    plan = plan_for(m4_doc())
    assert plan["apply"]["resolve"] == [
        {"path": "splunk_defaults.splunk_license_file", "value": LICENSE_VALUE}
    ]


def test_plan_is_read_only_and_does_not_mutate_the_input():
    doc = m4_doc()
    before = copy.deepcopy(doc)
    plan_for(doc)
    assert doc == before


def test_generator_output_sample_plans_ok():
    """The file build_architecture.py writes for its M4 example must plan without changes."""
    doc = json.loads(GENERATOR_SAMPLE.read_text(encoding="utf-8"))
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert hosts_with_role(plan["hosts"], "indexer") == ["idx1", "idx2", "idx3", "idx4"]


# --- Review findings: credentials, shape, and error output -----------------------


def test_extension_with_secret_word_key_is_rejected_without_echo():
    doc = m4_doc()
    doc["phase_5"]["_extensions"] = [
        {
            "field_name": "admin_password",
            "value": "extension-literal-xyz",
            "reason": "User provided this, not in schema yet",
            "suggested_placement": "unknown",
            "severity": "info",
        }
    ]
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("admin_password" in error for error in plan["errors"])
    assert "extension-literal-xyz" not in json.dumps(plan)


def test_secrets_container_with_a_literal_value_is_rejected_without_echo():
    doc = m4_doc()
    doc["phase_5"]["secrets"] = {"admin": "secrets-literal-xyz"}
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert "secrets-literal-xyz" not in json.dumps(plan)


def test_non_object_phase_is_an_error():
    doc = m4_doc()
    doc["phase_0a"] = "yes"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_0a" in error for error in plan["errors"])


def test_bad_provider_error_names_the_field_without_echoing_the_value():
    doc = m4_doc()
    doc["phase_4"] = {"provider": "provider-literal-xyz"}
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_4.provider" in error for error in plan["errors"])
    assert "provider-literal-xyz" not in json.dumps(plan)


def test_bad_sva_code_error_does_not_echo_the_value():
    doc = m4_doc()
    doc["phase_1"]["sva"] = "sva-literal-xyz"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_1.sva" in error for error in plan["errors"])
    assert "sva-literal-xyz" not in json.dumps(plan)


def test_topology_that_does_not_match_the_sva_code_is_an_error():
    doc = m4_doc()
    doc["phase_1"]["sva"] = "C3"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("does not match" in error for error in plan["errors"])


def test_missing_indexer_cluster_is_an_error():
    doc = m4_doc()
    del doc["phase_5"]["indexer_cluster"]
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("indexer_cluster" in error for error in plan["errors"])


def test_indexer_replication_port_is_read_from_the_input():
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"]["replication_port"] = 9999
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert plan["fragment"]["splunk_idxclusters"][0]["idxc_replication_port"] == 9999


def test_metadata_version_other_than_0_3_0_is_an_error():
    doc = m4_doc()
    doc["metadata"]["version"] = "9.9"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("version" in error for error in plan["errors"])


def test_cli_plan_failure_envelope_has_no_data_key(tmp_path):
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"]["peers"] = 9
    path = _write_doc(tmp_path, doc)
    result = run_spa(["--agent", "architecture", "plan", str(path)])
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert payload["error"]


def test_human_mode_writes_plan_errors_to_stderr_not_stdout(tmp_path):
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"]["peers"] = 9
    path = _write_doc(tmp_path, doc)
    result = run_spa(["--no-agent", "architecture", "plan", str(path)])
    assert result.returncode == 1
    assert "peers" not in result.stdout
    assert "peers" in result.stderr


# --- Generator alignment (generator is the authority) -----------------------------


def test_multisite_cluster_needs_at_least_three_indexer_peers():
    doc = m4_doc()
    idx = doc["phase_5"]["indexer_cluster"]
    idx["peers"] = 2
    idx["peers_by_site"] = {"site1": 1, "site2": 1}
    idx["site_rf"] = "origin:1, total:2"
    idx["site_sf"] = "origin:1, total:2"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("at least 3" in error for error in plan["errors"])


def test_site_sf_origin_above_site_rf_origin_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"]["site_rf"] = "origin:1, total:3"
    doc["phase_5"]["indexer_cluster"]["site_sf"] = "origin:2, total:2"
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("site_sf origin" in error for error in plan["errors"])


def test_org_prefix_of_32_characters_is_accepted():
    prefix = "a" + "b" * 31
    doc = m4_doc()
    doc["phase_5"]["org_prefix"] = prefix
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert plan["fragment"]["splunk_defaults"]["splunk_env_name"] == prefix


def test_org_prefix_of_33_characters_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["org_prefix"] = "a" + "b" * 32
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("org_prefix" in error for error in plan["errors"])


def test_shc_with_no_member_on_a_site_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["shcluster"]["members_by_site"] = {"site1": 3, "site2": 0}
    doc["phase_5"]["shcluster"]["members"] = 3
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("site2" in error and "members_by_site" in error for error in plan["errors"])


def test_phase_5b_role_with_no_host_is_an_error():
    doc = m4_doc()
    doc["phase_5"]["optional_roles"] = [
        row for row in doc["phase_5"]["optional_roles"] if row["role"] != "monitoring_console"
    ]
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("phase_5b.roles" in error for error in plan["errors"])


def test_license_manager_without_license_file_is_a_warning_at_plan_time():
    """The SVA file never holds phase_6b; the spa skill collects it before the write."""
    doc = m4_doc()
    doc["phase_6b"] = {"confirmed": False}
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert any("license_file" in warning for warning in plan["warnings"])


def test_unconfirmed_phase_adds_a_warning_and_still_plans():
    doc = m4_doc()
    doc["phase_5"]["confirmed"] = False
    plan = plan_for(doc)
    assert plan["ok"] is True, plan["errors"]
    assert any("phase_5" in warning and "confirmed" in warning for warning in plan["warnings"])


# --- CLI contract ---------------------------------------------------------------


def _write_doc(tmp_path, doc):
    path = tmp_path / "architecture.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_cli_plan_returns_one_json_object_for_a_valid_file(tmp_path):
    path = _write_doc(tmp_path, m4_doc())
    result = run_spa(["--agent", "architecture", "plan", str(path)])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["ok"] is True
    assert payload["data"]["hosts"]


def test_cli_plan_fails_with_json_error_for_an_invalid_file(tmp_path):
    doc = m4_doc()
    doc["phase_5"]["indexer_cluster"]["peers"] = 9
    path = _write_doc(tmp_path, doc)
    result = run_spa(["--agent", "architecture", "plan", str(path)])
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "peers" in payload["error"]


def test_cli_plan_rejects_a_file_that_is_not_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    result = run_spa(["--agent", "architecture", "plan", str(path)])
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "JSON" in payload["error"]


def test_cli_write_fragment_writes_the_merge_input(tmp_path):
    path = _write_doc(tmp_path, m4_doc())
    out = tmp_path / "fragment.json"
    result = run_spa(
        ["--agent", "architecture", "plan", str(path), "--write-fragment", str(out)]
    )
    assert result.returncode == 0, result.stderr
    fragment = json.loads(out.read_text(encoding="utf-8"))
    assert fragment["splunk_defaults"]["splunk_env_name"] == "test"
    assert fragment["splunk_hosts"]


def test_write_fragment_refuses_to_overwrite_splunk_config(tmp_path):
    path = _write_doc(tmp_path, m4_doc())
    config = tmp_path / "splunk_config.yml"
    config.write_text("plugin: splunk-platform-automator\n", encoding="utf-8")
    result = run_spa(
        ["--agent", "architecture", "plan", str(path), "--write-fragment", str(config)]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "splunk_config.yml" in payload["error"]
    assert config.read_text(encoding="utf-8") == "plugin: splunk-platform-automator\n"


def test_human_mode_prints_hosts_and_env_status_without_values(tmp_path):
    path = _write_doc(tmp_path, m4_doc())
    result = run_spa(
        ["--no-agent", "architecture", "plan", str(path)],
        extra_env={"SPLUNK_ADMIN_PASSWORD": "human-secret-value-xyz"},
    )
    assert result.returncode == 0, result.stderr
    assert "Hosts:" in result.stdout
    assert "cm" in result.stdout and "idx4" in result.stdout
    assert "Env SPLUNK_ADMIN_PASSWORD (admin): set" in result.stdout
    assert "human-secret-value-xyz" not in result.stdout + result.stderr


def test_cli_never_prints_a_secret_value(tmp_path):
    path = _write_doc(tmp_path, m4_doc())
    result = run_spa(
        ["--agent", "architecture", "plan", str(path)],
        extra_env={"SPLUNK_ADMIN_PASSWORD": "cli-secret-value-xyz"},
    )
    assert result.returncode == 0, result.stderr
    assert "cli-secret-value-xyz" not in result.stdout
    assert "cli-secret-value-xyz" not in result.stderr
    payload = json.loads(result.stdout)
    assert {row["key"]: row["set"] for row in payload["data"]["secrets"]}["admin"] is True


def test_plan_applies_to_a_real_env_and_validates(tmp_path):
    """Plan -> merge fragment -> unset base host -> validate, on a throwaway env."""
    import yaml

    from spa_testutil import seed_software_dir

    software = seed_software_dir(tmp_path / "data")
    (software / "Splunk_Enterprise.lic").write_text("placeholder-license\n", encoding="utf-8")
    (software / "splunk-9.3.1-1-linux-amd64.tgz").write_bytes(b"")
    (software / "splunkforwarder-9.3.1-1-linux-amd64.tgz").write_bytes(b"")
    secrets = {
        "SPA_SOFTWARE_DIR": str(software),
        "SPA_BASECONFIG_DIR": str(software),
        "SPLUNK_ADMIN_PASSWORD": "e2e-admin-value",
        "SPLUNK_IDXC_PASSWORD": "e2e-idxc-value",
        "SPLUNK_SHC_PASSWORD": "e2e-shc-value",
    }
    lab = tmp_path / "lab"
    init = run_spa(
        [
            "--agent", "init", "--env-dir", str(tmp_path), "--name", "lab",
            "--example", "topology.s1", "--provider", "external", "--skip-doctor",
        ],
        extra_env=secrets,
    )
    assert init.returncode == 0, init.stdout + init.stderr

    doc_path = _write_doc(tmp_path, m4_doc())
    fragment = tmp_path / "fragment.json"
    plan = run_spa(
        ["--agent", "architecture", "plan", str(doc_path), "--write-fragment", str(fragment)],
        extra_env=secrets,
    )
    assert plan.returncode == 0, plan.stdout + plan.stderr

    merge = run_spa(
        [
            "--agent", "--env", str(lab), "config", "merge", "--file", str(fragment), "--yes",
            "--resolve", "splunk_defaults.splunk_license_file", LICENSE_VALUE,
        ],
        extra_env=secrets,
    )
    assert json.loads(merge.stdout)["ok"] is True, merge.stdout + merge.stderr

    unset = run_spa(
        ["--agent", "--env", str(lab), "config", "unset", "splunk_hosts[name=shidx]", "--yes"],
        extra_env=secrets,
    )
    assert json.loads(unset.stdout)["ok"] is True, unset.stdout + unset.stderr

    validate = run_spa(["--agent", "--env", str(lab), "validate"], extra_env=secrets)
    assert json.loads(validate.stdout)["ok"] is True, validate.stdout + validate.stderr

    config_text = (lab / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)
    names = [entry.get("name") for entry in config["splunk_hosts"] if "name" in entry]
    assert "shidx" not in names
    assert "cm" in names and "lm" in names and "uf" in names
    indexers = [
        entry for entry in config["splunk_hosts"] if "indexer" in entry.get("roles", [])
    ]
    assert sorted(entry["name"] for entry in indexers) == ["idx1", "idx2", "idx3", "idx4"]
    assert config["splunk_defaults"]["splunk_env_name"] == "test"
    assert config["splunk_defaults"]["splunk_admin_password"] == (
        "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
    )
    for value in secrets.values():
        if value.endswith("-value"):
            assert value not in config_text
