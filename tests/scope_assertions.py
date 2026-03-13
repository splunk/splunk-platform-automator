"""
Assertion helpers for scope_debug.json produced by debug_app_scope.yml.
Used by test_app_scope_scenarios.py to validate direct, deployer, CM, and DS scope.
"""

from __future__ import annotations


def get_direct_results_for_host(scope: dict, host: str) -> list[dict]:
    """Return scope_debug_results for a host from direct_scope."""
    for item in scope.get("direct_scope") or []:
        if item.get("host") == host:
            return item.get("scope_debug_results") or []
    return []


def get_app_on_direct_for_host(scope: dict, host: str, app_name: str) -> dict | None:
    """Return the direct scope entry for (host, app) or None."""
    for r in get_direct_results_for_host(scope, host):
        if r.get("app") == app_name:
            return r
    return None


def assert_direct_on_scope(scope: dict, host: str, app_name: str, expected: bool) -> None:
    """Assert that for (host, app) on_scope equals expected."""
    entry = get_app_on_direct_for_host(scope, host, app_name)
    if entry is None:
        raise AssertionError(f"Expected direct entry for host={host!r} app={app_name!r} but none found")
    actual = entry.get("on_scope")
    assert actual == expected, (
        f"direct on_scope for host={host!r} app={app_name!r}: expected {expected}, got {actual}"
    )


def _first_deployer(scope: dict) -> dict:
    """Return first deployer entry from scope['deployer'] list, or empty dict."""
    deployer_list = scope.get("deployer") or []
    return deployer_list[0] if deployer_list else {}


def assert_deployer_apps(scope: dict, expected_app_names: list[str]) -> None:
    """Assert first deployer's apps (list of names) equals expected (order-independent)."""
    deployer = _first_deployer(scope)
    actual = sorted((deployer.get("apps") or []))
    expected_sorted = sorted(expected_app_names)
    assert actual == expected_sorted, (
        f"deployer.apps: expected {expected_sorted}, got {actual}"
    )


def assert_deployer_has_app_with_config(
    scope: dict,
    app_name: str,
    *,
    state: str | None = None,
    has_content_pack_apps: bool | None = None,
) -> None:
    """Assert first deployer's apps_with_config has an entry for app_name with optional state/content_pack_apps checks."""
    deployer = _first_deployer(scope)
    configs = deployer.get("apps_with_config") or []
    entry = next((c for c in configs if c.get("name") == app_name), None)
    assert entry is not None, (
        f"deployer.apps_with_config: expected entry for app={app_name!r}, got names {[c.get('name') for c in configs]}"
    )
    if state is not None:
        assert entry.get("state") == state, (
            f"deployer.apps_with_config[{app_name!r}].state: expected {state!r}, got {entry.get('state')!r}"
        )
    if has_content_pack_apps is not None:
        cp = entry.get("content_pack_apps")
        if has_content_pack_apps:
            assert cp is not None and isinstance(cp, list) and len(cp) > 0, (
                f"deployer.apps_with_config[{app_name!r}]: expected content_pack_apps non-empty list, got {cp!r}"
            )
        else:
            assert cp is None or (isinstance(cp, list) and len(cp) == 0), (
                f"deployer.apps_with_config[{app_name!r}]: expected content_pack_apps null/empty, got {cp!r}"
            )


def assert_deployer_target_hosts(scope: dict, expected_hosts: list[str]) -> None:
    """Assert first deployer's target_hosts equals expected (order-independent)."""
    deployer = _first_deployer(scope)
    actual = sorted((deployer.get("target_hosts") or []))
    expected_sorted = sorted(expected_hosts)
    assert actual == expected_sorted, (
        f"deployer.target_hosts: expected {expected_sorted}, got {actual}"
    )


def get_deployer_by_host(scope: dict, host: str) -> dict | None:
    """Return the deployer entry for host from scope['deployer'] list, or None."""
    deployer_list = scope.get("deployer") or []
    for d in deployer_list:
        if d.get("host") == host:
            return d
    return None


def assert_deployers_entry(
    scope: dict,
    host: str,
    expected_apps: list[str],
    expected_target_hosts: list[str],
) -> None:
    """Assert scope['deployer'] list has an entry for host with given apps and target_hosts."""
    entry = get_deployer_by_host(scope, host)
    deployer_list = scope.get("deployer") or []
    assert entry is not None, f"deployer: expected entry for host={host!r}, got {[d.get('host') for d in deployer_list]}"
    actual_apps = sorted(entry.get("apps") or [])
    expected_apps_sorted = sorted(expected_apps)
    assert actual_apps == expected_apps_sorted, (
        f"deployer[{host!r}].apps: expected {expected_apps_sorted}, got {actual_apps}"
    )
    actual_targets = sorted(entry.get("target_hosts") or [])
    expected_targets_sorted = sorted(expected_target_hosts)
    assert actual_targets == expected_targets_sorted, (
        f"deployer[{host!r}].target_hosts: expected {expected_targets_sorted}, got {actual_targets}"
    )


def _first_cluster_manager(scope: dict) -> dict:
    """Return first cluster_manager entry from scope['cluster_manager'] list, or empty dict."""
    cm_list = scope.get("cluster_manager") or []
    return cm_list[0] if cm_list else {}


def assert_cluster_manager_apps(scope: dict, expected_app_names: list[str]) -> None:
    """Assert first cluster_manager's apps (list of names) equals expected (order-independent)."""
    cm = _first_cluster_manager(scope)
    actual = sorted((cm.get("apps") or []))
    expected_sorted = sorted(expected_app_names)
    assert actual == expected_sorted, (
        f"cluster_manager.apps: expected {expected_sorted}, got {actual}"
    )


def assert_cluster_manager_target_hosts(scope: dict, expected_hosts: list[str]) -> None:
    """Assert first cluster_manager's target_hosts equals expected (order-independent)."""
    cm = _first_cluster_manager(scope)
    actual = sorted((cm.get("target_hosts") or []))
    expected_sorted = sorted(expected_hosts)
    assert actual == expected_sorted, (
        f"cluster_manager.target_hosts: expected {expected_sorted}, got {actual}"
    )


def _first_deployment_server(scope: dict) -> dict:
    """Return first deployment_server entry from scope['deployment_server'] list, or empty dict."""
    ds_list = scope.get("deployment_server") or []
    return ds_list[0] if ds_list else {}


def assert_ds_app_target_hosts(
    scope: dict,
    app_name: str,
    expected_hosts: list[str],
) -> None:
    """Assert first deployment_server's apps_with_targets has app with target_hosts equal to expected."""
    ds = _first_deployment_server(scope)
    targets = ds.get("apps_with_targets") or []
    entry = next((t for t in targets if t.get("app") == app_name), None)
    assert entry is not None, (
        f"deployment_server.apps_with_targets: expected app={app_name!r}, got {[t.get('app') for t in targets]}"
    )
    actual = sorted((entry.get("target_hosts") or []))
    expected_sorted = sorted(expected_hosts)
    assert actual == expected_sorted, (
        f"deployment_server.apps_with_targets[{app_name!r}].target_hosts: expected {expected_sorted}, got {actual}"
    )


def assert_ds_app_count(scope: dict, expected_count: int) -> None:
    """Assert first deployment_server's apps_with_targets has expected number of apps."""
    ds = _first_deployment_server(scope)
    targets = ds.get("apps_with_targets") or []
    assert len(targets) == expected_count, (
        f"deployment_server.apps_with_targets: expected {expected_count} app(s), got {len(targets)}"
    )


def get_ds_entries_for_app(scope: dict, app_name: str) -> list[dict]:
    """Return all apps_with_targets entries for the given app from the first deployment_server (same app, multiple serverclasses)."""
    ds = _first_deployment_server(scope)
    targets = ds.get("apps_with_targets") or []
    return [t for t in targets if t.get("app") == app_name]


def assert_ds_same_app_twice(
    scope: dict,
    app_name: str,
    expected_target_hosts_per_entry: list[list[str]],
) -> None:
    """Assert deployment_server has multiple entries for the same app with given target_hosts (order-independent)."""
    entries = get_ds_entries_for_app(scope, app_name)
    assert len(entries) == len(expected_target_hosts_per_entry), (
        f"deployment_server.apps_with_targets: expected {len(expected_target_hosts_per_entry)} entry/entries for app={app_name!r}, got {len(entries)}"
    )
    actual_sets = [sorted(e.get("target_hosts") or []) for e in entries]
    expected_sorted = [sorted(h) for h in expected_target_hosts_per_entry]
    # Match each expected set to an actual (order of entries may vary)
    for exp in expected_sorted:
        assert exp in actual_sets, (
            f"deployment_server.apps_with_targets[{app_name!r}]: expected an entry with target_hosts={exp}, got {actual_sets}"
        )
