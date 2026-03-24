import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.portfolio_service import (
    get_portfolio_allocation,
    get_portfolio_assets,
    get_portfolio_summary,
)
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Fernando Rocha, Chief Risk Officer (CRO) da gestora.

Perfil: Formal, cético, "advogado do diabo". Sempre questiona, nunca otimista demais.
Exemplo de fala: "O cenário parece bom, mas e se Selic subir mais 100bps? Stress test mostra drawdown de 18%."

Sua função:
- Supervisionar risco do portfólio inteiro (cross-asset: ações + crypto + renda fixa)
- Agregar relatórios dos Risk Officers (B3 e Crypto)
- Sintetizar compliance e alertas regulatórios
- Calcular risco agregado: correlações entre classes, stress tests
- Emitir recomendações de hedge e limites
- Você tem poder de VETO — pode barrar operações que violem limites de risco

Você reporta diretamente ao CIO, independente dos Heads de equipe.

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "risco_agregado": {{
    "nivel_geral": "baixo|moderado|alto|critico",
    "score": float,
    "principais_riscos": [str]
  }},
  "exposicao_por_classe": {{
    "acoes": {{"pct": float, "alvo": 50.0, "status": str}},
    "crypto": {{"pct": float, "alvo": 20.0, "status": str}},
    "renda_fixa": {{"pct": float, "alvo": 30.0, "status": str}}
  }},
  "stress_test": {{
    "cenario_bear": str,
    "drawdown_estimado_pct": float,
    "ativos_mais_vulneraveis": [str]
  }},
  "compliance_status": str,
  "vetos": [str],
  "recomendacoes_risco": [str],
  "resumo_executivo": str
}}"""


class ChiefRiskOfficer(BaseAgent):
    agent_name = "cro"
    level = "N1"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("low"),
            {
                "type": "function",
                "name": "get_portfolio_summary",
                "description": "Resumo do portfólio: valor total, rentabilidade",
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
                "description": "Todos os ativos com preço, P&L e lockup",
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
                "description": "Alocação atual vs alvo",
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
        if name == "get_portfolio_summary":
            data = get_portfolio_summary(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_allocation":
            data = get_portfolio_allocation(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(
        self,
        risk_b3_report: str = "",
        risk_crypto_report: str = "",
        compliance_report: str = "",
        quant_report: str = "",
        job_id: str | None = None,
    ) -> str:
        prompt = f"""Faça avaliação de risco consolidada do portfólio inteiro.

Você recebeu os seguintes relatórios dos seus subordinados:

--- RISK B3 (Patrícia Campos) ---
{risk_b3_report[:2000] if risk_b3_report else "Não disponível"}

--- RISK CRYPTO (André Faria) ---
{risk_crypto_report[:2000] if risk_crypto_report else "Não disponível"}

--- COMPLIANCE (Rafael Tanaka) ---
{compliance_report[:2000] if compliance_report else "Não disponível"}

--- QUANT (Eduardo Queiroz) ---
{quant_report[:2000] if quant_report else "Não disponível"}

Instruções:
1. Consulte o portfólio atual para ter visão atualizada
2. Sintetize todos os riscos identificados pelas equipes
3. Faça stress test: cenário bear (Selic +100bps, BTC -30%, USD/BRL +10%)
4. Emita vetos se alguma operação viola limites de risco
5. Dê recomendações de hedge e proteção

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Fernando Rocha (CRO) consolidando riscos...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="risk_consolidation",
            input_resumo="Consolidação de risco cross-asset",
            output=result,
        )
        return result
