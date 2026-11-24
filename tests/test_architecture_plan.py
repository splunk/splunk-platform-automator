"""Tests for spa architecture plan / apply / check (splunk.architecture schema 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_inprocess, run_spa_init

pytestmark = [pytest.mark.local, pytest.mark.cli, pytest.mark.cli_runtime]

EXAMPLES = PROJECT_ROOT / "examples" / "architectures"
C1 = EXAMPLES / "c1.json"
C3 = EXAMPLES / "c3.json"
M4 = EXAMPLES / "m4.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def plan_for(doc, env=None):
    from spa.architecture import plan_architecture

    return plan_architecture(doc, env=env or {}, spa_home=PROJECT_ROOT)


def expanded_names(hosts):
    from spa.architecture import expand_host_names

    names = []
    for host in hosts:
        names.extend(expand_host_names(host))
    return names


def roles_on(hosts, role):
    from spa.architecture import expand_host_names, host_roles

    found = []
    for host in hosts:
        if role in host_roles(host):
            found.extend(expand_host_names(host))
    return found


def test_examples_are_confirmed_schema_1_without_secrets_or_delivery():
    for path in (C1, C3, M4):
        doc = _load(path)
        assert doc["kind"] == "splunk.architecture"
        assert doc["schema_version"] == 1
        assert isinstance(doc["schema_version"], int)
        assert doc["generator"]["version"] == "0.3.0"
        assert doc["confirmed"] is True
        assert doc["apps"]["by_role"] == {}
        assert "secrets" not in doc
        assert "delivery" not in doc
        assert doc["extensions"] == []


def test_c3_example_plans_ok_and_scales_indexers():
    plan = plan_for(_load(C3))
    assert plan["ok"] is True, plan.get("errors")
    assert plan["sva"] == "C3"
    assert plan["topology"] == "topology.c3"
    hosts = plan["hosts"]
    assert len(roles_on(hosts, "indexer")) == 3
    assert len(roles_on(hosts, "search_head")) == 3
    assert roles_on(hosts, "license_manager") == ["lm"]
    assert roles_on(hosts, "cluster_manager") == ["cm"]
    assert "deployer" in host_roles_for(hosts, "ds")
    idxc = plan["config"]["splunk_idxclusters"][0]
    assert idxc["idxc_rf"] == 3
    assert idxc["idxc_sf"] == 2
    assert plan["config"]["splunk_defaults"]["splunk_env_name"] == "acme"
    assert "apps.by_role" in plan["skipped"]
    assert plan.get("skipped_app_folders") == []
    assert "provider" in plan["remaining"]
    for name in ("hardware", "os", "apps", "licenses"):
        assert name in plan["remaining"]
    assert "aws" not in plan["remaining"]


def test_remaining_questions_skips_settled_hardware_os_aws_apps_licenses():
    from spa.architecture import remaining_questions

    unset = remaining_questions(None, has_provider=True)
    assert unset == ["hardware", "os", "apps", "licenses"]
    assert remaining_questions(None, has_provider=False)[0] == "provider"

    aws = {
        "terraform": {
            "aws": {
                "region": "eu-central-1",
                "ami_id": "ami-0123456789abcdef0",
                "instance_type": "t3.medium",
                "ssh_username": "ec2-user",
            }
        },
        "os": {"packages": ["acl", "polkit"]},
        "splunk_defaults": {"splunk_license_file": "Splunk_Enterprise.lic"},
        "splunk_app_deployment": {
            "apps": [{"app_id": 833, "name": "Splunk_TA_nix", "target_roles": ["universal_forwarder"]}]
        },
    }
    assert remaining_questions(aws, has_provider=True) == []

    aws_only = {"terraform": {"aws": {"region": "eu-central-1", "ami_id": "ami-0123456789abcdef0"}}}
    assert remaining_questions(aws_only, has_provider=True) == [
        "hardware",
        "os",
        "aws",
        "apps",
        "licenses",
    ]
    unfinished_aws = {"terraform": {"aws": {"region": "eu-central-1", "instance_type": "t3.medium"}}}
    remaining = remaining_questions(unfinished_aws, has_provider=True)
    assert "aws" in remaining
    assert "hardware" not in remaining


def test_remaining_os_is_aws_only_and_per_host_values_settle():
    from spa.architecture import remaining_questions

    for provider in ({"virtualbox": {"box": "almalinux/8"}}, {"ccm": {"instance_type": "t3a.medium"}}, {"external": None}):
        assert "os" not in remaining_questions(provider, has_provider=True), provider

    hosts = [{"name": "sh1", "roles": ["search_head"]}, {"name": "idx1", "roles": ["indexer"]}]
    per_host = {
        "terraform": {"aws": {"region": "eu-central-1", "ami_id": "ami-0123456789abcdef0"}},
        "splunk_hosts": [
            {**host, "os": {"packages": ["acl"]}, "terraform": {"aws": {"ssh_username": "ec2-user"}}}
            for host in hosts
        ],
    }
    remaining = remaining_questions(per_host, has_provider=True)
    assert "os" not in remaining
    assert "aws" not in remaining

    per_host["splunk_hosts"][1] = hosts[1]
    remaining = remaining_questions(per_host, has_provider=True)
    assert "os" in remaining
    assert "aws" in remaining


def test_remaining_next_follows_real_remaining_gaps():
    from spa.next_steps import remaining_next

    rows = remaining_next(["hardware", "os", "aws", "apps", "licenses"])
    ids = [row["id"] for row in rows]
    assert ids == ["hardware", "os", "aws.region", "aws", "apps.search", "licenses.list"]
    region = rows[2]
    assert region["command"] == "spa --agent provider aws regions list"
    assert rows[3]["command"] == "spa --agent provider aws latest-ami"
    assert remaining_next([]) == []


def test_plan_lists_skipped_app_folder_names(tmp_path):
    doc = _load(C3)
    doc["apps"] = {
        "by_role": {
            "indexer": ["ClusterBaseConfigs"],
            "search_head": ["BaseConfigs", "ClusterBaseConfigs"],
        }
    }
    plan = plan_for(doc)
    assert plan["ok"] is True, plan.get("errors")
    assert plan["skipped_app_folders"] == ["ClusterBaseConfigs", "BaseConfigs"]


def host_roles_for(hosts, name):
    from spa.architecture import expand_host_names, host_roles

    for host in hosts:
        if name in expand_host_names(host):
            return host_roles(host)
    return []


def test_c1_example_plans_three_indexers_and_standalone_search_head():
    plan = plan_for(_load(C1))
    assert plan["ok"] is True, plan.get("errors")
    assert plan["topology"] == "topology.c1"
    hosts = plan["hosts"]
    assert len(roles_on(hosts, "indexer")) == 3
    assert roles_on(hosts, "search_head") == ["sh"]
    assert roles_on(hosts, "license_manager") == []


def test_m4_example_keeps_site_counts_and_adds_missing_roles():
    plan = plan_for(_load(M4))
    assert plan["ok"] is True, plan.get("errors")
    assert plan["topology"] == "topology.m4"
    hosts = plan["hosts"]
    assert len(roles_on(hosts, "indexer")) == 4
    assert len(roles_on(hosts, "search_head")) == 3
    assert roles_on(hosts, "license_manager") == ["lm"]
    assert roles_on(hosts, "universal_forwarder") == ["uf"]
    assert "deployment_server" in host_roles_for(hosts, "ds")
    assert "monitoring_console" in host_roles_for(hosts, "cm")
    idxc = plan["config"]["splunk_idxclusters"][0]
    assert idxc["idxc_site_rf"] == "origin:2, total:3"
    assert idxc["idxc_site_sf"] == "origin:1, total:2"
    assert any(
        "replication_factor" in warning and "search_head" in warning
        for warning in plan["warnings"]
    )


def test_unmapped_architecture_role_is_an_error():
    doc = _load(C3)
    doc["deployment"]["roles"].append({"role": "kvstore_server", "count": 1})
    plan = plan_for(doc)
    assert plan["ok"] is False
    assert any("kvstore_server" in error for error in plan["errors"])
    assert any("cluster_manager" in error for error in plan["errors"])


def test_missing_kind_or_schema_version_is_an_error():
    doc = _load(C3)
    del doc["schema_version"]
    plan = plan_for(doc)
    assert plan["ok"] is False
    joined = " ".join(plan["errors"])
    assert "schema_version" in joined
    assert "kind" in joined or "schema_version" in joined


def test_gate_architecture_version_accepts_int_1():
    from spa.architecture import gate_architecture_version

    gate_architecture_version({"kind": "splunk.architecture", "schema_version": 1})


@pytest.mark.parametrize("value", [True, False, "1", "0.4.0"])
def test_gate_architecture_version_rejects_bool_and_strings(value):
    from spa.architecture import ArchitectureError, gate_architecture_version

    with pytest.raises(ArchitectureError, match="integer"):
        gate_architecture_version({"kind": "splunk.architecture", "schema_version": value})


def test_gate_architecture_version_rejects_older_int_without_upgrade():
    from spa.architecture import ArchitectureError, gate_architecture_version

    with pytest.raises(ArchitectureError, match="not supported") as exc:
        gate_architecture_version({"kind": "splunk.architecture", "schema_version": 0})
    assert "Upgrade spa" not in str(exc.value)


def test_gate_architecture_version_newer_int_asks_to_upgrade_spa():
    from spa.architecture import ArchitectureError, gate_architecture_version

    with pytest.raises(ArchitectureError, match="Upgrade spa") as exc:
        gate_architecture_version({"kind": "splunk.architecture", "schema_version": 2})
    text = str(exc.value)
    assert "2" in text
    assert "1" in text


def test_newer_schema_version_asks_to_upgrade_spa():
    doc = _load(C3)
    doc["schema_version"] = 2
    plan = plan_for(doc)
    assert plan["ok"] is False
    joined = " ".join(plan["errors"]).lower()
    assert "2" in joined
    assert "upgrade spa" in joined


def test_unconfirmed_file_plans_with_a_warning():
    doc = _load(C3)
    doc["confirmed"] = False
    plan = plan_for(doc)
    assert plan["ok"] is True, plan.get("errors")
    assert any("confirmed" in warning for warning in plan["warnings"])


def test_secret_shaped_value_is_rejected_without_echo():
    doc = _load(C3)
    secret = "super-secret-password-value-xyz"
    doc["secrets"] = {
        "idxc": {"source": "env", "name": secret},
    }
    plan = plan_for(doc)
    assert plan["ok"] is False
    blob = json.dumps(plan)
    assert secret not in blob
    assert any("secrets" in error for error in plan["errors"])


def test_cli_plan_returns_one_json_object_for_c3():
    result = run_spa(["--agent", "architecture", "plan", str(C3)])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["ok"] is True
    assert payload["data"]["topology"] == "topology.c3"
    assert payload["data"]["schema_version"] == 1
    assert "data" in payload


def _plan_next(extra_env=None):
    result = run_spa(
        ["--agent", "architecture", "plan", str(C3)],
        extra_env=extra_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    return payload["data"]["next"]


def test_architecture_plan_next_is_write_mode_then_provider():
    from spa.providers import provider_ids

    nxt = _plan_next()
    ids = [row["id"] for row in nxt]
    assert ids[:2] == ["mode.write", "provider"]
    write = nxt[0]
    ask = write["ask"].lower()
    assert "architecture file is the plan" in ask
    assert "plan vs write" in ask
    assert "location" in ask and "name" in ask
    assert write["command"] == (
        "spa --agent environment init PARENT/NAME --architecture %s --provider"
        % C3
    )
    assert write["argv"] == [
        "spa",
        "--agent",
        "environment",
        "init",
        "PARENT/NAME",
        "--architecture",
        str(C3),
        "--provider",
    ]
    provider = nxt[1]
    allowed = [name for name in provider_ids() if name != "ccm"]
    assert provider["choice"]["allowed"] == allowed
    assert "ccm" not in allowed
    assert "apps.search" in ids
    assert "licenses.list" in ids


def test_human_architecture_plan_prints_next():
    result = run_spa(["--no-agent", "architecture", "plan", str(C3)])
    assert result.returncode == 0, result.stderr
    err = result.stderr
    assert "Next:" in err
    assert "Architecture file is the plan" in err
    assert "plan vs write" in err.lower()
    assert "spa environment init PARENT/NAME --architecture" in err
    assert "--agent" not in err


def test_cli_plan_does_not_require_an_env(tmp_path):
    result = run_spa(
        ["--agent", "--start-dir", str(tmp_path), "architecture", "plan", str(C3)]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_human_mode_prints_hosts_without_secret_values(tmp_path):
    result = run_spa(
        ["--no-agent", "architecture", "plan", str(C3)],
        extra_env={"SPLUNK_ADMIN_PASSWORD": "human-secret-value-xyz"},
    )
    assert result.returncode == 0, result.stderr
    assert "cm" in result.stdout
    assert "idx3" in result.stdout
    assert "lm" in result.stdout
    assert "human-secret-value-xyz" not in result.stdout + result.stderr


def test_init_architecture_overlays_c3(tmp_path):
    dest = tmp_path / "c3-lab"
    result = run_spa_init(
        ["--architecture", str(C3), "--provider", "aws", str(dest)]
    )
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    assert len(roles_on(cfg["splunk_hosts"], "indexer")) == 3
    assert roles_on(cfg["splunk_hosts"], "license_manager") == []
    assert cfg["splunk_idxclusters"][0]["idxc_rf"] == 3
    assert cfg["splunk_defaults"]["splunk_env_name"] == "acme"
    assert "terraform" in cfg and "aws" in cfg["terraform"]


def test_init_architecture_warns_when_license_manager_is_deferred(tmp_path):
    dest = tmp_path / "c3-lab"
    result = run_spa_init(
        ["--architecture", str(C3), "--provider", "aws", str(dest)]
    )
    assert result.returncode == 0, result.stderr
    text = result.stderr + result.stdout
    assert (
        "license_manager is required by the architecture file but not applied until a license file is set"
        in text
    )
    assert "architecture check: deployment.roles.license_master.count" in text
    assert "expected 1, found 0" in text
    assert "Remaining:" in text
    assert "license_manager" in text


def test_agent_init_architecture_includes_deferred_warnings(tmp_path):
    dest = tmp_path / "c3-lab"
    result = run_spa(
        [
            "--agent",
            "init",
            "--architecture",
            str(C3),
            "--provider",
            "aws",
            "--skip-doctor",
            str(dest),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    warnings = payload["data"]["architecture"]["warnings"]
    assert any("license_manager is required" in item for item in warnings)
    assert any("deployment.roles.license_master.count" in item for item in warnings)
    assert "license_manager" in payload["data"]["architecture"]["remaining"]


def test_agent_init_architecture_attaches_remaining_next(tmp_path):
    dest = tmp_path / "c3-lab"
    result = run_spa(
        [
            "--agent",
            "init",
            "--architecture",
            str(C3),
            "--provider",
            "aws",
            "--skip-doctor",
            str(dest),
        ],
        extra_env={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert data["remaining"] == data["architecture"]["remaining"]
    assert data["remaining"][:4] == ["os", "aws", "apps", "licenses"]
    assert "license_manager" in data["remaining"]
    assert "hardware" not in data["remaining"]
    ids = [row["id"] for row in data["next"]]
    assert ids[:5] == ["os", "aws.region", "aws", "apps.search", "licenses.list"]
    assert "license_manager.placement" in ids
    aws = next(row for row in data["next"] if row["id"] == "aws")
    assert aws["command"] == "spa --agent provider aws latest-ami"

    human = run_spa_init(
        ["--architecture", str(C3), "--provider", "aws", str(tmp_path / "c3-human")],
        extra_env={"XDG_CONFIG_HOME": str(tmp_path / "xdg-human")},
    )
    assert human.returncode == 0, human.stderr + human.stdout
    err = human.stderr
    assert "Next:" in err
    assert "Which AWS region for these hosts?" in err
    assert "Find a current AMI and SSH user for this region?" in err
    assert "spa provider aws latest-ami" in err
    assert "--agent" not in err


def test_init_architecture_and_example_are_exclusive(tmp_path):
    dest = tmp_path / "lab"
    result = run_spa_init(
        [
            "--architecture",
            str(C3),
            "--example",
            "topology.c3",
            "--provider",
            "aws",
            str(dest),
        ]
    )
    assert result.returncode == 2
    text = result.stderr + result.stdout
    assert "--architecture" in text
    assert "--example" in text


def test_init_refuses_unconfirmed_architecture(tmp_path):
    doc = _load(C3)
    doc["confirmed"] = False
    path = tmp_path / "unconfirmed.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    dest = tmp_path / "lab"
    result = run_spa_init(["--architecture", str(path), "--provider", "aws", str(dest)])
    assert result.returncode != 0
    assert "confirmed" in (result.stderr + result.stdout).lower()


def test_apply_overlays_existing_env(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "apply", str(C3), "--yes"],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    ingested = payload["data"]["ingested"]
    assert ingested
    warnings = payload["data"]["warnings"]
    assert any("license_manager is required" in item for item in warnings)
    assert any("deployment.roles.license_master.count" in item for item in warnings)
    assert "license_manager" in payload["data"]["remaining"]
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    assert len(roles_on(cfg["splunk_hosts"], "indexer")) == 3
    assert roles_on(cfg["splunk_hosts"], "license_manager") == []


def test_apply_warns_when_license_manager_is_deferred(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    result = run_spa(
        [
            "--no-agent",
            "--start-dir",
            str(dest),
            "architecture",
            "apply",
            str(C3),
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    text = result.stderr + result.stdout
    assert "license_manager is required" in text
    assert "architecture check: deployment.roles.license_master.count" in text
    assert "Remaining:" in text
    assert "Next:" in text
    assert "spa licenses list" in result.stderr
    assert "spa --agent licenses list" not in result.stderr


def test_apply_refuses_unconfirmed(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--example", "topology.c3", "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    doc = _load(C3)
    doc["confirmed"] = False
    path = tmp_path / "unconfirmed.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "apply", str(path), "--yes"],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "confirmed" in payload["error"].lower()


def _add_license_manager(env_dir, tmp_path):
    license_file = tmp_path / "Splunk_Enterprise.lic"
    license_file.write_text("dummy-license\n", encoding="utf-8")
    result = run_spa(
        [
            "--agent",
            "--start-dir",
            str(env_dir),
            "config",
            "add",
            "splunk_hosts[name=lm]",
            '{"roles":["license_manager"]}',
            "--resolve",
            "splunk_defaults.splunk_license_file",
            str(license_file),
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(env_dir)},
    )
    assert result.returncode == 0, result.stderr


def test_check_passes_after_c3_overlay(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--architecture", str(C3), "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    _add_license_manager(dest, tmp_path)
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "check", str(C3)],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["matched"]


def test_check_fails_when_an_indexer_is_dropped(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--architecture", str(C3), "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    _add_license_manager(dest, tmp_path)
    shrink = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "set",
            "splunk_hosts[iter.prefix=idx].iter.numbers",
            "1..2",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert shrink.returncode == 0, shrink.stderr
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "check", str(C3)],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any("indexer" in json.dumps(item) for item in payload["data"]["mismatches"])


def test_check_fails_when_rf_changes(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--architecture", str(C3), "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    _add_license_manager(dest, tmp_path)
    change = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "set",
            "splunk_idxclusters[idxc_name=idxc1].idxc_rf",
            "2",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert change.returncode == 0, change.stderr
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "check", str(C3)],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(
        "replication" in json.dumps(item).lower() or "idxc_rf" in json.dumps(item)
        for item in payload["data"]["mismatches"]
    )


def test_check_allows_an_extra_forwarder(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--architecture", str(C3), "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    _add_license_manager(dest, tmp_path)
    add = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "add",
            "splunk_hosts[name=uf]",
            '{"roles":["universal_forwarder"]}',
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert add.returncode == 0, add.stderr
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "check", str(C3)],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    extra = payload["data"].get("extra") or {}
    assert extra


def test_check_fails_after_wrong_topology_replace(tmp_path):
    dest = tmp_path / "lab"
    init = run_spa_init(["--architecture", str(C3), "--provider", "aws", str(dest)])
    assert init.returncode == 0, init.stderr
    swap = run_spa(
        [
            "--agent",
            "--start-dir",
            str(dest),
            "config",
            "topology",
            "topology.s1",
            "--yes",
        ],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert swap.returncode == 0, swap.stderr
    result = run_spa(
        ["--agent", "--start-dir", str(dest), "architecture", "check", str(C3)],
        extra_env={"SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any("sva" in json.dumps(item).lower() or "topology" in json.dumps(item).lower() for item in payload["data"]["mismatches"])
