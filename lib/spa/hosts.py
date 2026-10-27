"""User-facing host selection (names or roles). Ansible --limit stays internal."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


def allowed_role_names() -> List[str]:
    """Role ids from ``AllowedRole`` in schema.py, in source order.

    Reads the file. Importing schema needs pydantic, and ``spa`` must still
    start when that module is not installed yet.
    """
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "ansible" / "plugins" / "inventory" / "schema.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "AllowedRole":
            continue
        names: List[str] = []
        for item in node.body:
            value = item.value if isinstance(item, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                names.append(value.value)
        return names
    return []


class HostsError(ValueError):
    """A host check or --hosts selection failed."""

    def __init__(self, message: str = "", rows: Optional[Sequence[dict]] = None):
        super().__init__(message)
        self.rows = list(rows or [])


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


def _interpreter_failure(message: str) -> bool:
    """Ansible could not execute a module because the remote Python path is missing."""
    text = message.lower()
    return "module interpreter" in text or ("interpreter" in text and "not found" in text)


def _ping_failure_text(rows: Sequence[dict]) -> str:
    """One line per host. A become failure says SSH worked and sudo did not."""
    lines = []
    for row in rows:
        name = row["name"]
        if row.get("ok"):
            lines.append("%s ok" % name)
            continue
        message = str(row.get("message") or "").strip()
        if row.get("ssh") and row.get("become") is False and not _interpreter_failure(message):
            line = "SSH works for %s, but passwordless sudo to root failed." % name
        elif row.get("ssh") and _interpreter_failure(message):
            line = "SSH works for %s, but the remote module interpreter was not found." % name
        elif not row.get("ssh"):
            line = "SSH failed for %s." % name
        else:
            line = "Ansible ping failed for %s." % name
        if message:
            line = "%s %s" % (line, message)
        lines.append(line)
    return "\n".join(lines)


_ARCH_MACHINE = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}


def _normalize_architecture(value) -> str:
    return _ARCH_MACHINE.get(str(value or "").strip(), "")


def _environment_architecture(document: dict, host: dict) -> str:
    """Architecture on the splunk_environments entry this host belongs to."""
    environments = document.get("splunk_environments") or []
    if not isinstance(environments, list):
        return ""
    defaults = document.get("splunk_defaults") or {}
    default_name = "splk"
    if isinstance(defaults, dict) and defaults.get("splunk_env_name"):
        default_name = str(defaults["splunk_env_name"])
    named = host.get("splunk_env")
    wanted = str(named) if named and str(named) != default_name else default_name
    for environment in environments:
        if not isinstance(environment, dict):
            continue
        if str(environment.get("splunk_env_name") or "") != wanted:
            continue
        value = environment.get("splunk_architecture")
        return str(value) if value else ""
    return ""


def _expected_architecture(document: dict, name: str) -> str:
    """Host override, then that host's environment, then splunk_defaults, then amd64."""
    from spa.providers.classify import _expand_host

    matched = None
    for host in document.get("splunk_hosts") or []:
        if isinstance(host, dict) and name in _expand_host(host):
            matched = host
            override = host.get("splunk_architecture")
            if override:
                return str(override)
            break
    if matched is not None:
        environment = _environment_architecture(document, matched)
        if environment:
            return environment
    defaults = document.get("splunk_defaults") or {}
    if isinstance(defaults, dict) and defaults.get("splunk_architecture"):
        return str(defaults["splunk_architecture"])
    return "amd64"


def _architecture_failure_text(rows: Sequence[dict]) -> str:
    lines = []
    for row in rows:
        name = row["name"]
        if row.get("ok"):
            lines.append("%s ok" % name)
            continue
        actual = row.get("architecture")
        if not actual:
            lines.append("%s architecture was not reported" % name)
            continue
        lines.append(
            "%s architecture mismatch: config %s, host %s"
            % (name, row.get("expected_architecture"), actual)
        )
    return "\n".join(lines)


def ping_hosts(
    paths,
    hosts: Optional[Sequence[str]] = None,
    run=None,
) -> Dict[str, Any]:
    """Become ping, then compare splunk_architecture with the machine.

    Expected architecture is the host override, then that host's
    splunk_environments entry, then splunk_defaults, then amd64.

    Does not write config or inventory and does not deploy.
    """
    from spa.providers import inventory_hostnames_from_file, load_deployment_config
    from spa.providers.classify import classify_hostnames
    from spa.providers.external import _register_sentence
    from spa.shell import ansible_architecture, ansible_ping, drop_discovered_interpreter_cache

    document = load_deployment_config(paths)
    managed, external = classify_hostnames(document)
    selected = list(hosts) if hosts else [*managed, *external]
    present = set(inventory_hostnames_from_file(paths))
    missing = [name for name in selected if name not in present]
    if missing:
        name = missing[0]
        if name in external:
            raise HostsError(_register_sentence(name))
        raise HostsError(
            "hosts not provisioned: %s\nRun: spa provision --yes" % ", ".join(missing)
        )
    drop_discovered_interpreter_cache(selected, paths)
    rows, problem = ansible_ping(selected, paths=paths, become=True, run=run)
    if problem:
        raise HostsError(problem)
    if any(not row.get("ok") for row in rows):
        raise HostsError(_ping_failure_text(rows))
    facts, problem = ansible_architecture(selected, paths=paths, run=run)
    if problem:
        raise HostsError(problem)
    for row in rows:
        expected = _expected_architecture(document, row["name"])
        actual = facts.get(row["name"])
        row["expected_architecture"] = expected
        row["architecture"] = actual or ""
        if _normalize_architecture(expected) != _normalize_architecture(actual):
            row["ok"] = False
    if any(not row.get("ok") for row in rows):
        raise HostsError(_architecture_failure_text(rows), rows)
    return {"hosts": rows}
