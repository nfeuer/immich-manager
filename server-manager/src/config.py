"""
Configuration management for Immich Server Manager
"""

import os
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


class AlertsConfig(BaseModel):
    """Alerts configuration"""
    email: EmailConfig = Field(default_factory=EmailConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)


class Config(BaseModel):
    """Main configuration"""
    server: ServerConfig = Field(default_factory=ServerConfig)
    immich: ImmichConfig = Field(default_factory=ImmichConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file

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
