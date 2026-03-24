"""
Tests for Goldman Sachs multi-agent expansion.

Group 1: Unit tests (no API calls, $0)
  - TestPersonas: persona lookup, formatting, dynamic N3
  - TestRunBudgetTracker: thread-safe budget tracking
  - TestDebateOrchestrator: divergence detection
  - TestNewAgentStructure: all N2 agents instantiate, have tools, correct model
  - TestAnalysisPipeline: phase structure, budget integration

Group 2: Integration (requires OPENAI_API_KEY)
  - TestPipelineSmoke: minimal pipeline run with mocked sub-agents

Usage:
  python -m pytest tests/test_goldman_agents.py -v
  python -m pytest tests/test_goldman_agents.py -v -m "not integration"
"""

import json
import logging
import threading
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================================
# Group 1: Unit Tests ($0)
# ==============================================================================


class TestPersonas:
    """Persona lookup, formatting, and dynamic N3 generation."""

    def test_static_persona_lookup(self):
        from app.agents.personas import get_persona

        p = get_persona("fundamentalista_b3")
        assert p is not None
        assert p.display_name == "Ricardo Moura"
        assert p.cargo == "Fundamentalista"
        assert p.team == "b3"
        assert p.level == "N2"

    def test_cio_persona(self):
        from app.agents.personas import get_persona

        p = get_persona("cio")
        assert p is not None
        assert p.display_name == "Carlos Mendonça"
        assert p.level == "N0"

    def test_dynamic_n3_ticker(self):
        from app.agents.personas import get_persona

        p = get_persona("ticker_analyst_PETR4")
        assert p is not None
        assert "PETR4" in p.display_name
        assert p.level == "N3"
        assert p.team == "b3"

    def test_dynamic_n3_crypto(self):
        from app.agents.personas import get_persona

        p = get_persona("crypto_analyst_bitcoin")
        assert p is not None
        assert "Bitcoin" in p.display_name
        assert p.level == "N3"
        assert p.team == "crypto"

    def test_unknown_agent_returns_none(self):
        from app.agents.personas import get_persona

        assert get_persona("nonexistent_agent") is None

    def test_format_telegram_message(self):
        from app.agents.personas import format_telegram_message

        msg = format_telegram_message("tecnico_b3", "Papel perdeu a MM200")
        assert "Bruno Kato" in msg
        assert "Técnico" in msg
        assert "📊" in msg

    def test_persona_count(self):
        from app.agents.personas import PERSONAS

        assert len(PERSONAS) == 18  # 18 named agents (N3 are dynamic)

    def test_all_teams_represented(self):
        from app.agents.personas import PERSONAS

        teams = {p.team for p in PERSONAS.values()}
        assert teams == {"ceo", "b3", "crypto", "risk", "cross"}

    def test_group_member_lists(self):
        from app.agents.personas import B3_GROUP_MEMBERS, CRYPTO_GROUP_MEMBERS

        assert "head_b3" in B3_GROUP_MEMBERS
        assert "fundamentalista_b3" in B3_GROUP_MEMBERS
        assert "macro_economist" in B3_GROUP_MEMBERS  # cross-team participates
        assert "head_crypto" in CRYPTO_GROUP_MEMBERS
        assert "onchain_analyst" in CRYPTO_GROUP_MEMBERS


class TestRunBudgetTracker:
    """Thread-safe budget tracking."""

    def test_basic_tracking(self):
        from app.services.token_cost import RunBudgetTracker

        t = RunBudgetTracker(5.0)
        assert t.spent == 0.0
        assert t.remaining == 5.0
        assert not t.exceeded

        assert t.add(2.0)  # still within budget
        assert t.spent == 2.0
        assert t.remaining == 3.0

        assert not t.add(4.0)  # exceeds budget, returns False
        assert t.exceeded
        assert t.spent == 6.0
        assert t.remaining == 0.0

    def test_thread_safety(self):
        from app.services.token_cost import RunBudgetTracker

        t = RunBudgetTracker(100.0)
        errors = []

        def add_many():
            try:
                for _ in range(1000):
                    t.add(0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_many) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(errors) == 0
        assert abs(t.spent - 100.0) < 0.01  # 10 threads × 1000 × 0.01


class TestDebateOrchestrator:
    """Divergence detection between agent reports."""

    def test_detects_buy_vs_sell(self):
        from app.telegram.debate_orchestrator import detect_divergences

        reports = {
            "fundamentalista_b3": json.dumps({
                "analises_fundamentalistas": [
                    {"ticker": "PETR4", "recomendacao": "comprar", "score": 0.8}
                ]
            }),
            "tecnico_b3": json.dumps({
                "analises_tecnicas": [
                    {"ticker": "PETR4", "sinal": "venda", "score": 0.6}
                ]
            }),
        }

        divs = detect_divergences(reports)
        assert len(divs) == 1
        assert divs[0].asset == "PETR4"
        assert divs[0].position_a == "comprar"
        assert divs[0].position_b == "venda"

    def test_no_divergence_when_agree(self):
        from app.telegram.debate_orchestrator import detect_divergences

        reports = {
            "fundamentalista_b3": json.dumps({
                "analises_fundamentalistas": [
                    {"ticker": "VALE3", "recomendacao": "comprar"}
                ]
            }),
            "tecnico_b3": json.dumps({
                "analises_tecnicas": [
                    {"ticker": "VALE3", "sinal": "compra"}
                ]
            }),
        }

        divs = detect_divergences(reports)
        assert len(divs) == 0

    def test_handles_invalid_json(self):
        from app.telegram.debate_orchestrator import detect_divergences

        reports = {
            "fundamentalista_b3": "not json",
            "tecnico_b3": json.dumps({"analises_tecnicas": []}),
        }

        divs = detect_divergences(reports)
        assert len(divs) == 0

    def test_crypto_divergence(self):
        from app.telegram.debate_orchestrator import detect_divergences

        reports = {
            "onchain_analyst": json.dumps({
                "sinais_por_crypto": [
                    {"id": "bitcoin", "sinal_onchain": "acumulacao"}
                ]
            }),
            "tecnico_crypto": json.dumps({
                "analises_tecnicas": [
                    {"id": "BITCOIN", "sinal": "venda"}
                ]
            }),
        }

        divs = detect_divergences(reports)
        assert len(divs) == 1


class TestFormatters:
    """Telegram MarkdownV2 formatting."""

    def test_escape_special_chars(self):
        from app.telegram.formatters import escape_md

        assert escape_md("Hello_world") == "Hello\\_world"
        assert escape_md("test.py") == "test\\.py"
        assert escape_md("test") == "test"

    def test_format_agent_message(self):
        from app.telegram.formatters import format_agent_message

        msg = format_agent_message("📊", "Bruno", "Técnico", "Suporte em 34")
        assert "📊" in msg
        assert "*Bruno*" in msg
        assert "Suporte em 34" in msg

    def test_truncate(self):
        from app.telegram.formatters import truncate_for_telegram

        short = "hello"
        assert truncate_for_telegram(short) == short

        long_text = "x" * 5000
        truncated = truncate_for_telegram(long_text, max_chars=100)
        assert len(truncated) < 150
        assert "truncado" in truncated


class TestNewAgentStructure:
    """All new N2 agents instantiate correctly with proper config."""

    def test_b3_team_agents_instantiate(self, db_session):
        from app.agents.b3_team.fundamentalista_b3 import FundamentalistaB3
        from app.agents.b3_team.tecnico_b3 import TecnicoB3
        from app.agents.b3_team.setorial_b3 import SetorialB3
        from app.agents.b3_team.risk_b3 import RiskB3
        from app.agents.b3_team.trade_b3 import TradeB3

        agents = [
            FundamentalistaB3(db_session),
            TecnicoB3(db_session),
            SetorialB3(db_session),
            RiskB3(db_session),
            TradeB3(db_session),
        ]

        for agent in agents:
            assert agent.level == "N2"
            assert len(agent.get_tools()) >= 1
            prompt = agent.system_prompt()
            assert str(date.today().year) in prompt

    def test_crypto_team_agents_instantiate(self, db_session):
        from app.agents.crypto_team.fundamentalista_crypto import FundamentalistaCrypto
        from app.agents.crypto_team.tecnico_crypto import TecnicoCrypto
        from app.agents.crypto_team.onchain_analyst import OnChainAnalyst
        from app.agents.crypto_team.risk_crypto import RiskCrypto
        from app.agents.crypto_team.trade_crypto import TradeCrypto

        agents = [
            FundamentalistaCrypto(db_session),
            TecnicoCrypto(db_session),
            OnChainAnalyst(db_session),
            RiskCrypto(db_session),
            TradeCrypto(db_session),
        ]

        for agent in agents:
            assert agent.level == "N2"
            assert len(agent.get_tools()) >= 1

    def test_cross_team_agents_instantiate(self, db_session):
        from app.agents.cross_team.macro_economist import MacroEconomist
        from app.agents.cross_team.sentiment_analyst import SentimentAnalyst
        from app.agents.cross_team.compliance_officer import ComplianceOfficer
        from app.agents.cross_team.quant_analyst import QuantAnalyst

        agents = [
            MacroEconomist(db_session),
            SentimentAnalyst(db_session),
            ComplianceOfficer(db_session),
            QuantAnalyst(db_session),
        ]

        for agent in agents:
            assert agent.level == "N2"

    def test_cro_instantiates(self, db_session):
        from app.agents.cro import ChiefRiskOfficer

        cro = ChiefRiskOfficer(db_session)
        assert cro.level == "N1"
        assert cro.agent_name == "cro"

    def test_model_resolution(self):
        from app.agents.base_agent import resolve_agent_model

        assert resolve_agent_model("tecnico_b3") == "gpt-4.1"
        assert resolve_agent_model("fundamentalista_b3") == "gpt-5.1"
        assert resolve_agent_model("cio") == "gpt-5.2"
        assert resolve_agent_model("ticker_analyst_PETR4") == "gpt-5.1"
        assert resolve_agent_model("crypto_analyst_bitcoin") == "gpt-5.1"

    def test_reasoning_effort_config(self):
        assert settings.reasoning_effort["cio"] == "xhigh"
        assert settings.reasoning_effort["tecnico_b3"] == "none"
        assert settings.reasoning_effort["macro_economist"] == "high"
        assert settings.reasoning_effort["ticker_analyst"] == "medium"

    def test_budget_tracker_passed_to_agent(self, db_session):
        from app.agents.cross_team.macro_economist import MacroEconomist
        from app.services.token_cost import RunBudgetTracker

        budget = RunBudgetTracker(5.0)
        agent = MacroEconomist(db_session, budget_tracker=budget)
        assert agent.budget_tracker is budget


class TestAnalysisPipelineStructure:
    """Pipeline instantiation and structure (no API calls)."""

    def test_pipeline_creates_with_defaults(self):
        from app.agents.analysis_pipeline import AnalysisPipeline

        mock_factory = MagicMock()
        pipeline = AnalysisPipeline(mock_factory)
        assert pipeline.job_id  # UUID generated
        assert pipeline.trigger == "manual"
        assert pipeline.budget.remaining == settings.max_cost_per_run_usd

    def test_pipeline_accepts_custom_trigger(self):
        from app.agents.analysis_pipeline import AnalysisPipeline

        pipeline = AnalysisPipeline(MagicMock(), trigger="telegram")
        assert pipeline.trigger == "telegram"

    def test_truncate_helper(self):
        from app.agents.analysis_pipeline import _truncate

        assert _truncate("short") == "short"
        assert len(_truncate("x" * 5000, 100)) < 120
