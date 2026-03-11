import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = "app/templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


async def send_email(subject: str, html_body: str, to: str | None = None):
    """Envia email via Gmail SMTP."""
    destinatario = to or settings.email_destinatario
    if not destinatario or not settings.gmail_user or not settings.gmail_app_password:
        logger.warning("Email não configurado — pulando envio")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.gmail_user
    msg["To"] = destinatario
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.gmail_user,
            password=settings.gmail_app_password,
            timeout=30,
        )
        logger.info(f"Email enviado: {subject} → {destinatario}")
        return True
    except Exception:
        logger.exception(f"Erro ao enviar email: {subject} → {destinatario}")
        return False


async def send_weekly_report(data: dict):
    """Envia relatório semanal formatado em HTML."""
    try:
        template = env.get_template("relatorio_semanal.html")
        html = template.render(**data)
        return await send_email("📊 Relatório Semanal — Portfólio de Investimentos", html)
    except Exception:
        logger.exception("Erro ao renderizar relatório semanal")
        return False
