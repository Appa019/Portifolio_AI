import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_macro_data
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Helena Bastos, Economista-Chefe de uma gestora de investimentos brasileira.

Perfil: Formal-informativo, referencia Focus, atas do Copom e calendário econômico.
Exemplo de fala: "Copom deve manter em 14.25%, Focus tá alinhado."

Sua função:
- Analisar cenário macroeconômico brasileiro e global
- Avaliar impacto da política monetária (Selic, CDI) nas classes de ativos
- Monitorar inflação (IPCA), câmbio (USD/BRL) e risco-país
- Analisar decisões do Fed e fluxo de capitais para emergentes
- Produzir "macro backdrop" que informa todas as decisões de investimento

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "cenario_macro": {{
    "selic": {{"valor": float, "tendencia": "alta|estavel|baixa", "proximo_copom": "YYYY-MM-DD ou null"}},
    "ipca": {{"acumulado_12m": float, "tendencia": str}},
    "cambio": {{"ptax": float, "tendencia": str}},
    "cdi": {{"valor": float}},
    "cenario_global": str,
    "fed": str
  }},
  "impacto_por_classe": {{
    "acoes_b3": str,
    "crypto": str,
    "renda_fixa": str
  }},
  "riscos_principais": [str],
  "oportunidades_macro": [str],
  "resumo_executivo": str
}}"""


class MacroEconomist(BaseAgent):
    agent_name = "macro_economist"
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
                "name": "get_macro_data",
                "description": "Dados macroeconômicos BCB: Selic, CDI, IPCA acumulado 12m, câmbio PTAX",
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
        if name == "get_macro_data":
            data = get_macro_data(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, portfolio_context: str = "", job_id: str | None = None) -> str:
        prompt = f"""Produza uma análise macroeconômica completa para orientar decisões de investimento.

1. Busque dados macro (Selic, CDI, IPCA, PTAX) via ferramenta
2. Pesquise na web: última ata do Copom, expectativas Focus, decisão do Fed, risco-país
3. Avalie impacto em cada classe de ativo (ações B3, crypto, renda fixa)
4. Identifique riscos e oportunidades macro

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Helena Bastos (Macro) analisando cenário...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="macro_analysis",
            input_resumo="Análise macroeconômica",
            output=result,
        )
        return result
