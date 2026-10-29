"""Architecture input (SVA JSON) to a splunk_config.yml fragment. Read-only.

The plan never writes splunk_config.yml. It returns the host and cluster
entries as data. The agent applies them with ``spa config merge --file``
(upsert by name), then removes the base host with ``spa config unset``.
Secret values never enter the plan: secrets are ``lookup('env', ...)``
expressions built from env var names in the file.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Optional roles the file can request as separate hosts. Deployer and
# cluster-manager roles come from phase_5 cluster shapes, not from this list.
OPTIONAL_ROLE_MAP = {
    "license_manager": "license_manager",
    "deployment_server": "deployment_server",
    "monitoring_console": "monitoring_console",
    "universal_forwarder": "universal_forwarder",
    "heavy_forwarder": "heavy_forwarder",
}

# Keys of phase_5.env_lookups. Each value is an environment variable NAME, never a value.
ENV_LOOKUP_KEYS = ("admin", "idxc", "shc")

SVA_MIN_SHC_MEMBERS = 3
DEFAULT_REPLICATION_PORT = 9887
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
ORG_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
CREDENTIAL_KEY_RE = re.compile(r"password|secret|token|credential|key", re.IGNORECASE)
SITE_TOTAL_RE = re.compile(r"origin:\s*(\d+)\s*,\s*total:\s*(\d+)")
# Same value shapes spa config header refuses. Only the shape is checked; the value is never shown.
SECRET_VALUE_RE = re.compile(
    r"-----BEGIN|AKIA|ghp_|sk_live_|sk_test_|eyJ[^\s.]*\.[^\s.]+\.[^\s.]+"
)
# The 13 SVA codes the catalog and the SVA skill use. phase_1.sva must be one of these.
SVA_CODES = ("S1", "D1", "D11", "C1", "C11", "C3", "C13", "M2", "M12", "M3", "M13", "M4", "M14")
# Values of phase_4.provider, the same names spa init --provider accepts.
SPA_PROVIDERS = ("aws", "virtualbox", "external")
PHASE_ORDER = (
    "phase_0a",
    "phase_0b",
    "phase_1",
    "phase_2",
    "phase_3",
    "phase_4",
    "phase_5",
    "phase_5b",
    "phase_6",
    "phase_6b",
)


class ArchitectureError(ValueError):
    """The architecture file cannot be read or is not a JSON object."""


def load_architecture_file(path: Path) -> Dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ArchitectureError("cannot read architecture file: %s" % exc.strerror) from exc
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ArchitectureError("architecture file is not valid JSON: %s" % exc) from exc
    if not isinstance(doc, dict):
        raise ArchitectureError("architecture file must be a JSON object")
    return doc


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _lookup(env_var: str) -> str:
    return "{{ lookup('env', '%s') }}" % env_var


def _scan_credentials(node: Any, path: str, errors: List[str]) -> None:
    """Reject credential-shaped keys and secret-shaped values. Never echo values."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = "%s.%s" % (path, key) if path else str(key)
            if key == "_extensions":
                continue
            if CREDENTIAL_KEY_RE.search(str(key)) and not str(key).endswith("_env"):
                errors.append(
                    "%s looks like a credential. Remove it; the file names env vars only "
                    "(keys ending in _env)." % here
                )
                continue
            if str(key).endswith("_env"):
                if not (isinstance(value, str) and ENV_NAME_RE.match(value)):
                    errors.append(
                        "%s must be an environment variable name such as SPLUNK_ADMIN_PASSWORD; "
                        "the value is not shown." % here
                    )
                continue
            _scan_credentials(value, here, errors)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _scan_credentials(item, "%s[%d]" % (path, index), errors)
    elif isinstance(node, str) and SECRET_VALUE_RE.search(node):
        errors.append("%s looks like a secret value; it is not shown. Remove it." % path)


def _check_site_map(
    section: str,
    field: str,
    total: Optional[int],
    by_site: Mapping[str, Any],
    sites: List[str],
    errors: List[str],
) -> None:
    """Per-site counts: positive whole numbers, only listed sites, every listed site present."""
    if not by_site:
        return
    for site, count in by_site.items():
        if _as_int(count) is None or count < 1:
            errors.append(
                "phase_5.%s.%s.%s must be a whole number of at least 1." % (section, field, site)
            )
        elif sites and site not in sites:
            errors.append(
                "phase_5.%s.%s names %s, which is not in phase_5.indexer_cluster.sites." % (section, field, site)
            )
    if len(by_site) > 1 and not sites:
        errors.append(
            "phase_5.indexer_cluster.sites is required when phase_5.%s.%s lists more than one site." % (section, field)
        )
    for site in sites:
        if site not in by_site:
            errors.append(
                "phase_5.%s.%s has no count for %s. List every site in phase_5.indexer_cluster.sites."
                % (section, field, site)
            )
    counts = list(by_site.values())
    if total is not None and all(_as_int(count) is not None for count in counts):
        if sum(counts) != total:
            errors.append(
                "phase_5.%s.%s sums to %d but %s is %d."
                % (section, field, sum(counts), "peers" if section == "indexer_cluster" else "members", total)
            )


def _site_copies(idx: Dict[str, Any], key: str, errors: List[str]) -> Optional[Tuple[int, int]]:
    text = idx.get(key)
    match = SITE_TOTAL_RE.search(text) if isinstance(text, str) else None
    if not match:
        errors.append(
            "phase_5.indexer_cluster.%s is required for a multisite cluster, for example "
            "origin:2, total:3." % key
        )
        return None
    return int(match.group(1)), int(match.group(2))


def _check_indexer_cluster(idx: Dict[str, Any], errors: List[str]) -> Dict[str, Any]:
    name = idx.get("name", "idxc1")
    sites = idx.get("sites")
    if not isinstance(sites, list) or not sites or not all(isinstance(site, str) for site in sites):
        errors.append(
            'phase_5.indexer_cluster.sites must list the site names, for example ["site1", "site2"].'
        )
        return {}
    peers = _as_int(idx.get("peers"))
    if peers is None or peers < 1:
        errors.append("phase_5.indexer_cluster.peers must be a whole number of at least 1.")
        return {}
    by_site = idx.get("peers_by_site")
    if not isinstance(by_site, dict) or not by_site:
        errors.append(
            "phase_5.indexer_cluster.peers_by_site is required, for example "
            '{"site1": 2, "site2": 2}.'
        )
        return {}
    _check_site_map("indexer_cluster", "peers_by_site", peers, by_site, sites, errors)
    if isinstance(peers, int) and peers < 3:
        errors.append("phase_5.indexer_cluster.peers must be at least 3 (SVA minimum for an indexer cluster).")
    rf = _site_copies(idx, "site_rf", errors)
    sf = _site_copies(idx, "site_sf", errors)
    if rf is not None:
        if rf[1] > peers:
            errors.append(
                "phase_5.indexer_cluster.site_rf total (%d) is greater than peers (%d)." % (rf[1], peers)
            )
        for site, count in by_site.items():
            if _as_int(count) is not None and count < rf[0]:
                errors.append(
                    "%s has %d peer(s) but site_rf origin is %d. Each site needs at least %d peers."
                    % (site, count, rf[0], rf[0])
                )
    if rf is not None and sf is not None:
        if sf[1] > rf[1]:
            errors.append(
                "phase_5.indexer_cluster.site_sf total (%d) must not exceed site_rf total (%d)."
                % (sf[1], rf[1])
            )
        if sf[0] > rf[0]:
            errors.append(
                "phase_5.indexer_cluster.site_sf origin (%d) must not exceed site_rf origin (%d)."
                % (sf[0], rf[0])
            )
    shaped: Dict[str, Any] = {
        "name": name,
        "sites": [str(site) for site in sites],
        "peers": peers,
        "peers_by_site": by_site,
        "multisite": True,
        "replication_port": _as_int(idx.get("replication_port")) or DEFAULT_REPLICATION_PORT,
    }
    if rf is not None:
        shaped["site_rf"] = idx["site_rf"]
    if sf is not None:
        shaped["site_sf"] = idx["site_sf"]
    return shaped


def _check_shcluster_shape(
    shc: Dict[str, Any], multisite: bool, sites: List[str], errors: List[str]
) -> Dict[str, Any]:
    name = shc.get("name", "shc1")
    members = _as_int(shc.get("members"))
    if members is None or members < SVA_MIN_SHC_MEMBERS:
        errors.append(
            "phase_5.shcluster.members must be at least %d (SVA minimum for a search head cluster)."
            % SVA_MIN_SHC_MEMBERS
        )
    by_site = shc.get("members_by_site") or {}
    _check_site_map("shcluster", "members_by_site", members, by_site, sites, errors)
    if multisite and not by_site:
        errors.append(
            "phase_5.shcluster.members_by_site is required when the indexer cluster is multisite, "
            'for example {"site1": 2, "site2": 1}.'
        )
    return {
        "name": name,
        "members": members,
        "members_by_site": by_site,
        "multisite": multisite,
        "port": _as_int(shc.get("replication_port")) or DEFAULT_REPLICATION_PORT,
    }


def _expand_site_groups(
    by_site: Mapping[str, int], sites: List[str], prefix: str, total: int
) -> List[Tuple[Optional[str], int, int]]:
    """Return (site, first, last) numbering blocks in site order. Numbers run across sites."""
    if not by_site:
        return [(None, 1, total)]
    ordered = [site for site in sites if site in by_site] or list(by_site)
    groups = []
    number = 1
    for site in ordered:
        count = by_site[site]
        if count < 1:
            continue
        groups.append((site, number, number + count - 1))
        number += count
    return groups


def _host_entries(
    prefix: str, first: int, last: int, roles: List[str], **fields: Any
) -> List[Dict[str, Any]]:
    """One explicit host per number. The external provider rejects iter ranges, so none are emitted."""
    entries = []
    for number in range(first, last + 1):
        entry: Dict[str, Any] = {"name": "%s%d" % (prefix, number), "roles": list(roles)}
        for key, value in fields.items():
            if value is not None:
                entry[key] = value
        entries.append(entry)
    return entries


def _build_hosts(
    idx: Dict[str, Any],
    shc: Optional[Dict[str, Any]],
    sites: List[str],
    errors: List[str],
) -> List[Dict[str, Any]]:
    multisite = idx["multisite"]
    hosts: List[Dict[str, Any]] = [
        {
            "name": "cm",
            "roles": ["cluster_manager"],
            "idxcluster": idx["name"],
            "site": "site0" if multisite else None,
        }
    ]
    hosts[0] = {key: value for key, value in hosts[0].items() if value is not None}
    for site, first, last in _expand_site_groups(
        idx.get("peers_by_site") or {}, sites, "idx", idx["peers"]
    ):
        hosts.extend(
            _host_entries(
                "idx",
                first,
                last,
                ["indexer"],
                idxcluster=idx["name"],
                site=site if multisite else None,
            )
        )
    if shc is not None:
        hosts.append({"name": "ds", "roles": ["deployer"], "shcluster": shc["name"]})
        for site, first, last in _expand_site_groups(
            shc["members_by_site"], sites, "sh", shc["members"] or 0
        ):
            hosts.extend(
                _host_entries(
                    "sh",
                    first,
                    last,
                    ["search_head"],
                    shcluster=shc["name"],
                    site=site if shc["multisite"] else None,
                )
            )
    return hosts


def _add_optional_roles(
    hosts: List[Dict[str, Any]], optional: List[Any], errors: List[str]
) -> None:
    seen = {entry["name"]: entry for entry in hosts}
    for item in optional:
        if not isinstance(item, dict):
            errors.append("phase_5.optional_roles entries must be objects with name and role.")
            continue
        role = item.get("role")
        name = item.get("name")
        spa_role = OPTIONAL_ROLE_MAP.get(role)
        if spa_role is None:
            errors.append(
                "phase_5.optional_roles has a role that is not a supported SPA role; "
                "the value is not shown. Use one of: %s." % ", ".join(sorted(OPTIONAL_ROLE_MAP))
            )
            continue
        if not isinstance(name, str) or not name:
            errors.append("phase_5.optional_roles entry for %s needs a name." % role)
            continue
        if name in seen:
            existing = seen[name]
            if "deployer" in existing.get("roles", []) and spa_role not in existing["roles"]:
                existing["roles"].append(spa_role)
                continue
            errors.append("host name %s is used more than once." % name)
            continue
        entry = {"name": name, "roles": [spa_role]}
        hosts.append(entry)
        seen[name] = entry


def _extension_rows(raw: Any, errors: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if raw is None:
        return rows
    if not isinstance(raw, list):
        errors.append("phase_5._extensions must be a list.")
        return rows
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("field_name"), str):
            errors.append("phase_5._extensions entries need a text field_name.")
            continue
        if CREDENTIAL_KEY_RE.search(item["field_name"]):
            errors.append(
                "phase_5._extensions field_name %s looks like a credential. Remove it; "
                "the value is not shown." % item["field_name"]
            )
            continue
        if isinstance(item.get("value"), str) and SECRET_VALUE_RE.search(item["value"]):
            errors.append(
                "phase_5._extensions entry %s has a value that looks like a secret; "
                "it is not shown. Remove it." % item["field_name"]
            )
            continue
        rows.append(
            {
                "field_name": item["field_name"],
                "reason": item.get("reason"),
                "suggested_placement": item.get("suggested_placement"),
                "severity": item.get("severity", "info"),
                "status": "unmapped",
            }
        )
    return rows


def _catalog_sva(spa_home: Optional[Path], topology: str) -> Optional[str]:
    """The SVA code the catalog lists for a topology id, or None when the catalog does not say."""
    if spa_home is None:
        return None
    from spa.catalog import load_features

    try:
        features = load_features(Path(spa_home))
    except (FileNotFoundError, ValueError, OSError, ImportError):
        return None
    for item in features:
        if item.get("kind") == "topology" and item.get("id") == topology:
            return str(item["sva"]) if item.get("sva") else None
    return None


def _topology_known(spa_home: Optional[Path], topology: str, errors: List[str]) -> None:
    if spa_home is None:
        return
    from spa.init import list_catalog_topologies

    rows = list_catalog_topologies(Path(spa_home))
    known = {row["id"] for row in rows} | {row["template"] for row in rows}
    if topology not in known:
        errors.append(
            "phase_1.topology is not in the catalog; the value is not shown. "
            "List the ids: spa --agent init list."
        )


def _check_roles_and_license(
    doc: Mapping[str, Any],
    phase_5: Mapping[str, Any],
    hosts: List[Dict[str, Any]],
    errors: List[str],
    warnings: List[str],
) -> None:
    """Phase 8b checks, done here because the plan already has the host list.

    Every role in phase_5b.roles must be on a host. A license_manager needs
    phase_6b.license_file. The SVA file never holds phase_6b, so a missing
    license file is a warning here; the spa skill collects it before the write.
    Values are not echoed.
    """
    host_roles = {role for entry in hosts for role in entry.get("roles", [])}
    phase_5b = doc.get("phase_5b") if isinstance(doc.get("phase_5b"), dict) else {}
    roles = phase_5b.get("roles")
    if isinstance(roles, list):
        for index, role in enumerate(roles):
            if role not in host_roles:
                errors.append(
                    "phase_5b.roles[%d] has no host with that role; the value is not shown. "
                    "Add the host or remove the role." % index
                )
    if "license_manager" in host_roles:
        phase_6b = doc.get("phase_6b") if isinstance(doc.get("phase_6b"), dict) else {}
        if not (isinstance(phase_6b.get("license_file"), str) and phase_6b.get("license_file")):
            warnings.append(
                "phase_6b.license_file is not in the file. optional_roles has a license_manager, "
                "so the spa skill must collect it in phase 6b before the write."
            )


def plan_architecture(
    doc: Mapping[str, Any],
    env: Optional[Mapping[str, str]] = None,
    spa_home: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate an architecture file and return the config fragment and apply steps."""
    env = dict(env or {})
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(doc, Mapping):
        return {"ok": False, "errors": ["architecture file must be a JSON object"], "warnings": []}

    _scan_credentials(dict(doc), "", errors)

    for key, value in doc.items():
        if str(key).startswith("phase_") and not isinstance(value, dict):
            errors.append("%s must be a JSON object." % key)

    metadata = doc.get("metadata")
    if isinstance(metadata, dict) and metadata.get("version", "0.3.0") != "0.3.0":
        errors.append("metadata.version must be 0.3.0, the schema this planner reads.")

    phases = []
    for name in PHASE_ORDER:
        block = doc.get(name)
        if isinstance(block, dict):
            phases.append(
                {
                    "phase": name,
                    "confirmed": block.get("confirmed"),
                    "source": "Architecture file",
                }
            )
    for row in phases:
        if row["confirmed"] is not True:
            warnings.append(
                "%s is not confirmed (confirmed is not true). Confirm it in chat before any write."
                % row["phase"]
            )

    phase_1 = doc.get("phase_1") if isinstance(doc.get("phase_1"), dict) else {}
    topology = phase_1.get("topology")
    if not isinstance(topology, str) or not topology:
        errors.append("phase_1.topology is missing. Set it to a topology id from spa init list.")
    else:
        _topology_known(spa_home, topology, errors)

    sva = phase_1.get("sva")
    if sva is not None and sva not in SVA_CODES:
        errors.append(
            "phase_1.sva is not an SVA code; the value is not shown. Use one of: %s."
            % ", ".join(SVA_CODES)
        )
    elif sva is not None and isinstance(topology, str) and topology:
        catalog_sva = _catalog_sva(spa_home, topology)
        if catalog_sva and catalog_sva != sva:
            errors.append(
                "phase_1.sva does not match phase_1.topology; the catalog lists SVA %s for it."
                % catalog_sva
            )

    phase_4 = doc.get("phase_4") if isinstance(doc.get("phase_4"), dict) else {}
    provider = phase_4.get("provider")
    if provider is not None and provider not in SPA_PROVIDERS:
        errors.append(
            "phase_4.provider is not a provider; the value is not shown. Use one of: %s."
            % ", ".join(SPA_PROVIDERS)
        )

    phase_5 = doc.get("phase_5")
    if not isinstance(phase_5, dict):
        errors.append("phase_5 is missing. It holds indexer_cluster, shcluster, optional_roles, and env_lookups.")
        return _result(False, errors, warnings, phases, doc)

    org_prefix = phase_5.get("org_prefix")
    if org_prefix is not None and (
        not isinstance(org_prefix, str) or not ORG_PREFIX_RE.match(org_prefix)
    ):
        errors.append(
            "phase_5.org_prefix must be lowercase letters, digits, or underscores, starting with a letter."
        )
        org_prefix = None

    idx_raw = phase_5.get("indexer_cluster")
    if not isinstance(idx_raw, dict):
        errors.append(
            "phase_5.indexer_cluster is missing. It holds sites, peers, peers_by_site, site_rf, and site_sf."
        )
        return _result(False, errors, warnings, phases, doc)
    idx = _check_indexer_cluster(idx_raw, errors)
    sites = idx.get("sites") or []

    shc = None
    shc_raw = phase_5.get("shcluster")
    if isinstance(shc_raw, dict):
        shc = _check_shcluster_shape(shc_raw, True, sites, errors)

    extensions = _extension_rows(phase_5.get("_extensions"), errors)

    if phase_5.get("apps_by_role") is not None:
        warnings.append("phase_5.apps_by_role is ignored. SPA decides which apps each role gets.")

    if errors or not idx:
        return _result(False, errors, warnings, phases, doc, extensions=extensions)

    hosts = _build_hosts(idx, shc, sites, errors)
    optional = phase_5.get("optional_roles") or []
    if not isinstance(optional, list):
        errors.append("phase_5.optional_roles must be a list of objects with name and role.")
        optional = []
    _add_optional_roles(hosts, optional, errors)
    _check_roles_and_license(doc, phase_5, hosts, errors, warnings)

    lookups = phase_5.get("env_lookups")
    if not isinstance(lookups, dict):
        errors.append("phase_5.env_lookups is missing. It maps admin, idxc, and shc to env var names.")
        lookups = {}
    secret_rows: List[Dict[str, Any]] = []
    for key in ENV_LOOKUP_KEYS:
        if key not in lookups:
            errors.append("phase_5.env_lookups has no %s entry. Add the env var name for it." % key)
            continue
        value = lookups[key]
        if not (isinstance(value, str) and ENV_NAME_RE.match(value)):
            errors.append(
                "phase_5.env_lookups.%s must be an environment variable name such as "
                "SPLUNK_ADMIN_PASSWORD; the value is not shown." % key
            )
            continue
        secret_rows.append({"key": key, "env_var": value, "set": bool(env.get(value))})
    secret_by_kind = {row["key"]: row["env_var"] for row in secret_rows}

    defaults: Dict[str, Any] = {}
    if org_prefix:
        defaults["splunk_env_name"] = org_prefix
    if "admin" in secret_by_kind:
        defaults["splunk_admin_password"] = _lookup(secret_by_kind["admin"])

    idx_entry: Dict[str, Any] = {
        "idxc_name": idx["name"],
        "idxc_replication_port": idx["replication_port"],
        "idxc_site_rf": idx["site_rf"],
        "idxc_site_sf": idx["site_sf"],
    }
    if "idxc" in secret_by_kind:
        idx_entry["idxc_password"] = _lookup(secret_by_kind["idxc"])
    fragment: Dict[str, Any] = {}
    if defaults:
        fragment["splunk_defaults"] = defaults
    fragment["splunk_idxclusters"] = [idx_entry]

    shc_entries = []
    if shc is not None:
        shc_entry: Dict[str, Any] = {
            "shc_name": shc["name"],
            "shc_replication_port": shc["port"],
        }
        if shc["multisite"]:
            shc_entry["shc_site"] = "site0"
        if "shc" in secret_by_kind:
            shc_entry["shc_password"] = _lookup(secret_by_kind["shc"])
        shc_entries.append(shc_entry)
        fragment["splunk_shclusters"] = shc_entries

    fragment["splunk_hosts"] = hosts

    phase_6b = doc.get("phase_6b") if isinstance(doc.get("phase_6b"), dict) else {}
    license_file = phase_6b.get("license_file")
    resolve = []
    if isinstance(license_file, str) and license_file:
        resolve.append({"path": "splunk_defaults.splunk_license_file", "value": license_file})

    result = _result(
        True,
        errors,
        warnings,
        phases,
        doc,
        fragment=fragment,
        hosts=hosts,
        secrets=secret_rows,
        extensions=extensions,
    )
    result["apply"] = {
        "resolve": resolve,
        "steps": [
            "spa --agent init --example topology.s1 --provider PROVIDER ENV  (base env; its one host is removed in step 3)",
            "spa --agent --env ENV config merge --file FRAGMENT --yes"
            + "".join(
                " --resolve %s %s" % (item["path"], item["value"]) for item in resolve
            ),
            "spa --agent --env ENV config unset 'splunk_hosts[name=shidx]' --yes",
            "spa --agent --env ENV validate",
        ],
    }
    return result


def _result(
    ok: bool,
    errors: List[str],
    warnings: List[str],
    phases: List[Dict[str, Any]],
    doc: Mapping[str, Any],
    fragment: Optional[Dict[str, Any]] = None,
    hosts: Optional[List[Dict[str, Any]]] = None,
    secrets: Optional[List[Dict[str, Any]]] = None,
    extensions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": ok and not errors,
        "errors": errors,
        "warnings": warnings,
        "phases": phases,
        "environment": (doc.get("environment") or {}).get("name") if isinstance(doc.get("environment"), dict) else None,
        "hosts": hosts or [],
        "secrets": secrets or [],
        "extensions": extensions or [],
        "fragment": fragment if (ok and not errors and fragment) else {},
        "apply": {"resolve": [], "steps": []},
    }
    return result


def write_fragment(path: Path, fragment: Mapping[str, Any]) -> None:
    """Write the merge input for ``spa config merge --file``. Never writes splunk_config.yml."""
    target = Path(path)
    if target.name == "splunk_config.yml":
        raise ArchitectureError(
            "refusing to write splunk_config.yml here. Write a fragment file, then run spa config merge."
        )
    target.write_text(json.dumps(fragment, indent=2) + "\n", encoding="utf-8")


def format_plan_text(plan: Mapping[str, Any]) -> str:
    """Human view of a plan. Agents read the JSON envelope instead."""
    lines: List[str] = []
    if plan.get("errors"):
        lines.append("Architecture file has errors:")
        lines.extend("  - %s" % error for error in plan["errors"])
    for warning in plan.get("warnings") or []:
        lines.append("warning: %s" % warning)
    if plan.get("ok"):
        lines.append("Architecture plan (read-only; nothing written):")
        lines.append("Hosts:")
        for row in sorted(plan.get("hosts", []), key=lambda entry: _host_sort_key(entry["name"])):
            lines.append("  %-8s %s" % (row["name"], ", ".join(row["roles"])))
        for row in plan.get("secrets") or []:
            state = "set" if row["set"] else "not set"
            lines.append("Env %s (%s): %s" % (row["env_var"], row["key"], state))
        for row in plan.get("extensions") or []:
            lines.append(
                "Extension %s: not written; suggested placement %s"
                % (row["field_name"], row.get("suggested_placement") or "unknown")
            )
    return "\n".join(lines) + "\n"


def _host_sort_key(name: str) -> Tuple[int, str]:
    order = {"cm": 0, "ds": 1}
    return (order.get(name, 2), name)
