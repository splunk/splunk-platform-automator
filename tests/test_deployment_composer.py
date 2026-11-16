"""Local tests for live-deployment compose (topology × provider × suite hook)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from deployment_compose import (
    ComposeError,
    compose_deployment_config,
    load_suite,
)
from deployment_provider import OS_PACKAGES, ami_identity_from_payload

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_ROOT = PROJECT_ROOT / "tests" / "deployment"

MOCK_AMIS = {
    "ubuntu": {"ami_id": "ami-0aa11bb22cc33dd01", "suggested_ssh_username": "ubuntu"},
    "rhel": {"ami_id": "ami-0aa11bb22cc33dd02", "suggested_ssh_username": "ec2-user"},
    "amazon_linux": {
        "ami_id": "ami-0aa11bb22cc33dd03",
        "suggested_ssh_username": "ec2-user",
    },
    "debian": {"ami_id": "ami-0aa11bb22cc33dd04", "suggested_ssh_username": "admin"},
}


def _ami_resolver(os_key: str, region: str) -> dict:
    assert region == "eu-central-1"
    return dict(MOCK_AMIS[os_key])


def _write_layout(root: Path) -> Path:
    tests_root = root / "tests"
    topo = tests_root / "deployment" / "topologies"
    prov = tests_root / "deployment" / "providers"
    suites = tests_root / "deployment" / "suites"
    for path in (topo, prov, suites):
        path.mkdir(parents=True)

    (topo / "lab.yml").write_text(
        "plugin: splunk-platform-automator\n"
        "general:\n"
        "  url_locale: en-US\n"
        "splunk_defaults:\n"
        "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
        "splunk_app_deployment:\n"
        "  apps: []\n"
        "os:\n"
        "  set_hostname: true\n"
        "splunk_hosts:\n"
        "  - name: shidx\n"
        "    roles: [indexer, search_head]\n"
        "  - name: uf\n"
        "    roles: [universal_forwarder]\n",
        encoding="utf-8",
    )
    (prov / "aws.yml").write_text(
        "terraform:\n"
        "  aws:\n"
        "    region: eu-central-1\n"
        "    key_name: aws_key\n"
        "    instance_type: t3.2xlarge\n"
        "general:\n"
        "  url_locale: en-GB\n",
        encoding="utf-8",
    )
    (suites / "aws.yml").write_text(
        "provider: aws\n"
        "pytest_mark: aws\n"
        "topologies:\n"
        "  - id: lab\n"
        "    os: ubuntu\n"
                "    extra_ufs:\n"
                "      uf-rhel: rhel\n",
        encoding="utf-8",
    )
    return tests_root


def test_compose_merges_provider_first_topology_wins_then_aws_identity(tmp_path):
    tests_root = _write_layout(tmp_path)
    calls = []

    def resolver(os_key, region):
        calls.append(os_key)
        return _ami_resolver(os_key, region)

    composed = compose_deployment_config(
        tests_root,
        suite_id="aws",
        topology_id="lab",
        ami_resolver=resolver,
    )

    assert composed["plugin"] == "splunk-platform-automator"
    assert composed["schema_version"] == 1
    assert composed["general"]["url_locale"] == "en-US"
    assert composed["os"]["set_hostname"] is True
    assert composed["os"]["packages"] == OS_PACKAGES["ubuntu"]
    assert composed["splunk_app_deployment"] == {"apps": []}
    aws = composed["terraform"]["aws"]
    assert aws["region"] == "eu-central-1"
    assert aws["instance_type"] == "t3.2xlarge"
    assert aws["ami_id"] == MOCK_AMIS["ubuntu"]["ami_id"]
    assert aws["ssh_username"] == "ubuntu"
    names = [host["name"] for host in composed["splunk_hosts"]]
    assert names == ["shidx", "uf", "uf-rhel"]
    extra = composed["splunk_hosts"][2]
    assert extra["roles"] == ["universal_forwarder"]
    assert extra["terraform"]["aws"]["ami_id"] == MOCK_AMIS["rhel"]["ami_id"]
    assert extra["terraform"]["aws"]["ssh_username"] == "ec2-user"
    assert extra["os"]["packages"] == OS_PACKAGES["rhel"]
    assert sorted(set(calls)) == ["rhel", "ubuntu"]


def test_compose_rejects_provider_roots_on_topologies(tmp_path):
    tests_root = _write_layout(tmp_path)
    topo = tests_root / "deployment" / "topologies" / "lab.yml"
    data = yaml.safe_load(topo.read_text(encoding="utf-8"))
    data["terraform"] = {"aws": {"region": "us-east-1"}}
    topo.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ComposeError, match="must not contain terraform"):
        compose_deployment_config(
            tests_root,
            suite_id="aws",
            topology_id="lab",
            ami_resolver=_ami_resolver,
        )


def test_compose_rejects_hosts_on_provider_files(tmp_path):
    tests_root = _write_layout(tmp_path)
    prov = tests_root / "deployment" / "providers" / "aws.yml"
    data = yaml.safe_load(prov.read_text(encoding="utf-8"))
    data["splunk_hosts"] = [{"name": "stolen", "roles": ["indexer"]}]
    prov.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ComposeError, match="must not contain splunk_hosts"):
        compose_deployment_config(
            tests_root,
            suite_id="aws",
            topology_id="lab",
            ami_resolver=_ami_resolver,
        )


def test_aws_hook_uses_os_all_when_several_guests_are_needed(tmp_path, monkeypatch):
    tests_root = _write_layout(tmp_path)
    recorded = []

    def fake_latest_ami(*, os_key, region):
        recorded.append(os_key)
        assert region == "eu-central-1"
        if os_key == "all":
            return {
                "ok": True,
                "recommended_amis": {
                    key: {"ok": True, "item": value} for key, value in MOCK_AMIS.items()
                },
            }
        return {"ok": True, "item": MOCK_AMIS[os_key]}

    monkeypatch.setattr(
        "deployment_provider.fetch_latest_ami_payload", fake_latest_ami
    )
    compose_deployment_config(tests_root, suite_id="aws", topology_id="lab")
    assert recorded == ["all"]


def test_composed_aws_topologies_match_schema(tmp_path):
    plugin_dir = str(PROJECT_ROOT / "ansible" / "plugins" / "inventory")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    from schema import validate_config_file

    for topology_id in (
        "single_node",
        "2idx_sh_ds_hf_uf",
        "cm_2idxc_3shc_ds",
        "2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps",
    ):
        composed = compose_deployment_config(
            PROJECT_ROOT / "tests",
            suite_id="aws",
            topology_id=topology_id,
            ami_resolver=_ami_resolver,
        )
        staged = tmp_path / ("%s.yml" % topology_id)
        staged.write_text(yaml.safe_dump(composed, sort_keys=False), encoding="utf-8")
        validate_config_file(str(staged))


def test_aws_suite_file_lists_four_topologies_and_os_map():
    suite = load_suite(DEPLOYMENT_ROOT, "aws")
    assert suite["provider"] == "aws"
    assert suite["pytest_mark"] == "aws"
    ids = [row["id"] for row in suite["topologies"]]
    assert ids == [
        "single_node",
        "2idx_sh_ds_hf_uf",
        "cm_2idxc_3shc_ds",
        "2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps",
    ]
    by_id = {row["id"]: row for row in suite["topologies"]}
    assert by_id["single_node"]["os"] == "ubuntu"
    assert by_id["2idx_sh_ds_hf_uf"]["os"] == "amazon_linux"
    assert by_id["2idx_sh_ds_hf_uf"]["extra_ufs"] == {
        "uf-ubuntu": "ubuntu",
        "uf-rhel": "rhel",
    }
    assert by_id["cm_2idxc_3shc_ds"]["os"] == "rhel"
    assert by_id["2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps"]["os"] == "rhel"
    assert "extra_ufs" not in by_id["2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps"]


def test_live_topologies_are_provider_free_and_aws_provider_has_no_ami():
    forbidden = ("terraform", "ccm", "virtualbox", "aws")
    for path in sorted((DEPLOYMENT_ROOT / "topologies").glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        present = [key for key in forbidden if data.get(key)]
        assert not present, "%s must not contain %s" % (path.name, ", ".join(present))
    provider = yaml.safe_load(
        (DEPLOYMENT_ROOT / "providers" / "aws.yml").read_text(encoding="utf-8")
    )
    aws = (provider.get("terraform") or {}).get("aws") or {}
    assert "ami_id" not in aws
    assert "ssh_username" not in aws


def test_ami_identity_reads_items_when_rhel_omits_item():
    payload = {
        "ok": True,
        "data": {
            "ok": True,
            "os": "rhel",
            "items": [MOCK_AMIS["rhel"]],
        },
    }
    ident = ami_identity_from_payload(payload, "rhel")
    assert ident["ami_id"] == MOCK_AMIS["rhel"]["ami_id"]
    assert ident["suggested_ssh_username"] == "ec2-user"


def test_mocked_latest_ami_json_shape_matches_spa_agent_envelope():
    envelope = {
        "ok": True,
        "schema_version": 1,
        "data": {
            "ok": True,
            "region": "eu-central-1",
            "item": MOCK_AMIS["ubuntu"],
        },
    }
    assert json.loads(json.dumps(envelope))["data"]["item"]["ami_id"].startswith("ami-")


def test_aws_deployment_collection_parametrizes_suite_topology_ids():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "lib") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            "aws",
            str(PROJECT_ROOT / "tests" / "test_deployment.py"),
            "--deployment-suite",
            "aws",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for topology_id in (
        "single_node",
        "2idx_sh_ds_hf_uf",
        "cm_2idxc_3shc_ds",
        "2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps",
    ):
        assert topology_id in out
    assert "2site-idxc_shc_mc_ds_hf_uf" not in out
    assert "NO_CONFIGS_FOUND" not in out


def test_readme_documents_deployment_suites_and_spa_steps():
    text = (PROJECT_ROOT / "tests" / "README.md").read_text(encoding="utf-8")
    assert "tests/deployment/" in text
    assert "run_deployment_aws_tests.sh" in text
    assert "spa validate" in text
    assert "spa deploy --yes" in text
    assert "spa run verification/" in text
    assert "spa destroy --yes" in text
