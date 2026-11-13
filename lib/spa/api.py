"""JSON-serializable backend session used by the spa CLI and a future GUI.

Skills and agents call `bin/spa`, not this module. A later daemon wraps
LocalSpaSession; open_session(url=...) is reserved for that transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from spa.agent import COMMAND_SCHEMA, SCHEMA_VERSION
from spa.executil import apply_paths_env
from spa.paths import SpaPaths, env_dir_required_error, format_export, resolve_spa_paths


ProgressCallback = Callable[[Dict[str, Any]], None]


class HostLookupError(RuntimeError):
    """--hosts did not resolve against this env's inventory."""


def _subprocess_runner(argv: Sequence[str]) -> int:
    import subprocess

    return subprocess.run(
        list(argv), check=False, capture_output=True, text=True
    ).returncode


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


def _mutation_result(action: str, data: Any) -> CommandResult:
    payload = data if isinstance(data, dict) else {}
    if payload.get("ready") is False:
        parts = []
        for item in payload.get("requirements") or []:
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule_id") or "requirement")
            summary = str(item.get("summary") or "").split("\n", 1)[0].strip()
            parts.append("%s: %s" % (rule, summary) if summary else rule)
        detail = "; ".join(parts) if parts else "unresolved dependencies"
        return CommandResult(
            ok=False,
            data=payload,
            error="%s did not write: %s" % (action, detail),
            code=1,
        )
    return CommandResult(ok=True, data=data)


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
        splunk_config: Optional[str] = None,
        agent: bool = False,
    ) -> CommandResult: ...

    def doctor(
        self,
        spa_home: Optional[str] = None,
        env_dir: Optional[str] = None,
        provider: Optional[Sequence[str]] = None,
        strict: bool = False,
    ) -> CommandResult: ...

    def skills(
        self,
        action: str,
        platform: Optional[str] = None,
        name: Optional[str] = None,
        all_packages: bool = False,
        confirm: bool = False,
        agent: bool = False,
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
        architecture: Optional[str] = None,
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

    def environment_cleanup(self, confirm: bool = False, agent: bool = False) -> CommandResult: ...

    def config(
        self,
        action: str,
        paths: Optional[Sequence[str]] = None,
        value: Optional[str] = None,
        operand: Optional[str] = None,
        file: Optional[str] = None,
        value_file: Optional[str] = None,
        from_env: Optional[str] = None,
        from_env_fields: Optional[Sequence[Sequence[str]]] = None,
        explicit_default: bool = False,
        effective: bool = False,
        full: bool = False,
        dry_run: bool = False,
        expect_revision: Optional[str] = None,
        resolve: Optional[Sequence[Sequence[str]]] = None,
        resolve_file: Optional[str] = None,
        stdin_text: Optional[str] = None,
        confirm: bool = False,
        agent: bool = False,
        check_hand_edits: bool = False,
        header_fields: Optional[Dict[str, str]] = None,
        move_role: Optional[str] = None,
        move_from: Optional[str] = None,
        move_to: Optional[str] = None,
        move_prefix: Optional[str] = None,
        move_postfix: Optional[str] = None,
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
        set_values: Optional[Sequence[Sequence[str]]] = None,
        explicit_default: bool = False,
        content_packs: Optional[Sequence[str]] = None,
        install_all_content_packs: bool = False,
        content_pack: Optional[str] = None,
        archive: Optional[str] = None,
        force_new: bool = False,
        dry_run: bool = False,
        expect_revision: Optional[str] = None,
        resolve: Optional[Sequence[Sequence[str]]] = None,
        resolve_file: Optional[str] = None,
        stdin_text: Optional[str] = None,
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
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult: ...

    def destroy(
        self,
        extra: Optional[List[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult: ...

    def deploy(
        self,
        extra: Optional[List[str]] = None,
        verbose: bool = False,
        hosts: Optional[Sequence[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
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
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult: ...

    def logs(
        self,
        run_id: Optional[str] = None,
        last: bool = False,
        follow: bool = False,
        wait: bool = False,
        ansible_output: bool = False,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult: ...

    def aws(self, argv: Optional[List[str]] = None) -> CommandResult: ...

    def provider(
        self,
        child: str = "",
        action: Optional[str] = None,
        resource: Optional[str] = None,
        subaction: Optional[str] = None,
        hours: Optional[str] = None,
        days: Optional[int] = None,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult: ...

    def architecture_plan(self, path: str) -> CommandResult: ...

    def architecture_apply(
        self,
        path: str,
        confirm: bool = False,
        agent: bool = False,
        dry_run: bool = False,
        expect_revision: Optional[str] = None,
    ) -> CommandResult: ...

    def architecture_check(self, path: str) -> CommandResult: ...

    def licenses(
        self,
        software_dir: Optional[str] = None,
        config: Optional[str] = None,
        env_recommend: bool = True,
    ) -> CommandResult: ...

    def hosts_list(
        self, status: bool = False, hosts: Optional[Sequence[str]] = None
    ) -> CommandResult: ...

    def hosts_register(
        self,
        name: str,
        ssh_host: str,
        user: str,
        key: str,
        ssh_port: int = 22,
        roles: Optional[Sequence[str]] = None,
        ip_addr: Optional[str] = None,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult: ...

    def hosts_unregister(self, name: str, confirm: bool = False, agent: bool = False) -> CommandResult: ...

    def hosts_check(self, hosts: Optional[Sequence[str]] = None) -> CommandResult: ...

    def shell_list(self, verbose: bool = False, hosts: Optional[Sequence[str]] = None) -> CommandResult: ...

    def completion_script(self, shell: str) -> CommandResult: ...

    def complete(self, words: Sequence[str], index: int) -> CommandResult: ...


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

    def _apps_add_roles_choice(
        self, app_id: Optional[str], roles: Optional[Sequence[str]]
    ) -> Optional[CommandResult]:
        from spa.apps import AppsError, classify_kind, get_app, parse_app_id
        from spa.next_steps import roles_on_hosts, suggested_roles_for_app
        from spa.preflight import load_config_mapping

        if roles:
            return None
        try:
            parsed = parse_app_id(app_id)
            kind = classify_kind(parsed, get_app(parsed))
        except (AppsError, Exception):
            return None
        if kind not in {"ta", "es_not_premium"}:
            return None
        try:
            config = load_config_mapping(self.paths.config_file)
        except Exception:
            config = {}
        allowed = roles_on_hosts(config)
        suggested = [role for role in suggested_roles_for_app(parsed) if not allowed or role in allowed]
        retry = "spa --agent apps add %s --roles ROLE --yes" % parsed
        return CommandResult(
            ok=False,
            error="spa apps add needs --roles.",
            code=1,
            data={
                "ready": False,
                "app_id": parsed,
                "kind": kind,
                "requirements": [
                    {
                        "kind": "choice",
                        "rule_id": "apps.target_roles",
                        "summary": "Choose target_roles from roles on splunk_hosts.",
                        "allowed": allowed,
                        "suggested": suggested,
                        "retry": retry,
                    }
                ],
            },
        )

    def _lifecycle_next(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if action == "provision":
            from spa.next_steps import provision_next

            payload = dict(data)
            payload["next"] = provision_next(Path(self.paths.spa_env_dir).name)
            return payload
        if action == "deploy":
            from spa.next_steps import deploy_next

            payload = dict(data)
            payload["next"] = deploy_next(self.paths.spa_env_dir)
            return payload
        return data

    def _env_lookup_gate(self) -> Optional[CommandResult]:
        """Reject missing lookup targets before confirmation, inventory, or providers."""
        from spa.preflight import env_lookup_readiness, load_config_mapping, unresolved_env_message

        config_path = Path(self.paths.config_file)
        if not config_path.is_file():
            return None
        try:
            loaded = load_config_mapping(config_path)
        except Exception:
            return None
        message = unresolved_env_message(loaded)
        if not message:
            return None
        return CommandResult(
            ok=False,
            error=message,
            code=1,
            data={"env_lookups": env_lookup_readiness(loaded)},
        )

    def _schema_stamp_gate(self) -> Optional[CommandResult]:
        """Refuse provision/deploy until schema_version is authored. Does not write."""
        from spa.validate import require_authored_schema_version

        return require_authored_schema_version(Path(self.paths.config_file))

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

    def _deploy_create_needed(
        self, hosts: Optional[Sequence[str]]
    ) -> Tuple[bool, Optional[CommandResult]]:
        """Whether deploy should create missing managed hosts before the playbook."""
        from spa.providers import deploy_create_plan

        plan = deploy_create_plan(self.paths, hosts)
        if plan.error:
            return False, CommandResult(
                ok=False, code=1, error=plan.error, data=plan.data
            )
        return plan.will_create, None

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
        verbosity: int = 0,
        provider: str = "",
        timestamps: bool = False,
        color: bool = False,
    ):
        from spa.runlog import RunLog

        return RunLog(
            self.paths,
            command=command,
            playbook=playbook,
            agent=agent,
            ansible_output=ansible_output,
            native_output=native_output,
            verbosity=verbosity,
            provider=provider,
            timestamps=timestamps,
            color=color,
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

    def _config_discovery(
        self,
        action: str,
        paths: Optional[Sequence[str]],
        agent: bool = False,
    ) -> CommandResult:
        from spa.catalog import config_schema_payload, key_inventory
        from spa.config_tree import explain_config, search_config

        target = ((paths or [None])[0] or "").strip()
        try:
            if action == "explain":
                return CommandResult(ok=True, data=explain_config(target))
            if action == "search":
                if not target:
                    return CommandResult(
                        ok=False,
                        error="spa config search needs QUERY.\nExample: spa config search QUERY",
                        code=2,
                    )
                return CommandResult(ok=True, data=search_config(target))
            if action == "keys":
                return CommandResult(ok=True, data=key_inventory(self.paths.spa_home))
            if action == "schema":
                if agent:
                    return CommandResult(
                        ok=False,
                        error=(
                            "spa config schema --markdown is a human docs dump.\n"
                            "Look up a setting with: spa config search QUERY\n"
                            "Then: spa config explain PATH"
                        ),
                        code=2,
                    )
                return CommandResult(ok=True, data=config_schema_payload(self.paths.spa_home))
        except KeyError:
            return CommandResult(ok=False, error="Unknown config path: %s" % target, code=1)
        except (OSError, ValueError) as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=False, error="Unknown spa config action: %s" % action, code=2)

    def config(
        self,
        action: str,
        paths: Optional[Sequence[str]] = None,
        value: Optional[str] = None,
        operand: Optional[str] = None,
        file: Optional[str] = None,
        value_file: Optional[str] = None,
        from_env: Optional[str] = None,
        from_env_fields: Optional[Sequence[Sequence[str]]] = None,
        explicit_default: bool = False,
        effective: bool = False,
        full: bool = False,
        dry_run: bool = False,
        expect_revision: Optional[str] = None,
        resolve: Optional[Sequence[Sequence[str]]] = None,
        resolve_file: Optional[str] = None,
        stdin_text: Optional[str] = None,
        confirm: bool = False,
        agent: bool = False,
        check_hand_edits: bool = False,
        header_fields: Optional[Dict[str, str]] = None,
        move_role: Optional[str] = None,
        move_from: Optional[str] = None,
        move_to: Optional[str] = None,
        move_prefix: Optional[str] = None,
        move_postfix: Optional[str] = None,
    ) -> CommandResult:
        from spa.init import InitError
        from spa.usage import MISSING_OPERAND
        from spa.config_edit import (
            ConfigEditError,
            config_add,
            config_audit,
            config_get,
            config_header_set,
            config_merge,
            config_migrate,
            merge_operand,
            config_move_host,
            config_move_role,
            config_provider,
            config_set,
            config_templates,
            config_topology,
            config_unset,
        )

        if action == "templates":
            return CommandResult(
                ok=True, data=config_templates(self.paths.spa_home)
            )
        if action in {"explain", "search", "keys", "schema"}:
            return self._config_discovery(action, paths, agent=agent)
        blocked = self._env_gate()
        if blocked:
            return blocked
        config_path = self.paths.config_file
        try:
            if action == "get":
                return CommandResult(
                    ok=True,
                    data=config_get(
                        config_path,
                        self.paths.spa_home,
                        (paths or [None])[0],
                        effective=effective,
                        full=full,
                    ),
                )
            if action == "audit":
                return CommandResult(
                    ok=True,
                    data=config_audit(config_path, check_hand_edits=check_hand_edits),
                )
            if action not in {
                "set",
                "add",
                "unset",
                "merge",
                "topology",
                "provider",
                "migrate",
                "header-set",
                "move-role",
                "move-host",
            }:
                return CommandResult(
                    ok=False,
                    error="Unknown spa config action: %s" % action,
                    code=2,
                )
            if action == "header-set":
                if agent or not dry_run:
                    blocked = self._confirm_gate(
                        "spa config header set",
                        confirm=confirm,
                        agent=agent,
                        details=["config: %s" % config_path],
                        risk="config_edit",
                    )
                    if blocked:
                        return blocked
                data = config_header_set(
                    config_path,
                    dict(header_fields or {}),
                    dry_run=dry_run,
                    expect_revision=expect_revision,
                )
                return _mutation_result("config header set", data)
            if action == "topology":
                if not operand:
                    raise ConfigEditError(MISSING_OPERAND[("spa config topology", "TOPOLOGY")])
                from spa.config_edit import resolve_topology_id

                resolve_topology_id(Path(self.paths.spa_home), operand)
            if not dry_run and not agent:
                label = {
                    "move-role": "move role",
                    "move-host": "move host",
                    "header-set": "header set",
                }.get(action, action)
                blocked = self._confirm_gate(
                    "spa config %s" % label,
                    confirm=confirm,
                    agent=False,
                    details=["config: %s" % config_path],
                    risk="config_edit",
                )
                if blocked:
                    return blocked
            common = {
                "dry_run": dry_run,
                "expect_revision": expect_revision,
            }
            if action == "set":
                if not paths:
                    raise ConfigEditError(MISSING_OPERAND[("spa config set", "PATH")])
                data = config_set(
                    config_path,
                    self.paths.spa_home,
                    paths[0],
                    value,
                    value_file=value_file,
                    from_env=from_env,
                    explicit_default=explicit_default,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            elif action == "add":
                if not paths:
                    raise ConfigEditError(MISSING_OPERAND[("spa config add", "SELECTOR")])
                data = config_add(
                    config_path,
                    self.paths.spa_home,
                    paths[0],
                    value,
                    value_file=value_file,
                    from_env=from_env_fields,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            elif action == "unset":
                if not paths:
                    raise ConfigEditError(MISSING_OPERAND[("spa config unset", "PATH")])
                data = config_unset(
                    config_path,
                    self.paths.spa_home,
                    list(paths),
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            elif action == "merge":
                data = config_merge(
                    config_path,
                    self.paths.spa_home,
                    merge_operand(operand, file),
                    stdin_text=stdin_text,
                    explicit_default=explicit_default,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    **common,
                )
            elif action == "move-role":
                data = config_move_role(
                    config_path,
                    self.paths.spa_home,
                    move_role or "",
                    from_host=move_from,
                    to_host=move_to,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            elif action == "move-host":
                data = config_move_host(
                    config_path,
                    self.paths.spa_home,
                    old_name=move_from,
                    new_name=move_to,
                    prefix=move_prefix,
                    postfix=move_postfix,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            elif action == "topology":
                if not operand:
                    raise ConfigEditError(MISSING_OPERAND[("spa config topology", "TOPOLOGY")])
                data = config_topology(
                    config_path,
                    self.paths.spa_home,
                    operand,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            elif action == "migrate":
                data = config_migrate(
                    config_path,
                    self.paths.spa_home,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            else:
                if not operand:
                    raise ConfigEditError(MISSING_OPERAND[("spa config provider", "PROVIDER")])
                data = config_provider(
                    config_path,
                    self.paths.spa_home,
                    operand,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                    **common,
                )
            label = {
                "move-role": "move role",
                "move-host": "move host",
                "header-set": "header set",
            }.get(action, action)
            return _mutation_result("config %s" % label, data)
        except InitError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        except ConfigEditError as exc:
            text = str(exc)
            usage = any(
                token in text
                for token in (
                    "needs PATH",
                    "needs SELECTOR",
                    "needs NAME",
                    "needs TEMPLATE",
                    "or --file, not both",
                    "uses spa config merge --file",
                    "needs TOPOLOGY",
                    "needs PROVIDER",
                    "needs --check-hand-edits",
                    "needs an identity selector",
                    "requires an identity list",
                    "requires a JSON object",
                    "identity must be one of",
                    "App entries use spa apps add",
                    "Unknown schema path",
                    "Unknown topology",
                    "strict JSON",
                    "Provide exactly",
                    "Config header field",
                    "Unknown config header field",
                )
            )
            return CommandResult(ok=False, error=text, code=2 if usage else 1)

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
        set_values: Optional[Sequence[Sequence[str]]] = None,
        explicit_default: bool = False,
        content_packs: Optional[Sequence[str]] = None,
        install_all_content_packs: bool = False,
        content_pack: Optional[str] = None,
        archive: Optional[str] = None,
        force_new: bool = False,
        dry_run: bool = False,
        expect_revision: Optional[str] = None,
        resolve: Optional[Sequence[Sequence[str]]] = None,
        resolve_file: Optional[str] = None,
        stdin_text: Optional[str] = None,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        from spa.apps import (
            AppsError,
            build_entry,
            content_pack_catalog,
            download,
            search,
            snippet,
        )
        from spa.config_edit import ConfigEditError, config_app_add, config_app_remove
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
                    set_values=set_values,
                )
                return CommandResult(ok=True, data=data)
            if action == "content-packs-list":
                if archive is None:
                    blocked = self._env_gate()
                    if blocked:
                        return blocked
                data = content_pack_catalog(
                    app_id or "5391",
                    version=version or "latest",
                    archive=Path(archive) if archive else None,
                    apps_dir=self.paths.apps_dir if archive is None else None,
                    spa_home=self.paths.spa_home,
                    config=self._app_deployment_config() if archive is None else None,
                    agent=agent,
                )
                return CommandResult(ok=True, data=data)
            if action in {"add", "remove"}:
                blocked = self._env_gate()
                if blocked:
                    return blocked
                if not dry_run and not agent:
                    blocked = self._confirm_gate(
                        "spa apps %s" % action,
                        confirm=confirm,
                        agent=False,
                        details=["config: %s" % self.paths.config_file],
                        risk="config_edit",
                    )
                    if blocked:
                        return blocked
                if action == "remove":
                    data = config_app_remove(
                        self.paths.config_file,
                        self.paths.spa_home,
                        str(app_id or ""),
                        content_pack=content_pack,
                        roles=roles,
                        dry_run=dry_run,
                        expect_revision=expect_revision,
                        resolve=resolve,
                        resolve_file=resolve_file,
                        stdin_text=stdin_text,
                    )
                    return _mutation_result("apps remove", data)
                missing_roles = self._apps_add_roles_choice(app_id, roles)
                if missing_roles:
                    return missing_roles
                built = build_entry(
                    app_id,
                    version=version or "latest",
                    roles=roles,
                    source=source,
                    apps_dir=self.paths.apps_dir if source == "local" else None,
                    spa_home=self.paths.spa_home,
                    customize=customize,
                    content_packs=content_packs,
                    install_all_content_packs=install_all_content_packs,
                    explicit_default=explicit_default,
                    set_values=set_values,
                    for_add=True,
                )
                data = config_app_add(
                    self.paths.config_file,
                    self.paths.spa_home,
                    built["entry"],
                    force_new=force_new,
                    dry_run=dry_run,
                    expect_revision=expect_revision,
                    resolve=resolve,
                    resolve_file=resolve_file,
                    stdin_text=stdin_text,
                )
                data.update(
                    {
                        "app_id": built.get("app_id"),
                        "name": built["name"],
                        "kind": built["kind"],
                        "omitted_defaults": built.get("omitted_defaults") or [],
                    }
                )
                from spa.next_steps import apps_add_next

                follow = apps_add_next(
                    kind=str(built.get("kind") or ""),
                    app_id=built.get("app_id"),
                    playbooks=built.get("playbooks") or [],
                    customize=bool(customize),
                    content_packs=content_packs,
                )
                if follow:
                    data["next"] = follow
                return _mutation_result("apps add", data)
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
            code = (
                2
                if "must be an integer" in message
                or message.startswith("spa apps search")
                or message.startswith("spa apps content-packs")
                else 1
            )
            return CommandResult(ok=False, error=message, code=code)
        except SplunkbaseError as exc:
            message = str(exc)
            code = 2 if message == "spa apps search QUERY" else 1
            return CommandResult(ok=False, error=message, code=code)
        except ConfigEditError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=False, error="Unknown spa apps action: %s" % action, code=2)

    def validate(
        self,
        config: Optional[str] = None,
        check_licenses: bool = False,
        splunk_config: Optional[str] = None,
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
            splunk_config=splunk_config,
            on_progress=self.on_progress,
            agent=agent,
        )

    def doctor(
        self,
        spa_home: Optional[str] = None,
        env_dir: Optional[str] = None,
        provider: Optional[Sequence[str]] = None,
        strict: bool = False,
    ) -> CommandResult:
        from spa.doctor import collect_checks
        from spa.registry import PROVIDER_ALIASES
        from spa.usage import unknown_doctor_provider

        requested: List[str] = []
        for raw in provider or ():
            key = (raw or "").strip().lower()
            if key not in PROVIDER_ALIASES:
                return CommandResult(
                    ok=False, error=unknown_doctor_provider(raw), code=2
                )
            requested.append(PROVIDER_ALIASES[key])
        return collect_checks(
            spa_home=spa_home,
            env_dir=env_dir,
            provider=requested,
            strict=strict,
        )

    def skills(
        self,
        action: str,
        platform: Optional[str] = None,
        name: Optional[str] = None,
        all_packages: bool = False,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        import os
        from pathlib import Path

        from spa.paths import user_spa_config_dir
        from spa.skills import SkillsError, install_skills, remove_skills

        if action == "remove":
            blocked = self._confirm_gate(
                "spa skills remove",
                confirm=confirm,
                agent=agent,
                risk="skills_remove",
            )
            if blocked:
                return blocked
        elif action != "install":
            return CommandResult(
                ok=False,
                error="spa skills needs an action.\nInstall:  spa skills install [PLATFORM]\nRemove:   spa skills remove [PLATFORM] --yes",
                code=2,
            )
        source = self.paths.spa_home / "skills" / "spa"
        home = Path(os.environ.get("HOME") or str(Path.home()))
        config_dir = user_spa_config_dir(os.environ)
        runner = remove_skills if action == "remove" else install_skills
        try:
            data = runner(
                source=source,
                home=home,
                platform=platform,
                name=name,
                all_packages=all_packages,
                environ=os.environ,
                config_dir=config_dir,
            )
        except SkillsError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        return CommandResult(ok=True, data=data)

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
        architecture: Optional[str] = None,
    ) -> CommandResult:
        from spa.init import InitError, init_env

        messages: List[str] = []
        report: Dict[str, Any] = {}
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
                architecture=architecture,
                report=report,
            )
        except InitError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code, data={"messages": messages})
        dest = str(Path(env_dir).resolve())
        data: Dict[str, Any] = {
            "env_dir": dest,
            "name": registry_name or Path(env_dir).name,
            "messages": messages,
        }
        if report:
            data["architecture"] = report
        return CommandResult(
            ok=rc == 0,
            code=rc,
            data=data,
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
                data["providers_yml"] = str(prov_path)
        except RegistryError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        return CommandResult(ok=True, data=data)

    def environment_cleanup(self, confirm: bool = False, agent: bool = False) -> CommandResult:
        """List registry entries with no directory; remove them only with confirm (--yes)."""
        from spa.registry import RegistryError, cleanup_missing_environments, missing_environments

        try:
            missing = missing_environments()
            if not missing:
                return CommandResult(ok=True, data={"removed": []})
            listing = ["missing: %s  %s" % (row["name"], row["path"]) for row in missing]
            gate = self._confirm_gate(
                "spa environment cleanup",
                confirm=confirm,
                agent=agent,
                details=listing,
                risk="registry_cleanup",
            )
            if gate is not None:
                return CommandResult(
                    ok=False,
                    error="Missing environments:\n%s\n%s" % ("\n".join(listing), gate.error),
                    code=gate.code,
                )
            removed = cleanup_missing_environments()
        except RegistryError as exc:
            return CommandResult(ok=False, error=str(exc), code=exc.code)
        return CommandResult(ok=True, data={"removed": removed})

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
        from spa.confirm import ConfirmationError, ConfirmationUsageError, ensure_confirmed

        try:
            ensure_confirmed(
                label, confirm=confirm, agent=agent, details=details, risk=risk
            )
        except ConfirmationUsageError as exc:
            return CommandResult(ok=False, error=str(exc), code=2)
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
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        blocked = self._env_lookup_gate()
        if blocked:
            return blocked
        blocked = self._schema_stamp_gate()
        if blocked:
            return blocked
        return self._lifecycle_playbook(
            "provision",
            extra,
            confirm,
            agent,
            ansible_output=ansible_output,
            native_output=native_output,
            verbosity=verbosity,
            timestamps=timestamps,
            color=color,
            label="hosts provision",
        )

    def destroy(
        self,
        extra: Optional[List[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
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
            verbosity=verbosity,
            timestamps=timestamps,
            color=color,
        )

    def _begin_lifecycle(self, command: str):
        from spa.runlog import LifecycleInProgress, claim_lifecycle_lock

        try:
            return None, claim_lifecycle_lock(self.paths, command)
        except LifecycleInProgress as exc:
            return CommandResult(ok=False, error=str(exc), code=1), None

    def _lifecycle_playbook(
        self,
        action: str,
        extra: Optional[List[str]],
        confirm: bool,
        agent: bool,
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
        label: Optional[str] = None,
        skip_confirm: bool = False,
    ) -> CommandResult:
        blocked, lifecycle_lock = self._begin_lifecycle(action)
        if blocked:
            return blocked
        try:
            return self._run_lifecycle_playbook(
                action,
                extra,
                confirm,
                agent,
                ansible_output=ansible_output,
                native_output=native_output,
                verbosity=verbosity,
                timestamps=timestamps,
                color=color,
                label=label,
                skip_confirm=skip_confirm,
            )
        finally:
            lifecycle_lock.close()

    def _run_lifecycle_playbook(
        self,
        action: str,
        extra: Optional[List[str]],
        confirm: bool,
        agent: bool,
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
        label: Optional[str] = None,
        skip_confirm: bool = False,
    ) -> CommandResult:
        from spa.confirm import LIFECYCLE_RISK

        blocked = self._venv_gate()
        if blocked:
            return blocked
        from spa.providers import ProviderError, get_provider

        try:
            provider = get_provider(self.paths)
        except ProviderError as exc:
            return CommandResult(ok=False, error=str(exc), code=getattr(exc, "code", 1) or 1)
        managed, external = self._classified_hosts()
        if action == "provision" and not getattr(provider, "creates_hosts", True):
            outcome = provider.provision(list(extra or []), agent=agent)
            data = {"provider": provider.name, "action": action}
            if isinstance(outcome, dict):
                data.update(outcome)
            return CommandResult(ok=True, data=data)
        if action == "provision" and external and not agent:
            import sys

            print(
                "SPA does not provision external hosts: %s" % ", ".join(external),
                file=sys.stderr,
            )
        from spa.providers import run_lifecycle_preflight

        try:
            run_lifecycle_preflight(provider, action)
        except ProviderError as exc:
            return CommandResult(
                ok=False, error=str(exc), code=getattr(exc, "code", 1) or 1
            )
        confirm_label = label or action
        if not skip_confirm:
            blocked = self._confirm_gate(
                confirm_label,
                confirm=confirm,
                agent=agent,
                risk=LIFECYCLE_RISK.get(confirm_label) or LIFECYCLE_RISK.get(action),
            )
            if blocked:
                return blocked
        args = ["-e", "auto_approve=true", *list(extra or [])]
        log = None
        rc = 1
        try:
            blocked = self._refuse_owned_external(provider, external)
            if blocked:
                return blocked
            snapshot = self._inventory_snapshot()
            if provider.name == "virtualbox" and external:
                args = [*args, *managed]
            playbook_fn = getattr(provider, "lifecycle_playbook", None)
            playbook = playbook_fn(action) if callable(playbook_fn) else action
            log = self._run_log(
                action,
                playbook,
                agent,
                ansible_output,
                native_output,
                verbosity,
                provider=provider.name,
                timestamps=timestamps,
                color=color,
            )
            outcome = getattr(provider, action)(
                args,
                run_log=log,
                agent=agent,
                ansible_output=ansible_output,
                native_output=native_output,
                verbosity=verbosity,
                timestamps=timestamps,
                color=color,
                command=action,
            )
            if isinstance(outcome, dict):
                log.finish(0)
                data = {"provider": provider.name, "action": action}
                data.update(outcome)
                data.update(log.envelope_fields())
                return CommandResult(ok=True, data=self._lifecycle_next(action, data))
            rc = outcome
            if provider.name in {"aws", "virtualbox"} and external and action == "provision":
                self._merge_external_lines(snapshot, external)
            if provider.name in {"aws", "virtualbox"} and action == "destroy":
                if rc == 0:
                    self._write_external_lines(snapshot, external)
                    if provider.name == "aws":
                        self._remove_terraform_tree()
                elif external:
                    self._merge_external_lines(snapshot, external)
        except ProviderError as exc:
            data = log.envelope_fields() if log is not None else None
            code = getattr(exc, "code", 1) or 1
            if log is not None:
                log.finish(code)
            return CommandResult(ok=False, error=str(exc), code=code, data=data)
        log.finish(rc)
        data = {"provider": provider.name, "action": action}
        if action == "provision" and external:
            data["skipped_external"] = list(external)
        data.update(log.envelope_fields())
        if rc == 0:
            data = self._lifecycle_next(action, data)
        return CommandResult(
            ok=rc == 0,
            code=rc,
            data=data,
            error=None if rc == 0 else "%s failed" % action,
        )

    def _provider_creates_hosts(self) -> bool:
        from spa.providers import get_provider

        try:
            provider = get_provider(self.paths)
        except Exception:
            return False
        return bool(getattr(provider, "creates_hosts", False))

    def _classified_hosts(self):
        from spa.providers import load_deployment_config
        from spa.providers.classify import classify_hostnames

        try:
            document = load_deployment_config(self.paths)
        except Exception:
            return [], []
        return classify_hostnames(document)

    def _refuse_owned_external(self, provider, external):
        if provider.name not in {"aws", "virtualbox"} or not external:
            return None
        if provider.name == "aws":
            from spa.providers.aws import terraform_instance_names

            owned = terraform_instance_names(provider.state_dir / "terraform.tfstate")
            label = "aws"
        else:
            from spa.providers.virtualbox import owned_machine_names

            try:
                states = provider._machine_states()
            except Exception:
                states = {}
            owned = owned_machine_names(states)
            label = "virtualbox"
        hit = [name for name in external if name in owned]
        if not hit:
            return None
        return CommandResult(
            ok=False,
            code=1,
            error=(
                "host %s is still managed by %s. SPA will not destroy it. "
                "Run spa destroy --yes before marking it external."
                % (hit[0], label)
            ),
        )

    def _inventory_snapshot(self) -> str:
        path = self.paths.inventory_dir / "hosts"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _external_line_list(snapshot: str, external) -> List[str]:
        names = set(external)
        kept = []
        for line in snapshot.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.split()[0] in names:
                kept.append(line)
        return kept

    def _write_external_lines(self, snapshot: str, external) -> None:
        if not external:
            return
        path = self.paths.inventory_dir / "hosts"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = self._external_line_list(snapshot, external)
        text = "\n".join(lines)
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")

    def _merge_external_lines(self, snapshot: str, external) -> None:
        path = self.paths.inventory_dir / "hosts"
        names = set(external)
        current = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        kept = []
        for line in current:
            stripped = line.strip()
            token = stripped.split()[0] if stripped and not stripped.startswith("#") else ""
            if token not in names:
                kept.append(line)
        lines = kept + self._external_line_list(snapshot, external)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(lines)
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")

    def _remove_terraform_tree(self) -> None:
        import shutil

        state = self.paths.terraform_state_dir.resolve()
        modules = self.paths.terraform_modules_dir.resolve()
        if state == modules:
            return
        if state.is_dir():
            shutil.rmtree(state)
        parent = state.parent
        framework = modules.parent
        if (
            parent.name == "terraform"
            and parent.is_dir()
            and parent != framework
            and not any(parent.iterdir())
        ):
            parent.rmdir()

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
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        blocked = self._env_lookup_gate()
        if blocked:
            return blocked
        blocked = self._schema_stamp_gate()
        if blocked:
            return blocked
        blocked, lifecycle_lock = self._begin_lifecycle("deploy")
        if blocked:
            return blocked
        try:
            return self._deploy_holding_lock(
                extra,
                verbose=verbose,
                hosts=hosts,
                confirm=confirm,
                agent=agent,
                ansible_output=ansible_output,
                native_output=native_output,
                verbosity=verbosity,
                timestamps=timestamps,
                color=color,
            )
        finally:
            lifecycle_lock.close()

    def _deploy_holding_lock(
        self,
        extra: Optional[List[str]] = None,
        verbose: bool = False,
        hosts: Optional[Sequence[str]] = None,
        confirm: bool = False,
        agent: bool = False,
        ansible_output: bool = False,
        native_output: bool = False,
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult:
        from spa.hosts import with_ansible_limit
        from spa.playbooks import PlaybookError, resolve, run_playbook
        from spa.preflight import (
            check_controller_data,
            controller_data_error,
            guest_mismatch_archive_reason,
            load_config_mapping,
            software_archive_error,
        )

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

        will_create, blocked = self._deploy_create_needed(hosts)
        if blocked:
            return blocked

        try:
            resolved = self._resolve_hosts(hosts)
        except HostLookupError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        details = list(self._confirm_details(resolved) or [])
        blocked = self._confirm_gate(
            "deploy",
            confirm=confirm,
            agent=agent,
            details=details or None,
            risk="mutating",
        )
        if blocked:
            return blocked
        if will_create:
            created = self._run_lifecycle_playbook(
                "provision",
                extra=None,
                confirm=True,
                agent=agent,
                ansible_output=ansible_output,
                native_output=native_output,
                verbosity=verbosity,
                timestamps=timestamps,
                color=color,
                skip_confirm=True,
            )
            if not created.ok:
                return created
        from spa.hosts import HostsError, ping_hosts

        log = self._run_log(
            "deploy",
            "deploy_site.yml",
            agent,
            ansible_output or verbose,
            native_output,
            verbosity,
            timestamps=timestamps,
            color=color,
        )
        try:
            checked = ping_hosts(self.paths, resolved)
        except HostsError as exc:
            if exc.rows:
                log.emit_host_check(exc.rows)
            else:
                log.emit(
                    {
                        "phase": "host_check",
                        "kind": "host_result",
                        "status": "failed",
                        "task": "SSH and passwordless sudo",
                        "msg": str(exc),
                    }
                )
            log.finish(1)
            data = log.envelope_fields()
            data["host_check_reported"] = True
            error = str(exc)
            if any(row.get("ssh") is False for row in exc.rows) and self._provider_creates_hosts():
                error = "%s\nIf the hosts are suspended, run: spa resume --yes" % error
            if any(
                row.get("expected_architecture") and not row.get("ok") for row in exc.rows
            ):
                guest_note = guest_mismatch_archive_reason(
                    Path(controller.software_dir or self.paths.software_dir),
                    load_config_mapping(Path(self.paths.config_file)),
                    exc.rows,
                )
                if guest_note:
                    error = "%s\n%s" % (error, guest_note)
            return CommandResult(ok=False, error=error, code=1, data=data)
        log.emit_host_check(checked.get("hosts") or [])
        confirmed = software_archive_error(
            Path(controller.software_dir or self.paths.software_dir),
            load_config_mapping(Path(self.paths.config_file)),
        )
        if confirmed:
            log.finish(1)
            data = log.envelope_fields()
            return CommandResult(ok=False, error=confirmed, code=1, data=data)
        args = with_ansible_limit(extra, resolved)
        try:
            playbook = resolve("deploy_site", self.paths)
        except PlaybookError as exc:
            log.finish(1)
            return CommandResult(
                ok=False, error=str(exc), code=1, data=log.envelope_fields()
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
            verbosity=verbosity,
            timestamps=timestamps,
            color=color,
            run_log=log,
        )
        log.finish(rc)
        data: Dict[str, Any] = {"playbook": "deploy_site"}
        data.update(log.envelope_fields())
        if resolved:
            data["hosts"] = resolved
        if rc == 0:
            data = self._lifecycle_next("deploy", data)
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
            return CommandResult(ok=False, error=str(exc), code=getattr(exc, "code", 1) or 1)
        managed, external = self._classified_hosts()
        selected = list(resolved) if resolved else [*managed, *external]
        external_selected = [name for name in selected if name in external]
        managed_selected = [name for name in selected if name not in set(external)]
        if external_selected and not managed_selected:
            return CommandResult(
                ok=False,
                code=1,
                error="SPA does not own power for external hosts: %s" % ", ".join(external_selected),
            )
        call_hosts = managed_selected if external else resolved
        log = self._run_log(action, action, agent, ansible_output, provider=provider.name)
        log.emit({"status": "ok", "phase": "power", "task": action})
        try:
            data = getattr(provider, action)(
                yes=True, agent=agent, wait=wait, hosts=call_hosts, run_log=log
            )
        except ProviderError as exc:
            code = getattr(exc, "code", 1) or 1
            log.finish(code)
            payload = log.envelope_fields()
            return CommandResult(ok=False, error=str(exc), code=code, data=payload)
        log.finish(0)
        payload = dict(data or {})
        payload["provider"] = provider.name
        payload["action"] = action
        payload.update(log.envelope_fields())
        if resolved:
            payload["hosts"] = list(managed_selected) if external else resolved
        if external_selected:
            payload["skipped_external"] = external_selected
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
        verbosity: int = 0,
        timestamps: bool = False,
        color: bool = False,
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
            "run",
            str(playbook),
            agent,
            ansible_output or verbose,
            native_output,
            verbosity,
            timestamps=timestamps,
            color=color,
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
            verbosity=verbosity,
            timestamps=timestamps,
            color=color,
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

        return aws_mod.execute_argv(
            list(argv or []),
            environment_region=aws_mod.environment_config_region(self.paths.config_file),
        )

    def provider(
        self,
        child: str = "",
        action: Optional[str] = None,
        resource: Optional[str] = None,
        subaction: Optional[str] = None,
        hours: Optional[str] = None,
        days: Optional[int] = None,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        from spa import aws as aws_mod
        from spa.providers import ccm as ccm_mod
        from spa.usage import provider_needs_action

        if child not in {"aws", "ccm"}:
            return CommandResult(ok=False, error=provider_needs_action(), code=2)
        if child == "aws":
            tokens = [part for part in (action, resource, subaction) if part]
            if action and resource == action:
                tokens = [action] + ([subaction] if subaction else [])
            if not tokens:
                return CommandResult(ok=False, error=aws_mod.AWS_NEEDS_ACTION, code=2)
            return aws_mod.execute_argv(
                tokens,
                environment_region=aws_mod.environment_config_region(self.paths.config_file),
            )
        config: Dict[str, Any] = {}
        loaded = self._app_deployment_config()
        if isinstance(loaded, dict) and isinstance(loaded.get("ccm"), dict):
            config = loaded["ccm"]
        return ccm_mod.execute(
            action=action or "",
            resource=resource,
            subaction=subaction,
            hours=hours,
            days=days,
            confirm=confirm,
            agent=agent,
            paths=self.paths,
            config=config,
        )

    def licenses(
        self,
        software_dir: Optional[str] = None,
        config: Optional[str] = None,
        env_recommend: bool = True,
    ) -> CommandResult:
        from spa import licenses as licenses_mod
        from spa.next_steps import licenses_list_next

        project_root = Path(self.paths.spa_env_dir)
        config_path = None
        if config:
            config_path = Path(config).expanduser()
            if not config_path.is_absolute():
                config_path = (Path.cwd() / config_path).resolve()
                if not config_path.is_file():
                    config_path = (licenses_mod.repo_root_from_script() / config).resolve()
        elif self.paths.config_file and Path(self.paths.config_file).is_file():
            config_path = Path(self.paths.config_file)
        try:
            data = licenses_mod.scan_licenses(
                project_root,
                software_dir=software_dir or str(self.paths.software_dir),
                config_path=config_path,
                env_recommend=env_recommend,
            )
        except Exception as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        follow = licenses_list_next(data if isinstance(data, dict) else {})
        if follow:
            data["next"] = follow
        return CommandResult(ok=True, data=data)

    def architecture_plan(self, path: str) -> CommandResult:
        """Read a splunk.architecture file and plan the overlay. Read-only."""
        import os

        from spa import architecture as arch

        try:
            doc = arch.load_architecture_file(Path(path))
        except arch.ArchitectureError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        plan = arch.plan_architecture(doc, env=os.environ, spa_home=self.paths.spa_home)
        if not plan["ok"]:
            return CommandResult(
                ok=False,
                error="architecture file is not valid: " + "; ".join(plan["errors"]),
                code=1,
            )
        return CommandResult(ok=True, data=plan)

    def architecture_apply(
        self,
        path: str,
        confirm: bool = False,
        agent: bool = False,
        dry_run: bool = False,
        expect_revision: Optional[str] = None,
    ) -> CommandResult:
        from spa import architecture as arch
        from spa.config_edit import ConfigEditError

        blocked = self._env_gate()
        if blocked:
            return blocked
        try:
            doc = arch.load_architecture_file(Path(path))
            parsed, errors, warnings = arch.parse_architecture(doc)
        except arch.ArchitectureError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        if errors:
            return CommandResult(
                ok=False,
                error="architecture file is not valid: " + "; ".join(errors),
                code=1,
            )
        if not parsed.get("confirmed"):
            return CommandResult(ok=False, error="architecture file is not confirmed", code=1)
        if not dry_run:
            blocked = self._confirm_gate(
                "spa architecture apply",
                confirm=confirm,
                agent=agent,
                details=["config: %s" % self.paths.config_file],
                risk="config_edit",
            )
            if blocked:
                return blocked
        try:
            data = arch.apply_architecture_document(
                Path(self.paths.config_file),
                Path(self.paths.spa_home),
                parsed,
                dry_run=dry_run,
                expect_revision=expect_revision,
            )
        except (arch.ArchitectureError, ConfigEditError) as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        data.setdefault("warnings", [])
        data["warnings"] = list(data.get("warnings") or []) + warnings
        from spa.next_steps import remaining_next

        follow = remaining_next(data.get("remaining") or [])
        if follow:
            data["next"] = follow
        return _mutation_result("architecture apply", data)

    def architecture_check(self, path: str) -> CommandResult:
        from spa import architecture as arch

        blocked = self._env_gate()
        if blocked:
            return blocked
        try:
            doc = arch.load_architecture_file(Path(path))
            parsed, errors, warnings = arch.parse_architecture(doc)
        except arch.ArchitectureError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        if errors:
            return CommandResult(
                ok=False,
                error="architecture file is not valid: " + "; ".join(errors),
                code=1,
            )
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            return CommandResult(ok=False, error="PyYAML is required: %s" % exc, code=1)
        config_path = Path(self.paths.config_file)
        if not config_path.is_file():
            return CommandResult(ok=False, error="Config file not found: %s" % config_path, code=1)
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(config, dict):
            return CommandResult(ok=False, error="splunk_config.yml must contain a mapping", code=1)
        result = arch.check_architecture(config, parsed, spa_home=self.paths.spa_home)
        result["warnings"] = warnings
        if not result.get("ok"):
            return CommandResult(
                ok=False,
                error="architecture check found mismatches",
                data=result,
                code=1,
            )
        return CommandResult(ok=True, data=result)

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

    def hosts_register(
        self,
        name: str,
        ssh_host: str,
        user: str,
        key: str,
        ssh_port: int = 22,
        roles: Optional[Sequence[str]] = None,
        ip_addr: Optional[str] = None,
        confirm: bool = False,
        agent: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        blocked = self._confirm_gate("register", confirm=confirm, agent=agent, risk="mutating")
        if blocked:
            return blocked
        from spa.providers import ProviderError
        from spa.providers.external import RegisterSpec, register_host

        spec = RegisterSpec(name, ssh_host, user, key, ssh_port, tuple(roles or ()), ip_addr)
        try:
            data = register_host(self.paths, spec, _subprocess_runner)
        except ProviderError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=data)

    def hosts_unregister(
        self, name: str, confirm: bool = False, agent: bool = False
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        blocked = self._confirm_gate("unregister", confirm=confirm, agent=agent, risk="mutating")
        if blocked:
            return blocked
        from spa.providers import ProviderError
        from spa.providers.external import unregister_host

        try:
            data = unregister_host(self.paths, name)
        except ProviderError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=data)

    def hosts_check(self, hosts: Optional[Sequence[str]] = None) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.hosts import HostsError, ping_hosts

        try:
            resolved = self._resolve_hosts(hosts)
        except HostLookupError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        try:
            data = ping_hosts(self.paths, resolved)
        except HostsError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        return CommandResult(ok=True, data=data)

    def logs(
        self,
        run_id: Optional[str] = None,
        last: bool = False,
        follow: bool = False,
        wait: bool = False,
        ansible_output: bool = False,
        timestamps: bool = False,
        color: bool = False,
    ) -> CommandResult:
        blocked = self._env_gate()
        if blocked:
            return blocked
        from spa.runlog import (
            follow_jsonl,
            list_runs,
            load_run,
            now_local,
            read_jsonl,
            replay_jsonl,
            wait_for_new_run,
        )

        rows = list_runs(self.paths)
        if not last and not follow and not run_id:
            return CommandResult(ok=True, data={"runs": rows})
        target = None
        if run_id:
            target = load_run(self.paths, run_id)
            if target is None:
                return CommandResult(ok=False, error="Unknown run: %s" % run_id, code=1)
        elif follow and wait:
            try:
                target = wait_for_new_run(self.paths, now_local())
            except KeyboardInterrupt:
                return CommandResult(ok=False, code=130)
        elif rows:
            target = rows[0]
        if target is None:
            return CommandResult(ok=False, error="No runs in %s/logs" % self.paths.spa_env_dir, code=1)
        from pathlib import Path

        log_path = Path(str(target.get("log") or ""))
        if follow:
            interrupted = follow_jsonl(
                log_path,
                idle_passes=-1,
                ansible_output=ansible_output,
                timestamps=timestamps,
                color=color,
            )
            if interrupted:
                return CommandResult(ok=False, code=interrupted, data=target)
            return CommandResult(ok=True, data=target)
        target = dict(target)
        if ansible_output:
            target["replay"] = replay_jsonl(log_path, timestamps=timestamps, color=color)
        else:
            target["transcript"] = read_jsonl(log_path)
        return CommandResult(ok=True, data=target)

    def shell_list(
        self, verbose: bool = False, hosts: Optional[Sequence[str]] = None
    ) -> CommandResult:
        return self.hosts_list(status=verbose, hosts=hosts)

    def completion_script(self, shell: str) -> CommandResult:
        from spa.completion import COMPLETION_NEEDS_SHELL, completion_script

        if shell not in {"bash", "zsh"}:
            return CommandResult(ok=False, error=COMPLETION_NEEDS_SHELL, code=2)
        return CommandResult(ok=True, data={"shell": shell, "script": completion_script(shell)})

    def complete(self, words: Sequence[str], index: int) -> CommandResult:
        from spa.completion import complete
        from spa.preflight import load_config_mapping

        paths = self._paths_for_completion(words, index)
        config = None
        try:
            if paths.config_file.is_file():
                loaded = load_config_mapping(paths.config_file)
                config = loaded or None
        except Exception:
            config = None
        try:
            candidates = complete(list(words), index, config=config, paths=paths)
        except Exception:
            candidates = []
        return CommandResult(ok=True, data={"candidates": candidates})

    def _paths_for_completion(self, words: Sequence[str], index: int):
        """Honor --env and --start-dir typed on the line being completed."""
        from spa.paths import resolve_spa_paths

        tokens = [str(item) for item in words]
        limit = min(max(index, 0), len(tokens))
        cursor = 1 if tokens and (tokens[0] == "spa" or tokens[0].endswith("/spa")) else 0
        env_name = None
        start_dir = None
        while cursor < limit:
            token = tokens[cursor]
            if token in {"--env", "--start-dir"} and cursor + 1 < limit:
                value = tokens[cursor + 1]
                if token == "--env":
                    env_name = value
                else:
                    start_dir = value
                cursor += 2
                continue
            if token.startswith("-"):
                cursor += 1
                continue
            cursor += 1
        if env_name is None and start_dir is None:
            return self.paths
        try:
            import os

            start = Path(start_dir).expanduser().resolve() if start_dir else None
            environ = os.environ.copy()
            # The session already exported the default env's config path.
            environ.pop("SPLUNK_CONFIG_FILE", None)
            return resolve_spa_paths(start_dir=start, env_selector=env_name, environ=environ)
        except Exception:
            return self.paths


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
