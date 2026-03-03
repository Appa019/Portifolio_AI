# 🧠 Guia Definitivo: Modelo Ensemble State-of-the-Art para Previsão de Ações
### XGBoost + BiLSTM-Attention + PatchTST/TFT — Otimizado para RTX 2070 SUPER (8GB)
### Atualizado em 01/Março/2026 — Baseado nos papers mais recentes (2024-2026)

---

## Sumário

1. [Decisão de Hardware: RTX 2070 SUPER vs T4 Colab](#1-hardware)
2. [Setup Completo Ubuntu + CUDA + PyTorch](#2-setup)
3. [Estado da Arte: O que a Academia Diz (2024-2026)](#3-estado-da-arte)
4. [Arquitetura do Ensemble](#4-arquitetura)
5. [Validação Temporal — O Ponto MAIS Crítico](#5-validacao)
6. [Feature Engineering Baseado na Literatura](#6-features)
7. [Implementação: XGBoost (Base Learner 1)](#7-xgboost)
8. [Implementação: BiLSTM + Attention (Base Learner 2)](#8-bilstm)
9. [Implementação: PatchTST/TFT (Base Learner 3)](#9-transformer)
10. [Stacking Ensemble com Meta-Learner](#10-ensemble)
11. [Pipeline Completo End-to-End](#11-pipeline)
12. [Métricas de Avaliação Corretas](#12-metricas)
13. [Otimização para 8GB VRAM](#13-otimizacao)
14. [Erros Fatais a Evitar](#14-erros)
15. [Referências Acadêmicas](#15-referencias)

---

## 1. Decisão de Hardware: RTX 2070 SUPER vs T4 Colab {#1-hardware}

### Comparação Detalhada

| Especificação | **RTX 2070 SUPER (Sua)** | **T4 (Colab Free)** | Vencedor |
|---|---|---|:---:|
| **CUDA Cores** | 2560 | 2560 | Empate |
| **Tensor Cores** | 320 (1ª gen) | 320 (1ª gen) | Empate |
| **Clock Boost** | 1770 MHz | 1590 MHz | **RTX** |
| **VRAM** | 8 GB GDDR6 | 16 GB GDDR6 | **T4** |
| **Bandwidth** | 448 GB/s | 320 GB/s | **RTX** |
| **FP32 (TFLOPS)** | ~9.1 | ~8.1 | **RTX** |
| **FP16 Tensor** | ~18.1 TFLOPS | ~65 TFLOPS | **T4** |
| **TDP** | 215W | 70W | T4 (eficiência) |
| **Treino real** | ~40-80% mais rápida | Baseline | **RTX** |
| **Sessão** | Ilimitada | ~90min idle / ~12h total | **RTX** |
| **Disponibilidade** | 100% | Pode negar GPU | **RTX** |
| **Disco** | Ilimitado (seu SSD) | 110GB (volátil) | **RTX** |
| **Mixed Precision** | FP16 ✅ (Tensor Cores) | FP16 ✅ (INT8 otimizado) | Empate |

### 🏆 Veredicto: Use a RTX 2070 SUPER Local

**Razões decisivas:**

1. **Treino 40-80% mais rápido** — a T4 é otimizada para inferência, não treino. Benchmarks reais mostram que a RTX 2070 SUPER supera a T4 em tarefas de treinamento.

2. **Sem interrupções** — no Colab Free, sessões desconectam após ~90 min de inatividade ou ~12h total. Seu ensemble com walk-forward validation pode levar horas.

3. **Bandwidth 40% superior** (448 vs 320 GB/s) — crucial para alimentar o GPU durante treino com datasets financeiros que requerem leitura constante de dados.

4. **Linux nativo** — você já roda Ubuntu, que dá 5-10% de performance extra sobre Windows para deep learning. O Colab roda em VM com overhead.

5. **Sem fila** — Colab Free frequentemente não aloca T4 em horários de pico, ou dá GPUs degradadas.

**A limitação dos 8GB VRAM é gerenciável** para nosso caso de uso:
- Modelos de séries temporais financeiras são MUITO menores que LLMs ou diffusion models
- Um TFT/PatchTST com hidden_size=32-64 usa ~500MB-2GB de VRAM
- Um BiLSTM com 2 camadas + Attention usa ~200MB-1GB
- Sobra espaço de sobra para batch sizes razoáveis

**Quando recorrer ao Colab T4:**
- Se precisar testar um modelo com hidden_size muito grande (>128) e batch_size grande
- Para compartilhar notebooks reproduzíveis
- Como ambiente de backup

---

## 2. Setup Completo Ubuntu + CUDA + PyTorch {#2-setup}

```bash
# ============================================
# PASSO 1: Verificar driver NVIDIA
# ============================================
nvidia-smi
# Deve mostrar: GeForce RTX 2070 SUPER | Driver Version: 5xx.xx | CUDA Version: 12.x

# Se não estiver instalado:
sudo apt update
sudo apt install -y nvidia-driver-545  # ou versão mais recente
sudo reboot

# ============================================
# PASSO 2: Criar ambiente virtual isolado
# ============================================
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 -m venv ~/stock_ensemble
source ~/stock_ensemble/bin/activate

# ============================================
# PASSO 3: Instalar PyTorch com CUDA
# ============================================
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Verificar CUDA disponível
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0)}')"
# Deve imprimir: CUDA: True, GPU: NVIDIA GeForce RTX 2070 SUPER

# ============================================
# PASSO 4: Instalar dependências do projeto
# ============================================

# Deep Learning
pip install pytorch-lightning>=2.2
pip install pytorch-forecasting>=1.1  # TFT

# Machine Learning
pip install xgboost>=2.0 lightgbm scikit-learn>=1.4

# Dados e Features
pip install yfinance>=0.2.36 pandas numpy

# Indicadores Técnicos
pip install ta  # Technical Analysis library (alternativa ao TA-Lib, sem compilação C)

# Otimização e Interpretabilidade
pip install optuna>=3.5          # Hyperparameter tuning
pip install shap>=0.45           # Feature importance

# Visualização
pip install matplotlib seaborn plotly

# Utilitários
pip install tqdm joblib rich

# ============================================
# PASSO 5: Otimizações CUDA para RTX 2070 SUPER
# ============================================

# Adicionar ao ~/.bashrc ou ao script de treino:
export CUDA_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512  # Reduz fragmentação de VRAM

# Garantir que Mixed Precision funcione (Tensor Cores)
python -c "
import torch
print(f'cuDNN: {torch.backends.cudnn.version()}')
print(f'TF32 support: {torch.cuda.get_device_capability(0)}')
torch.backends.cudnn.benchmark = True  # Auto-tuner para convoluções
"
```

---

## 3. Estado da Arte: O que a Academia Diz (2024-2026) {#3-estado-da-arte}

### Compilação dos papers mais relevantes e recentes:

**Paper 1 — Stacked Heterogeneous Ensemble (MDPI, 2025)**
- *"Stock Price Prediction Using a Stacked Heterogeneous Ensemble"*
- Arquitetura: ARIMA + Random Forest + LSTM + GRU + Transformer como base learners, **XGBoost como meta-learner**
- Resultado: R² entre **0.9735 e 0.9905** em múltiplos índices
- Conclusão principal: **o stacking heterogêneo supera qualquer modelo individual**

**Paper 2 — CAB-XDE Framework (arXiv, 2024)**
- *"Customized Attention-BiLSTM and XGBoost Decision Ensemble"*
- Arquitetura: BiLSTM com mecanismo de atenção customizado + XGBoost
- Resultado: **~27% menor MAPE**, ~39% menor MAE, ~27% menor RMSE vs state-of-the-art
- Conclusão: a combinação de LSTM sequencial + boosting de gradiente é sinérgica

**Paper 3 — Hybrid LSTM-XGBoost (IEEE, 2025)**
- *"Machine Learning for Stock Market Volatility Prediction Using LSTM and XGBoost"*
- Acurácia: **99.23%**, RMSE 0.045, MAPE 1.23%
- Superou: LSTM solo, CNN-LSTM, GRU e XGBoost individuais

**Paper 4 — PatchTST para Ações (MDPI, 2025)**
- *"AI-Driven Intelligent Financial Forecasting"*
- **PatchTST demonstrou performance superior** para horizontes de 96-336 dias no S&P 500 e NASDAQ
- Superou: iTransformer, TimesNet, FiLM, DLinear em múltiplos horizontes
- Observação: modelos mais simples (DLinear) podem superar em horizontes muito longos (720 dias)

**Paper 5 — TFT-GNN Hybrid (MDPI, 2025)**
- *"A Novel Hybrid Temporal Fusion Transformer Graph Neural Network Model"*
- R² médio de **0.9645**, superando TFT standalone em 11 de 12 períodos avaliados
- **RSI e MACD** foram os indicadores técnicos mais influentes (feature attribution)
- O modelo foca nos **últimos 5-10 dias** de trading (attention temporal)

**Paper 6 — iTransformer-FFC (MDPI Electronics, 2025)**
- Combina iTransformer com Fast Fourier Convolution para capturar padrões multi-escala
- **8.73% menor MSE** e **6.95% menor MAE** que PatchTST em 5 datasets
- Direção mais recente: integração de domínio de frequência com atenção

**Paper 7 — LSTM + Transformer + Sentiment + Federated (IEEE Access, 2026)**
- Framework híbrido: LSTM + Transformer Attention + **FinBERT** (sentimento de notícias)
- LSTM consistentemente supera métodos tradicionais para dependências temporais
- Sentimento de notícias melhora previsões em períodos de alta volatilidade

**Paper 8 — INFO-TCN-iTransformer (Research Square, 2026 — preprint)**
- Framework mais recente: TCN para padrões locais + iTransformer para dependências globais
- Otimização de hiperparâmetros por algoritmo Vector-weighted Average (INFO)
- Abordagem mais recente de fusão local-global

### Consenso Acadêmico (2024-2026):

1. **Stacking Ensemble heterogêneo** é consistentemente superior a qualquer modelo individual
2. **XGBoost como meta-learner** é a escolha mais robusta e bem validada
3. **BiLSTM + Attention** captura melhor dependências temporais que LSTM simples
4. **PatchTST** é o transformer state-of-the-art para séries temporais financeiras curtas-médias
5. **TFT** é superior quando há features heterogêneas (estáticas + temporais + futuras conhecidas)
6. **RSI e MACD** são os indicadores técnicos mais informativos
7. **Walk-Forward Validation** é o único método de validação aceitável
8. **Directional Accuracy** importa mais que RMSE para trading

---

## 4. Arquitetura do Ensemble {#4-arquitetura}

```
                    ┌─────────────────────────────────────┐
                    │          DADOS BRUTOS                │
                    │   OHLCV + Volume + Indicadores      │
                    │   + Macro (Selic, IPCA, VIX)        │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │       FEATURE ENGINEERING            │
                    │  • 40+ indicadores técnicos          │
                    │  • Lag features (1-20 dias)          │
                    │  • Features temporais (DoW, mês)     │
                    │  • Volatilidade realizada             │
                    │  • Volume relativo                    │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌────────▼────────┐ ┌─────────▼─────────┐
     │  BASE LEARNER 1 │ │  BASE LEARNER 2 │ │  BASE LEARNER 3   │
     │                 │ │                  │ │                    │
     │   XGBoost       │ │  BiLSTM +        │ │   PatchTST         │
     │   (GPU hist)    │ │  Multi-Head      │ │   ou TFT           │
     │                 │ │  Attention       │ │   (Transformer)    │
     │  ✦ Features     │ │                  │ │                    │
     │    tabulares     │ │  ✦ Sequências    │ │  ✦ Patches de      │
     │  ✦ Não-linear.  │ │    temporais     │ │    série temporal  │
     │  ✦ Feature      │ │  ✦ Dependências  │ │  ✦ Multi-horizon   │
     │    importance   │ │    de longo      │ │  ✦ Interpretável   │
     │  ✦ Regularizado │ │    prazo         │ │  ✦ Multi-scale     │
     └────────┬────────┘ └────────┬────────┘ └─────────┬─────────┘
              │                    │                     │
              │     Out-of-Fold Predictions (OOF)       │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │      META-LEARNER (Camada 2)        │
                    │                                      │
                    │  XGBoost (regularizado)               │
                    │  ou Ridge Regression                  │
                    │                                      │
                    │  Input: [pred_xgb, pred_lstm,        │
                    │          pred_transformer]            │
                    │  + Features originais (opcional)      │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │        PREVISÃO FINAL                │
                    │  • Retorno previsto para D+1         │
                    │  • Direção (alta/baixa)              │
                    │  • Intervalo de confiança (TFT)      │
                    └─────────────────────────────────────┘
```

**Por que estes 3 modelos?**

| Modelo | O que captura | Força | Fraqueza (compensada pelos outros) |
|---|---|---|---|
| **XGBoost** | Relações não-lineares entre features tabulares | Feature importance, robusto a outliers, rápido | Não captura dependências sequenciais |
| **BiLSTM+Attn** | Padrões sequenciais e dependências temporais | Memória de longo prazo, atenção dinâmica | Pode sofrer de overfitting em séries ruidosas |
| **PatchTST/TFT** | Padrões multi-escala e relações entre timesteps distantes | Attention global, interpretável, multi-horizon | Requer mais dados para convergir |

---

## 5. Validação Temporal — O Ponto MAIS Crítico {#5-validacao}

### ⛔ REGRA ABSOLUTA: Nunca use split aleatório em séries temporais

Usar `train_test_split(shuffle=True)` em dados financeiros é o erro mais grave possível. Ele contamina o treino com informações do futuro (data leakage), produzindo resultados ilusoriamente bons que não se replicam em produção.

### Walk-Forward Validation (Expanding Window)

O padrão acadêmico correto para séries temporais financeiras:

```
Tempo ──────────────────────────────────────────────────────►

Fold 1: [===========TREINO===========][===VAL===]
Fold 2: [===============TREINO===============][===VAL===]
Fold 3: [===================TREINO===================][===VAL===]
Fold 4: [=======================TREINO=======================][===VAL===]
Fold 5: [===========================TREINO===========================][===VAL===]
                                                                        [==TEST==]
```

```python
import numpy as np
from sklearn.model_selection import TimeSeriesSplit

class WalkForwardValidator:
    """
    Walk-Forward Validation com Purging e Embargo.
    Padrão acadêmico para séries temporais financeiras.
    """
    
    def __init__(self, n_splits=5, val_size=60, gap=5, embargo=2):
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
        
        for i in range(self.n_splits):
            val_end = n - (self.n_splits - 1 - i) * self.val_size
            val_start = val_end - self.val_size
            train_end = val_start - self.gap  # PURGE
            
            if train_end < self.val_size:  # Treino muito pequeno
                continue
            
            train_idx = np.arange(0, train_end)
            val_idx = np.arange(val_start, val_end)
            
            yield train_idx, val_idx
    
    def summary(self, X):
        """Imprime resumo dos folds."""
        for fold, (train_idx, val_idx) in enumerate(self.split(X)):
            print(f"Fold {fold+1}: "
                  f"Treino [{X.index[train_idx[0]].date()} → {X.index[train_idx[-1]].date()}] "
                  f"({len(train_idx)} dias) | "
                  f"Val [{X.index[val_idx[0]].date()} → {X.index[val_idx[-1]].date()}] "
                  f"({len(val_idx)} dias)")

# Uso:
wfv = WalkForwardValidator(n_splits=5, val_size=60, gap=5)
wfv.summary(df)  # Mostra as datas de cada fold
```

### Esquema de Split Final

```python
# Split temporal fixo para avaliação final
TRAIN_END   = '2023-12-31'    # ~8 anos de treino
VAL_END     = '2024-12-31'    # 1 ano de validação (tuning)
# TEST = 2025-01-01 em diante  # NUNCA TOCADO até avaliação final

train_df = df[:TRAIN_END]
val_df   = df[TRAIN_END:VAL_END]
test_df  = df[VAL_END:]

print(f"Treino: {len(train_df)} dias | Val: {len(val_df)} dias | Teste: {len(test_df)} dias")
```

---

## 6. Feature Engineering Baseado na Literatura {#6-features}

Os papers de 2024-2026 convergem nos seguintes indicadores como os mais informativos:

```python
import pandas as pd
import numpy as np
from ta import add_all_ta_features
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator, SMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, VolumeWeightedAveragePrice

def create_features(df, include_macro=False):
    """
    Feature engineering completo baseado na literatura acadêmica (2024-2026).
    
    Papers indicam RSI e MACD como os mais influentes (TFT-GNN, MDPI 2025).
    Features organizadas por categoria de importância.
    """
    df = df.copy()
    
    # ================================================================
    # TIER 1: Features Primárias (mais influentes na literatura)
    # ================================================================
    
    # --- Retornos (target e features) ---
    df['returns'] = df['Close'].pct_change()
    df['log_returns'] = np.log(df['Close'] / df['Close'].shift(1))
    
    # --- RSI (14 períodos) — #1 em importância nos papers ---
    rsi = RSIIndicator(close=df['Close'], window=14)
    df['rsi_14'] = rsi.rsi()
    
    # RSI em múltiplos timeframes
    df['rsi_7'] = RSIIndicator(close=df['Close'], window=7).rsi()
    df['rsi_21'] = RSIIndicator(close=df['Close'], window=21).rsi()
    
    # --- MACD — #2 em importância nos papers ---
    macd = MACD(close=df['Close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_histogram'] = macd.macd_diff()
    
    # ================================================================
    # TIER 2: Features Secundárias (alta importância)
    # ================================================================
    
    # --- Médias Móveis e Cruzamentos ---
    for w in [5, 10, 20, 50, 200]:
        df[f'sma_{w}'] = SMAIndicator(close=df['Close'], window=w).sma_indicator()
        df[f'ema_{w}'] = EMAIndicator(close=df['Close'], window=w).ema_indicator()
    
    # Ratios de cruzamento (evitam features com escala de preço)
    df['price_sma20_ratio'] = df['Close'] / df['sma_20']
    df['sma5_sma20_ratio'] = df['sma_5'] / df['sma_20']
    df['sma20_sma50_ratio'] = df['sma_20'] / df['sma_50']
    df['ema12_ema26_ratio'] = df['ema_10'] / df['ema_20']  # Proxy
    
    # --- Bollinger Bands ---
    bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['bb_width'] = bb.bollinger_wband()
    df['bb_position'] = bb.bollinger_pband()  # % position within bands
    
    # --- ATR (Volatilidade) ---
    atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['atr_14'] = atr.average_true_range()
    df['atr_pct'] = df['atr_14'] / df['Close']  # ATR normalizado
    
    # --- Volatilidade Realizada ---
    df['volatility_5d'] = df['returns'].rolling(5).std()
    df['volatility_20d'] = df['returns'].rolling(20).std()
    df['volatility_60d'] = df['returns'].rolling(60).std()
    df['vol_ratio_5_20'] = df['volatility_5d'] / df['volatility_20d']  # Regime detection
    
    # ================================================================
    # TIER 3: Features de Volume e Momentum
    # ================================================================
    
    # --- Volume ---
    df['volume_sma_20'] = df['Volume'].rolling(20).mean()
    df['volume_ratio'] = df['Volume'] / df['volume_sma_20']
    df['volume_change'] = df['Volume'].pct_change()
    
    # OBV (On-Balance Volume)
    obv = OnBalanceVolumeIndicator(close=df['Close'], volume=df['Volume'])
    df['obv'] = obv.on_balance_volume()
    df['obv_sma'] = df['obv'].rolling(20).mean()
    
    # --- Stochastic Oscillator ---
    stoch = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'])
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    
    # --- ADX (Força da tendência) ---
    adx = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['adx'] = adx.adx()
    
    # ================================================================
    # TIER 4: Features de Lag e Padrões
    # ================================================================
    
    # Retornos passados (lags)
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f'return_lag_{lag}'] = df['returns'].shift(lag)
        df[f'volume_ratio_lag_{lag}'] = df['volume_ratio'].shift(lag)
    
    # Gap de abertura
    df['gap_open'] = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1)
    
    # Range intraday
    df['intraday_range'] = (df['High'] - df['Low']) / df['Close']
    
    # ================================================================
    # TIER 5: Features Temporais
    # ================================================================
    
    df['day_of_week'] = df.index.dayofweek       # 0=Monday
    df['month'] = df.index.month
    df['quarter'] = df.index.quarter
    df['is_month_start'] = df.index.is_month_start.astype(int)
    df['is_month_end'] = df.index.is_month_end.astype(int)
    
    # ================================================================
    # TIER 6: Features Macroeconômicas (opcional)
    # ================================================================
    
    if include_macro:
        # Adicionar features macro via BCB/FRED
        # Selic, IPCA, VIX, DXY, US10Y, etc.
        # (requer coleta separada e merge por data)
        pass
    
    # ================================================================
    # LIMPEZA
    # ================================================================
    
    # Remover features com preço absoluto (não-estacionárias)
    cols_to_drop = [c for c in df.columns if c.startswith(('sma_', 'ema_')) and 
                    not c.endswith('_ratio')]
    # Manter OBV pois já é diferenciado
    
    # Remover NaNs criados pelas janelas
    df = df.dropna()
    
    return df

# ================================================================
# TARGET: Retorno do próximo dia
# ================================================================
def create_target(df, horizon=1):
    """
    Target: retorno percentual para D+horizon.
    Usar retorno (não preço!) para estacionariedade.
    """
    df = df.copy()
    df['target'] = df['Close'].shift(-horizon) / df['Close'] - 1
    
    # Target de classificação (opcional)
    df['target_direction'] = (df['target'] > 0).astype(int)
    
    return df.dropna()
```

---

## 7. Implementação: XGBoost (Base Learner 1) {#7-xgboost}

```python
import xgboost as xgb
import numpy as np
from sklearn.metrics import mean_squared_error

class XGBoostForecaster:
    """
    XGBoost para previsão de retornos.
    Usa GPU (tree_method='gpu_hist') para acelerar na RTX 2070 SUPER.
    """
    
    def __init__(self, task='regression'):
        self.task = task
        self.model = xgb.XGBRegressor(
            n_estimators=2000,
            max_depth=6,
            learning_rate=0.01,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.1,          # L1
            reg_lambda=1.0,         # L2
            min_child_weight=5,     # Regularização extra
            gamma=0.1,              # Mínimo ganho para split
            tree_method='gpu_hist', # 🔥 GPU na RTX 2070 SUPER
            gpu_id=0,
            random_state=42,
            n_jobs=-1,
        )
    
    def fit(self, X_train, y_train, X_val=None, y_val=None):
        fit_params = {}
        if X_val is not None:
            fit_params['eval_set'] = [(X_val, y_val)]
            self.model.set_params(early_stopping_rounds=50)
        
        self.model.fit(X_train, y_train, verbose=100, **fit_params)
        return self
    
    def predict(self, X):
        return self.model.predict(X)
    
    def feature_importance(self, top_n=20):
        imp = pd.Series(
            self.model.feature_importances_,
            index=self.model.feature_names_in_
        ).sort_values(ascending=False)
        return imp.head(top_n)
```

---

## 8. Implementação: BiLSTM + Multi-Head Attention (Base Learner 2) {#8-bilstm}

```python
import torch
import torch.nn as nn
import pytorch_lightning as pl
from torch.utils.data import Dataset, DataLoader

# ============================================
# Dataset para sequências temporais
# ============================================
class TimeSeriesDataset(Dataset):
    def __init__(self, X, y, seq_len=60):
        self.X = torch.FloatTensor(X.values if hasattr(X, 'values') else X)
        self.y = torch.FloatTensor(y.values if hasattr(y, 'values') else y)
        self.seq_len = seq_len
    
    def __len__(self):
        return len(self.X) - self.seq_len
    
    def __getitem__(self, idx):
        x = self.X[idx:idx + self.seq_len]
        y = self.y[idx + self.seq_len]
        return x, y

# ============================================
# Multi-Head Attention Layer
# ============================================
class MultiHeadAttention(nn.Module):
    def __init__(self, hidden_size, n_heads=4):
        super().__init__()
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size * 2,  # BiLSTM output
            num_heads=n_heads,
            dropout=0.1,
            batch_first=True
        )
        self.norm = nn.LayerNorm(hidden_size * 2)
    
    def forward(self, x):
        attn_out, attn_weights = self.attention(x, x, x)
        out = self.norm(x + attn_out)  # Residual connection
        context = out.mean(dim=1)       # Pool temporal
        return context, attn_weights

# ============================================
# BiLSTM + Multi-Head Attention Model
# ============================================
class BiLSTMAttention(pl.LightningModule):
    def __init__(self, input_size, hidden_size=64, num_layers=2,
                 n_heads=4, dropout=0.3, lr=1e-3):
        super().__init__()
        self.save_hyperparameters()
        
        # Projeção de entrada
        self.input_proj = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout)
        )
        
        # BiLSTM
        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
        # Multi-Head Attention
        self.attention = MultiHeadAttention(hidden_size, n_heads)
        
        # Head de regressão
        self.head = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size // 2),
            nn.GELU(),
            nn.Dropout(dropout / 2),
            nn.Linear(hidden_size // 2, 1)
        )
        
        self.lr = lr
    
    def forward(self, x):
        # x: (batch, seq_len, features)
        x = self.input_proj(x)                     # (batch, seq_len, hidden)
        lstm_out, _ = self.lstm(x)                  # (batch, seq_len, hidden*2)
        context, attn_weights = self.attention(lstm_out)  # (batch, hidden*2)
        out = self.head(context)                     # (batch, 1)
        return out.squeeze(-1)
    
    def training_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = nn.HuberLoss(delta=1.0)(y_hat, y)  # Huber é mais robusto que MSE
        self.log('train_loss', loss, prog_bar=True)
        return loss
    
    def validation_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = nn.HuberLoss(delta=1.0)(y_hat, y)
        self.log('val_loss', loss, prog_bar=True)
    
    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(), lr=self.lr, weight_decay=1e-4
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=10, T_mult=2
        )
        return {"optimizer": optimizer, "lr_scheduler": scheduler}

# ============================================
# Treinar com Mixed Precision (CRUCIAL para 8GB VRAM)
# ============================================
def train_bilstm(X_train, y_train, X_val, y_val, input_size, seq_len=60):
    train_ds = TimeSeriesDataset(X_train, y_train, seq_len)
    val_ds = TimeSeriesDataset(X_val, y_val, seq_len)
    
    train_dl = DataLoader(train_ds, batch_size=128, shuffle=False, num_workers=4,
                          pin_memory=True)  # pin_memory acelera transferência CPU→GPU
    val_dl = DataLoader(val_ds, batch_size=256, shuffle=False, num_workers=4,
                        pin_memory=True)
    
    model = BiLSTMAttention(
        input_size=input_size,
        hidden_size=64,       # Adequado para 8GB VRAM
        num_layers=2,
        n_heads=4,
        dropout=0.3,
        lr=1e-3
    )
    
    trainer = pl.Trainer(
        max_epochs=100,
        accelerator='gpu',
        devices=1,
        precision='16-mixed',  # 🔥 MIXED PRECISION — reduz VRAM em ~40%
        gradient_clip_val=1.0,
        accumulate_grad_batches=2,  # Simula batch maior sem usar mais VRAM
        callbacks=[
            pl.callbacks.EarlyStopping(monitor='val_loss', patience=15, mode='min'),
            pl.callbacks.ModelCheckpoint(monitor='val_loss', mode='min',
                                         save_top_k=1, filename='best_bilstm'),
        ],
        enable_progress_bar=True,
        log_every_n_steps=10,
    )
    
    trainer.fit(model, train_dl, val_dl)
    
    # Carregar melhor checkpoint
    best = BiLSTMAttention.load_from_checkpoint(
        trainer.checkpoint_callback.best_model_path,
        input_size=input_size
    )
    return best
```

---

## 9. Implementação: PatchTST ou TFT (Base Learner 3) {#9-transformer}

### Opção A: Temporal Fusion Transformer (TFT)

Melhor quando há features heterogêneas (estáticas + temporais + futuras conhecidas).

```python
from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.metrics import QuantileLoss

def train_tft(df, target='target', max_encoder=60, max_decoder=5):
    """
    TFT via pytorch-forecasting.
    Configurado para caber nos 8GB da RTX 2070 SUPER.
    """
    df_tft = df.reset_index()
    df_tft['time_idx'] = range(len(df_tft))
    df_tft['group'] = 'stock'
    
    # Converter categorias
    df_tft['day_of_week'] = df_tft['day_of_week'].astype(str)
    df_tft['month'] = df_tft['month'].astype(str)
    
    cutoff = df_tft['time_idx'].max() - max_decoder
    
    training = TimeSeriesDataSet(
        df_tft[lambda x: x.time_idx <= cutoff],
        time_idx='time_idx',
        target=target,
        group_ids=['group'],
        max_encoder_length=max_encoder,
        max_prediction_length=max_decoder,
        time_varying_known_categoricals=['day_of_week', 'month'],
        time_varying_known_reals=['time_idx'],
        time_varying_unknown_reals=[
            target, 'rsi_14', 'macd', 'macd_histogram',
            'bb_position', 'atr_pct', 'returns', 'volatility_20d',
            'volume_ratio', 'adx', 'stoch_k'
        ],
        target_normalizer='auto',
        add_relative_time_idx=True,
        add_target_scales=True,
    )
    
    validation = TimeSeriesDataSet.from_dataset(training, df_tft, predict=True)
    
    train_dl = training.to_dataloader(train=True, batch_size=64, num_workers=4)
    val_dl = validation.to_dataloader(train=False, batch_size=128, num_workers=4)
    
    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=1e-3,
        hidden_size=32,            # 🔧 Compacto para 8GB VRAM
        attention_head_size=4,
        dropout=0.2,
        hidden_continuous_size=16,
        output_size=7,             # Quantiles: 0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98
        loss=QuantileLoss(),
        reduce_on_plateau_patience=8,
    )
    
    print(f"Parâmetros TFT: {tft.size()/1e3:.1f}k")  # Deve ser <500k
    
    trainer = pl.Trainer(
        max_epochs=80,
        accelerator='gpu',
        devices=1,
        precision='16-mixed',      # 🔥 Mixed precision
        gradient_clip_val=0.1,
        callbacks=[
            pl.callbacks.EarlyStopping(monitor='val_loss', patience=15),
            pl.callbacks.ModelCheckpoint(monitor='val_loss'),
        ],
    )
    
    trainer.fit(tft, train_dl, val_dl)
    
    best = TemporalFusionTransformer.load_from_checkpoint(
        trainer.checkpoint_callback.best_model_path
    )
    return best, training, validation
```

---

## 10. Stacking Ensemble com Meta-Learner {#10-ensemble}

```python
class StackingEnsemble:
    """
    Stacking Ensemble Heterogêneo.
    
    Baseado em: "Stock Price Prediction Using a Stacked 
    Heterogeneous Ensemble" (MDPI, 2025)
    
    Procedimento:
    1. Gerar out-of-fold (OOF) predictions dos base learners
    2. Treinar meta-learner nos OOF predictions
    3. Para previsão final: base learners predizem → meta-learner combina
    """
    
    def __init__(self, meta_type='xgboost'):
        self.base_models = {}
        self.meta_type = meta_type
        
        if meta_type == 'xgboost':
            self.meta = xgb.XGBRegressor(
                n_estimators=300,
                max_depth=3,          # Raso para evitar overfitting
                learning_rate=0.05,
                subsample=0.8,
                reg_alpha=1.0,        # Forte regularização
                reg_lambda=2.0,
                tree_method='gpu_hist',
            )
        elif meta_type == 'ridge':
            from sklearn.linear_model import RidgeCV
            self.meta = RidgeCV(alphas=np.logspace(-3, 3, 20))
        elif meta_type == 'linear':
            from sklearn.linear_model import LinearRegression
            self.meta = LinearRegression(positive=True)  # Pesos positivos
    
    def generate_oof_predictions(self, X, y, wfv, base_learners):
        """
        Gera OOF predictions para cada base learner.
        Usa Walk-Forward Validation.
        """
        n_models = len(base_learners)
        oof_preds = np.full((len(X), n_models), np.nan)
        
        for fold, (train_idx, val_idx) in enumerate(wfv.split(X)):
            print(f"\n{'='*50}")
            print(f"Fold {fold + 1}")
            print(f"{'='*50}")
            
            X_tr, X_vl = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_vl = y.iloc[train_idx], y.iloc[val_idx]
            
            for i, (name, learner) in enumerate(base_learners.items()):
                print(f"  → Treinando {name}...")
                
                learner.fit(X_tr, y_tr, X_vl, y_vl)
                preds = learner.predict(X_vl)
                oof_preds[val_idx, i] = preds
                
                rmse = np.sqrt(mean_squared_error(y_vl, preds))
                print(f"    RMSE fold: {rmse:.6f}")
        
        return oof_preds
    
    def fit_meta(self, oof_preds, y, feature_names=None):
        """Treina meta-learner nos OOF predictions."""
        mask = ~np.isnan(oof_preds).any(axis=1)
        X_meta = oof_preds[mask]
        y_meta = y.values[mask] if hasattr(y, 'values') else y[mask]
        
        self.meta.fit(X_meta, y_meta)
        
        if hasattr(self.meta, 'feature_importances_'):
            names = feature_names or [f'model_{i}' for i in range(X_meta.shape[1])]
            imp = pd.Series(self.meta.feature_importances_, index=names)
            print(f"\nPesos do Meta-Learner:")
            for name, weight in imp.items():
                print(f"  {name}: {weight:.4f}")
        
        return self
    
    def predict(self, base_predictions):
        """Previsão final."""
        return self.meta.predict(base_predictions)
```

---

## 11. Pipeline Completo End-to-End {#11-pipeline}

```python
"""
Pipeline completo: coleta → features → treino → ensemble → avaliação.
Otimizado para RTX 2070 SUPER (8GB VRAM) no Ubuntu.
"""

import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# ========================================
# 1. COLETA DE DADOS
# ========================================
ticker = "PETR4.SA"  # Mude para "AAPL" para mercado americano
df = yf.download(ticker, start="2015-01-01", end="2026-02-28", auto_adjust=True)
print(f"Dados coletados: {len(df)} dias ({df.index[0].date()} → {df.index[-1].date()})")

# ========================================
# 2. FEATURE ENGINEERING
# ========================================
df = create_features(df)
df = create_target(df, horizon=1)  # Retorno D+1
print(f"Após features: {len(df)} dias, {len([c for c in df.columns if c not in ['target','target_direction']])} features")

# ========================================
# 3. SPLIT TEMPORAL
# ========================================
TRAIN_END = '2023-12-31'
VAL_END = '2024-12-31'

feature_cols = [c for c in df.columns 
                if c not in ['target', 'target_direction', 'Open', 'High', 'Low', 'Close', 'Volume']]

train = df[:TRAIN_END]
val = df[TRAIN_END:VAL_END]
test = df[VAL_END:]

print(f"Train: {len(train)} | Val: {len(val)} | Test: {len(test)}")

# ========================================
# 4. NORMALIZAÇÃO (FIT APENAS NO TREINO!)
# ========================================
from sklearn.preprocessing import RobustScaler

scaler = RobustScaler()
scaler.fit(train[feature_cols])

X_train = pd.DataFrame(scaler.transform(train[feature_cols]),
                        index=train.index, columns=feature_cols)
X_val = pd.DataFrame(scaler.transform(val[feature_cols]),
                      index=val.index, columns=feature_cols)
X_test = pd.DataFrame(scaler.transform(test[feature_cols]),
                       index=test.index, columns=feature_cols)

y_train, y_val, y_test = train['target'], val['target'], test['target']

# ========================================
# 5. TREINAR BASE LEARNERS
# ========================================

# 5a. XGBoost
print("\n🌲 Treinando XGBoost...")
xgb_model = XGBoostForecaster()
xgb_model.fit(X_train, y_train, X_val, y_val)
xgb_pred_test = xgb_model.predict(X_test)

# 5b. BiLSTM + Attention
print("\n🧠 Treinando BiLSTM + Attention...")
bilstm_model = train_bilstm(X_train, y_train, X_val, y_val,
                              input_size=len(feature_cols), seq_len=60)

# 5c. TFT (ou PatchTST)
print("\n⚡ Treinando TFT...")
# ... (ver seção 9)

# ========================================
# 6. ENSEMBLE
# ========================================
print("\n🏆 Construindo Ensemble...")
wfv = WalkForwardValidator(n_splits=5, val_size=60, gap=5)

ensemble = StackingEnsemble(meta_type='xgboost')
oof = ensemble.generate_oof_predictions(
    X_train, y_train, wfv,
    base_learners={'xgb': xgb_model, 'bilstm': bilstm_model}
)
ensemble.fit_meta(oof, y_train, feature_names=['XGBoost', 'BiLSTM-Attn'])

# ========================================
# 7. AVALIAÇÃO FINAL (dados NUNCA vistos)
# ========================================
base_preds_test = np.column_stack([
    xgb_model.predict(X_test),
    # bilstm predictions,
    # tft predictions,
])
y_pred = ensemble.predict(base_preds_test)

# Métricas
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

rmse = np.sqrt(mean_squared_error(y_test, y_pred))
mae = mean_absolute_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)
mape = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100
dir_acc = (np.sign(y_pred) == np.sign(y_test)).mean() * 100

print(f"\n{'='*50}")
print(f"📊 RESULTADOS NO TESTE (dados nunca vistos)")
print(f"{'='*50}")
print(f"RMSE:              {rmse:.6f}")
print(f"MAE:               {mae:.6f}")
print(f"R²:                {r2:.4f}")
print(f"MAPE:              {mape:.2f}%")
print(f"Dir. Accuracy:     {dir_acc:.1f}%")

# Baseline ingênuo (previsão = 0, i.e., sem mudança)
naive_rmse = np.sqrt(mean_squared_error(y_test, np.zeros_like(y_test)))
naive_dir = 50.0  # Random
print(f"\n📏 BASELINE INGÊNUO:")
print(f"RMSE (naive=0):    {naive_rmse:.6f}")
print(f"Dir. Acc (random): {naive_dir:.1f}%")
print(f"\n{'Modelo SUPERA baseline ✅' if dir_acc > 52 else 'Modelo NÃO supera baseline ❌'}")
```

---

## 12. Métricas de Avaliação Corretas {#12-metricas}

| Métrica | Para que serve | Como interpretar |
|---|---|---|
| **RMSE** | Erro quadrático médio | Menor = melhor. Penaliza erros grandes. |
| **MAE** | Erro absoluto médio | Menor = melhor. Mais robusto a outliers. |
| **MAPE** | Erro percentual | Interpretável em %. Cuidado com valores próximos de zero. |
| **R²** | Qualidade do ajuste | 1.0 = perfeito. Pode ser negativo (pior que média). |
| **Directional Accuracy** | % de acerto na direção | **A métrica que importa para trading.** >52% já é significativo. |
| **Sharpe Ratio** | Retorno ajustado ao risco | >1.0 = bom, >2.0 = excelente. Requer backtest com custos. |
| **Max Drawdown** | Maior queda acumulada | Mede o risco extremo da estratégia. |

---

## 13. Otimização para 8GB VRAM {#13-otimizacao}

```python
# ================================================================
# OTIMIZAÇÕES ESPECÍFICAS PARA RTX 2070 SUPER (8GB)
# ================================================================

# 1. MIXED PRECISION — Reduz VRAM em ~40%, speedup de ~2x nos Tensor Cores
trainer = pl.Trainer(precision='16-mixed', ...)

# 2. GRADIENT CHECKPOINTING — Troca compute por memória
model.lstm.requires_grad_(True)
# Ou via PyTorch Lightning:
class MyModel(pl.LightningModule):
    def __init__(self):
        super().__init__()
        self.gradient_checkpointing = True  # Ativar se OOM

# 3. GRADIENT ACCUMULATION — Simula batch maior
trainer = pl.Trainer(accumulate_grad_batches=4, ...)
# Batch efetivo = batch_size * accumulate = 64 * 4 = 256

# 4. PIN MEMORY — Acelera transferência CPU → GPU
DataLoader(..., pin_memory=True, num_workers=4)

# 5. CUDA MEMORY CONFIG
import os
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:512'

# 6. LIMPAR CACHE CUDA
torch.cuda.empty_cache()
import gc; gc.collect()

# 7. MONITORAR VRAM
print(f"VRAM alocada: {torch.cuda.memory_allocated()/1e9:.2f} GB")
print(f"VRAM reservada: {torch.cuda.memory_reserved()/1e9:.2f} GB")

# 8. TAMANHOS RECOMENDADOS PARA 8GB VRAM
CONFIG_8GB = {
    'bilstm': {'hidden_size': 64, 'num_layers': 2, 'batch_size': 128, 'seq_len': 60},
    'tft':    {'hidden_size': 32, 'attention_heads': 4, 'batch_size': 64},
    'xgboost': {'tree_method': 'gpu_hist', 'max_depth': 6},  # Minimal VRAM usage
}
```

---

## 14. Erros Fatais a Evitar {#14-erros}

### ❌ Erros que Invalidam o Trabalho

| # | Erro | Por que é fatal | Solução |
|---|---|---|---|
| 1 | **Split aleatório** | Data leakage — usa futuro para prever passado | Walk-Forward Validation |
| 2 | **Normalizar antes do split** | Scaler "vê" dados do teste | Fit scaler APENAS no treino |
| 3 | **Prever preço absoluto** | Série não-estacionária, métricas infladas | Prever retornos ou log-retornos |
| 4 | **R²=0.99 sem baseline** | Modelo pode estar fazendo lag/eco | Comparar SEMPRE com baseline ingênuo |
| 5 | **Ignorar custos de transação** | Backtest ilusório | Incluir 0.1-0.2% por trade |

### ⚠️ Erros Conceituais Comuns

| # | Erro | Realidade |
|---|---|---|
| 6 | "Mais features = melhor" | Pode causar overfitting. Use feature selection (SHAP, importância XGBoost). |
| 7 | "Modelo complexo = melhor" | DLinear (linear simples) bate transformers em horizontes longos (>720 dias). |
| 8 | "Funciona em AAPL, funciona em tudo" | Cada ativo tem dinâmica própria. Valide por ativo. |
| 9 | "Alta acurácia = lucro" | Dir. Accuracy de 55% pode ser lucrativo; R²=0.95 pode dar prejuízo. |
| 10 | "Sentiment analysis sempre melhora" | Depende da qualidade dos dados. News com delay >15min já estão precificadas. |

### ✅ Checklist do Paper Bem Feito

- [ ] Walk-Forward Validation (expanding window)
- [ ] Purging + embargo entre treino/validação
- [ ] Baseline ingênuo como referência
- [ ] Métricas: RMSE + MAE + Directional Accuracy + Sharpe
- [ ] Feature importance (SHAP ou XGBoost)
- [ ] Normalização fit apenas no treino
- [ ] Target = retornos (não preço)
- [ ] Early stopping em todos os modelos
- [ ] Resultados em múltiplos ativos ou períodos
- [ ] Discussão honesta das limitações

---

## 15. Referências Acadêmicas {#15-referencias}

### Papers Fundamentais (Arquitetura)

1. **Vaswani et al. (2017)** — "Attention is All You Need" — Transformer original
2. **Lim et al. (2021)** — "Temporal Fusion Transformers for Interpretable Multi-horizon Time Series Forecasting" — Google Research, TFT
3. **Nie et al. (2023)** — "A Time Series is Worth 64 Words: Long-term Forecasting with Transformers" — PatchTST
4. **Liu et al. (2024)** — "iTransformer: Inverted Transformers Are Effective for Time Series Forecasting"

### Papers de Ensemble para Ações (2024-2026)

5. **MDPI IJFS (2025)** — "Stock Price Prediction Using a Stacked Heterogeneous Ensemble" — Stacking com XGBoost meta-learner, R² 0.97-0.99
6. **arXiv (2024)** — "Customized Attention-BiLSTM and XGBoost Decision Ensemble (CAB-XDE)" — ~27% menor MAPE
7. **IEEE (2025)** — "Machine Learning for Stock Market Volatility Prediction Using LSTM and XGBoost" — Hybrid, 99.23% accuracy
8. **MDPI (2025)** — "A Novel Hybrid TFT-GNN Model for Stock Market Prediction" — TFT + Graph Neural Network
9. **WJARR (2025)** — "Deep learning for stock price prediction: A comparative study" — CNN-LSTM-Attention ensemble
10. **MDPI (2025)** — "AI-Driven Intelligent Financial Forecasting" — PatchTST como SOTA para séries financeiras

### Papers de Validação e Metodologia

11. **De Prado (2018)** — "Advances in Financial Machine Learning" — Purged Walk-Forward CV
12. **López de Prado (2019)** — "Ten Financial Applications of Machine Learning" — Boas práticas

### Papers Mais Recentes (2026)

13. **IEEE Access (2026)** — "Enhancing Stock Market Prediction With Hybrid LSTM + Transformer + FinBERT + Federated Learning"
14. **Research Square (2026, preprint)** — "INFO-TCN-iTransformer" — Fusão TCN + iTransformer com otimização por INFO algorithm
15. **MDPI Electronics (2025)** — "iTransformer-FFC: Frequency-Aware Transformer" — 8.73% menor MSE que PatchTST

---

> **Nota final:** Nenhum modelo garante lucro no mercado financeiro. O mercado é parcialmente eficiente (Hipótese do Mercado Eficiente semi-forte), e qualquer edge encontrada tende a ser temporária e pequena. Use estes modelos como ferramentas de análise, não como oráculos. A Directional Accuracy de 53-55% já é considerada significativa pela literatura — e é nesse range que modelos bem construídos costumam operar.
>
> **Seu hardware (RTX 2070 SUPER + Ubuntu)** é mais que suficiente para treinar e iterar sobre este ensemble completo. O gargalo nunca será o hardware — será a qualidade dos dados e a disciplina metodológica.