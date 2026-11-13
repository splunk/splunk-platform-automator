"""Config-driven infrastructure provider dispatch for spa lifecycle commands."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

DEPLOY_HINT = "spa deploy --yes"

from spa.paths import SpaPaths


class ProviderError(RuntimeError):
    """The deployment provider is missing, ambiguous, or cannot run an action."""

    def __init__(self, message: str, *, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


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

    def payload(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "provisioned": self.provisioned,
            "reason": self.reason,
            "hint": self.hint,
            "missing": list(self.missing),
        }

    def message(self, extra_line: Optional[str] = None) -> str:
        """Human error for commands that cannot run until hosts are provisioned."""
        lines = []
        if self.missing:
            lines.append("hosts not provisioned: %s" % format_host_names(self.missing))
        else:
            lines.append("hosts not provisioned")
        if self.provider and self.provider not in {"unknown", "none"}:
            lines.append("provider: %s" % self.provider)
        if self.hint:
            lines.append("Run: %s" % self.hint)
        if extra_line:
            lines.append(extra_line)
        return "\n".join(lines)


class ProvisionStateProvider(Protocol):
    """Optional provider capability consumed by `spa deploy`."""

    name: str

    def provision_state(self) -> ProvisionState:
        """Return whether this env has been provisioned for every config host."""
        ...


def format_host_names(names: Sequence[str], cap: int = 12) -> str:
    shown = list(names)
    extra = ""
    if len(shown) > cap:
        extra = ", +%d more" % (len(shown) - cap)
        shown = shown[:cap]
    return "%s%s" % (", ".join(shown), extra)


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


@dataclass(frozen=True)
class DeployCreatePlan:
    """Whether spa deploy should create managed hosts before the playbook."""

    will_create: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


def lookup_provision_state(paths: SpaPaths) -> Optional[ProvisionState]:
    """Return provision state, or None when the provider lookup itself fails."""
    try:
        return check_provisioned(paths)
    except ProviderError:
        return None


def deploy_create_plan(
    paths: SpaPaths, hosts: Optional[Sequence[str]] = None
) -> DeployCreatePlan:
    """Create-or-refuse decision for spa deploy. Same path for every provider."""
    state = lookup_provision_state(paths)
    if state is None or state.provisioned:
        return DeployCreatePlan(will_create=False)
    from spa.hosts import parse_host_tokens
    from spa.providers.classify import classify_hostnames, hostnames_for_tokens

    try:
        document = load_deployment_config(paths)
    except Exception:
        document = {}
    _managed, external = classify_hostnames(document)
    tokens = parse_host_tokens(hosts)
    if tokens:
        selected = hostnames_for_tokens(document, tokens)
        if not selected:
            return DeployCreatePlan(will_create=False)
        missing = [name for name in state.missing if name in selected]
        if not missing:
            return DeployCreatePlan(will_create=False)
    else:
        missing = list(state.missing)
        if not missing and state.hint == DEPLOY_HINT:
            missing = [name for name in expected_hostnames(document) if name not in set(external)]
        if not missing:
            lines = [line for line in (state.reason, ("Run: %s" % state.hint) if state.hint else "") if line]
            return DeployCreatePlan(
                will_create=False,
                error="\n".join(lines) or state.message(),
                data=state.payload(),
            )
    external_set = set(external)
    external_missing = [name for name in missing if name in external_set]
    managed_missing = [name for name in missing if name not in external_set]
    if external_missing and not managed_missing:
        from spa.providers.external import _register_sentence

        return DeployCreatePlan(
            will_create=False,
            error=_register_sentence(external_missing[0]),
            data=state.payload(),
        )
    return DeployCreatePlan(will_create=bool(managed_missing))


def check_provisioned(paths: SpaPaths) -> ProvisionState:
    """Whether every config host is present. Deploy uses this internally; other commands may refuse."""
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
    if "ccm" in config:
        return get_provider(paths).provision_state()
    if "external" in config:
        return get_provider(paths).provision_state()
    return ProvisionState(provider="none", provisioned=True)


# Adding GCP later is intentionally a registry change, not a CLI change.
PROVIDER_MODULES = {
    "aws": "spa.providers.aws",
    "virtualbox": "spa.providers.virtualbox",
    "ccm": "spa.providers.ccm",
    "external": "spa.providers.external",
}

# Stdlib-only copy of Provider.order. provider_ids() must not import provider
# modules: spa doctor / spa venv still run before a venv (and PyYAML) exists.
# Keep these integers in lockstep with Provider.order (CCM 10, AWS 20,
# external 30, VirtualBox 40).
PROVIDER_ORDER = {
    "ccm": 10,
    "aws": 20,
    "external": 30,
    "virtualbox": 40,
}


def load_deployment_config(paths: SpaPaths) -> Dict[str, Any]:
    # Parser construction imports this package for spa provider ccm help.
    # spa doctor / spa venv must still run before a venv (and PyYAML) exists.
    import yaml

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
        if "ccm" in config:
            raise ProviderError(
                "Multiple providers are configured (ccm, terraform.%s); select exactly one."
                % configured[0]
            )
        name = configured[0]
        if name not in PROVIDER_MODULES:
            raise ProviderError(
                "Deployment provider %r is recognized from terraform.%s but is not implemented."
                % (name, name)
            )
        return ProviderSelection(name=name, config=terraform[name])

    if "ccm" in config and "virtualbox" in config:
        raise ProviderError(
            "Multiple providers are configured (ccm, virtualbox); select exactly one."
        )
    if "ccm" in config:
        ccm = config.get("ccm")
        if ccm is not None and not isinstance(ccm, dict):
            raise ProviderError("ccm must be a mapping in %s" % paths.config_file)
        return ProviderSelection(name="ccm", config=ccm or {})
    if "virtualbox" in config:
        vbox = config.get("virtualbox")
        if vbox is not None and not isinstance(vbox, dict):
            raise ProviderError("virtualbox must be a mapping in %s" % paths.config_file)
        return ProviderSelection(name="virtualbox", config=vbox or {})
    if "external" in config:
        external = config.get("external")
        if external is not None and not isinstance(external, dict):
            raise ProviderError("external must be a mapping in %s" % paths.config_file)
        return ProviderSelection(name="external", config=external or {})
    raise ProviderError(
        "No managed deployment provider found in %s "
        "(expected terraform.<provider>, virtualbox, or ccm; "
        "implemented: terraform.aws, virtualbox, ccm)."
        % paths.config_file
    )


def provider_is_remote(provider_id: str) -> bool:
    """Whether init should merge remote-provider defaults for this provider.

    Reads ``Provider.remote`` from the registered module so callers do not
    hardcode aws / ccm. VirtualBox is local. AWS, CCM, and external are
    remote. A later unregistered provider is remote unless it is VirtualBox.
    """
    name = (provider_id or "").strip().lower()
    if name in {"terraform.aws", "terraform"}:
        name = "aws"
    if name in {"vbox", "vb"}:
        name = "virtualbox"
    module_name = PROVIDER_MODULES.get(name)
    if module_name is None:
        return name != "virtualbox"
    module = importlib.import_module(module_name)
    return bool(getattr(module.Provider, "remote", True))


def provider_ids() -> List[str]:
    """Registered provider names sorted by ``Provider.order``, then name.

    Not ``PROVIDER_MODULES`` insertion order. Callers (help, schema, completion,
    skills) use this list instead of hardcoding aws / virtualbox / ccm.
    Reads ``PROVIDER_ORDER`` so listing help does not import implementations.
    """
    rows = [(int(PROVIDER_ORDER.get(name, 100)), name) for name in PROVIDER_MODULES]
    rows.sort()
    return [name for _order, name in rows]


def format_provider_choice() -> str:
    """Human list in ``provider_ids()`` order: ``ccm, aws, external, or virtualbox``."""
    names = provider_ids()
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "%s or %s" % (names[0], names[1])
    return "%s, or %s" % (", ".join(names[:-1]), names[-1])


def get_provider(paths: SpaPaths):
    selection = detect_provider(paths)
    module = importlib.import_module(PROVIDER_MODULES[selection.name])
    return module.Provider(paths, selection.config)


def run_lifecycle_preflight(provider: Any, action: str) -> None:
    """Raise ProviderError if this action cannot start. Default: allow."""
    method = getattr(provider, "lifecycle_preflight", None)
    if callable(method):
        method(action)


def lifecycle_warnings(provider: Any, action: str) -> List[str]:
    """Human lines after a successful lifecycle action (and in the envelope)."""
    method = getattr(provider, "lifecycle_warnings", None)
    if not callable(method):
        return []
    return [str(row) for row in (method(action) or []) if str(row).strip()]


def wait_managed_ssh(
    paths: SpaPaths, hosts: Optional[Sequence[str]] = None, **kwargs: Any
) -> Dict[str, Any]:
    """Wait until managed hosts accept SSH. Architecture mismatch fails immediately.

    External hosts are never waited on: their inventory lines are merged back
    only after the provider returns.
    """
    from spa.hosts import HostsError, wait_for_ssh
    from spa.providers.classify import classify_hostnames

    if not hosts:
        managed, _external = classify_hostnames(load_deployment_config(paths))
        if not managed:
            return {"hosts": []}
        hosts = managed
    try:
        return wait_for_ssh(paths, hosts, **kwargs)
    except HostsError as exc:
        raise ProviderError(str(exc)) from exc
