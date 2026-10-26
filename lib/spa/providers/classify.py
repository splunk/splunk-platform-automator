"""Split splunk_hosts into managed names and external names."""

from typing import Any, Dict, List, Mapping, Tuple

EXTERNAL = "external"


def env_is_external_only(config: Mapping[str, Any]) -> bool:
    """True when ``external:`` is the only provider, including a null value."""
    if "external" not in config:
        return False
    value = config.get("external")
    if value is not None and not isinstance(value, dict):
        return False
    if "virtualbox" in config:
        return False
    terraform = config.get("terraform") or {}
    if isinstance(terraform, dict) and any(isinstance(item, dict) for item in terraform.values()):
        return False
    return True


def is_external_host(host: Mapping[str, Any], config: Mapping[str, Any] = None) -> bool:
    """A host-level ``external:`` block, or every host when the env is external-only."""
    if "external" in host:
        return True
    return bool(config is not None and env_is_external_only(config))


def _expand_host(host: Mapping[str, Any]) -> List[str]:
    if host.get("name"):
        return [str(host["name"])]
    listed = host.get("list")
    if listed:
        return [str(item) for item in listed]
    iteration = host.get("iter")
    if not isinstance(iteration, dict):
        return []
    numbers = str(iteration.get("numbers") or "")
    if ".." not in numbers:
        return []
    start_text, end_text = numbers.split("..", 1)
    try:
        start, end = int(start_text), int(end_text)
    except ValueError:
        return []
    prefix = iteration.get("prefix") or ""
    postfix = iteration.get("postfix") or ""
    width = len(end_text)
    return [
        "%s%s%s" % (prefix, str(number).zfill(width), postfix)
        for number in range(start, end + 1)
    ]


def classify_hostnames(config: Mapping[str, Any]) -> Tuple[List[str], List[str]]:
    """Return (managed, external) hostnames in config order."""
    managed: List[str] = []
    external: List[str] = []
    for host in config.get("splunk_hosts") or []:
        if not isinstance(host, dict):
            continue
        names = _expand_host(host)
        if is_external_host(host, config):
            external.extend(names)
        else:
            managed.extend(names)
    return managed, external
