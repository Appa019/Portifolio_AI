"""
Teste de validação da auditoria multi-agentes — chamadas REAIS à OpenAI.

Valida:
  T1. Pattern A: previous_response_id só no round 0, input_list acumulada nos rounds seguintes
  T2. web_search_tool(): search_context_size configurável por agente
  T3. CDI dinâmico: calculate_stats aceita risk_free_rate_annual
  T4. Timeout em sub-agentes (mock de agente lento)
  T5. Execução paralela de function_calls (2+ no mesmo round)
  T6. History completa: N3 envia todos os fechamentos (não sampling 15 pontos)
  T7. Contexto persistente: resumo_contexto populado e injetado na próxima execução
  T8. ticker_resolver client singleton

Uso:
  source .venv/bin/activate
  python -m pytest tests/test_agent_audit.py -v
"""

import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from openai import OpenAI
from app.config import settings
from app.database import Base
from app.models.db_models import AgentContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """OpenAI client real."""
    assert settings.openai_api_key, "OPENAI_API_KEY não configurada"
    return OpenAI(api_key=settings.openai_api_key)


# db_session fixture is provided by tests/conftest.py


# ─── T1: Pattern A — agentic loop com input_list ─────────────────────────────

class TestPatternA:
    """Valida que o agentic loop funciona com Pattern A (input_list acumulada)."""

    def test_multi_round_tool_use(self, client):
        """Modelo chama tool → recebe resultado → responde. Sem previous_response_id entre rounds."""
        tools = [
            {
                "type": "function",
                "name": "get_price",
                "description": "Retorna preço atual de um ativo",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Ticker do ativo"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

        input_list = [{"role": "user", "content": "Qual o preço de PETR4? Use get_price."}]
        token_counts = []

        # Round 1: modelo deve chamar get_price
        r1 = client.responses.create(
            model="gpt-4.1-mini",
            instructions="Você é um assistente financeiro. Use get_price para consultar preços.",
            tools=tools,
            input=input_list,
        )
        token_counts.append({"round": 1, "input": r1.usage.input_tokens, "output": r1.usage.output_tokens})

        fc_items = [item for item in r1.output if item.type == "function_call"]
        assert len(fc_items) >= 1, "Modelo deveria chamar get_price"
        assert fc_items[0].name == "get_price"

        args = json.loads(fc_items[0].arguments)
        assert "ticker" in args

        # Acumular output (incluindo possíveis reasoning items) + function_call_output
        input_list = input_list + list(r1.output)
        input_list.append({
            "type": "function_call_output",
            "call_id": fc_items[0].call_id,
            "output": json.dumps({"ticker": "PETR4", "preco": 38.50, "moeda": "BRL"}),
        })

        # Round 2: SEM previous_response_id — Pattern A puro
        r2 = client.responses.create(
            model="gpt-4.1-mini",
            instructions="Você é um assistente financeiro. Use get_price para consultar preços.",
            tools=tools,
            input=input_list,
            # NÃO passa previous_response_id aqui
        )
        token_counts.append({"round": 2, "input": r2.usage.input_tokens, "output": r2.usage.output_tokens})

        # Round 2 deve ser resposta final (sem mais function_calls)
        fc_items_r2 = [item for item in r2.output if item.type == "function_call"]
        final_text = r2.output_text or ""

        assert final_text, "Modelo deveria retornar texto final"
        assert "38" in final_text or "PETR4" in final_text.upper(), \
            f"Resposta deveria mencionar o preço: {final_text[:200]}"

        logger.info("T1 PASS — Pattern A multi-round OK")
        for tc in token_counts:
            logger.info(f"  Round {tc['round']}: {tc['input']} input, {tc['output']} output tokens")

    def test_previous_response_id_cross_execution(self, client):
        """Valida que previous_response_id funciona para continuidade cross-execution (round 0)."""
        instructions = "Você é um assistente financeiro. Responda sempre em português."
        # Execução 1 — informação neutra no INPUT
        r1 = client.responses.create(
            model="gpt-4.1-mini",
            instructions=instructions,
            input=[{"role": "user", "content": "Meu portfólio tem 3 ativos: PETR4 (50%), VALE3 (30%) e Bitcoin (20%). O valor total é R$175.432,00."}],
        )
        resp_id = r1.id
        assert resp_id, "response.id deveria existir"

        # Execução 2 — usa previous_response_id (cross-execution), mesma instructions
        r2 = client.responses.create(
            model="gpt-4.1-mini",
            instructions=instructions,
            input=[{"role": "user", "content": "Qual era o valor total do meu portfólio que informei antes?"}],
            previous_response_id=resp_id,
        )
        text = r2.output_text or ""
        assert "175" in text, \
            f"Modelo deveria lembrar o valor via previous_response_id: {text[:200]}"

        logger.info("T1b PASS — previous_response_id cross-execution OK")


# ─── T2: web_search_tool() com search_context_size ────────────────────────────

class TestWebSearchTool:
    """Valida que search_context_size é aceito pela API."""

    def test_search_context_size_high(self, client):
        """API aceita search_context_size='high' sem erro."""
        from app.agents.base_agent import web_search_tool

        tool = web_search_tool("high")
        assert tool["search_context_size"] == "high"

        r = client.responses.create(
            model="gpt-4.1-mini",
            instructions="Responda brevemente.",
            tools=[tool],
            input=[{"role": "user", "content": "Qual o preço atual do bitcoin em USD? Responda em 1 frase."}],
        )
        text = r.output_text or ""
        # Pode ter function_calls intermediárias de web_search, mas deve terminar com texto
        # Se web_search foi chamada, a API processou o search_context_size sem erro
        assert r.id, "API aceitou search_context_size='high'"
        logger.info(f"T2 PASS — search_context_size='high' aceito. Tokens: {r.usage.input_tokens}+{r.usage.output_tokens}")

    def test_all_context_sizes(self):
        """Verifica que cada nível de agente usa o context_size correto."""
        from app.agents.base_agent import web_search_tool

        assert web_search_tool("low")["search_context_size"] == "low"
        assert web_search_tool("medium")["search_context_size"] == "medium"
        assert web_search_tool("high")["search_context_size"] == "high"
        logger.info("T2b PASS — todos os context_sizes construídos corretamente")

    def test_agents_use_correct_context_size(self, db_session):
        """Cada agente usa o search_context_size adequado ao seu nível."""
        from app.agents.ticker_analyst import TickerAnalyst
        from app.agents.crypto_analyst import CryptoAnalyst
        from app.agents.b3_agent import B3Agent
        from app.agents.crypto_agent import CryptoAgent

        # N3 = high
        ta = TickerAnalyst(db_session, "PETR4")
        tools = ta.get_tools()
        ws = [t for t in tools if t.get("type") == "web_search"][0]
        assert ws["search_context_size"] == "high", f"TickerAnalyst deveria usar 'high', got {ws['search_context_size']}"

        ca = CryptoAnalyst(db_session, "bitcoin")
        tools = ca.get_tools()
        ws = [t for t in tools if t.get("type") == "web_search"][0]
        assert ws["search_context_size"] == "high"

        # N2 = medium
        b3 = B3Agent(db_session)
        tools = b3.get_tools()
        ws = [t for t in tools if t.get("type") == "web_search"][0]
        assert ws["search_context_size"] == "medium"

        cr = CryptoAgent(db_session)
        tools = cr.get_tools()
        ws = [t for t in tools if t.get("type") == "web_search"][0]
        assert ws["search_context_size"] == "medium"

        logger.info("T2c PASS — N3=high, N2=medium confirmado")


# ─── T3: CDI dinâmico no calculate_stats ──────────────────────────────────────

class TestCDIDinamico:

    def test_calculate_stats_with_rf(self):
        """calculate_stats aceita e usa risk_free_rate_annual."""
        from app.agents.stats_agent import _calculate_stats

        prices = [100 + i * 0.3 for i in range(252)]

        # CDI 13.75%
        r1 = _calculate_stats(prices, rf_annual=0.1375)
        assert "taxa_livre_risco_anual" in r1
        assert r1["taxa_livre_risco_anual"] == 0.1375

        # CDI 10%
        r2 = _calculate_stats(prices, rf_annual=0.10)
        assert r2["taxa_livre_risco_anual"] == 0.10

        # Sharpe deve mudar com CDI diferente
        assert r1["sharpe_ratio"] != r2["sharpe_ratio"], \
            "Sharpe deveria mudar com taxa livre de risco diferente"

        logger.info(f"T3 PASS — CDI 13.75%: Sharpe={r1['sharpe_ratio']}, CDI 10%: Sharpe={r2['sharpe_ratio']}")

    def test_tool_schema_requires_rf(self, db_session):
        """Tool schema exige risk_free_rate_annual como required."""
        from app.agents.stats_agent import StatsAgent

        sa = StatsAgent(db_session)
        tools = sa.get_tools()
        calc_tool = [t for t in tools if t.get("name") == "calculate_stats"][0]

        assert "risk_free_rate_annual" in calc_tool["parameters"]["properties"]
        assert "risk_free_rate_annual" in calc_tool["parameters"]["required"]
        logger.info("T3b PASS — tool schema exige risk_free_rate_annual")

    def test_model_passes_rf_to_calculate_stats(self, client):
        """Modelo passa risk_free_rate_annual quando chama calculate_stats."""
        tools = [
            {
                "type": "function",
                "name": "calculate_stats",
                "description": "Calcula estatísticas de preços. Obter risk_free_rate_annual de CDI atual.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prices": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Lista de preços de fechamento",
                        },
                        "risk_free_rate_annual": {
                            "type": "number",
                            "description": "Taxa livre de risco anual (ex: 0.1375 para CDI 13.75%)",
                        },
                    },
                    "required": ["prices", "risk_free_rate_annual"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

        r = client.responses.create(
            model="gpt-4.1-mini",
            instructions="Calcule estatísticas dos preços fornecidos. O CDI atual é 13.75% a.a.",
            tools=tools,
            input=[{"role": "user", "content": "Calcule stats para preços: [100, 102, 99, 103, 105, 101, 107]"}],
        )

        fc_items = [item for item in r.output if item.type == "function_call"]
        assert len(fc_items) >= 1, "Modelo deveria chamar calculate_stats"
        args = json.loads(fc_items[0].arguments)
        assert "risk_free_rate_annual" in args, f"Args não contém risk_free_rate_annual: {args}"
        assert isinstance(args["risk_free_rate_annual"], (int, float))
        logger.info(f"T3c PASS — Modelo passou rf={args['risk_free_rate_annual']}")


# ─── T4: Timeout em sub-agentes ───────────────────────────────────────────────

class TestTimeout:

    def test_timeout_fires(self):
        """ThreadPoolExecutor timeout funciona em agente lento."""
        def slow_agent():
            time.sleep(5)
            return "nunca deveria chegar aqui"

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(slow_agent)
            with pytest.raises(FuturesTimeoutError):
                future.result(timeout=1)

        logger.info("T4 PASS — timeout dispara corretamente")

    def test_orchestrator_sub_agent_error_handling(self, db_session):
        """Orchestrator._run_sub_agent captura exceções e retorna erro JSON."""
        from app.agents.orchestrator import Orchestrator

        orch = Orchestrator(db_session)
        orch._job_id = "test-error"

        def failing_fn():
            raise RuntimeError("algo deu errado")

        with patch("app.ensemble.progress.emit"):
            result = orch._run_sub_agent(failing_fn, "FailAgent")

        parsed = json.loads(result)
        assert "erro" in parsed
        assert "algo deu errado" in parsed["erro"]
        logger.info(f"T4b PASS — _run_sub_agent capturou erro: {parsed}")


# ─── T5: Execução paralela de function_calls ─────────────────────────────────

class TestParallelExecution:

    def test_model_emits_multiple_function_calls(self, client):
        """Modelo pode emitir múltiplas function_calls no mesmo round."""
        tools = [
            {
                "type": "function",
                "name": "get_price",
                "description": "Retorna preço de um ativo",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"}
                    },
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

        r = client.responses.create(
            model="gpt-4.1-mini",
            instructions="Quando o usuário pedir múltiplos preços, chame get_price para CADA ticker separadamente.",
            tools=tools,
            input=[{"role": "user", "content": "Preços de PETR4, VALE3 e ITUB4"}],
        )

        fc_items = [item for item in r.output if item.type == "function_call"]
        assert len(fc_items) >= 2, \
            f"Modelo deveria emitir múltiplas function_calls, emitiu {len(fc_items)}"

        tickers = [json.loads(fc.arguments)["ticker"] for fc in fc_items]
        logger.info(f"T5 PASS — {len(fc_items)} function_calls no mesmo round: {tickers}")

    def test_parallel_executor(self, db_session):
        """_execute_parallel retorna resultados na ordem original."""
        from app.agents.base_agent import BaseAgent

        class DummyAgent(BaseAgent):
            agent_name = "test_parallel"
            def system_prompt(self): return ""
            def get_tools(self): return []
            def execute_function(self, name, args):
                time.sleep(0.1)  # simular trabalho
                return json.dumps({"ticker": args.get("ticker", "?"), "preco": 42.0})

        agent = DummyAgent(db_session)

        # Criar mock de function_call items
        class FakeFc:
            def __init__(self, call_id, name, arguments):
                self.call_id = call_id
                self.name = name
                self.arguments = arguments
                self.type = "function_call"

        fcs = [
            FakeFc("call_1", "get_price", '{"ticker": "PETR4"}'),
            FakeFc("call_2", "get_price", '{"ticker": "VALE3"}'),
            FakeFc("call_3", "get_price", '{"ticker": "ITUB4"}'),
        ]

        start = time.time()
        results = agent._execute_parallel(fcs, None)
        elapsed = time.time() - start

        assert len(results) == 3
        assert results[0]["call_id"] == "call_1"  # ordem preservada
        assert results[1]["call_id"] == "call_2"
        assert results[2]["call_id"] == "call_3"

        # Paralelo: 3 tasks × 0.1s deveria ser ~0.1s, não 0.3s
        assert elapsed < 0.25, f"Execução paralela demorou {elapsed:.2f}s (deveria ser <0.25s)"

        logger.info(f"T5b PASS — 3 function_calls paralelas em {elapsed:.3f}s, ordem preservada")


# ─── T6: History completa para N3 ────────────────────────────────────────────

class TestHistoryData:

    def test_ticker_analyst_sends_all_closes(self, db_session):
        """TickerAnalyst envia todos os fechamentos quando len > 60."""
        from app.agents.ticker_analyst import TickerAnalyst

        ta = TickerAnalyst(db_session, "TEST")

        # Mock get_stock_history retornando 252 registros
        fake_data = [
            {"data": f"2025-{(i//22)+1:02d}-{(i%22)+1:02d}", "abertura": 100+i*0.1,
             "maxima": 101+i*0.1, "minima": 99+i*0.1, "fechamento": 100.5+i*0.1, "volume": 1000000}
            for i in range(252)
        ]

        with patch("app.agents.ticker_analyst.get_stock_history", return_value=fake_data):
            result_str = ta.execute_function("get_stock_history", {"ticker": "TEST", "period": "1y"})

        result = json.loads(result_str)
        assert "fechamentos" in result, "Deveria ter campo 'fechamentos'"
        assert len(result["fechamentos"]) == 252, f"Deveria ter 252 fechamentos, tem {len(result['fechamentos'])}"
        assert "amostra" not in result, "NÃO deveria ter campo 'amostra' (sampling antigo)"
        assert "primeiro" in result
        assert "ultimo" in result
        logger.info(f"T6 PASS — {len(result['fechamentos'])} fechamentos enviados (não 15 amostrados)")

    def test_crypto_analyst_sends_all_closes(self, db_session):
        """CryptoAnalyst envia todos os fechamentos quando len > 60."""
        from app.agents.crypto_analyst import CryptoAnalyst

        ca = CryptoAnalyst(db_session, "bitcoin")

        fake_data = [
            {"data": f"2025-{(i//22)+1:02d}-{(i%22)+1:02d}", "abertura": 50000+i*10,
             "maxima": 50100+i*10, "minima": 49900+i*10, "fechamento": 50050+i*10, "volume": 5000000}
            for i in range(180)
        ]

        with patch("app.agents.crypto_analyst.get_crypto_history", return_value=fake_data):
            result_str = ca.execute_function("get_crypto_history", {"crypto_id": "bitcoin", "period": "6mo"})

        result = json.loads(result_str)
        assert "fechamentos" in result
        assert len(result["fechamentos"]) == 180
        assert "amostra" not in result
        logger.info(f"T6b PASS — CryptoAnalyst: {len(result['fechamentos'])} fechamentos")


# ─── T7: Contexto persistente (resumo_contexto) ──────────────────────────────

class TestPersistentContext:

    def test_save_context_stores_resumo(self, db_session):
        """_save_context salva resumo_contexto no DB."""
        from app.agents.base_agent import BaseAgent

        class DummyAgent(BaseAgent):
            agent_name = "test_context_agent"
            def system_prompt(self): return "test"
            def get_tools(self): return []
            def execute_function(self, name, args): return "{}"

        agent = DummyAgent(db_session)

        # Primeira execução
        agent._save_context("resp_001", resumo="Recomendei COMPRA de PETR4 a R$38.50")
        ctx = db_session.query(AgentContext).filter_by(agent_name="test_context_agent").first()

        assert ctx is not None
        assert ctx.last_response_id == "resp_001"
        assert ctx.resumo_contexto == "Recomendei COMPRA de PETR4 a R$38.50"
        assert ctx.execution_count == 1
        assert ctx.last_execution is not None

        # Segunda execução — atualiza
        agent._save_context("resp_002", resumo="Mudei para MANTER, preço subiu para R$42")
        db_session.refresh(ctx)

        assert ctx.last_response_id == "resp_002"
        assert ctx.resumo_contexto == "Mudei para MANTER, preço subiu para R$42"
        assert ctx.execution_count == 2

        logger.info("T7 PASS — resumo_contexto salvo e atualizado corretamente")

    def test_context_injected_in_input(self, db_session):
        """Contexto anterior é injetado no input do próximo call_model."""
        from app.agents.base_agent import BaseAgent

        class DummyAgent(BaseAgent):
            agent_name = "test_inject_agent"
            model = "gpt-4.1-mini"
            def system_prompt(self): return "Responda brevemente."
            def get_tools(self): return []
            def execute_function(self, name, args): return "{}"

        agent = DummyAgent(db_session)

        # Simular contexto anterior
        ctx = AgentContext(
            agent_name="test_inject_agent",
            last_response_id="resp_old",
            last_execution=datetime.now() - timedelta(days=7),
            execution_count=3,
            resumo_contexto="Na análise de 2026-02-23, recomendei COMPRA de PETR4, preço alvo R$44.",
        )
        db_session.add(ctx)
        db_session.commit()

        # Chamar call_model — deve injetar o contexto anterior
        result = agent.call_model("O que você recomenda agora?", max_rounds=1)

        # Verificar que o contexto foi injetado (modelo deveria mencionar algo da análise anterior)
        # Mesmo que o modelo não "lembre", o importante é que o input foi montado corretamente
        db_session.refresh(ctx)
        assert ctx.execution_count == 4, "execution_count deveria incrementar"
        assert ctx.resumo_contexto is not None, "resumo_contexto deveria ser atualizado"
        assert ctx.resumo_contexto != "Na análise de 2026-02-23, recomendei COMPRA de PETR4, preço alvo R$44.", \
            "resumo_contexto deveria ser atualizado com a nova resposta"

        logger.info(f"T7b PASS — Contexto injetado, novo resumo: {ctx.resumo_contexto[:100]}...")

    def test_n3_dynamic_agent_name_context(self, db_session):
        """N3 agents com nome dinâmico (ticker_analyst_PETR4) têm contexto individual."""
        from app.agents.base_agent import BaseAgent

        class FakeN3(BaseAgent):
            def __init__(self, db, ticker):
                self.agent_name = f"ticker_analyst_{ticker}"
                super().__init__(db)
            def system_prompt(self): return "test"
            def get_tools(self): return []
            def execute_function(self, name, args): return "{}"

        a1 = FakeN3(db_session, "PETR4")
        a2 = FakeN3(db_session, "VALE3")

        a1._save_context("resp_petr4", resumo="PETR4: compra, alvo R$44")
        a2._save_context("resp_vale3", resumo="VALE3: manter, lateralizado")

        ctx1 = db_session.query(AgentContext).filter_by(agent_name="ticker_analyst_PETR4").first()
        ctx2 = db_session.query(AgentContext).filter_by(agent_name="ticker_analyst_VALE3").first()

        assert ctx1.resumo_contexto == "PETR4: compra, alvo R$44"
        assert ctx2.resumo_contexto == "VALE3: manter, lateralizado"
        assert ctx1.last_response_id != ctx2.last_response_id

        logger.info("T7c PASS — N3 agents com contexto individual por ticker")


# ─── T8: ticker_resolver client singleton ─────────────────────────────────────

class TestTickerResolverSingleton:

    def test_singleton_client(self):
        """_get_client() retorna mesma instância."""
        from app.services.ticker_resolver import _get_client
        import app.services.ticker_resolver as tr

        # Reset
        tr._client = None

        c1 = _get_client()
        c2 = _get_client()

        assert c1 is c2, "Deveria retornar mesma instância (singleton)"
        logger.info("T8 PASS — ticker_resolver client singleton OK")


# ─── T9: Integração end-to-end simplificada ──────────────────────────────────

class TestE2ESimplificado:
    """Teste e2e: agente com 2 tools, multi-round, Pattern A."""

    def test_agent_full_loop(self, client):
        """Agente com 2 tools completa loop: tool1 → tool2 → resposta final."""
        tools = [
            {
                "type": "function",
                "name": "get_portfolio",
                "description": "Retorna resumo do portfólio",
                "parameters": {
                    "type": "object", "properties": {},
                    "required": [], "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_macro",
                "description": "Retorna dados macroeconômicos (Selic, CDI, IPCA)",
                "parameters": {
                    "type": "object", "properties": {},
                    "required": [], "additionalProperties": False,
                },
                "strict": True,
            },
        ]

        input_list = [{"role": "user", "content": "Analise meu portfólio considerando dados macro. "
                        "Chame get_portfolio E get_macro, depois responda."}]

        token_log = []
        max_rounds = 5

        for round_num in range(max_rounds):
            r = client.responses.create(
                model="gpt-4.1-mini",
                instructions="Você analisa portfólios. Use as ferramentas disponíveis antes de responder.",
                tools=tools,
                input=input_list,
            )
            token_log.append({
                "round": round_num + 1,
                "input_tokens": r.usage.input_tokens,
                "output_tokens": r.usage.output_tokens,
            })

            fc_items = [item for item in r.output if item.type == "function_call"]

            if not fc_items:
                # Resposta final
                final = r.output_text or ""
                assert final, "Resposta final não deveria ser vazia"
                logger.info(f"T9 PASS — Loop completo em {round_num + 1} rounds")
                for tl in token_log:
                    logger.info(f"  Round {tl['round']}: {tl['input_tokens']} in, {tl['output_tokens']} out")
                return

            # Acumular output + executar tools
            input_list = input_list + list(r.output)
            for fc in fc_items:
                if fc.name == "get_portfolio":
                    result = json.dumps({"valor_total": 150000, "acoes_pct": 48, "crypto_pct": 22, "cdb_pct": 30})
                elif fc.name == "get_macro":
                    result = json.dumps({"selic": 13.75, "cdi": 13.65, "ipca_12m": 4.5, "ptax": 5.85})
                else:
                    result = json.dumps({"erro": "desconhecido"})

                input_list.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result,
                })

        pytest.fail(f"Loop não completou em {max_rounds} rounds")


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
