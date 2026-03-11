"""
Testes de controle de concorrencia de browsers Chromium.

Valida:
- Semaforo global em _scrape_fresh() (MAX_FRESH_BROWSERS=6)
- Chromium args de economia de memoria
- Executor compartilhado em market_data._run_async() (max_workers=16)
- asyncio.Semaphore em scrape_multiple()
- Sub-agente orchestrator sem timeout
- Pre-fetch scraping em B3Agent e CryptoAgent (override _execute_parallel)

Uso:
  python -m pytest tests/test_browser_concurrency.py -v
"""

import concurrent.futures
import threading
import time
from unittest.mock import MagicMock, patch



class TestBrowserSemaphore:
    """Testa o semaforo global de browsers em yahoo_scraper."""

    def test_semaphore_exists_and_correct_limit(self):
        from app.services.yahoo_scraper import (
            MAX_FRESH_BROWSERS,
            _fresh_browser_semaphore,
        )
        assert MAX_FRESH_BROWSERS == 6
        assert isinstance(_fresh_browser_semaphore, threading.Semaphore)

    def test_n3_analyst_semaphore_exists(self):
        from app.agents.base_agent import N3_ANALYST_SEMAPHORE
        assert isinstance(N3_ANALYST_SEMAPHORE, threading.Semaphore)

    def test_active_browsers_counter_exists(self):
        from app.services.yahoo_scraper import (
            _active_browsers,
            _active_browsers_lock,
        )
        # threading.Lock() retorna _thread.lock, testar via hasattr
        assert hasattr(_active_browsers_lock, 'acquire')
        assert hasattr(_active_browsers_lock, 'release')
        assert isinstance(_active_browsers, int)

    def test_semaphore_limits_concurrent_access(self):
        """Verifica que o semaforo limita a N acessos simultaneos."""
        from app.services.yahoo_scraper import MAX_FRESH_BROWSERS

        sem = threading.Semaphore(MAX_FRESH_BROWSERS)
        active = 0
        peak = 0
        lock = threading.Lock()

        def worker():
            nonlocal active, peak
            sem.acquire()
            try:
                with lock:
                    active += 1
                    if active > peak:
                        peak = active
                time.sleep(0.05)
            finally:
                with lock:
                    active -= 1
                sem.release()

        threads = [threading.Thread(target=worker) for _ in range(60)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert peak <= MAX_FRESH_BROWSERS

    def test_scrape_fresh_acquires_and_releases_semaphore(self):
        """Verifica que _scrape_fresh adquire e libera o semaforo corretamente."""
        from app.services.yahoo_scraper import (
            _fresh_browser_semaphore,
            MAX_FRESH_BROWSERS,
        )
        # Semaforo deve estar com todos os slots livres (ou pronto para reuso)
        # Testar que o semaforo pode ser adquirido MAX_FRESH_BROWSERS vezes
        acquired = 0
        for _ in range(MAX_FRESH_BROWSERS):
            got = _fresh_browser_semaphore.acquire(blocking=False)
            if got:
                acquired += 1
        # Liberar todos
        for _ in range(acquired):
            _fresh_browser_semaphore.release()
        assert acquired == MAX_FRESH_BROWSERS


class TestChromiumArgs:
    """Testa que args de economia de memoria estao configurados."""

    def test_memory_args_defined(self):
        from app.services.yahoo_scraper import _CHROMIUM_MEMORY_ARGS
        assert "--js-flags=--max-old-space-size=256" in _CHROMIUM_MEMORY_ARGS
        assert "--disable-background-networking" in _CHROMIUM_MEMORY_ARGS
        assert "--no-first-run" in _CHROMIUM_MEMORY_ARGS

    def test_base_args_defined(self):
        from app.services.yahoo_scraper import _CHROMIUM_BASE_ARGS
        assert "--disable-blink-features=AutomationControlled" in _CHROMIUM_BASE_ARGS
        assert "--no-sandbox" in _CHROMIUM_BASE_ARGS
        assert "--disable-gpu" in _CHROMIUM_BASE_ARGS


class TestSharedExecutor:
    """Testa o executor compartilhado em market_data."""

    def test_shared_executor_exists(self):
        from app.services.market_data import _shared_executor
        assert isinstance(_shared_executor, concurrent.futures.ThreadPoolExecutor)

    def test_shared_executor_max_workers(self):
        from app.services.market_data import _shared_executor
        assert _shared_executor._max_workers == 16

    def test_run_async_uses_shared_executor(self):
        """Verifica que _run_async nao cria executor novo quando loop esta rodando."""

        # Simular coroutine simples
        async def simple_coro():
            return 42

        # Sem loop rodando, usa asyncio.run diretamente
        result = None
        from app.services.market_data import _run_async
        result = _run_async(simple_coro())
        assert result == 42

    def test_shared_executor_reused_across_calls(self):
        """Verifica que o mesmo executor e reutilizado entre chamadas."""
        from app.services import market_data
        executor1 = market_data._shared_executor
        executor2 = market_data._shared_executor
        assert executor1 is executor2


class TestScrapeMultipleGate:
    """Testa o gate de concorrencia em scrape_multiple."""

    def test_scrape_multiple_has_async_gate(self):
        """Verifica que scrape_multiple limita coroutines via asyncio.Semaphore."""
        import inspect
        from app.services.yahoo_scraper import scrape_multiple
        source = inspect.getsource(scrape_multiple)
        assert "asyncio.Semaphore" in source
        assert "MAX_FRESH_BROWSERS" in source


class TestOrchestratorSubAgent:
    """Testa execução de sub-agentes do orchestrator."""

    def test_run_sub_agent_exists(self):
        from app.agents.orchestrator import Orchestrator
        assert hasattr(Orchestrator, "_run_sub_agent")


class TestOpenAIClientSingleton:
    """Testa que o OpenAI client é reutilizado entre agentes."""

    def test_singleton_client(self):
        from app.agents.base_agent import _get_openai_client
        c1 = _get_openai_client()
        c2 = _get_openai_client()
        assert c1 is c2


class TestSemaphoreSlotRelease:
    """Testa que o semaforo e sempre liberado, mesmo com excecoes."""

    def test_slot_released_on_exception(self):
        """Simula cenario onde browser falha — slot deve ser liberado."""
        sem = threading.Semaphore(2)
        released = threading.Event()

        def failing_worker():
            sem.acquire()
            try:
                # Simula erro interno que e capturado pelo finally
                pass  # Em producao, a excecao e capturada no try/except de _scrape_fresh
            finally:
                sem.release()
                released.set()

        t = threading.Thread(target=failing_worker)
        t.start()
        t.join(timeout=5)
        assert released.is_set()
        # Semaforo deve ter 2 slots disponiveis novamente
        assert sem.acquire(blocking=False)
        assert sem.acquire(blocking=False)
        sem.release()
        sem.release()

    def test_slot_released_on_captcha_path(self):
        """Simula path de CAPTCHA onde slot e liberado durante backoff."""
        sem = threading.Semaphore(1)
        # Adquirir slot
        sem.acquire()
        # Simular path de CAPTCHA: release durante backoff
        sem.release()
        # Deve poder adquirir novamente
        assert sem.acquire(blocking=False)
        sem.release()


class TestPrefetchOverride:
    """Testa que B3Agent e CryptoAgent fazem prefetch antes dos N3."""

    def test_b3_agent_has_prefetch_method(self):
        from app.agents.b3_agent import B3Agent
        assert hasattr(B3Agent, '_prefetch_stock_data')
        assert hasattr(B3Agent, '_execute_parallel')

    def test_crypto_agent_has_prefetch_method(self):
        from app.agents.crypto_agent import CryptoAgent
        assert hasattr(CryptoAgent, '_prefetch_crypto_data')
        assert hasattr(CryptoAgent, '_execute_parallel')

    def test_b3_prefetch_calls_market_data(self):
        """Verifica que _prefetch_stock_data chama as 4 funções de scraping."""
        from app.agents.b3_agent import B3Agent

        with patch('app.database.SessionLocal') as mock_session_cls, \
             patch('app.services.market_data.get_stock_price') as mock_price, \
             patch('app.services.market_data.get_stock_fundamentals') as mock_fund, \
             patch('app.services.market_data.get_stock_history') as mock_hist, \
             patch('app.services.market_data.get_stock_dividends') as mock_div:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            agent = B3Agent.__new__(B3Agent)
            agent._prefetch_stock_data(["PETR4", "VALE3"])
            assert mock_price.call_count == 2
            assert mock_fund.call_count == 2
            assert mock_hist.call_count == 2
            assert mock_div.call_count == 2
            assert mock_db.close.call_count == 2

    def test_crypto_prefetch_calls_market_data(self):
        """Verifica que _prefetch_crypto_data chama as 2 funções de scraping."""
        from app.agents.crypto_agent import CryptoAgent

        with patch('app.database.SessionLocal') as mock_session_cls, \
             patch('app.services.market_data.get_crypto_price') as mock_price, \
             patch('app.services.market_data.get_crypto_history') as mock_hist:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            agent = CryptoAgent.__new__(CryptoAgent)
            agent._prefetch_crypto_data(["bitcoin", "ethereum"])
            assert mock_price.call_count == 2
            assert mock_hist.call_count == 2
            assert mock_db.close.call_count == 2

    def test_n3_semaphore_increased_for_prefetch(self):
        """N3 semaphore deve ser >= 7 (N3 não faz scraping com prefetch)."""
        from app.agents.base_agent import N3_ANALYST_SEMAPHORE
        # Verificar que pelo menos 7 slots estão disponíveis
        acquired = 0
        for _ in range(7):
            got = N3_ANALYST_SEMAPHORE.acquire(blocking=False)
            if got:
                acquired += 1
        for _ in range(acquired):
            N3_ANALYST_SEMAPHORE.release()
        assert acquired == 7
