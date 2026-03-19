import hashlib
import logging
import secrets
from html import escape

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _from_address() -> str:
    return f"The Campus <noreply@{settings.EMAIL_FROM_DOMAIN}>"


def generate_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Store only the hash in DB."""
    raw = secrets.token_urlsafe(32)
    return raw, _token_hash(raw)


def verify_token(raw: str, stored_hash: str) -> bool:
    return _token_hash(raw) == stored_hash


def send_verification_email(to_email: str, display_name: str, raw_token: str) -> None:
    if not settings.RESEND_API_KEY:
        # Dev mode: just print the link
        url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
        logger.warning("[DEV] Verification link for %s: %s", to_email, url)
        return

    resend.api_key = settings.RESEND_API_KEY
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"

    resend.Emails.send({
        "from": _from_address(),
        "to": to_email,
        "subject": "Подтвердите email — The Campus",
        "html": f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto">
          <h2>Привет, {escape(display_name)}!</h2>
          <p>Нажмите кнопку ниже, чтобы подтвердить ваш email-адрес.</p>
          <a href="{escape(verify_url)}"
             style="display:inline-block;padding:12px 24px;background:#059669;color:#fff;border-radius:6px;text-decoration:none;font-weight:600">
            Подтвердить email
          </a>
          <p style="color:#6b7280;font-size:13px;margin-top:16px">
            Ссылка действительна 24 часа. Если вы не регистрировались — проигнорируйте письмо.
          </p>
        </div>
        """,
    })


def send_password_reset_email(to_email: str, display_name: str, raw_token: str) -> None:
    if not settings.RESEND_API_KEY:
        url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
        logger.warning("[DEV] Password reset link for %s: %s", to_email, url)
        return

    resend.api_key = settings.RESEND_API_KEY
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

    resend.Emails.send({
        "from": _from_address(),
        "to": to_email,
        "subject": "Сброс пароля — The Campus",
        "html": f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto">
          <h2>Привет, {escape(display_name)}!</h2>
          <p>Вы запросили сброс пароля. Нажмите кнопку ниже:</p>
          <a href="{escape(reset_url)}"
             style="display:inline-block;padding:12px 24px;background:#059669;color:#fff;border-radius:6px;text-decoration:none;font-weight:600">
            Сбросить пароль
          </a>
          <p style="color:#6b7280;font-size:13px;margin-top:16px">
            Ссылка действительна 1 час. Если вы не запрашивали сброс — проигнорируйте письмо.
          </p>
        </div>
        """,
    })
