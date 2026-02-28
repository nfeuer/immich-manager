"""
Alert system for sending notifications via email, webhooks, and Discord.
"""

import aiosmtplib
import requests
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time
from typing import Optional, Dict, Any
import asyncio

logger = logging.getLogger(__name__)

# Discord embed colour codes
_DISCORD_COLORS = {
    "critical": 0xFF0000,
    "warning": 0xFFAA00,
    "info": 0x0099FF,
}

_SEVERITY_EMOJI = {
    "critical": "\U0001f534",   # red circle
    "warning": "\u26a0\ufe0f",  # warning sign
    "info": "\u2139\ufe0f",     # info
}


class AlertManager:
    """Manages alerts and notifications via email, webhook, and Discord."""

    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------

    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        if not self.config.quiet_hours.enabled:
            return False

        now = datetime.now().time()
        start = datetime.strptime(self.config.quiet_hours.start, "%H:%M").time()
        end = datetime.strptime(self.config.quiet_hours.end, "%H:%M").time()

        if start < end:
            return start <= now <= end
        else:
            return now >= start or now <= end

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    async def send_email(self, subject: str, body: str, severity: str = "info") -> bool:
        if not self.config.email.enabled:
            return False
        if severity != "critical" and self.is_quiet_hours():
            return False

        try:
            message = MIMEMultipart()
            message["From"] = self.config.email.from_addr
            message["To"] = ", ".join(self.config.email.to)
            message["Subject"] = f"[Immich {severity.upper()}] {subject}"

            html_body = f"""
            <html>
                <body>
                    <h2>{_SEVERITY_EMOJI.get(severity, '')} {subject}</h2>
                    <p><strong>Severity:</strong> {severity.upper()}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <hr>
                    <pre>{body}</pre>
                    <p style="color:#888;font-size:12px">
                        House of Feuer &mdash; <a href="https://houseoffeuer.com">houseoffeuer.com</a>
                    </p>
                </body>
            </html>
            """

            message.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                message,
                hostname=self.config.email.smtp_host,
                port=self.config.email.smtp_port,
                username=self.config.email.smtp_user,
                password=self.config.email.smtp_password,
                start_tls=True,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    # ------------------------------------------------------------------
    # Generic webhook (Slack / custom)
    # ------------------------------------------------------------------

    def send_webhook(self, title: str, message: str, severity: str = "info") -> bool:
        if not self.config.webhook.enabled or not self.config.webhook.url:
            return False
        if severity != "critical" and self.is_quiet_hours():
            return False

        try:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": _DISCORD_COLORS.get(severity, 0x0099FF),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "fields": [
                        {"name": "Severity", "value": severity.upper(), "inline": True},
                        {"name": "Source", "value": "Immich Server Manager", "inline": True},
                    ],
                }],
            }

            resp = requests.post(self.config.webhook.url, json=payload, timeout=10)
            return resp.status_code in (200, 204)

        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False

    # ------------------------------------------------------------------
    # Discord
    # ------------------------------------------------------------------

    def send_discord(self, title: str, message: str, severity: str = "info") -> bool:
        """Send a rich embed to a Discord channel via webhook."""
        discord_cfg = getattr(self.config, "discord", None)
        if not discord_cfg or not discord_cfg.enabled or not discord_cfg.webhook_url:
            return False
        if severity != "critical" and self.is_quiet_hours():
            return False

        try:
            bot_name = discord_cfg.bot_name or "House of Feuer"
            server_label = discord_cfg.server_name or "Immich Server"

            payload = {
                "username": bot_name,
                "embeds": [{
                    "title": f"{_SEVERITY_EMOJI.get(severity, '')} {title}",
                    "description": message,
                    "color": _DISCORD_COLORS.get(severity, 0x0099FF),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "fields": [
                        {"name": "Severity", "value": severity.upper(), "inline": True},
                        {"name": "Server", "value": server_label, "inline": True},
                    ],
                    "footer": {
                        "text": "House of Feuer | houseoffeuer.com",
                    },
                }],
            }

            resp = requests.post(discord_cfg.webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)

        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    # ------------------------------------------------------------------
    # Unified dispatch
    # ------------------------------------------------------------------

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "info",
        details: Optional[Dict[str, Any]] = None,
    ):
        """Send alert via all enabled channels."""
        full_message = message
        if details:
            full_message += "\n\nDetails:\n"
            for key, value in details.items():
                full_message += f"  {key}: {value}\n"

        if self.config.email.enabled:
            await self.send_email(title, full_message, severity)

        if self.config.webhook.enabled:
            self.send_webhook(title, full_message, severity)

        # Discord
        self.send_discord(title, full_message, severity)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def send_disk_health_alert(self, disk_data: Dict[str, Any]):
        device = disk_data.get("device", "unknown")
        warnings = disk_data.get("warnings", [])
        if not warnings:
            return

        message = f"Disk health issues detected on {device}:\n"
        for w in warnings:
            message += f"  - {w}\n"

        severity = "critical" if disk_data.get("smart_status") is False else "warning"
        asyncio.create_task(
            self.send_alert(
                f"Disk Health Warning: {device}",
                message,
                severity,
                {
                    "temperature": disk_data.get("temperature"),
                    "power_on_hours": disk_data.get("power_on_hours"),
                    "model": disk_data.get("model"),
                },
            )
        )

    def send_backup_alert(self, backup_result: Dict[str, Any]):
        if backup_result["status"] == "success":
            message = (
                f"Backup completed successfully\n"
                f"Size: {backup_result.get('size_mb', 0):.2f} MB\n"
                f"Duration: {backup_result.get('duration_seconds', 0):.1f} seconds"
            )
            asyncio.create_task(self.send_alert("Backup Completed", message, "info"))
        else:
            message = f"Backup failed!\nError: {backup_result.get('error', 'Unknown error')}"
            asyncio.create_task(self.send_alert("Backup Failed", message, "critical"))

    def send_system_alert(self, metric: str, value: float, threshold: float):
        message = (
            f"{metric} has exceeded threshold\n"
            f"Current: {value:.1f}%\n"
            f"Threshold: {threshold}%"
        )
        severity = "critical" if value > threshold + 10 else "warning"
        asyncio.create_task(self.send_alert(f"System Alert: {metric}", message, severity))
