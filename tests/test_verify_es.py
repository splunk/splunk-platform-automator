"""Static contract for ansible/verification/verify_es.yml (premium_app: es health)."""

from __future__ import annotations

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

CHECK_ENDPOINTS = (
    ("/services/apps/local", "installer / suite apps"),
    ("essinstaller2.log", "installer log"),
    ("/services/kvstore/status", "KV store"),
    ("/services/data/indexes", "indexes on search peers"),
    ("enableSplunkWebSSL", "SSL mode"),
    ("/services/licenser/", "ES license"),
    ("max_content_length", "upload limits"),
    ("correlationsearch", "correlation searches"),
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

    def test_checks_1_to_7_respect_fail_on_mismatch_check_8_never_fails(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert "fail_on_mismatch" in text
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
        for task in corr:
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

    def test_readme_documents_verify_es(self):
        text = README.read_text(encoding="utf-8")
        assert "verify_es.yml" in text
        assert "fail_on_mismatch" in text
        assert "-v" not in text.split("verify_es.yml", 1)[1].split("###", 1)[0]

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
