"""User-facing host selection (names or roles). Ansible --limit stays internal."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


class HostsError(ValueError):
    """A --hosts token did not match inventory names or roles."""


def parse_host_tokens(values: Optional[Sequence[str]]) -> List[str]:
    """Flatten repeatable --hosts values, including comma-separated lists."""
    tokens: List[str] = []
    for item in values or []:
        if not item:
            continue
        for part in str(item).split(","):
            part = part.strip()
            if part:
                tokens.append(part)
    return tokens


def inventory_hostnames(inventory: dict) -> List[str]:
    hosts: Set[str] = set()
    meta = (inventory or {}).get("_meta") or {}
    hostvars = meta.get("hostvars") or {}
    hosts.update(hostvars.keys())
    for name, group in (inventory or {}).items():
        if name == "_meta" or not isinstance(group, dict):
            continue
        for host in group.get("hosts") or []:
            hosts.add(host)
    return sorted(hosts)


def inventory_roles(inventory: dict) -> Dict[str, List[str]]:
    """Map role id (indexer, search_head, …) to hostnames from role_* groups."""
    roles: Dict[str, List[str]] = {}
    for name, group in (inventory or {}).items():
        if name == "_meta" or not isinstance(group, dict):
            continue
        if not name.startswith("role_"):
            continue
        role = name[5:]
        members = list(group.get("hosts") or [])
        roles[role] = sorted(set(members))
    return roles


def resolve_hosts(inventory: dict, tokens: Sequence[str]) -> List[str]:
    """Resolve names or roles to inventory hostnames. Unknown token fails."""
    if not tokens:
        return []
    known = inventory_hostnames(inventory)
    known_set = set(known)
    roles = inventory_roles(inventory)
    resolved: List[str] = []
    seen: Set[str] = set()

    def add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            resolved.append(name)

    for token in tokens:
        if token in known_set:
            add(token)
            continue
        role_key = token.replace("-", "_")
        if role_key in roles:
            for host in roles[role_key]:
                add(host)
            continue
        lowered = role_key.lower()
        match = next((key for key in roles if key.lower() == lowered), None)
        if match:
            for host in roles[match]:
                add(host)
            continue
        role_names = ", ".join(sorted(roles)) or "(none)"
        host_names = ", ".join(known) or "(none)"
        raise HostsError(
            "Unknown host or role %r. Known hosts: %s. Known roles: %s."
            % (token, host_names, role_names)
        )
    return resolved


def load_inventory() -> dict:
    """Inventory for display purposes. Never fail a command over a role label."""
    from spa import shell

    try:
        return shell.get_inventory_data()
    except Exception:
        return {}


def group_by_role(inventory: dict, names: Sequence[str]) -> List[Tuple[str, List[str]]]:
    """Group hosts by their role set so long lists stay one line per role."""
    roles = inventory_roles(inventory)
    grouped: Dict[str, List[str]] = {}
    for name in names:
        labels = sorted(role for role, members in roles.items() if name in members)
        key = ", ".join(label.replace("_", " ") for label in labels) or "no role"
        grouped.setdefault(key, []).append(name)
    return [(label, sorted(hosts)) for label, hosts in sorted(grouped.items())]


def format_names(names: Sequence[str], width: int = 72) -> str:
    """Join names, trimming to a count suffix when the line would run long."""
    names = list(names)
    joined = ", ".join(names)
    if len(joined) <= width:
        return joined
    shown: List[str] = []
    used = 0
    for name in names:
        if used + len(name) + 2 > width:
            break
        shown.append(name)
        used += len(name) + 2
    remaining = len(names) - len(shown)
    if not shown:
        return "%d hosts" % len(names)
    return "%s, +%d more" % (", ".join(shown), remaining)


def format_host_groups(
    inventory: dict, names: Sequence[str], indent: str = "  "
) -> List[str]:
    """Render one line per role: '  indexer (4): idx1, idx2, idx3, idx4'."""
    lines = []
    for label, hosts in group_by_role(inventory, names):
        lines.append(
            "%s%s (%d): %s" % (indent, label, len(hosts), format_names(hosts))
        )
    return lines


def with_ansible_limit(extra: Optional[Iterable[str]], hostnames: Optional[Sequence[str]]) -> List[str]:
    """Inject ansible-playbook --limit from resolved hosts. Existing --limit wins."""
    args = list(extra or [])
    if not hostnames:
        return args
    if "--limit" in args:
        return args
    return ["--limit", ":".join(hostnames), *args]
