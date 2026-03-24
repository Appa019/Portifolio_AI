import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_stock_history, get_stock_price
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Bruno Kato, Analista Técnico de ações B3.

Perfil: Informal, direto, grafista puro. "O preço diz tudo."
Exemplo de fala: "Papel perdeu a média de 200, suporte em R$34.50, se perder vai buscar R$31."

Sua função:
- Analisar price action, tendências e padrões gráficos
- Identificar suportes, resistências e zonas de liquidez
- Calcular/interpretar indicadores: médias móveis (9, 21, 50, 200), RSI, MACD, Bollinger
- Avaliar volume profile e força do movimento
- Definir pontos de entrada e saída técnicos

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "analises_tecnicas": [
    {{
      "ticker": str,
      "preco_atual": float,
      "tendencia": "alta|baixa|lateral",
      "suportes": [float],
      "resistencias": [float],
      "medias_moveis": {{
        "mm9": float, "mm21": float, "mm50": float, "mm200": float,
        "acima_mm200": bool
      }},
      "indicadores": {{
        "rsi_14": str,
        "macd": str,
        "volume_tendencia": str
      }},
      "sinal": "compra|venda|neutro",
      "score": float,
      "justificativa": str
    }}
  ],
  "resumo_executivo": str
}}"""


class TecnicoB3(BaseAgent):
    agent_name = "tecnico_b3"
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
                "description": "Histórico OHLCV de uma ação B3 (período padrão: 6 meses)",
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
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_stock_price":
            data = get_stock_price(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_stock_history":
            data = get_stock_history(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, tickers: list[str], portfolio_context: str = "", job_id: str | None = None) -> str:
        tickers_str = ", ".join(tickers)
        prompt = f"""Faça análise técnica dos seguintes tickers B3: {tickers_str}

1. Para cada ticker, busque preço atual e histórico via ferramentas
2. Pesquise na web: análises técnicas recentes, níveis-chave
3. Identifique tendência, suportes, resistências, sinais de indicadores
4. Dê sinal claro: compra, venda ou neutro

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Bruno Kato (Técnico) analisando gráficos de {tickers_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=10, job_id=job_id)
        self.save_analysis(
            tipo_analise="tecnico_b3",
            input_resumo=f"Análise técnica: {tickers_str}",
            output=result,
        )
        return result
