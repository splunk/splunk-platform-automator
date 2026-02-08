"""
Pydantic schema models for Splunk Platform Automator configuration validation.

This module provides comprehensive validation for splunk_config.yml files,
ensuring configurations are valid before Ansible inventory processing begins.
"""

from __future__ import annotations

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


class SplunkAppDeploymentConfig(BaseModel):
    """Splunk app deployment configuration (Splunkbase and local apps)."""
    model_config = ConfigDict(extra='allow')
    
    splunkbase_username: Optional[str] = None
    splunkbase_password: Optional[str] = None
    local_app_repo_path: Optional[str] = None
    apps: Optional[List[Dict[str, Any]]] = None
    host_specific_apps: Optional[List[Dict[str, Any]]] = None


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
