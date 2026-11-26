"""Unit tests for spa.licenses (no Software/ or AWS required)."""

import json
import os
import sys

import pytest

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from spa import licenses  # noqa: E402


def test_licenses_json_error_redacts_secrets(monkeypatch, capsys):
    secret = "AKIA0000000000000000"

    def boom(*_args, **_kwargs):
        raise RuntimeError("denied " + secret)

    monkeypatch.setattr(licenses, "scan_licenses", boom)
    assert licenses.main(["--json"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert secret not in captured.out
    assert "***" in captured.out


def _license_xml(
    *,
    license_type="enterprise",
    group_id="Enterprise",
    expiration="4102444800",
    creation="1700000000",
    addons=(),
):
    addon_xml = "".join("<add_on>%s</add_on>" % addon for addon in addons)
    return """<license>
  <signature>must-not-be-emitted</signature>
  <payload>
    <guid>must-not-be-emitted</guid>
    <type>{license_type}</type>
    <group_id>{group_id}</group_id>
    <creation_time>{creation}</creation_time>
    <expiration_time>{expiration}</expiration_time>
    <add_ons>{addons}</add_ons>
  </payload>
</license>
""".format(
        license_type=license_type,
        group_id=group_id,
        creation=creation,
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


def test_es_editions_addon_attribute_is_es_capability(tmp_path):
    """Premier NFR ships ES as add_on name=es_editions, not element text 'es'."""
    path = tmp_path / "Splunk_ES.lic"
    path.write_text(
        """<license>
  <signature>must-not-be-emitted</signature>
  <payload>
    <guid>must-not-be-emitted</guid>
    <type>enterprise</type>
    <group_id>Enterprise</group_id>
    <creation_time>1700000000</creation_time>
    <expiration_time>4102444800</expiration_time>
    <add_ons>
      <add_on name="es_editions" type="app"/>
    </add_ons>
  </payload>
</license>
"""
    )
    record = licenses.parse_license_file(path)
    assert "es" in record["addons"]
    assert "es" in record["capabilities"]
    assert "enterprise" in record["capabilities"]
    assert "must-not-be-emitted" not in str(record)
    validation = licenses.validate_configured_license_files(
        [record],
        ["Splunk_ES.lic"],
        ["enterprise", "es"],
        enforce_requirements=True,
    )
    assert validation["errors"] == []


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


def test_parse_license_rejects_dtd_after_leading_comment(tmp_path):
    comment = "<!-- " + ("x" * 4100) + " -->\n"
    delayed = (
        comment
        + '<!DOCTYPE license [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        + _license_xml()
    )
    path = tmp_path / "delayed-dtd.lic"
    path.write_text(delayed)
    assert len(comment.encode("utf-8")) > 4096
    record = licenses.parse_license_file(path)
    assert record["status"] == "invalid"


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
        _write_license(tmp_path / "lab-old.license", expiration="1893456000")
    )
    newer = licenses.parse_license_file(
        _write_license(tmp_path / "renamed-commercial.license", expiration="4102444800")
    )
    expired = licenses.parse_license_file(
        _write_license(tmp_path / "even-newer-name.lic", expiration="946684800")
    )
    proposal = licenses.propose_license_files([old, newer, expired], itsi_in_config=False)
    assert proposal["proposed_splunk_license_file"] == ["renamed-commercial.license"]


def test_proposal_stacks_dedicated_enterprise_and_itsi_when_combo_also_exists(tmp_path):
    enterprise = licenses.parse_license_file(_write_license(tmp_path / "Splunk_Enterprise.lic"))
    itsi = licenses.parse_license_file(
        _write_license(
            tmp_path / "Splunk_ITSI.lic",
            license_type="addon",
            group_id="ITSI",
            addons=("itsi",),
        )
    )
    combo = licenses.parse_license_file(
        _write_license(
            tmp_path / "combined.lic",
            addons=("ITSI", "Splunk Enterprise Security"),
        )
    )
    proposal = licenses.propose_license_files(
        [combo, enterprise, itsi], itsi_in_config=True, es_in_config=False
    )
    assert proposal["proposed_splunk_license_file"] == [
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
    ]


def test_discover_symlink_licenses_record_link_target(tmp_path):
    nfr = _write_license(tmp_path / "Splunk_Enterprise_NFR_lab.License")
    link = tmp_path / "Splunk_Enterprise.lic"
    link.symlink_to(nfr.name)
    discovered = licenses.discover_license_files(tmp_path)
    by_name = {item["basename"]: item for item in discovered}
    assert by_name["Splunk_Enterprise.lic"]["symlink"] is True
    assert by_name["Splunk_Enterprise.lic"]["link_target"] == "Splunk_Enterprise_NFR_lab.License"
    assert by_name["Splunk_Enterprise.lic"]["path"] == str(nfr.resolve())


def test_proposal_prefers_symlink_basenames_for_same_resolved_path(tmp_path):
    enterprise_nfr = _write_license(tmp_path / "Splunk_Enterprise_NFR_lab.License")
    itsi_nfr = _write_license(
        tmp_path / "Splunk_ITSI_NFR_lab.License",
        license_type="addon",
        group_id="ITSI",
        addons=("itsi",),
    )
    (tmp_path / "Splunk_Enterprise.lic").symlink_to(enterprise_nfr.name)
    (tmp_path / "Splunk_ITSI.lic").symlink_to(itsi_nfr.name)
    discovered = licenses.discover_license_files(tmp_path)
    proposal = licenses.propose_license_files(discovered, itsi_in_config=True)
    assert proposal["proposed_splunk_license_file"] == [
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
    ]
    rendered = licenses.format_licenses_text(
        {
            "discovered_files": discovered,
            "proposed_splunk_license_file": proposal["proposed_splunk_license_file"],
        }
    )
    assert "Splunk_Enterprise.lic -> Splunk_Enterprise_NFR_lab.License" in rendered
    assert "Splunk_ITSI.lic -> Splunk_ITSI_NFR_lab.License" in rendered


def test_licenses_list_next_sets_symlink_basenames(tmp_path):
    from spa.next_steps import licenses_list_next

    enterprise_nfr = _write_license(tmp_path / "Splunk_Enterprise_NFR_lab.License")
    itsi_nfr = _write_license(
        tmp_path / "Splunk_ITSI_NFR_lab.License",
        license_type="addon",
        group_id="ITSI",
        addons=("itsi",),
    )
    (tmp_path / "Splunk_Enterprise.lic").symlink_to(enterprise_nfr.name)
    (tmp_path / "Splunk_ITSI.lic").symlink_to(itsi_nfr.name)
    config = tmp_path / "splunk_config.yml"
    config.write_text(
        "splunk_app_deployment:\n"
        "  apps:\n"
        "    - app_id: 1841\n"
        "      premium_app: itsi\n"
        "splunk_hosts:\n"
        "  - name: lm\n"
        "    roles: [license_manager]\n"
    )
    scan = licenses.scan_licenses(
        tmp_path,
        software_dir=str(tmp_path),
        config_path=config,
    )
    assert scan["proposed_splunk_license_file"] == [
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
    ]
    nxt = licenses_list_next(scan)
    write = next(row for row in nxt if row["id"] == "config.set.license_file")
    assert "Splunk_Enterprise.lic" in write["ask"]
    assert "Splunk_ITSI.lic" in write["ask"]
    assert "Splunk_Enterprise_NFR_lab.License" not in write["ask"]
    assert write["argv"][-2] == '["Splunk_Enterprise.lic","Splunk_ITSI.lic"]'


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


def test_licenses_human_output_stays_out_of_json(monkeypatch, capsys):
    monkeypatch.setattr(
        licenses,
        "scan_licenses",
        lambda *args, **kwargs: {
            "ok": True,
            "software_dir": "/tmp/Software",
            "software_dir_exists": True,
            "discovered_files": [
                {
                    "basename": "Splunk_Enterprise.lic",
                    "license_type": "enterprise",
                    "status": "valid",
                    "expires_at": "2099-01-01",
                    "signature": "must-not-be-emitted",
                }
            ],
            "proposed_splunk_license_file": ["Splunk_Enterprise.lic"],
            "yaml_snippet": "splunk_license_file: Splunk_Enterprise.lic",
            "warnings": [],
            "license_validation": {"errors": [], "warnings": []},
        },
    )

    assert licenses.main([]) == 0
    human = capsys.readouterr()
    assert human.err == ""
    assert human.out.startswith("{") is False
    assert "Splunk_Enterprise.lic" in human.out
    assert "enterprise" in human.out
    assert "valid" in human.out
    assert "must-not-be-emitted" not in human.out

    assert licenses.main(["--json"]) == 0
    encoded = capsys.readouterr()
    assert encoded.err == ""
    payload = json.loads(encoded.out)
    assert payload["proposed_splunk_license_file"] == ["Splunk_Enterprise.lic"]
    assert "Software:" not in encoded.out

    assert licenses.main([], as_agent=True) == 0
    agent = capsys.readouterr()
    assert agent.err == ""
    assert json.loads(agent.out)["software_dir"] == "/tmp/Software"


def _keys(value):
    found = set()
    if isinstance(value, dict):
        found.update(value)
        for item in value.values():
            found.update(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_keys(item))
    return found


def test_agent_licenses_are_compact_until_details(monkeypatch, capsys):
    scan = {
        "ok": True,
        "software_dir": "/tmp/Software",
        "software_dir_exists": True,
        "discovered_files": [
            {
                "basename": "Splunk_Enterprise.lic",
                "path": "/tmp/Software/Splunk_Enterprise.lic",
                "size_bytes": 120,
                "license_type": "enterprise",
                "status": "valid",
                "expires_at": "2099-01-01",
                "addons": ["itsi"],
                "capabilities": ["enterprise", "itsi"],
            }
        ],
        "proposed_splunk_license_file": ["Splunk_Enterprise.lic"],
        "yaml_snippet": "splunk_license_file: Splunk_Enterprise.lic",
        "warnings": [],
        "license_validation": {"errors": [], "warnings": []},
    }
    monkeypatch.setattr(licenses, "scan_licenses", lambda *args, **kwargs: scan)

    assert licenses.main([]) == 0
    human = capsys.readouterr()
    assert human.err == ""
    assert human.out == licenses.format_licenses_text(scan)
    assert "enterprise" in human.out
    assert "/tmp/Software/Splunk_Enterprise.lic" not in human.out

    assert licenses.main([], as_agent=True) == 0
    agent = capsys.readouterr()
    assert agent.err == ""
    payload = json.loads(agent.out)
    assert payload["software_dir"] == "/tmp/Software"
    assert payload["licenses"] == [
        {
            "basename": "Splunk_Enterprise.lic",
            "status": "valid",
            "expiration": "2099-01-01",
            "capabilities": ["enterprise", "itsi"],
        }
    ]
    assert "path" not in _keys(payload)
    assert "licenses_detail" not in payload

    assert licenses.main(["--details"], as_agent=True) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert detailed["licenses"] == payload["licenses"]
    assert detailed["licenses_detail"][0]["path"] == "/tmp/Software/Splunk_Enterprise.lic"


def test_build_yaml_snippet():
    assert "Splunk_Enterprise.lic" in licenses.build_yaml_snippet([])
    assert licenses.build_yaml_snippet(["A.lic"]) == "splunk_license_file: A.lic"
    snippet = licenses.build_yaml_snippet(["A.lic", "B.lic"])
    assert snippet.startswith("splunk_license_file:")
    assert "- A.lic" in snippet


def test_add_license_file_first_nfr_creates_canonical_symlink(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    source = _write_license(tmp_path / "Splunk_Enterprise_NFR_lab.License")
    result = licenses.add_license_file(software, source)
    dest = software / "Splunk_Enterprise_NFR_lab.License"
    canonical = software / "Splunk_Enterprise.lic"
    assert dest.is_file()
    assert dest.read_text() == source.read_text()
    assert source.is_file()
    assert canonical.is_symlink()
    assert canonical.readlink() == type(canonical)("Splunk_Enterprise_NFR_lab.License")
    assert result["copied"] is True
    assert result["basename"] == "Splunk_Enterprise_NFR_lab.License"
    assert result["replaced"] is False
    assert result["canonical_mode"] == "symlink"


def test_add_license_file_newer_nfr_auto_retargets_canonical(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    old = _write_license(
        tmp_path / "Splunk_Enterprise_NFR_old.License",
        expiration="1893456000",
    )
    licenses.add_license_file(software, old)
    newer = _write_license(
        tmp_path / "Splunk_Enterprise_NFR_new.License",
        expiration="4102444800",
    )
    result = licenses.add_license_file(software, newer)
    canonical = software / "Splunk_Enterprise.lic"
    assert (software / "Splunk_Enterprise_NFR_old.License").is_file()
    assert (software / "Splunk_Enterprise_NFR_new.License").is_file()
    assert canonical.is_symlink()
    assert canonical.readlink() == type(canonical)("Splunk_Enterprise_NFR_new.License")
    assert result["replaced"] is True
    assert result["previous_target"] == "Splunk_Enterprise_NFR_old.License"
    assert result["canonical"] == "Splunk_Enterprise.lic"
    rendered = licenses.format_license_add_text(result)
    assert "Splunk_Enterprise_NFR_new.License" in rendered
    assert "Splunk_Enterprise_NFR_old.License" in rendered
    assert "must-not-be-emitted" not in rendered
    assert "must-not-be-emitted" not in str(result)


def test_add_license_file_older_nfr_and_size_extension_leave_canonical(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    first = _write_license(
        tmp_path / "Splunk_Enterprise_NFR_lab.License",
        expiration="4102444800",
    )
    licenses.add_license_file(software, first)
    older = _write_license(
        tmp_path / "Splunk_Enterprise_NFR_older.License",
        expiration="1893456000",
    )
    older_result = licenses.add_license_file(software, older)
    canonical = software / "Splunk_Enterprise.lic"
    assert (software / "Splunk_Enterprise_NFR_older.License").is_file()
    assert canonical.readlink() == type(canonical)("Splunk_Enterprise_NFR_lab.License")
    assert older_result["replaced"] is False
    assert older_result["basename"] == "Splunk_Enterprise_NFR_older.License"
    assert "canonical unchanged" in licenses.format_license_add_text(older_result)

    extension = _write_license(tmp_path / "Splunk_Enterprise_50GB.lic")
    stacked = licenses.add_license_file(software, extension)
    assert (software / "Splunk_Enterprise_50GB.lic").is_file()
    assert canonical.readlink() == type(canonical)("Splunk_Enterprise_NFR_lab.License")
    assert stacked["replaced"] is False
    assert stacked["basename"] == "Splunk_Enterprise_50GB.lic"
    assert "canonical unchanged" in licenses.format_license_add_text(stacked)


def test_add_license_file_replace_retargets_when_heuristic_does_not_fire(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    first = _write_license(tmp_path / "Splunk_Enterprise_NFR_lab.License")
    licenses.add_license_file(software, first)
    extension = _write_license(tmp_path / "Splunk_Enterprise_50GB.lic")
    result = licenses.add_license_file(software, extension, replace=True)
    canonical = software / "Splunk_Enterprise.lic"
    assert canonical.is_symlink()
    assert canonical.readlink() == type(canonical)("Splunk_Enterprise_50GB.lic")
    assert (software / "Splunk_Enterprise_NFR_lab.License").is_file()
    assert result["replaced"] is True
    assert result["previous_target"] == "Splunk_Enterprise_NFR_lab.License"
    assert result["canonical"] == "Splunk_Enterprise.lic"


def test_add_license_file_itsi_and_es_create_only_matching_canonical(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    itsi = _write_license(
        tmp_path / "Splunk_ITSI_NFR_lab.License",
        license_type="addon",
        group_id="ITSI",
        addons=("itsi",),
    )
    itsi_result = licenses.add_license_file(software, itsi)
    assert (software / "Splunk_ITSI.lic").is_symlink()
    assert (software / "Splunk_ITSI.lic").readlink() == type(itsi)("Splunk_ITSI_NFR_lab.License")
    assert not (software / "Splunk_Enterprise.lic").exists()
    assert not (software / "Splunk_ES.lic").exists()
    assert itsi_result["canonical"] == "Splunk_ITSI.lic"

    es = _write_license(
        tmp_path / "Splunk_ES_NFR_lab.License",
        license_type="addon",
        group_id="Enterprise Security",
        addons=("SplunkEnterpriseSecuritySuite",),
    )
    es_result = licenses.add_license_file(software, es)
    assert (software / "Splunk_ES.lic").is_symlink()
    assert (software / "Splunk_ES.lic").readlink() == type(es)("Splunk_ES_NFR_lab.License")
    assert not (software / "Splunk_Enterprise.lic").exists()
    assert es_result["canonical"] == "Splunk_ES.lic"

    extra_itsi = _write_license(
        tmp_path / "Splunk_ITSI_extra.lic",
        license_type="addon",
        group_id="ITSI",
        addons=("itsi",),
        expiration="1893456000",
    )
    extra = licenses.add_license_file(software, extra_itsi)
    assert (software / "Splunk_ITSI.lic").readlink() == type(itsi)("Splunk_ITSI_NFR_lab.License")
    assert extra["replaced"] is False
    assert extra["basename"] == "Splunk_ITSI_extra.lic"


def test_add_license_file_combo_creates_matching_canonicals(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    combo = _write_license(
        tmp_path / "combined_NFR.License",
        addons=("IT Service Intelligence",),
    )
    result = licenses.add_license_file(software, combo)
    enterprise = software / "Splunk_Enterprise.lic"
    itsi = software / "Splunk_ITSI.lic"
    assert enterprise.is_symlink()
    assert itsi.is_symlink()
    assert enterprise.readlink() == type(enterprise)("combined_NFR.License")
    assert itsi.readlink() == type(itsi)("combined_NFR.License")
    assert not (software / "Splunk_ES.lic").exists()
    assert {row["name"] for row in result["canonicals"]} == {
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
    }
    assert result["replaced"] is False


def test_add_license_file_dest_exists_invalid_and_hides_payload(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    first = _write_license(tmp_path / "lab.lic")
    licenses.add_license_file(software, first)
    again = tmp_path / "again"
    again.mkdir()
    duplicate = _write_license(again / "lab.lic")
    with pytest.raises(licenses.LicenseAddError, match="already exists"):
        licenses.add_license_file(software, duplicate)
    overwritten = licenses.add_license_file(software, duplicate, force=True)
    assert overwritten["copied"] is True
    assert (software / "lab.lic").read_text() == duplicate.read_text()

    invalid = tmp_path / "broken.lic"
    invalid.write_text("not XML")
    with pytest.raises(licenses.LicenseAddError, match="not valid XML"):
        licenses.add_license_file(software, invalid)

    wrong = tmp_path / "notes.txt"
    wrong.write_text("nope")
    with pytest.raises(licenses.LicenseAddError, match="must end with"):
        licenses.add_license_file(software, wrong)

    blob = str(overwritten) + licenses.format_license_add_text(overwritten)
    assert "must-not-be-emitted" not in blob
    assert "<license>" not in blob
    assert "guid" not in blob.lower() or "guid" not in str(overwritten)


def test_add_license_file_canonical_basename_is_a_regular_file(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    source = _write_license(tmp_path / "Splunk_Enterprise.lic")
    result = licenses.add_license_file(software, source)
    dest = software / "Splunk_Enterprise.lic"
    assert dest.is_file()
    assert not dest.is_symlink()
    assert result["copied"] is True
    assert result["basename"] == "Splunk_Enterprise.lic"
    assert result.get("canonicals") == []


def test_plan_license_add_names_auto_replace_in_details(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    old = _write_license(
        tmp_path / "Splunk_Enterprise_NFR_old.License",
        expiration="1893456000",
    )
    licenses.add_license_file(software, old)
    newer = _write_license(
        tmp_path / "Splunk_Enterprise_NFR_new.License",
        expiration="4102444800",
    )
    plan = licenses.plan_license_add(software, newer)
    assert any(
        "will retarget Splunk_Enterprise.lic from Splunk_Enterprise_NFR_old.License to Splunk_Enterprise_NFR_new.License"
        in line
        for line in plan["details"]
    )
    stacked = _write_license(tmp_path / "Splunk_Enterprise_50GB.lic")
    stack_plan = licenses.plan_license_add(software, stacked)
    assert any("canonical Splunk_Enterprise.lic stays" in line for line in stack_plan["details"])
    assert not (software / "Splunk_Enterprise_50GB.lic").exists()


def test_licenses_add_next_stacks_or_uses_canonical_after_replace():
    from spa.next_steps import licenses_add_next

    stacked = licenses_add_next(
        {"basename": "Splunk_Enterprise_50GB.lic", "replaced": False},
        config_exists=True,
        configured=["Splunk_Enterprise.lic"],
        existing_canonicals=["Splunk_Enterprise.lic"],
    )
    assert [row["id"] for row in stacked] == ["licenses.list", "config.set.license_file"]
    assert "Splunk_Enterprise_50GB.lic" in stacked[1]["ask"]
    assert "Splunk_Enterprise.lic" in stacked[1]["ask"]

    replaced = licenses_add_next(
        {
            "basename": "Splunk_Enterprise_NFR_new.License",
            "replaced": True,
            "canonical": "Splunk_Enterprise.lic",
        },
        config_exists=True,
        configured=["Splunk_Enterprise.lic"],
        existing_canonicals=["Splunk_Enterprise.lic"],
    )
    assert "Splunk_Enterprise.lic" in replaced[1]["ask"]
    assert "Splunk_Enterprise_NFR_new.License" not in replaced[1]["ask"]

    listed_only = licenses_add_next({"basename": "lab.lic", "replaced": False}, config_exists=False)
    assert [row["id"] for row in listed_only] == ["licenses.list"]


def test_add_license_file_windows_symlink_fallback_copies_canonical(tmp_path, monkeypatch):
    software = tmp_path / "Software"
    software.mkdir()
    source = _write_license(tmp_path / "Splunk_Enterprise_NFR_lab.License")

    def boom(self, *args, **kwargs):
        raise OSError("symlink privilege not held")

    monkeypatch.setattr(licenses.Path, "symlink_to", boom)
    first = licenses.add_license_file(software, source)
    canonical = software / "Splunk_Enterprise.lic"
    assert canonical.is_file()
    assert not canonical.is_symlink()
    assert canonical.read_text() == (software / source.name).read_text()
    assert first["canonical_mode"] == "copy"
    assert "canonical_mode: copy" in licenses.format_license_add_text(first)

    production = _write_license(tmp_path / "Splunk_Enterprise_50GB.lic")
    with pytest.raises(licenses.LicenseAddError, match="regular file"):
        licenses.add_license_file(software, production, replace=True)
    replaced = licenses.add_license_file(software, production, replace=True, force=True)
    assert canonical.is_file()
    assert not canonical.is_symlink()
    assert canonical.read_text() == (software / production.name).read_text()
    assert replaced["canonical_mode"] == "copy"
    assert replaced["replaced"] is True
