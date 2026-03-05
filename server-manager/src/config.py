"""
Configuration management for Immich Server Manager
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ServerConfig(BaseModel):
    """Server configuration"""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 2
    log_level: str = "INFO"


class ImmichConfig(BaseModel):
    """Immich configuration"""
    docker_compose_path: str = "/opt/immich"
    api_url: str = "http://localhost:2283/api"
    api_key: str = ""


class StorageConfig(BaseModel):
    """Storage configuration"""
    mergerfs_mount: str = "/mnt/storage"
    data_drives: List[str] = Field(default_factory=list)
    parity_drives: List[str] = Field(default_factory=list)
    snapraid_config: str = "/etc/snapraid.conf"


class EncryptionConfig(BaseModel):
    """Encryption configuration for backups"""
    enabled: bool = False
    public_key: str = ""


class BackupConfig(BaseModel):
    """Backup configuration"""
    enabled: bool = True
    local_path: str = "/mnt/backups/immich"
    schedule: str = "0 2 * * *"
    retention_days: int = 30
    compression: bool = True
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)


class MonitoringConfig(BaseModel):
    """Monitoring configuration"""
    disk_check_interval: int = 300  # seconds
    metrics_interval: int = 60  # seconds


class ThresholdsConfig(BaseModel):
    """Alert thresholds"""
    disk_temp_warning: int = 45
    disk_temp_critical: int = 50
    disk_space_warning: int = 85
    disk_space_critical: int = 95


class QuietHoursConfig(BaseModel):
    """Quiet hours configuration"""
    enabled: bool = True
    start: str = "22:00"
    end: str = "08:00"


class EmailConfig(BaseModel):
    """Email alert configuration"""
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_addr: str = Field(alias="from")
    to: List[str] = Field(default_factory=list)


class WebhookConfig(BaseModel):
    """Webhook alert configuration"""
    enabled: bool = False
    url: str = ""


class DiscordConfig(BaseModel):
    """Discord webhook alert configuration"""
    enabled: bool = False
    webhook_url: str = ""
    bot_name: str = "House of Feuer"
    server_name: str = ""  # Optional: your server's display name


class AlertsConfig(BaseModel):
    """Alerts configuration"""
    email: EmailConfig = Field(default_factory=EmailConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)


class AuthConfig(BaseModel):
    """Authentication and RBAC configuration"""
    default_role: str = "user"  # Role for new users: "admin", "user", or "guest"


class Config(BaseModel):
    """Main configuration"""
    server: ServerConfig = Field(default_factory=ServerConfig)
    immich: ImmichConfig = Field(default_factory=ImmichConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


_ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')


def _resolve_env_vars(obj):
    """
    Recursively resolve ${ENV_VAR} and ${ENV_VAR:-default} references in
    config values.  This lets users keep secrets out of config files, e.g.:
        smtp_password: "${SMTP_PASSWORD}"
        api_key: "${IMMICH_API_KEY:-}"
    """
    if isinstance(obj, str):
        def _replace(match):
            expr = match.group(1)
            if ':-' in expr:
                var_name, default = expr.split(':-', 1)
            else:
                var_name, default = expr, ''
            return os.environ.get(var_name.strip(), default)
        return _ENV_VAR_PATTERN.sub(_replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file.

    Supports ${ENV_VAR} and ${ENV_VAR:-default} syntax for secret values.

    Args:
        config_path: Path to config file, defaults to config/config.yaml

    Returns:
        Config object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if config_path is None:
        # Look for config in standard locations
        possible_paths = [
            "config/config.yaml",
            "/opt/immich-server-manager/config/config.yaml",
            os.environ.get("SERVER_MANAGER_CONFIG", ""),
        ]

        for path in possible_paths:
            if path and Path(path).exists():
                config_path = path
                break

    if not config_path or not Path(config_path).exists():
        raise FileNotFoundError(
            "Config file not found. Please create config/config.yaml from config.yaml.example"
        )

    with open(config_path, 'r') as f:
        config_data = yaml.safe_load(f)

    config_data = _resolve_env_vars(config_data)

    return Config(**config_data)


def save_config(config: Config, config_path: str = "config/config.yaml"):
    """
    Save configuration to YAML file

    Args:
        config: Config object to save
        config_path: Path to save config file
    """
    config_dict = config.model_dump()

    # Ensure directory exists
    Path(config_path).parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, 'w') as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
