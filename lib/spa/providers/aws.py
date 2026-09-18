"""AWS Terraform provider lifecycle implementation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from spa.executil import tool_path
from spa.paths import SpaPaths
from spa.playbooks import resolve, run_playbook
from spa.providers import (
    ProviderError,
    ProvisionState,
    expected_hostnames,
    inventory_hostnames_from_file,
    load_deployment_config,
)


class Provider:
    name = "aws"

    def __init__(self, paths: SpaPaths, config: Dict[str, Any]):
        self.paths = paths
        self.config = config
        self.state_dir = paths.spa_env_dir / "terraform" / "aws"

    def provision(self, extra: List[str], **kwargs: Any) -> int:
        run_log = kwargs.get("run_log")
        rc = run_playbook(
            resolve("aws_provision", self.paths),
            self.paths,
            extra,
            command=str(kwargs.get("command") or "provision"),
            agent=bool(kwargs.get("agent")),
            ansible_output=bool(kwargs.get("ansible_output")),
            native_output=bool(kwargs.get("native_output")),
            run_log=run_log,
        )
        if run_log is not None:
            run_log.attach_tf_plan()
        return rc

    def provision_state(self) -> ProvisionState:
        """Offline: Terraform state plus every config hostname in inventory/hosts."""
        expected = expected_hostnames(load_deployment_config(self.paths))
        inventory = set(inventory_hostnames_from_file(self.paths))
        missing = tuple(sorted(set(expected) - inventory))
        hint_provision = "spa provision --yes"
        hint_resume = "spa provision --yes (spa resume --yes if instances are stopped)"
        state_path = self.state_dir / "terraform.tfstate"
        if not state_path.is_file():
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="No Terraform state for this AWS env: %s" % self.state_dir,
                hint=hint_provision,
                missing=tuple(sorted(expected)),
            )
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="Cannot read Terraform state: %s" % state_path,
                hint=hint_provision,
                missing=tuple(sorted(expected)),
            )
        resources = payload.get("resources") if isinstance(payload, dict) else None
        if not isinstance(resources, list) or not resources:
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="Terraform state has no resources: %s" % state_path,
                hint=hint_provision,
                missing=tuple(sorted(expected)),
            )
        if missing:
            shown = list(missing)
            extra = ""
            cap = 12
            if len(shown) > cap:
                extra = ", +%d more" % (len(shown) - cap)
                shown = shown[:cap]
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="hosts not in inventory: %s%s" % (", ".join(shown), extra),
                hint=hint_resume,
                missing=missing,
            )
        return ProvisionState(provider=self.name, provisioned=True)

    def destroy(self, extra: List[str], **kwargs: Any) -> int:
        return run_playbook(
            resolve("aws_destroy", self.paths),
            self.paths,
            extra,
            command=str(kwargs.get("command") or "destroy"),
            agent=bool(kwargs.get("agent")),
            ansible_output=bool(kwargs.get("ansible_output")),
            native_output=bool(kwargs.get("native_output")),
            run_log=kwargs.get("run_log"),
        )

    def _terraform_output(self, name: str) -> Any:
        if not (self.state_dir / "terraform.tfstate").is_file():
            raise ProviderError(
                "No Terraform state for this AWS env: %s. Run spa provision first."
                % self.state_dir
            )
        terraform = tool_path(self.paths, "terraform")
        result = subprocess.run(
            [terraform, "-chdir=%s" % self.state_dir, "output", "-json", name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Terraform diagnostics can contain rendered variable context. Do
            # not echo them because configs may contain credential values.
            raise ProviderError(
                "Cannot read Terraform output %s from %s (terraform exited %s)."
                % (name, self.state_dir, result.returncode)
            )
        try:
            value = json.loads(result.stdout)
            # ansible_inventory is a Terraform string containing JSON.
            if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
                value = json.loads(value)
            return value
        except json.JSONDecodeError as exc:
            raise ProviderError("Invalid Terraform JSON output %s: %s" % (name, exc))

    def _targets(self) -> Dict[str, Dict[str, Any]]:
        states = self._terraform_output("instance_states")
        if not isinstance(states, dict) or not states:
            raise ProviderError("Terraform state contains no AWS instances.")
        missing = [name for name, value in states.items() if not (value or {}).get("id")]
        if missing:
            raise ProviderError(
                "Terraform output has no instance ID for: %s" % ", ".join(sorted(missing))
            )
        return states

    def _resolved_config(self) -> Dict[str, Any]:
        """Resolve env/vault credential references without printing their values."""
        plugin_dir = self.paths.spa_home / "ansible" / "plugins" / "inventory"
        sys.path.insert(0, str(plugin_dir))
        try:
            from secret_resolver import load_config_with_secrets

            full = load_config_with_secrets(str(self.paths.config_file), resolve_secrets=True)
            return ((full or {}).get("terraform") or {}).get("aws") or {}
        except ImportError:
            return self.config
        except Exception:
            raise ProviderError(
                "Could not resolve AWS settings from splunk_config.yml. "
                "Check environment/vault references; credential values were not displayed."
            )
        finally:
            try:
                sys.path.remove(str(plugin_dir))
            except ValueError:
                pass

    def _session(self):
        try:
            import boto3
        except ImportError:
            raise ProviderError(
                "AWS lifecycle commands require boto3. Recreate the venv "
                "(spa venv --shared --rebuild --yes) so requirements.txt is installed."
            )
        config = self._resolved_config()
        kwargs: Dict[str, Any] = {"region_name": config.get("region")}
        profile = config.get("profile") or config.get("profile_name")
        if profile:
            kwargs["profile_name"] = profile
        # Preserve the existing config credential option, but never include these
        # values in errors, output, logs, or inventory.
        if config.get("access_key_id") and config.get("secret_access_key"):
            kwargs["aws_access_key_id"] = config["access_key_id"]
            kwargs["aws_secret_access_key"] = config["secret_access_key"]
            if config.get("session_token"):
                kwargs["aws_session_token"] = config["session_token"]
        try:
            return boto3.Session(**kwargs)
        except Exception as exc:
            raise ProviderError("AWS session setup failed: %s" % exc)

    def _ec2(self):
        region = self.config.get("region")
        if not region:
            raise ProviderError("terraform.aws.region is required for AWS lifecycle commands.")
        try:
            return self._session().client("ec2", region_name=region)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("AWS EC2 client setup failed: %s" % exc)

    @staticmethod
    def _describe(ec2, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        try:
            response = ec2.describe_instances(InstanceIds=ids)
        except Exception as exc:
            raise ProviderError("AWS describe-instances failed: %s" % exc)
        found = {}
        for reservation in response.get("Reservations") or []:
            for instance in reservation.get("Instances") or []:
                found[instance["InstanceId"]] = instance
        missing = sorted(set(ids) - set(found))
        if missing:
            raise ProviderError("AWS did not return instance(s): %s" % ", ".join(missing))
        return found

    @staticmethod
    def _confirm(action: str, targets: Dict[str, Dict[str, Any]], yes: bool, agent: bool) -> None:
        if yes:
            return
        if agent:
            raise ProviderError("%s requires -y/--yes in agent mode." % action)
        from spa.hosts import format_host_groups, load_inventory

        names = sorted(targets)
        print(
            "%s %d AWS instance%s:"
            % (action.capitalize(), len(names), "" if len(names) == 1 else "s"),
            file=sys.stderr,
        )
        for line in format_host_groups(load_inventory(), names):
            print(line, file=sys.stderr)
        answer = input("Proceed? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            raise ProviderError("%s cancelled." % action.capitalize())

    @staticmethod
    def _instance_rows(
        targets: Dict[str, Dict[str, Any]], described: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        rows = []
        for name, target in sorted(targets.items()):
            instance = described[target["id"]]
            rows.append(
                {
                    "name": name,
                    "instance_id": target["id"],
                    "state": (instance.get("State") or {}).get("Name"),
                    "public_dns_name": instance.get("PublicDnsName") or None,
                    "public_ip": instance.get("PublicIpAddress") or None,
                    "private_dns_name": instance.get("PrivateDnsName") or None,
                    "private_ip": instance.get("PrivateIpAddress") or None,
                }
            )
        return rows

    def host_status(self) -> Dict[str, Dict[str, Any]]:
        """Return runtime state keyed by every useful inventory identifier."""
        targets = self._targets()
        described = self._describe(
            self._ec2(), [target["id"] for target in targets.values()]
        )
        status: Dict[str, Dict[str, Any]] = {}
        for row in self._instance_rows(targets, described):
            record = {
                "state": row["state"],
                "reachable": row["state"] == "running",
                "instance_id": row["instance_id"],
            }
            identifiers = (
                row["name"],
                row["instance_id"],
                row["public_dns_name"],
                row["public_ip"],
                row["private_dns_name"],
                row["private_ip"],
            )
            for identifier in identifiers:
                if identifier:
                    status[str(identifier)] = record
        return status

    def suspend(self, yes: bool, agent: bool, wait: bool = True, hosts: Optional[List[str]] = None) -> Dict[str, Any]:
        targets = self._select_targets(hosts)
        self._confirm("suspend", targets, yes, agent)
        ids = [target["id"] for target in targets.values()]
        ec2 = self._ec2()
        before = self._describe(ec2, ids)
        terminal = [
            instance_id
            for instance_id, instance in before.items()
            if (instance.get("State") or {}).get("Name") in {"shutting-down", "terminated"}
        ]
        if terminal:
            raise ProviderError(
                "Terraform-managed AWS instance(s) are terminating/terminated: %s. "
                "Run spa provision to reconcile the environment." % ", ".join(terminal)
            )
        stoppable = [
            instance_id
            for instance_id, instance in before.items()
            if (instance.get("State") or {}).get("Name") in {"pending", "running"}
        ]
        try:
            if stoppable:
                ec2.stop_instances(InstanceIds=stoppable)
            if wait:
                stopping = [
                    instance_id
                    for instance_id, instance in before.items()
                    if (instance.get("State") or {}).get("Name") != "stopped"
                ]
                if stopping:
                    ec2.get_waiter("instance_stopped").wait(InstanceIds=stopping)
            after = self._describe(ec2, ids)
        except Exception as exc:
            raise ProviderError("AWS stop-instances failed: %s" % exc)
        return {
            "provider": self.name,
            "action": "suspend",
            "waited": wait,
            "instances": self._instance_rows(targets, after),
            "note": "EBS volumes and other retained resources continue to incur charges.",
        }

    def _write_inventory(
        self,
        targets: Dict[str, Dict[str, Any]],
        described: Dict[str, Dict[str, Any]],
        merge: bool = False,
    ) -> Path:
        inventory_meta = self._terraform_output("ansible_inventory")
        if not isinstance(inventory_meta, dict):
            raise ProviderError("Terraform ansible_inventory output is not a mapping.")
        lines = [
            "# Ansible Inventory - Refreshed by spa resume",
            "# DO NOT EDIT - addresses may change after an AWS stop/start",
            "",
        ]
        self.paths.inventory_dir.mkdir(parents=True, exist_ok=True)
        destination = self.paths.inventory_dir / "hosts"
        entries = self._merge_inventory_entries(destination) if merge else {}
        for name, target in sorted(targets.items()):
            instance = described[target["id"]]
            meta = inventory_meta.get(name) or {}
            public_dns = instance.get("PublicDnsName") or instance.get("PublicIpAddress")
            if not public_dns:
                raise ProviderError("AWS instance %s has no public DNS name or IP." % name)
            values = {
                "ansible_host": public_dns,
                "ansible_user": meta.get("ansible_user") or self.config.get("ssh_username"),
                "ansible_ssh_private_key_file": meta.get("ansible_ssh_private_key_file")
                or self.config.get("ssh_private_key_file"),
                "ip_addr": instance.get("PrivateIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "public_dns_name": instance.get("PublicDnsName"),
                "private_dns_name": instance.get("PrivateDnsName"),
            }
            rendered = [
                "%s=%s" % (key, json.dumps(str(value)))
                for key, value in values.items()
                if value
            ]
            entries[name] = " ".join(rendered)
        names = sorted(entries) if merge else sorted(targets)
        for name in names:
            lines.append("%s %s" % (name, entries[name]))
        temporary = destination.with_suffix(".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(destination)
        return destination

    def _select_targets(self, hosts: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        targets = self._targets()
        if not hosts:
            return targets
        missing = [name for name in hosts if name not in targets]
        if missing:
            raise ProviderError(
                "No Terraform-managed instance for: %s. Known: %s"
                % (", ".join(missing), ", ".join(sorted(targets)))
            )
        return {name: targets[name] for name in hosts}

    def _merge_inventory_entries(self, path: Path) -> Dict[str, str]:
        entries: Dict[str, str] = {}
        if not path.is_file():
            return entries
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            name, _, rest = stripped.partition(" ")
            entries[name] = rest.strip()
        return entries

    def resume(self, yes: bool, agent: bool, wait: bool = True, hosts: Optional[List[str]] = None) -> Dict[str, Any]:
        targets = self._select_targets(hosts)
        self._confirm("resume", targets, yes, agent)
        ids = [target["id"] for target in targets.values()]
        ec2 = self._ec2()
        before = self._describe(ec2, ids)
        terminal = [
            instance_id
            for instance_id, instance in before.items()
            if (instance.get("State") or {}).get("Name") in {"shutting-down", "terminated"}
        ]
        if terminal:
            raise ProviderError(
                "Terraform-managed AWS instance(s) are terminating/terminated: %s. "
                "Run spa provision to reconcile the environment." % ", ".join(terminal)
            )
        stopping = [
            instance_id
            for instance_id, instance in before.items()
            if (instance.get("State") or {}).get("Name") == "stopping"
        ]
        if stopping:
            try:
                ec2.get_waiter("instance_stopped").wait(InstanceIds=stopping)
            except Exception as exc:
                raise ProviderError("AWS wait for stopping instances failed: %s" % exc)
        startable = [
            instance_id
            for instance_id, instance in before.items()
            if (instance.get("State") or {}).get("Name") in {"stopped", "stopping"}
        ]
        try:
            if startable:
                ec2.start_instances(InstanceIds=startable)
            if wait:
                ec2.get_waiter("instance_running").wait(InstanceIds=ids)
                ec2.get_waiter("instance_status_ok").wait(InstanceIds=ids)
            after = self._describe(ec2, ids)
        except Exception as exc:
            raise ProviderError("AWS start-instances failed: %s" % exc)
        inventory = self._write_inventory(targets, after, merge=bool(hosts))
        return {
            "provider": self.name,
            "action": "resume",
            "waited": wait,
            "inventory": str(inventory),
            "instances": self._instance_rows(targets, after),
        }
