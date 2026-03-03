"""
Feature Engineering para modelos de ensemble.
Baseado na literatura acadêmica (2024-2026):
- RSI e MACD como features mais influentes (TFT-GNN, MDPI 2025)
- Walk-forward validation obrigatória
- Target = retornos (nunca preço absoluto)
"""

import logging

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import ADXIndicator, EMAIndicator, MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

logger = logging.getLogger(__name__)


def validate_data_quality(df: pd.DataFrame, ticker: str = "unknown") -> list[str]:
    """Valida qualidade dos dados OHLCV antes de criar features.

    Apenas loga warnings — não modifica dados.

    Returns:
        Lista de warnings encontrados.
    """
    warnings_list = []

    # Close prices <= 0 (delisting ou erro de dados)
    n_negative = (df["Close"] <= 0).sum()
    if n_negative > 0:
        msg = f"[{ticker}] {n_negative} candles com Close <= 0 (delisting ou erro de dados)"
        warnings_list.append(msg)
        logger.warning(msg)

    # Retornos diários > 50% (split não ajustado)
    returns = df["Close"].pct_change().dropna()
    n_extreme = (returns.abs() > 0.5).sum()
    if n_extreme > 0:
        dates = returns[returns.abs() > 0.5].index.strftime("%Y-%m-%d").tolist()
        msg = f"[{ticker}] {n_extreme} retornos diários > 50% (split não ajustado?): {dates[:5]}"
        warnings_list.append(msg)
        logger.warning(msg)

    # Trechos longos de preço idêntico (dados congelados)
    same_price = (df["Close"] == df["Close"].shift(1))
    max_streak = 0
    streak = 0
    for val in same_price:
        if val:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    if max_streak >= 10:
        msg = f"[{ticker}] Sequência de {max_streak} dias com preço idêntico (dados congelados?)"
        warnings_list.append(msg)
        logger.warning(msg)

    # Volume zero prolongado
    if "Volume" in df.columns:
        n_zero_vol = (df["Volume"] == 0).sum()
        pct_zero_vol = n_zero_vol / len(df) * 100
        if pct_zero_vol > 10:
            msg = f"[{ticker}] {pct_zero_vol:.1f}% dos dias com volume zero"
            warnings_list.append(msg)
            logger.warning(msg)

    if not warnings_list:
        logger.info(f"[{ticker}] Qualidade de dados OK ({len(df)} linhas)")

    return warnings_list


def create_features(df: pd.DataFrame, include_macro: bool = False) -> pd.DataFrame:
    """Feature engineering completo organizado por importância na literatura."""
    df = df.copy()

    # TIER 1: Features Primárias (mais influentes)
    df["returns"] = df["Close"].pct_change()
    df["log_returns"] = np.log(df["Close"] / df["Close"].shift(1))

    # RSI — #1 em importância nos papers
    df["rsi_14"] = RSIIndicator(close=df["Close"], window=14).rsi()
    df["rsi_7"] = RSIIndicator(close=df["Close"], window=7).rsi()
    df["rsi_21"] = RSIIndicator(close=df["Close"], window=21).rsi()

    # MACD — #2 em importância
    macd = MACD(close=df["Close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    # TIER 2: Médias Móveis e Cruzamentos
    for w in [5, 10, 20, 50, 200]:
        df[f"sma_{w}"] = SMAIndicator(close=df["Close"], window=w).sma_indicator()
        df[f"ema_{w}"] = EMAIndicator(close=df["Close"], window=w).ema_indicator()

    # Ratios (evitam features com escala de preço)
    df["price_sma20_ratio"] = df["Close"] / df["sma_20"]
    df["sma5_sma20_ratio"] = df["sma_5"] / df["sma_20"]
    df["sma20_sma50_ratio"] = df["sma_20"] / df["sma_50"]
    df["ema10_ema20_ratio"] = df["ema_10"] / df["ema_20"]

    # Bollinger Bands
    bb = BollingerBands(close=df["Close"], window=20, window_dev=2)
    df["bb_width"] = bb.bollinger_wband()
    df["bb_position"] = bb.bollinger_pband()

    # ATR (Volatilidade)
    atr = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14)
    df["atr_14"] = atr.average_true_range()
    df["atr_pct"] = df["atr_14"] / df["Close"]

    # Volatilidade Realizada
    df["volatility_5d"] = df["returns"].rolling(5).std()
    df["volatility_20d"] = df["returns"].rolling(20).std()
    df["volatility_60d"] = df["returns"].rolling(60).std()
    df["vol_ratio_5_20"] = df["volatility_5d"] / df["volatility_20d"]

    # TIER 3: Volume e Momentum
    df["volume_sma_20"] = df["Volume"].rolling(20).mean()
    df["volume_ratio"] = df["Volume"] / df["volume_sma_20"]
    df["volume_change"] = df["Volume"].pct_change()

    obv = OnBalanceVolumeIndicator(close=df["Close"], volume=df["Volume"])
    df["obv"] = obv.on_balance_volume()
    df["obv_sma"] = df["obv"].rolling(20).mean()

    stoch = StochasticOscillator(high=df["High"], low=df["Low"], close=df["Close"])
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    adx = ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14)
    df["adx"] = adx.adx()

    # TIER 4: Lags e Padrões
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f"return_lag_{lag}"] = df["returns"].shift(lag)
        df[f"volume_ratio_lag_{lag}"] = df["volume_ratio"].shift(lag)

    df["gap_open"] = (df["Open"] - df["Close"].shift(1)) / df["Close"].shift(1)
    df["intraday_range"] = (df["High"] - df["Low"]) / df["Close"]

    # TIER 5: Features Temporais
    df["day_of_week"] = df.index.dayofweek
    df["month"] = df.index.month
    df["quarter"] = df.index.quarter
    df["is_month_start"] = df.index.is_month_start.astype(int)
    df["is_month_end"] = df.index.is_month_end.astype(int)

    # TIER 6: Features Macro do BCB (opcional)
    if include_macro:
        try:
            from app.services.market_data import get_bcb_historical_series

            start_str = df.index.min().strftime("%Y-%m-%d")

            # Selic meta (% a.a.) — série 432
            selic = get_bcb_historical_series(432, start_str)
            if len(selic) > 0:
                selic_daily = selic.reindex(df.index, method="ffill")
                df["selic_level"] = selic_daily.values
                # Variação 3 meses (~63 dias úteis)
                df["selic_change_3m"] = df["selic_level"] - df["selic_level"].shift(63)

            # IPCA mensal (%) — série 433 → acumulado 12 meses (multiplicativo)
            ipca = get_bcb_historical_series(433, start_str)
            if len(ipca) > 0:
                # Fórmula correta: produto((1 + ipca_i/100)) - 1, NÃO soma simples
                ipca_factor = (1 + ipca / 100)
                ipca_12m = ipca_factor.rolling(12).apply(np.prod, raw=True) - 1
                ipca_12m = ipca_12m * 100  # Voltar para percentual
                ipca_daily = ipca_12m.reindex(df.index, method="ffill")
                df["ipca_12m"] = ipca_daily.values

            # PTAX USD/BRL — série 1
            ptax = get_bcb_historical_series(1, start_str)
            if len(ptax) > 0:
                ptax_daily = ptax.reindex(df.index, method="ffill")
                df["ptax_change_20d"] = ptax_daily.pct_change(20).values

            macro_cols = [c for c in ["selic_level", "selic_change_3m", "ipca_12m", "ptax_change_20d"] if c in df.columns]
            logger.info(f"Macro features adicionadas: {macro_cols}")
        except Exception as e:
            logger.warning(f"Erro ao adicionar features macro: {e}")

    # Remover features com preço absoluto
    cols_to_drop = [c for c in df.columns if (c.startswith("sma_") or c.startswith("ema_")) and not c.endswith("_ratio")]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    # Substituir infinitos por NaN antes de dropna (evita ValueError no RobustScaler)
    df = df.replace([np.inf, -np.inf], np.nan)

    # NaN rate pós-features — qualidade suspeita se > 20%
    nan_rate = df.isna().any(axis=1).sum() / len(df)
    if nan_rate > 0.2:
        logger.warning(
            f"NaN rate pós-features: {nan_rate:.1%} (> 20%). "
            f"Qualidade de dados pode ser insuficiente para treino confiável."
        )

    df = df.dropna()
    return df


def create_target(df: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """Target: retorno percentual para D+horizon (nunca preço absoluto)."""
    df = df.copy()
    df["target"] = df["Close"].shift(-horizon) / df["Close"] - 1
    df["target_direction"] = (df["target"] > 0).astype(int)
    return df.dropna()


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Retorna colunas de features (exclui target e OHLCV bruto)."""
    exclude = {"target", "target_direction", "Open", "High", "Low", "Close", "Volume"}
    return [c for c in df.columns if c not in exclude]


# Features redundantes/multicolineares a remover para modelos neurais.
# XGBoost lida bem com multicolinearidade (tree-based), mas BiLSTM/TFT
# desperdiçam VRAM e capacidade de representação.
_NEURAL_DROP_FEATURES = {
    # RSI redundantes (rsi_14 é suficiente — #1 em importância nos papers)
    "rsi_7", "rsi_21",
    # Volatilidade redundante (volatility_20d é a principal)
    "volatility_5d", "volatility_60d",
    # Stochastic: stoch_d ≈ SMA(stoch_k), redundante
    "stoch_d",
    # OBV SMA = SMA(OBV), alta correlação com OBV
    "obv_sma",
    # log_returns ≈ returns para retornos pequenos
    "log_returns",
    # Lags fracos (1, 2 e 5 são os mais informativos)
    "return_lag_3", "return_lag_10", "return_lag_20",
    "volume_ratio_lag_2", "volume_ratio_lag_3",
    "volume_ratio_lag_10", "volume_ratio_lag_20",
}


def select_features(all_features: list[str]) -> list[str]:
    """Seleciona subset de features para modelos neurais (BiLSTM/TFT).

    Remove features multicolineares para reduzir VRAM (~30% menos)
    e melhorar capacidade de generalização. XGBoost deve usar ALL features.

    Returns:
        Lista filtrada de feature names (~35 vs ~50 originais).
    """
    return [f for f in all_features if f not in _NEURAL_DROP_FEATURES]
