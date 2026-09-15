"""Framework tarball and install.sh (Distribution M3)."""

import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from spa_testutil import PROJECT_ROOT, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

PACK = PROJECT_ROOT / "scripts" / "pack-framework.sh"
INSTALL = PROJECT_ROOT / "install.sh"


def _pack(tmp_path: Path) -> Path:
    out = tmp_path / "spa-framework.tgz"
    result = subprocess.run(
        ["bash", str(PACK), "-o", str(out)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert out.is_file()
    return out


def _install_env(home: Path, extra=None):
    env = os.environ.copy()
    env["HOME"] = str(home)
    for name in ("SPA_PREFIX", "SPA_BINDIR", "XDG_DATA_HOME"):
        env.pop(name, None)
    if extra:
        env.update(extra)
    return env


def _run_install(archive: Path, env, extra_args=None):
    cmd = [
        "bash",
        str(INSTALL),
        "--from",
        str(archive),
        "--skip-venv",
        "--skip-doctor",
        *(extra_args or []),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_pack_framework_excludes_tests_and_lab_config(tmp_path):
    archive = _pack(tmp_path)
    names = [
        name[2:] if name.startswith("./") else name
        for name in tarfile.open(archive).getnames()
    ]
    assert "ansible.cfg" in names
    assert "bin/spa" in names
    assert "install.sh" in names
    assert "defaults/aws.yml" in names
    assert "template/terraform_aws.tfvars.j2" in names
    assert not any(n == "tests" or n.startswith("tests/") for n in names)
    assert not any(n.startswith(".git/") or n == ".git" for n in names)
    assert "config/splunk_config.yml" not in names
    assert not any(n.startswith("inventory/") for n in names)


def test_install_from_tarball_and_extract_anywhere(tmp_path):
    archive = _pack(tmp_path)
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    result = subprocess.run(
        [
            "bash",
            str(INSTALL),
            "--from",
            str(archive),
            "--prefix",
            str(prefix),
            "--bindir",
            str(bindir),
            "--skip-venv",
            "--skip-doctor",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (prefix / "bin" / "spa").is_file()
    assert (prefix / "ansible.cfg").is_file()
    assert not (prefix / "tests").exists()
    wrapper = bindir / "spa"
    assert wrapper.is_file()
    text = wrapper.read_text()
    assert str(prefix) in text
    assert "GITHUB_TOKEN" not in text

    env = spa_env()
    env["PYTHONPATH"] = str(prefix / "lib")
    env["SPA_HOME"] = str(prefix)
    help_run = subprocess.run(
        [sys.executable, str(prefix / "bin" / "spa"), "--help"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(prefix),
    )
    assert help_run.returncode == 0, help_run.stderr + help_run.stdout
    assert "init" in help_run.stdout

    extract = tmp_path / "anywhere"
    extract.mkdir()
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(extract)], check=True)
    # spa init creates SPA_HOME/.venv when missing; stub activate so tests skip pip.
    activate = extract / ".venv" / "bin" / "activate"
    activate.parent.mkdir(parents=True)
    activate.write_text("# test stub\n")
    env["PYTHONPATH"] = str(extract / "lib")
    env["SPA_HOME"] = str(extract)
    dest = tmp_path / "env"
    init = subprocess.run(
        [
            sys.executable,
            str(extract / "bin" / "spa"),
            "init",
            "--skip-doctor",
            "--example",
            "single_node.yml",
            str(dest),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(extract),
    )
    assert init.returncode == 0, init.stderr + init.stdout
    spa_yml = yaml.safe_load((dest / ".spa.yml").read_text())
    assert Path(spa_yml["spa_home"]).resolve() == extract.resolve()
    assert (dest / "config" / "splunk_config.yml").is_file()
    assert not (dest / "ansible").exists()


def test_install_refuses_existing_prefix_without_force(tmp_path):
    archive = _pack(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "keep.txt").write_text("no")
    result = subprocess.run(
        [
            "bash",
            str(INSTALL),
            "--from",
            str(archive),
            "--prefix",
            str(prefix),
            "--bindir",
            str(tmp_path / "bin"),
            "--skip-venv",
            "--skip-doctor",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert (prefix / "keep.txt").read_text() == "no"


def test_install_default_uses_xdg_data_home_and_local_bin(tmp_path):
    archive = _pack(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    result = _run_install(archive, _install_env(home))
    assert result.returncode == 0, result.stderr + result.stdout
    prefix = home / ".local" / "share" / "spa"
    bindir = home / ".local" / "bin"
    assert (prefix / "bin" / "spa").is_file()
    wrapper = bindir / "spa"
    assert wrapper.is_file()
    text = wrapper.read_text()
    assert str(prefix) in text
    assert "GITHUB_TOKEN" not in text
    assert "SPA_HOME=" + str(prefix) in result.stdout


def test_install_honors_absolute_xdg_data_home(tmp_path):
    archive = _pack(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    data = tmp_path / "xdg-data"
    result = _run_install(
        archive, _install_env(home, {"XDG_DATA_HOME": str(data)})
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (data / "spa" / "bin" / "spa").is_file()
    assert not (home / ".local" / "share" / "spa").exists()
    assert (home / ".local" / "bin" / "spa").is_file()


def test_install_ignores_relative_xdg_data_home(tmp_path):
    archive = _pack(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    result = _run_install(
        archive, _install_env(home, {"XDG_DATA_HOME": "relative-data"})
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (home / ".local" / "share" / "spa" / "bin" / "spa").is_file()
    assert not (Path.cwd() / "relative-data" / "spa").exists()


def test_install_prefix_and_bindir_override_xdg(tmp_path):
    archive = _pack(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "custom-prefix"
    bindir = tmp_path / "custom-bin"
    result = _run_install(
        archive,
        _install_env(home, {"XDG_DATA_HOME": str(tmp_path / "ignored")}),
        extra_args=["--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (prefix / "bin" / "spa").is_file()
    assert (bindir / "spa").is_file()
    assert not (tmp_path / "ignored" / "spa").exists()
    assert not (home / ".local" / "share" / "spa").exists()


def test_install_from_stdin_pipe(tmp_path):
    archive = _pack(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    with INSTALL.open(encoding="utf-8") as handle:
        result = subprocess.run(
            [
                "bash",
                "-s",
                "--",
                "--from",
                str(archive),
                "--prefix",
                str(prefix),
                "--bindir",
                str(bindir),
                "--skip-venv",
                "--skip-doctor",
            ],
            stdin=handle,
            capture_output=True,
            text=True,
            env=_install_env(home),
        )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (prefix / "bin" / "spa").is_file()
    assert (bindir / "spa").is_file()
