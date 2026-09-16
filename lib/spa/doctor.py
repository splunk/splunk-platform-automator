"""Host prerequisite checks (`spa doctor`)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from spa.api import CommandResult
from spa.executil import resolve_venv_dir
from spa.paths import resolve_spa_paths


VAGRANT_REQUIRED_PLUGINS = ("vagrant-vbguest",)
VAGRANT_WSL_PLUGINS = ("virtualbox_WSL2",)


def _brew_hint(pkg: str) -> str:
    if shutil.which("brew"):
        return "brew install %s" % pkg
    return "install %s with your OS package manager"


def _linux_pkg_tool() -> Optional[str]:
    for name in ("apt-get", "dnf", "yum", "zypper", "pacman"):
        if shutil.which(name):
            return name
    return None


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        text = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lower = text.lower()
    return "microsoft" in lower or "wsl" in lower


def _vagrant_install_hint(platform: Optional[str] = None) -> str:
    """HashiCorp's package, not a distro Vagrant that is often too old for VirtualBox."""
    plat = platform or sys.platform
    if plat == "darwin":
        if shutil.which("brew"):
            return "brew tap hashicorp/tap && brew install hashicorp/tap/hashicorp-vagrant"
        return "install Vagrant from https://developer.hashicorp.com/vagrant/install"
    if plat.startswith("linux"):
        tool = _linux_pkg_tool()
        docs = "https://developer.hashicorp.com/vagrant/install#linux"
        if tool == "apt-get":
            return (
                "add the HashiCorp apt repo (%s) then: "
                "sudo apt-get update && sudo apt-get install -y vagrant"
                % docs
            )
        if tool in {"dnf", "yum"}:
            return (
                "add the HashiCorp yum repo (%s) then: sudo %s install -y vagrant"
                % (docs, tool)
            )
        if tool == "zypper":
            return "sudo zypper install vagrant  (or HashiCorp packages: %s)" % docs
        if tool == "pacman":
            return "sudo pacman -S vagrant"
        return "install Vagrant from %s" % docs
    return "install Vagrant from https://developer.hashicorp.com/vagrant/install"


def _terraform_install_hint(platform: Optional[str] = None) -> str:
    plat = platform or sys.platform
    docs = "https://developer.hashicorp.com/terraform/install"
    if plat == "darwin":
        if shutil.which("brew"):
            return "brew tap hashicorp/tap && brew install hashicorp/tap/terraform"
        return "install Terraform from %s" % docs
    if plat.startswith("linux"):
        tool = _linux_pkg_tool()
        if tool == "apt-get":
            return (
                "add the HashiCorp apt repo (%s) then: "
                "sudo apt-get update && sudo apt-get install -y terraform" % docs
            )
        if tool in {"dnf", "yum"}:
            return "add the HashiCorp yum repo (%s) then: sudo %s install -y terraform" % (docs, tool)
        if tool == "pacman":
            return "sudo pacman -S terraform"
        return "install Terraform from %s" % docs
    return "install Terraform from %s" % docs


def _virtualbox_install_hint(platform: Optional[str] = None) -> str:
    plat = platform or sys.platform
    downloads = "https://www.virtualbox.org/wiki/Downloads"
    if plat == "darwin":
        if shutil.which("brew"):
            return "brew install --cask virtualbox"
        return "install VirtualBox from %s" % downloads
    if plat.startswith("linux"):
        linux = "https://www.virtualbox.org/wiki/Linux_Downloads"
        tool = _linux_pkg_tool()
        if tool == "apt-get":
            return "sudo apt-get update && sudo apt-get install -y virtualbox  (newer builds: %s)" % linux
        if tool in {"dnf", "yum"}:
            return "sudo %s install -y VirtualBox  (newer builds: %s)" % (tool, linux)
        if tool == "zypper":
            return "sudo zypper install virtualbox  (newer builds: %s)" % linux
        if tool == "pacman":
            return "sudo pacman -S virtualbox"
        return "install VirtualBox from %s" % linux
    return "install VirtualBox from %s" % downloads


def _vagrant_plugin_names() -> Optional[List[str]]:
    vagrant = shutil.which("vagrant")
    if not vagrant:
        return None
    try:
        proc = subprocess.run(
            [vagrant, "plugin", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    names: List[str] = []
    for line in (proc.stdout or "").splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token:
            names.append(token)
    return names


def _virtualbox_version() -> Optional[str]:
    """Installed VirtualBox as major.minor, the granularity Vagrant drivers use."""
    import re

    exe = shutil.which("VBoxManage") or shutil.which("VBoxManage.exe")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout
    except OSError:
        return None
    match = re.match(r"\s*(\d+)\.(\d+)", out or "")
    return "%s.%s" % (match.group(1), match.group(2)) if match else None


def _vagrant_virtualbox_drivers() -> List[str]:
    """VirtualBox major.minor versions the installed Vagrant ships a driver for.

    Read from the gem tree instead of a hardcoded matrix: a Vagrant that cannot
    drive the installed VirtualBox reports only "No usable default provider".
    """
    roots: List[Path] = []
    vagrant = shutil.which("vagrant")
    if vagrant:
        real = Path(vagrant).resolve()
        roots.append(real.parent.parent / "embedded" / "gems" / "gems")
    roots += [
        Path("/opt/vagrant/embedded/gems/gems"),
        Path("/usr/share/vagrant/gems/gems"),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for gem in sorted(root.glob("vagrant-*"), reverse=True):
            driver = gem / "plugins" / "providers" / "virtualbox" / "driver"
            if not driver.is_dir():
                continue
            found = [
                path.stem[len("version_") :].replace("_", ".")
                for path in driver.glob("version_*.rb")
            ]
            if found:
                return sorted(found, key=lambda ver: tuple(int(part) for part in ver.split(".")))
    return []


def _config_providers(text: str) -> set:
    """Providers configured in splunk_config.yml: 'virtualbox' and/or 'aws'.

    Scans top-level keys so a mention in a comment or a nested key does not
    pull in tool checks. Doctor runs before the venv exists, so no PyYAML.
    """
    providers = set()
    top = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line[:1].isspace():
            top = line.split(":", 1)[0].strip()
            if top == "virtualbox":
                providers.add("virtualbox")
            continue
        if top == "terraform" and line.strip().split(":", 1)[0].strip() == "aws":
            providers.add("aws")
    return providers


def _direnv_hook_line() -> str:
    shell = os.path.basename(os.environ.get("SHELL") or "zsh")
    if shell == "bash":
        return 'eval "$(direnv hook bash)"'
    if shell == "fish":
        return "direnv hook fish | source"
    return 'eval "$(direnv hook zsh)"'


def _rc_files() -> List[Path]:
    home = Path.home()
    return [home / ".zshrc", home / ".bashrc", home / ".zprofile"]


def _hook_in_rc() -> bool:
    """Follow source / . from usual rc files so a nested hook still counts."""
    import re

    home = Path.home()
    roots = [
        home / ".zshrc",
        home / ".zprofile",
        home / ".zshenv",
        home / ".bashrc",
        home / ".bash_profile",
        home / ".config" / "fish" / "config.fish",
    ]
    source_re = re.compile(r"^\s*(?:source|\.)\s+(.+)$", re.MULTILINE)
    hook_re = re.compile(r"direnv\s+hook")
    seen = set()

    def first_path(rest: str) -> str:
        rest = rest.split("#", 1)[0].strip()
        if not rest:
            return ""
        if rest[0] in "'\"":
            quote = rest[0]
            end = rest.find(quote, 1)
            return rest[1:end] if end > 0 else rest[1:]
        return rest.split()[0]

    def scan(path: Path, depth: int = 0) -> bool:
        if depth > 20:
            return False
        try:
            resolved = Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
        except Exception:
            return False
        if str(resolved) in seen or not resolved.is_file():
            return False
        seen.add(str(resolved))
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        if hook_re.search(text):
            return True
        for match in source_re.finditer(text):
            nxt = first_path(match.group(1))
            if nxt and scan(Path(nxt), depth + 1):
                return True
        return False

    return any(root.is_file() and scan(root) for root in roots)


def _apply_hook() -> Optional[str]:
    line = _direnv_hook_line()
    if _hook_in_rc():
        return None
    rc = Path.home() / (".zshrc" if os.path.basename(os.environ.get("SHELL") or "zsh") != "bash" else ".bashrc")
    with rc.open("a", encoding="utf-8") as handle:
        handle.write("\n# direnv (spa doctor --fix-direnv)\n%s\n" % line)
    msg = "Added direnv hook to %s" % rc
    if not shutil.which("direnv"):
        return "%s (direnv is not installed yet)" % msg
    return msg


def collect_checks(
    *,
    spa_home: Optional[str] = None,
    env_dir: Optional[str] = None,
    aws: bool = False,
    virtualbox: bool = False,
    strict: bool = False,
    fix_direnv: bool = False,
) -> CommandResult:
    spa_home_path = Path(spa_home).resolve() if spa_home else resolve_spa_paths().spa_home
    env_path = Path(env_dir).resolve() if env_dir else None
    require_aws = aws
    require_vbox = virtualbox

    # Without --env, check the env the caller is standing in (SPA_ENV_DIR,
    # .spa.yml, cwd) so provider tools are checked for that config. Doctor
    # runs on broken layouts, so resolution failures must not raise here.
    discovered = None
    try:
        discovered = resolve_spa_paths(
            start_dir=env_path,
            environ={**os.environ, "SPA_HOME": str(spa_home_path)},
            clone_root=spa_home_path,
        )
    except Exception:
        discovered = None
    if env_path is None and discovered is not None and discovered.roots_differ:
        env_path = discovered.spa_env_dir

    cfg = None
    candidates = []
    if env_path:
        candidates.append(env_path / "config" / "splunk_config.yml")
    if discovered is not None:
        candidates.append(discovered.config_file)
    candidates.append(spa_home_path / "config" / "splunk_config.yml")
    for candidate in candidates:
        if candidate.is_file():
            cfg = candidate
            break
    if cfg:
        providers = _config_providers(cfg.read_text(encoding="utf-8", errors="replace"))
        require_aws = require_aws or "aws" in providers
        require_vbox = require_vbox or "virtualbox" in providers

    ok: List[Dict[str, str]] = []
    warns: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []
    notes: List[str] = []

    def rec(level: str, ident: str, msg: str, fix: str = "") -> None:
        row = {"id": ident, "message": msg, "fix": fix, "level": level}
        if level == "ok":
            ok.append(row)
        elif level == "warn":
            warns.append(row)
        else:
            errors.append(row)

    py = shutil.which("python3")
    if py:
        ver = subprocess.run(
            [py, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        venv_ok = subprocess.run([py, "-c", "import venv"], capture_output=True).returncode == 0
        if venv_ok:
            rec("ok", "python", "python3 (%s) with venv module" % ver)
        else:
            rec("error", "python", "python3 found but venv module missing", _brew_hint("python3"))
    else:
        rec("error", "python", "python3 not on PATH", _brew_hint("python3"))

    paths = resolve_spa_paths(start_dir=env_path or spa_home_path)
    venv = resolve_venv_dir(paths) if env_path else (
        spa_home_path / ".venv" if (spa_home_path / ".venv" / "bin" / "activate").is_file() else None
    )
    if env_path:
        venv = resolve_venv_dir(
            resolve_spa_paths(
                start_dir=env_path,
                environ={**os.environ, "SPA_ENV_DIR": str(env_path), "SPA_HOME": str(spa_home_path)},
            )
        )
    shared = spa_home_path / ".venv"
    checked = [env_path / ".venv"] if env_path else []
    checked.append(shared)
    for candidate in checked:
        if candidate.is_dir() and not (candidate / "bin" / "activate").is_file():
            rec(
                "warn",
                "spa_venv",
                "incomplete venv at %s (no bin/activate)" % candidate,
                "%s --create" % (spa_home_path / "bin" / "spa_venv.sh"),
            )
    if venv and (venv / "bin" / "activate").is_file():
        rec("ok", "spa_venv", "venv at %s" % venv)
        ansible = venv / "bin" / "ansible"
        if ansible.is_file():
            ver = subprocess.run([str(ansible), "--version"], capture_output=True, text=True).stdout.splitlines()
            rec("ok", "ansible", ver[0] if ver else str(ansible))
    elif (shared / "bin" / "activate").is_file():
        rec("ok", "spa_venv", "shared venv at %s" % shared)
    else:
        rec("warn", "spa_venv", "shared venv not created yet", "spa init or source bin/spa_venv.sh --create")

    spa_bin = shutil.which("spa")
    expected = str(spa_home_path / "bin" / "spa")
    if not spa_bin:
        rec("warn", "spa", "spa is not on PATH", "cd the env (direnv), or run %s directly" % expected)
    else:
        if Path(spa_bin).parent.resolve() != (spa_home_path / "bin").resolve():
            rec(
                "warn",
                "spa",
                "spa on PATH is %s, not %s (another checkout wins)" % (spa_bin, expected),
                "reload direnv so $SPA_HOME/bin is first",
            )
        else:
            rec("ok", "spa", "spa resolves to %s" % expected)

    selected = [
        name
        for name, wanted in (("terraform.aws", require_aws), ("virtualbox", require_vbox))
        if wanted
    ]
    if selected:
        rec(
            "ok",
            "provider",
            "provider tools checked for: %s (%s)"
            % (", ".join(selected), cfg if cfg else "--aws/--virtualbox"),
        )
    elif cfg:
        rec(
            "ok",
            "provider",
            "no provider in %s; skipping terraform/vagrant checks" % cfg,
        )

    if require_aws:
        if shutil.which("terraform"):
            rec("ok", "terraform", "terraform is on PATH")
        else:
            rec(
                "error",
                "terraform",
                "terraform required for terraform.aws (not on PATH)",
                _terraform_install_hint(),
            )

    if fix_direnv:
        hook_msg = _apply_hook()
        if hook_msg:
            notes.append(hook_msg)
    if shutil.which("direnv"):
        if _hook_in_rc() or os.environ.get("DIRENV_DIR"):
            rec("ok", "direnv", "direnv is installed and set up in your shell")
        else:
            rec(
                "warn",
                "direnv",
                "direnv is installed, but your shell does not load it yet",
                "spa doctor --fix-direnv",
            )
    else:
        rec("warn", "direnv", "direnv is not installed", _brew_hint("direnv") + "; then spa doctor --fix-direnv")

    software = None
    env_overlay = {**os.environ, "SPA_HOME": str(spa_home_path)}
    if env_path:
        env_overlay["SPA_ENV_DIR"] = str(env_path)
    try:
        resolved = resolve_spa_paths(
            start_dir=env_path or spa_home_path,
            environ=env_overlay,
            clone_root=spa_home_path,
        )
        if resolved.software_dir.is_dir():
            software = resolved.software_dir
    except Exception:
        software = None
    if software:
        rec("ok", "software", "Software at %s" % software)
    else:
        rec(
            "warn",
            "software",
            "no Software/ directory (installers and baseconfig apps)",
            "spa init --software-dir DIR ENV (saves ~/.config/spa/paths.yml); or sibling of env",
        )

    if require_vbox:
        has_vagrant = bool(shutil.which("vagrant"))
        vbox = _virtualbox_version()
        if has_vagrant:
            rec("ok", "vagrant", "vagrant is on PATH")
            plugins = _vagrant_plugin_names()
            if plugins is None:
                rec(
                    "warn",
                    "vagrant_plugins",
                    "could not list Vagrant plugins (`vagrant plugin list` failed)",
                    "vagrant plugin list",
                )
            else:
                missing = [name for name in VAGRANT_REQUIRED_PLUGINS if name not in plugins]
                if missing:
                    rec(
                        "error",
                        "vagrant_plugins",
                        "missing Vagrant plugin(s): %s"
                        % ", ".join(missing),
                        "vagrant plugin install %s" % " ".join(missing),
                    )
                else:
                    rec(
                        "ok",
                        "vagrant_plugins",
                        "Vagrant plugins: %s" % ", ".join(VAGRANT_REQUIRED_PLUGINS),
                    )
                if _is_wsl():
                    wsl_missing = [name for name in VAGRANT_WSL_PLUGINS if name not in plugins]
                    if wsl_missing:
                        rec(
                            "warn",
                            "vagrant_wsl_plugins",
                            "WSL detected; missing plugin(s) so Vagrant can talk to Windows VirtualBox: %s"
                            % ", ".join(wsl_missing),
                            "vagrant plugin install %s" % " ".join(wsl_missing),
                        )
        else:
            rec(
                "error",
                "vagrant",
                "vagrant required for VirtualBox (not on PATH)",
                _vagrant_install_hint(),
            )

        drivers = _vagrant_virtualbox_drivers() if has_vagrant else []
        if not vbox:
            rec(
                "error",
                "virtualbox",
                "VBoxManage not on PATH (VirtualBox not installed?)",
                _virtualbox_install_hint(),
            )
        elif drivers and vbox not in drivers:
            rec(
                "error",
                "virtualbox",
                "VirtualBox %s has no driver in this Vagrant (supported: %s); "
                "vagrant reports 'No usable default provider'"
                % (vbox, ", ".join(drivers[-3:])),
                "upgrade vagrant (%s) or install VirtualBox %s"
                % (_vagrant_install_hint(), drivers[-1]),
            )
        else:
            rec("ok", "virtualbox", "VirtualBox %s" % vbox)

    if shutil.which("brew"):
        rec("ok", "brew", "Homebrew available (optional; SPA uses spa_venv, not brew ansible)")

    payload = {
        "spa_home": str(spa_home_path),
        "errors": len(errors),
        "warnings": len(warns),
        "checks": ok + warns + errors,
        "notes": notes,
    }
    code = 0
    error = None
    if errors:
        code = 1
        error = "%s required check(s) failed." % len(errors)
    elif strict and warns:
        code = 1
        error = "%s warning(s) treated as failure (--strict)." % len(warns)
    return CommandResult(ok=code == 0, data=payload, error=error, code=code)


def format_doctor_text(result: CommandResult) -> str:
    data = result.data or {}
    lines = ["SPA host prerequisites (SPA_HOME=%s)" % data.get("spa_home", "")]
    for note in data.get("notes") or []:
        lines.append(note)
    lines.append("")
    for row in data.get("checks") or []:
        level = row.get("level")
        prefix = {"ok": "OK  ", "warn": "WARN", "error": "FAIL"}.get(level, "    ")
        lines.append("%s %s" % (prefix, row.get("message", "")))
        if row.get("fix") and level in {"warn", "error"}:
            lines.append("       → %s" % row["fix"])
    lines.append("")
    errors = data.get("errors") or 0
    warns = data.get("warnings") or 0
    if errors:
        lines.append("%s required check(s) failed." % errors)
    elif warns:
        lines.append("%s warning(s). Env may still work; fix before deploy if they apply." % warns)
    else:
        lines.append("All checks passed.")
    return "\n".join(lines) + "\n"


def run(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check host prerequisites for SPA")
    parser.add_argument("--spa-home")
    parser.add_argument("--env", "--lab", dest="env_dir", help="Env dir")
    parser.add_argument("--aws", action="store_true")
    parser.add_argument("--virtualbox", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fix-direnv", action="store_true")
    args = parser.parse_args(argv)
    result = collect_checks(
        spa_home=args.spa_home,
        env_dir=args.env_dir,
        aws=args.aws,
        virtualbox=args.virtualbox,
        strict=args.strict,
        fix_direnv=args.fix_direnv,
    )
    if args.json:
        print(json.dumps(result.data, indent=2, default=str))
    else:
        sys.stdout.write(format_doctor_text(result))
    return result.code
