import json
import logging
import threading
import traceback
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.services.market_data import (
    get_crypto_history,
    get_macro_data,
    get_stock_history,
)

logger = logging.getLogger(__name__)

try:
    import torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False


def _calculate_stats(prices: list[float], rf_annual: float = 0.13) -> dict:
    """Calcula estatísticas básicas de uma série de preços.

    Args:
        prices: Lista de preços de fechamento em ordem cronológica.
        rf_annual: Taxa livre de risco anual (ex: 0.1375 para CDI 13.75%).
    """
    if not prices or len(prices) < 5:
        return {"erro": "Dados insuficientes"}

    arr = np.array(prices, dtype=float)
    returns = np.diff(arr) / arr[:-1]

    # Volatilidade anualizada
    vol_diaria = np.std(returns)
    vol_anual = vol_diaria * np.sqrt(252)

    # Retorno acumulado
    retorno_total = (arr[-1] / arr[0] - 1) * 100

    # Sharpe com taxa livre de risco dinâmica
    rf_diario = rf_annual / 252
    excess_returns = returns - rf_diario
    sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252) if np.std(excess_returns) > 0 else 0

    # Max Drawdown
    cummax = np.maximum.accumulate(arr)
    drawdowns = (arr - cummax) / cummax
    max_drawdown = float(np.min(drawdowns)) * 100

    return {
        "retorno_total_pct": round(retorno_total, 2),
        "volatilidade_anual_pct": round(vol_anual * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "preco_min": round(float(np.min(arr)), 2),
        "preco_max": round(float(np.max(arr)), 2),
        "preco_medio": round(float(np.mean(arr)), 2),
        "num_observacoes": len(prices),
        "taxa_livre_risco_anual": round(rf_annual, 4),
    }


class StatsAgent(BaseAgent):
    agent_name = "stats_agent"

    def __init__(self, db: Session):
        super().__init__(db)
        self._job_id: str | None = None
        self._pipelines: dict[str, "EnsemblePipeline"] = {}  # cache por ticker
        self._trained_tickers: set[str] = set()
        self._predicted_tickers: set[str] = set()
        self._ticker_lock = threading.Lock()

    def system_prompt(self) -> str:
        hoje = date.today().isoformat()
        return f"""Você é um analista quantitativo especializado em análise estatística de ativos financeiros.
Data atual: {hoje}. Fuso horário: America/Sao_Paulo (BRT).

Seu papel:
- Receber tickers de ações B3 e criptomoedas dos outros agentes
- Calcular métricas quantitativas: volatilidade, Sharpe, max drawdown, correlação, beta
- Fornecer análise estatística fundamentada para decisões de investimento

Regras de negócio:
- Lock-up de 30 dias — considerar ao avaliar horizonte temporal das recomendações
- Perfil moderado — classificar risco adequado ao perfil conservador-moderado
- Alocação alvo: 50% ações / 20% crypto / 30% CDB — ponderar risco relativo entre classes

CONTEXTO PERSISTENTE: Você tem acesso ao resumo da sua análise anterior (injetado automaticamente).
Use-o para manter continuidade entre análises semanais — identificar mudanças, validar ou revisar recomendações anteriores.

Processo:
1. Use get_stock_history e get_crypto_history para obter dados históricos
2. Use calculate_stats para computar métricas de cada ativo
3. Use get_macro_data para obter taxa livre de risco (CDI/Selic)
4. Use train_ensemble para treinar/carregar modelo preditivo de cada ticker
5. Use predict_ensemble para obter previsão de retorno D+1 de cada ticker
6. Sintetize os resultados em recomendação quantitativa

Output obrigatório em JSON:
{{
  "data_analise": "{hoje}",
  "taxa_livre_risco": 0.0,
  "ativos_analisados": [
    {{
      "ticker": "PETR4",
      "tipo": "acao|crypto",
      "retorno_total_pct": 0.0,
      "volatilidade_anual_pct": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "beta": 0.0,
      "classificacao_risco": "baixo|medio|alto",
      "recomendacao_quant": "favorável|neutro|desfavorável"
    }}
  ],
  "correlacoes_destaque": "observações sobre correlações entre ativos",
  "resumo_quant": "resumo da análise quantitativa"
}}

Sempre responda em Português (BR)."""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "get_stock_history",
                "description": "Busca histórico OHLCV de ação B3. Retorna lista de {data, abertura, maxima, minima, fechamento, volume}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação (ex: PETR4)"},
                        "period": {"type": "string", "description": "Período: 1mo, 3mo, 6mo, 1y"},
                    },
                    "required": ["ticker", "period"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_crypto_history",
                "description": "Busca histórico OHLCV de criptomoeda. IDs: bitcoin, ethereum, solana etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crypto_id": {"type": "string", "description": "ID da crypto (ex: bitcoin)"},
                        "period": {"type": "string", "description": "Período: 1mo, 3mo, 6mo, 1y"},
                    },
                    "required": ["crypto_id", "period"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_macro_data",
                "description": "Busca dados macroeconômicos: Selic, CDI, IPCA acumulado 12m, PTAX",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "calculate_stats",
                "description": "Calcula estatísticas de uma série de preços de fechamento: volatilidade, Sharpe, drawdown, retorno. "
                               "Obter risk_free_rate_annual de get_macro_data (CDI/Selic) antes de chamar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prices": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Lista de preços de fechamento em ordem cronológica",
                        },
                        "risk_free_rate_annual": {
                            "type": "number",
                            "description": "Taxa livre de risco anual (ex: 0.1375 para CDI 13.75%). Obter de get_macro_data.",
                        },
                    },
                    "required": ["prices", "risk_free_rate_annual"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "train_ensemble",
                "description": "Treina modelo ensemble (XGBoost+BiLSTM+TFT) para um ticker. "
                               "Se modelo recente existir (<7 dias), carrega do cache. Retorna métricas.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker (ex: PETR4, BTC-USD)"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "predict_ensemble",
                "description": "Gera previsão de retorno D+1 usando modelo ensemble treinado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker (ex: PETR4, BTC-USD)"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        # Funções de market_data podem rodar em threads paralelas via _execute_parallel,
        # então usam session própria para evitar sqlite3.InterfaceError
        if name in ("get_stock_history", "get_crypto_history", "get_macro_data"):
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                return self._exec_market_data(name, args, db)
            finally:
                db.close()
        return self._exec_market_data(name, args, None)

    def _exec_market_data(self, name: str, args: dict, db) -> str:
        if name == "get_stock_history":
            data = get_stock_history(args["ticker"], args.get("period", "1y"), db)
            if not data:
                return json.dumps({"erro": "Dados não disponíveis"})
            return json.dumps({
                "ticker": args["ticker"],
                "periodo": args.get("period", "1y"),
                "total_registros": len(data),
                "fechamentos": [d["fechamento"] for d in data],
                "primeiro": data[0],
                "ultimo": data[-1],
            }, ensure_ascii=False, default=str)

        if name == "get_crypto_history":
            data = get_crypto_history(args["crypto_id"], args.get("period", "1y"), db)
            if not data:
                return json.dumps({"erro": "Dados não disponíveis"})
            return json.dumps({
                "crypto_id": args["crypto_id"],
                "periodo": args.get("period", "1y"),
                "total_registros": len(data),
                "fechamentos": [d["fechamento"] for d in data],
                "primeiro": data[0],
                "ultimo": data[-1],
            }, ensure_ascii=False, default=str)

        if name == "get_macro_data":
            data = get_macro_data(db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "calculate_stats":
            stats = _calculate_stats(args["prices"], rf_annual=args.get("risk_free_rate_annual", 0.13))
            return json.dumps(stats, ensure_ascii=False, default=str)

        if name == "train_ensemble":
            return self._handle_train_ensemble(args["ticker"])

        if name == "predict_ensemble":
            return self._handle_predict_ensemble(args["ticker"])

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def _get_pipeline(self, ticker: str) -> "EnsemblePipeline":
        """Retorna pipeline do cache ou cria nova."""
        if ticker not in self._pipelines:
            from app.ensemble.pipeline import EnsemblePipeline
            self._pipelines[ticker] = EnsemblePipeline(checkpoint_dir="checkpoints")
        return self._pipelines[ticker]

    def _handle_train_ensemble(self, ticker: str) -> str:
        from app.ensemble import progress

        # G6: Deduplicação de treino (thread-safe)
        ticker = ticker.strip().upper()
        with self._ticker_lock:
            if ticker in self._trained_tickers:
                logger.info(f"[stats_agent] Treino duplicado ignorado: {ticker}")
                return json.dumps({"status": "cache", "ticker": ticker,
                    "mensagem": f"{ticker} já treinado nesta execução"})
            self._trained_tickers.add(ticker)

        try:
            pipeline = self._get_pipeline(ticker)

            if pipeline.is_model_fresh(ticker):
                pipeline.load(ticker)
                progress.emit(self._job_id, "model_loaded",
                    f"Modelo {ticker} carregado do cache", 85)
                return json.dumps({
                    "status": "cache",
                    "ticker": ticker,
                    "mensagem": f"Modelo {ticker} carregado do cache (<7 dias)"
                })

            progress.emit(self._job_id, "ensemble_train",
                f"Treinando ensemble para {ticker}...", 30)
            metrics = pipeline.train(ticker, job_id=self._job_id)
            pipeline.save(ticker)
            progress.emit(self._job_id, "model_saved",
                f"Modelo {ticker} salvo", 85)

            return json.dumps({
                "status": "trained",
                "ticker": ticker,
                "metrics": metrics
            }, default=str)

        except ValueError as e:
            logger.warning(f"Dados insuficientes para ensemble {ticker}: {e}")
            progress.emit(self._job_id, "ensemble_error",
                f"Ensemble {ticker}: dados insuficientes — {e}", 0)
            return json.dumps({
                "status": "erro", "tipo": "dados_insuficientes",
                "ticker": ticker, "erro": str(e)
            })
        except Exception as e:
            if _HAS_TORCH and isinstance(e, torch.cuda.OutOfMemoryError):
                logger.error(f"CUDA OOM treinando ensemble {ticker}: {e}")
                torch.cuda.empty_cache()
                progress.emit(self._job_id, "ensemble_error",
                    f"Ensemble {ticker}: VRAM insuficiente (OOM)", 0)
                return json.dumps({
                    "status": "erro", "tipo": "cuda_oom",
                    "ticker": ticker, "erro": f"VRAM insuficiente: {e}"
                })
            logger.error(f"Erro inesperado treinando ensemble {ticker}: {traceback.format_exc()}")
            progress.emit(self._job_id, "ensemble_error",
                f"Ensemble {ticker}: erro inesperado — {type(e).__name__}", 0)
            return json.dumps({
                "status": "erro", "tipo": "erro_inesperado",
                "ticker": ticker, "erro": str(e)
            })

    def _handle_predict_ensemble(self, ticker: str) -> str:
        from app.ensemble import progress

        # G6: Deduplicação de predict (thread-safe)
        ticker = ticker.strip().upper()
        with self._ticker_lock:
            if ticker in self._predicted_tickers:
                logger.info(f"[stats_agent] Predict duplicado ignorado: {ticker}")
                return json.dumps({"status": "cache", "ticker": ticker,
                    "mensagem": f"{ticker} já previsto nesta execução"})
            self._predicted_tickers.add(ticker)

        try:
            pipeline = self._get_pipeline(ticker)

            # Se pipeline não tem modelo carregado, tentar load do disco
            if not pipeline.xgb_model:
                if not pipeline.load(ticker):
                    return json.dumps({"erro": f"Modelo nao encontrado para {ticker}. Treine primeiro."})

            result = pipeline.predict(ticker)
            return json.dumps(result, default=str)

        except ValueError as e:
            logger.warning(f"Dados insuficientes para predict {ticker}: {e}")
            progress.emit(self._job_id, "ensemble_error",
                f"Predict {ticker}: dados insuficientes — {e}", 0)
            return json.dumps({
                "status": "erro", "tipo": "dados_insuficientes",
                "ticker": ticker, "erro": str(e)
            })
        except Exception as e:
            if _HAS_TORCH and isinstance(e, torch.cuda.OutOfMemoryError):
                logger.error(f"CUDA OOM predict ensemble {ticker}: {e}")
                torch.cuda.empty_cache()
                progress.emit(self._job_id, "ensemble_error",
                    f"Predict {ticker}: VRAM insuficiente (OOM)", 0)
                return json.dumps({
                    "status": "erro", "tipo": "cuda_oom",
                    "ticker": ticker, "erro": f"VRAM insuficiente: {e}"
                })
            logger.error(f"Erro inesperado predict ensemble {ticker}: {traceback.format_exc()}")
            progress.emit(self._job_id, "ensemble_error",
                f"Predict {ticker}: erro inesperado — {type(e).__name__}", 0)
            return json.dumps({
                "status": "erro", "tipo": "erro_inesperado",
                "ticker": ticker, "erro": str(e)
            })

    def analyze(self, tickers_context: str, job_id: str | None = None) -> str:
        """Executa análise estatística dos tickers fornecidos."""
        self._job_id = job_id
        # Clear per-execution caches to prevent VRAM leak across weekly runs
        with self._ticker_lock:
            self._trained_tickers.clear()
            self._predicted_tickers.clear()
        self._pipelines.clear()

        prompt = f"""Realize análise quantitativa dos seguintes ativos:

{tickers_context}

Instruções:
1. Busque dados macro (CDI/Selic) como taxa livre de risco
2. Para cada ticker de ação, busque histórico de 1 ano e calcule estatísticas
3. Para cada crypto, busque histórico de 1 ano e calcule estatísticas
4. Use train_ensemble para treinar/carregar modelo preditivo de cada ticker
5. Use predict_ensemble para obter previsão de retorno D+1
6. Avalie risco-retorno de cada ativo
7. Retorne sua análise no formato JSON especificado no system prompt"""

        result = self.call_model(prompt, job_id=job_id)
        self.save_analysis(
            tipo_analise="analise_stats",
            input_resumo=tickers_context[:300],
            output=result,
        )
        return result
