import asyncio
import atexit
import concurrent.futures
import json
import logging
import re
import threading
from datetime import datetime, timedelta

import pandas as pd
import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.db_models import CachePreco

logger = logging.getLogger(__name__)

# Regex para tickers B3 válidos (ex: PETR4, VALE3, BOVA11, XPLG11F)
_TICKER_RE = re.compile(r'^[A-Z]{4}\d{1,2}[A-Z]?$')

CACHE_TTL_HOURS = 1

# Mapeamento ticker Yahoo → crypto_id (usado por portfolio_service, scheduler, router)
CRYPTO_IDS = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
    "ADA-USD": "cardano",
    "DOT-USD": "polkadot",
    "LINK-USD": "chainlink",
    "AVAX-USD": "avalanche",
}


def is_crypto(ticker: str) -> bool:
    """Verifica se ticker é cripto (termina em -USD ou é crypto_id)."""
    return ticker.upper().endswith("-USD") or ticker.lower() in CRYPTO_IDS.values()


def to_crypto_id(ticker: str) -> str:
    """Converte ticker Yahoo (BTC-USD) para crypto_id (bitcoin)."""
    upper = ticker.upper()
    if upper in CRYPTO_IDS:
        return CRYPTO_IDS[upper]
    return ticker.lower()

# Defaults numéricos para campos críticos usados pelo ensemble ML e agentes IA
_NUMERIC_DEFAULTS = {
    "beta": 1.0,
    "pe_ratio": 0.0,
    "pl": 0.0,
    "eps": 0.0,
    "dividend_yield": 0.0,
    "pvp": 0.0,
    "roe": 0.0,
    "margem_liquida": 0.0,
    "market_cap": 0,
    "volume": 0,
    "volume_medio_10d": 0,
    "variacao_pct": 0.0,
    "variacao_24h_pct": 0.0,
}


def _fill_none(d: dict, defaults: dict | None = None) -> dict:
    """Substitui None por defaults numéricos em campos específicos."""
    used = defaults if defaults is not None else _NUMERIC_DEFAULTS
    for key, default in used.items():
        if d.get(key) is None:
            d[key] = default
    return d


# Executor compartilhado — evita criar ThreadPoolExecutor novo por chamada
_shared_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="scraper"
)
atexit.register(_shared_executor.shutdown, wait=False)


def _run_async(coro):
    """Executa coroutine async de dentro de contexto sync."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return _shared_executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


# === Cache ===


def _get_cache(db: Session, ticker: str, fonte: str, tipo_dado: str) -> dict | None:
    entry = (
        db.query(CachePreco)
        .filter_by(ticker=ticker, fonte=fonte, tipo_dado=tipo_dado)
        .first()
    )
    if entry and entry.expira_em is not None and entry.expira_em > datetime.now():
        return json.loads(entry.dados_json)
    return None


def _set_cache(db: Session, ticker: str, fonte: str, tipo_dado: str, dados: dict, ttl_hours: int = CACHE_TTL_HOURS):
    agora = datetime.now()
    entry = (
        db.query(CachePreco)
        .filter_by(ticker=ticker, fonte=fonte, tipo_dado=tipo_dado)
        .first()
    )
    dados_json = json.dumps(dados, ensure_ascii=False, default=str)
    if entry:
        entry.dados_json = dados_json
        entry.atualizado_em = agora
        entry.expira_em = agora + timedelta(hours=ttl_hours)
    else:
        db.add(CachePreco(
            ticker=ticker,
            fonte=fonte,
            tipo_dado=tipo_dado,
            dados_json=dados_json,
            atualizado_em=agora,
            expira_em=agora + timedelta(hours=ttl_hours),
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Race condition: outro thread inseriu primeiro — update em vez disso
        entry = db.query(CachePreco).filter_by(ticker=ticker, fonte=fonte, tipo_dado=tipo_dado).first()
        if entry:
            entry.dados_json = dados_json
            entry.atualizado_em = agora
            entry.expira_em = agora + timedelta(hours=ttl_hours)
            try:
                db.commit()
            except Exception:
                db.rollback()


# === Ações B3 (Yahoo Scraper) ===


def get_stock_price(ticker: str, db: Session | None = None) -> dict | None:
    ticker = _validate_ticker(ticker) or ticker  # fallback ao original se não B3
    if db:
        cached = _get_cache(db, ticker, "yahoo_scraper", "preco")
        if cached:
            return cached

    result = _get_stock_price_scraper(ticker)
    if result:
        if db:
            _set_cache(db, ticker, "yahoo_scraper", "preco", result)
        return result

    logger.warning(f"Scraper falhou para {ticker}")
    return None


def _get_stock_price_scraper(ticker: str) -> dict | None:
    """Busca preço via Yahoo scraper (Playwright)."""
    try:
        from app.services.yahoo_scraper import scrape_quote

        data = _run_async(scrape_quote(ticker))
        if not data or not data.get("preco"):
            return None

        volume = data.get("volume") or 0
        if volume == 0:
            volume = data.get("avg_volume") or 0

        result = {
            "ticker": ticker,
            "preco": data["preco"],
            "variacao_pct": data.get("variacao_pct", 0),
            "volume": volume,
            "volume_medio_10d": data.get("avg_volume", 0),
            "market_cap": data.get("market_cap", 0),
            "nome": data.get("nome", ticker),
            "setor": "",
            "industria": "",
            "exchange": "",
            "mercado_aberto": data.get("mercado_aberto", False),
        }
        return _fill_none(result)
    except Exception as e:
        logger.warning(f"Erro scraper preço {ticker}: {e}")
        return None


def get_stock_fundamentals(ticker: str, db: Session | None = None) -> dict | None:
    ticker = _validate_ticker(ticker) or ticker
    if db:
        cached = _get_cache(db, ticker, "yahoo_scraper", "fundamentos")
        if cached:
            return cached

    result = _get_stock_fundamentals_scraper(ticker)
    if result:
        if db:
            _set_cache(db, ticker, "yahoo_scraper", "fundamentos", result)
        return result

    logger.warning(f"Scraper falhou fundamentos {ticker}")
    return None


def _get_stock_fundamentals_scraper(ticker: str) -> dict | None:
    """Busca fundamentos via Yahoo scraper (quote + financials + analysis)."""
    try:
        from app.services.yahoo_scraper import scrape_quote, scrape_financials, scrape_analysis

        async def _fetch_all():
            quote_data, fin_data, ana_data = await asyncio.gather(
                scrape_quote(ticker),
                scrape_financials(ticker),
                scrape_analysis(ticker),
                return_exceptions=True,
            )
            return (
                quote_data if not isinstance(quote_data, Exception) else None,
                fin_data if not isinstance(fin_data, Exception) else None,
                ana_data if not isinstance(ana_data, Exception) else None,
            )

        quote_data, fin_data, ana_data = _run_async(_fetch_all())

        if not quote_data or not quote_data.get("preco"):
            return None

        result = {
            "ticker": ticker,
            "nome": quote_data.get("nome", ""),
            "setor": "",
            "industria": "",
            "preco": quote_data.get("preco", 0),
            "pl": quote_data.get("pe_ratio"),
            "pvp": None,
            "roe": None,
            "dividend_yield": quote_data.get("dividend_yield"),
            "margem_liquida": None,
            "market_cap": quote_data.get("market_cap"),
            "52w_high": quote_data.get("week52_high"),
            "52w_low": quote_data.get("week52_low"),
            "beta": quote_data.get("beta"),
            "ebitda": None,
            "receita_total": None,
            "divida_total": None,
            "caixa_total": None,
        }

        # Enriquecer com dados financeiros
        if fin_data:
            income = fin_data.get("income_statement", {})
            balance = fin_data.get("balance_sheet", {})
            # Pegar valor mais recente de cada métrica
            for label, values in income.items():
                if not values:
                    continue
                # values é dict {ano: valor} — pegar primeiro valor não-None
                most_recent = next((v for v in values.values() if v is not None), None)
                label_lower = label.lower()
                if "total revenue" in label_lower or "receita" in label_lower:
                    result["receita_total"] = most_recent
                elif "ebitda" in label_lower:
                    result["ebitda"] = most_recent

            for label, values in balance.items():
                if not values:
                    continue
                most_recent = next((v for v in values.values() if v is not None), None)
                label_lower = label.lower()
                if "total debt" in label_lower or "dívida" in label_lower:
                    result["divida_total"] = most_recent
                elif "cash" in label_lower and "total" in label_lower:
                    result["caixa_total"] = most_recent

        # Enriquecer com análise de analistas
        if ana_data:
            recs = ana_data.get("recommendations", {})
            if recs:
                result["recomendacoes_analistas"] = recs

            targets = ana_data.get("price_targets", {})
            if targets:
                result["preco_alvo"] = {
                    "atual": targets.get("current"),
                    "baixo": targets.get("low"),
                    "alto": targets.get("high"),
                    "medio": targets.get("average"),
                }

        return _fill_none(result)
    except Exception as e:
        logger.warning(f"Erro scraper fundamentos {ticker}: {e}")
        return None


def get_stock_history(ticker: str, period: str = "1y", db: Session | None = None) -> list[dict] | None:
    ticker = _validate_ticker(ticker) or ticker
    cache_key = f"historico_{period}"
    if db:
        cached = _get_cache(db, ticker, "yahoo_scraper", cache_key)
        if cached:
            return cached

    result = _get_stock_history_scraper(ticker, period)
    if result:
        if db:
            _set_cache(db, ticker, "yahoo_scraper", cache_key, result)
        return result

    logger.warning(f"Scraper falhou histórico {ticker}")
    return None


def _get_stock_history_scraper(ticker: str, period: str = "1y") -> list[dict] | None:
    """Busca histórico via Yahoo scraper (Playwright)."""
    try:
        from app.services.yahoo_scraper import scrape_history

        records = _run_async(scrape_history(ticker, period))
        return records if records else None
    except Exception as e:
        logger.warning(f"Erro scraper histórico {ticker}: {e}")
        return None


def get_stock_dividends(ticker: str, db: Session | None = None) -> list[dict] | None:
    """Busca dividendos via Yahoo scraper (filter_type='div')."""
    ticker = _validate_ticker(ticker) or ticker
    if db:
        cached = _get_cache(db, ticker, "yahoo_scraper", "dividendos")
        if cached:
            return cached

    try:
        from app.services.yahoo_scraper import scrape_history

        records = _run_async(scrape_history(ticker, period="5y", filter_type="div"))
        if not records:
            return []

        if db:
            _set_cache(db, ticker, "yahoo_scraper", "dividendos", records)
        return records
    except Exception as e:
        logger.warning(f"Erro ao buscar dividendos {ticker}: {e}")
        return None


# === Criptoativos ===


def get_crypto_price(crypto_id: str, db: Session | None = None) -> dict | None:
    """Busca preço de cripto. crypto_id: 'bitcoin', 'ethereum', etc."""
    crypto_id = _validate_crypto_id(crypto_id) or crypto_id
    if db:
        cached = _get_cache(db, crypto_id, "yahoo_scraper", "preco")
        if cached:
            return cached

    result = _get_crypto_price_scraper(crypto_id)
    if result:
        if db:
            _set_cache(db, crypto_id, "yahoo_scraper", "preco", result)
        return result

    logger.warning(f"Scraper falhou crypto {crypto_id}")
    return None


def _get_crypto_price_scraper(crypto_id: str) -> dict | None:
    """Busca preço de crypto via Yahoo scraper."""
    try:
        from app.services.yahoo_scraper import scrape_quote, CRYPTO_TICKER_MAP

        yf_ticker = CRYPTO_TICKER_MAP.get(crypto_id.lower(), f"{crypto_id.upper()}-USD")
        data = _run_async(scrape_quote(yf_ticker))
        if not data or not data.get("preco"):
            return None

        preco_usd = data["preco"]
        ptax = get_ptax()
        preco_brl = preco_usd * ptax if ptax else 0

        result = {
            "id": crypto_id,
            "ticker": yf_ticker,
            "nome": data.get("nome", crypto_id),
            "preco_usd": preco_usd,
            "preco_brl": round(preco_brl, 2),
            "variacao_24h_pct": data.get("variacao_pct", 0),
            "market_cap_usd": data.get("market_cap", 0),
            "volume_24h": data.get("volume", 0),
        }
        return _fill_none(result)
    except Exception as e:
        logger.warning(f"Erro scraper crypto {crypto_id}: {e}")
        return None


def get_crypto_history(crypto_id: str, period: str = "1y", db: Session | None = None) -> list[dict] | None:
    crypto_id = _validate_crypto_id(crypto_id) or crypto_id
    cache_key = f"historico_{period}"
    if db:
        cached = _get_cache(db, crypto_id, "yahoo_scraper", cache_key)
        if cached:
            return cached

    result = _get_crypto_history_scraper(crypto_id, period)
    if result:
        if db:
            _set_cache(db, crypto_id, "yahoo_scraper", cache_key, result)
        return result

    logger.warning(f"Scraper falhou histórico crypto {crypto_id}")
    return None


def _get_crypto_history_scraper(crypto_id: str, period: str = "1y") -> list[dict] | None:
    """Busca histórico crypto via Yahoo scraper."""
    try:
        from app.services.yahoo_scraper import scrape_history, CRYPTO_TICKER_MAP

        yf_ticker = CRYPTO_TICKER_MAP.get(crypto_id.lower(), f"{crypto_id.upper()}-USD")
        records = _run_async(scrape_history(yf_ticker, period))
        return records if records else None
    except Exception as e:
        logger.warning(f"Erro scraper histórico crypto {crypto_id}: {e}")
        return None


TRENDING_CRYPTOS = {
    "BTC-USD": ("bitcoin", "Bitcoin", "BTC"),
    "ETH-USD": ("ethereum", "Ethereum", "ETH"),
    "SOL-USD": ("solana", "Solana", "SOL"),
    "XRP-USD": ("ripple", "XRP", "XRP"),
    "BNB-USD": ("binancecoin", "BNB", "BNB"),
    "ADA-USD": ("cardano", "Cardano", "ADA"),
    "DOGE-USD": ("dogecoin", "Dogecoin", "DOGE"),
    "AVAX-USD": ("avalanche-2", "Avalanche", "AVAX"),
    "DOT-USD": ("polkadot", "Polkadot", "DOT"),
    "LINK-USD": ("chainlink", "Chainlink", "LINK"),
    "MATIC-USD": ("matic-network", "Polygon", "MATIC"),
    "SHIB-USD": ("shiba-inu", "Shiba Inu", "SHIB"),
    "UNI-USD": ("uniswap", "Uniswap", "UNI"),
    "ATOM-USD": ("cosmos", "Cosmos", "ATOM"),
    "LTC-USD": ("litecoin", "Litecoin", "LTC"),
}

# Conjunto de todos os crypto_ids válidos (união de CRYPTO_IDS values + TRENDING_CRYPTOS)
VALID_CRYPTO_IDS: set[str] = set(CRYPTO_IDS.values()) | {v[0] for v in TRENDING_CRYPTOS.values()}


def _validate_ticker(ticker: str) -> str | None:
    """Retorna ticker B3 limpo ou None se inválido."""
    t = ticker.strip().upper()
    if _TICKER_RE.match(t):
        return t
    return None


def _validate_crypto_id(crypto_id: str) -> str | None:
    """Retorna crypto_id limpo ou None se inválido."""
    c = crypto_id.strip().lower()
    if c in VALID_CRYPTO_IDS:
        return c
    return None


def get_crypto_trending(db: Session | None = None) -> list[dict] | None:
    """Top cryptos ordenadas por variação 24h (via Yahoo scraper)."""
    if db:
        cached = _get_cache(db, "global", "yahoo_scraper", "trending")
        if cached:
            return cached

    ptax = get_ptax()
    tickers = list(TRENDING_CRYPTOS.keys())

    try:
        from app.services.yahoo_scraper import scrape_multiple

        batch = _run_async(scrape_multiple(tickers, pages=["quote"]))
        result = []
        for ticker in tickers:
            crypto_id, nome, simbolo = TRENDING_CRYPTOS[ticker]
            data = (batch.get(ticker) or {}).get("quote")
            if not data or not data.get("preco"):
                continue

            preco_usd = data["preco"]
            result.append({
                "id": crypto_id,
                "nome": nome,
                "simbolo": simbolo,
                "preco_usd": round(preco_usd, 2),
                "preco_brl": round(preco_usd * ptax, 2) if ptax else None,
                "variacao_24h_pct": round(data.get("variacao_pct", 0), 2),
                "volume_24h": data.get("volume", 0) or 0,
            })
    except Exception as e:
        logger.warning(f"Erro scrape_multiple trending: {e}")
        result = []

    if not result:
        return None

    result.sort(key=lambda x: x["variacao_24h_pct"], reverse=True)

    if db:
        _set_cache(db, "global", "yahoo_scraper", "trending", result)
    return result


# === Dados Macroeconômicos (BCB) ===

BCB_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"


_ptax_lock = threading.Lock()
_ptax_cache: float | None = None
_ptax_cache_time: datetime | None = None
_PTAX_CACHE_TTL = timedelta(minutes=5)


def get_ptax() -> float:
    """Cotação PTAX USD/BRL (série 1 do BCB). Cache em memória de 5 min, thread-safe."""
    global _ptax_cache, _ptax_cache_time

    with _ptax_lock:
        if _ptax_cache is not None and _ptax_cache_time and (datetime.now() - _ptax_cache_time) < _PTAX_CACHE_TTL:
            return _ptax_cache

    # Fetch fora do lock (I/O blocking)
    try:
        r = requests.get(f"{BCB_BASE}.1/dados/ultimos/1?formato=json", timeout=10)
        r.raise_for_status()
        valor = float(r.json()[0]["valor"])
        with _ptax_lock:
            _ptax_cache = valor
            _ptax_cache_time = datetime.now()
        return valor
    except Exception as e:
        logger.warning(f"Erro ao buscar PTAX: {e}")
        with _ptax_lock:
            return _ptax_cache if _ptax_cache is not None else 5.50


def get_bcb_historical_series(series_id: int, start_date: str = "2015-01-01") -> pd.Series:
    """Busca série histórica do BCB e retorna pd.Series com DatetimeIndex.

    Args:
        series_id: ID da série BCB (432=Selic, 433=IPCA, 1=PTAX, 12=CDI)
        start_date: Data inicial no formato YYYY-MM-DD

    Returns:
        pd.Series com DatetimeIndex (daily, forward-filled para dias não-úteis).
    """
    from datetime import datetime as _dt

    start_fmt = _dt.strptime(start_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    end_fmt = _dt.now().strftime("%d/%m/%Y")

    url = f"{BCB_BASE}.{series_id}/dados?formato=json&dataInicial={start_fmt}&dataFinal={end_fmt}"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            logger.warning(f"BCB série {series_id}: resposta vazia")
            return pd.Series(dtype=float)

        dates = [_dt.strptime(item["data"], "%d/%m/%Y") for item in data]
        values = [float(item["valor"]) for item in data]

        series = pd.Series(values, index=pd.DatetimeIndex(dates), name=f"bcb_{series_id}")
        series = series[~series.index.duplicated(keep="last")]
        series = series.sort_index()
        return series
    except Exception as e:
        logger.warning(f"Erro ao buscar série BCB {series_id}: {e}")
        return pd.Series(dtype=float)


def get_macro_data(db: Session | None = None) -> dict:
    """Dados macro: Selic, CDI, IPCA, PTAX."""
    if db:
        cached = _get_cache(db, "brasil", "bcb", "macro")
        if cached:
            return cached

    result = {}

    # Selic meta (série 432)
    try:
        r = requests.get(f"{BCB_BASE}.432/dados/ultimos/1?formato=json", timeout=10)
        r.raise_for_status()
        result["selic"] = float(r.json()[0]["valor"])
    except Exception as e:
        logger.warning(f"Erro Selic: {e}")
        result["selic"] = None

    # CDI (série 12)
    try:
        r = requests.get(f"{BCB_BASE}.12/dados/ultimos/1?formato=json", timeout=10)
        r.raise_for_status()
        result["cdi"] = float(r.json()[0]["valor"])
    except Exception as e:
        logger.warning(f"Erro CDI: {e}")
        result["cdi"] = None

    # IPCA últimos 12 meses (série 433)
    try:
        r = requests.get(f"{BCB_BASE}.433/dados/ultimos/12?formato=json", timeout=10)
        r.raise_for_status()
        ipca_data = r.json()
        result["ipca_mensal"] = [
            {"data": item["data"], "valor": float(item["valor"])}
            for item in ipca_data
        ]
        ipca_product = 1.0
        for item in ipca_data:
            ipca_product *= (1 + float(item["valor"]) / 100)
        result["ipca_acumulado_12m"] = round((ipca_product - 1) * 100, 2)
    except Exception as e:
        logger.warning(f"Erro IPCA: {e}")
        result["ipca_mensal"] = []
        result["ipca_acumulado_12m"] = None

    # PTAX (série 1)
    result["ptax"] = get_ptax()

    if db:
        _set_cache(db, "brasil", "bcb", "macro", result)
    return result


# === Notícias ===
# Notícias são obtidas via OpenAI web_search nos agentes (Phase 3).
# O web_search com user_location BR e datetime explícito é mais eficaz
# para notícias brasileiras do que APIs de notícias tradicionais.


# === Busca de Tickers ===


def search_tickers(query: str, tipo: str | None = None) -> list[dict]:
    """Busca tickers via scrape_quote + ticker_resolver."""
    results = []

    # Tentar scrape_quote direto (query pode ser um ticker válido)
    try:
        from app.services.yahoo_scraper import scrape_quote

        data = _run_async(scrape_quote(query))
        if data and data.get("preco"):
            quote_type = "CRYPTOCURRENCY" if "-USD" in query.upper() else "EQUITY"
            results.append({
                "symbol": query.upper(),
                "shortname": data.get("nome", query),
                "exchange": "",
                "quote_type": quote_type,
            })
    except Exception:
        pass

    # Se scrape_quote não encontrou, usar ticker_resolver
    if not results:
        try:
            from app.services.ticker_resolver import resolve_ticker

            resolved = resolve_ticker(query)
            if resolved and resolved.get("ticker"):
                ticker = resolved["ticker"]
                quote_type = "CRYPTOCURRENCY" if "-USD" in ticker else "EQUITY"
                results.append({
                    "symbol": ticker,
                    "shortname": resolved.get("nome", query),
                    "exchange": resolved.get("exchange", ""),
                    "quote_type": quote_type,
                })
        except Exception as e:
            logger.warning(f"Erro ticker_resolver: {e}")

    # Filtrar por tipo se especificado
    if tipo == "acao":
        results = [r for r in results if r["quote_type"] == "EQUITY" or ".SA" in r["symbol"]]
    elif tipo == "crypto":
        results = [r for r in results if r["quote_type"] == "CRYPTOCURRENCY" or "-USD" in r["symbol"]]

    return results


# === Utilitários ML ===


def validate_history(records: list[dict]) -> dict:
    """Valida qualidade de uma série temporal OHLCV para uso em ML.

    Retorna:
    {
        "valido": bool,
        "n_registros": int,
        "gaps": list[str],        # Datas com gap > 5 dias úteis
        "zeros_close": int,       # Candles com Close == 0
        "datas_duplicadas": int,  # Datas repetidas
        "ordem_correta": bool,    # Crescente por data
        "warnings": list[str],    # Avisos não críticos
    }
    """
    from datetime import datetime as _dt, timedelta as _td

    report: dict = {
        "valido": False,
        "n_registros": 0,
        "gaps": [],
        "zeros_close": 0,
        "datas_duplicadas": 0,
        "ordem_correta": True,
        "warnings": [],
    }

    if not records:
        report["warnings"].append("Lista de registros vazia")
        return report

    report["n_registros"] = len(records)

    # Checar zeros no Close
    report["zeros_close"] = sum(
        1 for r in records
        if (r.get("fechamento") or r.get("adj_fechamento") or 0) == 0
    )
    if report["zeros_close"] > 0:
        report["warnings"].append(f"{report['zeros_close']} candles com Close=0")

    # Parsear datas
    datas = []
    for r in records:
        try:
            datas.append(_dt.strptime(r["data"], "%Y-%m-%d").date())
        except (ValueError, KeyError):
            report["warnings"].append(f"Data inválida: {r.get('data')}")

    if not datas:
        report["warnings"].append("Nenhuma data válida encontrada")
        return report

    # Verificar ordem crescente
    report["ordem_correta"] = datas == sorted(datas)

    # Verificar duplicatas
    seen = set()
    dupes = 0
    for d in datas:
        if d in seen:
            dupes += 1
        seen.add(d)
    report["datas_duplicadas"] = dupes
    if dupes > 0:
        report["warnings"].append(f"{dupes} datas duplicadas")

    # Detectar gaps > 5 dias úteis (feriados prolongados ou dados ausentes)
    datas_sorted = sorted(set(datas))
    for i in range(1, len(datas_sorted)):
        delta = (datas_sorted[i] - datas_sorted[i - 1]).days
        if delta > 7:  # mais de 7 dias calendário ≈ >5 dias úteis
            report["gaps"].append(
                f"{datas_sorted[i - 1]} → {datas_sorted[i]} ({delta}d)"
            )

    # Série é válida se tem dados, sem duplicatas críticas e sem excesso de zeros
    zeros_pct = report["zeros_close"] / len(records)
    report["valido"] = (
        len(records) >= 10
        and report["datas_duplicadas"] == 0
        and zeros_pct < 0.05  # menos de 5% de zeros
    )

    return report


def to_ml_dataframe(records: list[dict], use_adj_close: bool = True):
    """Converte lista de records OHLCV em DataFrame pronto para ML/DL.

    - Index: DatetimeIndex (ISO 8601, UTC-naive, ordenado)
    - Colunas: Open, High, Low, Close, Volume (padrão OHLCV/TA-Lib)
    - Close = adj_fechamento se use_adj_close=True e campo disponível
    - Sem NaN (forward-fill + drop das restantes)
    - Datas em ordem crescente

    Compatível com: ta-lib, app/ensemble/features.py
    """
    import pandas as pd

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    df["data"] = pd.to_datetime(df["data"])
    df = df.set_index("data").sort_index()

    # Escolher coluna de Close (ajustado ou bruto)
    close_col = (
        "adj_fechamento"
        if (use_adj_close and "adj_fechamento" in df.columns)
        else "fechamento"
    )

    rename_map = {
        "abertura": "Open",
        "maxima": "High",
        "minima": "Low",
        close_col: "Close",
        "volume": "Volume",
    }
    df = df.rename(columns=rename_map)

    # Selecionar apenas colunas OHLCV (ignorar adj_fechamento/fechamento redundante)
    available = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[available].copy()

    # Garantir tipos numéricos
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remover NaN (forward-fill primeiro, depois drop das restantes)
    df = df.ffill().dropna()

    return df


# === Download em Massa ===


def download_multiple_stocks(tickers: list[str], period: str = "1y") -> dict:
    """Download histórico de múltiplos tickers via scraper + to_ml_dataframe.

    Retorna dict {ticker: DataFrame OHLCV}.
    """
    result = {}
    for ticker in tickers:
        try:
            records = _get_stock_history_scraper(ticker, period)
            if records:
                result[ticker] = to_ml_dataframe(records)
        except Exception as e:
            logger.warning(f"Erro download {ticker}: {e}")
    return result
