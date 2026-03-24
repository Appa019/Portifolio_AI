"""Mesa Crypto Group Bot — Team debate for crypto assets.

Same pattern as Mesa B3 but with crypto-specific agents and commands.

Commands (in group):
  /analise         — Run Crypto team analysis
  /moeda bitcoin   — Deep dive on a specific crypto
  Free text        — Ask the team (Head responds)
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.agents.personas import get_persona
from app.config import settings
from app.telegram.bot_base import log_conversation
from app.telegram.debate_orchestrator import detect_divergences
from app.telegram.formatters import escape_md
from app.telegram.group_broadcaster import GroupBroadcaster

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mesa-crypto")


def create_mesa_crypto_bot(db_factory) -> Application | None:
    """Create the Mesa Crypto group bot."""
    token = settings.telegram_mesa_crypto_token
    if not token:
        logger.info("[telegram] Mesa Crypto bot token not configured, skipping")
        return None

    app = Application.builder().token(token).build()

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 *Mesa Crypto — Equipe de Criptoativos*\n\n"
            "Esta é a mesa de operações de crypto\\.\n"
            "Aqui a equipe inteira debate e analisa o mercado\\.\n\n"
            "Comandos:\n"
            "/analise — Análise completa da equipe\n"
            "/moeda bitcoin — Deep dive em uma crypto\n\n"
            "Ou envie mensagem para a equipe\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def cmd_analise(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action(ChatAction.TYPING)
        chat_id = settings.telegram_mesa_crypto_chat_id or update.effective_chat.id

        broadcaster = GroupBroadcaster(context.bot, chat_id)
        await broadcaster.send_phase_header(2, "Análise Crypto")

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            _executor, partial(_run_crypto_team_analysis, db_factory)
        )

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
        head_result = results.get("head_crypto", "")
        if not head_result:
            head_result = _summarize_results(results)
        await broadcaster.send_agent_message("head_crypto", head_result)

        log_conversation(db_factory, update.effective_chat.id, "mesa_crypto", "head_crypto",
                         "/analise", str(results.keys()))

    async def cmd_moeda(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Uso: /moeda bitcoin")
            return

        crypto_id = context.args[0].strip().lower()
        await update.message.reply_chat_action(ChatAction.TYPING)

        chat_id = settings.telegram_mesa_crypto_chat_id or update.effective_chat.id
        broadcaster = GroupBroadcaster(context.bot, chat_id)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_run_crypto_deep_dive, db_factory, crypto_id)
        )

        analyst_name = f"crypto_analyst_{crypto_id}"
        await broadcaster.send_agent_message(analyst_name, result)

        log_conversation(db_factory, update.effective_chat.id, "mesa_crypto",
                         analyst_name, f"/moeda {crypto_id}", result[:4000])

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_text = update.message.text
        await update.message.reply_chat_action(ChatAction.TYPING)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, partial(_chat_with_head_crypto, db_factory, user_text)
        )

        chat_id = settings.telegram_mesa_crypto_chat_id or update.effective_chat.id
        broadcaster = GroupBroadcaster(context.bot, chat_id)
        await broadcaster.send_agent_message("head_crypto", result)

        log_conversation(db_factory, update.effective_chat.id, "mesa_crypto", "head_crypto",
                         user_text, result[:4000])

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("analise", cmd_analise))
    app.add_handler(CommandHandler("moeda", cmd_moeda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


# === Sync runners ===

def _run_crypto_team_analysis(db_factory) -> dict[str, str]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from app.agents.crypto_team.fundamentalista_crypto import FundamentalistaCrypto
    from app.agents.crypto_team.tecnico_crypto import TecnicoCrypto
    from app.agents.crypto_team.onchain_analyst import OnChainAnalyst
    from app.agents.crypto_team.risk_crypto import RiskCrypto
    from app.agents.crypto_team.trade_crypto import TradeCrypto
    from app.services.portfolio_service import get_portfolio_summary

    db = db_factory()
    try:
        summary = get_portfolio_summary(db)
        context = json.dumps(summary, ensure_ascii=False, default=str)[:1000]
    finally:
        db.close()

    cryptos = ["bitcoin", "ethereum", "solana", "chainlink"]

    tasks = {
        "fundamentalista_crypto": (FundamentalistaCrypto, lambda a: a.analyze(cryptos, context)),
        "tecnico_crypto": (TecnicoCrypto, lambda a: a.analyze(cryptos, context)),
        "onchain_analyst": (OnChainAnalyst, lambda a: a.analyze(cryptos, context)),
        "risk_crypto": (RiskCrypto, lambda a: a.analyze(context)),
        "trade_crypto": (TradeCrypto, lambda a: a.analyze(cryptos, context)),
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
                logger.exception(f"[mesa_crypto] {key} falhou")
                results[key] = json.dumps({"erro": str(e)})

    return results


def _run_crypto_deep_dive(db_factory, crypto_id: str) -> str:
    from app.agents.crypto_analyst import CryptoAnalyst
    db = db_factory()
    try:
        analyst = CryptoAnalyst(db, crypto_id)
        return analyst.analyze(crypto_id, "Deep dive solicitado via Telegram")
    finally:
        db.close()


def _chat_with_head_crypto(db_factory, user_text: str) -> str:
    from app.agents.crypto_agent import CryptoAgent
    db = db_factory()
    try:
        agent = CryptoAgent(db)
        return agent.call_model(user_text)
    finally:
        db.close()


def _summarize_results(results: dict[str, str]) -> str:
    parts = []
    for agent, result in results.items():
        persona = get_persona(agent)
        name = persona.display_name if persona else agent
        try:
            data = json.loads(result)
            resumo = data.get("resumo_executivo", result[:200])
        except (json.JSONDecodeError, TypeError):
            resumo = result[:200]
        parts.append(f"• {name}: {resumo}")
    return "Consolidação da equipe:\n" + "\n".join(parts)
