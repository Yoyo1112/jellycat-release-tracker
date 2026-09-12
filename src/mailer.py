"""Send the digest through Gmail's SMTP using an app password.

Recipients go in Bcc so that the people on the list cannot see each other's
addresses; the visible To: is the sending account itself.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


class MailConfigError(RuntimeError):
    """Raised when the Gmail credentials or recipient list are missing."""


def load_config() -> tuple[str, str, list[str]]:
    user = (os.environ.get("GMAIL_USER") or "").strip()
    # Google prints app passwords in groups of four; spaces are not part of it.
    password = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
    recipients = [
        address.strip()
        for address in (os.environ.get("MAIL_TO") or "").replace(";", ",").split(",")
        if address.strip()
    ]

    missing = [
        name
        for name, value in (
            ("GMAIL_USER", user),
            ("GMAIL_APP_PASSWORD", password),
            ("MAIL_TO", recipients),
        )
        if not value
    ]
    if missing:
        raise MailConfigError(f"缺少環境變數：{', '.join(missing)}")

    return user, password, recipients


def send(subject: str, text_body: str, html_body: str) -> list[str]:
    """Send one digest.  Returns the recipient list that was used."""
    user, password, recipients = load_config()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"Jellycat Tracker <{user}>"
    message["To"] = user
    message["Bcc"] = ", ".join(recipients)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)

    return recipients
