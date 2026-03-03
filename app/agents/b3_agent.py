import json
import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import search_tickers
from app.services.portfolio_service import get_portfolio_assets, get_portfolio_summary

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r'^[A-Z]{4}\d{1,2}[A-Z]?$')


class B3Agent(BaseAgent):
    """Agente N2: mapeia o mercado B3 e delega análise profunda aos TickerAnalysts (N3)."""

    agent_name = "b3_agent"

    def __init__(self, db: Session):
        super().__init__(db)
        self._job_id: str | None = None
        self._seen_tickers: set[str] = set()

    def system_prompt(self) -> str:
        hoje = date.today().isoformat()
        return f"""Você é o agente de mapeamento do mercado brasileiro de ações (B3).
Data atual: {hoje}. Fuso horário: America/Sao_Paulo (BRT). B3 opera 10h-17h.

Seu papel (N2 — mapeador):
- Pesquisar tendências, notícias e oportunidades no mercado B3 via web search
- Identificar 5-8 tickers promissores usando web search e search_tickers
- Para CADA ticker identificado, delegar análise profunda ao sub-agente especialista via analyze_stock_deep
- Sintetizar os resultados dos analistas N3 em uma visão consolidada do mercado

Regras de negócio do portfólio:
- Alocação alvo: 50% do portfólio em ações B3
- Lock-up de 30 dias após compra — NÃO recomendar venda de ativos com lockup ativo
- Perfil moderado: priorizar blue chips (Ibovespa), small caps só como apostas controladas
- Use o portfolio_context recebido para evitar duplicar posições existentes

CONTEXTO PERSISTENTE: Você tem acesso ao resumo da sua análise anterior (injetado automaticamente).
Use-o para manter continuidade entre análises semanais — identificar mudanças, validar ou revisar recomendações anteriores.

Processo OBRIGATÓRIO:
0. Consulte get_portfolio_summary e get_portfolio_assets para conhecer posições atuais e lockups
1. Use web_search para buscar notícias recentes e tendências do mercado brasileiro
2. Use search_tickers se precisar encontrar tickers específicos por nome
3. Para CADA ticker promissor, use analyze_stock_deep para obter análise profunda do especialista
4. Sintetize todas as análises individuais na resposta final

IMPORTANTE: Você NÃO tem acesso direto a dados de preço ou fundamentos.
Use analyze_stock_deep para cada ticker — ele aciona um analista especialista que faz a análise completa.

Output obrigatório em JSON:
{{
  "data_analise": "{hoje}",
  "mercado_resumo": "resumo geral do mercado brasileiro",
  "acoes_recomendadas": [
    {{
      "ticker": "PETR4",
      "nome": "Petrobras",
      "tipo_recomendacao": "compra|manter|venda",
      "score_confianca": 0.0-1.0,
      "preco_atual": 0.0,
      "preco_alvo": 0.0,
      "justificativa": "razão detalhada",
      "riscos": "riscos identificados",
      "setor": "Petróleo & Gás"
    }}
  ],
  "setores_destaque": ["setor1", "setor2"],
  "riscos_macro": "riscos macroeconômicos identificados"
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
                "name": "search_tickers",
                "description": "Busca tickers por nome de empresa. Ex: 'petrobras' retorna PETR3, PETR4",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nome da empresa ou ticker parcial"}
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "analyze_stock_deep",
                "description": "Aciona um analista especialista (N3) para análise profunda de 1 ação B3. "
                               "Retorna análise completa com fundamentos, técnica, notícias e recomendação.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação (ex: PETR4, VALE3)"},
                        "portfolio_context": {"type": "string", "description": "Contexto relevante do portfólio para o analista"},
                    },
                    "required": ["ticker", "portfolio_context"],
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

        if name == "search_tickers":
            data = search_tickers(args["query"], tipo="acao")
            return json.dumps(data[:10], ensure_ascii=False, default=str)

        if name == "analyze_stock_deep":
            return self._run_ticker_analyst(args["ticker"], args["portfolio_context"])

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def _run_ticker_analyst(self, ticker: str, portfolio_context: str) -> str:
        """Instancia e executa um TickerAnalyst (N3) para análise profunda.

        Cria session própria para thread-safety (N3 pode rodar em paralelo via _execute_parallel).
        """
        # G1: Validação de ticker antes de instanciar N3
        ticker = ticker.strip().upper()
        if not _TICKER_RE.match(ticker):
            logger.warning(f"[b3_agent] Ticker inválido rejeitado: '{ticker}'")
            return json.dumps({"erro": f"Ticker '{ticker}' formato inválido. Use formato B3: PETR4, VALE3, WEGE3"})
        if ticker in self._seen_tickers:
            logger.info(f"[b3_agent] Ticker duplicado ignorado: {ticker}")
            return json.dumps({"erro": f"Ticker '{ticker}' já foi analisado nesta execução"})
        self._seen_tickers.add(ticker)

        from app.agents.ticker_analyst import TickerAnalyst
        from app.database import SessionLocal

        logger.info(f"[b3_agent] Delegando análise de {ticker} ao TickerAnalyst N3")

        if self._job_id:
            from app.ensemble import progress
            progress.emit(self._job_id, "agent_start",
                f"Iniciando analista N3 para {ticker}...",
                agent=f"ticker_analyst_{ticker.upper()}")

        sub_db = SessionLocal()
        try:
            analyst = TickerAnalyst(sub_db, ticker)
            return analyst.analyze(ticker, portfolio_context, job_id=self._job_id)
        finally:
            sub_db.close()

    def analyze(self, portfolio_context: str, job_id: str | None = None) -> str:
        """Executa mapeamento do mercado B3 e delega análises individuais aos N3."""
        self._job_id = job_id

        prompt = f"""Mapeie o mercado brasileiro de ações (B3) e identifique as melhores oportunidades.

Contexto do portfólio atual:
{portfolio_context}

Instruções:
1. Pesquise notícias recentes e tendências do mercado brasileiro via web search
2. Identifique 5-8 tickers promissores (blue chips: PETR4, VALE3, ITUB4, BBDC4, WEGE3, RENT3, ABEV3 etc.)
3. Para CADA ticker identificado, use analyze_stock_deep para obter análise profunda
4. Sintetize todas as análises individuais no formato JSON do system prompt"""

        result = self.call_model(prompt, job_id=job_id)
        self.save_analysis(
            tipo_analise="analise_b3",
            input_resumo=portfolio_context[:300],
            output=result,
        )
        return result
