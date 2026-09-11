"""Unit tests for the Distribution M1 path contract (SPA_HOME / SPA_LAB_DIR)."""

import os
import sys

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ansible", "plugins", "inventory"))

from spa_paths import (  # noqa: E402
    find_spa_yml,
    is_spa_home,
    resolve_shared_data_dir,
    resolve_spa_paths,
)


def test_clone_is_spa_home():
    assert is_spa_home(PROJECT_ROOT)


def test_clone_equal_when_unset(tmp_path):
    paths = resolve_spa_paths(start_dir=tmp_path, environ={}, clone_root=PROJECT_ROOT)
    assert paths.spa_home == paths.spa_lab_dir
    assert str(paths.spa_home) == os.path.realpath(PROJECT_ROOT)
    assert paths.roots_differ is False
    assert paths.terraform_state_dir == paths.terraform_modules_dir
    assert paths.terraform_modules_dir == paths.spa_home / "terraform" / "aws"
    assert paths.inventory_dir == paths.spa_lab_dir / "inventory"
    assert paths.config_file == paths.spa_lab_dir / "config" / "splunk_config.yml"
    assert paths.spa_yml is None


def test_env_overrides(tmp_path):
    lab = tmp_path / "lab"
    lab.mkdir()
    env = {
        "SPA_HOME": PROJECT_ROOT,
        "SPA_LAB_DIR": str(lab),
    }
    paths = resolve_spa_paths(start_dir=tmp_path, environ=env, clone_root=PROJECT_ROOT)
    assert paths.spa_home == paths.spa_home.resolve()
    assert paths.spa_lab_dir == lab.resolve()
    assert paths.roots_differ is True
    assert paths.terraform_modules_dir == paths.spa_home / "terraform" / "aws"
    assert paths.terraform_state_dir == lab.resolve() / "terraform" / "aws"
    assert paths.config_file == lab.resolve() / "config" / "splunk_config.yml"


def test_splunk_config_file_wins(tmp_path):
    cfg = tmp_path / "custom.yml"
    cfg.write_text("plugin: splunk-platform-automator\n")
    env = {"SPLUNK_CONFIG_FILE": str(cfg)}
    paths = resolve_spa_paths(start_dir=tmp_path, environ=env, clone_root=PROJECT_ROOT)
    assert paths.config_file == cfg.resolve()
    assert paths.spa_home == paths.spa_lab_dir


def test_spa_yml_sets_home_and_lab(tmp_path):
    lab = tmp_path / "itsi"
    lab.mkdir()
    (lab / ".spa.yml").write_text("spa_home: %s\n" % PROJECT_ROOT)
    found = find_spa_yml(lab)
    assert found == lab / ".spa.yml"
    paths = resolve_spa_paths(start_dir=lab, environ={}, clone_root=PROJECT_ROOT)
    assert paths.spa_home == paths.spa_home.resolve()
    assert str(paths.spa_home) == os.path.realpath(PROJECT_ROOT)
    assert paths.spa_lab_dir == lab.resolve()
    assert paths.roots_differ is True
    assert paths.spa_yml == (lab / ".spa.yml").resolve()


def test_env_wins_over_spa_yml(tmp_path):
    lab = tmp_path / "from-yml"
    lab.mkdir()
    (lab / ".spa.yml").write_text("spa_home: /does/not/matter\n")
    other = tmp_path / "from-env"
    other.mkdir()
    env = {
        "SPA_HOME": PROJECT_ROOT,
        "SPA_LAB_DIR": str(other),
    }
    paths = resolve_spa_paths(start_dir=lab, environ=env, clone_root=PROJECT_ROOT)
    assert paths.spa_lab_dir == other.resolve()
    assert str(paths.spa_home) == os.path.realpath(PROJECT_ROOT)


def test_export_sets_ansible_inventory_to_lab(tmp_path):
    lab = tmp_path / "lab"
    (lab / "config").mkdir(parents=True)
    env = {"SPA_HOME": PROJECT_ROOT, "SPA_LAB_DIR": str(lab)}
    paths = resolve_spa_paths(start_dir=tmp_path, environ=env, clone_root=PROJECT_ROOT)
    exported = paths.export_env()
    assert exported["SPA_HOME"] == str(paths.spa_home)
    assert exported["SPA_LAB_DIR"] == str(paths.spa_lab_dir)
    assert exported["ANSIBLE_CONFIG"] == str(paths.spa_home / "ansible.cfg")
    assert str(paths.config_file) in exported["ANSIBLE_INVENTORY"]
    clone_config = os.path.join(PROJECT_ROOT, "config", "splunk_config.yml")
    assert clone_config not in exported["ANSIBLE_INVENTORY"].split(",")
    assert "SPA_SOFTWARE_DIR" in exported
    assert "SPA_BASECONFIG_DIR" in exported
    assert "SPA_APPS_DIR" in exported


def test_software_prefers_lab_sibling(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (tmp_path / "Software").mkdir()
    lab = tmp_path / "labs" / "itsi"
    lab.mkdir(parents=True)
    lab_sw = tmp_path / "labs" / "Software"
    lab_sw.mkdir()
    found = resolve_shared_data_dir(spa_home, lab, environ={})
    assert found == lab_sw.resolve()


def test_software_falls_back_to_spa_home_sibling(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    home_sw = tmp_path / "Software"
    home_sw.mkdir()
    lab = tmp_path / "labs" / "itsi"
    lab.mkdir(parents=True)
    found = resolve_shared_data_dir(spa_home, lab, environ={})
    assert found == home_sw.resolve()


def test_software_env_wins(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (tmp_path / "Software").mkdir()
    lab = tmp_path / "labs" / "itsi"
    lab.mkdir(parents=True)
    stub = tmp_path / "stub"
    stub.mkdir()
    found = resolve_shared_data_dir(
        spa_home, lab, environ={"SPA_SOFTWARE_DIR": str(stub)}
    )
    assert found == stub.resolve()


def test_spa_yml_software_dir(tmp_path):
    lab = tmp_path / "itsi"
    lab.mkdir()
    software = tmp_path / "shared-sw"
    software.mkdir()
    (lab / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\n"
        % (PROJECT_ROOT, software, software)
    )
    paths = resolve_spa_paths(start_dir=lab, environ={}, clone_root=PROJECT_ROOT)
    assert paths.software_dir == software.resolve()
    assert paths.baseconfig_dir == software.resolve()


def test_spa_yml_apps_dir(tmp_path):
    lab = tmp_path / "itsi"
    lab.mkdir()
    software = tmp_path / "shared-sw"
    apps = tmp_path / "shared-apps"
    software.mkdir()
    apps.mkdir()
    (lab / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\napps_dir: %s\n"
        % (PROJECT_ROOT, software, software, apps)
    )
    paths = resolve_spa_paths(start_dir=lab, environ={}, clone_root=PROJECT_ROOT)
    assert paths.apps_dir == apps.resolve()
    assert paths.export_env()["SPA_APPS_DIR"] == str(apps.resolve())


def test_apps_prefers_lab_sibling(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (spa_home / "apps").mkdir()
    lab = tmp_path / "labs" / "itsi"
    lab.mkdir(parents=True)
    lab_apps = tmp_path / "labs" / "apps"
    lab_apps.mkdir()
    found = resolve_shared_data_dir(
        spa_home, lab, configured="../apps", env_var="SPA_APPS_DIR", environ={}, home_leaf="apps"
    )
    assert found == lab_apps.resolve()


def test_apps_falls_back_to_spa_home_apps(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    home_apps = spa_home / "apps"
    home_apps.mkdir()
    lab = tmp_path / "labs" / "itsi"
    lab.mkdir(parents=True)
    found = resolve_shared_data_dir(
        spa_home, lab, configured="../apps", env_var="SPA_APPS_DIR", environ={}, home_leaf="apps"
    )
    assert found == home_apps.resolve()


def test_apps_env_wins(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (spa_home / "apps").mkdir()
    lab = tmp_path / "labs" / "itsi"
    lab.mkdir(parents=True)
    stub = tmp_path / "stub-apps"
    stub.mkdir()
    found = resolve_shared_data_dir(
        spa_home,
        lab,
        configured="../apps",
        env_var="SPA_APPS_DIR",
        environ={"SPA_APPS_DIR": str(stub)},
        home_leaf="apps",
    )
    assert found == stub.resolve()


def test_spa_yml_baseconfig_dir_separate(tmp_path):
    lab = tmp_path / "itsi"
    lab.mkdir()
    software = tmp_path / "installers"
    baseconfig = tmp_path / "baseconfig"
    software.mkdir()
    baseconfig.mkdir()
    (lab / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\n"
        % (PROJECT_ROOT, software, baseconfig)
    )
    paths = resolve_spa_paths(start_dir=lab, environ={}, clone_root=PROJECT_ROOT)
    assert paths.software_dir == software.resolve()
    assert paths.baseconfig_dir == baseconfig.resolve()
