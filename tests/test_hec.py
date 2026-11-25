"""HEC identity list: inventory, dest naming, inputs.conf updates, DS grouping, role wiring."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import pytest
import yaml

from spa.playbooks import parse_playbook_metadata
from spa_testutil import PROJECT_ROOT

pytestmark = pytest.mark.local

_PLUGIN = PROJECT_ROOT / "ansible" / "plugins" / "inventory" / "splunk-platform-automator.py"
_VERIFY_HEC = PROJECT_ROOT / "ansible" / "verification" / "verify_hec.yml"
_HEC_TASKS = PROJECT_ROOT / "ansible" / "roles" / "baseconfig_app" / "tasks"
_HEC_TASK = _HEC_TASKS / "org_all_hec_inputs.yml"
_CALLERS = {
    "idxsingle": PROJECT_ROOT / "ansible" / "roles" / "indexer" / "tasks" / "idxsingle.yml",
    "idxcluster": PROJECT_ROOT / "ansible" / "roles" / "indexer" / "tasks" / "idxcluster.yml",
    "cluster_manager": PROJECT_ROOT / "ansible" / "roles" / "cluster_manager" / "tasks" / "main.yml",
    "heavy_forwarder": PROJECT_ROOT / "ansible" / "roles" / "heavy_forwarder" / "tasks" / "main.yml",
    "shsingle": PROJECT_ROOT / "ansible" / "roles" / "search_head" / "tasks" / "shsingle.yml",
    "deployer": PROJECT_ROOT / "ansible" / "roles" / "deployer" / "tasks" / "main.yml",
    "deployment_server": PROJECT_ROOT
    / "ansible"
    / "roles"
    / "deployment_server"
    / "tasks"
    / "main.yml",
    "serverclass": PROJECT_ROOT
    / "ansible"
    / "roles"
    / "deployment_server"
    / "tasks"
    / "serverclass.yml",
}


def _inventory_module():
    spec = importlib.util.spec_from_file_location("spa_inventory_plugin_hec", _PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Inventory:
    def __init__(self):
        self.hosts = {}
        self.groups = {}

    def set_variable(self, host, key, value):
        self.hosts.setdefault(host, {})[key] = value


def _hec_task_text() -> str:
    parts = [_HEC_TASK.read_text(encoding="utf-8")]
    extra = _HEC_TASKS / "hec_input_stanza.yml"
    if extra.is_file():
        parts.append(extra.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _include_app_names(path: Path):
    tasks = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    names = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        include = task.get("ansible.builtin.include_role") or task.get("include_role")
        vars_block = task.get("vars") or {}
        if include and vars_block.get("app_name"):
            names.append(vars_block["app_name"])
    return names


def _hec_include_task(path: Path):
    tasks = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        vars_block = task.get("vars") or {}
        if vars_block.get("app_name") == "org_all_hec_inputs":
            return task
        loop = task.get("loop")
        if "org_all_hec_inputs" in str(loop) or "org_all_hec_inputs" in str(vars_block):
            return task
        if "splunk_hec_ds_apps" in str(task.get("loop") or "") or "splunk_hec_ds_apps" in str(
            vars_block
        ):
            if (task.get("ansible.builtin.include_role") or task.get("include_role")):
                return task
    raise AssertionError("no org_all_hec_inputs include in %s" % path)


def test_inventory_publishes_hec_dict_keyed_by_name_and_empty_default():
    module = _inventory_module()
    row = {"hec_name": "o11y", "inputs": {"alerts": {"token": "x"}}}
    assert module.hec_vars_from_config({"splunk_hec": [row]}) == {"o11y": row}
    assert module.hec_vars_from_config({}) == {}
    assert module.hec_vars_from_config({"splunk_hec": []}) == {}


def test_inventory_parse_keeps_splunk_hec_section():
    tree = ast.parse(_PLUGIN.read_text(encoding="utf-8"))
    sections = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "optional_sections" for t in node.targets)
    ]
    assert sections, "optional_sections not found in inventory plugin"
    assert "splunk_hec" in ast.literal_eval(sections[0])


def test_inventory_sets_splunk_hec_name_and_skips_hostvar_hec():
    module = _inventory_module()
    assert "hec" in module._HOST_VAR_SKIP
    inventory = _Inventory()
    module.publish_host_vars(
        inventory,
        "idx1",
        {"name": "idx1", "hec": "o11y", "roles": ["indexer"]},
    )
    assert inventory.hosts["idx1"]["splunk_hec_name"] == "o11y"
    assert "hec" not in inventory.hosts["idx1"]


def test_hec_dest_name_replaces_all_with_listening_infix():
    from spa.hec import hec_dest_name, hec_listening_infix

    assert hec_dest_name("splk", "idx") == "splk_idx_hec_inputs"
    assert hec_dest_name("splk", "hf") == "splk_hf_hec_inputs"
    assert hec_dest_name("splk", "sh") == "splk_sh_hec_inputs"
    assert hec_dest_name("splk", "syslog") == "splk_syslog_hec_inputs"
    assert hec_listening_infix(["indexer", "search_head"]) == "idx"
    assert hec_listening_infix(["heavy_forwarder"]) == "hf"
    assert hec_listening_infix(["search_head"]) == "sh"


def test_hec_ds_apps_splits_idx_and_hf_without_infix():
    from spa.hec import hec_ds_apps

    clients = [{"server": "idx1"}, {"server": "hf1"}]
    host_hec = {"idx1": "o11y", "hf1": "o11y"}
    host_roles = {"idx1": ["indexer"], "hf1": ["heavy_forwarder"]}
    rows = {"o11y": {"hec_name": "o11y"}}
    apps = hec_ds_apps(clients, host_hec, host_roles, rows, "splk")
    by_dest = {item["dest"]: item for item in apps}
    assert set(by_dest) == {"splk_idx_hec_inputs", "splk_hf_hec_inputs"}
    assert by_dest["splk_idx_hec_inputs"]["clients"] == ["idx1"]
    assert by_dest["splk_hf_hec_inputs"]["clients"] == ["hf1"]
    assert by_dest["splk_idx_hec_inputs"]["hec_name"] == "o11y"
    assert by_dest["splk_idx_hec_inputs"]["infix"] == "idx"


def test_hec_ds_apps_shares_one_dest_when_app_infix_is_set():
    from spa.hec import hec_ds_apps

    clients = [{"server": "idx1"}, {"server": "hf1"}]
    host_hec = {"idx1": "syslog", "hf1": "syslog"}
    host_roles = {"idx1": ["indexer"], "hf1": ["heavy_forwarder"]}
    rows = {"syslog": {"hec_name": "syslog", "app_infix": "syslog"}}
    apps = hec_ds_apps(clients, host_hec, host_roles, rows, "splk")
    assert len(apps) == 1
    assert apps[0]["dest"] == "splk_syslog_hec_inputs"
    assert apps[0]["clients"] == ["idx1", "hf1"]
    assert apps[0]["infix"] == "syslog"


def test_hec_task_file_updates_inputs_conf_in_place():
    text = _hec_task_text()
    assert "community.general.ini_file" in text
    assert "ansible.builtin.template" not in text
    assert "hec_inputs.conf.j2" not in text
    assert "ini_file" in text
    assert "is boolean" in text
    assert "http://hec_input" in text
    assert "ansible.builtin.replace" in text
    assert "uuid.uuid4" in text
    assert "no_log: true" in text
    assert not (_HEC_TASKS.parent / "templates" / "hec_inputs.conf.j2").exists()


def test_hec_input_options_default_enabled_and_indexes_to_index():
    tasks = yaml.safe_load((_HEC_TASKS / "hec_input_stanza.yml").read_text(encoding="utf-8"))
    options = next(task for task in tasks if str(task.get("name", "")).startswith("Set options"))
    assert "{'disabled': false, 'indexes': hec_input.value.index}" in options["loop"]
    assert "combine(" in options["loop"]


def test_role_callers_include_org_all_hec_inputs_except_idxcluster():
    for name, path in _CALLERS.items():
        if name in ("idxcluster", "serverclass"):
            continue
        names = _include_app_names(path)
        if name == "deployment_server":
            text = path.read_text(encoding="utf-8")
            assert "org_all_hec_inputs" in text
            continue
        assert "org_all_hec_inputs" in names, name
    assert "org_all_hec_inputs" not in _include_app_names(_CALLERS["idxcluster"])
    sh_task = _hec_include_task(_CALLERS["shsingle"])
    when = sh_task.get("when")
    assert "groups.role_indexer" in str(when)
    for name in ("idxsingle", "cluster_manager", "heavy_forwarder", "shsingle", "deployer"):
        task = _hec_include_task(_CALLERS[name])
        assert "splunk_hec_name" in str(task.get("when"))
    ds_main = _CALLERS["deployment_server"].read_text(encoding="utf-8")
    assert "splunk_hec_ds_apps" in ds_main
    serverclass = _CALLERS["serverclass"].read_text(encoding="utf-8")
    assert "splunk_hec_ds_apps" in serverclass
    dynamic = (
        PROJECT_ROOT / "ansible" / "group_vars" / "all" / "dynamic.yml"
    ).read_text(encoding="utf-8")
    assert "splunk_hec_ds_apps" in dynamic


def _walk_tasks(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk_tasks(item)
        return
    if not isinstance(node, dict):
        return
    yield node
    for key in ("block", "rescue", "always"):
        yield from _walk_tasks(node.get(key) or [])


def _verify_hec_plays_and_tasks():
    plays = yaml.safe_load(_VERIFY_HEC.read_text(encoding="utf-8")) or []
    tasks = []
    for play in plays:
        if isinstance(play, dict):
            tasks.extend(_walk_tasks(play.get("tasks") or []))
    return plays, tasks


def _uri_spec(task):
    return task.get("ansible.builtin.uri") or task.get("uri")


def test_verify_hec_playbook_contract():
    assert _VERIFY_HEC.is_file()
    meta = parse_playbook_metadata(_VERIFY_HEC)
    assert meta is not None
    assert meta["category"] == "verification"
    assert meta["risk"] == "mutating"

    plays, tasks = _verify_hec_plays_and_tasks()
    end_play = [
        task
        for task in tasks
        if (task.get("ansible.builtin.meta") or task.get("meta")) == "end_play"
        and "splunk_hec_name" in str(task.get("when"))
    ]
    assert end_play, "expected meta: end_play gated on splunk_hec_name"

    uri_tasks = [(task, _uri_spec(task)) for task in tasks if _uri_spec(task) is not None]
    token_get = [
        (task, spec)
        for task, spec in uri_tasks
        if "count=0" in str(spec.get("url", ""))
        and "/services/data/inputs/http" in str(spec.get("url", ""))
    ]
    assert token_get, "expected uri GET /services/data/inputs/http?count=0"

    for task in tasks:
        text = yaml.dump(task)
        assert "hec_input.value.token" not in text
        if "splunk_hec" in text:
            assert ".token" not in text

    collector = [
        (task, spec)
        for task, spec in uri_tasks
        if "/services/collector" in str(spec.get("url", ""))
        and str(spec.get("method", "")).upper() == "POST"
    ]
    assert collector, "expected uri POST to /services/collector"
    collector_headers = collector[0][1].get("headers") or {}
    assert any(
        str(key) == "X-Splunk-Request-Channel" for key in collector_headers
    ), "expected X-Splunk-Request-Channel on collector POST"

    search = [
        (task, spec)
        for task, spec in uri_tasks
        if "/services/search/jobs" in str(spec.get("url", ""))
    ]
    assert search, "expected search uri to /services/search/jobs"
    assert search[0][0].get("until")
    assert search[0][0].get("retries")

    for task, spec in token_get + collector:
        assert task.get("no_log") is True, task.get("name")

    play_vars = " ".join(str(play.get("vars") or {}) for play in plays if isinstance(play, dict))
    assert "rejectattr" not in play_vars

    includes = [
        task.get("ansible.builtin.include_role") or task.get("include_role")
        for task in tasks
    ]
    assert not any(
        inc
        and (
            (isinstance(inc, dict) and inc.get("tasks_from") == "splunk_rest")
            or "splunk_rest" in str(inc)
        )
        for inc in includes
    )
