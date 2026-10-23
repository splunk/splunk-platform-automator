"""Replay the clustered ITSI walkthrough through bin/spa."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from spa_testutil import LIB, PROJECT_ROOT, seed_software_dir, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

_BASH = re.compile(r"```bash\n(.*?)```", re.S)
_TEXT = re.compile(r"```text\n(.*?)```", re.S)
_SPA = str(PROJECT_ROOT / "bin" / "spa")


def _walkthrough() -> str:
    return (PROJECT_ROOT / "docs" / "config-walkthrough.md").read_text(encoding="utf-8")


def _fences(text: str) -> list[str]:
    return [
        block.strip()
        for block in _BASH.findall(text)
        if "spa provision" not in block and "spa deploy" not in block
    ]


def test_walkthrough_documents_the_unset_lookup_error():
    """The documented error is produced without changing this process environment."""
    documented = _TEXT.search(_walkthrough()).group(1).strip()
    script = """
import os
for name in ("SPLUNK_IDXC_PASSWORD", "SPLUNK_ADMIN_PASSWORD", "SPLUNK_SHC_PASSWORD"):
    os.environ.pop(name, None)
from spa.preflight import unresolved_env_message
print(unresolved_env_message({
    "splunk_defaults": {"splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"},
    "splunk_idxclusters": [{"idxc_password": "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"}],
    "splunk_shclusters": [{"shc_password": "{{ lookup('env', 'SPLUNK_SHC_PASSWORD') }}"}],
}))
"""
    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(LIB),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=child_env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == documented
    assert "SPLUNK_ADMIN_PASSWORD" in _walkthrough()
    assert "SPLUNKBASE_USERNAME" in _walkthrough()
    assert "SPLUNKBASE_PASSWORD" in _walkthrough()


def test_walkthrough_replay_builds_the_clustered_config(tmp_path):
    text = _walkthrough()
    script_parts = ["set -euo pipefail"]
    for block in _fences(text):
        if "fragments/shs.yml" in block and "--resolve" not in block:
            script_parts.append('cp config/splunk_config.yml "$SNAPSHOT"')
            script_parts.append(block)
            script_parts.append('cmp -s config/splunk_config.yml "$SNAPSHOT"')
        else:
            script_parts.append(block)
    script = "\n".join(script_parts)
    script = script.replace(
        "spa init --example cm_2idxc1site_3shc_uf --provider aws ./itsi-lab",
        "spa init --example cm_2idxc1site_3shc_uf --provider aws --skip-doctor ./itsi-lab",
    )
    script = re.sub(r"(?m)^spa ", "%s " % _SPA, script)
    software = seed_software_dir(tmp_path / "data")
    (software / "Splunk_Enterprise.lic").write_text("walkthrough-license-placeholder\n", encoding="utf-8")
    (software / "Splunk_ITSI.lic").write_text("walkthrough-license-placeholder\n", encoding="utf-8")
    (software / "splunk-9.3.1-1-linux-amd64.tgz").write_bytes(b"")
    (software / "splunkforwarder-9.3.1-1-linux-amd64.tgz").write_bytes(b"")
    stub = PROJECT_ROOT / "tests" / "splunkbase_http_stub"
    env = spa_env(
        {
            "SPA_VENV_DIR": str(PROJECT_ROOT / "tests" / ".venv"),
            "SPA_SOFTWARE_DIR": str(software),
            "SPA_BASECONFIG_DIR": str(software),
            "SPA_TEST_SPLUNKBASE_STUB": "1",
            "PYTHONPATH": os.pathsep.join([str(stub), str(LIB)]),
            "SNAPSHOT": str(tmp_path / "before-shs.yml"),
            "SPLUNK_ADMIN_PASSWORD": "walkthrough-admin",
            "SPLUNK_IDXC_PASSWORD": "walkthrough-idxc",
            "SPLUNK_SHC_PASSWORD": "walkthrough-shc",
            "SPLUNKBASE_USERNAME": "walkthrough-user",
            "SPLUNKBASE_PASSWORD": "walkthrough-splunkbase",
        }
    )
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    combined = result.stdout + result.stderr
    assert "itsi.search_tier" in combined
    assert "Java" in combined or "java" in combined
    assert "license" in combined.lower()
    config_path = tmp_path / "itsi-lab" / "config" / "splunk_config.yml"
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "Splunk Add-on for Unix and Linux" in combined
    assert loaded["splunk_defaults"]["splunk_license_file"] == [
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
    ]
    aws = loaded["terraform"]["aws"]
    assert aws["region"] == "eu-central-1"
    assert aws["ami_id"] == "ami-0f5fb818aeff8f5fb"
    assert aws["key_name"] == "aws_key"
    assert aws["security_group_names"] == ["Splunk_Basic"]
    assert aws["instance_type"] == "t3.medium"
    assert aws["root_volume_size"] == 50
    assert aws["root_volume_type"] == "gp3"
    hosts = loaded["splunk_hosts"]
    by_name = {host["name"]: host for host in hosts if host.get("name")}
    by_prefix = {
        host["iter"]["prefix"]: host for host in hosts if isinstance(host.get("iter"), dict)
    }
    assert set(by_name) == {"cm", "uf", "shs", "lm"}
    assert set(by_prefix) == {"idx", "sh"}
    for prefix in ("idx", "sh"):
        sized = by_prefix[prefix]["terraform"]["aws"]
        assert "ami_id" not in sized
        assert sized["instance_type"] == "c5.4xlarge"
    for name in ("cm", "uf", "lm", "shs"):
        assert "terraform" not in by_name[name]
    assert "license_manager" not in by_name["cm"]["roles"]
    assert by_name["lm"]["roles"] == [
        "license_manager",
        "deployment_server",
        "deployer",
    ]
    assert by_name["lm"]["shcluster"] == "shc1"
    assert by_name["cm"]["roles"] == ["cluster_manager", "monitoring_console"]
    assert "shcluster" not in by_name["cm"]
    text = config_path.read_text(encoding="utf-8")
    assert re.search(r"- name: lm\n\s+roles:", text)
    assert "java-21-openjdk" in by_prefix["sh"]["os"]["packages"]
    assert "java-21-openjdk" in by_name["shs"]["os"]["packages"]
    apps = loaded["splunk_app_deployment"]["apps"]
    itsi = next(app for app in apps if app.get("app_id") == 1841)
    library = next(app for app in apps if app.get("app_id") == 5391)
    forwarder = next(app for app in apps if app.get("app_id") == 833)
    assert itsi["shc_whitelist"] == ["shc1"]
    assert [pack["name"] for pack in library["content_pack_apps"]] == [
        "DA-ITSI-CP-nix",
        "DA-ITSI-CP-windows",
    ]
    packs = {pack["name"]: pack for pack in library["content_pack_apps"]}
    assert packs["DA-ITSI-CP-nix"]["customizations"] == {
        "run_playbook_after_restart": "ansible/apps_playbooks/DA-ITSI-CP-nix_configure.yml",
        "force_run_playbook_after_restart": False,
    }
    assert packs["DA-ITSI-CP-windows"]["customizations"] == {
        "run_playbook_after_restart": "ansible/apps_playbooks/DA-ITSI-CP-windows_configure.yml",
        "force_run_playbook_after_restart": False,
    }
    by_app_id = {app["app_id"]: app for app in apps}
    assert by_app_id[2882]["target_roles"] == ["search_head"]
    assert by_app_id[2890]["target_roles"] == ["search_head"]
    assert by_app_id[2890]["customizations"] == {
        "run_playbook": "ansible/apps_playbooks/Splunk_ML_Toolkit-configure.yml"
    }
    assert by_app_id[1621]["target_roles"] == ["search_head"]
    assert forwarder["target_roles"] == ["universal_forwarder"]
    assert forwarder["customizations"]["run_playbook"] == (
        "ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml"
    )
    assert forwarder["customizations"]["extra_vars"]["ta_nix_script_index"] == (
        "itsi_im_metrics"
    )
    defaults = loaded["splunk_defaults"]
    assert defaults["splunk_download"] == {"splunk": True, "splunkforwarder": True}
    assert defaults["splunk_set_servername"] is True
    assert defaults["splunk_set_default_hostname"] is True
    assert defaults["splunk_loginpage_print_userpw"] is False
    assert defaults["splunk_ssl"]["web"]["enable"] is True
    assert defaults["splunk_ssl"]["inputs"]["enable"] is True
    assert defaults["splunk_ssl"]["outputs"]["enable"] is True
    assert defaults["splunk_admin_password"] == (
        "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
    )
    assert "walkthrough-admin" not in config_path.read_text(encoding="utf-8")
    plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
    sys.path.insert(0, str(plugin))
    from schema import validate_config

    validate_config(loaded)
