import json
import logging
import time

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, web_search_tool
from app.prompts.orchestrator_prompt import get_prompt as _orchestrator_prompt
from app.agents.b3_agent import B3Agent
from app.agents.crypto_agent import CryptoAgent
from app.agents.stats_agent import StatsAgent
from app.config import settings
from app.services.market_data import get_macro_data
from app.services.portfolio_service import (
    get_portfolio_allocation,
    get_portfolio_assets,
    get_portfolio_summary,
)

logger = logging.getLogger(__name__)

class Orchestrator(BaseAgent):
    agent_name = "orchestrator"
    model = settings.modelo_orquestrador

    def __init__(self, db: Session, job_id: str | None = None):
        super().__init__(db)
        self._job_id = job_id

    def _run_sub_agent(self, fn, agent_label: str) -> str:
        """Executa função de sub-agente sem timeout — aguarda conclusão."""
        t0 = time.perf_counter()
        try:
            result = fn()
            elapsed = time.perf_counter() - t0
            logger.info(f"[orchestrator] {agent_label} concluído em {elapsed:.1f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(f"[orchestrator] {agent_label} falhou após {elapsed:.1f}s", exc_info=True)
            from app.ensemble import progress
            progress.emit(self._job_id, "error",
                f"{agent_label} falhou: {type(e).__name__}")
            return json.dumps({"erro": f"{agent_label} falhou: {e!s}"})

    def system_prompt(self) -> str:
        return _orchestrator_prompt()

    def get_tools(self) -> list[dict]:
        return [
            web_search_tool("low"),  # Orchestrator raramente usa web_search direto
            {
                "type": "function",
                "name": "get_portfolio_summary",
                "description": "Retorna resumo do portfólio: valor total, rentabilidade, alocação por classe",
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
                "name": "get_portfolio_assets",
                "description": "Lista detalhada de todos os ativos no portfólio com preço atual, P&L e lockup",
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
                "name": "get_portfolio_allocation",
                "description": "Alocação atual vs alvo (50% ações, 20% crypto, 30% CDB) com desvios",
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
                "name": "run_b3_analysis",
                "description": "Executa o sub-agente de análise de ações B3. Retorna análise completa do mercado brasileiro",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "portfolio_context": {"type": "string", "description": "Contexto resumido do portfólio para o sub-agente"}
                    },
                    "required": ["portfolio_context"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "run_crypto_analysis",
                "description": "Executa o sub-agente de análise de criptoativos. Retorna análise completa do mercado cripto",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "portfolio_context": {"type": "string", "description": "Contexto resumido do portfólio para o sub-agente"}
                    },
                    "required": ["portfolio_context"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "run_stats_analysis",
                "description": "Executa o sub-agente estatístico com os tickers a serem analisados quantitativamente",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tickers_context": {"type": "string", "description": "Lista de tickers e contexto para análise quantitativa"}
                    },
                    "required": ["tickers_context"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_macro_data",
                "description": "Dados macroeconômicos: Selic, CDI, IPCA acumulado 12m, câmbio PTAX",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def _validate_n2_output(self, result: str, agent_name: str) -> str:
        """G4: Valida que output do N2 é JSON parseável."""
        try:
            json.loads(result)
            return result  # JSON válido, retorna como está
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[{agent_name}] Output não-JSON recebido, wrapping")
            return json.dumps({
                "status": "analise_texto",
                "agente": agent_name,
                "conteudo": result[:3000],
            }, ensure_ascii=False)

    def _abbreviate_portfolio_context(self, full_context: str, max_chars: int = 2000) -> str:
        """G5: Resume portfolio context para passar a N2 agents."""
        if len(full_context) <= max_chars:
            return full_context
        return full_context[:max_chars] + "\n[... contexto truncado, consulte ferramentas para detalhes]"

    def execute_function(self, name: str, args: dict) -> str:
        if name == "get_portfolio_summary":
            data = get_portfolio_summary(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "get_portfolio_assets":
            data = get_portfolio_assets(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "get_portfolio_allocation":
            data = get_portfolio_allocation(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        if name == "run_b3_analysis":
            logger.info("[orchestrator] Iniciando sub-agente B3...")
            from app.database import SessionLocal
            from app.ensemble import progress
            progress.emit(self._job_id, "agent_start", "Iniciando B3 Agent...", 15)
            ctx = self._abbreviate_portfolio_context(args["portfolio_context"])
            sub_db = SessionLocal()
            try:
                agent = B3Agent(sub_db)
                raw = self._run_sub_agent(
                    lambda: agent.analyze(ctx, job_id=self._job_id),
                    "B3 Agent",
                )
            finally:
                sub_db.close()
            return self._validate_n2_output(raw, "b3_agent")

        if name == "run_crypto_analysis":
            logger.info("[orchestrator] Iniciando sub-agente Crypto...")
            from app.database import SessionLocal
            from app.ensemble import progress
            progress.emit(self._job_id, "agent_start", "Iniciando Crypto Agent...", 35)
            ctx = self._abbreviate_portfolio_context(args["portfolio_context"])
            sub_db = SessionLocal()
            try:
                agent = CryptoAgent(sub_db)
                raw = self._run_sub_agent(
                    lambda: agent.analyze(ctx, job_id=self._job_id),
                    "Crypto Agent",
                )
            finally:
                sub_db.close()
            return self._validate_n2_output(raw, "crypto_agent")

        if name == "run_stats_analysis":
            logger.info("[orchestrator] Iniciando sub-agente Estatístico + Ensemble...")
            from app.database import SessionLocal
            from app.ensemble import progress
            progress.emit(self._job_id, "agent_start", "Iniciando Stats Agent + Ensemble...", 55)
            sub_db = SessionLocal()
            try:
                agent = StatsAgent(sub_db)
                raw = self._run_sub_agent(
                    lambda: agent.analyze(args["tickers_context"], job_id=self._job_id),
                    "Stats Agent",
                )
            finally:
                sub_db.close()
            return self._validate_n2_output(raw, "stats_agent")

        if name == "get_macro_data":
            data = get_macro_data(self.db)
            return json.dumps(data, ensure_ascii=False, default=str)

        return json.dumps({"erro": f"Função desconhecida: {name}"})

    def run_full_analysis(self, job_id: str | None = None) -> str:
        """Análise completa semanal — coordena todos os sub-agentes."""
        from app.ensemble import progress

        self._job_id = job_id or self._job_id
        logger.info("[orchestrator] Iniciando análise completa")
        progress.emit(self._job_id, "orchestrator_start", "Orquestrador iniciou análise completa", 0)

        prompt = """Execute uma análise completa do portfólio e do mercado.

Passos obrigatórios:
1. Consulte o resumo e ativos do portfólio atual
2. Verifique a alocação atual vs alvo
3. Busque dados macroeconômicos (Selic, CDI, IPCA, câmbio)
4. Execute análise do mercado B3 via sub-agente
5. Execute análise do mercado cripto via sub-agente
6. Execute análise estatística dos tickers relevantes
7. Sintetize tudo em recomendação final no formato JSON do system prompt

Considere lockups ativos, desvios de alocação e oportunidades identificadas."""

        result = self.call_model(prompt, max_rounds=15, job_id=self._job_id)
        self.save_analysis(
            tipo_analise="analise_completa",
            input_resumo="Análise semanal completa",
            output=result,
        )
        logger.info("[orchestrator] Análise completa finalizada")
        return result

    def run_aporte_analysis(self, valor: float, job_id: str | None = None) -> str:
        """Análise de como alocar um novo aporte."""
        from app.ensemble import progress

        self._job_id = job_id or self._job_id
        logger.info(f"[orchestrator] Análise de aporte: R${valor:,.2f}")
        progress.emit(self._job_id, "orchestrator_start", f"Análise de aporte R${valor:,.2f} iniciada", 0)

        prompt = f"""O investidor deseja aportar R${valor:,.2f} no portfólio.

Passos obrigatórios:
1. Consulte o portfólio atual e a alocação
2. Identifique desvios da alocação alvo (50% ações, 20% crypto, 30% CDB)
3. Busque dados macro para contexto
4. Execute análise B3 e crypto para identificar melhores oportunidades agora
5. Recomende como distribuir os R${valor:,.2f} para:
   - Corrigir desvios de alocação
   - Aproveitar as melhores oportunidades identificadas
   - Manter perfil moderado

Retorne no formato JSON do system prompt, com foco em como distribuir o aporte."""

        result = self.call_model(prompt, max_rounds=15, job_id=self._job_id)
        self.save_analysis(
            tipo_analise="analise_aporte",
            input_resumo=f"Aporte de R${valor:,.2f}",
            output=result,
        )
        return result
