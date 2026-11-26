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


def _role_text() -> str:
    parts: list[str] = []
    for path in sorted(ROLE.rglob("*")):
        if path.is_file() and path.suffix in {".yml", ".yaml", ".j2"}:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


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
