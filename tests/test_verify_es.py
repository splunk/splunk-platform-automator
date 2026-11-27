"""Static contract for ansible/verification/verify_es.yml (premium_app: es health)."""

from __future__ import annotations

import importlib.util
import tarfile
from pathlib import Path

import pytest
import yaml

from spa.playbooks import catalog, parse_playbook_metadata
from spa.paths import resolve_spa_paths
from spa_testutil import PROJECT_ROOT

pytestmark = [pytest.mark.local]


PLAYBOOK = PROJECT_ROOT / "ansible/verification/verify_es.yml"
README = PROJECT_ROOT / "ansible/verification/README.md"
LIVE_SUITE = PROJECT_ROOT / "tests/test_verification.py"
LIVE_DEPLOYMENT = PROJECT_ROOT / "tests/test_deployment.py"
APPS_ES_DEFAULTS = PROJECT_ROOT / "ansible/roles/apps_es/defaults/main.yml"
RESOLVE = PROJECT_ROOT / "ansible/roles/apps_es/tasks/verify_resolve_es_archive_names.yml"

CHECK_ENDPOINTS = (
    ("/services/apps/local", "installer / suite apps"),
    ("essinstaller2.log", "installer log"),
    ("/services/kvstore/status", "KV store"),
    ("/services/data/indexes", "indexes on search peers"),
    ("enableSplunkWebSSL", "SSL mode"),
    ("/services/licenser/", "ES license"),
    ("max_content_length", "upload limits"),
    ("correlationsearch", "correlation searches"),
    ("suite_configured", "suite configured"),
    ("/services/configs/conf-indexes", "index volume overlay"),
    ("/services/messages", "ES messages"),
    ("splunkbase_newer", "newer Splunkbase release"),
)


def _walk_tasks(node, ancestors_no_log=False):
    if isinstance(node, list):
        for item in node:
            yield from _walk_tasks(item, ancestors_no_log)
        return
    if not isinstance(node, dict):
        return
    no_log = ancestors_no_log or node.get("no_log") is True
    yield node, no_log
    for key in ("block", "rescue", "always"):
        yield from _walk_tasks(node.get(key) or [], no_log)


def _plays_and_tasks():
    plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8")) or []
    tasks = []
    for play in plays:
        if isinstance(play, dict):
            tasks.extend(_walk_tasks(play.get("tasks") or []))
    return plays, tasks


def _uri_spec(task):
    return task.get("ansible.builtin.uri") or task.get("uri")


def _task_sends_credentials(task, spec):
    blob = yaml.dump(task)
    if spec is None:
        return "password" in blob and ("user:" in blob or "user" in str(task))
    if spec.get("user") or spec.get("password"):
        return True
    headers = spec.get("headers") or {}
    return any("authorization" in str(key).lower() for key in headers)


def _is_correlation_task(task):
    blob = yaml.dump(task).lower()
    name = str(task.get("name", "")).lower()
    return "correlation" in name or "correlationsearch" in blob


def _is_license_task(task, spec):
    name = str(task.get("name", "")).lower()
    url = str((spec or {}).get("url", "")).lower()
    return "licenser" in url or "licenser" in name


class TestVerifyEsPlaybook:
    """Standing static checks for the read-only ES health playbook."""

    def test_playbook_exists_with_read_only_header(self):
        assert PLAYBOOK.is_file()
        meta = parse_playbook_metadata(PLAYBOOK)
        assert meta is not None
        assert meta["schema"] == 1
        assert meta["category"] == "verification"
        assert meta["risk"] == "read-only"
        assert meta["requires_provisioned"] is True
        description = (meta.get("description") or "").lower()
        assert "install" in description
        assert "running" in description
        assert "upgrade" in description
        examples = meta.get("examples") or []
        assert examples
        joined = "\n".join(examples)
        assert "-v" not in joined
        assert "--yes" not in joined
        assert "fail_on_mismatch=true" in joined

    def test_catalog_lists_verification_verify_es(self):
        rows = catalog(resolve_spa_paths(start_dir=str(PROJECT_ROOT)))
        names = [row["name"] for row in rows]
        assert "verification/verify_es" in names
        row = next(item for item in rows if item["name"] == "verification/verify_es")
        assert row["missing"] is False
        assert row["risk"] == "read-only"
        assert row.get("requires_confirmation") is False

    def test_skips_when_no_installed_premium_app_es(self):
        _plays, tasks = _plays_and_tasks()
        end_play = [
            task
            for task, _no_log in tasks
            if (task.get("ansible.builtin.meta") or task.get("meta")) == "end_play"
        ]
        assert end_play, "expected meta: end_play when no installed premium_app: es"
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "premium_app" in text
        assert "es" in text

    def test_reuses_slice2_archive_resolver_and_upload_limit(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "verify_resolve_es_archive_names.yml" in text
        defaults = yaml.safe_load(APPS_ES_DEFAULTS.read_text(encoding="utf-8"))
        assert str(defaults["es_shc_max_content_length"]) == "5000000000"
        assert "es_shc_max_content_length" in text or "5000000000" in text

    def test_latest_row_pins_archive_to_deployed_version(self):
        """A latest/unset row resolves the archive at the deployed ES version, not live latest."""
        playbook = PLAYBOOK.read_text(encoding="utf-8")
        resolve = RESOLVE.read_text(encoding="utf-8")
        assert "spa_es_indexes" in playbook or "es_indexes_app" in playbook
        assert "etc/manager-apps" in playbook
        assert "etc/shcluster/apps" in playbook
        assert "verify_es_archive_version" in resolve
        assert "verify_es_archive_version" in playbook
        download_vars = resolve.split("Set Splunkbase vars for ES verify archive resolution", 1)[1]
        assert "verify_es_archive_version" in download_vars.split("Download ES archive", 1)[0]
        assert "verify_app_item.version" in resolve

    def test_check_endpoints_present(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        for needle, label in CHECK_ENDPOINTS:
            assert needle in text, label

    def test_uri_tasks_that_send_credentials_have_no_log(self):
        _plays, tasks = _plays_and_tasks()
        uri_tasks = [
            (task, _uri_spec(task), no_log)
            for task, no_log in tasks
            if _uri_spec(task) is not None
        ]
        assert uri_tasks, "expected uri tasks for REST checks"
        credentialed = [
            (task, spec, no_log)
            for task, spec, no_log in uri_tasks
            if _task_sends_credentials(task, spec)
        ]
        assert credentialed, "expected uri tasks that send user/password"
        for task, _spec, no_log in credentialed:
            assert no_log is True, task.get("name")

    def test_no_auth_flag_on_command_lines(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "-auth" not in text
        _plays, tasks = _plays_and_tasks()
        includes = [
            task.get("ansible.builtin.include_role") or task.get("include_role")
            for task, _no_log in tasks
        ]
        assert not any(
            inc
            and (
                (isinstance(inc, dict) and inc.get("tasks_from") == "splunk_rest")
                or "splunk_rest" in str(inc)
            )
            for inc in includes
        ), "splunk_rest helper has no no_log; use uri with no_log"

    def test_license_check_never_registers_or_prints_response_body(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "licenser" in text
        _plays, tasks = _plays_and_tasks()
        license_tasks = [
            (task, spec, no_log)
            for task, no_log in tasks
            for spec in [_uri_spec(task)]
            if _is_license_task(task, spec)
        ]
        assert license_tasks, "expected an ES license check"
        debug_blobs = [
            yaml.dump(task)
            for task, _no_log in tasks
            if task.get("ansible.builtin.debug") or task.get("debug")
        ]
        license_registers = []
        for task, spec, no_log in license_tasks:
            assert no_log is True, task.get("name")
            dump = yaml.dump(task)
            assert "ansible.builtin.debug" not in dump
            register = task.get("register")
            if register:
                license_registers.append(str(register))
                assert str(register).startswith("_"), register
        fail_tasks = [
            task
            for task, _no_log in tasks
            if task.get("ansible.builtin.fail") or task.get("fail")
        ]
        printed = "\n".join(debug_blobs + [yaml.dump(task) for task in fail_tasks])
        for register in license_registers:
            assert register not in printed
        # Summary / exported fact is present/absent only.
        assert "present" in text and "absent" in text
        fail_msgs = " ".join(
            str((task.get("ansible.builtin.fail") or task.get("fail") or {}).get("msg", ""))
            for task in fail_tasks
        )
        assert "<?xml" not in fail_msgs
        assert "license.xml" not in text.lower()

    def test_failing_checks_respect_fail_on_mismatch_info_checks_never_fail(self):
        """Failing set is 1-7, 9, 10; info set is 8, 11, 12."""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "fail_on_mismatch" in text
        assert "Checks 1-7, 9, 10 reported no mismatches" in text
        assert "Checks 1-7 reported no mismatches" not in text
        _plays, tasks = _plays_and_tasks()
        fail_tasks = [
            task
            for task, _no_log in tasks
            if task.get("ansible.builtin.fail") or task.get("fail")
        ]
        assert fail_tasks, "expected a fail task gated on fail_on_mismatch"
        assert any("fail_on_mismatch" in str(task.get("when")) for task in fail_tasks)
        corr = [task for task, _no_log in tasks if _is_correlation_task(task)]
        assert corr, "expected informational correlation-search check"
        info_names = ("correlation", "messages", "splunkbase_newer")
        info_tasks = [
            task
            for task, _no_log in tasks
            if any(name in str(task.get("name", "")).lower() or name in yaml.dump(task).lower() for name in info_names)
            and (task.get("ansible.builtin.set_fact") or task.get("ansible.builtin.uri") or task.get("uri"))
        ]
        assert info_tasks
        for task in info_tasks:
            dump = yaml.dump(task)
            assert "ansible.builtin.fail" not in dump
            assert "ansible.builtin.assert" not in dump
            spec = _uri_spec(task)
            if spec is not None:
                assert task.get("failed_when") is False or "failed_when: false" in dump
        for task in fail_tasks:
            when = str(task.get("when"))
            dump = yaml.dump(task)
            assert "correlation" not in when.lower()
            assert "check 8" not in dump.lower()
            assert "check 11" not in dump.lower()
            assert "check 12" not in dump.lower()

    def test_readme_documents_verify_es(self):
        text = README.read_text(encoding="utf-8")
        assert "verify_es.yml" in text
        assert "fail_on_mismatch" in text
        section = text.split("verify_es.yml", 1)[1].split("###", 1)[0]
        assert "-v" not in section
        assert "install" in section.lower()
        assert "running" in section.lower()
        assert "upgrade" in section.lower()
        assert "suite_configured" in section or "configured" in section.lower()
        assert "overlay" in section.lower()
        assert "1-7, 9, 10" in section or "checks 1-7, 9, 10" in section.lower()

    def test_apps_md_names_verification_verify_es(self):
        apps = (PROJECT_ROOT / "docs/apps.md").read_text(encoding="utf-8")
        verify = apps.split("## Verify and troubleshoot", 1)[1]
        assert "verification/verify_es" in verify.split("## ", 1)[0]

    def test_live_suite_skips_when_no_installed_es(self):
        for path, func_name in (
            (LIVE_SUITE, "def test_08_verify_es"),
            (LIVE_DEPLOYMENT, "def test_11_verify_es"),
        ):
            text = path.read_text(encoding="utf-8")
            assert func_name in text
            assert "premium_app" in text
            assert "verification/verify_es" in text
            assert "pytest.skip" in text
            assert "fail_on_mismatch=true" in text

    def test_archive_inventory_runs_on_target_download_host(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "list_es_archive_inventory.py" in text
        assert "re.match(r\"(SA-|DA-)" not in text
        assert "delegate_to: localhost" not in text.split("Extract expected ES")[1].split("- name:")[0]
        extract = text.split("Extract expected ES")[1].split("- name:")[0]
        assert "target_download" in extract
        assert "_es_archive_app_conf_paths" in text
        assert "^(?:.*/)?([^/]+)/default/app" in text

    def test_suite_apps_canonicalizes_versioned_names_and_allows_disabled_sa_ueba(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert r"[-_]\d+\.\d+.*$" in text or r"[-_]\\d+\\.\\d+.*$" in text
        assert "reject('equalto', 'SA-UEBA')" in text
        assert "_disabled_mismatch_apps" in text

    def test_shc_members_do_not_require_essinstaller_log(self):
        """essinstall runs on the deployer; members have the suite via the bundle."""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "verify_es_is_shc" in text.split("Record installer and suite-app findings", 1)[1].split("- name:", 1)[0]
        assert "log=N/A (SHC member)" in text
        assert "Scan essinstaller2.log for ERROR lines on deployer" in text

    def test_messages_and_splunkbase_newer_are_informational(self):
        """Checks 11 and 12 never fail; messages filter ES/essinstall/restart noise."""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "/services/messages" in text
        assert "splunkbase_newer" in text
        assert "resolve_splunkbase_version.yml" in text
        _plays, tasks = _plays_and_tasks()
        info_tasks = [
            task
            for task, _no_log in tasks
            if "messages" in str(task.get("name", "")).lower()
            or "splunkbase_newer" in yaml.dump(task)
            or "splunkbase latest" in str(task.get("name", "")).lower()
        ]
        assert info_tasks, "expected informational messages / splunkbase_newer tasks"
        for task in info_tasks:
            dump = yaml.dump(task)
            if task.get("ansible.builtin.fail") or task.get("fail"):
                raise AssertionError(task.get("name"))
            spec = _uri_spec(task)
            if spec is not None:
                assert task.get("failed_when") is False or "failed_when: false" in dump
            if "status:" in dump or "'status'" in dump:
                assert "info" in dump
                assert "mismatch" not in dump.split("status")[1][:80]

    def test_index_volume_overlay_on_peers_not_cm(self):
        """Check 10 compares peer REST homePath/coldPath to SPA overlay prefixes from the pinned archive."""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "index_volume_overlay" in text
        assert "/services/configs/conf-indexes" in text
        assert "splunk_server=*" in text
        assert "--merged-indexes-conf" in text
        assert "es_index_home_path" in text
        assert "es_index_cold_path" in text
        assert "volume:" in text
        overlay = text.split("index_volume_overlay", 1)[1]
        assert "thawedPath" not in overlay.split("- name:", 1)[0] if "- name:" in overlay else "thawedPath" not in overlay[:800]
        assert "homePath.maxDataSizeMB" not in text
        assert "'check': 10" in text or "check: 10" in text

    def test_index_volume_overlay_oneshot_does_not_cap_results(self):
        """Oneshot jobs default to 100 rows; a 2-peer cluster plus SH conf exceeds that and truncates idx2."""
        _plays, tasks = _plays_and_tasks()
        overlay_tasks = [
            task
            for task, _no_log in tasks
            if task.get("name") == "Query index volume paths across search peers from ES search head"
        ]
        assert overlay_tasks, "expected overlay REST query task"
        spec = _uri_spec(overlay_tasks[0])
        assert spec is not None
        body = spec.get("body") or {}
        assert body.get("count") in (0, "0")
        search = str(body.get("search") or "")
        assert "count=0" in search
        assert "splunk_server=*" in search

    def test_suite_configured_uses_apps_local_and_is_na_on_shc_members(self):
        """Check 9 reads configured from the already-fetched apps/local payload; SHC members are N/A."""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "suite_configured" in text
        assert "_suite_content.configured" in text
        assert "'check': 9" in text or "check: 9" in text
        assert "N/A (SHC member)" in text
        # No extra REST call for configured.
        assert text.count("/services/apps/local") == 1

    def test_installer_log_scan_uses_extracted_script_and_stamp(self):
        """SH and deployer scan last-session ERRORs via the shared script, not a heredoc."""
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert text.count("scan_es_installer_log.py") >= 2
        assert "--since-file=" in text
        assert "es_essinstall_started" in text
        assert "scope=whole_file" in text
        assert "ansible.builtin.script" in text
        sh_chunk = text.split("Scan essinstaller2.log for ERROR lines", 1)[1].split("- name:", 1)[0]
        assert "scan_es_installer_log.py" in sh_chunk
        assert "python3 - <<'PY'" not in sh_chunk
        dep_chunk = text.split("Scan essinstaller2.log for ERROR lines on deployer", 1)[1].split("- name:", 1)[0]
        assert "scan_es_installer_log.py" in dep_chunk
        assert "python3 - <<'PY'" not in dep_chunk


def _load_inventory_mod():
    path = PROJECT_ROOT / "ansible/verification/list_es_archive_inventory.py"
    spec = importlib.util.spec_from_file_location("list_es_archive_inventory", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestListEsArchiveInventory:
    """Nested ES 8.x wrapper layout: SA-/DA- live under SplunkEnterpriseSecuritySuite."""

    def test_nested_install_dir_and_inner_spl(self, tmp_path: Path):
        install = tmp_path / "tree" / "SplunkEnterpriseSecuritySuite" / "install"
        sa = install / "SA-ThreatIntelligence" / "default"
        sa.mkdir(parents=True)
        (sa / "app.conf").write_text("[launcher]\nversion=1.0\n", encoding="utf-8")
        (sa / "indexes.conf").write_text("[threat]\nhomePath = volume:hot/threat\n", encoding="utf-8")
        inner_root = tmp_path / "inner" / "DA-ESS-AccessProtection" / "default"
        inner_root.mkdir(parents=True)
        (inner_root / "app.conf").write_text("[launcher]\nversion=1.0\n", encoding="utf-8")
        inner_spl = tmp_path / "DA-ESS-AccessProtection.spl"
        with tarfile.open(inner_spl, "w:gz") as handle:
            handle.add(inner_root.parent.parent, arcname="DA-ESS-AccessProtection")
        wrapper = tmp_path / "tree" / "SplunkEnterpriseSecuritySuite" / "install"
        wrapper.mkdir(parents=True, exist_ok=True)
        dest_inner = wrapper / "DA-ESS-AccessProtection.spl"
        dest_inner.write_bytes(inner_spl.read_bytes())
        archive = tmp_path / "es.spl"
        tree = tmp_path / "tree"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(tree / "SplunkEnterpriseSecuritySuite", arcname="SplunkEnterpriseSecuritySuite")

        mod = _load_inventory_mod()
        result = mod.inventory_from_archive(str(archive))
        assert "SA-ThreatIntelligence" in result["apps"]
        assert "DA-ESS-AccessProtection" in result["apps"]
        assert "threat" in result["indexes"]
        assert "SplunkEnterpriseSecuritySuite" not in result["apps"]
        assert "SA-ThreatIntelligence" in result["all_apps"]
        assert "DA-ESS-AccessProtection" in result["all_apps"]

    def test_versioned_nested_spl_names_canonicalize_to_installed_folders(self, tmp_path: Path):
        """ES 8.8 nested .spl stems include -8.8.0-build; installed apps do not."""
        install = tmp_path / "tree" / "SplunkEnterpriseSecuritySuite" / "install"
        install.mkdir(parents=True)
        inner_root = tmp_path / "inner" / "SA-NetworkProtection" / "default"
        inner_root.mkdir(parents=True)
        (inner_root / "app.conf").write_text("[launcher]\nversion=1.0\n", encoding="utf-8")
        inner_spl = tmp_path / "SA-NetworkProtection-8.8.0-306069.spl"
        with tarfile.open(inner_spl, "w:gz") as handle:
            handle.add(inner_root.parent.parent, arcname="SA-NetworkProtection")
        dest_inner = install / "SA-NetworkProtection-8.8.0-306069.spl"
        dest_inner.write_bytes(inner_spl.read_bytes())
        tim_root = tmp_path / "inner_tim" / "DA-ESS-TIM" / "default"
        tim_root.mkdir(parents=True)
        (tim_root / "app.conf").write_text("[launcher]\nversion=1.0\n", encoding="utf-8")
        tim_spl = tmp_path / "DA-ESS-TIM_8.8.0-1201.spl"
        with tarfile.open(tim_spl, "w:gz") as handle:
            handle.add(tim_root.parent.parent, arcname="DA-ESS-TIM")
        (install / "DA-ESS-TIM_8.8.0-1201.spl").write_bytes(tim_spl.read_bytes())
        archive = tmp_path / "es.spl"
        tree = tmp_path / "tree"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(tree / "SplunkEnterpriseSecuritySuite", arcname="SplunkEnterpriseSecuritySuite")

        mod = _load_inventory_mod()
        result = mod.inventory_from_archive(str(archive))
        assert "SA-NetworkProtection" in result["apps"]
        assert "DA-ESS-TIM" in result["apps"]
        assert "SA-NetworkProtection-8.8.0-306069" not in result["apps"]
        assert "DA-ESS-TIM_8.8.0-1201" not in result["apps"]

    def test_merged_indexes_conf_includes_nested_spl(self, tmp_path: Path):
        install = tmp_path / "tree" / "SplunkEnterpriseSecuritySuite" / "install"
        install.mkdir(parents=True)
        inner_root = tmp_path / "inner" / "SA-NetworkProtection" / "default"
        inner_root.mkdir(parents=True)
        (inner_root / "app.conf").write_text("[launcher]\nversion=1.0\n", encoding="utf-8")
        (inner_root / "indexes.conf").write_text("[network]\nhomePath = volume:hot/network\n", encoding="utf-8")
        inner_spl = tmp_path / "SA-NetworkProtection-8.8.0-306069.spl"
        with tarfile.open(inner_spl, "w:gz") as handle:
            handle.add(inner_root.parent.parent, arcname="SA-NetworkProtection")
        (install / "SA-NetworkProtection-8.8.0-306069.spl").write_bytes(inner_spl.read_bytes())
        archive = tmp_path / "es.spl"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(tmp_path / "tree" / "SplunkEnterpriseSecuritySuite", arcname="SplunkEnterpriseSecuritySuite")
        dest = tmp_path / "merged" / "indexes.conf"
        dest.parent.mkdir()
        mod = _load_inventory_mod()
        written = mod.write_merged_indexes_conf(str(archive), str(dest))
        assert dest.is_file()
        text = dest.read_text(encoding="utf-8")
        assert "[network]" in text
        assert "network" in written["indexes"]

    def test_all_apps_includes_nested_non_sa_da(self, tmp_path: Path):
        """Deployer verify needs CIM/MLTK/etc., not only SA-/DA- suite apps."""
        install = tmp_path / "tree" / "SplunkEnterpriseSecuritySuite" / "install"
        install.mkdir(parents=True)
        suite_default = tmp_path / "tree" / "SplunkEnterpriseSecuritySuite" / "default"
        suite_default.mkdir(parents=True)
        (suite_default / "app.conf").write_text("[launcher]\nversion=8.8.0\n", encoding="utf-8")
        inner_root = tmp_path / "inner" / "Splunk_SA_CIM" / "default"
        inner_root.mkdir(parents=True)
        (inner_root / "app.conf").write_text("[launcher]\nversion=5.0\n", encoding="utf-8")
        inner_spl = tmp_path / "Splunk_SA_CIM.spl"
        with tarfile.open(inner_spl, "w:gz") as handle:
            handle.add(inner_root.parent.parent, arcname="Splunk_SA_CIM")
        (install / "Splunk_SA_CIM.spl").write_bytes(inner_spl.read_bytes())
        archive = tmp_path / "es.spl"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(
                tmp_path / "tree" / "SplunkEnterpriseSecuritySuite",
                arcname="SplunkEnterpriseSecuritySuite",
            )
        mod = _load_inventory_mod()
        result = mod.inventory_from_archive(str(archive))
        assert "Splunk_SA_CIM" in result["all_apps"]
        assert "SplunkEnterpriseSecuritySuite" in result["all_apps"]
        assert "Splunk_SA_CIM" not in result["apps"]

    def test_missing_archive_returns_empty(self, tmp_path: Path):
        mod = _load_inventory_mod()
        result = mod.inventory_from_archive(str(tmp_path / "nope.spl"))
        assert result == {"apps": [], "indexes": [], "all_apps": []}


def _load_scanner_mod():
    path = PROJECT_ROOT / "ansible/verification/scan_es_installer_log.py"
    spec = importlib.util.spec_from_file_location("scan_es_installer_log", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestScanEsInstallerLog:
    """Standing unit checks for last-session essinstaller2.log ERROR counting."""

    def test_scanner_module_loads(self):
        assert (PROJECT_ROOT / "ansible/verification/scan_es_installer_log.py").is_file()
        mod = _load_scanner_mod()
        assert callable(mod.scan_installer_log)

    @pytest.mark.parametrize(
        "case,log_text,stamp_text,want_count,want_scope,want_status",
        [
            (
                "error_only_before_stamp",
                "2026-01-01 10:00:00,001 ERROR old failure auth=secret\n"
                "2026-01-01 12:00:00,001 INFO later ok\n",
                "2026-01-01 11:00:00",
                0,
                "since_stamp",
                "ok",
            ),
            (
                "error_after_stamp",
                "2026-01-01 10:00:00,001 ERROR old failure\n"
                "2026-01-01 12:00:00.002 ERROR new failure admin:hunter2\n",
                "2026-01-01 11:00:00",
                1,
                "since_stamp",
                "ok",
            ),
            (
                "traceback_continuation_inherits_time",
                "2026-01-01 12:00:00,001 INFO start\n"
                "Traceback (most recent call last):\n"
                "  File essinstall.py, line 1\n"
                "ERROR boom\n",
                "2026-01-01 11:00:00",
                1,
                "since_stamp",
                "ok",
            ),
            (
                "stamp_missing_whole_file",
                "2026-01-01 10:00:00 ERROR old\n2026-01-01 12:00:00 ERROR new\n",
                None,
                2,
                "whole_file",
                "ok",
            ),
            (
                "no_parseable_timestamps_whole_file",
                "installer failed\nERROR no clock\n",
                "2026-01-01 11:00:00",
                1,
                "whole_file",
                "ok",
            ),
            (
                "missing_log",
                None,
                "2026-01-01 11:00:00",
                0,
                "",
                "MISSING",
            ),
        ],
        ids=[
            "error_only_before_stamp",
            "error_after_stamp",
            "traceback_continuation_inherits_time",
            "stamp_missing_whole_file",
            "no_parseable_timestamps_whole_file",
            "missing_log",
        ],
    )
    def test_counts_errors_since_stamp(
        self,
        tmp_path: Path,
        case: str,
        log_text: str | None,
        stamp_text: str | None,
        want_count: int,
        want_scope: str,
        want_status: str,
    ):
        log_path = tmp_path / "essinstaller2.log"
        since_path = tmp_path / "es_essinstall_started"
        if log_text is not None:
            log_path.write_text(log_text, encoding="utf-8")
        if stamp_text is not None:
            since_path.write_text(stamp_text + "\n", encoding="utf-8")
        mod = _load_scanner_mod()
        result = mod.scan_installer_log(
            str(log_path),
            str(since_path) if stamp_text is not None else str(tmp_path / "missing_stamp"),
        )
        assert result["status"] == want_status, case
        assert result["count"] == want_count, case
        assert result["scope"] == want_scope, case
        last = result.get("last_error") or ""
        assert "auth=" not in last.lower() or "***" in last
        assert "admin:hunter2" not in last
        if "admin:" in last.lower():
            assert "admin:***" in last
