"""
Sistema de eventos thread-safe para SSE.
Threads síncronas (BackgroundTasks) emitem eventos -> fila async -> SSE endpoint.
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_registry: dict[str, asyncio.Queue] = {}
_loop: asyncio.AbstractEventLoop | None = None


def register_job(job_id: str, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
    """Registra job e retorna fila de eventos."""
    q: asyncio.Queue = asyncio.Queue()
    _registry[job_id] = q
    global _loop
    _loop = loop
    logger.info(f"[progress] Job {job_id[:8]}... registrado")
    return q


def emit(job_id: str | None, step: str, message: str, percent: int = 0, **extra: Any):
    """Emite evento de progresso. Seguro para chamar de thread sincrona."""
    if not job_id or job_id not in _registry or not _loop:
        return
    event = {"step": step, "message": message, "percent": percent, **extra}
    try:
        _loop.call_soon_threadsafe(_registry[job_id].put_nowait, event)
    except Exception as e:
        logger.warning(f"[progress] Falha ao emitir evento: {e}")


def done(job_id: str | None):
    """Sinaliza conclusao e remove job do registro."""
    if not job_id:
        return
    emit(job_id, "done", "Analise concluida", 100)
    _registry.pop(job_id, None)
    logger.info(f"[progress] Job {job_id[:8]}... finalizado")


def get_queue(job_id: str) -> asyncio.Queue | None:
    """Retorna fila de eventos para o job, ou None se nao existir."""
    return _registry.get(job_id)


def is_active(job_id: str) -> bool:
    """Verifica se job ainda esta ativo."""
    return job_id in _registry
