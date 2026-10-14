"""First-party Ansible tasks must not print Splunk credentials."""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.local]

PROJECT = Path(__file__).resolve().parents[1]
ANSIBLE = PROJECT / "ansible"
FIXTURE = PROJECT / "tests" / "fixtures" / "ansible_no_log" / "site.yml"
SENTINEL = "spa-sentinel-credential"

NESTED_KEYS = {
    "block",
    "rescue",
    "always",
    "tasks",
    "pre_tasks",
    "post_tasks",
    "handlers",
    "roles",
}
SHORT_MODULES = {
    "command",
    "shell",
    "raw",
    "script",
    "copy",
    "file",
    "uri",
    "get_url",
    "set_fact",
    "debug",
    "fail",
    "assert",
    "include_role",
    "include_tasks",
    "import_role",
    "import_tasks",
    "template",
    "unarchive",
    "service",
    "stat",
    "wait_for",
    "xml",
    "pause",
    "meta",
    "block",
    "ini_file",
    "lineinfile",
    "replace",
    "slurp",
    "find",
    "fetch",
}
SECRET_JINJA = re.compile(
    r"\{\{[^}]*\b("
    r"splunk_admin_password|splunk_shc_pass|splunk_idxc_pass|"
    r"idxc_password|idxc_discovery_password|_snow_password|_sim_o11y_api_token"
    r")\b"
)
SPLUNKBASE_VALUE = re.compile(r"\{\{[^}]*\bsplunkbase_password\b")
HEADER_KEYS = {"X-SF-TOKEN", "X-Auth-Token"}
SECRET_FACT_KEYS = {"splunk_loginpage_user_info", "splunkbase_token", "splunkbase_app_info"}


def _ansible_playbook() -> str:
    override = (os.environ.get("ANSIBLE_PLAYBOOK") or "").strip()
    if override:
        return override
    found = shutil.which("ansible-playbook")
    if found:
        return found
    venv = PROJECT / "tests" / ".venv" / "bin" / "ansible-playbook"
    if venv.is_file():
        return str(venv)
    pytest.skip("ansible-playbook not on PATH")
    return ""


def _is_task(node: dict) -> bool:
    for key in node:
        if not isinstance(key, str):
            continue
        if key in SHORT_MODULES or key.startswith("ansible.") or key.startswith("community."):
            return True
    return False


def _walk_tasks(node, found: list) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_tasks(item, found)
        return
    if not isinstance(node, dict):
        return
    if _is_task(node):
        found.append(node)
    for key, value in node.items():
        if key in NESTED_KEYS:
            _walk_tasks(value, found)
        elif not _is_task(node):
            _walk_tasks(value, found)


def _flatten(node, keys: list[str], texts: list[str]) -> None:
    if isinstance(node, str):
        texts.append(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            keys.append(str(key))
            _flatten(value, keys, texts)
    elif isinstance(node, list):
        for item in node:
            _flatten(item, keys, texts)


def _sensitive(task: dict) -> bool:
    own = {key: value for key, value in task.items() if key not in NESTED_KEYS}
    keys: list[str] = []
    texts: list[str] = []
    _flatten(own, keys, texts)
    blob = "\n".join(texts)
    if SECRET_JINJA.search(blob):
        return True
    if any(SPLUNKBASE_VALUE.search(text) and "length" not in text for text in texts):
        return True
    if any(key in HEADER_KEYS or key in SECRET_FACT_KEYS or key == "password" for key in keys):
        return True
    if "_snow_password" in keys:
        return True
    if any(text in {"pass4SymmKey", "login_content", "HASHED_PASSWORD"} for text in texts):
        return True
    return False


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_fixture_playbook_has_no_sentinel_literal():
    assert SENTINEL not in FIXTURE.read_text(encoding="utf-8")


def test_first_party_tasks_hide_secret_arguments():
    failures: list[str] = []
    for path in sorted(ANSIBLE.rglob("*.yml")):
        if path.name.endswith(".old"):
            continue
        try:
            document = _load_yaml(path)
        except yaml.YAMLError as exc:
            failures.append(f"{path.relative_to(PROJECT)}: YAML parse error: {exc}")
            continue
        tasks: list = []
        _walk_tasks(document, tasks)
        for task in tasks:
            if not _sensitive(task):
                continue
            if task.get("no_log") is True:
                continue
            name = task.get("name") or task.get("ansible.builtin.command") or "(unnamed)"
            failures.append(f"{path.relative_to(PROJECT)}: {name}")
    assert failures == [], "secret-bearing tasks missing no_log:\n" + "\n".join(failures)


def test_auth_file_helper_and_no_log_hide_sentinel(tmp_path):
    playbook = _ansible_playbook()
    home = tmp_path / "opt" / "splunk"
    bindir = home / "bin"
    bindir.mkdir(parents=True)
    argv_out = tmp_path / "argv.txt"
    fake = bindir / "splunk"
    fake.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" > "$SPA_ARGV_OUT"\n'
        "printf 'ok\\n'\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    env = os.environ.copy()
    env.update(
        {
            "SPA_SENTINEL": SENTINEL,
            "SPA_FAKE_SPLUNK_HOME": str(home),
            "SPA_FAKE_USER": user,
            "SPA_FAKE_GROUP": group,
            "SPA_ARGV_OUT": str(argv_out),
            "ANSIBLE_CONFIG": str(PROJECT / "tests" / "fixtures" / "spa_jsonl_import" / "ansible.cfg"),
            "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"),
            "ANSIBLE_STDOUT_CALLBACK": "default",
            "ANSIBLE_CALLBACKS_ENABLED": "spa_jsonl",
            "ANSIBLE_CALLBACK_PLUGINS": str(ANSIBLE / "plugins" / "callback"),
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_FORCE_COLOR": "0",
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
            "ANSIBLE_REMOTE_TMP": str(tmp_path / "ansible-remote"),
        }
    )
    result = subprocess.run(
        [playbook, "-v", "-i", "localhost,", "-c", "local", str(FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(tmp_path),
    )
    combined = result.stdout + "\n" + result.stderr
    assert result.returncode == 0, combined
    assert SENTINEL not in result.stdout
    assert SENTINEL not in result.stderr
    prefix = "SPA_JSONL_EVENT="
    events = [
        json.loads(line[len(prefix) :])
        for line in result.stderr.splitlines()
        if line.startswith(prefix)
    ]
    leaked = [row for row in events if SENTINEL in json.dumps(row)]
    assert leaked == []
    msgs = [str(row.get("msg") or "") for row in events]
    assert not any(SENTINEL in msg for msg in msgs)
    captured = argv_out.read_text(encoding="utf-8")
    assert SENTINEL in captured
    assert "-auth" in captured
    leftovers = list((home / "var" / "run").glob("spa-cli-*"))
    assert leftovers == []
