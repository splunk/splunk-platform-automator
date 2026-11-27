"""Static checks for the apps_es premium-app role.

Pipeline wiring (apps_direct / apps_deployer / apps_cluster_manager) is Slice 3.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.local]


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE = REPO_ROOT / "ansible/roles/apps_es"
DEFAULTS = ROLE / "defaults/main.yml"
MAIN_TASKS = ROLE / "tasks/main.yml"
INSTALL_SH = ROLE / "tasks/es_install_search_head.yml"
INSTALL_DEPLOYER = ROLE / "tasks/es_install_deployer.yml"
INSTALL_INDEXER = ROLE / "tasks/es_install_indexer.yml"
INSTALL_LM = ROLE / "tasks/es_install_license_manager.yml"
VERIFY = ROLE / "tasks/verify_premium_es.yml"
RESOLVE = ROLE / "tasks/verify_resolve_es_archive_names.yml"
REMOVE_SH = ROLE / "tasks/es_remove_search_head.yml"
ITSI_VERIFY = REPO_ROOT / "ansible/roles/apps_itsi/tasks/verify_premium_app.yml"


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


def _when_text(task: dict) -> str:
    when = task.get("when")
    if when is None:
        return ""
    if isinstance(when, list):
        return " ".join(str(item) for item in when)
    return str(when)


def _iter_tasks(tasks: list, parent_whens: tuple[str, ...] = ()):
    for task in tasks:
        if not isinstance(task, dict):
            continue
        when = _when_text(task)
        whens = parent_whens + ((when,) if when else ())
        yield task, whens
        for key in ("block", "rescue", "always"):
            nested = task.get(key)
            if isinstance(nested, list):
                yield from _iter_tasks(nested, whens)


def _include_tasks_file(task: dict) -> str:
    include = task.get("ansible.builtin.include_tasks") or task.get("include_tasks") or ""
    if isinstance(include, dict):
        return str(include.get("file") or "")
    return str(include)


def _include_role_tasks_from(task: dict) -> str:
    role = task.get("ansible.builtin.include_role") or task.get("include_role") or {}
    if isinstance(role, dict):
        return str(role.get("tasks_from") or "")
    return ""


def _role_text() -> str:
    parts: list[str] = []
    for path in sorted(ROLE.rglob("*")):
        if path.is_file() and path.suffix in {".yml", ".yaml", ".j2"}:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _command_argv(task: dict) -> list[str]:
    cmd = task.get("ansible.builtin.command") or task.get("command") or {}
    if isinstance(cmd, dict):
        argv = cmd.get("argv")
        if isinstance(argv, list):
            return [str(item) for item in argv]
    return []


def _update_needed_whens(whens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(when for when in whens if "apps_es_update_needed" in when)


def _install_app_and_essinstall(path: Path):
    """(task, parent_whens, argv) triples for splunk install app and | essinstall."""
    install: list[tuple] = []
    essinstall: list[tuple] = []
    for task, whens in _iter_tasks(_load_tasks(path)):
        argv = _command_argv(task)
        name = str(task.get("name") or "")
        if "install" in argv and "app" in argv:
            install.append((task, whens, argv))
        if name.startswith("Run essinstall"):
            essinstall.append((task, whens, argv))
    return install, essinstall


def _assert_install_app_update_shares_essinstall_block(path: Path):
    """splunk install app -update 1 lives in the same apps_es_update_needed block as essinstall."""
    install, essinstall = _install_app_and_essinstall(path)
    assert install, path.name
    assert essinstall, path.name
    for _task, whens, argv in install:
        assert "-update" in argv, path.name
        idx = argv.index("-update")
        assert idx + 1 < len(argv) and argv[idx + 1] == "1", path.name
        install_block = _update_needed_whens(whens)
        assert install_block, path.name
        for _ess, ess_whens, _ess_argv in essinstall:
            assert _update_needed_whens(ess_whens) == install_block, path.name
    return install, essinstall


class TestEsRoleWiring:
    """Standing checks on apps_es task order, essinstall, SSL, indexes, and verify."""

    def test_role_layout_exists(self):
        assert (ROLE / "meta/main.yml").is_file()
        assert DEFAULTS.is_file()
        assert MAIN_TASKS.is_file()
        assert INSTALL_SH.is_file()
        assert INSTALL_DEPLOYER.is_file()
        assert INSTALL_INDEXER.is_file()
        assert VERIFY.is_file()
        assert VERIFY.name != ITSI_VERIFY.name
        assert VERIFY.name == "verify_premium_es.yml"

    def test_defaults_use_splunkbase_263_and_skip_java_and_lm_apps(self):
        content = DEFAULTS.read_text(encoding="utf-8")
        assert "es_splunkbase_app_id: 263" in content
        assert "java-21" not in content
        assert "java 21" not in content.lower()
        defaults = yaml.safe_load(content)
        assert defaults["es_lm_apps"] == []
        assert defaults["es_indexes_app"] == "spa_es_indexes"
        assert defaults["es_shc_limits_app"] == "spa_es_shc_limits"

    def test_search_head_uses_install_app_then_essinstall_not_unarchive(self):
        content = INSTALL_SH.read_text(encoding="utf-8")
        names = _task_names(_load_tasks(INSTALL_SH))
        assert any("install app" in name.lower() for name in names)
        assert any("essinstall" in name.lower() for name in names)
        assert "essinstall" in content
        assert "--deployment_type search_head" in content
        assert "ansible.builtin.unarchive" not in content
        assert "-auth" in content
        _assert_install_app_update_shares_essinstall_block(INSTALL_SH)

    def test_essinstall_stamp_before_essinstall_in_update_needed_block(self):
        """SPA records the target clock immediately before | essinstall so verify can scope the log."""
        for path in (INSTALL_SH, INSTALL_DEPLOYER):
            walked = list(_iter_tasks(_load_tasks(path)))
            stamp_idx = next(
                i
                for i, (task, _whens) in enumerate(walked)
                if "es_essinstall_started" in yaml.dump(task)
            )
            ess_idx = next(
                i
                for i, (task, _whens) in enumerate(walked)
                if str(task.get("name") or "").startswith("Run essinstall")
            )
            assert stamp_idx < ess_idx, path.name
            _stamp_task, stamp_whens = walked[stamp_idx]
            assert any("apps_es_update_needed" in when for when in stamp_whens), path.name
            blob = yaml.dump(walked[stamp_idx][0])
            assert "date '+%Y-%m-%d %H:%M:%S'" in blob or "%Y-%m-%d %H:%M:%S" in blob
            assert "var/run/spa" in blob

    def test_deployer_raises_limits_pushes_spa_es_shc_limits_then_essinstall(self):
        content = INSTALL_DEPLOYER.read_text(encoding="utf-8")
        names = _task_names(_load_tasks(INSTALL_DEPLOYER))
        assert "max_upload_size" in content
        assert "max_content_length" in content
        assert "splunkdConnectionTimeout" in content
        assert "spa_es_shc_limits" in content
        assert "Push shcluster bundle" in content
        assert "flush_handlers" in content
        assert "essinstall" in content
        assert "--deployment_type shc_deployer" in content
        assert "ansible.builtin.unarchive" not in content

        limits_idx = next(i for i, name in enumerate(names) if name.startswith("Stage spa_es_shc_limits"))
        flush_idx = next(i for i, name in enumerate(names) if name.startswith("Flush handlers so SHC members"))
        ess_idx = next(i for i, name in enumerate(names) if name.startswith("Run essinstall"))
        assert limits_idx < flush_idx < ess_idx
        _install, essinstall = _assert_install_app_update_shares_essinstall_block(INSTALL_DEPLOYER)
        for task, _whens, _argv in essinstall:
            notify = task.get("notify")
            if isinstance(notify, list):
                assert "Push shcluster bundle" in notify
            else:
                assert notify == "Push shcluster bundle"

    def test_ssl_enablement_omits_strict_and_passes_ignore(self):
        files = [
            INSTALL_SH.read_text(encoding="utf-8"),
            INSTALL_DEPLOYER.read_text(encoding="utf-8"),
        ]
        combined = "\n".join(files)
        assert "ssl_enablement" in combined
        assert "splunk_ssl.web.enable" in combined
        assert "--ssl_enablement ignore" in combined
        assert "strict" in combined

    def test_indexer_writes_spa_es_indexes_not_bundled_tas(self):
        content = INSTALL_INDEXER.read_text(encoding="utf-8")
        assert "spa_es_indexes" in content
        assert "apps_es_indexer_apps_base" in content
        assert "apps_es_indexer_notify" in content
        assert "Apply indexer cluster bundle" in MAIN_TASKS.read_text(encoding="utf-8") or "apps_es_indexer_notify" in MAIN_TASKS.read_text(encoding="utf-8")
        assert "TA-" not in content or "not" in content.lower()
        assert "ansible.builtin.unarchive" not in content
        assert "SA-" in content or "DA-" in content or "indexes.conf" in content
        assert "Ensure spa_es_indexes work dir" in content
        assert "when: not ((splunk_app_deployment.target_download" not in content

    def test_standalone_indexer_overlay_runs_on_combined_search_head(self):
        """Combined SH+indexer (single-node) must still write spa_es_indexes; Slice 2 skip is download-only."""
        standalone = next(
            task
            for task, _whens in _iter_tasks(_load_tasks(MAIN_TASKS))
            if _include_tasks_file(task) == "es_install_indexer.yml"
            and "standalone indexer" in str(task.get("name") or "").lower()
        )
        when = _when_text(standalone)
        assert "role_indexer" in when
        assert "idxcluster_" in when
        assert "role_search_head" not in when
        assert "role_cluster_manager" not in when

    def test_indexer_work_dir_becomes_root_when_target_download(self):
        """Deploy creates /tmp/splunk_apps/ES as root; become:false cannot mkdir spa_es_indexes_* there."""
        content = INSTALL_INDEXER.read_text(encoding="utf-8")
        for marker in (
            "Ensure spa_es_indexes work dir",
            "Merge nested SA-/DA- indexes.conf from ES archive",
            "Overlay volume paths and write spa_es_indexes app.conf",
        ):
            chunk = content.split(marker, 1)[1].split("- name:", 1)[0]
            assert "target_download" in chunk, marker
            assert "become: false" not in chunk, marker

    def test_main_does_not_unarchive_suite_onto_role_paths(self):
        main = MAIN_TASKS.read_text(encoding="utf-8")
        assert "es_install_search_head.yml" in main
        assert "es_install_deployer.yml" in main
        assert "es_install_indexer.yml" in main
        assert "ansible.builtin.unarchive" not in main
        assert "download_splunkbase_archive.yml" in main
        assert "app_id | default(es_splunkbase_app_id)" in main or "es_splunkbase_app_id" in main

    def test_java_21_not_required(self):
        assert MAIN_TASKS.is_file()
        text = _role_text()
        assert text
        assert "java-21" not in text
        assert "openjdk-21" not in text

    def test_removal_deletes_suite_and_spa_owned_apps(self):
        remove_sh = REMOVE_SH.read_text(encoding="utf-8")
        assert "spa_es_shc_limits" in remove_sh
        assert "etc/system/local/server.conf" in remove_sh
        assert "es_essinstall_started" in remove_sh
        assert "state: absent" in remove_sh
        indexer_remove = (ROLE / "tasks/es_remove_indexer.yml").read_text(encoding="utf-8")
        assert "spa_es_indexes" in indexer_remove

    def test_verify_uses_distinct_task_file_and_spa_owned_apps(self):
        content = VERIFY.read_text(encoding="utf-8")
        assert "spa_es_indexes" in content
        assert "spa_es_shc_limits" in content
        assert "verify_premium_app.yml" not in content
        names = _task_names(_load_tasks(VERIFY))
        assert names

    def test_license_manager_skips_extra_apps_when_list_empty(self):
        content = INSTALL_LM.read_text(encoding="utf-8")
        assert "es_lm_apps" in content
        assert "when:" in content

    def test_verify_resolve_temp_dir_does_not_require_apps_common_defaults(self):
        """verify_es includes this file without apps_common defaults (Ansible 2.19)."""
        assert RESOLVE.is_file()
        content = RESOLVE.read_text(encoding="utf-8")
        assert "splunk_app_deployment_defaults" not in content
        assert "default('/tmp/splunk_apps')" in content

    def test_verify_resolve_keeps_nested_app_conf_paths(self):
        """ES 8.x lists SA-/DA- under SplunkEnterpriseSecuritySuite, not as top-level names."""
        content = RESOLVE.read_text(encoding="utf-8")
        assert "list_es_archive_inventory.py" in content
        assert "all_apps" in content
        assert "_es_archive_app_names" in content

    def test_verify_resolve_skips_indexer_ta(self):
        """essinstall omits Splunk_TA_ForIndexers from search-tier layout."""
        content = RESOLVE.read_text(encoding="utf-8")
        assert "Splunk_TA_ForIndexers" in content
        assert "reject('in', _skip)" in content

    def test_verify_resolve_skips_wrong_os_scientific_python(self):
        """essinstall on Linux omits Windows Scientific Python (and the reverse on Windows)."""
        content = RESOLVE.read_text(encoding="utf-8")
        assert "Splunk_SA_Scientific_Python_windows_x86_64" in content
        assert "Splunk_SA_Scientific_Python_linux_x86_64" in content
        assert "ansible_system" in content
        assert "reject('in', _skip)" in content

    def test_deployer_fallback_writes_member_system_local_then_rolling_restart(self):
        """Slice 7 stage 3: bundle-delivered [httpServer] does not take effect on members."""
        content = INSTALL_DEPLOYER.read_text(encoding="utf-8")
        names = _task_names(_load_tasks(INSTALL_DEPLOYER))
        assert "etc/system/local/server.conf" in content
        assert "delegate_to" in content
        assert "Initiate SHC rolling restart" in content
        flush_idx = next(i for i, name in enumerate(names) if name.startswith("Flush handlers so SHC members"))
        fallback_idx = next(
            i for i, name in enumerate(names) if name.startswith("Raise max_content_length on ES SHC members")
        )
        ess_idx = next(i for i, name in enumerate(names) if name.startswith("Run essinstall"))
        assert flush_idx < fallback_idx < ess_idx

    def test_indexer_lists_nested_sa_da_indexes_conf(self):
        content = INSTALL_INDEXER.read_text(encoding="utf-8")
        assert "list_es_archive_inventory.py" in content
        assert "--merged-indexes-conf" in content
        assert "tar tzf" not in content

    def test_splunkbase_download_merges_defaults_before_api_url(self):
        """verify_es include_role download skips apps_common main.yml; Ansible 2.19
        rejects splunk_app_deployment.splunkbase_api_url unless defaults are merged."""
        path = REPO_ROOT / "ansible/roles/apps_common/tasks/download_splunkbase_archive.yml"
        content = path.read_text(encoding="utf-8")
        merge_idx = content.find("combine(splunk_app_deployment")
        target_idx = content.find("download_splunkbase_archive_target.yml")
        controller_idx = content.find("download_splunkbase_archive_controller.yml")
        assert merge_idx != -1
        assert "splunk_app_deployment_defaults" in content
        assert 0 <= merge_idx < min(i for i in (target_idx, controller_idx) if i != -1)

    def test_target_splunkbase_download_reuses_existing_archive(self):
        """A version-stamped archive already on disk is reused so verify does not
        rewrite a root-owned /tmp/splunk_apps cache. Missing-file mkdir/get_url
        still become root (first deploy or a cold verify)."""
        path = REPO_ROOT / "ansible/roles/apps_common/tasks/download_splunkbase_archive_target.yml"
        tasks = [task for task in _load_tasks(path) if isinstance(task, dict)]
        by_name = {task.get("name"): task for task in tasks if task.get("name")}
        skip_when = "not _splunkbase_target_archive_stat.stat.exists"

        stat_tasks = [
            task for task in tasks if isinstance(task.get("ansible.builtin.stat"), dict)
        ]
        assert len(stat_tasks) == 1
        stat_task = stat_tasks[0]
        assert stat_task["ansible.builtin.stat"].get("path") == "{{ splunkbase_archive_path }}"
        assert stat_task.get("register") == "_splunkbase_target_archive_stat"
        mkdir_idx = next(
            i for i, task in enumerate(tasks) if task.get("name") == "Create app cache directory (target)"
        )
        assert tasks.index(stat_task) < mkdir_idx

        create = by_name["Create app cache directory (target)"]
        auth = by_name["Authenticate with Splunkbase (target)"]
        token = by_name["Set Splunkbase auth token (target)"]
        download = by_name["Download app from Splunkbase (target)"]
        dest_fact = by_name["Set archive path from download result (target)"]
        for task in (create, auth, token, download):
            assert skip_when in _when_text(task), task.get("name")
        assert create.get("become") is True
        assert download.get("become") is True
        assert "splunkbase_download_result.dest is defined" in _when_text(dest_fact)

    def test_controller_splunkbase_download_reuses_existing_archive(self):
        """A version-stamped archive already on the controller is reused so
        deploy/verify does not re-authenticate or re-fetch from Splunkbase."""
        path = REPO_ROOT / "ansible/roles/apps_common/tasks/download_splunkbase_archive_controller.yml"
        tasks = [task for task in _load_tasks(path) if isinstance(task, dict)]
        by_name = {task.get("name"): task for task in tasks if task.get("name")}
        skip_when = "not _splunkbase_controller_archive_stat.stat.exists"

        stat_tasks = [
            task for task in tasks if isinstance(task.get("ansible.builtin.stat"), dict)
        ]
        assert len(stat_tasks) == 1
        stat_task = stat_tasks[0]
        assert stat_task["ansible.builtin.stat"].get("path") == "{{ splunkbase_archive_path }}"
        assert stat_task.get("register") == "_splunkbase_controller_archive_stat"
        mkdir_idx = next(
            i for i, task in enumerate(tasks) if task.get("name") == "Create app cache directory (controller)"
        )
        assert tasks.index(stat_task) < mkdir_idx

        create = by_name["Create app cache directory (controller)"]
        auth = by_name["Authenticate with Splunkbase (controller)"]
        token = by_name["Set Splunkbase auth token (controller)"]
        download = by_name["Download app from Splunkbase (controller)"]
        dest_fact = by_name["Set archive path from download result (controller)"]
        for task in (create, auth, token, download):
            assert skip_when in _when_text(task), task.get("name")
        for task in (stat_task, create, auth, token, download, dest_fact):
            assert task.get("delegate_to") == "localhost", task.get("name")
            assert task.get("run_once") is True, task.get("name")
        for task in (stat_task, create, auth, download):
            assert task.get("become") is False, task.get("name")
        assert "splunkbase_download_result.dest is defined" in _when_text(dest_fact)

    def test_app_conf_app_names_needed_never_includes_indexes_app(self):
        """spa_es_indexes is SPA-built; the ES archive cache must not be asked for it."""
        tasks = [task for task in _load_tasks(MAIN_TASKS) if isinstance(task, dict)]
        needed = [
            task
            for task in tasks
            if isinstance(task.get("ansible.builtin.set_fact"), dict)
            and "app_conf_app_names_needed" in task["ansible.builtin.set_fact"]
        ]
        assert needed
        for task in needed:
            value = str(task["ansible.builtin.set_fact"]["app_conf_app_names_needed"])
            assert "es_indexes_app" not in value
            assert "spa_es_indexes" not in value
            assert "not _es_skip_app_conf_cache" in _when_text(task)
            assert "es_lm_apps" in value

    def test_target_app_conf_cache_skipped_for_spa_owned_or_empty_lm(self):
        """CM-only and empty-LM hosts skip archive app.conf extract; expected versions
        are {} there instead of defaulting an unset cache fact. Controller capture
        does not propagate unused es_app_conf_app_names."""
        tasks = [task for task in _load_tasks(MAIN_TASKS) if isinstance(task, dict)]
        skip_tasks = [
            task
            for task in tasks
            if isinstance(task.get("ansible.builtin.set_fact"), dict)
            and "_es_skip_app_conf_cache" in task["ansible.builtin.set_fact"]
        ]
        assert len(skip_tasks) == 1
        skip_expr = str(skip_tasks[0]["ansible.builtin.set_fact"]["_es_skip_app_conf_cache"])
        assert "target_download" in skip_expr
        assert "role_cluster_manager" in skip_expr
        assert "role_license_manager" in skip_expr
        assert "es_lm_apps" in skip_expr
        assert "length" in skip_expr
        assert "_es_skip_splunkbase_download" in skip_expr

        cache = next(
            task
            for task in tasks
            if task.get("name") == "Ensure app conf cache and expected versions (common, target_download)"
        )
        cache_when = _when_text(cache)
        assert "not _es_skip_app_conf_cache" in cache_when
        assert "target_download" in cache_when

        expected = next(
            task
            for task in tasks
            if task.get("name") == "Set ES expected versions and app names from common cache"
        )
        assert "not _es_skip_app_conf_cache" in _when_text(expected)
        expected_facts = expected["ansible.builtin.set_fact"]
        assert "es_app_conf_app_names" not in expected_facts
        exp_versions = str(expected.get("vars", {}).get("_exp_versions", expected_facts.get("apps_es_expected_versions", "")))
        assert "(app_conf_expected_versions | default({}))" not in exp_versions
        assert "(app_conf_app_names | default([]))" not in str(expected)

        empty = [
            task
            for task in tasks
            if isinstance(task.get("ansible.builtin.set_fact"), dict)
            and task["ansible.builtin.set_fact"].get("apps_es_expected_versions") == {}
        ]
        assert empty
        for task in empty:
            assert "_es_skip_app_conf_cache" in _when_text(task)
            assert "es_app_conf_app_names" not in task["ansible.builtin.set_fact"]

        captures = [
            nested
            for task in tasks
            if isinstance(task, dict)
            for nested in (task.get("block") or [])
            if isinstance(nested, dict)
            and nested.get("name") == "Capture app conf cache result on localhost for propagation"
        ]
        assert len(captures) == 1
        capture_facts = captures[0]["ansible.builtin.set_fact"]
        assert "es_app_conf_expected_versions" in capture_facts
        assert "es_app_conf_app_names" not in capture_facts

    def test_indexer_sets_spa_es_indexes_expected_version_before_version_check(self):
        """SPA writes version = apps_es_resolved_version into spa_es_indexes app.conf."""
        tasks = [task for task in _load_tasks(INSTALL_INDEXER) if isinstance(task, dict)]
        names = _task_names(tasks)
        check_idx = names.index("Check existing ES indexes app version on indexer")
        combine = [
            task
            for task in tasks
            if isinstance(task.get("ansible.builtin.set_fact"), dict)
            and "apps_es_resolved_version" in str(task["ansible.builtin.set_fact"].get("apps_es_expected_versions", ""))
            and "es_indexes_app" in str(task["ansible.builtin.set_fact"].get("apps_es_expected_versions", ""))
        ]
        assert combine
        assert names.index(combine[0]["name"]) < check_idx
        assert "es_version_check.yml" in INSTALL_INDEXER.read_text(encoding="utf-8")

    def test_indexer_only_skips_es_splunkbase_get_url_when_indexes_current(self):
        """CM/standalone-indexer target_download hosts version-check spa_es_indexes
        before the ES Splunkbase get_url so a current indexes app skips the .spl
        fetch. Search heads and deployer still need the archive for essinstall.
        A skipped .spl also skips app.conf extract so a missing archive is not
        unpacked. Verify archive resolve is not gated on that skip.
        """
        walked = list(_iter_tasks(_load_tasks(MAIN_TASKS)))

        def _is_indexes_version_check(task: dict) -> bool:
            if task.get("block") or task.get("rescue") or task.get("always"):
                return False
            name = str(task.get("name") or "").lower()
            include = _include_tasks_file(task)
            facts = task.get("ansible.builtin.set_fact") or {}
            return (
                "es_version_check.yml" in include
                or "es_check_indexer_version.yml" in include
                or "indexes app version" in name
                or (
                    isinstance(facts, dict)
                    and "apps_es_version_check_apps" in facts
                    and "es_indexes_app" in str(facts.get("apps_es_version_check_apps", ""))
                )
            )

        check_idx = next(
            (i for i, (task, _) in enumerate(walked) if _is_indexes_version_check(task)),
            None,
        )
        resolve_idx = next(
            (
                i
                for i, (task, _) in enumerate(walked)
                if "resolve_splunkbase_version.yml" in _include_role_tasks_from(task)
            ),
            None,
        )
        download_idx = next(
            (
                i
                for i, (task, _) in enumerate(walked)
                if _include_role_tasks_from(task) == "download_splunkbase_archive.yml"
            ),
            None,
        )
        assert check_idx is not None, "indexer-only spa_es_indexes version check must live in main.yml"
        assert resolve_idx is not None, "indexer-only path must resolve Splunkbase version without the archive"
        assert download_idx is not None
        assert resolve_idx < check_idx < download_idx

        _, download_whens = walked[download_idx]
        download_when = " ".join(download_whens)
        assert "_es_skip_splunkbase_download" in download_when or "apps_es_update_needed" in download_when
        skip_facts = [
            task
            for task, _ in walked
            if isinstance(task.get("ansible.builtin.set_fact"), dict)
            and any(
                "apps_es_update_needed" in str(value) and "skip" in str(key).lower()
                for key, value in task["ansible.builtin.set_fact"].items()
            )
        ]
        skip_from_update = "apps_es_update_needed" in download_when or bool(skip_facts)
        if skip_facts:
            skip_when = " ".join(_when_text(task) for task in skip_facts)
            skip_from_update = skip_from_update or "apps_es_update_needed" in skip_when
            for task in skip_facts:
                value = " ".join(str(v) for v in task["ansible.builtin.set_fact"].values())
                assert "apps_es_update_needed" in value
        assert skip_from_update, "ES Splunkbase get_url must be skipped when apps_es_update_needed is false"

        skip_cache = next(
            task
            for task, _ in walked
            if isinstance(task.get("ansible.builtin.set_fact"), dict)
            and "_es_skip_app_conf_cache" in task["ansible.builtin.set_fact"]
        )
        skip_cache_expr = str(skip_cache["ansible.builtin.set_fact"]["_es_skip_app_conf_cache"])
        assert "_es_skip_splunkbase_download" in skip_cache_expr

        indexer_only_when = " ".join(
            " ".join(whens)
            for task, whens in walked
            if _is_indexes_version_check(task)
        )
        assert "target_download" in indexer_only_when
        assert "role_cluster_manager" in indexer_only_when
        assert "role_indexer" in indexer_only_when
        assert "role_search_head" in indexer_only_when
        assert "role_deployer" in indexer_only_when
        assert "idxcluster_" in indexer_only_when

        sh = INSTALL_SH.read_text(encoding="utf-8")
        deployer = INSTALL_DEPLOYER.read_text(encoding="utf-8")
        assert "apps_es_spl_path" in sh
        assert "apps_es_install_package" in sh
        assert "apps_es_spl_path" in deployer
        assert "apps_es_install_package" in deployer

        verify_tasks = list(_iter_tasks(_load_tasks(RESOLVE)))
        verify_download = next(
            task
            for task, _ in verify_tasks
            if _include_role_tasks_from(task) == "download_splunkbase_archive.yml"
        )
        verify_when = " ".join(
            " ".join(whens)
            for task, whens in verify_tasks
            if task is verify_download
        )
        assert "apps_es_update_needed" not in verify_when
        assert "_es_skip_splunkbase_download" not in verify_when

        target_path = REPO_ROOT / "ansible/roles/apps_common/tasks/download_splunkbase_archive_target.yml"
        get_url = next(
            task
            for task in _load_tasks(target_path)
            if isinstance(task, dict) and task.get("name") == "Download app from Splunkbase (target)"
        )
        get_url_when = _when_text(get_url)
        if "_splunkbase_skip_download" in get_url_when:
            assert "default(false)" in get_url_when
        else:
            assert "apps_es_update_needed" not in get_url_when
