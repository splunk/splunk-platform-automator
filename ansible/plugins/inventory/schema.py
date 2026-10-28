"""
Pydantic schema models for Splunk Platform Automator configuration validation.

This module provides comprehensive validation for splunk_config.yml files,
ensuring configurations are valid before Ansible inventory processing begins.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


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

# Version: "latest" or dotted numeric (e.g. 1.0, 4.21.1, 10.1.0)
VERSION_NUMBER_PATTERN = re.compile(r"^\d+(\.\d+)*$")
SPLUNK_VERSION_PATTERN = r"^(latest|\d+(\.\d+)*)$"
DEPRECATED_AWS = "The aws block is deprecated and has been replaced by terraform.aws."
SPLUNK_ARCHITECTURE_PATTERN = r"^(amd64|x86_64|arm64)$"
SPLUNK_SITE_PATTERN = r"^site\d+$"
# Splunk site factor tokens: origin:N, total:N, optional siteN:N
IDXC_SITE_FACTOR_PATTERN = (
    r"^(origin:\d+|total:\d+|site\d+:\d+)(, ?(origin:\d+|total:\d+|site\d+:\d+))*$"
)
IPV4_PATTERN = (
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$"
)
AMI_ID_PATTERN = r"^ami-[0-9a-fA-F]+$"


# =============================================================================
# Sub-models for nested configuration sections
# =============================================================================

class GeneralConfig(BaseModel):
    """General settings section."""
    model_config = ConfigDict(extra='forbid')
    
    url_locale: Optional[str] = Field(
        None,
        pattern=r'^[a-z]{2}[_-][A-Z]{2}$',
        description="Language segment in the Splunk Web links on the lab index page, such as en-GB. Default en-GB. Omit the key to keep that.",
    )


class VirtualBoxSyncedFolder(BaseModel):
    """VirtualBox synced folder configuration."""
    source: str = Field(..., description="Path on the Ansible controller to mount into the guest. Required.")
    target: str = Field(..., description="Path inside the guest where the controller folder is mounted. Required.")


class VirtualBoxConfig(BaseModel):
    """VirtualBox virtualization settings."""
    model_config = ConfigDict(extra='allow')
    
    start_ip: Optional[str] = Field(
        None,
        pattern=IPV4_PATTERN,
        description="First guest IPv4 on the VirtualBox host-only network. Later guests increment from it. Default 192.168.60.100. Omit the key to keep that.",
    )
    box: Optional[str] = Field(None, description="Vagrant box name. Default almalinux/8. Omit the key to keep that.")
    memory: Optional[int] = Field(None, ge=256, description="Guest memory in MB. Minimum 256. Default 512. Omit the key to keep that.")
    cpus: Optional[int] = Field(None, ge=1, description="Guest virtual CPU count. Minimum 1. Default 1. Omit the key to keep that.")
    install_vbox_additions: Optional[bool] = Field(
        None,
        description="When true, install VirtualBox guest additions. Default false. Omit the key to keep that.",
    )
    synced_folder: Optional[List[VirtualBoxSyncedFolder]] = Field(
        None,
        description="Folders mounted from the Ansible controller into the guest. Holds no value itself.",
    )


class AwsTerraformConfig(BaseModel):
    """AWS configuration for Terraform provisioning."""
    model_config = ConfigDict(extra='forbid')
    
    region: Optional[str] = Field(None, description="AWS region Terraform uses. Default eu-central-1. Omit the key to keep that.")
    ami_id: Optional[str] = Field(
        None,
        pattern=AMI_ID_PATTERN,
        description=(
            "EC2 AMI id. Default is the id shipped in defaults/aws.yml. Omit the key to keep that. "
            "spa config set writes an end-of-line comment with the image name and description when AWS can describe the id. "
            "Find a current Red Hat image with spa aws --region eu-central-1 --latest-ami --os rhel, "
            "or list matches with spa aws amis list --region eu-central-1 --os rhel. "
            "ubuntu, amazon_linux, and debian use the same --os form."
        ),
    )
    key_name: Optional[str] = Field(None, description="EC2 key pair name. Default aws_key. Omit the key to keep that.")
    ssh_private_key_file: Optional[str] = Field(
        None,
        description="Path on the Ansible controller to the private key for key_name. Default ~/.ssh/aws_key.pem. Omit the key to keep that.",
    )
    security_group_names: Optional[List[str]] = Field(
        None,
        description="EC2 security group names. Default is Splunk_Basic. Omit the key to keep that.",
    )
    instance_type: Optional[str] = Field(None, description="EC2 instance type. Default t2.micro. Omit the key to keep that.")
    root_volume_size: Optional[int] = Field(
        None,
        ge=8,
        description="Root EBS size in GB. Minimum 8. No default. Omit the key to keep the AMI disk size.",
    )
    root_volume_type: Optional[str] = Field(
        None,
        description="EBS volume type. AWS defines the names. No default. Omit the key to keep the AMI volume type.",
    )
    ssh_username: Optional[str] = Field(
        None,
        description="SSH login user for the AMI. Default ec2-user. Omit the key to keep that. Use ubuntu or admin when the AMI requires it.",
    )
    tags: Optional[Dict[str, str]] = Field(
        None,
        description="Map of AWS tag name to tag value. No default. Omit the key to set no tags.",
    )
    subnet_id: Optional[str] = Field(
        None,
        description="VPC subnet id. No default. Omit the key to use the default subnet in the region.",
    )


class TerraformConfig(BaseModel):
    """Terraform provisioning settings."""
    model_config = ConfigDict(extra='allow')
    
    aws: Optional[AwsTerraformConfig] = Field(
        None,
        description="EC2 settings Terraform applies. Holds no value itself.",
    )


class OsConfig(BaseModel):
    """Operating system configuration."""
    model_config = ConfigDict(extra='allow')
    
    remote_command: Optional[str] = Field(
        None,
        description="Shell command run on the guest before Ansible bootstraps, for an image that lacks Python or acl. No default. Omit the key to skip it.",
    )
    time_zone: Optional[str] = Field(
        None,
        description="IANA time zone set on the guest. Default is the Ansible controller's zone. Omit the key to keep that.",
    )
    enable_time_sync_cron: Optional[bool] = Field(
        None,
        description="When true, install a cron job that keeps the guest clock in sync. Default false. Omit the key to keep that. VirtualBox always turns this on.",
    )
    packages: Optional[List[str]] = Field(
        None,
        description="Extra packages installed with the guest package manager before Splunk. Default none. Omit the key to keep that.",
    )
    ssh_keys: Optional[List[str]] = Field(
        None,
        description="Public key files on the Ansible controller, appended to the login user's authorized_keys. Default none. Omit the key to keep that.",
    )
    set_hostname: Optional[bool] = Field(
        None,
        description="When true, set the guest hostname to its inventory name. Default false. Omit the key to keep that.",
    )
    disable_selinux: Optional[bool] = Field(
        None,
        description="When true, disable SELinux on RHEL and Amazon Linux. Skipped on universal forwarders. Default true. Omit the key to keep that.",
    )
    disable_apparmor: Optional[bool] = Field(
        None,
        description="When true, disable AppArmor on Ubuntu and Debian. Default true. Omit the key to keep that.",
    )
    update_hosts_file: Optional[bool] = Field(
        None,
        description="When true, write every lab host into /etc/hosts. Default true. Omit the key to keep that.",
    )
    splunk_group_create: Optional[bool] = Field(
        None,
        description="When true, create the Splunk OS group. Default true. Omit the key to keep that.",
    )
    splunk_user_create: Optional[bool] = Field(
        None,
        description="When true, create the Splunk OS user. Default true. Omit the key to keep that.",
    )


class SplunkDownloadConfig(BaseModel):
    """Splunk download settings."""
    splunk: Optional[bool] = Field(
        None,
        description="When true, the host downloads the Splunk Enterprise tarball. When false, the controller uploads the archive from Software. Default false. Omit the key to keep that.",
    )
    splunkforwarder: Optional[bool] = Field(
        None,
        description="When true, the host downloads the universal forwarder tarball. When false, the controller uploads the archive from Software. Default false. Omit the key to keep that.",
    )


class SplunkSslEndpointConfig(BaseModel):
    """SSL endpoint configuration."""
    model_config = ConfigDict(extra='allow')
    
    enable: Optional[bool] = Field(
        None,
        description="When true, turn on TLS for this endpoint. Default false. Omit the key to keep that.",
    )
    own_certs: Optional[bool] = Field(
        None,
        description="When true, use certificate files you provide for this endpoint instead of Splunk's generated certs. Default false. Omit the key to keep that.",
    )
    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Extra conf keys for this endpoint. Default points at Splunk's generated certificate paths. Omit the key to keep that.",
    )


class SplunkSslConfig(BaseModel):
    """Splunk SSL settings."""
    web: Optional[SplunkSslEndpointConfig] = Field(None, description="TLS settings for this endpoint. Holds no value itself.")
    inputs: Optional[SplunkSslEndpointConfig] = Field(None, description="TLS settings for this endpoint. Holds no value itself.")
    outputs: Optional[SplunkSslEndpointConfig] = Field(None, description="TLS settings for this endpoint. Holds no value itself.")


class SplunkSecretShareConfig(BaseModel):
    """Splunk secret sharing configuration."""
    splunk: Optional[bool] = Field(
        None,
        description="When true, reuse one splunk.secret across Splunk Enterprise hosts. Default false. Omit the key to keep that.",
    )
    splunkforwarder: Optional[bool] = Field(
        None,
        description="When true, reuse one splunk.secret across universal forwarders. Default false. Omit the key to keep that.",
    )
    equal: Optional[bool] = Field(
        None,
        description="When true, use the same splunk.secret for Enterprise and universal forwarders. Default false. Omit the key to keep that.",
    )


class SplunkVolumeConfig(BaseModel):
    """Splunk indexer volume configuration."""
    model_config = ConfigDict(extra='allow')
    
    path: Optional[str] = Field(
        None,
        description="Filesystem path or s3:// URI for this named volume. No default. Omit the key only when the volume name is enough.",
    )
    maxVolumeDataSizeMB: Optional[int] = Field(
        None,
        description="Maximum size of this volume in MB. No default. Omit the key to derive it from free space when a free-space reserve is set.",
    )
    storageType: Optional[str] = Field(
        None,
        description="local or remote. Default local. Omit the key to keep that. Set remote for a SmartStore volume.",
    )


class SplunkVolumeDefaultsConfig(BaseModel):
    """Splunk volume defaults configuration."""
    model_config = ConfigDict(extra='allow')
    
    VolumeDataSize_Free_MB: Optional[int] = Field(
        None,
        description="Megabytes left free when calculating a volume maximum size. No default. Omit the key to skip that calculation.",
    )
    homePath: Optional[str] = Field(
        None,
        description="Volume name used as the index home path. No default. Omit the key when you are not using named volumes.",
    )
    coldPath: Optional[str] = Field(
        None,
        description="Volume name used as the index cold path. No default. Omit the key when you are not using named volumes.",
    )
    remotePath: Optional[str] = Field(
        None,
        description="Volume name used as the SmartStore remote path. No default. Omit the key when indexes stay on local disk.",
    )


class SplunkDefaultsConfig(BaseModel):
    """Splunk default settings applied to all hosts."""
    model_config = ConfigDict(extra='allow')
    
    splunk_env_name: Optional[str] = Field(
        None,
        description="Short name for this Splunk environment. Default splk. Omit the key to keep that.",
    )
    splunk_version: Optional[str] = Field(
        None,
        pattern=SPLUNK_VERSION_PATTERN,
        description="Installer tarball version under Software: latest or a dotted version. Default latest. Omit the key to keep that.",
    )
    splunk_architecture: Optional[str] = Field(
        None,
        pattern=SPLUNK_ARCHITECTURE_PATTERN,
        description="CPU suffix of the Splunk tarball: amd64, x86_64, or arm64. This is not the machine running spa. Default amd64. Omit the key to keep that.",
    )
    splunk_user: Optional[str] = Field(
        None,
        description="OS account that runs Splunk. Default splunk. Omit the key to keep that.",
    )
    splunk_group: Optional[str] = Field(
        None,
        description="Primary OS group for the Splunk account. Default splunk. Omit the key to keep that.",
    )
    splunk_fips: Optional[bool] = Field(
        None,
        description="When true, install Splunk in FIPS mode. Default false. Omit the key to keep that.",
    )
    splunk_download: Optional[SplunkDownloadConfig] = Field(
        None,
        description="Whether the host downloads installers or the controller uploads them from Software. Holds no value itself.",
    )
    splunk_admin_password: str = Field(
        ...,
        description="Password for the Splunk admin user. Required. A literal password or an env lookup.",
    )
    splunk_license_file: Optional[Union[str, List[str]]] = Field(
        None,
        description="License file name, or a list of names, in Software. Copied onto a license_manager host. No default. Omit the key when hosts use an existing license server.",
    )
    splunk_license_server: Optional[str] = Field(
        None,
        description="IP or DNS name of an existing license manager. No default. Omit the key when this lab hosts the license manager.",
    )
    splunk_set_servername: Optional[bool] = Field(
        None,
        description="When true, set serverName to the inventory hostname. Default false. Omit the key to keep that.",
    )
    splunk_set_default_hostname: Optional[bool] = Field(
        None,
        description="When true, set default-hostname to the inventory hostname. Default false. Omit the key to keep that.",
    )
    splunk_loginpage_print_hostname: Optional[bool] = Field(
        None,
        description="When true, print the hostname on the Splunk login page. Default true. Omit the key to keep that.",
    )
    splunk_loginpage_print_userpw: Optional[bool] = Field(
        None,
        description="When true, print the admin user and password on the Splunk login page. Default true. Omit the key to keep that.",
    )
    splunk_loginpage_print_roles: Optional[bool] = Field(
        None,
        description="When true, print the host's Splunk roles on the login page. Default true. Omit the key to keep that.",
    )
    splunk_use_policykit: Optional[bool] = Field(
        None,
        description="When true, require polkit so Ansible can become root. Default true. Omit the key to keep that.",
    )
    splunk_kv_store_engine_wiredtiger: Optional[bool] = Field(
        None,
        description="When true, use WiredTiger for KV Store. Default true. Omit the key to keep that.",
    )
    splunk_conf: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Extra Splunk conf stanzas: file name, then stanza, then key. No default. Omit the key to add none.",
    )
    splunk_indexes: Optional[Dict[str, Any]] = Field(
        None,
        description="Index definitions as a map of index name to settings. Default is a test events index and a test_metrics metric index. Omit the key to keep that.",
    )
    splunk_indexes_default_paths: Optional[bool] = Field(
        None,
        description="When true, give indexes the usual hot and cold paths. Default true. Omit the key to keep that.",
    )
    # A volume with no properties (e.g. 'hot:') falls back to the default path at deploy time.
    splunk_indexer_volumes: Optional[Dict[str, Optional[SplunkVolumeConfig]]] = Field(
        None,
        description="Named indexer storage volumes. Holds no value itself.",
    )
    splunk_volume_defaults: Optional[SplunkVolumeDefaultsConfig] = Field(
        None,
        description="Path and size defaults applied to indexer volumes. Holds no value itself.",
    )
    splunk_ssl: Optional[SplunkSslConfig] = Field(
        None,
        description="TLS settings for Splunk endpoints. Holds no value itself.",
    )
    splunk_secret_share: Optional[SplunkSecretShareConfig] = Field(
        None,
        description="Whether hosts reuse one secret file. Holds no value itself.",
    )


class SplunkDirsConfig(BaseModel):
    """Splunk directory paths."""
    model_config = ConfigDict(extra='allow')
    
    splunk_baseconfig_dir: Optional[str] = Field(
        None,
        description="Directory of baseconfig apps, resolved next to the lab. Default ../Software. Omit the key to keep that.",
    )
    splunk_software_dir: Optional[str] = Field(
        None,
        description="Directory of Splunk tarballs and license files. Default ../Software. Omit the key to keep that.",
    )


class SplunkAppsConfig(BaseModel):
    """Splunk apps configuration (legacy baseconfig apps)."""
    model_config = ConfigDict(extra='allow')
    
    splunk_save_baseconfig_apps_dir: Optional[str] = Field(
        None,
        description="Lab folder that receives saved baseconfig apps. Default saved_base_config_apps. Omit the key to keep that.",
    )
    splunk_save_baseconfig_apps: Optional[bool] = Field(
        None,
        description="When true, copy rendered baseconfig apps into the lab. Default false. Omit the key to keep that.",
    )
    splunk_save_serverclass: Optional[bool] = Field(
        None,
        description="When true, also save the deployment-server serverclass. Default false. Omit the key to keep that.",
    )


ALLOWED_APP_SOURCES = ("local", "splunkbase")
ALLOWED_DEPLOYMENT_TARGETS = ("direct", "auto")
ALLOWED_APP_STATES = ("installed", "absent")
ALLOWED_UPDATE_MODES = ("clean", "merge")
ALLOWED_PREMIUM_APPS = ("itsi",)  # Premium apps: target_roles not required; deployment is role-based
CONTENT_LIBRARY_APP_ID = 5391  # Splunk Content Library for ITSI (Splunkbase)
CONTENT_LIBRARY_FOLDER = "DA-ITSI-ContentLibrary"  # On-disk folder of the library, also its name for a local archive


def _app_id_value(app: Dict[str, Any]) -> Optional[int]:
    """Return app_id as an int when it is an integer or digit string, else None."""
    raw = app.get("app_id")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _is_content_library_entry(app: Dict[str, Any]) -> bool:
    """Splunkbase app_id 5391 (any name), or a local entry named DA-ITSI-ContentLibrary."""
    if app.get("source", "splunkbase") == "splunkbase":
        return _app_id_value(app) == CONTENT_LIBRARY_APP_ID
    return app.get("source") == "local" and app.get("name") == CONTENT_LIBRARY_FOLDER


CONTENT_PACK_ITEM_KEYS = ("name", "content_pack_install", "content_pack_api", "customizations")
# Value type per content_pack_api key, as the apps_itsi_content_pack role reads them.
CONTENT_PACK_API_TYPES = {
    "install_all": bool,
    "saved_search_action": str,
    "backfill": bool,
    "resolution": str,
    "enabled": bool,
    "prefix": str,
}

CONTENT_PACK_CUSTOMIZATION_KEYS = ("run_playbook_after_restart", "force_run_playbook_after_restart", "extra_vars")

CONTENT_LIBRARY_ENTRY_KEYS = (
    "name",
    "source",
    "app_id",
    "path",
    "itsi_content_pack",
    "version",
    "state",
    "install_all_apps",
    "content_pack_apps",
    "update_mode",
)


def _validate_content_library_entry(app: Dict[str, Any], i: int, name: str) -> None:
    """Closed key set for the Content Library entry. Pack-level rules are added separately."""
    unknown = sorted(str(key) for key in app if key not in CONTENT_LIBRARY_ENTRY_KEYS)
    if unknown:
        raise ValueError(
            f"splunk_app_deployment.apps[{i}] (name={name!r}): the Content Library entry does not allow {unknown}. "
            f"Allowed keys: {list(CONTENT_LIBRARY_ENTRY_KEYS)}"
        )
    if "install_all_apps" in app and not isinstance(app["install_all_apps"], bool):
        raise ValueError(
            f"splunk_app_deployment.apps[{i}] (name={name!r}): install_all_apps must be true or false, "
            f"got {type(app['install_all_apps']).__name__}"
        )
    if app.get("install_all_apps") is True and "content_pack_apps" in app:
        raise ValueError(
            f"splunk_app_deployment.apps[{i}] (name={name!r}): set either content_pack_apps or install_all_apps: true, not both"
        )
    if app.get("source", "splunkbase") == "splunkbase" and "path" in app:
        raise ValueError(
            f"splunk_app_deployment.apps[{i}] (name={name!r}): 'path' is only for a local Content Library archive; "
            "a splunkbase library (app_id 5391) downloads from Splunkbase and must not set path"
        )
    if app.get("source") == "local":
        if "app_id" in app:
            raise ValueError(
                f"splunk_app_deployment.apps[{i}] (name={name!r}): a local Content Library archive does not take app_id; "
                "app_id is for Splunkbase downloads"
            )
        if "path" in app and not (isinstance(app["path"], str) and app["path"].strip()):
            raise ValueError(
                f"splunk_app_deployment.apps[{i}] (name={name!r}): 'path' must be a non-empty string naming the local archive"
            )
    packs = app.get("content_pack_apps")
    if isinstance(packs, list):
        seen_pack_names: set = set()
        for j, item in enumerate(packs):
            if not isinstance(item, dict):
                continue  # the generic content-pack checks report non-object items
            if "content_pack_install" in item and not isinstance(item["content_pack_install"], bool):
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].content_pack_install must be a bool, "
                    f"got {type(item['content_pack_install']).__name__}"
                )
            pack_name = item.get("name")
            if isinstance(pack_name, str):
                pack_key = pack_name.strip()
                if pack_key in seen_pack_names:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}] duplicate name {pack_name!r}; "
                        "each pack may appear once"
                    )
                seen_pack_names.add(pack_key)
            unknown_item = sorted(str(key) for key in item if key not in CONTENT_PACK_ITEM_KEYS)
            if unknown_item:
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}] does not allow {unknown_item}. "
                    f"Allowed keys: {list(CONTENT_PACK_ITEM_KEYS)}"
                )
            api_opts = item.get("content_pack_api")
            if api_opts is not None:
                if not isinstance(api_opts, dict):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].content_pack_api must be a dictionary"
                    )
                unknown_api = sorted(str(key) for key in api_opts if key not in CONTENT_PACK_API_TYPES)
                if unknown_api:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].content_pack_api does not allow "
                        f"{unknown_api}. Allowed keys: {list(CONTENT_PACK_API_TYPES)}"
                    )
                for api_key, api_value in api_opts.items():
                    expected = CONTENT_PACK_API_TYPES[api_key]
                    if not isinstance(api_value, expected):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].content_pack_api.{api_key} "
                            f"must be a {expected.__name__}, got {type(api_value).__name__}"
                        )
            cust_opts = item.get("customizations")
            if isinstance(cust_opts, dict):
                unknown_cust = sorted(str(key) for key in cust_opts if key not in CONTENT_PACK_CUSTOMIZATION_KEYS)
                if unknown_cust:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].customizations does not allow "
                        f"{unknown_cust}. Allowed keys: {list(CONTENT_PACK_CUSTOMIZATION_KEYS)}"
                    )
                if "force_run_playbook_after_restart" in cust_opts and not isinstance(
                    cust_opts["force_run_playbook_after_restart"], bool
                ):
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}].customizations."
                        f"force_run_playbook_after_restart must be a bool, got {type(cust_opts['force_run_playbook_after_restart']).__name__}"
                    )
            if isinstance(pack_name, str) and pack_name.strip() == str(app.get("name", "")).strip():
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): content_pack_apps[{j}] repeats the library {app.get('name')!r}. "
                    "The library is the top-level name; list only the additional packs in content_pack_apps"
                )


class SplunkAppDeploymentConfig(BaseModel):
    """Splunk app deployment configuration (Splunkbase and local apps)."""
    model_config = ConfigDict(extra='allow')
    
    splunkbase_username: Optional[str] = Field(
        None,
        description="Splunkbase user for app downloads. No default. Omit the key when every app is local. Use an env lookup when you set it.",
    )
    splunkbase_password: Optional[str] = Field(
        None,
        description="Splunkbase password for app downloads. No default. Omit the key when every app is local. Use an env lookup when you set it.",
    )
    local_app_repo_path: Optional[str] = Field(
        None,
        description="Folder of local apps. Default is the apps directory from spa init. Omit the key to keep that.",
    )
    update_mode: Optional[Literal["clean", "merge"]] = Field(
        None,
        description="merge keeps extra files such as local/; clean deletes the old app first. Default merge. Omit the key to keep that.",
    )
    target_download: Optional[StrictBool] = Field(
        None,
        description="When true, each target downloads the app from Splunkbase. Default false. Omit the key to keep that.",
    )
    cache_downloads: Optional[StrictBool] = Field(
        None,
        description="When true, keep the downloaded archive after it is extracted. Default true. Omit the key to keep that.",
    )
    backup_apps_before_update: Optional[StrictBool] = Field(
        None,
        description="When true, back up the existing app directory before an update. Default false. Omit the key to keep that.",
    )
    deploymentclient_check: StrictBool = Field(
        default=True,
        description=(
            "When true, run splunk btool deploymentclient to see which hosts are deployment clients. "
            "Default true. Omit the key to keep that."
        ),
    )
    apps: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="App entries to install or remove. Each entry is a map of name, source, and either a Splunkbase id or a local path. No default. Omit the key to deploy no apps.",
    )
    host_specific_apps: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Reserved. Not applied by deploy. No default. Omit the key.",
    )

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
            source = app.get("source", "splunkbase")
            if source not in ALLOWED_APP_SOURCES:
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
            if _app_id_value(app) == CONTENT_LIBRARY_APP_ID:
                if app.get("source", "splunkbase") != "splunkbase":
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): app_id {CONTENT_LIBRARY_APP_ID} (Content Library) "
                        f"requires source 'splunkbase'. A local library is named {CONTENT_LIBRARY_FOLDER!r} and uses a path to its archive."
                    )
                if not is_itsi_content_pack:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): app_id {CONTENT_LIBRARY_APP_ID} (Content Library) "
                        "requires itsi_content_pack: true"
                    )
            if app.get("name") == CONTENT_LIBRARY_FOLDER and not (is_itsi_content_pack and _is_content_library_entry(app)):
                raise ValueError(
                    f"splunk_app_deployment.apps[{i}] (name={name!r}): {CONTENT_LIBRARY_FOLDER!r} is reserved for "
                    f"Content Library app_id {CONTENT_LIBRARY_APP_ID} (splunkbase) or a local library archive"
                )
            if is_itsi_content_pack and _is_content_library_entry(app):
                _validate_content_library_entry(app, i, name)
                if not app.get("content_pack_apps") and app.get("install_all_apps") is not True:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): the Content Library requires content_pack_apps "
                        "(a non-empty list) or install_all_apps: true"
                    )
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
            app_update_mode = app.get("update_mode")
            if app_update_mode is not None:
                if not isinstance(app_update_mode, str) or app_update_mode.strip().lower() not in ALLOWED_UPDATE_MODES:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'update_mode' must be one of {ALLOWED_UPDATE_MODES}, got {app_update_mode!r}"
                    )
            # ITSI content pack: top-level name is always the on-disk app folder (library for multi-app, pack for single-app).
            if is_itsi_content_pack:
                if app.get("library_app") is not None:
                    raise ValueError(
                        f"splunk_app_deployment.apps[{i}] (name={name!r}): 'library_app' is not allowed for itsi_content_pack; "
                        "set top-level 'name' to the library app folder (e.g. DA-ITSI-ContentLibrary) and list additional packs in content_pack_apps."
                    )
                cp_apps = app.get("content_pack_apps")
                install_all_apps = app.get("install_all_apps")
                is_cp_single_app = (
                    not install_all_apps
                    and (cp_apps is None or (isinstance(cp_apps, list) and len(cp_apps) == 0))
                )
                if is_cp_single_app:
                    for bad_key in ("content_pack_install", "content_pack_apps", "install_all_apps"):
                        if app.get(bad_key) is not None:
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): '{bad_key}' is not allowed for single-app itsi_content_pack; "
                                "single-app content packs omit content_pack_apps and install_all_apps; top-level 'name' must be the on-disk app folder. "
                                "Optional top-level content_pack_api and customizations are allowed."
                            )
                    api_opts = app.get("content_pack_api")
                    if api_opts is not None and not isinstance(api_opts, dict):
                        raise ValueError(
                            f"splunk_app_deployment.apps[{i}] (name={name!r}): 'content_pack_api' must be a dictionary"
                        )
                    cust = app.get("customizations")
                    if cust is not None:
                        if not isinstance(cust, dict):
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): 'customizations' must be a dictionary"
                            )
                        rpar = cust.get("run_playbook_after_restart")
                        if rpar is not None and (not isinstance(rpar, str) or not rpar.strip()):
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.run_playbook_after_restart must be a non-empty string"
                            )
                        ev = cust.get("extra_vars")
                        if ev is not None and not isinstance(ev, dict):
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): customizations.extra_vars must be a dictionary"
                            )
                else:
                    for bad_key in ("content_pack_install", "content_pack_api", "customizations"):
                        if app.get(bad_key) is not None:
                            raise ValueError(
                                f"splunk_app_deployment.apps[{i}] (name={name!r}): top-level '{bad_key}' is not allowed for itsi_content_pack; "
                                "set these only inside content_pack_apps items"
                            )
                    if not install_all_apps:
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
            # Validate customizations structure if present (skip for itsi_content_pack; validated above)
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
        # update_mode: must be one of ALLOWED_UPDATE_MODES
        um = getattr(self, "update_mode", None)
        if um is not None:
            if not isinstance(um, str) or um.strip().lower() not in ALLOWED_UPDATE_MODES:
                raise ValueError(
                    f"splunk_app_deployment.update_mode must be one of {ALLOWED_UPDATE_MODES}, got {um!r}"
                )
        return self


class SplunkSystemdConfig(BaseModel):
    """Splunk systemd configuration."""
    model_config = ConfigDict(extra='allow')


class SplunkEnvironment(BaseModel):
    """Splunk environment definition."""
    model_config = ConfigDict(extra='allow')
    
    splunk_env_name: str = Field(..., description="Name of this environment inside the config. Required.")
    splunk_version: Optional[str] = Field(
        None,
        pattern=SPLUNK_VERSION_PATTERN,
        description="Installer version for hosts in this environment. Overrides the global version. No default. Omit the key to inherit it.",
    )
    splunk_admin_password: Optional[str] = Field(
        None,
        description="Admin password for hosts in this environment. Overrides the global password. No default. Omit the key to inherit it. Use an env lookup when you set it.",
    )
    splunk_license_file: Optional[str] = Field(
        None,
        description="License file for this environment. Overrides the global license file. No default. Omit the key to inherit it.",
    )
    splunk_indexes: Optional[Dict[str, Any]] = Field(
        None,
        description="Index map for this environment. Overrides the global indexes. No default. Omit the key to inherit them.",
    )


class IdxClusterConfig(BaseModel):
    """Indexer cluster configuration."""
    model_config = ConfigDict(extra='allow')
    
    idxc_name: str = Field(..., description="Indexer cluster name. Hosts select it with idxcluster. Required.")
    idxc_password: Optional[str] = Field(
        None,
        description="Indexer cluster secret. No default. Set it in splunk_config.yml. A literal password or an env lookup.",
    )
    idxc_replication_port: Optional[int] = Field(
        None,
        ge=1,
        le=65535,
        description="Indexer replication port. Default 9887. Omit the key to keep that.",
    )
    idxc_site_rf: Optional[str] = Field(
        None,
        pattern=IDXC_SITE_FACTOR_PATTERN,
        description="Multisite replication factor, such as origin:2, total:3. Default origin:2, total:3. Omit the key to keep that.",
    )
    idxc_site_sf: Optional[str] = Field(
        None,
        pattern=IDXC_SITE_FACTOR_PATTERN,
        description="Multisite search factor, such as origin:2, total:3. Default origin:2, total:3. Omit the key to keep that.",
    )
    idxc_rf: Optional[int] = Field(
        None,
        ge=1,
        description="Single-site replication factor. No default. Omit the key to leave Splunk's built-in factor.",
    )
    idxc_sf: Optional[int] = Field(
        None,
        ge=1,
        description="Single-site search factor. No default. Omit the key to leave Splunk's built-in factor.",
    )
    idxc_discovery_password: Optional[str] = Field(
        None,
        description="Password for indexer discovery. No default. Omit the key to leave discovery unset. Use an env lookup when you set it.",
    )


class ShClusterConfig(BaseModel):
    """Search head cluster configuration."""
    model_config = ConfigDict(extra='allow')
    
    shc_name: str = Field(..., description="Search head cluster name. Hosts select it with shcluster. Required.")
    shc_site: Optional[str] = Field(
        None,
        pattern=SPLUNK_SITE_PATTERN,
        description="Site label for this search head cluster, such as site0. Default site0. Omit the key to keep that.",
    )
    shc_password: Optional[str] = Field(
        None,
        description="Search head cluster secret. No default. Set it in splunk_config.yml. A literal password or an env lookup.",
    )
    shc_replication_port: Optional[int] = Field(
        None,
        ge=1,
        le=65535,
        description="Search head cluster replication port. Default 9887. Omit the key to keep that.",
    )


class HostIteration(BaseModel):
    """Host iteration for generating multiple hosts."""
    prefix: Optional[str] = Field(
        None,
        description="Text placed before each generated number in the hostname. No default. Omit the key to add nothing before the number.",
    )
    numbers: str = Field(
        ...,
        pattern=r'^\d+\.\.\d+$',
        description="Inclusive numeric range such as 1..3. One host is created per number. Required.",
    )
    postfix: Optional[str] = Field(
        None,
        description="Text placed after each generated number in the hostname. No default. Omit the key to add nothing after the number.",
    )


class ExternalConfig(BaseModel):
    """Bring-your-own SSH provider. Holds no settings of its own."""
    model_config = ConfigDict(extra='forbid')


class CustomConfig(BaseModel):
    """Custom/arbitrary settings (for ansible connection vars, etc.)."""
    model_config = ConfigDict(extra='allow')


_PASSWORD_KEYS = (
    "ansible_password",
    "ansible_ssh_pass",
    "ansible_ssh_password",
    "ansible_become_pass",
    "ansible_become_password",
)


def _drop_password_keys(mapping: Dict[str, Any]) -> bool:
    """Remove password keys from this mapping so a validation error cannot echo them."""
    rejected = False
    for key in _PASSWORD_KEYS:
        if key in mapping:
            mapping.pop(key)
            rejected = True
    custom = mapping.get("custom")
    if isinstance(custom, dict):
        rejected = _drop_password_keys(custom) or rejected
    return rejected


def _copy_without_password_keys(mapping: Dict[str, Any]) -> tuple:
    """Return a shallow copy and whether a password key was removed."""
    copied = dict(mapping)
    rejected = _drop_password_keys(copied)
    return copied, rejected


class SplunkHost(BaseModel):
    """Individual Splunk host configuration."""
    model_config = ConfigDict(extra='allow')
    
    # Host identification - exactly one must be specified
    name: Optional[str] = Field(
        None,
        description="Inventory hostname for this one host. No default. Set exactly one of name, list, or iter.",
    )
    list: Optional[List[str]] = Field(
        None,
        description="Hostnames generated from this one entry. No default. Set exactly one of name, list, or iter.",
    )
    iter: Optional[HostIteration] = Field(
        None,
        description="Generated hostnames from a numeric range. Holds no value itself.",
    )
    
    # Required for a managed host. External hosts may omit it.
    roles: Optional[List[AllowedRole]] = Field(
        None,
        description="Splunk roles for this host. Required unless the host is external. No default. Omit the key when an external host has no Splunk role.",
    )
    
    # Optional settings
    splunk_env: Optional[str] = Field(
        None,
        description="Environment name from splunk_environments. No default. Omit the key when the config has one environment.",
    )
    site: Optional[str] = Field(
        None,
        pattern=SPLUNK_SITE_PATTERN,
        description="Multisite label such as site1. Allowed only for indexer, search_head, or cluster_manager. No default. Omit the key for a single-site lab.",
    )
    cname: Optional[str] = Field(
        None,
        description="DNS alias published for this host. No default. Omit the key to publish none.",
    )
    idxcluster: Optional[str] = Field(
        None,
        description="Indexer cluster name. Required when roles includes cluster_manager. No default for other roles. Omit the key when the host is not in an indexer cluster.",
    )
    shcluster: Optional[str] = Field(
        None,
        description="Search head cluster name. Required when roles includes deployer. No default for other roles. Omit the key when the host is not in a search head cluster.",
    )
    ip_addr: Optional[str] = Field(
        None,
        description="Guest IPv4 when you assign it yourself. No default. Omit the key to let the provider assign the address.",
    )

    # Host-level overrides
    splunk_version: Optional[str] = Field(
        None,
        pattern=SPLUNK_VERSION_PATTERN,
        description="Per-host override of splunk_defaults.splunk_version. Installer version for this host only. No default. Omit the key to inherit the global version.",
    )
    splunk_architecture: Optional[str] = Field(
        None,
        pattern=SPLUNK_ARCHITECTURE_PATTERN,
        description="Per-host override of splunk_defaults.splunk_architecture. Tarball CPU suffix for this host only. No default. Omit the key to inherit the global architecture.",
    )
    splunk_admin_password: Optional[str] = Field(
        None,
        description="Per-host override of splunk_defaults.splunk_admin_password. No default. Omit the key to inherit the global password. Use an env lookup when you set it.",
    )
    splunk_license_file: Optional[str] = Field(
        None,
        description="Per-host override of splunk_defaults.splunk_license_file. No default. Omit the key to inherit the global license file.",
    )
    splunk_outputs: Optional[str] = Field(
        None,
        description="Reserved grouping of which indexers receive this host's data. Not applied; forwarders still send to every indexer. No default. Omit the key.",
    )
    splunk_search_peers: Optional[str] = Field(
        None,
        description="Reserved grouping of search peers for this host. Not applied. No default. Omit the key.",
    )
    splunk_conf: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Per-host override of splunk_defaults.splunk_conf. Extra conf stanzas for this host only. No default. Omit the key to inherit the global stanzas.",
    )
    splunk_fips: Optional[bool] = Field(
        None,
        description="Per-host override of splunk_defaults.splunk_fips. When true, install this host in FIPS mode. No default. Omit the key to inherit the global FIPS setting.",
    )
    
    # Nested configs
    os: Optional[OsConfig] = Field(
        None,
        description="Guest OS settings for this host only. Holds no value itself.",
    )
    external: Optional[ExternalConfig] = Field(
        None,
        description="Bring-your-own SSH block for this host only. Holds no value itself. No default. Set this on one host inside a terraform or virtualbox env. Omit the key when a root external: block covers every host.",
    )
    virtualbox: Optional[VirtualBoxConfig] = Field(
        None,
        description="VirtualBox settings for this host only. Holds no value itself.",
    )
    custom: Optional[CustomConfig] = Field(
        None,
        description="Extra Ansible variables for this host only, such as ansible_port. No default. Address, user, and key for an external host belong in inventory/hosts.",
    )
    terraform: Optional[TerraformConfig] = Field(
        None,
        description="Terraform settings for this host only. Holds no value itself.",
    )

    @model_validator(mode='before')
    @classmethod
    def reject_deprecated_aws(cls, data: Any) -> Any:
        if isinstance(data, dict) and "aws" in data:
            raise ValueError(DEPRECATED_AWS)
        return data

    @model_validator(mode='before')
    @classmethod
    def coerce_host_external(cls, data: Any) -> Any:
        """A bare ``external:`` is an empty block. ``provider`` is not a host key."""
        if not isinstance(data, dict):
            return data
        if "provider" in data:
            raise ValueError("use external: on a host. provider is not a host setting.")
        if "external" in data and data.get("external") is None:
            data = dict(data)
            data["external"] = {}
        return data

    @model_validator(mode='before')
    @classmethod
    def strip_rejected_passwords(cls, data: Any) -> Any:
        """Drop password keys so a rejection message cannot echo the value."""
        if not isinstance(data, dict):
            return data
        if _drop_password_keys(data):
            data["__spa_reject_password"] = True
        return data

    @model_validator(mode='after')
    def validate_external_connection(self) -> 'SplunkHost':
        """External hosts use a name. SSH lives in inventory/hosts. Managed hosts still need roles."""
        extra = dict(self.__pydantic_extra__ or {})
        rejected = bool(extra.pop("__spa_reject_password", False))
        if "__spa_reject_password" in (self.__pydantic_extra__ or {}):
            self.__pydantic_extra__.pop("__spa_reject_password", None)
        if self.external is not None:
            if self.name is None:
                raise ValueError("external requires name, not list or iter")
            if rejected:
                raise ValueError("passwords are not accepted")
            if not self.roles:
                self.roles = []
            return self
        if rejected:
            raise ValueError("passwords are not accepted")
        if not self.roles:
            raise ValueError("roles is required")
        return self

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
            roles = self.roles or []
            if not any(role in allowed_site_roles for role in roles):
                allowed_names = ', '.join(r.value for r in allowed_site_roles)
                raise ValueError(f"'site' is only allowed for roles: {allowed_names}")
        return self

    @model_validator(mode='after')
    def validate_cluster_manager_has_idxcluster(self) -> 'SplunkHost':
        """Ensure cluster_manager role has idxcluster specified."""
        if AllowedRole.cluster_manager in (self.roles or []) and not self.idxcluster:
            raise ValueError("'idxcluster' must be specified for hosts with role 'cluster_manager'")
        return self

    @model_validator(mode='after')
    def validate_deployer_has_shcluster(self) -> 'SplunkHost':
        """Ensure deployer role has shcluster specified."""
        if AllowedRole.deployer in (self.roles or []) and not self.shcluster:
            raise ValueError("'shcluster' must be specified for hosts with role 'deployer'")
        return self


# =============================================================================
# Root configuration model
# =============================================================================

def _model_host_count(host: SplunkHost) -> int:
    if host.list:
        return len(host.list)
    if host.iter:
        start, end = (int(part) for part in host.iter.numbers.split(".."))
        return end - start + 1
    return 1


def _host_env(host: SplunkHost) -> str:
    return (host.splunk_env or "").strip()


def _host_label(host: SplunkHost) -> str:
    if host.name:
        return host.name
    if host.list:
        return ", ".join(host.list)
    if host.iter:
        return "%s[%s]%s" % (host.iter.prefix or "", host.iter.numbers, host.iter.postfix or "")
    return "unnamed host"


def _raw_external_only(data: Dict[str, Any]) -> bool:
    """Root ``external:`` with no terraform provider mapping and no virtualbox."""
    if "external" not in data:
        return False
    value = data.get("external")
    if value is not None and not isinstance(value, dict):
        return False
    if "virtualbox" in data:
        return False
    terraform = data.get("terraform") or {}
    if isinstance(terraform, dict) and any(isinstance(item, dict) for item in terraform.values()):
        return False
    return True


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
    plugin: str = Field(
        ...,
        pattern=r'^splunk-platform-automator$',
        description="Name of the Ansible inventory plugin. Required.",
    )
    splunk_hosts: List[SplunkHost] = Field(
        ...,
        min_length=1,
        description="Hosts that spa provision and spa deploy act on. Holds no value itself.",
    )
    
    # Optional sections
    general: Optional[GeneralConfig] = Field(
        None,
        description="Settings for the lab index page written after deploy. Holds no value itself.",
    )
    custom: Optional[CustomConfig] = Field(
        None,
        description="Extra Ansible variables merged into host vars, such as ansible_port. No default. Do not put SSH passwords or private keys here.",
    )
    os: Optional[OsConfig] = Field(
        None,
        description="Guest OS settings applied before Splunk is installed. Holds no value itself.",
    )
    virtualbox: Optional[VirtualBoxConfig] = Field(
        None,
        description="VirtualBox guest size and network for Vagrant. Holds no value itself.",
    )
    external: Optional[ExternalConfig] = Field(
        None,
        description="Bring-your-own SSH provider. Holds no value itself. No default. Set this when no terraform.aws or virtualbox block is present.",
    )
    terraform: Optional[TerraformConfig] = Field(
        None,
        description="Terraform provider settings. Holds no value itself.",
    )
    splunk_defaults: Optional[SplunkDefaultsConfig] = Field(
        None,
        description="Splunk settings applied to every host unless a host overrides them. Holds no value itself.",
    )
    splunk_dirs: Optional[SplunkDirsConfig] = Field(
        None,
        description="Paths to Software and baseconfig apps. Holds no value itself.",
    )
    splunk_apps: Optional[SplunkAppsConfig] = Field(
        None,
        description="Saving rendered baseconfig apps back into the lab. Holds no value itself.",
    )
    splunk_app_deployment: Optional[SplunkAppDeploymentConfig] = Field(
        None,
        description="Install and removal of add-ons during deploy. Holds no value itself.",
    )
    splunk_systemd: Optional[SplunkSystemdConfig] = Field(
        None,
        description="systemd unit limits: service name, then section, then directive. Default limits ship with SPA. Omit the block to keep those.",
    )
    splunk_environments: Optional[List[SplunkEnvironment]] = Field(
        None,
        description="Named Splunk environments inside one config. Holds no value itself.",
    )
    splunk_idxclusters: Optional[List[IdxClusterConfig]] = Field(
        None,
        description="Indexer clusters that hosts select by name. Holds no value itself.",
    )
    splunk_shclusters: Optional[List[ShClusterConfig]] = Field(
        None,
        description="Search head clusters that hosts select by name. Holds no value itself.",
    )

    @model_validator(mode='before')
    @classmethod
    def validate_admin_password_is_set(cls, data: Any) -> Any:
        """The admin password must be a non-empty literal or an env lookup."""
        if not isinstance(data, dict):
            return data
        defaults = data.get("splunk_defaults")
        password = defaults.get("splunk_admin_password") if isinstance(defaults, dict) else None
        if not isinstance(password, str) or not password.strip():
            raise ValueError(
                "splunk_defaults.splunk_admin_password is required. "
                "Set a literal password or an env lookup such as "
                "\"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"."
            )
        return data

    @model_validator(mode='before')
    @classmethod
    def reject_deprecated_aws(cls, data: Any) -> Any:
        if isinstance(data, dict) and "aws" in data:
            raise ValueError(DEPRECATED_AWS)
        return data

    @model_validator(mode='before')
    @classmethod
    def coerce_external_blocks(cls, data: Any) -> Any:
        """A bare ``external:`` selects the provider. An external-only env covers every host."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "external" in data and data.get("external") is None:
            data["external"] = {}
        hosts = data.get("splunk_hosts")
        if not isinstance(hosts, list):
            return data
        external_only = _raw_external_only(data)
        copied = []
        for host in hosts:
            if not isinstance(host, dict):
                copied.append(host)
                continue
            host = dict(host)
            if external_only and "external" not in host:
                host["external"] = {}
            elif "external" in host and host.get("external") is None:
                host["external"] = {}
            copied.append(host)
        data["splunk_hosts"] = copied
        return data

    @field_validator('plugin')
    @classmethod
    def validate_plugin_name(cls, v: str) -> str:
        if v != 'splunk-platform-automator':
            raise ValueError(f"Invalid plugin: '{v}'. Must be 'splunk-platform-automator'")
        return v

    @model_validator(mode='before')
    @classmethod
    def strip_root_passwords(cls, data: Any) -> Any:
        """Drop password keys from the root custom block without mutating the caller."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        custom = data.get("custom")
        if isinstance(custom, dict):
            custom, rejected = _copy_without_password_keys(custom)
            data["custom"] = custom
            if rejected:
                data["__spa_reject_password"] = True
        return data

    @model_validator(mode='after')
    def reject_root_passwords(self) -> 'SplunkConfig':
        extra = self.__pydantic_extra__ or {}
        if extra.pop("__spa_reject_password", False):
            raise ValueError("passwords are not accepted")
        return self

    @model_validator(mode='after')
    def validate_external_env(self) -> 'SplunkConfig':
        """External-only envs need the root block and cannot also name a managed provider."""
        hosts = self.splunk_hosts or []
        if not hosts or not all(host.external is not None for host in hosts):
            return self
        managed = self.virtualbox is not None or (
            self.terraform is not None
            and (
                self.terraform.aws is not None
                or bool(self.terraform.__pydantic_extra__)
            )
        )
        if managed and self.external is not None:
            raise ValueError("an external-only env cannot also set terraform or virtualbox")
        if managed:
            raise ValueError("a mixed env needs at least one host without external:")
        if self.external is None:
            raise ValueError(
                "external hosts require a root external: block when terraform.aws and virtualbox are absent"
            )
        return self

    @model_validator(mode='after')
    def validate_deployer_requires_shc(self) -> 'SplunkConfig':
        """Enforce the SHC member minimum per deployer-linked cluster."""
        member_counts: Dict[str, int] = {}
        for host in self.splunk_hosts:
            if AllowedRole.search_head in host.roles and host.shcluster:
                member_counts[host.shcluster] = member_counts.get(host.shcluster, 0) + _model_host_count(host)
        for host in self.splunk_hosts:
            if AllowedRole.deployer not in host.roles or not host.shcluster:
                continue
            count = member_counts.get(host.shcluster, 0)
            # Zero members is the documented external-SHC exception.
            if 0 < count < 3:
                raise ValueError(
                    f"Search Head Cluster {host.shcluster!r} requires at least 3 linked search heads. "
                    f"Found {count}."
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
        
        if has_deployer and 0 < shc_member_count < 3:
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
    def validate_one_deployer_per_shcluster(self) -> 'SplunkConfig':
        """One deployer per search-head cluster. A second name is concatenated into the SSH target."""
        grouped: Dict[Tuple[str, str], List[SplunkHost]] = {}
        for host in self.splunk_hosts:
            if AllowedRole.deployer not in host.roles:
                continue
            shc = (host.shcluster or "").strip() if isinstance(host.shcluster, str) else ""
            grouped.setdefault((_host_env(host), shc), []).append(host)
        for (env, shc), hosts in grouped.items():
            total = sum(_model_host_count(host) for host in hosts)
            if total <= 1:
                continue
            where = f"environment {env!r}" if env else "this config"
            labels = ", ".join(_host_label(host) for host in hosts)
            cluster = shc or "(unset)"
            raise ValueError(
                f"Search head cluster {cluster!r} can have only one deployer in {where}. "
                f"Found {total} hosts: {labels}. "
                f"Keep the deployer role on one host for this cluster."
            )
        return self

    @model_validator(mode='after')
    def validate_singleton_management_roles(self) -> 'SplunkConfig':
        """One deployment server and one license manager per environment."""
        for role in (AllowedRole.deployment_server, AllowedRole.license_manager):
            grouped: Dict[str, List[SplunkHost]] = {}
            for host in self.splunk_hosts:
                if role not in host.roles:
                    continue
                grouped.setdefault(_host_env(host), []).append(host)
            for env, hosts in grouped.items():
                total = sum(_model_host_count(host) for host in hosts)
                if total <= 1:
                    continue
                where = f"environment {env!r}" if env else "this config"
                labels = ", ".join(_host_label(host) for host in hosts)
                raise ValueError(
                    f"Role {role.value!r} can be assigned only once in {where}. "
                    f"Found {total} hosts: {labels}. "
                    f"Move the role onto one host."
                )
        return self

    @model_validator(mode='after')
    def validate_idxc_members_have_idxcluster(self) -> 'SplunkConfig':
        """Enforce the IDXC member minimum per manager-linked cluster."""
        member_counts: Dict[str, int] = {}
        for host in self.splunk_hosts:
            if AllowedRole.indexer in host.roles and host.idxcluster:
                member_counts[host.idxcluster] = member_counts.get(host.idxcluster, 0) + _model_host_count(host)
        for host in self.splunk_hosts:
            if AllowedRole.cluster_manager not in host.roles or not host.idxcluster:
                continue
            count = member_counts.get(host.idxcluster, 0)
            if count < 2:
                raise ValueError(
                    f"Indexer Cluster (idxcluster={host.idxcluster!r}) requires at least 2 linked indexers. "
                    f"Found {count}."
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
    def validate_each_idxc_has_linked_cluster_manager(self) -> 'SplunkConfig':
        """Every named IDXC with members has a manager linked to that identity."""
        if not self.splunk_idxclusters:
            return self
        managers = {
            host.idxcluster
            for host in self.splunk_hosts
            if AllowedRole.cluster_manager in host.roles and host.idxcluster
        }
        member_clusters = {
            host.idxcluster
            for host in self.splunk_hosts
            if AllowedRole.indexer in host.roles and host.idxcluster
        }
        missing = member_clusters - managers
        if missing:
            raise ValueError(
                "Every Indexer Cluster with members requires a linked cluster_manager. "
                f"IDXC(s) without one: {sorted(missing)!r}."
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

    def _has_license_manager_role(self) -> bool:
        return any(AllowedRole.license_manager in host.roles for host in self.splunk_hosts)

    def _has_splunk_license_file_configured(self) -> bool:
        if self.splunk_defaults is not None and self.splunk_defaults.splunk_license_file is not None:
            return True
        if self.splunk_environments:
            for env in self.splunk_environments:
                if env.splunk_license_file is not None:
                    return True
        return any(host.splunk_license_file is not None for host in self.splunk_hosts)

    @model_validator(mode='after')
    def validate_license_manager_requires_license_file(self) -> 'SplunkConfig':
        """Ensure license_manager role has splunk_license_file defined.
        
        If a license_manager role is defined, the splunk_defaults must include
        a splunk_license_file setting.
        """
        if not self._has_license_manager_role():
            return self

        if not self._has_splunk_license_file_configured():
            raise ValueError(
                "When a license_manager role is defined, 'splunk_license_file' must be specified "
                "in splunk_defaults (or splunk_environments / host override)."
            )

        return self

    @model_validator(mode='after')
    def validate_license_file_requires_license_manager(self) -> 'SplunkConfig':
        """Ensure splunk_license_file is only set when a license_manager role exists.

        License files are applied by the license_manager role during deploy. Setting
        splunk_license_file without that role has no effect and is usually a config mistake.
        For trial-only labs, omit splunk_license_file instead.
        """
        if not self._has_splunk_license_file_configured():
            return self

        if not self._has_license_manager_role():
            raise ValueError(
                "When 'splunk_license_file' is set in splunk_defaults (or splunk_environments / "
                "host override), at least one host in splunk_hosts must have the license_manager "
                "role. Add license_manager to a host (for example co-locate on cm or mc) or remove "
                "splunk_license_file for trial-only labs."
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
            if str(app.get("state", "installed")).strip().lower() == "absent":
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
            if str(app.get("state", "installed")).strip().lower() == "absent":
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

    @model_validator(mode='after')
    def validate_itsi_search_tier_is_singular(self) -> 'SplunkConfig':
        """Installed ITSI resolves to exactly one SHC or one standalone search head."""
        if not self.splunk_app_deployment or not self.splunk_app_deployment.apps:
            return self
        plain_hosts = []
        for host in self.splunk_hosts:
            plain_hosts.append({
                "name": host.name,
                "list": list(host.list or []),
                "iter": (
                    {
                        "prefix": host.iter.prefix,
                        "numbers": host.iter.numbers,
                        "postfix": host.iter.postfix,
                    }
                    if host.iter else None
                ),
                "roles": [role.value for role in host.roles],
                "shcluster": host.shcluster,
            })
        issue = itsi_search_tier_requirement({
            "splunk_hosts": plain_hosts,
            "splunk_app_deployment": {"apps": self.splunk_app_deployment.apps},
        })
        if issue:
            raise ValueError(issue["summary"])
        return self


# =============================================================================
# Declarative cross-section dependency planning
# =============================================================================

def _dependency_rule(
    rule_id: str,
    kind: str,
    trigger: str,
    required_facts: List[str],
    repair: str,
    unresolved: str,
) -> Dict[str, Any]:
    return {
        "id": rule_id,
        "kind": kind,
        "trigger": trigger,
        "required_facts": required_facts,
        "repair": repair,
        "unresolved": unresolved,
        "error": unresolved,
    }


DEPENDENCY_RULES = (
    _dependency_rule("host.deployer.shcluster", "choice", "host role deployer", ["SHC identities"], "link sole SHC", "Choose the SHC identity served by the deployer."),
    _dependency_rule("shcluster.members.minimum", "cardinality", "linked deployer and local SHC members", ["member count"], "none", "Each local SHC requires at least three linked search heads."),
    _dependency_rule("shcluster.deployer.required", "cardinality", "local SHC members", ["linked deployer"], "none", "Each local SHC requires a linked deployer."),
    _dependency_rule("host.cluster_manager.idxcluster", "choice", "host role cluster_manager", ["IDXC identities"], "link sole IDXC", "Choose the IDXC identity served by the cluster manager."),
    _dependency_rule("idxcluster.members.minimum", "cardinality", "linked cluster manager", ["member count"], "none", "Each IDXC requires at least two linked indexers."),
    _dependency_rule("idxcluster.manager.required", "cardinality", "IDXC members", ["linked cluster manager"], "none", "Each IDXC with members requires a linked cluster manager."),
    _dependency_rule("license_manager.license_file", "external_resource", "license_manager role", ["license file"], "none", "Provide an existing Splunk license file path."),
    _dependency_rule("license_file.license_manager", "choice", "configured license file", ["license_manager placement"], "none", "Choose a host for the license_manager role."),
    _dependency_rule("itsi.topology", "cardinality", "ITSI or content pack app", ["search head", "indexer", "license manager"], "none", "ITSI requires search, indexing, and license tiers."),
    _dependency_rule("itsi.java", "value", "ITSI or content pack app", ["Java 21 package"], "none", "ITSI requires Java 21 on its search tier."),
    _dependency_rule("itsi.search_tier", "choice", "installed ITSI app", ["one SHC or one standalone search head"], "none", "ITSI must target exactly one search tier."),
    _dependency_rule("app.filter.cluster", "choice", "cluster app filter", ["existing cluster identities"], "none", "Choose existing cluster identities for app filters."),
    _dependency_rule("app.filter.serverclass", "choice", "server-class app filter", ["deployment server"], "none", "Server-class filters require a deployment_server host."),
    _dependency_rule("dependency.cycle", "value", "dependency planning", ["stable closure"], "none", "Dependency planning could not reach a stable closure."),
)

_DEPENDENCY_RULE_BY_ID = {rule["id"]: rule for rule in DEPENDENCY_RULES}


def _raw_host_count(host: Dict[str, Any]) -> int:
    names = host.get("list")
    if isinstance(names, list):
        return len(names)
    iteration = host.get("iter")
    if isinstance(iteration, dict):
        numbers = str(iteration.get("numbers") or "")
        match = re.fullmatch(r"(\d+)\.\.(\d+)", numbers)
        if match:
            first, last = int(match.group(1)), int(match.group(2))
            return max(0, last - first + 1)
    return 1


def _raw_host_label(host: Dict[str, Any], index: int) -> str:
    if host.get("name"):
        return "splunk_hosts[name=%s]" % host["name"]
    if isinstance(host.get("iter"), dict) and host["iter"].get("prefix"):
        return "splunk_hosts[iter.prefix=%s]" % host["iter"]["prefix"]
    return "splunk_hosts[%s]" % index


def _raw_host_names(host: Dict[str, Any]) -> List[str]:
    if host.get("name"):
        return [str(host["name"])]
    names = host.get("list")
    if isinstance(names, list):
        return [str(item) for item in names]
    iteration = host.get("iter")
    if isinstance(iteration, dict):
        match = re.fullmatch(r"(\d+)\.\.(\d+)", str(iteration.get("numbers") or ""))
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            width = len(match.group(2))
            prefix = iteration.get("prefix") or ""
            postfix = iteration.get("postfix") or ""
            return [
                "%s%s%s" % (prefix, str(number).zfill(width), postfix)
                for number in range(start, end + 1)
            ]
    return []


def _search_tiers(hosts: List[Dict[str, Any]]) -> tuple:
    clusters: Dict[str, List[str]] = {}
    standalone: List[str] = []
    for host in hosts or []:
        if not isinstance(host, dict):
            continue
        roles = {str(getattr(role, "value", role)) for role in (host.get("roles") or [])}
        if "search_head" not in roles:
            continue
        names = _raw_host_names(host)
        cluster = str(host.get("shcluster") or "").strip()
        if cluster:
            clusters.setdefault(cluster, []).extend(names)
        else:
            standalone.extend(names)
    return clusters, standalone


def _installed_itsi_apps(config: Dict[str, Any]) -> List[tuple]:
    apps = ((config.get("splunk_app_deployment") or {}).get("apps") or [])
    installed = []
    for index, app in enumerate(apps):
        if not isinstance(app, dict):
            continue
        if str(app.get("state", "installed")).strip().lower() == "absent":
            continue
        premium = str(app.get("premium_app") or "").strip().lower()
        if premium == "itsi" or app.get("app_id") == 1841:
            installed.append((index, app))
    return installed


def itsi_search_tier_requirement(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the singular ITSI search-tier choice, or None when placement is valid."""
    clusters, standalone = _search_tiers(config.get("splunk_hosts") or [])
    cluster_names = list(clusters)
    for _index, app in _installed_itsi_apps(config):
        app_id = app.get("app_id", 1841)
        selected_clusters = [
            str(value).strip()
            for value in (app.get("shc_whitelist") or [])
            if str(value).strip()
        ]
        selected_hosts = [
            str(value).strip()
            for value in (app.get("hosts_whitelist") or [])
            if str(value).strip()
        ]
        one_cluster = (
            len(selected_clusters) == 1
            and selected_clusters[0] in clusters
            and not selected_hosts
        )
        one_host = (
            len(selected_hosts) == 1
            and selected_hosts[0] in standalone
            and not selected_clusters
        )
        implicit_cluster = (
            not selected_clusters
            and not selected_hosts
            and len(cluster_names) == 1
            and not standalone
        )
        implicit_host = (
            not selected_clusters
            and not selected_hosts
            and len(standalone) == 1
            and not cluster_names
        )
        if one_cluster or one_host or implicit_cluster or implicit_host:
            continue
        if cluster_names:
            retry_path = "splunk_app_deployment.apps[app_id=%s].shc_whitelist" % app_id
            retry_value = cluster_names[0]
        else:
            retry_path = "splunk_app_deployment.apps[app_id=%s].hosts_whitelist" % app_id
            retry_value = standalone[0] if standalone else "search_head"
        return {
            "paths": [retry_path, "splunk_hosts"],
            "summary": (
                "ITSI must target exactly one search tier. "
                "Set shc_whitelist to one search-head cluster or hosts_whitelist to one standalone search head."
            ),
            "allowed": cluster_names + standalone,
            "retry": "--resolve '%s' '[\"%s\"]'" % (retry_path, retry_value),
        }
    return None


def _raw_license_file_present(config: Dict[str, Any]) -> bool:
    defaults = config.get("splunk_defaults") or {}
    if defaults.get("splunk_license_file"):
        return True
    for environment in config.get("splunk_environments") or []:
        if (environment.get("splunk_defaults") or {}).get("splunk_license_file"):
            return True
    return any(host.get("splunk_license_file") for host in config.get("splunk_hosts") or [])


def _plan_config_dependencies_pass(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply one pass of deterministic repairs and collect requirements.

    This function intentionally consumes plain mappings so the editor can plan
    an incomplete candidate before Pydantic rejects it. Final validation still
    runs the model validators after this function reports ready.
    """
    requirements: List[Dict[str, Any]] = []
    repairs: List[Dict[str, Any]] = []
    seen_requirements = set()

    def require(rule_id, kind, paths, summary, *, allowed=None, retry=None):
        rule = _DEPENDENCY_RULE_BY_ID[rule_id]
        if kind != rule["kind"]:
            raise RuntimeError(
                "Dependency rule %s emitted kind %s, expected %s"
                % (rule_id, kind, rule["kind"])
            )
        key = (rule_id, tuple(paths), summary)
        if key in seen_requirements:
            return
        seen_requirements.add(key)
        item = {
            "rule_id": rule_id,
            "kind": kind,
            "paths": list(paths),
            "summary": summary,
            "retry": retry or "Retry with --resolve PATH VALUE or --resolve-file FILE",
        }
        if allowed:
            item["allowed"] = list(allowed)
        requirements.append(item)

    hosts = config.setdefault("splunk_hosts", [])
    shclusters = config.get("splunk_shclusters") or []
    idxclusters = config.get("splunk_idxclusters") or []
    shc_names = [str(row.get("shc_name")) for row in shclusters if row.get("shc_name")]
    idxc_names = [str(row.get("idxc_name")) for row in idxclusters if row.get("idxc_name")]

    # Link managers only when the choice is unique; scaffold an explicitly
    # named cluster identity without inventing topology members.
    for index, host in enumerate(hosts):
        roles = set(host.get("roles") or [])
        label = _raw_host_label(host, index)
        if "deployer" in roles and not host.get("shcluster"):
            if len(shc_names) == 1:
                host["shcluster"] = shc_names[0]
                repairs.append({"op": "set", "path": label + ".shcluster", "value": shc_names[0]})
            else:
                require(
                    "host.deployer.shcluster", "choice",
                    [label + ".shcluster", "splunk_shclusters"],
                    "Choose the search-head cluster managed by this deployer.",
                    allowed=shc_names,
                )
        if "cluster_manager" in roles and not host.get("idxcluster"):
            if len(idxc_names) == 1:
                host["idxcluster"] = idxc_names[0]
                repairs.append({"op": "set", "path": label + ".idxcluster", "value": idxc_names[0]})
            else:
                require(
                    "host.cluster_manager.idxcluster", "choice",
                    [label + ".idxcluster", "splunk_idxclusters"],
                    "Choose the indexer cluster managed by this cluster manager.",
                    allowed=idxc_names,
                )

    # A caller-supplied identity is enough to scaffold the corresponding
    # section. It is not enough to synthesize members.
    for host in hosts:
        shcluster = host.get("shcluster")
        if shcluster and str(shcluster) not in shc_names:
            config.setdefault("splunk_shclusters", []).append({"shc_name": shcluster})
            shc_names.append(str(shcluster))
            repairs.append({"op": "append", "path": "splunk_shclusters", "value": {"shc_name": shcluster}})
        idxcluster = host.get("idxcluster")
        if idxcluster and str(idxcluster) not in idxc_names:
            config.setdefault("splunk_idxclusters", []).append({"idxc_name": idxcluster})
            idxc_names.append(str(idxcluster))
            repairs.append({"op": "append", "path": "splunk_idxclusters", "value": {"idxc_name": idxcluster}})

    for name in shc_names:
        deployers = [
            host for host in hosts
            if "deployer" in set(host.get("roles") or []) and str(host.get("shcluster")) == name
        ]
        members = sum(
            _raw_host_count(host)
            for host in hosts
            if "search_head" in set(host.get("roles") or []) and str(host.get("shcluster")) == name
        )
        if not deployers and (members or len(shc_names) > 1):
            require(
                "shcluster.deployer.required", "cardinality",
                ["splunk_shclusters[shc_name=%s]" % name, "splunk_hosts"],
                "Search-head cluster %s needs one linked deployer." % name,
            )
        if deployers and 0 < members < 3:
            require(
                "shcluster.members.minimum", "cardinality",
                ["splunk_shclusters[shc_name=%s]" % name, "splunk_hosts"],
                "Search-head cluster %s needs at least 3 linked search heads; found %s." % (name, members),
            )

    for name in idxc_names:
        managers = [
            host for host in hosts
            if "cluster_manager" in set(host.get("roles") or []) and str(host.get("idxcluster")) == name
        ]
        members = sum(
            _raw_host_count(host)
            for host in hosts
            if "indexer" in set(host.get("roles") or []) and str(host.get("idxcluster")) == name
        )
        if not managers:
            require(
                "idxcluster.manager.required", "cardinality",
                ["splunk_idxclusters[idxc_name=%s]" % name, "splunk_hosts"],
                "Indexer cluster %s needs one linked cluster manager." % name,
            )
        if managers and members < 2:
            require(
                "idxcluster.members.minimum", "cardinality",
                ["splunk_idxclusters[idxc_name=%s]" % name, "splunk_hosts"],
                "Indexer cluster %s needs at least 2 linked indexers; found %s." % (name, members),
            )

    has_license_manager = any(
        "license_manager" in set(host.get("roles") or []) for host in hosts
    )
    has_license_file = _raw_license_file_present(config)
    if has_license_manager and not has_license_file:
        require(
            "license_manager.license_file", "external_resource",
            ["splunk_defaults.splunk_license_file"],
            "Provide an existing Splunk license file path.",
        )
    if has_license_file and not has_license_manager:
        require(
            "license_file.license_manager", "choice",
            ["splunk_hosts"],
            "Choose a host for the license_manager role.",
        )

    apps = ((config.get("splunk_app_deployment") or {}).get("apps") or [])
    active_apps = [
        app
        for app in apps
        if isinstance(app, dict) and app.get("state", "installed") != "absent"
    ]
    has_content_pack = any(
        app.get("itsi_content_pack") is True
        and app.get("app_id") != 1841
        and app.get("premium_app") != "itsi"
        for app in active_apps
    )
    has_itsi_app = any(
        app.get("premium_app") == "itsi" or app.get("app_id") == 1841
        for app in active_apps
    )
    if has_content_pack and not has_itsi_app:
        itsi_entry = {
            "name": "Splunk IT Service Intelligence",
            "app_id": 1841,
            "premium_app": "itsi",
        }
        apps.insert(0, itsi_entry)
        repairs.append(
            {
                "op": "set",
                "path": "splunk_app_deployment.apps[app_id=1841]",
                "value": itsi_entry,
            }
        )
    has_itsi = any(
        app.get("premium_app") == "itsi"
        or app.get("app_id") == 1841
        or app.get("itsi_content_pack") is True
        for app in active_apps
    )
    if has_itsi:
        tier = itsi_search_tier_requirement(config)
        if tier:
            require(
                "itsi.search_tier", "choice",
                tier["paths"],
                tier["summary"],
                allowed=tier["allowed"],
                retry=tier["retry"],
            )
        role_set = {
            role
            for host in hosts
            for role in (host.get("roles") or [])
        }
        for role in ("search_head", "indexer", "license_manager"):
            if role not in role_set:
                require(
                    "itsi.topology", "cardinality",
                    ["splunk_hosts"],
                    "ITSI requires at least one %s host." % role,
                )
        global_packages = set((config.get("os") or {}).get("packages") or [])
        java_present = any(
            "java-21" in str(package)
            for package in global_packages
        ) or any(
            "search_head" in set(host.get("roles") or [])
            and any(
                "java-21" in str(package)
                for package in ((host.get("os") or {}).get("packages") or [])
            )
            for host in hosts
        )
        if not java_present:
            require(
                "itsi.java", "value",
                ["os.packages", "splunk_hosts[].os.packages"],
                "ITSI requires Java 21 on its search tier.",
            )

    for index, app in enumerate(apps):
        if not isinstance(app, dict):
            continue
        for field, existing in (
            ("shc_whitelist", shc_names), ("shc_blacklist", shc_names),
            ("idxc_whitelist", idxc_names), ("idxc_blacklist", idxc_names),
        ):
            missing = [str(name) for name in app.get(field) or [] if str(name) not in existing]
            if missing:
                require(
                    "app.filter.cluster", "choice",
                    ["splunk_app_deployment.apps[%s].%s" % (index, field)],
                    "App filter references unknown cluster identities: %s." % ", ".join(missing),
                    allowed=existing,
                )
        if app.get("sc_whitelist") or app.get("sc_blacklist"):
            if not any(
                "deployment_server" in set(host.get("roles") or [])
                for host in hosts
            ):
                require(
                    "app.filter.serverclass", "choice",
                    ["splunk_hosts", "splunk_app_deployment.apps[%s]" % index],
                    "Server-class filters require a deployment_server host.",
                )

    return {
        "ready": not requirements,
        "requirements": requirements,
        "repairs": repairs,
    }


def plan_config_dependencies(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply dependency rules to a fixpoint and detect repair cycles."""
    all_repairs: List[Dict[str, Any]] = []
    repair_keys = set()
    seen_states = set()

    for _ in range(64):
        before = json.dumps(config, sort_keys=True, default=str)
        if before in seen_states:
            return {
                "ready": False,
                "requirements": [{
                    "rule_id": "dependency.cycle",
                    "kind": "value",
                    "paths": [],
                    "summary": _DEPENDENCY_RULE_BY_ID["dependency.cycle"]["unresolved"],
                    "retry": "Remove the conflicting dependency resolutions and retry.",
                }],
                "repairs": all_repairs,
            }
        seen_states.add(before)
        result = _plan_config_dependencies_pass(config)
        for repair in result["repairs"]:
            key = json.dumps(repair, sort_keys=True, default=str)
            if key not in repair_keys:
                repair_keys.add(key)
                all_repairs.append(repair)
        after = json.dumps(config, sort_keys=True, default=str)
        if after == before:
            result["repairs"] = all_repairs
            return result

    return {
        "ready": False,
        "requirements": [{
            "rule_id": "dependency.cycle",
            "kind": "value",
            "paths": [],
            "summary": _DEPENDENCY_RULE_BY_ID["dependency.cycle"]["unresolved"],
            "retry": "Remove the conflicting dependency resolutions and retry.",
        }],
        "repairs": all_repairs,
    }


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
        model = SplunkConfig.model_validate(config_data)
    except ValidationError as initial_error:
        raise ConfigValidationError(initial_error.errors())
    candidate = model.model_dump(mode="json", exclude_none=True)
    dependency = plan_config_dependencies(candidate)
    if dependency["requirements"]:
        raise ConfigValidationError(
            [
                {
                    "loc": requirement["paths"],
                    "msg": requirement["summary"],
                }
                for requirement in dependency["requirements"]
            ]
        )
    if dependency["repairs"]:
        raise ConfigValidationError(
            [
                {
                    "loc": [repair.get("path") or "config"],
                    "msg": "Configuration requires dependency repair before validation.",
                }
                for repair in dependency["repairs"]
            ]
        )
    return model


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
