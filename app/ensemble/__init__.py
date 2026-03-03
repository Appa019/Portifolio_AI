"""
Ensemble ML: XGBoost + BiLSTM-Attention + TFT/PatchTST
Otimizado para RTX 2070 SUPER (8GB VRAM) com Mixed Precision FP16.
"""

from app.ensemble.pipeline import EnsemblePipeline

__all__ = ["EnsemblePipeline"]
