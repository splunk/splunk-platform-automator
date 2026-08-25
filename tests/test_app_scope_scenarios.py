"""
Scenario-based tests for app scope (debug_app_scope.yml).

Runs debug_app_scope.yml with run_scope_locally=true per scenario config,
then asserts on the produced scope_debug.json. No SSH or real hosts required.

Scenarios live under tests/configs/app_scope/<name>/splunk_config.yml.

Requires: ansible-playbook on PATH (or ANSIBLE_PLAYBOOK), Python deps from tests/requirements.txt (pytest, PyYAML).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.local


def _ansible_playbook_executable() -> str:
    """Path to ansible-playbook (ANSIBLE_PLAYBOOK env overrides PATH lookup)."""
    override = (os.environ.get("ANSIBLE_PLAYBOOK") or "").strip()
    if override:
        return override
    found = shutil.which("ansible-playbook")
    if not found:
        pytest.fail(
            "ansible-playbook not found on PATH. Install Ansible on the controller, or set ANSIBLE_PLAYBOOK "
            "to the full path. App scope tests shell out to debug_app_scope.yml."
        )
    return found

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
    assert_deployers_entry,
    assert_direct_on_scope,
    assert_ds_app_count,
    assert_ds_app_target_hosts,
    assert_ds_same_app_twice,
    get_app_on_direct_for_host,
    _first_deployer,
    _first_deployment_server,
)


def _project_root() -> Path:
    """Repository root (parent of tests/)."""
    return Path(__file__).resolve().parent.parent


def _scenarios_dir() -> Path:
    return _project_root() / "tests" / "configs" / "app_scope"


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
        _ansible_playbook_executable(),
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


def _expected_scope_path(scenario_name: str) -> Path:
    """Path to expected scope snapshot for this scenario (inside scenario directory)."""
    return _scenarios_dir() / scenario_name / "expected_scope.json"


def _normalize_scope(obj: dict | list) -> dict | list:
    """Normalize scope JSON for stable comparison: sort dict keys; sort lists of dicts by a canonical key."""
    if isinstance(obj, dict):
        return {k: _normalize_scope(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        if not obj:
            return obj
        first = obj[0]
        if isinstance(first, dict):
            # Sort list of dicts by first available of host, app, name (for stable order)
            key_attr = None
            for candidate in ("host", "app", "name"):
                if all(candidate in x for x in obj):
                    key_attr = candidate
                    break
            if key_attr is not None:
                obj = sorted(obj, key=lambda x: (x.get(key_attr), json.dumps(x, sort_keys=True)))
            return [_normalize_scope(x) for x in obj]
        if isinstance(first, str):
            return sorted(obj)
        return [_normalize_scope(x) for x in obj]
    return obj


def _scenarios_with_expected_snapshot():
    """Scenario names that have expected_scope.json in their scenario directory."""
    names = []
    for scenario_name in _collect_scenario_names():
        if (_scenarios_dir() / scenario_name / "expected_scope.json").is_file():
            names.append(scenario_name)
    return sorted(names)


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
        deployer = _first_deployer(scope)
        assert (deployer.get("apps") or []) == [] or deployer.get("host") is None
        ds = _first_deployment_server(scope)
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
    elif scenario_name == "ds_same_app_twice":
        # Same app (Splunk_TA_nix) twice: one serverclass for search_head, one for universal_forwarder.
        assert_ds_app_count(scope, 2)
        assert_ds_same_app_twice(scope, "Splunk_TA_nix", [["sh"], ["uf"]])
    elif scenario_name == "itsi_content_pack":
        # ITSI and content pack plus search_head-only apps (ML_Toolkit, Scientific_Python) go via deployer when all SHs are in SHC.
        assert_deployer_apps(
            scope,
            [
                "Splunk IT Service Intelligence",
                "DA-ITSI-ContentLibrary",
                "Splunk_ML_Toolkit",
                "Splunk_SA_Scientific_Python_linux_x86_64",
            ],
        )
        assert_deployer_has_app_with_config(
            scope, "DA-ITSI-ContentLibrary", state="installed", has_content_pack_apps=True
        )
        assert_deployer_target_hosts(scope, ["sh1", "sh2", "sh3"])
        # Search_head-only apps must not be on deployment_server; they are deployed from deployer only.
        ds_apps = [e["app"] for e in _first_deployment_server(scope).get("apps_with_targets") or []]
        for wrong_on_ds in ["Splunk_ML_Toolkit", "Splunk_SA_Scientific_Python_linux_x86_64"]:
            assert wrong_on_ds not in ds_apps, (
                f"App {wrong_on_ds!r} must not be on deployment_server when all search heads are in SHC (deployer only)"
            )
        assert_ds_app_target_hosts(scope, "Splunk_TA_nix", ["uf"])
    elif scenario_name == "deployer_shc_whitelist":
        # Two deployers: ds (shc1) gets MyApp only; ds2 (shc2) gets MyOtherApp only.
        assert_deployer_apps(scope, ["MyApp"])  # first deployer (ds)
        deployer = _first_deployer(scope)
        actual = set((deployer.get("target_hosts") or []))
        for h in ["sh1", "sh2", "sh3"]:
            assert h in actual, f"deployer.target_hosts should include shc1 member {h!r}, got {sorted(actual)}"
        deployer_list = scope.get("deployer") or []
        assert len(deployer_list) == 2, f"deployer: expected 2 entries, got {len(deployer_list)}"
        assert_deployers_entry(scope, "ds", ["MyApp"], ["sh1", "sh2", "sh3"])
        assert_deployers_entry(scope, "ds2", ["MyOtherApp"], ["sh4", "sh5", "sh6"])
    elif scenario_name == "deployer_standalone_sh_only":
            deployer_apps = _first_deployer(scope).get("apps") or []
            assert "StandaloneOnlyApp" not in deployer_apps, (
                f"StandaloneOnlyApp should not be on deployer (direct-only), got deployer.apps={deployer_apps}"
            )
            # App is deployed via DS to standalone_sh (DS has it with target_hosts [standalone_sh])
            assert_ds_app_target_hosts(scope, "StandaloneOnlyApp", ["standalone_sh"])
    elif scenario_name == "cm_idxc":
        assert_cluster_manager_apps(scope, ["IndexerApp"])
        assert_cluster_manager_target_hosts(scope, ["idx1", "idx2"])
    elif scenario_name == "itsi_shc":
        assert_deployer_apps(scope, ["Splunk IT Service Intelligence"])
        assert_deployer_target_hosts(scope, ["sh1", "sh2", "sh3"])
    elif scenario_name == "itsi_content_pack_single_app":
        # Single-app CP (no content_pack_apps); routes via direct on standalone SH with ITSI.
        assert_direct_on_scope(scope, "itsi", "Splunk IT Service Intelligence", True)
        assert_direct_on_scope(scope, "itsi", "DA-ITSI-CP-CUST-ATLAS-AWS-EBS", True)
        cp_entry = get_app_on_direct_for_host(scope, "itsi", "DA-ITSI-CP-CUST-ATLAS-AWS-EBS")
        assert cp_entry is not None
        assert cp_entry.get("content_pack_apps") in (None, [])
        deployer_apps = _first_deployer(scope).get("apps") or []
        assert "DA-ITSI-CP-CUST-ATLAS-AWS-EBS" not in deployer_apps
    elif scenario_name == "itsi_standalone_sh":
        # Single host is named "itsi" (search_head + indexer + license_manager), no SHC; ITSI and content pack via direct.
        assert_direct_on_scope(scope, "itsi", "Splunk IT Service Intelligence", True)
        assert_direct_on_scope(scope, "itsi", "DA-ITSI-ContentLibrary", True)
        deployer_apps = _first_deployer(scope).get("apps") or []
        assert "Splunk IT Service Intelligence" not in deployer_apps, (
            "ITSI should be direct-only when no SHC; deployer.apps should not list ITSI"
        )
    elif scenario_name == "idx_filters":
        # SingleIndexerApp: hosts_whitelist [idx] -> direct to idx only, not on CM
        assert_direct_on_scope(scope, "idx", "SingleIndexerApp", True)
        # IndexerClusterApp: idxc_whitelist [idxc1] -> on CM only, targets idx1, idx2
        assert_cluster_manager_apps(scope, ["IndexerClusterApp"])
        assert_cluster_manager_target_hosts(scope, ["idx1", "idx2"])
        cm_list = scope.get("cluster_manager") or []
        if cm_list:
            apps = cm_list[0].get("apps") or []
            assert "SingleIndexerApp" not in apps, (
                "SingleIndexerApp targets only standalone indexer idx via hosts_whitelist; must not be on CM"
            )
    elif scenario_name == "mixed_filters":
        assert_ds_app_target_hosts(scope, "AppViaDS", ["uf1"])
        assert_cluster_manager_apps(scope, ["AppOnIndexers"])
        assert_cluster_manager_target_hosts(scope, ["idx1", "idx2"])
        assert_deployer_apps(scope, ["AppOnShc1Only"])
        # Playbook outputs all SHC members in deployer.target_hosts; AppOnShc1Only targets shc1 only (shc_blacklist shc2).
        deployer = _first_deployer(scope)
        actual = set((deployer.get("target_hosts") or []))
        for h in ["sh1", "sh2", "sh3"]:
            assert h in actual, f"deployer.target_hosts should include shc1 member {h!r}, got {sorted(actual)}"
    elif scenario_name == "itsi_multi_shc":
        # Deployer (ds→shc1): ITSI, Content Packs, ML_Toolkit, cisco_meraki, Splunk_TA_nix (SH)
        assert_deployers_entry(
            scope, "ds",
            ["Splunk IT Service Intelligence", "DA-ITSI-ContentLibrary",
             "Splunk_ML_Toolkit", "Splunk_TA_cisco_meraki", "Splunk_TA_nix"],
            ["sh1", "sh2", "sh3"],
        )
        assert_deployer_has_app_with_config(
            scope, "DA-ITSI-ContentLibrary", state="installed", has_content_pack_apps=True
        )
        # Deployer (ds2→shc2): no apps (all shc_whitelist filter to shc1)
        assert_deployers_entry(scope, "ds2", [], ["sh4", "sh5", "sh6"])
        # CM gets ITSI + multi-role indexer portion + idxc_whitelist app
        assert_cluster_manager_apps(
            scope, ["Splunk IT Service Intelligence", "Splunk_TA_cisco_meraki", "org_all_hec_inputs"]
        )
        assert_cluster_manager_target_hosts(scope, ["idx1", "idx2"])
        # DS routes Splunk_TA_nix (UF) only
        assert_ds_app_count(scope, 1)
        assert_ds_app_target_hosts(scope, "Splunk_TA_nix", ["uf"])
        # Direct: splunk_ta_sim on hf via deployment_target + hosts_whitelist
        assert_direct_on_scope(scope, "hf", "splunk_ta_sim", True)
        # Direct: ITSI on ds (license_manager gets ITSI direct)
        assert_direct_on_scope(scope, "ds", "Splunk IT Service Intelligence", True)
    else:
        # Generic: at least structure present (all three are lists)
        assert "direct_scope" in scope
        assert isinstance(scope.get("deployer"), list)
        assert isinstance(scope.get("cluster_manager"), list)
        assert isinstance(scope.get("deployment_server"), list)


@pytest.mark.parametrize("scenario_name", _scenarios_with_expected_snapshot())
def test_scenario_scope_matches_snapshot(scenario_name: str):
    """When <scenario>/expected_scope.json exists, actual scope must match the snapshot.

    Expected file lives in each scenario directory (e.g. minimal_direct/expected_scope.json).
    Normalization (sorted keys, sorted lists by host/app) keeps the diff stable.
    To update snapshots after intentional changes:
      UPDATE_SCOPE_SNAPSHOTS=1 pytest tests/test_app_scope_scenarios.py -k snapshot
    """
    out_dir = _scenarios_dir() / "output"
    scope_path = out_dir / f"{scenario_name}_scope.json"
    if not scope_path.is_file():
        out_dir.mkdir(parents=True, exist_ok=True)
        result = _run_scope_playbook(scenario_name, scope_path)
        assert result.returncode == 0, (
            f"debug_app_scope.yml failed for scenario {scenario_name!r}"
        )
    actual = _load_scope_output(scope_path)
    expected_path = _expected_scope_path(scenario_name)
    assert expected_path.is_file(), f"Expected snapshot missing: {expected_path}"

    update_snapshots = os.environ.get("UPDATE_SCOPE_SNAPSHOTS", "").strip() in ("1", "true", "yes")
    norm_actual = _normalize_scope(actual)
    if update_snapshots:
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        with open(expected_path, "w", encoding="utf-8") as f:
            json.dump(norm_actual, f, indent=4, sort_keys=False)  # already normalized
        # After write, loaded expected will match
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)
    norm_expected = _normalize_scope(expected) if not update_snapshots else norm_actual

    if norm_actual != norm_expected:
        # Produce a readable diff (key-by-key or short summary)
        actual_str = json.dumps(norm_actual, indent=2, sort_keys=True)
        expected_str = json.dumps(norm_expected, indent=2, sort_keys=True)
        msg = (
            f"Scope output for scenario {scenario_name!r} does not match expected snapshot.\n"
            f"Expected file: {expected_path}\n"
            "Review the diff below. If the change is intentional, run:\n"
            "  UPDATE_SCOPE_SNAPSHOTS=1 pytest tests/test_app_scope_scenarios.py -k snapshot\n"
            "to update the expected snapshot.\n\n"
            f"--- expected\n+++ actual\n"
        )
        # Simple line diff for readability (optional: use difflib)
        from difflib import unified_diff
        diff = unified_diff(
            expected_str.splitlines(),
            actual_str.splitlines(),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
        msg += "\n".join(diff)
        assert False, msg
