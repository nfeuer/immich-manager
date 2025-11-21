"""
Alert system for sending notifications via email and webhooks
"""

import aiosmtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time
from typing import Optional, Dict, Any
import asyncio


class AlertManager:
    """Manages alerts and notifications"""

    def __init__(self, config):
        """
        Initialize alert manager

        Args:
            config: AlertsConfig object
        """
        self.config = config

    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours"""
        if not self.config.quiet_hours.enabled:
            return False

        now = datetime.now().time()
        start = datetime.strptime(self.config.quiet_hours.start, "%H:%M").time()
        end = datetime.strptime(self.config.quiet_hours.end, "%H:%M").time()

        if start < end:
            return start <= now <= end
        else:
            # Quiet hours span midnight
            return now >= start or now <= end

    async def send_email(self, subject: str, body: str, severity: str = "info") -> bool:
        """
        Send email alert

        Args:
            subject: Email subject
            body: Email body
            severity: Alert severity (info, warning, critical)

        Returns:
            True if sent successfully
        """
        if not self.config.email.enabled:
            return False

        # Skip non-critical alerts during quiet hours
        if severity != "critical" and self.is_quiet_hours():
            return False

        try:
            message = MIMEMultipart()
            message["From"] = self.config.email.from_addr
            message["To"] = ", ".join(self.config.email.to)
            message["Subject"] = f"[Immich {severity.upper()}] {subject}"

            # Add severity indicator
            severity_emoji = {
                "critical": "🔴",
                "warning": "⚠️",
                "info": "ℹ️"
            }

            html_body = f"""
            <html>
                <body>
                    <h2>{severity_emoji.get(severity, '')} {subject}</h2>
                    <p><strong>Severity:</strong> {severity.upper()}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <hr>
                    <pre>{body}</pre>
                </body>
            </html>
            """

            message.attach(MIMEText(html_body, "html"))

            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.config.email.smtp_host,
                port=self.config.email.smtp_port,
                username=self.config.email.smtp_user,
                password=self.config.email.smtp_password,
                start_tls=True
            )

            return True

        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    def send_webhook(self, title: str, message: str, severity: str = "info") -> bool:
        """
        Send webhook notification

        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity

        Returns:
            True if sent successfully
        """
        if not self.config.webhook.enabled or not self.config.webhook.url:
            return False

        # Skip non-critical alerts during quiet hours
        if severity != "critical" and self.is_quiet_hours():
            return False

        try:
            # Format for Slack/Discord-style webhooks
            color_map = {
                "critical": "#ff0000",
                "warning": "#ffaa00",
                "info": "#0099ff"
            }

            payload = {
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": int(color_map.get(severity, "#0099ff").lstrip("#"), 16),
                    "timestamp": datetime.now().isoformat(),
                    "fields": [
                        {
                            "name": "Severity",
                            "value": severity.upper(),
                            "inline": True
                        },
                        {
                            "name": "Source",
                            "value": "Immich Server Manager",
                            "inline": True
                        }
                    ]
                }]
            }

            response = requests.post(
                self.config.webhook.url,
                json=payload,
                timeout=10
            )

            return response.status_code == 200

        except Exception as e:
            print(f"Failed to send webhook: {e}")
            return False

    async def send_alert(self, title: str, message: str, severity: str = "info", details: Optional[Dict[str, Any]] = None):
        """
        Send alert via all enabled channels

        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity (info, warning, critical)
            details: Optional additional details
        """
        # Format message with details
        full_message = message
        if details:
            full_message += "\n\nDetails:\n"
            for key, value in details.items():
                full_message += f"  {key}: {value}\n"

        # Send via email
        if self.config.email.enabled:
            await self.send_email(title, full_message, severity)

        # Send via webhook
        if self.config.webhook.enabled:
            self.send_webhook(title, full_message, severity)

    def send_disk_health_alert(self, disk_data: Dict[str, Any]):
        """Send alert for disk health issues"""
        device = disk_data.get('device', 'unknown')
        warnings = disk_data.get('warnings', [])

        if not warnings:
            return

        message = f"Disk health issues detected on {device}:\n"
        for warning in warnings:
            message += f"  - {warning}\n"

        severity = "critical" if disk_data.get('smart_status') == False else "warning"

        asyncio.create_task(
            self.send_alert(
                f"Disk Health Warning: {device}",
                message,
                severity,
                {
                    'temperature': disk_data.get('temperature'),
                    'power_on_hours': disk_data.get('power_on_hours'),
                    'model': disk_data.get('model')
                }
            )
        )

    def send_backup_alert(self, backup_result: Dict[str, Any]):
        """Send alert for backup completion"""
        if backup_result['status'] == 'success':
            message = f"Backup completed successfully\n"
            message += f"Size: {backup_result.get('size_mb', 0):.2f} MB\n"
            message += f"Duration: {backup_result.get('duration_seconds', 0):.1f} seconds"

            asyncio.create_task(
                self.send_alert(
                    "Backup Completed",
                    message,
                    "info"
                )
            )
        else:
            message = f"Backup failed!\n"
            message += f"Error: {backup_result.get('error', 'Unknown error')}"

            asyncio.create_task(
                self.send_alert(
                    "Backup Failed",
                    message,
                    "critical"
                )
            )

    def send_system_alert(self, metric: str, value: float, threshold: float):
        """Send alert for system metric threshold exceeded"""
        message = f"{metric} has exceeded threshold\n"
        message += f"Current: {value:.1f}%\n"
        message += f"Threshold: {threshold}%"

        severity = "critical" if value > threshold + 10 else "warning"

        asyncio.create_task(
            self.send_alert(
                f"System Alert: {metric}",
                message,
                severity
            )
        )
