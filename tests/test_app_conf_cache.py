"""Standing checks for apps_common app.conf cache extract.

Live ES verify failed with tar Permission denied when re-extracting into a
cache tree whose directories were 0555 from a prior (become) extract.
"""

from __future__ import annotations

import os
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.local

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "ansible/roles/apps_common/tasks/app_conf_cache_target.yml"
CONTROLLER = REPO_ROOT / "ansible/roles/apps_common/tasks/app_conf_cache_controller.yml"


def _extract_task(path: Path) -> dict:
    tasks = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(tasks, list)
    for task in tasks:
        if isinstance(task, dict) and "Extract app conf files from archive to cache" in str(
            task.get("name") or ""
        ):
            return task
    raise AssertionError("extract task not found in %s" % path)


def test_extract_into_readonly_archive_dirs_needs_chmod(tmp_path):
    src = tmp_path / "src"
    (src / "Suite" / "default").mkdir(parents=True)
    (src / "Suite" / "default" / "app.conf").write_text("[launcher]\nversion=1.0\n")
    archive = tmp_path / "es.tgz"
    with tarfile.open(archive, "w:gz") as handle:
        def reset(tarinfo):
            tarinfo.mode = 0o555 if tarinfo.isdir() else 0o644
            return tarinfo
        handle.add(src / "Suite", arcname="Suite", filter=reset)

    dest = tmp_path / "dest"
    (dest / "Suite").mkdir(parents=True)
    os.chmod(dest / "Suite", 0o555)
    plain = subprocess.run(
        ["tar", "-xzf", str(archive), "-C", str(dest), "Suite/default/app.conf"],
        capture_output=True,
        text=True,
    )
    assert plain.returncode != 0
    assert "Permission denied" in (plain.stderr or "")
    assert not (dest / "Suite" / "default" / "app.conf").is_file()

    fixed = subprocess.run(
        [
            "bash",
            "-lc",
            "chmod -R u+rwX '%s' && tar --no-same-owner --no-same-permissions "
            "-xzf '%s' -C '%s' Suite/default/app.conf" % (dest, archive, dest),
        ],
        capture_output=True,
        text=True,
    )
    assert fixed.returncode == 0, fixed.stderr
    assert (dest / "Suite" / "default" / "app.conf").is_file()


def test_target_extract_uses_become_chmod_and_writable_tar_flags():
    task = _extract_task(TARGET)
    assert task.get("become") is True
    cmd = task.get("ansible.builtin.shell", {}).get("cmd") or ""
    assert "chmod -R u+rwX" in cmd
    assert "--no-same-owner" in cmd
    assert "--no-same-permissions" in cmd


def test_controller_extract_uses_chmod_and_writable_tar_flags():
    task = _extract_task(CONTROLLER)
    cmd = task.get("ansible.builtin.shell", {}).get("cmd") or ""
    assert "chmod -R u+rwX" in cmd
    assert "--no-same-owner" in cmd
    assert "--no-same-permissions" in cmd
