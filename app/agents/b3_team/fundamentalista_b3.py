import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_stock_fundamentals, get_stock_dividends
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Ricardo Moura, Analista Fundamentalista de ações B3.

Perfil: Informal, professoral, cita Damodaran e Buffett. Adora múltiplos.
Exemplo de fala: "Esse P/L tá esticado demais, papel tá caro pro que entrega."

Sua função:
- Analisar demonstrações financeiras e múltiplos (P/L, P/VP, EV/EBITDA, DY, ROE, ROIC)
- Avaliar qualidade dos lucros e endividamento (Dívida Líquida/EBITDA)
- Fazer valuation relativo (comparar com peers do setor)
- Identificar "margin of safety" — papéis baratos vs caros
- Considerar contabilidade brasileira (IFRS + CPC)

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "analises_fundamentalistas": [
    {{
      "ticker": str,
      "nome": str,
      "setor": str,
      "multiplos": {{
        "pl": float, "pvp": float, "ev_ebitda": float,
        "dividend_yield": float, "roe": float, "roic": float,
        "margem_liquida": float, "divida_ebitda": float
      }},
      "qualidade_lucros": str,
      "valuation_relativo": str,
      "recomendacao": "comprar|manter|vender",
      "score": float,
      "justificativa": str
    }}
  ],
  "setores_atrativos": [str],
  "setores_caros": [str],
  "resumo_executivo": str
}}"""


class FundamentalistaB3(BaseAgent):
    agent_name = "fundamentalista_b3"
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
                "name": "get_stock_fundamentals",
                "description": "Retorna indicadores fundamentalistas de uma ação B3 (P/L, P/VP, ROE, DY, margens)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação (ex: PETR4)"},
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_stock_dividends",
                "description": "Histórico de dividendos de uma ação B3",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação (ex: PETR4)"},
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_stock_fundamentals":
            data = get_stock_fundamentals(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_stock_dividends":
            data = get_stock_dividends(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, tickers: list[str], portfolio_context: str = "", job_id: str | None = None) -> str:
        tickers_str = ", ".join(tickers)
        prompt = f"""Faça análise fundamentalista dos seguintes tickers B3: {tickers_str}

1. Para cada ticker, busque indicadores fundamentalistas via ferramenta
2. Pesquise na web: resultados recentes, guidance, eventos corporativos
3. Compare múltiplos entre peers do mesmo setor
4. Identifique quais estão baratos e quais estão caros

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Ricardo Moura (Fundamentalista) analisando {tickers_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=10, job_id=job_id)
        self.save_analysis(
            tipo_analise="fundamental_b3",
            input_resumo=f"Análise fundamentalista: {tickers_str}",
            output=result,
        )
        return result
