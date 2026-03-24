import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.services.market_data import get_macro_data
from app.services.portfolio_service import (
    get_portfolio_allocation,
    get_portfolio_assets,
)
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Eduardo Queiroz, Analista Quantitativo de uma gestora de investimentos brasileira.

Perfil: Técnico, data-driven, fala em métricas e estatísticas.
Exemplo de fala: "Portfólio tá com beta 1.3 pro Ibov, Sharpe de 0.8."

Sua função:
- Calcular métricas quantitativas do portfólio (Sharpe ratio, beta, volatilidade)
- Analisar correlação entre ativos (ações vs crypto vs CDB)
- Sugerir alocação ótima (mean-variance, considerando CDI como risk-free)
- Identificar concentração e diversificação
- Comparar performance vs benchmarks (Ibovespa, BTC, CDI)

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "metricas_portfolio": {{
    "volatilidade_anual_pct": float,
    "sharpe_ratio": float,
    "beta_ibov": float,
    "max_drawdown_pct": float,
    "correlacao_btc": float
  }},
  "concentracao": {{
    "hhi_index": float,
    "top3_pct": float,
    "ativos_top3": [str]
  }},
  "alocacao_otima": {{
    "acoes_pct": float,
    "crypto_pct": float,
    "renda_fixa_pct": float,
    "justificativa": str
  }},
  "alocacao_atual_vs_otima": str,
  "resumo_executivo": str
}}"""


class QuantAnalyst(BaseAgent):
    agent_name = "quant_analyst"
    level = "N2"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "get_portfolio_assets",
                "description": "Lista todos os ativos do portfólio com preço, quantidade e P&L",
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
                "name": "get_portfolio_allocation",
                "description": "Alocação atual vs alvo (50% ações, 20% crypto, 30% CDB)",
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
                "name": "get_macro_data",
                "description": "Dados macro: Selic (risk-free rate), CDI, IPCA, PTAX",
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
                "name": "get_asset_history",
                "description": "Histórico de preços OHLCV de um ativo (ação B3 ou crypto)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker (ex: PETR4, bitcoin)"},
                        "tipo": {"type": "string", "description": "Tipo: acao ou crypto"},
                    },
                    "required": ["ticker", "tipo"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "get_portfolio_allocation":
            data = get_portfolio_allocation(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "get_macro_data":
            data = get_macro_data(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "get_asset_history":
            ticker = args["ticker"]
            tipo = args["tipo"]
            # Lazy import to avoid pulling in playwright at module load
            from app.services.yahoo_scraper import get_stock_history, get_crypto_history as get_crypto_hist
            if tipo == "crypto":
                data = get_crypto_hist(ticker, db=self.db)
            else:
                data = get_stock_history(ticker, db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, portfolio_context: str = "", job_id: str | None = None) -> str:
        prompt = f"""Faça uma análise quantitativa completa do portfólio.

1. Consulte ativos e alocação do portfólio
2. Busque dados macro (Selic como risk-free rate)
3. Busque históricos de preço dos principais ativos para calcular:
   - Volatilidade anualizada
   - Sharpe ratio (usando Selic como risk-free)
   - Correlações entre ativos
   - Concentração (HHI index)
4. Sugira alocação ótima considerando perfil moderado

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Eduardo Queiroz (Quant) calculando métricas...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=10, job_id=job_id)
        self.save_analysis(
            tipo_analise="quant_analysis",
            input_resumo="Análise quantitativa do portfólio",
            output=result,
        )
        return result
