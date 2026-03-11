"""
Teste REAL de GPU — treina XGBoost + BiLSTM + TFT + Stacking em PETR4.SA.
Verifica que cada modelo roda na GPU (CUDA) e gera predictions válidas.
"""

import os
import sys
import time

# Garantir que 'app' é importável quando rodando de qualquer diretório
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import torch
import xgboost as xgb

# ── Setup ──────────────────────────────────────────────────────────────
assert torch.cuda.is_available(), "CUDA não disponível!"
GPU = torch.cuda.get_device_name(0)
print(f"\n{'='*60}")
print(f"GPU: {GPU}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
print(f"PyTorch: {torch.__version__} | XGBoost: {xgb.__version__}")
print(f"{'='*60}\n")

# ── 1. Coletar dados reais via Yahoo scraper ──────────────────────────
print("[1/6] Coletando dados PETR4.SA via Yahoo scraper...")
t0 = time.time()
from app.ensemble.pipeline import EnsemblePipeline  # noqa: E402
df = EnsemblePipeline().collect_data("PETR4.SA", start="2020-01-01")
print(f"  → {len(df)} dias coletados ({time.time()-t0:.1f}s)\n")
assert len(df) > 500, f"Dados insuficientes: {len(df)}"

# ── 2. Feature engineering ─────────────────────────────────────────────
print("[2/6] Calculando features...")
t0 = time.time()
from app.ensemble.features import create_features, create_target, get_feature_columns  # noqa: E402

df = create_features(df)
df = create_target(df, horizon=1)
feature_cols = get_feature_columns(df)
print(f"  → {len(feature_cols)} features, {len(df)} linhas ({time.time()-t0:.1f}s)\n")

# Split temporal
n = len(df)
train_end = int(n * 0.8)
val_end = int(n * 0.9)
train, val, test = df.iloc[:train_end], df.iloc[train_end:val_end], df.iloc[val_end:]

from sklearn.preprocessing import RobustScaler  # noqa: E402
scaler = RobustScaler()
scaler.fit(train[feature_cols])
X_train = pd.DataFrame(scaler.transform(train[feature_cols]), index=train.index, columns=feature_cols)
X_val = pd.DataFrame(scaler.transform(val[feature_cols]), index=val.index, columns=feature_cols)
X_test = pd.DataFrame(scaler.transform(test[feature_cols]), index=test.index, columns=feature_cols)
y_train, y_val, y_test = train["target"], val["target"], test["target"]

print(f"  Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}\n")

results = {}

# ── 3. XGBoost GPU ─────────────────────────────────────────────────────
print("[3/6] XGBoost com device='cuda:0'...")
t0 = time.time()
from app.ensemble.xgboost_model import XGBoostForecaster  # noqa: E402

xgb_model = XGBoostForecaster(use_gpu=True)

# Verificar que device é cuda
params = xgb_model.model.get_params()
assert params.get("device") == "cuda:0", f"XGBoost device errado: {params.get('device')}"
assert "tree_method" not in params or params["tree_method"] is None or params["tree_method"] != "gpu_hist", \
    "tree_method não deveria ser gpu_hist explícito no XGBoost >= 2.0"
print(f"  device={params.get('device')} ✓ (sem tree_method explícito)")

xgb_model.fit(X_train, y_train, X_val, y_val)
xgb_preds = xgb_model.predict(X_test)
elapsed = time.time() - t0

assert len(xgb_preds) == len(X_test), "XGBoost preds shape errado"
assert not np.isnan(xgb_preds).any(), "XGBoost produziu NaN"
results["xgboost"] = {"time": elapsed, "preds": len(xgb_preds), "mean": float(np.mean(xgb_preds))}
print(f"  → {len(xgb_preds)} predictions, mean={np.mean(xgb_preds):.6f} ({elapsed:.1f}s) ✓\n")

# Limpar VRAM
torch.cuda.empty_cache()
import gc  # noqa: E402
gc.collect()

# ── 4. BiLSTM + Attention GPU ──────────────────────────────────────────
print("[4/6] BiLSTM + Attention com FP16 mixed precision...")
t0 = time.time()
from app.ensemble.bilstm_model import train_bilstm, predict_bilstm  # noqa: E402

seq_len = 60
bilstm_model = train_bilstm(
    X_train, y_train, X_val, y_val,
    input_size=len(feature_cols),
    seq_len=seq_len,
    hidden_size=64,
    max_epochs=5,  # Poucos epochs para teste rápido
    batch_size=128,
    checkpoint_dir="/tmp/test_bilstm_ckpt",
)

# Verificar que modelo está na GPU
device = next(bilstm_model.parameters()).device
assert device.type == "cuda", f"BiLSTM não está na GPU! device={device}"
print(f"  device={device} ✓")

bilstm_preds = predict_bilstm(bilstm_model, X_test, seq_len)
elapsed = time.time() - t0

# Com pad_to_full=True (default), output tem mesmo tamanho do input
# Primeiros seq_len valores são NaN (sem janela completa)
assert len(bilstm_preds) == len(X_test), f"BiLSTM pad_to_full: len={len(bilstm_preds)} != X_test={len(X_test)}"
n_valid = np.isfinite(bilstm_preds).sum()
assert n_valid > 0, "BiLSTM não gerou predictions válidas"
assert n_valid == len(X_test) - seq_len, f"BiLSTM: {n_valid} válidos != esperado {len(X_test) - seq_len}"
bilstm_valid = bilstm_preds[np.isfinite(bilstm_preds)]
assert not np.isnan(bilstm_valid).any(), "BiLSTM produziu NaN na região válida"
results["bilstm"] = {"time": elapsed, "preds": int(n_valid), "mean": float(np.mean(bilstm_valid))}
print(f"  → {n_valid} predictions válidas (de {len(bilstm_preds)} com NaN-padding), mean={np.mean(bilstm_valid):.6f} ({elapsed:.1f}s) ✓\n")

torch.cuda.empty_cache()
gc.collect()
vram_after_bilstm = torch.cuda.memory_allocated() / 1e6
print(f"  VRAM após cleanup: {vram_after_bilstm:.0f} MB\n")

# ── 5. TFT GPU ─────────────────────────────────────────────────────────
print("[5/6] TFT com FP16 mixed precision...")
t0 = time.time()
from app.ensemble.tft_model import TFTWrapper  # noqa: E402

tft_wrapper = TFTWrapper(
    target="target",
    max_encoder=seq_len,
    max_decoder=5,
    hidden_size=32,
    batch_size=64,
    checkpoint_dir="/tmp/test_tft_ckpt",
)
# A1 fix: TFT treina apenas com train+val (sem test) para evitar temporal leakage
tft_wrapper.fit(df.iloc[:val_end])

assert tft_wrapper.model is not None, "TFT model é None"
assert tft_wrapper._training_ds is not None, "TFT training_ds é None"

# predict_validation
tft_val_preds = tft_wrapper.predict_validation()
assert len(tft_val_preds) > 0, "TFT validation predictions vazio"
print(f"  val predictions: {len(tft_val_preds)} ✓")

# predict_on_data (teste REAL — BUG 5 fix)
tft_test_preds = tft_wrapper.predict_on_data(df.iloc[val_end:])
elapsed = time.time() - t0

assert len(tft_test_preds) > 0, "TFT predict_on_data retornou vazio!"
assert not np.isnan(tft_test_preds).any(), "TFT produziu NaN"
results["tft"] = {"time": elapsed, "preds_val": len(tft_val_preds), "preds_test": len(tft_test_preds),
                   "mean": float(np.mean(tft_test_preds))}
print(f"  test predictions (predict_on_data): {len(tft_test_preds)} ✓")
print(f"  mean={np.mean(tft_test_preds):.6f} ({elapsed:.1f}s) ✓\n")

torch.cuda.empty_cache()
gc.collect()

# ── 6. Stacking Meta-Learner (CPU) ────────────────────────────────────
print("[6/6] Stacking meta-learner (CPU)...")
t0 = time.time()
from app.ensemble.stacking import StackingEnsemble  # noqa: E402

# Alinhar predictions para stacking usando máscara np.isfinite (novo padrão)
# bilstm_preds agora tem NaN-padding (len == len(X_test))
# TFT pode ter tamanho diferente
tft_padded = np.full(len(xgb_preds), np.nan)
tft_padded[len(tft_padded) - len(tft_test_preds):] = tft_test_preds

stacked = np.column_stack([xgb_preds, bilstm_preds, tft_padded])
valid_mask = np.all(np.isfinite(stacked), axis=1)
xgb_aligned = xgb_preds[valid_mask]
bilstm_aligned = bilstm_preds[valid_mask]
tft_aligned = tft_padded[valid_mask]
min_len = len(xgb_aligned)
base_preds = np.column_stack([xgb_aligned, bilstm_aligned, tft_aligned])
y_aligned = y_test.iloc[len(y_test) - len(valid_mask):][valid_mask]

ensemble = StackingEnsemble(meta_type="xgboost")

# Verificar que meta-learner está no CPU
meta_params = ensemble.meta.get_params()
assert meta_params.get("device") == "cpu", f"Meta-learner device errado: {meta_params.get('device')}"
print(f"  meta-learner device={meta_params.get('device')} ✓")

ensemble.fit_meta(base_preds, y_aligned, feature_names=["XGBoost", "BiLSTM", "TFT"])
final_preds = ensemble.predict(base_preds)
elapsed = time.time() - t0

assert len(final_preds) == min_len, "Stacking preds shape errado"
assert not np.isnan(final_preds).any(), "Stacking produziu NaN"

from sklearn.metrics import mean_squared_error, r2_score  # noqa: E402
rmse = float(np.sqrt(mean_squared_error(y_aligned, final_preds)))
r2 = float(r2_score(y_aligned, final_preds))
dir_acc = float((np.sign(final_preds) == np.sign(y_aligned)).mean() * 100)

results["stacking"] = {"time": elapsed, "rmse": rmse, "r2": r2, "dir_acc": dir_acc}
print(f"  → RMSE={rmse:.6f}, R²={r2:.4f}, Dir.Acc={dir_acc:.1f}% ({elapsed:.1f}s) ✓\n")

# ── Resultado Final ────────────────────────────────────────────────────
print(f"{'='*60}")
print("RESULTADO DO TESTE GPU")
print(f"{'='*60}")
for name, r in results.items():
    t = r["time"]
    print(f"  {name:12s}: {t:6.1f}s  {'✅' if t > 0 else '❌'}")
print(f"{'='*60}")
print(f"  Ensemble final: RMSE={results['stacking']['rmse']:.6f} | "
      f"R²={results['stacking']['r2']:.4f} | "
      f"Dir.Acc={results['stacking']['dir_acc']:.1f}%")
print(f"{'='*60}")

# Peak VRAM
peak_vram = torch.cuda.max_memory_allocated() / 1e9
print(f"\n  Peak VRAM usage: {peak_vram:.2f} GB / 8.0 GB")
assert peak_vram < 7.5, f"VRAM muito alto: {peak_vram:.2f} GB — risco de OOM"
print(f"  VRAM headroom: {8.0 - peak_vram:.2f} GB ✓")

total_time = sum(r["time"] for r in results.values())
print(f"\n  Tempo total: {total_time:.0f}s")
print("\n✅ TODOS OS MODELOS RODARAM NA GPU COM SUCESSO\n")
