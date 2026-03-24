import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_macro_data
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Beatriz Almeida, Analista Setorial e Macro de ações B3.

Perfil: Informal, conectora, liga Selic com setores.
Exemplo de fala: "Com juros nesse patamar, utilities voam. Varejo vai sofrer."

Sua função:
- Mapear setores da B3: bancos, commodities, utilities, varejo, saúde, tech, construção
- Analisar rotação setorial (quais setores se beneficiam do cenário atual)
- Avaliar impacto da Selic/IPCA em cada setor
- Considerar correlação USD/BRL com exportadoras (Vale, Suzano, Petro)
- Identificar setores em ciclo favorável vs desfavorável

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "cenario_setorial": [
    {{
      "setor": str,
      "perspectiva": "favoravel|neutro|desfavoravel",
      "drivers": [str],
      "tickers_destaque": [str],
      "impacto_selic": str,
      "impacto_cambio": str
    }}
  ],
  "rotacao_recomendada": {{
    "aumentar_exposicao": [str],
    "reduzir_exposicao": [str],
    "justificativa": str
  }},
  "resumo_executivo": str
}}"""


class SetorialB3(BaseAgent):
    agent_name = "setorial_b3"
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
                "description": "Dados macro BCB: Selic, CDI, IPCA, PTAX",
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
        prompt = f"""Faça uma análise setorial completa do mercado B3.

1. Busque dados macro (Selic, IPCA, câmbio)
2. Pesquise na web: tendências setoriais, resultados recentes dos setores
3. Avalie impacto da política monetária em cada setor
4. Identifique rotação setorial em curso
5. Recomende onde aumentar e reduzir exposição

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Beatriz Almeida (Setorial) mapeando setores...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="setorial_b3",
            input_resumo="Análise setorial B3",
            output=result,
        )
        return result
