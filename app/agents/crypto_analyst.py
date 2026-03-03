import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import (
    get_crypto_history,
    get_crypto_price,
)

logger = logging.getLogger(__name__)


class CryptoAnalyst(BaseAgent):
    """Agente N3: análise profunda de 1 criptoativo individual."""

    def __init__(self, db: Session, crypto_id: str):
        self.crypto_id = crypto_id.lower()
        self.agent_name = f"crypto_analyst_{self.crypto_id}"
        super().__init__(db)

    def system_prompt(self) -> str:
        hoje = date.today().isoformat()
        return f"""Você é um analista especializado focado exclusivamente em {self.crypto_id}.
Data atual: {hoje}. Fuso horário: America/Sao_Paulo (BRT). Cripto opera 24/7.

Seu papel:
- Realizar análise profunda e detalhada de {self.crypto_id}
- Avaliar métricas on-chain: TVL, endereços ativos, volume de transações, hash rate (se aplicável)
- Avaliar técnica: tendência, suportes, resistências, médias móveis, RSI
- Pesquisar notícias recentes, sentimento de mercado e regulação BR

Regras de negócio do portfólio:
- Alocação alvo: 20% crypto (dentro dos 100% do portfólio)
- Lock-up de 30 dias após compra — se ativo em carteira, verificar se lockup expirou antes de recomendar venda
- Perfil moderado: priorizar BTC/ETH, avaliar risco-retorno adequado ao perfil
- Usar o contexto do portfólio fornecido para contextualizar a recomendação

Processo de análise:
1. Use web_search para buscar notícias recentes sobre {self.crypto_id}, regulação cripto no Brasil e sentimento
2. Use get_crypto_price para o preço atual em USD e BRL
3. Use get_crypto_history para análise técnica (tendência, suportes, resistências)

Output obrigatório em JSON:
{{
  "id": "{self.crypto_id}",
  "ticker": "ticker no formato padrão (ex: BTC-USD)",
  "nome": "nome completo",
  "tipo_recomendacao": "compra|manter|venda",
  "score_confianca": 0.0-1.0,
  "preco_atual_usd": 0.0,
  "preco_atual_brl": 0.0,
  "justificativa": "razão detalhada da recomendação",
  "riscos": "riscos identificados",
  "onchain": {{
    "metricas_relevantes": "resumo de métricas on-chain encontradas",
    "avaliacao": "resumo on-chain"
  }},
  "tecnica": {{
    "tendencia": "alta|lateral|baixa",
    "suporte_usd": 0.0,
    "resistencia_usd": 0.0,
    "avaliacao": "resumo técnico"
  }},
  "sentimento": "resumo do sentimento de mercado",
  "regulacao_br": "impacto regulatório no Brasil"
}}

Sempre responda em Português (BR). Seja profundo e fundamentado."""

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("high"),  # N3 análise profunda precisa mais contexto
            {
                "type": "function",
                "name": "get_crypto_price",
                "description": "Busca preço atual de uma criptomoeda em USD e BRL. IDs: bitcoin, ethereum, solana, cardano, polkadot, chainlink, avalanche",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID da crypto (ex: bitcoin, ethereum, solana)"}
                    },
                    "required": ["crypto_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_crypto_history",
                "description": "Busca histórico OHLCV de uma criptomoeda. Períodos: 1mo, 3mo, 6mo, 1y",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID da crypto"},
                        "period": {"type": "string", "description": "Período: 1mo, 3mo, 6mo, 1y"},
                    },
                    "required": ["crypto_id", "period"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_crypto_price":
            data = get_crypto_price(args["crypto_id"], self.db)
            return json.dumps(data or {"erro": "Dados não disponíveis"}, ensure_ascii=False, default=str)

        if name == "get_crypto_history":
            data = get_crypto_history(args["crypto_id"], args.get("period", "1y"), self.db)
            if not data:
                return json.dumps({"erro": "Dados não disponíveis"})
            if len(data) > 60:
                # Enviar todos os fechamentos para análise técnica completa
                return json.dumps({
                    "total_registros": len(data),
                    "fechamentos": [d["fechamento"] for d in data],
                    "primeiro": data[0],
                    "ultimo": data[-1],
                }, ensure_ascii=False, default=str)
            return json.dumps(data, ensure_ascii=False, default=str)

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, crypto_id: str, portfolio_context: str, job_id: str | None = None) -> str:
        """Executa análise profunda de um criptoativo individual."""
        prompt = f"""Realize uma análise profunda e completa de {crypto_id}.

Contexto do portfólio:
{portfolio_context}

Instruções:
1. Pesquise notícias recentes sobre {crypto_id}, regulação cripto no Brasil e sentimento
2. Consulte preço atual em USD e BRL
3. Analise histórico de preços (6 meses) para técnica
4. Busque informações on-chain relevantes via web search
5. Retorne sua análise no formato JSON especificado no system prompt"""

        result = self.call_model(prompt, job_id=job_id)
        self.save_analysis(
            tipo_analise="analise_crypto_individual",
            input_resumo=f"Análise profunda {crypto_id}",
            output=result,
        )
        return result
