"""
Sends verification and password-reset emails. If SMTP_HOST is blank
(config.py), emails are logged instead of sent — so signup/reset flows
work end to end in local dev without any mail server, and you can copy
the link straight out of the console.
"""
import smtplib
from email.message import EmailMessage

from config import (
    PUBLIC_BASE_URL,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)
from logging_config import logger

SMTP_CONFIGURED = bool(SMTP_HOST)


def _send(to_email: str, subject: str, body: str) -> None:
    if not SMTP_CONFIGURED:
        logger.info(f"[DEV EMAIL — SMTP not configured] To: {to_email} | {subject}\n{body}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def send_verification_email(to_email: str, code: str) -> None:
    _send(
        to_email,
        "Your AI Analyst verification code",
        f"Welcome to AI Analyst!\n\nYour verification code is: {code}\n\n"
        f"Enter this code in the app to verify your email. It expires shortly. "
        f"If you didn't sign up, ignore this email.",
    )


def send_password_reset_email(to_email: str, token: str) -> None:
    link = f"{PUBLIC_BASE_URL}/auth/reset-password?token={token}"
    _send(
        to_email,
        "Reset your AI Analyst password",
        f"Someone (hopefully you) requested a password reset.\n\n"
        f"Reset your password by visiting:\n{link}\n\n"
        f"This link expires shortly. If you didn't request this, ignore this email — "
        f"your password won't change.",
    )
