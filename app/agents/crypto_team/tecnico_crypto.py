import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_crypto_history, get_crypto_price
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Juliana Pires, Analista Técnica de Crypto.

Perfil: Informal, pragmática, opera 24/7 e entende dinâmicas específicas de crypto.
Exemplo de fala: "Funding tá positivo demais, short squeeze vindo. RSI em oversold no 4h."

Sua função:
- Análise técnica adaptada para mercado 24/7 (sem gaps de pregão)
- Suportes, resistências, tendências, padrões gráficos
- Indicadores: RSI, MACD, Bollinger, médias móveis
- Métricas crypto-específicas: funding rates, open interest, liquidation levels
- BTC dominance e correlação com altcoins (alt season patterns)

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "analises_tecnicas": [
    {{
      "id": str,
      "ticker": str,
      "preco_atual_usd": float,
      "tendencia": "alta|baixa|lateral",
      "suportes_usd": [float],
      "resistencias_usd": [float],
      "indicadores": {{
        "rsi_14": str,
        "macd": str,
        "funding_rate": str,
        "volume_tendencia": str
      }},
      "sinal": "compra|venda|neutro",
      "score": float,
      "justificativa": str
    }}
  ],
  "btc_dominance": str,
  "alt_season_signal": bool,
  "resumo_executivo": str
}}"""


class TecnicoCrypto(BaseAgent):
    agent_name = "tecnico_crypto"
    level = "N2"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("high"),
            {
                "type": "function",
                "name": "get_crypto_price",
                "description": "Preço atual de uma criptomoeda em USD e BRL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID (ex: bitcoin, ethereum)"},
                    },
                    "required": ["crypto_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_crypto_history",
                "description": "Histórico OHLCV de uma criptomoeda",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID (ex: bitcoin, ethereum)"},
                    },
                    "required": ["crypto_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_crypto_price":
            data = get_crypto_price(args["crypto_id"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_crypto_history":
            data = get_crypto_history(args["crypto_id"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, cryptos: list[str], portfolio_context: str = "", job_id: str | None = None) -> str:
        cryptos_str = ", ".join(cryptos)
        prompt = f"""Faça análise técnica das seguintes criptomoedas: {cryptos_str}

1. Para cada crypto, busque preço e histórico
2. Pesquise na web: funding rates, open interest, BTC dominance
3. Identifique tendência, suportes, resistências e sinais técnicos
4. Avalie se estamos em alt season ou BTC season

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Juliana Pires (Técnica Crypto) analisando gráficos de {cryptos_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=10, job_id=job_id)
        self.save_analysis(
            tipo_analise="tecnico_crypto",
            input_resumo=f"Análise técnica crypto: {cryptos_str}",
            output=result,
        )
        return result
