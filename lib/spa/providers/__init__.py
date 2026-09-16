"""Config-driven infrastructure provider dispatch for spa lifecycle commands."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, Tuple

import yaml

from spa.paths import SpaPaths


class ProviderError(RuntimeError):
    """The deployment provider is missing, ambiguous, or cannot run an action."""


@dataclass(frozen=True)
class ProviderSelection:
    name: str
    config: Dict[str, Any]


class HostStatusProvider(Protocol):
    """Optional provider capability consumed by `spa hosts list --status`."""

    name: str

    def host_status(self) -> Dict[str, Dict[str, Any]]:
        """Map inventory names/addresses to state and reachability."""
        ...


@dataclass(frozen=True)
class ProvisionState:
    """Whether every config host is present in the provisioned inventory."""

    provider: str
    provisioned: bool
    reason: str = ""
    hint: str = ""
    missing: Tuple[str, ...] = ()


class ProvisionStateProvider(Protocol):
    """Optional provider capability consumed by `spa deploy`."""

    name: str

    def provision_state(self) -> ProvisionState:
        """Return whether this env has been provisioned for every config host."""
        ...


def expected_hostnames(config: Dict[str, Any]) -> List[str]:
    """Expand splunk_hosts name / list / iter the same way the inventory plugin does."""
    names: List[str] = []
    for host in config.get("splunk_hosts") or []:
        if not isinstance(host, dict):
            continue
        if host.get("name"):
            names.append(str(host["name"]))
            continue
        listed = host.get("list")
        if listed:
            names.extend(str(item) for item in listed)
            continue
        iteration = host.get("iter")
        if not isinstance(iteration, dict):
            continue
        numbers = str(iteration.get("numbers") or "")
        if ".." not in numbers:
            continue
        start_text, end_text = numbers.split("..", 1)
        try:
            start, end = int(start_text), int(end_text)
        except ValueError:
            continue
        prefix = iteration.get("prefix") or ""
        postfix = iteration.get("postfix") or ""
        width = len(end_text)
        for number in range(start, end + 1):
            names.append("%s%s%s" % (prefix, str(number).zfill(width), postfix))
    return names


def inventory_hostnames_from_file(paths: SpaPaths) -> List[str]:
    """First token of each non-comment line in inventory/hosts."""
    hosts_file = paths.inventory_dir / "hosts"
    if not hosts_file.is_file():
        return []
    names: List[str] = []
    try:
        lines = hosts_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.append(stripped.split()[0])
    return names


def check_provisioned(paths: SpaPaths) -> ProvisionState:
    """Block spa deploy only when a spa-managed provider can prove hosts are missing."""
    try:
        config = load_deployment_config(paths)
    except ProviderError:
        return ProvisionState(provider="unknown", provisioned=True)

    terraform = config.get("terraform") or {}
    if isinstance(terraform, dict):
        configured = [
            name for name, value in terraform.items() if isinstance(value, dict)
        ]
        if len(configured) == 1 and configured[0] in PROVIDER_MODULES:
            return get_provider(paths).provision_state()
    if "virtualbox" in config:
        return get_provider(paths).provision_state()
    return ProvisionState(provider="none", provisioned=True)


# Adding GCP later is intentionally a registry change, not a CLI change.
PROVIDER_MODULES = {
    "aws": "spa.providers.aws",
    "virtualbox": "spa.providers.virtualbox",
}


def load_deployment_config(paths: SpaPaths) -> Dict[str, Any]:
    if not paths.config_file.is_file():
        raise ProviderError("Splunk config not found: %s" % paths.config_file)
    try:
        with paths.config_file.open(encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ProviderError("Cannot read deployment type from %s: %s" % (paths.config_file, exc))
    if not isinstance(config, dict):
        raise ProviderError("Splunk config root must be a mapping: %s" % paths.config_file)
    return config


def detect_provider(paths: SpaPaths) -> ProviderSelection:
    """Detect one infrastructure provider from splunk_config.yml."""
    config = load_deployment_config(paths)
    terraform = config.get("terraform") or {}
    if not isinstance(terraform, dict):
        raise ProviderError("terraform must be a mapping in %s" % paths.config_file)

    configured = [
        name for name, value in terraform.items() if isinstance(value, dict)
    ]
    if len(configured) > 1:
        raise ProviderError(
            "Multiple terraform providers are configured (%s); select exactly one."
            % ", ".join(sorted(configured))
        )
    if configured:
        name = configured[0]
        if name not in PROVIDER_MODULES:
            raise ProviderError(
                "Deployment provider %r is recognized from terraform.%s but is not implemented."
                % (name, name)
            )
        return ProviderSelection(name=name, config=terraform[name])

    if "virtualbox" in config:
        vbox = config.get("virtualbox")
        if vbox is not None and not isinstance(vbox, dict):
            raise ProviderError("virtualbox must be a mapping in %s" % paths.config_file)
        return ProviderSelection(name="virtualbox", config=vbox or {})
    if "aws" in config:
        raise ProviderError(
            "The legacy top-level aws section is inventory-only. "
            "spa infrastructure commands require terraform.aws."
        )
    raise ProviderError(
        "No managed deployment provider found in %s "
        "(expected terraform.<provider> or virtualbox; implemented: terraform.aws, virtualbox)."
        % paths.config_file
    )


def get_provider(paths: SpaPaths):
    selection = detect_provider(paths)
    module = importlib.import_module(PROVIDER_MODULES[selection.name])
    return module.Provider(paths, selection.config)
