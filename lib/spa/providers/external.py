"""SSH access to hosts SPA did not create."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from spa.paths import SpaPaths
from spa.providers import (
    ProviderError,
    ProvisionState,
    inventory_hostnames_from_file,
    load_deployment_config,
)
from spa.providers.classify import classify_hostnames, env_is_external_only, is_external_host

SshRunner = Callable[[Sequence[str]], int]

_CONNECTION_KEYS = (
    "ansible_host",
    "ansible_user",
    "ansible_port",
    "ansible_ssh_private_key_file",
)


def _register_sentence(name: str) -> str:
    return (
        "host %s has no SSH inventory line. "
        "Run: spa hosts register %s --address ADDRESS --user USER --key PATH --yes"
        % (name, name)
    )


def _expanded_key(key_path: str) -> Path:
    return Path(key_path).expanduser()


def probe_ssh(
    address: str,
    user: str,
    key_path: str,
    port: int,
    run: SshRunner,
) -> None:
    """One BatchMode ssh true. Does not read the key or run sudo."""
    if shutil.which("ssh") is None:
        raise ProviderError("ssh is not on PATH")
    key = _expanded_key(key_path)
    if not key.is_file():
        raise ProviderError("key file not found: %s" % key)
    argv = [
        "ssh",
        "-i",
        str(key),
        "-p",
        str(port or 22),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "%s@%s" % (user, address),
        "true",
    ]
    if run(argv) != 0:
        raise ProviderError("ssh failed for %s@%s" % (user, address))


def inventory_line(name: str, address: str, user: str, key_path: str, port: int) -> str:
    key = str(_expanded_key(key_path))
    parts = [
        name,
        "ansible_host=%s" % json.dumps(address),
        "ansible_user=%s" % json.dumps(user),
        "ansible_ssh_private_key_file=%s" % json.dumps(key),
    ]
    if int(port or 22) != 22:
        parts.append("ansible_port=%s" % json.dumps(int(port)))
    return " ".join(parts)


def upsert_inventory(path: Path, name: str, line_body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    replaced = False
    out: List[str] = []
    for line in existing:
        stripped = line.strip()
        token = ""
        if stripped and not stripped.startswith("#"):
            token = stripped.split()[0]
        if token == name:
            out.append(line_body)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(line_body)
    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def connection_from_inventory(path: Path, name: str) -> Dict[str, Any]:
    """Address, user, and key from one ``inventory/hosts`` line."""
    line = _inventory_lines(path).get(name)
    if not line:
        return {}
    fields: Dict[str, Any] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            continue
        key, raw = token.split("=", 1)
        try:
            fields[key] = json.loads(raw)
        except json.JSONDecodeError:
            fields[key] = raw
    return fields


def _inventory_lines(path: Path) -> Dict[str, str]:
    lines: Dict[str, str] = {}
    if not path.is_file():
        return lines
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines[stripped.split()[0]] = line
    return lines


def _drop_inventory_name(path: Path, name: str) -> None:
    if not path.is_file():
        return
    kept = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        token = stripped.split()[0] if stripped and not stripped.startswith("#") else ""
        if token != name:
            kept.append(line)
    text = "\n".join(kept)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _external_host_records(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = []
    for host in config.get("splunk_hosts") or []:
        if isinstance(host, dict) and is_external_host(host, config) and host.get("name"):
            records.append(host)
    return records


class RegisterSpec:
    def __init__(
        self,
        name: str,
        address: str,
        user: str,
        key_path: str,
        port: int = 22,
        roles: Sequence[str] = (),
    ) -> None:
        self.name = name
        self.address = address
        self.user = user
        self.key_path = key_path
        self.port = int(port or 22)
        self.roles = tuple(roles)


def _load_document(path: Path):
    from ruamel.yaml import YAML

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    with path.open(encoding="utf-8") as handle:
        document = yaml.load(handle) or {}
    return yaml, document


def _dump_document(yaml, document, path: Path) -> None:
    from spa.init import _bare_external_keys

    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(document, handle)
    path.write_text(_bare_external_keys(path.read_text(encoding="utf-8")), encoding="utf-8")


def _managed_owner(document: Dict[str, Any], name: str) -> Optional[str]:
    managed, _external = classify_hostnames(document)
    if name not in managed:
        return None
    terraform = document.get("terraform") or {}
    if isinstance(terraform, dict):
        names = [key for key, value in terraform.items() if isinstance(value, dict)]
        if len(names) == 1 and names[0] in {"aws", "virtualbox"}:
            return names[0]
    if "virtualbox" in document:
        return "virtualbox"
    return None


def register_host(paths: SpaPaths, spec: RegisterSpec, run: SshRunner) -> Dict[str, Any]:
    """Probe SSH, then write the host and one inventory line."""
    key = _expanded_key(spec.key_path)
    if not key.is_file():
        raise ProviderError("key file not found: %s" % key)
    yaml, document = _load_document(paths.config_file)
    owner = _managed_owner(document, spec.name)
    if owner:
        raise ProviderError(
            "%s is managed by %s. SPA does not take over a managed host."
            % (spec.name, owner)
        )
    probe_ssh(spec.address, spec.user, str(key), spec.port, run)
    terraform = document.get("terraform") or {}
    has_terraform = isinstance(terraform, dict) and any(
        isinstance(value, dict) for value in terraform.values()
    )
    if not has_terraform and "virtualbox" not in document and "external" not in document:
        document["external"] = None
    external_only = env_is_external_only(document)
    hosts = document.get("splunk_hosts")
    if hosts is None:
        document["splunk_hosts"] = []
        hosts = document["splunk_hosts"]
    target = None
    for host in hosts:
        if isinstance(host, dict) and host.get("name") == spec.name:
            target = host
            break
    if target is None:
        target = {"name": spec.name}
        hosts.append(target)
    target.pop("provider", None)
    for field in _CONNECTION_KEYS:
        target.pop(field, None)
    if not external_only and "external" not in target:
        target["external"] = None
    if spec.roles:
        target["roles"] = list(spec.roles)
    _dump_document(yaml, document, paths.config_file)
    line = inventory_line(spec.name, spec.address, spec.user, str(key), spec.port)
    destination = paths.inventory_dir / "hosts"
    upsert_inventory(destination, spec.name, line)
    return {
        "name": spec.name,
        "ansible_host": spec.address,
        "ansible_user": spec.user,
        "ansible_port": spec.port,
        "ansible_ssh_private_key_file": str(key),
        "key": "set",
        "inventory": str(destination),
    }


def unregister_host(paths: SpaPaths, name: str) -> Dict[str, Any]:
    """Drop one inventory line. The config host stays. Does not call ssh."""
    _yaml, document = _load_document(paths.config_file)
    owner = _managed_owner(document, name)
    if owner:
        raise ProviderError("%s is managed by %s. Use spa destroy --yes." % (name, owner))
    hosts_file = paths.inventory_dir / "hosts"
    if name not in _inventory_lines(hosts_file):
        _managed, external = classify_hostnames(document)
        if name in external:
            raise ProviderError(_register_sentence(name))
        raise ProviderError("unknown host: %s" % name)
    _drop_inventory_name(hosts_file, name)
    return {"name": name, "unregistered": True}


class Provider:
    name = "external"

    def __init__(self, paths: SpaPaths, config: Dict[str, Any], run: Optional[SshRunner] = None):
        self.paths = paths
        self.config = config or {}
        self._run = run

    def _runner(self) -> SshRunner:
        if self._run is not None:
            return self._run

        def _default(argv: Sequence[str]) -> int:
            import subprocess

            completed = subprocess.run(list(argv), check=False)
            return completed.returncode

        return _default

    def _hosts(self) -> List[Dict[str, Any]]:
        try:
            document = load_deployment_config(self.paths)
        except ProviderError:
            document = {}
        return _external_host_records(document)

    def provision(self, extra: Optional[Sequence[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        del extra, kwargs
        hosts_file = self.paths.inventory_dir / "hosts"
        previous = _inventory_lines(hosts_file)
        written: List[str] = []
        try:
            for host in self._hosts():
                name = str(host["name"])
                recorded = connection_from_inventory(hosts_file, name)
                address = recorded.get("ansible_host")
                user = recorded.get("ansible_user")
                key_path = recorded.get("ansible_ssh_private_key_file")
                if not (address and user and key_path):
                    raise ProviderError(_register_sentence(name))
                port = int(recorded.get("ansible_port") or 22)
                probe_ssh(str(address), str(user), str(key_path), port, self._runner())
                upsert_inventory(
                    hosts_file,
                    name,
                    inventory_line(name, str(address), str(user), str(key_path), port),
                )
                written.append(name)
        except Exception:
            for name in written:
                if name in previous:
                    upsert_inventory(hosts_file, name, previous[name])
                else:
                    _drop_inventory_name(hosts_file, name)
            raise
        return {"provider": self.name, "action": "provision"}

    def provision_state(self) -> ProvisionState:
        try:
            document = load_deployment_config(self.paths)
        except ProviderError:
            document = {}
        _managed, external = classify_hostnames(document)
        present = set(inventory_hostnames_from_file(self.paths))
        missing = tuple(name for name in external if name not in present)
        hint = ""
        if missing:
            hint = _register_sentence(missing[0]).split("Run: ", 1)[-1]
        return ProvisionState(
            provider=self.name,
            provisioned=not missing,
            reason="" if not missing else "missing inventory lines: %s" % ", ".join(missing),
            hint=hint,
            missing=missing,
        )

    def destroy(self, extra: Optional[Sequence[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        del extra, kwargs
        names = []
        document_path = self.paths.config_file
        from ruamel.yaml import YAML

        yaml = YAML(typ="rt")
        yaml.preserve_quotes = True
        with document_path.open(encoding="utf-8") as handle:
            document = yaml.load(handle) or {}
        for host in document.get("splunk_hosts") or []:
            if not isinstance(host, dict) or not is_external_host(host, document):
                continue
            name = str(host.get("name") or "")
            if name:
                names.append(name)
            for key in _CONNECTION_KEYS:
                host.pop(key, None)
            _drop_inventory_name(self.paths.inventory_dir / "hosts", name)
        with document_path.open("w", encoding="utf-8") as handle:
            yaml.dump(document, handle)
        from spa.init import _bare_external_keys

        document_path.write_text(
            _bare_external_keys(document_path.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        return {
            "provider": self.name,
            "action": "destroy",
            "unregistered": names,
            "note": "Those machines were not shut down.",
        }

    def suspend(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        names = [str(host["name"]) for host in self._hosts()]
        raise ProviderError("SPA does not own power for external hosts: %s" % ", ".join(names))

    def resume(self, **kwargs: Any) -> Dict[str, Any]:
        return self.suspend(**kwargs)

    def host_status(self, name: Optional[str] = None) -> Dict[str, Any]:
        if name is None:
            return {str(host["name"]): self._one_status(str(host["name"])) for host in self._hosts()}
        return self._one_status(name)

    def _one_status(self, name: str) -> Dict[str, Any]:
        if not any(item.get("name") == name for item in self._hosts()):
            return {"name": name, "state": "unreachable", "reachable": False}
        recorded = connection_from_inventory(self.paths.inventory_dir / "hosts", name)
        try:
            probe_ssh(
                str(recorded.get("ansible_host") or ""),
                str(recorded.get("ansible_user") or ""),
                str(recorded.get("ansible_ssh_private_key_file") or ""),
                int(recorded.get("ansible_port") or 22),
                self._runner(),
            )
        except ProviderError:
            return {"name": name, "state": "unreachable", "reachable": False}
        return {"name": name, "state": "reachable", "reachable": True}
