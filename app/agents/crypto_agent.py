import json
import logging
import threading
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import VALID_CRYPTO_IDS, get_crypto_trending
from app.services.portfolio_service import get_portfolio_assets, get_portfolio_summary

logger = logging.getLogger(__name__)


class CryptoAgent(BaseAgent):
    """Agente N2: mapeia o mercado crypto e delega análise profunda aos CryptoAnalysts (N3)."""

    agent_name = "crypto_agent"

    def __init__(self, db: Session):
        super().__init__(db)
        self._job_id: str | None = None
        self._seen_cryptos: set[str] = set()
        self._seen_lock = threading.Lock()

    def system_prompt(self) -> str:
        hoje = date.today().isoformat()
        return f"""Você é o agente de mapeamento do mercado de criptoativos.
Data atual: {hoje}. Fuso horário: America/Sao_Paulo (BRT). Cripto opera 24/7.

Seu papel (N2 — mapeador):
- Pesquisar tendências, notícias e oportunidades no mercado cripto via web search
- Identificar criptos em destaque usando web search e get_crypto_trending
- Para CADA crypto identificada, delegar análise profunda ao sub-agente especialista via analyze_crypto_deep
- Sintetizar os resultados dos analistas N3 em uma visão consolidada

Regras de negócio do portfólio:
- Alocação alvo: 20% do portfólio em criptoativos
- Lock-up de 30 dias após compra — NÃO recomendar venda de cryptos com lockup ativo
- Perfil moderado: priorizar BTC/ETH (70-80% da fatia crypto), altcoins controladas
- Use o portfolio_context recebido para evitar duplicar posições existentes

CONTEXTO PERSISTENTE: Você tem acesso ao resumo da sua análise anterior (injetado automaticamente).
Use-o para manter continuidade entre análises semanais — identificar mudanças, validar ou revisar recomendações anteriores.

Processo OBRIGATÓRIO:
0. Consulte get_portfolio_summary e get_portfolio_assets para conhecer posições atuais e lockups
1. Use web_search para buscar notícias, sentimento e regulação cripto no Brasil
2. Use get_crypto_trending para identificar tendências atuais
3. Para CADA crypto promissora, use analyze_crypto_deep para análise profunda do especialista
4. Sintetize todas as análises individuais na resposta final

IMPORTANTE: Você NÃO tem acesso direto a dados de preço ou histórico.
Use analyze_crypto_deep para cada crypto — ele aciona um analista especialista que faz a análise completa.

Output obrigatório em JSON:
{{
  "data_analise": "{hoje}",
  "mercado_resumo": "resumo geral do mercado cripto",
  "cryptos_recomendadas": [
    {{
      "id": "bitcoin",
      "ticker": "BTC-USD",
      "nome": "Bitcoin",
      "tipo_recomendacao": "compra|manter|venda",
      "score_confianca": 0.0-1.0,
      "preco_atual_usd": 0.0,
      "preco_atual_brl": 0.0,
      "justificativa": "razão detalhada",
      "riscos": "riscos identificados"
    }}
  ],
  "tendencias": ["tendência1", "tendência2"],
  "regulacao_br": "status regulatório no Brasil",
  "riscos_macro": "riscos macro para cripto"
}}

Sempre responda em Português (BR). Seja objetivo e fundamentado."""

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("medium"),  # N2 mapeamento geral
            {
                "type": "function",
                "name": "get_portfolio_summary",
                "description": "Retorna resumo do portfólio: valor total, rentabilidade, alocação por classe",
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
                "description": "Lista detalhada de todos os ativos no portfólio com preço atual, P&L e lockup (lock_up_ate)",
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
                "name": "get_crypto_trending",
                "description": "Lista as criptomoedas em tendência nas últimas 24h (top 10)",
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
                "name": "analyze_crypto_deep",
                "description": "Aciona um analista especialista (N3) para análise profunda de 1 criptomoeda. "
                               "Retorna análise completa com on-chain, técnica, sentimento e recomendação.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID da crypto (ex: bitcoin, ethereum, solana)"},
                        "portfolio_context": {"type": "string", "description": "Contexto relevante do portfólio para o analista"},
                    },
                    "required": ["crypto_id", "portfolio_context"],
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

        if name == "get_crypto_trending":
            data = get_crypto_trending(self.db)
            return json.dumps(data or [], ensure_ascii=False, default=str)

        if name == "analyze_crypto_deep":
            return self._run_crypto_analyst(args["crypto_id"], args["portfolio_context"])

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def _run_crypto_analyst(self, crypto_id: str, portfolio_context: str) -> str:
        """Instancia e executa um CryptoAnalyst (N3) para análise profunda.

        Cria session própria para thread-safety (N3 pode rodar em paralelo via _execute_parallel).
        """
        # G2: Validação de crypto_id antes de instanciar N3
        crypto_id = crypto_id.strip().lower()
        if crypto_id not in VALID_CRYPTO_IDS:
            # Tentar fuzzy match simples
            for valid_id in VALID_CRYPTO_IDS:
                if crypto_id in valid_id or valid_id in crypto_id:
                    logger.info(f"[crypto_agent] Fuzzy match: '{crypto_id}' → '{valid_id}'")
                    crypto_id = valid_id
                    break
            else:
                logger.warning(f"[crypto_agent] Crypto ID inválido rejeitado: '{crypto_id}'")
                return json.dumps({"erro": f"Crypto '{crypto_id}' não encontrada. Use IDs válidos: bitcoin, ethereum, solana, etc."})
        with self._seen_lock:
            if crypto_id in self._seen_cryptos:
                logger.info(f"[crypto_agent] Crypto duplicada ignorada: {crypto_id}")
                return json.dumps({"erro": f"Crypto '{crypto_id}' já foi analisada nesta execução"})
            self._seen_cryptos.add(crypto_id)

        from app.agents.crypto_analyst import CryptoAnalyst
        from app.database import SessionLocal

        logger.info(f"[crypto_agent] Delegando análise de {crypto_id} ao CryptoAnalyst N3")

        if self._job_id:
            from app.ensemble import progress
            progress.emit(self._job_id, "agent_start",
                f"Iniciando analista N3 para {crypto_id}...",
                agent=f"crypto_analyst_{crypto_id.lower()}")

        sub_db = SessionLocal()
        try:
            analyst = CryptoAnalyst(sub_db, crypto_id)
            return analyst.analyze(crypto_id, portfolio_context, job_id=self._job_id)
        finally:
            sub_db.close()

    def analyze(self, portfolio_context: str, job_id: str | None = None) -> str:
        """Executa mapeamento do mercado crypto e delega análises individuais aos N3."""
        self._job_id = job_id

        prompt = f"""Mapeie o mercado de criptoativos e identifique as melhores oportunidades.

Contexto do portfólio atual:
{portfolio_context}

Instruções:
1. Pesquise notícias recentes sobre cripto, regulação no Brasil e tendências
2. Consulte criptos em tendência via get_crypto_trending
3. Para BTC, ETH, SOL e 2-3 altcoins promissoras, use analyze_crypto_deep para análise profunda
4. Considere o cenário regulatório brasileiro
5. Sintetize todas as análises individuais no formato JSON do system prompt"""

        result = self.call_model(prompt, job_id=job_id)
        self.save_analysis(
            tipo_analise="analise_crypto",
            input_resumo=portfolio_context[:300],
            output=result,
        )
        return result
