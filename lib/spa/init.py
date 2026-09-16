"""Scaffold, migrate, and convert SPA environment directories (`spa init`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from spa.paths import _expand, is_spa_home, load_user_paths, save_user_paths

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

_LOG: ContextVar[Optional[List[str]]] = ContextVar("spa_init_log", default=None)


def _say(message: str) -> None:
    log = _LOG.get()
    if log is not None:
        log.append(message)
        return
    print(message)

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
    ".vagrant/",
    ".vault_pass*",
)

TOPOLOGY_FORBIDDEN = ("virtualbox", "terraform", "os", "splunk_app_deployment", "aws")
PROVIDER_FORBIDDEN = (
    "splunk_hosts",
    "splunk_idxclusters",
    "splunk_shclusters",
    "splunk_environments",
    "os",
)

# Old single-file names → topology id + implied provider.
EXAMPLE_ALIASES = {
    "single_node.yml": ("single_node", "virtualbox"),
    "idx_sh_uf.yml": ("idx_sh_uf", "virtualbox"),
    "cm_2idxc_sh_uf.yml": ("cm_2idxc_sh_uf", "virtualbox"),
    "cm_2idxc_sh_uf_aws.yml": ("cm_2idxc_sh_uf", "aws"),
    "cm_2idxc1site_3shc_uf.yml": ("cm_2idxc1site_3shc_uf", "virtualbox"),
    "4idxc2site_sh.yml": ("4idxc2site_sh", "virtualbox"),
    "cm_4idxc2site_3shc_ds_uf.yml": ("cm_4idxc2site_3shc_ds_uf", "virtualbox"),
    "two_envs_each_cm_2idxc1site_ds_sh_uf.yml": (
        "two_envs_each_cm_2idxc1site_ds_sh_uf",
        "virtualbox",
    ),
    "cm1_2idxc1site_cm2_2idxc1site_ds_3shc_smc_uf.yml": (
        "cm1_2idxc1site_cm2_2idxc1site_ds_3shc_smc_uf",
        "virtualbox",
    ),
    "ds_cm_2idxc1site_sh_hf_uf.yml": ("ds_cm_2idxc1site_sh_hf_uf", "virtualbox"),
    "idx_3shc_uf.yml": ("idx_3shc_uf", "virtualbox"),
    "aws_lab_baseline.yml": ("single_node", "aws"),
    "splunk_config_terraform_aws.yml": ("cm_2idxc_sh_uf", "aws"),
    "splunk_config_aws.yml": ("cm_2idxc_sh_uf", "aws"),
}


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


def _first_existing(*candidates: Path) -> str:
    for candidate in candidates:
        if candidate.is_dir():
            return str(candidate.resolve())
    return ""


def write_spa_yml(
    dest: Path,
    spa_home: Path,
    *,
    software_dir: Optional[str] = None,
    baseconfig_dir: Optional[str] = None,
    apps_dir: Optional[str] = None,
    persist_user: bool = False,
    environ: Optional[dict] = None,
) -> tuple:
    env = environ if environ is not None else os.environ
    start = dest.resolve()
    if persist_user and (software_dir or baseconfig_dir or apps_dir):
        saved = save_user_paths(
            software_dir=software_dir,
            baseconfig_dir=baseconfig_dir,
            apps_dir=apps_dir,
            environ=env,
            relative_to=start,
        )
        _say("  paths:     %s" % saved)

    user = load_user_paths(env)
    sw = ""
    if software_dir:
        sw = str(_expand(software_dir, start))
    elif user.get("software_dir"):
        sw = str(_expand(str(user["software_dir"]), start))
    else:
        sw = _first_existing(dest / "../Software", spa_home / "../Software", spa_home / "Software")

    bc = ""
    if baseconfig_dir:
        bc = str(_expand(baseconfig_dir, start))
    elif user.get("baseconfig_dir"):
        bc = str(_expand(str(user["baseconfig_dir"]), start))
    elif sw:
        bc = sw
    else:
        bc = sw

    apps = ""
    if apps_dir:
        apps = str(_expand(apps_dir, start))
    elif user.get("apps_dir"):
        apps = str(_expand(str(user["apps_dir"]), start))
    else:
        apps = _first_existing(dest / "../apps", spa_home / "../apps", spa_home / "apps")

    lines = [
        "# Splunk Platform Automator env pointer.",
        "# Framework stays in spa_home. Do not copy ansible/ into this directory.",
        "spa_home: %s" % spa_home,
    ]
    if sw:
        lines.append("software_dir: %s" % sw)
        lines.append("baseconfig_dir: %s" % (bc or sw))
    if apps:
        lines.append("apps_dir: %s" % apps)
    (dest / ".spa.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not sw:
        _say(
            "No Software directory found. Point once with: spa init --software-dir DIR %s"
            % dest
        )
    return sw, apps


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


def migrate_state(
    src: Path, dest: Path, spa_home: Path, keep_source: bool, yml_opts: Optional[dict] = None
) -> None:
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
    src_vagrant = src / ".vagrant"
    if src_vagrant.exists():
        transfer_path(src_vagrant, dest / ".vagrant", keep_source)
    link_terraform_modules(dest, spa_home)
    write_spa_yml(dest, spa_home, **(yml_opts or {}))


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


def _say_old_clone_report(dest: Path) -> None:
    _say("This looks like an old clone-style Splunk environment:")
    _say("  %s" % dest)
    _say("")
    _say("Keep:")
    for item in KEEP_HINT:
        _say("  - %s" % item)
    _say("")
    _say("Remove with --force:")
    leftovers = leftover_present(dest) or list(FRAMEWORK_LEFTOVERS[:8]) + ["…"]
    for item in leftovers:
        _say("  - %s" % item)
    _say("")
    _say("Re-run:  spa init --force %s" % dest)
    _say("Config (splunk_config.yml) is left alone unless you also pass --example.")


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
        _say("  venv:      removed incomplete %s" % venv)


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
        _say("  venv:      skipped (no bin/spa_venv.sh under %s)" % spa_home)
        return
    if env_venv:
        venv_dir = dest / ".venv"
    else:
        venv_dir = spa_home / ".venv"
    if rebuild and (venv_dir / "bin" / "activate").is_file():
        shutil.rmtree(venv_dir)
    if (venv_dir / "bin" / "activate").is_file() and not rebuild:
        _say("  venv:      %s (existing)" % venv_dir)
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
            _say("Creating/updating Python venv extras: %s" % venv_dir)
            subprocess.check_call(cmd)
        return
    _say("Creating Python venv: %s" % venv_dir)
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
        _say("direnv: approved %s/.envrc (cd into the env to load venv + SPA_*)" % dest)
    else:
        _say("direnv: could not approve .envrc (run: cd %s && direnv allow)" % dest)


def run_doctor(dest: Path, spa_home: Path, skip: bool) -> None:
    if skip:
        return
    from spa.doctor import collect_checks, format_doctor_text

    result = collect_checks(
        spa_home=str(spa_home),
        env_dir=str(dest),
        fix_direnv=sys.stdout.isatty(),
    )
    for line in format_doctor_text(result).rstrip().splitlines():
        _say(line)
    if not result.ok:
        raise InitError(
            "Host prerequisite check failed. Fix the items above before provision/deploy."
        )


def list_examples(spa_home: Path) -> Dict[str, Any]:
    topologies = []
    providers = []
    topo_dir = spa_home / "examples" / "topologies"
    if topo_dir.is_dir():
        for path in sorted(topo_dir.glob("*.yml")):
            topologies.append({"id": path.stem, "file": str(path.relative_to(spa_home))})
    prov_dir = spa_home / "examples" / "providers"
    if prov_dir.is_dir():
        for path in sorted(prov_dir.glob("*.yml")):
            providers.append({"id": path.stem, "file": str(path.relative_to(spa_home))})
    return {"topologies": topologies, "providers": providers}


def format_example_list(data: Dict[str, Any]) -> str:
    lines = ["Topologies:"]
    for item in data.get("topologies") or []:
        lines.append("  %s" % item["id"])
    lines.append("Providers:")
    for item in data.get("providers") or []:
        lines.append("  %s" % item["id"])
    lines.append("Compose: spa init --example TOPOLOGY --provider aws|virtualbox ENV")
    return "\n".join(lines)


def _normalize_example_name(name: str) -> str:
    name = (name or "").replace("examples/", "").replace("topologies/", "").strip()
    if name.endswith(".yaml"):
        name = name[: -len(".yaml")] + ".yml"
    if not name.endswith(".yml"):
        name = name + ".yml"
    return name


def resolve_example_pair(
    spa_home: Path, example: Optional[str], provider: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    """Return (topology_id, provider_id, alias_hint)."""
    provider_id = (provider or "").strip().lower() or None
    if provider_id in {"terraform.aws", "terraform"}:
        provider_id = "aws"
    raw = _normalize_example_name(example or "single_node.yml")
    hint = None
    topology_id = Path(raw).stem
    alias = EXAMPLE_ALIASES.get(raw)
    if alias:
        topology_id, implied = alias
        hint = (
            "Alias %s → --example %s --provider %s"
            % (raw, topology_id, implied)
        )
        if provider_id is None:
            provider_id = implied
    if provider_id is None:
        raise InitError(
            "spa init --example requires --provider aws or virtualbox.\n"
            "List: spa init --list"
        )
    topo = spa_home / "examples" / "topologies" / ("%s.yml" % topology_id)
    prov = spa_home / "examples" / "providers" / ("%s.yml" % provider_id)
    if not topo.is_file():
        raise InitError("Topology example not found: %s" % topo)
    if not prov.is_file():
        raise InitError("Provider example not found: %s (use aws or virtualbox)" % prov)
    return topology_id, provider_id, hint


def _load_yaml_mapping(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise InitError("PyYAML is required to compose examples")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise InitError("Example is not a mapping: %s" % path)
    return data


def compose_example_config(spa_home: Path, topology_id: str, provider_id: str) -> Dict[str, Any]:
    topo_path = spa_home / "examples" / "topologies" / ("%s.yml" % topology_id)
    prov_path = spa_home / "examples" / "providers" / ("%s.yml" % provider_id)
    topology = _load_yaml_mapping(topo_path)
    provider = _load_yaml_mapping(prov_path)
    bad_topo = [key for key in TOPOLOGY_FORBIDDEN if topology.get(key)]
    if bad_topo:
        raise InitError(
            "Topology %s must not contain %s" % (topo_path.name, ", ".join(bad_topo))
        )
    bad_prov = [key for key in PROVIDER_FORBIDDEN if provider.get(key)]
    if bad_prov:
        raise InitError(
            "Provider %s must not contain %s" % (prov_path.name, ", ".join(bad_prov))
        )
    plugin = topology.get("plugin") or provider.get("plugin") or "splunk-platform-automator"
    composed: Dict[str, Any] = {"plugin": plugin}
    for key, value in provider.items():
        if key == "plugin":
            continue
        composed[key] = value
    for key, value in topology.items():
        if key == "plugin":
            continue
        composed[key] = value
    return composed


def dump_splunk_config(data: Dict[str, Any]) -> str:
    if yaml is None:
        raise InitError("PyYAML is required to compose examples")
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


def write_composed_config(
    dest_config: Path, spa_home: Path, example: Optional[str], provider: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    topology_id, provider_id, hint = resolve_example_pair(spa_home, example, provider)
    composed = compose_example_config(spa_home, topology_id, provider_id)
    dest_config.parent.mkdir(parents=True, exist_ok=True)
    dest_config.write_text(dump_splunk_config(composed), encoding="utf-8")
    return topology_id, provider_id, hint


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
    log: Optional[List[str]] = None,
    software_dir: Optional[str] = None,
    baseconfig_dir: Optional[str] = None,
    apps_dir: Optional[str] = None,
    provider: Optional[str] = None,
) -> int:
    token = _LOG.set(log) if log is not None else None
    try:
        return _init_env(
            dest,
            spa_home,
            example=example,
            example_set=example_set,
            from_dir=from_dir,
            migrate_set=migrate_set,
            keep_source=keep_source,
            force=force,
            env_venv=env_venv,
            python=python,
            ansible=ansible,
            pip_pkgs=pip_pkgs,
            write_envrc_file=write_envrc_file,
            skip_doctor=skip_doctor,
            rebuild_venv=rebuild_venv,
            software_dir=software_dir,
            baseconfig_dir=baseconfig_dir,
            apps_dir=apps_dir,
            provider=provider,
        )
    finally:
        if token is not None:
            _LOG.reset(token)


def _init_env(
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
    software_dir: Optional[str] = None,
    baseconfig_dir: Optional[str] = None,
    apps_dir: Optional[str] = None,
    provider: Optional[str] = None,
) -> int:
    pip_pkgs = list(pip_pkgs or [])
    dest = dest.resolve()
    spa_home = spa_home.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    source = (from_dir or spa_home).resolve()
    config_dest = dest / "config" / "splunk_config.yml"
    yml_opts = {
        "software_dir": software_dir,
        "baseconfig_dir": baseconfig_dir,
        "apps_dir": apps_dir,
        "persist_user": bool(software_dir or baseconfig_dir or apps_dir),
    }

    def _write() -> tuple:
        return write_spa_yml(dest, spa_home, **yml_opts)

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
            _say_old_clone_report(dest)
            raise InitError("Refusing to strip framework files without --force.", code=2)
        _say("Converting clone-style env at %s" % dest)
        strip_framework(dest, spa_home)
        ensure_env_dirs(dest)
        _write()
        if write_envrc_file:
            write_envrc(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        _say("Converted to an env dir at %s" % dest)
        _say("  config:    %s" % config_dest)
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
            _write()
            if write_envrc_file:
                write_envrc(dest, spa_home)
            link_terraform_modules(dest, spa_home)
            create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
            allow_direnv(dest)
            run_doctor(dest, spa_home, skip_doctor)
            _say("Refreshed env pointer files at %s (splunk_config.yml kept)" % dest)
            return 0
        _say("Migrating existing env from %s" % source)
        migrate_state(source, dest, spa_home, keep_source, yml_opts=yml_opts)
        if write_envrc_file:
            write_envrc(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        _say("Env migrated to %s" % dest)
        return 0

    if is_spa_env(dest) and not force:
        raise InitError("Env already exists (%s). Use --force to refresh .spa.yml/.envrc." % dest)

    if example_set:
        ensure_env_dirs(dest)
        topology_id, provider_id, hint = write_composed_config(
            config_dest, spa_home, example, provider
        )
        _write()
        if write_envrc_file:
            write_envrc(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        _say("Env scaffolded at %s" % dest)
        _say("  example:   %s --provider %s" % (topology_id, provider_id))
        if hint:
            _say("  note:      %s" % hint)
        _say("  config:    %s" % config_dest)
        return 0

    # --force without --example on an existing env: refresh metadata, keep config
    if force and (has_config(dest) or is_spa_env(dest)):
        ensure_env_dirs(dest)
        _write()
        if write_envrc_file:
            write_envrc(dest, spa_home)
        link_terraform_modules(dest, spa_home)
        create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
        allow_direnv(dest)
        run_doctor(dest, spa_home, skip_doctor)
        _say("Refreshed env at %s (splunk_config.yml kept)" % dest)
        return 0

    # Fresh env, default topology + VirtualBox (same as former single_node.yml)
    if config_dest.exists() or (dest / ".spa.yml").exists():
        raise InitError("Env already exists (%s). Use --force to refresh .spa.yml/.envrc." % dest)
    ensure_env_dirs(dest)
    topology_id, provider_id, hint = write_composed_config(
        config_dest, spa_home, "single_node", "virtualbox"
    )
    _write()
    if write_envrc_file:
        write_envrc(dest, spa_home)
    create_venv(dest, spa_home, env_venv, python, ansible, pip_pkgs, rebuild=rebuild_venv)
    allow_direnv(dest)
    run_doctor(dest, spa_home, skip_doctor)
    _say("Env scaffolded at %s" % dest)
    _say("  example:   %s --provider %s" % (topology_id, provider_id))
    if hint:
        _say("  note:      %s" % hint)
    _say("  config:    %s" % config_dest)
    return 0
