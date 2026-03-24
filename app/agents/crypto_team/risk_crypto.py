import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_crypto_history
from app.services.portfolio_service import get_portfolio_allocation, get_portfolio_assets
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é André Faria, Risk Officer da equipe Crypto.

Perfil: Cauteloso, alarmista, sempre questiona segurança.
Exemplo de fala: "Já viram a audit desse protocolo? Smart contract risk é altíssimo."

Sua função:
- Avaliar smart contract risk de protocolos DeFi
- Monitorar exchange/custody risk (hacks, insolvência)
- Rastrear regulatory risk (CVM, SEC, marcos legais)
- Calcular correlação com BTC (beta > 1 para maioria dos altcoins)
- Avaliar liquidez em mercados BR (Mercado Bitcoin, Binance BR)
- Considerar fat tails na distribuição de retornos (crypto não é gaussiana)

Você reporta ao Fernando Rocha (CRO), NÃO ao Head Crypto.

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "exposicao_crypto": {{
    "pct_portfolio": float,
    "alvo_pct": 20.0,
    "desvio_pct": float,
    "status": "dentro|acima|abaixo"
  }},
  "riscos_por_ativo": [
    {{
      "id": str,
      "smart_contract_risk": "alto|medio|baixo",
      "exchange_risk": str,
      "regulatory_risk": str,
      "liquidez_br": str,
      "correlacao_btc": float
    }}
  ],
  "riscos_sistemicos": [
    {{"tipo": str, "descricao": str, "severidade": "alta|media|baixa"}}
  ],
  "resumo_executivo": str
}}"""


class RiskCrypto(BaseAgent):
    agent_name = "risk_crypto"
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
                "description": "Todos os ativos do portfólio com preço e P&L",
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
            {
                "type": "function",
                "name": "get_crypto_history",
                "description": "Histórico OHLCV de uma criptomoeda (para calcular volatilidade)",
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
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_portfolio_allocation":
            data = get_portfolio_allocation(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        if name == "get_crypto_history":
            data = get_crypto_history(args["crypto_id"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, portfolio_context: str = "", job_id: str | None = None) -> str:
        prompt = f"""Faça avaliação de risco completa da carteira de criptomoedas.

1. Consulte ativos e alocação do portfólio
2. Pesquise na web: hacks recentes, audits de protocolos, regulação CVM/SEC
3. Para cada crypto no portfólio, avalie smart contract risk, exchange risk, regulação
4. Verifique se alocação em crypto está dentro do alvo (20%)
5. Identifique riscos sistêmicos (contagion, regulatory crackdown)

{f"Contexto: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "André Faria (Risk Crypto) avaliando exposição...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="risk_crypto",
            input_resumo="Avaliação de risco crypto",
            output=result,
        )
        return result
