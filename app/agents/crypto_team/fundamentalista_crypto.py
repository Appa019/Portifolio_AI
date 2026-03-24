import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_crypto_price
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Thiago Satoshi, Analista Fundamentalista de Crypto.

Perfil: Informal, entusiasta de tokenomics, sempre questiona métricas infladas.
Exemplo de fala: "Esse TVL é real ou é airdrop farming? Token supply schedule é inflacionário."

Sua função:
- Analisar tokenomics: supply schedule, inflation rate, vesting cliffs, token burns
- Avaliar equipe/fundadores, roadmap e competitividade do protocolo
- Verificar TVL (Total Value Locked) e revenue real do protocolo
- Identificar "real yield" vs yield inflacionário
- Comparar com competitors no mesmo segmento (L1, L2, DeFi, etc.)

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "analises_fundamentalistas": [
    {{
      "id": str,
      "ticker": str,
      "nome": str,
      "segmento": str,
      "tokenomics": {{
        "supply_max": str,
        "supply_circulante": str,
        "inflation_rate": str,
        "vesting_cliff": str,
        "token_burn": bool
      }},
      "metricas_protocolo": {{
        "tvl_usd": str,
        "revenue_protocolo": str,
        "real_yield": bool,
        "active_users": str
      }},
      "competitive_moat": str,
      "recomendacao": "comprar|manter|vender",
      "score": float,
      "justificativa": str
    }}
  ],
  "narrativas_quentes": [str],
  "resumo_executivo": str
}}"""


class FundamentalistaCrypto(BaseAgent):
    agent_name = "fundamentalista_crypto"
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
                "name": "get_crypto_price",
                "description": "Preço atual de uma criptomoeda em USD e BRL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID da crypto (ex: bitcoin, ethereum)"},
                    },
                    "required": ["crypto_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_crypto_price":
            data = get_crypto_price(args["crypto_id"], db=self.db)
            return json.dumps(data, ensure_ascii=False, default=str)
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, cryptos: list[str], portfolio_context: str = "", job_id: str | None = None) -> str:
        cryptos_str = ", ".join(cryptos)
        prompt = f"""Faça análise fundamentalista das seguintes criptomoedas: {cryptos_str}

1. Para cada crypto, busque preço atual
2. Pesquise na web: tokenomics, TVL, revenue do protocolo, equipe, roadmap
3. Avalie se o TVL e yield são reais ou inflados por incentivos
4. Compare com competitors no mesmo segmento

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Thiago Satoshi (Fundamentalista Crypto) analisando {cryptos_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=10, job_id=job_id)
        self.save_analysis(
            tipo_analise="fundamental_crypto",
            input_resumo=f"Análise fundamentalista crypto: {cryptos_str}",
            output=result,
        )
        return result
