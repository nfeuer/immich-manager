"""
Email notification system for Photo Curator
Handles monthly reminders and other email alerts (all opt-in)
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Handles email notifications with user preference checking"""

    def __init__(self, config: Dict):
        """
        Initialize email notifier

        Args:
            config: Email configuration dictionary
        """
        self.enabled = config.get('enabled', False)
        self.smtp_host = config.get('smtp_host')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_user = config.get('smtp_user')
        self.smtp_password = config.get('smtp_password')
        self.from_email = config.get('from', self.smtp_user)

        if not self.enabled:
            logger.info("Email notifications disabled in config")

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None
    ) -> bool:
        """
        Send an email

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML email body
            body_text: Plain text fallback (optional)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Email notifications disabled, skipping: {subject}")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email

            # Attach plain text (fallback)
            if body_text:
                part1 = MIMEText(body_text, 'plain')
                msg.attach(part1)

            # Attach HTML
            part2 = MIMEText(body_html, 'html')
            msg.attach(part2)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def send_monthly_reminder(
        self,
        user_email: str,
        user_name: str,
        year: int,
        month: int,
        photo_count: int,
        curator_url: str
    ) -> bool:
        """
        Send monthly curation reminder

        Args:
            user_email: User's email address
            user_name: User's name
            year: Year
            month: Month
            photo_count: Number of photos available
            curator_url: URL to curator

        Returns:
            True if sent successfully
        """
        month_names = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]

        month_name = month_names[month - 1]

        subject = f"Time to curate your {month_name} {year} photos!"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #4250af 0%, #667eea 100%);
                    color: white;
                    padding: 30px 20px;
                    border-radius: 12px 12px 0 0;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .content {{
                    background: #f9fafb;
                    padding: 30px 20px;
                    border-radius: 0 0 12px 12px;
                }}
                .stats {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #4250af;
                }}
                .stats-number {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #4250af;
                }}
                .button {{
                    display: inline-block;
                    background: #4250af;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 6px;
                    font-weight: 500;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    color: #6b7280;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📸 Your Monthly Photo Curation</h1>
            </div>
            <div class="content">
                <p>Hi {user_name},</p>

                <p>It's time to curate your photos from <strong>{month_name} {year}</strong>!</p>

                <div class="stats">
                    <div class="stats-number">{photo_count}</div>
                    <div>photos ready to curate</div>
                </div>

                <p>Our AI has analyzed your photos and selected the best ones, but you can always:</p>
                <ul>
                    <li>✨ Review AI suggestions</li>
                    <li>➕ Add photos you love</li>
                    <li>➖ Remove photos you don't want</li>
                    <li>💾 Create a beautiful album in Immich</li>
                </ul>

                <center>
                    <a href="{curator_url}" class="button">Start Curating →</a>
                </center>

                <p style="margin-top: 30px; font-size: 14px; color: #6b7280;">
                    This usually takes just 5-10 minutes, and it's a great way to preserve your favorite memories!
                </p>
            </div>
            <div class="footer">
                <p>You're receiving this because you have monthly reminders enabled in your Photo Curator preferences.</p>
                <p><a href="{curator_url}/preferences" style="color: #4250af;">Manage email preferences</a></p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Hi {user_name},

        It's time to curate your photos from {month_name} {year}!

        You have {photo_count} photos ready to curate.

        Visit the Photo Curator: {curator_url}

        Our AI has selected the best photos, but you can review, add, or remove any photos before creating your album.

        ---
        You're receiving this because you have monthly reminders enabled.
        Manage preferences: {curator_url}/preferences
        """

        return self.send_email(user_email, subject, html_body, text_body)

    def send_storage_warning(
        self,
        user_email: str,
        user_name: str,
        used_gb: float,
        quota_gb: float,
        percent_used: float
    ) -> bool:
        """
        Send storage quota warning

        Args:
            user_email: User's email
            user_name: User's name
            used_gb: GB used
            quota_gb: GB quota
            percent_used: Percentage used

        Returns:
            True if sent successfully
        """
        subject = f"⚠️ Storage Warning: {percent_used:.0f}% of quota used"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: #f59e0b;
                    color: white;
                    padding: 30px 20px;
                    border-radius: 12px 12px 0 0;
                    text-align: center;
                }}
                .content {{
                    background: #fffbeb;
                    padding: 30px 20px;
                    border-radius: 0 0 12px 12px;
                }}
                .warning-box {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #f59e0b;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⚠️ Storage Warning</h1>
            </div>
            <div class="content">
                <p>Hi {user_name},</p>

                <div class="warning-box">
                    <p><strong>You're using {percent_used:.1f}% of your storage quota</strong></p>
                    <p>{used_gb:.2f} GB of {quota_gb:.2f} GB used</p>
                </div>

                <p>Consider:</p>
                <ul>
                    <li>🗑️ Using the Duplicate Manager to remove duplicate photos</li>
                    <li>📥 Archiving old photos to free up space</li>
                    <li>🔍 Reviewing and deleting unwanted photos</li>
                </ul>

                <p style="margin-top: 20px; font-size: 14px; color: #92400e;">
                    This is a critical system notification and cannot be disabled.
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Storage Warning

        Hi {user_name},

        You're using {percent_used:.1f}% of your storage quota ({used_gb:.2f} GB of {quota_gb:.2f} GB).

        Consider using the Duplicate Manager or archiving old photos to free up space.

        This is a critical system notification and cannot be disabled.
        """

        return self.send_email(user_email, subject, html_body, text_body)
