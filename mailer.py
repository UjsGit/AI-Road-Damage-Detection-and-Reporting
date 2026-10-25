"""
Email delivery utility for Pothole Detection & Municipal Reporting.
Uses Python standard library (smtplib + email.message.EmailMessage).
"""

import os
import smtplib
import socket
import logging
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger("pothole_mailer")


def get_smtp_config():
    """Retrieve SMTP settings from environment variables."""
    server = os.environ.get("SMTP_SERVER", "").strip()
    port_str = os.environ.get("SMTP_PORT", "587").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "true").strip().lower() in ("true", "1", "yes")
    use_ssl = os.environ.get("SMTP_USE_SSL", "false").strip().lower() in ("true", "1", "yes")

    sender_email = os.environ.get("SMTP_SENDER_EMAIL", "").strip() or username or "no-reply@city.gov.in"
    sender_name = os.environ.get("SMTP_SENDER_NAME", "").strip() or "Pothole Detection Municipal Portal"

    return {
        "server": server,
        "port": port,
        "username": username,
        "password": password,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "sender_email": sender_email,
        "sender_name": sender_name,
    }


def is_smtp_configured() -> bool:
    """Check if minimum SMTP server configuration is present."""
    config = get_smtp_config()
    return bool(config["server"])


def send_resolution_email(
    recipient_email: str,
    recipient_name: str,
    report_id: int,
    location: str = None,
    notes: str = None
) -> tuple[bool, str]:
    """
    Send an email notifying the citizen reporter that their report has been Resolved.

    Returns:
        tuple (success: bool, message: str)
    """
    if not recipient_email or "@" not in recipient_email:
        return False, "Recipient email is invalid or missing."

    config = get_smtp_config()
    if not config["server"]:
        return False, "SMTP server is not configured."

    display_name = recipient_name.strip() if recipient_name else "Citizen"
    loc_display = location.strip() if location else "Recorded GPS Coordinates"
    notes_display = notes.strip() if notes else "Road maintenance and repair work verified."

    msg = EmailMessage()
    msg["Subject"] = f"[RESOLVED] Road Damage Report #{report_id} - Municipal Action Completed"
    msg["From"] = formataddr((config["sender_name"], config["sender_email"]))
    msg["To"] = recipient_email

    # Plain text version
    text_content = f"""Dear {display_name},

Good news! Your reported road damage issue has been inspected and marked as Resolved by the municipal maintenance team.

Report Summary:
- Report ID: #{report_id}
- Location: {loc_display}
- Status: Resolved
- Resolution Notes: {notes_display}

You can view before-and-after photographic repair verification and track your reported issues in your citizen portal:
/my-reports

Thank you for reporting road hazards and helping keep our streets safe.

Sincerely,
{config['sender_name']}
"""

    # HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 24px; color: #212529; }}
  .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #dfe3e8; overflow: hidden; }}
  .header {{ background: #198754; color: #ffffff; padding: 20px 24px; }}
  .header h1 {{ margin: 0; font-size: 20px; }}
  .body {{ padding: 24px; }}
  .badge {{ display: inline-block; background: #d1e7dd; color: #0f5132; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 13px; }}
  .details {{ background: #fafbfc; border: 1px solid #dfe3e8; border-radius: 6px; padding: 16px; margin: 20px 0; }}
  .details-row {{ margin-bottom: 8px; font-size: 14px; }}
  .details-row strong {{ color: #111827; }}
  .footer {{ padding: 16px 24px; font-size: 12px; color: #667085; border-top: 1px solid #dfe3e8; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>Road Hazard Resolved</h1>
  </div>
  <div class="body">
    <p>Dear <strong>{display_name}</strong>,</p>
    <p>We are pleased to inform you that your road damage report has been inspected and marked as <span class="badge">Resolved</span> by the municipal engineering team.</p>
    
    <div class="details">
      <div class="details-row"><strong>Report ID:</strong> #{report_id}</div>
      <div class="details-row"><strong>Location:</strong> {loc_display}</div>
      <div class="details-row"><strong>Status:</strong> Resolved</div>
      <div class="details-row"><strong>Notes:</strong> {notes_display}</div>
    </div>
    
    <p>You can sign in to your citizen portal to review photographic repair proof and track all your submissions.</p>
    <p>Thank you for partnering with the municipal administration to improve road safety.</p>
  </div>
  <div class="footer">
    {config['sender_name']} &bull; Automated Municipal Notification
  </div>
</div>
</body>
</html>
"""

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    try:
        timeout = 10
        if config["use_ssl"]:
            server_conn = smtplib.SMTP_SSL(config["server"], config["port"], timeout=timeout)
        else:
            server_conn = smtplib.SMTP(config["server"], config["port"], timeout=timeout)

        with server_conn:
            if config["use_tls"] and not config["use_ssl"]:
                server_conn.starttls()

            if config["username"] and config["password"]:
                server_conn.login(config["username"], config["password"])

            server_conn.send_message(msg)

        logger.info("Resolution notification email accepted by SMTP server for report #%s to %s", report_id, recipient_email)
        return True, "Email notification accepted by mail server."

    except (smtplib.SMTPException, socket.timeout, OSError) as exc:
        logger.exception("Failed to send resolution email for report #%s: %s", report_id, exc)
        return False, f"SMTP delivery failed: {type(exc).__name__}"
