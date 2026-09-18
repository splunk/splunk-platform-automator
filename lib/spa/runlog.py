"""Per-environment JSONL run transcripts, redaction, and compact progress.

Transcripts live under ``$SPA_ENV_DIR/logs/`` (not XDG state). Clocks are local
wall time with a numeric UTC offset (never naive, never ``Z``-only).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TextIO

from spa.paths import SpaPaths
from spa.tfchanges import compact_tf_host_bits, format_tf_replay, load_tf_plan_json

HEARTBEAT_SECONDS = 20
META_SUFFIX = ".meta.json"
JSONL_SUFFIX = ".jsonl"

# Ordered only for provision/destroy (Terraform steps). Deploy/run groups are
# event-driven names and are not a fixed-length catalog.
PROVISION_PHASES: List[Dict[str, str]] = [
    {"id": "tf_init", "title": "Terraform init"},
    {"id": "tf_plan", "title": "Terraform plan"},
    {"id": "tf_apply", "title": "Terraform apply"},
    {"id": "wait_ssh", "title": "Wait for SSH"},
]

TF_CHANGE_PHASES = {"tf_plan", "tf_apply"}

POWER_PHASES: List[Dict[str, str]] = [
    {"id": "power", "title": "Instance power"},
]

# Vagrant walks one machine at a time and prints no fixed step list, so its
# groups are event-driven per machine instead of an ordered catalog.
VAGRANT_GROUP = "vagrant"
VAGRANT_HOST_GROUP_PREFIX = "vm:"

# Events replayed as the provider's own text instead of Ansible play/task banners.
PROVIDER_SOURCE = "provider"

# Ansible's own stderr notes ("[WARNING]: ...") belong to no play or group.
NOTE_KIND = "note"

GROUP_TITLES: Dict[str, str] = {
    "preflight": "Preflight / readiness",
    "os": "OS and host prep",
    "linkpage": "Host link page",
    "binary": "Splunk install",
    "role_deployment_server": "Deployment server",
    "role_license_manager": "License manager",
    "role_cluster_manager": "Cluster manager",
    "role_indexer": "Indexers",
    "role_deployer": "Deployer",
    "role_search_head": "Search heads",
    "role_monitoring_console": "Monitoring console",
    "role_heavy_forwarder": "Heavy forwarders",
    "role_universal_forwarder": "Universal forwarders",
    "baseconfig": "Baseconfig apps",
    "conf": "Extra Splunk conf",
    "other_roles": "Helper roles (LDAP)",
    "apps": "App deployment",
    "apps_precheck": "App deployment · App preflight",
    "apps_clients": "App deployment · Deployment-client detection",
    "apps_ds": "App deployment · Deployment Server apps",
    "apps_cm": "App deployment · Cluster Manager apps",
    "apps_shc": "App deployment · Search Head Cluster apps",
    "apps_direct": "App deployment · Direct host apps",
    "apps_premium_itsi": "App deployment · Premium apps (ITSI)",
    "apps_content_packs": "App deployment · Content packs",
    "apps_cp_api": "App deployment · Content pack API",
    "apps_post_restart": "App deployment · Post-restart playbooks",
    "apps_summary": "App deployment · App summary",
    "apps_remove": "Remove apps",
    "upgrade_splunk": "Upgrade Splunk",
    "upgrade_distributed_cm": "Upgrade cluster manager",
    "upgrade_distributed_sh": "Upgrade search heads",
    "upgrade_idxc_begin": "Indexer rolling upgrade · begin",
    "upgrade_idxc_peers": "Indexer rolling upgrade · peers",
    "upgrade_idxc_end": "Indexer rolling upgrade · end",
    "upgrade_shc_begin": "Search head rolling upgrade · begin",
    "upgrade_shc_members": "Search head rolling upgrade · members",
    "upgrade_shc_end": "Search head rolling upgrade · end",
    "tf_init": "Terraform init",
    "tf_plan": "Terraform plan",
    "tf_apply": "Terraform apply",
    "wait_ssh": "Wait for SSH",
    "power": "Instance power",
    VAGRANT_GROUP: "Vagrant",
}

PLAYBOOK_GROUP = {
    "preflight_deploy": "preflight",
    "setup_common": "os",
    "create_linkpage": "linkpage",
    "splunk_install": "binary",
    "splunk_setup_conf": "conf",
    "setup_other_roles": "other_roles",
    "splunk_apps_deploy": "apps",
    "splunk_apps_remove": "apps_remove",
    "aws_provision": "tf_init",
    "aws_destroy": "tf_apply",
    "aws_wait_hosts": "wait_ssh",
    "upgrade_splunk": "upgrade_splunk",
}

ROLE_PLAY_GROUP = (
    ("deployment server", "role_deployment_server"),
    ("license manager", "role_license_manager"),
    ("cluster manager", "role_cluster_manager"),
    ("cluster master", "role_cluster_manager"),
    ("indexer", "role_indexer"),
    ("deployer", "role_deployer"),
    ("search head", "role_search_head"),
    ("monitoring console", "role_monitoring_console"),
    ("heavy forwarder", "role_heavy_forwarder"),
    ("universal forwarder", "role_universal_forwarder"),
)

ROLE_NAME_GROUP = {
    "deployment_server": "role_deployment_server",
    "license_manager": "role_license_manager",
    "cluster_manager": "role_cluster_manager",
    "cluster_master": "role_cluster_manager",
    "indexer": "role_indexer",
    "deployer": "role_deployer",
    "search_head": "role_search_head",
    "monitoring_console": "role_monitoring_console",
    "heavy_forwarder": "role_heavy_forwarder",
    "universal_forwarder": "role_universal_forwarder",
    "universal_forwarder_windows": "role_universal_forwarder",
}

# Kept for tests / callers that still import the old names.
DEPLOY_PHASES: List[Dict[str, str]] = [
    {"id": key, "title": GROUP_TITLES[key]}
    for key in (
        "preflight",
        "os",
        "linkpage",
        "binary",
        "role_deployment_server",
        "role_license_manager",
        "role_cluster_manager",
        "role_indexer",
        "role_deployer",
        "role_search_head",
        "role_monitoring_console",
        "role_heavy_forwarder",
        "role_universal_forwarder",
        "baseconfig",
        "conf",
        "other_roles",
        "apps",
    )
]
PLAYBOOK_PHASE = dict(PLAYBOOK_GROUP)
PLAY_NAME_PHASE = tuple(ROLE_PLAY_GROUP)

CALLBACK_EVENT_PREFIX = "SPA_JSONL_EVENT="
_REDACT = "***"
_SECRET_LINE = re.compile(
    r"(?i)((?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?access[_-]?key|vault[_-]?password|authorization|bearer)"
    r"\s*[=:]\s*)(\S+)"
)
_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_SECRET = re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)(\S+)")
_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE|RSA PRIVATE KEY)"
    r"-----.*?-----END [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE|RSA PRIVATE KEY)-----",
    re.DOTALL,
)
_VAULT = re.compile(r"\$ANSIBLE_VAULT;[^\n]+(?:\n[0-9a-fA-F]+)+")
_LICENSE_XML = re.compile(r"(?is)<license\b[^>]*>.*?</license>")
_BEARER = re.compile(r"(?i)\b(bearer\s+)([a-z0-9._\-]+)")
_SPLUNK_CLI_SECRET = re.compile(
    r"(?i)(-(?:auth|remotePassword|password|secret)\s+)(?:'[^']*'|\"[^\"]*\"|\S+)"
)


def now_local(clock: Optional[Callable[[], datetime]] = None) -> datetime:
    """Controller-local time with an explicit offset (honors TZ)."""
    if clock is not None:
        stamp = clock()
        if stamp.tzinfo is None:
            return stamp.astimezone()
        return stamp
    return datetime.now().astimezone()


def format_event_time(stamp: Optional[datetime] = None) -> str:
    """ISO-8601 with milliseconds and numeric offset, never Z."""
    local = stamp if stamp is not None else now_local()
    if local.tzinfo is None:
        local = local.astimezone()
    offset = local.utcoffset()
    if offset is None:
        offset = timedelta(0)
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    base = local.replace(tzinfo=None, microsecond=(local.microsecond // 1000) * 1000)
    return "%s.%03d%s%02d:%02d" % (
        base.strftime("%Y-%m-%dT%H:%M:%S"),
        local.microsecond // 1000,
        sign,
        hours,
        minutes,
    )


def format_run_id_stamp(stamp: Optional[datetime] = None) -> str:
    """Filename-safe local stamp: 2026-09-17T170200+0200."""
    local = stamp if stamp is not None else now_local()
    if local.tzinfo is None:
        local = local.astimezone()
    offset = local.utcoffset()
    if offset is None:
        offset = timedelta(0)
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return "%s%s%02d%02d" % (local.strftime("%Y-%m-%dT%H%M%S"), sign, hours, minutes)


def format_headline_time(stamp: Optional[datetime] = None) -> str:
    local = stamp if stamp is not None else now_local()
    if local.tzinfo is None:
        local = local.astimezone()
    offset = local.utcoffset() or timedelta(0)
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return "%s%s%02d:%02d" % (local.strftime("%H:%M:%S"), sign, hours, minutes)


def redact(value: Any) -> Any:
    """Strip secrets from strings nested in JSON-able structures."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    text = str(value)
    text = _PEM.sub("-----BEGIN [REDACTED]-----", text)
    text = _VAULT.sub("$ANSIBLE_VAULT;[REDACTED]", text)
    text = _LICENSE_XML.sub("<license>[REDACTED]</license>", text)
    text = _AWS_KEY.sub(_REDACT, text)
    text = _AWS_SECRET.sub(r"\1" + _REDACT, text)
    text = _BEARER.sub(r"\1" + _REDACT, text)
    text = _SPLUNK_CLI_SECRET.sub(r"\1" + _REDACT, text)
    text = _SECRET_LINE.sub(r"\1" + _REDACT, text)
    return text


def logs_dir(paths: SpaPaths) -> Path:
    return Path(paths.spa_env_dir) / "logs"


def _stem(path: str) -> str:
    if not path:
        return ""
    return Path(str(path)).stem.lower().replace("-", "_")


def group_title(phase_id: Optional[str]) -> str:
    if not phase_id:
        return ""
    if phase_id in GROUP_TITLES:
        return GROUP_TITLES[phase_id]
    if phase_id.startswith("play:"):
        return phase_id[5:]
    if phase_id.startswith(VAGRANT_HOST_GROUP_PREFIX):
        return "VM " + phase_id[len(VAGRANT_HOST_GROUP_PREFIX) :]
    text = str(phase_id).replace("_", " ").replace("-", " ")
    return text[:1].upper() + text[1:] if text else str(phase_id)


def phases_for_command(command: str, provider: str = "") -> List[Dict[str, str]]:
    if command in {"provision", "destroy"}:
        # Terraform runs a known sequence; Vagrant does not.
        if provider == "virtualbox":
            return []
        return list(PROVISION_PHASES)
    if command in {"suspend", "resume"}:
        return list(POWER_PHASES)
    return []


def map_phase(
    *,
    command: str,
    playbook: str = "",
    play: str = "",
    task: str = "",
    role: str = "",
    tags: Optional[Sequence[str]] = None,
    parent_playbook: str = "",
    play_file: str = "",
    task_file: str = "",
    role_path: str = "",
    provider: str = "",
) -> Optional[str]:
    """Map Ansible (or provider) context to a stable named group id."""
    origin = _stem(play_file) or _stem(playbook)
    entry = _stem(parent_playbook) or _stem(playbook)
    role_l = (role or "").lower()
    role_path_l = (role_path or "").replace("\\", "/").lower()
    task_file_l = (task_file or "").replace("\\", "/").lower()
    task_l = (task or "").lower()
    play_l = (play or "").lower()
    tagset = {str(item).lower() for item in (tags or [])}

    if command in {"provision", "destroy"}:
        if provider == "virtualbox":
            # Vagrant lines already carry the machine group they belong to.
            return None
        mapped = PLAYBOOK_GROUP.get(origin) or PLAYBOOK_GROUP.get(entry)
        return _provision_phase_from_task(task or play, mapped)
    if command in {"suspend", "resume"}:
        return "power"
    if command == "validate":
        return None

    overlay = _overlay_group(role_l, role_path_l, task_file_l, task_l, tagset)
    if overlay:
        return overlay

    if origin in {"splunk_apps_deploy", "splunk_apps_remove"}:
        apps = _apps_play_group(play_l, origin)
        if apps:
            return apps

    if origin == "splunk_setup_roles":
        return _role_from_play(play_l) or ROLE_NAME_GROUP.get(role_l) or "role_deployment_server"

    if origin.startswith("upgrade_") or entry.startswith("upgrade_"):
        return _upgrade_group(origin or entry, play_l, task_file_l)

    if origin in PLAYBOOK_GROUP:
        return PLAYBOOK_GROUP[origin]

    role_group = _role_from_play(play_l) or ROLE_NAME_GROUP.get(role_l)
    if role_group:
        return role_group
    apps = _apps_play_group(play_l, origin)
    if apps:
        return apps

    if play:
        return "play:" + play
    if origin:
        return origin
    if task_l:
        return "run"
    return None


def _overlay_group(
    role_l: str,
    role_path_l: str,
    task_file_l: str,
    task_l: str,
    tagset: set,
) -> Optional[str]:
    blob = " ".join((role_l, role_path_l, task_file_l, task_l))
    if "cp_api_install" in blob:
        return "apps_cp_api"
    if "apps_itsi_content_pack" in blob or "process_direct_app_apply_content_pack" in blob:
        return "apps_content_packs"
    if (
        "apps_itsi" in role_l
        or "/apps_itsi/" in role_path_l
        or "process_direct_app_apply_itsi" in blob
        or "itsi_install" in blob
        or "verify_premium_app" in blob
    ) and "content_pack" not in blob:
        return "apps_premium_itsi"
    if (
        "splunk_baseconfig" in tagset
        or "baseconfig_app" in role_l
        or "baseconfig_app" in role_path_l
        or "org_" in task_l
    ):
        return "baseconfig"
    return None


def _apps_play_group(play_l: str, origin: str) -> Optional[str]:
    if origin == "splunk_apps_remove":
        return "apps_remove"
    if "pre-deployment" in play_l:
        return "apps_precheck"
    if "deployment client" in play_l:
        return "apps_clients"
    if "deploy apps to deployment server" in play_l:
        return "apps_ds"
    if "deploy apps to cluster manager" in play_l:
        return "apps_cm"
    if "deploy apps to deployer" in play_l:
        return "apps_shc"
    if "directly to hosts" in play_l:
        return "apps_direct"
    if "post-restart" in play_l:
        return "apps_post_restart"
    if play_l == "deployment summary" or play_l.endswith("deployment summary"):
        return "apps_summary"
    if origin == "splunk_apps_deploy":
        return "apps"
    return None


def _role_from_play(play_l: str) -> Optional[str]:
    for needle, phase in ROLE_PLAY_GROUP:
        if needle in play_l:
            return phase
    return None


def _upgrade_group(origin: str, play_l: str, task_file_l: str) -> str:
    blob = play_l + " " + task_file_l
    if origin == "upgrade_distributed":
        if "search" in play_l:
            return "upgrade_distributed_sh"
        return "upgrade_distributed_cm"
    if origin == "upgrade_idxc_rolling":
        if "begin" in blob:
            return "upgrade_idxc_begin"
        if "end" in blob:
            return "upgrade_idxc_end"
        return "upgrade_idxc_peers"
    if origin == "upgrade_shc_rolling":
        if "begin" in blob:
            return "upgrade_shc_begin"
        if "end" in blob:
            return "upgrade_shc_end"
        return "upgrade_shc_members"
    return "upgrade_splunk"


def _provision_phase_from_task(task: str, fallback: Optional[str] = None) -> str:
    lower = (task or "").lower()
    if "wait" in lower or "ssh" in lower:
        return "wait_ssh"
    if "plan" in lower:
        return "tf_plan"
    if "apply" in lower or "destroy" in lower or "present" in lower:
        return "tf_apply"
    if "init" in lower or "link terraform" in lower or "tfvars" in lower:
        return "tf_init"
    return fallback or "tf_init"


def _phase_catalog(command: str, playbook: str, provider: str = "") -> List[Dict[str, str]]:
    return phases_for_command(command, provider)


# Vagrant prefixes machine output with "==> name:" and indents continuation
# lines ("    name: SSH address: ..."). Anything else is a run-wide message.
_VAGRANT_MACHINE_LINE = re.compile(r"^(?:==>|\s{2,})\s*(?P<host>[^\s:]+):\s*(?P<text>.*)$")
_VAGRANT_BRINGING_UP = re.compile(r"^Bringing machine '(?P<host>[^']+)' up\b")
# Plugins such as vagrant-vbguest label their own lines "[machine] ...".
_VAGRANT_PLUGIN_LINE = re.compile(r"^\[(?P<host>[^\]\s]+)\]\s*(?P<text>.*)$")
# Box downloads rewrite a percentage line with \r; each rewrite reaches us as
# its own line, and keeping them would count download ticks as steps.
_VAGRANT_TRANSIENT_LINE = re.compile(r"^progress:\s*\d+%", re.IGNORECASE)
# Vagrant's own notices use these names where a machine name would be.
_VAGRANT_PSEUDO_HOSTS = frozenset({"vagrant", "default"})
_VAGRANT_FAILURE_PATTERNS = (
    re.compile(r"^error\b", re.IGNORECASE),
    re.compile(r"^fatal\b", re.IGNORECASE),
    re.compile(r"there was an error", re.IGNORECASE),
    re.compile(r"vagrant failed to", re.IGNORECASE),
    re.compile(r"could not be found", re.IGNORECASE),
    re.compile(r"timed out", re.IGNORECASE),
    re.compile(r"non-zero exit status", re.IGNORECASE),
    re.compile(r"^stderr:", re.IGNORECASE),
)


def vagrant_failure_line(text: str) -> bool:
    return any(pattern.search(text) for pattern in _VAGRANT_FAILURE_PATTERNS)


def vagrant_event(line: str) -> Optional[Dict[str, Any]]:
    """Turn one ``vagrant up``/``destroy`` output line into a run event.

    Machine-prefixed lines open a group per machine; run-wide lines (box
    downloads, plugin notices) fold into whichever group is already open.
    """
    raw = line.rstrip("\n")
    if not raw.strip():
        return None
    host = ""
    text = raw.strip()
    machine = _VAGRANT_MACHINE_LINE.match(raw) or _VAGRANT_PLUGIN_LINE.match(text)
    if machine:
        host = machine.group("host")
        text = machine.group("text").strip()
    else:
        bringing = _VAGRANT_BRINGING_UP.match(text)
        if bringing:
            host = bringing.group("host")
    if host in _VAGRANT_PSEUDO_HOSTS:
        host = ""
    if not text or _VAGRANT_TRANSIENT_LINE.match(text):
        return None
    failed = vagrant_failure_line(text)
    event: Dict[str, Any] = {
        "source": PROVIDER_SOURCE,
        "task": text,
        "msg": text,
        "status": "failed" if failed else "ok",
        # Counting every Vagrant line as a host result would report a result
        # per printed line; steps are tasks, and only failures name a host.
        "kind": "host_result" if failed else "task_start",
    }
    if host:
        event["phase"] = VAGRANT_HOST_GROUP_PREFIX + host
        if failed:
            event["host"] = host
    return event


# Providers that stream their own CLI output instead of Ansible callback JSONL.
PROVIDER_LINE_EVENTS: Dict[str, Callable[[str], Optional[Dict[str, Any]]]] = {
    "virtualbox": vagrant_event,
}

# Group for provider output printed before (or outside of) any machine.
PROVIDER_BASE_GROUP: Dict[str, str] = {"virtualbox": VAGRANT_GROUP}


_ANSI = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def want_color(stream: Optional[TextIO] = None, *, agent: bool = False) -> bool:
    if agent:
        return False
    if (os.environ.get("NO_COLOR") or "").strip():
        return False
    if (os.environ.get("ANSIBLE_NOCOLOR") or "").strip():
        return False
    if (os.environ.get("TERM") or "") == "dumb":
        return False
    target = stream if stream is not None else sys.stderr
    return bool(getattr(target, "isatty", lambda: False)())


def want_live_cr(stream: Optional[TextIO] = None, *, agent: bool = False) -> bool:
    if agent:
        return False
    target = stream if stream is not None else sys.stderr
    return bool(getattr(target, "isatty", lambda: False)())


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled or not color:
        return text
    return "%s%s%s" % (_ANSI.get(color, ""), text, _ANSI["reset"])


# Colors plus cursor/erase controls: Vagrant clears the line while it rewrites
# download progress, and a bare "\033[K" would otherwise land in the log.
_ANSI_RE = re.compile(r"\033\[[0-9;?]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return "%ss" % total
    return "%dm%02ds" % (total // 60, total % 60)


def _infer_kind(raw: Dict[str, Any], status: str) -> str:
    kind = str(raw.get("kind") or "")
    if kind:
        return kind
    if status in {"phase_start", "phase_end", "heartbeat", "tf_changes"}:
        return status
    if raw.get("recap"):
        return "recap"
    if raw.get("host"):
        return "host_result"
    if raw.get("play") and not raw.get("task"):
        return "play_start"
    return "task_start"


def render_replay_text(events: Sequence[Dict[str, Any]]) -> str:
    """Reconstruct Ansible-style (and Terraform) text from JSONL objects."""
    chunks: List[str] = []
    last_task = None
    for event in events:
        kind = str(event.get("kind") or _infer_kind(event, str(event.get("status") or "")))
        if event.get("source") == PROVIDER_SOURCE or kind == NOTE_KIND:
            # Vagrant lines and Ansible warnings are already readable text.
            text = str(event.get("msg") or event.get("task") or "").strip()
            if text:
                chunks.append(text)
            continue
        if kind == "tf_changes":
            summary = event.get("tf_summary") or {
                "hosts": event.get("hosts") or [],
                "other": event.get("other") or [],
            }
            chunks.append(format_tf_replay(summary).rstrip("\n"))
            continue
        if kind == "play_start":
            play = event.get("play") or "play"
            last_task = None
            chunks.append("PLAY [%s] %s" % (play, "*" * max(10, 60 - len(str(play)))))
            continue
        if kind == "task_start" and not event.get("handler"):
            task = event.get("task") or ""
            if task and task != last_task:
                last_task = task
                chunks.append("TASK [%s] %s" % (task, "*" * max(10, 60 - len(str(task)))))
            continue
        if kind == "host_result":
            host = event.get("host") or ""
            status = str(event.get("status") or "ok")
            if event.get("handler") or not host:
                continue
            if status == "changed":
                chunks.append("changed: [%s]" % host)
            elif status == "failed":
                chunks.append("fatal: [%s]: FAILED! => %s" % (host, event.get("msg") or ""))
            elif status == "unreachable":
                chunks.append("fatal: [%s]: UNREACHABLE! => %s" % (host, event.get("msg") or ""))
            elif status == "skipped":
                chunks.append("skipping: [%s]" % host)
            else:
                chunks.append("ok: [%s]" % host)
            continue
        if kind == "recap":
            chunks.append("PLAY RECAP %s" % ("*" * 60))
            recap = event.get("recap") or {}
            if isinstance(recap, dict):
                for host, stats in recap.items():
                    if not isinstance(stats, dict):
                        chunks.append("%s" % host)
                        continue
                    chunks.append(
                        "%-26s : ok=%-4s changed=%-4s unreachable=%-4s failed=%-4s"
                        % (
                            host,
                            stats.get("ok", 0),
                            stats.get("changed", 0),
                            stats.get("unreachable", 0),
                            stats.get("failures", stats.get("failed", 0)),
                        )
                    )
            continue
    if not chunks:
        return ""
    return "\n".join(chunks) + "\n"


def replay_jsonl(path: Path) -> str:
    if not path.is_file():
        return ""
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            events.append(row)
    return render_replay_text(events)


class RunLog:
    """Write JSONL + sidecar and fan out human/agent stderr progress."""

    def __init__(
        self,
        paths: SpaPaths,
        command: str,
        playbook: str = "",
        *,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
        provider: str = "",
        clock: Optional[Callable[[], datetime]] = None,
        stream: Optional[TextIO] = None,
        heartbeat_seconds: int = HEARTBEAT_SECONDS,
    ) -> None:
        self.paths = paths
        self.command = command
        self.playbook = playbook
        self.agent = agent
        self.provider = provider
        self.ansible_output = ansible_output
        self._clock = clock
        self._stream = stream if stream is not None else sys.stderr
        self.heartbeat_seconds = heartbeat_seconds
        self.spa_env = Path(paths.spa_env_dir).name
        started = now_local(clock)
        self.started_at = started
        self.run_id = "%s-%s" % (format_run_id_stamp(started), command)
        folder = logs_dir(paths)
        folder.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = folder / (self.run_id + JSONL_SUFFIX)
        self.meta_path = folder / (self.run_id + META_SUFFIX)
        self._handle = self.jsonl_path.open("a", encoding="utf-8")
        self.catalog = _phase_catalog(command, playbook, provider)
        self._current_phase: Optional[str] = None
        self._phase_index: Optional[int] = None
        self._phase_title: Optional[str] = None
        self._phase_started: Optional[datetime] = None
        self._lock = threading.Lock()
        self._stop_heartbeat = threading.Event()
        self._hb_thread: Optional[threading.Thread] = None
        self._last_failure: Dict[str, Any] = {}
        self.rc: Optional[int] = None
        self._color = want_color(self._stream, agent=agent)
        # Ansible's own stdout callback is streamed to the human, so the JSONL
        # replay must not print the same run a second time.
        self.native_output = bool(native_output) and not agent
        self._live_cr = want_live_cr(self._stream, agent=agent) and not ansible_output
        self._live_open = False
        self._live_width = 0
        self._tasks: set = set()
        self._hosts: set = set()
        self._results = 0
        self._changed = 0
        self._skipped = 0
        self._failed = 0
        self._tf_bits = ""
        self._tf_terse = ""
        self._tf_summary: Optional[Dict[str, Any]] = None
        self._tf_attached = False
        self._replay_play = None
        self._replay_task = None
        self._write_meta(rc=None, ended=None)

    @property
    def wants_color(self) -> bool:
        """True when the human stream can take ANSI (drives Ansible's own color)."""
        return self._color

    @property
    def saw_failure(self) -> bool:
        """True once any event in this run was reported as failed."""
        return self._failed > 0

    def envelope_fields(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "log": str(self.jsonl_path),
            "run_id": self.run_id,
        }
        if self._last_failure.get("phase"):
            payload["phase"] = self._last_failure.get("phase")
        if self._last_failure.get("host"):
            payload["host"] = self._last_failure["host"]
        if self._last_failure.get("task"):
            payload["task"] = self._last_failure["task"]
        return payload

    def counters(self) -> Dict[str, Any]:
        return {
            "tasks": len(self._tasks),
            "hosts": len(self._hosts),
            "results": self._results,
            "changed": self._changed,
            "skipped": self._skipped,
            "failed": self._failed,
        }

    def start_heartbeat(self) -> None:
        if self.heartbeat_seconds <= 0 or self._hb_thread is not None:
            return

        def _loop() -> None:
            while not self._stop_heartbeat.wait(self.heartbeat_seconds):
                with self._lock:
                    phase = self._current_phase
                    index = self._phase_index
                    counts = self.counters()
                if not phase:
                    continue
                self.emit(
                    {
                        "status": "heartbeat",
                        "kind": "heartbeat",
                        "phase": phase,
                        "phase_id": phase,
                        "phase_index": index,
                        "tasks": counts["tasks"],
                        "hosts": counts["hosts"],
                        "changed": counts["changed"],
                    }
                )

        self._hb_thread = threading.Thread(target=_loop, name="spa-run-heartbeat", daemon=True)
        self._hb_thread.start()

    def emit(self, raw: Dict[str, Any]) -> None:
        with self._lock:
            event = self._normalize(raw)
            line = json.dumps(event, default=str, ensure_ascii=False)
            self._handle.write(line + "\n")
            self._handle.flush()
        self._render(event)

    def consume_callback_line(self, line: str) -> None:
        # Ansible may color its own output; the JSONL store stays escape-free.
        text = _strip_ansi(line.rstrip("\n"))
        if not text:
            return
        payload: Dict[str, Any]
        if text.startswith("{"):
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError:
                payload = self._note_payload(text)
            else:
                payload = loaded if isinstance(loaded, dict) else {"status": "ok", "msg": text}
        else:
            payload = self._note_payload(text)
        self.emit(payload)
        if self._looks_like_tf_plan_done(payload):
            self.attach_tf_plan()

    @staticmethod
    def _note_payload(text: str) -> Dict[str, Any]:
        """Ansible text on stderr: a warning to keep, or a hard error to show."""
        payload: Dict[str, Any] = {
            "status": "ok",
            "kind": NOTE_KIND,
            "msg": text,
            "raw": True,
        }
        if text.startswith("ERROR!"):
            payload["status"] = "failed"
        return payload

    def consume_provider_line(self, line: str) -> None:
        """Feed one provider CLI line (Vagrant today) through its own dialect.

        Providers that drive Ansible keep emitting callback JSONL, so anything
        without a dialect falls back to the callback reader.
        """
        dialect = PROVIDER_LINE_EVENTS.get(self.provider)
        if dialect is None:
            self.consume_callback_line(line)
            return
        event = dialect(_strip_ansi(line.rstrip("\n")))
        if event is None:
            return
        self.emit(event)

    def emit_native_output(self, line: str) -> None:
        """Write one raw native Ansible line to the human stream only.

        Unredacted on purpose: `spa … -v` is the debugging view, and Ansible's own
        output is reproduced byte for byte, secrets included.  Stored transcripts
        stay redacted, so only this terminal sees them.
        """
        if self.agent:
            return
        self._stream.write(line if line.endswith("\n") else line + "\n")
        self._stream.flush()

    def attach_tf_plan(self, summary: Optional[Dict[str, Any]] = None) -> None:
        """Fold allowlisted Terraform host diffs into the current phase line."""
        if self._tf_attached and summary is None:
            return
        if summary is None:
            summary = self._load_tf_summary()
        if not summary or not (summary.get("hosts") or summary.get("other")):
            return
        self._tf_attached = True
        self._tf_summary = summary
        self._tf_bits = compact_tf_host_bits(summary)
        self._tf_terse = compact_tf_host_bits(summary, names=False)
        self.emit(
            {
                "kind": "tf_changes",
                "status": "tf_changes",
                "phase": self._current_phase or "tf_plan",
                "tf_summary": redact(summary),
                "hosts": [row.get("host") for row in (summary.get("hosts") or [])],
                "msg": self._tf_bits,
            }
        )

    def _load_tf_summary(self) -> Optional[Dict[str, Any]]:
        plan_path = Path(self.paths.spa_env_dir) / "terraform" / "aws" / "tfplan"
        if not plan_path.is_file():
            return None
        try:
            from spa.executil import ToolNotFound, tool_path

            terraform = tool_path(self.paths, "terraform")
        except (OSError, ToolNotFound):
            return None
        try:
            result = subprocess.run(
                [terraform, "show", "-json", str(plan_path)],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(plan_path.parent),
            )
        except OSError:
            return None
        if result.returncode != 0 or not (result.stdout or "").strip():
            return None
        try:
            return load_tf_plan_json(result.stdout)
        except (ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _looks_like_tf_plan_done(payload: Dict[str, Any]) -> bool:
        task = str(payload.get("task") or "").lower()
        status = str(payload.get("status") or "")
        if status not in {"ok", "changed"}:
            return False
        return "terraform plan" in task or task.endswith("tfplan")

    def finish(self, rc: int) -> None:
        self._stop_heartbeat.set()
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=1)
        ended = now_local(self._clock)
        if self._current_phase:
            self.emit(
                {
                    "status": "phase_end",
                    "kind": "phase_end",
                    "phase": self._current_phase,
                    "phase_id": self._current_phase,
                    "ok": rc == 0,
                    "tasks": len(self._tasks),
                    "hosts": len(self._hosts),
                    "results": self._results,
                    "changed": self._changed,
                    "skipped": self._skipped,
                }
            )
        self.rc = rc
        self._write_meta(rc=rc, ended=ended)
        self._handle.close()

    def _reset_phase_stats(self) -> None:
        self._tasks = set()
        self._hosts = set()
        self._results = 0
        self._changed = 0
        self._skipped = 0
        self._failed = 0
        self._phase_started = now_local(self._clock)

    def _progress_payload(self, event: Dict[str, Any], status: str) -> Dict[str, Any]:
        elapsed = 0.0
        if self._phase_started is not None:
            elapsed = (now_local(self._clock) - self._phase_started).total_seconds()
        payload: Dict[str, Any] = {
            "type": "progress",
            "phase": event.get("phase") or self._current_phase,
            "phase_title": event.get("phase_title") or self._phase_title,
            "phase_index": event.get("phase_index") if event.get("phase_index") is not None else self._phase_index,
            "phase_count": event.get("phase_count") or (len(self.catalog) or None),
            "status": status,
            "tasks": len(self._tasks),
            "hosts": len(self._hosts),
            "results": self._results,
            "changed": self._changed,
            "skipped": self._skipped,
            "elapsed": format_elapsed(elapsed),
        }
        if self._tf_bits:
            payload["tf"] = self._tf_bits
            payload["hosts_changed"] = [
                row.get("host") for row in ((self._tf_summary or {}).get("hosts") or [])
            ]
            payload["actions"] = [
                row.get("action") for row in ((self._tf_summary or {}).get("hosts") or [])
            ]
        return payload

    def _normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        stamp = now_local(self._clock)
        playbook = str(raw.get("playbook") or self.playbook or "")
        play = str(raw.get("play") or "")
        task = str(raw.get("task") or raw.get("task_name") or "")
        role = str(raw.get("role") or "")
        tags = raw.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        status = str(raw.get("status") or "ok")
        kind = _infer_kind(raw, status)
        note = kind == NOTE_KIND
        phase = raw.get("phase") or raw.get("phase_id")
        if note:
            # A warning is not a step: it must not open or close a group.
            phase = phase or self._current_phase
        elif not phase or status not in {"heartbeat", "phase_end"}:
            mapped = map_phase(
                command=self.command,
                playbook=playbook,
                play=play,
                task=task,
                role=role,
                tags=tags,
                parent_playbook=self.playbook,
                play_file=str(raw.get("play_file") or ""),
                task_file=str(raw.get("task_file") or ""),
                role_path=str(raw.get("role_path") or ""),
                provider=self.provider,
            )
            if mapped:
                phase = mapped
        if not phase and not note:
            # Provider output without a group of its own belongs to the open one.
            phase = self._current_phase or PROVIDER_BASE_GROUP.get(self.provider)
        if not note and status not in {"heartbeat", "phase_end"}:
            self._maybe_phase_change(str(phase) if phase else None, stamp)
        if kind == "task_start" and task:
            self._tasks.add(task)
        if kind == "host_result" and raw.get("host"):
            if str(raw.get("host")) not in {"localhost", "127.0.0.1"}:
                self._hosts.add(str(raw.get("host")))
            if task:
                self._tasks.add(task)
            self._results += 1
            if status == "changed":
                self._changed += 1
            if status == "skipped":
                self._skipped += 1
        # A provider CLI can fail without naming a host (bad Vagrantfile,
        # missing plugin), and that still has to show up as a failed phase.
        if status in {"failed", "unreachable"}:
            self._failed += 1
        title = group_title(str(phase)) if phase else None
        index = None
        count = len(self.catalog) or None
        if phase:
            for i, row in enumerate(self.catalog, start=1):
                if row["id"] == phase:
                    title = row["title"]
                    index = i
                    break
        event: Dict[str, Any] = {
            "time": format_event_time(stamp),
            "run_id": self.run_id,
            "spa_env": self.spa_env,
            "command": self.command,
            "playbook": Path(playbook).stem if playbook else Path(self.playbook).stem,
            "play_file": _stem(str(raw.get("play_file") or "")) or None,
            "task_file": str(raw.get("task_file") or "") or None,
            "kind": kind,
            "source": raw.get("source") or None,
            "phase": phase,
            "phase_id": phase,
            "phase_title": title,
            "phase_index": index if index is not None else self._phase_index,
            "phase_count": count,
            "ok": raw.get("ok"),
            "play": play or None,
            "task": task or None,
            "role": role or None,
            "host": raw.get("host") or None,
            "status": status,
            "duration_ms": raw.get("duration_ms"),
            "msg": redact(raw.get("msg") or raw.get("task_name") or task or ""),
            "handler": bool(raw.get("handler")),
            "task_uuid": raw.get("task_uuid") or None,
            "recap": redact(raw.get("recap")) if raw.get("recap") else None,
            "tf_summary": redact(raw.get("tf_summary")) if raw.get("tf_summary") else None,
            "tasks": raw.get("tasks", len(self._tasks)),
            "hosts_n": len(self._hosts),
            "changed": raw.get("changed", self._changed),
        }
        if status in {"failed", "unreachable"}:
            self._last_failure = {
                "phase": phase,
                "host": event.get("host"),
                "task": event.get("task"),
            }
        return {key: value for key, value in event.items() if value is not None and value != ""}

    def _catalog_index(self, phase: Optional[str]) -> Optional[int]:
        for i, row in enumerate(self.catalog, start=1):
            if row["id"] == phase:
                return i
        return None

    def _maybe_phase_change(self, phase: Optional[str], stamp: datetime) -> None:
        if not phase or phase == self._current_phase:
            return
        # Terraform provision/destroy catalogs are ordered; late setup tasks can
        # map back to an earlier id and should fold into the open phase.
        candidate = self._catalog_index(phase)
        if (
            self.command in {"provision", "destroy"}
            and candidate is not None
            and self._phase_index is not None
            and candidate <= self._phase_index
        ):
            return
        previous = self._current_phase
        if previous:
            self._write_phase_marker(
                "phase_end",
                previous,
                stamp,
                extra={
                    "ok": True,
                    "phase_title": self._phase_title,
                    "phase_index": self._phase_index,
                    "phase_count": len(self.catalog) or None,
                    "tasks": len(self._tasks),
                    "hosts": len(self._hosts),
                    "results": self._results,
                    "changed": self._changed,
                    "skipped": self._skipped,
                },
            )
        self._current_phase = phase
        self._phase_index = candidate
        self._phase_title = group_title(phase)
        self._reset_phase_stats()
        self._write_phase_marker(
            "phase_start",
            phase,
            stamp,
            extra={
                "phase_title": self._phase_title,
                "phase_index": self._phase_index,
                "phase_count": len(self.catalog) or None,
            },
        )

    def _write_phase_marker(
        self, status: str, phase: str, stamp: datetime, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        event: Dict[str, Any] = {
            "time": format_event_time(stamp),
            "run_id": self.run_id,
            "spa_env": self.spa_env,
            "command": self.command,
            "kind": status,
            "playbook": Path(self.playbook).stem if self.playbook else None,
            "phase": phase,
            "phase_id": phase,
            "status": status,
        }
        if extra:
            event.update(extra)
        line = json.dumps({k: v for k, v in event.items() if v is not None}, default=str)
        self._handle.write(line + "\n")
        self._handle.flush()
        self._render(event)

    def _phase_line_text(self, *, final: bool, failed_run: bool = False, width: Optional[int] = None) -> str:
        prefix = format_headline_time(self._phase_started or now_local(self._clock))
        title = self._phase_title or group_title(self._current_phase)
        head = "%s  %s" % (self.command.capitalize(), title)
        # "tasks" counts distinct task names, "changed"/"skipped" count task-host
        # results, so changed is shown against the result total to keep the unit
        # obvious (changed 131/625 means 131 of 625 results changed something).
        changed = "changed %s/%s" % (self._changed, self._results) if self._changed else ""
        skipped = "skipped %s" % self._skipped if self._skipped else ""
        failed = "failed %s" % self._failed if self._failed else ""
        counters: List[str] = []
        if self._tasks:
            counters.append("tasks %s" % len(self._tasks))
        if self._hosts:
            counters.append("hosts %s" % len(self._hosts))
        counters.extend(part for part in (changed, skipped, failed) if part)
        leaner: List[List[str]] = [
            [part for part in counters if part != skipped],
            [part for part in (changed, failed) if part],
        ]
        tf = self._tf_bits if (self._current_phase or "") in TF_CHANGE_PHASES else ""
        if tf:
            # What Terraform changes beats localhost task bookkeeping.
            counters = [failed] if failed else []
            leaner = []
        tail: List[str] = []
        if self._phase_started is not None:
            tail.append(format_elapsed((now_local(self._clock) - self._phase_started).total_seconds()))
        if final:
            tail.append(self._phase_outcome(failed_run=failed_run))

        def assemble(shown_counters: Sequence[str], shown_tf: str, shown_prefix: str = prefix, shown_head: str = head) -> str:
            parts = [shown_prefix, shown_head, *shown_counters]
            if shown_tf:
                parts.append(shown_tf)
            parts.extend(tail)
            return "  ".join(str(p) for p in parts if p)

        text = assemble(counters, tf)
        if width is None or len(text) <= width:
            return text
        # Elapsed time and status carry the most meaning, so shrink the middle
        # (Terraform details first, then counters) instead of cutting the tail.
        if tf:
            for variant in (self._tf_terse, ""):
                if variant == tf:
                    continue
                text = assemble(counters, variant)
                if len(text) <= width:
                    return text
            room = width - len(assemble(counters, "")) - 2
            if room >= 12:
                return assemble(counters, tf[: room - 1] + "\u2026")
        for lean in leaner:
            if lean == counters:
                continue
            candidate = assemble(lean, "")
            if len(candidate) <= width:
                return candidate
        short_head = title
        for candidate in (
            assemble([], ""),
            assemble([], "", shown_prefix=""),
            assemble([], "", shown_prefix="", shown_head=short_head),
        ):
            if len(candidate) <= width:
                return candidate
        text = assemble([], "", shown_prefix="", shown_head=short_head)
        return text[: max(0, width - 1)] + "\u2026"

    def _phase_outcome(self, *, failed_run: bool = False) -> str:
        if failed_run or self._failed:
            return "failed"
        if self._changed or (
            self._tf_bits and (self._current_phase or "") in TF_CHANGE_PHASES
        ):
            return "changed"
        return "ok"

    def _phase_line_color(self, *, final: bool, failed_run: bool = False) -> str:
        if not final:
            return "cyan"
        outcome = self._phase_outcome(failed_run=failed_run)
        if outcome == "failed":
            return "red"
        if outcome == "changed":
            return "yellow"
        return "green"

    def _emit_phase_line(self, *, final: bool, failed_run: bool = False) -> None:
        color = self._phase_line_color(final=final, failed_run=failed_run)
        if self._live_cr:
            # A line wider than the terminal wraps, and \r then only rewrites
            # the last visual row, smearing fragments across the screen.
            limit = self._terminal_width() - 1
            text = self._phase_line_text(final=final, failed_run=failed_run, width=limit)
            self._write_live(text, color, finalize=final)
            return
        text = self._phase_line_text(final=final, failed_run=failed_run)
        if final or not self._live_open:
            self._write_stderr(_paint(text, color, self._color))

    def _terminal_width(self) -> int:
        try:
            return max(20, shutil.get_terminal_size(fallback=(100, 24)).columns)
        except Exception:  # pragma: no cover - defensive
            return 100

    def _write_live(self, text: str, color: str = "", *, finalize: bool) -> None:
        stream = self._stream
        if self._live_cr:
            limit = self._terminal_width() - 1
            plain = _strip_ansi(text)
            if len(plain) > limit:
                plain = plain[: max(0, limit - 1)] + "\u2026"
            painted = _paint(plain, color, self._color)
            pad = max(0, min(self._live_width, limit) - len(plain))
            if finalize:
                stream.write("\r" + painted + (" " * pad) + "\n")
                self._live_open = False
                self._live_width = 0
            else:
                stream.write("\r" + painted + (" " * pad))
                self._live_open = True
                self._live_width = max(self._live_width, len(plain))
            stream.flush()
            return
        if finalize or not self._live_open:
            painted = _paint(text, color, self._color)
            stream.write(painted if painted.endswith("\n") else painted + "\n")
            stream.flush()
            self._live_open = not finalize

    def _break_live(self) -> None:
        if self._live_cr and self._live_open:
            self._stream.write("\n")
            self._stream.flush()
            self._live_open = False
            self._live_width = 0

    def _render(self, event: Dict[str, Any]) -> None:
        status = event.get("status")
        kind = str(event.get("kind") or status or "")
        if self.agent:
            if status == "phase_start":
                self._write_stderr(json.dumps(self._progress_payload(event, "running"), default=str))
            elif status == "heartbeat":
                self._write_stderr(json.dumps(self._progress_payload(event, "running"), default=str))
            elif status == "phase_end":
                state = "failed" if event.get("ok") is False or self._failed else "ok"
                self._write_stderr(json.dumps(self._progress_payload(event, state), default=str))
            elif status == "tf_changes":
                self._write_stderr(json.dumps(self._progress_payload(event, "running"), default=str))
            elif status in {"failed", "unreachable"}:
                payload = {
                    "type": "progress",
                    "phase": event.get("phase"),
                    "status": "failed",
                    "host": event.get("host"),
                    "task": event.get("task"),
                }
                self._write_stderr(json.dumps(payload, default=str))
            return
        if self.ansible_output:
            if not self.native_output:
                self._render_ansible_live(event, kind)
            return
        if status == "phase_start":
            self._emit_phase_line(final=False)
            return
        if status == "heartbeat":
            if self._live_cr:
                self._emit_phase_line(final=False)
            return
        if status == "phase_end":
            self._emit_phase_line(final=True, failed_run=event.get("ok") is False)
            return
        if status == "tf_changes":
            if self._live_cr:
                self._emit_phase_line(final=False)
            return
        if status in {"failed", "unreachable"}:
            self._break_live()
            # A provider line is its own task and message; print it once.
            parts: List[str] = []
            for part in (event.get("host"), event.get("task"), event.get("msg")):
                text = str(part or "").strip()
                if text and text not in parts:
                    parts.append(text)
            self._write_stderr(_paint("  ".join(["failed", *parts]), "red", self._color))
            if self._current_phase and self._live_cr:
                self._emit_phase_line(final=False)
            return
        if kind == NOTE_KIND:
            # Kept in the transcript; Ansible warnings are noise on the live line.
            return
        if kind in {"task_start", "play_start", "recap"} or event.get("handler"):
            return
        if status == "skipped":
            if self._live_cr:
                self._emit_phase_line(final=False)
            return
        if kind == "host_result" and self._live_cr:
            self._emit_phase_line(final=False)

    def _render_ansible_live(self, event: Dict[str, Any], kind: str) -> None:
        if kind == "tf_changes":
            summary = event.get("tf_summary") or self._tf_summary
            if summary:
                self._write_stderr(format_tf_replay(summary).rstrip("\n"))
            return
        text = render_replay_text([event]).rstrip("\n")
        if text:
            self._write_stderr(text)

    def _write_stderr(self, text: str) -> None:
        stream = self._stream
        stream.write(text if text.endswith("\n") else text + "\n")
        stream.flush()

    def _write_meta(self, rc: Optional[int], ended: Optional[datetime]) -> None:
        duration = None
        if ended is not None:
            duration = int((ended - self.started_at).total_seconds() * 1000)
        payload = {
            "run_id": self.run_id,
            "command": self.command,
            "playbook": self.playbook,
            "spa_env": self.spa_env,
            "start": format_event_time(self.started_at),
            "end": format_event_time(ended) if ended is not None else None,
            "duration_ms": duration,
            "rc": rc,
            "log": str(self.jsonl_path),
        }
        self.meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def list_runs(paths: SpaPaths) -> List[Dict[str, Any]]:
    folder = logs_dir(paths)
    if not folder.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for meta in sorted(folder.glob("*" + META_SUFFIX)):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data.setdefault("run_id", meta.name[: -len(META_SUFFIX)])
            rows.append(data)
    rows.sort(key=lambda row: str(row.get("start") or row.get("run_id") or ""), reverse=True)
    return rows


def load_run(paths: SpaPaths, run_id: str) -> Optional[Dict[str, Any]]:
    folder = logs_dir(paths)
    meta = folder / (run_id + META_SUFFIX)
    jsonl = folder / (run_id + JSONL_SUFFIX)
    if not meta.is_file() and not jsonl.is_file():
        matches = [row for row in list_runs(paths) if str(row.get("run_id", "")).startswith(run_id)]
        if len(matches) == 1:
            run_id = str(matches[0]["run_id"])
            meta = folder / (run_id + META_SUFFIX)
            jsonl = folder / (run_id + JSONL_SUFFIX)
        else:
            return None
    payload: Dict[str, Any] = {}
    if meta.is_file():
        try:
            loaded = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    payload["run_id"] = payload.get("run_id") or run_id
    payload["log"] = str(jsonl if jsonl.is_file() else payload.get("log") or jsonl)
    return payload


def read_jsonl(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def follow_jsonl(
    path: Path,
    *,
    idle_passes: int = 3,
    sleep_s: float = 0.2,
    stream: Optional[TextIO] = None,
    ansible_output: bool = False,
) -> int:
    """Print new JSONL lines. Stops after idle_passes with no growth (tests); infinite if idle_passes < 0."""
    out = stream if stream is not None else sys.stdout
    offset = 0
    idle = 0
    leftover = ""
    while True:
        if path.is_file():
            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                chunk = handle.read()
                offset = handle.tell()
            if chunk:
                if ansible_output:
                    leftover += chunk
                    lines = leftover.split("\n")
                    leftover = lines[-1]
                    events = []
                    for line in lines[:-1]:
                        text = line.strip()
                        if not text.startswith("{"):
                            continue
                        try:
                            row = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(row, dict):
                            events.append(row)
                    rendered = render_replay_text(events)
                    if rendered:
                        out.write(rendered)
                        out.flush()
                else:
                    out.write(chunk)
                    out.flush()
                idle = 0
            else:
                idle += 1
        else:
            idle += 1
        if idle_passes >= 0 and idle >= idle_passes:
            return 0
        time.sleep(sleep_s)
