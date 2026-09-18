"""spa_jsonl callback origin paths and event fields."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from spa.origin import origin_file

pytestmark = [pytest.mark.local]

PROJECT = Path(__file__).resolve().parents[1]


def test_origin_file_strips_line_and_column():
    play = SimpleNamespace(get_path=lambda: "/repo/ansible/splunk_install.yml:13")
    assert origin_file(play) == "/repo/ansible/splunk_install.yml"
    task = SimpleNamespace(
        get_path=None,
        _ds=SimpleNamespace(ansible_pos=("/repo/ansible/roles/indexer/tasks/main.yml", 4, 2)),
    )
    assert origin_file(task) == "/repo/ansible/roles/indexer/tasks/main.yml"
    tagged = SimpleNamespace(
        get_path=lambda: "",
        _ds=None,
        _origin=SimpleNamespace(path="/abs/child.yml:9:0"),
    )
    assert origin_file(tagged) == "/abs/child.yml"
    win = SimpleNamespace(get_path=lambda: r"C:\repo\splunk_install.yml:10:2")
    assert origin_file(win).endswith("splunk_install.yml")


def test_callback_emits_play_file_and_role_path(monkeypatch):
    sys.path.insert(0, str(PROJECT / "ansible" / "plugins" / "callback"))
    try:
        from spa_jsonl import CallbackModule
    except Exception as exc:  # pragma: no cover - ansible tmp dir in some sandboxes
        pytest.skip("ansible callback import failed: %s" % exc)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    cb = CallbackModule()
    cb.v2_playbook_on_start(SimpleNamespace(_file_name="/repo/ansible/deploy_site.yml"))
    play = SimpleNamespace(
        get_name=lambda: "Install the splunk enterprise software",
        get_path=lambda: "/repo/ansible/splunk_install.yml:13",
    )
    cb.v2_playbook_on_play_start(play)

    class Role:
        _role_name = "splunk_software"

        def get_role_path(self):
            return "/repo/ansible/roles/splunk_software"

    task = SimpleNamespace(
        get_name=lambda: "Install package",
        _uuid="u1",
        tags=["splunk"],
        _role=Role(),
        get_path=lambda: "/repo/ansible/roles/splunk_software/tasks/main.yml:4",
    )
    cb.v2_playbook_on_task_start(task, False)
    prefix = "SPA_JSONL_EVENT="
    events = [
        json.loads(line[len(prefix) :])
        for line in buf.getvalue().splitlines()
        if line.startswith(prefix)
    ]
    kinds = [row["kind"] for row in events]
    assert kinds == ["playbook_start", "play_start", "task_start"]
    assert events[0]["playbook"].endswith("deploy_site.yml")
    assert events[1]["play_file"].endswith("splunk_install.yml")
    assert events[2]["play_file"].endswith("splunk_install.yml")
    assert events[2]["task_file"].endswith("main.yml")
    assert events[2]["role"] == "splunk_software"
    assert events[2]["role_path"].endswith("splunk_software")


def test_callback_imported_playbook_reports_child_file():
    playbook = shutil.which("ansible-playbook")
    if not playbook:
        venv = PROJECT / "tests" / ".venv" / "bin" / "ansible-playbook"
        playbook = str(venv) if venv.is_file() else ""
    if not playbook:
        pytest.skip("ansible-playbook not on PATH")
    fixture_dir = PROJECT / "tests" / "fixtures" / "spa_jsonl_import"
    plugin_dir = PROJECT / "ansible" / "plugins" / "callback"
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(fixture_dir / "ansible.cfg")
    env["ANSIBLE_STDOUT_CALLBACK"] = "default"
    env["ANSIBLE_CALLBACKS_ENABLED"] = "spa_jsonl"
    env["ANSIBLE_CALLBACK_PLUGINS"] = str(plugin_dir)
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["ANSIBLE_LOCAL_TEMP"] = str(fixture_dir / ".tmp")
    result = subprocess.run(
        [playbook, "-i", "localhost,", "-c", "local", str(fixture_dir / "site.yml")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(fixture_dir),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "PLAY [Child imported play]" in result.stdout
    prefix = "SPA_JSONL_EVENT="
    events = [
        json.loads(line[len(prefix) :])
        for line in result.stderr.splitlines()
        if line.startswith(prefix)
    ]
    starts = [row for row in events if row.get("kind") == "playbook_start"]
    assert len(starts) == 1
    assert starts[0]["playbook"].endswith("site.yml")
    plays = [row for row in events if row.get("kind") == "play_start"]
    assert plays
    assert str(plays[0].get("play_file") or "").endswith("child.yml")
    assert plays[0].get("play") == "Child imported play"
