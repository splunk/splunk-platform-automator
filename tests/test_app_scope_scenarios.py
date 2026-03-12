"""
Scenario-based tests for app scope (debug_app_scope.yml).

Runs debug_app_scope.yml with run_scope_locally=true per scenario config,
then asserts on the produced scope_debug.json. No SSH or real hosts required.

Scenarios live under tests/scenarios/app_scope/<name>/splunk_config.yml.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Allow importing scope_assertions when running pytest from project root
_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))
from scope_assertions import (
    assert_cluster_manager_apps,
    assert_cluster_manager_target_hosts,
    assert_deployer_apps,
    assert_deployer_has_app_with_config,
    assert_deployer_target_hosts,
    assert_direct_on_scope,
    assert_ds_app_count,
    assert_ds_app_target_hosts,
    get_app_on_direct_for_host,
)


def _project_root() -> Path:
    """Repository root (parent of tests/)."""
    return Path(__file__).resolve().parent.parent


def _scenarios_dir() -> Path:
    return _project_root() / "tests" / "scenarios" / "app_scope"


def _collect_scenario_names():
    """Discover scenario names (subdirs of app_scope that contain splunk_config.yml)."""
    base = _scenarios_dir()
    if not base.is_dir():
        return []
    names = []
    for p in base.iterdir():
        if p.is_dir() and (p / "splunk_config.yml").is_file():
            names.append(p.name)
    return sorted(names)


def _run_scope_playbook(scenario_name: str, scope_output_path: Path) -> subprocess.CompletedProcess:
    """Run debug_app_scope.yml with -i <scenario_config> -e run_scope_locally=true etc."""
    root = _project_root()
    playbook = root / "ansible" / "verification" / "debug_app_scope.yml"
    config_path = _scenarios_dir() / scenario_name / "splunk_config.yml"
    assert config_path.is_file(), f"Scenario config missing: {config_path}"
    # Use workspace-local temp dirs so Ansible does not need ~/.ansible/tmp (fails in sandbox/CI).
    # ANSIBLE_LOCAL_TEMP = controller-side tmp; ANSIBLE_REMOTE_TEMP = remote/host tmp (used for localhost too).
    out_dir = scope_output_path.parent
    ansible_tmp = out_dir / ".ansible_tmp"
    ansible_tmp.mkdir(parents=True, exist_ok=True)
    remote_tmp = ansible_tmp / "remote"
    remote_tmp.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ansible-playbook",
        str(playbook),
        "-i", str(config_path),
        "-e", "run_scope_locally=true",
        "-e", f"scope_output_path={scope_output_path}",
        "-e", "assert_scope_invariants=true",
    ]
    env = {
        **os.environ,
        "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
        "ANSIBLE_LOCAL_TEMP": str(ansible_tmp),
        "ANSIBLE_REMOTE_TEMP": str(remote_tmp),
    }
    result = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if result.returncode != 0:
        print(f"\n--- debug_app_scope.yml (scenario={scenario_name}) FAILED ---")
        print("STDOUT:", result.stdout[-4000:] if len(result.stdout) > 4000 else result.stdout)
        print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
    return result


def _load_scope_output(scope_output_path: Path) -> dict:
    """Load and parse scope_debug JSON."""
    with open(scope_output_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("scenario_name", _collect_scenario_names())
def test_scenario_scope_playbook_succeeds(scenario_name: str):
    """Run debug_app_scope for the scenario and assert playbook succeeds."""
    root = _project_root()
    out_dir = _scenarios_dir() / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    scope_path = out_dir / f"{scenario_name}_scope.json"
    result = _run_scope_playbook(scenario_name, scope_path)
    assert result.returncode == 0, (
        f"debug_app_scope.yml failed for scenario {scenario_name!r}"
    )
    assert scope_path.is_file(), f"Scope output not written: {scope_path}"


@pytest.mark.parametrize("scenario_name", _collect_scenario_names())
def test_scenario_scope_assertions(scenario_name: str):
    """Run scope playbook (if needed), load JSON, run scenario-specific assertions."""
    root = _project_root()
    out_dir = _scenarios_dir() / "output"
    scope_path = out_dir / f"{scenario_name}_scope.json"
    if not scope_path.is_file():
        out_dir.mkdir(parents=True, exist_ok=True)
        result = _run_scope_playbook(scenario_name, scope_path)
        assert result.returncode == 0, (
            f"debug_app_scope.yml failed for scenario {scenario_name!r}; run test_scenario_scope_playbook_succeeds first"
        )
    scope = _load_scope_output(scope_path)

    # Scenario-specific assertions
    if scenario_name == "minimal_direct":
        assert_direct_on_scope(scope, "sh", "org_some_local_app", True)
        deployer = scope.get("deployer") or {}
        assert (deployer.get("apps") or []) == [] or deployer.get("host") is None
        ds = scope.get("deployment_server") or {}
        assert len(ds.get("apps_with_targets") or []) == 0 or ds.get("host") is None
    elif scenario_name == "ds_only":
        assert_ds_app_count(scope, 1)
        assert_ds_app_target_hosts(scope, "Splunk_TA_nix", ["sh", "uf"])
    elif scenario_name == "deployer_shc":
        assert_deployer_apps(scope, ["Splunk_TA_nix"])
        assert_deployer_target_hosts(scope, ["sh1", "sh2", "sh3"])
        assert_deployer_has_app_with_config(scope, "Splunk_TA_nix", state="installed", has_content_pack_apps=False)
    elif scenario_name == "state_absent":
        assert_direct_on_scope(scope, "sh", "org_old_app", True)
        entry = get_app_on_direct_for_host(scope, "sh", "org_old_app")
        assert entry is not None and entry.get("state") == "absent"
    elif scenario_name == "ds_with_hosts_whitelist":
        assert_ds_app_count(scope, 1)
        assert_ds_app_target_hosts(scope, "Splunk_TA_nix", ["sh1"])
    elif scenario_name == "itsi_content_pack":
        assert_deployer_apps(scope, ["Splunk IT Service Intelligence", "Splunk App for Content Packs"])
        assert_deployer_has_app_with_config(
            scope, "Splunk App for Content Packs", state="installed", has_content_pack_apps=True
        )
        assert_deployer_target_hosts(scope, ["sh1", "sh2", "sh3"])
    else:
        # Generic: at least structure present
        assert "direct_scope" in scope
        assert isinstance(scope.get("deployer"), dict)
        assert isinstance(scope.get("cluster_manager"), dict)
        assert isinstance(scope.get("deployment_server"), dict)
