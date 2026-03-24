"""AnalysisPipeline — Goldman Sachs-style 4-phase execution orchestrator.

Deterministic Python orchestrator (NOT an LLM agent). Executes 4 phases
in order, running agents in parallel within each phase and passing
context summaries between phases.

Phase 1 — Intelligence:  Macro + Sentiment + Risk Officers + Compliance (parallel)
Phase 2 — Team Analysis: HeadB3(+team) ‖ HeadCrypto(+team) (parallel between teams)
Phase 3 — Risk Consolidation: CRO + Quant (parallel)
Phase 4 — Final Decision: CIO
"""

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from app.config import settings
from app.models.db_models import AnalysisRun
from app.services.token_cost import RunBudgetTracker

logger = logging.getLogger(__name__)


def _truncate(text: str, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... truncado]"


def _safe_run(fn, label: str, job_id: str | None = None) -> str:
    """Execute a callable safely, returning error JSON on failure."""
    t0 = time.perf_counter()
    try:
        result = fn()
        elapsed = time.perf_counter() - t0
        logger.info(f"[pipeline] {label} concluído em {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.error(f"[pipeline] {label} falhou após {elapsed:.1f}s", exc_info=True)
        return json.dumps({"erro": f"{label} falhou: {e!s}"})


class AnalysisPipeline:
    """Orchestrates the 4-phase Goldman Sachs-style analysis."""

    def __init__(self, db_factory, job_id: str | None = None, trigger: str = "manual"):
        self.db_factory = db_factory  # SessionLocal callable
        self.job_id = job_id or str(uuid.uuid4())
        self.trigger = trigger
        self.budget = RunBudgetTracker(settings.max_cost_per_run_usd)
        self._results: dict[str, str] = {}

    def run_full(self) -> str:
        """Execute all 4 phases and return CIO's final decision."""
        from app.services import progress

        t0 = time.perf_counter()
        logger.info(f"[pipeline] Iniciando análise completa (job={self.job_id})")
        progress.emit(self.job_id, "pipeline_start", "Análise Goldman Sachs iniciada — 4 fases", 0)

        # Create analysis run record
        run_db = self.db_factory()
        try:
            run = AnalysisRun(
                id=self.job_id,
                started_at=datetime.now(),
                status="running",
                trigger=self.trigger,
            )
            run_db.add(run)
            run_db.commit()
        except Exception:
            run_db.rollback()
            logger.exception("[pipeline] Falha ao criar AnalysisRun")
        finally:
            run_db.close()

        # Phase 1
        progress.emit(self.job_id, "phase_start", "FASE 1 — Inteligência", 5,
                       phase=1, phase_name="intelligence")
        phase1 = self._run_phase1()
        self._update_run(phases_completed=1)

        if self.budget.exceeded:
            logger.warning("[pipeline] Budget exceeded after phase 1")
            self._finalize_run("budget_exceeded", t0)
            return json.dumps({"erro": "Budget excedido na fase 1", "parcial": phase1})

        # Phase 2
        progress.emit(self.job_id, "phase_start", "FASE 2 — Análise por Equipe", 20,
                       phase=2, phase_name="team_analysis")
        phase2 = self._run_phase2(phase1)
        self._update_run(phases_completed=2)

        if self.budget.exceeded:
            logger.warning("[pipeline] Budget exceeded after phase 2")
            self._finalize_run("budget_exceeded", t0)
            return json.dumps({"erro": "Budget excedido na fase 2", "parcial": {**phase1, **phase2}})

        # Phase 3
        progress.emit(self.job_id, "phase_start", "FASE 3 — Consolidação de Risco", 70,
                       phase=3, phase_name="risk_consolidation")
        phase3 = self._run_phase3(phase1, phase2)
        self._update_run(phases_completed=3)

        # Phase 4
        progress.emit(self.job_id, "phase_start", "FASE 4 — Decisão Final", 85,
                       phase=4, phase_name="final_decision")
        final = self._run_phase4(phase1, phase2, phase3)
        self._update_run(phases_completed=4)
        self._finalize_run("completed", t0)

        progress.emit(self.job_id, "pipeline_done", "Análise completa finalizada", 100)
        return final

    def _run_phase1(self) -> dict[str, str]:
        """Phase 1: Intelligence gathering (parallel)."""
        from app.agents.cross_team.compliance_officer import ComplianceOfficer
        from app.agents.cross_team.macro_economist import MacroEconomist
        from app.agents.cross_team.sentiment_analyst import SentimentAnalyst
        from app.agents.b3_team.risk_b3 import RiskB3
        from app.agents.crypto_team.risk_crypto import RiskCrypto

        tasks = {
            "macro": (MacroEconomist, lambda a: a.analyze(job_id=self.job_id)),
            "sentiment": (SentimentAnalyst, lambda a: a.analyze(job_id=self.job_id)),
            "risk_b3": (RiskB3, lambda a: a.analyze(job_id=self.job_id)),
            "risk_crypto": (RiskCrypto, lambda a: a.analyze(job_id=self.job_id)),
            "compliance": (ComplianceOfficer, lambda a: a.analyze(job_id=self.job_id)),
        }

        return self._run_parallel_agents(tasks)

    def _run_phase2(self, phase1: dict[str, str]) -> dict[str, str]:
        """Phase 2: Team analysis (B3 and Crypto in parallel).

        Each Head agent coordinates its own N2 team internally.
        For now, we use the existing B3Agent and CryptoAgent which already
        handle N3 deep dives. The N2 specialists (fundamentalista, tecnico, etc.)
        provide additional context injected into the Head's prompt.
        """
        from app.agents.b3_agent import B3Agent
        from app.agents.crypto_agent import CryptoAgent

        # Build context from phase 1
        context_parts = []
        if phase1.get("macro"):
            context_parts.append(f"[MACRO] {_truncate(phase1['macro'], 1000)}")
        if phase1.get("sentiment"):
            context_parts.append(f"[SENTIMENTO] {_truncate(phase1['sentiment'], 1000)}")
        portfolio_context = "\n".join(context_parts) if context_parts else ""

        def run_b3():
            db = self.db_factory()
            try:
                agent = B3Agent(db)
                return agent.analyze(portfolio_context, job_id=self.job_id)
            finally:
                db.close()

        def run_crypto():
            db = self.db_factory()
            try:
                agent = CryptoAgent(db)
                return agent.analyze(portfolio_context, job_id=self.job_id)
            finally:
                db.close()

        results = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(_safe_run, run_b3, "B3 Team", self.job_id): "b3_analysis",
                executor.submit(_safe_run, run_crypto, "Crypto Team", self.job_id): "crypto_analysis",
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    results[key] = json.dumps({"erro": str(e)})

        self._results.update(results)
        return results

    def _run_phase3(self, phase1: dict[str, str], phase2: dict[str, str]) -> dict[str, str]:
        """Phase 3: Risk consolidation (CRO + Quant in parallel)."""
        from app.agents.cro import ChiefRiskOfficer
        from app.agents.cross_team.quant_analyst import QuantAnalyst

        tasks = {
            "cro": (
                ChiefRiskOfficer,
                lambda a: a.analyze(
                    risk_b3_report=phase1.get("risk_b3", ""),
                    risk_crypto_report=phase1.get("risk_crypto", ""),
                    compliance_report=phase1.get("compliance", ""),
                    quant_report="",
                    job_id=self.job_id,
                ),
            ),
            "quant": (QuantAnalyst, lambda a: a.analyze(job_id=self.job_id)),
        }

        return self._run_parallel_agents(tasks)

    def _run_phase4(self, phase1: dict, phase2: dict, phase3: dict) -> str:
        """Phase 4: CIO final decision."""
        from app.agents.orchestrator import Orchestrator

        # Build comprehensive context for CIO
        context = f"""=== RELATÓRIOS DA EQUIPE ===

--- FASE 1: INTELIGÊNCIA ---
[Helena Bastos — Macro]: {_truncate(phase1.get('macro', 'N/A'), 1500)}
[Marina Leal — Sentimento]: {_truncate(phase1.get('sentiment', 'N/A'), 1000)}
[Rafael Tanaka — Compliance]: {_truncate(phase1.get('compliance', 'N/A'), 1000)}

--- FASE 2: ANÁLISE POR EQUIPE ---
[Marcelo Tavares — Mesa B3]: {_truncate(phase2.get('b3_analysis', 'N/A'), 2000)}
[Luísa Nakamoto — Mesa Crypto]: {_truncate(phase2.get('crypto_analysis', 'N/A'), 2000)}

--- FASE 3: RISCO ---
[Fernando Rocha — CRO]: {_truncate(phase3.get('cro', 'N/A'), 1500)}
[Eduardo Queiroz — Quant]: {_truncate(phase3.get('quant', 'N/A'), 1000)}
"""

        db = self.db_factory()
        try:
            cio = Orchestrator(db, job_id=self.job_id)

            prompt = f"""Você é Carlos Mendonça, CIO. Recebeu os relatórios de todas as equipes.

{context}

Com base em TODOS os relatórios acima:
1. Consulte o portfólio atual e alocação
2. Sintetize as recomendações de todas as equipes
3. Considere os vetos e alertas do CRO
4. Produza a decisão final de alocação no formato JSON do system prompt

Sua decisão é FINAL e deve considerar TODOS os inputs recebidos."""

            from app.services import progress
            progress.emit(self.job_id, "agent_start",
                "Carlos Mendonça (CIO) tomando decisão final...",
                agent="cio", percent=90)

            result = cio.call_model(prompt, max_rounds=10, job_id=self.job_id)
            cio.save_analysis(
                tipo_analise="analise_completa",
                input_resumo="Decisão final CIO — análise Goldman Sachs",
                output=result,
            )
            return result
        finally:
            db.close()

    def _run_parallel_agents(self, tasks: dict) -> dict[str, str]:
        """Run multiple agents in parallel, each with its own DB session."""
        results = {}

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {}
            for key, (agent_cls, run_fn) in tasks.items():
                def make_task(cls=agent_cls, fn=run_fn):
                    db = self.db_factory()
                    try:
                        agent = cls(db, budget_tracker=self.budget)
                        return fn(agent)
                    finally:
                        db.close()

                futures[executor.submit(_safe_run, make_task, key, self.job_id)] = key

            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    results[key] = json.dumps({"erro": str(e)})

        self._results.update(results)
        return results

    def _update_run(self, phases_completed: int):
        db = self.db_factory()
        try:
            run = db.query(AnalysisRun).filter_by(id=self.job_id).first()
            if run:
                run.phases_completed = phases_completed
                run.total_cost_usd = self.budget.spent
                run.total_agents = len(self._results)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("[pipeline] Falha ao atualizar AnalysisRun")
        finally:
            db.close()

    def _finalize_run(self, status: str, t0: float):
        elapsed = time.perf_counter() - t0
        logger.info(
            f"[pipeline] Finalizado: status={status}, "
            f"custo=${self.budget.spent:.4f}, tempo={elapsed:.1f}s"
        )
        db = self.db_factory()
        try:
            run = db.query(AnalysisRun).filter_by(id=self.job_id).first()
            if run:
                run.finished_at = datetime.now()
                run.status = status
                run.total_cost_usd = self.budget.spent
                run.total_agents = len(self._results)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("[pipeline] Falha ao finalizar AnalysisRun")
        finally:
            db.close()
