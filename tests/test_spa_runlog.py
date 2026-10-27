"""Run transcripts, redaction, phase map, and spa logs."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pytest
import yaml

from spa.playbooks import run_playbook
from spa.paths import resolve_spa_paths
from spa.runlog import (
    RunLog,
    _strip_ansi,
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


def test_run_log_name_appends_playbook_stem(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    log = RunLog(
        paths,
        "run",
        "ansible/upgrade_splunk.yml",
        agent=True,
        heartbeat_seconds=0,
        stream=StringIO(),
        clock=lambda: datetime(2026, 10, 14, 18, 32, 16, tzinfo=timezone(timedelta(hours=2))),
    )
    assert log.run_id == "2026-10-14T183216+0200-run-upgrade_splunk"
    log.finish(0)


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


def test_ansible_output_events_are_timestamped_ordered_and_replayed(tmp_path):
    from spa.runlog import replay_jsonl

    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    log = RunLog(
        paths,
        "run",
        "ansible/splunk_install.yml",
        agent=True,
        heartbeat_seconds=0,
        stream=StringIO(),
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )

    log.consume_ansible_output("PLAY [Install]\n")
    log.consume_ansible_output("\n")
    log.consume_ansible_output("\033[0;32mok: [idx1] => sentinel\033[0m\n")
    log.finish(0)

    rows = [
        json.loads(line)
        for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    output = [row for row in rows if row.get("kind") == "ansible_output"]
    assert [row["sequence"] for row in output] == [1, 2, 3]
    assert [row["text"] for row in output] == [
        "PLAY [Install]",
        "",
        "ok: [idx1] => sentinel",
    ]
    assert all(row["source"] == "ansible" for row in output)
    assert all(row["time"] == "2026-09-17T17:02:00.000+02:00" for row in output)
    assert "\033[" not in log.jsonl_path.read_text(encoding="utf-8")
    assert replay_jsonl(log.jsonl_path) == (
        "PLAY [Install]\n\nok: [idx1] => sentinel\n"
    )


def test_ansible_output_timestamps_and_color_are_display_only(tmp_path):
    from spa.runlog import replay_jsonl

    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    log = RunLog(
        paths,
        "run",
        "ansible/splunk_install.yml",
        agent=True,
        heartbeat_seconds=0,
        stream=StringIO(),
        clock=lambda: datetime(2026, 9, 17, 17, 2, 1, 123000, tzinfo=timezone(timedelta(hours=2))),
    )
    log.consume_ansible_output("PLAY [Install]\n")
    log.consume_ansible_output("\n")
    log.consume_ansible_output("ok: [idx1]\n")
    log.consume_ansible_output("changed: [idx1]\n")
    log.consume_ansible_output("fatal: [idx1]: FAILED!\n")
    log.consume_ansible_output("ERROR! missing playbook\n")
    log.finish(0)

    stored = [
        json.loads(line)
        for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["text"] for row in stored] == [
        "PLAY [Install]",
        "",
        "ok: [idx1]",
        "changed: [idx1]",
        "fatal: [idx1]: FAILED!",
        "ERROR! missing playbook",
    ]
    assert "\033[" not in log.jsonl_path.read_text(encoding="utf-8")
    stamped = replay_jsonl(log.jsonl_path, timestamps=True)
    assert stamped == (
        "17:02:01.123+02:00  PLAY [Install]\n"
        "\n"
        "17:02:01.123+02:00  ok: [idx1]\n"
        "17:02:01.123+02:00  changed: [idx1]\n"
        "17:02:01.123+02:00  fatal: [idx1]: FAILED!\n"
        "17:02:01.123+02:00  ERROR! missing playbook\n"
    )
    colored = replay_jsonl(log.jsonl_path, timestamps=True, color=True)
    assert colored.startswith("17:02:01.123+02:00  \033[36mPLAY [Install]\033[0m\n")
    assert "\033[32mok: [idx1]\033[0m" in colored
    assert "\033[33mchanged: [idx1]\033[0m" in colored
    assert "\033[31mfatal: [idx1]: FAILED!\033[0m" in colored
    assert "\033[31mERROR! missing playbook\033[0m" in colored
    assert "\033[36m17:02:01.123" not in colored


def test_follow_ansible_output_waits_for_native_events(tmp_path):
    from spa.runlog import follow_jsonl

    path = tmp_path / "run.jsonl"
    rows = [
        {"kind": "play_start", "play": "Install", "status": "running"},
        {"kind": "host_result", "task": "Package", "host": "idx1", "status": "ok"},
        {"kind": "ansible_output", "text": "PLAY [Install]", "sequence": 1},
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = StringIO()

    follow_jsonl(path, idle_passes=1, sleep_s=0, stream=output, ansible_output=True)

    assert output.getvalue() == "PLAY [Install]\n"


def test_follow_ctrl_c_exits_quietly(tmp_path, monkeypatch):
    from spa.runlog import follow_jsonl

    path = tmp_path / "run.jsonl"
    path.write_text('{"kind":"task_start","task":"Check"}\n', encoding="utf-8")

    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("spa.runlog.time.sleep", interrupt)
    output = StringIO()
    assert follow_jsonl(path, idle_passes=-1, sleep_s=0.2, stream=output) == 130
    assert "Traceback" not in output.getvalue()


def test_follow_completed_legacy_run_replays_with_infinite_follow(tmp_path, monkeypatch):
    from spa.runlog import follow_jsonl

    path = tmp_path / "legacy.jsonl"
    path.write_text(
        json.dumps({"kind": "play_start", "play": "Legacy", "status": "running"})
        + "\n",
        encoding="utf-8",
    )
    path.with_name("legacy.meta.json").write_text(
        json.dumps({"rc": 0}) + "\n",
        encoding="utf-8",
    )
    output = StringIO()

    def stop_after_first_pass(_seconds):
        raise RuntimeError("stop follow")

    monkeypatch.setattr("spa.runlog.time.sleep", stop_after_first_pass)
    with pytest.raises(RuntimeError, match="stop follow"):
        follow_jsonl(path, idle_passes=-1, sleep_s=0, stream=output, ansible_output=True)

    assert "PLAY [Legacy]" in output.getvalue()


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


@pytest.mark.parametrize("playbook", sorted((PROJECT / "ansible").glob("*.yml")))
def test_first_party_root_playbooks_have_compact_titles(playbook):
    from spa.runlog import group_title

    payload = yaml.safe_load(playbook.read_text(encoding="utf-8")) or []
    plays = [row for row in payload if isinstance(row, dict) and "hosts" in row]
    imports = [row for row in payload if isinstance(row, dict) and "import_playbook" in row]
    assert plays or imports, playbook.name
    for play in plays:
        name = str(play.get("name") or "").strip()
        assert name, playbook.name
        phase = map_phase(
            command="run",
            playbook=playbook.name,
            play_file=str(playbook),
            play=name,
        )
        assert phase, "%s: %s" % (playbook.name, name)
        assert group_title(phase), "%s: %s" % (playbook.name, name)


def test_map_phase_app_overlays_and_upgrade():
    from spa.runlog import group_title

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
        map_phase(
            command="run",
            playbook="upgrade_idxc_rolling.yml",
            play="Upgrade indexer",
            host="idx1",
            kind="host_start",
        )
        == "upgrade_idxc_peers:idx1"
    )
    assert group_title("upgrade_idxc_peers:idx1") == "Indexer rolling upgrade · idx1"
    assert group_title("upgrade_idxc_begin") == "Indexer rolling upgrade · Begin"
    assert group_title("upgrade_step:disable boot start") == (
        "Upgrade Splunk · Disable boot start"
    )
    assert group_title("upgrade_distributed_cm:backup splunk etc") == (
        "Upgrade cluster manager · Backup splunk etc"
    )
    assert group_title("apps_ds") == "App deployment · Deployment Server apps"
    assert (
        map_phase(
            command="run",
            playbook="upgrade_shc_rolling.yml",
            play="Upgrade search head",
            host="sh1",
            kind="host_start",
        )
        == "upgrade_shc_members:sh1"
    )
    assert group_title("upgrade_shc_members:sh1") == "Search head rolling upgrade · sh1"
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
    assert "Provision  VM idx1  Tasks 3" in text
    assert text.rstrip().endswith("ok")


def test_ansible_warnings_do_not_open_a_group(tmp_path):
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
    )
    log.consume_callback_line(
        "[WARNING]: Could not match supplied host pattern, ignoring: role_deployer\n"
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
    log.consume_callback_line("[WARNING]: SELinux state temporarily changed\n")
    log.finish(0)
    text = stderr.getvalue()
    assert "Deploy site" not in text
    assert "[WARNING]" not in text
    assert "Deploy  Splunk install" in text
    events = [json.loads(line) for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()]
    # The warnings stay in the transcript and in the Ansible-style replay.
    notes = [row for row in events if row.get("kind") == "note"]
    assert len(notes) == 2
    assert all("phase" not in row or row["phase"] == "binary" for row in notes)
    from spa.runlog import render_replay_text

    assert "[WARNING]: SELinux state temporarily changed" in render_replay_text(events)


def test_ansible_hard_error_on_stderr_is_shown(tmp_path):
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
    )
    log.consume_callback_line("ERROR! the playbook: missing.yml could not be found\n")
    log.finish(1)
    assert "missing.yml could not be found" in stderr.getvalue()
    assert log.saw_failure is True


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


def test_agent_phase_change_is_one_plain_line(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    stderr = StringIO()
    log = RunLog(
        paths,
        "deploy",
        "",
        agent=True,
        heartbeat_seconds=0,
        stream=stderr,
    )
    log.emit(
        {
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup cluster manager role",
            "kind": "host_start",
            "task": "Configure CM",
            "host": "cm",
            "status": "running",
        }
    )
    log.emit({"kind": "heartbeat", "status": "heartbeat"})
    log.emit({"kind": "heartbeat", "status": "heartbeat"})
    log.emit(
        {
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/splunk_setup_conf.yml",
            "kind": "host_start",
            "task": "Write server.conf",
            "host": "cm",
            "status": "running",
        }
    )
    lines = [line for line in stderr.getvalue().splitlines() if line.strip()]
    assert lines == [
        "Configuring the cluster manager.",
        "Configuring Splunk.",
    ]
    assert all(not line.startswith("{") for line in lines)


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
            "kind": "host_start",
            "task": "Download the splunk archive from splunk.com",
            "host": "idx1",
            "status": "running",
        }
    )
    log.emit({"kind": "heartbeat", "status": "heartbeat"})
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
    assert "password=secret" not in err
    plain = [line for line in err.splitlines() if line.strip() and not line.startswith("{")]
    assert plain[0] == "Downloading Splunk on idx1."
    assert plain.count("Downloading Splunk on idx1.") == 1
    events = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
    kinds = [row.get("status") for row in events]
    assert "running" not in kinds
    assert "failed" in kinds
    assert any(row.get("host") == "idx1" and row.get("task") == "Boom" for row in events)
    transcript = log.jsonl_path.read_text(encoding="utf-8")
    assert "password=secret" in transcript
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


def test_compact_tty_shows_current_host_and_task_only_while_running(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "run",
        "ansible/custom_lab.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    event = {
        "playbook": "custom_lab.yml",
        "play": "Maintain lab",
        "task": "Call check_splunk_version",
        "task_file": "ansible/roles/splunk_software/tasks/check_splunk_version.yml",
        "host": "idx1",
    }

    log.emit({**event, "kind": "host_start", "status": "running"})
    running = stderr.getvalue()
    assert "idx1" in running
    assert "check splunk version" in running.lower()

    log.emit({**event, "kind": "host_result", "status": "ok"})
    log.finish(0)
    settled = _plain_line(stderr.getvalue().splitlines()[-1])
    assert "Maintain lab" in settled
    assert "idx1" not in settled
    assert "check splunk version" not in settled.lower()
    assert settled.endswith("ok")


def test_run_playbook_fake_ansible(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "assert os.environ['ANSIBLE_STDOUT_CALLBACK'] == 'default'\n"
        "assert 'spa_jsonl' in os.environ['ANSIBLE_CALLBACKS_ENABLED'].split(',')\n"
        "assert os.environ['PYTHONUNBUFFERED'] == '1'\n"
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
    assert '"kind": "ansible_output"' in body
    assert '"text": "PLAY [native output]"' in body
    meta = json.loads(log.meta_path.read_text(encoding="utf-8"))
    assert meta["rc"] == 0
    assert meta["run_id"] == log.run_id
    assert str(log.jsonl_path) == meta["log"]
    envelope_err = stderr.getvalue()
    assert "PLAY [" not in envelope_err


def test_run_playbook_passes_and_records_ansible_verbosity(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "assert sys.argv[-1] == '-vvv', sys.argv\n"
        "print('ansible verbosity 3')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setattr("spa.playbooks.tool_path", lambda _paths, name: str(fake))
    log = RunLog(
        paths,
        "run",
        str(PROJECT / "ansible" / "splunk_install.yml"),
        agent=True,
        heartbeat_seconds=0,
        stream=StringIO(),
        verbosity=3,
    )

    rc = run_playbook(
        PROJECT / "ansible" / "splunk_install.yml",
        paths,
        command="run",
        agent=True,
        verbosity=3,
        run_log=log,
    )
    log.finish(rc)

    assert rc == 0
    meta = json.loads(log.meta_path.read_text(encoding="utf-8"))
    assert meta["verbosity"] == 3
    assert "ansible verbosity 3" in log.jsonl_path.read_text(encoding="utf-8")


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


def test_run_playbook_native_output_is_live_and_stored_unredacted(tmp_path, monkeypatch):
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
    # Labs transcripts preserve the native line until issue 88 adds secret handling.
    transcript = log.jsonl_path.read_text(encoding="utf-8")
    assert "sentinel" in transcript
    assert '"task": "List user"' in transcript


def test_ansible_output_without_verbose_shows_captured_native_output(tmp_path, monkeypatch):
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
    # --ansible-output shows the native callback without increasing verbosity.
    assert "FORCE_COLOR=0" in live
    assert "fatal: [idx1]" in live
    assert "-auth admin:sentinel" in live


def test_live_ansible_output_can_force_color_and_show_stored_time(tmp_path, monkeypatch):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ANSIBLE_NOCOLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    fake = tmp_path / "ansible-playbook"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "print('FORCE_COLOR=' + os.environ['ANSIBLE_FORCE_COLOR'])\n"
        "print('ok: [idx1]')\n",
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
        timestamps=True,
        color=True,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 1, 123000, tzinfo=timezone(timedelta(hours=2))),
    )
    rc = run_playbook(
        PROJECT / "ansible" / "splunk_install.yml",
        paths,
        command="run",
        ansible_output=True,
        timestamps=True,
        color=True,
        run_log=log,
    )
    log.finish(rc)

    live = stderr.getvalue()
    assert "FORCE_COLOR=1" in live
    assert "17:02:01.123+02:00  ok: [idx1]" in live
    stored = log.jsonl_path.read_text(encoding="utf-8")
    assert '"text": "ok: [idx1]"' in stored
    assert "17:02:01.123+02:00  ok" not in stored


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
    listed = run_spa(["--no-agent", "logs", "list"], extra_env=extra)
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
    assert "Tasks 1" in text
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


def test_logs_can_show_timestamps_and_color(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    log = RunLog(
        paths,
        "run",
        "ansible/splunk_install.yml",
        agent=True,
        heartbeat_seconds=0,
        stream=StringIO(),
        clock=lambda: datetime(2026, 9, 17, 17, 2, 1, 123000, tzinfo=timezone(timedelta(hours=2))),
    )
    log.consume_ansible_output("TASK [Install package]\n")
    log.consume_ansible_output("ok: [idx1]\n")
    log.finish(0)

    result = run_spa(
        ["--no-agent", "logs", "--last", "--ansible-output", "--timestamps", "--color"],
        env=extra,
    )
    assert result.returncode == 0, result.stderr
    assert "17:02:01.123+02:00  \033[36mTASK [Install package]\033[0m" in result.stdout
    assert "17:02:01.123+02:00  \033[32mok: [idx1]\033[0m" in result.stdout


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


def _plain_line(text: str) -> str:
    """Status checks ignore TTY color, which a dirty shell can turn off."""
    return _strip_ansi(text).strip()


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
    assert _phase_ids(log) == [
        "upgrade_idxc_begin",
        "upgrade_idxc_peers:idx1",
        "upgrade_idxc_end",
    ]
    text = stderr.getvalue()
    assert "Run  Indexer rolling upgrade · Begin" in text
    assert "Indexer rolling upgrade · idx1" in text
    assert "Indexer rolling upgrade · End" in text


def test_rolling_work_line_tasks_sits_under_the_parent_step(tmp_path):
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
        clock=lambda: datetime(2026, 10, 15, 10, 15, 20, tzinfo=timezone(timedelta(hours=2))),
    )
    base = {
        "playbook": "upgrade_idxc_rolling.yml",
        "play_file": "ansible/upgrade_idxc_rolling.yml",
        "play": "Upgrade indexer",
        "host": "idx1",
    }
    steps = (
        (
            "ansible/roles/splunk_software/tasks/upgrade_idxc_rolling_upgrade.yml",
            "splunk_software : Call get_idxc_peerids",
            "ok",
        ),
        (
            "ansible/roles/splunk_software/tasks/get_idxc_peerids.yml",
            "splunk_software : Fetch peer ids",
            "ok",
        ),
        (
            "ansible/roles/splunk_software/tasks/upgrade_idxc_rolling_upgrade.yml",
            "splunk_software : Set idxc peerid",
            "ok",
        ),
    )
    for task_file, task, status in steps:
        log.emit(
            {
                **base,
                "kind": "host_result",
                "task_file": task_file,
                "task": task,
                "status": status,
            }
        )
    log.finish(0)
    settled = [line.strip() for line in stderr.getvalue().splitlines() if line.strip()]
    parent = next(line for line in settled if "Get idxc peerids" in line and line.rstrip().endswith("ok"))
    work = next(line for line in settled if "· idx1   Tasks" in line)
    assert parent.index("Get") == work.index("Tasks")


@pytest.mark.parametrize(
    ("playbook", "play", "phase_prefix", "title"),
    [
        (
            "upgrade_idxc_rolling.yml",
            "Upgrade indexer",
            "upgrade_idxc_peers",
            "Indexer rolling upgrade",
        ),
        (
            "upgrade_shc_rolling.yml",
            "Upgrade search head cluster member",
            "upgrade_shc_members",
            "Search head rolling upgrade",
        ),
    ],
)
def test_runlog_upgrade_rolling_settles_each_peer(
    tmp_path, playbook, play, phase_prefix, title
):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "run",
        "ansible/" + playbook,
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    for host in ("idx1", "idx2"):
        event = {
            "playbook": playbook,
            "play_file": "ansible/" + playbook,
            "play": play,
            "task": "Call upgrade_idxc_rolling_check",
            "host": host,
        }
        log.emit({**event, "kind": "host_start", "status": "running"})
        log.emit({**event, "kind": "host_result", "status": "changed"})
    log.finish(0)

    assert _phase_ids(log) == [
        phase_prefix + ":idx1",
        phase_prefix + ":idx2",
    ]
    text = stderr.getvalue()
    assert title + " · idx1" in text
    assert title + " · idx2" in text


def test_upgrade_rolling_play_start_does_not_open_coarse_group(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    log = RunLog(
        paths,
        "run",
        "ansible/upgrade_idxc_rolling.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=StringIO(),
    )
    base = {
        "playbook": "upgrade_idxc_rolling.yml",
        "play_file": "ansible/upgrade_idxc_rolling.yml",
        "play": "Upgrade indexer",
        "task": "Call upgrade_idxc_rolling_check",
    }
    log.emit({**base, "kind": "play_start", "status": "running"})
    log.emit({**base, "kind": "task_start", "status": "running"})
    log.emit({**base, "kind": "host_start", "host": "idx1", "status": "running"})
    log.emit({**base, "kind": "host_result", "host": "idx1", "status": "changed"})
    log.finish(0)

    assert _phase_ids(log) == ["upgrade_idxc_peers:idx1"]


def test_parallel_upgrade_splunk_shares_one_step_line(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "run",
        "ansible/upgrade_splunk.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
    )
    base = {
        "playbook": "upgrade_splunk.yml",
        "play_file": "ansible/upgrade_splunk.yml",
        "play": "Upgrade splunk software",
    }
    for host in ("idx1", "idx2"):
        log.emit(
            {
                **base,
                "kind": "host_start",
                "host": host,
                "task": "Display upgrade version info",
                "status": "running",
            }
        )
    for host, current in (("idx1", "9.1.2"), ("idx2", "9.2.0")):
        log.emit(
            {
                **base,
                "kind": "host_result",
                "host": host,
                "task": "Display upgrade version info",
                "status": "ok",
                "msg": "Upgrade splunk from version '%s' to version '9.3.1'" % current,
            }
        )
    log.finish(0)

    settled = [
        _plain_line(line)
        for line in stderr.getvalue().splitlines()
        if _plain_line(line).endswith("ok")
    ]
    assert len(settled) == 1
    assert "Upgrade Splunk · Display upgrade version info" in settled[0]
    assert "9.2.0 → 9.3.1" in settled[0]
    assert "· idx" not in settled[0]
    rows = [
        json.loads(line)
        for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    ended = next(row for row in rows if row.get("status") == "phase_end")
    assert ended["hosts_n"] == 2
    assert ended["phase"] == "upgrade_step:Display upgrade version info"


def test_upgrade_progress_keeps_current_and_target_versions_on_settled_line(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "run",
        "ansible/upgrade_splunk.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 9, 17, 17, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    base = {
        "playbook": "upgrade_splunk.yml",
        "play_file": "ansible/upgrade_splunk.yml",
        "play": "Upgrade splunk software",
        "host": "idx1",
    }
    log.emit(
        {
            **base,
            "kind": "host_start",
            "task": "Display upgrade version info",
            "status": "running",
        }
    )
    log.emit(
        {
            **base,
            "kind": "host_result",
            "task": "Display upgrade version info",
            "status": "ok",
            "msg": "Upgrade splunk from version '9.1.2' to version '9.3.1'",
        }
    )
    log.finish(0)

    rows = [
        json.loads(line)
        for line in log.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    version = next(row for row in rows if row.get("upgrade_from"))
    assert version["upgrade_product"] == "splunk"
    assert version["upgrade_from"] == "9.1.2"
    assert version["upgrade_to"] == "9.3.1"
    settled = _plain_line(stderr.getvalue().splitlines()[-1])
    assert "9.1.2 → 9.3.1" in settled
    assert settled.endswith("ok")


def test_upgrade_progress_recognizes_equal_version_as_current():
    from spa.runlog import upgrade_version_fields

    fields = upgrade_version_fields(
        "Inform about not upgrading",
        "Installed version '9.3.1' is equal to upgrade version '9.3.1' -> nothing to upgrade",
    )
    assert fields == {
        "upgrade_product": "splunk",
        "upgrade_from": "9.3.1",
        "upgrade_to": "9.3.1",
        "upgrade_current": True,
    }
    prefixed = upgrade_version_fields(
        "splunk_software : Display upgrade version info",
        "Upgrade splunkforwarder from version '10.4.0' to version '10.4.2'",
    )
    assert prefixed["upgrade_product"] == "splunkforwarder"
    assert prefixed["upgrade_from"] == "10.4.0"
    assert prefixed["upgrade_to"] == "10.4.2"


def test_upgrade_includes_settle_a_line_per_step_and_keep_versions(tmp_path):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})

    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = RunLog(
        paths,
        "run",
        "ansible/upgrade_splunk.yml",
        agent=False,
        heartbeat_seconds=0,
        stream=stderr,
        clock=lambda: datetime(2026, 10, 14, 22, 0, 59, tzinfo=timezone(timedelta(hours=2))),
    )
    base = {
        "playbook": "upgrade_splunk.yml",
        "play_file": "ansible/upgrade_splunk.yml",
        "play": "Upgrade splunk software",
    }
    version_msg = "Upgrade splunk from version '10.4.0' to version '10.4.2'"
    steps = (
        (
            "ansible/roles/splunk_software/tasks/upgrade.yml",
            "splunk_software : Display upgrade version info",
            "ok",
            version_msg,
        ),
        (
            "ansible/roles/splunk_software/tasks/upgrade.yml",
            "splunk_software : Backup splunk etc",
            "changed",
            "Backup splunk etc",
        ),
        (
            "ansible/roles/splunk_software/tasks/set_splunk_installed_version.yml",
            "splunk_software : Set installed version",
            "ok",
            "found splunk version 10.4.2",
        ),
        (
            "ansible/roles/splunk_software/tasks/upgrade.yml",
            "splunk_software : Call add_custom_policykit",
            "skipped",
            "splunk_software : Call add_custom_policykit",
        ),
        (
            "ansible/roles/splunk_software/tasks/upgrade.yml",
            "splunk_software : Start splunk by service control",
            "changed",
            "Start splunk by service control",
        ),
    )
    for task_file, task, status, msg in steps:
        log.emit({**base, "kind": "task_start", "task_file": task_file, "task": task, "status": "running"})
        for host in ("cm", "idx1", "idx2"):
            log.emit(
                {
                    **base,
                    "kind": "host_result",
                    "task_file": task_file,
                    "task": task,
                    "host": host,
                    "status": status,
                    "msg": msg if host == "cm" else version_msg if "Display upgrade" in task else msg,
                }
            )
    log.finish(0)

    assert _phase_ids(log) == [
        "upgrade_step:Display upgrade version info",
        "upgrade_step:Backup splunk etc",
        "upgrade_step:Start splunk by service control",
    ]
    settled = [
        _plain_line(line)
        for line in stderr.getvalue().splitlines()
        if _plain_line(line).endswith(("ok", "changed"))
    ]
    version_lines = [line for line in settled if "10.4.0 → 10.4.2" in line]
    assert len(version_lines) == 1
    assert "Display upgrade version info" in version_lines[0]
    assert any("Backup splunk etc" in line for line in settled)
    assert any("Start splunk by service control" in line for line in settled)
    assert not any("policykit" in line.lower() for line in settled)
    assert not any("Set installed version" in line for line in settled)
    assert not any("· idx" in line or "· cm" in line for line in settled)


def test_rolling_upgrade_appends_include_step_without_moving_begin_end():
    from spa.runlog import group_title

    assert (
        map_phase(command="run", playbook="upgrade_idxc_rolling.yml", play="Begin tasks")
        == "upgrade_idxc_begin"
    )
    assert (
        map_phase(command="run", playbook="upgrade_idxc_rolling.yml", play="End tasks")
        == "upgrade_idxc_end"
    )
    phase = map_phase(
        command="run",
        playbook="upgrade_idxc_rolling.yml",
        play_file="ansible/upgrade_idxc_rolling.yml",
        play="Upgrade indexer",
        task_file="ansible/roles/splunk_software/tasks/upgrade.yml",
        task="splunk_software : Upload and extract the splunk software",
        host="idx1",
        kind="host_result",
    )
    assert phase == "upgrade_idxc_peers:idx1:Upload and extract the splunk software"
    assert group_title(phase) == (
        "Indexer rolling upgrade · idx1 · Upload and extract the splunk software"
    )
    assert (
        map_phase(
            command="run",
            playbook="upgrade_shc_rolling.yml",
            play_file="ansible/upgrade_shc_rolling.yml",
            play="Upgrade search head",
            task_file="ansible/roles/splunk_software/tasks/upgrade_shc_rolling_upgrade.yml",
            task="splunk_software : Call upgrade",
            host="sh1",
            kind="host_result",
        )
        == "upgrade_shc_members:sh1:upgrade"
    )


def test_deploy_include_does_not_open_an_upgrade_step():
    assert (
        map_phase(
            command="deploy",
            playbook="ansible/deploy_site.yml",
            play_file="ansible/splunk_apps_deploy.yml",
            play="Deploy apps to Deployment Server",
            task_file="ansible/roles/apps_deployment_server/tasks/process_ds_app.yml",
            task="Process one app",
            host="cm",
            kind="host_result",
        )
        == "apps_ds"
    )


def _phase_log(tmp_path, command="provision", playbook="aws_provision", agent=False, stream=None):
    extra = min_env_vars(tmp_path)
    paths = resolve_spa_paths(environ={**extra})
    return RunLog(
        paths,
        command,
        playbook,
        agent=agent,
        heartbeat_seconds=0,
        stream=stream if stream is not None else StringIO(),
        clock=lambda: datetime(2026, 9, 17, 17, 10, 2, tzinfo=timezone(timedelta(hours=2))),
    )


def test_phase_sentence_emits_once(tmp_path):
    log = _phase_log(tmp_path)
    event = {
        "command": "provision",
        "phase": "tf_apply",
        "status": "running",
        "kind": "host_start",
        "task": "Apply Terraform Configuration",
        "host": "shidx",
    }
    assert log.phase_sentence(event) == "Creating shidx."
    assert log.phase_sentence(event) is None
    log.finish(0)


def test_empty_role_play_does_not_name_the_role(tmp_path):
    """A setup play with no matching hosts is not a role in this environment."""
    stderr = StringIO()
    log = _phase_log(
        tmp_path,
        command="deploy",
        playbook="ansible/deploy_site.yml",
        agent=True,
        stream=stderr,
    )
    log.emit(
        {
            "kind": "play_start",
            "status": "ok",
            "playbook": "ansible/splunk_setup_roles.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup heavy forwarder role",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "playbook": "ansible/splunk_setup_roles.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup universal forwarder role",
            "task": "universal_forwarder : Configure outputs",
            "host": "uf",
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert "heavy forwarder" not in text.lower()
    assert "Configuring universal forwarders." in text


def test_phase_sentence_deploy_and_run(tmp_path):
    deploy = _phase_log(tmp_path, command="deploy", playbook="ansible/deploy_site.yml")
    cluster_manager = {
        "command": "deploy",
        "phase": "role_cluster_manager",
        "status": "phase_start",
        "kind": "phase_start",
        "host": "cm",
    }
    assert deploy.phase_sentence(cluster_manager) == "Configuring the cluster manager."
    assert deploy.phase_sentence(cluster_manager) is None
    assert (
        deploy.phase_sentence(
            {"command": "deploy", "phase": "conf", "status": "phase_start", "kind": "phase_start"}
        )
        == "Configuring Splunk."
    )
    assert (
        deploy.phase_sentence(
            {"command": "deploy", "phase": "apps_cm", "status": "phase_start", "kind": "phase_start"}
        )
        == "Installing cluster manager apps."
    )
    assert (
        deploy.phase_sentence(
            {
                "command": "deploy",
                "phase": "apps_premium_itsi",
                "status": "phase_start",
                "kind": "phase_start",
            }
        )
        == "Installing ITSI."
    )
    deploy.finish(0)

    upgrade = _phase_log(tmp_path, command="run", playbook="ansible/upgrade_idxc_rolling.yml")
    stop = {
        "command": "run",
        "phase": "upgrade_idxc_peers:idx1:Stop splunk",
        "host": "idx1",
        "status": "phase_start",
        "kind": "phase_start",
    }
    assert upgrade.phase_sentence(stop) == "Upgrading indexer idx1."
    start = dict(stop)
    start["phase"] = "upgrade_idxc_peers:idx1:Start splunk"
    assert upgrade.phase_sentence(start) is None
    upgrade.finish(0)

    restart = _phase_log(tmp_path, command="run", playbook="ansible/splunk_restart.yml")
    assert (
        restart.phase_sentence(
            {
                "command": "run",
                "playbook": "splunk_restart",
                "phase": "play:Restart splunk",
                "host": "shidx",
                "status": "phase_start",
                "kind": "phase_start",
            }
        )
        == "Restarting Splunk on shidx."
    )
    restart.finish(0)

    custom = _phase_log(tmp_path, command="run", playbook="ansible/splunk_cli.yml")
    play = {
        "command": "run",
        "playbook": "splunk_cli",
        "phase": "play:Run a splunk command",
        "phase_title": "Run a splunk command",
        "status": "phase_start",
        "kind": "phase_start",
    }
    assert custom.phase_sentence(play) == "Running Run a splunk command."
    assert custom.phase_sentence(play) is None
    custom.finish(0)


def test_agent_render_writes_phase_sentences_to_stderr(tmp_path, capsys):
    stderr = StringIO()
    log = _phase_log(tmp_path, agent=True, stream=stderr)
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Apply Terraform Configuration",
            "host": "shidx",
            "playbook": "aws_provision.yml",
        }
    )
    for _ in range(2):
        log.emit(
            {
                "status": "heartbeat",
                "kind": "heartbeat",
                "phase": "tf_apply",
                "task": "Apply Terraform Configuration",
                "host": "shidx",
            }
        )
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "task": "Wait for SSH port to be available on all hosts",
            "host": "shidx",
            "playbook": "aws_wait_hosts.yml",
        }
    )
    log.finish(0)
    assert stderr.getvalue() == "Creating shidx.\nshidx is up.\n"
    assert capsys.readouterr().out == ""


def test_agent_render_deploy_sentences_skip_heartbeats(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, command="deploy", playbook="ansible/deploy_site.yml", agent=True, stream=stderr)
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/setup_common.yml",
            "task": "Install packages",
            "host": "shidx",
        }
    )
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "os", "host": "shidx"})
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/splunk_install.yml",
            "task": "Download the splunk archive from splunk.com",
            "host": "shidx",
        }
    )
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "binary", "host": "shidx"})
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/splunk_setup_roles.yml",
            "play": "Setup cluster manager role",
            "task": "Configure CM",
            "host": "cm",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/splunk_setup_conf.yml",
            "task": "Write server.conf",
            "host": "cm",
        }
    )
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "conf"})
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/splunk_apps_deploy.yml",
            "play": "Deploy apps to Cluster Managers",
            "task": "Install apps",
            "host": "cm",
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert '"type": "progress"' not in text
    assert text == (
        "Hosts are already prepared.\n"
        "Downloading Splunk on shidx.\n"
        "Configuring the cluster manager.\n"
        "The cluster manager is already configured.\n"
        "Configuring Splunk.\n"
        "Installing cluster manager apps.\n"
    )


def test_agent_render_run_restart_sentence(tmp_path):
    stderr = StringIO()
    log = _phase_log(
        tmp_path,
        command="run",
        playbook="ansible/splunk_restart.yml",
        agent=True,
        stream=stderr,
    )
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "playbook": "ansible/splunk_restart.yml",
            "play": "Restart splunk",
            "task": "Call restart splunk from role splunk_common",
            "host": "shidx",
        }
    )
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "play:Restart splunk", "host": "shidx"})
    log.finish(0)
    assert stderr.getvalue() == "Restarting Splunk on shidx.\n"


def test_agent_creating_uses_plan_hosts_when_apply_is_localhost(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, agent=True, stream=stderr)
    log.attach_tf_plan(
        {
            "hosts": [
                {"host": "shidx", "action": "create", "fields": []},
                {"host": "idx1", "action": "create", "fields": []},
            ],
            "other": [],
        }
    )
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Apply Terraform Configuration",
            "host": "localhost",
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert '"type": "progress"' not in text
    assert "Creating shidx.\n" in text
    assert "Creating idx1.\n" in text
    assert text.count("Creating shidx.") == 1
    assert text.count("Creating idx1.") == 1


def test_agent_destroying_uses_plan_hosts_when_destroy_is_localhost(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, command="destroy", playbook="aws_destroy", agent=True, stream=stderr)
    log.attach_tf_plan(
        {"hosts": [{"host": "shidx", "action": "delete", "fields": []}], "other": []}
    )
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Destroy Terraform Infrastructure",
            "host": "localhost",
        }
    )
    log.finish(0)
    assert stderr.getvalue().count("Destroying shidx.") == 1


def test_agent_destroy_names_inventory_or_config_hosts(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, command="destroy", playbook="aws_destroy", agent=True, stream=stderr)
    (log.paths.inventory_dir / "hosts").write_text(
        "cm ansible_host=10.0.0.1\nidx1 ansible_host=10.0.0.2\n# comment\n",
        encoding="utf-8",
    )
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Destroy Terraform Infrastructure",
            "host": "localhost",
            "playbook": "aws_destroy.yml",
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert text.count("Destroying cm.") == 1
    assert text.count("Destroying idx1.") == 1
    assert '"type": "progress"' not in text

    config_stderr = StringIO()
    config_log = _phase_log(
        tmp_path / "config-only",
        command="destroy",
        playbook="aws_destroy",
        agent=True,
        stream=config_stderr,
    )
    config_log.paths.config_file.write_text(
        "splunk_hosts:\n  - name: shidx\n    roles: [search_head]\n",
        encoding="utf-8",
    )
    config_log.emit(
        {
            "kind": "phase_start",
            "status": "phase_start",
            "phase": "tf_apply",
            "command": "destroy",
        }
    )
    config_log.finish(0)
    assert config_stderr.getvalue().count("Destroying shidx.") == 1


def test_agent_twenty_heartbeats_keep_one_sentence(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, agent=True, stream=stderr)
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Apply Terraform Configuration",
            "host": "shidx",
            "playbook": "aws_provision.yml",
        }
    )
    for _ in range(20):
        log.emit(
            {
                "status": "heartbeat",
                "kind": "heartbeat",
                "phase": "tf_apply",
                "task": "Apply Terraform Configuration",
                "host": "shidx",
            }
        )
    log.finish(0)
    assert stderr.getvalue() == "Creating shidx.\n"


def test_agent_heartbeat_does_not_repeat_the_sentence(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, agent=True, stream=stderr)
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Apply Terraform Configuration",
            "host": "shidx",
            "playbook": "aws_provision.yml",
        }
    )
    base = datetime(2026, 9, 17, 17, 10, 2, tzinfo=timezone(timedelta(hours=2)))
    log._phase_started = base
    log._clock = lambda: base + timedelta(seconds=40)
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "tf_apply"})
    log._clock = lambda: base + timedelta(seconds=80)
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "tf_apply"})
    log.finish(0)
    assert stderr.getvalue() == "Creating shidx.\n"


def test_download_sentence_is_once_per_host(tmp_path):
    log = _phase_log(tmp_path, command="deploy", playbook="deploy_site")
    first = {
        "command": "deploy",
        "phase": "binary",
        "status": "running",
        "kind": "host_start",
        "task": "Download the splunk archive from splunk.com",
        "host": "cm",
    }
    second = dict(first, task="Upload and unarchive splunk archive from ansible host")
    other = dict(first, host="idx1")
    extract = dict(first, task="Extract splunk archive")
    assert log.phase_sentence(first) == "Downloading Splunk on cm."
    assert log.phase_sentence(other) == "Downloading Splunk on idx1."
    assert log.phase_sentence(second) is None
    assert log.phase_sentence(extract) == "Extracting Splunk on cm."
    already = dict(extract, kind="host_result", status="ok")
    assert log.phase_sentence(already) == "Splunk is already extracted on cm."
    changed = dict(extract, kind="host_result", status="changed", host="idx1")
    assert log.phase_sentence(changed) is None


def test_role_already_configured_waits_for_the_roles_own_tasks(tmp_path):
    """Opening checks are not the role. Already configured waits until those tasks finish unchanged."""
    stderr = StringIO()
    log = _phase_log(
        tmp_path,
        command="deploy",
        playbook="ansible/deploy_site.yml",
        agent=True,
        stream=stderr,
    )
    checks = {
        "kind": "host_result",
        "status": "ok",
        "playbook": "ansible/deploy_site.yml",
        "play_file": "ansible/splunk_setup_roles.yml",
        "play": "Setup deployment server role",
        "host": "cm",
    }
    log.emit(dict(checks, task="splunk_common : Check for systemctl"))
    log.emit(dict(checks, task="deployment_server : Start role tasks"))
    log.emit(
        dict(
            checks,
            role="baseconfig_app",
            task="Install org app",
        )
    )
    assert "already configured" not in stderr.getvalue()
    log.emit(
        dict(
            checks,
            task="deployment_server : Configure indexAndForward in outputs.conf",
            status="changed",
        )
    )
    log.emit(
        dict(
            checks,
            play="Setup license manager role",
            task="license_manager : Add license file to splunk",
            status="changed",
        )
    )
    log.finish(0)
    text = stderr.getvalue()
    assert "Configuring the deployment server." in text
    assert "already configured" not in text

    done = StringIO()
    done_log = _phase_log(
        tmp_path / "done",
        command="deploy",
        playbook="ansible/deploy_site.yml",
        agent=True,
        stream=done,
    )
    done_log.emit(dict(checks, task="splunk_common : Check for systemctl"))
    done_log.emit(
        dict(checks, task="deployment_server : Configure indexAndForward in outputs.conf")
    )
    assert "already configured" not in done.getvalue()
    done_log.emit(
        dict(
            checks,
            play="Setup license manager role",
            task="license_manager : Add license file to splunk",
        )
    )
    done_log.finish(0)
    done_text = done.getvalue()
    assert "The deployment server is already configured." in done_text
    assert done_text.index("Configuring the deployment server.") < done_text.index(
        "The deployment server is already configured."
    )


def test_unchanged_phase_says_already_done(tmp_path):
    log = _phase_log(tmp_path, command="deploy", playbook="deploy_site")
    prepared = {
        "command": "deploy",
        "phase": "os",
        "status": "phase_end",
        "kind": "phase_end",
        "ok": True,
        "changed": 0,
    }
    assert log.phase_sentence(prepared) == "Hosts are already prepared."
    changed = dict(prepared, changed=4)
    assert log.phase_sentence(changed) == "Host is prepared."


def test_plan_start_and_readiness_name_each_host(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, agent=True, stream=stderr)
    log.emit(
        {
            "kind": "host_start",
            "status": "running",
            "task": "Run Terraform Plan",
            "host": "localhost",
            "playbook": "aws_provision.yml",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "task": "Display instance readiness status",
            "host": "localhost",
            "msg": [
                "Terraform has verified all instances passed AWS status checks.",
                "  - cm: running (203.0.113.10)",
                "  - idx1: running (203.0.113.11)",
            ],
        }
    )
    log.finish(0)
    text = stderr.getvalue()
    assert text == "Planning the infrastructure.\ncm is up.\nidx1 is up.\n"
    assert "203.0.113" not in text


def test_phase_sentence_second_host_and_direct_apps(tmp_path):
    log = _phase_log(tmp_path)
    first = {
        "command": "provision",
        "phase": "tf_apply",
        "status": "running",
        "kind": "host_start",
        "task": "Apply Terraform Configuration",
        "host": "shidx",
    }
    second = dict(first)
    second["host"] = "idx1"
    assert log.phase_sentence(first) == "Creating shidx."
    assert log.phase_sentence(second) == "Creating idx1."
    log.finish(0)

    apps = _phase_log(tmp_path, command="deploy", playbook="ansible/deploy_site.yml")
    direct = {
        "command": "deploy",
        "phase": "apps_direct",
        "status": "phase_start",
        "kind": "phase_start",
        "host": "shidx",
    }
    assert apps.phase_sentence(direct) == "Installing apps on shidx."
    other = dict(direct)
    other["host"] = "idx1"
    assert apps.phase_sentence(other) == "Installing apps on idx1."
    repeat = dict(other)
    repeat["task"] = "Install the next app"
    assert apps.phase_sentence(repeat) is None
    apps.finish(0)


def test_human_mode_keeps_heartbeat_without_phase_sentences(tmp_path):
    class Tty(StringIO):
        def isatty(self):
            return True

    stderr = Tty()
    log = _phase_log(tmp_path, agent=False, stream=stderr)
    log.emit(
        {
            "kind": "host_result",
            "status": "changed",
            "task": "Apply Terraform Configuration",
            "host": "shidx",
            "playbook": "aws_provision.yml",
        }
    )
    before = stderr.getvalue()
    assert "Creating shidx." not in before
    assert "Terraform apply" in before
    log.emit({"status": "heartbeat", "kind": "heartbeat", "phase": "tf_apply"})
    after = stderr.getvalue()
    assert "Creating shidx." not in after
    assert after.count("Terraform apply") > before.count("Terraform apply")
    log.finish(0)


def test_agent_failed_run_omits_success_sentence(tmp_path):
    stderr = StringIO()
    log = _phase_log(tmp_path, command="deploy", playbook="ansible/deploy_site.yml", agent=True, stream=stderr)
    log.emit(
        {
            "kind": "host_result",
            "status": "ok",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/setup_common.yml",
            "task": "Install packages",
            "host": "shidx",
        }
    )
    log.emit(
        {
            "kind": "host_result",
            "status": "failed",
            "playbook": "ansible/deploy_site.yml",
            "play_file": "ansible/setup_common.yml",
            "task": "Install packages",
            "host": "shidx",
            "msg": "disk full",
        }
    )
    log.finish(1)
    text = stderr.getvalue()
    assert "Host is prepared." not in text
    assert "succeeded" not in text.lower()
    assert '"status": "failed"' in text
    assert log.rc == 1
