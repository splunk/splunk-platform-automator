"""Inventory defaults loading."""

import importlib.util
from types import SimpleNamespace

import pytest

from spa_testutil import PROJECT_ROOT

pytestmark = pytest.mark.local

_PLUGIN = PROJECT_ROOT / "ansible" / "plugins" / "inventory" / "splunk-platform-automator.py"


def _inventory_module():
    spec = importlib.util.spec_from_file_location("spa_inventory_plugin", _PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.InventoryModule


def test_populate_defaults_skips_a_file_whose_stem_is_not_a_root_key(tmp_path):
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "aws.yml").write_text(
        "terraform:\n  aws:\n    region: eu-central-1\n",
        encoding="utf-8",
    )
    (defaults / "general.yml").write_text(
        "general:\n  linkpage_title: Lab\n",
        encoding="utf-8",
    )
    inventory = _inventory_module()
    plugin = inventory.__new__(inventory)
    plugin.spa_paths = SimpleNamespace(spa_home=tmp_path)
    plugin._populate_defaults()
    assert "aws" not in plugin.defaults
    assert plugin.defaults["general"]["linkpage_title"] == "Lab"
