"""寄信：EmailSender 介面、SMTP 實作與共用的 Email 版型（Jinja2）。

notifications.service 只依賴 `EmailSender` 介面；worker 使用 `SmtpEmailSender`，
測試以假物件替換，不會真的連線 SMTP。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from emails.message import Message
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str


class EmailSendError(Exception):
    """寄送失敗（SMTP 拒收、連線失敗等）。"""


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """寄出一封信；失敗時拋出例外。"""
        ...


def render_email(
    *, to: str, title: str, body: str, button_label: str, button_url: str
) -> EmailMessage:
    """共用版型：主旨＝標題，內文一段說明＋一個按鈕。"""
    html = _templates.get_template("email.html").render(
        title=title, body=body, button_label=button_label, button_url=button_url
    )
    return EmailMessage(to=to, subject=title, html=html)


class SmtpEmailSender:
    """以 `.env` 的 SMTP 設定寄信；寄件者名稱為 EMAILS_FROM_NAME（FLOW）。"""

    def send(self, message: EmailMessage) -> None:
        if not settings.emails_enabled:
            raise EmailSendError(
                "SMTP is not configured (SMTP_HOST / EMAILS_FROM_EMAIL)"
            )
        smtp: dict[str, object] = {
            "host": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "timeout": 10,
        }
        if settings.SMTP_TLS:
            smtp["tls"] = True
        elif settings.SMTP_SSL:
            smtp["ssl"] = True
        if settings.SMTP_USER:
            smtp["user"] = settings.SMTP_USER
        if settings.SMTP_PASSWORD:
            smtp["password"] = settings.SMTP_PASSWORD
        assert settings.EMAILS_FROM_EMAIL is not None
        mail = Message(
            subject=message.subject,
            html=message.html,
            mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
        )
        response = mail.send(to=message.to, smtp=smtp)
        if response is None or not response.success:
            error = getattr(response, "error", None)
            status = getattr(response, "status_code", None)
            raise EmailSendError(f"SMTP send failed (status={status}): {error!r}")
