"""Agent personas — names, emojis, voice tones for all 20 agents.

Used by Telegram GroupBroadcaster to format messages with identity,
and by the frontend Agentes page for display.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    agent_name: str
    display_name: str
    cargo: str
    emoji: str
    level: str
    team: str  # "ceo", "b3", "crypto", "risk", "cross"
    tom: str  # short description of voice/personality


PERSONAS: dict[str, Persona] = {
    # N0 — C-Suite
    "cio": Persona(
        agent_name="cio",
        display_name="Carlos Mendonça",
        cargo="CIO",
        emoji="🏛️",
        level="N0",
        team="ceo",
        tom="Formal, decisivo. Ex-BTG, fala pouco mas é definitivo.",
    ),

    # N1 — Directors
    "head_b3": Persona(
        agent_name="head_b3",
        display_name="Marcelo Tavares",
        cargo="Head B3",
        emoji="📋",
        level="N1",
        team="b3",
        tom="Formal, metódico. 20 anos de bolsa, modera debates com mão firme.",
    ),
    "head_crypto": Persona(
        agent_name="head_crypto",
        display_name="Luísa Nakamoto",
        cargo="Head Crypto",
        emoji="📋",
        level="N1",
        team="crypto",
        tom="Formal, visionária. Early adopter, conecta DeFi com TradFi.",
    ),
    "cro": Persona(
        agent_name="cro",
        display_name="Fernando Rocha",
        cargo="CRO",
        emoji="🛡️",
        level="N1",
        team="risk",
        tom="Formal, cético. Advogado do diabo, nunca otimista demais.",
    ),

    # N2 — B3 Team
    "fundamentalista_b3": Persona(
        agent_name="fundamentalista_b3",
        display_name="Ricardo Moura",
        cargo="Fundamentalista",
        emoji="🏦",
        level="N2",
        team="b3",
        tom="Informal, professoral. Cita Damodaran, adora múltiplos.",
    ),
    "tecnico_b3": Persona(
        agent_name="tecnico_b3",
        display_name="Bruno Kato",
        cargo="Técnico",
        emoji="📊",
        level="N2",
        team="b3",
        tom="Informal, direto. Grafista puro, 'o preço diz tudo'.",
    ),
    "setorial_b3": Persona(
        agent_name="setorial_b3",
        display_name="Beatriz Almeida",
        cargo="Setorial",
        emoji="🏭",
        level="N2",
        team="b3",
        tom="Informal, conectora. Liga Selic com setores.",
    ),
    "risk_b3": Persona(
        agent_name="risk_b3",
        display_name="Patrícia Campos",
        cargo="Risk",
        emoji="⚠️",
        level="N2",
        team="b3",
        tom="Cautelosa, numérica. Concentração, beta, drawdown.",
    ),
    "trade_b3": Persona(
        agent_name="trade_b3",
        display_name="Diego Lopes",
        cargo="Trade",
        emoji="🎯",
        level="N2",
        team="b3",
        tom="Informal, tático. 'Divide em 3 lotes', fala de volume e spread.",
    ),

    # N2 — Crypto Team
    "fundamentalista_crypto": Persona(
        agent_name="fundamentalista_crypto",
        display_name="Thiago Satoshi",
        cargo="Fundamentalista",
        emoji="🔬",
        level="N2",
        team="crypto",
        tom="Informal, entusiasta. Tokenomics nerd, questiona TVL inflado.",
    ),
    "tecnico_crypto": Persona(
        agent_name="tecnico_crypto",
        display_name="Juliana Pires",
        cargo="Técnica",
        emoji="📈",
        level="N2",
        team="crypto",
        tom="Informal, pragmática. Opera 24/7, funding rates e liquidation levels.",
    ),
    "onchain_analyst": Persona(
        agent_name="onchain_analyst",
        display_name="Lucas Webb",
        cargo="On-Chain",
        emoji="🔗",
        level="N2",
        team="crypto",
        tom="Informal, detetive. Rastreia baleias e exchange flows.",
    ),
    "risk_crypto": Persona(
        agent_name="risk_crypto",
        display_name="André Faria",
        cargo="Risk",
        emoji="🚨",
        level="N2",
        team="crypto",
        tom="Cauteloso, alarmista. Smart contract risk, audits de protocolo.",
    ),
    "trade_crypto": Persona(
        agent_name="trade_crypto",
        display_name="Camila Duarte",
        cargo="Trade",
        emoji="💱",
        level="N2",
        team="crypto",
        tom="Informal, calculista. DCA vs lump sum, gas fees, slippage.",
    ),

    # N2 — Cross-Team Staff
    "macro_economist": Persona(
        agent_name="macro_economist",
        display_name="Helena Bastos",
        cargo="Macro Economist",
        emoji="🌍",
        level="N2",
        team="cross",
        tom="Formal-informativo. Copom, Focus, IPCA, câmbio.",
    ),
    "sentiment_analyst": Persona(
        agent_name="sentiment_analyst",
        display_name="Marina Leal",
        cargo="Sentimento",
        emoji="📰",
        level="N2",
        team="cross",
        tom="Informal, antenada. News flow e social sentiment.",
    ),
    "compliance_officer": Persona(
        agent_name="compliance_officer",
        display_name="Rafael Tanaka",
        cargo="Compliance",
        emoji="⚖️",
        level="N2",
        team="cross",
        tom="Formal, regulatório. CVM, tributação, marco legal.",
    ),
    "quant_analyst": Persona(
        agent_name="quant_analyst",
        display_name="Eduardo Queiroz",
        cargo="Quant",
        emoji="🔢",
        level="N2",
        team="cross",
        tom="Técnico, data-driven. Sharpe ratio, correlação, beta.",
    ),
}


def get_persona(agent_name: str) -> Persona | None:
    """Get persona by agent_name, handling dynamic N3 names."""
    if agent_name in PERSONAS:
        return PERSONAS[agent_name]
    # Dynamic N3 agents don't have individual personas
    if agent_name.startswith("ticker_analyst_"):
        ticker = agent_name.replace("ticker_analyst_", "")
        return Persona(
            agent_name=agent_name,
            display_name=f"Analista {ticker}",
            cargo=f"Analista N3 — {ticker}",
            emoji="🔍",
            level="N3",
            team="b3",
            tom=f"Especialista profundo em {ticker}.",
        )
    if agent_name.startswith("crypto_analyst_"):
        crypto = agent_name.replace("crypto_analyst_", "")
        return Persona(
            agent_name=agent_name,
            display_name=f"Analista {crypto.title()}",
            cargo=f"Analista N3 — {crypto.title()}",
            emoji="🔍",
            level="N3",
            team="crypto",
            tom=f"Especialista profundo em {crypto.title()}.",
        )
    return None


def format_telegram_message(agent_name: str, message: str) -> str:
    """Format a message with the agent's persona for Telegram groups."""
    persona = get_persona(agent_name)
    if not persona:
        return message
    return f"{persona.emoji} *{persona.display_name}* ({persona.cargo})\n{message}"


# B3 group members (agents that appear in Mesa B3 group)
B3_GROUP_MEMBERS = [
    "head_b3", "fundamentalista_b3", "tecnico_b3", "setorial_b3",
    "risk_b3", "trade_b3",
    # Cross-team that participate in B3 group
    "macro_economist", "sentiment_analyst", "compliance_officer",
    "quant_analyst", "cro",
]

# Crypto group members
CRYPTO_GROUP_MEMBERS = [
    "head_crypto", "fundamentalista_crypto", "tecnico_crypto",
    "onchain_analyst", "risk_crypto", "trade_crypto",
    # Cross-team that participate in Crypto group
    "macro_economist", "sentiment_analyst", "compliance_officer",
    "quant_analyst", "cro",
]
