"""Framework group_vars load without an env-dir symlink."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from ansible.inventory.group import Group
from ansible.parsing.dataloader import DataLoader

pytestmark = [pytest.mark.local]

PROJECT = Path(__file__).resolve().parents[1]
PLUGIN = PROJECT / "ansible" / "plugins" / "vars" / "spa_group_vars.py"


def _load_plugin():
    spec = importlib.util.spec_from_file_location("spa_group_vars", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.VarsModule()


def test_spa_group_vars_loads_framework_all_group():
    plugin = _load_plugin()
    data = plugin.get_vars(DataLoader(), str(PROJECT / "inventory"), [Group("all")])
    assert data.get("spa_preflight_deploy") is True
    assert "splunk_software" in data
    assert "spa_home" not in data
