"""Mesa B3 Group Bot — Team debate for B3 equities.

A single bot posts messages on behalf of all B3 team members, each with
their own persona (name, emoji, voice tone). Supports debates when agents disagree.

Commands (in group):
  /analise        — Run B3 team analysis
  /ticker PETR4   — Deep dive on a specific stock
  Free text       — Ask the team (Head responds, may call specialists)
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from telegram import Bot, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.agents.personas import get_persona
from app.config import settings
from app.telegram.bot_base import log_conversation, start_bot_polling
from app.telegram.debate_orchestrator import detect_divergences, generate_rebuttal_prompt
from app.telegram.formatters import escape_md
from app.telegram.group_broadcaster import GroupBroadcaster

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mesa-b3")


def create_mesa_b3_bot(db_factory) -> Application | None:
    """Create the Mesa B3 group bot."""
    token = settings.telegram_mesa_b3_token
    if not token:
        logger.info("[telegram] Mesa B3 bot token not configured, skipping")
        return None

    app = Application.builder().token(token).build()

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 *Mesa B3 — Equipe de Ações*\n\n"
            "Esta é a mesa de operações de ações B3\\.\n"
            "Aqui a equipe inteira debate e analisa o mercado\\.\n\n"
            "Comandos:\n"
            "/analise — Análise completa da equipe\n"
            "/ticker PETR4 — Deep dive em um ticker\n\n"
            "Ou envie mensagem para a equipe\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def cmd_analise(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action(ChatAction.TYPING)
        chat_id = settings.telegram_mesa_b3_chat_id or update.effective_chat.id

        broadcaster = GroupBroadcaster(context.bot, chat_id)
        await broadcaster.send_phase_header(2, "Análise B3")

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            _executor, partial(_run_b3_team_analysis, db_factory)
        )

        # Broadcast each agent's result
        for agent_name, result in results.items():
            await broadcaster.send_agent_message(agent_name, result)

        # Check for debates
        divergences = detect_divergences(results)
        if divergences:
            await broadcaster.send_debate_header()
            for d in divergences:
                persona_a = get_persona(d.agent_a)
                persona_b = get_persona(d.agent_b)
                debate_msg = (
                    f"💥 {d.asset}: {persona_a.display_name if persona_a else d.agent_a} "
                    f"diz {d.position_a.upper()}, "
                    f"{persona_b.display_name if persona_b else d.agent_b} "
                    f"diz {d.position_b.upper()}"
                )
                safe = escape_md(debate_msg)
                await context.bot.send_message(
                    chat_id=chat_id, text=safe,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                await asyncio.sleep(1.0)

        # Head conclusion
        head_persona = get_persona("head_b3")
        head_result = results.get("head_b3", "")
        if not head_result:
            head_result = _summarize_results(results)
        await broadcaster.send_agent_message("head_b3", head_result)

        log_conversation(db_factory, update.effective_chat.id, "mesa_b3", "head_b3",
                         "/analise", str(results.keys()))

    async def cmd_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /ticker PETR4")
            return

        ticker = context.args[0].strip().upper()
        await update.message.reply_chat_action(ChatAction.TYPING)

        chat_id = settings.telegram_mesa_b3_chat_id or update.effective_chat.id
        broadcaster = GroupBroadcaster(context.bot, chat_id)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_ticker_deep_dive, db_factory, ticker)
        )

        # Post as the N3 analyst
        analyst_name = f"ticker_analyst_{ticker}"
        await broadcaster.send_agent_message(analyst_name, result)

        log_conversation(db_factory, update.effective_chat.id, "mesa_b3",
                         analyst_name, f"/ticker {ticker}", result[:4000])

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Free text — Head B3 responds."""
        user_text = update.message.text
        await update.message.reply_chat_action(ChatAction.TYPING)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_chat_with_head_b3, db_factory, user_text)
        )

        chat_id = settings.telegram_mesa_b3_chat_id or update.effective_chat.id
        broadcaster = GroupBroadcaster(context.bot, chat_id)
        await broadcaster.send_agent_message("head_b3", result)

        log_conversation(db_factory, update.effective_chat.id, "mesa_b3", "head_b3",
                         user_text, result[:4000])

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("analise", cmd_analise))
    app.add_handler(CommandHandler("ticker", cmd_ticker))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


# === Sync runners ===

def _run_b3_team_analysis(db_factory) -> dict[str, str]:
    """Run B3 team specialists and return results keyed by agent_name."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from app.agents.b3_team.fundamentalista_b3 import FundamentalistaB3
    from app.agents.b3_team.setorial_b3 import SetorialB3
    from app.agents.b3_team.tecnico_b3 import TecnicoB3
    from app.agents.b3_team.risk_b3 import RiskB3
    from app.agents.b3_team.trade_b3 import TradeB3
    from app.services.portfolio_service import get_portfolio_summary

    db = db_factory()
    try:
        summary = get_portfolio_summary(db)
        context = json.dumps(summary, ensure_ascii=False, default=str)[:1000]
    finally:
        db.close()

    # Default tickers for analysis
    tickers = ["PETR4", "VALE3", "ITUB4", "WEGE3", "BBDC4"]

    tasks = {
        "fundamentalista_b3": (FundamentalistaB3, lambda a: a.analyze(tickers, context)),
        "tecnico_b3": (TecnicoB3, lambda a: a.analyze(tickers, context)),
        "setorial_b3": (SetorialB3, lambda a: a.analyze(context)),
        "risk_b3": (RiskB3, lambda a: a.analyze(context)),
        "trade_b3": (TradeB3, lambda a: a.analyze(tickers, context)),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        for key, (cls, fn) in tasks.items():
            def run(agent_cls=cls, run_fn=fn):
                agent_db = db_factory()
                try:
                    agent = agent_cls(agent_db)
                    return run_fn(agent)
                finally:
                    agent_db.close()

            futures[pool.submit(run)] = key

        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                logger.exception(f"[mesa_b3] {key} falhou")
                results[key] = json.dumps({"erro": str(e)})

    return results


def _run_ticker_deep_dive(db_factory, ticker: str) -> str:
    from app.agents.ticker_analyst import TickerAnalyst
    db = db_factory()
    try:
        analyst = TickerAnalyst(db, ticker)
        return analyst.analyze(ticker, "Deep dive solicitado via Telegram")
    finally:
        db.close()


def _chat_with_head_b3(db_factory, user_text: str) -> str:
    from app.agents.b3_agent import B3Agent
    db = db_factory()
    try:
        agent = B3Agent(db)
        return agent.call_model(user_text)
    finally:
        db.close()


def _summarize_results(results: dict[str, str]) -> str:
    """Create a summary when head didn't run separately."""
    parts = []
    for agent, result in results.items():
        persona = get_persona(agent)
        name = persona.display_name if persona else agent
        # Try to get resumo_executivo
        try:
            data = json.loads(result)
            resumo = data.get("resumo_executivo", result[:200])
        except (json.JSONDecodeError, TypeError):
            resumo = result[:200]
        parts.append(f"• {name}: {resumo}")
    return "Consolidação da equipe:\n" + "\n".join(parts)
