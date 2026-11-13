"""Tests for spa doctor host prerequisite checks."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_doctor_passes_on_dev_machine():
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "python3" in (result.stdout + result.stderr).lower()
    assert "SPA host prerequisites" in result.stdout
    # CI has no Software/ dir or shared venv, so doctor may warn and still exit 0.
    assert "All checks passed." in result.stdout or "warning(s). Env may still work" in result.stdout


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


def test_doctor_ok_when_path_spa_is_symlink_to_spa_home(tmp_path):
    other_bin = tmp_path / "local" / "bin"
    other_bin.mkdir(parents=True)
    (other_bin / "spa").symlink_to(PROJECT_ROOT / "bin" / "spa")
    env = spa_env()
    env["PATH"] = str(other_bin) + os.pathsep + env["PATH"]
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "another checkout wins" not in output
    assert f"spa resolves to {PROJECT_ROOT}/bin/spa" in result.stdout


def test_doctor_aws_strict_fails_without_terraform():
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT), "--provider", "aws"], env=env)
    assert result.returncode != 0
    assert "terraform" in (result.stdout + result.stderr).lower()


def _doctor_result(checks, *, ok=True, warnings=0, errors=0, error=None):
    from spa.api import CommandResult

    return CommandResult(
        ok=ok,
        code=0 if ok else 1,
        error=error,
        data={
            "spa_home": str(PROJECT_ROOT),
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "notes": ["ignored banner note"],
        },
    )


def _capture_run_doctor(monkeypatch, result, tmp_path):
    from spa.init import InitError, _LOG, run_doctor

    monkeypatch.setattr("spa.doctor.collect_checks", lambda **kwargs: result)
    log = []
    token = _LOG.set(log)
    raised = None
    try:
        run_doctor(tmp_path / "env", PROJECT_ROOT, skip=False)
    except InitError as exc:
        raised = exc
    finally:
        _LOG.reset(token)
    return log, raised


def test_run_doctor_silent_when_all_ok(monkeypatch, tmp_path):
    result = _doctor_result(
        [
            {
                "level": "ok",
                "id": "python",
                "message": "python3 (3.12) with venv module",
                "fix": "",
            }
        ]
    )
    log, raised = _capture_run_doctor(monkeypatch, result, tmp_path)
    assert raised is None
    assert log == []


def test_run_doctor_prints_only_warn_and_fail_rows(monkeypatch, tmp_path):
    from spa.init import InitError

    result = _doctor_result(
        [
            {
                "level": "ok",
                "id": "python",
                "message": "python3 (3.12) with venv module",
                "fix": "",
            },
            {
                "level": "warn",
                "id": "spa",
                "message": "another checkout wins",
                "fix": "put this checkout first on PATH",
            },
            {
                "level": "error",
                "id": "ccm_token",
                "message": "CCM_TOKEN: not set",
                "fix": "Set CCM_TOKEN to a CCM personal access token",
            },
        ],
        ok=False,
        warnings=1,
        errors=1,
        error="1 required check(s) failed.",
    )
    log, raised = _capture_run_doctor(monkeypatch, result, tmp_path)
    assert isinstance(raised, InitError)
    blob = str(raised)
    assert log == []
    assert "Host prerequisite check failed" in blob
    assert "SPA host prerequisites" not in blob
    assert "All checks passed." not in blob
    assert "python3 (3.12) with venv module" not in blob
    assert "ignored banner note" not in blob
    assert "WARN another checkout wins" in blob
    assert "put this checkout first on PATH" in blob
    assert "FAIL CCM_TOKEN: not set" in blob
    assert "Set CCM_TOKEN to a CCM personal access token" in blob


def test_run_doctor_prints_warnings_and_still_succeeds(monkeypatch, tmp_path):
    result = _doctor_result(
        [
            {
                "level": "ok",
                "id": "python",
                "message": "python3 (3.12) with venv module",
                "fix": "",
            },
            {
                "level": "warn",
                "id": "spa",
                "message": "another checkout wins",
                "fix": "put this checkout first on PATH",
            },
        ],
        warnings=1,
    )
    log, raised = _capture_run_doctor(monkeypatch, result, tmp_path)
    assert raised is None
    blob = "\n".join(log)
    assert "SPA host prerequisites" not in blob
    assert "All checks passed." not in blob
    assert "python3 (3.12) with venv module" not in blob
    assert "WARN another checkout wins" in blob
    assert "put this checkout first on PATH" in blob


def test_init_stays_quiet_when_doctor_passes_and_surfaces_failures(tmp_path):
    dest = tmp_path / "env"
    result = run_spa(
        ["init", "--example", "cm_2idxc_sh", "--provider", "aws", str(dest)],
        extra_env={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    out = result.stderr + result.stdout
    assert "SPA host prerequisites" not in out
    assert "All checks passed." not in out
    if result.returncode != 0:
        assert "terraform" in out.lower() or "FAIL" in out or "WARN" in out
    else:
        assert dest.exists()


def test_init_skip_doctor(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SPA host prerequisites" not in (result.stdout + result.stderr)


def test_doctor_skips_vagrant_without_virtualbox(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(
        ["--example", "cm_2idxc_sh", "--provider", "aws", "--skip-doctor", str(dest)]
    )
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "vagrant required" not in out.lower()
    assert "vagrant is on PATH" not in out


def test_doctor_external_requires_ssh_not_terraform(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(
        ["--example", "single_node", "--provider", "aws", "--skip-doctor", str(dest)]
    )
    config = dest / "config" / "splunk_config.yml"
    config.write_text(
        "---\nexternal: {}\nsplunk_hosts:\n  - name: shidx\n    roles: [indexer]\n",
        encoding="utf-8",
    )
    empty = tmp_path / "no-ssh"
    empty.mkdir()
    env = spa_env()
    env["PATH"] = str(empty)
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--env", str(dest)], env=env
    )
    out = result.stdout + result.stderr
    assert "required for terraform.aws" not in out
    assert "ssh required for external hosts" in out


def test_config_providers_ignores_commented_external():
    from spa.doctor import _config_providers

    assert "external" not in _config_providers("# external: {}\nvirtualbox: {}\n")
    assert _config_providers("external: {}\n") == {"external"}


def test_doctor_checks_env_provider_without_env_flag(tmp_path):
    """spa doctor from an env dir must check that env's provider tools."""
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)})
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env, cwd=dest)
    out = result.stdout + result.stderr
    assert "provider tools checked for: virtualbox" in out
    assert "vagrant required for VirtualBox" in out
    assert result.returncode != 0


def test_doctor_reports_when_config_has_no_provider(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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
    # a top-level aws: key is not terraform.aws
    assert _config_providers("aws:\n  region: eu-central-1\n") == set()
    # comments and host-level keys must not pull in tool checks
    assert _config_providers("# virtualbox: nope\nsplunk_hosts:\n  - virtualbox: {}\n") == set()
    assert _config_providers("ccm:\n  instance_type: t3a.medium\n") == {"ccm"}
    assert _config_providers("# ccm: nope\nsplunk_hosts:\n  - ccm: {}\n") == set()


def test_doctor_env_provider_terraform_aws(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(
        ["--example", "cm_2idxc_sh", "--provider", "aws", "--skip-doctor", str(dest)]
    )
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
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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


def test_doctor_warns_when_spa_venv_dir_points_outside_checkout(tmp_path, monkeypatch):
    stale = tmp_path / "old-checkout" / ".venv"
    (stale / "bin").mkdir(parents=True)
    (stale / "bin" / "activate").write_text("", encoding="utf-8")
    (stale / "bin" / "python").symlink_to(sys.executable)
    monkeypatch.setenv("SPA_VENV_DIR", str(stale))

    from spa import doctor as doctor_mod

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT))
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert by_id["spa_venv_pin"]["level"] == "warn"
    assert "outside this SPA_HOME/environment" in by_id["spa_venv_pin"]["message"]
    assert "unset SPA_VENV_DIR" in by_id["spa_venv_pin"]["fix"]


def test_doctor_warns_when_venv_cannot_import_requirements(tmp_path, monkeypatch):
    """An activatable venv with a half-finished install must not look healthy."""
    stale = tmp_path / "old-checkout" / ".venv"
    (stale / "bin").mkdir(parents=True)
    (stale / "bin" / "activate").write_text("", encoding="utf-8")
    (stale / "bin" / "python3").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (stale / "bin" / "python3").chmod(0o755)
    monkeypatch.setenv("SPA_VENV_DIR", str(stale))

    from spa import doctor as doctor_mod

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT))
    packages = next(row for row in result.data["checks"] if row["id"] == "spa_venv_packages")
    assert packages["level"] == "warn"
    assert str(stale) in packages["message"]
    assert "cannot import yaml / pydantic" in packages["message"]
    assert packages["fix"] == "spa venv reinstall --shared --yes"
    # The broken pin must not be selected as the venv spa runs tools from.
    selected = next(row for row in result.data["checks"] if row["id"] == "spa_venv")
    assert str(stale) not in selected["message"]


def test_doctor_virtualbox_requires_vagrant(tmp_path):
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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
    run_spa_init(["--example", "single_node", "--provider", "virtualbox", "--skip-doctor", str(dest)])
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


def test_doctor_ccm_flag_fails_when_token_not_set(monkeypatch):
    monkeypatch.delenv("CCM_TOKEN", raising=False)
    from spa import doctor as doctor_mod

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), provider=["ccm"])
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert by_id["ccm_token"]["level"] == "error"
    assert by_id["ccm_token"]["message"] == "CCM_TOKEN: not set"
    assert "https://ccm.splunkits.io/" in by_id["ccm_token"]["fix"]
    assert result.ok is False
    assert "ccm_api" not in by_id


def test_doctor_ccm_reports_token_set_and_api_reachable(monkeypatch):
    monkeypatch.setenv("CCM_TOKEN", "test-ccm-pat-value")
    from spa import doctor as doctor_mod
    from spa.providers import ccm as ccm_mod

    monkeypatch.setattr(ccm_mod, "ping", lambda client=None: None)
    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), provider=["ccm"])
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert by_id["ccm_token"]["level"] == "ok"
    assert by_id["ccm_token"]["message"] == "CCM_TOKEN: set"
    assert by_id["ccm_api"]["level"] == "ok"
    assert "reachable" in by_id["ccm_api"]["message"].lower()
    blob = json.dumps(result.data)
    assert "test-ccm-pat-value" not in blob


def test_doctor_ccm_api_failure_does_not_print_token(monkeypatch):
    from spa.providers.ccm import CcmError

    monkeypatch.setenv("CCM_TOKEN", "test-ccm-pat-value")
    from spa import doctor as doctor_mod
    from spa.providers import ccm as ccm_mod

    def _boom(client=None):
        raise CcmError("CCM API returned HTTP 401")

    monkeypatch.setattr(ccm_mod, "ping", _boom)
    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), provider=["ccm"])
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert by_id["ccm_token"]["message"] == "CCM_TOKEN: set"
    assert by_id["ccm_api"]["level"] == "error"
    assert "HTTP 401" in by_id["ccm_api"]["message"]
    blob = json.dumps(result.data)
    assert "test-ccm-pat-value" not in blob
    assert result.ok is False


def test_doctor_ccm_env_checks_token_without_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("CCM_TOKEN", raising=False)
    dest = tmp_path / "env"
    run_spa_init(["--example", "single_node", "--provider", "ccm", "--skip-doctor", str(dest)])
    from spa import doctor as doctor_mod

    result = doctor_mod.collect_checks(spa_home=str(PROJECT_ROOT), env_dir=str(dest))
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert "provider tools checked for: ccm" in by_id["provider"]["message"]
    assert by_id["ccm_token"]["message"] == "CCM_TOKEN: not set"
    assert by_id["ccm_token"]["level"] == "error"


def test_doctor_ccm_cli_flag_reports_token_not_set():
    env = spa_env()
    env.pop("CCM_TOKEN", None)
    result = run_spa(
        ["doctor", "--spa-home", str(PROJECT_ROOT), "--provider", "ccm"], env=env
    )
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "CCM_TOKEN: not set" in out
    assert "CCM_TOKEN: set" not in out


def test_doctor_provider_flag_is_repeatable(monkeypatch):
    monkeypatch.delenv("CCM_TOKEN", raising=False)
    from spa import doctor as doctor_mod

    result = doctor_mod.collect_checks(
        spa_home=str(PROJECT_ROOT), provider=["aws", "ccm"]
    )
    by_id = {row["id"]: row for row in result.data["checks"]}
    assert "terraform.aws" in by_id["provider"]["message"]
    assert "ccm" in by_id["provider"]["message"]
    assert by_id["ccm_token"]["message"] == "CCM_TOKEN: not set"


def test_doctor_unknown_provider_names_legal_values():
    result = run_spa(["--no-agent", "doctor", "--provider", "gcp"])
    assert result.returncode == 2, result.stderr
    assert "Unknown provider: gcp" in result.stderr
    assert "spa doctor --provider ccm" in result.stderr
    assert result.stdout.strip() == ""


SOFTWARE_IDS = ("software_binaries", "software_baseconfigs", "software_licenses")
LICENSE_XML = "<license><payload>SECRET_LICENSE_XML_PAYLOAD</payload></license>\n"
ENTERPRISE_TGZ = "splunk-9.4.0-linux-x86_64.tgz"
FORWARDER_TGZ = "splunkforwarder-9.4.0-linux-x86_64.tgz"
ENTERPRISE_URL = "https://www.splunk.com/en_us/download/splunk-enterprise.html"
FORWARDER_URL = "https://www.splunk.com/en_us/download/universal-forwarder.html"


def _isolate_dirs(tmp_path, monkeypatch, *, software=None, baseconfig=None):
    """tmp spa_home plus isolated HOME / XDG so ../Software and ../baseconfigs cannot leak."""
    spa_home = tmp_path / "spa_home"
    spa_home.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    if software is None:
        software = tmp_path / "Software"
    if baseconfig is None:
        baseconfig = tmp_path / "baseconfigs"
    monkeypatch.setenv("SPA_SOFTWARE_DIR", str(software))
    monkeypatch.setenv("SPA_BASECONFIG_DIR", str(baseconfig))
    return spa_home, software, baseconfig


def _collect_software(spa_home, **kwargs):
    from spa import doctor as doctor_mod

    return doctor_mod.collect_checks(spa_home=str(spa_home), **kwargs)


def _software_rows(result):
    by_id = {row["id"]: row for row in result.data["checks"]}
    return {ident: by_id[ident] for ident in SOFTWARE_IDS}


def _seed_baseconfig_markers(software):
    (software / "Configurations - Base" / "org_s2_indexer_indexes").mkdir(parents=True)
    (software / "Configurations - Index Replication" / "org_cluster_manager_base").mkdir(
        parents=True
    )


def test_doctor_software_empty_dir_warns_all_three_buckets(tmp_path, monkeypatch):
    spa_home, software, baseconfig = _isolate_dirs(tmp_path, monkeypatch)
    software.mkdir()
    baseconfig.mkdir()
    result = _collect_software(spa_home)
    rows = _software_rows(result)
    for ident, row in rows.items():
        assert row["level"] == "warn", ident
    assert str(software) in rows["software_binaries"]["message"]
    assert str(software) in rows["software_licenses"]["message"]
    assert str(baseconfig) in rows["software_baseconfigs"]["message"]
    assert str(software) not in rows["software_baseconfigs"]["message"]
    assert result.ok is True
    assert result.code == 0
    binaries = rows["software_binaries"]
    assert ENTERPRISE_URL in binaries["fix"]
    assert FORWARDER_URL in binaries["fix"]
    assert "SPA_HOME" in binaries["fix"]
    baseconfigs = rows["software_baseconfigs"]
    assert "go/baseconfigs" in baseconfigs["fix"]
    assert "Configurations - Base" in baseconfigs["fix"]
    assert "--baseconfig-dir" in baseconfigs["fix"]
    licenses = rows["software_licenses"]
    assert "spa licenses list" in licenses["fix"]
    assert "trial" in licenses["message"].lower() or "trial" in licenses["fix"].lower()


def test_doctor_software_missing_dir_warns_all_three_and_names_path(tmp_path, monkeypatch):
    spa_home, software, baseconfig = _isolate_dirs(tmp_path, monkeypatch)
    assert not software.exists()
    assert not baseconfig.exists()
    result = _collect_software(spa_home)
    rows = _software_rows(result)
    for ident, row in rows.items():
        assert row["level"] == "warn", ident
    assert str(software) in rows["software_binaries"]["message"]
    assert str(software) in rows["software_licenses"]["message"]
    assert str(baseconfig) in rows["software_baseconfigs"]["message"]
    assert "spa environment set --software-dir" in rows["software_binaries"]["fix"]
    assert "spa environment set --software-dir" in rows["software_licenses"]["fix"]
    assert "spa environment set --baseconfig-dir" in rows["software_baseconfigs"]["fix"]
    assert "spa environment set --software-dir" not in rows["software_baseconfigs"]["fix"]
    assert result.ok is True
    assert result.code == 0


@pytest.mark.parametrize("filename", [ENTERPRISE_TGZ, FORWARDER_TGZ])
def test_doctor_software_binaries_need_enterprise_and_forwarder(
    tmp_path, monkeypatch, filename
):
    spa_home, software, _baseconfig = _isolate_dirs(tmp_path, monkeypatch)
    software.mkdir()
    (software / filename).write_bytes(b"")
    result = _collect_software(spa_home)
    binaries = _software_rows(result)["software_binaries"]
    assert binaries["level"] == "warn"
    assert str(software) in binaries["message"]
    assert ENTERPRISE_URL in binaries["fix"]
    assert FORWARDER_URL in binaries["fix"]


def test_doctor_markers_only_under_software_dir_warn_baseconfigs(tmp_path, monkeypatch):
    spa_home, software, baseconfig = _isolate_dirs(tmp_path, monkeypatch)
    software.mkdir()
    (software / ENTERPRISE_TGZ).write_bytes(b"")
    (software / FORWARDER_TGZ).write_bytes(b"")
    _seed_baseconfig_markers(software)
    (software / "Splunk_Enterprise.lic").write_text(LICENSE_XML, encoding="utf-8")
    result = _collect_software(spa_home)
    rows = _software_rows(result)
    assert rows["software_binaries"]["level"] == "ok"
    assert rows["software_licenses"]["level"] == "ok"
    assert rows["software_baseconfigs"]["level"] == "warn"
    assert str(baseconfig) in rows["software_baseconfigs"]["message"]
    assert str(software) not in rows["software_baseconfigs"]["message"]
    assert "--baseconfig-dir" in rows["software_baseconfigs"]["fix"]


def test_doctor_software_inventory_ok_when_all_three_buckets_present(tmp_path, monkeypatch):
    spa_home, software, baseconfig = _isolate_dirs(tmp_path, monkeypatch)
    software.mkdir()
    (software / ENTERPRISE_TGZ).write_bytes(b"")
    (software / FORWARDER_TGZ).write_bytes(b"")
    _seed_baseconfig_markers(baseconfig)
    (software / "Splunk_Enterprise.lic").write_text(LICENSE_XML, encoding="utf-8")
    result = _collect_software(spa_home)
    rows = _software_rows(result)
    assert rows["software_binaries"]["level"] == "ok"
    assert str(software) in rows["software_binaries"]["message"]
    assert rows["software_licenses"]["level"] == "ok"
    assert str(software) in rows["software_licenses"]["message"]
    assert rows["software_baseconfigs"]["level"] == "ok"
    assert str(baseconfig) in rows["software_baseconfigs"]["message"]
    assert str(software) not in rows["software_baseconfigs"]["message"]
    blob = json.dumps(result.data)
    assert "SECRET_LICENSE_XML_PAYLOAD" not in blob
    assert "<license>" not in blob
    assert LICENSE_XML.strip() not in blob
    assert result.ok is True


def test_doctor_software_warnings_do_not_fail_cli(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    baseconfig = tmp_path / "baseconfigs"
    baseconfig.mkdir()
    env = spa_env(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "SPA_SOFTWARE_DIR": str(software),
            "SPA_BASECONFIG_DIR": str(baseconfig),
        }
    )
    result = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert str(software) in out
    assert str(baseconfig) in out
    assert "WARN" in out
    assert ENTERPRISE_URL in out
    assert "go/baseconfigs" in out
    assert "--baseconfig-dir" in out
    assert "spa licenses list" in out


def test_doctor_cli_json_never_prints_license_xml(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    (software / ENTERPRISE_TGZ).write_bytes(b"")
    (software / FORWARDER_TGZ).write_bytes(b"")
    (software / "Splunk_Enterprise.lic").write_text(LICENSE_XML, encoding="utf-8")
    baseconfig = tmp_path / "baseconfigs"
    _seed_baseconfig_markers(baseconfig)
    env = spa_env(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "SPA_SOFTWARE_DIR": str(software),
            "SPA_BASECONFIG_DIR": str(baseconfig),
        }
    )
    human = run_spa(["doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    agent = run_spa(["--json", "doctor", "--spa-home", str(PROJECT_ROOT)], env=env)
    blob = human.stdout + human.stderr + agent.stdout + agent.stderr
    assert human.returncode == 0, human.stderr + human.stdout
    assert agent.returncode == 0, agent.stderr + agent.stdout
    payload = json.loads(agent.stdout)
    rows = {row["id"]: row for row in payload["data"]["checks"]}
    assert rows["software_binaries"]["level"] == "ok"
    assert str(software) in rows["software_binaries"]["message"]
    assert rows["software_licenses"]["level"] == "ok"
    assert str(software) in rows["software_licenses"]["message"]
    assert rows["software_baseconfigs"]["level"] == "ok"
    assert str(baseconfig) in rows["software_baseconfigs"]["message"]
    assert str(software) not in rows["software_baseconfigs"]["message"]
    assert "SECRET_LICENSE_XML_PAYLOAD" not in blob
    assert "<license>" not in blob


def test_doctor_software_strict_promotes_warnings(tmp_path, monkeypatch):
    spa_home, software, _baseconfig = _isolate_dirs(tmp_path, monkeypatch)
    software.mkdir()
    result = _collect_software(spa_home, strict=True)
    rows = _software_rows(result)
    assert all(row["level"] == "warn" for row in rows.values())
    assert result.ok is False
    assert result.code == 1
    assert "warning" in (result.error or "").lower()
