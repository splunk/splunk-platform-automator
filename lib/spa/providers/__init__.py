"""Config-driven infrastructure provider dispatch for spa lifecycle commands."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Dict, Protocol

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


# Adding GCP later is intentionally a registry change, not a CLI change.
PROVIDER_MODULES = {
    "aws": "spa.providers.aws",
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
        raise ProviderError(
            "VirtualBox lifecycle is not managed by spa yet. "
            "Run vagrant from SPA_HOME for now."
        )
    if "aws" in config:
        raise ProviderError(
            "The legacy top-level aws section is inventory-only. "
            "spa infrastructure commands require terraform.aws."
        )
    raise ProviderError(
        "No managed deployment provider found in %s "
        "(expected terraform.<provider>; currently implemented: terraform.aws)."
        % paths.config_file
    )


def get_provider(paths: SpaPaths):
    selection = detect_provider(paths)
    module = importlib.import_module(PROVIDER_MODULES[selection.name])
    return module.Provider(paths, selection.config)
