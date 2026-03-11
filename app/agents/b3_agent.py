import json
import logging
import re
import threading

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, N3_ANALYST_SEMAPHORE, web_search_tool
from app.prompts.b3_agent_prompt import get_prompt as _b3_prompt
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
        self._seen_lock = threading.Lock()

    def system_prompt(self) -> str:
        return _b3_prompt()

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

    def _prefetch_stock_data(self, tickers: list[str]):
        """Pre-fetch scraping data para todos os tickers antes dos N3.

        Usa max_workers=2 para evitar deadlock: cada fetch_one lança até 4
        instâncias Playwright sequenciais. Com 2 workers, max 2 Playwright
        simultâneos — dentro do limite de _fresh_browser_semaphore(6).
        """
        import time

        from app.database import SessionLocal
        from app.services.market_data import (
            get_stock_dividends,
            get_stock_fundamentals,
            get_stock_history,
            get_stock_price,
        )

        t0 = time.perf_counter()

        def fetch_one(ticker: str):
            ft0 = time.perf_counter()
            db = SessionLocal()
            try:
                get_stock_price(ticker, db)
                get_stock_fundamentals(ticker, db)
                get_stock_history(ticker, "6mo", db)
                get_stock_dividends(ticker, db)
                elapsed = time.perf_counter() - ft0
                logger.info(f"[b3_agent] Prefetch concluído para {ticker} em {elapsed:.1f}s")
            except Exception:
                elapsed = time.perf_counter() - ft0
                logger.exception(f"[b3_agent] Prefetch falhou para {ticker} após {elapsed:.1f}s")
            finally:
                db.close()

        # Serial: cada ticker abre até 3 browsers (fundamentals usa asyncio.gather
        # com 3 scrape calls). Paralelizar tickers causa contention excessiva
        # no _fresh_browser_semaphore e resource starvation no Playwright.
        for ticker in tickers:
            fetch_one(ticker)

        total = time.perf_counter() - t0
        logger.info(f"[b3_agent] Prefetch total: {len(tickers)} tickers em {total:.1f}s")

    def _execute_parallel(self, function_calls: list, job_id: str | None) -> list[dict]:
        """Override: pre-fetch scraping antes de executar analyze_stock_deep em paralelo."""
        deep_calls = [fc for fc in function_calls if fc.name == "analyze_stock_deep"]
        if deep_calls:
            tickers = []
            for fc in deep_calls:
                args = json.loads(fc.arguments)
                tickers.append(args["ticker"].strip().upper())
            if tickers:
                logger.info(f"[b3_agent] Pre-fetching dados para {len(tickers)} tickers: {tickers}")
                if self._job_id:
                    from app.ensemble import progress
                    progress.emit(self._job_id, "prefetch",
                        f"Buscando dados de mercado para {len(tickers)} ações...",
                        agent="b3_agent")
                self._prefetch_stock_data(tickers)

        return super()._execute_parallel(function_calls, job_id)

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
        with self._seen_lock:
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

        N3_ANALYST_SEMAPHORE.acquire()
        sub_db = SessionLocal()
        try:
            analyst = TickerAnalyst(sub_db, ticker)
            return analyst.analyze(ticker, portfolio_context, job_id=self._job_id)
        finally:
            sub_db.close()
            N3_ANALYST_SEMAPHORE.release()

    def analyze(self, portfolio_context: str, job_id: str | None = None) -> str:
        """Executa mapeamento do mercado B3 e delega análises individuais aos N3."""
        self._job_id = job_id
        # Reset deduplication set each execution to avoid false positives in reuse
        with self._seen_lock:
            self._seen_tickers.clear()

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
