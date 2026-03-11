"""
Sistema de eventos thread-safe para SSE.
Threads síncronas (BackgroundTasks) emitem eventos -> fila async -> SSE endpoint.
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Registry armazena {job_id: {"queue": Queue, "loop": loop}} — loop por job, não global
_registry: dict[str, dict] = {}


def register_job(job_id: str, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
    """Registra job e retorna fila de eventos."""
    q: asyncio.Queue = asyncio.Queue()
    _registry[job_id] = {"queue": q, "loop": loop}
    logger.info(f"[progress] Job {job_id[:8]}... registrado")
    return q


def emit(job_id: str | None, step: str, message: str, percent: int = 0, **extra: Any):
    """Emite evento de progresso. Seguro para chamar de thread sincrona."""
    if not job_id:
        return
    entry = _registry.get(job_id)
    if not entry:
        return
    event = {"step": step, "message": message, "percent": percent, **extra}
    try:
        entry["loop"].call_soon_threadsafe(entry["queue"].put_nowait, event)
    except Exception as e:
        logger.warning(f"[progress] Falha ao emitir evento: {e}")


def done(job_id: str | None):
    """Sinaliza conclusao e remove job do registro."""
    if not job_id:
        return
    emit(job_id, "done", "Analise concluida", 100)
    _registry.pop(job_id, None)
    logger.info(f"[progress] Job {job_id[:8]}... finalizado")


def cleanup(job_id: str):
    """Remove job do registro sem emitir evento (cliente já desconectou)."""
    _registry.pop(job_id, None)
    logger.info(f"[progress] Job {job_id[:8]}... removido por disconnect do cliente")


def get_queue(job_id: str) -> asyncio.Queue | None:
    """Retorna fila de eventos para o job, ou None se nao existir."""
    entry = _registry.get(job_id)
    return entry["queue"] if entry else None


def is_active(job_id: str) -> bool:
    """Verifica se job ainda esta ativo."""
    return job_id in _registry
