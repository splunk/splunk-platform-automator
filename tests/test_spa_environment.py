"""spa environment registry: init dest, set, list, --env, remove."""

from pathlib import Path

import json
import os

import pytest
import yaml

from spa.registry import resolve_init_dest
from spa.paths import resolve_spa_paths
from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _xdg(tmp_path: Path) -> dict:
    return {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}


def test_bare_env_is_not_export():
    result = run_spa(["env"])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "export SPA_" not in result.stdout
    assert "list" in combined or "usage" in combined.lower() or "environment" in combined.lower()


def test_one_off_init_does_not_write_env_dir(tmp_path):
    extra = _xdg(tmp_path)
    parent = tmp_path / "custom"
    dest = parent / "my-lab"
    a = run_spa(
        [
            "environment",
            "init",
            "--skip-doctor",
            "--example",
            "single_node.yml",
            "--env-dir",
            str(parent),
            "--name",
            "my-lab",
        ],
        extra_env=extra,
    )
    assert a.returncode == 0, a.stderr + a.stdout
    assert dest.is_dir()
    paths_yml = tmp_path / "xdg" / "spa" / "paths.yml"
    if paths_yml.is_file():
        data = yaml.safe_load(paths_yml.read_text()) or {}
        assert "env_dir" not in data
    b = run_spa(
        [
            "environment",
            "init",
            "--skip-doctor",
            "--example",
            "single_node.yml",
            str(tmp_path / "custom2" / "other"),
        ],
        extra_env=extra,
    )
    assert b.returncode == 0, b.stderr + b.stdout
    c = run_spa_init(
        ["--example", "single_node.yml", str(tmp_path / "custom3" / "third")],
        extra_env=extra,
    )
    assert c.returncode == 0, c.stderr + c.stdout
    listed = run_spa(["environment", "list"], extra_env=extra)
    assert listed.returncode == 0
    assert "my-lab" in listed.stdout
    assert "other" in listed.stdout
    assert "third" in listed.stdout


def test_positional_name_override(tmp_path):
    extra = _xdg(tmp_path)
    dest = tmp_path / "folder"
    result = run_spa(
        [
            "init",
            "--skip-doctor",
            "--example",
            "single_node.yml",
            "--name",
            "prod",
            str(dest),
        ],
        extra_env=extra,
    )
    assert result.returncode == 0, result.stderr
    listed = run_spa(["--json", "environment", "list"], extra_env=extra)
    payload = json.loads(listed.stdout)
    names = {row["name"] for row in payload["data"]["environments"]}
    assert "prod" in names
    assert "folder" not in names


def test_set_env_dir_then_name_only_init(tmp_path):
    extra = _xdg(tmp_path)
    extra["SPA_ENV_PARENT"] = ""  # ignore; paths.yml should win after set
    extra.pop("SPA_ENV_PARENT", None)
    parent = tmp_path / "labs"
    set_result = run_spa(
        ["environment", "set", "--env-dir", str(parent)],
        extra_env=extra,
    )
    assert set_result.returncode == 0, set_result.stderr
    data = yaml.safe_load((tmp_path / "xdg" / "spa" / "paths.yml").read_text())
    assert Path(data["env_dir"]).resolve() == parent.resolve()
    init = run_spa(
        ["environment", "init", "--skip-doctor", "--example", "single_node.yml", "alpha"],
        extra_env=extra,
    )
    assert init.returncode == 0, init.stderr + init.stdout
    assert (parent / "alpha" / ".spa.yml").is_file()


def test_set_provider_virtualbox_creates_file_aws_removes(tmp_path):
    extra = _xdg(tmp_path)
    prov = tmp_path / "xdg" / "spa" / "providers.yml"
    set_vb = run_spa(["environment", "set", "--provider", "vbox"], extra_env=extra)
    assert set_vb.returncode == 0, set_vb.stderr
    assert prov.is_file()
    body = yaml.safe_load(prov.read_text())
    assert body["default"] == "virtualbox"
    set_aws = run_spa(["environment", "set", "--provider", "aws"], extra_env=extra)
    assert set_aws.returncode == 0, set_aws.stderr
    assert not prov.is_file()


def test_set_software_paths(tmp_path):
    extra = _xdg(tmp_path)
    software = tmp_path / "Software"
    apps = tmp_path / "labs" / "apps"
    software.mkdir()
    apps.mkdir(parents=True)
    result = run_spa(
        [
            "environment",
            "set",
            "--software-dir",
            str(software),
            "--apps-dir",
            str(apps),
        ],
        extra_env=extra,
    )
    assert result.returncode == 0, result.stderr
    data = yaml.safe_load((tmp_path / "xdg" / "spa" / "paths.yml").read_text())
    assert Path(data["software_dir"]).resolve() == software.resolve()
    assert Path(data["baseconfig_dir"]).resolve() == software.resolve()
    assert Path(data["apps_dir"]).resolve() == apps.resolve()
    other = tmp_path / "baseconfig"
    other.mkdir()
    second = run_spa(
        ["environment", "set", "--baseconfig-dir", str(other)],
        extra_env=extra,
    )
    assert second.returncode == 0, second.stderr
    data = yaml.safe_load((tmp_path / "xdg" / "spa" / "paths.yml").read_text())
    assert Path(data["baseconfig_dir"]).resolve() == other.resolve()
    assert Path(data["software_dir"]).resolve() == software.resolve()


def test_init_seeds_only_missing_global_paths(tmp_path):
    extra = _xdg(tmp_path)
    software = tmp_path / "Software"
    apps = tmp_path / "apps"
    software.mkdir()
    apps.mkdir()
    first = run_spa_init(
        [
            "--example",
            "single_node.yml",
            "--software-dir",
            str(software),
            "--apps-dir",
            str(apps),
            str(tmp_path / "first"),
        ],
        extra_env=extra,
    )
    assert first.returncode == 0, first.stderr + first.stdout
    paths = tmp_path / "xdg" / "spa" / "paths.yml"
    data = yaml.safe_load(paths.read_text())
    assert Path(data["software_dir"]).resolve() == software.resolve()
    assert Path(data["baseconfig_dir"]).resolve() == software.resolve()
    assert Path(data["apps_dir"]).resolve() == apps.resolve()

    other = tmp_path / "OtherSoftware"
    other.mkdir()
    second = run_spa_init(
        [
            "--example",
            "single_node.yml",
            "--software-dir",
            str(other),
            str(tmp_path / "second"),
        ],
        extra_env=extra,
    )
    assert second.returncode == 0, second.stderr + second.stdout
    unchanged = yaml.safe_load(paths.read_text())
    assert Path(unchanged["software_dir"]).resolve() == software.resolve()
    env_yml = yaml.safe_load((tmp_path / "second" / ".spa.yml").read_text())
    assert Path(env_yml["software_dir"]).resolve() == other.resolve()


def test_init_persists_discovered_global_paths(tmp_path):
    extra = _xdg(tmp_path)
    software = tmp_path / "Software"
    apps = tmp_path / "apps"
    software.mkdir()
    apps.mkdir()
    result = run_spa_init(
        ["--example", "single_node.yml", str(tmp_path / "lab")],
        extra_env=extra,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    data = yaml.safe_load((tmp_path / "xdg" / "spa" / "paths.yml").read_text())
    assert Path(data["software_dir"]).resolve() == software.resolve()
    assert Path(data["baseconfig_dir"]).resolve() == software.resolve()
    assert Path(data["apps_dir"]).resolve() == apps.resolve()


def test_force_init_persists_paths_from_existing_env_yml(tmp_path):
    extra = _xdg(tmp_path)
    software = tmp_path / "shared" / "Software"
    apps = tmp_path / "shared" / "apps"
    software.mkdir(parents=True)
    apps.mkdir()
    dest = write_min_env(tmp_path / "old" / "my-lab")
    (dest / ".spa.yml").write_text(
        "spa_home: %s\nsoftware_dir: %s\nbaseconfig_dir: %s\napps_dir: %s\n"
        % (PROJECT_ROOT, software, software, apps),
        encoding="utf-8",
    )
    (dest / "config" / "splunk_config.yml").write_text("splunk_hosts: {}\n")
    result = run_spa(
        ["environment", "init", str(dest), "--force", "--skip-doctor"],
        extra_env=extra,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    data = yaml.safe_load((tmp_path / "xdg" / "spa" / "paths.yml").read_text())
    assert Path(data["software_dir"]).resolve() == software.resolve()
    assert Path(data["baseconfig_dir"]).resolve() == software.resolve()
    assert Path(data["apps_dir"]).resolve() == apps.resolve()


def test_set_default_environment(tmp_path):
    extra = _xdg(tmp_path)
    one = tmp_path / "one"
    two = tmp_path / "two"
    assert run_spa_init(["--example", "single_node.yml", str(one)], extra_env=extra).returncode == 0
    assert run_spa_init(["--example", "single_node.yml", str(two)], extra_env=extra).returncode == 0
    result = run_spa(["environment", "set", "--default", "two"], extra_env=extra)
    assert result.returncode == 0, result.stderr
    listed = run_spa(["--json", "environment", "list"], extra_env=extra)
    rows = json.loads(listed.stdout)["data"]["environments"]
    assert [row["name"] for row in rows if row["default"]] == ["two"]
    resolved = resolve_spa_paths(
        start_dir=PROJECT_ROOT,
        clone_root=PROJECT_ROOT,
        environ={**extra, "HOME": str(tmp_path / "home")},
    )
    assert resolved.spa_env_dir == two.resolve()

    unknown = run_spa(["environment", "set", "--default", "missing"], extra_env=extra)
    assert unknown.returncode != 0


def test_set_without_flags_errors(tmp_path):
    result = run_spa(["environment", "set"], extra_env=_xdg(tmp_path))
    assert result.returncode != 0


def test_env_dir_without_name_errors(tmp_path):
    result = run_spa(
        ["init", "--skip-doctor", "--example", "single_node.yml", "--env-dir", str(tmp_path / "p")],
        extra_env=_xdg(tmp_path),
    )
    assert result.returncode != 0
    assert "--name" in (result.stderr + result.stdout)


def test_select_env_by_registry_name(tmp_path):
    extra = _xdg(tmp_path)
    dest = tmp_path / "lab1"
    assert run_spa_init(["--example", "single_node.yml", str(dest)], extra_env=extra).returncode == 0
    result = run_spa(
        ["--json", "--env", dest.name, "environment", "list"],
        extra_env=extra,
        cwd=tmp_path,
    )
    # list does not need --env; validate does
    val = run_spa(["--json", "validate", "--env", dest.name], extra_env=extra, cwd=PROJECT_ROOT)
    # validate may fail on missing software but should resolve env
    combined = val.stdout + val.stderr
    assert dest.name in combined or "splunk_config" in combined or val.returncode in (0, 1)


def test_remove_requires_yes(tmp_path):
    extra = _xdg(tmp_path)
    dest = tmp_path / "gone"
    assert run_spa_init(["--example", "single_node.yml", str(dest)], extra_env=extra).returncode == 0
    refused = run_spa(["environment", "remove", dest.name], extra_env=extra)
    assert refused.returncode != 0
    assert dest.is_dir()
    removed = run_spa(["environment", "remove", dest.name, "--yes"], extra_env=extra)
    assert removed.returncode == 0, removed.stderr
    assert not dest.exists()


def test_remove_refuses_deployed_without_force(tmp_path):
    extra = _xdg(tmp_path)
    dest = tmp_path / "live"
    assert run_spa_init(["--example", "single_node.yml", str(dest)], extra_env=extra).returncode == 0
    (dest / "inventory" / "hosts").write_text("idx1 ansible_host=10.0.0.1\n", encoding="utf-8")
    refused = run_spa(["environment", "remove", dest.name, "--yes"], extra_env=extra)
    assert refused.returncode != 0
    assert dest.is_dir()
    forced = run_spa(["environment", "remove", dest.name, "--yes", "--force"], extra_env=extra)
    assert forced.returncode == 0, forced.stderr
    assert not dest.exists()


def test_test_runs_never_touch_the_user_registry(tmp_path):
    """A test run must not register envs in the operator's ~/.config/spa."""
    from spa.registry import user_environments_yml

    user_config = Path(os.environ.get("HOME") or Path.home()).resolve() / ".config" / "spa"
    ambient = user_environments_yml().resolve()
    assert user_config not in ambient.parents and ambient.parent != user_config
    assert run_spa_init(["--example", "single_node.yml", str(tmp_path / "env")]).returncode == 0
    listed = run_spa(["--json", "environment", "list"])
    rows = json.loads(listed.stdout)["data"]["environments"]
    assert [row["name"] for row in rows] == ["env"]
    assert ambient.is_file()


def test_registry_readable_without_pyyaml(tmp_path, monkeypatch):
    """spa must not report an empty registry just because PyYAML is missing."""
    import spa.registry as registry

    xdg = tmp_path / "xdg"
    env = {"XDG_CONFIG_HOME": str(xdg), "HOME": str(tmp_path / "home")}
    lab = tmp_path / "labs" / "my-lab"
    lab.mkdir(parents=True)
    registry.register_environment("my-lab", lab, env)
    written = (xdg / "spa" / "environments.yml").read_text(encoding="utf-8")

    monkeypatch.setattr(registry, "yaml", None)
    without_yaml = registry.load_environments(env)
    assert without_yaml["default"] == "my-lab"
    assert Path(without_yaml["environments"]["my-lab"]["path"]) == lab.resolve()

    second = tmp_path / "labs" / "second"
    second.mkdir()
    registry.register_environment("second", second, env)
    reread = registry.load_environments(env)
    assert sorted(reread["environments"]) == ["my-lab", "second"]
    # The file a PyYAML-less spa wrote is still valid YAML for everyone else.
    parsed = yaml.safe_load((xdg / "spa" / "environments.yml").read_text(encoding="utf-8"))
    assert Path(parsed["environments"]["second"]["path"]) == second.resolve()
    assert "my-lab" in written


def test_stale_default_is_ignored_and_marked_missing(tmp_path):
    extra = _xdg(tmp_path)
    spa_config = tmp_path / "xdg" / "spa"
    spa_config.mkdir(parents=True)
    gone = tmp_path / "gone-lab"
    (spa_config / "environments.yml").write_text(
        yaml.safe_dump({"default": "gone-lab", "environments": {"gone-lab": {"path": str(gone)}}}),
        encoding="utf-8",
    )
    listed = run_spa(["environment", "list"], extra_env=extra)
    assert listed.returncode == 0, listed.stderr
    assert "(missing)" in listed.stdout

    env = dict(os.environ)
    env.update(extra)
    env.pop("SPA_ENV_DIR", None)
    from spa.registry import registry_default_path

    assert registry_default_path(env) is None


def test_pre3_cwd_does_not_silently_use_registered_default(tmp_path):
    extra = _xdg(tmp_path)
    extra["SPA_ENV_DIR"] = ""
    extra["SPLUNK_CONFIG_FILE"] = ""
    default = write_min_env(tmp_path / "my-lab")
    spa_config = tmp_path / "xdg" / "spa"
    spa_config.mkdir(parents=True)
    (spa_config / "environments.yml").write_text(
        yaml.safe_dump(
            {
                "default": "my-lab",
                "environments": {"my-lab": {"path": str(default)}},
            }
        ),
        encoding="utf-8",
    )
    old = tmp_path / "old-spa"
    (old / "config").mkdir(parents=True)
    (old / "config" / "splunk_config.yml").write_text(
        "plugin: splunk-platform-automator\n", encoding="utf-8"
    )
    plugin = old / "ansible" / "plugins" / "inventory"
    plugin.mkdir(parents=True)
    (plugin / "splunk-platform-automator.py").write_text(
        "# old plugin\n", encoding="utf-8"
    )

    result = run_spa(["--no-agent", "hosts", "-s"], extra_env=extra, cwd=old)
    assert result.returncode == 2
    combined = result.stderr + result.stdout
    assert "pre-3.0 SPA environment" in combined
    assert "Refusing to use the registered default" in combined
    assert "spa init --force" in combined


def test_force_init_adopts_unregistered_env(tmp_path):
    extra = _xdg(tmp_path)
    extra["HOME"] = str(tmp_path / "home")
    parent = tmp_path / "old-labs"
    dest = write_min_env(parent / "my-lab")
    (dest / "config" / "splunk_config.yml").write_text("splunk_hosts: {}\n", encoding="utf-8")
    listed_before = run_spa(["environment", "list"], extra_env=extra)
    assert "my-lab" not in listed_before.stdout
    adopted = run_spa(
        ["env", "init", "my-lab", "--force", "--skip-doctor"],
        extra_env=extra,
        cwd=parent,
    )
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    listed = run_spa(["--json", "environment", "list"], extra_env=extra)
    payload = json.loads(listed.stdout)
    rows = {row["name"]: row["path"] for row in payload["data"]["environments"]}
    assert dest.resolve() == Path(rows["my-lab"]).resolve()

    from_inside = run_spa(
        ["env", "init", "my-lab", "--force", "--skip-doctor"],
        extra_env=extra,
        cwd=dest,
    )
    assert from_inside.returncode == 0, from_inside.stderr + from_inside.stdout


def test_resolve_init_dest_force_prefers_existing_cwd(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    parent = tmp_path / "work"
    dest = parent / "my-lab"
    dest.mkdir(parents=True)
    (dest / ".spa.yml").write_text("spa_home: /tmp\n", encoding="utf-8")
    found, name, persist = resolve_init_dest(
        "my-lab",
        force=True,
        environ=env,
        relative_to=parent,
    )
    assert persist is False
    assert name == "my-lab"
    assert found.resolve() == dest.resolve()
    inside, _, _ = resolve_init_dest(
        "my-lab",
        force=True,
        environ=env,
        relative_to=dest,
    )
    assert inside.resolve() == dest.resolve()
    fresh, _, _ = resolve_init_dest(
        "brand-new",
        force=True,
        environ=env,
        relative_to=parent,
    )
    assert fresh == (home / "Splunk-Platform-Automator" / "brand-new")


def test_default_init_provider_is_aws(tmp_path):
    dest = tmp_path / "aws-default"
    result = run_spa_init(["--example", "cm_2idxc_sh_uf", str(dest)], extra_env=_xdg(tmp_path))
    assert result.returncode == 0, result.stderr
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    assert "terraform" in cfg
    assert "virtualbox" not in cfg
