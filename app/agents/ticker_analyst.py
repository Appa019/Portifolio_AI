import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.services.market_data import (
    get_stock_dividends,
    get_stock_fundamentals,
    get_stock_history,
    get_stock_price,
)

logger = logging.getLogger(__name__)


class TickerAnalyst(BaseAgent):
    """Agente N3: análise profunda de 1 ação B3 individual."""

    def __init__(self, db: Session, ticker: str):
        self.ticker = ticker.upper()
        self.agent_name = f"ticker_analyst_{self.ticker}"
        super().__init__(db)

    def system_prompt(self) -> str:
        hoje = date.today().isoformat()
        return f"""Você é um analista especializado focado exclusivamente em {self.ticker}.
Data atual: {hoje}. Fuso horário: America/Sao_Paulo (BRT). B3 opera 10h-17h.

Seu papel:
- Realizar análise profunda e detalhada de {self.ticker}
- Avaliar fundamentos: P/L, P/VP, ROE, dividend yield, margens, crescimento
- Avaliar técnica: tendência, suportes, resistências, médias móveis, volume
- Pesquisar notícias recentes e cenário setorial

Regras de negócio do portfólio:
- Alocação alvo: 50% ações B3 / 20% crypto / 30% CDB liquidez diária
- Lock-up de 30 dias após compra — se ativo em carteira, verificar se lockup expirou antes de recomendar venda
- Perfil moderado: considerar risco-retorno adequado ao perfil conservador-moderado
- Usar o contexto do portfólio fornecido para contextualizar a recomendação (posição atual, peso, etc.)

Processo de análise:
1. Use web_search para buscar notícias recentes sobre {self.ticker} e seu setor
2. Use get_stock_price para o preço atual
3. Use get_stock_fundamentals para dados fundamentalistas completos
4. Use get_stock_history para análise técnica (tendência, suportes, resistências)
5. Use get_stock_dividends para histórico de proventos

Output obrigatório em JSON:
{{
  "ticker": "{self.ticker}",
  "nome": "nome da empresa",
  "setor": "setor da empresa",
  "tipo_recomendacao": "compra|manter|venda",
  "score_confianca": 0.0-1.0,
  "preco_atual": 0.0,
  "preco_alvo": 0.0,
  "justificativa": "razão detalhada da recomendação",
  "riscos": "riscos identificados",
  "fundamentos": {{
    "pl": 0.0,
    "pvp": 0.0,
    "roe_pct": 0.0,
    "dividend_yield_pct": 0.0,
    "margem_liquida_pct": 0.0,
    "avaliacao": "resumo fundamentalista"
  }},
  "tecnica": {{
    "tendencia": "alta|lateral|baixa",
    "suporte": 0.0,
    "resistencia": 0.0,
    "avaliacao": "resumo técnico"
  }},
  "noticias_relevantes": "resumo das notícias mais relevantes"
}}

Sempre responda em Português (BR). Seja profundo e fundamentado."""

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("high"),  # N3 análise profunda precisa mais contexto
            {
                "type": "function",
                "name": "get_stock_price",
                "description": "Busca preço atual de uma ação B3 pelo ticker (ex: PETR4, VALE3)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação (ex: PETR4)"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_stock_fundamentals",
                "description": "Busca dados fundamentalistas: P/L, P/VP, ROE, dividend yield, margens, market cap",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_stock_history",
                "description": "Busca histórico OHLCV de uma ação. Períodos: 1mo, 3mo, 6mo, 1y, 2y",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação"},
                        "period": {"type": "string", "description": "Período: 1mo, 3mo, 6mo, 1y, 2y"},
                    },
                    "required": ["ticker", "period"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_stock_dividends",
                "description": "Busca histórico de dividendos de uma ação B3",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker da ação"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def execute_function(self, name: str, args: dict) -> str:
        # Cada function call pode rodar em thread separada via _execute_parallel,
        # então cria session própria para evitar sqlite3.InterfaceError
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            return self._exec_with_db(name, args, db)
        finally:
            db.close()

    def _exec_with_db(self, name: str, args: dict, db) -> str:
        if name == "get_stock_price":
            data = get_stock_price(args["ticker"], db)
            return json.dumps(data or {"erro": "Dados não disponíveis"}, ensure_ascii=False, default=str)

        if name == "get_stock_fundamentals":
            data = get_stock_fundamentals(args["ticker"], db)
            return json.dumps(data or {"erro": "Dados não disponíveis"}, ensure_ascii=False, default=str)

        if name == "get_stock_history":
            data = get_stock_history(args["ticker"], args.get("period", "1y"), db)
            if not data:
                return json.dumps({"erro": "Dados não disponíveis"})
            if len(data) > 60:
                return json.dumps({
                    "total_registros": len(data),
                    "fechamentos": [d["fechamento"] for d in data],
                    "primeiro": data[0],
                    "ultimo": data[-1],
                }, ensure_ascii=False, default=str)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "get_stock_dividends":
            data = get_stock_dividends(args["ticker"], db)
            return json.dumps(data or [], ensure_ascii=False, default=str)

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def analyze(self, ticker: str, portfolio_context: str, job_id: str | None = None) -> str:
        """Executa análise profunda de um ticker B3 individual."""
        prompt = f"""Realize uma análise profunda e completa de {ticker}.

Contexto do portfólio:
{portfolio_context}

Instruções:
1. Pesquise notícias recentes sobre {ticker} e seu setor
2. Consulte preço atual e dados fundamentalistas
3. Analise histórico de preços (6 meses) para técnica
4. Verifique histórico de dividendos
5. Retorne sua análise no formato JSON especificado no system prompt"""

        result = self.call_model(prompt, job_id=job_id)
        self.save_analysis(
            tipo_analise="analise_ticker",
            input_resumo=f"Análise profunda {ticker}",
            output=result,
        )
        return result
