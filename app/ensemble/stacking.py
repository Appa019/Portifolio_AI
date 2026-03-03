"""
Stacking Ensemble com Meta-Learner.
Baseado em: "Stock Price Prediction Using a Stacked Heterogeneous Ensemble" (MDPI, 2025)

Procedimento:
1. Gerar out-of-fold (OOF) predictions dos base learners
2. Treinar meta-learner nos OOF predictions
3. Para previsão final: base learners predizem → meta-learner combina
"""

import logging

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error

from app.ensemble.validation import WalkForwardValidator

logger = logging.getLogger(__name__)


class StackingEnsemble:
    """Stacking Ensemble Heterogêneo com XGBoost meta-learner (CPU — 3 features não justifica GPU)."""

    def __init__(self, meta_type: str = "xgboost"):
        self.base_models = {}
        self.meta_type = meta_type

        if meta_type == "xgboost":
            self.meta = xgb.XGBRegressor(
                n_estimators=300,
                max_depth=3,  # Raso para evitar overfitting
                learning_rate=0.05,
                subsample=0.8,
                reg_alpha=1.0,  # Forte regularização
                reg_lambda=2.0,
                device="cpu",  # 3 features = CPU é mais rápido que GPU
            )
        elif meta_type == "ridge":
            from sklearn.linear_model import RidgeCV
            self.meta = RidgeCV(alphas=np.logspace(-3, 3, 20))
        else:
            from sklearn.linear_model import LinearRegression
            self.meta = LinearRegression(positive=True)

    def generate_oof_predictions(self, X, y, wfv: WalkForwardValidator, base_learners: dict) -> np.ndarray:
        """Gera OOF predictions via Walk-Forward Validation."""
        n_models = len(base_learners)
        oof_preds = np.full((len(X), n_models), np.nan)

        for fold, (train_idx, val_idx) in enumerate(wfv.split(X)):
            logger.info(f"Fold {fold + 1}")
            X_tr, X_vl = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_vl = y.iloc[train_idx], y.iloc[val_idx]

            for i, (name, learner) in enumerate(base_learners.items()):
                logger.info(f"  Treinando {name}...")
                learner.fit(X_tr, y_tr, X_vl, y_vl)
                preds = learner.predict(X_vl)
                oof_preds[val_idx, i] = preds
                rmse = np.sqrt(mean_squared_error(y_vl, preds))
                logger.info(f"    RMSE fold: {rmse:.6f}")

        return oof_preds

    def fit_meta(self, oof_preds: np.ndarray, y, feature_names: list[str] | None = None):
        """Treina meta-learner nos OOF predictions."""
        mask = ~np.isnan(oof_preds).any(axis=1)
        X_meta = oof_preds[mask]
        y_meta = y.values[mask] if hasattr(y, "values") else y[mask]

        self.meta.fit(X_meta, y_meta)

        if hasattr(self.meta, "feature_importances_"):
            names = feature_names or [f"model_{i}" for i in range(X_meta.shape[1])]
            imp = pd.Series(self.meta.feature_importances_, index=names)
            logger.info("Pesos do Meta-Learner:")
            for name, weight in imp.items():
                logger.info(f"  {name}: {weight:.4f}")

        return self

    def predict(self, base_predictions: np.ndarray) -> np.ndarray:
        """Previsão final combinando base learners."""
        return self.meta.predict(base_predictions)
