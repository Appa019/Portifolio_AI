"""
Pipeline End-to-End do Ensemble: coleta -> features -> treino -> previsao.
Otimizado para RTX 2070 SUPER (8GB VRAM) com Mixed Precision FP16.

Integra com stats_agent.py via predict(ticker, horizon_days).

Base learners: XGBoost + BiLSTM-Attention + TFT
Meta-learner: XGBoost (per MDPI 2025 guide)
"""

import gc
import json
import logging
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import RobustScaler

from app.ensemble.bilstm_model import BiLSTMAttention, predict_bilstm, train_bilstm
from app.ensemble.features import create_features, create_target, get_feature_columns, select_features, validate_data_quality
from app.ensemble.stacking import StackingEnsemble
from app.ensemble.tft_model import TFTWrapper, predict_tft, train_tft
from app.ensemble.validation import WalkForwardValidator
from app.ensemble.xgboost_model import XGBoostForecaster

logger = logging.getLogger(__name__)

# Minimum data requirements for reliable ensemble training
MIN_TRAIN = 252   # ~1 year of trading days
MIN_VAL = 80      # seq_len(60) + 20 margin
MIN_TEST = 80     # seq_len(60) + 20 margin

# Zona neutra: |pred| < threshold → direção "neutra" (sem sinal real)
NEUTRAL_THRESHOLD = 0.001  # 0.1%

CRYPTO_TICKER_MAP = {
    "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "solana": "SOL-USD",
    "cardano": "ADA-USD", "polkadot": "DOT-USD", "chainlink": "LINK-USD",
    "avalanche": "AVAX-USD", "ripple": "XRP-USD",
}

# Otimizacoes CUDA
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:512")
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True

# Configs para 8GB VRAM
CONFIG_8GB = {
    "bilstm": {"hidden_size": 64, "num_layers": 2, "batch_size": 128, "seq_len": 60},
    "tft": {"hidden_size": 32, "attention_heads": 4, "batch_size": 64},
    "xgboost": {"max_depth": 6},
}


def _vram_stats() -> dict | None:
    """Retorna estatísticas de VRAM em MB. None se CUDA indisponível."""
    if not torch.cuda.is_available():
        return None
    return {
        "allocated_mb": round(torch.cuda.memory_allocated() / 1024**2, 1),
        "reserved_mb": round(torch.cuda.memory_reserved() / 1024**2, 1),
        "max_allocated_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "free_mb": round(
            (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_reserved()) / 1024**2, 1
        ),
    }


def _clear_vram(label: str = "", job_id: str | None = None):
    """Limpa VRAM entre modelos com logging — crucial para 8-15 tickers sequenciais."""
    if not torch.cuda.is_available():
        return

    from app.ensemble import progress

    before = _vram_stats()
    torch.cuda.empty_cache()
    gc.collect()
    after = _vram_stats()

    logger.info(
        f"VRAM cleanup{f' ({label})' if label else ''}: "
        f"{before['allocated_mb']}MB → {after['allocated_mb']}MB allocated, "
        f"{after['free_mb']}MB free"
    )
    if job_id:
        progress.emit(job_id, "vram", f"VRAM: {after['allocated_mb']}MB usado, {after['free_mb']}MB livre", 0,
                       data={"before": before, "after": after, "label": label})


def _check_vram_budget(model_name: str, min_free_mb: int = 512):
    """Verifica se há VRAM suficiente antes de treinar um modelo."""
    stats = _vram_stats()
    if stats is None:
        return
    if stats["free_mb"] < min_free_mb:
        logger.warning(
            f"VRAM baixa antes de {model_name}: {stats['free_mb']}MB livre < {min_free_mb}MB mínimo. "
            f"Forçando limpeza extra."
        )
        torch.cuda.empty_cache()
        gc.collect()
        stats = _vram_stats()
        logger.info(f"VRAM após limpeza forçada: {stats['free_mb']}MB livre")


def _adaptive_batch_size(model_type: str, n_features: int, seq_len: int = 60) -> int:
    """Calcula batch size adaptativo baseado na VRAM livre.

    Args:
        model_type: "bilstm" ou "tft"
        n_features: número de features de input
        seq_len: comprimento da sequência temporal

    Returns:
        Batch size no range [32,256] para BiLSTM, [16,128] para TFT.
    """
    if not torch.cuda.is_available():
        # CPU: usar batch padrão do CONFIG_8GB
        return CONFIG_8GB[model_type]["batch_size"]

    stats = _vram_stats()
    free_mb = stats["free_mb"]

    # Estimar bytes por sample (float32 = 4 bytes):
    # Forward: input + activations ≈ 3× input size (heurística conservadora)
    if model_type == "bilstm":
        hidden = CONFIG_8GB["bilstm"]["hidden_size"]
        # Input: seq_len × features × 4B + LSTM activations: seq_len × hidden×2 × layers × 4B
        bytes_per_sample = seq_len * n_features * 4 + seq_len * hidden * 2 * 2 * 4
        bytes_per_sample *= 3  # activations + gradients overhead
        min_bs, max_bs = 32, 256
    else:  # tft
        hidden = CONFIG_8GB["tft"]["hidden_size"]
        # TFT has more complex attention — use 5× overhead multiplier
        bytes_per_sample = seq_len * n_features * 4 + seq_len * hidden * 4 * 4
        bytes_per_sample *= 5
        min_bs, max_bs = 16, 128

    # Reserve 1GB for model params + framework overhead
    usable_mb = max(free_mb - 1024, 256)
    usable_bytes = usable_mb * 1024 * 1024

    batch_size = int(usable_bytes / bytes_per_sample)
    batch_size = max(min_bs, min(max_bs, batch_size))
    # Round to nearest power of 2 for GPU efficiency
    batch_size = 2 ** int(np.log2(batch_size))

    logger.info(f"Batch adaptativo {model_type}: {batch_size} (VRAM livre: {free_mb}MB, {n_features} features)")
    return batch_size


class EnsemblePipeline:
    """Pipeline completo de ensemble para previsao de retornos."""

    def __init__(self, checkpoint_dir: str = "checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        self.scaler = RobustScaler()
        self.xgb_model = None
        self.bilstm_model = None
        self.tft_wrapper = None
        self.ensemble = None
        self.feature_cols = []
        self.neural_feature_cols = []  # Subset para BiLSTM/TFT (sem multicolinearidade)
        self.seq_len = CONFIG_8GB["bilstm"]["seq_len"]
        self._df_full = None  # DataFrame com features para reutilização (TFT)

    def collect_data(self, ticker: str, start: str = "2015-01-01") -> pd.DataFrame:
        """Coleta dados OHLCV via Yahoo scraper (Playwright)."""
        from app.services.market_data import (
            get_crypto_history, get_stock_history, is_crypto, to_ml_dataframe,
        )

        ticker = CRYPTO_TICKER_MAP.get(ticker.lower(), ticker)
        suffix = ".SA" if not ticker.endswith((".SA", "-USD")) else ""
        full_ticker = f"{ticker}{suffix}"

        # Ensemble precisa de séries longas — usar period="max" e filtrar por start_date
        if is_crypto(full_ticker):
            crypto_id = full_ticker.replace("-USD", "").lower()
            records = get_crypto_history(crypto_id, period="max")
        else:
            records = get_stock_history(full_ticker.replace(".SA", ""), period="max")

        if not records:
            raise ValueError(f"Sem dados do scraper para {full_ticker}")

        df = to_ml_dataframe(records)

        # Filtrar por start_date
        if start:
            df = df[df.index >= start]

        logger.info(f"Dados coletados: {full_ticker} -- {len(df)} dias (scraper)")
        return df

    def prepare_data(self, df: pd.DataFrame, horizon: int = 1, ticker: str = "unknown"):
        """Feature engineering + target + split temporal."""
        validate_data_quality(df, ticker=ticker)
        df = create_features(df)
        df = create_target(df, horizon=horizon)
        self.feature_cols = get_feature_columns(df)
        self.neural_feature_cols = select_features(self.feature_cols)

        # Split temporal: 80% treino, 10% validacao, 10% teste
        n = len(df)
        train_end = int(n * 0.8)
        val_end = int(n * 0.9)

        train = df.iloc[:train_end]
        val = df.iloc[train_end:val_end]
        test = df.iloc[val_end:]

        # Validar tamanho mínimo dos splits
        if len(train) < MIN_TRAIN:
            raise ValueError(
                f"Dados insuficientes para treino: {len(train)} < {MIN_TRAIN} mínimo. "
                f"Ticker precisa de ao menos {MIN_TRAIN + MIN_VAL + MIN_TEST} pontos pós-features."
            )
        if len(val) < MIN_VAL:
            raise ValueError(
                f"Dados insuficientes para validação: {len(val)} < {MIN_VAL} mínimo (seq_len=60 + 20). "
                f"BiLSTM/TFT não conseguem gerar predições com val set tão curto."
            )
        if len(test) < MIN_TEST:
            raise ValueError(
                f"Dados insuficientes para teste: {len(test)} < {MIN_TEST} mínimo (seq_len=60 + 20). "
                f"Avaliação de métricas não é confiável com test set tão curto."
            )

        # Normalizacao — fit APENAS no treino
        self.scaler.fit(train[self.feature_cols])

        X_train = pd.DataFrame(self.scaler.transform(train[self.feature_cols]),
                               index=train.index, columns=self.feature_cols)
        X_val = pd.DataFrame(self.scaler.transform(val[self.feature_cols]),
                             index=val.index, columns=self.feature_cols)
        X_test = pd.DataFrame(self.scaler.transform(test[self.feature_cols]),
                              index=test.index, columns=self.feature_cols)

        return X_train, train["target"], X_val, val["target"], X_test, test["target"], df, train_end, val_end

    @staticmethod
    def _align_predictions(y_true, *pred_arrays):
        """Alinha predições de múltiplos modelos usando máscara np.isfinite.

        Com NaN-padding do BiLSTM, basta encontrar a região onde TODOS os
        modelos têm valores finitos. Elimina toda a aritmética de offsets.

        Returns:
            (y_aligned, *preds_aligned) — todos com mesmo length.
        """
        # Stack e encontrar região válida comum
        stacked = np.column_stack(pred_arrays)
        valid_mask = np.all(np.isfinite(stacked), axis=1)

        # y_true pode ser Series ou array
        y_vals = y_true.values if hasattr(y_true, "values") else y_true
        # Alinhar pelo final: y_true e preds devem ter mesmo length
        # Se preds são menores que y_true (TFT), truncar y_true pelo final
        min_len = min(len(y_vals), len(valid_mask))
        y_slice = y_vals[len(y_vals) - min_len:]
        mask_slice = valid_mask[len(valid_mask) - min_len:]

        y_aligned = y_slice[mask_slice]
        preds_aligned = tuple(arr[len(arr) - min_len:][mask_slice] for arr in pred_arrays)

        return (y_aligned, *preds_aligned)

    @staticmethod
    def _check_diversity(y_true, preds_dict: dict[str, np.ndarray], job_id: str | None = None):
        """Verifica diversidade entre base learners. Loga correlação, RMSE individual e warnings.

        Args:
            y_true: array de valores reais
            preds_dict: {"XGBoost": array, "BiLSTM": array, "TFT": array}
        """
        from app.ensemble import progress

        names = list(preds_dict.keys())
        preds = list(preds_dict.values())

        # RMSE individual por modelo
        for name, pred in zip(names, preds):
            rmse = float(np.sqrt(np.mean((y_true - pred) ** 2)))
            logger.info(f"  RMSE {name}: {rmse:.6f}")

        # Correlação pairwise
        n = len(names)
        for i in range(n):
            for j in range(i + 1, n):
                corr = float(np.corrcoef(preds[i], preds[j])[0, 1])
                logger.info(f"  Correlação {names[i]} × {names[j]}: {corr:.4f}")
                if corr > 0.95:
                    logger.warning(
                        f"DIVERSIDADE BAIXA: {names[i]} × {names[j]} correlação {corr:.4f} > 0.95. "
                        f"Ensemble pode não agregar valor sobre modelos individuais."
                    )

        # Desvio padrão médio entre modelos (diversidade geral)
        stacked = np.column_stack(preds)
        mean_std = float(np.mean(np.std(stacked, axis=1)))
        logger.info(f"  Diversidade (std média entre modelos): {mean_std:.6f}")

        if job_id:
            progress.emit(job_id, "diversity", f"Diversidade: std={mean_std:.6f}", 0,
                           data={"mean_std": mean_std})

    def _ticker_dir(self, ticker: str) -> str:
        """Diretorio de checkpoint para um ticker."""
        safe = ticker.replace(".", "_").replace("-", "_")
        return os.path.join(self.checkpoint_dir, safe)

    def train(self, ticker: str, start: str = "2015-01-01", horizon: int = 1,
              job_id: str | None = None, full_oof: bool = False) -> dict:
        """Treina pipeline completo: XGBoost + BiLSTM + TFT + Stacking."""
        from app.ensemble import progress

        progress.emit(job_id, "data_collect", f"Coletando dados: {ticker}...", 5)
        df_raw = self.collect_data(ticker, start)

        progress.emit(job_id, "features", f"Calculando indicadores ({ticker})...", 10)
        X_train, y_train, X_val, y_val, X_test, y_test, df_full, train_end, val_end = self.prepare_data(df_raw, horizon, ticker=ticker)
        self._df_full = df_full  # Guardar para reutilização no TFT
        self._train_end = train_end  # Boundary train | val
        self._val_end = val_end  # Boundary train+val | test

        logger.info(f"Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")
        logger.info(f"Features: {len(self.feature_cols)}")

        ticker_dir = self._ticker_dir(ticker)

        # 1. XGBoost (GPU)
        progress.emit(job_id, "xgboost_train", f"XGBoost treinando ({ticker})...", 20)
        _check_vram_budget("XGBoost")
        self.xgb_model = XGBoostForecaster(use_gpu=True)
        self.xgb_model.fit(X_train, y_train, X_val, y_val)

        # Feature importance — log top 15 e salvar para metadata
        self._xgb_feature_importance = {}
        try:
            imp = self.xgb_model.feature_importance(top_n=15)
            self._xgb_feature_importance = imp.to_dict()
            logger.info("Top 15 XGBoost features:")
            for fname, score in imp.items():
                logger.info(f"  {fname}: {score:.4f}")
            if job_id:
                progress.emit(job_id, "feature_importance",
                              f"Top feature: {imp.index[0]} ({imp.iloc[0]:.4f})", 25,
                              data={"top_15": self._xgb_feature_importance})
        except Exception as e:
            logger.warning(f"Feature importance indisponível: {e}")

        _clear_vram("post-XGBoost", job_id)

        # 2. BiLSTM + Attention (GPU, FP16) — usa subset de features (menos multicolinearidade)
        progress.emit(job_id, "bilstm_train", f"BiLSTM + Attention ({ticker})...", 35)
        logger.info(f"BiLSTM features: {len(self.neural_feature_cols)}/{len(self.feature_cols)} (selecionadas)")
        _check_vram_budget("BiLSTM", min_free_mb=1024)
        self.bilstm_model = train_bilstm(
            X_train[self.neural_feature_cols], y_train,
            X_val[self.neural_feature_cols], y_val,
            input_size=len(self.neural_feature_cols),
            seq_len=self.seq_len,
            hidden_size=CONFIG_8GB["bilstm"]["hidden_size"],
            batch_size=_adaptive_batch_size("bilstm", len(self.neural_feature_cols), self.seq_len),
            checkpoint_dir=os.path.join(ticker_dir, "bilstm"),
        )
        _clear_vram("post-BiLSTM", job_id)

        # 3. TFT (GPU, FP16)
        progress.emit(job_id, "tft_train", f"TFT treinando ({ticker})...", 55)
        _check_vram_budget("TFT", min_free_mb=1024)
        # Reutilizar df_full (já tem features + target calculados)
        self.tft_wrapper = TFTWrapper(
            target="target",
            max_encoder=self.seq_len,
            max_decoder=5,
            hidden_size=CONFIG_8GB["tft"]["hidden_size"],
            batch_size=_adaptive_batch_size("tft", len(self.feature_cols), self.seq_len),
            checkpoint_dir=os.path.join(ticker_dir, "tft"),
        )
        self.tft_wrapper.fit(df_full.iloc[:self._val_end])
        _clear_vram("post-TFT", job_id)

        # 4. Stacking — treinar meta-learner
        progress.emit(job_id, "stacking", f"Stacking meta-learner ({ticker})...", 75)

        # OOF para XGBoost via Walk-Forward (rápido: ~10s/fold × 5 folds)
        if full_oof:
            progress.emit(job_id, "stacking", f"OOF Walk-Forward XGBoost ({ticker})...", 76)
            wfv = WalkForwardValidator(n_splits=5, val_size=60, gap=5, embargo=2)
            # Concatenar treino+val para OOF
            X_trainval = pd.concat([X_train, X_val])
            y_trainval = pd.concat([y_train, y_val])
            xgb_oof = np.full(len(X_trainval), np.nan)
            for fold, (tr_idx, vl_idx) in enumerate(wfv.split(X_trainval)):
                xgb_fold = XGBoostForecaster(use_gpu=True)
                xgb_fold.fit(X_trainval.iloc[tr_idx], y_trainval.iloc[tr_idx],
                             X_trainval.iloc[vl_idx], y_trainval.iloc[vl_idx])
                xgb_oof[vl_idx] = xgb_fold.predict(X_trainval.iloc[vl_idx])
                logger.info(f"  OOF fold {fold + 1} completo")
            # Extrair OOF da região de validação
            val_start_idx = len(X_train)
            xgb_pred_val = xgb_oof[val_start_idx:]
            # Preencher gaps com predição do modelo principal
            nan_mask = np.isnan(xgb_pred_val)
            if nan_mask.any():
                xgb_pred_val[nan_mask] = self.xgb_model.predict(X_val)[nan_mask]
            logger.info(f"OOF XGBoost: {(~nan_mask).sum()}/{len(xgb_pred_val)} pontos via walk-forward")
        else:
            xgb_pred_val = self.xgb_model.predict(X_val)

        # BiLSTM e TFT: single-fold (retreinar 5x seria ~15min/ticker — inviável)
        bilstm_pred_val = predict_bilstm(self.bilstm_model, X_val[self.neural_feature_cols], self.seq_len)
        # TFT val: usar predict_on_data no slice de validação com contexto de encoder
        # predict_validation() retorna apenas max_decoder (~1 sample) — insuficiente para stacking
        context_start = max(0, self._train_end - self.seq_len)
        tft_val_slice = df_full.iloc[context_start:self._val_end]
        tft_pred_val_raw = self.tft_wrapper.predict_on_data(tft_val_slice)
        # Pad para alinhar com val_size: TFT produz menos predições que o slice completo
        tft_pred_val = np.full(len(X_val), np.nan)
        if len(tft_pred_val_raw) > 0:
            tft_pred_val[len(tft_pred_val) - len(tft_pred_val_raw):] = tft_pred_val_raw
        logger.info(f"TFT val: {len(tft_pred_val_raw)} predições reais (de {len(X_val)} val points)")

        # Contratos de tamanho — validação
        assert len(xgb_pred_val) == len(X_val), (
            f"XGBoost val: len(pred)={len(xgb_pred_val)} != len(X_val)={len(X_val)}"
        )
        assert len(bilstm_pred_val) == len(X_val), (
            f"BiLSTM val (pad_to_full): len(pred)={len(bilstm_pred_val)} != len(X_val)={len(X_val)}"
        )
        logger.info(
            f"Contratos val OK: XGBoost={len(xgb_pred_val)}, "
            f"BiLSTM={len(bilstm_pred_val)} ({np.isfinite(bilstm_pred_val).sum()} válidos), "
            f"TFT={len(tft_pred_val)} ({np.isfinite(tft_pred_val).sum()} válidos), "
            f"val_size={len(X_val)}"
        )

        # Alinhar via máscara np.isfinite (BiLSTM retorna NaN-padded)
        # Se TFT produziu poucos pontos válidos, usar ensemble 2-learner (XGBoost + BiLSTM)
        MIN_STACKING_POINTS = 20
        tft_valid_count = int(np.isfinite(tft_pred_val).sum())

        try:
            if tft_valid_count >= MIN_STACKING_POINTS:
                # 3-learner stacking
                y_val_al, xgb_val_al, bilstm_val_al, tft_val_al = self._align_predictions(
                    y_val, xgb_pred_val, bilstm_pred_val, tft_pred_val
                )
                if len(y_val_al) < MIN_STACKING_POINTS:
                    raise ValueError(f"Apenas {len(y_val_al)} pontos alinhados (3-learner) < {MIN_STACKING_POINTS}")
                base_preds_val = np.column_stack([xgb_val_al, bilstm_val_al, tft_val_al])
                self.ensemble = StackingEnsemble(meta_type="xgboost")
                self.ensemble.fit_meta(base_preds_val, y_val_al,
                                       feature_names=["XGBoost", "BiLSTM-Attn", "TFT"])
                self._n_base_learners = 3
            else:
                # 2-learner stacking (TFT muito esparso)
                logger.info(
                    f"TFT produziu apenas {tft_valid_count} predições válidas. "
                    f"Usando ensemble 2-learner (XGBoost + BiLSTM)."
                )
                y_val_al, xgb_val_al, bilstm_val_al = self._align_predictions(
                    y_val, xgb_pred_val, bilstm_pred_val
                )
                if len(y_val_al) < MIN_STACKING_POINTS:
                    raise ValueError(f"Apenas {len(y_val_al)} pontos alinhados (2-learner) < {MIN_STACKING_POINTS}")
                base_preds_val = np.column_stack([xgb_val_al, bilstm_val_al])
                self.ensemble = StackingEnsemble(meta_type="xgboost")
                self.ensemble.fit_meta(base_preds_val, y_val_al,
                                       feature_names=["XGBoost", "BiLSTM-Attn"])
                self._n_base_learners = 2

            oof_label = "OOF walk-forward" if full_oof else "single-fold"
            logger.info(
                f"Meta-learner treinado em VALIDACAO ({len(y_val_al)} pontos, "
                f"{self._n_base_learners} base learners, XGBoost: {oof_label})"
            )
        except (ValueError, IndexError) as e:
            logger.warning(f"Fallback XGBoost-only: {e}")
            self.ensemble = None
            self._n_base_learners = 0

        # 5. Avaliar no TESTE — com TFT predictions reais
        progress.emit(job_id, "metrics", f"Avaliando metricas ({ticker})...", 90)
        xgb_pred_test = self.xgb_model.predict(X_test)
        bilstm_pred_test = predict_bilstm(self.bilstm_model, X_test[self.neural_feature_cols], self.seq_len)

        # Contratos de tamanho — garantir consistência pós-predict
        assert len(xgb_pred_test) == len(X_test), (
            f"XGBoost: len(pred)={len(xgb_pred_test)} != len(X)={len(X_test)}"
        )
        assert len(bilstm_pred_test) == len(X_test), (
            f"BiLSTM (pad_to_full): len(pred)={len(bilstm_pred_test)} != len(X)={len(X_test)}"
        )
        n_bilstm_valid = np.isfinite(bilstm_pred_test).sum()
        logger.info(
            f"Contratos OK: XGBoost={len(xgb_pred_test)}, "
            f"BiLSTM={len(bilstm_pred_test)} ({n_bilstm_valid} válidos), "
            f"test_size={len(X_test)}"
        )

        # TFT predictions reais no test set
        tft_pred_test = np.full(len(X_test), np.nan)
        if self.tft_wrapper:
            try:
                df_test_slice = df_full.iloc[self._val_end:]
                tft_raw = self.tft_wrapper.predict_on_data(df_test_slice)
                if len(tft_raw) == 0:
                    logger.warning(
                        f"TFT predict_on_data retornou vazio (test slice: {len(df_test_slice)} linhas). "
                        f"Usando proxy XGBoost+BiLSTM."
                    )
                    proxy_mask = np.isfinite(bilstm_pred_test)
                    tft_pred_test[proxy_mask] = (xgb_pred_test[proxy_mask] + bilstm_pred_test[proxy_mask]) / 2
                else:
                    # Alinhar TFT pelo final do array
                    tft_pred_test[len(tft_pred_test) - len(tft_raw):] = tft_raw
            except Exception as e:
                logger.warning(f"TFT predict_on_data falhou: {e}. Usando proxy.")
                # Proxy: média de XGBoost e BiLSTM onde ambos são finitos
                proxy_mask = np.isfinite(bilstm_pred_test)
                tft_pred_test[proxy_mask] = (xgb_pred_test[proxy_mask] + bilstm_pred_test[proxy_mask]) / 2

        if self.ensemble:
            if getattr(self, "_n_base_learners", 3) == 3:
                y_test_al, xgb_t, bilstm_t, tft_t = self._align_predictions(
                    y_test, xgb_pred_test, bilstm_pred_test, tft_pred_test
                )
                if len(y_test_al) > 0:
                    self._check_diversity(
                        y_test_al,
                        {"XGBoost": xgb_t, "BiLSTM-Attn": bilstm_t, "TFT": tft_t},
                        job_id,
                    )
                    base_preds_test = np.column_stack([xgb_t, bilstm_t, tft_t])
                    y_pred = self.ensemble.predict(base_preds_test)
                    y_test_aligned = y_test_al
                else:
                    valid = np.isfinite(bilstm_pred_test)
                    y_pred = xgb_pred_test[valid]
                    y_test_aligned = y_test.values[valid]
            else:
                # 2-learner mode: XGBoost + BiLSTM only
                y_test_al, xgb_t, bilstm_t = self._align_predictions(
                    y_test, xgb_pred_test, bilstm_pred_test
                )
                if len(y_test_al) > 0:
                    self._check_diversity(
                        y_test_al,
                        {"XGBoost": xgb_t, "BiLSTM-Attn": bilstm_t},
                        job_id,
                    )
                    base_preds_test = np.column_stack([xgb_t, bilstm_t])
                    y_pred = self.ensemble.predict(base_preds_test)
                    y_test_aligned = y_test_al
                else:
                    valid = np.isfinite(bilstm_pred_test)
                    y_pred = xgb_pred_test[valid]
                    y_test_aligned = y_test.values[valid]
        else:
            valid = np.isfinite(bilstm_pred_test)
            y_pred = xgb_pred_test[valid] if valid.any() else xgb_pred_test
            y_test_aligned = y_test.values[valid] if valid.any() else y_test.values

        y_true_arr = y_test_aligned.values if hasattr(y_test_aligned, "values") else y_test_aligned
        metrics = self._evaluate(y_true_arr, y_pred)
        progress.emit(job_id, "metrics", f"Metricas: {metrics}", 95, data=metrics)
        logger.info(f"Resultados: {metrics}")

        _clear_vram("post-evaluation", job_id)
        return metrics

    def predict(self, ticker: str, horizon_days: int = 1) -> dict:
        """Interface para stats_agent: previsao para um ticker."""
        if not self.xgb_model or not self.bilstm_model:
            return {"erro": "Modelo nao treinado. Execute train() primeiro."}

        df = self.collect_data(ticker, start="2024-01-01")
        df = create_features(df)
        # NÃO chamar create_target() na inferência — ela remove as últimas `horizon` linhas
        # via dropna(), perdendo o dado mais recente (hoje). Para predict, só precisamos
        # das features, não do target.
        # Adicionar coluna target dummy (0.0) para TFT from_dataset() que exige schema matching.
        if "target" not in df.columns:
            df["target"] = 0.0

        X = pd.DataFrame(self.scaler.transform(df[self.feature_cols]),
                         index=df.index, columns=self.feature_cols)

        xgb_pred = self.xgb_model.predict(X.iloc[[-1]])
        X_neural = X[self.neural_feature_cols] if self.neural_feature_cols else X
        # Passar seq_len*2 rows para garantir ao menos seq_len predições válidas
        bilstm_pred = predict_bilstm(self.bilstm_model, X_neural.iloc[-self.seq_len * 2:], self.seq_len)

        # Com NaN-padding, verificar se o último valor é finito
        bilstm_last = bilstm_pred[np.isfinite(bilstm_pred)]
        if len(bilstm_last) == 0:
            xgb_val = float(xgb_pred[0])
            if abs(xgb_val) < NEUTRAL_THRESHOLD:
                direcao = "neutra"
            else:
                direcao = "alta" if xgb_val > 0 else "baixa"
            return {
                "ticker": ticker,
                "horizonte_dias": horizon_days,
                "retorno_previsto_pct": round(xgb_val * 100, 4),
                "direcao": direcao,
                "confianca_pct": 50.0,  # Single model — default moderate
                "pred_std": 0.0,
                "pred_xgboost": round(xgb_val * 100, 4),
                "pred_bilstm": None,
                "pred_tft": None,
                "pred_ensemble": round(xgb_val * 100, 4),
                "fonte": "xgboost_only",
            }
        bilstm_val = float(bilstm_last[-1])

        # TFT prediction real quando possível
        tft_pred_val = None
        if self.tft_wrapper and self.tft_wrapper.model and self.tft_wrapper._training_ds:
            try:
                tft_preds = self.tft_wrapper.predict_on_data(df)
                if len(tft_preds) > 0:
                    tft_pred_val = float(tft_preds[-1])
            except Exception as e:
                logger.warning(f"TFT predict falhou: {e}. Usando proxy.")

        if self.ensemble:
            n_learners = getattr(self, "_n_base_learners", 3)
            if n_learners == 3:
                tft_final = tft_pred_val if tft_pred_val is not None else (xgb_pred[0] + bilstm_val) / 2
                base_preds = np.array([[xgb_pred[0], bilstm_val, tft_final]])
            else:
                base_preds = np.array([[xgb_pred[0], bilstm_val]])
            ensemble_pred = self.ensemble.predict(base_preds)[0]
            fonte = "ensemble"
        else:
            ensemble_pred = (xgb_pred[0] + bilstm_val) / 2
            fonte = "media_base"

        # Validação de saída — fallback se ensemble produzir NaN/inf
        base_values = [float(xgb_pred[0]), bilstm_val]
        if tft_pred_val is not None:
            base_values.append(tft_pred_val)

        if not np.isfinite(ensemble_pred):
            logger.warning(f"Ensemble predict produziu valor não-finito: {ensemble_pred}. Tentando fallback.")
            finite_values = [v for v in base_values if np.isfinite(v)]
            if finite_values:
                ensemble_pred = np.mean(finite_values)
                fonte = "fallback_avg"
                logger.info(f"Fallback: média de {len(finite_values)} base learners finitos = {ensemble_pred:.6f}")
            else:
                ensemble_pred = 0.0
                fonte = "fallback_zero"
                logger.error("Nenhum base learner produziu valor finito. Retornando 0.0.")

        # Zona neutra + confiança
        if abs(ensemble_pred) < NEUTRAL_THRESHOLD:
            direcao = "neutra"
        else:
            direcao = "alta" if ensemble_pred > 0 else "baixa"

        # Score de confiança baseado em concordância e dispersão
        finite_base = [v for v in base_values if np.isfinite(v)]
        if len(finite_base) >= 2:
            pred_std = float(np.std(finite_base))
            # Concordância: proporção de modelos na mesma direção do ensemble
            agreement = sum(1 for v in finite_base if np.sign(v) == np.sign(ensemble_pred)) / len(finite_base)
            # Decaimento exponencial: std=0 → 1.0, std=0.005 → ~0.37, std=0.01 → ~0.14
            dispersion_score = float(np.exp(-pred_std / 0.005))
            confianca_pct = round(dispersion_score * agreement * 100, 1)
        else:
            pred_std = 0.0
            agreement = 1.0
            confianca_pct = 50.0  # Single model — default moderate

        result = {
            "ticker": ticker,
            "horizonte_dias": horizon_days,
            "retorno_previsto_pct": round(float(ensemble_pred) * 100, 4),
            "direcao": direcao,
            "confianca_pct": confianca_pct,
            "pred_std": round(pred_std * 100, 4),
            "pred_xgboost": round(float(xgb_pred[0]) * 100, 4),
            "pred_bilstm": round(float(bilstm_val) * 100, 4),
            "pred_ensemble": round(float(ensemble_pred) * 100, 4),
            "pred_tft": round(tft_pred_val * 100, 4) if tft_pred_val is not None else None,
            "fonte": fonte,
        }
        return result

    def save(self, ticker: str):
        """Salva modelos treinados em disco para reutilizacao."""
        d = self._ticker_dir(ticker)
        os.makedirs(d, exist_ok=True)

        # Scaler
        joblib.dump(self.scaler, os.path.join(d, "scaler.pkl"))

        # XGBoost
        if self.xgb_model:
            self.xgb_model.model.save_model(os.path.join(d, "xgboost.json"))

        # BiLSTM (PyTorch state_dict)
        if self.bilstm_model:
            torch.save(self.bilstm_model.state_dict(), os.path.join(d, "bilstm.pt"))

        # TFT (checkpoint completo)
        if self.tft_wrapper:
            self.tft_wrapper.save_checkpoint(os.path.join(d, "tft.ckpt"))

        # Ensemble meta-learner
        if self.ensemble:
            joblib.dump(self.ensemble, os.path.join(d, "ensemble_meta.pkl"))

        # Metadata
        meta = {
            "trained_at": datetime.now().isoformat(),
            "feature_cols": self.feature_cols,
            "neural_feature_cols": self.neural_feature_cols,
            "seq_len": self.seq_len,
            "ticker": ticker,
            "xgb_feature_importance": getattr(self, "_xgb_feature_importance", {}),
            "n_base_learners": getattr(self, "_n_base_learners", 3),
        }
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f)

        logger.info(f"Modelos salvos em {d}")

    def load(self, ticker: str) -> bool:
        """Carrega modelos do disco. Retorna True se sucesso."""
        d = self._ticker_dir(ticker)
        meta_path = os.path.join(d, "meta.json")
        if not os.path.exists(meta_path):
            return False

        with open(meta_path) as f:
            meta = json.load(f)
        self.feature_cols = meta["feature_cols"]
        self.neural_feature_cols = meta.get("neural_feature_cols", select_features(self.feature_cols))
        self.seq_len = meta["seq_len"]
        self._n_base_learners = meta.get("n_base_learners", 3)

        # Scaler
        scaler_path = os.path.join(d, "scaler.pkl")
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)

        # XGBoost
        xgb_path = os.path.join(d, "xgboost.json")
        if os.path.exists(xgb_path):
            self.xgb_model = XGBoostForecaster(use_gpu=True)
            self.xgb_model.model.load_model(xgb_path)

        # BiLSTM
        bilstm_path = os.path.join(d, "bilstm.pt")
        if os.path.exists(bilstm_path):
            try:
                self.bilstm_model = BiLSTMAttention(input_size=len(self.neural_feature_cols))
                self.bilstm_model.load_state_dict(
                    torch.load(bilstm_path, map_location="cpu", weights_only=True)
                )
                self.bilstm_model.eval()
                if torch.cuda.is_available():
                    self.bilstm_model = self.bilstm_model.cuda()
            except (RuntimeError, KeyError, EOFError, OSError) as e:
                logger.warning(
                    f"Checkpoint BiLSTM incompatível (arquitetura mudou): {e}. "
                    f"Modelo será retreinado no próximo train()."
                )
                self.bilstm_model = None

        # TFT
        tft_path = os.path.join(d, "tft.ckpt")
        if os.path.exists(tft_path):
            try:
                from pytorch_forecasting import TemporalFusionTransformer
                tft_model = TemporalFusionTransformer.load_from_checkpoint(tft_path)
                self.tft_wrapper = TFTWrapper()
                self.tft_wrapper.model = tft_model
            except Exception as e:
                logger.warning(f"Falha ao carregar TFT: {e}. Continuando sem TFT.")
                self.tft_wrapper = None

        # Ensemble meta-learner
        ensemble_path = os.path.join(d, "ensemble_meta.pkl")
        if os.path.exists(ensemble_path):
            self.ensemble = joblib.load(ensemble_path)

        logger.info(f"Modelos carregados de {d}")
        return True

    def is_model_fresh(self, ticker: str, max_age_days: int = 7) -> bool:
        """Verifica se modelo salvo e recente o suficiente."""
        d = self._ticker_dir(ticker)
        meta_path = os.path.join(d, "meta.json")
        if not os.path.exists(meta_path):
            return False
        with open(meta_path) as f:
            meta = json.load(f)
        trained_at = datetime.fromisoformat(meta["trained_at"])
        age = (datetime.now() - trained_at).days
        return age < max_age_days

    def _evaluate(self, y_true, y_pred) -> dict:
        rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        mae = float(mean_absolute_error(y_true, y_pred))
        r2 = float(r2_score(y_true, y_pred))
        # sMAPE (symmetric) em vez de MAPE — MAPE explode quando y_true ≈ 0 (retornos)
        denom = np.abs(y_true) + np.abs(y_pred)
        smape = float(np.mean(2 * np.abs(y_true - y_pred) / np.where(denom == 0, 1.0, denom)) * 100)
        dir_acc = float((np.sign(y_pred) == np.sign(y_true)).mean() * 100)

        return {
            "rmse": round(rmse, 6),
            "mae": round(mae, 6),
            "r2": round(r2, 4),
            "smape_pct": round(smape, 2),
            "directional_accuracy_pct": round(dir_acc, 1),
        }
