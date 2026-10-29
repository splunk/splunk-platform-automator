"""Tests for spa init (env scaffold, migrate, --force vs config)."""

import os
from pathlib import Path

import pytest
import yaml

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_explicit_aws_provider_is_not_described_as_virtualbox():
    from spa.init import resolve_example_pair

    topology, provider = resolve_example_pair(
        PROJECT_ROOT, "cm_2idxc_3shc_ds", "aws"
    )
    assert topology == "cm_2idxc_3shc_ds"
    assert provider == "aws"


def test_init_example_accepts_topology_c1():
    from spa.init import resolve_example_pair

    stem, provider = resolve_example_pair(PROJECT_ROOT, "topology.c1", "aws")
    assert stem == "cm_2idxc_sh"
    assert provider == "aws"


def test_init_example_unknown_topology_id():
    from spa.init import InitError, resolve_example_pair

    with pytest.raises(InitError) as exc:
        resolve_example_pair(PROJECT_ROOT, "topology.nope", "aws")
    assert exc.value.code == 2


def test_catalog_id_composes_the_same_config_as_its_stem():
    from spa.init import compose_example_config, resolve_example_pair

    expected = {
        "topology.s1": "single_node",
        "topology.d1": "2idx_sh",
        "topology.d11": "2idx_sh_es",
        "topology.c1": "cm_2idxc_sh",
        "topology.c11": "cm_2idxc_sh_es",
        "topology.c3": "cm_2idxc_3shc_ds",
        "topology.c13": "cm_2idxc_2x3shc_ds",
        "topology.m2": "4idxc2site_2sh",
        "topology.m12": "4idxc2site_2sh_es",
        "topology.m3": "cm_4idxc2site_2x3shc_ds",
        "topology.m13": "cm_4idxc2site_4x3shc_ds",
        "topology.m14": "cm_4idxc2site_stretched_2x3shc_ds",
        "topology.m4": "cm_4idxc2site_stretched_3shc_ds",
    }
    for topology_id, stem in expected.items():
        resolved, provider = resolve_example_pair(PROJECT_ROOT, topology_id, "aws")
        assert resolved == stem
        assert compose_example_config(PROJECT_ROOT, resolved, provider) == compose_example_config(
            PROJECT_ROOT, stem, "aws"
        )


def test_init_topology_c1_writes_the_catalog_template(tmp_path):
    dest = tmp_path / "lab"
    result = run_spa_init(["--example", "topology.c1", "--provider", "aws", str(dest)])
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    names = [host.get("name") for host in cfg["splunk_hosts"] if "name" in host]
    assert "cm" in names
    assert "uf" not in names
    assert "terraform" in cfg and "aws" in cfg["terraform"]


def test_init_topology_d11_adds_an_es_search_head(tmp_path):
    dest = tmp_path / "d11"
    result = run_spa_init(["--example", "topology.d11", "--provider", "aws", str(dest)])
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    blob = str(cfg)
    assert "universal_forwarder" not in blob
    search_heads = [
        host for host in cfg["splunk_hosts"] if "search_head" in (host.get("roles") or [])
    ]
    assert any(str(host.get("name", "")).startswith("es") for host in search_heads)


def test_init_unknown_topology_does_not_create_an_env(tmp_path):
    dest = tmp_path / "nope"
    result = run_spa_init(["--example", "topology.nope", "--provider", "aws", str(dest)])
    assert result.returncode == 2
    assert not dest.exists()


def test_init_help():
    result = run_spa(["init", "--help"])
    assert result.returncode == 0
    assert "splunk_config.yml" in result.stdout


def test_init_provider_help_names_external():
    result = run_spa(["init", "--help"])
    assert result.returncode == 0
    assert "aws, virtualbox, or external" in result.stdout
    assert "aws or virtualbox" not in result.stdout


def test_init_list_examples():
    result = run_spa(["init", "list"])
    assert result.returncode == 0
    out = result.stdout
    assert "single_node" in out
    assert "cm_2idxc_sh" in out
    assert "topology.c1  cm_2idxc_sh" in out
    assert "topology.d11  2idx_sh_es" in out
    assert "virtualbox" in out
    assert "aws" in out
    assert "cm_2idxc_sh_aws.yml" not in out
    assert "--provider" in out


def test_scaffold_creates_env_without_ansible(tmp_path):
    dest = tmp_path / "my-env"
    result = run_spa_init(["--example", "single_node.yml", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert (dest / ".spa.yml").is_file()
    assert (dest / "inventory").is_dir()
    assert (dest / "inventory" / "hosts").is_file()
    assert not (dest / "terraform" / "aws").exists()
    assert not (dest / "saved_base_config_apps").exists()
    assert not (dest / "ansible").exists()
    assert "aws_ec2.yml" not in (result.stderr + result.stdout)

    spa_yml = yaml.safe_load((dest / ".spa.yml").read_text())
    assert spa_yml["spa_home"] == str(PROJECT_ROOT)
    clone_software = (PROJECT_ROOT / ".." / "Software").resolve()
    if clone_software.is_dir():
        assert Path(spa_yml["software_dir"]).resolve() == clone_software
        assert Path(spa_yml["baseconfig_dir"]).resolve() == clone_software
    clone_apps = (PROJECT_ROOT / "apps").resolve()
    sibling_apps = (PROJECT_ROOT / ".." / "apps").resolve()
    if sibling_apps.is_dir():
        assert Path(spa_yml["apps_dir"]).resolve() == sibling_apps
    elif clone_apps.is_dir():
        assert Path(spa_yml["apps_dir"]).resolve() == clone_apps

    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    assert cfg["plugin"] == "splunk-platform-automator"
    assert cfg["splunk_hosts"]


def test_example_flag(tmp_path):
    dest = tmp_path / "c1"
    result = run_spa_init(["--example", "cm_2idxc_sh", str(dest)])
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    names = [h.get("name") for h in cfg["splunk_hosts"] if "name" in h]
    assert "cm" in names
    assert "terraform" in cfg
    assert "virtualbox" not in cfg
    assert "os" not in cfg


def test_example_with_aws_provider(tmp_path):
    dest = tmp_path / "c1-aws"
    result = run_spa_init(["--example", "cm_2idxc_sh", "--provider", "aws", str(dest)])
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    assert "terraform" in cfg
    assert cfg["terraform"]["aws"]["region"]
    assert "virtualbox" not in cfg
    assert "os" not in cfg
    names = [h.get("name") for h in cfg["splunk_hosts"] if "name" in h]
    assert "cm" in names


def test_legacy_example_filename_is_rejected(tmp_path):
    dest = tmp_path / "legacy"
    result = run_spa_init(["--example", "cm_2idxc_sh_aws.yml", str(dest)])
    text = result.stderr + result.stdout
    assert result.returncode != 0
    assert "cm_2idxc_sh_aws" in text
    assert "Alias" not in text


def test_refuse_overwrite(tmp_path):
    dest = tmp_path / "exists"
    first = run_spa_init(["--example", "single_node.yml", str(dest)])
    assert first.returncode == 0
    second = run_spa_init(["--example", "single_node.yml", str(dest)])
    assert second.returncode != 0
    assert "already exists" in (second.stderr + second.stdout).lower()


def test_force_overwrite_with_example(tmp_path):
    dest = tmp_path / "exists"
    assert run_spa_init(["--example", "single_node.yml", str(dest)]).returncode == 0
    result = run_spa_init(["--force", "--example", "single_node.yml", str(dest)])
    assert result.returncode == 0, result.stderr


def test_force_without_example_keeps_config(tmp_path):
    dest = tmp_path / "exists"
    assert run_spa_init(["--example", "single_node.yml", str(dest)]).returncode == 0
    marker = "# keep-me-marker\n"
    cfg = dest / "config" / "splunk_config.yml"
    cfg.write_text(cfg.read_text() + marker)
    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert marker in cfg.read_text()
    leftover = dest / "inventory" / "group_vars"
    leftover.symlink_to(PROJECT_ROOT / "ansible" / "group_vars")
    again = run_spa_init(["--force", str(dest)])
    assert again.returncode == 0, again.stderr + again.stdout
    assert marker in cfg.read_text()
    assert not leftover.exists() and not leftover.is_symlink()


def test_force_removes_incomplete_env_venv(tmp_path):
    """An empty .venv holds no state and breaks every cd into the env."""
    dest = tmp_path / "exists"
    assert run_spa_init(["--example", "single_node.yml", str(dest)]).returncode == 0
    broken = dest / ".venv"
    (broken / "include").mkdir(parents=True)
    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert not broken.exists()


def test_force_keeps_complete_env_venv(tmp_path):
    """A usable venv is user state (pinned Ansible); --force must not delete it."""
    dest = tmp_path / "exists"
    assert run_spa_init(["--example", "single_node.yml", str(dest)]).returncode == 0
    venv = dest / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "activate").write_text("# pretend venv\n")
    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (venv / "bin" / "activate").is_file()


def test_refuse_spa_home():
    result = run_spa_init([str(PROJECT_ROOT)])
    assert result.returncode != 0
    assert "SPA_HOME" in (result.stderr + result.stdout)


def test_init_list_json_has_no_addons():
    import json

    result = run_spa(["--json", "init", "list"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    data = payload.get("data") or {}
    assert "topologies" in data
    assert "providers" in data
    assert "addons" not in data
    ids = [item["id"] for item in data["topologies"]] + [item["id"] for item in data["providers"]]
    joined = " ".join(ids)
    assert "single_node" in joined
    assert "aws" in joined
    catalog = {item["id"]: item["template"] for item in data["catalog"]}
    assert catalog["topology.c1"] == "cm_2idxc_sh"
    assert catalog["topology.m14"] == "cm_4idxc2site_stretched_2x3shc_ds"
    assert "itsi" not in joined
    assert "SmartStore" not in joined
    assert "apps" not in joined


def test_missing_example(tmp_path):
    result = run_spa_init(
        ["--example", "does-not-exist.yml", "--provider", "virtualbox", str(tmp_path / "x")]
    )
    assert result.returncode == 2
    text = (result.stderr + result.stdout).lower()
    assert "does-not-exist" in text
    assert "spa init list" in text
    assert "examples/topologies" not in text


def _write_old_env(root: Path, marker: str = "migrated-env") -> None:
    (root / "config").mkdir(parents=True)
    (root / "inventory").mkdir(parents=True)
    (root / "terraform" / "aws").mkdir(parents=True)
    (root / "config" / "splunk_config.yml").write_text(
        f"plugin: splunk-platform-automator\n# {marker}\n"
    )
    (root / "config" / "index.html").write_text("<html>hosts</html>\n")
    (root / "inventory" / "hosts").write_text("cm ansible_host=10.0.0.1\n")
    (root / "inventory" / "group_vars").symlink_to(PROJECT_ROOT / "ansible" / "group_vars")
    (root / "terraform" / "aws" / "terraform.tfstate").write_text('{"version": 4}\n')
    (root / "terraform" / "aws" / "terraform.tfvars").write_text("region = \"eu-central-1\"\n")
    (root / "terraform" / "aws" / "main.tf").write_text("# leftover module copy\n")
    (root / ".vagrant" / "machines" / "idx1").mkdir(parents=True)
    (root / ".vagrant" / "machines" / "idx1" / "id").write_text("vbox-id\n")


def test_auto_migrate_when_spa_home_has_config(tmp_path):
    source = tmp_path / "old-home"
    dest = tmp_path / "env"
    _write_old_env(source)
    result = run_spa_init([str(dest)], env={"SPA_HOME": str(source)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Migrating existing env" in (result.stderr + result.stdout)
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert not (source / "config" / "splunk_config.yml").exists()
    spa_yml = yaml.safe_load((dest / ".spa.yml").read_text())
    assert spa_yml["spa_home"] == str(source)


def test_migrate_from_existing_env(tmp_path):
    source = tmp_path / "old-clone"
    dest = tmp_path / "env"
    _write_old_env(source)
    (source / "ansible").mkdir()
    (source / "ansible" / "deploy_site.yml").write_text("# framework\n")

    result = run_spa_init(["--from", str(source), str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stderr + result.stdout
    assert "Migrating existing env" in out
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()
    assert (dest / "config" / "index.html").is_file()
    assert (dest / "inventory" / "hosts").read_text() == "cm ansible_host=10.0.0.1\n"
    assert not (dest / "inventory" / "group_vars").is_symlink()
    assert not (dest / "inventory" / "group_vars").exists()
    assert (dest / "terraform" / "aws" / "terraform.tfstate").is_file()
    assert (dest / "terraform" / "aws" / "terraform.tfvars").is_file()
    assert (dest / ".vagrant" / "machines" / "idx1" / "id").read_text() == "vbox-id\n"
    assert (dest / ".spa.yml").is_file()
    assert not (dest / "ansible").exists()
    spa_yml = yaml.safe_load((dest / ".spa.yml").read_text())
    assert spa_yml["spa_home"] == str(PROJECT_ROOT)

    dest_main = dest / "terraform" / "aws" / "main.tf"
    assert dest_main.is_symlink()
    assert dest_main.resolve() == (PROJECT_ROOT / "terraform" / "aws" / "main.tf").resolve()

    assert not (source / "config" / "splunk_config.yml").exists()
    assert not (source / "inventory" / "hosts").exists()
    assert not (source / "terraform" / "aws" / "terraform.tfstate").exists()
    assert not (source / ".vagrant").exists()
    assert (source / "ansible" / "deploy_site.yml").is_file()


def test_old_clone_warns_once_about_unused_aws_ec2(tmp_path):
    dest = tmp_path / "copied-clone"
    _write_old_env(dest)
    (dest / "ansible" / "roles").mkdir(parents=True)
    (dest / "config" / "aws_ec2.yml").write_text("# unused\n", encoding="utf-8")

    first = run_spa_init(["--force", str(dest)])
    assert first.returncode == 0, first.stderr + first.stdout
    assert "config/aws_ec2.yml is unused. Delete it." in (first.stderr + first.stdout)
    assert (dest / "config" / "aws_ec2.yml").is_file()

    second = run_spa_init(["--force", str(dest)])
    assert second.returncode == 0, second.stderr + second.stdout
    assert "aws_ec2.yml" not in (second.stderr + second.stdout)


def test_migrate_warns_about_unused_aws_ec2(tmp_path):
    source = tmp_path / "old-clone"
    dest = tmp_path / "env"
    _write_old_env(source)
    (source / "config" / "aws_ec2.yml").write_text("# unused\n", encoding="utf-8")

    result = run_spa_init(["--from", str(source), str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "config/aws_ec2.yml is unused. Delete it." in (result.stderr + result.stdout)
    assert (dest / "config" / "aws_ec2.yml").is_file()


def test_migrate_keep_source(tmp_path):
    source = tmp_path / "old-clone"
    dest = tmp_path / "env"
    _write_old_env(source)
    result = run_spa_init(["--from", str(source), "--keep-source", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert (source / "config" / "splunk_config.yml").is_file()
    assert (source / ".vagrant" / "machines" / "idx1" / "id").is_file()
    assert (dest / ".vagrant" / "machines" / "idx1" / "id").read_text() == "vbox-id\n"


def test_migrate_requires_config(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    result = run_spa_init(["--from", str(source), str(tmp_path / "env")])
    assert result.returncode != 0
    assert "nothing to migrate" in (result.stderr + result.stdout).lower()


def test_old_clone_without_force_exits_2(tmp_path):
    dest = tmp_path / "copied-clone"
    _write_old_env(dest)
    (dest / "ansible" / "roles").mkdir(parents=True)
    (dest / "bin").mkdir()
    (dest / "README.md").write_text("# old clone\n")
    (dest / "ansible.cfg").write_text("[defaults]\n")
    (dest / "pic").mkdir()
    (dest / ".gitignore").write_text("*.log\n")
    cfg_before = (dest / "config" / "splunk_config.yml").read_text()

    result = run_spa_init([str(dest)])
    assert result.returncode == 2
    report = result.stderr + result.stdout
    assert "old clone-style" in report.lower() or "clone-style" in report.lower()
    assert "pic" in report
    assert ".gitignore" in report
    assert (dest / "ansible").is_dir()
    assert (dest / "config" / "splunk_config.yml").read_text() == cfg_before


def test_old_clone_force_strips_keeps_config(tmp_path):
    dest = tmp_path / "copied-clone"
    _write_old_env(dest)
    (dest / "ansible" / "roles").mkdir(parents=True)
    (dest / "bin").mkdir()
    (dest / "README.md").write_text("# old clone\n")
    (dest / "ansible.cfg").write_text("[defaults]\n")

    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()
    assert (dest / "inventory" / "hosts").is_file()
    assert not (dest / "inventory" / "group_vars").exists()
    assert (dest / "terraform" / "aws" / "terraform.tfstate").is_file()
    assert (dest / ".spa.yml").is_file()
    assert not (dest / "ansible").exists()
    assert not (dest / "bin").exists()
    assert not (dest / "README.md").exists()
    assert not (dest / "ansible.cfg").exists()
    assert (dest / "terraform" / "aws" / "main.tf").is_symlink()


# Shipped paths spa init --force must strip, plus checkout-only leftovers.
# Synthetic names only: no vault contents, keys, certificates, or tokens.
_STRIP_FILES = (
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "RELEASE.md",
    "ROADMAP.md",
    "VERSION",
    "Vagrantfile",
    "ansible.cfg",
    "install.sh",
    "requirements.txt",
    "requirements.yml",
)
_STRIP_DIRS = (
    ".agent",
    "ansible",
    "bin",
    "defaults",
    "docs",
    "examples",
    "lib",
    "pic",
    "scripts",
    "skills",
    "template",
)
_CHECKOUT_FILES = (
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitattributes",
    ".gitmodules",
    "setup_ansible_remote.txt",
)
_CHECKOUT_DIRS = (".git", ".github", "tests", ".ansible")
_FRAMEWORK_BODY = "FRAMEWORK-README-BODY\n"


def _section_paths(text: str, heading: str) -> list:
    paths = []
    capturing = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == heading:
            capturing = True
            continue
        if not capturing:
            continue
        if stripped.endswith(":") and not line.startswith((" ", "\t")):
            break
        if not line.startswith((" ", "\t")):
            if stripped:
                break
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if stripped:
            paths.append(stripped)
    return paths


def _plant_file(root: Path, rel: str, body: str = "framework\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _plant_dir(root: Path, rel: str) -> None:
    path = root / rel
    path.mkdir(parents=True, exist_ok=True)
    (path / ".keep").write_text("framework\n", encoding="utf-8")


def _plant_full_checkout(root: Path) -> None:
    """Old clone shape: every shipped path, checkout leftovers, and env state."""
    _write_old_env(root)
    for rel in _STRIP_FILES:
        body = _FRAMEWORK_BODY if rel == "README.md" else "framework\n"
        _plant_file(root, rel, body)
    for rel in _STRIP_DIRS:
        _plant_dir(root, rel)
    _plant_dir(root, ".cursor/skills")
    _plant_file(root, ".cursor/plans/note.txt", "local-plan\n")
    for rel in _CHECKOUT_FILES:
        _plant_file(root, rel)
    for rel in _CHECKOUT_DIRS:
        _plant_dir(root, rel)
    (root / "saved_base_config_apps").mkdir(parents=True, exist_ok=True)
    (root / "saved_base_config_apps" / "kept.txt").write_text("kept-app\n", encoding="utf-8")
    (root / ".vault_pass").write_text("", encoding="utf-8")
    (root / ".vault_pass.txt").write_text("", encoding="utf-8")
    activate = root / ".venv" / "bin" / "activate"
    activate.parent.mkdir(parents=True, exist_ok=True)
    activate.write_text("old-activate\n", encoding="utf-8")
    tf = root / "terraform" / "aws"
    (tf / "README.md").write_text(_FRAMEWORK_BODY, encoding="utf-8")
    (tf / "custom.tf").write_text("# local copy\n", encoding="utf-8")
    (tf / "terraform.tfstate.backup").write_text("{}\n", encoding="utf-8")
    (tf / "tfplan").write_text("plan\n", encoding="utf-8")
    (tf / ".terraform.lock.hcl").write_text("# lock\n", encoding="utf-8")
    (tf / ".terraform").mkdir(exist_ok=True)
    (tf / ".terraform" / "providers").write_text("provider\n", encoding="utf-8")


def _tree_snapshot(root: Path) -> dict:
    snap = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            snap[rel] = ("link", os.readlink(path))
        elif path.is_file():
            snap[rel] = ("file", path.read_bytes())
        elif path.is_dir():
            snap[rel] = ("dir",)
    return snap


def test_force_strips_manifest_and_lists_retained(tmp_path):
    dest = tmp_path / "copied-clone"
    _plant_full_checkout(dest)

    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stdout + result.stderr
    assert _FRAMEWORK_BODY not in out
    assert "migrated-env" not in out
    assert "kept-app" not in out

    removed = _section_paths(out, "Removed:")
    retained = _section_paths(out, "Retained:")
    for rel in _STRIP_FILES + _STRIP_DIRS + _CHECKOUT_FILES + _CHECKOUT_DIRS:
        assert not (dest / rel).exists(), rel
        assert rel in removed, rel
    assert not (dest / ".cursor" / "skills").exists()
    assert ".cursor/skills" in removed
    assert ".cursor" not in removed
    assert (dest / ".cursor" / "plans" / "note.txt").read_text() == "local-plan\n"
    assert ".cursor/plans" in retained

    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()
    assert (dest / "inventory" / "hosts").read_text() == "cm ansible_host=10.0.0.1\n"
    assert not (dest / "inventory" / "group_vars").exists()
    assert "inventory/group_vars" in removed
    for name in (
        "config",
        "inventory",
        "saved_base_config_apps",
        ".vagrant",
        ".vault_pass",
        ".vault_pass.txt",
        ".venv",
        "terraform/aws/terraform.tfstate",
        "terraform/aws/terraform.tfvars",
        "terraform/aws/terraform.tfstate.backup",
        "terraform/aws/tfplan",
        "terraform/aws/.terraform.lock.hcl",
        "terraform/aws/.terraform",
    ):
        assert (dest / name).exists(), name
        assert name in retained, name
    assert (dest / "saved_base_config_apps" / "kept.txt").read_text() == "kept-app\n"
    assert (dest / ".vault_pass").read_text() == ""
    assert (dest / ".venv" / "bin" / "activate").read_text() == "old-activate\n"
    assert not (dest / "terraform" / "aws" / "README.md").exists()
    assert not (dest / "terraform" / "aws" / "custom.tf").exists()
    assert "terraform/aws/README.md" in removed
    assert "terraform/aws/custom.tf" in removed
    for tf in (PROJECT_ROOT / "terraform" / "aws").glob("*.tf"):
        link = dest / "terraform" / "aws" / tf.name
        assert link.is_symlink(), tf.name
        assert link.resolve() == tf.resolve()
    assert (dest / ".spa.yml").is_file()


def test_force_refresh_keeps_files_after_ansible_is_gone(tmp_path):
    """A converted env (no ansible/) is refreshed, not stripped, by a later --force."""
    dest = tmp_path / "env"
    _write_old_env(dest)
    (dest / ".spa.yml").write_text("spa_home: %s\n" % PROJECT_ROOT, encoding="utf-8")
    (dest / "pic").mkdir()
    (dest / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    (dest / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (dest / "setup_ansible_remote.txt").write_text("retired\n", encoding="utf-8")
    (dest / ".ansible" / "roles").mkdir(parents=True)
    (dest / "requirements.txt").write_text("env-local-reqs\n", encoding="utf-8")

    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "pic").is_dir()
    assert (dest / "VERSION").read_text() == "9.9.9\n"
    assert (dest / ".gitignore").read_text() == "*.log\n"
    assert (dest / "setup_ansible_remote.txt").read_text() == "retired\n"
    assert (dest / ".ansible" / "roles").is_dir()
    assert (dest / "requirements.txt").read_text() == "env-local-reqs\n"
    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()


def test_force_rerun_keeps_converted_tree(tmp_path):
    dest = tmp_path / "copied-clone"
    _plant_full_checkout(dest)
    first = run_spa_init(["--force", str(dest)])
    assert first.returncode == 0, first.stderr + first.stdout
    assert not (dest / "pic").exists()
    (dest / "requirements.txt").write_text("env-local-reqs\n", encoding="utf-8")
    before = _tree_snapshot(dest)

    second = run_spa_init(["--force", str(dest)])
    assert second.returncode == 0, second.stderr + second.stdout
    assert _tree_snapshot(dest) == before
    assert (dest / "requirements.txt").read_text() == "env-local-reqs\n"


def test_from_moves_state_and_leaves_framework(tmp_path):
    source = tmp_path / "old-clone"
    dest = tmp_path / "env"
    _plant_full_checkout(source)

    result = run_spa_init(["--from", str(source), str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()
    assert (dest / "inventory" / "hosts").is_file()
    assert (dest / "terraform" / "aws" / "terraform.tfstate").is_file()
    assert (dest / ".vagrant" / "machines" / "idx1" / "id").is_file()
    for rel in ("ansible", "pic", ".gitignore", "VERSION", "install.sh", "tests", ".git"):
        assert not (dest / rel).exists(), rel
        assert (source / rel).exists(), rel
    assert not (source / "config" / "splunk_config.yml").exists()
    assert not (source / "inventory" / "hosts").exists()
    assert not (source / "terraform" / "aws" / "terraform.tfstate").exists()
    assert not (source / ".vagrant").exists()
    assert (source / "saved_base_config_apps" / "kept.txt").read_text() == "kept-app\n"
    assert not (dest / "saved_base_config_apps").exists()
    assert (source / ".venv" / "bin" / "activate").read_text() == "old-activate\n"
    dest_activate = dest / ".venv" / "bin" / "activate"
    if dest_activate.is_file():
        assert dest_activate.read_text() != "old-activate\n"


def test_from_keep_source_leaves_old_unchanged(tmp_path):
    source = tmp_path / "old-clone"
    dest = tmp_path / "env"
    _plant_full_checkout(source)
    before = _tree_snapshot(source)

    result = run_spa_init(["--from", str(source), "--keep-source", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert _tree_snapshot(source) == before
    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()
    assert not (dest / "pic").exists()
    assert not (dest / "ansible").exists()


def test_force_unlinks_framework_symlink(tmp_path):
    dest = tmp_path / "copied-clone"
    outside = tmp_path / "outside-pic"
    outside.mkdir()
    (outside / "stay.txt").write_text("outside\n", encoding="utf-8")
    _write_old_env(dest)
    (dest / "ansible").mkdir()
    (dest / "pic").symlink_to(outside)

    result = run_spa_init(["--force", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (dest / "pic").exists()
    assert not (dest / "pic").is_symlink()
    assert (outside / "stay.txt").read_text() == "outside\n"


def test_framework_manifest_matches_actions():
    from spa.framework_paths import (
        CHECKOUT_ONLY_LEFTOVERS,
        framework_actions,
        load_framework_manifest,
    )

    manifest = set(load_framework_manifest(PROJECT_ROOT))
    assert manifest == set(framework_actions())
    assert set(CHECKOUT_ONLY_LEFTOVERS).isdisjoint(manifest)


def test_removal_plan_does_not_mutate(tmp_path):
    from spa.framework_paths import removal_plan

    dest = tmp_path / "copied-clone"
    _plant_full_checkout(dest)
    before = _tree_snapshot(dest)
    plan = removal_plan(dest, PROJECT_ROOT)
    assert _tree_snapshot(dest) == before
    assert "pic" in plan.remove
    assert ".cursor/skills" in plan.remove
    assert ".cursor" not in plan.remove
    assert plan.relink is True
    assert "config" in plan.retain


def test_strip_missing_manifest_leaves_tree(tmp_path):
    from spa.init import InitError, strip_framework

    dest = tmp_path / "copied-clone"
    home = tmp_path / "home"
    dest.mkdir()
    home.mkdir()
    (dest / "ansible").mkdir()
    (dest / "ansible" / "keep.yml").write_text("keep\n", encoding="utf-8")
    with pytest.raises(InitError, match="manifest"):
        strip_framework(dest, home)
    assert (dest / "ansible" / "keep.yml").read_text() == "keep\n"


def test_strip_refuses_spa_home(tmp_path):
    from spa.init import InitError, strip_framework

    home = tmp_path / "home"
    (home / "scripts").mkdir(parents=True)
    (home / "scripts" / "framework-files.txt").write_text("ansible\npic\n", encoding="utf-8")
    (home / "ansible").mkdir()
    (home / "ansible" / "keep.yml").write_text("keep\n", encoding="utf-8")
    (home / "pic").mkdir()
    with pytest.raises(InitError, match="SPA_HOME"):
        strip_framework(home, home)
    assert (home / "ansible" / "keep.yml").read_text() == "keep\n"
    assert (home / "pic").is_dir()


def test_example_and_migrate_conflict(tmp_path):
    result = run_spa_init(
        ["--example", "single_node.yml", "--migrate", str(tmp_path / "env")]
    )
    assert result.returncode != 0
    assert "not both" in (result.stderr + result.stdout).lower()


def test_refuse_same_source_and_dest(tmp_path):
    source = tmp_path / "old"
    _write_old_env(source)
    result = run_spa_init(["--from", str(source), str(source)])
    assert result.returncode != 0
    assert "same path" in (result.stderr + result.stdout).lower()


def test_init_uses_existing_shared_venv(tmp_path):
    shared = PROJECT_ROOT / ".venv" / "bin" / "activate"
    if not shared.is_file():
        pytest.skip("shared venv not present")
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stderr + result.stdout
    assert "venv:" in out
    assert "(existing)" in out
    assert "Creating Python venv" not in out


def test_ansible_pin_passed_to_venv(tmp_path, monkeypatch):
    calls = []

    def fake_call(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr("spa.init.subprocess.check_call", fake_call)
    monkeypatch.setattr("spa.init.run_doctor", lambda *a, **k: None)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from spa.init import init_env

    dest = tmp_path / "pinned"
    rc = init_env(
        dest,
        PROJECT_ROOT,
        example="single_node.yml",
        example_set=True,
        provider="aws",
        env_venv=True,
        ansible="2.17.8",
        skip_doctor=True,
        rebuild_venv=True,
    )
    assert rc == 0
    joined = " ".join(" ".join(c) for c in calls)
    assert "ansible==2.17.8" in joined
    assert str(dest / ".venv") in joined
    save_app = PROJECT_ROOT / "ansible" / "roles" / "baseconfig_app" / "tasks" / "save_app.yml"
    save_sc = (
        PROJECT_ROOT / "ansible" / "roles" / "deployment_server" / "tasks" / "save_serverclass.yml"
    )
    defaults = yaml.safe_load((PROJECT_ROOT / "defaults" / "splunk_apps.yml").read_text())
    assert defaults["splunk_apps"]["splunk_save_baseconfig_apps_dir"] == "saved_base_config_apps"
    for path in (save_app, save_sc):
        text = path.read_text()
        assert "spa_saved_baseconfig_apps_dir" in text
        assert "../{{" not in text
        assert "../{{splunk_save_baseconfig_apps_dir" not in text


def test_init_software_dir_writes_user_and_env_yml(tmp_path):
    dest = tmp_path / "env"
    dest2 = tmp_path / "env2"
    software = tmp_path / "Software"
    software.mkdir()
    xdg = tmp_path / "xdg-config"
    home = tmp_path / "home"
    home.mkdir()
    isolated = {"HOME": str(home), "XDG_CONFIG_HOME": str(xdg)}
    result = run_spa_init(
        ["--example", "single_node.yml", "--software-dir", str(software), str(dest)],
        env=isolated,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    user = yaml.safe_load((xdg / "spa" / "paths.yml").read_text())
    spa_yml = yaml.safe_load((dest / ".spa.yml").read_text())
    assert Path(user["software_dir"]).resolve() == software.resolve()
    assert Path(user["baseconfig_dir"]).resolve() == software.resolve()
    assert Path(spa_yml["software_dir"]).resolve() == software.resolve()
    second = run_spa_init(["--example", "single_node.yml", str(dest2)], env=isolated)
    assert second.returncode == 0, second.stderr + second.stdout
    spa2 = yaml.safe_load((dest2 / ".spa.yml").read_text())
    assert Path(spa2["software_dir"]).resolve() == software.resolve()


def _role_count(hosts, role):
    total = 0
    for host in hosts:
        if role not in (host.get("roles") or []):
            continue
        numbers = (host.get("iter") or {}).get("numbers")
        if numbers and ".." in str(numbers):
            start, end = str(numbers).split("..")
            total += int(end) - int(start) + 1
        else:
            total += 1
    return total


def _composed(stem):
    from spa.init import compose_example_config

    return compose_example_config(PROJECT_ROOT, stem, "aws")


def test_catalog_topologies_match_sva_shape():
    text = (PROJECT_ROOT / "examples" / "catalog" / "features.yml").read_text()
    # Stems are the catalog template values after this task. Compose the stem.
    expected = {
        "single_node": "s1",
        "2idx_sh": "d1",
        "2idx_sh_es": "d11",
        "cm_2idxc_sh": "c1",
        "cm_2idxc_sh_es": "c11",
        "cm_2idxc_3shc_ds": "c3",
        "cm_2idxc_2x3shc_ds": "c13",
        "4idxc2site_2sh": "m2",
        "4idxc2site_2sh_es": "m12",
        "cm_4idxc2site_2x3shc_ds": "m3",
        "cm_4idxc2site_4x3shc_ds": "m13",
        "cm_4idxc2site_stretched_2x3shc_ds": "m14",
        "cm_4idxc2site_stretched_3shc_ds": "m4",
    }
    for stem in expected:
        config = _composed(stem)
        blob = str(config)
        assert "universal_forwarder" not in blob
        assert "storageType" not in blob
        assert "s3://" not in blob
        assert "remotePath" not in blob
        hosts = config["splunk_hosts"]
        if stem == "single_node":
            assert _role_count(hosts, "indexer") == 1
            assert _role_count(hosts, "search_head") == 1
            assert "splunk_idxclusters" not in config
        elif stem == "2idx_sh":
            assert _role_count(hosts, "indexer") == 2
            assert _role_count(hosts, "search_head") == 1
            assert "splunk_idxclusters" not in config
        elif stem == "2idx_sh_es":
            assert _role_count(hosts, "indexer") == 2
            assert _role_count(hosts, "search_head") == 2
            assert "splunk_idxclusters" not in config
        elif stem == "cm_2idxc_sh":
            assert _role_count(hosts, "cluster_manager") == 1
            assert _role_count(hosts, "indexer") == 2
            assert _role_count(hosts, "search_head") == 1
            assert config["splunk_idxclusters"][0]["idxc_rf"] == 2
            assert "idxc_site_rf" not in config["splunk_idxclusters"][0]
            assert "splunk_shclusters" not in config
        elif stem == "cm_2idxc_sh_es":
            assert _role_count(hosts, "search_head") == 2
            assert "splunk_shclusters" not in config
        elif stem == "cm_2idxc_3shc_ds":
            assert _role_count(hosts, "indexer") == 2
            assert _role_count(hosts, "search_head") == 3
            assert _role_count(hosts, "deployer") == 1
            assert config["splunk_idxclusters"][0]["idxc_rf"] == 2
            assert len(config["splunk_shclusters"]) == 1
        elif stem == "cm_2idxc_2x3shc_ds":
            assert _role_count(hosts, "search_head") == 6
            assert _role_count(hosts, "deployer") == 2
            assert len(config["splunk_shclusters"]) == 2
        elif stem == "4idxc2site_2sh":
            assert _role_count(hosts, "indexer") == 4
            assert _role_count(hosts, "search_head") == 2
            sites = {host.get("site") for host in hosts if "search_head" in host["roles"]}
            assert sites == {"site1", "site2"}
            assert "splunk_shclusters" not in config
        elif stem == "4idxc2site_2sh_es":
            assert _role_count(hosts, "search_head") == 4
            assert "splunk_shclusters" not in config
        elif stem == "cm_4idxc2site_2x3shc_ds":
            assert _role_count(hosts, "search_head") == 6
            assert _role_count(hosts, "deployer") == 2
            assert {row["shc_site"] for row in config["splunk_shclusters"]} == {"site1", "site2"}
        elif stem == "cm_4idxc2site_4x3shc_ds":
            assert _role_count(hosts, "search_head") == 12
            assert _role_count(hosts, "deployer") == 4
            assert len(config["splunk_shclusters"]) == 4
        elif stem == "cm_4idxc2site_stretched_2x3shc_ds":
            assert _role_count(hosts, "search_head") == 6
            assert _role_count(hosts, "deployer") == 2
            assert {row["shc_site"] for row in config["splunk_shclusters"]} == {"site0"}
        elif stem == "cm_4idxc2site_stretched_3shc_ds":
            # SVA M4: multisite cluster manager, 3+ site peers, one stretched SHC of 3+ members, 1 deployer. No ES tier.
            assert _role_count(hosts, "cluster_manager") == 1
            assert _role_count(hosts, "indexer") == 4
            assert _role_count(hosts, "search_head") == 3
            assert _role_count(hosts, "deployer") == 1
            assert len(config["splunk_shclusters"]) == 1
            assert {row["shc_site"] for row in config["splunk_shclusters"]} == {"site0"}
            assert {host.get("site") for host in hosts if "search_head" in host["roles"]} == {"site1", "site2"}


def _init_no_provider(dest, **extra_env):
    return run_spa(
        ["--no-agent", "environment", "init", "--skip-doctor", "--example", "single_node.yml", str(dest)],
        extra_env=extra_env,
    )


def test_init_requires_provider_when_no_default_is_saved(tmp_path):
    """init without --provider and no saved default names the three providers and writes nothing."""
    dest = tmp_path / "lab"
    result = _init_no_provider(dest, XDG_CONFIG_HOME=str(tmp_path / "xdg"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--provider" in result.stderr
    for name in ("aws", "virtualbox", "external"):
        assert name in result.stderr, name
    assert "spa environment set --provider NAME" in result.stderr
    assert not dest.exists()


def test_init_agent_error_requires_provider_without_data(tmp_path):
    """Agent mode returns ok false with the provider choice and no data."""
    import json

    dest = tmp_path / "lab"
    result = run_spa(
        ["--agent", "environment", "init", "--skip-doctor", "--example", "single_node.yml", str(dest)],
        extra_env={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "--provider" in payload["error"]
    assert "data" not in payload
    assert not dest.exists()


def test_init_uses_saved_virtualbox_default(tmp_path):
    """A default saved with environment set --provider is used when init omits --provider."""
    xdg = str(tmp_path / "xdg")
    saved = run_spa(["environment", "set", "--provider", "virtualbox"], extra_env={"XDG_CONFIG_HOME": xdg})
    assert saved.returncode == 0, saved.stderr
    dest = tmp_path / "lab"
    result = _init_no_provider(dest, XDG_CONFIG_HOME=xdg)
    assert result.returncode == 0, result.stdout + result.stderr
    config = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "virtualbox" in config
    assert "terraform:" not in config


def test_init_uses_saved_aws_default_when_set_explicitly(tmp_path):
    """Setting aws explicitly is kept, so init does not ask for --provider again."""
    xdg = str(tmp_path / "xdg")
    saved = run_spa(["environment", "set", "--provider", "aws"], extra_env={"XDG_CONFIG_HOME": xdg})
    assert saved.returncode == 0, saved.stderr
    assert (tmp_path / "xdg" / "spa" / "providers.yml").is_file()
    dest = tmp_path / "lab"
    result = _init_no_provider(dest, XDG_CONFIG_HOME=xdg)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "terraform:" in (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")


def test_explicit_provider_flag_wins_over_saved_default(tmp_path):
    xdg = str(tmp_path / "xdg")
    run_spa(["environment", "set", "--provider", "virtualbox"], extra_env={"XDG_CONFIG_HOME": xdg})
    dest = tmp_path / "lab"
    result = run_spa(
        ["--no-agent", "environment", "init", "--skip-doctor", "--example", "single_node.yml",
         "--provider", "aws", str(dest)],
        extra_env={"XDG_CONFIG_HOME": xdg},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "terraform:" in (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
