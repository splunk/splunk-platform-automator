"""VirtualBox lifecycle via Vagrant (Vagrantfile stays in SPA_HOME)."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
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
from spa.runlog import PROVIDER_SOURCE, VAGRANT_GROUP

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

    def _vagrantfile(self):
        return self.paths.spa_home / "Vagrantfile"

    def _ansible_dir(self, required: bool) -> Optional[str]:
        """Directory holding ansible, usually the SPA venv and not on PATH."""
        try:
            return str(Path(tool_path(self.paths, "ansible")).parent)
        except ToolNotFound as exc:
            if required:
                raise ProviderError(str(exc)) from exc
            return None

    def _vagrant_env(self) -> Dict[str, str]:
        env = {**os.environ, **self.paths.export_env()}
        env["VAGRANT_CWD"] = str(self.paths.spa_home)
        env["VAGRANT_DOTFILE_PATH"] = str(self.paths.spa_env_dir / ".vagrant")
        # The Vagrantfile looks for ansible on PATH; spa keeps it in the venv.
        ansible_dir = self._ansible_dir(required=False)
        if ansible_dir:
            path = env.get("PATH", "")
            if ansible_dir not in path.split(os.pathsep):
                env["PATH"] = ansible_dir + (os.pathsep + path if path else "")
        return env

    def _require_vagrantfile(self) -> None:
        if not self._vagrantfile().is_file():
            raise ProviderError(
                "Vagrantfile not found in SPA_HOME (%s). VirtualBox lifecycle "
                "runs Vagrant from the framework tree."
                % self.paths.spa_home
            )

    def _require_clean_machine_state(self) -> None:
        """Vagrant reuses the provider recorded per machine, even a removed one."""
        machines = self.paths.spa_env_dir / ".vagrant" / "machines"
        if not machines.is_dir():
            return
        stale = [
            state
            for machine in sorted(machines.iterdir())
            if machine.is_dir()
            for state in sorted(machine.iterdir())
            if state.is_dir() and state.name != self.name
        ]
        if not stale:
            return
        raise ProviderError(
            "Vagrant state for another provider (%s) in %s. Vagrant would keep "
            "using that provider for %s. Remove it: rm -rf %s"
            % (
                ", ".join(sorted({state.name for state in stale})),
                machines,
                ", ".join(sorted({state.parent.name for state in stale})),
                " ".join(str(state) for state in stale),
            )
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
        run_log: Any = None,
    ) -> subprocess.CompletedProcess:
        self._require_vagrantfile()
        self._require_clean_machine_state()
        cmd = [self._vagrant_bin(), *args]
        if run_log is not None and not capture:
            run_log.emit(
                {
                    "status": "ok",
                    "source": PROVIDER_SOURCE,
                    "phase": VAGRANT_GROUP,
                    "task": " ".join(["vagrant", *args[:1]]),
                }
            )
            run_log.start_heartbeat()
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.paths.spa_home),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._vagrant_env(),
            )
            assert proc.stdout is not None
            assert proc.stderr is not None
            chunks: List[str] = []
            errors: List[str] = []

            def _consume(line: str, from_stderr: bool) -> None:
                (errors if from_stderr else chunks).append(line)
                if getattr(run_log, "native_output", False):
                    run_log.emit_native_output(line)
                run_log.consume_provider_line(line)

            def _read_stderr() -> None:
                for line in proc.stderr:  # type: ignore[union-attr]
                    _consume(line, True)

            err_thread = threading.Thread(
                target=_read_stderr, name="spa-vagrant-stderr", daemon=True
            )
            err_thread.start()
            for line in proc.stdout:
                _consume(line, False)
            rc = proc.wait()
            err_thread.join(timeout=5)
            if rc != 0 and not getattr(run_log, "saw_failure", False):
                # Vagrant reports errors on stderr, and its first line is the
                # headline; fall back to the last thing printed at all.
                detail = next((text.strip() for text in errors if text.strip()), "")
                if not detail:
                    detail = next((text.strip() for text in reversed(chunks) if text.strip()), "")
                run_log.emit(
                    {
                        "status": "failed",
                        "source": PROVIDER_SOURCE,
                        "phase": VAGRANT_GROUP,
                        "task": " ".join(["vagrant", *args[:1]]),
                        "msg": detail or ("vagrant exited %s" % rc),
                    }
                )
            if check and rc != 0:
                raise ProviderError("vagrant %s failed (exit %s)" % (" ".join(args), rc))
            return subprocess.CompletedProcess(
                cmd, rc, stdout="".join(chunks), stderr="".join(errors)
            )
        result = subprocess.run(
            cmd,
            cwd=str(self.paths.spa_home),
            capture_output=capture,
            text=True,
            env=self._vagrant_env(),
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

    def provision(self, extra: List[str], **kwargs: Any) -> int:
        # The Vagrantfile exits 2 when ansible is missing; say so with the
        # venv hint instead of letting Vagrant print it as a bare error.
        self._ansible_dir(required=True)
        leftover = drop_ansible_extra(extra)
        result = self._run(
            ["up", *leftover],
            capture=False,
            check=False,
            run_log=kwargs.get("run_log"),
        )
        return result.returncode

    def destroy(self, extra: List[str], **kwargs: Any) -> int:
        self._ansible_dir(required=True)
        leftover = drop_ansible_extra(extra)
        args = ["destroy", "-f", *leftover]
        result = self._run(
            args,
            capture=False,
            check=False,
            run_log=kwargs.get("run_log"),
        )
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
        run_log: Any = None,
    ) -> Dict[str, Any]:
        del wait
        if not yes and agent:
            raise ProviderError("suspend requires -y/--yes in agent mode.")
        names = self._select_hosts(hosts)
        self._run(["halt", *names], capture=False, check=True, run_log=run_log)
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
        run_log: Any = None,
    ) -> Dict[str, Any]:
        del wait
        if not yes and agent:
            raise ProviderError("resume requires -y/--yes in agent mode.")
        names = self._select_hosts(hosts)
        self._run(["up", *names], capture=False, check=True, run_log=run_log)
        states = self._machine_states()
        selected = names or list(states)
        return {
            "instances": [
                {"name": name, "state": states.get(name, "unknown")}
                for name in selected
            ],
            "inventory": str(self.paths.inventory_dir / "hosts"),
        }
