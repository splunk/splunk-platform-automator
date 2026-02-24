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
            target_roles = app.get("target_roles")
            premium_app = app.get("premium_app")
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
            if premium_app is not None:
                if not isinstance(premium_app, str) or not premium_app.strip():
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'premium_app' must be a non-empty string when set"
                    )
                if premium_app.strip().lower() not in ALLOWED_PREMIUM_APPS:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'premium_app' must be one of {ALLOWED_PREMIUM_APPS}, got {premium_app!r}"
                    )
                # app_sh_name / app_shc_name (premium app search head targeting): only one allowed; non-empty string when set
                app_sh_name = app.get("app_sh_name")
                app_shc_name = app.get("app_shc_name")
                if app_sh_name is not None and app_shc_name is not None:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): use only one of 'app_sh_name' or 'app_shc_name' for premium app targeting, not both"
                    )
                if app_sh_name is not None and (not isinstance(app_sh_name, str) or not app_sh_name.strip()):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'app_sh_name' must be a non-empty string (standalone search head host name)"
                    )
                if app_shc_name is not None and (not isinstance(app_shc_name, str) or not app_shc_name.strip()):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'app_shc_name' must be a non-empty string (search head cluster name)"
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
            # Validate customizations structure if present
            customizations = app.get("customizations")
            if customizations is not None:
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
                extra_vars = customizations.get("extra_vars")
                if extra_vars is not None and not isinstance(extra_vars, dict):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.extra_vars must be a dictionary"
                    )

        # Duplicate check: same (name, deployment target) = same target hosts and directory → flag. Customizations do not change destination.
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
            if premium_app and isinstance(premium_app, str) and premium_app.strip():
                app_sh_name = app.get("app_sh_name")
                app_shc_name = app.get("app_shc_name")
                deploy_key = ("premium", premium_app.strip().lower(), app_sh_name if app_sh_name else app_shc_name if app_shc_name else "default")
            else:
                target_roles = app.get("target_roles")
                roles_tuple = tuple(sorted(target_roles)) if isinstance(target_roles, list) else ()
                deploy_key = (deployment_target, roles_tuple)
            key = (name, deploy_key)
            if key in seen:
                raise ValueError(
                    f"Duplicate app deployment: app {name!r} is defined more than once for the same target (apps[{seen[key]}] and apps[{i}]). "
                    "Same app name with the same target_roles (and deployment_target) deploys to the same hosts and directory; "
                    "only one definition per destination is allowed. Use different target_roles for different role sets."
                )
            seen[key] = i

        # Duplicate check for deployment-server–distributed apps: same app name may not appear twice when both are
        # managed by the same deployment server (target_roles set, deployment_target != 'direct', not premium).
        # target_roles does not distinguish deployment destination here because both entries are managed by the same DS.
        seen_ds_name: Dict[str, int] = {}
        for i, app in enumerate(self.apps):
            name = app.get("name")
            if name is None or not isinstance(name, str):
                continue
            name = name.strip()
            premium_app = app.get("premium_app")
            if premium_app and isinstance(premium_app, str) and premium_app.strip():
                continue
            deployment_target = app.get("deployment_target", "auto")
            if isinstance(deployment_target, str):
                deployment_target = deployment_target.strip().lower() or "auto"
            else:
                deployment_target = "auto"
            if deployment_target == "direct":
                continue
            target_roles = app.get("target_roles")
            if not isinstance(target_roles, list) or len(target_roles) == 0:
                continue
            if name in seen_ds_name:
                raise ValueError(
                    f"Duplicate app deployment: app {name!r} is defined more than once for deployment server distribution "
                    f"(apps[{seen_ds_name[name]}] and apps[{i}]). Apps managed by the same deployment server must have unique names; "
                    "target_roles do not distinguish destination when both are managed by the same DS."
                )
            seen_ds_name[name] = i
        return self

    @model_validator(mode='after')
    def validate_splunk_app_deployment_direct_vars(self) -> 'SplunkAppDeploymentConfig':
        """Validate top-level splunk_app_deployment keys (target_download, cache_downloads, etc.) when present."""
        # Booleans
        for key in ("target_download", "cache_downloads", "backup_apps_before_update", "restart_after_deployment"):
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
    def validate_no_direct_deploy_to_shc_members(self) -> 'SplunkConfig':
        """Fail if any app is configured for direct deployment to search_head while SHC members exist.

        Apps must not use deployment_target: direct with target_roles including search_head when
        there are search heads in a Search Head Cluster; SHC members receive apps via the Deployer.
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

        # Find apps with deployment_target: direct and search_head in target_roles
        apps_direct_to_shc: List[Dict[str, Any]] = []
        for app in dep.apps:
            target_roles = app.get("target_roles") or []
            if not isinstance(target_roles, list):
                continue
            if app.get("deployment_target") != "direct":
                continue
            if "search_head" in target_roles:
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
    def validate_premium_app_requires_sh_target_when_multiple_sh(self) -> 'SplunkConfig':
        """When there is more than one standalone search head, or both an SHC and standalone SHs, premium apps must set app_sh_name or app_shc_name."""
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

        # Ambiguous: more than one standalone SH, or both SHC and at least one standalone SH
        ambiguous = standalone_sh_count > 1 or (has_shc and standalone_sh_count >= 1)
        if not ambiguous:
            return self

        for i, app in enumerate(dep.apps):
            if not app.get("premium_app"):
                continue
            app_sh_name = app.get("app_sh_name")
            app_shc_name = app.get("app_shc_name")
            has_sh_set = isinstance(app_sh_name, str) and app_sh_name.strip()
            has_shc_name_set = isinstance(app_shc_name, str) and app_shc_name.strip()
            if not has_sh_set and not has_shc_name_set:
                name = app.get("name", "?")
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): premium app must have 'app_sh_name' or 'app_shc_name' when "
                    "there is more than one standalone search head, or both a Search Head Cluster and standalone search heads. "
                    "Set app_sh_name to a standalone search head host name, or app_shc_name to the SHC name."
                )
        return self

    @model_validator(mode='after')
    def validate_app_sh_name_app_shc_name_values(self) -> 'SplunkConfig':
        """For premium apps: app_sh_name must be a standalone search head; app_shc_name must be a defined SHC name."""
        dep = self.splunk_app_deployment
        if not dep or not dep.apps:
            return self

        # Allowed SHC names from splunk_shclusters
        shc_names: set = set()
        if self.splunk_shclusters:
            for shc in self.splunk_shclusters:
                shc_names.add(shc.shc_name)

        # Standalone search head host names (search_head role, no shcluster); from name or list only (not iter)
        standalone_sh_names: set = set()
        for host in self.splunk_hosts:
            if AllowedRole.search_head not in host.roles or host.shcluster:
                continue
            if host.name:
                standalone_sh_names.add(host.name)
            elif host.list:
                for h in host.list:
                    standalone_sh_names.add(h)

        for i, app in enumerate(dep.apps):
            if not app.get("premium_app"):
                continue
            name = app.get("name", "?")
            app_sh_name = app.get("app_sh_name")
            app_shc_name = app.get("app_shc_name")
            if app_shc_name is not None:
                if shc_names and app_shc_name not in shc_names:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'app_shc_name' must be one of the defined search head cluster names "
                        f"from splunk_shclusters. Allowed: {sorted(shc_names)!r}, got {app_shc_name!r}"
                    )
            if app_sh_name is not None:
                if standalone_sh_names and app_sh_name not in standalone_sh_names:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'app_sh_name' must be a standalone search head host name "
                        f"(search_head role without shcluster). Allowed: {sorted(standalone_sh_names)!r}, got {app_sh_name!r}"
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
        config_data: Dictionary loaded from splunk_config.yml
        
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
