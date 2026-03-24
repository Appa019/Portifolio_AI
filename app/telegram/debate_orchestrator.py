"""DebateOrchestrator — Detects divergences between agents and generates debate rounds.

When two agents disagree on a recommendation (e.g., Fundamentalista says BUY,
Técnico says SELL), this orchestrator triggers a rebuttal round where each
agent responds to the other's position, and the Head closes with a conclusion.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class Divergence:
    """Represents a disagreement between two agents."""
    asset: str
    agent_a: str
    position_a: str  # "comprar", "vender", "manter"
    agent_b: str
    position_b: str


def detect_divergences(reports: dict[str, str]) -> list[Divergence]:
    """Compare agent reports to find disagreements on the same asset.

    Looks for tipo_recomendacao, recomendacao, sinal, or acao fields in JSON reports.
    """
    # Extract recommendations per agent
    agent_recs: dict[str, list[tuple[str, str]]] = {}  # agent → [(asset, recommendation)]

    for agent_name, report_text in reports.items():
        recs = _extract_recommendations(report_text)
        if recs:
            agent_recs[agent_name] = recs

    # Compare all pairs
    divergences = []
    agents = list(agent_recs.keys())
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            a, b = agents[i], agents[j]
            recs_a = {asset: rec for asset, rec in agent_recs[a]}
            recs_b = {asset: rec for asset, rec in agent_recs[b]}

            # Find common assets with different recommendations
            common = set(recs_a.keys()) & set(recs_b.keys())
            for asset in common:
                if _are_opposing(recs_a[asset], recs_b[asset]):
                    divergences.append(Divergence(
                        asset=asset,
                        agent_a=a, position_a=recs_a[asset],
                        agent_b=b, position_b=recs_b[asset],
                    ))

    if divergences:
        logger.info(f"[debate] {len(divergences)} divergências detectadas")
    return divergences


def generate_rebuttal_prompt(divergence: Divergence, own_position: str, opponent_position: str, opponent_name: str) -> str:
    """Generate a prompt for an agent to rebut the opposing view."""
    return f"""Um colega da equipe ({opponent_name}) discorda da sua posição sobre {divergence.asset}.

Sua posição: {own_position}
Posição do colega: {opponent_position}

Responda em 2-3 frases CURTAS, no seu tom habitual, defendendo sua posição
ou reconhecendo o ponto do colega se for válido. Seja direto e específico.
NÃO repita toda a análise — apenas rebata o ponto de divergência."""


def generate_head_conclusion_prompt(divergences: list[Divergence], rebuttals: dict[str, str]) -> str:
    """Generate a prompt for the Head to close the debate with a conclusion."""
    debate_summary = []
    for d in divergences:
        debate_summary.append(
            f"• {d.asset}: {d.agent_a} diz {d.position_a}, {d.agent_b} diz {d.position_b}"
        )

    rebuttal_text = "\n".join(f"[{name}]: {text[:300]}" for name, text in rebuttals.items())

    return f"""Houve divergência na equipe:
{chr(10).join(debate_summary)}

Réplicas:
{rebuttal_text}

Como Head da equipe, dê a CONCLUSÃO FINAL em 3-4 frases.
Decida qual posição prevalece e por quê. Seja definitivo."""


def _extract_recommendations(report_text: str) -> list[tuple[str, str]]:
    """Extract (asset, recommendation) pairs from a JSON report."""
    recs = []
    try:
        data = json.loads(report_text)
    except (json.JSONDecodeError, TypeError):
        return recs

    if not isinstance(data, dict):
        return recs

    # Search common recommendation list patterns
    for key in ("analises_fundamentalistas", "analises_tecnicas", "estrategias_trade",
                "sinais_por_crypto"):
        items = data.get(key, [])
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                asset = item.get("ticker") or item.get("id") or item.get("asset", "")
                rec = (
                    item.get("recomendacao")
                    or item.get("sinal")
                    or item.get("acao")
                    or item.get("sinal_onchain")
                    or ""
                )
                if asset and rec:
                    recs.append((asset.upper(), rec.lower()))

    return recs


def _are_opposing(rec_a: str, rec_b: str) -> bool:
    """Check if two recommendations are opposing."""
    buy_words = {"comprar", "compra", "acumulacao", "bullish"}
    sell_words = {"vender", "venda", "distribuicao", "bearish"}

    a_buy = rec_a in buy_words
    a_sell = rec_a in sell_words
    b_buy = rec_b in buy_words
    b_sell = rec_b in sell_words

    return (a_buy and b_sell) or (a_sell and b_buy)
