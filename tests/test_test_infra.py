"""xdist isolation and runner pins (unit job)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_worker_local_dir_isolates_xdist_workers(tmp_path, monkeypatch):
    from spa_testutil import worker_local_dir

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    path_a = worker_local_dir(tmp_path)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    path_b = worker_local_dir(tmp_path)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    serial = worker_local_dir(tmp_path)

    assert path_a != path_b
    assert path_a.name == "gw0"
    assert path_b.name == "gw1"
    assert serial.name == "master"


def test_xdist_group_name_keeps_app_scope_scenario_together():
    from spa_testutil import xdist_group_name

    ds_only = xdist_group_name({"scenario_scope_result": "ds_only"})
    other = xdist_group_name({"scenario_scope_result": "minimal_direct"})
    assert ds_only == "app_scope_ds_only"
    assert other == "app_scope_minimal_direct"
    assert ds_only != other
    assert xdist_group_name({"config_file": "lab.yml"}) == "lab"
    assert xdist_group_name({"topology_id": "single_node"}) == "single_node"
    assert xdist_group_name({}) is None


def test_ansible_parallel_runs_use_loadgroup():
    """-n must use loadgroup so app-scope xdist_group markers keep a scenario on one worker."""
    for name in (
        "run_local_tests.sh",
        "run_ansible_tests.sh",
        "run_app_scope_scenarios_tests.sh",
    ):
        text = (PROJECT_ROOT / "tests" / name).read_text(encoding="utf-8")
        assert '"$arg" == "-n"' in text, name
        assert "--dist=loadgroup" in text, name
