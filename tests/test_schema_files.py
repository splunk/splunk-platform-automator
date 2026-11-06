"""File-based schema tests: validate_config_file and shipped config sweep."""

import glob
import os
import sys

import pytest
import yaml

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ansible", "plugins", "inventory"))

from schema import ConfigValidationError, validate_config_file  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVENTORY_PLUGIN = "plugin: splunk-platform-automator\n"


def _with_inventory_plugin(text):
    data = yaml.safe_load(text) or {}
    if isinstance(data, dict) and "plugin" in data:
        return text
    lines = text.splitlines(True)
    if lines and lines[0].strip() == "---":
        return lines[0] + INVENTORY_PLUGIN + "".join(lines[1:])
    return INVENTORY_PLUGIN + text


def _example_paths():
    paths = sorted(glob.glob(os.path.join(PROJECT_ROOT, "examples", "topologies", "*.yml")))
    paths += sorted(glob.glob(os.path.join(PROJECT_ROOT, "examples", "*.yml")))
    return paths


def _app_scope_paths():
    return sorted(glob.glob(os.path.join(PROJECT_ROOT, "tests", "configs", "app_scope", "*", "splunk_config.yml")))


class TestValidateConfigFile:
    def test_valid_temp_file(self, tmp_path):
        cfg = tmp_path / "splunk_config.yml"
        cfg.write_text(
            "plugin: splunk-platform-automator\n"
            "splunk_defaults:\n"
            "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
            "splunk_hosts:\n"
            "  - name: idx1\n"
            "    roles: [indexer]\n"
        )
        result = validate_config_file(str(cfg))
        assert result.plugin == "splunk-platform-automator"
        assert result.splunk_hosts[0].name == "idx1"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_config_file(str(tmp_path / "missing.yml"))

    def test_invalid_yaml_raises(self, tmp_path):
        cfg = tmp_path / "bad.yml"
        cfg.write_text("plugin: [unterminated\n")
        with pytest.raises(yaml.YAMLError):
            validate_config_file(str(cfg))

    def test_invalid_schema_raises(self, tmp_path):
        cfg = tmp_path / "invalid.yml"
        cfg.write_text("plugin: splunk-platform-automator\nsplunk_hosts: []\n")
        with pytest.raises(ConfigValidationError):
            validate_config_file(str(cfg))


@pytest.mark.parametrize("config_path", _example_paths(), ids=os.path.basename)
def test_example_config_validates(config_path, tmp_path):
    staged = tmp_path / "splunk_config.yml"
    with open(config_path, encoding="utf-8") as handle:
        staged.write_text(_with_inventory_plugin(handle.read()), encoding="utf-8")
    validate_config_file(str(staged))


@pytest.mark.parametrize(
    "config_path",
    _app_scope_paths(),
    ids=lambda p: os.path.basename(os.path.dirname(p)),
)
def test_app_scope_config_validates(config_path):
    validate_config_file(config_path)
