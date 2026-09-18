"""JSON-serializable backend session used by the spa CLI and a future GUI.

Skills and agents call `bin/spa`, not this module. A later daemon wraps
LocalSpaSession; open_session(url=...) is reserved for that transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from spa.agent import COMMAND_SCHEMA, SCHEMA_VERSION
from spa.executil import apply_paths_env
from spa.paths import SpaPaths, env_dir_required_error, format_export, resolve_spa_paths


ProgressCallback = Callable[[Dict[str, Any]], None]


class HostLookupError(RuntimeError):
    """--hosts did not resolve against this env's inventory."""


class RemoteSessionNotImplemented(RuntimeError):
    """open_session(url=...) is reserved for a future controller daemon."""


def jsonable(value: Any) -> Any:
    """Convert Path / datetime values so CommandResult.data can be JSON-dumped."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return str(value)


@dataclass
class CommandResult:
    ok: bool
    data: Any = None
    error: Optional[str] = None
    code: int = 0

    def __post_init__(self) -> None:
        from spa.runlog import redact

        self.data = jsonable(self.data)
        if self.error:
            self.error = str(redact(self.error))
        if self.code == 0 and not self.ok:
            self.code = 1
        if self.ok and self.code != 0:
            self.ok = False

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": self.ok, "schema_version": SCHEMA_VERSION}
        if self.data is not None:
            payload["data"] = self.data
        if self.error:
            payload["error"] = self.error
        return payload


@runtime_checkable
class SpaSession(Protocol):
    """Backend port. The CLI and a future GUI both depend on this, not each other."""

    def schema(self) -> CommandResult: ...

    def env(self) -> CommandResult: ...

    def catalog(self, extra_dir: Optional[str] = None) -> CommandResult: ...

    def describe_playbook(
        self, name: str, extra_dir: Optional[str] = None
    ) -> CommandResult: ...

    def validate(
        self,
        config: Optional[str] = None,
        check_licenses: bool = False,
        splunk_config_aws: bool = False,
        agent: bool = False,
    ) -> CommandResult: ...

    def doctor(
        self,
        spa_home: Optional[str] = None,
        env_dir: Optional[str] = None,
        aws: bool = False,
        virtualbox: bool = False,
        strict: bool = False,
    ) -> CommandResult: ...

    def venv(
        self,
        action: str = "path",
        environment: bool = False,
        python: Optional[str] = None,
        no_install: bool = False,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult: ...

    def init(
        self,
        env_dir: str,
        example: Optional[str] = None,
        example_set: bool = False,
        from_dir: Optional[str] = None,
        migrate_set: bool = False,
        keep_source: bool = False,
        force: bool = False,
        env_venv: bool = False,
        python: Optional[str] = None,
        ansible: Optional[str] = None,
        pip_pkgs: Optional[Sequence[str]] = None,
        skip_doctor: bool = False,
        rebuild_venv: bool = False,
        software_dir: Optional[str] = None,
        baseconfig_dir: Optional[str] = None,
        apps_dir: Optional[str] = None,
        provider: Optional[str] = None,
        registry_name: Optional[str] = None,
    ) -> CommandResult: ...

    def list_examples(self) -> CommandResult: ...

    def environment_list(self) -> CommandResult: ...

    def environment_set(
        self,
        env_dir: Optional[str] = None,
        provider: Optional[str] = None,
        software_dir: Optional[str] = None,
        baseconfig_dir: Optional[str] = None,
        apps_dir: Optional[str] = None,
        default: Optional[str] = None,
    ) -> CommandResult: ...

    def environment_remove(
        self, name: str, confirm: bool = False, force: bool = False
    ) -> CommandResult: ...

    def features(
        self,
        action: str = "list",
        ident: Optional[str] = None,
        query: Optional[str] = None,
        include_keys: bool = False,
    ) -> CommandResult: ...

    def apps(
        self,
        action: str,
        query: Optional[str] = None,
        app_id: Optional[str] = None,
        limit: int = 10,
        app_type: Optional[str] = None,
        kind: Optional[str] = None,
        version: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        source: str = "splunkbase",
        extract: bool = False,
        overwrite: bool = False,
        customize: bool = False,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult: ...

    def provision(
        self,
        extra: Optional[List[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult: ...

    def destroy(
        self,
        extra: Optional[List[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult: ...

    def deploy(
        self,
        extra: Optional[List[str]] = None,
        verbose: bool = False,
        hosts: Optional[Sequence[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        skip_provision_check: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult: ...

    def suspend(
        self,
        confirm: bool = False,
        wait: bool = True,
        agent: bool = False,
        hosts: Optional[Sequence[str]] = None,
        ansible_output: bool = False,
    ) -> CommandResult: ...

    def resume(
        self,
        confirm: bool = False,
        wait: bool = True,
        agent: bool = False,
        hosts: Optional[Sequence[str]] = None,
        ansible_output: bool = False,
    ) -> CommandResult: ...

    def run(
        self,
        name: str,
        extra: Optional[List[str]] = None,
        extra_dir: Optional[str] = None,
        verbose: bool = False,
        hosts: Optional[Sequence[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        apps_playbook: Optional[str] = None,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult: ...

    def logs(
        self,
        run_id: Optional[str] = None,
        last: bool = False,
        follow: bool = False,
        ansible_output: bool = False,
    ) -> CommandResult: ...

    def aws(self, argv: Optional[List[str]] = None) -> CommandResult: ...

    def licenses(
        self,
        software_dir: Optional[str] = None,
        config: Optional[str] = None,
        env_recommend: bool = True,
    ) -> CommandResult: ...

    def hosts_list(
        self, status: bool = False, hosts: Optional[Sequence[str]] = None
    ) -> CommandResult: ...

    def shell_list(self, verbose: bool = False, hosts: Optional[Sequence[str]] = None) -> CommandResult: ...


class LocalSpaSession:
    """In-process backend against SPA_HOME / SPA_ENV_DIR on this machine."""

    def __init__(
        self,
        start_dir: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
        paths: Optional[SpaPaths] = None,
    ) -> None:
        self.on_progress = on_progress
        if paths is not None:
            self.paths = paths
        else:
            start = Path(start_dir).resolve() if start_dir else None
            self.paths = resolve_spa_paths(start_dir=start)
        apply_paths_env(self.paths)

    def _env_gate(self) -> Optional[CommandResult]:
        message = env_dir_required_error(self.paths)
        if message:
            return CommandResult(ok=False, error=message, code=2)
        return None

    def _venv_gate(self) -> Optional[CommandResult]:
        """Ansible/provider work needs the venv; say so instead of ImportError."""
        from spa.executil import venv_required_error

        message = venv_required_error(self.paths)
        if message:
            return CommandResult(ok=False, error=message, code=2)
        return None

    def _app_deployment_config(self) -> Dict[str, Any]:
        """splunk_config.yml mapping so Splunkbase creds can come from config."""
        from spa.preflight import load_config_mapping

        try:
            return load_config_mapping(self.paths.config_file)
        except Exception:  # unreadable or invalid YAML: spa validate reports it
            return {}

    def _provision_state(self):
        """Shared provision gate used by deploy, hosts list --status, ssh, and copy."""
        from spa.providers import lookup_provision_state

        return lookup_provision_state(self.paths)

    def _require_provisioned(
        self, extra_line: Optional[str] = None
    ) -> Optional[CommandResult]:
        """Return a failure when check_provisioned says hosts are not up yet."""
        state = self._provision_state()
        if state is None or state.provisioned:
            return None
        return CommandResult(
            ok=False,
            code=1,
            error=state.message(extra_line),
            data=state.payload(),
        )

    def _progress(self, event: Dict[str, Any]) -> None:
        if self.on_progress:
            self.on_progress(jsonable(event))

    def _run_log(
        self,
        command: str,
        playbook: str,
        agent: bool,
        ansible_output: bool,
        native_output: bool = False,
        provider: str = "",
    ):
        from spa.runlog import RunLog

        return RunLog(
            self.paths,
            command=command,
            playbook=playbook,
            agent=agent,
            ansible_output=ansible_output,
            native_output=native_output,
            provider=provider,
        )

    def schema(self) -> CommandResult:
        data = dict(COMMAND_SCHEMA)
        data["schema_version"] = SCHEMA_VERSION
        return CommandResult(ok=True, data=data)

    def env(self) -> CommandResult:
        return CommandResult(
            ok=True,
            data={
                "export": self.paths.export_env(),
                "shell": format_export(self.paths),
            },
        )

    def catalog(self, extra_dir: Optional[str] = None) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.playbooks import MetadataError, catalog

        try:
            rows = catalog(self.paths, extra_dir=extra_dir)
        except MetadataError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=rows)

    def describe_playbook(self, name: str, extra_dir: Optional[str] = None) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.playbooks import MetadataError, PlaybookError, describe

        try:
            data = describe(name, self.paths, extra_dir=extra_dir)
        except (MetadataError, PlaybookError) as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=data)

    def list_examples(self) -> CommandResult:
        from spa.init import list_examples

        return CommandResult(ok=True, data=list_examples(self.paths.spa_home))

    def features(
        self,
        action: str = "list",
        ident: Optional[str] = None,
        query: Optional[str] = None,
        include_keys: bool = False,
    ) -> CommandResult:
        from spa.catalog import (
            feature_key_details,
            format_feature_text,
            get_feature,
            key_inventory,
            list_payload,
            load_features,
            search_features,
            summarize_feature,
        )

        spa_home = self.paths.spa_home
        if include_keys and action != "show":
            return CommandResult(
                ok=False,
                error="spa features --keys requires: spa features show ID --keys",
                code=2,
            )
        try:
            if action == "keys":
                return CommandResult(ok=True, data=key_inventory(spa_home))
            features = load_features(spa_home)
        except (OSError, ValueError) as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        if action == "list":
            return CommandResult(ok=True, data=list_payload(spa_home))
        if action == "search":
            if not (query or "").strip():
                return CommandResult(ok=False, error="spa features search QUERY", code=2)
            found = search_features(features, query or "")
            return CommandResult(
                ok=True,
                data={
                    "query": query,
                    "features": [summarize_feature(item) for item in found],
                },
            )
        if action == "show":
            if not (ident or "").strip():
                return CommandResult(ok=False, error="spa features show ID", code=2)
            item = get_feature(features, ident or "")
            if item is None:
                return CommandResult(
                    ok=False, error="Unknown feature: %s" % ident, code=1
                )
            feature = dict(item)
            feature.pop("keys", None)
            details = feature_key_details(item) if include_keys else None
            if details is not None:
                feature["key_details"] = details
            return CommandResult(
                ok=True,
                data={
                    "feature": feature,
                    "text": format_feature_text(item, key_details=details),
                },
            )
        return CommandResult(ok=False, error="Unknown spa features action: %s" % action, code=2)

    def apps(
        self,
        action: str,
        query: Optional[str] = None,
        app_id: Optional[str] = None,
        limit: int = 10,
        app_type: Optional[str] = None,
        kind: Optional[str] = None,
        version: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        source: str = "splunkbase",
        extract: bool = False,
        overwrite: bool = False,
        customize: bool = False,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        from spa.apps import AppsError, download, search, snippet
        from spa.splunkbase import SplunkbaseError

        try:
            if action == "search":
                data = search(
                    query or "",
                    limit=limit,
                    app_type=app_type,
                    kind=kind,
                    spa_home=self.paths.spa_home,
                )
                return CommandResult(ok=True, data=data)
            if action == "snippet":
                if source == "local":
                    blocked = self._env_gate()
                    if blocked:
                        return blocked
                data = snippet(
                    app_id,
                    version=version or "latest",
                    roles=roles,
                    source=source,
                    apps_dir=self.paths.apps_dir if source == "local" else None,
                    spa_home=self.paths.spa_home,
                    customize=customize,
                )
                return CommandResult(ok=True, data=data)
            if action == "download":
                blocked = self._env_gate()
                if blocked:
                    return blocked
                blocked = self._confirm_gate(
                    "apps download",
                    confirm=confirm,
                    agent=agent,
                    details=[
                        "apps_dir: %s" % self.paths.apps_dir,
                        "extract: %s" % bool(extract),
                        "overwrite: %s" % bool(overwrite),
                    ],
                    risk="mutating",
                )
                if blocked:
                    return blocked
                data = download(
                    app_id,
                    self.paths.apps_dir,
                    version=version or "latest",
                    extract=extract,
                    overwrite=overwrite,
                    config=self._app_deployment_config(),
                )
                return CommandResult(ok=True, data=data)
        except AppsError as exc:
            message = str(exc)
            code = 2 if "must be an integer" in message or message.startswith("spa apps search") else 1
            return CommandResult(ok=False, error=message, code=code)
        except SplunkbaseError as exc:
            message = str(exc)
            code = 2 if message == "spa apps search QUERY" else 1
            return CommandResult(ok=False, error=message, code=code)
        return CommandResult(ok=False, error="Unknown spa apps action: %s" % action, code=2)

    def validate(
        self,
        config: Optional[str] = None,
        check_licenses: bool = False,
        splunk_config_aws: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.validate import validate_env

        return validate_env(
            self.paths,
            config=config,
            check_licenses=check_licenses,
            splunk_config_aws=splunk_config_aws,
            on_progress=self.on_progress,
            agent=agent,
        )

    def doctor(
        self,
        spa_home: Optional[str] = None,
        env_dir: Optional[str] = None,
        aws: bool = False,
        virtualbox: bool = False,
        strict: bool = False,
    ) -> CommandResult:
        from spa.doctor import collect_checks

        return collect_checks(
            spa_home=spa_home,
            env_dir=env_dir,
            aws=aws,
            virtualbox=virtualbox,
            strict=strict,
        )

    def venv(
        self,
        action: str = "path",
        environment: bool = False,
        python: Optional[str] = None,
        no_install: bool = False,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        if action not in {"path", "create", "reinstall", "upgrade", "rebuild"}:
            return CommandResult(ok=False, error="Unknown spa venv action: %s" % action, code=2)
        if environment:
            blocked = self._env_gate()
            if blocked:
                return blocked
            target = self.paths.spa_env_dir / ".venv"
        else:
            target = self.paths.spa_home / ".venv"
        if action != "path":
            blocked = self._confirm_gate(
                "%s the %s SPA venv"
                % (action, "environment" if environment else "shared"),
                confirm=confirm,
                agent=agent,
                details=["venv: %s" % target],
                risk="local_destructive" if action == "rebuild" else "local",
            )
            if blocked:
                return blocked
        script = self.paths.spa_home / "bin" / "spa_venv.sh"
        if not script.is_file():
            return CommandResult(ok=False, error="Missing %s" % script, code=1)
        flag = "--path" if action == "path" else "--%s" % action
        cmd = ["bash", str(script), flag, "--dir", str(target)]
        if python:
            cmd.extend(["--python", python])
        if no_install:
            cmd.append("--no-install")
        from spa.executil import run_venv_script

        def _step(label: str) -> None:
            if self.on_progress:
                self.on_progress({"step": label})

        code, stdout, log, progress = run_venv_script(cmd, on_step=_step)
        data: Dict[str, Any] = {
            "action": action,
            "scope": "environment" if environment else "shared",
            "path": str(target),
            "progress": progress,
            "stdout": stdout,
            "log": log,
        }
        return CommandResult(
            ok=code == 0,
            code=code,
            data=data,
            error=None if code == 0 else (log.strip() or "spa venv failed"),
        )

    def init(
        self,
        env_dir: str,
        example: Optional[str] = None,
        example_set: bool = False,
        from_dir: Optional[str] = None,
        migrate_set: bool = False,
        keep_source: bool = False,
        force: bool = False,
        env_venv: bool = False,
        python: Optional[str] = None,
        ansible: Optional[str] = None,
        pip_pkgs: Optional[Sequence[str]] = None,
        skip_doctor: bool = False,
        rebuild_venv: bool = False,
        software_dir: Optional[str] = None,
        baseconfig_dir: Optional[str] = None,
        apps_dir: Optional[str] = None,
        provider: Optional[str] = None,
        registry_name: Optional[str] = None,
    ) -> CommandResult:
        from spa.init import InitError, init_env

        messages: List[str] = []
        try:
            rc = init_env(
                Path(env_dir),
                self.paths.spa_home,
                example=example,
                example_set=example_set,
                from_dir=Path(from_dir) if from_dir else None,
                migrate_set=migrate_set,
                keep_source=keep_source,
                force=force,
                env_venv=env_venv,
                python=python,
                ansible=ansible,
                pip_pkgs=pip_pkgs,
                skip_doctor=skip_doctor,
                rebuild_venv=rebuild_venv,
                log=messages,
                software_dir=software_dir,
                baseconfig_dir=baseconfig_dir,
                apps_dir=apps_dir,
                provider=provider,
                registry_name=registry_name,
            )
        except InitError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code, data={"messages": messages})
        dest = str(Path(env_dir).resolve())
        return CommandResult(
            ok=rc == 0,
            code=rc,
            data={"env_dir": dest, "name": registry_name or Path(env_dir).name, "messages": messages},
            error=None if rc == 0 else "init failed",
        )

    def environment_list(self) -> CommandResult:
        from spa.registry import RegistryError, list_environments

        try:
            rows = list_environments()
        except RegistryError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        return CommandResult(ok=True, data={"environments": rows})

    def environment_set(
        self,
        env_dir: Optional[str] = None,
        provider: Optional[str] = None,
        software_dir: Optional[str] = None,
        baseconfig_dir: Optional[str] = None,
        apps_dir: Optional[str] = None,
        default: Optional[str] = None,
    ) -> CommandResult:
        from spa.paths import save_user_paths, user_paths_yml
        from spa.registry import (
            RegistryError,
            set_default_env_dir,
            set_default_environment,
            set_default_provider,
        )

        if not any((env_dir, provider, software_dir, baseconfig_dir, apps_dir, default)):
            return CommandResult(
                ok=False,
                error=(
                    "spa environment set: pass --env-dir, --software-dir, "
                    "--baseconfig-dir, --apps-dir, --default, and/or --provider"
                ),
                code=2,
            )
        data: Dict[str, Any] = {}
        try:
            if software_dir or baseconfig_dir or apps_dir:
                save_user_paths(
                    software_dir=software_dir,
                    baseconfig_dir=baseconfig_dir,
                    apps_dir=apps_dir,
                )
                data["paths_yml"] = str(user_paths_yml())
                if software_dir:
                    data["software_dir"] = software_dir
                if baseconfig_dir:
                    data["baseconfig_dir"] = baseconfig_dir
                if apps_dir:
                    data["apps_dir"] = apps_dir
            if env_dir:
                path = set_default_env_dir(env_dir)
                data["env_dir"] = str(path)
                data["paths_yml"] = str(path)
            if default:
                registry_path = set_default_environment(default)
                data["default"] = default
                data["environments_yml"] = str(registry_path)
            if provider:
                prov_path = set_default_provider(provider)
                data["provider"] = provider
                data["providers_yml"] = str(prov_path) if prov_path else None
        except RegistryError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        return CommandResult(ok=True, data=data)

    def environment_remove(
        self, name: str, confirm: bool = False, force: bool = False
    ) -> CommandResult:
        from spa.registry import RegistryError, remove_environment

        try:
            payload = remove_environment(name, confirm=confirm, force=force)
        except RegistryError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        return CommandResult(ok=True, data=payload)

    def _confirm_gate(
        self,
        label: str,
        *,
        confirm: bool,
        agent: bool,
        details: Optional[Sequence[str]] = None,
        risk: Optional[str] = None,
    ) -> Optional[CommandResult]:
        from spa.confirm import ConfirmationError, ensure_confirmed

        try:
            ensure_confirmed(
                label, confirm=confirm, agent=agent, details=details, risk=risk
            )
        except ConfirmationError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return None

    @staticmethod
    def _confirm_details(hosts: Optional[Sequence[str]] = None) -> Optional[List[str]]:
        if not hosts:
            return None
        from spa.hosts import format_names

        return ["hosts: %s" % format_names(hosts)]

    def provision(
        self,
        extra: Optional[List[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        return self._lifecycle_playbook(
            "provision",
            extra,
            confirm,
            agent,
            ansible_output=ansible_output,
            native_output=native_output,
        )

    def destroy(
        self,
        extra: Optional[List[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        return self._lifecycle_playbook(
            "destroy",
            extra,
            confirm,
            agent,
            ansible_output=ansible_output,
            native_output=native_output,
        )

    def _lifecycle_playbook(
        self,
        action: str,
        extra: Optional[List[str]],
        confirm: bool,
        agent: bool,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult:
        from spa.confirm import LIFECYCLE_RISK

        blocked = self._venv_gate()
        if blocked:
            return blocked
        from spa.providers import ProviderError, get_provider

        blocked = self._confirm_gate(
            action,
            confirm=confirm,
            agent=agent,
            risk=LIFECYCLE_RISK.get(action),
        )
        if blocked:
            return blocked
        args = ["-e", "auto_approve=true", *list(extra or [])]
        log = None
        rc = 1
        try:
            provider = get_provider(self.paths)
            if provider.name == "aws":
                playbook = "aws_provision" if action == "provision" else "aws_destroy"
            else:
                playbook = "vagrant_up" if action == "provision" else "vagrant_destroy"
            log = self._run_log(
                action,
                playbook,
                agent,
                ansible_output,
                native_output,
                provider=provider.name,
            )
            rc = getattr(provider, action)(
                args,
                run_log=log,
                agent=agent,
                ansible_output=ansible_output,
                native_output=native_output,
                command=action,
            )
        except ProviderError as exc:
            data = log.envelope_fields() if log is not None else None
            if log is not None:
                log.finish(1)
            return CommandResult(ok=False, error=str(exc), code=1, data=data)
        log.finish(rc)
        data = {"provider": provider.name, "action": action}
        data.update(log.envelope_fields())
        return CommandResult(
            ok=rc == 0,
            code=rc,
            data=data,
            error=None if rc == 0 else "%s failed" % action,
        )

    def _resolve_hosts(self, hosts: Optional[Sequence[str]]) -> Optional[List[str]]:
        from spa.hosts import HostsError, parse_host_tokens, resolve_hosts
        from spa import shell as shell_mod

        tokens = parse_host_tokens(hosts)
        if not tokens:
            return None
        try:
            inventory = shell_mod.get_inventory_data()
            return resolve_hosts(inventory, tokens)
        except (HostsError, shell_mod.ShellError) as exc:
            raise HostLookupError(str(exc)) from exc

    def deploy(
        self,
        extra: Optional[List[str]] = None,
        verbose: bool = False,
        hosts: Optional[Sequence[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        skip_provision_check: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.hosts import with_ansible_limit
        from spa.playbooks import PlaybookError, resolve, run_playbook
        from spa.preflight import check_controller_data, controller_data_error

        controller = check_controller_data(self.paths)
        if not controller.ok:
            return CommandResult(
                ok=False,
                code=1,
                error=controller_data_error(controller),
                data={
                    "software_dir": controller.software_dir,
                    "baseconfig_dir": controller.baseconfig_dir,
                    "apps_dir": controller.apps_dir,
                    "missing": list(controller.missing),
                },
            )

        provision = self._provision_state()
        if not skip_provision_check:
            blocked = self._require_provisioned(
                "Or: spa deploy --yes --allow-unprovisioned"
            )
            if blocked:
                return blocked

        try:
            resolved = self._resolve_hosts(hosts)
        except HostLookupError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        blocked = self._confirm_gate(
            "deploy",
            confirm=confirm,
            agent=agent,
            details=self._confirm_details(resolved),
            risk="mutating",
        )
        if blocked:
            return blocked
        args = with_ansible_limit(extra, resolved)
        try:
            playbook = resolve("deploy_site", self.paths)
        except PlaybookError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        log = self._run_log(
            "deploy", str(playbook), agent, ansible_output or verbose, native_output
        )
        rc = run_playbook(
            playbook,
            self.paths,
            args,
            on_progress=self.on_progress,
            command="deploy",
            agent=agent,
            ansible_output=ansible_output or verbose,
            native_output=native_output,
            run_log=log,
        )
        log.finish(rc)
        data: Dict[str, Any] = {"playbook": "deploy_site"}
        data.update(log.envelope_fields())
        if resolved:
            data["hosts"] = resolved
        if skip_provision_check:
            data["provision_check_skipped"] = True
            if provision is not None:
                data["provisioned"] = provision.provisioned
                data["provider"] = provision.provider
                if provision.missing:
                    data["missing"] = list(provision.missing)
        return CommandResult(
            ok=rc == 0,
            code=rc,
            data=data,
            error=None if rc == 0 else "playbook failed",
        )

    def suspend(
        self,
        confirm: bool = False,
        wait: bool = True,
        agent: bool = False,
        hosts: Optional[Sequence[str]] = None,
        ansible_output: bool = False,
    ) -> CommandResult:
        return self._power(
            "suspend",
            confirm=confirm,
            wait=wait,
            agent=agent,
            hosts=hosts,
            ansible_output=ansible_output,
        )

    def resume(
        self,
        confirm: bool = False,
        wait: bool = True,
        agent: bool = False,
        hosts: Optional[Sequence[str]] = None,
        ansible_output: bool = False,
    ) -> CommandResult:
        return self._power(
            "resume",
            confirm=confirm,
            wait=wait,
            agent=agent,
            hosts=hosts,
            ansible_output=ansible_output,
        )

    def _power(
        self,
        action: str,
        confirm: bool,
        wait: bool,
        agent: bool,
        hosts: Optional[Sequence[str]] = None,
        ansible_output: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        blocked = self._require_provisioned()
        if blocked:
            return blocked
        from spa.confirm import LIFECYCLE_RISK
        from spa.providers import ProviderError, get_provider

        try:
            resolved = self._resolve_hosts(hosts)
        except HostLookupError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        blocked = self._confirm_gate(
            action,
            confirm=confirm,
            agent=agent,
            details=self._confirm_details(resolved),
            risk=LIFECYCLE_RISK.get(action),
        )
        if blocked:
            return blocked
        try:
            provider = get_provider(self.paths)
        except ProviderError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        log = self._run_log(action, action, agent, ansible_output, provider=provider.name)
        log.emit({"status": "ok", "phase": "power", "task": action})
        try:
            data = getattr(provider, action)(
                yes=True, agent=agent, wait=wait, hosts=resolved, run_log=log
            )
        except ProviderError as exc:
            log.finish(1)
            payload = log.envelope_fields()
            return CommandResult(ok=False, error=str(exc), code=1, data=payload)
        log.finish(0)
        payload = dict(data or {})
        payload["provider"] = provider.name
        payload["action"] = action
        payload.update(log.envelope_fields())
        if resolved:
            payload["hosts"] = resolved
        return CommandResult(ok=True, data=payload)

    def run(
        self,
        name: str,
        extra: Optional[List[str]] = None,
        extra_dir: Optional[str] = None,
        verbose: bool = False,
        hosts: Optional[Sequence[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        apps_playbook: Optional[str] = None,
        ansible_output: bool = False,
        native_output: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.confirm import requires_confirmation
        from spa.hosts import with_ansible_limit
        from spa.playbooks import (
            MetadataError,
            PlaybookError,
            parse_playbook_metadata,
            resolve_named,
            run_playbook,
        )

        try:
            resolved = self._resolve_hosts(hosts)
        except HostLookupError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        args = list(extra or [])
        if apps_playbook:
            from spa.app_playbooks import AppPlaybookError, resolve_apps_playbook, run_extra_vars

            try:
                row = resolve_apps_playbook(
                    self.paths.spa_home,
                    apps_playbook,
                    spa_env_dir=self.paths.spa_env_dir,
                )
            except AppPlaybookError as exc:
                return CommandResult(ok=False, error=str(exc), code=2)
            args = run_extra_vars(row) + args
        args = with_ansible_limit(args, resolved)
        try:
            playbook, renamed_from, canonical = resolve_named(name, self.paths, extra_dir=extra_dir)
            meta = parse_playbook_metadata(playbook)
        except (PlaybookError, MetadataError) as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        missing = meta is None
        risk = None if missing else meta.get("risk")
        if requires_confirmation(risk=risk, missing_metadata=missing):
            blocked = self._confirm_gate(
                "run %s" % canonical,
                confirm=confirm,
                agent=agent,
                details=self._confirm_details(resolved),
                risk=risk if isinstance(risk, str) else None,
            )
            if blocked:
                return blocked
        if meta and meta.get("requires_provisioned"):
            blocked = self._require_provisioned()
            if blocked:
                return blocked
        log = self._run_log(
            "run", str(playbook), agent, ansible_output or verbose, native_output
        )
        rc = run_playbook(
            playbook,
            self.paths,
            args,
            on_progress=self.on_progress,
            command="run",
            agent=agent,
            ansible_output=ansible_output or verbose,
            native_output=native_output,
            run_log=log,
        )
        log.finish(rc)
        data: Dict[str, Any] = {"playbook": canonical, "path": str(playbook)}
        data.update(log.envelope_fields())
        if renamed_from:
            data["renamed_from"] = renamed_from
            data["use"] = canonical
        if resolved:
            data["hosts"] = resolved
        return CommandResult(
            ok=rc == 0,
            code=rc,
            data=data,
            error=None if rc == 0 else "playbook failed",
        )

    def aws(self, argv: Optional[List[str]] = None) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa import aws as aws_mod

        return aws_mod.execute_argv(list(argv or []))

    def licenses(
        self,
        software_dir: Optional[str] = None,
        config: Optional[str] = None,
        env_recommend: bool = True,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa import licenses as licenses_mod

        project_root = licenses_mod.resolve_env_root()
        config_path = None
        if config:
            config_path = Path(config).expanduser()
            if not config_path.is_absolute():
                config_path = (Path.cwd() / config_path).resolve()
                if not config_path.is_file():
                    config_path = (licenses_mod.repo_root_from_script() / config).resolve()
        try:
            data = licenses_mod.scan_licenses(
                project_root,
                software_dir=software_dir,
                config_path=config_path,
                env_recommend=env_recommend,
            )
        except Exception as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=data)

    def hosts_list(
        self, status: bool = False, hosts: Optional[Sequence[str]] = None
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa import shell as shell_mod

        try:
            provision = self._provision_state()
            runtime = not (
                status and provision is not None and not provision.provisioned
            )
            resolved = self._resolve_hosts(hosts)
            inventory = shell_mod.get_inventory_data()
            report = shell_mod.filter_report(
                shell_mod.host_report(
                    inventory,
                    verbose=status,
                    paths=self.paths,
                    runtime=runtime,
                ),
                resolved,
            )
            if status and not runtime and provision is not None:
                report.update(provision.payload())
                for row in report.get("hosts") or []:
                    row["provider"] = provision.provider
                    row["provider_status"] = "unprovisioned"
                    row["ansible"] = "unprovisioned"
        except HostLookupError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        except shell_mod.ShellError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=report)

    def logs(
        self,
        run_id: Optional[str] = None,
        last: bool = False,
        follow: bool = False,
        ansible_output: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.runlog import follow_jsonl, list_runs, load_run, read_jsonl, replay_jsonl

        rows = list_runs(self.paths)
        if not last and not follow and not run_id:
            return CommandResult(ok=True, data={"runs": rows})
        target = None
        if run_id:
            target = load_run(self.paths, run_id)
            if target is None:
                return CommandResult(ok=False, error="Unknown run: %s" % run_id, code=1)
        elif rows:
            target = rows[0]
        if target is None:
            return CommandResult(ok=False, error="No runs in %s/logs" % self.paths.spa_env_dir, code=1)
        from pathlib import Path

        log_path = Path(str(target.get("log") or ""))
        if follow:
            follow_jsonl(log_path, idle_passes=-1, ansible_output=ansible_output)
            return CommandResult(ok=True, data=target)
        target = dict(target)
        if ansible_output:
            target["replay"] = replay_jsonl(log_path)
        else:
            target["transcript"] = read_jsonl(log_path)
        return CommandResult(ok=True, data=target)

    def shell_list(
        self, verbose: bool = False, hosts: Optional[Sequence[str]] = None
    ) -> CommandResult:
        return self.hosts_list(status=verbose, hosts=hosts)


def open_session(
    start_dir: Optional[str] = None,
    url: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
    paths: Optional[SpaPaths] = None,
) -> LocalSpaSession:
    """Return a local session. url= is reserved for a future remote controller."""
    if url:
        raise RemoteSessionNotImplemented(
            "Remote controller sessions are not implemented. "
            "LocalSpaSession is the only backend; a later daemon will use url= / SPA_CONTROLLER."
        )
    return LocalSpaSession(start_dir=start_dir, on_progress=on_progress, paths=paths)
