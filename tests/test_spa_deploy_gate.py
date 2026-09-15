"""spa deploy refuses until every config host is in the provisioned inventory."""

import json
from dataclasses import replace

import pytest

from spa.api import LocalSpaSession
from spa.paths import resolve_spa_paths
from spa.providers import (
    check_provisioned,
    expected_hostnames,
    inventory_hostnames_from_file,
)
from spa_testutil import PROJECT_ROOT, run_spa

pytestmark = [pytest.mark.local, pytest.mark.cli]

AWS_TWO_HOSTS = """
terraform:
  aws:
    region: eu-central-1
splunk_hosts:
  - name: idx1
  - name: idx2
"""

AWS_ITER = """
terraform:
  aws:
    region: eu-central-1
splunk_hosts:
  - iter:
      prefix: idx
      numbers: 1..2
"""

STATE_WITH_RESOURCE = json.dumps({"resources": [{"type": "aws_instance"}]})


def _paths(tmp_path, config):
    config_path = tmp_path / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    return replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=tmp_path / "inventory",
        terraform_state_dir=tmp_path / "terraform" / "aws",
        roots_differ=True,
    )


def _write_state(paths, body=STATE_WITH_RESOURCE):
    paths.terraform_state_dir.mkdir(parents=True, exist_ok=True)
    (paths.terraform_state_dir / "terraform.tfstate").write_text(body)


def _write_inventory(paths, *names):
    paths.inventory_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# inventory"]
    for name in names:
        lines.append('%s ansible_host="example.invalid"' % name)
    (paths.inventory_dir / "hosts").write_text("\n".join(lines) + "\n")


def test_expected_hostnames_name_list_and_iter():
    assert expected_hostnames({"splunk_hosts": [{"name": "sh"}]}) == ["sh"]
    assert expected_hostnames({"splunk_hosts": [{"list": ["hf1", "hf2"]}]}) == ["hf1", "hf2"]
    assert expected_hostnames(
        {"splunk_hosts": [{"iter": {"prefix": "idx", "numbers": "1..2"}}]}
    ) == ["idx1", "idx2"]


def test_no_tfstate_is_not_provisioned(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    state = check_provisioned(paths)
    assert state.provisioned is False
    assert state.provider == "aws"
    assert "spa provision" in state.hint
    assert set(state.missing) == {"idx1", "idx2"}


def test_empty_resources_is_not_provisioned(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    _write_state(paths, json.dumps({"resources": []}))
    state = check_provisioned(paths)
    assert state.provisioned is False
    assert "no resources" in state.reason.lower()


def test_empty_inventory_lists_all_hosts(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    _write_state(paths)
    state = check_provisioned(paths)
    assert state.provisioned is False
    assert set(state.missing) == {"idx1", "idx2"}
    assert "idx1" in state.reason
    assert "idx2" in state.reason


def test_partial_inventory_is_not_provisioned(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    state = check_provisioned(paths)
    assert state.provisioned is False
    assert state.missing == ("idx2",)
    assert "idx2" in state.reason


def test_complete_inventory_is_provisioned(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2")
    state = check_provisioned(paths)
    assert state.provisioned is True
    assert state.missing == ()


def test_iter_hosts_require_every_expanded_name(tmp_path):
    paths = _paths(tmp_path, AWS_ITER)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    assert check_provisioned(paths).missing == ("idx2",)
    _write_inventory(paths, "idx1", "idx2")
    assert check_provisioned(paths).provisioned is True


def test_extra_inventory_host_does_not_block(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2", "uf1")
    assert check_provisioned(paths).provisioned is True
    assert "uf1" in inventory_hostnames_from_file(paths)


def test_virtualbox_and_legacy_aws_skip_the_gate(tmp_path):
    vbox = _paths(tmp_path / "vbox", "virtualbox:\n  memory: 4096\n")
    assert check_provisioned(vbox).provisioned is True
    legacy = _paths(tmp_path / "legacy", "aws:\n  region: eu-central-1\n")
    assert check_provisioned(legacy).provisioned is True


def test_missing_config_skips_the_gate(tmp_path):
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=tmp_path,
        config_file=tmp_path / "config" / "splunk_config.yml",
        inventory_dir=tmp_path / "inventory",
        terraform_state_dir=tmp_path / "terraform" / "aws",
        roots_differ=True,
    )
    assert check_provisioned(paths).provisioned is True


def _session_env(tmp_path, config=AWS_TWO_HOSTS):
    paths = _paths(tmp_path, config)
    return paths, LocalSpaSession(paths=paths)


def test_deploy_does_not_run_playbook_when_partial(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert not called
    assert result.data["missing"] == ["idx2"]
    assert "spa provision" in result.error
    assert "--allow-unprovisioned" in result.error


def test_deploy_allow_unprovisioned_runs_playbook(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    result = session.deploy(confirm=True, skip_provision_check=True)
    assert result.ok
    assert called
    assert result.data["provision_check_skipped"] is True
    assert result.data["missing"] == ["idx2"]


def test_allow_unprovisioned_without_yes_still_requires_confirmation(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    result = session.deploy(confirm=False, agent=True, skip_provision_check=True)
    assert result.ok is False
    assert not called
    assert "requires -y/--yes" in result.error


def test_cli_unprovisioned_aws_names_provision(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    result = run_spa(
        ["--no-agent", "deploy", "--yes"],
        extra_env={
            "SPA_HOME": str(PROJECT_ROOT),
            "SPA_ENV_DIR": str(tmp_path),
            "SPLUNK_CONFIG_FILE": str(paths.config_file),
        },
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "spa provision" in result.stderr
    assert "idx1" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_agent_unprovisioned_json(tmp_path):
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    result = run_spa(
        ["--agent", "deploy", "--yes"],
        extra_env={
            "SPA_HOME": str(PROJECT_ROOT),
            "SPA_ENV_DIR": str(tmp_path),
            "SPLUNK_CONFIG_FILE": str(paths.config_file),
        },
        cwd=tmp_path,
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["data"]["provisioned"] is False
    assert "idx1" in payload["data"]["missing"]
    assert "idx2" in payload["data"]["missing"]


def test_cli_allow_unprovisioned_invokes_playbook(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(tmp_path))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(paths.config_file))
    from spa.cli import main

    rc = main(["--no-agent", "deploy", "--yes", "--allow-unprovisioned"])
    assert rc == 0
    assert called


def test_help_and_schema_include_allow_unprovisioned():
    help_result = run_spa(["deploy", "--help"])
    assert help_result.returncode == 0
    assert "--allow-unprovisioned" in help_result.stdout
    schema = json.loads(run_spa(["agent", "schema"]).stdout)
    deploy = next(row for row in schema["data"]["commands"] if row["name"] == "deploy")
    flags = [item["long"] for item in deploy.get("flags") or []]
    assert "--allow-unprovisioned" in flags
