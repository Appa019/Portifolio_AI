"""
BiLSTM + Multi-Head Attention Base Learner.
Otimizado para RTX 2070 SUPER (8GB VRAM) com Mixed Precision FP16.

Referência: CAB-XDE Framework (arXiv, 2024) — ~27% menor MAPE vs SOTA
"""

import logging
import os

import numpy as np
import lightning.pytorch as pl
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)

# Otimização VRAM para RTX 2070 SUPER
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:512")


class TimeSeriesDataset(Dataset):
    """Dataset para sequências temporais."""

    def __init__(self, X, y, seq_len: int = 60):
        self.X = torch.FloatTensor(X.values if hasattr(X, "values") else X)
        self.y = torch.FloatTensor(y.values if hasattr(y, "values") else y)
        self.seq_len = seq_len

    def __len__(self):
        return len(self.X) - self.seq_len

    def __getitem__(self, idx):
        x = self.X[idx : idx + self.seq_len]
        y = self.y[idx + self.seq_len]
        return x, y


class MultiHeadAttention(nn.Module):
    """Multi-Head Attention sobre output do BiLSTM."""

    def __init__(self, hidden_size: int, n_heads: int = 4):
        super().__init__()
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size * 2,  # BiLSTM output
            num_heads=n_heads,
            dropout=0.1,
            batch_first=True,
        )
        self.norm = nn.LayerNorm(hidden_size * 2)

    def forward(self, x):
        attn_out, attn_weights = self.attention(x, x, x)
        out = self.norm(x + attn_out)  # Residual connection
        context = out.mean(dim=1)  # Pool temporal
        return context, attn_weights


class BiLSTMAttention(pl.LightningModule):
    """BiLSTM + Multi-Head Attention para previsão de retornos financeiros."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,  # Adequado para 8GB VRAM
        num_layers: int = 2,
        n_heads: int = 4,
        dropout: float = 0.3,
        lr: float = 1e-3,
    ):
        super().__init__()
        self.save_hyperparameters()

        self.input_proj = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.LayerNorm(hidden_size),
            nn.Dropout(dropout),
        )

        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        self.attention = MultiHeadAttention(hidden_size, n_heads)

        self.head = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size // 2),
            nn.GELU(),
            nn.Dropout(dropout / 2),
            nn.Linear(hidden_size // 2, 1),
        )

        self.lr = lr

    def forward(self, x):
        x = self.input_proj(x)
        lstm_out, _ = self.lstm(x)
        context, _ = self.attention(lstm_out)
        out = self.head(context)
        return out.squeeze(-1)

    def training_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        # delta=0.02 adequado para retornos (tipicamente [-0.05, 0.05])
        # Com delta=1.0 a loss era efetivamente MSE (outliers nunca excedem 1.0)
        loss = nn.HuberLoss(delta=0.02)(y_hat, y)
        self.log("train_loss", loss, prog_bar=True)
        return loss

    def validation_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = nn.HuberLoss(delta=0.02)(y_hat, y)
        self.log("val_loss", loss, prog_bar=True)

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(self.parameters(), lr=self.lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=10, T_mult=2
        )
        return {"optimizer": optimizer, "lr_scheduler": scheduler}


def train_bilstm(
    X_train, y_train, X_val, y_val,
    input_size: int,
    seq_len: int = 60,
    hidden_size: int = 64,
    max_epochs: int = 100,
    batch_size: int = 128,
    checkpoint_dir: str = "checkpoints/bilstm",
):
    """Treina BiLSTM com Mixed Precision (FP16) para caber na RTX 2070 SUPER."""
    train_ds = TimeSeriesDataset(X_train, y_train, seq_len)
    val_ds = TimeSeriesDataset(X_val, y_val, seq_len)

    train_dl = DataLoader(
        train_ds, batch_size=batch_size, shuffle=False,
        num_workers=4, pin_memory=True,  # pin_memory acelera CPU→GPU
    )
    val_dl = DataLoader(
        val_ds, batch_size=batch_size * 2, shuffle=False,
        num_workers=4, pin_memory=True,
    )

    model = BiLSTMAttention(
        input_size=input_size,
        hidden_size=hidden_size,
        num_layers=2,
        n_heads=4,
        dropout=0.3,
        lr=1e-3,
    )

    accel = "gpu" if torch.cuda.is_available() else "cpu"
    precision = "16-mixed" if accel == "gpu" else "32-true"

    trainer = pl.Trainer(
        max_epochs=max_epochs,
        accelerator=accel,
        devices=1,
        precision=precision,  # FP16 só com GPU — CPU não suporta 16-mixed
        gradient_clip_val=1.0,
        accumulate_grad_batches=2,  # Simula batch maior sem usar mais VRAM
        callbacks=[
            pl.callbacks.EarlyStopping(monitor="val_loss", patience=15, mode="min"),
            pl.callbacks.ModelCheckpoint(
                dirpath=checkpoint_dir,
                monitor="val_loss",
                mode="min",
                save_top_k=1,
                filename="best_bilstm",
            ),
        ],
        enable_progress_bar=True,
        log_every_n_steps=10,
    )

    trainer.fit(model, train_dl, val_dl)

    # Convergence logging
    epochs_run = trainer.current_epoch + 1
    early_stopped = epochs_run < max_epochs
    best_val_loss = trainer.checkpoint_callback.best_model_score
    best_val_str = f"{best_val_loss:.6f}" if best_val_loss is not None else "N/A"
    logger.info(
        f"BiLSTM convergence: {epochs_run}/{max_epochs} epochs, "
        f"best_val_loss={best_val_str}, early_stopped={'yes' if early_stopped else 'no'}"
    )

    best = BiLSTMAttention.load_from_checkpoint(
        trainer.checkpoint_callback.best_model_path,
        input_size=input_size,
    )
    return best


def predict_bilstm(
    model: BiLSTMAttention, X, seq_len: int = 60,
    pad_to_full: bool = True, batch_size: int = 256,
) -> np.ndarray:
    """Gera previsões do BiLSTM com inferência batched.

    Args:
        pad_to_full: Se True, prepende NaN para igualar len(output) == len(X).
                     Primeiros seq_len valores serão NaN (sem janela completa).
        batch_size: Tamanho do batch para inferência (256 cabe na RTX 2070 SUPER).

    Returns:
        Array de predições. Com pad_to_full=True: len == len(X).
    """
    model.eval()
    device = next(model.parameters()).device

    X_tensor = torch.FloatTensor(X.values if hasattr(X, "values") else X)
    n_samples = len(X_tensor) - seq_len

    if n_samples <= 0:
        if pad_to_full:
            return np.full(len(X_tensor), np.nan)
        return np.array([])

    # Construir todas as janelas de uma vez via unfold-like indexing
    indices = torch.arange(n_samples).unsqueeze(1) + torch.arange(seq_len).unsqueeze(0)
    windows = X_tensor[indices]  # (n_samples, seq_len, features)

    # Inferência em batches
    preds = []
    with torch.no_grad():
        for start in range(0, n_samples, batch_size):
            batch = windows[start : start + batch_size].to(device)
            out = model(batch)
            preds.append(out.cpu().numpy())

    result = np.concatenate(preds)

    if pad_to_full:
        # Prepend NaN para alinhar com input: primeiros seq_len = NaN
        padding = np.full(seq_len, np.nan)
        result = np.concatenate([padding, result])

    return result


class BiLSTMWrapper:
    """Wrapper para BiLSTM com interface fit/predict uniforme para stacking."""

    def __init__(self, input_size: int, seq_len: int = 60, **kwargs):
        self.input_size = input_size
        self.seq_len = seq_len
        self.kwargs = kwargs
        self.model = None

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        self.model = train_bilstm(
            X_train, y_train, X_val, y_val,
            input_size=self.input_size, seq_len=self.seq_len, **self.kwargs,
        )
        return self

    def predict(self, X) -> np.ndarray:
        return predict_bilstm(self.model, X, self.seq_len, pad_to_full=False)
