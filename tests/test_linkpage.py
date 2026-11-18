"""Architecture host page extras gathered at generate time."""

import json
import sys

import pytest

from spa_testutil import PROJECT_ROOT, LIB

pytestmark = pytest.mark.local

sys.path.insert(0, str(LIB))

from spa.linkpage import snapshot_extras  # noqa: E402
from spa.paths import resolve_spa_paths  # noqa: E402


def _env_paths(tmp_path, config_text, software=None):
    dest = tmp_path / "env"
    (dest / "config").mkdir(parents=True)
    (dest / "config" / "splunk_config.yml").write_text(config_text, encoding="utf-8")
    software = software or (tmp_path / "Software")
    software.mkdir(exist_ok=True)
    return resolve_spa_paths(
        start_dir=dest,
        environ={
            "SPA_HOME": str(PROJECT_ROOT),
            "SPA_ENV_DIR": str(dest),
            "SPA_SOFTWARE_DIR": str(software),
        },
        clone_root=PROJECT_ROOT,
    )


def test_linkpage_snapshot_reads_ccm_ttl(tmp_path):
    paths = _env_paths(
        tmp_path,
        "plugin: splunk-platform-automator\n"
        "schema_version: 1\n"
        "splunk_hosts:\n"
        "  - name: shidx\n"
        "    roles: [indexer, search_head]\n",
    )
    (paths.spa_env_dir / "ccm").mkdir()
    (paths.spa_env_dir / "ccm" / "state.json").write_text(
        json.dumps({"ttl": "2026-11-20T09:18:01.000000Z", "deployment_id": "dep-test"}),
        encoding="utf-8",
    )
    extras = snapshot_extras(paths)
    assert extras["linkpage_ccm_ttl"] == "2026-11-20T09:18:01.000000Z"
    assert extras["linkpage_licenses"] == []
    assert "dep-test" not in json.dumps(extras)


def test_linkpage_snapshot_lists_configured_licenses_without_guid(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    (software / "Splunk_Enterprise.lic").write_text(
        """<license>
  <signature>must-not-be-emitted</signature>
  <payload>
    <guid>must-not-be-emitted</guid>
    <type>enterprise</type>
    <group_id>Enterprise</group_id>
    <creation_time>1700000000</creation_time>
    <expiration_time>4102444800</expiration_time>
  </payload>
</license>
""",
        encoding="utf-8",
    )
    paths = _env_paths(
        tmp_path,
        "plugin: splunk-platform-automator\n"
        "schema_version: 1\n"
        "splunk_defaults:\n"
        "  splunk_license_file:\n"
        "    - Splunk_Enterprise.lic\n"
        "splunk_hosts:\n"
        "  - name: shidx\n"
        "    roles: [indexer, search_head]\n",
        software=software,
    )
    extras = snapshot_extras(paths)
    assert extras["linkpage_licenses"] == [
        {
            "basename": "Splunk_Enterprise.lic",
            "expires_at": "2100-01-01T00:00:00Z",
            "status": "valid",
        }
    ]
    dumped = json.dumps(extras)
    assert "must-not-be-emitted" not in dumped
    assert "guid" not in dumped
    assert str(software) not in dumped
