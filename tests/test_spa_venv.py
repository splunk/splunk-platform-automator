"""Tests for bin/spa_venv.sh and SPA environment venv selection.

Venv resolution is checked with --path (no side effects). Creation is checked
with --no-install so no pip/galaxy download is needed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, spa_env, write_min_env

pytestmark = pytest.mark.local

SCRIPT = PROJECT_ROOT / "bin" / "spa_venv.sh"


def _run(args, env=None):
    full_env = spa_env()
    full_env.pop("SPA_VENV_DIR", None)
    full_env.pop("SPA_ENV_DIR", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_venv_script_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], cwd=PROJECT_ROOT)
    assert result.returncode == 0


def test_path_defaults_to_shared_venv():
    result = _run(["--path"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_env_venv_wins_when_present(tmp_path):
    dest = tmp_path / "env"
    (dest / ".venv").mkdir(parents=True)
    result = _run(["--path", "--env", str(dest)])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(dest / ".venv")


def test_env_without_venv_falls_back_to_shared(tmp_path):
    dest = tmp_path / "env"
    dest.mkdir()
    result = _run(["--path", "--env", str(dest)])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_env_override_wins(tmp_path):
    dest = tmp_path / "env"
    (dest / ".venv").mkdir(parents=True)
    explicit = tmp_path / "explicit"
    result = _run(
        ["--path", "--env", str(dest)], env={"SPA_VENV_DIR": str(explicit)}
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(explicit)


def test_dir_flag_wins_over_env(tmp_path):
    result = _run(
        ["--path", "--dir", str(tmp_path / "flag")],
        env={"SPA_VENV_DIR": str(tmp_path / "env")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path / "flag")


def test_create_without_install(tmp_path):
    venv = tmp_path / "venv"
    result = _run(["--create", "--no-install", "--dir", str(venv)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert (venv / "bin" / "activate").is_file()


def test_run_venv_script_streams_progress_and_keeps_pip_in_the_log(tmp_path):
    from spa.executil import run_venv_script

    script = tmp_path / "fake_venv.sh"
    script.write_text(
        "#!/bin/bash\n"
        'echo "Creating virtual environment..." >&2\n'
        'echo "Downloading junk that operators should not see"\n'
        'echo "Virtual environment ready: /tmp/example.venv"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    seen = []
    code, stdout, log, progress = run_venv_script(
        ["bash", str(script)], on_step=seen.append
    )
    assert code == 0
    assert stdout.strip() == "Virtual environment ready: /tmp/example.venv"
    assert "Downloading junk" in log
    assert "Downloading junk" not in "\n".join(progress)
    assert seen[0] == "Creating virtual environment..."
    assert seen[-1].startswith("Virtual environment ready:")


def test_spa_venv_create_prints_progress_not_pip(tmp_path):
    dest = write_min_env(tmp_path / "env")
    result = run_spa(
        ["venv", "--environment", "--create", "--no-install", "--yes"],
        cwd=dest,
        env={"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)},
    )
    out = result.stdout
    assert result.returncode == 0, result.stderr + out
    assert "Creating virtual environment..." in out
    assert out.strip().endswith("Virtual environment ready: %s" % (dest / ".venv"))
    assert "Collecting" not in out
    assert "Downloading" not in out


def test_collections_progress_reports_install_and_already_installed(tmp_path):
    """Skipping the collections step silently reads as 'it never ran'."""
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "activate").write_text(
        'PATH="%s:$PATH"\nexport PATH\n' % bin_dir, encoding="utf-8"
    )
    for name in ("pip", "ansible-galaxy"):
        tool = bin_dir / name
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o755)
    collections = tmp_path / "collections"

    missing = _run(
        ["--create", "--dir", str(venv)],
        env={"SPA_COLLECTIONS_DIR": str(collections)},
    )
    assert missing.returncode == 0, missing.stderr + missing.stdout
    assert "Installing Ansible collections..." in missing.stderr

    # Same run once the collections are on disk beside the venv.
    for name in ("community/general", "ansible/posix", "ansible/windows"):
        (collections / "ansible_collections" / name).mkdir(parents=True, exist_ok=True)
    present = _run(
        ["--create", "--dir", str(venv)],
        env={"SPA_COLLECTIONS_DIR": str(collections)},
    )
    assert present.returncode == 0, present.stderr + present.stdout
    assert "Ansible collections already installed" in present.stderr
    assert "Installing Ansible collections..." not in present.stderr


def test_reinstall_runs_requirements_for_existing_venv(tmp_path):
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "pip.log"
    (bin_dir / "activate").write_text(
        'PATH="%s:$PATH"\nexport PATH\n' % bin_dir, encoding="utf-8"
    )
    pip = bin_dir / "pip"
    pip.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$PIP_LOG"\n', encoding="utf-8")
    pip.chmod(0o755)
    galaxy = bin_dir / "ansible-galaxy"
    galaxy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    galaxy.chmod(0o755)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("example-package\n", encoding="utf-8")

    result = _run(
        ["--reinstall", "--dir", str(venv), "--requirements", str(requirements)],
        env={"PIP_LOG": str(log)},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "-r %s" % requirements in log.read_text(encoding="utf-8")


def test_upgrade_bumps_packages_and_collections(tmp_path):
    """--upgrade must pip --upgrade and galaxy --upgrade, never galaxy --force."""
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    pip_log = tmp_path / "pip.log"
    galaxy_log = tmp_path / "galaxy.log"
    (bin_dir / "activate").write_text(
        'PATH="%s:$PATH"\nexport PATH\n' % bin_dir, encoding="utf-8"
    )
    pip = bin_dir / "pip"
    pip.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$PIP_LOG"\n', encoding="utf-8")
    pip.chmod(0o755)
    galaxy = bin_dir / "ansible-galaxy"
    galaxy.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$GALAXY_LOG"\n', encoding="utf-8"
    )
    galaxy.chmod(0o755)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("ansible>=3.4.0\n", encoding="utf-8")
    collections = tmp_path / "collections"
    for name in ("community/general", "ansible/posix", "ansible/windows"):
        (collections / "ansible_collections" / name).mkdir(parents=True)

    result = _run(
        ["--upgrade", "--dir", str(venv), "--requirements", str(requirements)],
        env={
            "PIP_LOG": str(pip_log),
            "GALAXY_LOG": str(galaxy_log),
            "SPA_COLLECTIONS_DIR": str(collections),
        },
    )

    assert result.returncode == 0, result.stderr + result.stdout
    pip_text = pip_log.read_text(encoding="utf-8")
    assert "--upgrade -r %s" % requirements in pip_text
    assert "Upgrading packages..." in result.stderr
    assert "Updating Ansible collections..." in result.stderr
    galaxy_text = galaxy_log.read_text(encoding="utf-8")
    assert "collection install --upgrade" in galaxy_text
    assert "--force" not in galaxy_text
    assert "Ansible collections already installed" not in result.stderr


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("--upgrade", "local"),
        ("--reinstall", "local"),
        ("--create", "local"),
        ("--rebuild", "local_destructive"),
    ],
)
def test_venv_prompt_talks_about_this_machine_not_hosts(monkeypatch, action, expected):
    from spa.confirm import prompt_text

    seen = []
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "n")
    from spa.cli import main

    rc = main(["--no-agent", "venv", "--shared", action])

    assert rc != 0
    assert len(seen) == 1
    label = "%s the shared SPA venv" % action.lstrip("-")
    assert seen == [prompt_text(label, risk=expected)]
    assert "host" not in seen[0]


def test_launcher_reexecs_into_shared_venv_when_interpreter_is_incomplete(tmp_path):
    """A symlinked bin/spa must not run on a python3 without yaml / pydantic."""
    bare = tmp_path / "bare-venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], check=True)
    env = spa_env()
    env.pop("SPA_VENV_DIR", None)
    env["PATH"] = str(bare / "bin") + os.pathsep + env["PATH"]

    probe = subprocess.run(
        [str(bare / "bin" / "python3"), "-c", "import yaml"],
        capture_output=True,
    )
    assert probe.returncode != 0, "test needs an interpreter without PyYAML"
    if not (PROJECT_ROOT / ".venv" / "bin" / "activate").is_file():
        pytest.skip("shared venv not built on this machine")

    result = subprocess.run(
        [str(bare / "bin" / "python3"), str(PROJECT_ROOT / "bin" / "spa"), "--no-agent", "venv", "--path"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_launcher_reexec_is_skipped_when_guard_is_set(tmp_path):
    """One hop only: the guard prevents an exec loop if no venv can run spa."""
    body = (PROJECT_ROOT / "bin" / "spa").read_text(encoding="utf-8")
    assert "SPA_VENV_REEXEC" in body
    assert "os.execv" in body


def _bare_interpreter(tmp_path: Path) -> Path:
    """A venv with no pip and none of SPA's requirements."""
    bare = tmp_path / "bare-venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], check=True)
    python = bare / "bin" / "python3"
    probe = subprocess.run([str(python), "-c", "import yaml"], capture_output=True)
    if probe.returncode == 0:
        pytest.skip("interpreter inherits PyYAML; cannot test the missing-venv path")
    return python


def _run_bare(python: Path, args, env_dir: Path):
    env = spa_env(
        {
            "SPA_HOME": str(PROJECT_ROOT),
            "SPA_ENV_DIR": str(env_dir),
            # Point the pin at nothing so no usable venv can be re-exec'd into.
            "SPA_VENV_DIR": str(env_dir / "no-such-venv"),
            # Test the gate itself, not the launcher hop into SPA_HOME/.venv.
            "SPA_VENV_REEXEC": "1",
        }
    )
    return subprocess.run(
        [str(python), str(PROJECT_ROOT / "bin" / "spa"), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize("command", ["provision", "validate", "deploy", "run"])
def test_commands_needing_the_venv_fail_with_a_named_error(tmp_path, command):
    """A missing requirement must be a named error with a fix, not a traceback."""
    python = _bare_interpreter(tmp_path)
    dest = write_min_env(tmp_path / "env")

    result = _run_bare(python, ["--no-agent", command], dest)

    output = result.stdout + result.stderr
    assert result.returncode == 2, output
    assert "Traceback" not in output
    assert "ModuleNotFoundError" not in output
    assert "spa cannot run this command" in output
    assert "PyYAML" in output and "pydantic" in output
    assert "spa doctor" in output


def test_venv_gate_reports_each_candidate_state(tmp_path):
    python = _bare_interpreter(tmp_path)
    dest = write_min_env(tmp_path / "env")
    (dest / ".venv" / "include").mkdir(parents=True)

    result = _run_bare(python, ["--no-agent", "validate"], dest)

    output = result.stdout + result.stderr
    assert "%s  (incomplete (no bin/activate))" % (dest / ".venv") in output
    assert "%s  (not created)" % (dest / "no-such-venv") in output


def test_venv_gate_is_json_in_agent_mode(tmp_path):
    python = _bare_interpreter(tmp_path)
    dest = write_min_env(tmp_path / "env")

    result = _run_bare(python, ["--agent", "provision", "--yes"], dest)

    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "spa cannot run this command" in payload["error"]
    assert "spa doctor" in payload["error"]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("absent", "Create it:   spa venv --shared --create --yes"),
        ("incomplete", "Repair it:   spa venv --shared --rebuild --yes"),
    ],
)
def test_venv_message_fix_matches_what_is_on_disk(tmp_path, state, expected, monkeypatch):
    """Create vs repair vs reinstall: the advice has to match the real state."""
    from spa.executil import venv_setup_message
    from spa.paths import resolve_spa_paths

    # venv_candidates reads the live SPA_VENV_DIR, not the paths environ.
    monkeypatch.delenv("SPA_VENV_DIR", raising=False)
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    dest = tmp_path / "env"
    dest.mkdir()
    if state == "incomplete":
        (home / ".venv" / "include").mkdir(parents=True)
    env = spa_env({"SPA_HOME": str(home), "SPA_ENV_DIR": str(dest)})
    env.pop("SPA_VENV_DIR", None)
    paths = resolve_spa_paths(start_dir=dest, environ=env)

    message = venv_setup_message(paths, ["yaml"])

    assert "PyYAML is not installed" in message
    assert expected in message


def test_venv_message_points_at_the_launcher_when_the_venv_is_fine(tmp_path, monkeypatch):
    """A healthy venv plus the wrong interpreter is not a requirements gap."""
    from spa.executil import venv_setup_message
    from spa.paths import resolve_spa_paths

    if not (PROJECT_ROOT / ".venv" / "bin" / "activate").is_file():
        pytest.skip("shared venv not built on this machine")
    monkeypatch.delenv("SPA_VENV_DIR", raising=False)
    dest = write_min_env(tmp_path / "env")
    env = spa_env({"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)})
    env.pop("SPA_VENV_DIR", None)
    paths = resolve_spa_paths(start_dir=dest, environ=env)

    message = venv_setup_message(paths, ["yaml"])

    assert "spa started on another interpreter" in message
    assert "Run it through: %s" % (PROJECT_ROOT / "bin" / "spa") in message
    assert "--reinstall" not in message


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["--no-agent", "venv", "--path"], ".venv"),
        (["--no-agent", "doctor"], "SPA host prerequisites"),
        (["--no-agent", "environment", "list"], ""),
        (["--no-agent", "init", "--list"], "single_node"),
    ],
)
def test_bootstrap_commands_still_run_without_a_venv(tmp_path, args, needle):
    """venv / doctor / environment / init are how you get out of that state."""
    python = _bare_interpreter(tmp_path)
    dest = write_min_env(tmp_path / "env")

    result = _run_bare(python, args, dest)

    output = result.stdout + result.stderr
    assert "spa cannot run this command" not in output
    assert "Traceback" not in output
    if needle:
        assert needle in output


def test_lazy_requirement_import_is_reported_as_a_venv_problem(monkeypatch, capsys):
    """boto3 and friends are imported deep in a subcommand, not pre-checked."""
    import spa.cli as cli_mod

    def _boom(_argv):
        raise ModuleNotFoundError("No module named 'boto3'", name="boto3")

    monkeypatch.setattr(cli_mod, "_run", _boom)
    code = cli_mod.main(["--no-agent", "aws"])
    captured = capsys.readouterr()
    assert code == 2
    assert "boto3 is not installed" in captured.err
    assert "Traceback" not in captured.err
    assert "spa doctor" in captured.err


def test_unrelated_import_error_is_not_swallowed(monkeypatch):
    import spa.cli as cli_mod

    def _boom(_argv):
        raise ModuleNotFoundError("No module named 'totally_unrelated'", name="totally_unrelated")

    monkeypatch.setattr(cli_mod, "_run", _boom)
    with pytest.raises(ModuleNotFoundError):
        cli_mod.main(["--no-agent", "aws"])


def test_spa_venv_defaults_to_shared_path_despite_stale_pin(tmp_path):
    stale = tmp_path / "old-clone" / ".venv"
    result = run_spa(
        ["venv", "--path"],
        env={"SPA_VENV_DIR": str(stale)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(PROJECT_ROOT / ".venv")


def test_spa_venv_can_create_environment_venv_without_install(tmp_path):
    dest = write_min_env(tmp_path / "env")
    result = run_spa(
        ["venv", "--environment", "--create", "--no-install", "--yes"],
        cwd=dest,
        env={"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / ".venv" / "bin" / "activate").is_file()


def test_incomplete_venv_is_recreated(tmp_path):
    venv = tmp_path / "broken"
    (venv / "include").mkdir(parents=True)
    result = _run(["--create", "--no-install", "--dir", str(venv)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Recreating incomplete virtual environment" in (result.stderr + result.stdout)
    assert (venv / "bin" / "activate").is_file()


def test_incomplete_venv_reported_with_no_create(tmp_path):
    venv = tmp_path / "broken"
    (venv / "include").mkdir(parents=True)
    result = _run(["--no-create", "--dir", str(venv)])
    assert result.returncode != 0
    assert "incomplete venv" in result.stderr


def test_incomplete_venv_does_not_export_spa_venv_dir(tmp_path):
    """A venv we could not activate must not be pinned for later spa commands."""
    venv = tmp_path / "broken"
    (venv / "include").mkdir(parents=True)
    probe = subprocess.run(
        ["bash", "-c", 'source "$1" --no-create --dir "$2"; echo "SPA_VENV_DIR=[${SPA_VENV_DIR:-}]"',
         "bash", str(SCRIPT), str(venv)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=spa_env(),
    )
    assert "SPA_VENV_DIR=[]" in probe.stdout


def test_no_create_does_not_create(tmp_path):
    venv = tmp_path / "missing"
    result = _run(["--no-create", "--dir", str(venv)])
    assert not venv.exists()
    assert "no venv at" in (result.stderr + result.stdout)


def test_unknown_option_fails():
    result = _run(["--nope"])
    assert result.returncode != 0
    assert "Unknown option" in result.stderr


def test_init_does_not_write_envrc(tmp_path):
    dest = tmp_path / "env"
    result = run_spa_init(["--example", "single_node.yml", "--skip-doctor", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (dest / ".envrc").exists()


def test_collections_install_is_forced_into_target_path():
    body = SCRIPT.read_text()
    assert "collection install --force" in body


def test_collections_not_reinstalled_when_present():
    collections = PROJECT_ROOT / ".collections" / "ansible_collections"
    if not (PROJECT_ROOT / ".venv" / "bin" / "activate").is_file() or not collections.is_dir():
        pytest.skip("shared venv/collections not built on this machine")
    result = _run(["--no-create"])
    assert result.returncode == 0, result.stderr
    assert "Installing Ansible collections" not in (result.stdout + result.stderr)


def test_run_venv_wrapper_uses_tests_venv():
    body = (PROJECT_ROOT / "tests" / "run_venv.sh").read_text()
    assert "bin/spa_venv.sh" in body
    assert ".venv" in body
    result = subprocess.run(
        ["bash", "-n", str(PROJECT_ROOT / "tests" / "run_venv.sh")],
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0
