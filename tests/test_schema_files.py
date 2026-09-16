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

# Not runnable inventories: docs, fragments, or host-less skeletons.
SKIP_EXAMPLE_BASENAMES = {
    "configuration_description.yml",
}


def _example_paths():
    paths = sorted(glob.glob(os.path.join(PROJECT_ROOT, "examples", "topologies", "*.yml")))
    paths += sorted(glob.glob(os.path.join(PROJECT_ROOT, "examples", "*.yml")))
    return [p for p in paths if os.path.basename(p) not in SKIP_EXAMPLE_BASENAMES]


def _app_scope_paths():
    return sorted(glob.glob(os.path.join(PROJECT_ROOT, "tests", "configs", "app_scope", "*", "splunk_config.yml")))


class TestValidateConfigFile:
    def test_valid_temp_file(self, tmp_path):
        cfg = tmp_path / "splunk_config.yml"
        cfg.write_text(
            "plugin: splunk-platform-automator\n"
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
def test_example_config_validates(config_path):
    validate_config_file(config_path)


@pytest.mark.parametrize(
    "config_path",
    _app_scope_paths(),
    ids=lambda p: os.path.basename(os.path.dirname(p)),
)
def test_app_scope_config_validates(config_path):
    validate_config_file(config_path)
