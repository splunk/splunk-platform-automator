"""Unit tests for inventory app routing (DS / CM / deployer / direct)."""

import os
import sys

import pytest

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ansible", "plugins", "inventory"))

from app_routing import (  # noqa: E402
    METHOD_CLUSTER_MANAGER,
    METHOD_DEPLOYER,
    METHOD_DIRECT,
    METHOD_DS,
    resolve_app_routing,
    topology_from_hosts,
)


def _topo(hosts):
    return topology_from_hosts(hosts)


def _app(**overrides):
    app = {"name": "Foo", "source": "local", "target_roles": ["universal_forwarder"]}
    app.update(overrides)
    return app


def test_indexer_only_is_not_ds_even_with_deployment_server():
    topo = _topo(
        [
            {"name": "ds", "roles": ["deployment_server"]},
            {"name": "idx1", "roles": ["indexer"]},
            {"name": "uf1", "roles": ["universal_forwarder"]},
        ]
    )
    routing = resolve_app_routing(_app(target_roles=["indexer"]), topo)
    assert METHOD_DS not in routing.methods
    assert METHOD_DIRECT in routing.methods
    assert routing.effective_serverclass is None


def test_search_head_only_ds_requires_standalone_sh():
    clustered = _topo(
        [
            {"name": "ds", "roles": ["deployment_server"]},
            {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
            {"name": "sh1", "roles": ["search_head"], "shcluster": "shc1"},
            {"name": "sh2", "roles": ["search_head"], "shcluster": "shc1"},
            {"name": "sh3", "roles": ["search_head"], "shcluster": "shc1"},
        ]
    )
    routing = resolve_app_routing(_app(target_roles=["search_head"]), clustered)
    assert METHOD_DS not in routing.methods
    assert METHOD_DEPLOYER in routing.methods

    with_standalone = _topo(
        [
            {"name": "ds", "roles": ["deployment_server"]},
            {"name": "sh1", "roles": ["search_head"]},
        ]
    )
    routing = resolve_app_routing(_app(target_roles=["search_head"]), with_standalone)
    assert METHOD_DS in routing.methods
    assert routing.effective_serverclass == "app_Foo"


def test_no_ds_auto_is_direct_for_standalone_and_uf():
    topo = _topo(
        [
            {"name": "idx1", "roles": ["indexer"]},
            {"name": "sh1", "roles": ["search_head"]},
            {"name": "uf1", "roles": ["universal_forwarder"]},
        ]
    )
    for roles in (["indexer"], ["search_head"], ["universal_forwarder"]):
        routing = resolve_app_routing(_app(target_roles=roles), topo)
        assert routing.methods == frozenset({METHOD_DIRECT})
        assert routing.effective_serverclass is None


def test_deployment_target_direct_skips_ds_and_clusters():
    topo = _topo(
        [
            {"name": "ds", "roles": ["deployment_server"]},
            {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc1"},
            {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"},
            {"name": "uf1", "roles": ["universal_forwarder"]},
        ]
    )
    routing = resolve_app_routing(
        _app(target_roles=["indexer", "universal_forwarder"], deployment_target="direct"),
        topo,
    )
    assert routing.methods == frozenset({METHOD_DIRECT})
    assert routing.effective_serverclass is None


def test_clustered_indexer_search_head_plus_uf_methods():
    topo = _topo(
        [
            {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc1"},
            {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"},
            {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
            {"name": "sh1", "roles": ["search_head"], "shcluster": "shc1"},
            {"name": "ds", "roles": ["deployment_server"]},
            {"name": "uf1", "roles": ["universal_forwarder"]},
        ]
    )
    clustered = resolve_app_routing(
        _app(name="Splunk_TA_nix", target_roles=["indexer", "search_head"]),
        topo,
    )
    assert clustered.methods == frozenset({METHOD_CLUSTER_MANAGER, METHOD_DEPLOYER})
    assert clustered.effective_serverclass is None

    uf = resolve_app_routing(
        _app(name="Splunk_TA_nix", target_roles=["universal_forwarder"]),
        topo,
    )
    assert uf.methods == frozenset({METHOD_DS})
    assert uf.effective_serverclass == "app_Splunk_TA_nix"
