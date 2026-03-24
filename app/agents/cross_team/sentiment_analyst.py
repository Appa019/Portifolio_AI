import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é Marina Leal, Analista de Sentimento e Notícias de uma gestora de investimentos brasileira.

Perfil: Informal, antenada, monitora fluxo de notícias em tempo real.
Exemplo de fala: "InfoMoney tá bullish em Petro, Twitter tá bearish em ETH."

Sua função:
- Monitorar fluxo de notícias financeiras (InfoMoney, Valor Econômico, Bloomberg, CoinDesk, The Block)
- Classificar sentimento (bullish/bearish/neutro) por ativo e setor
- Detectar eventos materiais (M&A, guidance change, hack, regulatory action)
- Agregar headlines relevantes para o portfólio
- Identificar narrativas dominantes no mercado

Data de hoje: {hoje}

Responda SEMPRE em português (BR).

Retorne em JSON:
{{
  "sentimento_geral": {{
    "b3": "bullish|bearish|neutro",
    "crypto": "bullish|bearish|neutro",
    "score_b3": float,  // -1.0 a 1.0
    "score_crypto": float  // -1.0 a 1.0
  }},
  "noticias_destaque": [
    {{"titulo": str, "fonte": str, "impacto": "positivo|negativo|neutro", "ativos_afetados": [str]}}
  ],
  "narrativas_dominantes": {{
    "b3": [str],
    "crypto": [str]
  }},
  "alertas_material": [str],
  "resumo_executivo": str
}}"""


class SentimentAnalyst(BaseAgent):
    agent_name = "sentiment_analyst"
    level = "N2"

    def __init__(self, db: Session, budget_tracker: RunBudgetTracker | None = None):
        super().__init__(db, budget_tracker)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(hoje=date.today().isoformat())

    def get_tools(self) -> list[dict]:
        return [web_search_tool("high")]

    def execute_function(self, name: str, args: dict) -> str:
        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, portfolio_context: str = "", job_id: str | None = None) -> str:
        prompt = f"""Produza um digest de sentimento e notícias do mercado financeiro.

1. Pesquise notícias recentes sobre mercado brasileiro (B3, Ibovespa, principais ações)
2. Pesquise notícias recentes sobre mercado crypto (Bitcoin, Ethereum, altcoins relevantes)
3. Classifique o sentimento geral para cada classe
4. Identifique eventos materiais que possam afetar decisões de investimento
5. Liste narrativas dominantes em cada mercado

{f"Contexto do portfólio (ativos que nos importam): {portfolio_context}" if portfolio_context else ""}

Retorne no formato JSON especificado no system prompt."""

        if job_id:
            from app.services import progress
            progress.emit(job_id, "agent_start",
                "Marina Leal (Sentimento) varrendo notícias...",
                agent=self.agent_name)

        result = self.call_model(prompt, max_rounds=6, job_id=job_id)
        self.save_analysis(
            tipo_analise="sentiment_analysis",
            input_resumo="Análise de sentimento e notícias",
            output=result,
        )
        return result
