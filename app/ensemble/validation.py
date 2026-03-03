"""
Walk-Forward Validation com Purging e Embargo.
Padrão acadêmico para séries temporais financeiras.

REGRA ABSOLUTA: Nunca usar split aleatório em séries temporais.
Referência: López de Prado (2018) — "Advances in Financial Machine Learning"
"""

import numpy as np
import pandas as pd


class WalkForwardValidator:
    """Walk-Forward Validation (Expanding Window) com Purging e Embargo."""

    def __init__(self, n_splits: int = 5, val_size: int = 60, gap: int = 5, embargo: int = 2):
        """
        n_splits:  número de folds
        val_size:  tamanho da janela de validação (dias úteis)
        gap:       purge — dias removidos entre treino e validação
        embargo:   dias removidos após validação (evita leakage reverso)
        """
        self.n_splits = n_splits
        self.val_size = val_size
        self.gap = gap
        self.embargo = embargo

    def split(self, X):
        n = len(X)
        embargo_zones: set[int] = set()

        for i in range(self.n_splits):
            val_end = n - (self.n_splits - 1 - i) * self.val_size
            val_start = val_end - self.val_size
            train_end = val_start - self.gap  # PURGE

            if train_end < self.val_size:
                continue

            # Remove embargo zones from previous folds' validation periods
            train_idx = np.array([j for j in range(train_end) if j not in embargo_zones])
            val_idx = np.arange(val_start, val_end)

            yield train_idx, val_idx

            # Add embargo zone AFTER this fold's validation for subsequent folds
            # Prevents leakage via rolling-window features (rsi_14, volatility_20d, etc.)
            embargo_start = val_end
            embargo_end = min(val_end + self.embargo, n)
            embargo_zones.update(range(embargo_start, embargo_end))

    def summary(self, X):
        """Imprime resumo dos folds."""
        for fold, (train_idx, val_idx) in enumerate(self.split(X)):
            if hasattr(X, "index"):
                print(
                    f"Fold {fold + 1}: "
                    f"Treino [{X.index[train_idx[0]].date()} → {X.index[train_idx[-1]].date()}] "
                    f"({len(train_idx)} dias) | "
                    f"Val [{X.index[val_idx[0]].date()} → {X.index[val_idx[-1]].date()}] "
                    f"({len(val_idx)} dias)"
                )
            else:
                print(
                    f"Fold {fold + 1}: "
                    f"Treino [0 → {train_idx[-1]}] ({len(train_idx)}) | "
                    f"Val [{val_idx[0]} → {val_idx[-1]}] ({len(val_idx)})"
                )
