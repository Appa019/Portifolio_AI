"""
Teste E2E Multi-Agentes — Chamadas REAIS OpenAI + Yahoo Scraping REAL.

Valida a hierarquia completa de multi-agentes end-to-end:
  - Fase 1: Scraping real (preços, histórico, fundamentos) via Yahoo/BCB
  - Fase 2: Agentes N3 reais (TickerAnalyst, CryptoAnalyst) com gpt-4.1-mini
  - Fase 3: Agentes N2 reais (B3Agent, CryptoAgent) com gpt-4.1-mini → delegam a N3
  - Fase 4: StatsAgent com calculate_stats real
  - Fase 5: Verificar custos_tokens, analises_ia, agent_contexts no DB
  - Fase 6: Backend HTTP — uvicorn + endpoints /custos, /analises, /portfolio, /health

Uso:
  source .venv/bin/activate
  python -m pytest tests/test_e2e_multiagent.py -v

Custo estimado: ~$0.01-0.03 (gpt-4.1-mini, poucas chamadas)
Tempo estimado: ~2-5 min (scraping + OpenAI rounds)
"""

import json
import logging
import os
import socket
import subprocess
import sys
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.db_models import AgentContext, AnaliseIA, CustoToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── Fixtures ────────────────────────────────────────────────────────────────

TEST_MODEL = "gpt-4.1-mini"


@pytest.fixture(scope="module")
def db_engine():
    """SQLite em memória compartilhado — StaticPool garante conexão única."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Importar todos os modelos para garantir registro no Base.metadata
    import app.models.db_models  # noqa: F401
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Session isolada por teste (rollback no teardown)."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def shared_session(db_engine):
    """Session compartilhada para fases que precisam ver dados de fases anteriores."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


def _patch_model():
    """Context manager que troca modelos para gpt-4.1-mini."""
    return patch.multiple(
        settings,
        modelo_orquestrador=TEST_MODEL,
        modelo_subagente=TEST_MODEL,
    )


def _require_api_key():
    """Skip se OPENAI_API_KEY não está configurada."""
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY não configurada")


# ─── Fase 1: Scraping Real ──────────────────────────────────────────────────

class TestFase1ScrapingReal:
    """Scraping real sem mocks — dados de mercado vindos do Yahoo Finance e BCB."""

    def test_stock_price_petr4(self, db_session):
        """Busca preço atual de PETR4 via Yahoo scraper."""
        from app.services.market_data import get_stock_price

        data = get_stock_price("PETR4", db_session)
        assert data is not None, "get_stock_price('PETR4') retornou None"
        assert "preco" in data or "preco_atual" in data or "regularMarketPrice" in data, \
            f"Campos inesperados no retorno: {list(data.keys())}"

        preco = data.get("preco") or data.get("preco_atual") or data.get("regularMarketPrice", 0)
        assert isinstance(preco, (int, float)), f"Preço deveria ser numérico, got {type(preco)}"
        assert preco > 0, f"Preço PETR4 deveria ser positivo, got {preco}"

        logger.info(f"F1.1 PASS — PETR4 preço: R${preco}")

    def test_crypto_price_bitcoin(self, db_session):
        """Busca preço atual de bitcoin via Yahoo scraper."""
        from app.services.market_data import get_crypto_price

        data = get_crypto_price("bitcoin", db_session)
        assert data is not None, "get_crypto_price('bitcoin') retornou None"

        preco = data.get("preco_usd") or data.get("preco") or data.get("regularMarketPrice", 0)
        assert isinstance(preco, (int, float)), f"Preço deveria ser numérico, got {type(preco)}"
        assert preco > 1000, f"Bitcoin deveria custar >$1000, got ${preco}"

        logger.info(f"F1.2 PASS — Bitcoin preço: ${preco}")

    def test_stock_history_petr4(self, db_session):
        """Busca histórico 3mo de PETR4."""
        from app.services.market_data import get_stock_history

        data = get_stock_history("PETR4", "3mo", db_session)
        assert data is not None, "get_stock_history retornou None"
        assert isinstance(data, list), f"Esperava lista, got {type(data)}"
        assert len(data) >= 30, f"Esperava >=30 registros para 3mo, got {len(data)}"

        first = data[0]
        assert "fechamento" in first, f"Registro sem 'fechamento': {list(first.keys())}"
        assert first["fechamento"] > 0

        logger.info(f"F1.3 PASS — PETR4 histórico 3mo: {len(data)} registros")

    def test_crypto_history_bitcoin(self, db_session):
        """Busca histórico 3mo de bitcoin."""
        from app.services.market_data import get_crypto_history

        data = get_crypto_history("bitcoin", "3mo", db_session)
        assert data is not None, "get_crypto_history retornou None"
        assert isinstance(data, list)
        assert len(data) >= 30, f"Esperava >=30 registros, got {len(data)}"

        logger.info(f"F1.4 PASS — Bitcoin histórico 3mo: {len(data)} registros")

    def test_stock_fundamentals_petr4(self, db_session):
        """Busca fundamentos de PETR4."""
        from app.services.market_data import get_stock_fundamentals

        data = get_stock_fundamentals("PETR4", db_session)
        assert data is not None, "get_stock_fundamentals retornou None"
        assert isinstance(data, dict)
        logger.info(f"F1.5 PASS — PETR4 fundamentos: {list(data.keys())[:8]}")

    def test_macro_data(self, db_session):
        """Busca dados macro (Selic, CDI, IPCA, PTAX) via BCB."""
        from app.services.market_data import get_macro_data

        data = get_macro_data(db_session)
        assert data is not None, "get_macro_data retornou None"
        assert isinstance(data, dict)

        # Pelo menos Selic ou CDI deve estar presente
        has_rates = any(k in data for k in ("selic", "cdi", "taxa_selic"))
        assert has_rates, f"Dados macro sem taxas de juros: {list(data.keys())}"

        logger.info(f"F1.6 PASS — Dados macro: {data}")


# ─── Fase 2: Agentes N3 Reais ───────────────────────────────────────────────

class TestFase2AgentesN3:
    """Agentes N3 (TickerAnalyst, CryptoAnalyst) com chamadas reais OpenAI + scraping."""

    def test_ticker_analyst_petr4(self, db_session):
        """TickerAnalyst analisa PETR4 com gpt-4.1-mini + scraping real."""
        _require_api_key()
        from app.agents.ticker_analyst import TickerAnalyst

        with _patch_model():
            analyst = TickerAnalyst(db_session, "PETR4")
            # Limitar rounds para economizar tokens
            result = analyst.call_model(
                "Analise PETR4 brevemente. Use get_stock_price e get_stock_history(PETR4, 3mo). "
                "Responda com um JSON resumido.",
                max_rounds=3,
            )

        assert result, "TickerAnalyst retornou resultado vazio"
        assert len(result) > 50, f"Resultado muito curto ({len(result)} chars)"

        # Verificar custos logados
        custos = db_session.query(CustoToken).filter(
            CustoToken.agente == "ticker_analyst_PETR4"
        ).all()
        assert len(custos) >= 1, "Custos não foram logados para ticker_analyst_PETR4"

        total_input = sum(c.tokens_input for c in custos)
        total_output = sum(c.tokens_output for c in custos)

        logger.info(
            f"F2.1 PASS — TickerAnalyst PETR4: {len(result)} chars, "
            f"{total_input} in / {total_output} out tokens, "
            f"{len(custos)} cost entries"
        )

    def test_crypto_analyst_bitcoin(self, db_session):
        """CryptoAnalyst analisa bitcoin com gpt-4.1-mini + scraping real."""
        _require_api_key()
        from app.agents.crypto_analyst import CryptoAnalyst

        with _patch_model():
            analyst = CryptoAnalyst(db_session, "bitcoin")
            result = analyst.call_model(
                "Analise bitcoin brevemente. Use get_crypto_price e get_crypto_history(bitcoin, 3mo). "
                "Responda com um JSON resumido.",
                max_rounds=3,
            )

        assert result, "CryptoAnalyst retornou resultado vazio"
        assert len(result) > 50, f"Resultado muito curto ({len(result)} chars)"

        custos = db_session.query(CustoToken).filter(
            CustoToken.agente == "crypto_analyst_bitcoin"
        ).all()
        assert len(custos) >= 1, "Custos não foram logados para crypto_analyst_bitcoin"

        logger.info(f"F2.2 PASS — CryptoAnalyst bitcoin: {len(result)} chars")

    def test_n3_context_persisted(self, db_session):
        """Agentes N3 salvam contexto (agent_contexts) após execução."""
        _require_api_key()
        from app.agents.ticker_analyst import TickerAnalyst

        with _patch_model():
            analyst = TickerAnalyst(db_session, "VALE3")
            analyst.call_model(
                "Analise VALE3 brevemente. Use get_stock_price. Responda em 2 frases.",
                max_rounds=2,
            )

        ctx = db_session.query(AgentContext).filter_by(
            agent_name="ticker_analyst_VALE3"
        ).first()
        assert ctx is not None, "AgentContext não foi salvo para ticker_analyst_VALE3"
        assert ctx.last_response_id is not None, "last_response_id não foi salvo"
        assert ctx.execution_count >= 1, "execution_count deveria ser >= 1"
        assert ctx.resumo_contexto, "resumo_contexto deveria estar populado"

        logger.info(
            f"F2.3 PASS — Context VALE3: exec_count={ctx.execution_count}, "
            f"resumo={ctx.resumo_contexto[:80]}..."
        )


# ─── Fase 3: Agentes N2 Reais (delegam a N3) ────────────────────────────────

class TestFase3AgentesN2:
    """Agentes N2 (B3Agent, CryptoAgent) com delegação real a N3."""

    def test_b3_agent_delegates_to_n3(self, db_session):
        """B3Agent mapeia mercado e delega a TickerAnalyst N3 (1 ticker para economizar)."""
        _require_api_key()
        from app.agents.b3_agent import B3Agent

        with _patch_model():
            agent = B3Agent(db_session)
            # Prompt ultra-direcionado: skip web_search, vai direto para analyze_stock_deep
            result = agent.call_model(
                "NÃO faça web_search. Vá direto: chame analyze_stock_deep com "
                "ticker='PETR4' e portfolio_context='Carteira moderada, 50% ações, R$100k'. "
                "Após receber o resultado, responda com um resumo breve em JSON.",
                max_rounds=5,
            )

        assert result, "B3Agent retornou resultado vazio"

        # Verificar que TickerAnalyst N3 foi instanciado (custos logados)
        custos_n3 = db_session.query(CustoToken).filter(
            CustoToken.agente.like("ticker_analyst_%")
        ).all()
        assert len(custos_n3) >= 1, "Nenhum custo de TickerAnalyst N3 logado — delegação não funcionou"

        # B3Agent próprio também deve ter custos
        custos_b3 = db_session.query(CustoToken).filter(
            CustoToken.agente == "b3_agent"
        ).all()
        assert len(custos_b3) >= 1, "Custos do B3Agent não foram logados"

        # Verificar análise salva
        analises = db_session.query(AnaliseIA).filter(
            AnaliseIA.agente.like("ticker_analyst_%")
        ).all()

        logger.info(
            f"F3.1 PASS — B3Agent delegou a N3. "
            f"Custos B3: {len(custos_b3)}, Custos N3: {len(custos_n3)}, "
            f"Análises N3: {len(analises)}. Result: {len(result)} chars"
        )

    def test_crypto_agent_delegates_to_n3(self, db_session):
        """CryptoAgent mapeia mercado e delega a CryptoAnalyst N3 (1 crypto)."""
        _require_api_key()
        from app.agents.crypto_agent import CryptoAgent

        with _patch_model():
            agent = CryptoAgent(db_session)
            # Prompt ultra-direcionado: skip web_search, vai direto para analyze_crypto_deep
            result = agent.call_model(
                "NÃO faça web_search nem get_crypto_trending. Vá direto: chame analyze_crypto_deep com "
                "crypto_id='bitcoin' e portfolio_context='Carteira moderada, 20% crypto, R$100k'. "
                "Após receber o resultado, responda com um resumo breve em JSON.",
                max_rounds=5,
            )

        assert result, "CryptoAgent retornou resultado vazio"

        custos_n3 = db_session.query(CustoToken).filter(
            CustoToken.agente.like("crypto_analyst_%")
        ).all()
        assert len(custos_n3) >= 1, "Nenhum custo de CryptoAnalyst N3 logado"

        custos_crypto = db_session.query(CustoToken).filter(
            CustoToken.agente == "crypto_agent"
        ).all()
        assert len(custos_crypto) >= 1, "Custos do CryptoAgent não foram logados"

        logger.info(
            f"F3.2 PASS — CryptoAgent delegou a N3. "
            f"Custos Crypto: {len(custos_crypto)}, Custos N3: {len(custos_n3)}. "
            f"Result: {len(result)} chars"
        )


# ─── Fase 4: StatsAgent com calculate_stats real ────────────────────────────

class TestFase4StatsAgent:
    """StatsAgent com calculate_stats, get_macro_data e scraping real."""

    def test_stats_agent_calculates(self, db_session):
        """StatsAgent calcula stats de PETR4 com dados reais."""
        _require_api_key()
        from app.agents.stats_agent import StatsAgent

        with _patch_model():
            agent = StatsAgent(db_session)
            result = agent.call_model(
                "1) Busque get_macro_data para obter CDI. "
                "2) Busque get_stock_history de PETR4 período 1y. "
                "3) Use calculate_stats com os fechamentos e o CDI como risk_free_rate_annual. "
                "4) Responda com o JSON das estatísticas.",
                max_rounds=5,
            )

        assert result, "StatsAgent retornou resultado vazio"
        assert len(result) > 50

        custos = db_session.query(CustoToken).filter(
            CustoToken.agente == "stats_agent"
        ).all()
        assert len(custos) >= 1, "Custos do StatsAgent não foram logados"

        logger.info(f"F4.1 PASS — StatsAgent: {len(result)} chars, {len(custos)} cost entries")

    def test_calculate_stats_standalone(self):
        """calculate_stats funciona standalone com preços reais."""
        from app.agents.stats_agent import _calculate_stats

        # Simular série de preços realista
        prices = [38.0 + i * 0.05 + (i % 7) * 0.1 for i in range(252)]
        stats = _calculate_stats(prices, rf_annual=0.1375)

        assert "retorno_total_pct" in stats
        assert "sharpe_ratio" in stats
        assert "volatilidade_anual_pct" in stats
        assert "max_drawdown_pct" in stats
        assert stats["taxa_livre_risco_anual"] == 0.1375
        assert stats["num_observacoes"] == 252

        logger.info(
            f"F4.2 PASS — calculate_stats: retorno={stats['retorno_total_pct']}%, "
            f"sharpe={stats['sharpe_ratio']}, vol={stats['volatilidade_anual_pct']}%"
        )


# ─── Fase 5: Verificação do DB ──────────────────────────────────────────────

class TestFase5VerificacaoDB:
    """Verifica que dados foram persistidos corretamente no DB após as fases anteriores."""

    def test_custos_tokens_populated(self, shared_session):
        """Tabela custos_tokens tem registros dos agentes."""
        _require_api_key()
        from app.agents.ticker_analyst import TickerAnalyst

        # Executar um agente na shared_session para garantir dados
        with _patch_model():
            analyst = TickerAnalyst(shared_session, "ITUB4")
            analyst.call_model(
                "Qual o preço de ITUB4? Use get_stock_price. Responda em 1 frase.",
                max_rounds=2,
            )

        custos = shared_session.query(CustoToken).all()
        assert len(custos) >= 1, "Nenhum custo registrado no DB"

        for c in custos:
            assert c.agente, "agente vazio"
            assert c.modelo, "modelo vazio"
            assert c.tokens_input > 0, f"tokens_input=0 para {c.agente}"
            assert c.tokens_output > 0, f"tokens_output=0 para {c.agente}"
            assert c.custo_usd >= 0, f"custo_usd negativo para {c.agente}"
            assert c.cotacao_dolar > 0, f"cotacao_dolar invalida para {c.agente}"

        agentes = {c.agente for c in custos}
        logger.info(f"F5.1 PASS — {len(custos)} registros de custo, agentes: {agentes}")

    def test_agent_contexts_populated(self, shared_session):
        """Tabela agent_contexts tem contextos salvos."""
        _require_api_key()

        # O agente já foi executado no teste acima (shared_session)
        contexts = shared_session.query(AgentContext).all()
        assert len(contexts) >= 1, "Nenhum contexto salvo"

        for ctx in contexts:
            assert ctx.agent_name, "agent_name vazio"
            assert ctx.last_response_id, "last_response_id vazio"
            assert ctx.execution_count >= 1, f"execution_count=0 para {ctx.agent_name}"

        nomes = {c.agent_name for c in contexts}
        logger.info(f"F5.2 PASS — {len(contexts)} agent contexts: {nomes}")

    def test_analises_ia_populated(self, shared_session):
        """Tabela analises_ia tem análises salvas (se agentes usaram save_analysis)."""
        _require_api_key()
        from app.agents.ticker_analyst import TickerAnalyst

        # Executar analyze() que chama save_analysis internamente
        with _patch_model():
            analyst = TickerAnalyst(shared_session, "BBDC4")
            analyst.analyze(
                "BBDC4",
                portfolio_context="Portfólio teste",
                job_id=None,
            )

        analises = shared_session.query(AnaliseIA).filter(
            AnaliseIA.agente == "ticker_analyst_BBDC4"
        ).all()
        assert len(analises) >= 1, "Análise não foi salva no DB"

        a = analises[0]
        assert a.tipo_analise == "analise_ticker"
        assert a.output_completo, "output_completo vazio"
        assert len(a.output_completo) > 20

        logger.info(f"F5.3 PASS — Análise BBDC4 salva: {len(a.output_completo)} chars")


# ─── Fase 6: Backend HTTP ───────────────────────────────────────────────────

def _is_port_open(host: str, port: int) -> bool:
    """Checa se uma porta está aberta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


class TestFase6BackendHTTP:
    """Testa endpoints HTTP reais via uvicorn."""

    @pytest.fixture(scope="class")
    def uvicorn_server(self):
        """Inicia uvicorn em background e para após os testes."""
        if _is_port_open("127.0.0.1", 8000):
            # Servidor já está rodando (ex: dev mode)
            yield "http://127.0.0.1:8000"
            return

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )

        # Esperar servidor subir (max 15s)
        for _ in range(30):
            if _is_port_open("127.0.0.1", 8000):
                break
            time.sleep(0.5)
        else:
            proc.terminate()
            pytest.fail("Uvicorn não iniciou em 15s")

        yield "http://127.0.0.1:8000"
        proc.terminate()
        proc.wait(timeout=5)

    def test_health_endpoint(self, uvicorn_server):
        """GET /api/health retorna status ok."""
        import requests

        r = requests.get(f"{uvicorn_server}/api/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

        logger.info("F6.1 PASS — /api/health OK")

    def test_portfolio_endpoint(self, uvicorn_server):
        """GET /api/portfolio retorna dados do portfólio."""
        import requests

        r = requests.get(f"{uvicorn_server}/api/portfolio", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

        logger.info(f"F6.2 PASS — /api/portfolio: {list(data.keys())[:6]}")

    def test_custos_endpoint(self, uvicorn_server):
        """GET /api/custos retorna lista de custos."""
        import requests

        r = requests.get(f"{uvicorn_server}/api/custos", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

        logger.info(f"F6.3 PASS — /api/custos: {len(data)} registros")

    def test_analises_endpoint(self, uvicorn_server):
        """GET /api/analises retorna lista de análises."""
        import requests

        r = requests.get(f"{uvicorn_server}/api/analises", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

        logger.info(f"F6.4 PASS — /api/analises: {len(data)} registros")

    def test_configuracoes_endpoint(self, uvicorn_server):
        """GET /api/configuracoes retorna configs."""
        import requests

        r = requests.get(f"{uvicorn_server}/api/configuracoes", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (dict, list))

        logger.info(f"F6.5 PASS — /api/configuracoes OK")

    def test_macro_endpoint(self, uvicorn_server):
        """GET /api/market/macro retorna dados macro."""
        import requests

        r = requests.get(f"{uvicorn_server}/api/market/macro", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

        logger.info(f"F6.6 PASS — /api/market/macro: {list(data.keys())[:6]}")


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
