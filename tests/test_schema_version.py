"""Schema version dispatcher: schema_version stamp and operator config_version."""

from __future__ import annotations

import os
import sys

import pytest
import yaml

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ansible", "plugins", "inventory"))

from schema import (  # noqa: E402
    ConfigValidationError,
    SplunkConfig,
    validate_config,
    validate_config_file,
)

_OMIT = object()
_PASSWORD = "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"


def _minimal(schema_version=_OMIT, config_version=_OMIT):
    config = {"plugin": "splunk-platform-automator"}
    if schema_version is not _OMIT:
        config["schema_version"] = schema_version
    if config_version is not _OMIT:
        config["config_version"] = config_version
    config["splunk_defaults"] = {"splunk_admin_password": _PASSWORD}
    config["splunk_hosts"] = [{"name": "shidx", "roles": ["indexer"]}]
    return config


class TestSchemaVersionTables:
    def test_day_one_current_is_1_with_empty_migrations(self):
        import schema

        assert schema.CURRENT_SCHEMA_VERSION == 1
        assert schema.SCHEMAS == {1: SplunkConfig}
        assert schema.MIGRATIONS == {}


class TestEffectiveSchemaVersion:
    def test_absent_schema_version_validates_as_version_1(self):
        result = validate_config(_minimal())
        assert result.schema_version is None
        assert result.plugin == "splunk-platform-automator"

    def test_null_schema_version_validates_as_version_1(self):
        result = validate_config(_minimal(schema_version=None))
        assert result.schema_version is None

    def test_stamped_1_round_trips(self):
        result = validate_config(_minimal(schema_version=1))
        assert result.schema_version == 1

    def test_bool_schema_version_is_rejected(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(_minimal(schema_version=True))
        text = str(exc_info.value)
        assert "schema_version" in text
        assert "boolean" in text.lower()

    def test_string_schema_version_is_rejected(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(_minimal(schema_version="1"))
        text = str(exc_info.value)
        assert "schema_version" in text
        assert "integer" in text.lower()

    def test_schema_version_below_1_is_rejected(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(_minimal(schema_version=0))
        text = str(exc_info.value)
        assert "schema_version" in text

    def test_schema_version_above_current_is_rejected(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(_minimal(schema_version=2))
        text = str(exc_info.value)
        assert "schema_version" in text
        assert "2" in text

    def test_older_than_current_validates_historically_then_names_migrate(self, monkeypatch):
        import schema

        monkeypatch.setattr(schema, "CURRENT_SCHEMA_VERSION", 2)
        monkeypatch.setattr(schema, "SCHEMAS", {1: SplunkConfig, 2: SplunkConfig})
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(_minimal(schema_version=1))
        text = str(exc_info.value)
        assert "schema_version" in text
        assert "spa config migrate" in text

    def test_older_than_current_reports_historical_errors_before_migrate(self, monkeypatch):
        import schema

        monkeypatch.setattr(schema, "CURRENT_SCHEMA_VERSION", 2)
        monkeypatch.setattr(schema, "SCHEMAS", {1: SplunkConfig, 2: SplunkConfig})
        config = _minimal(schema_version=1)
        config["splunk_hosts"] = []
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        text = str(exc_info.value)
        assert "splunk_hosts" in text
        assert "spa config migrate" not in text


class TestConfigVersion:
    def test_string_config_version_round_trips(self):
        result = validate_config(_minimal(config_version="1.4.0"))
        assert result.config_version == "1.4.0"
        assert result.schema_version is None

    def test_integer_config_version_round_trips(self):
        result = validate_config(_minimal(config_version=12))
        assert result.config_version == 12

    def test_bool_config_version_is_rejected(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(_minimal(config_version=True))
        text = str(exc_info.value)
        assert "config_version" in text

    def test_config_version_does_not_satisfy_schema_stamp(self):
        result = validate_config(_minimal(config_version="chg-117"))
        assert result.config_version == "chg-117"
        assert result.schema_version is None


class TestIdentityKeyOrder:
    def test_leading_comments_and_blank_lines_before_plugin_pass(self, tmp_path):
        cfg = tmp_path / "splunk_config.yml"
        cfg.write_text(
            "---\n"
            "# intent: config-test\n"
            "# sva: S1\n"
            "\n"
            "plugin: splunk-platform-automator\n"
            "splunk_defaults:\n"
            "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
            "splunk_hosts:\n"
            "  - name: shidx\n"
            "    roles: [indexer]\n",
            encoding="utf-8",
        )
        result = validate_config_file(str(cfg))
        assert result.plugin == "splunk-platform-automator"
        assert result.schema_version is None

    def test_general_before_plugin_fails(self):
        config = {
            "general": {"url_locale": "en-GB"},
            "plugin": "splunk-platform-automator",
            "splunk_defaults": {"splunk_admin_password": _PASSWORD},
            "splunk_hosts": [{"name": "shidx", "roles": ["indexer"]}],
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        text = str(exc_info.value)
        assert "plugin" in text

    def test_schema_version_after_general_fails(self):
        config = {
            "plugin": "splunk-platform-automator",
            "general": {"url_locale": "en-GB"},
            "schema_version": 1,
            "splunk_defaults": {"splunk_admin_password": _PASSWORD},
            "splunk_hosts": [{"name": "shidx", "roles": ["indexer"]}],
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        text = str(exc_info.value)
        assert "schema_version" in text

    def test_blank_line_and_comment_between_plugin_and_schema_version_still_validate(self, tmp_path):
        cfg = tmp_path / "splunk_config.yml"
        cfg.write_text(
            "plugin: splunk-platform-automator\n"
            "\n"
            "# hand comment\n"
            "schema_version: 1\n"
            "splunk_defaults:\n"
            "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
            "splunk_hosts:\n"
            "  - name: shidx\n"
            "    roles: [indexer]\n",
            encoding="utf-8",
        )
        result = validate_config_file(str(cfg))
        assert result.schema_version == 1

    def test_yaml_load_preserves_plugin_then_schema_version(self):
        loaded = yaml.safe_load(
            "plugin: splunk-platform-automator\n"
            "schema_version: 1\n"
            "splunk_defaults:\n"
            "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
            "splunk_hosts:\n"
            "  - name: shidx\n"
            "    roles: [indexer]\n"
        )
        result = validate_config(loaded)
        assert list(loaded)[:2] == ["plugin", "schema_version"]
        assert result.schema_version == 1
