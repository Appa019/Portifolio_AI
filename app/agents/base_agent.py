import json
import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import threading

from openai import OpenAI, RateLimitError, APIStatusError, APITimeoutError
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.logging_config import set_job_id
from app.models.db_models import AgentContext, AnaliseIA
from app.services.token_cost import log_token_cost

logger = logging.getLogger(__name__)

# Limita N3 analysts simultâneos. Com pre-fetch, N3 não lança browsers (só cache hits + OpenAI).
# 7 permite todos os analysts de um N2 rodarem em paralelo.
N3_ANALYST_SEMAPHORE = threading.Semaphore(7)

# user_location compartilhado por todos os agentes
_USER_LOCATION = {
    "type": "approximate",
    "country": "BR",
    "city": "São Paulo",
    "timezone": "America/Sao_Paulo",
}

# Singleton OpenAI client — reutilizado por todos os agentes (connection pooling)
_openai_client: OpenAI | None = None
_openai_lock = threading.Lock()


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        with _openai_lock:
            if _openai_client is None:
                _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


@retry(
    retry=retry_if_exception_type((RateLimitError, APIStatusError, APITimeoutError)),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _call_openai_api(client: OpenAI, **kwargs):
    """Wrapper com retry automático para erros transientes da OpenAI API."""
    return client.responses.create(**kwargs)


def web_search_tool(context_size: str = "medium") -> dict:
    """Cria ferramenta web_search com search_context_size configurável.

    Args:
        context_size: "low" | "medium" | "high" — controla quanto conteúdo
                      web o modelo ingere por busca.
    """
    return {
        "type": "web_search",
        "search_context_size": context_size,
        "user_location": _USER_LOCATION,
    }


# Manter compatibilidade — constante padrão (medium)
WEB_SEARCH_TOOL = web_search_tool("medium")


class BaseAgent(ABC):
    """Classe base para todos os agentes IA usando OpenAI Responses API."""

    agent_name: str = "base"
    model: str = settings.modelo_subagente

    def __init__(self, db: Session):
        self.db = db
        self.client = _get_openai_client()
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    @abstractmethod
    def system_prompt(self) -> str:
        """Prompt de sistema do agente."""

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Lista de ferramentas disponíveis para o agente."""

    @abstractmethod
    def execute_function(self, name: str, args: dict) -> str:
        """Executa uma function call e retorna o resultado como string."""

    def call_model(self, user_input: str, max_rounds: int = 10, job_id: str | None = None) -> str:
        """Loop agentic: chama modelo, executa function calls, retorna resposta final.

        Pattern A (oficial OpenAI): input_list acumulada entre rounds.
        previous_response_id usado APENAS no round 0 para continuidade cross-execution.
        """
        t0 = time.perf_counter()
        set_job_id(job_id)

        tools = self.get_tools()
        context = self._load_context()
        # previous_response_id só para continuidade cross-execution (round 0)
        cross_exec_prev_id = context.last_response_id if context else None
        last_response_id: str | None = None

        # Injetar contexto da análise anterior (se disponível)
        if context and context.resumo_contexto and context.last_execution:
            data_anterior = context.last_execution.strftime("%Y-%m-%d")
            context_prefix = (
                f"[CONTEXTO DA SUA ANÁLISE ANTERIOR ({data_anterior})]:\n"
                f"{context.resumo_contexto[:1500]}\n\n"
                f"[NOVA ANÁLISE]:\n"
            )
            input_list = [{"role": "user", "content": context_prefix + user_input}]
        else:
            input_list = [{"role": "user", "content": user_input}]

        # Resolve reasoning effort uma vez (N3 usa agent_name base sem ticker)
        agent_key = self.agent_name.split("_", 2)
        if len(agent_key) >= 2 and agent_key[0] in ("ticker", "crypto") and agent_key[1] == "analyst":
            effort_key = f"{agent_key[0]}_analyst"
        else:
            effort_key = self.agent_name
        effort = settings.reasoning_effort.get(effort_key, "none")

        logger.info(f"[{self.agent_name}] call_model iniciado (model={self.model}, effort={effort})")

        for round_num in range(max_rounds):
            logger.info(f"[{self.agent_name}] Round {round_num + 1}/{max_rounds}")

            if job_id:
                from app.ensemble import progress
                progress.emit(job_id, "agent_thinking",
                    f"[{self.agent_name}] Round {round_num + 1}...",
                    agent=self.agent_name, round=round_num + 1)

            kwargs = {
                "model": self.model,
                "instructions": self.system_prompt(),
                "tools": tools,
                "input": input_list,
            }
            if effort != "none":
                kwargs["reasoning"] = {"effort": effort}

            # previous_response_id APENAS no round 0 (cross-execution)
            if round_num == 0 and cross_exec_prev_id:
                kwargs["previous_response_id"] = cross_exec_prev_id

            t_api = time.perf_counter()
            try:
                response = _call_openai_api(self.client, **kwargs)
            except Exception as e:
                if cross_exec_prev_id and "previous_response_id" in str(e).lower():
                    logger.warning(f"[{self.agent_name}] Stale response_id, retrying without it")
                    if job_id:
                        from app.ensemble import progress
                        progress.emit(job_id, "agent_thinking",
                            f"[{self.agent_name}] Contexto anterior expirado, reiniciando...",
                            agent=self.agent_name)
                    kwargs.pop("previous_response_id", None)
                    cross_exec_prev_id = None
                    response = _call_openai_api(self.client, **kwargs)
                else:
                    raise
            api_elapsed = time.perf_counter() - t_api

            last_response_id = response.id

            # Log token usage
            if response.usage:
                self._total_input_tokens += response.usage.input_tokens
                self._total_output_tokens += response.usage.output_tokens
                logger.info(
                    f"[{self.agent_name}] Round {round_num + 1} API: {api_elapsed:.1f}s | "
                    f"tokens in={response.usage.input_tokens} out={response.usage.output_tokens}"
                )

            # Check for function calls
            function_calls = [item for item in response.output if item.type == "function_call"]

            if not function_calls:
                # Resposta final — salvar contexto e retornar
                final_text = response.output_text or ""
                self._save_context(last_response_id, resumo=final_text[:2000])
                self._log_costs()
                elapsed = time.perf_counter() - t0
                logger.info(
                    f"[{self.agent_name}] call_model concluído em {elapsed:.1f}s | "
                    f"{round_num + 1} rounds | tokens total in={self._total_input_tokens} out={self._total_output_tokens}"
                )
                return final_text

            # Log function calls recebidas
            fc_names = [fc.name for fc in function_calls]
            logger.info(f"[{self.agent_name}] Round {round_num + 1} function_calls: {fc_names}")

            # Pattern A: acumular TODOS os output items (incluindo reasoning)
            input_list = input_list + list(response.output)

            # Executar function calls (paralelo se >1)
            if len(function_calls) > 1:
                fco_results = self._execute_parallel(function_calls, job_id)
            else:
                fco_results = self._execute_sequential(function_calls, job_id)

            input_list.extend(fco_results)

        # Max rounds reached
        final_text = response.output_text or ""
        self._save_context(last_response_id, resumo=final_text[:2000])
        self._log_costs()
        elapsed = time.perf_counter() - t0
        logger.warning(f"[{self.agent_name}] max_rounds atingido ({max_rounds}) após {elapsed:.1f}s")
        return final_text

    def _execute_one_function(self, fc_item, job_id: str | None) -> dict:
        """Executa uma function_call e retorna o function_call_output dict."""
        set_job_id(job_id)

        if job_id:
            from app.ensemble import progress
            progress.emit(job_id, "function_call",
                f"[{self.agent_name}] Executando: {fc_item.name}",
                agent=self.agent_name, function=fc_item.name)

        t0 = time.perf_counter()
        try:
            args = json.loads(fc_item.arguments)
            result = self.execute_function(fc_item.name, args)
        except Exception:
            logger.exception(f"[{self.agent_name}] Erro executando {fc_item.name}")
            result = json.dumps({"erro": "Erro interno na execução da função"})

        elapsed = time.perf_counter() - t0
        logger.info(f"[{self.agent_name}] {fc_item.name} concluído em {elapsed:.1f}s")

        output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        return {"type": "function_call_output", "call_id": fc_item.call_id, "output": output}

    def _execute_sequential(self, function_calls: list, job_id: str | None) -> list[dict]:
        """Executa function calls sequencialmente."""
        return [self._execute_one_function(fc, job_id) for fc in function_calls]

    def _execute_parallel(self, function_calls: list, job_id: str | None) -> list[dict]:
        """Executa múltiplas function calls em paralelo (ThreadPoolExecutor).

        NOTA: As function calls compartilham self.db. Para operações que criam
        sub-agentes (como analyze_stock_deep), cada sub-agente deve criar sua
        própria session via SessionLocal() para thread-safety.
        """
        max_workers = min(len(function_calls), 20)
        results: dict[str, dict] = {}  # call_id → fco dict

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._execute_one_function, fc, job_id): fc.call_id
                for fc in function_calls
            }
            for future in as_completed(futures):
                call_id = futures[future]
                try:
                    results[call_id] = future.result()
                except Exception:
                    logger.exception(f"[{self.agent_name}] Parallel exec error ({call_id})")
                    results[call_id] = {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"erro": "Erro interno na execução paralela"}),
                    }

        # G7: Agregar erros e emitir warning se maioria falhou
        error_count = sum(1 for r in results.values() if '"erro"' in r.get("output", ""))
        if error_count > len(function_calls) // 2:
            logger.warning(
                f"[{self.agent_name}] {error_count}/{len(function_calls)} function calls falharam"
            )
            if job_id:
                from app.ensemble import progress
                progress.emit(job_id, "warning",
                    f"[{self.agent_name}] {error_count}/{len(function_calls)} chamadas falharam",
                    agent=self.agent_name)

        # Manter ordem original das function_calls
        return [results[fc.call_id] for fc in function_calls]

    def save_analysis(self, tipo_analise: str, input_resumo: str, output: str, score: float | None = None, acao: str | None = None):
        """Persiste resultado em AnaliseIA."""
        analise = AnaliseIA(
            data=datetime.now(),
            tipo_analise=tipo_analise,
            agente=self.agent_name,
            input_resumo=input_resumo[:500],
            output_completo=output,
            score_confianca=score,
            acao_recomendada=acao,
        )
        self.db.add(analise)
        try:
            self.db.commit()
            self.db.refresh(analise)
        except Exception:
            self.db.rollback()
            # Log at ERROR (not silent) but do NOT re-raise: the analysis result was
            # already computed by the LLM and must still reach the orchestrator.
            # Re-raising here would cause _run_sub_agent() to swallow the result and
            # return {"erro": "..."} instead of the actual analysis.
            logger.error(
                f"[{self.agent_name}] Falha ao persistir análise no banco — "
                "resultado NÃO salvo mas retornado ao chamador normalmente.",
                exc_info=True,
            )
        return analise

    def _load_context(self) -> AgentContext | None:
        return self.db.query(AgentContext).filter_by(agent_name=self.agent_name).first()

    def _save_context(self, response_id: str, resumo: str = ""):
        ctx = self._load_context()
        if ctx:
            ctx.last_response_id = response_id
            ctx.last_execution = datetime.now()
            ctx.execution_count += 1
            if resumo:
                ctx.resumo_contexto = resumo
        else:
            ctx = AgentContext(
                agent_name=self.agent_name,
                last_response_id=response_id,
                last_execution=datetime.now(),
                execution_count=1,
                resumo_contexto=resumo or None,
            )
            self.db.add(ctx)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception(f"[{self.agent_name}] Falha ao salvar contexto")

    def _log_costs(self):
        if self._total_input_tokens > 0 or self._total_output_tokens > 0:
            log_token_cost(
                db=self.db,
                agente=self.agent_name,
                modelo=self.model,
                tokens_input=self._total_input_tokens,
                tokens_output=self._total_output_tokens,
                descricao=f"Execução {self.agent_name}",
            )
            self._total_input_tokens = 0
            self._total_output_tokens = 0
