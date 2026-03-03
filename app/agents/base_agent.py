import json
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import datetime

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models.db_models import AgentContext, AnaliseIA
from app.services.token_cost import log_token_cost

logger = logging.getLogger(__name__)

# user_location compartilhado por todos os agentes
_USER_LOCATION = {
    "type": "approximate",
    "country": "BR",
    "city": "São Paulo",
    "timezone": "America/Sao_Paulo",
}


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
        self.client = OpenAI(api_key=settings.openai_api_key)
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

            try:
                response = self.client.responses.create(**kwargs)
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
                    response = self.client.responses.create(**kwargs)
                else:
                    raise

            last_response_id = response.id

            # Log token usage
            if response.usage:
                self._total_input_tokens += response.usage.input_tokens
                self._total_output_tokens += response.usage.output_tokens

            # Check for function calls
            function_calls = [item for item in response.output if item.type == "function_call"]

            if not function_calls:
                # Resposta final — salvar contexto e retornar
                final_text = response.output_text or ""
                self._save_context(last_response_id, resumo=final_text[:2000])
                self._log_costs()
                return final_text

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
        logger.warning(f"[{self.agent_name}] max_rounds atingido ({max_rounds})")
        return final_text

    def _execute_one_function(self, fc_item, job_id: str | None) -> dict:
        """Executa uma function_call e retorna o function_call_output dict."""
        if job_id:
            from app.ensemble import progress
            progress.emit(job_id, "function_call",
                f"[{self.agent_name}] Executando: {fc_item.name}",
                agent=self.agent_name, function=fc_item.name)

        try:
            args = json.loads(fc_item.arguments)
            result = self.execute_function(fc_item.name, args)
        except Exception as e:
            logger.error(f"[{self.agent_name}] Erro executando {fc_item.name}: {e}")
            result = json.dumps({"erro": str(e)})

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
        max_workers = min(len(function_calls), 4)
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
                except Exception as e:
                    logger.error(f"[{self.agent_name}] Parallel exec error ({call_id}): {e}")
                    results[call_id] = {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"erro": str(e)}),
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
        self.db.commit()
        self.db.refresh(analise)
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
        self.db.commit()

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
