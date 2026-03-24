import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.services.market_data import get_crypto_history, get_crypto_price
from app.services.portfolio_service import get_portfolio_assets, get_portfolio_summary
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Camila Duarte, Trade Strategist de Crypto.

Perfil: Informal, calculista, foca em DCA e eficiência de execução.
Exemplo de fala: "Slippage tá alto nessa DEX. Melhor ir por Binance BR e dividir em DCA semanal."

Sua função:
- Definir estratégia de execução: DCA vs lump sum
- Calcular position sizing baseado em risco
- Considerar: mercado 24/7, spreads em exchanges BR, gas fees
- Avaliar slippage em altcoins de menor liquidez
- Definir stop loss e take profit em crypto (volatilidade > ações)
- Considerar lockup de 30 dias após compra

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "estrategias_trade": [
    {{
      "id": str,
      "ticker": str,
      "acao": "comprar|vender|manter",
      "preco_entrada_usd": float,
      "preco_stop_loss_usd": float,
      "preco_take_profit_usd": float,
      "sizing": {{
        "valor_brl": float,
        "pct_portfolio": float
      }},
      "estrategia": str,
      "exchange_recomendada": str,
      "dca_frequencia": str,
      "justificativa": str
    }}
  ],
  "capital_disponivel_brl": float,
  "resumo_executivo": str
}}"""


class TradeCrypto(BaseAgent):
    agent_name = "trade_crypto"
    level = "N2"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "get_crypto_price",
                "description": "Preço atual em USD e BRL",
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
                "description": "Histórico OHLCV para avaliar volume e volatilidade",
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
                "name": "get_portfolio_summary",
                "description": "Resumo do portfólio (valor total)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_portfolio_assets",
                "description": "Ativos do portfólio (posições existentes)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
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
        if name == "get_portfolio_summary":
            data = get_portfolio_summary(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, cryptos: list[str], portfolio_context: str = "", job_id: str | None = None) -> str:
        cryptos_str = ", ".join(cryptos)
        prompt = f"""Defina estratégias de trade para as seguintes criptomoedas: {cryptos_str}

1. Consulte portfólio atual (valor total, posições)
2. Para cada crypto, busque preço e histórico (volume, volatilidade)
3. Defina: preço de entrada, stop loss, take profit, sizing
4. Recomende DCA vs lump sum, exchange preferida, e timing
5. Considere lockup de 30 dias e gas fees

{f"Contexto: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Camila Duarte (Trade Crypto) calculando sizing para {cryptos_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="trade_crypto",
            input_resumo=f"Estratégia de trade crypto: {cryptos_str}",
            output=result,
        )
        return result
