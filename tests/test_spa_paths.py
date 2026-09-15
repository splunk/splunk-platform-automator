"""Unit tests for the SPA_HOME / SPA_ENV_DIR path contract."""

import os
import sys

import pytest

from spa_testutil import PROJECT_ROOT, LIB

pytestmark = pytest.mark.local

sys.path.insert(0, str(LIB))

from spa.paths import (  # noqa: E402
    find_spa_yml,
    is_spa_home,
    resolve_shared_data_dir,
    resolve_spa_paths,
    save_user_paths,
    user_paths_yml,
    xdg_config_home,
)


def test_clone_is_spa_home():
    assert is_spa_home(PROJECT_ROOT)


def test_clone_equal_when_unset(tmp_path):
    paths = resolve_spa_paths(start_dir=tmp_path, environ={}, clone_root=PROJECT_ROOT)
    assert paths.spa_home == paths.spa_env_dir
    assert str(paths.spa_home) == os.path.realpath(PROJECT_ROOT)
    assert paths.roots_differ is False
    assert paths.terraform_state_dir == paths.terraform_modules_dir
    assert paths.terraform_modules_dir == paths.spa_home / "terraform" / "aws"
    assert paths.inventory_dir == paths.spa_env_dir / "inventory"
    assert paths.config_file == paths.spa_env_dir / "config" / "splunk_config.yml"
    assert paths.spa_yml is None


def test_env_overrides(tmp_path):
    dest = tmp_path / "env"
    dest.mkdir()
    env = {
        "SPA_HOME": str(PROJECT_ROOT),
        "SPA_ENV_DIR": str(dest),
    }
    paths = resolve_spa_paths(start_dir=tmp_path, environ=env, clone_root=PROJECT_ROOT)
    assert paths.spa_home == paths.spa_home.resolve()
    assert paths.spa_env_dir == dest.resolve()
    assert paths.roots_differ is True
    assert paths.terraform_modules_dir == paths.spa_home / "terraform" / "aws"
    assert paths.terraform_state_dir == dest.resolve() / "terraform" / "aws"
    assert paths.config_file == dest.resolve() / "config" / "splunk_config.yml"


def test_splunk_config_file_wins(tmp_path):
    cfg = tmp_path / "custom.yml"
    cfg.write_text("plugin: splunk-platform-automator\n")
    env = {"SPLUNK_CONFIG_FILE": str(cfg)}
    paths = resolve_spa_paths(start_dir=tmp_path, environ=env, clone_root=PROJECT_ROOT)
    assert paths.config_file == cfg.resolve()
    assert paths.spa_home == paths.spa_env_dir


def test_spa_yml_sets_home_and_env(tmp_path):
    dest = tmp_path / "itsi"
    dest.mkdir()
    (dest / ".spa.yml").write_text("spa_home: %s\n" % PROJECT_ROOT)
    found = find_spa_yml(dest)
    assert found == dest / ".spa.yml"
    paths = resolve_spa_paths(start_dir=dest, environ={}, clone_root=PROJECT_ROOT)
    assert str(paths.spa_home) == os.path.realpath(PROJECT_ROOT)
    assert paths.spa_env_dir == dest.resolve()
    assert paths.roots_differ is True
    assert paths.spa_yml == (dest / ".spa.yml").resolve()


def test_env_wins_over_spa_yml(tmp_path):
    dest = tmp_path / "from-yml"
    dest.mkdir()
    (dest / ".spa.yml").write_text("spa_home: /does/not/matter\n")
    other = tmp_path / "from-env"
    other.mkdir()
    env = {
        "SPA_HOME": str(PROJECT_ROOT),
        "SPA_ENV_DIR": str(other),
    }
    paths = resolve_spa_paths(start_dir=dest, environ=env, clone_root=PROJECT_ROOT)
    assert paths.spa_env_dir == other.resolve()
    assert str(paths.spa_home) == os.path.realpath(PROJECT_ROOT)


def test_export_sets_ansible_inventory_to_env(tmp_path):
    dest = tmp_path / "env"
    (dest / "config").mkdir(parents=True)
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}
    paths = resolve_spa_paths(start_dir=tmp_path, environ=env, clone_root=PROJECT_ROOT)
    exported = paths.export_env()
    assert exported["SPA_HOME"] == str(paths.spa_home)
    assert exported["SPA_ENV_DIR"] == str(paths.spa_env_dir)
    assert exported["ANSIBLE_CONFIG"] == str(paths.spa_home / "ansible.cfg")
    assert str(paths.config_file) in exported["ANSIBLE_INVENTORY"]
    clone_config = os.path.join(PROJECT_ROOT, "config", "splunk_config.yml")
    assert clone_config not in exported["ANSIBLE_INVENTORY"].split(",")
    assert "SPA_SOFTWARE_DIR" in exported
    assert "SPA_BASECONFIG_DIR" in exported
    assert "SPA_APPS_DIR" in exported


def test_software_prefers_env_sibling(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (tmp_path / "Software").mkdir()
    dest = tmp_path / "envs" / "itsi"
    dest.mkdir(parents=True)
    env_sw = tmp_path / "envs" / "Software"
    env_sw.mkdir()
    found = resolve_shared_data_dir(spa_home, dest, environ={})
    assert found == env_sw.resolve()


def test_software_falls_back_to_spa_home_sibling(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    home_sw = tmp_path / "Software"
    home_sw.mkdir()
    dest = tmp_path / "envs" / "itsi"
    dest.mkdir(parents=True)
    found = resolve_shared_data_dir(spa_home, dest, environ={})
    assert found == home_sw.resolve()


def test_software_env_wins(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (tmp_path / "Software").mkdir()
    dest = tmp_path / "envs" / "itsi"
    dest.mkdir(parents=True)
    stub = tmp_path / "stub"
    stub.mkdir()
    found = resolve_shared_data_dir(
        spa_home, dest, environ={"SPA_SOFTWARE_DIR": str(stub)}
    )
    assert found == stub.resolve()


def test_spa_yml_software_dir(tmp_path):
    dest = tmp_path / "itsi"
    dest.mkdir()
    software = tmp_path / "shared-sw"
    software.mkdir()
    (dest / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\n"
        % (PROJECT_ROOT, software, software)
    )
    paths = resolve_spa_paths(start_dir=dest, environ={}, clone_root=PROJECT_ROOT)
    assert paths.software_dir == software.resolve()
    assert paths.baseconfig_dir == software.resolve()


def test_spa_yml_apps_dir(tmp_path):
    dest = tmp_path / "itsi"
    dest.mkdir()
    software = tmp_path / "shared-sw"
    apps = tmp_path / "shared-apps"
    software.mkdir()
    apps.mkdir()
    (dest / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\napps_dir: %s\n"
        % (PROJECT_ROOT, software, software, apps)
    )
    paths = resolve_spa_paths(start_dir=dest, environ={}, clone_root=PROJECT_ROOT)
    assert paths.apps_dir == apps.resolve()
    assert paths.export_env()["SPA_APPS_DIR"] == str(apps.resolve())


def test_apps_prefers_env_sibling(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (spa_home / "apps").mkdir()
    dest = tmp_path / "envs" / "itsi"
    dest.mkdir(parents=True)
    env_apps = tmp_path / "envs" / "apps"
    env_apps.mkdir()
    found = resolve_shared_data_dir(
        spa_home, dest, configured="../apps", env_var="SPA_APPS_DIR", environ={}, home_leaf="apps"
    )
    assert found == env_apps.resolve()


def test_apps_falls_back_to_spa_home_apps(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    home_apps = spa_home / "apps"
    home_apps.mkdir()
    dest = tmp_path / "envs" / "itsi"
    dest.mkdir(parents=True)
    found = resolve_shared_data_dir(
        spa_home, dest, configured="../apps", env_var="SPA_APPS_DIR", environ={}, home_leaf="apps"
    )
    assert found == home_apps.resolve()


def test_apps_env_wins(tmp_path):
    spa_home = tmp_path / "framework"
    spa_home.mkdir()
    (spa_home / "apps").mkdir()
    dest = tmp_path / "envs" / "itsi"
    dest.mkdir(parents=True)
    stub = tmp_path / "stub-apps"
    stub.mkdir()
    found = resolve_shared_data_dir(
        spa_home,
        dest,
        configured="../apps",
        env_var="SPA_APPS_DIR",
        environ={"SPA_APPS_DIR": str(stub)},
        home_leaf="apps",
    )
    assert found == stub.resolve()


def test_spa_yml_baseconfig_dir_separate(tmp_path):
    dest = tmp_path / "itsi"
    dest.mkdir()
    software = tmp_path / "installers"
    baseconfig = tmp_path / "baseconfig"
    software.mkdir()
    baseconfig.mkdir()
    (dest / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\n"
        % (PROJECT_ROOT, software, baseconfig)
    )
    paths = resolve_spa_paths(start_dir=dest, environ={}, clone_root=PROJECT_ROOT)
    assert paths.software_dir == software.resolve()
    assert paths.baseconfig_dir == baseconfig.resolve()


def test_xdg_config_home_ignores_relative(tmp_path):
    isolated = {"HOME": str(tmp_path / "home"), "XDG_CONFIG_HOME": "relative-config"}
    assert xdg_config_home(isolated) == tmp_path / "home" / ".config"


def test_user_paths_yml_after_env_spa_yml(tmp_path):
    dest = tmp_path / "itsi"
    dest.mkdir()
    (dest / ".spa.yml").write_text("spa_home: %s\n" % PROJECT_ROOT)
    software = tmp_path / "controller-sw"
    software.mkdir()
    xdg = tmp_path / "xdg-config"
    save_user_paths(software_dir=str(software), environ={"XDG_CONFIG_HOME": str(xdg)})
    env = {"XDG_CONFIG_HOME": str(xdg)}
    paths = resolve_spa_paths(start_dir=dest, environ=env, clone_root=PROJECT_ROOT)
    assert paths.software_dir == software.resolve()
    assert paths.baseconfig_dir == software.resolve()
    assert user_paths_yml(env) == xdg / "spa" / "paths.yml"


def test_env_spa_yml_wins_over_user_paths(tmp_path):
    dest = tmp_path / "itsi"
    dest.mkdir()
    env_sw = tmp_path / "env-sw"
    user_sw = tmp_path / "user-sw"
    env_sw.mkdir()
    user_sw.mkdir()
    (dest / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\n"
        % (PROJECT_ROOT, env_sw, env_sw)
    )
    xdg = tmp_path / "xdg-config"
    save_user_paths(software_dir=str(user_sw), environ={"XDG_CONFIG_HOME": str(xdg)})
    paths = resolve_spa_paths(
        start_dir=dest,
        environ={"XDG_CONFIG_HOME": str(xdg)},
        clone_root=PROJECT_ROOT,
    )
    assert paths.software_dir == env_sw.resolve()
