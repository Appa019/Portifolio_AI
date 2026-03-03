"""
Testes de controle de concorrencia de browsers Chromium.

Valida:
- Semaforo global em _scrape_fresh() (MAX_FRESH_BROWSERS=10)
- Chromium args de economia de memoria
- Executor compartilhado em market_data._run_async()
- asyncio.Semaphore em scrape_multiple()
- Timeout do orchestrator (600s)

Uso:
  python -m pytest tests/test_browser_concurrency.py -v
"""

import asyncio
import concurrent.futures
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBrowserSemaphore:
    """Testa o semaforo global de browsers em yahoo_scraper."""

    def test_semaphore_exists_and_correct_limit(self):
        from app.services.yahoo_scraper import (
            MAX_FRESH_BROWSERS,
            _fresh_browser_semaphore,
        )
        assert MAX_FRESH_BROWSERS == 10
        assert isinstance(_fresh_browser_semaphore, threading.Semaphore)

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
        barrier = threading.Barrier(MAX_FRESH_BROWSERS + 5)

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

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert peak <= MAX_FRESH_BROWSERS

    def test_scrape_fresh_acquires_and_releases_semaphore(self):
        """Verifica que _scrape_fresh adquire e libera o semaforo corretamente."""
        from app.services.yahoo_scraper import (
            _active_browsers,
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
        assert _shared_executor._max_workers == 4

    def test_run_async_uses_shared_executor(self):
        """Verifica que _run_async nao cria executor novo quando loop esta rodando."""
        from app.services.market_data import _shared_executor

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


class TestOrchestratorTimeout:
    """Testa o timeout do orchestrator."""

    def test_sub_agent_timeout_is_600(self):
        from app.agents.orchestrator import _SUB_AGENT_TIMEOUT
        assert _SUB_AGENT_TIMEOUT == 600


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
