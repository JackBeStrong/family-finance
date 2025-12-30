"""
Email sender using Gmail SMTP.

Supports:
- Plain text emails
- HTML emails
- Markdown emails (converted to HTML via 'markdown' library)
- Multiple recipients (comma-separated)

Configuration via environment variables:
- SMTP_SERVER: SMTP server hostname (default: smtp.gmail.com)
- SMTP_PORT: SMTP server port (default: 587)
- SMTP_PASSWORD: SMTP password (Gmail app password)
- SENDER_EMAIL: Sender email address
- RECEIVER_EMAIL: Recipient email address(es), comma-separated for multiple
"""

import os
import smtplib
import logging
import markdown
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Union

logger = logging.getLogger(__name__)


# Simple HTML wrapper for email styling
EMAIL_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2, h3 {{ color: #2c3e50; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f4f4f4; }}
        code {{ background-color: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background-color: #f4f4f4; padding: 12px; border-radius: 5px; overflow-x: auto; }}
    </style>
</head>
<body>
{body}
</body>
</html>"""


class EmailSender:
    """Gmail SMTP email sender with markdown support."""
    
    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_password: Optional[str] = None,
        sender_email: Optional[str] = None,
        receiver_email: Optional[str] = None
    ):
        self.smtp_server = smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD")
        self.sender_email = sender_email or os.environ.get("SENDER_EMAIL")
        self.receiver_email = receiver_email or os.environ.get("RECEIVER_EMAIL")
        
        if not self.smtp_password:
            raise ValueError("SMTP_PASSWORD environment variable is required")
        if not self.sender_email:
            raise ValueError("SENDER_EMAIL environment variable is required")
        if not self.receiver_email:
            raise ValueError("RECEIVER_EMAIL environment variable is required")
    
    def _parse_recipients(self, emails: Union[str, List[str]]) -> List[str]:
        """
        Parse recipient email(s) into a list.
        
        Supports:
        - Single email string
        - Comma-separated email string
        - List of emails
        """
        if isinstance(emails, list):
            return [e.strip() for e in emails if e.strip()]
        return [e.strip() for e in emails.split(',') if e.strip()]
    
    def send_email(
        self,
        subject: str,
        body: str,
        content_type: str = "plain",
        receiver_email: Optional[Union[str, List[str]]] = None
    ) -> bool:
        """
        Send an email via SMTP.
        
        Args:
            subject: Email subject line
            body: Email body content
            content_type: One of "plain", "html", or "markdown"
            receiver_email: Override default receiver(s) (optional), can be comma-separated
        
        Returns:
            True if email sent successfully, False otherwise
        """
        recipients = self._parse_recipients(receiver_email or self.receiver_email)
        
        logger.info(f"Sending email to {recipients}, subject: {subject}, type: {content_type}")
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender_email
            msg["To"] = ", ".join(recipients)  # Header shows all recipients
            
            if content_type == "markdown":
                # Convert markdown to HTML using the markdown library
                html_body = markdown.markdown(body, extensions=['tables', 'fenced_code', 'nl2br'])
                full_html = EMAIL_HTML_TEMPLATE.format(body=html_body)
                msg.attach(MIMEText(body, "plain"))  # Plain text fallback
                msg.attach(MIMEText(full_html, "html"))
            elif content_type == "html":
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))
            
            logger.info(f"Connecting to {self.smtp_server}:{self.smtp_port}")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.smtp_password)
                server.sendmail(self.sender_email, recipients, msg.as_string())
            
            logger.info(f"Email sent successfully to {len(recipients)} recipient(s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


def send_report_email(subject: str, body: str, content_type: str = "markdown") -> bool:
    """
    Convenience function to send a report email.
    Default content type is markdown since AI reports are typically in markdown.
    """
    sender = EmailSender()
    return sender.send_email(subject, body, content_type)
