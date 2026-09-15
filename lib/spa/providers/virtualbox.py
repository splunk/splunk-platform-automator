"""VirtualBox lifecycle via Vagrant (Vagrantfile stays in SPA_HOME)."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional, Sequence

from spa.executil import ToolNotFound, tool_path
from spa.paths import SpaPaths
from spa.providers import (
    ProviderError,
    ProvisionState,
    expected_hostnames,
    inventory_hostnames_from_file,
    load_deployment_config,
)

_RUNNING = frozenset({"running"})
_ABSENT = frozenset({"not_created", "not created"})


def parse_machine_readable_status(text: str) -> Dict[str, str]:
    """Map VM name -> vagrant state from ``vagrant status --machine-readable``."""
    states: Dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(",", 3)
        if len(parts) < 4:
            continue
        _ts, name, kind, value = parts
        if kind == "state" and name:
            states[name] = value
    return states


def drop_ansible_extra(extra: Optional[Sequence[str]]) -> List[str]:
    """spa always passes ``-e auto_approve=true``; Vagrant does not take Ansible flags."""
    out: List[str] = []
    skip_next = False
    for arg in extra or []:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-e", "--extra-vars"):
            skip_next = True
            continue
        if arg.startswith("-e=") or arg.startswith("--extra-vars="):
            continue
        out.append(arg)
    return out


class Provider:
    name = "virtualbox"

    def __init__(self, paths: SpaPaths, config: Dict[str, Any]):
        self.paths = paths
        self.config = config

    def _vagrantfile(self) -> Path:
        return self.paths.spa_home / "Vagrantfile"

    def _clone_config(self) -> Path:
        return self.paths.spa_home / "config" / "splunk_config.yml"

    def _require_clone_layout(self) -> None:
        vagrantfile = self._vagrantfile()
        if not vagrantfile.is_file():
            raise ProviderError(
                "Vagrantfile not found in SPA_HOME (%s). VirtualBox lifecycle "
                "runs Vagrant from the framework tree, not from an env dir."
                % self.paths.spa_home
            )
        try:
            wanted = self._clone_config().resolve()
            actual = self.paths.config_file.resolve()
        except OSError as exc:
            raise ProviderError("Cannot resolve VirtualBox config path: %s" % exc)
        if actual != wanted:
            raise ProviderError(
                "VirtualBox lifecycle requires config in the clone "
                "($SPA_HOME/config/splunk_config.yml). Env dirs from spa init "
                "have no Vagrantfile; use terraform.aws for those, or copy a "
                "VirtualBox example into the clone."
            )

    def _vagrant_bin(self) -> str:
        try:
            return tool_path(self.paths, "vagrant")
        except ToolNotFound as exc:
            raise ProviderError(str(exc)) from exc

    def _run(
        self,
        args: List[str],
        *,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        self._require_clone_layout()
        cmd = [self._vagrant_bin(), *args]
        result = subprocess.run(
            cmd,
            cwd=str(self.paths.spa_home),
            capture_output=capture,
            text=True,
        )
        if check and result.returncode != 0:
            detail = ""
            if capture:
                detail = (result.stderr or result.stdout or "").strip()
                if detail:
                    first = detail.splitlines()[0]
                    detail = ": %s" % first
            raise ProviderError(
                "vagrant %s failed (exit %s)%s"
                % (" ".join(args), result.returncode, detail)
            )
        return result

    def _machine_states(self) -> Dict[str, str]:
        result = self._run(["status", "--machine-readable"], capture=True, check=False)
        if result.returncode != 0:
            raise ProviderError(
                "Cannot read Vagrant status from %s (vagrant exited %s)."
                % (self.paths.spa_home, result.returncode)
            )
        return parse_machine_readable_status(result.stdout or "")

    def provision(self, extra: List[str]) -> int:
        leftover = drop_ansible_extra(extra)
        result = self._run(["up", *leftover], capture=False, check=False)
        return result.returncode

    def destroy(self, extra: List[str]) -> int:
        leftover = drop_ansible_extra(extra)
        args = ["destroy", "-f", *leftover]
        result = self._run(args, capture=False, check=False)
        return result.returncode

    def provision_state(self) -> ProvisionState:
        expected = expected_hostnames(load_deployment_config(self.paths))
        inventory = set(inventory_hostnames_from_file(self.paths))
        missing_inv = tuple(sorted(set(expected) - inventory))
        hint = "spa provision --yes"
        try:
            states = self._machine_states()
        except ProviderError:
            states = None
        missing_vm = ()
        if states is not None:
            missing_vm = tuple(
                sorted(
                    name
                    for name in expected
                    if states.get(name, "not_created") in _ABSENT
                )
            )
        if missing_inv or missing_vm:
            missing = tuple(sorted(set(missing_inv) | set(missing_vm)))
            shown = list(missing)
            extra = ""
            if len(shown) > 12:
                extra = ", +%d more" % (len(shown) - 12)
                shown = shown[:12]
            reason = "hosts not provisioned: %s%s" % (", ".join(shown), extra)
            if missing_inv and not missing_vm:
                reason = "hosts not in inventory: %s%s" % (", ".join(shown), extra)
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason=reason,
                hint=hint,
                missing=missing,
            )
        return ProvisionState(provider=self.name, provisioned=True)

    def host_status(self) -> Dict[str, Dict[str, Any]]:
        status: Dict[str, Dict[str, Any]] = {}
        for name, state in self._machine_states().items():
            status[name] = {
                "state": state,
                "reachable": state in _RUNNING,
            }
        return status

    def _select_hosts(self, hosts: Optional[Sequence[str]]) -> List[str]:
        if not hosts:
            return []
        return [str(name) for name in hosts]

    def suspend(
        self,
        yes: bool = False,
        agent: bool = False,
        wait: bool = True,
        hosts: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        del wait
        if not yes and agent:
            raise ProviderError("suspend requires -y/--yes in agent mode.")
        names = self._select_hosts(hosts)
        self._run(["halt", *names], capture=False, check=True)
        states = self._machine_states()
        selected = names or list(states)
        return {
            "instances": [
                {"name": name, "state": states.get(name, "unknown")}
                for name in selected
            ],
            "note": "VirtualBox VMs halted; disks and Vagrant state are kept.",
        }

    def resume(
        self,
        yes: bool = False,
        agent: bool = False,
        wait: bool = True,
        hosts: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        del wait
        if not yes and agent:
            raise ProviderError("resume requires -y/--yes in agent mode.")
        names = self._select_hosts(hosts)
        self._run(["up", *names], capture=False, check=True)
        states = self._machine_states()
        selected = names or list(states)
        return {
            "instances": [
                {"name": name, "state": states.get(name, "unknown")}
                for name in selected
            ],
            "inventory": str(self.paths.inventory_dir / "hosts"),
        }
