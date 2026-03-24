import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import get_crypto_price
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Lucas Webb, Analista On-Chain de Crypto.

Perfil: Informal, detetive, rastreia baleias e fluxos de exchange.
Exemplo de fala: "Exchange outflow tá no maior nível do ano. Baleias acumulando."

Sua função (EXCLUSIVA de crypto — não existe equivalente em ações):
- Monitorar whale wallets (movimentações de grandes carteiras)
- Rastrear exchange inflows/outflows (sinal de sell pressure vs acumulação)
- Analisar métricas on-chain: MVRV ratio, SOPR, NVT, active addresses
- Monitorar hash rate (BTC) e staking ratio (ETH)
- Identificar sinais de distribuição ou acumulação
- Usar dados de Glassnode, Dune Analytics, DefiLlama

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "metricas_onchain": {{
    "btc": {{
      "exchange_balance_trend": str,
      "whale_accumulation": bool,
      "mvrv_ratio": str,
      "hash_rate_trend": str,
      "active_addresses_trend": str
    }},
    "eth": {{
      "exchange_balance_trend": str,
      "staking_ratio": str,
      "gas_fees_trend": str,
      "defi_tvl_trend": str
    }}
  }},
  "sinais_por_crypto": [
    {{
      "id": str,
      "sinal_onchain": "acumulacao|distribuicao|neutro",
      "metricas_chave": [str],
      "score": float,
      "justificativa": str
    }}
  ],
  "whale_alerts": [str],
  "resumo_executivo": str
}}"""


class OnChainAnalyst(BaseAgent):
    agent_name = "onchain_analyst"
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
                        "crypto_id": {"type": "string", "description": "ID (ex: bitcoin, ethereum)"},
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
        prompt = f"""Faça análise on-chain das seguintes criptomoedas: {cryptos_str}

1. Pesquise na web: dados on-chain do Glassnode, Dune Analytics, DefiLlama
2. Para Bitcoin: exchange balance, whale movements, MVRV, hash rate
3. Para Ethereum: staking ratio, gas fees, DeFi TVL
4. Para cada crypto: identifique se estamos em fase de acumulação ou distribuição
5. Relate whale alerts recentes

{f"Contexto do portfólio: {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                f"Lucas Webb (On-Chain) rastreando baleias e fluxos de {cryptos_str}...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=8, job_id=job_id)
        self.save_analysis(
            tipo_analise="onchain_analysis",
            input_resumo=f"Análise on-chain: {cryptos_str}",
            output=result,
        )
        return result
