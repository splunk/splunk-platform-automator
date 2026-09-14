"""Unit tests for spa.licenses (no Software/ or AWS required)."""

import os
import sys

import pytest

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from spa import licenses  # noqa: E402


def _license_xml(
    *,
    license_type="enterprise",
    group_id="Enterprise",
    expiration="4102444800",
    addons=(),
):
    addon_xml = "".join("<add_on>%s</add_on>" % addon for addon in addons)
    return """<license>
  <signature>must-not-be-emitted</signature>
  <payload>
    <guid>must-not-be-emitted</guid>
    <type>{license_type}</type>
    <group_id>{group_id}</group_id>
    <creation_time>1700000000</creation_time>
    <expiration_time>{expiration}</expiration_time>
    <add_ons>{addons}</add_ons>
  </payload>
</license>
""".format(
        license_type=license_type,
        group_id=group_id,
        expiration=expiration,
        addons=addon_xml,
    )


def _write_license(path, **kwargs):
    path.write_text(_license_xml(**kwargs))
    return path


def test_discover_license_files(tmp_path):
    _write_license(tmp_path / "Splunk_Enterprise.lic")
    _write_license(tmp_path / "Splunk_ITSI.lic", addons=("IT Service Intelligence",))
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


def test_parse_license_content_and_does_not_expose_sensitive_payload(tmp_path):
    path = _write_license(
        tmp_path / "opaque-name.lic",
        addons=("IT Service Intelligence", "SplunkEnterpriseSecuritySuite"),
    )
    record = licenses.parse_license_file(path)
    assert record["license_type"] == "enterprise"
    assert record["group_id"] == "Enterprise"
    assert record["addons"] == ["es", "itsi"]
    assert record["capabilities"] == ["enterprise", "es", "itsi"]
    assert record["expires_at"] == "2100-01-01T00:00:00Z"
    assert record["status"] == "valid"
    assert "signature" not in record
    assert "guid" not in record
    assert "must-not-be-emitted" not in str(record)


def test_parse_expired_perpetual_invalid_and_rejects_doctype(tmp_path):
    expired = _write_license(tmp_path / "expired.lic", expiration="946684800")
    perpetual = _write_license(tmp_path / "perpetual.lic", expiration="0")
    invalid = tmp_path / "invalid.lic"
    invalid.write_text("not XML")
    dtd = tmp_path / "dtd.lic"
    dtd.write_text('<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><license/>')
    assert licenses.parse_license_file(expired)["status"] == "expired"
    assert licenses.parse_license_file(perpetual)["status"] == "perpetual"
    assert licenses.parse_license_file(invalid)["status"] == "invalid"
    assert licenses.parse_license_file(dtd)["status"] == "invalid"


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


@pytest.mark.parametrize(
    "config,expected",
    [
        ({"splunk_app_deployment": {"apps": [{"app_id": 263}]}}, True),
        ({"splunk_app_deployment": {"apps": [{"name": "Splunk Enterprise Security"}]}}, True),
        ({"splunk_app_deployment": {"apps": [{"app_id": 263, "state": "absent"}]}}, False),
        ({}, False),
    ],
)
def test_config_has_es(config, expected):
    assert licenses.config_has_es(config) is expected


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
    _write_license(tmp_path / "Splunk_Enterprise.lic")
    _write_license(tmp_path / "Splunk_ITSI.lic", license_type="addon", group_id="ITSI", addons=("itsi",))
    discovered = licenses.discover_license_files(tmp_path)
    proposal = licenses.propose_license_files(discovered, itsi_in_config=True)
    assert proposal["proposed_splunk_license_file"] == ["Splunk_Enterprise.lic", "Splunk_ITSI.lic"]
    assert proposal["itsi_license"] == "Splunk_ITSI.lic"


def test_propose_license_files_itsi_missing(tmp_path):
    discovered = [
        licenses.parse_license_file(
            _write_license(tmp_path / "Splunk_Enterprise.lic")
        )
    ]
    proposal = licenses.propose_license_files(discovered, itsi_in_config=True)
    assert proposal["proposed_splunk_license_file"] == ["Splunk_Enterprise.lic"]
    assert proposal["itsi_license"] is None
    assert "itsi" in proposal["unsatisfied_requirements"]


def test_proposal_prefers_latest_usable_license_by_content(tmp_path):
    old = licenses.parse_license_file(
        _write_license(tmp_path / "Splunk_Enterprise.lic", expiration="1893456000")
    )
    newer = licenses.parse_license_file(
        _write_license(tmp_path / "renamed-commercial.license", expiration="4102444800")
    )
    expired = licenses.parse_license_file(
        _write_license(tmp_path / "even-newer-name.lic", expiration="946684800")
    )
    proposal = licenses.propose_license_files([old, newer, expired], itsi_in_config=False)
    assert proposal["proposed_splunk_license_file"] == ["renamed-commercial.license"]


def test_proposal_can_satisfy_enterprise_itsi_and_es_with_one_license(tmp_path):
    combined = licenses.parse_license_file(
        _write_license(
            tmp_path / "combined.lic",
            addons=("ITSI", "Splunk Enterprise Security"),
        )
    )
    proposal = licenses.propose_license_files(
        [combined], itsi_in_config=True, es_in_config=True
    )
    assert proposal["proposed_splunk_license_file"] == ["combined.lic"]
    assert proposal["unsatisfied_requirements"] == []


def test_configured_license_validation_checks_expiration_and_capabilities(tmp_path):
    enterprise = licenses.parse_license_file(_write_license(tmp_path / "enterprise.lic"))
    expired_itsi = licenses.parse_license_file(
        _write_license(
            tmp_path / "itsi-old.lic",
            license_type="addon",
            group_id="ITSI",
            expiration="946684800",
            addons=("ITSI",),
        )
    )
    validation = licenses.validate_configured_license_files(
        [enterprise, expired_itsi],
        ["enterprise.lic", "itsi-old.lic"],
        ["enterprise", "itsi"],
        enforce_requirements=True,
    )
    assert any("expired" in error for error in validation["errors"])
    assert any("required capability: itsi" in error for error in validation["errors"])


def test_scan_licenses_matches_configured_es_entitlement(tmp_path):
    _write_license(tmp_path / "base.lic")
    _write_license(
        tmp_path / "security-addon.lic",
        license_type="addon",
        group_id="Enterprise Security",
        addons=("SplunkEnterpriseSecuritySuite",),
    )
    config = tmp_path / "splunk_config.yml"
    config.write_text(
        """
splunk_defaults:
  splunk_license_file:
    - base.lic
    - security-addon.lic
splunk_hosts:
  - name: lm
    roles: [license_manager]
splunk_app_deployment:
  apps:
    - name: Splunk Enterprise Security
      app_id: 263
      target_roles: [search_head]
"""
    )
    result = licenses.scan_licenses(
        tmp_path,
        software_dir=str(tmp_path),
        config_path=config,
    )
    assert result["es_in_config"] is True
    assert result["required_capabilities"] == ["enterprise", "es"]
    assert result["proposed_splunk_license_file"] == ["base.lic", "security-addon.lic"]
    assert result["license_validation"]["errors"] == []


def test_build_yaml_snippet():
    assert "Splunk_Enterprise.lic" in licenses.build_yaml_snippet([])
    assert licenses.build_yaml_snippet(["A.lic"]) == "splunk_license_file: A.lic"
    snippet = licenses.build_yaml_snippet(["A.lic", "B.lic"])
    assert snippet.startswith("splunk_license_file:")
    assert "- A.lic" in snippet
