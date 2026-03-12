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


def assert_deployer_apps(scope: dict, expected_app_names: list[str]) -> None:
    """Assert deployer.apps (list of names) equals expected (order-independent)."""
    deployer = scope.get("deployer") or {}
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
    """Assert deployer.apps_with_config has an entry for app_name with optional state/content_pack_apps checks."""
    deployer = scope.get("deployer") or {}
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
    """Assert deployer.target_hosts equals expected (order-independent)."""
    deployer = scope.get("deployer") or {}
    actual = sorted((deployer.get("target_hosts") or []))
    expected_sorted = sorted(expected_hosts)
    assert actual == expected_sorted, (
        f"deployer.target_hosts: expected {expected_sorted}, got {actual}"
    )


def assert_cluster_manager_apps(scope: dict, expected_app_names: list[str]) -> None:
    """Assert cluster_manager.apps (list of names) equals expected (order-independent)."""
    cm = scope.get("cluster_manager") or {}
    actual = sorted((cm.get("apps") or []))
    expected_sorted = sorted(expected_app_names)
    assert actual == expected_sorted, (
        f"cluster_manager.apps: expected {expected_sorted}, got {actual}"
    )


def assert_cluster_manager_target_hosts(scope: dict, expected_hosts: list[str]) -> None:
    """Assert cluster_manager.target_hosts equals expected (order-independent)."""
    cm = scope.get("cluster_manager") or {}
    actual = sorted((cm.get("target_hosts") or []))
    expected_sorted = sorted(expected_hosts)
    assert actual == expected_sorted, (
        f"cluster_manager.target_hosts: expected {expected_sorted}, got {actual}"
    )


def assert_ds_app_target_hosts(
    scope: dict,
    app_name: str,
    expected_hosts: list[str],
) -> None:
    """Assert deployment_server.apps_with_targets has app with target_hosts equal to expected."""
    ds = scope.get("deployment_server") or {}
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
    """Assert deployment_server.apps_with_targets has expected number of apps."""
    ds = scope.get("deployment_server") or {}
    targets = ds.get("apps_with_targets") or []
    assert len(targets) == expected_count, (
        f"deployment_server.apps_with_targets: expected {expected_count} app(s), got {len(targets)}"
    )
