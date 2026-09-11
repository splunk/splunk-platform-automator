"""Scaffold, migrate, and convert SPA environment directories (`spa init`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from spa.paths import is_spa_home

FRAMEWORK_LEFTOVERS = (
    "ansible",
    "bin",
    "tests",
    "skills",
    "examples",
    "docs",
    "defaults",
    "template",
    "scripts",
    "lib",
    ".github",
    ".cursor",
    ".agent",
    ".git",
    "Vagrantfile",
    "ansible.cfg",
    "requirements.txt",
    "requirements.yml",
    "CHANGELOG.md",
    "README.md",
    "ROADMAP.md",
    "AGENTS.md",
    "RELEASE.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitattributes",
    ".gitmodules",
)

KEEP_HINT = (
    "config/ (including splunk_config.yml)",
    "inventory/",
    "terraform/aws state, tfvars, .terraform",
    "saved_base_config_apps/",
    ".vault_pass*",
)


class InitError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def has_config(root: Path) -> bool:
    return (root / "config" / "splunk_config.yml").is_file()


def is_spa_env(root: Path) -> bool:
    return (root / ".spa.yml").is_file()


def is_old_clone_tree(root: Path) -> bool:
    return (root / "ansible").is_dir() and has_config(root)


def ensure_env_dirs(dest: Path) -> None:
    for rel in ("config", "inventory", "terraform/aws", "saved_base_config_apps"):
        (dest / rel).mkdir(parents=True, exist_ok=True)
    hosts = dest / "inventory" / "hosts"
    if not hosts.exists():
        hosts.write_text("", encoding="utf-8")


def write_spa_yml(dest: Path, spa_home: Path) -> tuple:
    software_dir = ""
    apps_dir = ""
    for candidate in (dest / "../Software", spa_home / "../Software", spa_home / "Software"):
        if candidate.is_dir():
            software_dir = str(candidate.resolve())
            break
    for candidate in (dest / "../apps", spa_home / "../apps", spa_home / "apps"):
        if candidate.is_dir():
            apps_dir = str(candidate.resolve())
            break
    lines = [
        "# Splunk Platform Automator env pointer.",
        "# Framework stays in spa_home. Do not copy ansible/ into this directory.",
        "spa_home: %s" % spa_home,
    ]
    if software_dir:
        lines.append("software_dir: %s" % software_dir)
        lines.append("baseconfig_dir: %s" % software_dir)
    if apps_dir:
        lines.append("apps_dir: %s" % apps_dir)
    (dest / ".spa.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return software_dir, apps_dir


def write_envrc(dest: Path, spa_home: Path) -> None:
    body = """# Splunk Platform Automator env (direnv). Enable with: direnv allow
# Activates the venv (env .venv when present, else SPA_HOME/.venv) and exports
# SPA_HOME / SPA_ENV_DIR / ANSIBLE_* so ansible-playbook uses this env.
export SPA_HOME="%s"
export SPA_ENV_DIR="$(pwd)"
unset SPLUNK_CONFIG_FILE
if declare -f PATH_add >/dev/null 2>&1; then
    PATH_add "${SPA_HOME}/bin"
else
    export PATH="${SPA_HOME}/bin:${PATH}"
fi
source "${SPA_HOME}/bin/spa_venv.sh" --no-create --env "${SPA_ENV_DIR}"
eval "$("${SPA_HOME}/bin/spa" env --export)"
""" % spa_home
    (dest / ".envrc").write_text(body, encoding="utf-8")


def link_terraform_modules(dest: Path, spa_home: Path) -> None:
    dest_tf = dest / "terraform" / "aws"
    src_tf = spa_home / "terraform" / "aws"
    dest_tf.mkdir(parents=True, exist_ok=True)
    if not src_tf.is_dir():
        return
    for tf in src_tf.glob("*.tf"):
        target = dest_tf / tf.name
        if target.exists() or target.is_symlink():
            target.unlink()
        os.symlink(tf.resolve(), target)


def transfer_path(src: Path, dest: Path, keep_source: bool) -> None:
    if not src.exists() and not src.is_symlink():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir() and not src.is_symlink():
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest, follow_symlinks=False)
    if not keep_source:
        if src.is_dir() and not src.is_symlink():
            shutil.rmtree(src)
        else:
            src.unlink()


def migrate_state(src: Path, dest: Path, spa_home: Path, keep_source: bool) -> None:
    ensure_env_dirs(dest)
    if (src / "config").is_dir():
        for item in src.joinpath("config").iterdir():
            transfer_path(item, dest / "config" / item.name, keep_source)
        if not keep_source:
            try:
                src.joinpath("config").rmdir()
            except OSError:
                pass
    if (src / "inventory").is_dir():
        for item in src.joinpath("inventory").iterdir():
            transfer_path(item, dest / "inventory" / item.name, keep_source)
        if not keep_source:
            try:
                src.joinpath("inventory").rmdir()
            except OSError:
                pass
    src_tf = src / "terraform" / "aws"
    dest_tf = dest / "terraform" / "aws"
    for name in (
        "terraform.tfvars",
        "terraform.tfstate",
        "terraform.tfstate.backup",
        "tfplan",
        ".terraform.lock.hcl",
        ".terraform",
    ):
        transfer_path(src_tf / name, dest_tf / name, keep_source)
    for extra in (".vault_pass", ".vault_pass.txt"):
        if (src / extra).is_file():
            transfer_path(src / extra, dest / extra, keep_source)
    link_terraform_modules(dest, spa_home)
    write_spa_yml(dest, spa_home)


def leftover_present(root: Path) -> List[str]:
    found = []
    for name in FRAMEWORK_LEFTOVERS:
        if (root / name).exists():
            found.append(name)
    tf = root / "terraform" / "aws"
    if tf.is_dir():
        for path in tf.glob("*.tf"):
            if path.is_file() and not path.is_symlink():
                found.append("terraform/aws/" + path.name)
    return found


def print_old_clone_report(dest: Path) -> None:
    print("This looks like an old clone-style Splunk environment:")
    print("  %s" % dest)
    print()
    print("Keep:")
    for item in KEEP_HINT:
        print("  - %s" % item)
    print()
    print("Remove with --force:")
    leftovers = leftover_present(dest) or list(FRAMEWORK_LEFTOVERS[:8]) + ["…"]
    for item in leftovers:
        print("  - %s" % item)
    print()
    print("Re-run:  spa init --force %s" % dest)
    print("Config (splunk_config.yml) is left alone unless you also pass --example.")


def strip_framework(dest: Path, spa_home: Path) -> None:
    for name in FRAMEWORK_LEFTOVERS:
        path = dest / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    tf = dest / "terraform" / "aws"
    if tf.is_dir():
        for path in tf.glob("*.tf"):
            if path.is_symlink():
                continue
            if path.is_file():
                path.unlink()
        readme = tf / "README.md"
        if readme.is_file():
            readme.unlink()
    link_terraform_modules(dest, spa_home)


def prune_incomplete_venv(dest: Path) -> None:
    """Remove an env .venv with no bin/activate (interrupted or failed create).

    It holds no state, and leaving it makes spa_venv.sh fail on every cd. A
    complete venv is user state (a pinned Ansible) and is never removed here.
    """
    venv = dest / ".venv"
    if venv.is_dir() and not (venv / "bin" / "activate").is_file():
        shutil.rmtree(venv)
        print("  venv:      removed incomplete %s" % venv)


def create_venv(
    dest: Path,
    spa_home: Path,
    env_venv: bool,
    python: Optional[str],
    ansible: Optional[str],
    pip_pkgs: Sequence[str],
    rebuild: bool = False,
) -> None:
    venv_script = spa_home / "bin" / "spa_venv.sh"
    if not venv_script.is_file():
        print("  venv:      skipped (no bin/spa_venv.sh under %s)" % spa_home)
        return
    if env_venv:
        venv_dir = dest / ".venv"
    else:
        venv_dir = spa_home / ".venv"
    if rebuild and (venv_dir / "bin" / "activate").is_file():
        shutil.rmtree(venv_dir)
    if (venv_dir / "bin" / "activate").is_file() and not rebuild:
        print("  venv:      %s (existing)" % venv_dir)
        extra = []
        if ansible:
            extra.append("ansible==%s" % ansible)
        extra.extend(pip_pkgs)
        env_req = dest / "requirements.txt"
        cmd = ["bash", str(venv_script), "--create", "--dir", str(venv_dir)]
        if python:
            cmd.extend(["--python", python])
        if env_venv and env_req.is_file():
            cmd.extend(["--requirements", str(spa_home / "requirements.txt"), "--requirements", str(env_req)])
        if extra:
            cmd.extend(extra)
            print("Creating/updating Python venv extras: %s" % venv_dir)
            subprocess.check_call(cmd)
        return
    print("Creating Python venv: %s" % venv_dir)
    cmd = ["bash", str(venv_script), "--create", "--dir", str(venv_dir)]
    if python:
        cmd.extend(["--python", python])
    env_req = dest / "requirements.txt"
    if env_venv and env_req.is_file():
        cmd.extend(["--requirements", str(spa_home / "requirements.txt"), "--requirements", str(env_req)])
    extra = []
    if ansible:
        extra.append("ansible==%s" % ansible)
    extra.extend(pip_pkgs)
    cmd.extend(extra)
    subprocess.check_call(cmd)


def allow_direnv(dest: Path) -> None:
    if shutil.which("direnv") is None:
        return
    result = subprocess.run(["direnv", "allow"], cwd=str(dest), capture_output=True, text=True)
    if result.returncode == 0:
        print("direnv: approved %s/.envrc (cd into the env to load venv + SPA_*)" % dest)
    else:
        print("direnv: could not approve .envrc (run: cd %s && direnv allow)" % dest)


def run_doctor(dest: Path, spa_home: Path, skip: bool) -> None:
    if skip:
        return
    from spa import doctor as doctor_mod

    extra = ["--fix-direnv"] if sys.stdout.isatty() else []
    rc = doctor_mod.run(["--spa-home", str(spa_home), "--env", str(dest), *extra])
    if rc != 0:
        raise InitError(
            "Host prerequisite check failed. Fix the items above before provision/deploy."
        )


def list_examples(spa_home: Path) -> List[str]:
    names = []
    examples = spa_home / "examples"
    if examples.is_dir():
        for path in sorted(examples.glob("*.yml")):
            names.append(path.name)
    return names


def init_env(
    dest: Path,
    spa_home: Path,
    *,
    example: Optional[str] = None,
    example_set: bool = False,
    from_dir: Optional[Path] = None,
    migrate_set: bool = False,
    keep_source: bool = False,
    force: bool = False,
    env_venv: bool = False,
    python: Optional[str] = None,
    ansible: Optional[str] = None,
    pip_pkgs: Optional[Sequence[str]] = None,
    write_envrc_file: bool = True,
    skip_doctor: bool = False,
    rebuild_venv: bool = False,
) -> int:
    pip_pkgs = list(pip_pkgs or [])
    dest = dest.resolve()
    spa_home = spa_home.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    source = (from_dir or spa_home).resolve()
    config_dest = dest / "config" / "splunk_config.yml"

    if dest == spa_home:
        raise InitError(
            "Refusing to scaffold into SPA_HOME (%s).\n"
            "This checkout is the framework. Pick another directory for the env." % spa_home
        )
    if source == dest and from_dir:
        raise InitError("Source and dest are the same path (%s)." % dest)
    if example_set and migrate_set:
        raise InitError("Use --example or --migrate/--from, not both.")
    if force:
        prune_incomplete_venv(dest)

    if is_old_clone_tree(dest) and not example_set and from_dir is None:
        if not force:
            print_old_clone_report(dest)
            raise InitError("Refusing to strip framework files without --force.", code=2)
        print("Converting clone-style env at %s" % dest)
        strip_framework(dest, spa_home)
        ensure_env_dirs(dest)
        write_spa_yml(dest, spa_home)
        if write_envrc_file:
            write_envrc(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        print("Converted to an env dir at %s" % dest)
        print("  config:    %s" % config_dest)
        return 0

    want_migrate = migrate_set or (not example_set and has_config(source) and source != dest)
    if want_migrate:
        if not has_config(source):
            raise InitError("No config/splunk_config.yml in %s. Nothing to migrate." % source)
        if has_config(dest) and not force:
            raise InitError(
                "Env already has a config (%s). Use --force to refresh .spa.yml/.envrc "
                "(config is kept unless --example)." % config_dest
            )
        if has_config(dest) and force and not example_set:
            # refresh pointer files only; do not copy config from source over dest
            ensure_env_dirs(dest)
            write_spa_yml(dest, spa_home)
            if write_envrc_file:
                write_envrc(dest, spa_home)
            link_terraform_modules(dest, spa_home)
            create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
            allow_direnv(dest)
            run_doctor(dest, spa_home, skip_doctor)
            print("Refreshed env pointer files at %s (splunk_config.yml kept)" % dest)
            return 0
        print("Migrating existing env from %s" % source)
        migrate_state(source, dest, spa_home, keep_source)
        if write_envrc_file:
            write_envrc(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        print("Env migrated to %s" % dest)
        return 0

    if is_spa_env(dest) and not force:
        raise InitError("Env already exists (%s). Use --force to refresh .spa.yml/.envrc." % dest)

    if example_set:
        name = example or "single_node.yml"
        name = name.replace("examples/", "")
        if not name.endswith((".yml", ".yaml")):
            name = name + ".yml"
        source_example = spa_home / "examples" / name
        if not source_example.is_file():
            raise InitError("Example not found: %s" % source_example)
        ensure_env_dirs(dest)
        shutil.copy2(source_example, config_dest)
        write_spa_yml(dest, spa_home)
        if write_envrc_file:
            write_envrc(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        print("Env scaffolded at %s" % dest)
        print("  example:   %s" % name)
        print("  config:    %s" % config_dest)
        return 0

    # --force without --example on an existing env: refresh metadata, keep config
    if force and (has_config(dest) or is_spa_env(dest)):
        ensure_env_dirs(dest)
        write_spa_yml(dest, spa_home)
        if write_envrc_file:
            write_envrc(dest, spa_home)
        link_terraform_modules(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        print("Refreshed env at %s (splunk_config.yml kept)" % dest)
        return 0

    # Fresh env, default example
    name = "single_node.yml"
    source_example = spa_home / "examples" / name
    if not source_example.is_file():
        raise InitError("Example not found: %s" % source_example)
    if config_dest.exists() or (dest / ".spa.yml").exists():
        raise InitError("Env already exists (%s). Use --force to refresh .spa.yml/.envrc." % dest)
    ensure_env_dirs(dest)
    shutil.copy2(source_example, config_dest)
    write_spa_yml(dest, spa_home)
    if write_envrc_file:
        write_envrc(dest, spa_home)
    create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
    allow_direnv(dest)
    run_doctor(dest, spa_home, skip_doctor)
    print("Env scaffolded at %s" % dest)
    print("  example:   %s" % name)
    print("  config:    %s" % config_dest)
    return 0
