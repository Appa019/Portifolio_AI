"""
Temporal Fusion Transformer (TFT) Base Learner.
Otimizado para RTX 2070 SUPER (8GB VRAM) — hidden_size=32, FP32.
FP32 obrigatório: attention mask usa bias -1e9 que overflow em FP16 (max ~65504).
Referência: Lim et al. (2021, Google Research) + PatchTST (Nie et al., 2023)
"""

import logging
import os

import numpy as np
import pandas as pd
import lightning.pytorch as pl
import torch
from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.metrics import QuantileLoss

logger = logging.getLogger(__name__)


def train_tft(
    df: pd.DataFrame,
    target: str = "target",
    max_encoder: int = 60,
    max_decoder: int = 5,
    max_epochs: int = 80,
    batch_size: int = 64,
    hidden_size: int = 32,  # Compacto para 8GB VRAM
    checkpoint_dir: str = "checkpoints/tft",
):
    """Treina TFT com Mixed Precision (FP16) na RTX 2070 SUPER."""
    df_tft = df.reset_index()
    df_tft["time_idx"] = range(len(df_tft))
    df_tft["group"] = "stock"
    df_tft["day_of_week"] = df_tft["day_of_week"].astype(str)
    df_tft["month"] = df_tft["month"].astype(str)

    cutoff = df_tft["time_idx"].max() - max_decoder

    # Features disponíveis no dataset
    unknown_reals = [target]
    for col in ["rsi_14", "macd", "macd_histogram", "bb_position", "atr_pct",
                 "returns", "volatility_20d", "volume_ratio", "adx", "stoch_k"]:
        if col in df_tft.columns:
            unknown_reals.append(col)

    training = TimeSeriesDataSet(
        df_tft[lambda x: x.time_idx <= cutoff],
        time_idx="time_idx",
        target=target,
        group_ids=["group"],
        max_encoder_length=max_encoder,
        max_prediction_length=max_decoder,
        time_varying_known_categoricals=["day_of_week", "month"],
        time_varying_known_reals=["time_idx"],
        time_varying_unknown_reals=unknown_reals,
        target_normalizer="auto",
        add_relative_time_idx=True,
        add_target_scales=True,
    )

    validation = TimeSeriesDataSet.from_dataset(training, df_tft, predict=True)

    train_dl = training.to_dataloader(train=True, batch_size=batch_size, num_workers=4)
    val_dl = validation.to_dataloader(train=False, batch_size=batch_size * 2, num_workers=4)

    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=1e-3,
        hidden_size=hidden_size,
        attention_head_size=4,
        dropout=0.2,
        hidden_continuous_size=16,
        output_size=7,  # Quantiles: 0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98
        loss=QuantileLoss(),
        reduce_on_plateau_patience=8,
    )

    logger.info(f"Parâmetros TFT: {tft.size() / 1e3:.1f}k")

    accel = "gpu" if torch.cuda.is_available() else "cpu"
    # TFT attention mask usa mask_bias=-1e9 que overflow em FP16 (max ~65504).
    # RTX 2070 SUPER não suporta BF16, então usar FP32 para TFT.
    precision = "32-true"

    trainer = pl.Trainer(
        max_epochs=max_epochs,
        accelerator=accel,
        devices=1,
        precision=precision,  # FP16 só com GPU
        gradient_clip_val=0.1,
        callbacks=[
            pl.callbacks.EarlyStopping(monitor="val_loss", patience=15),
            pl.callbacks.ModelCheckpoint(dirpath=checkpoint_dir, monitor="val_loss"),
        ],
    )

    trainer.fit(tft, train_dl, val_dl)

    # Convergence logging
    epochs_run = trainer.current_epoch + 1
    early_stopped = epochs_run < max_epochs
    best_val_loss = trainer.checkpoint_callback.best_model_score
    best_val_str = f"{best_val_loss:.6f}" if best_val_loss is not None else "N/A"
    logger.info(
        f"TFT convergence: {epochs_run}/{max_epochs} epochs, "
        f"best_val_loss={best_val_str}, early_stopped={'yes' if early_stopped else 'no'}"
    )

    best = TemporalFusionTransformer.load_from_checkpoint(
        trainer.checkpoint_callback.best_model_path
    )
    best._best_model_path = trainer.checkpoint_callback.best_model_path
    return best, training, validation


def predict_tft(model: TemporalFusionTransformer, dataset: TimeSeriesDataSet) -> np.ndarray:
    """Gera previsoes do TFT usando o dataset formatado."""
    dl = dataset.to_dataloader(train=False, batch_size=128, num_workers=4)
    preds = model.predict(dl, return_x=False)
    # preds shape: (n_samples, max_decoder, n_quantiles) ou (n_samples, max_decoder)
    if preds.ndim == 3:
        # Pegar mediana (quantile index 3 = 0.5 dos 7 quantiles)
        median_preds = preds[:, 0, 3].numpy()
    elif preds.ndim == 2:
        median_preds = preds[:, 0].numpy()
    else:
        median_preds = preds.numpy()
    return median_preds


class TFTWrapper:
    """Wrapper para TFT com interface fit/predict uniforme para stacking."""

    def __init__(self, target: str = "target", max_encoder: int = 60,
                 max_decoder: int = 5, hidden_size: int = 32,
                 batch_size: int = 64, checkpoint_dir: str = "checkpoints/tft",
                 **kwargs):
        self.target = target
        self.max_encoder = max_encoder
        self.max_decoder = max_decoder
        self.hidden_size = hidden_size
        self.batch_size = batch_size
        self.checkpoint_dir = checkpoint_dir
        self.kwargs = kwargs
        self.model = None
        self._training_ds = None
        self._val_ds = None

    def fit(self, df: pd.DataFrame, **kwargs):
        """Treina TFT. Recebe DataFrame completo (pre-split) com features + target."""
        self.model, self._training_ds, self._val_ds = train_tft(
            df,
            target=self.target,
            max_encoder=self.max_encoder,
            max_decoder=self.max_decoder,
            hidden_size=self.hidden_size,
            batch_size=self.batch_size,
            checkpoint_dir=self.checkpoint_dir,
        )
        return self

    def predict_validation(self) -> np.ndarray:
        """Gera previsoes no conjunto de validacao."""
        if self.model is None or self._val_ds is None:
            raise RuntimeError("Modelo nao treinado. Chame fit() primeiro.")
        return predict_tft(self.model, self._val_ds)

    def predict_on_data(self, df: pd.DataFrame) -> np.ndarray:
        """Gera previsoes reais do TFT sobre um DataFrame arbitrário (ex: test set).

        Usa TimeSeriesDataSet.from_dataset() com o training dataset como base
        para garantir mesmo esquema de normalização e features.
        """
        if self.model is None or self._training_ds is None:
            raise RuntimeError("Modelo nao treinado. Chame fit() primeiro.")

        df_tft = df.reset_index()
        df_tft["time_idx"] = range(len(df_tft))
        df_tft["group"] = "stock"
        df_tft["day_of_week"] = df_tft["day_of_week"].astype(str)
        df_tft["month"] = df_tft["month"].astype(str)

        test_ds = TimeSeriesDataSet.from_dataset(self._training_ds, df_tft, predict=True)
        if len(test_ds) == 0:
            logger.warning(
                f"TFT predict_on_data: dataset vazio após from_dataset() "
                f"(input: {len(df)} linhas, time_idx: 0-{len(df_tft)-1}). "
                f"Slice provavelmente muito curto para max_encoder={self.max_encoder}."
            )
            return np.array([])
        return predict_tft(self.model, test_ds)

    def save_checkpoint(self, path: str):
        """Salva checkpoint completo do TFT."""
        if self.model is not None and hasattr(self.model, "_best_model_path"):
            import shutil
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copy2(self.model._best_model_path, path)

    @classmethod
    def load_checkpoint(cls, path: str) -> TemporalFusionTransformer:
        """Carrega TFT de checkpoint."""
        return TemporalFusionTransformer.load_from_checkpoint(path)
