"""
Yahoo Finance Scraper via Playwright (Chromium headless).

Motor principal de coleta de dados de mercado. Substitui yfinance para cotações,
fundamentos, histórico e análise de analistas. Suporta até 10 workers paralelos.
"""

import asyncio
import logging
import random
import re
import threading
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

YAHOO_BASE = "https://finance.yahoo.com/quote"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Mapeamento de cryptos para ticker Yahoo Finance
CRYPTO_TICKER_MAP = {
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "solana": "SOL-USD",
    "cardano": "ADA-USD",
    "polkadot": "DOT-USD",
    "chainlink": "LINK-USD",
    "avalanche": "AVAX-USD",
    "polygon": "MATIC-USD",
}

MAX_PAGES_PER_CONTEXT = 50
MAX_CONCURRENT = 10
PAGE_TIMEOUT_MS = 15_000
MAX_RETRIES = 4
RATE_LIMIT_PER_MIN = 30

# === Controle de concorrência de browsers ===
# Limita browsers Chromium simultâneos em toda a aplicação.
# threading.Semaphore porque _run_async() cria event loops separados por thread.
MAX_FRESH_BROWSERS = 10
_fresh_browser_semaphore = threading.Semaphore(MAX_FRESH_BROWSERS)
_active_browsers = 0
_active_browsers_lock = threading.Lock()

# Chromium args para economia de memória (~250MB por processo em vez de ~400MB)
_CHROMIUM_MEMORY_ARGS = [
    "--js-flags=--max-old-space-size=256",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
    "--disable-component-extensions-with-background-pages",
]

# Args base compartilhados entre BrowserPool e fresh browsers
_CHROMIUM_BASE_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-extensions",
    "--disable-gpu",
]

# Cache de tickers resolvidos: ticker_original → ticker_yahoo
_resolved_tickers: dict[str, str | None] = {}


def _normalize_ticker(ticker: str) -> str:
    """Converte ticker local para formato Yahoo Finance."""
    # Checar cache de resolução primeiro
    if ticker in _resolved_tickers:
        resolved = _resolved_tickers[ticker]
        if resolved:
            return resolved

    t = ticker.strip().upper()
    # Já tem sufixo
    if ".SA" in t or "-USD" in t:
        return t
    # Crypto por nome
    if ticker.lower() in CRYPTO_TICKER_MAP:
        return CRYPTO_TICKER_MAP[ticker.lower()]
    # Assume ação B3
    if re.match(r"^[A-Z]{4}\d{1,2}$", t):
        return f"{t}.SA"
    return t


def _try_resolve_ticker(ticker: str) -> str | None:
    """Tenta resolver ticker via agente IA com web search.

    Retorna ticker Yahoo corrigido ou None.
    """
    if ticker in _resolved_tickers:
        return _resolved_tickers[ticker]

    try:
        from app.services.ticker_resolver import resolve_ticker
        result = resolve_ticker(ticker)
        if result and result.get("ticker_yahoo"):
            yahoo_ticker = result["ticker_yahoo"]
            _resolved_tickers[ticker] = yahoo_ticker
            logger.info(f"Ticker resolvido via IA: {ticker} → {yahoo_ticker}")
            return yahoo_ticker
        else:
            _resolved_tickers[ticker] = None
            return None
    except Exception as e:
        logger.debug(f"Ticker resolver indisponível: {e}")
        return None


def _build_stealth_headers(ua: str) -> dict:
    """Constrói headers sec-ch-ua consistentes com o User-Agent fornecido.

    Chromium real envia client hints que precisam casar com o UA — inconsistência
    é um sinal forte de bot detectable pelo Yahoo Finance.
    Firefox e Safari não enviam sec-ch-ua, por isso não adicionamos nesses casos.
    """
    headers: dict[str, str] = {}
    if "Firefox" in ua or "Safari" in ua and "Chrome" not in ua:
        return headers  # Firefox/Safari não usam sec-ch-ua
    if "Edg/" in ua:
        m = re.search(r"Edg/(\d+)", ua)
        v = m.group(1) if m else "129"
        headers["sec-ch-ua"] = f'"Microsoft Edge";v="{v}", "Chromium";v="{v}", "Not_A Brand";v="24"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"'
    elif "Chrome/" in ua:
        m = re.search(r"Chrome/(\d+)", ua)
        v = m.group(1) if m else "131"
        platform = (
            '"Windows"' if "Windows" in ua
            else '"Linux"' if "Linux" in ua
            else '"macOS"'
        )
        headers["sec-ch-ua"] = f'"Google Chrome";v="{v}", "Chromium";v="{v}", "Not_A Brand";v="24"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = platform
    return headers


def _parse_number(text: str | None) -> float | None:
    """Extrai número de string formatada (ex: '1,234.56', '1.23T', '45.67%')."""
    if not text:
        return None
    text = text.strip().replace(",", "")
    if text in ("N/A", "--", "—", ""):
        return None

    multiplier = 1
    if text.endswith("T"):
        multiplier = 1_000_000_000_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("%"):
        text = text[:-1]

    try:
        return float(text) * multiplier
    except (ValueError, TypeError):
        return None


def _parse_range(text: str | None) -> tuple[float | None, float | None]:
    """Parse '123.45 - 678.90' range strings."""
    if not text:
        return None, None
    parts = re.split(r"\s*[-–—]\s*", text)
    if len(parts) == 2:
        return _parse_number(parts[0]), _parse_number(parts[1])
    return None, None


def _parse_date(text: str) -> str | None:
    """Converte data em vários formatos para ISO 8601 ('YYYY-MM-DD').

    Suporta: 'Feb 28, 2025', 'February 28, 2025', '2025-02-28'.
    Retorna None se não conseguir parsear.
    """
    from datetime import datetime as _dt

    if not text:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return _dt.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


STEALTH_JS = ""  # Desabilitado: qualquer override de navigator quebra o React do Yahoo

VIEWPORT_VARIANTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1680, "height": 1050},
]


class BrowserPool:
    """Pool de browser contexts paralelos para scraping.

    Singleton: 1 instância Chromium compartilhada, até MAX_CONCURRENT contexts.
    Cada context é reciclado após MAX_PAGES_PER_CONTEXT páginas.

    Anti-detecção:
    - User-agent rotativo por context
    - Viewport variável
    - Stealth JS (remove navigator.webdriver, injeta chrome runtime)
    - Random delay entre requisições
    - Referrer spoofing via Google
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._lock = asyncio.Lock()
        self._initialized = False
        self._request_times: list[float] = []
        self._captcha_count = 0

    async def initialize(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    *_CHROMIUM_BASE_ARGS,
                    *_CHROMIUM_MEMORY_ARGS,
                    "--window-size=1920,1080",
                    "--lang=pt-BR,pt,en-US,en",
                ],
            )
            self._initialized = True
            self._captcha_count = 0
            logger.info("BrowserPool inicializado — Chromium headless pronto")

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._initialized = False
        logger.info("BrowserPool encerrado")

    async def _restart_browser(self):
        """Reinicia o browser completamente — usado após muitos CAPTCHAs."""
        logger.info("Reiniciando browser para limpar fingerprint...")
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                *_CHROMIUM_BASE_ARGS,
                *_CHROMIUM_MEMORY_ARGS,
                "--lang=pt-BR,pt,en-US,en",
            ],
        )
        self._captcha_count = 0
        logger.info("Browser reiniciado")

    async def _rate_limit(self):
        """Limita a RATE_LIMIT_PER_MIN requisições por minuto."""
        now = asyncio.get_event_loop().time()
        self._request_times = [t for t in self._request_times if now - t < 60]
        if len(self._request_times) >= RATE_LIMIT_PER_MIN:
            wait = 60 - (now - self._request_times[0])
            if wait > 0:
                logger.debug(f"Rate limit: aguardando {wait:.1f}s")
                await asyncio.sleep(wait)
        self._request_times.append(asyncio.get_event_loop().time())

    async def _create_stealth_context(self) -> BrowserContext:
        """Cria context com stealth: UA rotativo, viewport variável, headers reais."""
        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORT_VARIANTS)
        context = await self._browser.new_context(
            user_agent=ua,
            viewport=vp,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            extra_http_headers=_build_stealth_headers(ua),
        )
        if STEALTH_JS:
            await context.add_init_script(STEALTH_JS)
        return context

    @asynccontextmanager
    async def acquire_page(self):
        """Adquire uma page stealth dentro de um context do pool."""
        if not self._initialized:
            await self.initialize()

        # Se muitos CAPTCHAs, reiniciar browser antes de continuar
        if self._captcha_count >= 3:
            async with self._lock:
                if self._captcha_count >= 3:
                    await self._restart_browser()

        async with self._semaphore:
            await self._rate_limit()
            # Delay humano aleatório entre requests — suficiente para não disparar rate-limit do Yahoo
            await asyncio.sleep(random.uniform(1.5, 3.5))
            context = await self._create_stealth_context()
            page = await context.new_page()
            try:
                yield page
            finally:
                await page.close()
                await context.close()

    def report_captcha(self):
        """Incrementa contador de CAPTCHAs para trigger de restart."""
        self._captcha_count += 1


# Singleton global
_pool = BrowserPool()


async def get_pool() -> BrowserPool:
    """Retorna pool inicializado (lazy init)."""
    if not _pool._initialized:
        await _pool.initialize()
    return _pool


async def close_pool():
    """Fecha o pool — chamar no shutdown do app."""
    await _pool.close()


# === Cookie consent ===

async def _dismiss_consent(page: Page):
    """Tenta fechar banners de consentimento/cookies."""
    selectors = [
        "button[name='agree']",
        "button.consent-overlay--accept",
        "[data-testid='consent-accept']",
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Aceitar tudo')",
        "button:has-text('Scroll to continue')",
        ".btn.primary:has-text('Accept')",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue


# === Detecção e evasão de CAPTCHA ===

async def _is_captcha(page: Page) -> bool:
    """Detecta se a página atual é um CAPTCHA."""
    try:
        content = await page.content()
        lower = content.lower()
        indicators = ["captcha", "recaptcha", "are you a robot", "not a robot",
                       "unusual traffic", "verify you are human", "press & hold"]
        return any(ind in lower for ind in indicators)
    except Exception:
        return False


async def _navigate_stealth(page: Page, url: str, timeout: int = PAGE_TIMEOUT_MS):
    """Navega com táticas de evasão progressivas.

    Estratégias (em ordem):
    1. Navegação direta
    2. Se CAPTCHA: warm-up via homepage do Yahoo Finance primeiro
    3. Se CAPTCHA: warm-up via Google referrer
    4. Se CAPTCHA: abrir browser novo, ir direto ao link
    """
    # Estratégia 1: navegação direta
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    if not await _is_captcha(page):
        return resp

    logger.info(f"CAPTCHA na navegação direta, tentando warm-up via homepage...")

    # Estratégia 2: visitar homepage antes
    await page.goto("https://finance.yahoo.com/", wait_until="domcontentloaded", timeout=timeout)
    await _dismiss_consent(page)
    await asyncio.sleep(random.uniform(1.5, 3.0))
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    if not await _is_captcha(page):
        return resp

    logger.info(f"CAPTCHA após homepage, tentando referrer Google...")

    # Estratégia 3: simular vinda do Google
    await page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=10000)
    await asyncio.sleep(random.uniform(1.0, 2.0))
    await page.evaluate(f'window.location.href = "{url}"')
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    if not await _is_captcha(page):
        return None  # sem response object neste caso

    return None


async def _navigate_fresh_browser(
    url: str,
    timeout: int = PAGE_TIMEOUT_MS,
    warm_up: bool = False,
) -> tuple[Page | None, dict]:
    """Abre browser completamente novo e vai direto ao link.

    Args:
        url: URL destino
        timeout: timeout de navegação em ms
        warm_up: se True, visita homepage do Yahoo antes (ganha cookies legítimos)

    Retorna (page, context_info) — caller DEVE fechar via _cleanup_fresh().
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            *_CHROMIUM_BASE_ARGS,
            *_CHROMIUM_MEMORY_ARGS,
            "--lang=en-US,en",
        ],
    )
    ua = random.choice(USER_AGENTS)
    vp = random.choice(VIEWPORT_VARIANTS)
    context = await browser.new_context(
        user_agent=ua,
        viewport=vp,
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
    )
    page = await context.new_page()

    # Delay humano aleatório
    await asyncio.sleep(random.uniform(0.3, 1.2))

    if warm_up:
        # Visitar homepage primeiro para ganhar cookies/consent legítimos
        try:
            await page.goto("https://finance.yahoo.com/", wait_until="domcontentloaded", timeout=timeout)
            await _dismiss_consent(page)
            await asyncio.sleep(random.uniform(1.0, 2.5))
        except Exception as e:
            logger.debug(f"Warm-up navigation: {e}")

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as e:
        logger.debug(f"Page navigation: {e}")

    return page, {"browser": browser, "pw": pw, "context": context}


async def _cleanup_fresh(info: dict):
    """Fecha browser/context/playwright de um fresh browser. Sempre chamar no finally."""
    for key in ("context", "browser"):
        try:
            await info[key].close()
        except Exception as e:
            logger.debug(f"Cleanup {key}: {e}")
    try:
        await info["pw"].stop()
    except Exception as e:
        logger.debug(f"Cleanup playwright: {e}")


async def _scrape_fresh(url: str, extractor, retries: int = MAX_RETRIES) -> any:
    """Helper central: abre browser novo → navega → extrai → fecha.

    Cada tentativa usa browser completamente novo (evita CAPTCHA acumulado).
    Estratégias progressivas por tentativa:
      1. Browser novo, direto ao link
      2. Browser novo + warm-up via homepage (ganha cookies legítimos)
      3. Browser novo + warm-up + delay longo
      4+ (se retries > 3): repete com delays crescentes

    O `extractor` é uma async function(page) que retorna os dados.

    Concorrência: threading.Semaphore(MAX_FRESH_BROWSERS) limita browsers
    simultâneos em toda a aplicação. Sem timeout — cada browser é limitado
    por PAGE_TIMEOUT_MS do Playwright + cleanup no finally.
    """
    global _active_browsers

    for attempt in range(retries):
        fresh_info = None
        slot_held = False
        try:
            # Adquirir slot do semáforo (espera sem timeout)
            _fresh_browser_semaphore.acquire()
            slot_held = True
            with _active_browsers_lock:
                _active_browsers += 1
                active = _active_browsers
            logger.debug(f"Browser slot acquired ({active}/{MAX_FRESH_BROWSERS} active) for {url.split('/')[-2]}")

            # Estratégia progressiva
            use_warmup = attempt >= 1  # warm-up a partir da 2ª tentativa

            page, fresh_info = await _navigate_fresh_browser(
                url, warm_up=use_warmup
            )

            if await _is_captcha(page):
                logger.warning(f"CAPTCHA em {url.split('/')[-2]} (tentativa {attempt + 1}/{retries})")
                # Fechar imediatamente antes de esperar
                await _cleanup_fresh(fresh_info)
                fresh_info = None
                # Liberar slot durante o backoff
                with _active_browsers_lock:
                    _active_browsers -= 1
                _fresh_browser_semaphore.release()
                slot_held = False
                if attempt < retries - 1:
                    # Backoff exponencial: 5s, 15s, 30s
                    wait = min(5 * (2 ** attempt), 60)
                    logger.info(f"Aguardando {wait}s antes de retry...")
                    await asyncio.sleep(wait)
                    continue
                return None

            await _dismiss_consent(page)
            result = await extractor(page)
            return result

        except Exception as e:
            logger.warning(f"Erro scrape {url.split('/')[-2]} (tentativa {attempt + 1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep((attempt + 1) * 3)
            continue
        finally:
            if fresh_info:
                await _cleanup_fresh(fresh_info)
            if slot_held:
                with _active_browsers_lock:
                    _active_browsers -= 1
                    active = _active_browsers
                _fresh_browser_semaphore.release()
                logger.debug(f"Browser slot released ({active}/{MAX_FRESH_BROWSERS} active)")


# === Extração de dados ===

async def _get_text(page: Page, selector: str) -> str | None:
    """Extrai texto de um seletor, retorna None se não encontrado."""
    try:
        el = page.locator(selector).first
        if await el.is_visible(timeout=2000):
            text = await el.inner_text()
            return text.strip() if text else None
    except Exception:
        return None


async def _get_stat_value(page: Page, label: str) -> str | None:
    """Extrai valor de uma stat row pelo label (ex: 'Previous Close').

    Yahoo Finance structure:
      <li>
        <span class="label yf-6myrf1" title="Previous Close">Previous Close</span>
        <span class="value yf-6myrf1">39.61</span>
      </li>
    """
    try:
        row = page.locator(f'li:has(span[title="{label}"])').first
        if await row.is_visible(timeout=2000):
            value_el = row.locator("span.value").first
            text = await value_el.inner_text()
            return text.strip() if text else None
    except Exception:
        return None
    return None


# === Scraping de páginas ===

async def scrape_quote(ticker: str) -> dict | None:
    """Scrapa cotação atual de /quote/{TICKER}. Browser novo a cada tentativa."""
    yf_ticker = _normalize_ticker(ticker)
    url = f"{YAHOO_BASE}/{yf_ticker}/"

    async def _extract_quote(page: Page) -> dict | None:
        # Detectar redirect para lookup (ticker inexistente)
        if "/lookup/" in page.url or "Symbol Lookup" in (await page.title()):
            logger.info(f"Ticker {yf_ticker} não existe no Yahoo — tentando resolver via IA")
            resolved = _try_resolve_ticker(ticker)
            if resolved and resolved != yf_ticker:
                await page.goto(f"{YAHOO_BASE}/{resolved}/", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                if "/lookup/" in page.url:
                    return None
            else:
                return None

        # Esperar stats renderizarem
        try:
            await page.wait_for_selector('li:has(span[title="Previous Close"])', timeout=PAGE_TIMEOUT_MS)
        except Exception:
            # Poll via wait_for_function para tickers lentos (ex: CPLE6.SA)
            try:
                await page.wait_for_function(
                    'document.querySelector(\'[data-testid="qsp-price"]\') !== null'
                    ' || document.querySelector(\'li span[title="Previous Close"]\') !== null',
                    timeout=20_000,
                )
            except Exception:
                return None

        # Extrair tudo via JS (rápido e confiável)
        data = await page.evaluate(r"""
            () => {
                const price = document.querySelector('[data-testid="qsp-price"]');
                const change = document.querySelector('[data-testid="qsp-price-change"]');
                const changePct = document.querySelector('[data-testid="qsp-price-change-percent"]');
                const h1s = document.querySelectorAll('h1');
                const nome = h1s.length >= 2 ? h1s[1].textContent.trim() : '';

                const stats = {};
                document.querySelectorAll('li').forEach(li => {
                    const label = li.querySelector('span.label');
                    const value = li.querySelector('span.value');
                    if (label && value) {
                        const l = (label.getAttribute('title') || label.textContent).trim();
                        const v = value.textContent.trim();
                        if (l && v) stats[l] = v;
                    }
                });

                // Detectar estado do mercado via badge/texto do Yahoo
                const marketBadge = document.querySelector('[data-testid="market-time"]');
                const marketText = marketBadge ? marketBadge.textContent.toLowerCase() : '';
                const isOpen = marketText.includes('open') || marketText.includes('aberto');

                return {
                    preco: price ? price.textContent.trim() : '',
                    variacao: change ? change.textContent.trim() : '',
                    variacao_pct: changePct ? changePct.textContent.trim() : '',
                    nome: nome,
                    stats: stats,
                    mercado_aberto: isOpen,
                };
            }
        """)

        preco = _parse_number(data["preco"])
        if preco is None:
            return None

        variacao_abs = _parse_number(data["variacao"])
        pct_text = data["variacao_pct"].strip("()% ")
        is_neg = pct_text.startswith("-")
        pct_text = pct_text.lstrip("+-")
        variacao_pct = _parse_number(pct_text)
        if variacao_pct and is_neg:
            variacao_pct = -variacao_pct

        nome = data["nome"]
        if nome and "(" in nome:
            nome = nome.split("(")[0].strip()

        stats = data["stats"]
        day_low, day_high = _parse_range(stats.get("Day's Range"))
        w52_low, w52_high = _parse_range(stats.get("52 Week Range"))

        market_cap_val = None
        for key in stats:
            if "market cap" in key.lower():
                market_cap_val = _parse_number(stats[key])
                break

        div_text = stats.get("Forward Dividend & Yield", "")
        dividend_yield = None
        if div_text and "(" in div_text:
            match = re.search(r"\(([\d.]+)%?\)", div_text)
            if match:
                dividend_yield = _parse_number(match.group(1))
                if dividend_yield:
                    dividend_yield = dividend_yield / 100

        return {
            "ticker": ticker,
            "nome": nome or ticker,
            "preco": preco,
            "variacao_abs": variacao_abs,
            "variacao_pct": variacao_pct,
            "previous_close": _parse_number(stats.get("Previous Close")),
            "abertura": _parse_number(stats.get("Open")),
            "day_range_low": day_low,
            "day_range_high": day_high,
            "week52_low": w52_low,
            "week52_high": w52_high,
            "volume": _parse_number(stats.get("Volume")),
            "avg_volume": _parse_number(stats.get("Avg. Volume")),
            "market_cap": market_cap_val,
            "beta": _parse_number(stats.get("Beta (5Y Monthly)")),
            "pe_ratio": _parse_number(stats.get("PE Ratio (TTM)")),
            "eps": _parse_number(stats.get("EPS (TTM)")),
            "dividend_yield": dividend_yield,
            "target_est": _parse_number(stats.get("1y Target Est")),
            "mercado_aberto": data.get("mercado_aberto", False),
        }

    return await _scrape_fresh(url, _extract_quote)


def _build_history_url(
    yf_ticker: str,
    period1: int | None = None,
    period2: int | None = None,
    period: str = "1y",
    filter_type: str = "history",
    frequency: str = "1d",
) -> str:
    """Constrói URL de histórico com filtros via query params.

    URL format:
      /quote/{TICKER}/history/?period1=UNIX&period2=UNIX&filter=TYPE&frequency=FREQ

    Args:
        yf_ticker: Ticker Yahoo (ex: PETR4.SA)
        period1: Unix timestamp início (ou None para calcular via period)
        period2: Unix timestamp fim (ou None para agora)
        period: Período relativo se period1/period2 não fornecidos:
                "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"
        filter_type: Tipo de dado:
                     "history" — preços OHLCV (padrão)
                     "div" — dividendos
                     "split" — desdobramentos
                     "capitalGain" — ganhos de capital
        frequency: Frequência: "1d" (diário), "1wk" (semanal), "1mo" (mensal)
    """
    import time as _time

    now = int(_time.time())

    if period1 is not None and period2 is not None:
        p1, p2 = period1, period2
    else:
        p2 = now
        period_map = {
            "1d": 86400,
            "5d": 5 * 86400,
            "1mo": 30 * 86400,
            "3mo": 90 * 86400,
            "6mo": 180 * 86400,
            "1y": 365 * 86400,
            "2y": 2 * 365 * 86400,
            "5y": 5 * 365 * 86400,
            "max": 50 * 365 * 86400,
        }
        p1 = now - period_map.get(period, 365 * 86400)

    params = f"period1={p1}&period2={p2}&frequency={frequency}"
    if filter_type and filter_type != "history":
        params += f"&filter={filter_type}"

    return f"{YAHOO_BASE}/{yf_ticker}/history/?{params}"


async def scrape_history(
    ticker: str,
    period: str = "1y",
    start_date: str | None = None,
    end_date: str | None = None,
    filter_type: str = "history",
    frequency: str = "1d",
) -> list[dict] | None:
    """Scrapa histórico de /quote/{TICKER}/history/ com filtros completos.

    Args:
        ticker: Ticker (ex: "PETR4", "BTC-USD")
        period: Período relativo: "1d","5d","1mo","3mo","6mo","1y","2y","5y","max"
                Ignorado se start_date/end_date fornecidos.
        start_date: Data início "YYYY-MM-DD" (opcional, sobrescreve period)
        end_date: Data fim "YYYY-MM-DD" (opcional, default=hoje)
        filter_type: Tipo de dados:
                     "history" — OHLCV (padrão)
                     "div" — dividendos
                     "split" — stock splits
                     "capitalGain" — ganhos de capital
        frequency: "1d" (diário), "1wk" (semanal), "1mo" (mensal)

    Returns:
        Para filter_type="history":
            Lista de {data, abertura, maxima, minima, fechamento, volume}
        Para filter_type="div":
            Lista de {data, dividendo}
        Para filter_type="split":
            Lista de {data, ratio}
        Para filter_type="capitalGain":
            Lista de {data, valor}
    """
    import calendar
    from datetime import datetime as _dt

    yf_ticker = _normalize_ticker(ticker)

    # Converter datas string para unix timestamp
    period1, period2 = None, None
    if start_date:
        dt = _dt.strptime(start_date, "%Y-%m-%d")
        period1 = int(calendar.timegm(dt.timetuple()))
    if end_date:
        dt = _dt.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        period2 = int(calendar.timegm(dt.timetuple()))

    url = _build_history_url(yf_ticker, period1, period2, period, filter_type, frequency)
    ft = filter_type  # captura para closure

    async def _extract_history(page: Page) -> list[dict] | None:
        try:
            await page.wait_for_selector("table tbody tr", timeout=PAGE_TIMEOUT_MS)
        except Exception:
            return None

        # Scroll dinâmico até estabilizar o número de linhas (suporta períodos longos)
        prev_count = 0
        for _ in range(30):  # máx 30 tentativas (~24s)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)
            current_count = await page.evaluate(
                "document.querySelectorAll('table tbody tr').length"
            )
            if current_count == prev_count:
                break  # sem novas linhas → carregamento completo
            prev_count = current_count

        # Extrair via JS (muito mais rápido que query_selector_all em Python)
        raw_rows = await page.evaluate(r"""
            () => {
                const rows = document.querySelectorAll('table tbody tr');
                return Array.from(rows).map(row => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    const texts = cells.map(c => c.textContent.trim());
                    const spanVal = cells.length >= 2 && cells[1].querySelector('span')
                        ? cells[1].querySelector('span').textContent.trim() : '';
                    return {texts, spanVal, cellCount: cells.length};
                });
            }
        """)

        records = []
        for row in raw_rows:
            texts = row["texts"]
            if not texts:
                continue
            date_text = texts[0]
            if not date_text:
                continue

            if ft == "history":
                if row["cellCount"] < 6:
                    continue
                if "dividend" in date_text.lower() or "split" in date_text.lower():
                    continue
                iso_date = _parse_date(date_text)
                if not iso_date:
                    continue
                o, h, l, c = _parse_number(texts[1]), _parse_number(texts[2]), _parse_number(texts[3]), _parse_number(texts[4])
                # Coluna 5 = Adj Close (quando cellCount >= 7)
                adj_c = _parse_number(texts[5]) if row["cellCount"] >= 7 else None
                v = _parse_number(texts[-1])
                if o is None or c is None:
                    continue
                records.append({
                    "data": iso_date,
                    "abertura": round(o, 2),
                    "maxima": round(h or o, 2),
                    "minima": round(l or o, 2),
                    "fechamento": round(c, 2),
                    "adj_fechamento": round(adj_c, 2) if adj_c else round(c, 2),
                    "volume": int(v) if v else 0,
                })

            elif ft == "div":
                if row["cellCount"] < 2:
                    continue
                iso_date = _parse_date(date_text)
                if not iso_date:
                    continue
                val_text = row["spanVal"] or texts[1]
                val = _parse_number(val_text.split()[0] if val_text else "")
                if val is not None:
                    records.append({"data": iso_date, "dividendo": round(val, 6)})

            elif ft == "split":
                if row["cellCount"] < 2:
                    continue
                iso_date = _parse_date(date_text)
                if not iso_date:
                    continue
                ratio_match = re.match(r"([\d.]+\s*:\s*[\d.]+)", texts[1])
                records.append({"data": iso_date, "ratio": ratio_match.group(1).strip() if ratio_match else texts[1]})

            elif ft == "capitalGain":
                if row["cellCount"] < 2:
                    continue
                iso_date = _parse_date(date_text)
                if not iso_date:
                    continue
                val_text = row["spanVal"] or texts[1]
                val = _parse_number(val_text.split()[0] if val_text else "")
                if val is not None:
                    records.append({"data": iso_date, "valor": round(val, 6)})

        if not records:
            return None
        records.reverse()
        return records

    return await _scrape_fresh(url, _extract_history)


async def scrape_financials(
    ticker: str,
    statement: str = "all",
    quarterly: bool = False,
) -> dict | None:
    """Scrapa demonstrações financeiras do Yahoo Finance.

    Cada demonstração tem URL dedicada:
      - /quote/{TICKER}/financials/   → Income Statement (DRE)
      - /quote/{TICKER}/balance-sheet/ → Balanço Patrimonial
      - /quote/{TICKER}/cash-flow/     → Fluxo de Caixa

    Args:
        ticker: Ticker (ex: "PETR4", "EMBJ")
        statement: Qual demonstração buscar:
                   "all" — todas as 3 (padrão)
                   "income" — só DRE
                   "balance" — só Balanço
                   "cashflow" — só Fluxo de Caixa
        quarterly: True para dados trimestrais, False para anuais (padrão)

    Returns:
        Dict com:
            income_statement: {metric: {period: value, ...}, ...}
            balance_sheet: {metric: {period: value, ...}, ...}
            cash_flow: {metric: {period: value, ...}, ...}
        Cada chave presente conforme `statement` solicitado.
    """
    yf_ticker = _normalize_ticker(ticker)

    # Mapear statements para URLs
    statement_urls = {
        "income": f"{YAHOO_BASE}/{yf_ticker}/financials/",
        "balance": f"{YAHOO_BASE}/{yf_ticker}/balance-sheet/",
        "cashflow": f"{YAHOO_BASE}/{yf_ticker}/cash-flow/",
    }
    statement_keys = {
        "income": "income_statement",
        "balance": "balance_sheet",
        "cashflow": "cash_flow",
    }

    if statement == "all":
        targets = ["income", "balance", "cashflow"]
    elif statement in statement_urls:
        targets = [statement]
    else:
        logger.warning(f"Statement inválido: {statement}")
        return None

    result = {}
    q = quarterly  # captura para closures

    async def _scrape_one_statement(url: str, key: str, _q: bool) -> tuple[str, dict]:
        """Scrapa uma demonstração financeira e retorna (key, data)."""
        async def _extract_fin(page: Page) -> dict | None:
            try:
                await page.wait_for_selector("div.tableBody div.row", timeout=PAGE_TIMEOUT_MS)
            except Exception:
                return None

            if _q:
                try:
                    q_tab = page.locator('#tab-quarterly').first
                    if await q_tab.is_visible(timeout=3000):
                        sel = await q_tab.get_attribute("aria-selected")
                        if sel != "true":
                            await q_tab.click()
                            await page.wait_for_timeout(4000)
                except Exception:
                    pass

            return await _extract_financial_table(page)

        data = await _scrape_fresh(url, _extract_fin)
        return key, data if data else {}

    # Paralelizar com asyncio.gather (3 browsers simultâneos para statement="all")
    tasks = [
        _scrape_one_statement(statement_urls[t], statement_keys[t], q)
        for t in targets
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for item in results:
        if isinstance(item, Exception):
            logger.warning(f"Erro ao scrapear demonstração financeira de {ticker}: {item}")
            continue
        key, data = item
        result[key] = data

    return result if result else None


async def _extract_financial_table(page: Page) -> dict:
    """Extrai dados de uma tabela financeira via JavaScript (mais confiável que query_selector).

    Retorna: {"Total Revenue": {"TTM": 7237200.0, "6/30/2025": 1819100.0, ...}, ...}
    """
    try:
        raw = await page.evaluate("""
            () => {
                const headers = Array.from(document.querySelectorAll('div.tableHeader div.column'))
                    .map(e => e.textContent.trim())
                    .filter(t => t && t.toLowerCase() !== 'breakdown');
                const rows = document.querySelectorAll('div.tableBody div.row');
                const result = {};
                rows.forEach(row => {
                    const te = row.querySelector('div.rowTitle');
                    const label = te ? (te.getAttribute('title') || te.textContent.trim()) : '';
                    if (!label) return;
                    const vals = Array.from(row.querySelectorAll('div.column:not(.sticky)'))
                        .map(c => c.textContent.trim());
                    const entry = {};
                    vals.forEach((v, i) => { if (i < headers.length) entry[headers[i]] = v; });
                    if (Object.keys(entry).length > 0) result[label] = entry;
                });
                return result;
            }
        """)

        # Converter strings para números
        data = {}
        for label, values in raw.items():
            data[label] = {k: _parse_number(v) for k, v in values.items()}
        return data

    except Exception as e:
        logger.debug(f"Erro extraindo tabela financeira via JS: {e}")
        return {}


async def scrape_analysis(ticker: str) -> dict | None:
    """Scrapa análise de analistas de /quote/{TICKER}/analysis/. Browser novo."""
    yf_ticker = _normalize_ticker(ticker)
    url = f"{YAHOO_BASE}/{yf_ticker}/analysis/"

    async def _extract_analysis(page: Page) -> dict | None:
        # Poll via wait_for_function até linhas aparecerem (JS lazy)
        # Ações B3 frequentemente não têm estimativas no Yahoo — timeout é aceito
        try:
            await page.wait_for_function(
                "() => document.querySelectorAll('table tbody tr').length > 0",
                timeout=PAGE_TIMEOUT_MS * 2,
            )
        except Exception:
            pass  # sem dados de analistas — retornar estrutura vazia (não None)

        raw = await page.evaluate(r"""
            () => {
                const result = {
                    earnings_estimate: {}, revenue_estimate: {},
                    growth_estimates: {}, recommendations: {}, price_targets: {},
                };
                const tables = document.querySelectorAll('table');
                tables.forEach(table => {
                    const th = table.querySelector('thead th');
                    const header = th ? th.textContent.toLowerCase() : '';
                    const data = {};
                    table.querySelectorAll('tbody tr').forEach(row => {
                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length < 2) return;
                        const label = cells[0].textContent.trim();
                        const values = cells.slice(1).map(c => c.textContent.trim());
                        data[label] = values;
                    });
                    if (header.includes('earnings estimate')) result.earnings_estimate = data;
                    else if (header.includes('revenue estimate')) result.revenue_estimate = data;
                    else if (header.includes('growth')) result.growth_estimates = data;
                    else if (header.includes('recommendation')) result.recommendations = data;
                });
                // Price targets
                const fullText = document.body.textContent;
                ['Low', 'Current', 'Average', 'High'].forEach(label => {
                    const m = fullText.match(new RegExp(label + '\\s*[:]\\s*([\\d,.]+)'));
                    if (m) result.price_targets[label.toLowerCase()] = m[1];
                });
                return result;
            }
        """)

        if raw:
            # Parsear price_targets para float
            for key, val in list(raw.get("price_targets", {}).items()):
                raw["price_targets"][key] = _parse_number(str(val)) if val else None
            # Parsear recommendations para int (lista de strings → lista de ints)
            for key, vals in list(raw.get("recommendations", {}).items()):
                if isinstance(vals, list):
                    parsed = []
                    for v in vals:
                        n = _parse_number(str(v))
                        parsed.append(int(n) if n is not None else v)
                    raw["recommendations"][key] = parsed
            # Parsear earnings/revenue/growth estimates (listas de strings → listas de float)
            for section in ("earnings_estimate", "revenue_estimate", "growth_estimates"):
                for key, vals in list(raw.get(section, {}).items()):
                    if isinstance(vals, list):
                        raw[section][key] = [_parse_number(str(v)) for v in vals]
        return raw

    return await _scrape_fresh(url, _extract_analysis)


# === API pública de alto nível ===

async def scrape_key_statistics(ticker: str) -> dict | None:
    """Scrapa key statistics de /quote/{TICKER}/key-statistics/.

    Retorna dict organizado por seção:
    {
        "valuation_measures": {"Market Cap": 6480000000, "Trailing P/E": 17.12, ...},
        "financial_highlights": {"Profit Margin": 0.0429, ...},
        "trading_information": {"Beta (5Y Monthly)": 0.92, "52 Week High": 80.75, ...},
        "fiscal_year": {...},
        "profitability": {...},
        "management_effectiveness": {...},
        "income_statement": {...},
        "balance_sheet": {...},
        "cash_flow_statement": {...},
        "stock_price_history": {...},
        "share_statistics": {...},
        "dividends_splits": {...},
    }
    """
    yf_ticker = _normalize_ticker(ticker)
    url = f"{YAHOO_BASE}/{yf_ticker}/key-statistics/"

    SECTION_MAP = {
        "valuation measures": "valuation_measures",
        "financial highlights": "financial_highlights",
        "trading information": "trading_information",
        "fiscal year": "fiscal_year",
        "profitability": "profitability",
        "management effectiveness": "management_effectiveness",
        "income statement": "income_statement",
        "balance sheet": "balance_sheet",
        "cash flow statement": "cash_flow_statement",
        "stock price history": "stock_price_history",
        "share statistics": "share_statistics",
        "dividends & splits": "dividends_splits",
    }

    async def _extract_key_stats(page: Page) -> dict | None:
        # Poll via wait_for_function até seções terem conteúdo real
        try:
            await page.wait_for_function(
                "() => document.querySelectorAll('section li').length > 5",
                timeout=PAGE_TIMEOUT_MS * 2,
            )
        except Exception:
            # Fallback: aguardar tabela de valoração (sempre presente)
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('table tbody tr').length > 0",
                    timeout=10_000,
                )
            except Exception:
                logger.warning(f"Timeout esperando key-statistics {ticker}")
                return None

        raw = await page.evaluate(r"""
            () => {
                const sections = {};
                document.querySelectorAll('section h3, section h2').forEach(h => {
                    const name = h.textContent.trim();
                    if (!name) return;
                    const parent = h.closest('section') || h.parentElement;
                    const data = {};
                    parent.querySelectorAll('li, tr').forEach(row => {
                        const labelEl = row.querySelector('.label, td:first-child, span.label');
                        const valueEl = row.querySelector('.value, td:last-child, span.value');
                        if (labelEl && valueEl) {
                            const l = (labelEl.getAttribute('title') || labelEl.textContent).trim();
                            const v = valueEl.textContent.trim();
                            if (l && v && l !== v) data[l] = v;
                        }
                    });
                    if (Object.keys(data).length > 0) sections[name] = data;
                });

                const valTable = document.querySelector('table');
                if (valTable) {
                    const headers = Array.from(valTable.querySelectorAll('thead th'))
                        .map(th => th.textContent.trim()).filter(t => t);
                    const valData = {};
                    valTable.querySelectorAll('tbody tr').forEach(row => {
                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length >= 2) {
                            const label = cells[0].textContent.trim();
                            const values = {};
                            cells.slice(1).forEach((c, i) => {
                                if (i + 1 < headers.length) values[headers[i + 1]] = c.textContent.trim();
                            });
                            if (Object.keys(values).length > 0) valData[label] = values;
                        }
                    });
                    if (Object.keys(valData).length > 0) sections['_valuation_table'] = valData;
                }

                return sections;
            }
        """)

        result = {}
        for section_name, stats in raw.items():
            if section_name == "_valuation_table":
                result["valuation_table"] = {
                    label: {k: _parse_number(v) for k, v in periods.items()}
                    for label, periods in stats.items()
                }
            else:
                key = SECTION_MAP.get(section_name.lower(), section_name.lower().replace(" ", "_"))
                result[key] = {label: _parse_number(v) for label, v in stats.items()}

        return result if result else None

    return await _scrape_fresh(url, _extract_key_stats)


async def _scrape_news_page(ticker: str, page_path: str) -> list[dict] | None:
    """Scrapa notícias/press releases. Browser novo a cada tentativa."""
    yf_ticker = _normalize_ticker(ticker)
    url = f"{YAHOO_BASE}/{yf_ticker}/{page_path}/"

    async def _extract_news(page: Page) -> list[dict] | None:
        try:
            await page.wait_for_selector('li.stream-item', timeout=PAGE_TIMEOUT_MS)
        except Exception:
            return None

        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

        items = await page.evaluate(r"""
            () => {
                const articles = document.querySelectorAll('li.stream-item section[data-testid="storyitem"]');
                return Array.from(articles).map(item => {
                    const h3 = item.querySelector('h3');
                    const links = Array.from(item.querySelectorAll('a[href]'));
                    const titleLink = links.find(a => a.querySelector('h3')) || links.find(a => a.href.includes('/news/')) || links[0];
                    const img = item.querySelector('img');
                    let fonte = '', tempo = '';
                    const allDivs = Array.from(item.querySelectorAll('div, span'))
                        .map(d => d.textContent.trim())
                        .filter(t => t.includes('\u2022') || t.includes('\u00b7'))
                        .sort((a, b) => a.length - b.length);
                    for (const t of allDivs) {
                        const m = t.match(/([A-Za-z][A-Za-z .&']{1,30}?)\s*[\u2022\u00b7]\s*(\d+[dhm]\w*\s*ago)/);
                        if (m) { fonte = m[1].trim(); tempo = m[2].trim(); break; }
                        const m2 = t.match(/([A-Za-z][A-Za-z .&']{1,30}?)\s*[\u2022\u00b7]\s*([A-Z][a-z]{2}\s+\d+,?\s*\d{4})/);
                        if (m2) { fonte = m2[1].trim(); tempo = m2[2].trim(); break; }
                    }
                    return {
                        titulo: h3 ? h3.textContent.trim() : '',
                        url: titleLink ? titleLink.href : '',
                        fonte, tempo,
                        imagem: img ? img.src : '',
                    };
                }).filter(a => a.titulo && a.url && a.url.includes('/news/'));
            }
        """)
        return items if items else None

    return await _scrape_fresh(url, _extract_news)


async def scrape_news(ticker: str) -> list[dict] | None:
    """Scrapa últimas notícias de /quote/{TICKER}/latest-news/.

    Returns:
        Lista de dicts: {titulo, url, fonte, tempo, imagem}
    """
    return await _scrape_news_page(ticker, "latest-news")


async def scrape_press_releases(ticker: str) -> list[dict] | None:
    """Scrapa press releases de /quote/{TICKER}/press-releases/.

    Returns:
        Lista de dicts: {titulo, url, fonte, tempo, imagem}
    """
    return await _scrape_news_page(ticker, "press-releases")


# === API pública de alto nível ===

async def scrape_multiple(
    tickers: list[str], pages: list[str] | None = None
) -> dict:
    """Scrapa múltiplos tickers em paralelo (até MAX_CONCURRENT simultâneos).

    Args:
        tickers: Lista de tickers (ex: ["PETR4", "VALE3", "BTC-USD"])
        pages: Tipos de página a scrapear: "quote", "history", "financials", "analysis"
               Default: ["quote"]

    Returns:
        Dict ticker -> {page_type -> dados}
    """
    if pages is None:
        pages = ["quote"]

    page_funcs = {
        "quote": scrape_quote,
        "history": scrape_history,
        "financials": scrape_financials,
        "analysis": scrape_analysis,
        "key_statistics": scrape_key_statistics,
        "news": scrape_news,
        "press_releases": scrape_press_releases,
    }

    # Gate coroutines para evitar overhead de 15+ coroutines todas esperando no semáforo
    _async_gate = asyncio.Semaphore(MAX_FRESH_BROWSERS)

    async def scrape_one(ticker: str) -> tuple[str, dict]:
        async with _async_gate:
            results = {}
            for page_type in pages:
                func = page_funcs.get(page_type)
                if func:
                    results[page_type] = await func(ticker)
            return ticker, results

    tasks = [scrape_one(t) for t in tickers]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    output = {}
    for item in completed:
        if isinstance(item, Exception):
            logger.warning(f"Erro em scrape_multiple: {item}")
            continue
        ticker, data = item
        output[ticker] = data

    return output
