"""
XGBoost Base Learner — GPU accelerated via device="cuda:0".
Otimizado para RTX 2070 SUPER (8GB VRAM).
XGBoost >= 2.0: device= auto-seleciona tree_method, sem necessidade de tree_method="gpu_hist".
"""

import logging

import numpy as np
import pandas as pd
import xgboost as xgb

logger = logging.getLogger(__name__)


class XGBoostForecaster:
    """XGBoost para previsão de retornos com aceleração GPU."""

    def __init__(self, use_gpu: bool = True):
        device = "cpu"
        if use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda:0"
                else:
                    logger.info("CUDA não disponível, usando CPU para XGBoost")
            except ImportError:
                logger.info("PyTorch não instalado, usando CPU para XGBoost")

        self.model = xgb.XGBRegressor(
            n_estimators=2000,
            max_depth=8,             # 6→8: captura interações mais complexas
            learning_rate=0.01,
            subsample=0.8,
            colsample_bytree=0.6,    # 0.7→0.6: mais randomness por árvore
            reg_alpha=0.5,           # 0.1→0.5: L1 mais forte (compensa profundidade)
            reg_lambda=2.0,          # 1.0→2.0: L2 mais forte
            min_child_weight=10,     # 5→10: splits mais conservadores
            gamma=0.3,              # 0.1→0.3: threshold mais alto para split
            device=device,
            random_state=42,
        )

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        fit_params = {}
        if X_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            self.model.set_params(early_stopping_rounds=50)

        self.model.fit(X_train, y_train, verbose=100, **fit_params)
        return self

    def predict(self, X) -> np.ndarray:
        return self.model.predict(X)

    def feature_importance(self, top_n: int = 20) -> pd.Series:
        imp = pd.Series(
            self.model.feature_importances_,
            index=self.model.feature_names_in_,
        ).sort_values(ascending=False)
        return imp.head(top_n)
