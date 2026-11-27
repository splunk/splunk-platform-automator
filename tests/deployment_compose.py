"""Compose provider-free live topologies with a suite provider hook."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import yaml

from deployment_provider import PROVIDERS, AmiResolver, OsResolver

TOPOLOGY_FORBIDDEN = ("terraform", "ccm", "virtualbox", "aws")
PROVIDER_FORBIDDEN = (
    "splunk_hosts",
    "splunk_idxclusters",
    "splunk_shclusters",
    "splunk_environments",
)


class ComposeError(Exception):
    """Invalid topology, provider, or suite YAML for live compose."""


def _load_mapping(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ComposeError("Missing %s" % path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ComposeError("%s must be a YAML mapping" % path)
    return data


def load_suite(deployment_root: Path, suite_id: str) -> Dict[str, Any]:
    data = _load_mapping(Path(deployment_root) / "suites" / ("%s.yml" % suite_id))
    if not data.get("provider"):
        raise ComposeError("Suite %s.yml must set provider" % suite_id)
    topologies = data.get("topologies")
    if not isinstance(topologies, list) or not topologies:
        raise ComposeError("Suite %s.yml must list topologies" % suite_id)
    return data


def suite_topology_ids(suite: Mapping[str, Any]) -> list[str]:
    return [str(row["id"]) for row in suite["topologies"]]


def _suite_row(suite: Mapping[str, Any], topology_id: str) -> Mapping[str, Any]:
    for row in suite["topologies"]:
        if row.get("id") == topology_id:
            return row
    raise ComposeError("Suite does not include topology %s" % topology_id)


def compose_deployment_config(
    tests_root: Path,
    *,
    suite_id: str,
    topology_id: str,
    ami_resolver: Optional[AmiResolver] = None,
    os_resolver: Optional[OsResolver] = None,
    identity_hook: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Provider keys first, topology keys win, then the suite provider hook."""
    deployment_root = Path(tests_root) / "deployment"
    suite = load_suite(deployment_root, suite_id)
    row = _suite_row(suite, topology_id)
    provider_id = str(suite["provider"])
    topo_path = deployment_root / "topologies" / ("%s.yml" % topology_id)
    prov_path = deployment_root / "providers" / ("%s.yml" % provider_id)
    topology = _load_mapping(topo_path)
    provider = _load_mapping(prov_path)

    bad_topo = [key for key in TOPOLOGY_FORBIDDEN if topology.get(key)]
    if bad_topo:
        raise ComposeError(
            "Topology %s must not contain %s" % (topo_path.name, ", ".join(bad_topo))
        )
    bad_prov = [key for key in PROVIDER_FORBIDDEN if provider.get(key)]
    if bad_prov:
        raise ComposeError(
            "Provider %s must not contain %s" % (prov_path.name, ", ".join(bad_prov))
        )

    plugin = topology.get("plugin") or provider.get("plugin") or "splunk-platform-automator"
    composed: Dict[str, Any] = {"plugin": plugin, "schema_version": 1}
    for key, value in provider.items():
        if key in ("plugin", "schema_version", "config_version"):
            continue
        composed[key] = copy.deepcopy(value)
    for key, value in topology.items():
        if key in ("plugin", "schema_version", "config_version"):
            continue
        composed[key] = copy.deepcopy(value)

    hook = identity_hook or PROVIDERS.get(provider_id)
    if hook is None:
        raise ComposeError("No provider hook registered for %s" % provider_id)
    region = ((composed.get("terraform") or {}).get("aws") or {}).get("region")
    if provider_id == "aws" and not region:
        raise ComposeError("Provider %s must set terraform.aws.region" % prov_path.name)
    hook.compose_identity(
        composed,
        os_key=str(row["os"]),
        extra_ufs=row.get("extra_ufs") or {},
        region=str(region or ""),
        ami_resolver=ami_resolver,
        os_resolver=os_resolver,
    )
    return composed
