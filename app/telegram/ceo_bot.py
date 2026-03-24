"""CEO Bot — Private chat with Carlos Mendonça (CIO).

Commands:
  /start     — Welcome message
  /analise   — Trigger full Goldman Sachs analysis pipeline
  /portfolio — Portfolio summary
  /risco     — Request risk report from CRO
  /aporte N  — How to allocate N reais
  /custos    — Token costs summary
  Free text  — Chat with the CIO
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import settings
from app.telegram.bot_base import log_conversation, start_bot_polling
from app.telegram.formatters import escape_md

logger = logging.getLogger(__name__)

# Thread pool for running sync agents from async handlers
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ceo-bot")


def create_ceo_bot(db_factory) -> Application | None:
    """Create and configure the CEO bot. Returns None if token not set."""
    token = settings.telegram_ceo_token
    if not token:
        logger.info("[telegram] CEO bot token not configured, skipping")
        return None

    app = Application.builder().token(token).build()

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🏛️ *Carlos Mendonça \\— CIO*\n\n"
            "Bem\\-vindo\\. Sou o Chief Investment Officer da sua gestora\\.\n\n"
            "Comandos disponíveis:\n"
            "/analise — Análise completa Goldman Sachs\n"
            "/portfolio — Resumo do portfólio\n"
            "/risco — Relatório de risco\n"
            "/aporte N — Como alocar R$N\n"
            "/custos — Custos de tokens\n\n"
            "Ou envie qualquer mensagem para conversar\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def cmd_analise(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action(ChatAction.TYPING)
        await update.message.reply_text(
            "🏛️ Iniciando análise completa\\. As equipes serão acionadas e os "
            "resultados aparecerão nos grupos Mesa B3 e Mesa Crypto\\.\n\n"
            "Isso pode levar alguns minutos\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_full_analysis, db_factory)
        )

        safe = escape_md(result[:3500])
        await update.message.reply_text(
            f"🏛️ *Carlos Mendonça \\— Decisão Final*\n\n{safe}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        log_conversation(db_factory, update.effective_chat.id, "ceo", "cio",
                         "/analise", result[:4000])

    async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action(ChatAction.TYPING)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_portfolio, db_factory)
        )
        safe = escape_md(result[:3500])
        await update.message.reply_text(
            f"🏛️ *Portfólio Atual*\n\n{safe}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def cmd_risco(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action(ChatAction.TYPING)
        await update.message.reply_text(
            "🛡️ Consultando Fernando Rocha \\(CRO\\)\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_risk, db_factory)
        )
        safe = escape_md(result[:3500])
        await update.message.reply_text(
            f"🛡️ *Fernando Rocha \\— CRO*\n\n{safe}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        log_conversation(db_factory, update.effective_chat.id, "ceo", "cro",
                         "/risco", result[:4000])

    async def cmd_aporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /aporte 10000")
            return
        try:
            valor = float(context.args[0].replace(",", "."))
        except ValueError:
            await update.message.reply_text("Valor inválido\\. Uso: /aporte 10000",
                                            parse_mode=ParseMode.MARKDOWN_V2)
            return

        await update.message.reply_chat_action(ChatAction.TYPING)
        await update.message.reply_text(
            f"🏛️ Analisando aporte de R${escape_md(f'{valor:,.2f}')}\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_aporte, db_factory, valor)
        )
        safe = escape_md(result[:3500])
        await update.message.reply_text(
            f"🏛️ *Carlos Mendonça \\— Aporte*\n\n{safe}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        log_conversation(db_factory, update.effective_chat.id, "ceo", "cio",
                         f"/aporte {valor}", result[:4000])

    async def cmd_custos(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action(ChatAction.TYPING)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_custos, db_factory)
        )
        safe = escape_md(result[:3500])
        await update.message.reply_text(
            f"💰 *Custos de Tokens*\n\n{safe}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Free-text conversation with CIO."""
        user_text = update.message.text
        await update.message.reply_chat_action(ChatAction.TYPING)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_chat_with_cio, db_factory, user_text)
        )
        safe = escape_md(result[:3500])
        await update.message.reply_text(
            f"🏛️ *Carlos Mendonça*\n\n{safe}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        log_conversation(db_factory, update.effective_chat.id, "ceo", "cio",
                         user_text, result[:4000])

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("analise", cmd_analise))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("risco", cmd_risco))
    app.add_handler(CommandHandler("aporte", cmd_aporte))
    app.add_handler(CommandHandler("custos", cmd_custos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


# === Sync agent runners (executed in thread pool) ===

def _run_full_analysis(db_factory) -> str:
    from app.agents.analysis_pipeline import AnalysisPipeline
    pipeline = AnalysisPipeline(db_factory, trigger="telegram")
    return pipeline.run_full()


def _run_portfolio(db_factory) -> str:
    from app.services.portfolio_service import get_portfolio_summary, get_portfolio_assets
    db = db_factory()
    try:
        summary = get_portfolio_summary(db)
        assets = get_portfolio_assets(db)
        return json.dumps({"resumo": summary, "ativos": assets}, ensure_ascii=False, default=str, indent=2)
    finally:
        db.close()


def _run_risk(db_factory) -> str:
    from app.agents.cro import ChiefRiskOfficer
    db = db_factory()
    try:
        cro = ChiefRiskOfficer(db)
        return cro.analyze()
    finally:
        db.close()


def _run_aporte(db_factory, valor: float) -> str:
    from app.agents.orchestrator import Orchestrator
    db = db_factory()
    try:
        cio = Orchestrator(db)
        return cio.run_aporte_analysis(valor)
    finally:
        db.close()


def _run_custos(db_factory) -> str:
    from app.services.token_cost import calculate_cost_usd
    from app.models.db_models import CustoToken
    from sqlalchemy import func
    db = db_factory()
    try:
        rows = (
            db.query(
                CustoToken.agente,
                func.sum(CustoToken.custo_usd).label("total_usd"),
                func.sum(CustoToken.custo_brl).label("total_brl"),
                func.count().label("calls"),
            )
            .group_by(CustoToken.agente)
            .order_by(func.sum(CustoToken.custo_usd).desc())
            .all()
        )
        lines = ["Agente | USD | BRL | Calls"]
        for r in rows:
            lines.append(f"{r.agente} | ${r.total_usd:.4f} | R${r.total_brl:.4f} | {r.calls}")
        return "\n".join(lines) if lines else "Sem custos registrados."
    finally:
        db.close()


def _chat_with_cio(db_factory, user_text: str) -> str:
    from app.agents.orchestrator import Orchestrator
    db = db_factory()
    try:
        cio = Orchestrator(db)
        return cio.call_model(user_text)
    finally:
        db.close()
