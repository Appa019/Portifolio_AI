import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.services.market_data import get_macro_data, get_stock_history
from app.services.portfolio_service import get_portfolio_allocation, get_portfolio_assets
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Patrícia Campos, Risk Officer da equipe B3.

Perfil: Cautelosa, numérica, sempre alerta para concentração e drawdown.
Exemplo de fala: "Tá muito exposto em commodities. Beta do portfólio tá 1.4."

Sua função:
- Monitorar exposição por setor e ativo individual
- Calcular concentração (nenhum ativo > 15% do portfólio)
- Avaliar beta do portfólio B3 em relação ao Ibovespa
- Identificar drawdown máximo histórico das posições
- Verificar se a alocação em ações está dentro do alvo (50%)
- Alertar sobre riscos de concentração, liquidez e correlação

Você reporta ao Fernando Rocha (CRO), NÃO ao Head B3.

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "exposicao_acoes": {{
    "pct_portfolio": float,
    "alvo_pct": 50.0,
    "desvio_pct": float,
    "status": "dentro|acima|abaixo"
  }},
  "concentracao": {{
    "top3_ativos": [{{"ticker": str, "pct": float}}],
    "acima_limite_15pct": [str],
    "hhi_acoes": float
  }},
  "riscos_identificados": [
    {{"tipo": str, "descricao": str, "severidade": "alta|media|baixa"}}
  ],
  "metricas": {{
    "beta_estimado": float,
    "setores_concentrados": [str]
  }},
  "resumo_executivo": str
}}"""


class RiskB3(BaseAgent):
    agent_name = "risk_b3"
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
                "name": "get_stock_history",
                "description": "Histórico OHLCV de uma ação B3 (para calcular volatilidade)",
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
                "name": "get_macro_data",
                "description": "Dados macro: Selic, CDI, IPCA, PTAX",
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
        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_allocation":
            data = get_portfolio_allocation(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_stock_history":
            data = get_stock_history(args["ticker"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_macro_data":
            data = get_macro_data(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, portfolio_context: str = "", job_id: str | None = None) -> str:
        prompt = f"""Faça uma avaliação de risco completa da carteira de ações B3.

1. Consulte os ativos e alocação do portfólio
2. Verifique concentração por ativo (limite: 15% cada) e por setor
3. Analise se a alocação em ações está dentro do alvo (50%)
4. Busque histórico dos principais ativos para estimar volatilidade
5. Identifique todos os riscos: concentração, setor, liquidez, macro

{f"Contexto: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Patrícia Campos (Risk B3) avaliando exposição...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="risk_b3",
            input_resumo="Avaliação de risco B3",
            output=result,
        )
        return result
