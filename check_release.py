import os
import smtplib
import requests
from email.mime.text import MIMEText

URL = "https://us.jellycat.com/amuseables-birthday-cake-bag-charm/"
STATE_FILE = "status.txt"
COMING_SOON_MARKER = "Coming Soon!"


def get_current_status() -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JellycatWatcher/1.0)"}
    resp = requests.get(URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return "coming_soon" if COMING_SOON_MARKER in resp.text else "available"


def read_last_status() -> str | None:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return None


def write_status(status: str) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(status)


def send_email(subject: str, body: str) -> None:
    smtp_server = os.environ["SMTP_SERVER"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email_to

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [email_to], msg.as_string())


def main() -> None:
    current_status = get_current_status()
    last_status = read_last_status()

    print(f"Last status: {last_status} | Current status: {current_status}")

    if current_status == "available" and last_status != "available":
        send_email(
            subject="It's here! Jellycat Birthday Cake Bag Charm is available",
            body=f"The bag charm just went live:\n{URL}",
        )
        print("Notification email sent.")

    write_status(current_status)


if __name__ == "__main__":
    main()
