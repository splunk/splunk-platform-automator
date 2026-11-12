"""spa deploy refuses until every config host is in the provisioned inventory."""

import fcntl
import json
from dataclasses import replace
from pathlib import Path

import pytest

from spa.api import LocalSpaSession
from spa.paths import resolve_spa_paths
from spa.providers import (
    check_provisioned,
    expected_hostnames,
    inventory_hostnames_from_file,
)
from spa_testutil import PROJECT_ROOT, min_env_vars, run_spa, seed_software_dir

pytestmark = [pytest.mark.local, pytest.mark.cli]

AWS_TWO_HOSTS = """
plugin: splunk-platform-automator
schema_version: 1
terraform:
  aws:
    region: eu-central-1
splunk_hosts:
  - name: idx1
  - name: idx2
"""

AWS_ITER = """
plugin: splunk-platform-automator
schema_version: 1
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
    software = seed_software_dir(tmp_path)
    return replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=tmp_path / "inventory",
        terraform_state_dir=tmp_path / "terraform" / "aws",
        roots_differ=True,
        software_dir=software,
        baseconfig_dir=software,
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
    assert "spa deploy --yes" in state.hint
    assert set(state.missing) == {"idx1", "idx2"}
    text = state.message()
    assert text.startswith("hosts not provisioned: idx1, idx2")
    assert "provider: aws" in text
    assert "Run: spa deploy --yes" in text
    assert "Missing hosts:" not in text
    assert "terraform.tfstate" not in text
    assert "Terraform" not in text


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


def test_virtualbox_skips_the_gate(tmp_path):
    vbox = _paths(tmp_path / "vbox", "virtualbox:\n  memory: 4096\n")
    assert check_provisioned(vbox).provisioned is True


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


def _cli_env(paths):
    return {
        "SPA_HOME": str(PROJECT_ROOT),
        "SPA_ENV_DIR": str(paths.spa_env_dir),
        "SPLUNK_CONFIG_FILE": str(paths.config_file),
        "SPA_SOFTWARE_DIR": str(paths.software_dir),
        "SPA_BASECONFIG_DIR": str(paths.baseconfig_dir),
    }


def test_deploy_creates_missing_hosts_then_checks_then_deploys(tmp_path, monkeypatch):
    from spa.providers import ProvisionState

    order = []

    class FakeProvider:
        name = "aws"

        def provision(self, extra, **_kwargs):
            order.append("create")
            return 0

        def provision_state(self):
            return ProvisionState(
                provider="aws",
                provisioned=False,
                missing=("idx2",),
                hint="spa deploy --yes",
            )

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: order.append("check") or {"hosts": []},
    )
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: order.append("deploy") or 0,
    )
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: {
            "_meta": {"hostvars": {"idx1": {}, "idx2": {}}},
            "all": {"hosts": ["idx1", "idx2"]},
        },
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    result = session.deploy(confirm=True)
    assert result.ok
    assert order == ["create", "check", "deploy"]
    assert "--allow-unprovisioned" not in (result.error or "")


def test_deploy_failed_check_does_not_recreate_hosts(tmp_path, monkeypatch):
    from spa.hosts import HostsError

    created = []

    class FakeProvider:
        name = "aws"

        def provision(self, extra, **_kwargs):
            created.append(True)
            return 0

        def provision_state(self):
            from spa.providers import ProvisionState

            return ProvisionState(provider="aws", provisioned=True)

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: (_ for _ in ()).throw(HostsError("SSH failed for idx1.")),
    )
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("deploy must not run")),
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2")
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert created == []
    assert "SSH failed for idx1" in result.error


@pytest.mark.parametrize(
    "creates_hosts, ssh, expect_hint",
    [(True, False, True), (False, False, False), (True, True, False)],
)
def test_deploy_unreachable_hosts_suggest_resume(
    tmp_path, monkeypatch, creates_hosts, ssh, expect_hint
):
    from spa.hosts import HostsError
    from spa.providers import ProvisionState

    class FakeProvider:
        name = "aws"

        def provision_state(self):
            return ProvisionState(provider="aws", provisioned=True)

    FakeProvider.creates_hosts = creates_hosts
    rows = [{"name": "idx1", "ok": False, "ssh": ssh, "become": False, "message": "timed out"}]
    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: (_ for _ in ()).throw(HostsError("SSH failed for idx1.", rows)),
    )
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("deploy must not run")),
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2")
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert "SSH failed for idx1." in result.error
    assert ("spa resume --yes" in result.error) is expect_hint


def test_deploy_blocks_when_not_provisioned_and_nothing_to_create(tmp_path, monkeypatch):
    from spa.providers import ProvisionState

    class FakeProvider:
        name = "ccm"

        def provision(self, extra, **_kwargs):
            raise AssertionError("must not create hosts")

        def provision_state(self):
            return ProvisionState(
                provider="ccm",
                provisioned=False,
                reason="CCM terminated this deployment (TTL expiry or CCM terminate): d-1",
                hint="spa destroy --yes then spa deploy --yes",
            )

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("hosts check must not run")),
    )
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("deploy must not run")),
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2")
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert "CCM terminated this deployment" in result.error
    assert "spa destroy --yes then spa deploy --yes" in result.error


def test_deploy_confirm_names_create_and_deploy_when_hosts_missing(
    tmp_path, monkeypatch
):
    seen = []

    class FakeProvider:
        name = "aws"

        def provision(self, extra, **_kwargs):
            raise AssertionError("must not create before confirm")

        def provision_state(self):
            from spa.providers import ProvisionState

            return ProvisionState(
                provider="aws",
                provisioned=False,
                missing=("idx2",),
                hint="spa deploy --yes",
            )

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    result = session.deploy(confirm=False)
    assert result.ok is False
    assert seen
    prompt = seen[0].lower()
    assert "create" in prompt and "deploy" in prompt


def test_deploy_hosts_role_creates_missing_members_then_deploys(
    tmp_path, monkeypatch
):
    from spa.providers import ProvisionState

    order = []

    class FakeProvider:
        name = "aws"

        def provision(self, extra, **_kwargs):
            order.append("create")
            return 0

        def provision_state(self):
            return ProvisionState(
                provider="aws",
                provisioned=False,
                missing=("idx2",),
                hint="spa deploy --yes",
            )

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: order.append("check") or {"hosts": []},
    )
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: order.append("deploy") or 0,
    )
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: {
            "_meta": {"hostvars": {"idx1": {}, "idx2": {}, "sh1": {}}},
            "all": {"hosts": ["idx1", "idx2", "sh1"]},
            "role_indexer": {"hosts": ["idx1", "idx2"]},
            "role_search_head": {"hosts": ["sh1"]},
        },
    )
    config = """
plugin: splunk-platform-automator
schema_version: 1
terraform:
  aws:
    region: eu-central-1
splunk_hosts:
  - name: idx1
    roles: [indexer]
  - name: idx2
    roles: [indexer]
  - name: sh1
    roles: [search_head]
"""
    paths, session = _session_env(tmp_path, config)
    _write_state(paths)
    _write_inventory(paths, "idx1", "sh1")
    result = session.deploy(confirm=True, hosts=["indexer"])
    assert result.ok
    assert order == ["create", "check", "deploy"]


def test_deploy_named_host_runs_when_that_host_is_provisioned(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr("spa.hosts.ping_hosts", lambda *a, **k: {"hosts": []})
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: {"_meta": {"hostvars": {"idx1": {}}}, "all": {"hosts": ["idx1"]}},
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1")
    result = session.deploy(confirm=True, hosts=["idx1"])
    assert result.ok
    assert called
    assert "provision_check_skipped" not in result.data


def test_allow_unprovisioned_without_yes_still_requires_confirmation(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    paths, session = _session_env(tmp_path)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2")
    result = session.deploy(confirm=False, agent=True)
    assert result.ok is False
    assert not called
    assert "requires -y/--yes" in result.error


def test_deploy_fails_when_software_missing(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0
    )
    paths, session = _session_env(tmp_path)
    session = LocalSpaSession(
        paths=replace(paths, software_dir=tmp_path / "missing-sw", baseconfig_dir=tmp_path / "missing-sw")
    )
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert not called
    assert "Software directory not found" in result.error
    assert "spa init --software-dir" in result.error


def test_cli_unprovisioned_aws_creates_hosts(tmp_path, monkeypatch):
    from spa.providers import ProvisionState

    order = []

    class FakeProvider:
        name = "aws"

        def provision(self, extra, **_kwargs):
            order.append("create")
            return 0

        def provision_state(self):
            return ProvisionState(
                provider="aws",
                provisioned=False,
                missing=("idx1", "idx2"),
                hint="spa deploy --yes",
            )

    paths = _paths(tmp_path, AWS_TWO_HOSTS)
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(paths.spa_env_dir))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(paths.config_file))
    monkeypatch.setenv("SPA_SOFTWARE_DIR", str(paths.software_dir))
    monkeypatch.setenv("SPA_BASECONFIG_DIR", str(paths.baseconfig_dir))
    monkeypatch.setattr("spa.providers.get_provider", lambda _paths: FakeProvider())
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: order.append("check") or {"hosts": []},
    )
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.playbooks.run_playbook",
        lambda *a, **k: order.append("deploy") or 0,
    )
    from spa.cli import main

    rc = main(["--no-agent", "deploy", "--yes"])
    assert rc == 0
    assert order == ["create", "check", "deploy"]


def test_lifecycle_commands_block_each_other_until_the_process_ends(tmp_path):
    paths = resolve_spa_paths(environ={**min_env_vars(tmp_path)})
    lock_dir = Path(paths.spa_env_dir) / "logs"
    lock_dir.mkdir(parents=True)
    held = (lock_dir / ".lifecycle.lock").open("a+")
    held.write("provision\n")
    held.flush()
    fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    session = LocalSpaSession(paths=paths)
    for start in (session.deploy, session.provision, session.destroy):
        refused = start(confirm=True, agent=True)
        assert refused.to_dict() == {
            "ok": False,
            "schema_version": 1,
            "error": "A provision is already running.",
        }
    assert list(lock_dir.glob("*deploy*.jsonl")) == []
    held.close()
    from spa.runlog import claim_lifecycle_lock

    again = claim_lifecycle_lock(paths, "destroy")
    again.seek(0)
    assert again.read().strip() == "destroy"
    again.close()


def test_lifecycle_lock_is_refused_before_confirmation(tmp_path, monkeypatch):
    paths = resolve_spa_paths(environ={**min_env_vars(tmp_path)})
    lock_dir = Path(paths.spa_env_dir) / "logs"
    lock_dir.mkdir(parents=True)
    held = (lock_dir / ".lifecycle.lock").open("a+")
    held.write("deploy\n")
    held.flush()
    fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def fail_if_prompted(_prompt=""):
        raise AssertionError("prompted")

    monkeypatch.setattr("builtins.input", fail_if_prompted)
    session = LocalSpaSession(paths=paths)
    for start in (session.deploy, session.provision, session.destroy):
        without_yes = start(confirm=False, agent=False)
        with_yes = start(confirm=True, agent=True)
        for refused in (without_yes, with_yes):
            assert refused.to_dict() == {
                "ok": False,
                "schema_version": 1,
                "error": "A deploy is already running.",
            }
    held.close()


UNSTAMPED_AWS = """
plugin: splunk-platform-automator
terraform:
  aws:
    region: eu-central-1
splunk_hosts:
  - name: idx1
  - name: idx2
"""


def test_deploy_refuses_unstamped_config_before_playbook(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append("deploy") or 0
    )
    monkeypatch.setattr("spa.confirm.ensure_confirmed", lambda *a, **k: None)
    paths, session = _session_env(tmp_path, UNSTAMPED_AWS)
    _write_state(paths)
    _write_inventory(paths, "idx1", "idx2")
    before = paths.config_file.read_bytes()
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert "no schema_version" in result.error
    assert "version 1" in result.error
    assert "spa config migrate --yes" in result.error
    assert result.data is None
    assert not called
    assert paths.config_file.read_bytes() == before


def test_provision_refuses_unstamped_config_before_playbook(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "spa.playbooks.run_playbook", lambda *a, **k: called.append("provision") or 0
    )
    monkeypatch.setattr("spa.providers.get_provider", lambda *a, **k: called.append("provider"))
    monkeypatch.setattr("spa.confirm.ensure_confirmed", lambda *a, **k: None)
    paths, session = _session_env(tmp_path, UNSTAMPED_AWS)
    before = paths.config_file.read_bytes()
    result = session.provision(confirm=True)
    assert result.ok is False
    assert "no schema_version" in result.error
    assert "version 1" in result.error
    assert "spa config migrate --yes" in result.error
    assert result.data is None
    assert not called
    assert paths.config_file.read_bytes() == before


def test_help_and_schema_omit_allow_unprovisioned():
    help_result = run_spa(["deploy", "--help"])
    assert help_result.returncode == 0
    assert "--allow-unprovisioned" not in help_result.stdout
    schema = json.loads(run_spa(["agent", "schema"]).stdout)
    deploy = next(row for row in schema["data"]["commands"] if row["name"] == "deploy")
    flags = [item["long"] for item in deploy.get("flags") or []]
    assert "--allow-unprovisioned" not in flags
