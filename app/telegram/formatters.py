"""Telegram MarkdownV2 formatting utilities for agent messages."""

import re


def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Characters that must be escaped: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special = r"_*[]()~`>#+-=|{}.!"
    result = []
    for ch in text:
        if ch in special:
            result.append(f"\\{ch}")
        else:
            result.append(ch)
    return "".join(result)


def format_agent_header(emoji: str, name: str, cargo: str) -> str:
    """Format agent identity header in MarkdownV2 bold."""
    safe_name = escape_md(name)
    safe_cargo = escape_md(cargo)
    return f"{emoji} *{safe_name}* \\({safe_cargo}\\)"


def format_agent_message(emoji: str, name: str, cargo: str, body: str) -> str:
    """Format a full agent message with header + body for Telegram."""
    header = format_agent_header(emoji, name, cargo)
    safe_body = escape_md(body)
    return f"{header}\n{safe_body}"


def truncate_for_telegram(text: str, max_chars: int = 4000) -> str:
    """Truncate text to fit Telegram's message limit (4096 chars)."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\\.\\.\\. \\(truncado\\)"
