"""Shipped framework paths and how ``spa init --force`` treats them.

``scripts/framework-files.txt`` stays a bare path list. Actions live here so
pack and install keep their current manifest parsing. A drift test fails when
a manifest line has no action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# strip: delete the path. relink: keep the directory and refresh module links.
# strip_entry: delete that path only, not its parent.
_ACTIONS = {
    ".gitignore": "strip",
    ".agent": "strip",
    ".cursor/skills": "strip_entry",
    "AGENTS.md": "strip",
    "CHANGELOG.md": "strip",
    "LICENSE": "strip",
    "README.md": "strip",
    "RELEASE.md": "strip",
    "ROADMAP.md": "strip",
    "VERSION": "strip",
    "Vagrantfile": "strip",
    "ansible": "strip",
    "ansible.cfg": "strip",
    "bin": "strip",
    "defaults": "strip",
    "docs": "strip",
    "examples": "strip",
    "install.sh": "strip",
    "lib": "strip",
    "pic": "strip",
    "requirements.txt": "strip",
    "requirements.yml": "strip",
    "scripts": "strip",
    "skills": "strip",
    "template": "strip",
    "terraform": "relink",
}

# Not shipped by pack or install. Current checkout extras, plus paths that
# older clones still have after they left the framework:
# setup_ansible_remote.txt (retired WinRM bootstrap) and .ansible/
# (empty local roles/modules/collections; collections now live beside the venv).
CHECKOUT_ONLY_LEFTOVERS = (
    ".git",
    ".github",
    "tests",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitattributes",
    ".gitmodules",
    "setup_ansible_remote.txt",
    ".ansible",
)

_RETAIN_NAMES = (
    "config",
    "inventory",
    "saved_base_config_apps",
    ".vagrant",
    ".vault_pass",
    ".vault_pass.txt",
    ".spa.yml",
)

_TF_STATE_NAMES = (
    "terraform.tfvars",
    "terraform.tfstate",
    "terraform.tfstate.backup",
    "tfplan",
    ".terraform.lock.hcl",
    ".terraform",
)


class FrameworkPathError(Exception):
    """The framework manifest is missing or has a path with no action."""


@dataclass(frozen=True)
class RemovalPlan:
    """What ``strip_framework`` would change. Building a plan does not touch disk."""

    remove: tuple
    relink: bool
    retain: tuple


def load_framework_manifest(spa_home: Path) -> tuple:
    """Read ``SPA_HOME/scripts/framework-files.txt``. Comments and blanks are ignored."""
    path = Path(spa_home) / "scripts" / "framework-files.txt"
    if not path.is_file():
        raise FrameworkPathError("Framework manifest not found: %s" % path)
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return tuple(lines)


def framework_actions() -> Mapping[str, str]:
    """Every shipped path mapped to ``strip``, ``relink``, or ``strip_entry``."""
    return dict(_ACTIONS)


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _cursor_would_be_empty(dest: Path) -> bool:
    cursor = dest / ".cursor"
    if not cursor.is_dir() or cursor.is_symlink():
        return False
    for child in cursor.iterdir():
        if child.name != "skills":
            return False
    return True


def _retain_paths(dest: Path) -> tuple:
    found = []
    for name in _RETAIN_NAMES:
        if _present(dest / name):
            found.append(name)
    if (dest / ".venv" / "bin" / "activate").is_file():
        found.append(".venv")
    cursor = dest / ".cursor"
    if cursor.is_dir() and not cursor.is_symlink():
        for child in sorted(cursor.iterdir(), key=lambda item: item.name):
            if child.name != "skills":
                found.append(".cursor/" + child.name)
    tf = dest / "terraform" / "aws"
    if _present(tf):
        for name in _TF_STATE_NAMES:
            if _present(tf / name):
                found.append("terraform/aws/" + name)
    return tuple(found)


def removal_plan(dest: Path, spa_home: Path) -> RemovalPlan:
    """Paths to delete, whether Terraform modules should be relinked, and what stays.

    Does not modify ``dest``. A missing manifest or an unmapped manifest path
    raises ``FrameworkPathError`` before any caller deletes.
    """
    dest = Path(dest)
    manifest = load_framework_manifest(spa_home)
    actions = framework_actions()
    unknown = [rel for rel in manifest if rel not in actions]
    if unknown:
        raise FrameworkPathError(
            "No framework action for manifest path: %s" % ", ".join(unknown)
        )

    remove = []
    for rel in manifest:
        action = actions[rel]
        if action in ("strip", "strip_entry") and _present(dest / rel):
            remove.append(rel)
    for rel in CHECKOUT_ONLY_LEFTOVERS:
        if _present(dest / rel):
            remove.append(rel)
    if _cursor_would_be_empty(dest):
        remove.append(".cursor")

    tf = dest / "terraform" / "aws"
    return RemovalPlan(
        remove=tuple(remove),
        relink=_present(tf),
        retain=_retain_paths(dest),
    )
