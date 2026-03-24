import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.services.market_data import get_stock_history, get_stock_price
from app.services.portfolio_service import get_portfolio_assets, get_portfolio_summary
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Diego Lopes, Trade Strategist da equipe B3.

Perfil: Informal, tático, foca em timing e sizing.
Exemplo de fala: "Divide em 3 lotes: 1/3 agora, 1/3 no suporte, 1/3 só se confirmar reversão."

Sua função:
- Definir timing de entrada e saída para ações B3
- Calcular position sizing baseado em risco (% do portfólio por trade)
- Considerar liquidez do papel (volume médio), spread bid/ask, lote padrão (100 ações)
- Respeitar horário de pregão B3 (10h-17h BRT)
- Definir stop loss e take profit
- Considerar lockup de 30 dias após compra

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "estrategias_trade": [
    {{
      "ticker": str,
      "acao": "comprar|vender|manter",
      "preco_entrada": float,
      "preco_stop_loss": float,
      "preco_take_profit": float,
      "sizing": {{
        "valor_brl": float,
        "pct_portfolio": float,
        "quantidade_acoes": int,
        "lotes": int
      }},
      "estrategia_entrada": str,
      "timing": str,
      "justificativa": str
    }}
  ],
  "capital_disponivel_brl": float,
  "resumo_executivo": str
}}"""


class TradeB3(BaseAgent):
    agent_name = "trade_b3"
    level = "N2"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "get_stock_price",
                "description": "Preço atual de uma ação B3",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker (ex: PETR4)"},
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_stock_history",
                "description": "Histórico OHLCV de uma ação B3 (para avaliar volume e volatilidade)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker (ex: PETR4)"},
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_portfolio_summary",
                "description": "Resumo do portfólio (valor total, disponível para trades)",
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
                "description": "Ativos atuais do portfólio (para saber posições existentes)",
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
        if name == "get_stock_price":
            data = get_stock_price(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_stock_history":
            data = get_stock_history(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_summary":
            data = get_portfolio_summary(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, tickers: list[str], portfolio_context: str = "", job_id: str | None = None) -> str:
        tickers_str = ", ".join(tickers)
        prompt = f"""Defina estratégias de trade para os seguintes tickers: {tickers_str}

1. Consulte o portfólio atual (valor total, posições existentes)
2. Para cada ticker, busque preço atual e histórico (volume, volatilidade)
3. Defina: preço de entrada, stop loss, take profit, sizing
4. Considere liquidez, lote padrão B3 (100 ações) e lockup de 30 dias

{f"Contexto: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Diego Lopes (Trade) calculando sizing para {tickers_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="trade_b3",
            input_resumo=f"Estratégia de trade: {tickers_str}",
            output=result,
        )
        return result
