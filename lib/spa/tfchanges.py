"""Allowlisted Terraform plan summaries for spa compact progress and replay.

Never persist the full ``terraform show -json`` document. Instance hosts come
from ``aws_instance.splunk["hostname"]`` (for_each key = inventory name).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

_INSTANCE = re.compile(r'^aws_instance\.splunk\["([^"]+)"\]')


def summarize_tf_plan_document(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``{"hosts": [...], "other": [...]}`` from a plan JSON object."""
    hosts: List[Dict[str, Any]] = []
    other: List[Dict[str, str]] = []
    for change in plan.get("resource_changes") or []:
        if not isinstance(change, dict):
            continue
        address = str(change.get("address") or "")
        payload = change.get("change") or {}
        if not isinstance(payload, dict):
            payload = {}
        actions = [str(item) for item in (payload.get("actions") or [])]
        if actions == ["no-op"] or not actions:
            continue
        action = _action_name(actions)
        match = _INSTANCE.match(address)
        if match:
            hosts.append(_instance_row(match.group(1), action, payload))
        else:
            other.append({"address": address, "action": action})
    return {"hosts": hosts, "other": other}


def load_tf_plan_json(text: str) -> Dict[str, Any]:
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("Terraform plan JSON must be an object")
    return summarize_tf_plan_document(loaded)


def compact_tf_host_bits(summary: Dict[str, Any], *, max_names: int = 3, names: bool = True) -> str:
    """Short fragment: ``update idx1 (instance_type, disk)  create 5: cm, idx1, +3``.

    Grouped per action and capped so the live phase line never wraps.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in summary.get("hosts") or []:
        action = str(row.get("action") or "update")
        groups.setdefault(action, []).append(row)
    parts: List[str] = []
    for action in ("create", "replace", "update", "delete"):
        rows = groups.get(action)
        if not rows:
            continue
        label = "destroy" if action == "delete" else action
        if len(rows) == 1:
            host = rows[0].get("host") or "?"
            fields = list(rows[0].get("fields") or [])
            if names and action in {"update", "replace"} and fields:
                parts.append("%s %s (%s)" % (label, host, ", ".join(fields)))
            else:
                parts.append("%s %s" % (label, host))
            continue
        hosts = [str(row.get("host") or "?") for row in rows]
        if not names:
            parts.append("%s %d" % (label, len(hosts)))
            continue
        shown = hosts[:max_names]
        rest = len(hosts) - len(shown)
        listed = ", ".join(shown) + (", +%d" % rest if rest else "")
        parts.append("%s %d: %s" % (label, len(hosts), listed))
    return "  ".join(parts)


def format_tf_replay(summary: Dict[str, Any]) -> str:
    lines = ["Terraform"]
    for row in summary.get("hosts") or []:
        lines.extend(_replay_host_lines(row))
    for row in summary.get("other") or []:
        lines.append("  %s  %s" % (row.get("action"), row.get("address")))
    if len(lines) == 1:
        lines.append("  (no instance changes)")
    return "\n".join(lines) + "\n"


def _action_name(actions: List[str]) -> str:
    if "create" in actions and "delete" in actions:
        return "replace"
    if actions == ["create"] or (len(actions) == 1 and actions[0] == "create"):
        return "create"
    if "delete" in actions and "create" not in actions:
        return "delete"
    return "update"


def _instance_row(host: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    before = payload.get("before") if isinstance(payload.get("before"), dict) else {}
    after = payload.get("after") if isinstance(payload.get("after"), dict) else {}
    fields: List[str] = []
    diffs: Dict[str, Dict[str, Any]] = {}
    for key, label in (("instance_type", "instance_type"), ("ami", "ami")):
        old, new = before.get(key), after.get(key)
        if old != new and (old is not None or new is not None):
            fields.append(label)
            diffs[label] = {"before": old, "after": new}
    disk = _disk_diff(before, after)
    if disk:
        fields.append("disk")
        diffs["disk"] = disk
    return {
        "host": host,
        "action": action,
        "fields": fields,
        "diffs": diffs,
        "instance_type": after.get("instance_type") or before.get("instance_type"),
    }


def _root_volume(obj: Dict[str, Any]) -> Dict[str, Any]:
    block = obj.get("root_block_device")
    if isinstance(block, list) and block and isinstance(block[0], dict):
        return block[0]
    if isinstance(block, dict):
        return block
    return {}


def _disk_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    old_root = _root_volume(before)
    new_root = _root_volume(after)
    old_size, new_size = old_root.get("volume_size"), new_root.get("volume_size")
    old_type, new_type = old_root.get("volume_type"), new_root.get("volume_type")
    extra_old = _extra_volume_sizes(before)
    extra_new = _extra_volume_sizes(after)
    if old_size == new_size and old_type == new_type and extra_old == extra_new:
        return None
    return {
        "before_size": old_size,
        "after_size": new_size,
        "before_type": old_type,
        "after_type": new_type,
    }


def _extra_volume_sizes(obj: Dict[str, Any]) -> List[Any]:
    block = obj.get("ebs_block_device")
    if not isinstance(block, list):
        return []
    sizes = []
    for item in block:
        if isinstance(item, dict):
            sizes.append(item.get("volume_size"))
    return sizes


def _create_hint(row: Dict[str, Any]) -> str:
    itype = row.get("instance_type")
    disk = (row.get("diffs") or {}).get("disk") or {}
    size = disk.get("after_size")
    bits = []
    if itype:
        bits.append(str(itype))
    if size is not None:
        bits.append("%s GiB" % size)
    return " ".join(bits)


def _replay_host_lines(row: Dict[str, Any]) -> List[str]:
    host = row.get("host")
    action = row.get("action")
    diffs = row.get("diffs") or {}
    lines: List[str] = []
    itype = diffs.get("instance_type")
    if itype:
        lines.append(
            "  %s  %s  instance_type  %s -> %s"
            % (action, host, itype.get("before"), itype.get("after"))
        )
    disk = diffs.get("disk")
    if disk:
        after_t = disk.get("after_type") or disk.get("before_type") or ""
        unit = (" GiB (%s)" % after_t) if after_t else " GiB"
        lines.append(
            "  %s  %s  disk           %s -> %s%s"
            % (
                action,
                host,
                disk.get("before_size"),
                disk.get("after_size"),
                unit if disk.get("after_size") is not None else "",
            )
        )
    ami = diffs.get("ami")
    if ami:
        lines.append(
            "  %s  %s  ami            %s -> %s"
            % (action, host, ami.get("before"), ami.get("after"))
        )
    if not lines:
        extra = _create_hint(row)
        if extra:
            lines.append("  %s  %s   %s" % (action, host, extra))
        else:
            lines.append("  %s  %s" % (action, host))
    return lines
