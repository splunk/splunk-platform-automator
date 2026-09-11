"""Tests for bin/init_spa_dir.sh (Distribution M1 lab scaffold)."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "bin" / "init_spa_dir.sh"


def _run(args, env=None, cwd=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    argv = [str(SCRIPT), *args]
    # Unit tests do not require host Vagrant/Terraform; doctor still runs in test_spa_doctor.
    if "--skip-doctor" not in args:
        argv.insert(1, "--skip-doctor")
    return subprocess.run(
        argv,
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_init_script_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], cwd=PROJECT_ROOT)
    assert result.returncode == 0


def test_scaffold_creates_lab_without_ansible(tmp_path):
    lab = tmp_path / "my-lab"
    result = _run(["--example", "single_node.yml", str(lab)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (lab / "config" / "splunk_config.yml").is_file()
    assert (lab / ".spa.yml").is_file()
    assert (lab / "inventory").is_dir()
    assert (lab / "inventory" / "hosts").is_file()
    assert (lab / "terraform" / "aws").is_dir()
    assert (lab / "saved_base_config_apps").is_dir()
    assert not (lab / "ansible").exists()

    spa_yml = yaml.safe_load((lab / ".spa.yml").read_text())
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

    cfg = yaml.safe_load((lab / "config" / "splunk_config.yml").read_text())
    assert cfg["plugin"] == "splunk-platform-automator"
    assert cfg["splunk_hosts"]


def test_example_flag(tmp_path):
    lab = tmp_path / "c1"
    result = _run(["--example", "cm_2idxc_sh_uf", str(lab)])
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((lab / "config" / "splunk_config.yml").read_text())
    names = [h.get("name") for h in cfg["splunk_hosts"] if "name" in h]
    assert "cm" in names


def test_refuse_overwrite(tmp_path):
    lab = tmp_path / "exists"
    first = _run(["--example", "single_node.yml", str(lab)])
    assert first.returncode == 0
    second = _run(["--example", "single_node.yml", str(lab)])
    assert second.returncode != 0
    assert "already exists" in (second.stderr + second.stdout).lower()


def test_force_overwrite(tmp_path):
    lab = tmp_path / "exists"
    assert _run(["--example", "single_node.yml", str(lab)]).returncode == 0
    result = _run(["--force", "--example", "single_node.yml", str(lab)])
    assert result.returncode == 0, result.stderr


def test_refuse_spa_home():
    result = _run([str(PROJECT_ROOT)])
    assert result.returncode != 0
    assert "SPA_HOME" in (result.stderr + result.stdout)


def test_missing_example(tmp_path):
    result = _run(["--example", "does-not-exist.yml", str(tmp_path / "x")])
    assert result.returncode != 0
    assert "not found" in (result.stderr + result.stdout).lower()


def _write_old_env(root: Path, marker: str = "migrated-env") -> None:
    (root / "config").mkdir(parents=True)
    (root / "inventory").mkdir(parents=True)
    (root / "terraform" / "aws").mkdir(parents=True)
    (root / "config" / "splunk_config.yml").write_text(
        f"plugin: splunk-platform-automator\n# {marker}\n"
    )
    (root / "config" / "index.html").write_text("<html>hosts</html>\n")
    (root / "inventory" / "hosts").write_text("cm ansible_host=10.0.0.1\n")
    (root / "terraform" / "aws" / "terraform.tfstate").write_text('{"version": 4}\n')
    (root / "terraform" / "aws" / "terraform.tfvars").write_text("region = \"eu-central-1\"\n")
    (root / "terraform" / "aws" / "main.tf").write_text("# leftover module copy\n")


def test_auto_migrate_when_spa_home_has_config(tmp_path):
    source = tmp_path / "old-home"
    lab = tmp_path / "lab"
    _write_old_env(source)
    result = _run([str(lab)], env={"SPA_HOME": str(source)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Migrating existing env" in (result.stderr + result.stdout)
    assert (lab / "config" / "splunk_config.yml").is_file()
    assert not (source / "config" / "splunk_config.yml").exists()
    spa_yml = yaml.safe_load((lab / ".spa.yml").read_text())
    assert spa_yml["spa_home"] == str(source)


def test_migrate_from_existing_env(tmp_path):
    source = tmp_path / "old-clone"
    lab = tmp_path / "lab"
    _write_old_env(source)
    (source / "ansible").mkdir()
    (source / "ansible" / "deploy_site.yml").write_text("# framework\n")

    result = _run(["--from", str(source), str(lab)])
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stderr + result.stdout
    assert "Migrating existing env" in out
    assert (lab / "config" / "splunk_config.yml").is_file()
    assert "migrated-env" in (lab / "config" / "splunk_config.yml").read_text()
    assert (lab / "config" / "index.html").is_file()
    assert (lab / "inventory" / "hosts").read_text() == "cm ansible_host=10.0.0.1\n"
    assert (lab / "terraform" / "aws" / "terraform.tfstate").is_file()
    assert (lab / "terraform" / "aws" / "terraform.tfvars").is_file()
    assert (lab / ".spa.yml").is_file()
    assert not (lab / "ansible").exists()
    spa_yml = yaml.safe_load((lab / ".spa.yml").read_text())
    assert spa_yml["spa_home"] == str(PROJECT_ROOT)

    # Modules stay in SPA_HOME; lab gets a symlink, not a copied main.tf.
    lab_main = lab / "terraform" / "aws" / "main.tf"
    assert lab_main.is_symlink()
    assert lab_main.resolve() == (PROJECT_ROOT / "terraform" / "aws" / "main.tf").resolve()

    # Default is move — source lab files are gone; framework files stay.
    assert not (source / "config" / "splunk_config.yml").exists()
    assert not (source / "inventory" / "hosts").exists()
    assert not (source / "terraform" / "aws" / "terraform.tfstate").exists()
    assert (source / "ansible" / "deploy_site.yml").is_file()


def test_migrate_keep_source(tmp_path):
    source = tmp_path / "old-clone"
    lab = tmp_path / "lab"
    _write_old_env(source)
    result = _run(["--from", str(source), "--keep-source", str(lab)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (lab / "config" / "splunk_config.yml").is_file()
    assert (source / "config" / "splunk_config.yml").is_file()


def test_migrate_requires_config(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    result = _run(["--from", str(source), str(tmp_path / "lab")])
    assert result.returncode != 0
    assert "nothing to migrate" in (result.stderr + result.stdout).lower()


def test_convert_old_clone_in_place(tmp_path):
    dest = tmp_path / "copied-clone"
    _write_old_env(dest)
    (dest / "ansible" / "roles").mkdir(parents=True)
    (dest / "bin").mkdir()
    (dest / "README.md").write_text("# old clone\n")
    (dest / "ansible.cfg").write_text("[defaults]\n")

    result = _run([str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Detected an existing clone-style env" in (result.stderr + result.stdout)
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert "migrated-env" in (dest / "config" / "splunk_config.yml").read_text()
    assert (dest / "inventory" / "hosts").is_file()
    assert (dest / "terraform" / "aws" / "terraform.tfstate").is_file()
    assert (dest / ".spa.yml").is_file()
    assert not (dest / "ansible").exists()
    assert not (dest / "bin").exists()
    assert not (dest / "README.md").exists()
    assert not (dest / "ansible.cfg").exists()
    assert (dest / "terraform" / "aws" / "main.tf").is_symlink()


def test_example_and_migrate_conflict(tmp_path):
    result = _run(
        ["--example", "single_node.yml", "--migrate", str(tmp_path / "lab")]
    )
    assert result.returncode != 0
    assert "not both" in (result.stderr + result.stdout).lower()


def test_refuse_same_source_and_dest(tmp_path):
    source = tmp_path / "old"
    _write_old_env(source)
    result = _run(["--from", str(source), str(source)])
    assert result.returncode != 0
    assert "same path" in (result.stderr + result.stdout).lower()


def test_init_uses_existing_shared_venv(tmp_path):
    shared = PROJECT_ROOT / ".venv" / "bin" / "activate"
    if not shared.is_file():
        pytest.skip("shared venv not present")
    lab = tmp_path / "lab"
    result = _run(["--example", "single_node.yml", "--skip-doctor", str(lab)])
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stderr + result.stdout
    assert "venv:" in out
    assert "(existing)" in out
    assert "Creating Python venv" not in out


def test_save_baseconfig_tasks_write_under_lab_dir():
    save_app = PROJECT_ROOT / "ansible" / "roles" / "baseconfig_app" / "tasks" / "save_app.yml"
    save_sc = (
        PROJECT_ROOT / "ansible" / "roles" / "deployment_server" / "tasks" / "save_serverclass.yml"
    )
    defaults = yaml.safe_load((PROJECT_ROOT / "defaults" / "splunk_apps.yml").read_text())
    assert defaults["splunk_apps"]["splunk_save_baseconfig_apps_dir"] == "saved_base_config_apps"
    for path in (save_app, save_sc):
        text = path.read_text()
        assert "spa_saved_baseconfig_apps_dir" in text
        assert '../{{' not in text
        assert '../{{splunk_save_baseconfig_apps_dir' not in text
