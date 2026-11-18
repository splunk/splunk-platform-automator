"""Inventory-only app deployment routing.

Mirrors the Ansible DS / cluster-manager / deployer / direct heuristic
(``deploymentclient_check: false`` path). Schema uniqueness checks use this
instead of inferring DS use from the app dict alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, Iterable, Mapping, Optional, Sequence, Tuple


METHOD_DS = "ds"
METHOD_CLUSTER_MANAGER = "cluster_manager"
METHOD_DEPLOYER = "deployer"
METHOD_DIRECT = "direct"

UF_HF_ROLES = frozenset(
    {
        "universal_forwarder",
        "heavy_forwarder",
        "universal_forwarder_windows",
    }
)
INDEXER_CM_ROLES = frozenset({"indexer", "cluster_manager"})


@dataclass(frozen=True)
class TopologyHost:
    name: str
    roles: FrozenSet[str]
    idxcluster: Optional[str]
    shcluster: Optional[str]


@dataclass(frozen=True)
class TopologySnapshot:
    hosts: Tuple[TopologyHost, ...]

    def names_with_role(self, role: str) -> FrozenSet[str]:
        return frozenset(h.name for h in self.hosts if role in h.roles)

    def names_with_any_role(self, roles: Iterable[str]) -> FrozenSet[str]:
        want = frozenset(roles)
        return frozenset(h.name for h in self.hosts if h.roles & want)

    @property
    def has_deployment_server(self) -> bool:
        return any("deployment_server" in h.roles for h in self.hosts)

    @property
    def ds_host_names(self) -> FrozenSet[str]:
        return self.names_with_role("deployment_server")

    @property
    def idxc_member_names(self) -> FrozenSet[str]:
        return frozenset(h.name for h in self.hosts if h.idxcluster)

    @property
    def shc_member_names(self) -> FrozenSet[str]:
        return frozenset(h.name for h in self.hosts if h.shcluster)

    @property
    def standalone_search_heads(self) -> FrozenSet[str]:
        return frozenset(
            h.name for h in self.hosts if "search_head" in h.roles and not h.shcluster
        )

    @property
    def idxc_names_with_indexers(self) -> FrozenSet[str]:
        return frozenset(
            h.idxcluster
            for h in self.hosts
            if h.idxcluster and "indexer" in h.roles
        )

    @property
    def shc_names_with_search_heads(self) -> FrozenSet[str]:
        return frozenset(
            h.shcluster
            for h in self.hosts
            if h.shcluster and "search_head" in h.roles
        )

    def names_in_idxc(self, cluster: str) -> FrozenSet[str]:
        return frozenset(h.name for h in self.hosts if h.idxcluster == cluster)

    def names_in_shc(self, cluster: str) -> FrozenSet[str]:
        return frozenset(h.name for h in self.hosts if h.shcluster == cluster)


@dataclass(frozen=True)
class AppRouting:
    methods: FrozenSet[str]
    effective_serverclass: Optional[str]


def _attr(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _opt_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _role_name(role: Any) -> str:
    if hasattr(role, "value"):
        return str(role.value).strip().lower()
    return str(role).strip().lower()


def expand_host_names(host: Any) -> Tuple[str, ...]:
    """Expand name / list / iter the same way inventory host filters do (iter zfill)."""
    name = _attr(host, "name")
    if name:
        return (str(name),)
    host_list = _attr(host, "list")
    if host_list:
        return tuple(str(item) for item in host_list)
    iteration = _attr(host, "iter")
    if iteration is None:
        return ()
    numbers = _attr(iteration, "numbers") or ""
    prefix = _attr(iteration, "prefix") or ""
    postfix = _attr(iteration, "postfix") or ""
    start_s, end_s = str(numbers).split("..")
    start, end = int(start_s), int(end_s)
    width = len(end_s)
    return tuple(
        "%s%s%s" % (prefix, str(n).zfill(width), postfix)
        for n in range(start, end + 1)
    )


def topology_from_hosts(hosts: Sequence[Any]) -> TopologySnapshot:
    expanded = []
    for host in hosts:
        roles = frozenset(_role_name(r) for r in (_attr(host, "roles") or ()) if r)
        idxcluster = _opt_str(_attr(host, "idxcluster"))
        shcluster = _opt_str(_attr(host, "shcluster"))
        for name in expand_host_names(host):
            expanded.append(
                TopologyHost(
                    name=name,
                    roles=roles,
                    idxcluster=idxcluster,
                    shcluster=shcluster,
                )
            )
    return TopologySnapshot(tuple(expanded))


def _norm_deployment_target(app: Mapping[str, Any]) -> str:
    value = app.get("deployment_target", "auto")
    if isinstance(value, str):
        return value.strip().lower() or "auto"
    return "auto"


def _target_roles(app: Mapping[str, Any]) -> Tuple[str, ...]:
    raw = app.get("target_roles") or []
    if not isinstance(raw, list):
        return ()
    return tuple(str(role).strip().lower() for role in raw if role)


def _is_premium(app: Mapping[str, Any]) -> bool:
    premium = app.get("premium_app")
    return bool(isinstance(premium, str) and premium.strip())


def _is_itsi(app: Mapping[str, Any]) -> bool:
    premium = app.get("premium_app")
    return isinstance(premium, str) and premium.strip().lower() == "itsi"


def _is_content_pack(app: Mapping[str, Any]) -> bool:
    return bool(app.get("itsi_content_pack"))


def _str_list(app: Mapping[str, Any], key: str) -> Tuple[str, ...]:
    value = app.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def effective_serverclass(app: Mapping[str, Any]) -> Optional[str]:
    name = app.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    serverclass = app.get("serverclass")
    if isinstance(serverclass, str) and serverclass.strip():
        return serverclass.strip()
    return "app_" + name.strip()


def _ds_eligible(app: Mapping[str, Any], topo: TopologySnapshot) -> bool:
    """Match apps_deployment_server Filter apps for deployment server distribution."""
    if _norm_deployment_target(app) == "direct":
        return False
    if _is_premium(app) or _is_content_pack(app):
        return False
    if not topo.has_deployment_server:
        return False
    roles = _target_roles(app)
    if not roles:
        return False
    if not any(role not in INDEXER_CM_ROLES for role in roles):
        return False
    if not any(role != "search_head" for role in roles):
        if not topo.standalone_search_heads:
            return False
    if "search_head" in roles:
        if _str_list(app, "shc_whitelist") or _str_list(app, "shc_blacklist"):
            return False
    return True


def _computed_ds_clients(app: Mapping[str, Any], topo: TopologySnapshot) -> FrozenSet[str]:
    """Match process_ds_app.yml whitelist (inventory heuristic, no btool)."""
    sc_whitelist = app.get("sc_whitelist")
    if sc_whitelist is not None:
        if not isinstance(sc_whitelist, list) or len(sc_whitelist) == 0:
            return frozenset()
        clients = {str(item) for item in sc_whitelist if item}
        clients -= set(topo.ds_host_names)
        return frozenset(clients)

    filtered = set(topo.names_with_any_role(_target_roles(app)))
    filtered -= set(topo.idxc_member_names)
    filtered -= set(topo.shc_member_names)

    idxc_whitelist = _str_list(app, "idxc_whitelist")
    if idxc_whitelist:
        union: set = set()
        for cluster in idxc_whitelist:
            union |= set(topo.names_in_idxc(cluster))
        filtered &= union

    idxc_blacklist = _str_list(app, "idxc_blacklist")
    if idxc_blacklist:
        union = set()
        for cluster in idxc_blacklist:
            union |= set(topo.names_in_idxc(cluster))
        filtered -= union

    if _str_list(app, "shc_whitelist"):
        filtered -= set(topo.names_with_role("search_head"))

    hosts_whitelist = _str_list(app, "hosts_whitelist")
    hosts_blacklist = _str_list(app, "hosts_blacklist")
    if hosts_whitelist or hosts_blacklist:
        standalone_sh = set(topo.standalone_search_heads)
        search_heads = filtered & standalone_sh
        others = filtered - search_heads
        if hosts_whitelist:
            search_heads &= set(hosts_whitelist)
        if hosts_blacklist:
            search_heads -= set(hosts_blacklist)
        filtered = others | search_heads

    filtered -= set(topo.ds_host_names)
    return frozenset(filtered)


def _uses_ds(app: Mapping[str, Any], topo: TopologySnapshot) -> bool:
    if not _ds_eligible(app, topo):
        return False
    return bool(_computed_ds_clients(app, topo))


def _effective_target_roles(app: Mapping[str, Any]) -> Tuple[str, ...]:
    if _is_content_pack(app):
        return ("search_head",)
    if _is_itsi(app):
        return ("search_head", "indexer", "license_manager")
    return _target_roles(app)


def _uses_cluster_manager(app: Mapping[str, Any], topo: TopologySnapshot) -> bool:
    if _norm_deployment_target(app) == "direct":
        return False
    if not topo.idxc_names_with_indexers:
        return False
    if _is_content_pack(app):
        return False
    roles = _effective_target_roles(app)
    if not _is_itsi(app) and "indexer" not in roles and "cluster_manager" not in roles:
        return False
    idxc_whitelist = _str_list(app, "idxc_whitelist")
    idxc_blacklist = _str_list(app, "idxc_blacklist")
    all_idxc = set(topo.idxc_names_with_indexers)
    targeted = set(idxc_whitelist) if idxc_whitelist else (all_idxc - set(idxc_blacklist))
    if (idxc_whitelist or idxc_blacklist) and not targeted:
        return False
    if not (targeted & all_idxc):
        return False
    hosts_whitelist = _str_list(app, "hosts_whitelist")
    if hosts_whitelist and not _is_itsi(app):
        members: set = set()
        for cluster in targeted & all_idxc:
            members |= set(topo.names_in_idxc(cluster))
        if not (set(hosts_whitelist) & members):
            return False
    return True


def _uses_deployer(app: Mapping[str, Any], topo: TopologySnapshot) -> bool:
    if _norm_deployment_target(app) == "direct":
        return False
    if not topo.shc_names_with_search_heads:
        return False
    roles = _effective_target_roles(app)
    if "search_head" not in roles:
        return False
    shc_whitelist = _str_list(app, "shc_whitelist")
    shc_blacklist = _str_list(app, "shc_blacklist")
    all_shc = set(topo.shc_names_with_search_heads)
    targeted = set(shc_whitelist) if shc_whitelist else (all_shc - set(shc_blacklist))
    if (shc_whitelist or shc_blacklist) and not targeted:
        return False
    if not (targeted & all_shc):
        return False
    hosts_whitelist = _str_list(app, "hosts_whitelist")
    if hosts_whitelist:
        members: set = set()
        for cluster in targeted & all_shc:
            members |= {
                host.name
                for host in topo.hosts
                if host.shcluster == cluster and "search_head" in host.roles
            }
        if not (set(hosts_whitelist) & members):
            return False
    return True


def _uses_direct(
    app: Mapping[str, Any],
    topo: TopologySnapshot,
    ds_clients: FrozenSet[str],
) -> bool:
    if _norm_deployment_target(app) == "direct":
        return True
    roles = set(_effective_target_roles(app))
    if not roles:
        return False
    for host in topo.hosts:
        if not (host.roles & roles):
            continue
        if host.idxcluster and "indexer" in host.roles and "indexer" in roles:
            continue
        if host.shcluster and "search_head" in host.roles and "search_head" in roles:
            continue
        if host.name in ds_clients:
            continue
        return True
    return False


def resolve_app_routing(app: Mapping[str, Any], topo: TopologySnapshot) -> AppRouting:
    methods = set()
    uses_ds = _uses_ds(app, topo)
    if uses_ds:
        methods.add(METHOD_DS)
    if _uses_cluster_manager(app, topo):
        methods.add(METHOD_CLUSTER_MANAGER)
    if _uses_deployer(app, topo):
        methods.add(METHOD_DEPLOYER)
    ds_clients = _computed_ds_clients(app, topo) if uses_ds else frozenset()
    if _uses_direct(app, topo, ds_clients):
        methods.add(METHOD_DIRECT)
    serverclass = effective_serverclass(app) if uses_ds else None
    return AppRouting(methods=frozenset(methods), effective_serverclass=serverclass)
