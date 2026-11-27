"""Static contract for ansible/verification/wait_for_kvstore.yml."""

from __future__ import annotations

import pytest
import yaml

from spa.playbooks import catalog, parse_playbook_metadata
from spa.paths import resolve_spa_paths
from spa_testutil import PROJECT_ROOT

pytestmark = [pytest.mark.local]

WAIT = PROJECT_ROOT / "ansible/verification/wait_for_kvstore.yml"
README = PROJECT_ROOT / "ansible/verification/README.md"


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


def test_wait_for_kvstore_defaults_splunk_user_and_home():
    """Verification plays do not include splunk_common; undefined splunk_user fails become_user."""
    text = WAIT.read_text(encoding="utf-8")
    plays = yaml.safe_load(text) or []
    become_users = [
        str(play.get("become_user") or "")
        for play in plays
        if isinstance(play, dict)
    ]
    assert become_users, "expected play-level become_user"
    joined = "\n".join(become_users)
    assert "splunk_user | default('splunk')" in joined
    assert "splunk_home | default('/opt/splunk')" in text


def test_wait_for_kvstore_is_generic_search_head_cli():
    text = WAIT.read_text(encoding="utf-8")
    assert "premium_app" not in text
    assert "es_app" not in text.lower()
    assert "itsi" not in text.lower()
    assert "show" in text
    assert "kvstore-status" in text
    assert "splunk_search_head_list" in text
    assert "splunk_shc_host_list" in text
    meta = parse_playbook_metadata(WAIT)
    assert meta is not None
    assert meta["schema"] == 1
    assert meta["category"] == "verification"
    assert meta["risk"] == "read-only"
    assert meta["requires_provisioned"] is True
    description = (meta.get("description") or "").lower()
    assert "premium_app" not in description
    assert "enterprise security" not in description
    assert "itsi" not in description
    examples = "\n".join(meta.get("examples") or [])
    assert "spa run verification/wait_for_kvstore" in examples
    assert "-v" not in examples
    plays = yaml.safe_load(text) or []
    hosts = " ".join(str(play.get("hosts", "")) for play in plays if isinstance(play, dict))
    assert "role_search_head" in hosts
    tasks = []
    for play in plays:
        if isinstance(play, dict):
            tasks.extend(_walk_tasks(play.get("tasks") or []))
    wait_tasks = [
        (task, no_log)
        for task, no_log in tasks
        if "kvstore-status" in yaml.dump(task)
    ]
    assert wait_tasks, "expected splunk show kvstore-status"
    task, no_log = wait_tasks[0]
    until = str(task.get("until") or "")
    assert "ready" in until
    assert task.get("retries")
    assert task.get("delay")
    assert no_log is True
    when = task.get("when")
    when_text = when if isinstance(when, str) else yaml.dump(when)
    assert "splunk_search_head_list" in when_text
    assert "splunk_shc_host_list" in when_text
    assert "-auth" in yaml.dump(task)


def test_catalog_lists_verification_wait_for_kvstore():
    rows = catalog(resolve_spa_paths(start_dir=str(PROJECT_ROOT)))
    names = [row["name"] for row in rows]
    assert "verification/wait_for_kvstore" in names
    row = next(item for item in rows if item["name"] == "verification/wait_for_kvstore")
    assert row["missing"] is False
    assert row["risk"] == "read-only"
    assert row.get("requires_confirmation") is False


def test_readme_documents_wait_for_kvstore():
    text = README.read_text(encoding="utf-8")
    section = text.split("wait_for_kvstore.yml", 1)[1].split("###", 1)[0]
    assert "show kvstore-status" in section
    assert "splunk_shc_host_list" in section
    assert "premium_app" not in section
    assert "-v" not in section
