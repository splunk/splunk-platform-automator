"""Run transcripts, redaction, phase map, and spa logs."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pytest

from spa.playbooks import run_playbook
from spa.paths import resolve_spa_paths
from spa.runlog import (
    RunLog,
    format_event_time,
    format_run_id_stamp,
    list_runs,
    map_phase,
    now_local,
    redact,
)
from spa_testutil import min_env_vars, run_spa

pytestmark = [pytest.mark.local]

PROJECT = Path(__file__).resolve().parents[1]


def test_format_event_time_local_offset_not_z():
    zurich = datetime(2026, 9, 17, 17, 2, 0, 123456, tzinfo=timezone(timedelta(hours=2)))
    assert format_event_time(zurich) == "2026-09-17T17:02:00.123+02:00"
    assert format_run_id_stamp(zurich) == "2026-09-17T170200+0200"
    utc = datetime(2026, 9, 17, 15, 2, 0, 0, tzinfo=timezone.utc)
    stamp = format_event_time(utc)
    assert stamp.endswith("+00:00")
    assert "Z" not in stamp


def test_now_local_honors_tz_env():
    old = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "UTC"
        time.tzset()
        utc_stamp = format_event_time(now_local())
        assert utc_stamp.endswith("+00:00")
        assert "Z" not in utc_stamp
        os.environ["TZ"] = "Europe/Zurich"
        time.tzset()
        zurich = datetime(2026, 9, 17, 12, 0, 0).astimezone()
        assert format_event_time(zurich).endswith("+02:00")
        assert "+0200" in format_run_id_stamp(zurich)
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def test_redact_secrets():
    text = redact(
        "password=hunter2 token=abcd AKIA0000000000000000 "
        "splunk list user -auth admin:cli-secret -remotePassword peer-secret "
        "-password 'new-secret' -secret shc-secret "
        "-----BEGIN PRIVATE KEY-----\nMII\n-----END PRIVATE KEY----- "
        "$ANSIBLE_VAULT;1.1;AES256\n00aa "
        "<license>SECRETXML</license> "
        "Bearer eyJabc"
    )
    assert "hunter2" not in text
    assert "cli-secret" not in text
    assert "peer-secret" not in text
    assert "new-secret" not in text
    assert "shc-secret" not in text
    assert "AKIA0000000000000000" not in text
    assert "BEGIN PRIVATE KEY" not in text
    assert "00aa" not in text
    assert "SECRETXML" not in text
    assert "eyJabc" not in text
    assert "***" in text or "[REDACTED]" in text


def test_map_deploy_phases():
    assert map_phase(command="deploy", playbook="preflight_deploy.yml") == "preflight"
    assert map_phase(command="deploy", playbook="splunk_install.yml") == "binary"
    assert (
        map_phase(command="deploy", playbook="splunk_setup_roles.yml", play="Setup cluster manager role")
        == "role_cluster_manager"
    )
    assert (
        map_phase(
            command="deploy",
            playbook="splunk_setup_roles.yml",
            play="Setup search head role",
        )
        == "role_search_head"
    )
    assert map_phase(command="deploy", tags=["splunk_baseconfig"], task="Apply org_all_indexes") == "baseconfig"
    assert map_phase(command="provision", task="Run Terraform Plan") == "tf_plan"
    assert map_phase(command="provision", task="Wait for SSH") == "wait_ssh"
    assert map_phase(command="run", playbook="splunk_install.yml") == "binary"
    assert (
        map_phase(
            command="run",
            playbook="splunk_install.yml",
            parent_playbook="ansible/deploy_site.yml",
        )
        == "binary"
    )


def test_map_phase_uses_imported_play_file_not_entry():
    assert (
        map_phase(
            command="deploy",
            playbook="ansible/deploy_site.yml",
            play_file="ansible/splunk_apps_deploy.yml",
            play="Deploy apps to Deployers",
        )
        == "apps_shc"
    )
    assert (
        map_phase(
            command="run",
            playbook="ansible/splunk_apps_deploy.yml",
            play_file="ansible/splunk_apps_deploy.yml",
            play="Deploy apps to Deployers",
        )
        == "apps_shc"
    )
    assert (
        map_phase(
            command="deploy",
            playbook="ansible/deploy_site.yml",
            play_file="ansible/splunk_setup_roles.yml",
            play="Setup cluster manager role",
        )
        == "role_cluster_manager"
    )


def test_map_phase_app_overlays_and_upgrade():
    assert (
        map_phase(
            command="deploy",
            play_file="ansible/splunk_apps_deploy.yml",
            play="Deploy apps to Cluster Managers",
            role="apps_itsi",
            role_path="ansible/roles/apps_itsi",
        )
        == "apps_premium_itsi"
    )
    assert (
        map_phase(
            command="run",
            play_file="ansible/splunk_apps_deploy.yml",
            role="apps_itsi_content_pack",
        )
        == "apps_content_packs"
    )
    assert (
        map_phase(
            command="run",
            play_file="ansible/splunk_apps_deploy.yml",
            play="Run post-restart playbooks (direct deployment)",
            task_file="ansible/roles/apps_itsi_content_pack/tasks/cp_api_install.yml",
        )
        == "apps_cp_api"
    )
    assert (
        map_phase(command="run", playbook="upgrade_idxc_rolling.yml", play="Begin tasks")
        == "upgrade_idxc_begin"
    )
    assert (
        map_phase(command="run", playbook="upgrade_idxc_rolling.yml", play="Upgrade indexer")
        == "upgrade_idxc_peers"
    )
    assert (
        map_phase(command="run", playbook="upgrade_idxc_rolling.yml", play="End tasks")
        == "upgrade_idxc_end"
    )
    assert map_phase(command="run", playbook="custom_lab.yml", play="Do a thing") == "play:Do a thing"


def test_provision_groups_follow_the_provider():
    from spa.runlog import group_title, phases_for_command

    assert [row["id"] for row in phases_for_command("provision")][0] == "tf_init"
    assert phases_for_command("provision", provider="virtualbox") == []
    assert map_phase(command="provision", task="Run Terraform Plan", provider="virtualbox") is None
    assert group_title("vm:idx1") == "VM idx1"


def test_vagrant_lines_map_to_machines_and_failures():
    from spa.runlog import vagrant_event

    assert vagrant_event("==> idx1: Booting VM...") == {
        "source": "provider",
        "phase": "vm:idx1",
        "task": "Booting VM...",
        "msg": "Booting VM...",
        "status": "ok",
        "kind": "task_start",
    }
    assert vagrant_event("    idx1: SSH address: 127.0.0.1:2222")["phase"] == "vm:idx1"
    assert vagrant_event("[idx1] GuestAdditions seems to be installed")["phase"] == "vm:idx1"
    assert vagrant_event("Bringing machine 'idx1' up with 'virtualbox' provider...")["phase"] == "vm:idx1"
    # Vagrant's own notices and box download ticks are not machine steps.
    assert "phase" not in vagrant_event("==> vagrant: A new version of Vagrant is available")
    assert vagrant_event("    box: Progress: 40% (Rate: 3247k/s)") is None
    assert vagrant_event("") is None
    failure = vagrant_event("==> idx1: There was an error while executing `VBoxManage`")
    assert failure["status"] == "failed"
    assert failure["host"] == "idx1"
    assert vagrant_event("ERROR: Cannot find ansible binary")["status"] == "failed"


def test_runlog_vagrant_run_wide_lines_stay_in_the_open_group(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "provision",
        "vagrant_up",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        provider="virtualbox",
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.consume_provider_line("==> idx1: Booting VM...\n")
    log.consume_provider_line("\x1b[KGuestAdditions versions do not match.\n")
    log.consume_provider_line("==> idx1: Machine booted and ready!\n")
    log.finish(0)
    events = [json.loads(line) for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert {row.get("phase") for row in events} == {"vm:idx1"}
    from spa.runlog import render_replay_text

    replay = render_replay_text(events)
    assert "Booting VM..." in replay
    assert "TASK [" not in replay
    assert [row.get("status") for row in events].count("phase_start") == 1
    assert "\x1b" not in log.jsonl_path.read_text(encoding="utf-8")
    text = stderr.getvalue()
    assert "Provision  VM idx1  tasks 3" in text
    assert text.rstrip().endswith("ok")


def test_runlog_marks_the_phase_failed_without_a_host(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "provision",
        "vagrant_up",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        provider="virtualbox",
    )
    log.consume_provider_line("ERROR: Cannot find ansible binary\n")
    log.finish(2)
    text = stderr.getvalue()
    assert "Cannot find ansible binary" in text
    assert text.rstrip().endswith("failed")


def test_runlog_agent_stderr_is_sparse(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=True,
        ansible_output=True,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit(
        {
            "playbook": "splunk_install.yml",
            "play": "Install the splunk software",
            "task": "Install package",
            "host": "idx1",
            "status": "ok",
        }
    )
    log.emit(
        {
            "playbook": "splunk_install.yml",
            "task": "Boom",
            "host": "idx1",
            "status": "failed",
            "msg": "password=secret",
        }
    )
    log.finish(1)
    err = stderr.getvalue()
    assert "PLAY" not in err
    assert "Install package" not in err
    events = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
    kinds = [row.get("status") for row in events]
    assert "running" in kinds
    assert any("tasks" in row for row in events if row.get("status") == "running")
    assert "failed" in kinds
    assert any(row.get("host") == "idx1" and row.get("task") == "Boom" for row in events)
    transcript = log.jsonl_path.read_text(encoding="utf-8")
    assert "password=secret" not in transcript
    assert "***" in transcript
    fields = log.envelope_fields()
    assert fields["log"] == str(log.jsonl_path)
    assert fields["phase"]
    assert fields["host"] == "idx1"


def test_runlog_human_phase_headline(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit(
        {
            "playbook": "splunk_install.yml",
            "play": "Install the splunk software",
            "task": "Install package",
            "host": "idx1",
            "status": "changed",
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert "17:02:00+02:00" in text
    assert "Deploy  Splunk install" in text
    assert "[1/" not in text
    assert "[6/10]" not in text
    assert "changed 1/1" in text
    assert "hosts 1" in text
    assert text.rstrip().endswith("changed")


def test_run_playbook_fake_ansible(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "assert os.environ['ANSIBLE_STDOUT_CALLBACK'] == 'default'\n"
        "assert 'spa_jsonl' in os.environ['ANSIBLE_CALLBACKS_ENABLED'].split(',')\n"
        "print('PLAY [native output]')\n"
        "print('SPA_JSONL_EVENT=' + json.dumps({"
        '"playbook": "splunk_install.yml", "play": "Install the splunk software",'
        ' "task": "Install package", "host": "idx1", "status": "ok"}), file=sys.stderr)\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr("spa.playbooks.tool_path", lambda _paths, name: str(fake))
    playbook = PROJECT / "ansible" / "splunk_install.yml"
    stderr = StringIO()
    from spa.runlog import RunLog

    log = RunLog(
        paths,
        "run",
        str(playbook),
        agent=True,
        heartbeat_seconds=0,
        stream=stderr,
    )
    rc = run_playbook(playbook, paths, command="run", agent=True, run_log=log)
    log.finish(rc)
    assert rc == 0
    assert log.jsonl_path.is_file()
    assert log.meta_path.is_file()
    body = log.jsonl_path.read_text(encoding="utf-8")
    assert "idx1" in body
    assert "Install package" in body
    meta = json.loads(log.meta_path.read_text(encoding="utf-8"))
    assert meta["rc"] == 0
    assert meta["run_id"] == log.run_id
    assert str(log.jsonl_path) == meta["log"]
    envelope_err = stderr.getvalue()
    assert "PLAY [" not in envelope_err


def test_native_output_keeps_ansible_color_on_a_tty_and_not_in_jsonl(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ANSIBLE_NOCOLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "print('FORCE_COLOR=' + os.environ['ANSIBLE_FORCE_COLOR'])\n"
        "print('\\033[0;32mok: [idx1]\\033[0m')\n"
        "print('\\033[0;35m[WARNING]: colored warning\\033[0m', file=sys.stderr)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr("spa.playbooks.tool_path", lambda _paths, name: str(fake))
    from spa.runlog import RunLog

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "run",
        str(PROJECT / "ansible" / "splunk_install.yml"),
        agent=False,
        ansible_output=True,
        native_output=True,
        heartbeat_seconds=0,
        stream=stderr,
    )
    assert log.wants_color is True
    rc = run_playbook(
        PROJECT / "ansible" / "splunk_install.yml",
        paths,
        command="run",
        ansible_output=True,
        native_output=True,
        run_log=log,
    )
    log.finish(rc)

    live = stderr.getvalue()
    assert "FORCE_COLOR=1" in live
    assert "\033[0;32mok: [idx1]\033[0m" in live
    transcript = log.jsonl_path.read_text(encoding="utf-8")
    assert "\033[" not in transcript
    assert "colored warning" in transcript


def test_run_playbook_native_output_is_live_raw_and_stored_redacted(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print('PLAY [Native play]')\n"
        "print('fatal: [idx1]: FAILED! => cmd=splunk list user -auth admin:sentinel')\n"
        "print('SPA_JSONL_EVENT=' + json.dumps({"
        '"playbook": "splunk_install.yml", "play": "Native play",'
        ' "task": "List user", "host": "idx1", "status": "failed",'
        ' "msg": "command failed"}), file=sys.stderr)\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr("spa.playbooks.tool_path", lambda _paths, name: str(fake))
    from spa.runlog import RunLog

    stderr = StringIO()
    log = RunLog(
        paths,
        "run",
        str(PROJECT / "ansible" / "splunk_install.yml"),
        agent=False,
        ansible_output=True,
        native_output=True,
        heartbeat_seconds=0,
        stream=stderr,
    )
    rc = run_playbook(
        PROJECT / "ansible" / "splunk_install.yml",
        paths,
        command="run",
        ansible_output=True,
        native_output=True,
        run_log=log,
    )
    log.finish(rc)

    live = stderr.getvalue()
    assert "PLAY [Native play]" in live
    # spa -v reproduces Ansible byte for byte, secrets included.
    assert "-auth admin:sentinel" in live
    # Native output only: the JSONL replay must not print the same run again.
    assert live.count("PLAY [Native play]") == 1
    assert live.count("fatal: [idx1]") == 1
    assert "command failed" not in live
    # The stored transcript stays redacted even when the terminal saw the secret.
    transcript = log.jsonl_path.read_text(encoding="utf-8")
    assert "sentinel" not in transcript
    assert '"task": "List user"' in transcript


def test_ansible_output_without_verbose_stays_redacted_and_reconstructed(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "print('FORCE_COLOR=' + os.environ['ANSIBLE_FORCE_COLOR'])\n"
        "print('fatal: [idx1]: FAILED! => cmd=splunk list user -auth admin:sentinel')\n"
        "print('SPA_JSONL_EVENT=' + json.dumps({"
        '"playbook": "splunk_install.yml", "play": "Native play",'
        ' "task": "List user", "host": "idx1", "status": "failed",'
        ' "msg": "cmd=splunk list user -auth admin:sentinel"}), file=sys.stderr)\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr("spa.playbooks.tool_path", lambda _paths, name: str(fake))
    from spa.runlog import RunLog

    stderr = StringIO()
    log = RunLog(
        paths,
        "run",
        str(PROJECT / "ansible" / "splunk_install.yml"),
        agent=False,
        ansible_output=True,
        heartbeat_seconds=0,
        stream=stderr,
    )
    assert log.native_output is False
    rc = run_playbook(
        PROJECT / "ansible" / "splunk_install.yml",
        paths,
        command="run",
        ansible_output=True,
        run_log=log,
    )
    log.finish(rc)

    live = stderr.getvalue()
    # Ansible's own stdout is not echoed; this view is rebuilt from the JSONL events.
    assert "FORCE_COLOR" not in live
    assert "fatal: [idx1]" in live
    assert "sentinel" not in live
    assert "-auth ***" in live


def test_spa_logs_list_and_last(tmp_path):
    extra = min_env_vars(tmp_path)
    env_dir = Path(extra["SPA_ENV_DIR"])
    folder = env_dir / "logs"
    folder.mkdir()

    def write_run(run_id: str, start: str, msg: str) -> None:
        jsonl = folder / ("%s.jsonl" % run_id)
        jsonl.write_text(
            '{"time":"%s","msg":"%s"}\n' % (start, msg),
            encoding="utf-8",
        )
        (folder / ("%s.meta.json" % run_id)).write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "command": "deploy",
                    "rc": 0,
                    "log": str(jsonl),
                    "start": start,
                }
            ),
            encoding="utf-8",
        )

    write_run("older", "2026-09-17T17:02:00.123+02:00", "older-run")
    write_run("rid", "2026-09-18T15:00:00.000+02:00", "hello-run")
    listed = run_spa(["--no-agent", "logs"], extra_env=extra)
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.index("rid") < listed.stdout.index("older")
    last = run_spa(["--no-agent", "logs", "--last"], extra_env=extra)
    assert last.returncode == 0, last.stderr
    assert "hello-run" in last.stdout
    agent = run_spa(["--agent", "logs", "--last"], extra_env=extra)
    assert agent.returncode == 0, agent.stderr
    payload = json.loads(agent.stdout)
    assert payload["ok"] is True
    assert payload["data"]["log"]
    assert payload["data"]["run_id"] == "rid"
    assert "transcript" not in payload["data"]
    assert "hello-run" not in agent.stdout
    runs = list_runs(resolve_spa_paths(environ={**extra}))
    assert [row["run_id"] for row in runs] == ["rid", "older"]


def test_runlog_human_does_not_color_when_no_color(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit(
        {
            "kind": "host_result",
            "playbook": "splunk_install.yml",
            "task": "Install package",
            "host": "idx1",
            "status": "ok",
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert "\033[" not in text
    assert text.rstrip().endswith("ok")


def test_runlog_counts_results_and_skipped(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    for host, status in (
        ("idx1", "changed"),
        ("idx2", "changed"),
        ("idx1", "ok"),
        ("idx2", "skipped"),
        ("sh1", "skipped"),
    ):
        log.emit(
            {
                "kind": "host_result",
                "playbook": "splunk_install.yml",
                "play": "Install the splunk software",
                "task": "Install package",
                "host": host,
                "status": status,
            }
        )
    assert log.counters() == {
        "tasks": 1,
        "hosts": 3,
        "results": 5,
        "changed": 2,
        "skipped": 2,
        "failed": 0,
    }
    log.finish(0)
    text = stderr.getvalue()
    assert "tasks 1" in text
    assert "changed 2/5" in text
    assert "skipped 2" in text


def test_runlog_phase_line_status_word(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit(
        {
            "kind": "host_result",
            "playbook": "splunk_install.yml",
            "task": "Install package",
            "host": "idx1",
            "status": "failed",
            "msg": "boom",
        }
    )
    log.finish(1)
    assert stderr.getvalue().rstrip().endswith("failed")


def test_ansible_replay_and_logs_flag(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=False,
        ansible_output=True,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit({"kind": "play_start", "play": "Install the splunk software", "status": "ok"})
    log.emit({"kind": "task_start", "play": "Install the splunk software", "task": "Install package", "status": "ok"})
    log.emit(
        {
            "kind": "host_result",
            "play": "Install the splunk software",
            "task": "Install package",
            "host": "idx1",
            "status": "ok",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "play": "Install the splunk software",
            "task": "Install package",
            "host": "idx2",
            "status": "changed",
        }
    )
    log.emit(
        {
            "kind": "recap",
            "status": "ok",
            "recap": {"idx1": {"ok": 1, "changed": 0, "unreachable": 0, "failures": 0}},
        }
    )
    log.finish(0)
    live = stderr.getvalue()
    assert "PLAY [Install the splunk software]" in live
    assert "ok: [idx1]" in live
    assert "changed: [idx2]" in live
    assert "PLAY RECAP" in live
    from spa.runlog import replay_jsonl

    replayed = replay_jsonl(log.jsonl_path)
    assert "ok: [idx1]" in replayed
    dump = run_spa(
        ["--no-agent", "logs", "--last", "--ansible-output"],
        extra_env={"SPA_HOME": extra["SPA_HOME"], "SPA_ENV_DIR": extra["SPA_ENV_DIR"]},
    )
    assert dump.returncode == 0, dump.stderr
    assert "ok: [idx1]" in dump.stdout
    assert "hello-run" not in dump.stdout


TF_PLAN_FIXTURE = {
    "resource_changes": [
        {
            "address": 'aws_instance.splunk["idx1"]',
            "change": {
                "actions": ["update"],
                "before": {
                    "instance_type": "t3.large",
                    "root_block_device": [{"volume_size": 50, "volume_type": "gp3"}],
                },
                "after": {
                    "instance_type": "m5.xlarge",
                    "root_block_device": [{"volume_size": 100, "volume_type": "gp3"}],
                },
            },
        },
        {
            "address": 'aws_instance.splunk["uf2"]',
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {
                    "instance_type": "t3.medium",
                    "root_block_device": [{"volume_size": 30, "volume_type": "gp3"}],
                },
            },
        },
        {
            "address": "null_resource.readiness",
            "change": {"actions": ["create"], "before": None, "after": {}},
        },
    ]
}


def test_tf_plan_host_diffs_and_replay():
    from spa.tfchanges import compact_tf_host_bits, format_tf_replay, summarize_tf_plan_document

    summary = summarize_tf_plan_document(TF_PLAN_FIXTURE)
    hosts = {row["host"]: row for row in summary["hosts"]}
    assert hosts["idx1"]["action"] == "update"
    assert "instance_type" in hosts["idx1"]["fields"]
    assert "disk" in hosts["idx1"]["fields"]
    assert hosts["uf2"]["action"] == "create"
    bits = compact_tf_host_bits(summary)
    assert "update idx1 (instance_type, disk)" in bits
    assert "create uf2" in bits
    text = format_tf_replay(summary)
    assert "t3.large -> m5.xlarge" in text
    assert "50 -> 100" in text
    assert "null_resource.readiness" in text


def test_runlog_folds_tf_changes_into_phase_line(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "provision",
        "aws_provision",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 10, 2, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit({"task": "Run Terraform Plan", "status": "ok", "host": "localhost"})
    from spa.tfchanges import summarize_tf_plan_document

    log.attach_tf_plan(summarize_tf_plan_document(TF_PLAN_FIXTURE))
    log.finish(0)
    text = stderr.getvalue()
    assert "Terraform plan" in text
    assert "idx1" in text
    assert "uf2" in text
    assert "instance_type" in text
    assert text.rstrip().endswith("changed")


def test_compact_tf_bits_group_many_hosts():
    from spa.tfchanges import compact_tf_host_bits

    summary = {
        "hosts": [{"host": name, "action": "create", "fields": []} for name in ("cm", "idx1", "idx2", "sh", "uf")],
        "other": [],
    }
    bits = compact_tf_host_bits(summary)
    assert bits == "create 5: cm, idx1, idx2, +2"


def test_provision_phases_never_reopen(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    log = RunLog(
        paths,
        "provision",
        "aws_provision",
        agent=False,
        heartbeat_seconds=0,
        stream=StringIO(),
        clock=lambda: datetime(2026, 9, 17, 17, 10, 2, tzinfo=timezone(timedelta(hours=2))),
    )
    for task in (
        "Write terraform tfvars",
        "Run Terraform Plan",
        "Symlink terraform files",
        "Ensure instances are present",
        "Write terraform tfvars",
    ):
        log.emit({"kind": "host_result", "task": task, "status": "ok", "host": "localhost"})
    log.finish(0)
    events = [json.loads(line) for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()]
    starts = [row["phase"] for row in events if row.get("status") == "phase_start"]
    assert starts == ["tf_init", "tf_plan", "tf_apply"]


def test_live_phase_line_never_wraps(tmp_path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "60")
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "provision",
        "aws_provision",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 10, 2, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit({"kind": "host_result", "task": "Run Terraform Plan", "status": "ok", "host": "localhost"})
    from spa.tfchanges import summarize_tf_plan_document

    log.attach_tf_plan(summarize_tf_plan_document(TF_PLAN_FIXTURE))
    for host in ("cm", "idx1", "idx2", "sh", "uf"):
        log.emit({"kind": "host_result", "task": "Ensure instances are present", "status": "changed", "host": host})
    log.finish(0)
    raw = stderr.getvalue()
    from spa.runlog import _strip_ansi

    for chunk in _strip_ansi(raw).replace("\n", "\r").split("\r"):
        assert len(chunk) < 60, chunk


def _phase_ids(log: RunLog) -> list:
    ids = []
    for line in log.jsonl_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("status") == "phase_start":
            ids.append(row.get("phase"))
    return ids


def test_runlog_named_groups_allow_returning_after_baseconfig(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "ansible/deploy_site.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    log.emit(
        {
            "kind": "host_result",
            "playbook": "deploy_site.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup cluster manager role",
            "task": "Configure CM",
            "host": "cm",
            "status": "ok",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "playbook": "deploy_site.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup cluster manager role",
            "task": "Apply org_all_indexes",
            "role": "baseconfig_app",
            "tags": ["splunk_baseconfig"],
            "host": "cm",
            "status": "changed",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "playbook": "deploy_site.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup search head role",
            "task": "Configure SH",
            "host": "sh",
            "status": "ok",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "playbook": "deploy_site.yml",
            "play_file": "ansible/splunk_apps_deploy.yml",
            "play": "Deploy apps to Deployers",
            "role": "apps_deployer",
            "host": "ds",
            "status": "changed",
        }
    )
    log.finish(0)
    assert _phase_ids(log) == [
        "role_cluster_manager",
        "baseconfig",
        "role_search_head",
        "apps_shc",
    ]
    text = stderr.getvalue()
    assert "[6/10]" not in text
    assert "Cluster manager" in text
    assert "Baseconfig apps" in text
    assert "Search heads" in text
    assert "Search Head Cluster apps" in text


def test_runlog_upgrade_rolling_three_groups(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "run",
        "ansible/upgrade_idxc_rolling.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    for play, host in (
        ("Begin tasks", "cm"),
        ("Upgrade indexer", "idx1"),
        ("End tasks", "cm"),
    ):
        log.emit(
            {
                "kind": "host_result",
                "playbook": "upgrade_idxc_rolling.yml",
                "play_file": "ansible/upgrade_idxc_rolling.yml",
                "play": play,
                "task": play,
                "host": host,
                "status": "ok",
            }
        )
    log.finish(0)
    assert _phase_ids(log) == ["upgrade_idxc_begin", "upgrade_idxc_peers", "upgrade_idxc_end"]
    text = stderr.getvalue()
    assert "Run  Indexer rolling upgrade · begin" in text
    assert "Indexer rolling upgrade · peers" in text
    assert "Indexer rolling upgrade · end" in text
