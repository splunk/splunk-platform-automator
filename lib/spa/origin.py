"""Ansible Origin / get_path helpers.

Mirrored in ``ansible/plugins/callback/spa_jsonl.py`` so the callback can load
without ``PYTHONPATH=lib``. Keep both copies in sync.
"""

from __future__ import annotations

import re

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
