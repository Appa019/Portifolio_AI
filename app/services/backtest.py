"""
Benchmark passivo 50/20/30 para comparação com o portfólio real.

Fontes de dados:
  - Ações (50%): BOVA11.SA — ETF que replica o Ibovespa (proxy mercado B3)
  - Crypto (20%): BTC-USD — Bitcoin (proxy mercado cripto)
  - CDB (30%): CDI acumulado via BCB série 12 (rendimento diário composto)

Metodologia:
  - Aporta capital inicial na data de início com a alocação-alvo
  - Rebalanceamento mensal opcional (primeira sessão de cada mês)
  - CDI accrual diário: fator = (1 + cdi_anual/100)^(1/252)
  - Métricas: retorno total, CAGR, volatilidade, Sharpe, max drawdown
  - Sem custos de transação no benchmark (avantaja o benchmark vs real)
"""

import logging
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_ACOES_TICKER = "BOVA11.SA"   # ETF Ibovespa
_CRYPTO_TICKER = "BTC-USD"    # Bitcoin
_CDI_SERIE_BCB = 12            # BCB série 12 — CDI overnight (% a.a.)


def _fetch_prices_yf(ticker: str, start: str, end: str) -> pd.Series:
    """Preços de fechamento ajustados via yfinance."""
    try:
        import yfinance as yf

        df = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if df.empty:
            logger.warning(f"backtest: yfinance sem dados para {ticker} ({start}→{end})")
            return pd.Series(dtype=float)
        return df["Close"].squeeze().dropna()
    except Exception as e:
        logger.warning(f"backtest: yfinance erro {ticker}: {e}")
        return pd.Series(dtype=float)


def _fetch_cdi_daily_factors(start: str) -> pd.Series:
    """Série de fatores diários de CDI.

    BCB série 12 retorna taxa overnight em % a.d. (ex: 0.0551 = 0.0551%/dia).
    Fator diário = 1 + taxa_diaria/100 (ex: 1.000551).
    Forward-fill para fins de semana e feriados (sem observação BCB nesses dias).
    """
    try:
        from app.services.market_data import get_bcb_historical_series

        serie = get_bcb_historical_series(_CDI_SERIE_BCB, start_date=start)
        if serie.empty:
            raise ValueError("BCB retornou série vazia")
        # serie values = % ao dia (ex: 0.0551). Factor = 1 + 0.000551
        daily_factor = 1 + serie / 100
        return daily_factor
    except Exception as e:
        logger.warning(f"backtest: CDI histórico indisponível ({e}) — usando taxa atual")
        from app.services.market_data import get_cdi_annual_rate
        cdi_annual = get_cdi_annual_rate()
        # Convert annual % to daily factor
        factor = (1 + cdi_annual / 100) ** (1 / 252)
        logger.warning(f"backtest: CDI fallback {cdi_annual:.2f}% a.a. → fator {factor:.8f}/dia")
        return pd.Series({"fallback": factor}, dtype=float)


def run_passive_benchmark(
    start_date: str = "2021-01-01",
    alloc_acoes: float = 0.50,
    alloc_crypto: float = 0.20,
    alloc_cdb: float = 0.30,
    initial_capital: float = 100_000.0,
    rebalance_monthly: bool = True,
) -> dict:
    """Simula benchmark passivo com alocação-alvo e rebalanceamento mensal.

    Args:
        start_date: Data de início da simulação (YYYY-MM-DD).
        alloc_acoes: Fração alvo em ações (0.0–1.0).
        alloc_crypto: Fração alvo em crypto (0.0–1.0).
        alloc_cdb: Fração alvo em CDB/CDI (0.0–1.0).
        initial_capital: Capital inicial em BRL para normalização.
        rebalance_monthly: Se True, rebalanceia na 1ª sessão de cada mês.

    Returns:
        Dict com série temporal diária e métricas de performance.
    """
    end_date = date.today().isoformat()

    logger.info(f"backtest: {start_date}→{end_date} | {alloc_acoes:.0%}/{alloc_crypto:.0%}/{alloc_cdb:.0%}")

    # --- Fetch price series ---
    bova11 = _fetch_prices_yf(_ACOES_TICKER, start_date, end_date)
    btc = _fetch_prices_yf(_CRYPTO_TICKER, start_date, end_date)
    cdi_factors = _fetch_cdi_daily_factors(start_date)

    if bova11.empty:
        return {"erro": f"Dados de {_ACOES_TICKER} indisponíveis (yfinance). Tente novamente."}
    if btc.empty:
        return {"erro": f"Dados de {_CRYPTO_TICKER} indisponíveis (yfinance). Tente novamente."}

    # --- Align to common trading dates (intersection of equity calendars) ---
    common_idx = bova11.index.intersection(btc.index)
    if len(common_idx) < 30:
        return {"erro": f"Dados insuficientes: apenas {len(common_idx)} dias em comum."}

    bova11 = bova11.reindex(common_idx).ffill()
    btc = btc.reindex(common_idx).ffill()

    # CDI: reindex to equity dates; forward-fill gaps (weekends/holidays have no BCB observation)
    is_scalar_fallback = len(cdi_factors) == 1 and "fallback" in cdi_factors.index
    if is_scalar_fallback:
        fallback_val = float(cdi_factors.iloc[0])
        cdi_daily = pd.Series(fallback_val, index=common_idx)
    else:
        cdi_daily = cdi_factors.reindex(common_idx, method="ffill").fillna(
            (1 + 13.75 / 100) ** (1 / 252)  # ultimate fallback
        )

    # --- Initial allocation ---
    # Units of BOVA11 and BTC bought on day 0
    p0_acoes = float(bova11.iloc[0])
    p0_btc = float(btc.iloc[0])

    acoes_units = (initial_capital * alloc_acoes) / p0_acoes if p0_acoes > 0 else 0.0
    crypto_units = (initial_capital * alloc_crypto) / p0_btc if p0_btc > 0 else 0.0
    cdb_val = initial_capital * alloc_cdb  # cash equivalent, accrues CDI daily

    series: list[dict] = []
    prev_month: tuple[int, int] | None = None

    for i, dt in enumerate(common_idx):
        p_acoes = float(bova11.iloc[i])
        p_btc = float(btc.iloc[i])
        _cdi_f = float(cdi_daily.iloc[i])

        # CDB daily accrual (applied before reading today's portfolio value)
        if i > 0:
            cdi_f_prev = float(cdi_daily.iloc[i - 1])
            cdb_val *= cdi_f_prev  # apply yesterday's factor to start of today

        acoes_val = acoes_units * p_acoes
        crypto_val = crypto_units * p_btc
        total = acoes_val + crypto_val + cdb_val

        series.append({
            "data": dt.strftime("%Y-%m-%d"),
            "valor_total": round(total, 2),
            "acoes": round(acoes_val, 2),
            "crypto": round(crypto_val, 2),
            "cdb": round(cdb_val, 2),
        })

        # Monthly rebalance: first trading day of each new month
        if rebalance_monthly:
            cur_month = (dt.year, dt.month)
            if prev_month is not None and cur_month != prev_month:
                # Rebalance to target weights
                acoes_val = total * alloc_acoes
                crypto_val = total * alloc_crypto
                cdb_val = total * alloc_cdb
                if p_acoes > 0:
                    acoes_units = acoes_val / p_acoes
                if p_btc > 0:
                    crypto_units = crypto_val / p_btc
            prev_month = cur_month
        else:
            if prev_month is None:
                prev_month = (dt.year, dt.month)

    if not series:
        return {"erro": "Série temporal vazia após processamento."}

    # --- Compute metrics ---
    values = np.array([s["valor_total"] for s in series], dtype=float)
    daily_returns = np.diff(values) / values[:-1]

    total_return_pct = (values[-1] / values[0] - 1) * 100
    n_years = len(values) / 252
    cagr_pct = ((values[-1] / values[0]) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

    vol_anual_pct = float(np.std(daily_returns) * np.sqrt(252) * 100)

    try:
        from app.services.market_data import get_cdi_annual_rate
        cdi_atual = get_cdi_annual_rate()
    except Exception:
        cdi_atual = 13.75
    rf_daily = (1 + cdi_atual / 100) ** (1 / 252) - 1
    excess = daily_returns - rf_daily
    sharpe = float(np.mean(excess) / np.std(excess) * np.sqrt(252)) if np.std(excess) > 0 else 0.0

    cum_max = np.maximum.accumulate(values)
    drawdowns = (values - cum_max) / cum_max
    max_dd_pct = float(np.min(drawdowns) * 100)

    # Best/worst rolling 30-day windows
    if len(daily_returns) >= 30:
        roll30 = np.convolve(daily_returns, np.ones(30), mode="valid") / 30 * 30 * 100
        best30 = float(np.max(roll30))
        worst30 = float(np.min(roll30))
    else:
        best30 = worst30 = 0.0

    return {
        "benchmark_acoes": _ACOES_TICKER,
        "benchmark_crypto": _CRYPTO_TICKER,
        "benchmark_cdb": f"CDI (BCB série {_CDI_SERIE_BCB})",
        "data_inicio": series[0]["data"],
        "data_fim": series[-1]["data"],
        "capital_inicial": initial_capital,
        "valor_final": round(float(values[-1]), 2),
        "retorno_total_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "volatilidade_anual_pct": round(vol_anual_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "melhor_30d_pct": round(best30, 2),
        "pior_30d_pct": round(worst30, 2),
        "rebalanceamento_mensal": rebalance_monthly,
        "cdi_atual_anual_pct": round(cdi_atual, 2),
        "alocacao": {
            "acoes_pct": round(alloc_acoes * 100, 1),
            "crypto_pct": round(alloc_crypto * 100, 1),
            "cdb_pct": round(alloc_cdb * 100, 1),
        },
        "serie": series,
    }
