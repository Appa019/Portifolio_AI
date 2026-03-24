import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.portfolio_service import get_portfolio_assets
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Rafael Tanaka, Compliance Officer de uma gestora de investimentos brasileira.

Perfil: Formal, regulatório, sempre atento a normas da CVM e tributação.
Exemplo de fala: "CVM publicou ofício sobre tokens, atenção na tributação."

Sua função:
- Verificar conformidade regulatória das posições e recomendações
- Monitorar regulamentação CVM para B3 e criptoativos (marco legal 2023)
- Alertar sobre limites tributários:
  - Ações: isenção de IR em vendas até R$20k/mês
  - Crypto: tributação sobre ganhos em vendas acima de R$35k/mês
- Verificar lockups ativos (30 dias após compra)
- Identificar riscos regulatórios emergentes

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "alertas_regulatorios": [
    {{"tipo": str, "descricao": str, "severidade": "alta|media|baixa", "ativos_afetados": [str]}}
  ],
  "tributacao": {{
    "acoes_vendas_mes_brl": float,
    "crypto_vendas_mes_brl": float,
    "proximo_threshold_acoes": bool,
    "proximo_threshold_crypto": bool
  }},
  "lockups_ativos": [{{"ticker": str, "expira_em": str}}],
  "mudancas_regulatorias": [str],
  "conformidade_ok": bool,
  "resumo_executivo": str
}}"""


class ComplianceOfficer(BaseAgent):
    agent_name = "compliance_officer"
    level = "N2"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("medium"),
            {
                "type": "function",
                "name": "get_portfolio_assets",
                "description": "Lista todos os ativos do portfólio com lockups, preço e P&L",
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
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, portfolio_context: str = "", job_id: str | None = None) -> str:
        prompt = f"""Faça uma verificação completa de compliance e regulação.

1. Consulte os ativos e lockups do portfólio
2. Pesquise na web: últimas normas CVM, mudanças na regulação de criptoativos no Brasil
3. Verifique thresholds tributários (R$20k ações, R$35k crypto)
4. Identifique lockups próximos de vencimento
5. Liste alertas regulatórios relevantes

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Rafael Tanaka (Compliance) verificando regulação...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=6, job_id=job_id)
        self.save_analysis(
            tipo_analise="compliance_check",
            input_resumo="Verificação de compliance",
            output=result,
        )
        return result
