"""Unit tests for spa.licenses (no Software/ or AWS required)."""

import os
import sys

import pytest

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from spa import licenses  # noqa: E402


def test_discover_license_files(tmp_path):
    (tmp_path / "Splunk_Enterprise.lic").write_text("")
    (tmp_path / "Splunk_ITSI.lic").write_text("")
    (tmp_path / "notes.txt").write_text("ignore")
    found = licenses.discover_license_files(tmp_path)
    names = {item["basename"] for item in found}
    assert names == {"Splunk_Enterprise.lic", "Splunk_ITSI.lic"}


def test_discover_missing_dir(tmp_path):
    assert licenses.discover_license_files(tmp_path / "missing") == []


def test_pick_canonical_exact_and_fallback():
    discovered = [{"basename": "Splunk_Enterprise.lic"}, {"basename": "lab-itsi.license"}]
    assert licenses.pick_canonical(discovered, "Splunk_Enterprise.lic", "enterprise") == "Splunk_Enterprise.lic"
    assert licenses.pick_canonical(discovered, "Splunk_ITSI.lic", "itsi") == "lab-itsi.license"
    assert licenses.pick_canonical(discovered, "Missing.lic", "nope") is None


@pytest.mark.parametrize(
    "config,expected",
    [
        ({"splunk_app_deployment": {"apps": [{"premium_app": "itsi"}]}}, True),
        ({"splunk_app_deployment": {"apps": [{"app_id": 1841}]}}, True),
        ({"splunk_app_deployment": {"apps": [{"itsi_content_pack": True}]}}, True),
        ({"splunk_app_deployment": {"apps": [{"name": "Splunk IT Service Intelligence"}]}}, True),
        ({"splunk_app_deployment": {"apps": [{"name": "Splunk_TA_nix"}]}}, False),
        ({}, False),
    ],
)
def test_config_has_itsi(config, expected):
    assert licenses.config_has_itsi(config) is expected


def test_config_has_license_manager():
    assert licenses.config_has_license_manager(
        {"splunk_hosts": [{"name": "lm", "roles": ["license_manager"]}]}
    )
    assert not licenses.config_has_license_manager(
        {"splunk_hosts": [{"name": "idx", "roles": ["indexer"]}]}
    )


def test_current_license_files_scalar_and_list():
    assert licenses.current_license_files({"splunk_defaults": {"splunk_license_file": "A.lic"}}) == ["A.lic"]
    assert licenses.current_license_files(
        {"splunk_defaults": {"splunk_license_file": ["A.lic", "B.lic"]}}
    ) == ["A.lic", "B.lic"]
    assert licenses.current_license_files({"splunk_defaults": {}}) is None


def test_propose_license_files_with_itsi(tmp_path):
    (tmp_path / "Splunk_Enterprise.lic").write_text("")
    (tmp_path / "Splunk_ITSI.lic").write_text("")
    discovered = licenses.discover_license_files(tmp_path)
    proposal = licenses.propose_license_files(discovered, itsi_in_config=True)
    assert proposal["proposed_splunk_license_file"] == ["Splunk_Enterprise.lic", "Splunk_ITSI.lic"]
    assert proposal["itsi_license"] == "Splunk_ITSI.lic"


def test_propose_license_files_itsi_missing():
    discovered = [{"basename": "Splunk_Enterprise.lic"}]
    proposal = licenses.propose_license_files(discovered, itsi_in_config=True)
    assert proposal["proposed_splunk_license_file"] == ["Splunk_Enterprise.lic"]
    assert proposal["itsi_license"] is None
    assert any("no ITSI license" in reason for reason in proposal["reasons"])


def test_build_yaml_snippet():
    assert "Splunk_Enterprise.lic" in licenses.build_yaml_snippet([])
    assert licenses.build_yaml_snippet(["A.lic"]) == "splunk_license_file: A.lic"
    snippet = licenses.build_yaml_snippet(["A.lic", "B.lic"])
    assert snippet.startswith("splunk_license_file:")
    assert "- A.lic" in snippet
