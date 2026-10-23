"""Behavioral contract for transactional splunk_config.yml editing."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from spa.config_edit import (
    ConfigEditError,
    config_app_add,
    config_app_remove,
    config_get,
    config_merge,
    config_provider,
    config_set,
    config_topology,
    config_unset,
)
from spa.apps import AppsError, build_entry, inspect_content_pack_archive, snippet
from spa_testutil import PROJECT_ROOT, min_env_vars, run_spa, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _config(tmp_path: Path, body: str | None = None) -> Path:
    path = tmp_path / "config" / "splunk_config.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        body
        or """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        encoding="utf-8",
    )
    return path


def _load(path: Path):
    yaml = YAML(typ="safe")
    return yaml.load(path.read_text(encoding="utf-8"))


class TestPathContract:
    def test_set_replaces_a_null_section_with_a_mapping(self, tmp_path):
        """CFG-PATH-003. A comment-only section loads as null and can still be extended."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_defaults:
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        result = config_set(
            path,
            PROJECT_ROOT,
            "splunk_defaults.splunk_admin_password",
            from_env="SPLUNK_ADMIN_PASSWORD",
        )
        assert result["changed"] is True
        assert _load(path)["splunk_defaults"]["splunk_admin_password"] == "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"

    def test_set_preserves_comments_and_changes_only_the_path(self, tmp_path):
        """CFG-PATH-001 CFG-PATH-003 CFG-LAYOUT-001."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
# keep me
os:
  set_hostname: true
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        result = config_set(path, PROJECT_ROOT, "os.time_zone", "Europe/Berlin")
        assert result["changed"] is True
        assert result["operations"] == [{"op": "set", "path": "os.time_zone", "value": "Europe/Berlin"}]
        assert "# keep me" in path.read_text(encoding="utf-8")
        assert _load(path)["os"] == {"set_hostname": True, "time_zone": "Europe/Berlin"}

    def test_set_requires_strict_json_for_list(self, tmp_path):
        """CFG-PATH-001."""
        path = _config(tmp_path)
        with pytest.raises(ConfigEditError, match="JSON"):
            config_set(path, PROJECT_ROOT, "splunk_hosts[name=sh].roles", "search_head,indexer")

    def test_selector_get_set_and_unset_use_stable_identity(self, tmp_path):
        """CFG-PATH-002 CFG-PATH-004 CFG-PATH-005."""
        path = _config(tmp_path)
        config_set(path, PROJECT_ROOT, "splunk_hosts[name=sh].roles", '["search_head","indexer"]')
        got = config_get(path, PROJECT_ROOT, "splunk_hosts[name=sh].roles")
        assert got["authored"] == ["search_head", "indexer"]
        config_set(path, PROJECT_ROOT, "splunk_hosts[name=sh].os.time_zone", "UTC")
        config_unset(path, PROJECT_ROOT, "splunk_hosts[name=sh].os.time_zone")
        assert "os" not in _load(path)["splunk_hosts"][0]

    def test_unset_selected_item_removes_only_that_item(self, tmp_path):
        """CFG-PATH-002 CFG-PATH-004."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: sh
    roles: [search_head]
  - name: idx
    roles: [indexer]
""",
        )
        config_unset(path, PROJECT_ROOT, "splunk_hosts[name=idx]", validate=False)
        assert _load(path)["splunk_hosts"] == [{"name": "sh", "roles": ["search_head"]}]

    def test_bare_or_missing_selector_is_rejected_without_write(self, tmp_path):
        """CFG-PATH-002 CFG-TXN-004."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="identity selector"):
            config_set(path, PROJECT_ROOT, "splunk_hosts[].roles", '["indexer"]')
        with pytest.raises(ConfigEditError, match="matched no items"):
            config_set(path, PROJECT_ROOT, "splunk_hosts[name=missing].roles", '["indexer"]')
        assert path.read_bytes() == before

    def test_from_env_authors_lookup_and_get_redacts_secret(self, tmp_path):
        """CFG-PATH-007 CFG-SEC-001."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        result = config_set(
            path,
            PROJECT_ROOT,
            "splunk_defaults.splunk_admin_password",
            from_env="SPLUNK_ADMIN_PASSWORD",
        )
        assert result["operations"][0]["value"] == "<redacted>"
        assert "SPLUNK_ADMIN_PASSWORD" not in result["diff"]
        assert "<redacted>" in result["diff"]
        got = config_get(path, PROJECT_ROOT, "splunk_defaults.splunk_admin_password")
        assert got["authored"] == "set"
        assert "SPLUNK_ADMIN_PASSWORD" not in json.dumps(got)

    def test_secret_positional_value_and_multiple_selector_match_are_rejected(self, tmp_path):
        """CFG-PATH-002 CFG-PATH-007 CFG-SEC-001."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: duplicate
    roles: [search_head]
  - name: duplicate
    roles: [indexer]
""",
        )
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="Secret paths require"):
            config_set(
                path,
                PROJECT_ROOT,
                "splunk_defaults.splunk_admin_password",
                "literal",
            )
        with pytest.raises(ConfigEditError, match="matched multiple items"):
            config_set(
                path,
                PROJECT_ROOT,
                "splunk_hosts[name=duplicate].roles",
                '["deployer"]',
            )
        assert path.read_bytes() == before

    def test_structured_assignment_rejects_and_redacts_nested_secrets(self, tmp_path):
        """CFG-PATH-007 CFG-SEC-001 CFG-TXN-003."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="environment lookup"):
            config_set(
                path,
                PROJECT_ROOT,
                "splunk_hosts",
                '[{"name":"sh","roles":["search_head"],'
                '"splunk_admin_password":"literal-secret"}]',
                validate=False,
            )
        assert path.read_bytes() == before

        result = config_set(
            path,
            PROJECT_ROOT,
            "splunk_hosts",
            '[{"name":"sh","roles":["search_head"],'
            '"splunk_admin_password":"{{ lookup(\'env\', \'HOST_PASSWORD\') }}"}]',
            validate=False,
        )
        serialized = json.dumps(result)
        assert "HOST_PASSWORD" not in serialized
        assert "literal-secret" not in serialized
        assert "<redacted>" in serialized

    def test_get_distinguishes_schema_default_from_unset(self, tmp_path):
        """CFG-PATH-005."""
        path = _config(tmp_path)
        defaulted = config_get(
            path, PROJECT_ROOT, "os.disable_selinux", effective=True
        )
        unset = config_get(path, PROJECT_ROOT, "os.time_zone", effective=True)
        assert defaulted["source"] == "schema_default"
        assert defaulted["authored"] is None and defaulted["effective"] is True
        assert unset["source"] == "unset"
        assert unset["authored"] is None and unset["effective"] is None

    def test_schema_default_is_omitted_unless_explicit(self, tmp_path):
        """CFG-PATH-006."""
        path = _config(tmp_path)
        omitted = config_set(path, PROJECT_ROOT, "os.disable_selinux", "true")
        assert omitted["changed"] is False
        assert omitted["omitted_defaults"] == [{"path": "os.disable_selinux", "value": True}]
        written = config_set(
            path,
            PROJECT_ROOT,
            "os.disable_selinux",
            "true",
            explicit_default=True,
        )
        assert written["changed"] is True
        assert _load(path)["os"]["disable_selinux"] is True


class TestMergeContract:
    def test_merge_recurses_and_unions_lists_at_global_host_and_custom_depth(self, tmp_path):
        """CFG-MERGE-002 CFG-MERGE-003 CFG-MERGE-004 CFG-MERGE-005."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
os:
  packages: [acl]
custom:
  labels: [one]
splunk_hosts:
  - name: sh
    roles: [search_head]
    os:
      packages: [java]
""",
        )
        fragment = tmp_path / "fragment.yml"
        fragment.write_text(
            """\
os:
  packages: [polkit, acl]
custom:
  labels: [two]
splunk_hosts:
  - name: sh
    roles: [deployer]
    shcluster: shc1
    os:
      packages: [unzip, java]
splunk_shclusters:
  - shc_name: shc1
""",
            encoding="utf-8",
        )
        result = config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        data = _load(path)
        assert result["changed"] is True
        assert data["os"]["packages"] == ["acl", "polkit"]
        assert data["custom"]["labels"] == ["one", "two"]
        assert data["splunk_hosts"][0]["roles"] == ["search_head", "deployer"]
        assert data["splunk_hosts"][0]["os"]["packages"] == ["java", "unzip"]
        changed_paths = {item["path"] for item in result["operations"]}
        assert "splunk_hosts[name=sh].roles" in changed_paths
        assert "splunk_hosts[name=sh].os.packages" in changed_paths

    def test_merge_skips_null_and_is_idempotent(self, tmp_path):
        """CFG-MERGE-002 CFG-MERGE-006 CFG-TXN-005."""
        path = _config(tmp_path)
        fragment = tmp_path / "fragment.yml"
        fragment.write_text("splunk_defaults:\nos:\n  packages: [acl]\n", encoding="utf-8")
        first = config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        mtime = path.stat().st_mtime_ns
        second = config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        assert first["warnings"] and second["changed"] is False
        assert path.stat().st_mtime_ns == mtime

    def test_merge_yaml_12_keeps_yes_as_string_and_json_works(self, tmp_path):
        """CFG-MERGE-001."""
        path = _config(tmp_path)
        fragment = tmp_path / "fragment.yml"
        fragment.write_text("custom:\n  answer: yes\n", encoding="utf-8")
        config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        assert _load(path)["custom"]["answer"] == "yes"
        json_fragment = tmp_path / "fragment.json"
        json_fragment.write_text('{"custom":{"number":2}}', encoding="utf-8")
        config_merge(path, PROJECT_ROOT, str(json_fragment), validate=False)
        assert _load(path)["custom"]["number"] == 2

    def test_merge_cli_takes_a_local_fragment_only_through_file(self, tmp_path):
        """CFG-MERGE-001."""
        env_dir = write_min_env(tmp_path / "env")
        _config(env_dir)
        fragment = tmp_path / "fragment.yml"
        fragment.write_text("os:\n  packages: [acl]\n", encoding="utf-8")
        env = min_env_vars(env_dir)
        positional = run_spa(
            ["--agent", "--start-dir", str(env_dir), "config", "merge", str(fragment), "--yes"],
            env=env,
        )
        assert positional.returncode == 2, positional.stdout
        assert "--file" in positional.stdout
        both = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "merge",
                "os-tools",
                "--file",
                str(fragment),
            ],
            env=env,
        )
        assert both.returncode == 2, both.stdout
        assert "not both" in both.stdout
        missing = run_spa(
            ["--agent", "--start-dir", str(env_dir), "config", "merge"],
            env=env,
        )
        assert missing.returncode == 2, missing.stdout
        assert "TEMPLATE" in missing.stdout
        accepted = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "merge",
                "--file",
                str(fragment),
                "--dry-run",
            ],
            env=env,
        )
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    def test_fragment_limits_and_duplicate_keys_fail_without_write(self, tmp_path):
        """CFG-MERGE-001 CFG-MERGE-002 CFG-TXN-004."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="1 MiB"):
            config_merge(
                path,
                PROJECT_ROOT,
                "-",
                stdin_text="custom:\n  value: " + ("x" * (1024 * 1024)),
                validate=False,
            )
        duplicate = tmp_path / "duplicate.yml"
        duplicate.write_text(
            "custom:\n  value: one\n  value: two\n", encoding="utf-8"
        )
        with pytest.raises(ConfigEditError, match="duplicate"):
            config_merge(path, PROJECT_ROOT, str(duplicate), validate=False)
        oversized = tmp_path / "oversized.yml"
        with oversized.open("wb") as handle:
            handle.truncate(8 * 1024 * 1024 + 1)
        with pytest.raises(ConfigEditError, match="8 MiB"):
            config_merge(path, PROJECT_ROOT, str(oversized), validate=False)
        assert path.read_bytes() == before

    def test_merge_nested_content_pack_items_by_identity(self, tmp_path):
        """CFG-MERGE-003 CFG-MERGE-004."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_app_deployment:
  apps:
    - name: DA-ITSI-ContentLibrary
      app_id: 5391
      content_pack_apps:
        - name: pack-one
          custom:
            existing: true
""",
        )
        fragment = tmp_path / "packs.yml"
        fragment.write_text(
            """\
splunk_app_deployment:
  apps:
    - app_id: 5391
      content_pack_apps:
        - name: pack-one
          custom:
            added: true
""",
            encoding="utf-8",
        )
        config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        packs = _load(path)["splunk_app_deployment"]["apps"][0]["content_pack_apps"]
        assert packs == [{"name": "pack-one", "custom": {"existing": True, "added": True}}]

    def test_merge_omits_defaults_and_fragment_comments(self, tmp_path):
        """CFG-PATH-006 CFG-MERGE-006."""
        path = _config(tmp_path)
        fragment = tmp_path / "defaults.yml"
        fragment.write_text(
            """\
# fragment comment must not be copied
os:
  disable_selinux: true
  packages: [acl]
""",
            encoding="utf-8",
        )
        result = config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        assert "disable_selinux" not in _load(path)["os"]
        assert result["omitted_defaults"] == [{"path": "os.disable_selinux", "value": True}]
        assert "# fragment comment" not in path.read_text(encoding="utf-8")

    def test_merge_unions_lists_in_provider_host_app_and_custom_scopes(self, tmp_path):
        """CFG-MERGE-004 CFG-MERGE-005."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
terraform:
  aws:
    security_group_names: [base]
os:
  ssh_keys: [global-a]
custom:
  objects: [{name: one, value: 1}]
splunk_hosts:
  - name: sh
    roles: [search_head]
    custom:
      flags: [one]
splunk_app_deployment:
  apps:
    - name: TA
      app_id: 833
      target_roles: [search_head]
      idxc_whitelist: [idxc1]
""",
        )
        fragment = tmp_path / "all-list-scopes.yml"
        fragment.write_text(
            """\
terraform:
  aws:
    security_group_names: [extra, base]
os:
  ssh_keys: [global-b]
custom:
  objects: [{name: one, value: 2}]
splunk_hosts:
  - name: sh
    roles: [deployer]
    custom:
      flags: [two]
splunk_app_deployment:
  apps:
    - app_id: 833
      target_roles: [indexer]
      idxc_whitelist: [idxc2]
""",
            encoding="utf-8",
        )
        config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        data = _load(path)
        assert data["terraform"]["aws"]["security_group_names"] == ["base", "extra"]
        assert data["os"]["ssh_keys"] == ["global-a", "global-b"]
        assert data["custom"]["objects"] == [
            {"name": "one", "value": 1},
            {"name": "one", "value": 2},
        ]
        host = data["splunk_hosts"][0]
        assert host["roles"] == ["search_head", "deployer"]
        assert host["custom"]["flags"] == ["one", "two"]
        app = data["splunk_app_deployment"]["apps"][0]
        assert app["target_roles"] == ["search_head", "indexer"]
        assert app["idxc_whitelist"] == ["idxc1", "idxc2"]

    def test_merge_deduplicates_scalar_lists_by_exact_type_and_value(self, tmp_path):
        """CFG-MERGE-004."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
custom:
  typed: [true]
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        fragment = tmp_path / "typed-scalars.yml"
        fragment.write_text("custom:\n  typed: [1, 1.0, true]\n", encoding="utf-8")
        config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        values = _load(path)["custom"]["typed"]
        assert [(type(value), value) for value in values] == [
            (bool, True),
            (int, 1),
            (float, 1.0),
        ]

    def test_set_keeps_a_scalar_license_when_a_fragment_adds_another(self, tmp_path):
        """CFG-MERGE-004. A filename set and a fragment list become one license list."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        fragment = tmp_path / "license-and-java.yml"
        fragment.write_text(
            """\
splunk_defaults:
  splunk_license_file:
    - Splunk_ITSI.lic
splunk_hosts:
  - name: lm
    roles: [license_manager, deployment_server, deployer]
    shcluster: shc1
""",
            encoding="utf-8",
        )
        config_set(
            path,
            PROJECT_ROOT,
            "splunk_defaults.splunk_license_file",
            "Splunk_Enterprise.lic",
            resolve_file=str(fragment),
            validate=False,
        )
        data = _load(path)
        assert data["splunk_defaults"]["splunk_license_file"] == [
            "Splunk_Enterprise.lic",
            "Splunk_ITSI.lic",
        ]
        assert data["splunk_hosts"][1]["name"] == "lm"
        assert data["splunk_hosts"][1]["roles"] == [
            "license_manager",
            "deployment_server",
            "deployer",
        ]

    def test_merge_deduplicates_deeply_equal_structured_items_across_yaml_types(
        self, tmp_path
    ):
        """CFG-MERGE-005 CFG-MERGE-006."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
custom:
  objects:
    - name: one
      nested: [true, 1]
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        fragment = tmp_path / "same-object.yml"
        fragment.write_text(
            "custom:\n  objects:\n    - name: one\n      nested: [true, 1]\n",
            encoding="utf-8",
        )
        before = path.read_bytes()
        result = config_merge(path, PROJECT_ROOT, str(fragment), validate=False)
        assert result["changed"] is False
        assert path.read_bytes() == before
        assert len(_load(path)["custom"]["objects"]) == 1

    @pytest.mark.parametrize(
        "fragment",
        sorted(
            [
                *PROJECT_ROOT.joinpath("examples", "topologies").glob("*.yml"),
                *PROJECT_ROOT.joinpath("examples", "providers").glob("*.yml"),
            ]
        ),
        ids=lambda path: "%s-%s" % (path.parent.name, path.stem),
    )
    def test_every_layout_example_merges_to_a_schema_valid_candidate(
        self, tmp_path, fragment
    ):
        """CFG-MERGE-006 CFG-TXN-002."""
        from spa.init import compose_example_config, dump_splunk_config

        path = tmp_path / "config" / "splunk_config.yml"
        path.parent.mkdir(parents=True)
        path.write_text(
            dump_splunk_config(
                compose_example_config(
                    PROJECT_ROOT,
                    topology_id="single_node",
                    provider_id="virtualbox",
                )
            ),
            encoding="utf-8",
        )
        result = config_merge(path, PROJECT_ROOT, str(fragment))
        assert result["validation"] == "ok"


class TestTransactionContract:
    @pytest.mark.parametrize("dry_run", [False, True])
    def test_lock_serializes_write_and_dry_run(self, tmp_path, dry_run):
        """CFG-TXN-001."""
        import spa.config_edit as editor

        path = _config(tmp_path)
        code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from spa.config_edit import config_set\n"
            "print('ready', flush=True)\n"
            "config_set(Path(sys.argv[1]), Path(sys.argv[2]), "
            "'os.time_zone', 'UTC', dry_run=(sys.argv[3] == 'true'), validate=False)\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "lib")
        with editor._locked(path):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(path),
                    str(PROJECT_ROOT),
                    str(dry_run).lower(),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            assert process.stdout.readline().strip() == "ready"
            assert process.poll() is None
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stdout + stderr

    def test_dry_run_is_faithful_and_does_not_write(self, tmp_path):
        """CFG-TXN-002 CFG-TXN-003."""
        path = _config(tmp_path)
        before = path.read_bytes()
        result = config_set(path, PROJECT_ROOT, "os.time_zone", "Europe/Berlin", dry_run=True)
        assert result["changed"] is True and result["operations"]
        assert path.read_bytes() == before

    def test_dry_run_and_write_have_identical_operations(self, tmp_path):
        """CFG-TXN-003."""
        dry_path = _config(tmp_path / "dry")
        write_path = _config(tmp_path / "write")
        dry = config_set(
            dry_path, PROJECT_ROOT, "os.time_zone", "UTC", dry_run=True
        )
        written = config_set(write_path, PROJECT_ROOT, "os.time_zone", "UTC")
        assert dry["operations"] == written["operations"]
        assert dry["diff"] == written["diff"]
        assert "+  time_zone: UTC" in dry["diff"]
        assert "revision_after" not in dry
        assert written["revision_after"] == config_get(
            write_path, PROJECT_ROOT
        )["revision"]

    def test_revision_conflict_precedes_mutation(self, tmp_path):
        """CFG-TXN-001."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="revision"):
            config_set(path, PROJECT_ROOT, "os.time_zone", "UTC", expect_revision="0" * 64)
        assert path.read_bytes() == before

    def test_invalid_candidate_rolls_back_and_symlink_is_refused(self, tmp_path):
        """CFG-TXN-004."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="validation"):
            config_set(path, PROJECT_ROOT, "splunk_hosts[name=sh].roles", "[]")
        assert path.read_bytes() == before
        link = tmp_path / "config" / "linked.yml"
        link.symlink_to(path)
        with pytest.raises(ConfigEditError, match="symlink"):
            config_set(link, PROJECT_ROOT, "os.time_zone", "UTC")

    def test_validation_fault_cleans_temp_and_preserves_mode(self, tmp_path, monkeypatch):
        """CFG-TXN-002 CFG-TXN-004 CFG-TXN-005."""
        import spa.config_edit as editor

        path = _config(tmp_path)
        path.chmod(0o640)
        before = path.read_bytes()

        def fail_validation(candidate, spa_home):
            raise ConfigEditError("injected validation failure")

        monkeypatch.setattr(editor, "_validate", fail_validation)
        with pytest.raises(ConfigEditError, match="injected"):
            config_set(path, PROJECT_ROOT, "os.time_zone", "UTC")
        assert path.read_bytes() == before
        assert not list(path.parent.glob(".splunk_config.yml.*.tmp"))

        monkeypatch.undo()
        config_set(path, PROJECT_ROOT, "os.time_zone", "UTC")
        assert path.stat().st_mode & 0o777 == 0o640


class TestLayoutContract:
    def test_canonical_order_puts_clustering_before_defaults(self):
        """CFG-LAYOUT-001."""
        from spa.catalog import CONFIG_AREAS

        roots = [root for _, _, area_roots in CONFIG_AREAS for root in area_roots]
        assert roots.index("splunk_shclusters") < roots.index("splunk_defaults")

    def test_provider_switch_replaces_only_provider_sections(self, tmp_path):
        """CFG-LAYOUT-002 CFG-LAYOUT-004."""
        path = _config(tmp_path)
        config_set(path, PROJECT_ROOT, "custom.keep", "value", validate=False)
        config_provider(path, PROJECT_ROOT, "aws")
        assert "terraform" in _load(path) and "virtualbox" not in _load(path)
        config_provider(path, PROJECT_ROOT, "virtualbox")
        data = _load(path)
        assert "virtualbox" in data and "terraform" not in data
        assert data["custom"]["keep"] == "value"

    def test_topology_switch_replaces_owned_sections_and_keeps_defaults(self, tmp_path):
        """CFG-LAYOUT-002 CFG-LAYOUT-003 CFG-LAYOUT-005."""
        path = _config(tmp_path)
        config_set(path, PROJECT_ROOT, "splunk_defaults.splunk_version", "9.4.0", validate=False)
        config_topology(path, PROJECT_ROOT, "cm_2idxc_sh_uf", validate=False)
        data = _load(path)
        assert data["splunk_defaults"]["splunk_version"] == "9.4.0"
        indexers = next(host for host in data["splunk_hosts"] if "indexer" in host["roles"])
        assert indexers["iter"]["numbers"] == "1..2"

    def test_topology_switch_to_single_node_removes_stale_cluster_roots(self, tmp_path):
        """CFG-LAYOUT-003."""
        path = _config(tmp_path)
        config_topology(path, PROJECT_ROOT, "cm_2idxc_sh_uf", validate=False)
        config_topology(path, PROJECT_ROOT, "single_node", validate=False)
        data = _load(path)
        assert "splunk_idxclusters" not in data
        assert "splunk_shclusters" not in data

    def test_layout_feature_ids_resolve_through_template(self, tmp_path):
        """CFG-LAYOUT-002."""
        path = _config(tmp_path)
        assert config_provider(path, PROJECT_ROOT, "provider.aws")["provider"] == "aws"
        assert config_topology(path, PROJECT_ROOT, "topology.c1", validate=False)["topology"] == "cm_2idxc_sh_uf"

    def test_all_clustered_topology_examples_use_iter_for_member_ranges(self):
        """CFG-LAYOUT-005."""
        data = _load(PROJECT_ROOT / "examples" / "topologies" / "ds_cm_2idxc1site_sh_hf_uf.yml")
        indexers = next(host for host in data["splunk_hosts"] if "indexer" in host["roles"])
        assert indexers["iter"] == {"prefix": "idx", "numbers": "1..2"}

    def test_written_config_separates_sections_and_list_items(self, tmp_path):
        """CFG-LAYOUT-006."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
os:
  packages:
    - acl
    - curl
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
splunk_hosts:
  - name: ds
    roles:
      - deployment_server
  # Search head
  - name: sh
    roles: [search_head]
  - iter:
      prefix: idx
      numbers: 1..2
    roles:
      - indexer
splunk_app_deployment:
  apps:
    - app_id: 742
      name: one
      content_pack_apps:
        - name: cp1
        - name: cp2
    - app_id: 833
      name: two
""",
        )
        config_set(path, PROJECT_ROOT, "splunk_defaults.splunk_version", "9.4.0", validate=False)
        expected = """\
plugin: splunk-platform-automator

os:
  packages:
  - acl
  - curl

splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
  splunk_version: 9.4.0

splunk_hosts:
- name: ds
  roles:
  - deployment_server

  # Search head
- name: sh
  roles: [search_head]

- iter:
    prefix: idx
    numbers: 1..2
  roles:
  - indexer

splunk_app_deployment:
  apps:
  - app_id: 742
    name: one
    content_pack_apps:
    - name: cp1
    - name: cp2

  - app_id: 833
    name: two
"""
        assert path.read_text(encoding="utf-8") == expected
        config_set(path, PROJECT_ROOT, "splunk_defaults.splunk_license_file", "x.lic", validate=False)
        text = path.read_text(encoding="utf-8")
        assert "\n\n\n" not in text
        assert "  splunk_version: 9.4.0\n  splunk_license_file: x.lic\n\nsplunk_hosts:" in text
        config_set(path, PROJECT_ROOT, "splunk_defaults.splunk_license_file", "x.lic", validate=False)
        assert path.read_text(encoding="utf-8") == text

    def test_composed_init_config_separates_sections_and_hosts(self):
        """CFG-LAYOUT-006."""
        from spa.init import dump_splunk_config

        text = dump_splunk_config(
            {
                "plugin": "splunk-platform-automator",
                "splunk_defaults": {"splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"},
                "splunk_hosts": [
                    {"name": "cm", "roles": ["cluster_manager", "license_manager"]},
                    {"name": "sh", "roles": ["search_head"]},
                ],
            }
        )
        assert "plugin: splunk-platform-automator\n\nsplunk_defaults:" in text
        assert "\n\nsplunk_hosts:\n- name: cm\n" in text
        assert "  - license_manager\n\n- name: sh\n" in text
        assert "  - cluster_manager\n  - license_manager\n" in text
        assert not text.endswith("\n\n")

    def test_spacing_and_comments_are_not_validated(self, tmp_path):
        """CFG-LAYOUT-006. Spacing is write formatting, not a schema rule."""
        plugin = str(PROJECT_ROOT / "ansible" / "plugins" / "inventory")
        if plugin not in sys.path:
            sys.path.insert(0, plugin)
        from schema import validate_config_file

        bodies = {
            "compact": """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
            "spaced": """\
plugin: splunk-platform-automator


# operator note

splunk_defaults:

  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"


splunk_hosts:

  # kept
  - name: sh

    roles: [search_head]
""",
        }
        for name, body in bodies.items():
            path = tmp_path / name / "splunk_config.yml"
            path.parent.mkdir()
            path.write_text(body, encoding="utf-8")
            before = path.read_bytes()
            loaded = validate_config_file(str(path))
            config_get(path, PROJECT_ROOT, "splunk_hosts")
            assert loaded.splunk_hosts[0].name == "sh"
            assert path.read_bytes() == before

        edited = tmp_path / "spaced" / "splunk_config.yml"
        config_set(edited, PROJECT_ROOT, "splunk_defaults.splunk_version", "9.4.0", validate=True)
        text = edited.read_text(encoding="utf-8")
        assert "# operator note" in text
        assert "# kept" in text
        assert "splunk_version: 9.4.0" in text


class TestAddContract:
    def test_add_appends_a_new_identity_and_injects_the_selector(self, tmp_path):
        """CFG-ADD-001."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(env_dir)
        before = path.read_bytes()
        preview = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_hosts[name=extra]",
                '{"roles":["search_head"]}',
                "--dry-run",
            ],
            env=min_env_vars(env_dir),
        )
        assert preview.returncode == 0, preview.stderr + preview.stdout
        assert path.read_bytes() == before
        result = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_hosts[name=extra]",
                '{"roles":["search_head"]}',
            ],
            env=min_env_vars(env_dir),
        )
        assert result.returncode == 0, result.stderr + result.stdout
        payload = json.loads(result.stdout)
        assert payload["data"]["changed"] is True
        hosts = _load(path)["splunk_hosts"]
        assert [host["name"] for host in hosts] == ["sh", "extra"]
        assert hosts[0]["roles"] == ["search_head"]
        assert re.search(r"- name: extra\n\s+roles:", path.read_text(encoding="utf-8"))
        value_file = tmp_path / "host.yml"
        value_file.write_text("roles: [search_head]\n", encoding="utf-8")
        added = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_hosts[name=fromfile]",
                "--value-file",
                str(value_file),
            ],
            env=min_env_vars(env_dir),
        )
        assert added.returncode == 0, added.stderr + added.stdout
        names = [host["name"] for host in _load(path)["splunk_hosts"]]
        assert names == ["sh", "extra", "fromfile"]

    def test_add_rejects_collisions_mismatches_and_bare_selectors(self, tmp_path):
        """CFG-ADD-002."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(env_dir)
        before = path.read_bytes()
        cases = (
            ("splunk_hosts[name=sh]", '{"roles":["search_head"]}', "already exists"),
            ("splunk_hosts[name=extra]", '{"name":"other","roles":["search_head"]}', "does not match"),
            ("splunk_hosts[]", '{"roles":["search_head"]}', "identity selector"),
            ("os.packages", "{}", "identity selector"),
            ("general[name=lab]", "{}", "identity list"),
            ("splunk_hosts[label=extra]", '{"roles":["search_head"]}', "identity must be one of"),
        )
        for selector, body, message in cases:
            result = run_spa(
                [
                    "--agent",
                    "--start-dir",
                    str(env_dir),
                    "config",
                    "add",
                    selector,
                    body,
                ],
                env=min_env_vars(env_dir),
            )
            assert result.returncode != 0, selector
            assert message in json.loads(result.stdout)["error"]
            assert path.read_bytes() == before

    def test_add_refuses_app_entries(self, tmp_path):
        """CFG-ADD-003."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(env_dir)
        before = path.read_bytes()
        result = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_app_deployment.apps[app_id=833]",
                '{"version":"latest"}',
            ],
            env=min_env_vars(env_dir),
        )
        payload = json.loads(result.stdout)
        assert result.returncode == 2
        assert payload["error"] == "App entries use spa apps add"
        assert "data" not in payload
        assert path.read_bytes() == before

    def test_add_secret_fields_require_an_environment_lookup(self, tmp_path):
        """CFG-ADD-004."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(env_dir)
        before = path.read_bytes()
        rejected = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_shclusters[shc_name=shc1]",
                '{"shc_password":"rejected-plaintext","shc_replication_port":9887}',
            ],
            env=min_env_vars(env_dir),
        )
        assert rejected.returncode == 1
        assert "lookup" in json.loads(rejected.stdout)["error"]
        assert "rejected-plaintext" not in rejected.stdout
        assert path.read_bytes() == before
        added = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_shclusters[shc_name=shc1]",
                '{"shc_replication_port":9887}',
                "--from-env",
                "shc_password",
                "SPLUNK_SHC_PASSWORD",
            ],
            env=min_env_vars(env_dir),
        )
        assert added.returncode == 0, added.stderr + added.stdout
        cluster = _load(path)["splunk_shclusters"][0]
        assert cluster["shc_name"] == "shc1"
        assert cluster["shc_password"] == "{{ lookup('env', 'SPLUNK_SHC_PASSWORD') }}"
        assert "rejected-plaintext" not in path.read_text(encoding="utf-8")
        wrong_field = run_spa(
            [
                "--agent",
                "--start-dir",
                str(env_dir),
                "config",
                "add",
                "splunk_hosts[name=extra]",
                '{"roles":["search_head"]}',
                "--from-env",
                "roles",
                "SPLUNK_ROLES",
            ],
            env=min_env_vars(env_dir),
        )
        assert wrong_field.returncode != 0
        assert "secret field" in json.loads(wrong_field.stdout)["error"]

    def test_every_configurable_feature_has_one_command(self):
        """CFG-ADD-005."""
        from spa.catalog import feature_class, feature_command, load_features, public_feature

        features = load_features(PROJECT_ROOT)
        supported = {"set", "add", "topology", "provider", "apps add"}
        saw_command = False
        for item in features:
            command = feature_command(item)
            public = public_feature(item, features)
            if feature_class(item) == "unsupported":
                assert command is None
                assert public["configurable"] is False
                continue
            saw_command = True
            assert set(command) == {"action", "path", "command"}
            assert command["action"] in supported
            assert command["command"].startswith("spa ")
            assert "\n" not in command["command"]
        by_selector = {
            str(item.get("selector") or item.get("id")): feature_command(item) for item in features
        }
        assert by_selector["splunk_hosts[].name"]["command"] == (
            "spa config add 'splunk_hosts[name=NAME]' JSON_OBJECT"
        )
        assert by_selector["splunk_idxclusters[].idxc_name"]["action"] == "add"
        assert by_selector["splunk_shclusters[].shc_name"]["action"] == "add"
        assert by_selector["splunk_app_deployment.apps[].app_id"]["action"] == "apps add"
        assert by_selector["topology.c1"]["action"] == "topology"
        assert by_selector["provider.aws"]["action"] == "provider"
        assert feature_command({"id": "note.example", "kind": "note", "title": "Not configurable"}) is None
        assert saw_command


class TestCommandContract:
    def test_human_unresolved_edit_prints_requirements_and_no_write(self, tmp_path):
        """CFG-DEP-003 CFG-TXN-003."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(
            env_dir,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: dep
    roles: [indexer]
""",
        )
        before = path.read_bytes()
        result = run_spa(
            [
                "--no-agent",
                "--start-dir",
                str(env_dir),
                "config",
                "set",
                "splunk_hosts[name=dep].roles",
                '["deployer"]',
                "--yes",
            ],
            env=min_env_vars(env_dir),
        )
        assert result.returncode == 0
        assert "unresolved" in result.stdout.lower()
        assert "Choose the search-head cluster" in result.stdout
        assert "--resolve" in result.stdout
        assert path.read_bytes() == before

    def test_agent_set_writes_without_yes_and_returns_compact_envelope(self, tmp_path):
        """CFG-CLI-001 CFG-CLI-002 CFG-CLI-003."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(env_dir)
        result = run_spa(
            ["--agent", "--start-dir", str(env_dir), "config", "set", "os.time_zone", "UTC"],
            env=min_env_vars(env_dir),
        )
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["ok"] is True and payload["data"]["changed"] is True
        assert "authored" not in payload["data"]
        assert _load(path)["os"]["time_zone"] == "UTC"

    def test_agent_get_without_path_is_outline_not_document(self, tmp_path):
        """CFG-CLI-004 CFG-PATH-005."""
        env_dir = write_min_env(tmp_path / "env")
        _config(env_dir)
        result = run_spa(
            ["--agent", "--start-dir", str(env_dir), "config", "get"],
            env=min_env_vars(env_dir),
        )
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["data"]["top_level_keys"] == [
            "plugin",
            "splunk_defaults",
            "splunk_hosts",
        ]
        assert "authored" not in payload["data"]

    def test_bare_config_is_usage_error(self, tmp_path):
        """CFG-CLI-001 CFG-CLI-002."""
        env_dir = write_min_env(tmp_path / "env")
        _config(env_dir)
        result = run_spa(
            ["--agent", "--start-dir", str(env_dir), "config"],
            env=min_env_vars(env_dir),
        )
        payload = json.loads(result.stdout)
        assert result.returncode == 2
        assert payload == {
            "ok": False,
            "schema_version": 1,
            "error": (
                "spa config needs an action.\n"
                "Look up a setting: spa config search QUERY\n"
                "Then:              spa config explain PATH\n"
                "Read current:      spa config get [PATH]\n"
                "Write:             set, add, unset, merge, topology, or provider\n"
                "Coverage:          spa config keys\n"
                "Docs dump:         spa config schema --markdown"
            ),
        }

    def test_templates_lists_shipped_fragments_without_environment(self):
        """CFG-CLI-001 CFG-MERGE-001."""
        result = run_spa(["--agent", "config", "templates"])
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["data"]["templates"] == [
            {
                "name": "os-tools",
                "summary": "Add common operating-system utility packages.",
            }
        ]

    def test_feature_catalog_has_templates_and_no_apply_contract(self):
        """CFG-CLI-004 CFG-LAYOUT-002."""
        from spa.catalog import load_features, public_feature, resolve_feature

        features = load_features(PROJECT_ROOT)
        topology = resolve_feature(features, "topology.c1")
        public = public_feature(topology, features, include_keys=True)
        assert public["template"] == "cm_2idxc_sh_uf"
        assert "apply" not in public
        assert all("merge" not in feature for feature in features)

    def test_app_mutation_schema_exposes_resolution_flags_and_truthful_roles_help(self):
        """CFG-CLI-001 CFG-DEP-004 CFG-APP-005."""
        from spa.agent import COMMAND_SCHEMA

        actions = {
            command["name"]: command for command in COMMAND_SCHEMA["commands"]
        }
        assert actions["config get"]["read_only"] is True
        for name in ("apps add", "apps remove"):
            flags = {flag["long"] for flag in actions[name]["flags"]}
            assert {"--resolve", "--resolve-file"} <= flags
        help_result = run_spa(["--no-agent", "apps", "snippet", "--help"])
        assert help_result.returncode == 0
        normalized_help = " ".join(help_result.stdout.split())
        assert "ignored for ITSI" not in normalized_help
        assert "rejected for ITSI" in normalized_help


class TestExplainContract:
    def test_explain_is_one_level_for_humans_and_agents(self):
        """CFG-CLI-005."""
        human = run_spa(["config", "explain", "splunk_hosts"])
        assert human.returncode == 0, human.stderr
        assert "IDENTITY" in human.stdout
        assert "WHEN:" in human.stdout
        assert human.stdout.splitlines()[0] == "PATH: splunk_hosts"
        agent = run_spa(["--agent", "config", "explain", "splunk_hosts"])
        payload = json.loads(agent.stdout)
        assert payload["ok"] is True
        assert [item["name"] for item in payload["data"]["identity"]["one_of"]] == [
            "name",
            "list",
            "iter",
        ]
        assert "roles" in [item["name"] for item in payload["data"]["fields"]]
        assert "scope" not in payload["data"]
        packages = json.loads(run_spa(["--agent", "config", "explain", "os.packages"]).stdout)
        assert packages["data"]["scope"] == {
            "applies_to": "all_hosts",
            "per_host_path": "splunk_hosts.os.packages",
            "behavior": "merge",
        }
        human_packages = run_spa(["config", "explain", "os.packages"])
        assert "SCOPE:" in human_packages.stdout
        assert "Per-host alternative: splunk_hosts.os.packages" in human_packages.stdout
        assert "Each host gets the global list plus its own items." in human_packages.stdout
        refused = run_spa(["--agent", "config", "schema", "--markdown"])
        error = json.loads(refused.stdout)
        assert refused.returncode == 2
        assert error["ok"] is False and "data" not in error

    def test_search_returns_paths_without_commands(self):
        """CFG-CLI-006."""
        result = run_spa(["--agent", "config", "search", "packages"])
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["data"]["total_matches"] >= 1
        assert len(payload["data"]["matches"]) <= 10
        assert {"path", "description"} == set(payload["data"]["matches"][0])
        by_path = {item["path"]: item["description"] for item in payload["data"]["matches"]}
        assert "All hosts" in by_path["os.packages"]
        assert "Per-host" in by_path["splunk_hosts.os.packages"]


class TestDependencyContract:
    def test_inline_resolution_refuses_literal_secret(self, tmp_path):
        """CFG-DEP-004 CFG-PATH-007 CFG-SEC-001."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="Secret paths require"):
            config_set(
                path,
                PROJECT_ROOT,
                "os.time_zone",
                "UTC",
                resolve=[
                    ["splunk_defaults.splunk_admin_password", "literal-secret"]
                ],
            )
        assert path.read_bytes() == before

    def test_inline_structured_resolution_refuses_nested_literal_secret(self, tmp_path):
        """CFG-DEP-004 CFG-PATH-007 CFG-SEC-001."""
        path = _config(tmp_path)
        before = path.read_bytes()
        with pytest.raises(ConfigEditError, match="environment lookup"):
            config_set(
                path,
                PROJECT_ROOT,
                "os.time_zone",
                "UTC",
                resolve=[
                    [
                        "splunk_hosts",
                        '[{"name":"sh","roles":["search_head"],'
                        '"splunk_admin_password":"literal-secret"}]',
                    ]
                ],
                validate=False,
            )
        assert path.read_bytes() == before

    def test_declarative_rule_registry_has_stable_unique_ids(self):
        """CFG-DEP-001."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        sys.path.insert(0, str(plugin))
        from schema import DEPENDENCY_RULES

        ids = [rule["id"] for rule in DEPENDENCY_RULES]
        assert len(ids) == len(set(ids))
        assert all(
            {
                "trigger",
                "required_facts",
                "repair",
                "unresolved",
                "error",
            } <= set(rule)
            for rule in DEPENDENCY_RULES
        )
        assert {
            "host.deployer.shcluster",
            "host.cluster_manager.idxcluster",
            "license_manager.license_file",
            "itsi.topology",
        } <= set(ids)

    def test_dependency_planner_reaches_fixpoint_after_scaffolding_cluster(self):
        """CFG-DEP-002."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        if str(plugin) not in sys.path:
            sys.path.insert(0, str(plugin))
        from schema import plan_config_dependencies

        candidate = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"]},
                {
                    "iter": {"prefix": "sh", "numbers": "1..3"},
                    "roles": ["search_head"],
                    "shcluster": "shc1",
                },
            ],
        }
        result = plan_config_dependencies(candidate)
        assert result["ready"] is True
        assert candidate["splunk_hosts"][0]["shcluster"] == "shc1"
        assert candidate["splunk_shclusters"] == [{"shc_name": "shc1"}]

    def test_dependency_planner_detects_repair_cycle(self, monkeypatch):
        """CFG-DEP-002."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        if str(plugin) not in sys.path:
            sys.path.insert(0, str(plugin))
        import schema

        def oscillating_pass(candidate):
            candidate["custom"]["toggle"] = not candidate["custom"]["toggle"]
            return {
                "ready": True,
                "requirements": [],
                "repairs": [
                    {
                        "op": "set",
                        "path": "custom.toggle",
                        "value": candidate["custom"]["toggle"],
                    }
                ],
            }

        monkeypatch.setattr(
            schema, "_plan_config_dependencies_pass", oscillating_pass
        )
        result = schema.plan_config_dependencies(
            {"plugin": "splunk-platform-automator", "custom": {"toggle": False}}
        )
        assert result["ready"] is False
        assert result["requirements"][0]["rule_id"] == "dependency.cycle"

    def test_dependency_rules_report_unmanaged_defined_clusters(self):
        """CFG-DEP-001 CFG-DEP-005."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        if str(plugin) not in sys.path:
            sys.path.insert(0, str(plugin))
        from schema import plan_config_dependencies

        result = plan_config_dependencies(
            {
                "plugin": "splunk-platform-automator",
                "splunk_hosts": [],
                "splunk_shclusters": [
                    {"shc_name": "shc1"},
                    {"shc_name": "shc2"},
                ],
                "splunk_idxclusters": [{"idxc_name": "idxc1"}],
            }
        )
        assert {
            (item["rule_id"], tuple(item["paths"]))
            for item in result["requirements"]
        } == {
            (
                "shcluster.deployer.required",
                ("splunk_shclusters[shc_name=shc1]", "splunk_hosts"),
            ),
            (
                "shcluster.deployer.required",
                ("splunk_shclusters[shc_name=shc2]", "splunk_hosts"),
            ),
            (
                "idxcluster.manager.required",
                ("splunk_idxclusters[idxc_name=idxc1]", "splunk_hosts"),
            ),
        }

    def test_final_validation_rejects_unpersisted_dependency_repairs(self):
        """CFG-DEP-001 CFG-DEP-002."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        if str(plugin) not in sys.path:
            sys.path.insert(0, str(plugin))
        from schema import ConfigValidationError, validate_config

        candidate = {
            "plugin": "splunk-platform-automator",
            "splunk_defaults": {
                "splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
            },
            "splunk_shclusters": [{"shc_name": "shc1"}],
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"]},
                {
                    "iter": {"prefix": "sh", "numbers": "1..3"},
                    "roles": ["search_head"],
                    "shcluster": "shc1",
                },
            ],
        }
        before = json.dumps(candidate, sort_keys=True)
        with pytest.raises(ConfigValidationError, match="shcluster"):
            validate_config(candidate)
        assert json.dumps(candidate, sort_keys=True) == before

    def test_unresolved_deployer_returns_requirements_without_partial_write(self, tmp_path):
        """CFG-DEP-002 CFG-DEP-003."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(
            env_dir,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: dep
    roles: [search_head]
""",
        )
        before = path.read_bytes()
        result = run_spa(
            [
                "--agent", "--start-dir", str(env_dir), "config", "set",
                "splunk_hosts[name=dep].roles", '["deployer"]',
            ],
            env=min_env_vars(env_dir),
        )
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["data"]["ready"] is False
        assert payload["data"]["changed"] is False
        assert payload["data"]["requirements"][0]["rule_id"] == "host.deployer.shcluster"
        assert path.read_bytes() == before

    def test_resolution_fragment_joins_original_operation_in_one_write(self, tmp_path):
        """CFG-DEP-002 CFG-DEP-004 CFG-DEP-005."""
        env_dir = write_min_env(tmp_path / "env")
        path = _config(
            env_dir,
            """\
plugin: splunk-platform-automator
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
splunk_hosts:
  - name: dep
    roles: [search_head]
""",
        )
        resolution = tmp_path / "shc.yml"
        resolution.write_text(
            """\
splunk_shclusters:
  - shc_name: shc1
splunk_hosts:
  - name: dep
    shcluster: shc1
  - iter:
      prefix: sh
      numbers: 1..3
    roles: [search_head]
    shcluster: shc1
""",
            encoding="utf-8",
        )
        result = run_spa(
            [
                "--agent", "--start-dir", str(env_dir), "config", "set",
                "splunk_hosts[name=dep].roles", '["deployer"]',
                "--resolve-file", str(resolution),
            ],
            env=min_env_vars(env_dir),
        )
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["data"]["ready"] is True and payload["data"]["changed"] is True
        data = _load(path)
        assert data["splunk_hosts"][0]["shcluster"] == "shc1"
        assert data["splunk_hosts"][1]["iter"]["numbers"] == "1..3"

    def test_license_manager_requires_external_license_resource(self, tmp_path):
        """CFG-DEP-003."""
        path = _config(tmp_path)
        result = config_set(
            path,
            PROJECT_ROOT,
            "splunk_hosts[name=sh].roles",
            '["license_manager"]',
        )
        assert result["ready"] is False
        assert result["requirements"][0]["kind"] == "external_resource"

    @pytest.mark.parametrize(
        ("cluster_key", "cluster_name_key", "manager_role", "member_role", "link_key", "minimum"),
        [
            ("splunk_shclusters", "shc_name", "deployer", "search_head", "shcluster", 3),
            ("splunk_idxclusters", "idxc_name", "cluster_manager", "indexer", "idxcluster", 2),
        ],
    )
    def test_final_validation_enforces_member_minimum_per_cluster(
        self,
        cluster_key,
        cluster_name_key,
        manager_role,
        member_role,
        link_key,
        minimum,
    ):
        """CFG-DEP-001 CFG-DEP-005."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        sys.path.insert(0, str(plugin))
        from schema import ConfigValidationError, validate_config

        hosts = []
        for cluster, member_count in (("one", minimum), ("two", 1)):
            hosts.append(
                {
                    "name": "%s-manager" % cluster,
                    "roles": [manager_role],
                    link_key: cluster,
                }
            )
            hosts.append(
                {
                    "iter": {"prefix": "%s-member" % cluster, "numbers": "1..%s" % member_count},
                    "roles": [member_role],
                    link_key: cluster,
                }
            )
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_defaults": {
                "splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
            },
            cluster_key: [{cluster_name_key: "one"}, {cluster_name_key: "two"}],
            "splunk_hosts": hosts,
        }
        with pytest.raises(ConfigValidationError, match="two"):
            validate_config(config)

    def test_itsi_dependency_reports_java_and_serverclass_requirements(self, tmp_path):
        """CFG-DEP-002 CFG-DEP-003."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: sh
    roles: [search_head]
  - name: idx
    roles: [indexer]
  - name: lm
    roles: [license_manager]
splunk_defaults:
  splunk_license_file: Enterprise.lic
splunk_app_deployment:
  apps:
    - name: Splunk IT Service Intelligence
      app_id: 1841
      premium_app: itsi
    - name: TA
      app_id: 833
      target_roles: [indexer]
      sc_whitelist: [linux]
""",
        )
        result = config_set(
            path,
            PROJECT_ROOT,
            "os.time_zone",
            "UTC",
        )
        rule_ids = {item["rule_id"] for item in result["requirements"]}
        assert {"itsi.java", "app.filter.serverclass"} <= rule_ids

    def test_dependency_planner_adds_itsi_before_evaluating_content_pack_closure(self):
        """CFG-DEP-002 CFG-APP-007."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        sys.path.insert(0, str(plugin))
        from schema import plan_config_dependencies

        candidate = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "sh", "roles": ["search_head"]}],
            "splunk_app_deployment": {
                "apps": [
                    {
                        "name": "DA-ITSI-CP-CUST-ATLAS-AWS-EBS",
                        "app_id": 7294,
                        "itsi_content_pack": True,
                    }
                ]
            },
        }
        planned = plan_config_dependencies(candidate)
        assert candidate["splunk_app_deployment"]["apps"][0]["app_id"] == 1841
        assert planned["repairs"][0]["value"]["app_id"] == 1841

    def test_final_validation_requires_a_manager_for_each_named_idxc(self):
        """CFG-DEP-001 CFG-DEP-005."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        sys.path.insert(0, str(plugin))
        from schema import ConfigValidationError, validate_config

        with pytest.raises(ConfigValidationError, match="idxc2"):
            validate_config(
                {
                    "plugin": "splunk-platform-automator",
                    "splunk_defaults": {
                        "splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
                    },
                    "splunk_idxclusters": [
                        {"idxc_name": "idxc1"},
                        {"idxc_name": "idxc2"},
                    ],
                    "splunk_hosts": [
                        {
                            "name": "cm1",
                            "roles": ["cluster_manager"],
                            "idxcluster": "idxc1",
                        },
                        {
                            "name": "cm2",
                            "roles": ["cluster_manager"],
                            "idxcluster": "idxc1",
                        },
                        {
                            "iter": {"prefix": "idx1-", "numbers": "1..2"},
                            "roles": ["indexer"],
                            "idxcluster": "idxc1",
                        },
                        {
                            "iter": {"prefix": "idx2-", "numbers": "1..2"},
                            "roles": ["indexer"],
                            "idxcluster": "idxc2",
                        },
                    ],
                }
            )

    def test_final_validation_consumes_shared_dependency_rules(self):
        """CFG-DEP-001."""
        import sys

        plugin = PROJECT_ROOT / "ansible" / "plugins" / "inventory"
        sys.path.insert(0, str(plugin))
        from schema import ConfigValidationError, validate_config

        with pytest.raises(ConfigValidationError, match="Java 21"):
            validate_config(
                {
                    "plugin": "splunk-platform-automator",
                    "splunk_defaults": {
                        "splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
                        "splunk_license_file": "Enterprise.lic",
                    },
                    "splunk_hosts": [
                        {"name": "sh", "roles": ["search_head"]},
                        {"name": "idx", "roles": ["indexer"]},
                        {"name": "lm", "roles": ["license_manager"]},
                    ],
                    "splunk_app_deployment": {
                        "apps": [
                            {
                                "name": "Splunk IT Service Intelligence",
                                "app_id": 1841,
                                "premium_app": "itsi",
                            }
                        ]
                    },
                }
            )


    def test_ambiguous_itsi_search_tier_preserves_bytes_until_one_filter(self, tmp_path):
        """CFG-APP-009 CFG-DEP-003."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
os:
  packages: [java-21-openjdk]
splunk_defaults:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
  splunk_license_file: [Enterprise.lic]
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"
splunk_shclusters:
  - shc_name: shc1
    shc_password: "{{ lookup('env', 'SPLUNK_SHC_PASSWORD') }}"
splunk_hosts:
  - name: cm
    roles: [cluster_manager, deployer, license_manager]
    idxcluster: idxc1
    shcluster: shc1
  - iter:
      prefix: idx
      numbers: 1..2
    roles: [indexer]
    idxcluster: idxc1
  - iter:
      prefix: sh
      numbers: 1..3
    roles: [search_head]
    shcluster: shc1
splunk_app_deployment:
  apps:
    - name: Splunk IT Service Intelligence
      app_id: 1841
      premium_app: itsi
""",
        )
        before = path.read_bytes()
        fragment = tmp_path / "shs.yml"
        fragment.write_text(
            """\
splunk_hosts:
  - name: shs
    roles: [search_head]
""",
            encoding="utf-8",
        )
        rejected = config_merge(path, PROJECT_ROOT, str(fragment))
        assert rejected["ready"] is False
        assert rejected["changed"] is False
        requirement = next(
            item for item in rejected["requirements"] if item["rule_id"] == "itsi.search_tier"
        )
        assert requirement["kind"] == "choice"
        assert requirement["allowed"] == ["shc1", "shs"]
        assert requirement["retry"] == (
            "--resolve 'splunk_app_deployment.apps[app_id=1841].shc_whitelist' '[\"shc1\"]'"
        )
        assert path.read_bytes() == before
        accepted = config_merge(
            path,
            PROJECT_ROOT,
            str(fragment),
            resolve=[(
                "splunk_app_deployment.apps[app_id=1841].shc_whitelist",
                '["shc1"]',
            )],
        )
        assert accepted["ready"] is True
        assert accepted["changed"] is True
        loaded = _load(path)
        assert loaded["splunk_app_deployment"]["apps"][0]["shc_whitelist"] == ["shc1"]
        assert any(host.get("name") == "shs" for host in loaded["splunk_hosts"])
        contract = (PROJECT_ROOT / "docs" / "config-editing.md").read_text(encoding="utf-8")
        assert "### CFG-APP-009 — singular ITSI search tier" in contract

class TestAppContract:
    @staticmethod
    def _client(app):
        class Client:
            def get(self, url, headers=None):
                return 200, json.dumps(app)

        return Client()

    def test_builder_omits_splunkbase_defaults_and_requires_ta_roles(self):
        """CFG-APP-001 CFG-APP-002 CFG-APP-004."""
        app = {
            "uid": 833,
            "appid": "Splunk_TA_nix",
            "title": "Splunk Add-on for Unix and Linux",
            "release": {"title": "10.3.4"},
        }
        built = build_entry(833, roles=["indexer"], client=self._client(app))
        assert built["entry"] == {
            "name": "Splunk_TA_nix",
            "app_id": 833,
            "target_roles": ["indexer"],
        }
        with pytest.raises(AppsError, match="--roles"):
            build_entry(833, client=self._client(app))

    def test_app_add_upserts_credentials_and_is_idempotent(self, tmp_path):
        """CFG-APP-002 CFG-APP-003 CFG-APP-008."""
        path = _config(tmp_path)
        entry = {"name": "Splunk_TA_nix", "app_id": 833, "target_roles": ["indexer"]}
        first = config_app_add(path, PROJECT_ROOT, entry, validate=False)
        mtime = path.stat().st_mtime_ns
        second = config_app_add(path, PROJECT_ROOT, entry, validate=False)
        deployment = _load(path)["splunk_app_deployment"]
        assert first["changed"] is True and second["changed"] is False
        assert path.stat().st_mtime_ns == mtime
        assert deployment["splunkbase_username"] == "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
        assert deployment["splunkbase_password"] == "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
        assert deployment["apps"] == [entry]

    def test_snippet_and_add_share_typed_schema_backed_set_fields(self):
        """CFG-APP-003 CFG-APP-004."""
        app = {
            "uid": 833,
            "appid": "Splunk_TA_nix",
            "title": "Splunk Add-on for Unix and Linux",
            "release": {"title": "10.3.4"},
        }
        built = snippet(
            833,
            roles=["indexer"],
            set_values=[["idxc_whitelist", '["idxc1"]']],
            client=self._client(app),
        )
        assert built["entry"]["idxc_whitelist"] == ["idxc1"]
        assert "idxc_whitelist:" in built["snippet"]
        with pytest.raises(AppsError, match="duplicates"):
            build_entry(
                833,
                roles=["indexer"],
                set_values=[["target_roles", '["search_head"]']],
                client=self._client(app),
            )

        omitted = build_entry(
            833,
            roles=["indexer"],
            set_values=[["state", "installed"]],
            client=self._client(app),
        )
        assert "state" not in omitted["entry"]
        assert omitted["omitted_defaults"] == [
            {"path": "state", "value": "installed"}
        ]
        explicit = build_entry(
            833,
            roles=["indexer"],
            set_values=[["state", "installed"]],
            explicit_default=True,
            client=self._client(app),
        )
        assert explicit["entry"]["state"] == "installed"

    def test_app_add_replaces_supplied_list_on_existing_entry(self, tmp_path):
        """CFG-APP-003 CFG-MERGE-004."""
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: idx
    roles: [indexer]
splunk_app_deployment:
  apps:
    - name: Splunk_TA_nix
      app_id: 833
      target_roles: [search_head, indexer]
      idxc_whitelist: [idxc1, idxc2]
""",
        )
        config_app_add(
            path,
            PROJECT_ROOT,
            {
                "name": "Splunk_TA_nix",
                "app_id": 833,
                "target_roles": ["indexer"],
                "idxc_whitelist": ["idxc2"],
            },
            validate=False,
        )
        app = _load(path)["splunk_app_deployment"]["apps"][0]
        assert app["target_roles"] == ["indexer"]
        assert app["idxc_whitelist"] == ["idxc2"]

    def test_app_add_and_remove_use_transaction_controls(self, tmp_path):
        """CFG-APP-008."""
        path = _config(tmp_path)
        before = path.read_bytes()
        entry = {
            "name": "Splunk_TA_nix",
            "app_id": 833,
            "target_roles": ["indexer"],
        }
        preview = config_app_add(
            path, PROJECT_ROOT, entry, dry_run=True, validate=False
        )
        assert preview["changed"] is True
        assert path.read_bytes() == before
        with pytest.raises(ConfigEditError, match="revision"):
            config_app_add(
                path,
                PROJECT_ROOT,
                entry,
                expect_revision="0" * 64,
                validate=False,
            )
        config_app_add(path, PROJECT_ROOT, entry, validate=False)
        authored = path.read_bytes()
        removal = config_app_remove(
            path,
            PROJECT_ROOT,
            "833",
            dry_run=True,
            validate=False,
        )
        assert removal["changed"] is True
        assert path.read_bytes() == authored

    def test_content_pack_adds_itsi_dependency_and_remove_pack_keeps_itsi(self, tmp_path):
        """CFG-APP-005 CFG-APP-006 CFG-APP-007."""
        path = _config(tmp_path)
        library = {
            "name": "DA-ITSI-ContentLibrary",
            "app_id": 5391,
            "itsi_content_pack": True,
            "content_pack_apps": [{"name": "DA-ITSI-CP-nix"}],
        }
        result = config_app_add(path, PROJECT_ROOT, library, validate=False)
        assert result["dependencies"] == [1841]
        apps = _load(path)["splunk_app_deployment"]["apps"]
        assert [app["app_id"] for app in apps] == [1841, 5391]
        config_app_remove(
            path,
            PROJECT_ROOT,
            "5391",
            content_pack="DA-ITSI-CP-nix",
            validate=False,
        )
        apps = _load(path)["splunk_app_deployment"]["apps"]
        assert any(app.get("app_id") == 1841 for app in apps)
        assert any(app.get("app_id") == 5391 for app in apps)

    def test_content_pack_kind_and_policy_combinations_are_enforced(self):
        """CFG-APP-005 CFG-APP-006."""
        library = {
            "uid": 5391,
            "appid": "DA-ITSI-ContentLibrary",
            "title": "Content Pack for Splunk App for Content Packs",
        }
        with pytest.raises(AppsError, match="requires"):
            build_entry(5391, client=self._client(library))
        with pytest.raises(AppsError, match="mutually exclusive"):
            build_entry(
                5391,
                content_packs=["pack-one"],
                install_all_content_packs=True,
                client=self._client(library),
            )
        pack = {
            "uid": 7294,
            "appid": "DA-ITSI-CP-CUST-ATLAS-AWS-EBS",
            "title": "Content Pack for AWS EBS",
        }
        built = build_entry(7294, client=self._client(pack))
        assert built["entry"]["content_pack_api"] == {
            "install_all": True,
            "enabled": True,
        }
        assert "target_roles" not in built["entry"]
        with pytest.raises(AppsError, match="--roles"):
            build_entry(7294, roles=["search_head"], client=self._client(pack))

    def test_existing_content_library_policy_cannot_be_switched(self, tmp_path):
        """CFG-APP-006."""
        path = _config(tmp_path)
        config_app_add(
            path,
            PROJECT_ROOT,
            {
                "name": "DA-ITSI-ContentLibrary",
                "app_id": 5391,
                "itsi_content_pack": True,
                "content_pack_api": {"install_all_apps": True},
            },
            validate=False,
        )
        with pytest.raises(ConfigEditError, match="other install policy"):
            config_app_add(
                path,
                PROJECT_ROOT,
                {
                    "name": "DA-ITSI-ContentLibrary",
                    "app_id": 5391,
                    "itsi_content_pack": True,
                    "content_pack_apps": [{"name": "pack-one"}],
                },
                validate=False,
            )

    def test_content_pack_dependency_closure_never_partially_writes(self, tmp_path):
        """CFG-APP-007 CFG-DEP-002 CFG-DEP-003."""
        path = _config(tmp_path)
        before = path.read_bytes()
        result = config_app_add(
            path,
            PROJECT_ROOT,
            {
                "name": "DA-ITSI-CP-CUST-ATLAS-AWS-EBS",
                "app_id": 7294,
                "itsi_content_pack": True,
                "content_pack_api": {"install_all": True, "enabled": True},
            },
        )
        assert result["ready"] is False
        assert result["dependencies"] == [1841]
        assert path.read_bytes() == before
        assert {"itsi.topology", "license_manager.license_file", "itsi.java"} & {
            item["rule_id"] for item in result["requirements"]
        }

    def test_content_pack_discovery_and_add_help_are_actionable(self, tmp_path):
        """CFG-APP-010."""
        archive = tmp_path / "library.tgz"
        with tarfile.open(archive, mode="w:gz") as bundle:
            payload = (
                b"[launcher]\nversion = 1.2.3\n"
                b"description = Unix infrastructure content.\n"
                b"[ui]\nlabel = Unix and Linux\n"
            )
            member = tarfile.TarInfo("DA-ITSI-CP-nix/default/app.conf")
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
        rows = inspect_content_pack_archive(archive, spa_home=PROJECT_ROOT)
        assert rows[0]["name"] == "DA-ITSI-CP-nix"
        assert rows[0]["command"].endswith(
            "--content-pack DA-ITSI-CP-nix --yes"
        )
        help_result = run_spa(["--no-agent", "apps", "add", "--help"])
        assert help_result.returncode == 0
        assert "spa apps content-packs list 5391" in help_result.stdout
        assert "does not deploy" in help_result.stdout


class TestSecurityContract:
    def test_explicit_env_lookup_requires_a_non_empty_value(self, tmp_path, monkeypatch):
        """CFG-SEC-003."""
        from spa.preflight import env_lookup_readiness, unresolved_env_message

        monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "sentinel-secret-value")
        monkeypatch.setenv("EMPTY_SECRET", "")
        monkeypatch.delenv("NESTED_TOKEN", raising=False)
        config = {
            "splunk_defaults": {
                "splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
                "literal_password": "kept-literal",
            },
            "custom": {"token": "{{ lookup('env', 'NESTED_TOKEN') }}"},
            "items": ["{{ lookup('env', 'EMPTY_SECRET') }}"],
        }
        assert env_lookup_readiness(config) == [
            {"name": "EMPTY_SECRET", "state": "not set"},
            {"name": "NESTED_TOKEN", "state": "not set"},
            {"name": "SPLUNK_ADMIN_PASSWORD", "state": "set"},
        ]
        message = unresolved_env_message(config)
        assert message == (
            "Environment variables required by splunk_config.yml are not set: "
            "EMPTY_SECRET, NESTED_TOKEN.\n"
            "Export each variable to a non-empty value and rerun the command."
        )
        assert "sentinel-secret-value" not in message
        assert "kept-literal" not in message
        contract = (PROJECT_ROOT / "docs" / "config-editing.md").read_text(encoding="utf-8")
        assert "### CFG-SEC-003 — required environment references" in contract

    def test_from_env_authors_lookup_while_variable_is_unset(self, tmp_path, monkeypatch):
        """CFG-SEC-003."""
        monkeypatch.delenv("SPLUNK_ADMIN_PASSWORD", raising=False)
        path = _config(
            tmp_path,
            """\
plugin: splunk-platform-automator
splunk_hosts:
  - name: sh
    roles: [search_head]
""",
        )
        before = path.read_bytes()
        result = config_set(
            path,
            PROJECT_ROOT,
            "splunk_defaults.splunk_admin_password",
            from_env="SPLUNK_ADMIN_PASSWORD",
        )
        assert result["changed"] is True
        assert path.read_bytes() != before
        assert "lookup('env', 'SPLUNK_ADMIN_PASSWORD')" in path.read_text(encoding="utf-8")

    def test_catalog_and_documentation_examples_are_credential_and_certificate_safe(self):
        """CFG-SEC-002."""
        from spa.catalog import load_features, validate_feature_catalog
        from spa.config_edit import _validate_fragment_secrets

        validate_feature_catalog(load_features(PROJECT_ROOT))
        yaml = YAML(typ="safe")
        for path in PROJECT_ROOT.joinpath("examples").rglob("*.yml"):
            _validate_fragment_secrets(yaml.load(path.read_text(encoding="utf-8")))
        texts = [
            path.read_text(encoding="utf-8")
            for path in [*PROJECT_ROOT.joinpath("docs").glob("*.md"), *PROJECT_ROOT.joinpath("examples").rglob("*.yml")]
        ]
        assert all("-----BEGIN CERTIFICATE-----" not in text for text in texts)
