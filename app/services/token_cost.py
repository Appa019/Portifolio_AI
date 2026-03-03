import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import CustoToken
from app.services.market_data import get_ptax

logger = logging.getLogger(__name__)

# Preços por 1M tokens (USD)
PRICING = {
    "gpt-5.2": {"input": 1.75, "output": 14.00},
    "gpt-5.1": {"input": 1.25, "output": 10.00},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
}


def calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = PRICING.get(model, PRICING["gpt-5.1"])
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def log_token_cost(
    db: Session,
    agente: str,
    modelo: str,
    tokens_input: int,
    tokens_output: int,
    descricao: str = "",
) -> CustoToken:
    custo_usd = calculate_cost_usd(modelo, tokens_input, tokens_output)
    cotacao = get_ptax()
    custo_brl = custo_usd * cotacao

    entry = CustoToken(
        data=datetime.now(),
        agente=agente,
        modelo=modelo,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        custo_usd=round(custo_usd, 6),
        cotacao_dolar=cotacao,
        custo_brl=round(custo_brl, 4),
        descricao=descricao,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(
        f"Token cost logged: {agente}/{modelo} — "
        f"{tokens_input}in/{tokens_output}out — "
        f"${custo_usd:.4f} / R${custo_brl:.4f}"
    )
    return entry
