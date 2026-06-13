"""
Minimal SMTP mailer for password-reset emails.

Reads SMTP_* settings from config. If SMTP_HOST is blank, email is considered
disabled and send_email() returns False without raising -- callers then fall back
to the super-admin-issued reset code.
"""

import smtplib
from email.message import EmailMessage

import config


def email_enabled():
    return bool(getattr(config, 'SMTP_HOST', '').strip())


def send_email(to_address, subject, body, html_body=None):
    """Send an email. Returns True on success, False if disabled/failed.
    If html_body is given, it's added as an HTML alternative (plain `body` is the fallback)."""
    if not email_enabled():
        return False
    if not to_address:
        return False

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = config.SMTP_FROM
    msg['To'] = to_address
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(config.SMTP_HOST, int(config.SMTP_PORT), timeout=20) as server:
            if getattr(config, 'SMTP_USE_TLS', False):
                server.starttls()
            if getattr(config, 'SMTP_USER', ''):
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"Warning: failed to send email to {to_address}: {exc}", flush=True)
        return False


def send_password_reset(to_address, reset_url):
    subject = "Overall Programs Dashboard - password reset"
    ttl = config.RESET_TOKEN_TTL_MINUTES
    # Plain-text fallback (for clients that don't render HTML).
    body = (
        "A password reset was requested for your Overall Programs Dashboard account.\n\n"
        f"Reset your password using this link (valid for {ttl} minutes):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    # HTML version: a clickable button — the URL/token live in the href, not shown as text.
    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Segoe UI,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1);">
        <tr><td style="background:#1e3a5f;padding:20px 28px;color:#ffffff;font-size:18px;font-weight:600;">
          📊 Overall Programs Dashboard
        </td></tr>
        <tr><td style="padding:28px;color:#1a202c;font-size:14px;line-height:1.6;">
          <p style="margin:0 0 16px;">A password reset was requested for your account.</p>
          <p style="margin:0 0 24px;">Click the button below to choose a new password.
             This link is valid for {ttl} minutes.</p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
            <tr><td align="center" bgcolor="#2c5282" style="border-radius:8px;background:#2c5282;">
              <a href="{reset_url}" target="_blank"
                 style="display:inline-block;padding:12px 28px;background:#2c5282;color:#ffffff;
                        text-decoration:none;font-size:15px;font-weight:600;border-radius:8px;">Reset My Password</a>
            </td></tr>
          </table>
          <p style="margin:0;color:#718096;font-size:12px;">
             If you didn't request this, you can safely ignore this email.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return send_email(to_address, subject, body, html_body=html_body)
