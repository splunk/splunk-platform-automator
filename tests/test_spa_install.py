"""Framework tarball and install.sh (Distribution M3)."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from spa_testutil import AGENT_ENV_VARS, INHERITED_PATH_VARS, LIB, PROJECT_ROOT, spa_env

pytestmark = pytest.mark.local

PACK = PROJECT_ROOT / "scripts" / "pack-framework.sh"
INSTALL = PROJECT_ROOT / "install.sh"


@pytest.fixture(scope="session")
def framework_tarball(tmp_path_factory):
    out = tmp_path_factory.mktemp("framework") / "spa-framework.tgz"
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
        "sh",
        str(INSTALL),
        "--from",
        str(archive),
        "--skip-venv",
        "--skip-doctor",
        *(extra_args or []),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_pack_framework_excludes_tests_and_lab_config(framework_tarball):
    archive = framework_tarball
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


def test_install_from_tarball_and_extract_anywhere(tmp_path, framework_tarball):
    archive = framework_tarball
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    result = subprocess.run(
        [
            "sh",
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
            "--provider",
            "aws",
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


def test_install_refuses_existing_prefix_without_force(tmp_path, framework_tarball):
    archive = framework_tarball
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "keep.txt").write_text("no")
    result = subprocess.run(
        [
            "sh",
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


def test_install_default_uses_xdg_data_home_and_local_bin(tmp_path, framework_tarball):
    archive = framework_tarball
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


def test_install_honors_absolute_xdg_data_home(tmp_path, framework_tarball):
    archive = framework_tarball
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


def test_install_ignores_relative_xdg_data_home(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    result = _run_install(
        archive, _install_env(home, {"XDG_DATA_HOME": "relative-data"})
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (home / ".local" / "share" / "spa" / "bin" / "spa").is_file()
    assert not (Path.cwd() / "relative-data" / "spa").exists()


def test_install_prefix_and_bindir_override_xdg(tmp_path, framework_tarball):
    archive = framework_tarball
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


def test_install_from_stdin_pipe(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    with INSTALL.open(encoding="utf-8") as handle:
        result = subprocess.run(
            [
                "sh",
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


def _run_uninstall(env, extra_args=None):
    cmd = ["sh", str(INSTALL), "--uninstall", *(extra_args or [])]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_uninstall_default_prefix_and_wrapper(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    env = _install_env(home)
    assert _run_install(archive, env).returncode == 0
    prefix = home / ".local" / "share" / "spa"
    wrapper = home / ".local" / "bin" / "spa"
    assert prefix.is_dir()
    assert wrapper.is_file()
    result = _run_uninstall(env, extra_args=["--yes"])
    assert result.returncode == 0, result.stderr + result.stdout
    assert not prefix.exists()
    assert not wrapper.exists()
    assert "Removed wrapper:" in result.stdout
    assert "Removed prefix:" in result.stdout


def test_uninstall_refuses_non_spa_directory(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "not-spa"
    prefix.mkdir()
    keep = prefix / "keep.txt"
    keep.write_text("stay")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    wrapper = bindir / "spa"
    wrapper.write_text("export SPA_HOME=%s\n" % prefix)
    result = _run_uninstall(
        _install_env(home),
        extra_args=["--yes", "--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode != 0
    assert keep.read_text() == "stay"
    assert wrapper.is_file()
    assert "not an SPA install prefix" in result.stderr


def test_uninstall_prompt_says_user_config_is_kept(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    xdg = tmp_path / "xdg"
    config_dir = xdg / "spa"
    config_dir.mkdir(parents=True)
    (config_dir / "paths.yml").write_text("software_dir: /tmp/Software\n")
    env = _install_env(home, {"XDG_CONFIG_HOME": str(xdg)})
    for name in AGENT_ENV_VARS:
        env.pop(name, None)
    result = subprocess.run(
        ["sh", str(INSTALL), "--uninstall"],
        input="n\n",
        capture_output=True,
        text=True,
        env=env,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    prefix = home / ".local" / "share" / "spa"
    wrapper = home / ".local" / "bin" / "spa"
    assert (
        "uninstall will remove:\n%s\n%s\nconfigs will not be removed:\n%s\n"
        % (prefix, wrapper, config_dir)
    ) in combined
    assert (config_dir / "paths.yml").read_text() == "software_dir: /tmp/Software\n"


def test_uninstall_leaves_user_config_dir(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    xdg = tmp_path / "xdg"
    config_dir = xdg / "spa"
    config_dir.mkdir(parents=True)
    (config_dir / "paths.yml").write_text("software_dir: /tmp/Software\n")
    env = _install_env(home, {"XDG_CONFIG_HOME": str(xdg)})
    assert _run_install(archive, env).returncode == 0
    result = _run_uninstall(env, extra_args=["--yes"])
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert not (home / ".local" / "share" / "spa").exists()
    assert (config_dir / "paths.yml").read_text() == "software_dir: /tmp/Software\n"
    assert "configs will not be removed:\n%s\n" % config_dir in combined


def test_uninstall_leaves_sibling_env_dir(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    env = _install_env(home)
    assert _run_install(archive, env).returncode == 0
    sibling = tmp_path / "envs" / "my-env"
    sibling.mkdir(parents=True)
    (sibling / "config").mkdir()
    (sibling / "config" / "splunk_config.yml").write_text("plugin: splunk-platform-automator\n")
    result = _run_uninstall(env, extra_args=["--yes"])
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (home / ".local" / "share" / "spa").exists()
    assert (sibling / "config" / "splunk_config.yml").is_file()


def test_uninstall_leaves_unrelated_wrapper(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    env = _install_env(home)
    result = _run_install(
        archive,
        env,
        extra_args=["--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    wrapper = bindir / "spa"
    wrapper.write_text("#!/bin/sh\necho other-spa\n")
    result = _run_uninstall(
        env,
        extra_args=["--yes", "--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert not prefix.exists()
    assert wrapper.is_file()
    assert "other-spa" in wrapper.read_text()
    assert "Leaving" in result.stderr


def test_install_without_software_completes_and_next_step_names_software(
    tmp_path, framework_tarball
):
    """install.sh still exits 0 when Software is absent; next-step names Software."""
    home = tmp_path / "home"
    home.mkdir()
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    pybin = tmp_path / "pybin"
    pybin.mkdir()
    (pybin / "python3").symlink_to(sys.executable)
    env = _install_env(
        home,
        {
            "XDG_CONFIG_HOME": str(xdg),
            "PATH": "%s%s%s" % (pybin, os.pathsep, os.environ.get("PATH", "")),
        },
    )
    for name in (*AGENT_ENV_VARS, *INHERITED_PATH_VARS):
        env.pop(name, None)
    result = subprocess.run(
        [
            "sh",
            str(INSTALL),
            "--from",
            str(framework_tarball),
            "--skip-venv",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "Installed wrapper:" in result.stdout
    _, _, next_step = result.stdout.partition("Installed wrapper:")
    assert "Software" in next_step
    assert "spa environment set --create-defaults --yes" in next_step
    assert "spa environment set --software-dir" not in next_step


def _installed_prefix(tmp_path, framework_tarball):
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    result = _run_install(
        framework_tarball,
        _install_env(tmp_path),
        extra_args=["--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    (prefix / "VERSION").write_text("0.0.1-old\n")
    (prefix / "marker.txt").write_text("old tree")
    return prefix, bindir


def _assert_prefix_unchanged(prefix):
    assert (prefix / "VERSION").read_text() == "0.0.1-old\n"
    assert (prefix / "marker.txt").read_text() == "old tree"
    assert (prefix / "bin" / "spa").is_file()
    _assert_no_staging_siblings(prefix)


def _assert_no_staging_siblings(prefix):
    leftovers = [
        p.name
        for p in prefix.parent.iterdir()
        if p.name.startswith(prefix.name + ".new.")
        or p.name.startswith(prefix.name + ".old.")
    ]
    assert leftovers == []


def _force_install(prefix, bindir, archive, env):
    return subprocess.run(
        [
            "sh",
            str(INSTALL),
            "--force",
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
        env=env,
    )


def test_force_from_missing_tarball_keeps_prefix(tmp_path, framework_tarball):
    prefix, bindir = _installed_prefix(tmp_path, framework_tarball)
    result = _force_install(
        prefix, bindir, tmp_path / "missing.tar.gz", _install_env(tmp_path)
    )
    assert result.returncode == 1, result.stderr + result.stdout
    assert "tarball not found" in result.stderr
    _assert_prefix_unchanged(prefix)


def test_force_from_corrupt_tarball_keeps_prefix(tmp_path, framework_tarball):
    prefix, bindir = _installed_prefix(tmp_path, framework_tarball)
    corrupt = tmp_path / "corrupt.tar.gz"
    corrupt.write_text("not a gzip archive\n")
    result = _force_install(prefix, bindir, corrupt, _install_env(tmp_path))
    assert result.returncode == 1, result.stderr + result.stdout
    _assert_prefix_unchanged(prefix)


def test_force_from_tarball_without_bin_spa_keeps_prefix(tmp_path, framework_tarball):
    prefix, bindir = _installed_prefix(tmp_path, framework_tarball)
    tree = tmp_path / "partial"
    (tree / "ansible").mkdir(parents=True)
    (tree / "ansible.cfg").write_text("[defaults]\n")
    partial = tmp_path / "partial.tar.gz"
    with tarfile.open(partial, "w:gz") as tar:
        tar.add(tree, arcname=".")
    result = _force_install(prefix, bindir, partial, _install_env(tmp_path))
    assert result.returncode == 1, result.stderr + result.stdout
    assert "missing ansible.cfg / bin/spa / ansible/" in result.stderr
    _assert_prefix_unchanged(prefix)


def test_force_from_good_tarball_replaces_prefix(tmp_path, framework_tarball):
    prefix, bindir = _installed_prefix(tmp_path, framework_tarball)
    (bindir / "spa").write_text("#!/bin/sh\necho stale\n")
    result = _force_install(prefix, bindir, framework_tarball, _install_env(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (prefix / "marker.txt").exists()
    assert (prefix / "VERSION").read_text() != "0.0.1-old\n"
    assert (prefix / "bin" / "spa").is_file()
    _assert_no_staging_siblings(prefix)
    wrapper = (bindir / "spa").read_text()
    assert "stale" not in wrapper
    assert str(prefix) in wrapper


FAKE_TOKEN = "ghp_faketoken0123456789"

FAKE_CURL = r"""#!/bin/sh
{ for a in "$@"; do printf '%s\n' "$a"; done; echo '---'; } >> "$FAKE_LOG.curl"
[ -n "${FAKE_CURL_FAIL:-}" ] && exit 6
out=""
url=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -H) shift 2 ;;
        -*) shift ;;
        *) url="$1"; shift ;;
    esac
done
case "$url" in
    */releases/latest) printf '{"tag_name": "v9.9.9"}\n' ;;
    */releases/tags/*)
        printf '{"assets": [{"name": "spa-framework-9.9.9.tar.gz", "url": "https://api.github.com/repos/x/y/releases/assets/1"}]}\n' ;;
    *) cp "$FAKE_TARBALL" "$out" ;;
esac
"""

FAKE_GH = r"""#!/bin/sh
{ for a in "$@"; do printf '%s\n' "$a"; done; echo '---'; } >> "$FAKE_LOG.gh"
case "$1 $2" in
    "auth status") exit 0 ;;
    "release view") echo v9.9.9 ;;
    "release download")
        dir=""; pattern=""
        while [ $# -gt 0 ]; do
            case "$1" in
                -D) dir="$2"; shift 2 ;;
                --pattern) pattern="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        cp "$FAKE_TARBALL" "$dir/$pattern" ;;
    *) exit 1 ;;
esac
"""


def _fake_download_env(tmp_path, framework_tarball, with_gh=False, extra=None):
    """Env with fake curl (and optionally gh) first on a minimal PATH without real gh."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    curl = fakebin / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    if with_gh:
        gh = fakebin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
    (fakebin / "python3").symlink_to(sys.executable)
    home = tmp_path / "home"
    home.mkdir()
    env = _install_env(
        home,
        {
            "PATH": "%s:/usr/bin:/bin" % fakebin,
            "FAKE_LOG": str(tmp_path / "fake"),
            "FAKE_TARBALL": str(framework_tarball),
        },
    )
    env.pop("GITHUB_TOKEN", None)
    if extra:
        env.update(extra)
    return env


def _fake_calls(tmp_path, tool):
    log = tmp_path / ("fake." + tool)
    if not log.is_file():
        return []
    calls, cur = [], []
    for line in log.read_text().splitlines():
        if line == "---":
            calls.append(cur)
            cur = []
        else:
            cur.append(line)
    return calls


def _run_download_install(tmp_path, env, extra_args=None):
    """Run a copy of install.sh outside any SPA tree so it must download."""
    script = tmp_path / "standalone" / "install.sh"
    script.parent.mkdir()
    script.write_text(INSTALL.read_text())
    return subprocess.run(
        [
            "sh",
            str(script),
            "--prefix",
            str(tmp_path / "prefix"),
            "--bindir",
            str(tmp_path / "bin"),
            "--skip-venv",
            "--skip-doctor",
            *(extra_args or []),
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def _call_url(call):
    return next(a for a in call if a.startswith("https://"))


def _has_auth(call):
    return any(a.lower().startswith("authorization:") for a in call)


def test_download_anonymous_without_gh_or_token(tmp_path, framework_tarball):
    env = _fake_download_env(tmp_path, framework_tarball)
    result = _run_download_install(tmp_path, env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "prefix" / "bin" / "spa").is_file()
    calls = _fake_calls(tmp_path, "curl")
    urls = [_call_url(c) for c in calls]
    assert urls[0] == (
        "https://api.github.com/repos/splunk/splunk-platform-automator/releases/latest"
    )
    assert urls[-1] == (
        "https://github.com/splunk/splunk-platform-automator/releases/download/"
        "v9.9.9/spa-framework-9.9.9.tar.gz"
    )
    assert not any(_has_auth(c) for c in calls)
    assert "private repo" not in result.stderr


def test_download_with_token_only_sends_it_to_api(tmp_path, framework_tarball):
    env = _fake_download_env(
        tmp_path, framework_tarball, extra={"GITHUB_TOKEN": FAKE_TOKEN}
    )
    result = _run_download_install(tmp_path, env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "prefix" / "bin" / "spa").is_file()
    calls = _fake_calls(tmp_path, "curl")
    assert calls
    for call in calls:
        url = _call_url(call)
        if _has_auth(call):
            assert url.startswith("https://api.github.com/"), url
    assert any(_has_auth(c) for c in calls)
    assert FAKE_TOKEN not in result.stdout + result.stderr


def test_download_ignores_gh_and_uses_curl(tmp_path, framework_tarball):
    env = _fake_download_env(tmp_path, framework_tarball, with_gh=True)
    result = _run_download_install(tmp_path, env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "prefix" / "bin" / "spa").is_file()
    assert _fake_calls(tmp_path, "gh") == []
    urls = [_call_url(c) for c in _fake_calls(tmp_path, "curl")]
    assert urls[-1].startswith(
        "https://github.com/splunk/splunk-platform-automator/releases/download/"
    )


def test_download_offline_keeps_prefix_and_names_from(tmp_path, framework_tarball):
    prefix, bindir = _installed_prefix(tmp_path, framework_tarball)
    env = _fake_download_env(
        tmp_path, framework_tarball, extra={"FAKE_CURL_FAIL": "1"}
    )
    result = _run_download_install(tmp_path, env, extra_args=["--force"])
    assert result.returncode == 1, result.stderr + result.stdout
    assert "offline" in result.stderr
    assert "--from FILE" in result.stderr
    _assert_prefix_unchanged(prefix)


SKILL_MARKER = "self-update-e2e-marker"


def _next_release_tarball(tmp_path, framework_tarball, venv_stub=None):
    tree = tmp_path / "next-tree"
    tree.mkdir()
    with tarfile.open(framework_tarball, "r:gz") as tar:
        tar.extractall(tree)
    (tree / "VERSION").write_text("9.9.9\n")
    skill = tree / "skills" / "spa" / "spa" / "SKILL.md"
    skill.write_text(skill.read_text() + "\n" + SKILL_MARKER + "\n")
    if venv_stub is not None:
        stub = tree / "bin" / "spa_venv.sh"
        stub.write_text(venv_stub)
        stub.chmod(0o755)
    archive = tmp_path / "spa-framework-9.9.9.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tree, arcname=".")
    return archive


def _record_cursor_skill(tmp_path, prefix):
    home = tmp_path / "home"
    dest = home / ".cursor" / "skills" / "spa"
    dest.parent.mkdir(parents=True)
    shutil.copytree(prefix / "skills" / "spa" / "spa", dest)
    config_dir = tmp_path / "xdg" / "spa"
    config_dir.mkdir(parents=True)
    (config_dir / "skills.yml").write_text(
        "# SPA skill copies. Not secrets.\ncopies:\n  - %s\n" % dest
    )
    return home, dest, config_dir


def test_self_update_from_tarball_end_to_end_in_process(tmp_path, framework_tarball):
    sys.path.insert(0, str(LIB))
    from spa.install_kind import classify_install_kind
    from spa.version import _install_runner, self_update

    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    result = _run_install(
        framework_tarball,
        _install_env(tmp_path),
        extra_args=["--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    previous = (prefix / "VERSION").read_text().strip()
    archive = _next_release_tarball(tmp_path, framework_tarball)
    home, dest, config_dir = _record_cursor_skill(tmp_path, prefix)
    env_dir = tmp_path / "envs" / "lab"
    env_dir.mkdir(parents=True)
    (env_dir / "keep.txt").write_text("env\n")

    def runner(argv):
        return _install_runner([*argv, "--skip-venv", "--skip-doctor"], agent=True)

    outcome = self_update(
        prefix,
        spa_bin=str(bindir / "spa"),
        confirm=True,
        agent=True,
        from_file=str(archive),
        runner=runner,
        config_dir=config_dir,
        home=home,
    )
    assert outcome.ok is True, outcome.error
    assert outcome.data["version"] == "9.9.9"
    assert outcome.data["previous"] == previous
    assert (prefix / "VERSION").read_text() == "9.9.9\n"
    assert classify_install_kind(prefix, str(bindir / "spa")) == "prefix"
    assert (config_dir / "skills.yml").is_file()
    assert (env_dir / "keep.txt").read_text() == "env\n"
    assert SKILL_MARKER in (dest / "SKILL.md").read_text()
    assert "spa" in outcome.data["skills"]["updated"]


def _python_shim_venv_stub():
    return (
        "#!/bin/sh\n"
        'home="$(cd "$(dirname "$0")/.." && pwd)"\n'
        'mkdir -p "$home/.venv/bin"\n'
        "printf '#!/bin/sh\\nexec %s \"$@\"\\n' > \"$home/.venv/bin/python\"\n"
        'chmod 0755 "$home/.venv/bin/python"\n'
    ) % sys.executable


def test_self_update_from_tarball_end_to_end_real_process(tmp_path, framework_tarball):
    prefix = tmp_path / "prefix"
    bindir = tmp_path / "bin"
    result = _run_install(
        framework_tarball,
        _install_env(tmp_path),
        extra_args=["--prefix", str(prefix), "--bindir", str(bindir)],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    stub = prefix / "bin" / "spa_venv.sh"
    stub.write_text(_python_shim_venv_stub())
    subprocess.run([str(stub), "--create"], check=True)
    archive = _next_release_tarball(
        tmp_path, framework_tarball, venv_stub=_python_shim_venv_stub()
    )
    env = spa_env(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "PATH": os.pathsep.join(
                [str(bindir), str(Path(sys.executable).parent), "/usr/bin", "/bin"]
            ),
        }
    )
    env.pop("PYTHONPATH", None)
    (tmp_path / "home").mkdir()
    result = subprocess.run(
        [
            str(prefix / ".venv" / "bin" / "python"),
            str(prefix / "bin" / "spa"),
            "--agent",
            "self",
            "update",
            "--from",
            str(archive),
            "--yes",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, result.stdout
    payload = json.loads(lines[0])
    assert payload["ok"] is True
    assert payload["data"]["version"] == "9.9.9"
    assert (prefix / "VERSION").read_text() == "9.9.9\n"


def test_uninstall_agent_without_yes_does_not_delete(tmp_path, framework_tarball):
    archive = framework_tarball
    home = tmp_path / "home"
    home.mkdir()
    env = _install_env(home, {"SPA_AGENT": "1"})
    assert _run_install(archive, env).returncode == 0
    prefix = home / ".local" / "share" / "spa"
    wrapper = home / ".local" / "bin" / "spa"
    result = _run_uninstall(env)
    assert result.returncode != 0
    assert "requires --yes" in result.stderr
    assert prefix.is_dir()
    assert wrapper.is_file()
