"""ITSI content pack unit tests: role wiring and config defaults.

Schema validation for single-app and multi-app bundles lives in test_schema.py (TestAppDeploymentConfig).
Scope/routing scenarios live in test_app_scope_scenarios.py (itsi_content_pack*, itsi_standalone_sh).
"""

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.local, pytest.mark.itsi]


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TASKS = REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/main.yml"
REMOVE_TASKS = REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/cp_remove.yml"
DEFAULTS = REPO_ROOT / "ansible/roles/apps_itsi_content_pack/defaults/main.yml"
PROCESS_DIRECT_APP = REPO_ROOT / "ansible/roles/apps_direct/tasks/process_direct_app.yml"
APPLY_ITSI = REPO_ROOT / "ansible/roles/apps_direct/tasks/process_direct_app_apply_itsi.yml"
APPLY_CP = REPO_ROOT / "ansible/roles/apps_direct/tasks/process_direct_app_apply_content_pack.yml"
APPLY_STANDARD = REPO_ROOT / "ansible/roles/apps_direct/tasks/process_direct_app_apply_standard.yml"
VERIFY_YML = REPO_ROOT / "ansible/roles/apps_direct/tasks/verify.yml"
VERIFY_CP_WRAPPER = REPO_ROOT / "ansible/roles/apps_direct/tasks/verify_content_pack_app_dirs.yml"
VERIFY_CP_DIRS = REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/verify_app_dirs.yml"
VERIFY_CP_SINGLE = REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/verify_single_dir.yml"
ITSI_LM_INSTALL = REPO_ROOT / "ansible/roles/apps_itsi/tasks/itsi_install_license_manager.yml"


def _load_tasks(path: Path) -> list:
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    assert isinstance(doc, list)
    return doc


def _task_names(tasks: list) -> list[str]:
    names: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if "name" in task:
            names.append(task["name"])
        for block_key in ("block", "rescue", "always"):
            nested = task.get(block_key)
            if isinstance(nested, list):
                names.extend(_task_names(nested))
    return names


class TestItsiContentPackRoleWiring:
    """Static checks on apps_itsi_content_pack role tasks and defaults."""

    def test_single_app_synthesis_tasks_present(self):
        names = _task_names(_load_tasks(MAIN_TASKS))
        assert "Synthesize single-app content pack from top-level name and options" in names
        assert "Build effective app list for content pack (selected apps)" in names
        assert "Synthesize standalone content pack apps from archive app name(s)" not in names
        assert "Register post-restart configure playbook for standalone content pack (direct deployment)" not in names

    def test_content_pack_install_default_true_in_defaults(self):
        content = DEFAULTS.read_text(encoding="utf-8")
        assert "cp_content_pack_install_default: true" in content

    def test_multi_app_content_pack_install_uses_role_default(self):
        content = MAIN_TASKS.read_text(encoding="utf-8")
        assert "cp_content_pack_install_default" in content
        assert "default(cp_content_pack_install_default)" in content
        multi_block = content.split("content_pack_install")[1].split("Register post-restart API install")[0]
        assert "default(false)" not in multi_block

    def test_single_app_and_remove_use_unified_app_lists(self):
        main_content = MAIN_TASKS.read_text(encoding="utf-8")
        remove_content = REMOVE_TASKS.read_text(encoding="utf-8")
        assert "cp_single_app_mode" in main_content
        assert "cp_standalone_mode" not in main_content
        assert "cp_effective_app_list" in main_content
        assert "app_item.name" in main_content
        assert "cp_library_app" not in main_content
        assert "cp_remove_list" in remove_content
        assert "cp_single_app_mode" in remove_content
        assert "cp_library_app" not in remove_content

    def test_selected_apps_unarchive_uses_dereference_extra_opts(self):
        main_content = MAIN_TASKS.read_text(encoding="utf-8")
        assert "--dereference" in main_content
        assert "--add-file" not in main_content

    def test_version_check_resets_accumulators_per_run(self):
        names = _task_names(_load_tasks(REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/cp_version_check.yml"))
        assert "Reset content pack version check accumulators" in names

    def test_direct_app_apply_tasks_split_by_app_kind(self):
        content = PROCESS_DIRECT_APP.read_text(encoding="utf-8")
        assert "_direct_app_apply_tasks" in content
        assert "process_direct_app_apply_itsi.yml" in content
        assert "process_direct_app_apply_content_pack.yml" in content
        assert "process_direct_app_apply_standard.yml" in content
        assert "premium pack" not in content.lower()
        assert APPLY_ITSI.is_file()
        assert APPLY_CP.is_file()
        assert APPLY_STANDARD.is_file()
        itsi_apply = APPLY_ITSI.read_text(encoding="utf-8")
        cp_apply = APPLY_CP.read_text(encoding="utf-8")
        assert "(premium app ITSI)" in itsi_apply
        assert "(ITSI content pack)" in cp_apply
        assert "premium pack" not in itsi_apply.lower()
        assert "(premium app ITSI)" not in cp_apply

    def test_direct_verify_routes_single_and_multi_app_cp(self):
        verify_playbook = REPO_ROOT / "ansible/verification/verify_app_deployment.yml"
        verify_text = verify_playbook.read_text(encoding="utf-8")
        direct_verify = VERIFY_YML.read_text(encoding="utf-8")
        cp_wrapper = VERIFY_CP_WRAPPER.read_text(encoding="utf-8")
        cp_dirs = VERIFY_CP_DIRS.read_text(encoding="utf-8")
        assert "build_content_pack_verify_index.yml" not in verify_text
        assert "verify_content_pack_app_dirs.yml" in direct_verify
        assert "verify_app_dirs.yml" in cp_wrapper
        assert "_is_single_app_cp" in direct_verify
        assert "verify_single_app.yml" in direct_verify
        assert "verify_premium_app.yml" in direct_verify
        assert "_cpv_fs_dirs" in cp_dirs
        assert VERIFY_CP_SINGLE.is_file()
        assert "_cp_verify_index" not in cp_dirs
        assert not (REPO_ROOT / "ansible/roles/apps_common/tasks/build_content_pack_verify_index.yml").exists()
        assert not (REPO_ROOT / "ansible/roles/apps_common/tasks/resolve_content_pack_verify_fs_dirs.yml").exists()


class TestItsiLicenseManagerRestart:
    """License manager must restart after ITSI license apps before content-pack API."""

    def test_license_manager_flushes_restart_after_unarchive(self):
        tasks = _load_tasks(ITSI_LM_INSTALL)
        names = [task.get("name") for task in tasks if isinstance(task, dict)]
        unarchive_idx = names.index("Transfer and unarchive ITSI license apps to etc/apps")
        flag_idx = names.index(
            "Set app_path and restart flag so license manager Restart splunk handler runs"
        )
        flush_idx = names.index(
            "Flush handlers so license manager restarts after ITSI license apps"
        )
        assert unarchive_idx < flag_idx < flush_idx
        unarchive = tasks[unarchive_idx]
        assert unarchive.get("notify") == "Restart splunk"
        flag = tasks[flag_idx]
        assert flag["ansible.builtin.set_fact"]["restart_splunk_direct_etc_apps"] is True
        assert flag["ansible.builtin.set_fact"]["app_path"] == "{{ splunk_home }}/etc/apps"
        assert tasks[flush_idx].get("ansible.builtin.meta") == "flush_handlers"
        wait_names = names[flush_idx:]
        assert "Wait for splunkd port after license manager restart" in wait_names
        assert "Wait for splunkd full service after license manager restart" in wait_names


class TestItsiContentPackSuiteStateWait:
    """ITSI 5+ content-pack POST requires suite_state before install."""

    def test_cp_api_install_waits_for_suite_state_before_refresh(self):
        tasks = _load_tasks(REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/cp_api_install.yml")
        names = [task.get("name") for task in tasks if isinstance(task, dict)]
        wait_idx = names.index(
            "Wait until ITSI suite_state is plus (or pre-ITSI 404) before content pack API"
        )
        fail_idx = names.index("Fail if ITSI suite_state is still undefined")
        refresh_idx = names.index("Refresh content pack registry ({{ app_name }})")
        post_idx = names.index(
            "Install content pack ({{ app_name }}) via ITSI API (POST) (post-restart)"
        )
        assert wait_idx < fail_idx < refresh_idx < post_idx
        wait = tasks[wait_idx]
        assert "itsi_feature_flagging_state/suite_state" in wait["ansible.builtin.uri"]["url"]
        assert wait.get("retries") == 90
        assert wait.get("delay") == 10
        until = wait.get("until") or ""
        assert "plus" in until
        assert "404" in until

    def test_cp_api_install_post_timeout_covers_large_packs(self):
        tasks = _load_tasks(REPO_ROOT / "ansible/roles/apps_itsi_content_pack/tasks/cp_api_install.yml")
        post = next(
            task
            for task in tasks
            if task.get("name")
            == "Install content pack ({{ app_name }}) via ITSI API (POST) (post-restart)"
        )
        timeout = post["ansible.builtin.uri"]["timeout"]
        assert "default(600)" in timeout
        assert "default(300)" not in timeout


class TestItsiContentPackBackupRestoreWait:
    """Configure POSTs must wait out ITSI backup/restore lock (SI-BR_0001)."""

    def test_deploy_waits_for_backup_jobs_before_configure(self):
        content = (REPO_ROOT / "ansible/splunk_apps_deploy.yml").read_text(encoding="utf-8")
        assert "Wait until ITSI backup/restore jobs are idle before configure playbooks" in content
        assert "backup_restore_interface/backup_restore" in content
        api_idx = content.index("Run cp_api_install (content pack API install) for each app")
        wait_idx = content.index(
            "Wait until ITSI backup/restore jobs are idle before configure playbooks"
        )
        cfg_idx = content.index("Run run_playbook_after_restart (configure) for app")
        assert api_idx < wait_idx < cfg_idx

    def test_enable_services_retries_backup_restore_lock(self):
        for rel in (
            "ansible/apps_playbooks/DA-ITSI-CP-nix_configure.yml",
            "ansible/apps_playbooks/DA-ITSI-CP-windows_configure.yml",
            "ansible/apps_playbooks/DA-ITSI-CP-monitoring-alerting_configure.yml",
        ):
            tasks = _load_tasks(REPO_ROOT / rel)
            enable = next(task for task in tasks if task.get("name") == "Enable Services")
            assert enable.get("retries") == 30
            assert enable.get("delay") == 10
            assert "SI-BR_0001" in (enable.get("until") or "")
