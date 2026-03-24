"""Base infrastructure for Telegram bots.

Provides shared patterns: polling setup, command registration,
message logging to DB, and async-to-sync bridge for agents.
"""

import asyncio
import logging
import threading
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.config import settings
from app.models.db_models import TelegramConversation

logger = logging.getLogger(__name__)


def log_conversation(
    db_factory,
    chat_id: int,
    bot_type: str,
    agent_name: str,
    message_text: str,
    response_text: str,
    cost_usd: float = 0.0,
):
    """Save a Telegram conversation turn to the database."""
    db = db_factory()
    try:
        entry = TelegramConversation(
            chat_id=chat_id,
            bot_type=bot_type,
            agent_name=agent_name,
            message_text=message_text[:2000],
            response_text=response_text[:4000],
            cost_usd=cost_usd,
            created_at=datetime.now(),
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"[telegram] Falha ao salvar conversa ({bot_type}/{agent_name})")
    finally:
        db.close()


def run_agent_sync(agent_cls, db_factory, user_input: str, agent_kwargs: dict | None = None) -> str:
    """Instantiate and run an agent synchronously (for use in async handlers).

    Creates a fresh DB session, runs the agent's call_model, and returns the result.
    """
    db = db_factory()
    try:
        kwargs = agent_kwargs or {}
        agent = agent_cls(db, **kwargs)
        return agent.call_model(user_input)
    except Exception:
        logger.exception(f"[telegram] Agent {agent_cls.agent_name} falhou")
        return "Desculpe, ocorreu um erro ao processar sua mensagem."
    finally:
        db.close()


def start_bot_polling(token: str, app: Application, bot_name: str):
    """Start a Telegram bot in a daemon thread with its own event loop."""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info(f"[telegram] Bot {bot_name} iniciando polling...")
        try:
            loop.run_until_complete(app.initialize())
            loop.run_until_complete(app.start())
            loop.run_until_complete(app.updater.start_polling(drop_pending_updates=True))
            logger.info(f"[telegram] Bot {bot_name} polling ativo")
            loop.run_forever()
        except Exception:
            logger.exception(f"[telegram] Bot {bot_name} falhou")
        finally:
            loop.close()

    thread = threading.Thread(target=_run, name=f"telegram-{bot_name}", daemon=True)
    thread.start()
    return thread
