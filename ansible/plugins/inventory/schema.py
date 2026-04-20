"""
Pydantic schema models for Splunk Platform Automator configuration validation.

This module provides comprehensive validation for splunk_config.yml files,
ensuring configurations are valid before Ansible inventory processing begins.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


# =============================================================================
# Enums for allowed values
# =============================================================================

class AllowedRole(str, Enum):
    """Allowed Splunk roles for hosts."""
    cluster_manager = "cluster_manager"
    deployer = "deployer"
    deployment_server = "deployment_server"
    heavy_forwarder = "heavy_forwarder"
    indexer = "indexer"
    license_manager = "license_manager"
    monitoring_console = "monitoring_console"
    search_head = "search_head"
    universal_forwarder = "universal_forwarder"
    universal_forwarder_windows = "universal_forwarder_windows"


# Roles that are allowed to have a 'site' variable
ROLES_WITH_SITE = {AllowedRole.indexer, AllowedRole.search_head, AllowedRole.cluster_manager}


# =============================================================================
# Sub-models for nested configuration sections
# =============================================================================

class GeneralConfig(BaseModel):
    """General settings section."""
    model_config = ConfigDict(extra='forbid')
    
    url_locale: Optional[str] = Field(
        None, 
        pattern=r'^[a-z]{2}[_-][A-Z]{2}$',
        description="Language locale for links (e.g., 'en-GB')"
    )


class VirtualBoxSyncedFolder(BaseModel):
    """VirtualBox synced folder configuration."""
    source: str
    target: str


class VirtualBoxConfig(BaseModel):
    """VirtualBox virtualization settings."""
    model_config = ConfigDict(extra='allow')
    
    start_ip: Optional[str] = Field(None, description="Starting IP address (192.68.56.0/21 range)")
    box: Optional[str] = Field(None, description="Vagrant box name")
    memory: Optional[int] = Field(None, ge=256, description="Memory in MB (min 256)")
    cpus: Optional[int] = Field(None, ge=1, description="Number of CPUs (min 1)")
    install_vbox_additions: Optional[bool] = Field(None, description="Install VBox guest additions")
    synced_folder: Optional[List[VirtualBoxSyncedFolder]] = None


class AwsTerraformConfig(BaseModel):
    """AWS configuration for Terraform provisioning."""
    model_config = ConfigDict(extra='allow')
    
    region: Optional[str] = Field(None, description="AWS region")
    ami_id: Optional[str] = Field(None, description="AMI ID")
    key_name: Optional[str] = Field(None, description="SSH key name")
    ssh_private_key_file: Optional[str] = Field(None, description="Path to SSH private key")
    security_group_names: Optional[List[str]] = Field(None, description="Security group names")
    instance_type: Optional[str] = Field(None, description="EC2 instance type")
    root_volume_size: Optional[int] = Field(None, ge=8, description="Root volume size in GB")
    tags: Optional[Dict[str, str]] = Field(None, description="AWS resource tags")
    subnet_id: Optional[str] = Field(None, description="AWS VPC subnet ID")


class TerraformConfig(BaseModel):
    """Terraform provisioning settings."""
    model_config = ConfigDict(extra='allow')
    
    aws: Optional[AwsTerraformConfig] = None


class OsConfig(BaseModel):
    """Operating system configuration."""
    model_config = ConfigDict(extra='allow')
    
    remote_command: Optional[str] = None
    time_zone: Optional[str] = None
    enable_time_sync_cron: Optional[bool] = None
    packages: Optional[List[str]] = None
    set_hostname: Optional[bool] = None
    disable_selinux: Optional[bool] = None
    disable_apparmor: Optional[bool] = None
    update_hosts_file: Optional[bool] = None
    splunk_group_create: Optional[bool] = None
    splunk_user_create: Optional[bool] = None


class SplunkDownloadConfig(BaseModel):
    """Splunk download settings."""
    splunk: Optional[bool] = None
    splunkforwarder: Optional[bool] = None


class SplunkSslEndpointConfig(BaseModel):
    """SSL endpoint configuration."""
    model_config = ConfigDict(extra='allow')
    
    enable: Optional[bool] = None
    own_certs: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class SplunkSslConfig(BaseModel):
    """Splunk SSL settings."""
    web: Optional[SplunkSslEndpointConfig] = None
    inputs: Optional[SplunkSslEndpointConfig] = None
    outputs: Optional[SplunkSslEndpointConfig] = None


class SplunkSecretShareConfig(BaseModel):
    """Splunk secret sharing configuration."""
    splunk: Optional[bool] = None
    splunkforwarder: Optional[bool] = None
    equal: Optional[bool] = None


class SplunkVolumeConfig(BaseModel):
    """Splunk indexer volume configuration."""
    model_config = ConfigDict(extra='allow')
    
    path: Optional[str] = None
    maxVolumeDataSizeMB: Optional[int] = None


class SplunkVolumeDefaultsConfig(BaseModel):
    """Splunk volume defaults configuration."""
    model_config = ConfigDict(extra='allow')
    
    VolumeDataSize_Free_MB: Optional[int] = None
    homePath: Optional[str] = None
    coldPath: Optional[str] = None


class SplunkDefaultsConfig(BaseModel):
    """Splunk default settings applied to all hosts."""
    model_config = ConfigDict(extra='allow')
    
    splunk_env_name: Optional[str] = None
    splunk_version: Optional[str] = None
    splunk_architecture: Optional[str] = Field(None, pattern=r'^(amd64|x86_64|arm64)$')
    splunk_fips: Optional[bool] = None
    splunk_download: Optional[SplunkDownloadConfig] = None
    splunk_admin_password: Optional[str] = None
    splunk_license_file: Optional[Union[str, List[str]]] = None
    splunk_license_server: Optional[str] = None
    splunk_set_servername: Optional[bool] = None
    splunk_set_default_hostname: Optional[bool] = None
    splunk_loginpage_print_hostname: Optional[bool] = None
    splunk_loginpage_print_userpw: Optional[bool] = None
    splunk_loginpage_print_roles: Optional[bool] = None
    splunk_use_policykit: Optional[bool] = None
    splunk_kv_store_engine_wiredtiger: Optional[bool] = None
    splunk_conf: Optional[Dict[str, Dict[str, Any]]] = None
    splunk_indexes: Optional[Dict[str, Any]] = None
    splunk_indexes_default_paths: Optional[bool] = None
    splunk_indexer_volumes: Optional[Dict[str, SplunkVolumeConfig]] = None
    splunk_volume_defaults: Optional[SplunkVolumeDefaultsConfig] = None
    splunk_ssl: Optional[SplunkSslConfig] = None
    splunk_secret_share: Optional[SplunkSecretShareConfig] = None


class SplunkDirsConfig(BaseModel):
    """Splunk directory paths."""
    model_config = ConfigDict(extra='allow')
    
    splunk_baseconfig_dir: Optional[str] = None
    splunk_software_dir: Optional[str] = None


class SplunkAppsConfig(BaseModel):
    """Splunk apps configuration (legacy baseconfig apps)."""
    model_config = ConfigDict(extra='allow')
    
    splunk_save_baseconfig_apps_dir: Optional[str] = None
    splunk_save_baseconfig_apps: Optional[bool] = None
    splunk_save_serverclass: Optional[bool] = None


ALLOWED_APP_SOURCES = ("local", "splunkbase")
ALLOWED_DEPLOYMENT_TARGETS = ("direct", "auto")
ALLOWED_APP_STATES = ("installed", "absent")
ALLOWED_PREMIUM_APPS = ("itsi",)  # Premium apps: target_roles not required; deployment is role-based
# Version: "latest" or dotted numeric (e.g. 1.0, 4.21.1, 10.1.0)
VERSION_NUMBER_PATTERN = re.compile(r"^\d+(\.\d+)*$")


class SplunkAppDeploymentConfig(BaseModel):
    """Splunk app deployment configuration (Splunkbase and local apps)."""
    model_config = ConfigDict(extra='allow')
    
    splunkbase_username: Optional[str] = None
    splunkbase_password: Optional[str] = None
    local_app_repo_path: Optional[str] = None
    deploymentclient_check: bool = Field(
        default=True,
        description=(
            "When true (default), app deployment runs splunk btool deploymentclient on hosts (with a deployment server "
            "in inventory) to set _splunk_is_deployment_client and to filter deployment-server serverclass whitelists. "
            "When false, skip btool and assume non–deployment-server, non–SHC/IDXC-member hosts are deployment clients."
        ),
    )
    apps: Optional[List[Dict[str, Any]]] = None
    host_specific_apps: Optional[List[Dict[str, Any]]] = None

    @model_validator(mode='after')
    def validate_app_deployment_apps(self) -> 'SplunkAppDeploymentConfig':
        """Validate each app entry: required name, allowed source/deployment_target/target_roles.

        The same app name may appear multiple times with different target_roles and customizations
        (e.g. one entry for indexer cluster, one for universal_forwarder). deployment_target is
        calculated from roles and inventory at deploy time, not used as a uniqueness key here.
        """
        if not self.apps:
            return self
        allowed_roles = {r.value for r in AllowedRole}
        for i, app in enumerate(self.apps):
            if not isinstance(app, dict):
                raise ValueError(f"splunk_app_deployment.apps[{i}] must be a dictionary")
            name = app.get("name")
            if name is None:
                raise ValueError(f"splunk_app_deployment.apps[{i}] must have a 'name' field")
            if not isinstance(name, str):
                raise ValueError(f"splunk_app_deployment.apps[{i}].name must be a string")
            source = app.get("source")
            if source is not None and source not in ALLOWED_APP_SOURCES:
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): 'source' must be one of {ALLOWED_APP_SOURCES}, got {source!r}"
                )
            if source == "splunkbase":
                app_id = app.get("app_id")
                if app_id is None:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'app_id' is required when source is 'splunkbase'"
                    )
                is_int = isinstance(app_id, int) and type(app_id) is not bool
                is_numeric_str = isinstance(app_id, str) and app_id.strip() and app_id.strip().isdigit()
                if not (is_int or is_numeric_str):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'app_id' must be a number (integer) when source is 'splunkbase', got {type(app_id).__name__!r}"
                    )
            deployment_target = app.get("deployment_target", "auto")
            if isinstance(deployment_target, str):
                deployment_target = deployment_target.strip().lower() or "auto"
            else:
                deployment_target = "auto"
            if deployment_target not in ALLOWED_DEPLOYMENT_TARGETS:
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): 'deployment_target' must be one of {ALLOWED_DEPLOYMENT_TARGETS}, got {app.get('deployment_target')!r}"
                )
            # When deployment_target is direct, deployment server is not used; sc_* filters must not be set.
            if deployment_target == "direct":
                for sc_key in ("sc_whitelist", "sc_blacklist"):
                    val = app.get(sc_key)
                    if val is not None and (not isinstance(val, list) or len(val) > 0):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): '{sc_key}' must not be set when deployment_target is 'direct'; "
                            "direct deployment ignores the deployment server, so sc_* filters have no effect."
                        )
            target_roles = app.get("target_roles")
            premium_app = app.get("premium_app")
            itsi_content_pack = app.get("itsi_content_pack")
            if premium_app is not None and target_roles is not None:
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): 'target_roles' must not be set when 'premium_app' is set; "
                    "deployment is calculated automatically for premium apps"
                )
            if target_roles is not None:
                if not isinstance(target_roles, list):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'target_roles' must be a list"
                    )
                for r in target_roles:
                    if r not in allowed_roles:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): 'target_roles' contains invalid role {r!r}. "
                            f"Allowed: {sorted(allowed_roles)}"
                        )
            # Normal apps (no premium_app, no itsi_content_pack) must specify target_roles.
            is_premium = premium_app and isinstance(premium_app, str) and premium_app.strip()
            is_itsi_content_pack = itsi_content_pack is True or (isinstance(itsi_content_pack, bool) and itsi_content_pack)
            if not is_premium and not is_itsi_content_pack and (target_roles is None or not isinstance(target_roles, list) or len(target_roles) == 0):
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): 'target_roles' is required for normal apps (must be a non-empty list)"
                )
            if premium_app is not None:
                if not isinstance(premium_app, str) or not premium_app.strip():
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'premium_app' must be a non-empty string when set"
                    )
                if premium_app.strip().lower() not in ALLOWED_PREMIUM_APPS:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'premium_app' must be one of {ALLOWED_PREMIUM_APPS}, got {premium_app!r}"
                    )
            for key in ("hosts_whitelist", "hosts_blacklist", "shc_whitelist", "shc_blacklist", "idxc_whitelist", "idxc_blacklist", "sc_blacklist"):
                val = app.get(key)
                if val is not None:
                    if not isinstance(val, list):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' must be a list"
                        )
                    for j, v in enumerate(val):
                        if not isinstance(v, str):
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}[{j}]' must be a string"
                            )
            sc_whitelist_val = app.get("sc_whitelist")
            if sc_whitelist_val is not None:
                if not isinstance(sc_whitelist_val, list):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'sc_whitelist' must be a list (serverclass patterns)"
                    )
                for j, v in enumerate(sc_whitelist_val):
                    if not isinstance(v, str):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): 'sc_whitelist[{j}]' must be a string"
                        )
            # Normal apps only: cluster/filter keys require matching target_roles.
            if not is_premium and not is_itsi_content_pack and isinstance(target_roles, list) and len(target_roles) > 0:
                _tr_norm = [str(r).strip().lower() for r in target_roles if r]
                has_shc = (
                    (app.get("shc_whitelist") and len(app.get("shc_whitelist")) > 0)
                    or (app.get("shc_blacklist") and len(app.get("shc_blacklist")) > 0)
                )
                if has_shc and "search_head" not in _tr_norm:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): shc_whitelist/shc_blacklist require target_roles to include 'search_head'"
                    )
                has_idxc = (
                    (app.get("idxc_whitelist") and len(app.get("idxc_whitelist")) > 0)
                    or (app.get("idxc_blacklist") and len(app.get("idxc_blacklist")) > 0)
                )
                if has_idxc and "indexer" not in _tr_norm:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): idxc_whitelist/idxc_blacklist require target_roles to include 'indexer'"
                    )
                _ds_connected_roles = ("universal_forwarder", "heavy_forwarder", "universal_forwarder_windows", "indexer")
                has_sc = (
                    (app.get("sc_whitelist") and len(app.get("sc_whitelist")) > 0)
                    or (app.get("sc_blacklist") and len(app.get("sc_blacklist")) > 0)
                )
                if has_sc and not any(r in _tr_norm for r in _ds_connected_roles):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): sc_whitelist/sc_blacklist require target_roles to include at least one role connected to the deployment server (e.g. universal_forwarder, heavy_forwarder, indexer)"
                    )
            state = app.get("state")
            if state is not None:
                state_str = state.strip().lower() if isinstance(state, str) else state
                if state_str not in ALLOWED_APP_STATES:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'state' must be one of {ALLOWED_APP_STATES}, got {app.get('state')!r}"
                    )
            version = app.get("version")
            if version is not None:
                if not isinstance(version, str) or not version.strip():
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'version' must be a non-empty string ('latest' or a version number)"
                    )
                version_norm = version.strip().lower()
                if version_norm != "latest" and not VERSION_NUMBER_PATTERN.match(version.strip()):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'version' must be 'latest' or a version number (e.g. 1.0, 4.21.1), got {version!r}"
                    )
            # ITSI content pack: reject top-level content_pack_install, content_pack_api, customizations; validate content_pack_apps
            if is_itsi_content_pack:
                for bad_key in ("content_pack_install", "content_pack_api", "customizations"):
                    if app.get(bad_key) is not None:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): top-level '{bad_key}' is not allowed for itsi_content_pack; "
                            "set these only inside content_pack_apps items"
                        )
                install_all_apps = app.get("install_all_apps")
                if not install_all_apps:
                    cp_apps = app.get("content_pack_apps")
                    if cp_apps is None:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): 'content_pack_apps' is required when itsi_content_pack is true and install_all_apps is not true"
                        )
                    if not isinstance(cp_apps, list):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): 'content_pack_apps' must be a list of objects"
                        )
                    for j, cp_item in enumerate(cp_apps):
                        if not isinstance(cp_item, dict):
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}] must be an object (dict)"
                            )
                        cp_name = cp_item.get("name")
                        if cp_name is None or not isinstance(cp_name, str) or not cp_name.strip():
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}] must have a non-empty 'name' string"
                            )
                        if cp_item.get("content_pack_install"):
                            api_opts = cp_item.get("content_pack_api")
                            if api_opts is not None and not isinstance(api_opts, dict):
                                raise ValueError(
                                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].content_pack_api must be a dictionary"
                                )
                        cust = cp_item.get("customizations")
                        if cust is not None:
                            if not isinstance(cust, dict):
                                raise ValueError(
                                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].customizations must be a dictionary"
                                )
                            rpar = cust.get("run_playbook_after_restart")
                            if rpar is not None and (not isinstance(rpar, str) or not rpar.strip()):
                                raise ValueError(
                                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].customizations.run_playbook_after_restart must be a non-empty string"
                                )
                            ev = cust.get("extra_vars")
                            if ev is not None and not isinstance(ev, dict):
                                raise ValueError(
                                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].customizations.extra_vars must be a dictionary"
                                )
            # Validate customizations structure if present (skip for itsi_content_pack; top-level customizations rejected above)
            customizations = app.get("customizations")
            if customizations is not None and not is_itsi_content_pack:
                if not isinstance(customizations, dict):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'customizations' must be a dictionary"
                    )
                remove = customizations.get("remove")
                if remove is not None:
                    if not isinstance(remove, list):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.remove must be a list of paths"
                        )
                    for j, path in enumerate(remove):
                        if not isinstance(path, str) or not path.strip():
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.remove[{j}] must be a non-empty string (path)"
                            )
                local_configs = customizations.get("local_configs")
                if local_configs is not None:
                    if not isinstance(local_configs, dict):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.local_configs must be a dictionary (filename -> sections)"
                        )
                    for filename, sections in local_configs.items():
                        if not isinstance(sections, dict):
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.local_configs.{filename!r} must be a dictionary (section -> options)"
                            )
                        for section_name, opts in sections.items():
                            if not isinstance(opts, dict):
                                raise ValueError(
                                    f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.local_configs.{filename!r}.{section_name!r} must be a dictionary (option -> value)"
                                )
                run_playbook = customizations.get("run_playbook")
                run_role = customizations.get("run_role")
                if run_playbook is not None and (not isinstance(run_playbook, str) or not run_playbook.strip()):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.run_playbook must be a non-empty string (path from project root)"
                    )
                if run_role is not None and (not isinstance(run_role, str) or not run_role.strip()):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.run_role must be a non-empty string (role name)"
                    )
                if run_playbook and run_role:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): use only one of customizations.run_playbook or customizations.run_role per entry, not both"
                    )
                run_playbook_after_restart = customizations.get("run_playbook_after_restart")
                if run_playbook_after_restart is not None and (not isinstance(run_playbook_after_restart, str) or not run_playbook_after_restart.strip()):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.run_playbook_after_restart must be a non-empty string (path from project root)"
                    )
                # run_playbook_after_restart: allowed for direct or deployer→SHC (runs on target or first SH).
                # Disallow only for apps deployed from cluster manager (idxc, no search_head).
                if run_playbook_after_restart is not None and run_playbook_after_restart.strip():
                    no_search_head = "search_head" not in (target_roles or [])
                    if deployment_target != "direct" and no_search_head:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.run_playbook_after_restart is not allowed for apps deployed from a cluster manager; "
                            "use deployment_target 'direct' or include search_head in target_roles (deployer→SHC runs on first SH in cluster)"
                        )
                extra_vars = customizations.get("extra_vars")
                if extra_vars is not None and not isinstance(extra_vars, dict):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.extra_vars must be a dictionary"
                    )
                update_indexes = customizations.get("update_indexes")
                if update_indexes is not None and not isinstance(update_indexes, bool):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.update_indexes must be true or false when set"
                    )

        # Duplicate check: same (name, deployment target, filters) = same target hosts and directory.
        def _filter_tuple(a: dict) -> tuple:
            return (
                tuple(sorted(a.get("hosts_whitelist") or [])),
                tuple(sorted(a.get("hosts_blacklist") or [])),
                tuple(sorted(a.get("shc_whitelist") or [])),
                tuple(sorted(a.get("shc_blacklist") or [])),
                tuple(sorted(a.get("idxc_whitelist") or [])),
                tuple(sorted(a.get("idxc_blacklist") or [])),
                tuple(a.get("sc_whitelist") or []),
                tuple(sorted(a.get("sc_blacklist") or [])),
            )
        seen: Dict[tuple, int] = {}
        for i, app in enumerate(self.apps):
            name = app.get("name")
            if name is None or not isinstance(name, str):
                continue
            deployment_target = app.get("deployment_target", "auto")
            if isinstance(deployment_target, str):
                deployment_target = deployment_target.strip().lower() or "auto"
            else:
                deployment_target = "auto"
            premium_app = app.get("premium_app")
            fkey = _filter_tuple(app)
            if premium_app and isinstance(premium_app, str) and premium_app.strip():
                deploy_key = ("premium", premium_app.strip().lower(), fkey)
            elif app.get("itsi_content_pack"):
                deploy_key = ("itsi_content_pack", fkey)
            else:
                target_roles = app.get("target_roles")
                roles_tuple = tuple(sorted(target_roles)) if isinstance(target_roles, list) else ()
                deploy_key = (deployment_target, roles_tuple, fkey)
            key = (name, deploy_key)
            if key in seen:
                raise ValueError(
                    f"Duplicate app deployment: app {name!r} is defined more than once for the same target (apps[{seen[key]}] and apps[{i}]). "
                    "Same app name with the same target_roles (and deployment_target) deploys to the same hosts and directory; "
                    "only one definition per destination is allowed. Use different target_roles for different role sets."
                )
            seen[key] = i

        # When any itsi_content_pack entry with state installed exists, require at least one app with premium_app: itsi and state: installed.
        # If all itsi_content_pack entries have state: absent, no ITSI app is required (removal scenario).
        has_itsi_content_pack_to_install = any(
            isinstance(a, dict)
            and a.get("itsi_content_pack")
            and (str(a.get("state", "installed")).strip().lower() != "absent")
            for a in (self.apps or [])
        )
        if has_itsi_content_pack_to_install:
            has_itsi_installed = any(
                isinstance(a, dict)
                and (a.get("premium_app") or "").strip().lower() == "itsi"
                and (a.get("itsi_content_pack") or False) is False
                and (str(a.get("state", "installed")).strip().lower() == "installed")
                for a in (self.apps or [])
            )
            if not has_itsi_installed:
                raise ValueError(
                    "When any app has itsi_content_pack: true and state other than 'absent', at least one other app with premium_app: itsi and state: installed must be defined"
                )

        # Content pack state must match ITSI app state (they must always be the same).
        itsi_apps = [a for a in (self.apps or []) if isinstance(a, dict) and (a.get("premium_app") or "").strip().lower() == "itsi"]
        if itsi_apps:
            def _norm_state(s: Any) -> str:
                if s is None:
                    return "installed"
                t = s.strip().lower() if isinstance(s, str) else s
                return t if t in ALLOWED_APP_STATES else "installed"
            itsi_state = _norm_state(itsi_apps[0].get("state"))
            for i, app in enumerate(self.apps):
                if not isinstance(app, dict) or not app.get("itsi_content_pack"):
                    continue
                name = app.get("name") or "?"
                cp_state = _norm_state(app.get("state"))
                if cp_state != itsi_state:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): itsi_content_pack state must match the ITSI app state. "
                        f"ITSI app has state {itsi_state!r}; content pack has state {cp_state!r}. They must always be the same (both 'installed' or both 'absent')."
                    )

        # Roles that receive apps from the deployment server (DS). UF/HF are DS clients; indexer (when not
        # direct) can also be managed by DS and gets a serverclass. search_head-only goes via deployer.
        DS_CLIENT_ROLES = ("universal_forwarder", "heavy_forwarder", "universal_forwarder_windows")
        # Roles that get a serverclass on the DS when the app is DS-managed (so we must enforce unique serverclass).
        DS_SERVERCLASS_ROLES = DS_CLIENT_ROLES + ("indexer",)

        def _app_is_ds_distributed(app: dict) -> bool:
            """True if this app is distributed via the deployment server (targets UF/HF)."""
            deployment_target = app.get("deployment_target", "auto")
            if isinstance(deployment_target, str):
                deployment_target = deployment_target.strip().lower() or "auto"
            else:
                deployment_target = "auto"
            if deployment_target == "direct":
                return False
            target_roles = app.get("target_roles")
            if not isinstance(target_roles, list) or len(target_roles) == 0:
                return False
            return any(
                r and isinstance(r, str) and r.strip().lower() in DS_CLIENT_ROLES
                for r in target_roles
            )

        def _app_uses_ds_serverclass(app: dict) -> bool:
            """True if this app gets a serverclass on the DS (DS-managed and targets UF/HF or indexer).
            Excludes search_head-only (deployer); includes indexer so indexer+UF same name is flagged."""
            if not _app_is_ds_managed(app):
                return False
            target_roles = app.get("target_roles")
            if not isinstance(target_roles, list) or len(target_roles) == 0:
                return False
            return any(
                r and isinstance(r, str) and r.strip().lower() in DS_SERVERCLASS_ROLES
                for r in target_roles
            )

        def _app_is_ds_managed(app: dict) -> bool:
            """True if this app is managed by the deployment server (would be in ds_apps)."""
            deployment_target = app.get("deployment_target", "auto")
            if isinstance(deployment_target, str):
                deployment_target = deployment_target.strip().lower() or "auto"
            else:
                deployment_target = "auto"
            if deployment_target == "direct":
                return False
            premium_app = app.get("premium_app")
            if premium_app and isinstance(premium_app, str) and premium_app.strip():
                return False
            target_roles = app.get("target_roles")
            return isinstance(target_roles, list) and len(target_roles) > 0

        # Duplicate check for deployment-server–distributed apps: same app name may not appear twice when
        # both are distributed via the deployment server (i.e. both target UF/HF). Apps that go only to
        # deployer (search_head), cluster manager (indexer), or direct are not considered here.
        seen_ds_name: Dict[str, int] = {}
        for i, app in enumerate(self.apps):
            name = app.get("name")
            if name is None or not isinstance(name, str):
                continue
            name = name.strip()
            premium_app = app.get("premium_app")
            if premium_app and isinstance(premium_app, str) and premium_app.strip():
                continue
            if not _app_is_ds_distributed(app):
                continue
            if name in seen_ds_name:
                raise ValueError(
                    f"Duplicate app deployment: app {name!r} is defined more than once for deployment server distribution "
                    f"(apps[{seen_ds_name[name]}] and apps[{i}]). Apps managed by the same deployment server must have unique names; "
                    "target_roles do not distinguish destination when both are managed by the same DS."
                )
            seen_ds_name[name] = i

        # Duplicate serverclass check among apps that get a serverclass on the DS: DS-managed and target
        # UF/HF or indexer. search_head-only excluded (deployer). So indexer (no direct) + UF same name → flagged;
        # search_head + UF → not flagged (only UF uses serverclass).
        seen_sc: Dict[str, tuple] = {}  # serverclass -> (app_index, app_name)
        for i, app in enumerate(self.apps):
            if not _app_uses_ds_serverclass(app):
                continue
            name = app.get("name")
            if name is None or not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            sc = app.get("serverclass")
            if isinstance(sc, str) and sc.strip():
                effective_sc = sc.strip()
            else:
                effective_sc = "app_" + name
            if effective_sc in seen_sc:
                first_i, first_name = seen_sc[effective_sc]
                raise ValueError(
                    f"Duplicate serverclass: two apps managed by the deployment server use the same serverclass "
                    f"{effective_sc!r} (apps[{first_i}] and apps[{i}], both name={name!r}). "
                    "Give each entry a unique serverclass (and target_path if they need different customizations), "
                    "e.g. serverclass: \"app_Splunk_TA_nix_indexer\" and serverclass: \"app_Splunk_TA_nix_uf\"."
                )
            seen_sc[effective_sc] = (i, name)
        return self

    @model_validator(mode='after')
    def validate_splunk_app_deployment_direct_vars(self) -> 'SplunkAppDeploymentConfig':
        """Validate top-level splunk_app_deployment keys (target_download, cache_downloads, etc.) when present."""
        # Booleans
        for key in (
            "target_download",
            "cache_downloads",
            "backup_apps_before_update",
            "restart_after_deployment",
            "deploymentclient_check",
        ):
            val = getattr(self, key, None)
            if val is not None and not isinstance(val, bool):
                raise ValueError(
                    f"splunk_app_deployment.{key} must be a boolean, got {type(val).__name__!r}"
                )
        # Non-empty strings (paths / URLs)
        for key in ("temp_dir", "backup_location", "local_app_repo_path", "splunkbase_api_url"):
            val = getattr(self, key, None)
            if val is not None:
                if not isinstance(val, str) or not val.strip():
                    raise ValueError(
                        f"splunk_app_deployment.{key} must be a non-empty string, got {val!r}"
                    )
        # download_timeout, restart_timeout: positive integer
        for key in ("download_timeout", "restart_timeout"):
            val = getattr(self, key, None)
            if val is not None:
                if not isinstance(val, int) or isinstance(val, bool) or val < 1:
                    raise ValueError(
                        f"splunk_app_deployment.{key} must be a positive integer, got {val!r}"
                    )
        # retry_count: non-negative integer
        retry = getattr(self, "retry_count", None)
        if retry is not None:
            if not isinstance(retry, int) or isinstance(retry, bool) or retry < 0:
                raise ValueError(
                    f"splunk_app_deployment.retry_count must be a non-negative integer, got {retry!r}"
                )
        return self


class SplunkSystemdConfig(BaseModel):
    """Splunk systemd configuration."""
    model_config = ConfigDict(extra='allow')


class SplunkEnvironment(BaseModel):
    """Splunk environment definition."""
    model_config = ConfigDict(extra='allow')
    
    splunk_env_name: str
    splunk_version: Optional[str] = None
    splunk_admin_password: Optional[str] = None
    splunk_license_file: Optional[str] = None
    splunk_indexes: Optional[Dict[str, Any]] = None


class IdxClusterConfig(BaseModel):
    """Indexer cluster configuration."""
    model_config = ConfigDict(extra='allow')
    
    idxc_name: str
    idxc_password: Optional[str] = None
    idxc_replication_port: Optional[int] = Field(None, ge=1, le=65535)
    idxc_site_rf: Optional[str] = None
    idxc_site_sf: Optional[str] = None
    idxc_rf: Optional[int] = Field(None, ge=1)
    idxc_sf: Optional[int] = Field(None, ge=1)
    idxc_discovery_password: Optional[str] = None


class ShClusterConfig(BaseModel):
    """Search head cluster configuration."""
    model_config = ConfigDict(extra='allow')
    
    shc_name: str
    shc_site: Optional[str] = None
    shc_password: Optional[str] = None
    shc_replication_port: Optional[int] = Field(None, ge=1, le=65535)


class HostIteration(BaseModel):
    """Host iteration for generating multiple hosts."""
    prefix: Optional[str] = None
    numbers: str = Field(..., pattern=r'^\d+\.\.\d+$', description="Range like '1..3'")
    postfix: Optional[str] = None


class CustomConfig(BaseModel):
    """Custom/arbitrary settings (for ansible connection vars, etc.)."""
    model_config = ConfigDict(extra='allow')


class SplunkHost(BaseModel):
    """Individual Splunk host configuration."""
    model_config = ConfigDict(extra='allow')
    
    # Host identification - exactly one must be specified
    name: Optional[str] = None
    list: Optional[List[str]] = None
    iter: Optional[HostIteration] = None
    
    # Required
    roles: List[AllowedRole] = Field(..., min_length=1, description="At least one role required")
    
    # Optional settings
    splunk_env: Optional[str] = None
    site: Optional[str] = None
    cname: Optional[str] = None
    idxcluster: Optional[str] = None
    shcluster: Optional[str] = None
    ip_addr: Optional[str] = None
    
    # Host-level overrides
    splunk_version: Optional[str] = None
    splunk_architecture: Optional[str] = None
    splunk_admin_password: Optional[str] = None
    splunk_license_file: Optional[str] = None
    splunk_outputs: Optional[str] = None
    splunk_search_peers: Optional[str] = None
    splunk_conf: Optional[Dict[str, Dict[str, Any]]] = None
    splunk_fips: Optional[bool] = None
    
    # Nested configs
    os: Optional[OsConfig] = None
    aws: Optional[Dict[str, Any]] = None
    virtualbox: Optional[VirtualBoxConfig] = None
    custom: Optional[CustomConfig] = None
    terraform: Optional[TerraformConfig] = None

    @model_validator(mode='after')
    def validate_host_identifier(self) -> 'SplunkHost':
        """Ensure exactly one of name, list, or iter is specified."""
        identifiers = [self.name, self.list, self.iter]
        count = sum(1 for i in identifiers if i is not None)
        
        if count == 0:
            raise ValueError("Host must have exactly one of: 'name', 'list', or 'iter'")
        if count > 1:
            raise ValueError("Host cannot have multiple identifiers. Use only one of: 'name', 'list', or 'iter'")
        
        return self

    @model_validator(mode='after')
    def validate_site_with_roles(self) -> 'SplunkHost':
        """Ensure 'site' is only used with allowed roles."""
        if self.site is not None:
            allowed_site_roles = {AllowedRole.indexer, AllowedRole.search_head, AllowedRole.cluster_manager}
            if not any(role in allowed_site_roles for role in self.roles):
                allowed_names = ', '.join(r.value for r in allowed_site_roles)
                raise ValueError(f"'site' is only allowed for roles: {allowed_names}")
        return self

    @model_validator(mode='after')
    def validate_cluster_manager_has_idxcluster(self) -> 'SplunkHost':
        """Ensure cluster_manager role has idxcluster specified."""
        if AllowedRole.cluster_manager in self.roles and not self.idxcluster:
            raise ValueError("'idxcluster' must be specified for hosts with role 'cluster_manager'")
        return self

    @model_validator(mode='after')
    def validate_deployer_has_shcluster(self) -> 'SplunkHost':
        """Ensure deployer role has shcluster specified."""
        if AllowedRole.deployer in self.roles and not self.shcluster:
            raise ValueError("'shcluster' must be specified for hosts with role 'deployer'")
        return self


# =============================================================================
# Root configuration model
# =============================================================================

class SplunkConfig(BaseModel):
    """
    Root configuration model for splunk_config.yml.
    
    Required fields:
    - plugin: Must be 'splunk-platform-automator'
    - splunk_hosts: List of host configurations (at least one)
    
    All other sections are optional.
    """
    model_config = ConfigDict(extra='allow')
    
    # Required fields
    plugin: str = Field(..., pattern=r'^splunk-platform-automator$')
    splunk_hosts: List[SplunkHost] = Field(..., min_length=1, description="At least one host required")
    
    # Optional sections
    general: Optional[GeneralConfig] = None
    custom: Optional[CustomConfig] = None
    os: Optional[OsConfig] = None
    virtualbox: Optional[VirtualBoxConfig] = None
    aws: Optional[Dict[str, Any]] = None
    terraform: Optional[TerraformConfig] = None
    splunk_defaults: Optional[SplunkDefaultsConfig] = None
    splunk_dirs: Optional[SplunkDirsConfig] = None
    splunk_apps: Optional[SplunkAppsConfig] = None
    splunk_app_deployment: Optional[SplunkAppDeploymentConfig] = None
    splunk_systemd: Optional[SplunkSystemdConfig] = None
    splunk_environments: Optional[List[SplunkEnvironment]] = None
    splunk_idxclusters: Optional[List[IdxClusterConfig]] = None
    splunk_shclusters: Optional[List[ShClusterConfig]] = None

    @field_validator('plugin')
    @classmethod
    def validate_plugin_name(cls, v: str) -> str:
        if v != 'splunk-platform-automator':
            raise ValueError(f"Invalid plugin: '{v}'. Must be 'splunk-platform-automator'")
        return v

    @model_validator(mode='after')
    def validate_deployer_requires_shc(self) -> 'SplunkConfig':
        """Ensure deployer role has at least 3 search heads (SHC minimum).
        
        Only validates when search heads are explicitly defined in the config.
        A deployer with 0 search heads is allowed (external SHC scenario).
        """
        has_deployer = False
        search_head_count = 0
        
        for host in self.splunk_hosts:
            if AllowedRole.deployer in host.roles:
                has_deployer = True
            if AllowedRole.search_head in host.roles:
                # Count hosts based on identifier type
                if host.name:
                    search_head_count += 1
                elif host.list:
                    search_head_count += len(host.list)
                elif host.iter:
                    # Parse range like '1..3' to count hosts
                    parts = host.iter.numbers.split('..')
                    start, end = int(parts[0]), int(parts[1])
                    search_head_count += (end - start + 1)
        
        # Only validate if search heads are defined (1 or 2 is invalid with deployer)
        if has_deployer and search_head_count > 0 and search_head_count < 3:
            raise ValueError(
                f"A deployer requires a Search Head Cluster with at least 3 search heads. "
                f"Found {search_head_count} search head(s)."
            )
        
        return self

    @model_validator(mode='after')
    def validate_shc_members_have_shcluster(self) -> 'SplunkConfig':
        """Ensure at least 3 search heads have shcluster flag when deployer exists.
        
        If a deployer role is defined, at least 3 search_head roles must have
        an shcluster specified to form a valid Search Head Cluster.
        Standalone search heads without shcluster are allowed alongside SHC members.
        """
        has_deployer = False
        shc_member_count = 0
        
        for host in self.splunk_hosts:
            if AllowedRole.deployer in host.roles:
                has_deployer = True
            
            if AllowedRole.search_head in host.roles and host.shcluster:
                # Count SHC members based on identifier type
                if host.name:
                    shc_member_count += 1
                elif host.list:
                    shc_member_count += len(host.list)
                elif host.iter:
                    parts = host.iter.numbers.split('..')
                    start, end = int(parts[0]), int(parts[1])
                    shc_member_count += (end - start + 1)
        
        if has_deployer and shc_member_count < 3:
            raise ValueError(
                f"When a deployer is defined, at least 3 search heads must have 'shcluster' specified. "
                f"Found {shc_member_count} search head(s) with shcluster."
            )
        
        return self

    @model_validator(mode='after')
    def validate_shc_members_require_deployer(self) -> 'SplunkConfig':
        """If any search head has shcluster set (SHC member), a deployer role must be defined.
        
        Search Head Cluster members receive apps from the deployer; without a deployer
        the SHC configuration is invalid.
        """
        has_shc_member = False
        has_deployer = False
        for host in self.splunk_hosts:
            if AllowedRole.search_head in host.roles and host.shcluster:
                has_shc_member = True
            if AllowedRole.deployer in host.roles:
                has_deployer = True
        if has_shc_member and not has_deployer:
            raise ValueError(
                "Search heads with 'shcluster' set (Search Head Cluster members) require a deployer. "
                "No host has the 'deployer' role. Add a host with role 'deployer' or remove 'shcluster' from search heads."
            )
        return self

    @model_validator(mode='after')
    def validate_shcluster_requires_splunk_shclusters(self) -> 'SplunkConfig':
        """If any host has shcluster set, splunk_shclusters must be defined and include that cluster name."""
        shcluster_names_used: set = set()
        for host in self.splunk_hosts:
            if host.shcluster and isinstance(host.shcluster, str) and host.shcluster.strip():
                shcluster_names_used.add(host.shcluster.strip())
        if not shcluster_names_used:
            return self
        defined_shc_names = set()
        if self.splunk_shclusters:
            for shc in self.splunk_shclusters:
                defined_shc_names.add(shc.shc_name)
        missing = shcluster_names_used - defined_shc_names
        if missing:
            raise ValueError(
                f"Host(s) have 'shcluster' set to cluster name(s) that are not defined in splunk_shclusters: {sorted(missing)!r}. "
                f"splunk_shclusters must define each cluster name used by hosts. "
                f"Defined in splunk_shclusters: {sorted(defined_shc_names)!r}."
            )
        return self

    @model_validator(mode='after')
    def validate_deployer_shcluster_must_match_defined_shc(self) -> 'SplunkConfig':
        """Ensure every deployer has shcluster set to a defined shc_name from splunk_shclusters.

        When multiple SHCs are defined, the deployer must explicitly specify which cluster
        it serves via the shcluster field (same value as one of splunk_shclusters[].shc_name).
        """
        defined_shc_names: set = set()
        if self.splunk_shclusters:
            for shc in self.splunk_shclusters:
                defined_shc_names.add(shc.shc_name)

        for host in self.splunk_hosts:
            if AllowedRole.deployer not in host.roles:
                continue
            # Host-level validator already requires deployer to have shcluster set
            shc_val = (host.shcluster or "").strip() if isinstance(host.shcluster, str) else ""
            if not shc_val:
                raise ValueError(
                    "Host with role 'deployer' must have 'shcluster' set to the SHC name it serves. "
                    "When multiple SHCs are defined, the deployer must specify which cluster via 'shcluster'."
                )
            if defined_shc_names and shc_val not in defined_shc_names:
                raise ValueError(
                    f"Host with role 'deployer' has shcluster={host.shcluster!r}, which must be one of the "
                    f"SHC names defined in splunk_shclusters. When multiple SHCs are defined, the deployer "
                    f"must specify which cluster it serves. Defined SHC names: {sorted(defined_shc_names)!r}."
                )
        return self

    @model_validator(mode='after')
    def validate_each_shc_has_deployer_when_multiple_shcs(self) -> 'SplunkConfig':
        """When multiple SHCs are defined, each SHC must have at least one deployer.

        Every shc_name in splunk_shclusters must have a host with role 'deployer' and
        shcluster set to that shc_name. A single deployer can only serve one SHC.
        """
        if not self.splunk_shclusters or len(self.splunk_shclusters) < 2:
            return self

        defined_shc_names = {shc.shc_name for shc in self.splunk_shclusters}
        shc_names_with_deployer: set = set()
        for host in self.splunk_hosts:
            if AllowedRole.deployer not in host.roles:
                continue
            shc_val = (host.shcluster or "").strip() if isinstance(host.shcluster, str) else ""
            if shc_val and shc_val in defined_shc_names:
                shc_names_with_deployer.add(shc_val)

        missing = defined_shc_names - shc_names_with_deployer
        if missing:
            raise ValueError(
                f"When multiple Search Head Clusters are defined, each SHC must have a deployer. "
                f"SHC(s) without a deployer: {sorted(missing)!r}. "
                f"Add a host with role 'deployer' and shcluster set to each of these cluster names, "
                f"or remove the SHC definition. SHCs with a deployer: {sorted(shc_names_with_deployer)!r}."
            )
        return self

    @model_validator(mode='after')
    def validate_idxc_members_have_idxcluster(self) -> 'SplunkConfig':
        """Ensure at least 2 indexers have idxcluster flag when cluster_manager exists.
        
        If a cluster_manager role is defined, at least 2 indexer roles must have
        an idxcluster specified to form a valid Indexer Cluster.
        Standalone indexers without idxcluster are allowed alongside IDXC members.
        """
        has_cluster_manager = False
        idxc_member_count = 0
        
        for host in self.splunk_hosts:
            if AllowedRole.cluster_manager in host.roles:
                has_cluster_manager = True
            
            if AllowedRole.indexer in host.roles and host.idxcluster:
                # Count IDXC members based on identifier type
                if host.name:
                    idxc_member_count += 1
                elif host.list:
                    idxc_member_count += len(host.list)
                elif host.iter:
                    parts = host.iter.numbers.split('..')
                    start, end = int(parts[0]), int(parts[1])
                    idxc_member_count += (end - start + 1)
        
        if has_cluster_manager and idxc_member_count < 2:
            raise ValueError(
                f"When a cluster_manager is defined, at least 2 indexers must have 'idxcluster' specified. "
                f"Found {idxc_member_count} indexer(s) with idxcluster."
            )
        
        return self

    @model_validator(mode='after')
    def validate_idxc_members_require_cluster_manager(self) -> 'SplunkConfig':
        """If any indexer has idxcluster set (IDXC member), a cluster_manager role must be defined.
        
        Indexer cluster members are managed by the cluster manager; without a cluster_manager
        the IDXC configuration is invalid.
        """
        has_idxc_member = False
        has_cluster_manager = False
        for host in self.splunk_hosts:
            if AllowedRole.indexer in host.roles and host.idxcluster:
                has_idxc_member = True
            if AllowedRole.cluster_manager in host.roles:
                has_cluster_manager = True
        if has_idxc_member and not has_cluster_manager:
            raise ValueError(
                "Indexers with 'idxcluster' set (Indexer Cluster members) require a cluster_manager. "
                "No host has the 'cluster_manager' role. Add a host with role 'cluster_manager' or remove 'idxcluster' from indexers."
            )
        return self

    @model_validator(mode='after')
    def validate_idxcluster_requires_splunk_idxclusters(self) -> 'SplunkConfig':
        """If any host has idxcluster set, splunk_idxclusters must be defined and include that cluster name."""
        idxcluster_names_used: set = set()
        for host in self.splunk_hosts:
            if host.idxcluster and isinstance(host.idxcluster, str) and host.idxcluster.strip():
                idxcluster_names_used.add(host.idxcluster.strip())
        if not idxcluster_names_used:
            return self
        defined_idxc_names = set()
        if self.splunk_idxclusters:
            for idxc in self.splunk_idxclusters:
                defined_idxc_names.add(idxc.idxc_name)
        missing = idxcluster_names_used - defined_idxc_names
        if missing:
            raise ValueError(
                f"Host(s) have 'idxcluster' set to cluster name(s) that are not defined in splunk_idxclusters: {sorted(missing)!r}. "
                f"splunk_idxclusters must define each cluster name used by hosts. "
                f"Defined in splunk_idxclusters: {sorted(defined_idxc_names)!r}."
            )
        return self

    @model_validator(mode='after')
    def validate_license_manager_requires_license_file(self) -> 'SplunkConfig':
        """Ensure license_manager role has splunk_license_file defined.
        
        If a license_manager role is defined, the splunk_defaults must include
        a splunk_license_file setting.
        """
        has_license_manager = False
        
        for host in self.splunk_hosts:
            if AllowedRole.license_manager in host.roles:
                has_license_manager = True
                break
        
        if has_license_manager:
            # Check if splunk_license_file is defined in splunk_defaults
            has_license_file = (
                self.splunk_defaults is not None and 
                self.splunk_defaults.splunk_license_file is not None
            )
            if not has_license_file:
                raise ValueError(
                    "When a license_manager role is defined, 'splunk_license_file' must be specified "
                    "in splunk_defaults."
                )
        
        return self

    @model_validator(mode='after')
    def validate_itsi_requires_search_head_indexer_license_manager(self) -> 'SplunkConfig':
        """When ITSI (Splunk IT Service Intelligence) is in app deployment, the environment must have search_head, indexer, and license_manager roles."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        has_itsi = any(
            isinstance(a, dict)
            and (a.get("premium_app") or "").strip().lower() == "itsi"
            for a in dep.apps
        )
        if not has_itsi:
            return self

        roles_present: set = set()
        for host in self.splunk_hosts:
            roles_present.update(host.roles)

        required = {AllowedRole.search_head, AllowedRole.indexer, AllowedRole.license_manager}
        missing = required - roles_present
        if missing:
            missing_names = sorted(r.value for r in missing)
            raise ValueError(
                "When Splunk IT Service Intelligence (ITSI) is in splunk_app_deployment, the environment "
                "must include hosts with roles: search_head, indexer, and license_manager. "
                f"Missing role(s): {missing_names!r}. Add at least one host with each of these roles in splunk_hosts."
            )
        return self

    @model_validator(mode='after')
    def validate_itsi_single_indexer_layer(self) -> 'SplunkConfig':
        """When ITSI is enabled for install, allow only one indexer layer: either one IDXC or one standalone indexer.

        The code cannot cope with two or more indexer clusters, or a mix of IDXC and standalone indexers.
        """
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        # ITSI must be present and installed (not removal-only)
        has_itsi_for_install = any(
            isinstance(a, dict)
            and (a.get("premium_app") or "").strip().lower() == "itsi"
            and (str(a.get("state", "installed")).strip().lower() != "absent")
            for a in dep.apps
        )
        if not has_itsi_for_install:
            return self

        num_idxc = len(self.splunk_idxclusters) if self.splunk_idxclusters else 0

        def _host_count(host: SplunkHost) -> int:
            if host.name is not None:
                return 1
            if host.list is not None:
                return len(host.list)
            if host.iter is not None:
                parts = host.iter.numbers.split("..")
                start, end = int(parts[0]), int(parts[1])
                return end - start + 1
            return 0

        standalone_indexer_count = 0
        for host in self.splunk_hosts:
            if AllowedRole.indexer not in host.roles:
                continue
            if host.idxcluster and isinstance(host.idxcluster, str) and host.idxcluster.strip():
                continue
            standalone_indexer_count += _host_count(host)

        # Allowed: exactly one IDXC and no standalone indexers, OR no IDXC and exactly one standalone indexer
        if num_idxc == 1 and standalone_indexer_count == 0:
            return self
        if num_idxc == 0 and standalone_indexer_count == 1:
            return self

        raise ValueError(
            "When Splunk IT Service Intelligence (ITSI) is enabled for install, the environment must have "
            "exactly one indexer layer: either one indexer cluster (splunk_idxclusters with one cluster and all "
            "indexers in it) or one standalone indexer (no splunk_idxclusters, exactly one indexer host without "
            "idxcluster). The code cannot cope with multiple indexer clusters or a mix of cluster and standalone "
            "indexers. "
            f"Current: {num_idxc} indexer cluster(s), {standalone_indexer_count} standalone indexer(s). "
            "Use exactly one cluster with all indexers as members, or remove clusters and use a single standalone indexer."
        )

    @model_validator(mode='after')
    def validate_no_direct_deploy_to_shc_members(self) -> 'SplunkConfig':
        """Fail if any app is configured for direct deployment to search_head while SHC members exist.

        Apps must not use deployment_target: direct with target_roles including search_head when
        there are search heads in a Search Head Cluster; SHC members receive apps via the Deployer.
        Exceptions: (1) when the app has hosts_whitelist set, the target set can be restricted to
        standalone search heads only by host name; (2) when shc_whitelist or shc_blacklist is set
        and the effective targeted SHC set is empty (no SHC targeted), only standalone SHs get the
        app, so direct is allowed. Otherwise if an SHC member would receive the app direct, raise.
        """
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        # Check if any search head host is an SHC member (has shcluster set)
        has_shc_member = False
        for host in self.splunk_hosts:
            if AllowedRole.search_head not in host.roles or not host.shcluster:
                continue
            has_shc_member = True
            break

        if not has_shc_member:
            return self

        shc_names: set = set()
        if self.splunk_shclusters:
            for shc in self.splunk_shclusters:
                shc_names.add(shc.shc_name)

        # Find apps with deployment_target: direct and search_head in target_roles
        # Allow when: hosts_whitelist set (restrict to standalone SHs by name), or
        # shc_whitelist/shc_blacklist results in no SHC targeted (only standalone SHs get the app).
        apps_direct_to_shc: List[Dict[str, Any]] = []
        for app in dep.apps:
            target_roles = app.get("target_roles") or []
            if not isinstance(target_roles, list):
                continue
            if app.get("deployment_target") != "direct":
                continue
            if "search_head" not in target_roles:
                continue
            # Allow if app has hosts_whitelist (can restrict to standalone SHs by host name)
            hw = app.get("hosts_whitelist") or []
            if isinstance(hw, list) and any(isinstance(v, str) and v.strip() for v in hw):
                continue
            # Allow if shc_whitelist/shc_blacklist leaves no SHC targeted (app goes to standalone SH only)
            shc_w = [v.strip() for v in (app.get("shc_whitelist") or []) if isinstance(v, str) and v.strip()]
            shc_b = [v.strip() for v in (app.get("shc_blacklist") or []) if isinstance(v, str) and v.strip()]
            if shc_w or shc_b:
                effectively_targeted = set(shc_w) if shc_w else (shc_names - set(shc_b))
                if not effectively_targeted:
                    continue
            apps_direct_to_shc.append(app)

        if apps_direct_to_shc:
            names = ", ".join(app.get("name", "?") for app in apps_direct_to_shc)
            raise ValueError(
                "Invalid app deployment config: at least one app is set to deploy directly "
                "(deployment_target: direct) to search_head while there are search heads in a "
                "Search Head Cluster (SHC). SHC members must receive apps via the Deployer, not "
                "direct deployment. Apps with deployment_target: direct and target_roles including "
                f"search_head: {names}. Fix: remove deployment_target: direct for these apps or "
                "restrict target_roles so they do not include search_head when SHC is in use; "
                "deploy SHC apps via the Deployer (omit deployment_target or set deployment_target: auto)."
            )

        return self

    @model_validator(mode='after')
    def validate_target_filter_shc_idxc_names(self) -> 'SplunkConfig':
        """shc_whitelist/shc_blacklist must reference defined SHC names (splunk_shclusters).
        idxc_whitelist/idxc_blacklist must reference defined IDXC names (splunk_idxclusters).
        The corresponding cluster section must be defined when these options are used."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        shc_names: set = set()
        if self.splunk_shclusters:
            for shc in self.splunk_shclusters:
                shc_names.add(shc.shc_name)
        idxc_names: set = set()
        if self.splunk_idxclusters:
            for idxc in self.splunk_idxclusters:
                idxc_names.add(idxc.idxc_name)

        for i, app in enumerate(dep.apps):
            name = app.get("name", "?")

            for key in ("shc_whitelist", "shc_blacklist"):
                val = app.get(key)
                if not val or not isinstance(val, list):
                    continue
                vals = [v.strip() for v in val if isinstance(v, str) and v.strip()]
                if not vals:
                    continue
                if not self.splunk_shclusters:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' requires splunk_shclusters to be defined. "
                        "Add splunk_shclusters and define the SHC names used in the app."
                    )
                for v in vals:
                    if v not in shc_names:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' must contain names from splunk_shclusters. "
                            f"Unknown SHC {v!r}. Defined: {sorted(shc_names)!r}"
                        )

            for key in ("idxc_whitelist", "idxc_blacklist"):
                val = app.get(key)
                if not val or not isinstance(val, list):
                    continue
                vals = [v.strip() for v in val if isinstance(v, str) and v.strip()]
                if not vals:
                    continue
                if not self.splunk_idxclusters:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' requires splunk_idxclusters to be defined. "
                        "Add splunk_idxclusters and define the IDXC names used in the app."
                    )
                for v in vals:
                    if v not in idxc_names:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' must contain names from splunk_idxclusters. "
                            f"Unknown IDXC {v!r}. Defined: {sorted(idxc_names)!r}"
                        )
        return self

    @model_validator(mode='after')
    def validate_cluster_and_ds_filters_have_matching_hosts(self) -> 'SplunkConfig':
        """When using shc_*/idxc_* filters, targeted clusters must have hosts with the relevant role.
        When using sc_* filters, there must be a deployment server host."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        # SHC names that have at least one search_head member
        shc_clusters_with_search_head: set = set()
        for host in self.splunk_hosts:
            if AllowedRole.search_head not in host.roles:
                continue
            sc = getattr(host, "shcluster", None)
            if sc and isinstance(sc, str) and sc.strip():
                shc_clusters_with_search_head.add(sc.strip())

        # IDXC names that have at least one indexer member
        idxc_clusters_with_indexer: set = set()
        for host in self.splunk_hosts:
            if AllowedRole.indexer not in host.roles:
                continue
            ic = getattr(host, "idxcluster", None)
            if ic and isinstance(ic, str) and ic.strip():
                idxc_clusters_with_indexer.add(ic.strip())

        has_deployment_server = any(
            AllowedRole.deployment_server in host.roles for host in self.splunk_hosts
        )

        # DS client roles that have at least one host (deployment clients of the deployment server)
        _ds_role_enums = (
            AllowedRole.universal_forwarder,
            AllowedRole.heavy_forwarder,
            AllowedRole.universal_forwarder_windows,
            AllowedRole.indexer,
        )
        ds_client_roles_with_hosts: set = set()
        for host in self.splunk_hosts:
            for r in host.roles:
                if r in _ds_role_enums:
                    ds_client_roles_with_hosts.add(r.value)

        shc_names: set = set()
        if self.splunk_shclusters:
            for shc in self.splunk_shclusters:
                shc_names.add(shc.shc_name)
        idxc_names: set = set()
        if self.splunk_idxclusters:
            for idxc in self.splunk_idxclusters:
                idxc_names.add(idxc.idxc_name)

        for i, app in enumerate(dep.apps):
            name = app.get("name", "?")
            # serverclass requires at least one host with role deployment_server
            sc = app.get("serverclass")
            if isinstance(sc, str) and sc.strip():
                if not has_deployment_server:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'serverclass' is set but there is no host with role deployment_server in splunk_hosts. "
                        "Add a host with role deployment_server, or remove serverclass if this app is not deployed via the deployment server."
                    )
            if app.get("premium_app") and isinstance(app.get("premium_app"), str) and (app.get("premium_app") or "").strip():
                continue
            if app.get("itsi_content_pack") is True:
                continue

            target_roles_list = app.get("target_roles") or []
            if not isinstance(target_roles_list, list):
                continue
            _tr_norm = [str(r).strip().lower() for r in target_roles_list if r]

            # shc_*: targeted clusters must include at least one cluster that has a search_head
            shc_w = [v.strip() for v in (app.get("shc_whitelist") or []) if isinstance(v, str) and v.strip()]
            shc_b = [v.strip() for v in (app.get("shc_blacklist") or []) if isinstance(v, str) and v.strip()]
            if shc_w or shc_b:
                if "search_head" not in _tr_norm:
                    continue  # already validated in validate_apps_structure
                if not shc_names:
                    continue  # already validated in validate_target_filter_shc_idxc_names
                effectively_targeted = set(shc_w) if shc_w else (shc_names - set(shc_b))
                # Allow no SHC targeted: app can target standalone search heads only (e.g. hosts_whitelist or DS to single sh).
                if not effectively_targeted:
                    continue
                overlap = effectively_targeted & shc_clusters_with_search_head
                if not overlap:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): shc_whitelist/shc_blacklist target SHC(s) {sorted(effectively_targeted)!r}, "
                        f"but no host with role search_head is in those clusters. "
                        f"Search head cluster members (hosts with search_head and shcluster set): {sorted(shc_clusters_with_search_head)!r}. "
                        "Ensure targeted clusters have at least one search head member in splunk_hosts."
                    )

            # idxc_*: targeted clusters must include at least one cluster that has an indexer
            idxc_w = [v.strip() for v in (app.get("idxc_whitelist") or []) if isinstance(v, str) and v.strip()]
            idxc_b = [v.strip() for v in (app.get("idxc_blacklist") or []) if isinstance(v, str) and v.strip()]
            if idxc_w or idxc_b:
                if "indexer" not in _tr_norm:
                    continue
                if not idxc_names:
                    continue
                effectively_targeted = set(idxc_w) if idxc_w else (idxc_names - set(idxc_b))
                if not effectively_targeted:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): idxc_blacklist excludes all defined IDXCs; "
                        "no indexer cluster is targeted. Adjust idxc_whitelist or idxc_blacklist."
                    )
                overlap = effectively_targeted & idxc_clusters_with_indexer
                if not overlap:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): idxc_whitelist/idxc_blacklist target IDXC(s) {sorted(effectively_targeted)!r}, "
                        f"but no host with role indexer is in those clusters. "
                        f"Indexer cluster members (hosts with indexer and idxcluster set): {sorted(idxc_clusters_with_indexer)!r}. "
                        "Ensure targeted clusters have at least one indexer member in splunk_hosts."
                    )

            # sc_*: deployment server must exist and at least one host with a target role must be a deployment client
            sc_w = app.get("sc_whitelist") and len(app.get("sc_whitelist")) > 0
            sc_b = app.get("sc_blacklist") and len(app.get("sc_blacklist")) > 0
            if sc_w or sc_b:
                _ds_roles = ("universal_forwarder", "heavy_forwarder", "universal_forwarder_windows", "indexer")
                app_ds_roles = set(_tr_norm) & set(_ds_roles)
                if not app_ds_roles:
                    continue
                if not has_deployment_server:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): sc_whitelist/sc_blacklist require at least one host with role deployment_server "
                        "so that apps can be deployed to forwarders/indexers. Add a host with role deployment_server in splunk_hosts."
                    )
                # At least one of the app's target roles (DS roles) must have a host that is a deployment client
                overlap = app_ds_roles & ds_client_roles_with_hosts
                if not overlap:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): sc_whitelist/sc_blacklist require at least one host with one of target_roles {sorted(app_ds_roles)!r} "
                        f"to be a deployment client of the deployment server. Hosts with those roles in splunk_hosts: {sorted(ds_client_roles_with_hosts)!r}. "
                        "Add a host with one of the app's target_roles (e.g. universal_forwarder, heavy_forwarder, indexer)."
                    )
        return self

    @model_validator(mode='after')
    def validate_target_filter_hosts_exist(self) -> 'SplunkConfig':
        """hosts_whitelist and hosts_blacklist must contain only host names that exist in splunk_hosts
        and must not include cluster members (SHC or IDXC); use shc_whitelist/idxc_whitelist for those."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        def expand_host_names(host: 'SplunkHost') -> set:
            names: set = set()
            if host.name:
                names.add(host.name)
            elif host.list:
                for h in host.list:
                    names.add(h)
            elif host.iter:
                parts = host.iter.numbers.split('..')
                start, end = int(parts[0]), int(parts[1])
                width = len(parts[1])
                prefix = host.iter.prefix or ""
                postfix = host.iter.postfix or ""
                for n in range(start, end + 1):
                    names.add(prefix + str(n).zfill(width) + postfix)
            return names

        inventory_host_names: set = set()
        cluster_member_host_names: set = set()
        for host in self.splunk_hosts:
            names = expand_host_names(host)
            inventory_host_names.update(names)
            if host.shcluster or host.idxcluster:
                cluster_member_host_names.update(names)

        if not inventory_host_names:
            return self

        for i, app in enumerate(dep.apps):
            name = app.get("name", "?")
            for key in ("hosts_whitelist", "hosts_blacklist"):
                val = app.get(key)
                if not val or not isinstance(val, list):
                    continue
                for j, v in enumerate(val):
                    if not isinstance(v, str) or not v.strip():
                        continue
                    h = v.strip()
                    if h not in inventory_host_names:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' must contain host names from splunk_hosts. "
                            f"Unknown host {v!r} at index {j}."
                        )
                    if h in cluster_member_host_names:
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): '{key}' must not contain cluster members. "
                            f"Host {v!r} is a member of an SHC or IDXC; use shc_whitelist/shc_blacklist or idxc_whitelist/idxc_blacklist instead."
                        )
        return self

    @model_validator(mode='after')
    def validate_target_roles_include_host_filter_roles(self) -> 'SplunkConfig':
        """For normal apps, target_roles must include every role that hosts in hosts_whitelist/hosts_blacklist have."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        def expand_host_names(host: 'SplunkHost') -> set:
            names: set = set()
            if host.name:
                names.add(host.name)
            elif host.list:
                for h in host.list:
                    names.add(h)
            elif host.iter:
                parts = host.iter.numbers.split('..')
                start, end = int(parts[0]), int(parts[1])
                width = len(parts[1])
                prefix = host.iter.prefix or ""
                postfix = host.iter.postfix or ""
                for n in range(start, end + 1):
                    names.add(prefix + str(n).zfill(width) + postfix)
            return names

        # Map each host name to the set of role values (strings) for that host
        host_names_to_roles: Dict[str, set] = {}
        for host in self.splunk_hosts:
            names = expand_host_names(host)
            role_values = {r.value for r in host.roles}
            for n in names:
                host_names_to_roles.setdefault(n, set()).update(role_values)

        for i, app in enumerate(dep.apps):
            if app.get("premium_app") and isinstance(app.get("premium_app"), str) and app.get("premium_app", "").strip():
                continue
            name = app.get("name", "?")
            target_roles_list = app.get("target_roles") or []
            if not isinstance(target_roles_list, list):
                continue
            target_roles_set = set(target_roles_list)
            host_filter_names = set()
            for key in ("hosts_whitelist", "hosts_blacklist"):
                val = app.get(key)
                if val and isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v.strip():
                            host_filter_names.add(v.strip())
            if not host_filter_names:
                continue
            required_roles = set()
            for h in host_filter_names:
                required_roles.update(host_names_to_roles.get(h, set()))
            missing = required_roles - target_roles_set
            if missing:
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): hosts in hosts_whitelist/hosts_blacklist have roles {sorted(required_roles)!r}; "
                    f"target_roles must include all of them. Missing in target_roles: {sorted(missing)!r}."
                )
        return self

    @model_validator(mode='after')
    def validate_premium_app_requires_target_filters_when_shc_and_standalone_sh(self) -> 'SplunkConfig':
        """When there is both an SHC and at least one standalone search head (or more than one standalone SH),
        premium apps must specify targeting via shc_whitelist or hosts_whitelist (blacklists are not allowed on premium apps)."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        standalone_sh_count = 0
        has_shc = False
        for host in self.splunk_hosts:
            if AllowedRole.search_head not in host.roles:
                continue
            if host.shcluster:
                has_shc = True
            else:
                if host.name:
                    standalone_sh_count += 1
                elif host.list:
                    standalone_sh_count += len(host.list)
                elif host.iter:
                    parts = host.iter.numbers.split('..')
                    start, end = int(parts[0]), int(parts[1])
                    standalone_sh_count += (end - start + 1)

        ambiguous = standalone_sh_count > 1 or (has_shc and standalone_sh_count >= 1)
        if not ambiguous:
            return self

        for i, app in enumerate(dep.apps):
            if not app.get("premium_app"):
                continue
            has_filter = (
                (app.get("shc_whitelist") and len(app.get("shc_whitelist", [])) > 0)
                or (app.get("hosts_whitelist") and len(app.get("hosts_whitelist", [])) > 0)
            )
            if not has_filter:
                name = app.get("name", "?")
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): premium app must specify targeting when "
                    "there is more than one standalone search head, or both a Search Head Cluster and standalone search heads. "
                    "Set one of: shc_whitelist (e.g. ['shc1']), or hosts_whitelist (no blacklists allowed on premium apps)."
                )
        return self

    @model_validator(mode='after')
    def validate_premium_app_only_hosts_and_shc_filters(self) -> 'SplunkConfig':
        """Premium apps may only use hosts_whitelist OR shc_whitelist (not both). No blacklists, no idxc_*/sc_*."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        for i, app in enumerate(dep.apps):
            if not app.get("premium_app"):
                continue
            name = app.get("name", "?")
            # Not both: premium apps may use hosts_whitelist OR shc_whitelist, not both
            hw = app.get("hosts_whitelist") or []
            sw = app.get("shc_whitelist") or []
            if isinstance(hw, list) and isinstance(sw, list):
                has_hw = any(isinstance(v, str) and v.strip() for v in hw)
                has_sw = any(isinstance(v, str) and v.strip() for v in sw)
                if has_hw and has_sw:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): premium apps may use "
                        "hosts_whitelist OR shc_whitelist, not both. Set only one."
                    )
            # Only hosts_whitelist and shc_whitelist allowed; no blacklists, no idxc_*, no sc_*
            for key in ("hosts_blacklist", "shc_blacklist", "idxc_whitelist", "idxc_blacklist", "sc_whitelist", "sc_blacklist"):
                val = app.get(key)
                if not val or not isinstance(val, list):
                    continue
                if any(isinstance(v, str) and v.strip() for v in val):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): premium apps may only use "
                        "hosts_whitelist and shc_whitelist (no blacklists). "
                        f"'{key}' is not allowed on premium apps."
                    )
        return self

    @model_validator(mode='after')
    def validate_itsi_search_heads_not_both_shc_and_standalone(self) -> 'SplunkConfig':
        """ITSI must target either SHC search heads or standalone search heads, not both.
        If the effective list of search heads to deploy to contains both SHC members and standalone SHs, fail."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        def expand_host_names(host: 'SplunkHost') -> set:
            names: set = set()
            if host.name:
                names.add(host.name)
            elif host.list:
                for h in host.list:
                    names.add(h)
            elif host.iter:
                parts = host.iter.numbers.split('..')
                start, end = int(parts[0]), int(parts[1])
                width = len(parts[1])
                prefix = host.iter.prefix or ""
                postfix = host.iter.postfix or ""
                for n in range(start, end + 1):
                    names.add(prefix + str(n).zfill(width) + postfix)
            return names

        sh_names_all: set = set()
        sh_names_shc: set = set()
        sh_names_standalone: set = set()
        shc_name_to_hosts: Dict[str, set] = {}
        for host in self.splunk_hosts:
            if AllowedRole.search_head not in host.roles:
                continue
            names = expand_host_names(host)
            sh_names_all.update(names)
            if host.shcluster and isinstance(host.shcluster, str) and host.shcluster.strip():
                sc = host.shcluster.strip()
                sh_names_shc.update(names)
                shc_name_to_hosts.setdefault(sc, set()).update(names)
            else:
                sh_names_standalone.update(names)

        if not sh_names_all:
            return self

        for i, app in enumerate(dep.apps):
            if not (app.get("premium_app") and isinstance(app.get("premium_app"), str) and (app.get("premium_app") or "").strip().lower() == "itsi"):
                continue
            name = app.get("name", "?")
            effective_sh: set = set()
            shc_w = [v.strip() for v in (app.get("shc_whitelist") or []) if isinstance(v, str) and v.strip()]
            hw = [v.strip() for v in (app.get("hosts_whitelist") or []) if isinstance(v, str) and v.strip()]
            if shc_w:
                for sc in shc_w:
                    effective_sh.update(shc_name_to_hosts.get(sc, set()))
            elif hw:
                effective_sh = set(hw) & sh_names_all
            else:
                effective_sh = set(sh_names_all)
            if not effective_sh:
                continue
            has_shc = bool(effective_sh & sh_names_shc)
            has_standalone = bool(effective_sh & sh_names_standalone)
            if has_shc and has_standalone:
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): ITSI must target either a Search Head Cluster (SHC) or standalone search heads, not both. "
                    "The effective list of search heads to deploy to contains both SHC members and standalone search heads. "
                    "Use shc_whitelist to target only SHC(s), or hosts_whitelist to target only standalone search head host(s)."
                )
        return self


# =============================================================================
# Validation helper function
# =============================================================================

class ConfigValidationError(Exception):
    """Custom exception for configuration validation errors."""
    
    def __init__(self, errors: List[Dict[str, Any]]):
        self.errors = errors
        super().__init__(self._format_errors())
    
    def _format_errors(self) -> str:
        """Format validation errors into readable message."""
        lines = ["Configuration validation failed:"]
        for error in self.errors:
            loc = " -> ".join(str(l) for l in error.get('loc', []))
            msg = error.get('msg', 'Unknown error')
            lines.append(f"  - {loc}: {msg}")
        return "\n".join(lines)


def validate_config(config_data: Dict[str, Any]) -> SplunkConfig:
    """
    Validate a configuration dictionary against the schema.

    Args:
        config_data: Dictionary loaded from splunk_config.yml (after secret
            resolution by the inventory plugin).

    Returns:
        Validated SplunkConfig model instance

    Raises:
        ConfigValidationError: If validation fails, with detailed error messages
    """
    from pydantic import ValidationError

    try:
        return SplunkConfig.model_validate(config_data)
    except ValidationError as e:
        raise ConfigValidationError(e.errors())


def validate_config_file(file_path: str) -> SplunkConfig:
    """
    Validate a configuration file.
    
    Args:
        file_path: Path to splunk_config.yml file
        
    Returns:
        Validated SplunkConfig model instance
        
    Raises:
        ConfigValidationError: If validation fails
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    import yaml
    
    with open(file_path, 'r') as f:
        config_data = yaml.safe_load(f)
    
    return validate_config(config_data)
