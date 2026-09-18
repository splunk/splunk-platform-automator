"""Aggregate callback that emits JSON events beside Ansible's stdout callback."""

from __future__ import annotations

DOCUMENTATION = r"""
    name: spa_jsonl
    type: aggregate
    short_description: JSON lines for spa env-dir transcripts
    description:
      - Emits one prefixed JSON object per event on stderr.
      - Runs beside Ansible's default stdout callback so spa can optionally show native output.
      - spa captures these events, redacts secrets, and writes $SPA_ENV_DIR/logs.
"""

import json
import re
import sys

from ansible.plugins.callback import CallbackBase

EVENT_PREFIX = "SPA_JSONL_EVENT="

# Strip :line or :line:col from Ansible Origin / get_path() without breaking Windows drives.
_ORIGIN_LINE = re.compile(r"(?::\d+){1,2}$")


def origin_file(obj) -> str:
    """Absolute source file for a Play or Task, without a trailing :line[:col]."""
    if obj is None:
        return ""
    raw = ""
    getter = getattr(obj, "get_path", None)
    if callable(getter):
        try:
            raw = getter() or ""
        except Exception:
            raw = ""
    if not raw:
        ds = getattr(obj, "_ds", None)
        pos = getattr(ds, "ansible_pos", None) if ds is not None else None
        if pos:
            raw = str(pos[0] if not isinstance(pos, str) else pos)
    if not raw:
        origin = getattr(obj, "_origin", None)
        path = getattr(origin, "path", None) if origin is not None else None
        if path:
            raw = str(path)
    text = str(raw or "").strip()
    if not text:
        return ""
    return _ORIGIN_LINE.sub("", text)


def role_origin(task) -> tuple:
    """Return (role_name, role_path) for a task, if a role is bound."""
    role_obj = getattr(task, "_role", None) if task is not None else None
    if role_obj is None:
        return "", ""
    name = getattr(role_obj, "_role_name", None) or ""
    if not name and hasattr(role_obj, "get_name"):
        try:
            name = role_obj.get_name(include_role_fqcn=False) or ""
        except TypeError:
            name = role_obj.get_name() or ""
    path = ""
    getter = getattr(role_obj, "get_role_path", None)
    if callable(getter):
        try:
            path = getter() or ""
        except Exception:
            path = ""
    if not path:
        path = str(getattr(role_obj, "_role_path", None) or "")
    return str(name or ""), str(path or "")


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "spa_jsonl"
    CALLBACK_NEEDS_ENABLED = True

    def __init__(self):
        super().__init__()
        self._playbook = ""
        self._play = ""
        self._play_file = ""
        self._handler = False

    def _emit(self, **fields):
        payload = {key: value for key, value in fields.items() if value is not None and value != ""}
        sys.stderr.write(EVENT_PREFIX + json.dumps(payload, default=str) + "\n")
        sys.stderr.flush()

    def _task_meta(self, task):
        name = ""
        tags = []
        uuid = ""
        if task is None:
            return name, "", "", tags, uuid, ""
        name = task.get_name() if hasattr(task, "get_name") else str(task)
        uuid = str(getattr(task, "_uuid", None) or "")
        role, role_path = role_origin(task)
        tags = list(getattr(task, "tags", None) or [])
        task_file = origin_file(task)
        return name, role, role_path, tags, uuid, task_file

    def v2_playbook_on_start(self, playbook):
        self._playbook = getattr(playbook, "_file_name", None) or str(playbook)
        self._emit(kind="playbook_start", playbook=self._playbook, status="ok")

    def v2_playbook_on_play_start(self, play):
        self._play = play.get_name() if hasattr(play, "get_name") else str(play)
        self._play_file = origin_file(play)
        self._handler = False
        self._emit(
            kind="play_start",
            playbook=self._playbook,
            play_file=self._play_file or None,
            play=self._play,
            status="ok",
        )

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._handler = False
        name, role, role_path, tags, uuid, task_file = self._task_meta(task)
        self._emit(
            kind="task_start",
            playbook=self._playbook,
            play_file=self._play_file or None,
            play=self._play,
            task=name,
            task_file=task_file or None,
            role=role or None,
            role_path=role_path or None,
            tags=tags,
            task_uuid=uuid or None,
            status="ok",
            handler=False,
        )

    def v2_playbook_on_handler_task_start(self, task):
        self._handler = True
        name, role, role_path, tags, uuid, task_file = self._task_meta(task)
        self._emit(
            kind="task_start",
            playbook=self._playbook,
            play_file=self._play_file or None,
            play=self._play,
            task=name,
            task_file=task_file or None,
            role=role or None,
            role_path=role_path or None,
            tags=tags,
            task_uuid=uuid or None,
            status="ok",
            handler=True,
        )

    def _from_result(self, result, status):
        task = getattr(result, "task", None) or getattr(result, "_task", None)
        host_obj = getattr(result, "host", None) or getattr(result, "_host", None)
        host = host_obj.get_name() if host_obj is not None else ""
        name, role, role_path, tags, uuid, task_file = self._task_meta(task)
        payload = getattr(result, "result", None) or getattr(result, "_result", None) or {}
        msg = payload.get("msg") or payload.get("message") or name
        if status == "changed" or (status == "ok" and payload.get("changed")):
            status = "changed" if payload.get("changed") else status
        duration_ms = None
        delta = payload.get("delta")
        if isinstance(delta, (int, float)):
            duration_ms = int(delta * 1000)
        self._emit(
            kind="host_result",
            playbook=self._playbook,
            play_file=self._play_file or None,
            play=self._play,
            task=name,
            task_file=task_file or None,
            role=role or None,
            role_path=role_path or None,
            tags=tags,
            task_uuid=uuid or None,
            host=host,
            status=status,
            msg=msg,
            handler=self._handler,
            duration_ms=duration_ms,
        )

    def v2_runner_on_ok(self, result):
        self._from_result(result, "ok")

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._from_result(result, "failed")

    def v2_runner_on_skipped(self, result):
        self._from_result(result, "skipped")

    def v2_runner_on_unreachable(self, result):
        self._from_result(result, "unreachable")

    def v2_playbook_on_stats(self, stats):
        recap = {}
        hosts = []
        if stats is not None:
            processed = getattr(stats, "processed", None)
            if isinstance(processed, dict):
                hosts = list(processed.keys())
            elif processed:
                hosts = list(processed)
        for host in hosts:
            if hasattr(stats, "summarize"):
                recap[str(host)] = stats.summarize(host)
        self._emit(
            kind="recap",
            playbook=self._playbook,
            play_file=self._play_file or None,
            play=self._play,
            status="ok",
            task="PLAY RECAP",
            recap=recap or None,
        )
