"""Outgoing mail.

SMTP rather than a provider SDK, because it works with whatever host a
self-hosted deployment already has. When SMTP_HOST is unset the message is
logged instead of sent: development needs the reset link somewhere visible,
and an operator who has not configured mail should see that plainly rather
than discover it from a user who never got their email.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    message = EmailMessage()
    name, address = parseaddr(settings.SMTP_FROM)
    message["From"] = formataddr((name, address)) if name else address
    message["To"] = to
    message["Subject"] = subject
    # Plain text first, HTML as the alternative -- a reset link has to survive
    # a client that refuses to render HTML.
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def send(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Returns True when the message was handed to an SMTP server.

    Never raises: a caller decides what to tell the user, and for password
    reset the answer is the same either way so the endpoint cannot be used to
    probe whether an address exists.
    """
    if not settings.email_configured:
        logger.warning(
            "SMTP is not configured; email not sent.\n--- %s -> %s ---\n%s\n---",
            subject,
            to,
            text,
        )
        return False

    message = _build(to, subject, text, html)
    try:
        if settings.SMTP_PORT == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
            )
        with server:
            if settings.SMTP_STARTTLS and settings.SMTP_PORT != 465:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        logger.info("Sent %r to %s", subject, to)
        return True
    except Exception:
        # Logged with the exception, but never re-raised to the request.
        logger.exception("Could not send %r to %s", subject, to)
        return False


def password_reset_email(
    *, to: str, full_name: str, shop_name: str | None, reset_url: str, ttl_minutes: int
) -> tuple[str, str, str]:
    """Subject, plain text, HTML."""
    where = f" for {shop_name}" if shop_name else ""
    subject = f"Reset your password{where}"

    text = f"""Hello {full_name},

Someone asked to reset the password for your account{where}.

Open this link to choose a new one. It expires in {ttl_minutes} minutes and
can only be used once:

{reset_url}

If it wasn't you, ignore this email -- your password has not changed. Nobody
can use this link without opening it.
"""

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f6f5;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#111">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:32px">
    <h1 style="margin:0 0 16px;font-size:20px">Reset your password</h1>
    <p style="margin:0 0 16px;line-height:1.6">Hello {full_name},</p>
    <p style="margin:0 0 24px;line-height:1.6">
      Someone asked to reset the password for your account{where}.
    </p>
    <a href="{reset_url}"
       style="display:inline-block;background:#0d9488;color:#fff;text-decoration:none;
              padding:12px 24px;border-radius:8px;font-weight:600">Choose a new password</a>
    <p style="margin:24px 0 0;line-height:1.6;font-size:14px;color:#555">
      The link expires in {ttl_minutes} minutes and works once.
    </p>
    <p style="margin:16px 0 0;line-height:1.6;font-size:14px;color:#555">
      If it wasn't you, ignore this email — your password has not changed.
    </p>
    <p style="margin:24px 0 0;font-size:12px;color:#888;word-break:break-all">
      Or paste this into your browser:<br>{reset_url}
    </p>
  </div>
</body></html>"""

    return subject, text, html
