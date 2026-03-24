"""GroupBroadcaster — Posts agent messages to Telegram groups with persona formatting.

Sends messages sequentially with typing delays to simulate a real trading floor discussion.
"""

import asyncio
import logging
import random

from telegram import Bot
from telegram.constants import ChatAction, ParseMode

from app.agents.personas import get_persona
from app.telegram.formatters import escape_md, truncate_for_telegram

logger = logging.getLogger(__name__)


class GroupBroadcaster:
    """Broadcasts agent analysis results to a Telegram group chat."""

    def __init__(self, bot: Bot, chat_id: int | str):
        self.bot = bot
        self.chat_id = chat_id

    async def send_agent_message(self, agent_name: str, message: str, delay: bool = True):
        """Send a message formatted with the agent's persona."""
        persona = get_persona(agent_name)
        if not persona:
            logger.warning(f"[broadcaster] No persona for {agent_name}")
            return

        # Simulate typing
        if delay:
            await self.bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(random.uniform(1.5, 3.0))

        # Format message with persona
        header = f"{persona.emoji} *{escape_md(persona.display_name)}* \\({escape_md(persona.cargo)}\\)"

        # Clean and truncate body
        body = message.strip()
        # Try to extract just the summary/key points if JSON
        body = _extract_readable(body)
        safe_body = escape_md(body)

        full_msg = truncate_for_telegram(f"{header}\n{safe_body}")

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=full_msg,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            # Fallback: send without markdown if parsing fails
            logger.exception(f"[broadcaster] MarkdownV2 failed for {agent_name}, sending plain")
            plain = f"{persona.emoji} {persona.display_name} ({persona.cargo})\n{body[:3500]}"
            await self.bot.send_message(chat_id=self.chat_id, text=plain)

    async def send_phase_header(self, phase_num: int, phase_name: str):
        """Send a phase separator header to the group."""
        headers = {
            1: "📡 FASE 1 — INTELIGÊNCIA",
            2: "📊 FASE 2 — ANÁLISE DA EQUIPE",
            3: "🛡️ FASE 3 — CONSOLIDAÇÃO DE RISCO",
            4: "🏛️ FASE 4 — DECISÃO FINAL",
        }
        text = headers.get(phase_num, f"FASE {phase_num}")
        separator = "═" * 30
        safe = escape_md(f"\n{separator}\n{text}\n{separator}")
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=safe,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def send_debate_header(self):
        """Send a debate section header."""
        safe = escape_md("⚡ DEBATE — Divergências identificadas")
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=f"\\n🔥 *{safe}*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def broadcast_phase_results(self, phase_results: dict[str, str], phase_num: int, phase_name: str):
        """Broadcast all agent results from a phase sequentially."""
        await self.send_phase_header(phase_num, phase_name)

        for agent_name, result in phase_results.items():
            await self.send_agent_message(agent_name, result)


def _extract_readable(text: str) -> str:
    """Try to extract resumo_executivo from JSON, otherwise return as-is."""
    import json
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Prefer resumo_executivo
            resumo = data.get("resumo_executivo", "")
            if resumo:
                return resumo
            # Fallback: return first string value found
            for v in data.values():
                if isinstance(v, str) and len(v) > 50:
                    return v
    except (json.JSONDecodeError, TypeError):
        pass
    # Return first 2000 chars if not JSON
    return text[:2000]
