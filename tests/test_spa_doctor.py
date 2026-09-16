"""Tests for spa doctor host prerequisite checks."""

import os
import shutil
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_doctor_passes_on_dev_machine():
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "python3" in (result.stdout + result.stderr).lower()


def test_doctor_warns_when_spa_comes_from_another_clone(tmp_path):
    other_bin = tmp_path / "other-clone" / "bin"
    other_bin.mkdir(parents=True)
    (other_bin / "spa").write_text("#!/bin/sh\nexit 0\n")
    (other_bin / "spa").chmod(0o755)
    env = spa_env()
    env["PATH"] = str(other_bin) + os.pathsep + env["PATH"]
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    output = result.stdout + result.stderr
    assert str(other_bin / "spa") in output
    assert "another checkout wins" in output


def test_doctor_ok_when_spa_comes_from_spa_home():
    env = spa_env()
    env["PATH"] = str(PROJECT_ROOT / "bin") + os.pathsep + env["PATH"]
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"spa resolves to {PROJECT_ROOT}/bin/spa" in result.stdout


def test_doctor_aws_strict_fails_without_terraform():
    if shutil.which("terraform"):
        pytest.skip("terraform is installed")
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--aws"], env=env)
    assert result.returncode != 0
    assert "terraform" in (result.stdout + result.stderr).lower()


def test_init_runs_doctor_by_default(tmp_path):
    dest = tmp_path / "env"
    result = run_spa(["init", "--example", "cm_2idxc_sh_uf_aws.yml", str(dest)])
    out = result.stderr + result.stdout
    assert "SPA host prerequisites" in out
    if result.returncode != 0:
        assert "terraform" in out.lower()


def test_init_skip_doctor(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SPA host prerequisites" not in (result.stdout + result.stderr)


def test_doctor_skips_vagrant_without_virtualbox(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "cm_2idxc_sh_uf_aws.yml", "--skip-doctor", str(dest)])
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "vagrant required" not in out.lower()
    assert "vagrant is on PATH" not in out


def test_doctor_checks_env_provider_without_env_flag(tmp_path):
    """spa doctor from an env dir must check that env's provider tools."""
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)})
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env, cwd=dest)
    out = result.stdout + result.stderr
    assert "provider tools checked for: virtualbox" in out
    assert "vagrant required for VirtualBox" in out
    assert result.returncode != 0


def test_doctor_reports_when_config_has_no_provider(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    config = dest / "config" / "splunk_config.yml"
    config.write_text(
        "---\nsplunk_hosts:\n  - name: idx1\n    roles: [indexer]\n", encoding="utf-8"
    )
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)})
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env, cwd=dest)
    out = result.stdout + result.stderr
    assert "no provider in" in out
    assert "required for VirtualBox" not in out
    assert "required for terraform.aws" not in out


def test_config_providers_ignores_comments_and_nested_keys():
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa.doctor import _config_providers

    assert _config_providers("virtualbox:\n  memory: 4096\n") == {"virtualbox"}
    assert _config_providers("terraform:\n  aws:\n    region: eu-central-1\n") == {"aws"}
    # a legacy top-level aws: block is inventory-only, not terraform.aws
    assert _config_providers("aws:\n  region: eu-central-1\n") == set()
    # comments and host-level keys must not pull in tool checks
    assert _config_providers("# virtualbox: nope\nsplunk_hosts:\n  - virtualbox: {}\n") == set()


def test_doctor_env_provider_terraform_aws(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "cm_2idxc_sh_uf_aws.yml", "--skip-doctor", str(dest)])
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)})
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env, cwd=dest)
    out = result.stdout + result.stderr
    assert "provider tools checked for: terraform.aws" in out
    assert "terraform required for terraform.aws" in out
    assert "required for VirtualBox" not in out


def test_doctor_flags_virtualbox_without_a_vagrant_driver(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(doctor_mod, "_virtualbox_version", lambda: "7.2")
    monkeypatch.setattr(doctor_mod, "_vagrant_virtualbox_drivers", lambda: ["6.1", "7.0"])
    monkeypatch.setattr(doctor_mod, "_vagrant_plugin_names", lambda: ["vagrant-vbguest"])

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), env_dir=str(dest))
    vbox = next(row for row in result.data["checks"] if row["id"] == "virtualbox")
    assert vbox["level"] == "error"
    assert "7.2" in vbox["message"]
    assert "7.0" in vbox["message"]
    assert "upgrade vagrant" in vbox["fix"]


def test_doctor_ok_when_vagrant_supports_installed_virtualbox(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(doctor_mod, "_virtualbox_version", lambda: "7.0")
    monkeypatch.setattr(doctor_mod, "_vagrant_virtualbox_drivers", lambda: ["6.1", "7.0"])
    monkeypatch.setattr(doctor_mod, "_vagrant_plugin_names", lambda: ["vagrant-vbguest"])

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), env_dir=str(dest))
    vbox = next(row for row in result.data["checks"] if row["id"] == "virtualbox")
    assert vbox["level"] == "ok"
    assert "VirtualBox 7.0" in vbox["message"]


def test_doctor_reports_incomplete_venv_for_the_env_under_test(tmp_path):
    """--env decides which .venv is checked, not the caller's SPA_ENV_DIR."""
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    (dest / ".venv" / "include").mkdir(parents=True)
    other = tmp_path / "other"
    (other / ".venv" / "include").mkdir(parents=True)
    env = spa_env({"SPA_ENV_DIR": str(other)})
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "incomplete venv at %s" % (dest / ".venv") in out
    assert str(other / ".venv") not in out


def test_doctor_warns_when_hook_missing(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    assert "direnv" in out.lower()
    if shutil.which("direnv"):
        assert "fix-direnv" in out or "shell" in out.lower()


def test_doctor_fix_direnv_writes_zshrc(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--fix-direnv"], env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    zshrc = tmp_path / ".zshrc"
    assert zshrc.is_file()
    assert "direnv hook zsh" in zshrc.read_text()


def test_doctor_ok_when_hook_in_sourced_zshrc(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    nested = tmp_path / ".config" / "zsh" / "extra.zsh"
    nested.parent.mkdir(parents=True)
    nested.write_text('eval "$(direnv hook zsh)"\n')
    (tmp_path / ".zshrc").write_text('source "$HOME/.config/zsh/extra.zsh"\n')
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    if not shutil.which("direnv"):
        pytest.skip("direnv not installed")
    assert "set up in your shell" in out or "environment is loaded" in out
    assert "does not load it yet" not in out


def test_doctor_fix_direnv_skips_when_nested_hook_exists(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    nested = tmp_path / ".zsh" / "direnv.zsh"
    nested.parent.mkdir(parents=True)
    nested.write_text('eval "$(direnv hook zsh)"\n')
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("source ~/.zsh/direnv.zsh\n")
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--fix-direnv"], env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "direnv hook" not in zshrc.read_text()
    assert "Added direnv" not in (result.stdout + result.stderr)


def test_doctor_ok_when_hook_present(tmp_path):
    env = spa_env()
    env["HOME"] = str(tmp_path)
    env["SHELL"] = "/bin/zsh"
    (tmp_path / ".zshrc").write_text('eval "$(direnv hook zsh)"\n')
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    if not shutil.which("direnv"):
        pytest.skip("direnv not installed")
    assert "set up in your shell" in out or "environment is loaded" in out
    assert "does not load it yet" not in out


def test_doctor_virtualbox_requires_vagrant(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "vagrant" in out.lower()
    if result.returncode != 0:
        assert "virtualbox" in out.lower() or "vagrant" in out.lower()


def test_vagrant_install_hint_macos_uses_hashicorp_tap(monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    hint = doctor_mod._vagrant_install_hint("darwin")
    assert "brew tap hashicorp/tap" in hint
    assert "hashicorp-vagrant" in hint
    assert "brew install --cask virtualbox" in doctor_mod._virtualbox_install_hint("darwin")


def test_vagrant_install_hint_linux_apt(monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    monkeypatch.setattr(
        doctor_mod.shutil,
        "which",
        lambda name: "/usr/bin/apt-get" if name == "apt-get" else None,
    )
    hint = doctor_mod._vagrant_install_hint("linux")
    assert "apt-get install -y vagrant" in hint
    assert "developer.hashicorp.com/vagrant/install" in hint
    vbox = doctor_mod._virtualbox_install_hint("linux")
    assert "apt-get install -y virtualbox" in vbox


def test_doctor_requires_vagrant_vbguest_plugin(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(doctor_mod, "_virtualbox_version", lambda: "7.0")
    monkeypatch.setattr(doctor_mod, "_vagrant_virtualbox_drivers", lambda: ["6.1", "7.0"])
    monkeypatch.setattr(doctor_mod, "_vagrant_plugin_names", lambda: ["vagrant-scp"])
    monkeypatch.setattr(doctor_mod, "_is_wsl", lambda: False)

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), env_dir=str(dest))
    plugins = next(row for row in result.data["checks"] if row["id"] == "vagrant_plugins")
    assert plugins["level"] == "error"
    assert "vagrant-vbguest" in plugins["message"]
    assert plugins["fix"] == "vagrant plugin install vagrant-vbguest"


def test_doctor_warns_for_wsl_virtualbox_plugin(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(doctor_mod, "_virtualbox_version", lambda: "7.0")
    monkeypatch.setattr(doctor_mod, "_vagrant_virtualbox_drivers", lambda: ["7.0"])
    monkeypatch.setattr(doctor_mod, "_vagrant_plugin_names", lambda: ["vagrant-vbguest"])
    monkeypatch.setattr(doctor_mod, "_is_wsl", lambda: True)

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), env_dir=str(dest))
    wsl = next(row for row in result.data["checks"] if row["id"] == "vagrant_wsl_plugins")
    assert wsl["level"] == "warn"
    assert "virtualbox_WSL2" in wsl["message"]
    assert wsl["fix"] == "vagrant plugin install virtualbox_WSL2"


def test_doctor_missing_vagrant_and_virtualbox_both_instruct(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "lib"))
    from spa import doctor as doctor_mod

    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor_mod, "_virtualbox_version", lambda: None)
    monkeypatch.setattr(doctor_mod, "_vagrant_install_hint", lambda: "brew tap hashicorp/tap && brew install hashicorp/tap/hashicorp-vagrant")
    monkeypatch.setattr(doctor_mod, "_virtualbox_install_hint", lambda: "brew install --cask virtualbox")

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), env_dir=str(dest))
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert by_id["vagrant"]["level"] == "error"
    assert "hashicorp-vagrant" in by_id["vagrant"]["fix"]
    assert by_id["virtualbox"]["level"] == "error"
    assert "cask virtualbox" in by_id["virtualbox"]["fix"]
