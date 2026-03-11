"""
Testes de logica multi-agentes — validacao de orquestracao, routing, deduplicacao.

Grupo 1: Unit tests (sem API calls, $0)
  - TestN3Logic: tool routing, history format
  - TestN2Logic: deduplicacao, validacao de tickers
  - TestOrchestratorHelpers: _validate_n2_output, _abbreviate_portfolio_context
  - TestDynamicNaming: agent_name dinamico, reasoning effort resolution

Grupo 2: Integration tests (gpt-5.1, reasoning=none, max_rounds=5)
  - TestIntegrationN3: agentic loop completo, context lifecycle
  - TestIntegrationN2: B3 delega a N3
  - TestIntegrationOrchestrator: consulta portfolio tools

Uso:
  python -m pytest tests/test_multiagent_logic.py -v                    # todos
  python -m pytest tests/test_multiagent_logic.py -v -m "not integration"  # so unit
  python -m pytest tests/test_multiagent_logic.py -v -m integration     # so integration
"""

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.db_models import AgentContext, CustoToken

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Constants ----------------------------------------------------------------

TEST_MODEL = "gpt-5.1"
MAX_ROUNDS = 5
_NONE_EFFORT = {k: "none" for k in settings.reasoning_effort}


# --- Fixtures -----------------------------------------------------------------

@pytest.fixture
def db_session():
    """SQLite em memoria para testes isolados (StaticPool para thread safety)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# --- Helpers ------------------------------------------------------------------

@contextmanager
def _patch_model_and_reasoning():
    """Patches BaseAgent.model, Orchestrator.model, e reasoning_effort para testes baratos."""
    from app.agents.base_agent import BaseAgent
    from app.agents.orchestrator import Orchestrator

    with (
        patch.object(BaseAgent, "model", TEST_MODEL),
        patch.object(Orchestrator, "model", TEST_MODEL),
        patch.object(settings, "reasoning_effort", _NONE_EFFORT),
    ):
        yield


def _require_api_key():
    """Skip test se OPENAI_API_KEY nao configurada."""
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY nao configurada")


# ==============================================================================
# Grupo 1: Unit Tests — Sem API calls ($0)
# ==============================================================================


class TestN3Logic:
    """Tool routing e formato de dados nos agentes N3."""

    def test_n3_tool_routing_stock(self, db_session):
        """TickerAnalyst.execute_function() roteia get_stock_price, fundamentals, dividends."""
        from app.agents.ticker_analyst import TickerAnalyst

        ta = TickerAnalyst(db_session, "PETR4")

        mock_price = {"ticker": "PETR4", "preco": 38.5, "moeda": "BRL"}
        mock_fundaments = {"ticker": "PETR4", "pl": 5.2, "pvp": 1.1}
        mock_dividends = [{"data": "2026-01-15", "valor": 0.75}]

        with (
            patch("app.agents.ticker_analyst.get_stock_price", return_value=mock_price),
            patch("app.agents.ticker_analyst.get_stock_fundamentals", return_value=mock_fundaments),
            patch("app.agents.ticker_analyst.get_stock_dividends", return_value=mock_dividends),
        ):
            # get_stock_price
            r1 = json.loads(ta.execute_function("get_stock_price", {"ticker": "PETR4"}))
            assert r1["preco"] == 38.5

            # get_stock_fundamentals
            r2 = json.loads(ta.execute_function("get_stock_fundamentals", {"ticker": "PETR4"}))
            assert r2["pl"] == 5.2

            # get_stock_dividends
            r3 = json.loads(ta.execute_function("get_stock_dividends", {"ticker": "PETR4"}))
            assert len(r3) == 1
            assert r3[0]["valor"] == 0.75

        # Funcao desconhecida retorna erro
        r4 = json.loads(ta.execute_function("unknown_tool", {}))
        assert "erro" in r4
        assert "desconhecida" in r4["erro"].lower()

        logger.info("PASS — N3 tool routing stock: 4 rotas verificadas")

    def test_n3_history_sends_all_closes(self, db_session):
        """get_stock_history com >60 registros retorna fechamentos[] completo, sem amostra."""
        from app.agents.ticker_analyst import TickerAnalyst

        ta = TickerAnalyst(db_session, "VALE3")

        fake_data = [
            {
                "data": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "abertura": 60 + i * 0.05,
                "maxima": 61 + i * 0.05,
                "minima": 59 + i * 0.05,
                "fechamento": 60.5 + i * 0.05,
                "volume": 500000,
            }
            for i in range(100)
        ]

        with patch("app.agents.ticker_analyst.get_stock_history", return_value=fake_data):
            result = json.loads(
                ta.execute_function("get_stock_history", {"ticker": "VALE3", "period": "1y"})
            )

        assert "fechamentos" in result
        assert len(result["fechamentos"]) == 100
        assert "amostra" not in result, "NAO deveria ter campo 'amostra' (sampling antigo)"
        assert result["total_registros"] == 100
        assert "primeiro" in result
        assert "ultimo" in result

        logger.info("PASS — N3 history: 100 fechamentos completos, sem amostra")

    def test_n3_crypto_tool_routing(self, db_session):
        """CryptoAnalyst.execute_function() roteia get_crypto_price e get_crypto_history."""
        from app.agents.crypto_analyst import CryptoAnalyst

        ca = CryptoAnalyst(db_session, "bitcoin")

        # get_crypto_price
        mock_price = {"id": "bitcoin", "preco_usd": 67000, "preco_brl": 340000}
        with patch("app.agents.crypto_analyst.get_crypto_price", return_value=mock_price):
            r1 = json.loads(ca.execute_function("get_crypto_price", {"crypto_id": "bitcoin"}))
            assert r1["preco_usd"] == 67000

        # get_crypto_history com 80 registros -> formato comprimido
        fake_data = [
            {
                "data": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "abertura": 50000 + i * 10,
                "maxima": 50100 + i * 10,
                "minima": 49900 + i * 10,
                "fechamento": 50050 + i * 10,
                "volume": 5000000,
            }
            for i in range(80)
        ]
        with patch("app.agents.crypto_analyst.get_crypto_history", return_value=fake_data):
            r2 = json.loads(
                ca.execute_function("get_crypto_history", {"crypto_id": "bitcoin", "period": "6mo"})
            )

        assert "fechamentos" in r2
        assert len(r2["fechamentos"]) == 80
        assert r2["total_registros"] == 80

        # Funcao desconhecida
        r3 = json.loads(ca.execute_function("unknown_fn", {}))
        assert "erro" in r3

        logger.info("PASS — N3 crypto tool routing: price + history + unknown verificados")


class TestN2Logic:
    """Deduplicacao e validacao nos agentes N2."""

    def test_b3_agent_deduplication(self, db_session):
        """_seen_tickers impede analise duplicada do mesmo ticker."""
        from app.agents.b3_agent import B3Agent

        b3 = B3Agent(db_session)

        with patch("app.agents.ticker_analyst.TickerAnalyst") as MockTA:
            mock_instance = MagicMock()
            mock_instance.analyze.return_value = '{"ticker":"PETR4","tipo_recomendacao":"compra"}'
            MockTA.return_value = mock_instance

            # Primeira chamada — deve criar N3
            r1 = b3._run_ticker_analyst("PETR4", "contexto teste")
            MockTA.assert_called_once()

            # Segunda chamada — bloqueada por deduplicacao
            r2 = json.loads(b3._run_ticker_analyst("PETR4", "contexto teste"))
            assert "erro" in r2
            assert "já foi analisado" in r2["erro"]
            # MockTA ainda chamado apenas 1 vez (sem segunda instanciacao)
            MockTA.assert_called_once()

        logger.info("PASS — B3 deduplication: segunda chamada bloqueada")

    def test_b3_agent_ticker_validation(self, db_session):
        """Regex _TICKER_RE rejeita tickers invalidos antes de criar N3."""
        from app.agents.b3_agent import B3Agent

        b3 = B3Agent(db_session)

        # Tickers invalidos (apos upper() pelo metodo)
        invalid_tickers = ["BTC", "INVALID_TICKER", "123", "AB12"]

        for ticker in invalid_tickers:
            result = json.loads(b3._run_ticker_analyst(ticker, "contexto"))
            assert "erro" in result, f"Ticker '{ticker}' deveria ser rejeitado"

        # Ticker valido NAO deve ser rejeitado
        with patch("app.agents.ticker_analyst.TickerAnalyst") as MockTA:
            mock_instance = MagicMock()
            mock_instance.analyze.return_value = '{"ok": true}'
            MockTA.return_value = mock_instance

            b3._run_ticker_analyst("WEGE3", "contexto")
            MockTA.assert_called_once()

        logger.info(f"PASS — B3 ticker validation: {len(invalid_tickers)} rejeitados, 1 aceito")

    def test_crypto_agent_deduplication(self, db_session):
        """_seen_cryptos impede analise duplicada."""
        from app.agents.crypto_agent import CryptoAgent

        ca = CryptoAgent(db_session)

        with patch("app.agents.crypto_analyst.CryptoAnalyst") as MockCA:
            mock_instance = MagicMock()
            mock_instance.analyze.return_value = '{"id":"bitcoin","tipo_recomendacao":"compra"}'
            MockCA.return_value = mock_instance

            # Primeira chamada — cria N3
            ca._run_crypto_analyst("bitcoin", "contexto teste")
            MockCA.assert_called_once()

            # Segunda chamada — deduplicacao
            r2 = json.loads(ca._run_crypto_analyst("bitcoin", "contexto teste"))
            assert "erro" in r2
            assert "já foi analisada" in r2["erro"]
            MockCA.assert_called_once()

        logger.info("PASS — Crypto deduplication: segunda chamada bloqueada")


class TestOrchestratorHelpers:
    """Helpers do Orchestrator: validacao de output N2 e abbreviation."""

    def test_validate_n2_output(self, db_session):
        """JSON valido passa inalterado; texto livre e wrapped."""
        from app.agents.orchestrator import Orchestrator

        orch = Orchestrator(db_session)

        # JSON valido — inalterado
        valid_json = '{"status":"ok","acoes":[]}'
        assert orch._validate_n2_output(valid_json, "b3_agent") == valid_json

        # Texto livre — wrapped em envelope JSON
        plain_text = "Analise do mercado B3: tendencia de alta no setor de commodities..."
        result = json.loads(orch._validate_n2_output(plain_text, "b3_agent"))
        assert result["status"] == "analise_texto"
        assert result["agente"] == "b3_agent"
        assert "commodities" in result["conteudo"]

        logger.info("PASS — _validate_n2_output: JSON inalterado, texto wrapped")

    def test_abbreviate_portfolio_context(self, db_session):
        """String curta inalterada; string >2000 chars truncada com marcador."""
        from app.agents.orchestrator import Orchestrator

        orch = Orchestrator(db_session)

        # Curta — inalterada
        short = "Portfolio: R$150k, 48% acoes, 22% crypto, 30% CDB"
        assert orch._abbreviate_portfolio_context(short) == short

        # Longa (>2000 chars) — truncada
        long_ctx = "A" * 3000
        result = orch._abbreviate_portfolio_context(long_ctx)
        assert len(result) < 3000
        assert result.startswith("A" * 100)
        assert "truncado" in result

        logger.info("PASS — _abbreviate_portfolio_context: curta inalterada, longa truncada")


class TestDynamicNaming:
    """Nomes dinamicos de agentes N3 e resolucao de reasoning effort."""

    def test_n3_dynamic_agent_naming(self, db_session):
        """TickerAnalyst e CryptoAnalyst geram agent_name correto."""
        from app.agents.crypto_analyst import CryptoAnalyst
        from app.agents.ticker_analyst import TickerAnalyst

        ta = TickerAnalyst(db_session, "PETR4")
        assert ta.agent_name == "ticker_analyst_PETR4"

        # lowercase input -> uppercase
        ta2 = TickerAnalyst(db_session, "vale3")
        assert ta2.agent_name == "ticker_analyst_VALE3"

        # uppercase input -> lowercase
        ca = CryptoAnalyst(db_session, "BITCOIN")
        assert ca.agent_name == "crypto_analyst_bitcoin"

        ca2 = CryptoAnalyst(db_session, "ethereum")
        assert ca2.agent_name == "crypto_analyst_ethereum"

        logger.info("PASS — N3 dynamic naming: ticker upper, crypto lower")

    def test_reasoning_effort_resolution(self):
        """N3 agent_names resolvem para chave base; N2 resolvem para si mesmos."""
        # Reproduz a logica de resolucao de call_model (linhas 92-97 de base_agent.py)
        test_cases = {
            "ticker_analyst_PETR4": "ticker_analyst",
            "ticker_analyst_VALE3": "ticker_analyst",
            "crypto_analyst_bitcoin": "crypto_analyst",
            "crypto_analyst_ethereum": "crypto_analyst",
            "b3_agent": "b3_agent",
            "crypto_agent": "crypto_agent",
            "stats_agent": "stats_agent",
            "orchestrator": "orchestrator",
        }

        for agent_name, expected_key in test_cases.items():
            agent_key = agent_name.split("_", 2)
            if (
                len(agent_key) >= 2
                and agent_key[0] in ("ticker", "crypto")
                and agent_key[1] == "analyst"
            ):
                effort_key = f"{agent_key[0]}_analyst"
            else:
                effort_key = agent_name

            assert effort_key == expected_key, f"{agent_name} -> {effort_key}, esperado {expected_key}"

        # Verificar que todas as chaves existem em settings.reasoning_effort
        required_keys = [
            "ticker_analyst", "crypto_analyst", "b3_agent",
            "crypto_agent", "stats_agent", "orchestrator",
        ]
        for key in required_keys:
            assert key in settings.reasoning_effort, f"Chave '{key}' nao encontrada em reasoning_effort"

        logger.info("PASS — Reasoning effort resolution: 8 casos + 6 chaves verificados")


# ==============================================================================
# Grupo 2: Integration Tests — gpt-5.1, reasoning=none, max_rounds=5
# ==============================================================================


@pytest.mark.integration
class TestIntegrationN3:
    """Testes de integracao N3: agentic loop real com gpt-5.1."""

    def test_n3_agentic_loop_ticker(self, db_session):
        """TickerAnalyst completa loop agentic: LLM chama tools mockados -> texto final."""
        _require_api_key()

        mock_price = {"ticker": "PETR4", "preco": 38.5, "moeda": "BRL", "variacao_dia_pct": 1.2}
        mock_fundaments = {"ticker": "PETR4", "pl": 5.2, "pvp": 1.1, "roe": 28.5, "dy": 8.3}
        mock_history = [
            {
                "data": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "fechamento": 36 + i * 0.02,
                "volume": 1000000,
            }
            for i in range(120)
        ]
        mock_dividends = [{"data": "2025-12-15", "tipo": "dividendo", "valor": 0.75}]

        with (
            _patch_model_and_reasoning(),
            patch("app.agents.ticker_analyst.get_stock_price", return_value=mock_price),
            patch("app.agents.ticker_analyst.get_stock_fundamentals", return_value=mock_fundaments),
            patch("app.agents.ticker_analyst.get_stock_history", return_value=mock_history),
            patch("app.agents.ticker_analyst.get_stock_dividends", return_value=mock_dividends),
            patch("app.services.token_cost.get_ptax", return_value=5.50),
        ):
            from app.agents.ticker_analyst import TickerAnalyst

            ta = TickerAnalyst(db_session, "PETR4")
            result = ta.call_model(
                "Analise PETR4 usando todas as ferramentas disponiveis. Responda em JSON.",
                max_rounds=MAX_ROUNDS,
            )

        assert result, "Deveria retornar texto"
        assert len(result) > 50, f"Resposta muito curta ({len(result)} chars)"

        # AgentContext criado no DB
        ctx = db_session.query(AgentContext).filter_by(agent_name="ticker_analyst_PETR4").first()
        assert ctx is not None, "AgentContext deveria ser criado"
        assert ctx.execution_count >= 1
        assert ctx.resumo_contexto is not None

        # CustoToken logado no DB
        custo = db_session.query(CustoToken).filter_by(agente="ticker_analyst_PETR4").first()
        assert custo is not None, "CustoToken deveria ser logado"
        assert custo.tokens_input > 0
        assert custo.tokens_output > 0

        logger.info(
            f"PASS — N3 agentic loop: {custo.tokens_input}in/{custo.tokens_output}out, "
            f"ctx.exec_count={ctx.execution_count}, resposta={len(result)} chars"
        )

    def test_n3_context_lifecycle(self, db_session):
        """Seed contexto anterior -> proxima execucao injeta -> execution_count incrementa."""
        _require_api_key()

        # Seed contexto anterior
        ctx = AgentContext(
            agent_name="ticker_analyst_VALE3",
            last_response_id="resp_old_vale3",
            last_execution=datetime.now() - timedelta(days=7),
            execution_count=2,
            resumo_contexto="Na analise anterior, recomendei COMPRA de VALE3 a R$62.",
        )
        db_session.add(ctx)
        db_session.commit()

        mock_price = {"ticker": "VALE3", "preco": 65.0, "moeda": "BRL"}

        with (
            _patch_model_and_reasoning(),
            patch("app.agents.ticker_analyst.get_stock_price", return_value=mock_price),
            patch("app.agents.ticker_analyst.get_stock_fundamentals", return_value={"ticker": "VALE3", "pl": 6.0}),
            patch("app.agents.ticker_analyst.get_stock_history", return_value=[]),
            patch("app.agents.ticker_analyst.get_stock_dividends", return_value=[]),
            patch("app.services.token_cost.get_ptax", return_value=5.50),
        ):
            from app.agents.ticker_analyst import TickerAnalyst

            ta = TickerAnalyst(db_session, "VALE3")
            result = ta.call_model(
                "Atualize sua analise de VALE3. Use get_stock_price para o preco atual.",
                max_rounds=MAX_ROUNDS,
            )

        assert result, "Deveria retornar texto"

        db_session.refresh(ctx)
        assert ctx.execution_count == 3, f"execution_count deveria ser 3, e {ctx.execution_count}"
        assert ctx.resumo_contexto != "Na analise anterior, recomendei COMPRA de VALE3 a R$62.", \
            "resumo_contexto deveria ter sido atualizado"

        logger.info(
            f"PASS — N3 context lifecycle: exec_count=2->3, "
            f"novo resumo={ctx.resumo_contexto[:80]}..."
        )


@pytest.mark.integration
class TestIntegrationN2:
    """Testes de integracao N2: B3Agent delega a N3."""

    def test_b3_delegates_to_n3(self, db_session):
        """B3Agent (gpt-5.1) chama analyze_stock_deep -> TickerAnalyst N3 mockado."""
        _require_api_key()

        fake_n3_result = json.dumps({
            "ticker": "PETR4",
            "nome": "Petrobras",
            "tipo_recomendacao": "compra",
            "score_confianca": 0.8,
            "preco_atual": 38.5,
            "preco_alvo": 45.0,
            "justificativa": "Forte geracao de caixa",
            "riscos": "Risco politico",
        })

        with (
            _patch_model_and_reasoning(),
            patch("app.agents.ticker_analyst.TickerAnalyst") as MockTA,
            patch("app.agents.b3_agent.search_tickers", return_value=[{"ticker": "PETR4", "name": "Petrobras"}]),
            patch("app.services.token_cost.get_ptax", return_value=5.50),
        ):
            mock_instance = MagicMock()
            mock_instance.analyze.return_value = fake_n3_result
            MockTA.return_value = mock_instance

            from app.agents.b3_agent import B3Agent

            b3 = B3Agent(db_session)
            result = b3.call_model(
                "Analise apenas PETR4 usando analyze_stock_deep com portfolio_context='Portfolio teste'. "
                "Chame analyze_stock_deep uma vez para PETR4 e retorne o resultado em JSON.",
                max_rounds=MAX_ROUNDS,
            )

        assert result, "Deveria retornar texto"

        # N3 deveria ter sido instanciado
        MockTA.assert_called()

        # CustoToken do B3 logado
        custo = db_session.query(CustoToken).filter_by(agente="b3_agent").first()
        assert custo is not None, "CustoToken do B3Agent deveria ser logado"
        assert custo.tokens_input > 0

        logger.info(
            f"PASS — B3 delegates to N3: MockTA called {MockTA.call_count}x, "
            f"custo={custo.tokens_input}in/{custo.tokens_output}out"
        )


@pytest.mark.integration
class TestIntegrationOrchestrator:
    """Testes de integracao do Orchestrator."""

    def test_orchestrator_calls_portfolio_tools(self, db_session):
        """Orchestrator (gpt-5.1) consulta get_portfolio_summary e get_portfolio_allocation."""
        _require_api_key()

        mock_summary = {
            "valor_total_brl": 150000,
            "rentabilidade_total_pct": 12.5,
            "total_ativos": 5,
        }
        mock_allocation = {
            "atual": {"acoes": 48, "crypto": 22, "cdb": 30},
            "alvo": {"acoes": 50, "crypto": 20, "cdb": 30},
            "desvio": {"acoes": -2, "crypto": 2, "cdb": 0},
        }

        with (
            _patch_model_and_reasoning(),
            patch("app.agents.orchestrator.get_portfolio_summary", return_value=mock_summary),
            patch("app.agents.orchestrator.get_portfolio_allocation", return_value=mock_allocation),
            patch("app.agents.orchestrator.get_portfolio_assets", return_value=[]),
            patch("app.agents.orchestrator.get_macro_data", return_value={"selic": 13.75, "cdi": 13.65}),
            patch("app.services.token_cost.get_ptax", return_value=5.50),
            patch("app.ensemble.progress.emit"),
        ):
            from app.agents.orchestrator import Orchestrator

            orch = Orchestrator(db_session)
            # Mock sub-agentes para nao executar analises reais
            orch._run_sub_agent = MagicMock(
                return_value='{"status":"ok","acoes_recomendadas":[]}'
            )

            result = orch.call_model(
                "Consulte o resumo do portfolio e a alocacao atual usando get_portfolio_summary "
                "e get_portfolio_allocation. Relate os dados obtidos. "
                "NAO execute sub-agentes (run_b3_analysis, run_crypto_analysis, run_stats_analysis).",
                max_rounds=MAX_ROUNDS,
            )

        assert result, "Deveria retornar texto"

        # CustoToken do orchestrator logado
        custo = db_session.query(CustoToken).filter_by(agente="orchestrator").first()
        assert custo is not None, "CustoToken do orchestrator deveria ser logado"
        assert custo.tokens_input > 0

        logger.info(
            f"PASS — Orchestrator portfolio tools: "
            f"custo={custo.tokens_input}in/{custo.tokens_output}out, "
            f"resposta={len(result)} chars"
        )


# --- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
