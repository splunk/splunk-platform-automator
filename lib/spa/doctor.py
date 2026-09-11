"""Host prerequisite checks (`spa doctor`)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from spa.executil import resolve_venv_dir
from spa.paths import resolve_spa_paths


def _brew_hint(pkg: str) -> str:
    if shutil.which("brew"):
        return "brew install %s" % pkg
    return "install %s with your OS package manager" % pkg


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


def _apply_hook() -> None:
    if not shutil.which("direnv"):
        print("direnv is not installed; cannot add the hook.", file=sys.stderr)
        return
    line = _direnv_hook_line()
    if _hook_in_rc():
        return
    rc = Path.home() / (".zshrc" if os.path.basename(os.environ.get("SHELL") or "zsh") != "bash" else ".bashrc")
    with rc.open("a", encoding="utf-8") as handle:
        handle.write("\n# direnv (spa doctor --fix-direnv)\n%s\n" % line)
    print("Added direnv hook to %s" % rc)


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

    spa_home = Path(args.spa_home).resolve() if args.spa_home else resolve_spa_paths().spa_home
    env_dir = Path(args.env_dir).resolve() if args.env_dir else None
    require_aws = args.aws
    require_vbox = args.virtualbox
    cfg = None
    if env_dir and (env_dir / "config" / "splunk_config.yml").is_file():
        cfg = env_dir / "config" / "splunk_config.yml"
    elif (spa_home / "config" / "splunk_config.yml").is_file():
        cfg = spa_home / "config" / "splunk_config.yml"
    if cfg:
        text = cfg.read_text(encoding="utf-8", errors="replace")
        if not require_aws and "terraform:" in text and "aws:" in text:
            require_aws = True
        if not require_vbox and (text.startswith("virtualbox:") or "\nvirtualbox:" in text):
            require_vbox = True

    ok: List[Dict[str, str]] = []
    warns: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

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

    paths = resolve_spa_paths(start_dir=env_dir or spa_home)
    if args.spa_home:
        # keep doctor --spa-home
        pass
    venv = resolve_venv_dir(paths) if env_dir else (
        spa_home / ".venv" if (spa_home / ".venv" / "bin" / "activate").is_file() else None
    )
    if env_dir:
        venv = resolve_venv_dir(resolve_spa_paths(start_dir=env_dir, environ={**os.environ, "SPA_ENV_DIR": str(env_dir), "SPA_HOME": str(spa_home)}))
    shared = spa_home / ".venv"
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
    expected = str(spa_home / "bin" / "spa")
    if not spa_bin:
        rec("warn", "spa", "spa is not on PATH", "cd the env (direnv), or run %s directly" % expected)
    else:
        resolved = str(Path(spa_bin).resolve())
        if Path(spa_bin).parent.resolve() != (spa_home / "bin").resolve():
            rec(
                "warn",
                "spa",
                "spa on PATH is %s, not %s (another checkout wins)" % (spa_bin, expected),
                "reload direnv so $SPA_HOME/bin is first",
            )
        else:
            rec("ok", "spa", "spa resolves to %s" % expected)

    if require_aws:
        if shutil.which("terraform"):
            rec("ok", "terraform", "terraform is on PATH")
        else:
            rec("error", "terraform", "terraform required for AWS (not on PATH)", _brew_hint("terraform"))

    if args.fix_direnv:
        _apply_hook()
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
    roots = [spa_home]
    if env_dir:
        roots.insert(0, env_dir)
    for root in roots:
        for candidate in (root / "../Software", spa_home / "../Software", spa_home / "Software"):
            if candidate.is_dir():
                software = candidate.resolve()
                break
        if software:
            break
    if software:
        rec("ok", "software", "Software at %s" % software)
    else:
        rec("warn", "software", "no Software/ directory (installers and baseconfig apps)", "sibling of env or SPA_HOME: ../Software")

    if require_vbox:
        if shutil.which("vagrant"):
            rec("ok", "vagrant", "vagrant is on PATH")
        else:
            rec("error", "vagrant", "vagrant required for VirtualBox (not on PATH)", _brew_hint("vagrant"))

    if shutil.which("brew"):
        rec("ok", "brew", "Homebrew available (optional; SPA uses spa_venv, not brew ansible)")

    if args.json:
        print(json.dumps({"errors": len(errors), "warnings": len(warns), "checks": ok + warns + errors}, indent=2))
    else:
        print("SPA host prerequisites (SPA_HOME=%s)" % spa_home)
        print()
        for row in ok:
            print("OK   %s" % row["message"])
        for row in warns:
            print("WARN %s" % row["message"])
            if row.get("fix"):
                print("       → %s" % row["fix"])
        for row in errors:
            print("FAIL %s" % row["message"])
            if row.get("fix"):
                print("       → %s" % row["fix"])
        print()
        if errors:
            print("%s required check(s) failed." % len(errors))
        elif warns:
            print("%s warning(s). Env may still work; fix before deploy if they apply." % len(warns))
        else:
            print("All checks passed.")

    if errors:
        return 1
    if args.strict and warns:
        return 1
    return 0
